import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sqlite3
import hashlib
import io
import re
import os
import tempfile
import unicodedata
from datetime import datetime, timedelta, timezone

# Tenta importar bibliotecas externas opcionais
try:
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

try:
    from fpdf import FPDF
except ImportError:
    FPDF = None

# ===========================================
# CONFIGURAÇÃO INICIAL E ESTILOS
# ===========================================
st.set_page_config(
    page_title="SMDET - Gestão POT",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilo CSS Personalizado
st.markdown("""
<style>
    .header-container {
        text-align: center;
        padding-bottom: 20px;
        border-bottom: 2px solid #ddd;
        margin-bottom: 30px;
    }
    .header-secretaria {
        color: #555;
        font-size: 1rem;
        margin-bottom: 5px;
        font-weight: 500;
    }
    .header-programa {
        color: #1E3A8A;
        font-size: 1.5rem;
        font-weight: bold;
        margin-bottom: 5px;
    }
    .header-sistema {
        color: #2563EB;
        font-size: 1.8rem;
        font-weight: bold;
    }
    .stAlert {
        padding: 10px;
        border-radius: 5px;
    }
    .user-row {
        padding: 10px 0;
        border-bottom: 1px solid #eee;
    }
    .status-badge {
        background-color: #d1fae5;
        color: #065f46;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.8em;
    }
    .error-badge {
        background-color: #fee2e2;
        color: #991b1b;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.8em;
    }
</style>
""", unsafe_allow_html=True)

# Função para renderizar o cabeçalho padrão
def render_header():
    st.markdown("""
        <div class="header-container">
            <div class="header-secretaria">Secretaria Municipal de Desenvolvimento Econômico e Trabalho (SMDET)</div>
            <div class="header-programa">Programa Operação Trabalho (POT)</div>
            <div class="header-sistema">Sistema de Gestão e Monitoramento de Pagamentos</div>
        </div>
    """, unsafe_allow_html=True)

# ===========================================
# GESTÃO DE BANCO DE DADOS (SQLite)
# ===========================================

DB_FILE = 'pot_system.db'

def init_db():
    # check_same_thread=False é crucial para Streamlit em ambiente local/cloud simples
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            password TEXT,
            role TEXT,
            name TEXT,
            first_login INTEGER DEFAULT 1
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            programa TEXT,
            gerenciadora TEXT,
            num_cartao TEXT,
            nome TEXT,
            cpf TEXT,
            rg TEXT,
            valor_pagto REAL,
            data_pagto TEXT,
            qtd_dias INTEGER,
            mes_ref TEXT,
            ano_ref TEXT,
            tipo_arquivo TEXT,
            arquivo_origem TEXT,
            linha_arquivo INTEGER,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS bank_discrepancies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cartao TEXT,
            nome_sis TEXT,
            nome_bb TEXT,
            cpf_sis TEXT,
            cpf_bb TEXT,
            divergencia TEXT,
            arquivo_origem TEXT,
            tipo_erro TEXT, 
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT,
            action TEXT,
            details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Criar usuário Admin padrão se não existir
    c.execute("SELECT * FROM users WHERE email = 'admin@prefeitura.sp.gov.br'")
    if not c.fetchone():
        default_pass = hashlib.sha256('smdet2025'.encode()).hexdigest()
        c.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?)", 
                  ('admin@prefeitura.sp.gov.br', default_pass, 'admin_ti', 'Administrador TI', 0))
    
    conn.commit()
    conn.close()

def get_db_connection():
    # Retorna conexão configurada para evitar erros de thread no Streamlit
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def log_action(user_email, action, details):
    """Registra uma ação no log de auditoria."""
    try:
        conn = get_db_connection()
        conn.execute("INSERT INTO audit_logs (user_email, action, details) VALUES (?, ?, ?)", 
                     (user_email, action, details))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Erro ao logar: {e}")

# ===========================================
# CONTEÚDO DOS MANUAIS
# ===========================================

def get_manual_content(tipo):
    # (Mantido igual, apenas resumido aqui para economizar espaço se necessário, 
    # mas o código completo incluirá todo o texto conforme solicitado)
    if tipo == "usuario":
        return """
        # Manual Operacional Básico - Sistema POT
        
        ## 1. Visão Geral
        Bem-vindo ao Sistema de Gestão e Monitoramento de Pagamentos do POT.
        
        ## 2. Persistência de Dados
        - Todos os dados enviados são salvos automaticamente no Banco de Dados Seguro.
        - Ao recarregar a página (F5), os arquivos no campo de upload somem, mas os dados PROCESSADOS continuam salvos nas abas de Dashboard e Análise.

        ## 3. Upload e Validação
        - Navegue até a aba **Upload e Processamento**.
        - O sistema valida automaticamente CPFs duplicados e conflitos de cartão.
        - Erros críticos aparecerão em vermelho na aba **Análise e Correção**.
        """
    elif tipo == "admin_equipe":
        return """
        # Manual de Gestão - Admin Equipe
        
        ## 1. Gestão de Usuários
        - Cadastre novos analistas com e-mail institucional.
        - Utilize o botão **🗑️** para excluir usuários desligados.
        - Utilize o botão **🔄** para resetar a senha de quem esqueceu (volta para `mudar123`).

        ## 2. Correção de Dados (Malha Fina)
        - Na aba **Análise e Correção**, você pode editar diretamente os dados errados.
        - Ao clicar em "Salvar", o sistema atualiza o banco oficial.
        - **Atenção:** A detecção de erros roda automaticamente após cada salvamento.
        """
    elif tipo == "admin_ti":
        return """
        # Manual Técnico (TI)
        
        ## 1. Auditoria e Logs
        - Todas as ações (Login, Upload, Edição, Exclusão de Usuário) são logadas.
        - Acesse a aba **Administração TI** para ver e baixar os logs.
        
        ## 2. Reset do Sistema
        - O botão "Limpar Dados" apaga todas as tabelas de pagamentos, mas mantém os usuários e logs.
        """
    return ""

def create_manual_pdf(title, content):
    if FPDF is None: return None
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 8, sanitize_text("Prefeitura de São Paulo"), 0, 1, 'C')
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 8, sanitize_text("Secretaria Municipal do Desenvolvimento Econômico e Trabalho"), 0, 1, 'C')
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, sanitize_text(title), 0, 1, 'C')
    pdf.ln(10)
    pdf.set_font("Arial", '', 12)
    lines = content.split('\n')
    for line in lines:
        clean_line = line.strip()
        if clean_line.startswith('# '):
            pdf.set_font("Arial", 'B', 14); pdf.ln(5)
            pdf.multi_cell(0, 10, sanitize_text(clean_line.replace('# ', '')))
            pdf.set_font("Arial", '', 12)
        elif clean_line.startswith('## '):
            pdf.set_font("Arial", 'B', 12); pdf.ln(3)
            pdf.multi_cell(0, 10, sanitize_text(clean_line.replace('## ', '')))
            pdf.set_font("Arial", '', 12)
        elif clean_line.startswith('- '):
             pdf.multi_cell(0, 8, sanitize_text("  - " + clean_line.replace('- ', '')))
        else:
            pdf.multi_cell(0, 8, sanitize_text(clean_line))
    return pdf.output(dest='S').encode('latin-1', 'replace')

# ===========================================
# FUNÇÕES UTILITÁRIAS
# ===========================================

def sanitize_text(text):
    if not isinstance(text, str): return str(text)
    text = text.replace('–', '-').replace('—', '-').replace('“', '"').replace('”', '"')
    return text.encode('latin-1', 'replace').decode('latin-1')

def remove_accents(input_str):
    if not isinstance(input_str, str): return str(input_str)
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)]).upper().strip()

def get_brasilia_time():
    return datetime.now(timezone(timedelta(hours=-3)))

# ===========================================
# LÓGICA DE NEGÓCIO
# ===========================================

COLUMN_MAP = {
    'num cartao': 'num_cartao', 'numcartao': 'num_cartao', 'numcartão': 'num_cartao', 
    'código': 'num_cartao', 'codigo': 'num_cartao', 'c?igo': 'num_cartao',
    'nome': 'nome', 'nome do beneficiário': 'nome', 'participante': 'nome',
    'cpf': 'cpf', 'rg': 'rg',
    'valor pagto': 'valor_pagto', 'valorpagto': 'valor_pagto', 'valor total': 'valor_pagto',
    'dias a apagar': 'qtd_dias', 'dias': 'qtd_dias',
    'data pagto': 'data_pagto', 'datapagto': 'data_pagto',
    'projeto': 'programa', 'mês': 'mes_ref', 'mes': 'mes_ref',
    'gerenciadora': 'gerenciadora', 'entidade': 'gerenciadora', 'parceiro': 'gerenciadora', 'os': 'gerenciadora'
}

def remove_total_row(df):
    if df.empty: return df
    last_idx = df.index[-1]
    id_cols = ['num_cartao', 'cpf', 'nome', 'rg']
    is_id_empty = True
    for col in id_cols:
        if col in df.columns:
            val = df.at[last_idx, col]
            if pd.notna(val) and str(val).strip() != '' and str(val).strip().lower() != 'nan':
                is_id_empty = False
                break
    if is_id_empty: df = df.drop(last_idx)
    return df

def parse_bb_txt_cadastro(file):
    colspecs = [(0, 11), (11, 42), (42, 52), (52, 92), (92, 104), (104, 119)]
    names = ['tipo', 'projeto_bb', 'num_cartao', 'nome_bb', 'rg_bb', 'cpf_bb']
    file.seek(0)
    df = pd.read_fwf(file, colspecs=colspecs, names=names, dtype=str, encoding='latin1')
    if 'tipo' in df.columns:
        df = df[df['tipo'].astype(str).str.strip() == '1'].copy()
    df['num_cartao'] = df['num_cartao'].str.strip()
    df['nome_bb'] = df['nome_bb'].str.strip()
    df['cpf_bb'] = df['cpf_bb'].str.replace(r'\D', '', regex=True)
    return df

def standardize_dataframe(df, filename):
    df['linha_arquivo'] = df.index + 2
    df.columns = [str(c).strip() for c in df.columns]
    
    rename_dict = {}
    for col in df.columns:
        col_lower = col.lower()
        if col_lower in COLUMN_MAP:
            rename_dict[col] = COLUMN_MAP[col_lower]
        else:
            for key, val in COLUMN_MAP.items():
                if key in col_lower:
                    rename_dict[col] = val
                    break
    
    df = df.rename(columns=rename_dict)
    df = df.loc[:, ~df.columns.duplicated()]
    
    filename_upper = filename.upper()
    programa = 'DESCONHECIDO'
    if 'ADS' in filename_upper: programa = 'ADS'
    elif 'ABAE' in filename_upper: programa = 'ABAE'
    elif 'ABASTECE' in filename_upper or 'ABAST' in filename_upper: programa = 'ABASTECE'
    elif 'GAE' in filename_upper: programa = 'GAE'
    elif 'ESPORTE' in filename_upper: programa = 'ESPORTES'
    elif 'ZELADO' in filename_upper: programa = 'ZELADORIA'
    elif 'AGRICULTURA' in filename_upper: programa = 'AGRICULTURA'
    elif 'DEFESA' in filename_upper: programa = 'DEFESA CIVIL'
    
    if 'programa' not in df.columns or df['programa'].isnull().all():
        df['programa'] = programa

    if 'gerenciadora' not in df.columns:
        df['gerenciadora'] = 'NÃO IDENTIFICADA'
    else:
        df['gerenciadora'] = df['gerenciadora'].fillna('NÃO IDENTIFICADA')
        
    meses = ['JANEIRO', 'FEVEREIRO', 'MARÇO', 'ABRIL', 'MAIO', 'JUNHO', 'JULHO', 'AGOSTO', 'SETEMBRO', 'OUTUBRO', 'NOVEMBRO', 'DEZEMBRO']
    mes_ref = 'N/A'
    for mes in meses:
        if mes in filename_upper:
            mes_ref = mes
            break
            
    if 'mes_ref' not in df.columns:
        df['mes_ref'] = mes_ref
        
    essential_check = ['num_cartao', 'nome', 'cpf', 'rg', 'valor_pagto']
    for col in essential_check:
        if col not in df.columns: df[col] = None 

    df = remove_total_row(df)

    # Limpeza básica
    if 'num_cartao' in df.columns:
        df['num_cartao'] = df['num_cartao'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    if 'cpf' in df.columns:
        df['cpf'] = df['cpf'].astype(str).str.replace(r'\D', '', regex=True).replace('nan', '')
    
    def clean_currency(x):
        if isinstance(x, str):
            x = x.replace('R$', '').replace(' ', '')
            if ',' in x and '.' in x: x = x.replace('.', '').replace(',', '.')
            elif ',' in x: x = x.replace(',', '.')
        try: return float(x)
        except: return 0.0
            
    if 'valor_pagto' in df.columns:
        df['valor_pagto'] = df['valor_pagto'].apply(clean_currency)
        
    df['arquivo_origem'] = filename
    cols_to_keep = ['programa', 'gerenciadora', 'num_cartao', 'nome', 'cpf', 'rg', 'valor_pagto', 'data_pagto', 'qtd_dias', 'mes_ref', 'ano_ref', 'arquivo_origem', 'linha_arquivo']
    final_cols = [c for c in cols_to_keep if c in df.columns]
    return df[final_cols]

def detect_critical_duplicates(df):
    """
    Detecta duplicidades críticas (mesmo CPF, dados diferentes) e fraudes potenciais.
    Retorna um DataFrame vazio se não houver erros.
    """
    if df is None or df.empty:
        return pd.DataFrame()
    
    needed = ['cpf', 'num_cartao', 'nome']
    if not all(col in df.columns for col in needed):
        return pd.DataFrame()
    
    df_check = df.copy()
    # Normalização robusta
    df_check['cpf_clean'] = df_check['cpf'].astype(str).str.strip().str.replace(r'\D', '', regex=True)
    df_check['card_clean'] = df_check['num_cartao'].astype(str).str.strip().str.replace(r'^0+', '', regex=True).str.replace(r'\.0$', '', regex=True)
    df_check['nome_clean'] = df_check['nome'].apply(remove_accents)
    
    # Remover inválidos
    df_check = df_check[ 
        (df_check['cpf_clean'] != '') & 
        (df_check['cpf_clean'].str.lower() != 'nan') &
        (df_check['cpf_clean'].str.len() > 5) # CPFs muito curtos geralmente são lixo
    ]
    
    critical_errors = []

    # 1. Verifica conflitos de CPF (Um CPF -> Múltiplos Cartões ou Nomes)
    cpf_groups = df_check.groupby('cpf_clean')
    for cpf, group in cpf_groups:
        unique_cards = group['card_clean'].unique()
        unique_names = group['nome_clean'].unique()
        
        # Filtra 'nan' e vazios dos unicos
        unique_cards = [c for c in unique_cards if c and str(c).lower() != 'nan']
        unique_names = [n for n in unique_names if n and str(n).lower() != 'nan']

        has_card_conflict = len(unique_cards) > 1
        has_name_conflict = len(unique_names) > 1
        
        if has_card_conflict or has_name_conflict:
            motivo = []
            if has_card_conflict: 
                cards_orig = group['num_cartao'].unique()
                motivo.append(f"CONFLITO CARTÃO ({', '.join(map(str, cards_orig))})")
            if has_name_conflict: 
                motivo.append(f"CONFLITO NOME")
            
            err_msg = " | ".join(motivo)
            for _, row in group.iterrows():
                critical_errors.append({
                    'ARQUIVO': row.get('arquivo_origem', '-'),
                    'LINHA': row.get('linha_arquivo', '-'),
                    'CPF': cpf,
                    'CARTÃO': row.get('num_cartao', '-'),
                    'NOME': row.get('nome', '-'),
                    'ERRO': err_msg
                })

    # 2. Verifica Cartão Duplicado em Pessoas Diferentes (Um Cartão -> Múltiplos CPFs)
    card_groups = df_check.groupby('card_clean')
    for card, group in card_groups:
        if not card or str(card).lower() == 'nan': continue
        unique_cpfs = group['cpf_clean'].unique()
        unique_cpfs = [c for c in unique_cpfs if c]
        
        if len(unique_cpfs) > 1:
            for _, row in group.iterrows():
                critical_errors.append({
                    'ARQUIVO': row.get('arquivo_origem', '-'),
                    'LINHA': row.get('linha_arquivo', '-'),
                    'CPF': row.get('cpf', '-'),
                    'CARTÃO': row.get('num_cartao', '-'),
                    'NOME': row.get('nome', '-'),
                    'ERRO': f"FRAUDE: CARTÃO USADO EM {len(unique_cpfs)} CPFs"
                })

    if not critical_errors: return pd.DataFrame()
    res_df = pd.DataFrame(critical_errors)
    # Remover duplicatas exatas de reporte
    return res_df.drop_duplicates(subset=['ARQUIVO', 'LINHA', 'CPF', 'CARTÃO', 'ERRO'])

def generate_bb_txt(df):
    buffer = io.StringIO()
    header = f"{'0':<11}{'Projeto':<31}{'NumCartão':<10} {'Nome':<40} {'RG':<12} {'CPF':<15}\n"
    buffer.write(header)
    for _, row in df.iterrows():
        projeto = str(row.get('programa', ''))[:30]
        cartao = str(row.get('num_cartao', ''))[:15]
        nome = str(row.get('nome', ''))[:40]
        rg = str(row.get('rg', ''))[:12]
        cpf = str(row.get('cpf', ''))[:14]
        line = f"{'1':<11}{projeto:<31}{cartao:<10} {nome:<40} {rg:<12} {cpf:<15}\n"
        buffer.write(line)
    return buffer.getvalue()

def print_pdf_row_multiline(pdf, widths, data, align='L', fill=False):
    font_size = 8
    pdf.set_font("Arial", '', font_size)
    line_height = 5
    max_lines = 1
    # Calcular altura necessária
    for i, datum in enumerate(data):
        col_width = widths[i]
        text_width = pdf.get_string_width(sanitize_text(str(datum)))
        if text_width > col_width - 2:
            lines_needed = int(text_width / (col_width - 2)) + 1
            if lines_needed > max_lines: max_lines = lines_needed
    row_height = max_lines * line_height
    
    # Quebra de página se necessário
    if pdf.get_y() + row_height > 190: 
        pdf.add_page(orientation='L')
        # Redesenhar cabeçalho da tabela se quiser (opcional, simplificado aqui)
    
    x_start = pdf.get_x()
    y_start = pdf.get_y()
    for i, width in enumerate(widths):
        pdf.set_xy(x_start + sum(widths[:i]), y_start)
        content = sanitize_text(str(data[i]))
        pdf.multi_cell(width, line_height, content, 1, align, fill)
    pdf.set_xy(x_start, y_start + row_height)

def generate_pdf_report(df_filtered, critical_errors_df=None):
    if FPDF is None: return b"Erro: FPDF ausente."
    pdf = FPDF()
    pdf.add_page(orientation='L')
    
    # --- CABEÇALHO ---
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 8, sanitize_text("Prefeitura de São Paulo"), 0, 1, 'C')
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 8, sanitize_text("Secretaria Municipal do Desenvolvimento Econômico e Trabalho"), 0, 1, 'C')
    pdf.ln(5)
    pdf.set_fill_color(220, 220, 220)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 12, sanitize_text("Relatório Executivo POT"), 1, 1, 'C', fill=True)
    pdf.ln(5)
    
    data_br = get_brasilia_time().strftime('%d/%m/%Y às %H:%M')
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 6, sanitize_text(f"Gerado em: {data_br}"), 0, 1, 'R')
    pdf.ln(5)

    # 1. RESUMO
    total_valor = df_filtered['valor_pagto'].sum() if 'valor_pagto' in df_filtered.columns else 0.0
    total_benef = df_filtered['num_cartao'].nunique() if 'num_cartao' in df_filtered.columns else 0
    total_projetos = df_filtered['programa'].nunique() if 'programa' in df_filtered.columns else 0
    total_registros = len(df_filtered)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, sanitize_text("1. Resumo Analítico"), 0, 1)
    pdf.set_font("Arial", '', 11)
    pdf.cell(100, 8, f"Total Pago: R$ {total_valor:,.2f}", 1)
    pdf.cell(0, 8, sanitize_text(f"Beneficiários Únicos: {total_benef}"), 1, 1)
    pdf.cell(100, 8, sanitize_text(f"Projetos Ativos: {total_projetos}"), 1)
    pdf.cell(0, 8, sanitize_text(f"Total Registros: {total_registros}"), 1, 1)
    pdf.ln(5)

    # 2. GRÁFICOS
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, sanitize_text("2. Visualização Gráfica"), 0, 1)
    if plt and 'programa' in df_filtered.columns and not df_filtered.empty:
        try:
            plt.figure(figsize=(10, 4))
            grp = df_filtered.groupby('programa')['valor_pagto'].sum().sort_values()
            plt.barh(grp.index, grp.values, color='#4682B4') 
            plt.title('Valor Total por Projeto')
            plt.xlabel('Valor (R$)')
            plt.grid(axis='x', linestyle='--', alpha=0.7)
            plt.tight_layout()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                plt.savefig(tmp.name, dpi=100)
                img_path = tmp.name
            pdf.image(img_path, x=20, w=180)
            plt.close()
            os.remove(img_path)
        except: pass
    else: pdf.cell(0, 10, sanitize_text("Gráfico indisponível."), 0, 1)
    pdf.ln(10)

    # 3. DETALHAMENTO
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, sanitize_text("3. Detalhamento Financeiro"), 0, 1)
    if 'programa' in df_filtered.columns and not df_filtered.empty:
        group_proj = df_filtered.groupby('programa').agg({'valor_pagto': 'sum', 'num_cartao': 'count'}).reset_index().sort_values('valor_pagto', ascending=False)
        pdf.set_font("Arial", 'B', 9)
        pdf.set_fill_color(240, 240, 240)
        widths_det = [100, 40, 60]
        cols_det = ['PROJETO', 'REGISTROS', 'VALOR TOTAL']
        for i, col in enumerate(cols_det): pdf.cell(widths_det[i], 8, sanitize_text(col), 1, 0, 'C', True)
        pdf.ln()
        pdf.set_font("Arial", '', 9)
        for _, row in group_proj.iterrows():
            pdf.cell(widths_det[0], 7, sanitize_text(str(row['programa'])[:50]), 1)
            pdf.cell(widths_det[1], 7, str(row['num_cartao']), 1, 0, 'C')
            pdf.cell(widths_det[2], 7, f"R$ {row['valor_pagto']:,.2f}", 1, 1, 'R')
    pdf.ln(10)

    # 4. ALERTAS CRÍTICOS
    # Se não foi passado externamente, calcula agora
    if critical_errors_df is None:
        critical_errors_df = detect_critical_duplicates(df_filtered)
        
    if not critical_errors_df.empty:
        pdf.set_text_color(255, 0, 0)
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, sanitize_text(f"⚠️ 4. ALERTA DE INCONSISTÊNCIAS ({len(critical_errors_df)} Ocorrências)"), 0, 1)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", '', 10)
        pdf.multi_cell(0, 6, sanitize_text("Registros com conflitos cadastrais graves (Mesmo CPF com Nomes/Cartões diferentes) ou indícios de fraude."))
        pdf.ln(2)
        
        pdf.set_font("Arial", 'B', 9)
        pdf.set_fill_color(255, 230, 230)
        widths = [45, 15, 30, 25, 70, 90]
        cols = ['ARQUIVO', 'LIN', 'CPF', 'CARTÃO', 'NOME', 'ERRO DETECTADO']
        for i, col in enumerate(cols): pdf.cell(widths[i], 8, sanitize_text(col), 1, 0, 'C', True)
        pdf.ln()
        pdf.set_font("Arial", '', 8)
        
        # Limitar a exibição no PDF se for muito grande para não travar
        max_rows = 200
        count = 0
        for _, row in critical_errors_df.iterrows():
            if count >= max_rows:
                pdf.cell(0, 8, sanitize_text(f"... e mais {len(critical_errors_df)-max_rows} erros (veja no sistema)."), 1, 1, 'C')
                break
            data_row = [str(row['ARQUIVO']), str(row['LINHA']), str(row['CPF']), str(row['CARTÃO']), str(row['NOME']), str(row['ERRO'])]
            print_pdf_row_multiline(pdf, widths, data_row)
            count += 1
    else:
        pdf.set_text_color(0, 128, 0)
        pdf.set_font("Arial", 'B', 11)
        pdf.cell(0, 10, sanitize_text("✅ 4. Validação de Integridade: Nenhuma duplicidade crítica detectada nesta seleção."), 0, 1)
        pdf.set_text_color(0, 0, 0)

    return pdf.output(dest='S').encode('latin-1', 'replace')

def generate_audit_log_pdf(logs_df):
    if FPDF is None: return b"Erro FPDF"
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, sanitize_text("Relatório de Auditoria do Sistema"), 0, 1, 'C')
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 8)
    pdf.set_fill_color(240, 240, 240)
    w = [35, 45, 40, 70]
    headers = ["DATA/HORA", "USUÁRIO", "AÇÃO", "DETALHES"]
    for i, h in enumerate(headers): pdf.cell(w[i], 8, sanitize_text(h), 1, 0, 'C', True)
    pdf.ln()
    pdf.set_font("Arial", '', 8)
    for _, row in logs_df.iterrows():
        data = [str(row['timestamp']), str(row['user_email']), str(row['action']), str(row['details'])]
        print_pdf_row_multiline(pdf, w, data)
    return pdf.output(dest='S').encode('latin-1', 'replace')

def generate_conference_pdf(hist_df):
    if FPDF is None: return b"Erro: FPDF ausente."
    pdf = FPDF()
    pdf.add_page(orientation='L')
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 8, sanitize_text("Prefeitura de São Paulo"), 0, 1, 'C')
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 8, sanitize_text("Relatório de Divergências Bancárias"), 0, 1, 'C')
    pdf.ln(5)
    data_br = get_brasilia_time().strftime('%d/%m/%Y às %H:%M')
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 6, sanitize_text(f"Gerado em: {data_br}"), 0, 1, 'R')
    pdf.ln(5)

    if hist_df.empty:
        pdf.cell(0, 10, sanitize_text("Nenhuma divergência registrada."), 0, 1)
        return pdf.output(dest='S').encode('latin-1', 'replace')

    pdf.set_font("Arial", 'B', 8)
    pdf.set_fill_color(255, 240, 240)
    widths = [30, 80, 80, 50]
    headers = ["CARTÃO", "NOME NO SISTEMA", "NOME NO BANCO", "DIVERGÊNCIA"]
    for i, h in enumerate(headers): pdf.cell(widths[i], 8, sanitize_text(h), 1, 0, 'C', True)
    pdf.ln()
    pdf.set_font("Arial", '', 7)
    for _, row in hist_df.iterrows():
        row_data = [
            str(row.get('cartao','')),
            str(row.get('nome_sis','')),
            str(row.get('nome_bb','')),
            str(row.get('divergencia',''))
        ]
        print_pdf_row_multiline(pdf, widths, row_data)
    return pdf.output(dest='S').encode('latin-1', 'replace')

# ===========================================
# INTERFACE
# ===========================================

def login_screen():
    render_header()
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        with st.form("login"):
            email = st.text_input("E-mail")
            password = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar"):
                if email.endswith("@prefeitura.sp.gov.br"):
                    conn = get_db_connection()
                    phash = hashlib.sha256(password.encode()).hexdigest()
                    user = conn.execute("SELECT * FROM users WHERE email=? AND password=?", (email, phash)).fetchone()
                    conn.close()
                    if user:
                        st.session_state['logged_in'] = True
                        st.session_state['user_info'] = {'email': user[0], 'role': user[2], 'name': user[3], 'first_login': user[4]}
                        log_action(user[0], "LOGIN", "Usuário acessou o sistema")
                        st.rerun()
                    else: st.error("Inválido.")
                else: st.error("Domínio inválido.")

def change_password_screen():
    render_header()
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown("### 🔐 Troca de Senha Obrigatória")
        st.warning("É necessário redefinir sua senha para continuar.")
        with st.form("change_pass"):
            p1 = st.text_input("Nova Senha", type="password")
            p2 = st.text_input("Confirmar Senha", type="password")
            if st.form_submit_button("Atualizar Senha"):
                if len(p1) < 6:
                    st.error("A senha deve ter pelo menos 6 caracteres.")
                elif p1 != p2:
                    st.error("As senhas não conferem.")
                else:
                    new_hash = hashlib.sha256(p1.encode()).hexdigest()
                    conn = get_db_connection()
                    email = st.session_state['user_info']['email']
                    conn.execute("UPDATE users SET password = ?, first_login = 0 WHERE email = ?", (new_hash, email))
                    conn.commit()
                    conn.close()
                    st.session_state['user_info']['first_login'] = 0
                    log_action(email, "TROCA_SENHA", "Usuário alterou a senha inicial")
                    st.success("Senha alterada com sucesso! Redirecionando...")
                    st.rerun()

def main_app():
    user = st.session_state['user_info']
    st.sidebar.markdown(f"### Olá, {user['name']}")
    
    menu = ["Dashboard", "Upload e Processamento", "Análise e Correção", "Conferência Bancária (BB)", "Relatórios e Exportação"]
    menu.insert(1, "Manuais e Treinamento")
    if user['role'] in ['admin_ti', 'admin_equipe']: menu.append("Gestão de Equipe")
    if user['role'] == 'admin_ti': menu.append("Administração TI")
    
    choice = st.sidebar.radio("Menu", menu)
    
    if st.sidebar.button("Sair"):
        log_action(user['email'], "LOGOUT", "Usuário saiu do sistema")
        st.session_state.clear()
        st.rerun()

    # --- CARREGAR DADOS GLOBAIS DO BANCO ---
    # Evitar st.cache_data para garantir que a persistência seja visível imediatamente
    conn = get_db_connection()
    try:
        df_payments = pd.read_sql("SELECT * FROM payments", conn)
    except:
        df_payments = pd.DataFrame()
    conn.close()

    # --- DASHBOARD ---
    if choice == "Dashboard":
        render_header()
        st.markdown("### 📊 Dashboard Executivo")
        
        if not df_payments.empty:
            k1, k2, k3, k4 = st.columns(4)
            total = df_payments['valor_pagto'].sum()
            benef = df_payments['num_cartao'].nunique()
            projs = df_payments['programa'].nunique()
            gers = df_payments['gerenciadora'].nunique()
            k1.metric("Total Pago", f"R$ {total:,.2f}")
            k2.metric("Beneficiários Únicos", benef)
            k3.metric("Projetos Ativos", projs)
            k4.metric("Gerenciadoras", gers)
            
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Total por Projeto")
                g1 = df_payments.groupby('programa')['valor_pagto'].sum().reset_index()
                st.plotly_chart(px.bar(g1, x='valor_pagto', y='programa', orientation='h'), use_container_width=True)
            with c2:
                st.subheader("Por Gerenciadora")
                g2 = df_payments.groupby('gerenciadora')['valor_pagto'].sum().reset_index()
                st.plotly_chart(px.pie(g2, names='gerenciadora', values='valor_pagto'), use_container_width=True)
        else: st.info("Sem dados no sistema. Faça upload na aba 'Upload e Processamento'.")

    # --- MANUAIS ---
    elif choice == "Manuais e Treinamento":
        render_header()
        st.markdown("### 📚 Manuais e Treinamento")
        role = user['role']
        
        with st.expander("📘 Manual Operacional Básico (Usuário)", expanded=True):
            content_user = get_manual_content("usuario")
            st.markdown(content_user)
            pdf_user = create_manual_pdf("Manual Operacional Básico", content_user)
            if pdf_user: st.download_button("Baixar PDF (Básico)", pdf_user, "manual_usuario.pdf", "application/pdf")

        if role in ['admin_equipe', 'admin_ti']:
            with st.expander("📗 Manual de Gestão e Correção (Líderes)"):
                content_team = get_manual_content("admin_equipe")
                st.markdown(content_team)
                pdf_team = create_manual_pdf("Manual de Gestão e Correção", content_team)
                if pdf_team: st.download_button("Baixar PDF (Gestão)", pdf_team, "manual_gestao.pdf", "application/pdf")

        if role == 'admin_ti':
            with st.expander("📕 Manual Técnico e Auditoria (TI)"):
                content_ti = get_manual_content("admin_ti")
                st.markdown(content_ti)
                pdf_ti = create_manual_pdf("Manual Técnico", content_ti)
                if pdf_ti: st.download_button("Baixar PDF (Técnico)", pdf_ti, "manual_tecnico.pdf", "application/pdf")

    # --- UPLOAD ---
    elif choice == "Upload e Processamento":
        render_header()
        st.markdown("### 📂 Upload de Pagamentos")
        
        # Feedback de persistência
        reg_count = len(df_payments)
        if reg_count > 0:
            st.info(f"💾 **Banco de Dados Ativo:** {reg_count} registros já carregados e seguros. Novos uploads serão adicionados.")
        else:
            st.warning("O banco de dados está vazio.")

        files = st.file_uploader("Arquivos (CSV/XLSX)", accept_multiple_files=True)
        
        if files and st.button("Processar Arquivos"):
            conn = get_db_connection()
            try:
                exist_query = pd.read_sql("SELECT DISTINCT arquivo_origem FROM payments", conn)
                exist = exist_query['arquivo_origem'].tolist() if not exist_query.empty else []
            except: exist = []
            conn.close()
            
            dfs = []
            for f in files:
                if f.name in exist:
                    st.warning(f"Ignorado (já existe): {f.name}")
                    continue
                if 'REL.CADASTRO' in f.name.upper():
                    st.warning(f"Ignorado (Parece arquivo de conferência bancária): {f.name}")
                    continue
                try:
                    if f.name.endswith('.csv'): 
                        try: df = pd.read_csv(f, sep=';', encoding='latin1', dtype=str, low_memory=False)
                        except: f.seek(0); df = pd.read_csv(f, sep=',', encoding='utf-8', dtype=str, low_memory=False)
                    else: df = pd.read_excel(f, dtype=str)
                    
                    df_std = standardize_dataframe(df, f.name)
                    if not df_std.empty: dfs.append(df_std)
                except Exception as e: st.error(f"Erro ao ler {f.name}: {e}")
            
            if dfs:
                final = pd.concat(dfs, ignore_index=True)
                conn = get_db_connection()
                # Append seguro
                final.to_sql('payments', conn, if_exists='append', index=False)
                conn.close()
                log_action(user['email'], "UPLOAD", f"Upload de {len(files)} arquivos, {len(final)} registros")
                st.success(f"✅ {len(final)} registros salvos com sucesso no banco de dados!")
                
                # Feedback imediato de erros no upload
                crit = detect_critical_duplicates(final)
                if not crit.empty:
                    st.error("🚨 ERROS CRÍTICOS IDENTIFICADOS NESTE UPLOAD!")
                    st.dataframe(crit, use_container_width=True)
                
                # Rerun para atualizar contadores e tabelas globais
                st.rerun()

    # --- ANÁLISE E CORREÇÃO ---
    elif choice == "Análise e Correção":
        render_header()
        st.markdown("### 🛠️ Análise e Auditoria de Dados")
        
        if df_payments.empty:
            st.info("Sem dados para analisar.")
        else:
            # 1. Detectar erros na base COMPLETA
            crit_all = detect_critical_duplicates(df_payments)
            
            if not crit_all.empty:
                st.error(f"🚨 {len(crit_all)} Inconsistências Críticas Encontradas na Base")
                st.markdown("Estes registros possuem o **mesmo CPF** mas **Nomes** ou **Cartões** diferentes.")
                st.dataframe(crit_all, use_container_width=True)
            else:
                st.success("✅ Base íntegra. Nenhuma duplicidade crítica de CPF encontrada.")
            
            st.markdown("---")
            st.markdown("### 📝 Editor de Dados (Malha Fina)")
            
            if user['role'] in ['admin_ti', 'admin_equipe']:
                st.warning("⚠️ Atenção: As alterações feitas aqui são aplicadas diretamente ao Banco de Dados.")
                # Editor
                edited_df = st.data_editor(df_payments, num_rows="dynamic", key="editor_analise", use_container_width=True)
                
                if st.button("💾 Salvar Correções no Banco de Dados"):
                    try:
                        conn = get_db_connection()
                        # Transação segura: Só deleta se o insert funcionar
                        # Em SQLite, to_sql com replace recria a tabela, o que é seguro se edited_df tem tudo
                        # Mas como data_editor pode ser pesado, é melhor substituir tudo SE não estiver filtrado.
                        # Assumindo que edited_df é a base completa carregada acima.
                        
                        # Limpar tabela e reinserir (método Replace do Pandas é atômico em alguns drivers, mas vamos forçar transação)
                        with conn:
                            conn.execute("DELETE FROM payments") # Limpa tabela antiga
                            edited_df.to_sql('payments', conn, if_exists='append', index=False) # Insere nova
                        
                        conn.close()
                        log_action(user['email'], "CORRECAO_DADOS", "Usuário aplicou correções via Malha Fina")
                        st.success("✅ Dados atualizados com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar: {e}")
            else:
                st.dataframe(df_payments)

    # --- RELATÓRIOS ---
    elif choice == "Relatórios e Exportação":
        render_header()
        st.markdown("### 📥 Relatórios e Exportação")
        
        if not df_payments.empty:
            projs = df_payments['programa'].unique()
            sel_proj = st.multiselect("Filtrar Projeto", projs, default=projs)
            
            if sel_proj:
                df_exp = df_payments[df_payments['programa'].isin(sel_proj)]
            else:
                df_exp = df_payments
            
            # Recalcular erros para o PDF baseados no filtro (ou na base toda se preferir)
            # Geralmente erros de CPF duplicado devem olhar a base toda, mas reportar apenas os do filtro
            # Aqui vamos passar os erros detectados no subset para o PDF
            crit_subset = detect_critical_duplicates(df_exp)
            
            st.markdown("---")
            c1, c2, c3, c4 = st.columns(4)
            
            with c1:
                st.markdown("###### 📑 Relatório Executivo")
                if st.button("Gerar Relatório PDF"):
                    with st.spinner("Gerando PDF..."):
                        pdf_data = generate_pdf_report(df_exp, crit_subset)
                        if isinstance(pdf_data, bytes):
                            st.download_button("⬇️ Baixar PDF", pdf_data, "relatorio_executivo.pdf", "application/pdf")
                            log_action(user['email'], "RELATORIO_PDF", "Gerou relatório executivo")
                        else: st.error(pdf_data)
            
            with c2:
                st.markdown("###### 📄 Dados Completos")
                csv = df_exp.to_csv(index=False, sep=';').encode('utf-8-sig')
                st.download_button("⬇️ Baixar CSV", csv, "dados_pot.csv", "text/csv")
            
            with c3:
                st.markdown("###### 📊 Planilha Excel")
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer: df_exp.to_excel(writer, index=False)
                st.download_button("⬇️ Baixar Excel", buffer.getvalue(), "dados_pot.xlsx", "application/vnd.ms-excel")
            
            with c4:
                st.markdown("###### 🏦 Layout Banco (BB)")
                txt = generate_bb_txt(df_exp)
                st.download_button("⬇️ Baixar TXT", txt, "remessa_bb.txt", "text/plain")

    # --- CONFERÊNCIA BANCÁRIA ---
    elif choice == "Conferência Bancária (BB)":
        render_header()
        st.markdown("### 🏦 Conferência BB")
        
        conn = get_db_connection()
        try:
            hist = pd.read_sql("SELECT * FROM bank_discrepancies", conn)
        except: hist = pd.DataFrame()
        conn.close()
        
        if not hist.empty:
            st.warning(f"⚠️ {len(hist)} divergências encontradas no histórico.")
            st.dataframe(hist)
            
            c_pdf, c_limp = st.columns(2)
            
            pdf_conf = generate_conference_pdf(hist)
            if isinstance(pdf_conf, bytes):
                c_pdf.download_button("📑 Baixar Relatório PDF (Divergências)", pdf_conf, "divergencias_bb.pdf", "application/pdf")
            
            if user['role'] in ['admin_ti', 'admin_equipe']:
                if c_limp.button("Limpar Histórico de Divergências"):
                    conn = get_db_connection()
                    conn.execute("DELETE FROM bank_discrepancies")
                    conn.commit()
                    conn.close()
                    st.success("Histórico limpo.")
                    st.rerun()
                
        files = st.file_uploader("Upload Retorno Banco (TXT)", accept_multiple_files=True)
        if files and st.button("Processar Conferência"):
            dfs = []
            for f in files:
                try:
                    d = parse_bb_txt_cadastro(f)
                    d['arquivo_bb'] = f.name
                    dfs.append(d)
                except: st.error(f"Erro ao ler {f.name}")
            
            if dfs:
                final_bb = pd.concat(dfs)
                conn = get_db_connection()
                # Pega apenas colunas necessárias para comparar
                df_sys = pd.read_sql("SELECT num_cartao, nome, cpf FROM payments", conn)
                
                # Criar chaves normalizadas
                final_bb['key'] = final_bb['num_cartao'].astype(str).str.replace(r'^0+','', regex=True)
                df_sys['key'] = df_sys['num_cartao'].astype(str).str.replace(r'^0+','', regex=True).str.replace(r'\.0$','', regex=True)
                
                merged = pd.merge(df_sys, final_bb, on='key', suffixes=('_sis', '_bb'))
                divs = []
                for _, row in merged.iterrows():
                    nm_s = str(row.get('nome_sis','')).strip().upper()
                    nm_b = str(row.get('nome_bb','')).strip().upper()
                    # Comparação simples de string, pode ser melhorada com fuzzy matching no futuro
                    if nm_s != nm_b:
                        divs.append({
                            'cartao': row['key'],
                            'nome_sis': nm_s,
                            'nome_bb': nm_b,
                            'divergencia': 'NOME DIFERENTE',
                            'arquivo_origem': row['arquivo_bb']
                        })
                
                if divs:
                    dd = pd.DataFrame(divs)
                    dd.to_sql('bank_discrepancies', conn, if_exists='append', index=False)
                    st.error(f"🚨 {len(dd)} novas divergências encontradas e salvas!")
                    st.rerun()
                else: st.success("✅ Processamento concluído: Nenhuma divergência encontrada.")
                conn.close()

    # --- GESTÃO DE EQUIPE ---
    elif choice == "Gestão de Equipe":
        render_header()
        st.markdown("### 👥 Gestão de Acessos")
        
        # Formulário de Cadastro
        with st.expander("➕ Adicionar Novo Usuário", expanded=False):
            with st.form("add_user"):
                c1, c2, c3 = st.columns([2, 2, 1])
                new_email = c1.text_input("E-mail (Institucional)")
                new_name = c2.text_input("Nome Completo")
                new_role = c3.selectbox("Perfil", ["user", "admin_equipe"])
                
                if st.form_submit_button("Criar Usuário"):
                    if new_email.endswith("@prefeitura.sp.gov.br"):
                        conn = get_db_connection()
                        try:
                            ptemp = hashlib.sha256('mudar123'.encode()).hexdigest()
                            conn.execute("INSERT INTO users VALUES (?, ?, ?, ?, 1)", (new_email, ptemp, new_role, new_name))
                            conn.commit()
                            st.success(f"Usuário {new_name} criado com sucesso!")
                            log_action(user['email'], "CRIAR_USUARIO", f"Criou usuário {new_email}")
                        except sqlite3.IntegrityError:
                            st.error("Erro: E-mail já cadastrado.")
                        except Exception as e: st.error(f"Erro: {e}")
                        conn.close()
                    else: st.error("Email deve ser @prefeitura.sp.gov.br")

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### Usuários Cadastrados")
        
        conn = get_db_connection()
        users_db = pd.read_sql("SELECT email, name, role FROM users", conn)
        conn.close()
        
        # Cabeçalho
        cols = st.columns([3, 3, 2, 1, 1])
        cols[0].markdown("**Nome**")
        cols[1].markdown("**E-mail**")
        cols[2].markdown("**Perfil**")
        cols[3].markdown("**Reset**")
        cols[4].markdown("**Excluir**")
        st.markdown("<hr style='margin: 5px 0'>", unsafe_allow_html=True)

        for _, row in users_db.iterrows():
            with st.container():
                c = st.columns([3, 3, 2, 1, 1])
                c[0].write(row['name'])
                c[1].write(row['email'])
                
                r_map = {'admin_ti': 'Admin TI', 'admin_equipe': 'Líder/Admin', 'user': 'Analista'}
                c[2].write(r_map.get(row['role'], row['role']))
                
                is_self = (row['email'] == user['email'])
                
                # Reset
                if c[3].button("🔄", key=f"rst_{row['email']}", disabled=is_self, help="Reseta senha para 'mudar123'"):
                    conn = get_db_connection()
                    pass_reset = hashlib.sha256('mudar123'.encode()).hexdigest()
                    conn.execute("UPDATE users SET password = ?, first_login = 1 WHERE email = ?", (pass_reset, row['email']))
                    conn.commit()
                    conn.close()
                    st.toast(f"Senha de {row['name']} resetada!")
                    log_action(user['email'], "RESET_SENHA", f"Resetou {row['email']}")
                
                # Excluir
                if c[4].button("🗑️", key=f"del_{row['email']}", disabled=is_self):
                    conn = get_db_connection()
                    conn.execute("DELETE FROM users WHERE email = ?", (row['email'],))
                    conn.commit()
                    conn.close()
                    st.success(f"Removido: {row['name']}")
                    log_action(user['email'], "EXCLUIR_USUARIO", f"Excluiu {row['email']}")
                    st.rerun()
                
                st.markdown("<div class='user-row'></div>", unsafe_allow_html=True)

    # --- ADMIN TI ---
    elif choice == "Administração TI" and user['role'] == 'admin_ti':
        render_header()
        st.markdown("### 🛡️ Painel de Auditoria e Controle")
        
        conn = get_db_connection()
        logs = pd.read_sql("SELECT * FROM audit_logs ORDER BY timestamp DESC", conn)
        conn.close()
        
        st.dataframe(logs, use_container_width=True)
        
        c1, c2 = st.columns(2)
        pdf_logs = generate_audit_log_pdf(logs)
        if isinstance(pdf_logs, bytes):
            c1.download_button("📄 Baixar Logs (PDF)", pdf_logs, "auditoria_sistema.pdf", "application/pdf")
            
        if c2.button("⚠️ LIMPAR LOGS"):
            conn = get_db_connection()
            conn.execute("DELETE FROM audit_logs")
            conn.commit()
            conn.close()
            st.warning("Logs limpos.")
            st.rerun()

        st.markdown("---")
        if st.button("🗑️ LIMPAR DADOS PAGAMENTOS (RESET TOTAL)"):
            conn = get_db_connection()
            conn.execute("DELETE FROM payments")
            conn.execute("DELETE FROM bank_discrepancies")
            conn.commit()
            conn.close()
            log_action(user['email'], "RESET_DB", "Limpou todas as tabelas de dados")
            st.success("Banco de dados de pagamentos reiniciado.")
            st.rerun()

if __name__ == "__main__":
    init_db()
    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
    
    if st.session_state['logged_in']: 
        if st.session_state['user_info']['first_login']: change_password_screen()
        else: main_app()
    else: login_screen()
