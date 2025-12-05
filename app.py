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
    .metric-card {
        background-color: #f8f9fa;
        border: 1px solid #dee2e6;
        padding: 15px;
        border-radius: 5px;
        text-align: center;
    }
    .stAlert {
        padding: 10px;
        border-radius: 5px;
    }
    .manual-header {
        color: #1E3A8A;
        border-bottom: 1px solid #ccc;
        padding-bottom: 5px;
    }
    /* Estilo para a tabela de usuários */
    .user-row {
        padding: 10px 0;
        border-bottom: 1px solid #eee;
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
    conn = sqlite3.connect(DB_FILE)
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
    
    # Migrações seguras
    for col, tbl in [('linha_arquivo', 'payments'), ('gerenciadora', 'payments'), ('tipo_erro', 'bank_discrepancies')]:
        try:
            c.execute(f"SELECT {col} FROM {tbl} LIMIT 1")
        except sqlite3.OperationalError:
            try:
                col_type = 'INTEGER' if col == 'linha_arquivo' else 'TEXT'
                c.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {col_type}")
                conn.commit()
            except Exception: pass

    # Criar usuário Admin padrão
    c.execute("SELECT * FROM users WHERE email = 'admin@prefeitura.sp.gov.br'")
    if not c.fetchone():
        default_pass = hashlib.sha256('smdet2025'.encode()).hexdigest()
        c.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?)", 
                  ('admin@prefeitura.sp.gov.br', default_pass, 'admin_ti', 'Administrador TI', 0))
    
    conn.commit()
    conn.close()

def get_db_connection():
    return sqlite3.connect(DB_FILE)

def log_action(user_email, action, details):
    """Registra uma ação no log de auditoria."""
    conn = get_db_connection()
    conn.execute("INSERT INTO audit_logs (user_email, action, details) VALUES (?, ?, ?)", 
                 (user_email, action, details))
    conn.commit()
    conn.close()

# ===========================================
# CONTEÚDO DOS MANUAIS
# ===========================================

def get_manual_content(tipo):
    """Retorna o texto do manual baseado no tipo."""
    if tipo == "usuario":
        return """
        # Manual Operacional Básico - Sistema POT
        
        ## 1. Visão Geral
        Bem-vindo ao Sistema de Gestão e Monitoramento de Pagamentos do POT. Este sistema permite o upload, validação e análise dos pagamentos realizados aos beneficiários.

        ## 2. Acesso ao Sistema
        - Utilize seu e-mail institucional (@prefeitura.sp.gov.br) e senha.
        - No primeiro acesso, será solicitada a troca da senha provisória.

        ## 3. Upload de Arquivos
        - Navegue até a aba **Upload e Processamento**.
        - Arraste arquivos Excel (.xlsx) ou CSV para a área indicada.
        - O sistema validará automaticamente:
            - Formato das colunas.
            - **Duplicidades Críticas:** Se o mesmo CPF aparecer com nomes ou cartões diferentes, um alerta vermelho será exibido.
        - Clique em "Processar Arquivos" para salvar no banco de dados.

        ## 4. Conferência Bancária
        - Utilize a aba **Conferência Bancária (BB)**.
        - Suba os arquivos de retorno do banco (formato TXT REL.CADASTRO).
        - O sistema cruzará os dados do banco com o sistema e apontará divergências de Nome ou CPF.

        ## 5. Relatórios
        - Na aba **Relatórios e Exportação**, você pode baixar:
            - Planilha completa (Excel/CSV).
            - Arquivo de Remessa (TXT Layout BB).
            - **Relatório Executivo (PDF):** Contém resumo financeiro e alertas de integridade.
        """
    elif tipo == "admin_equipe":
        return """
        # Manual de Gestão e Correção - Perfil Líder/Admin Equipe
        
        ## 1. Responsabilidades
        Além das funções básicas, o Admin Equipe é responsável pela integridade dos dados e gestão dos usuários operacionais.

        ## 2. Correção de Dados (Malha Fina)
        - Ao identificar erros críticos (CPF duplicado com dados divergentes) no Upload ou no Relatório PDF:
        - Vá para a aba **Análise e Correção**.
        - Utilize a tabela editável para corrigir Nomes errados, CPFs digitados incorretamente ou números de cartão.
        - Clique em **"Salvar Correções"** para atualizar o banco de dados oficial.
        
        ## 3. Gestão de Usuários
        - Na aba **Gestão de Equipe**, você pode cadastrar novos analistas.
        - Preencha E-mail e Nome.
        - A senha inicial padrão é `mudar123`. Oriente o usuário a trocá-la imediatamente.
        - **Novidade:** Agora é possível resetar senhas de usuários esquecidos e excluir cadastros antigos.
        
        ## 4. Limpeza de Histórico de Conferência
        - Na aba de Conferência Bancária, você tem permissão para limpar o histórico de divergências antigas para iniciar um novo ciclo de verificação.
        """
    elif tipo == "admin_ti":
        return """
        # Manual Técnico e Auditoria - Perfil TI (Super Admin)
        
        ## 1. Controle Total
        O perfil Admin TI tem acesso irrestrito a todas as funcionalidades, incluindo ações destrutivas e logs de segurança.

        ## 2. Painel de Auditoria (Logs)
        - Acesse a aba **Administração TI**.
        - Visualize a tabela de logs que registra QUEM fez O QUE e QUANDO (Uploads, Logins, Criação de usuários, etc.).
        - Você pode baixar o **Relatório de Auditoria em PDF** para fins de compliance.
        - Use o botão "Limpar Logs" apenas em ambiente de testes ou quando autorizado.

        ## 3. Reset do Sistema
        - O botão **"LIMPAR DADOS PAGAMENTOS"** apaga TODA a base de pagamentos e divergências bancárias.
        - **CUIDADO:** Esta ação é irreversível. Use apenas para limpar dados de teste antes de entrar em produção ou iniciar um novo ano fiscal.
        
        ## 4. Manutenção
        - O sistema utiliza banco de dados SQLite (`pot_system.db`).
        - As bibliotecas necessárias estão listadas no `requirements.txt`.
        """
    return ""

def create_manual_pdf(title, content):
    """Gera um PDF simples com o conteúdo do manual."""
    if FPDF is None: return None
    pdf = FPDF()
    pdf.add_page()
    
    # --- CABEÇALHO OFICIAL ---
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 8, sanitize_text("Prefeitura de São Paulo"), 0, 1, 'C')
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 8, sanitize_text("Secretaria Municipal do Desenvolvimento Econômico e Trabalho"), 0, 1, 'C')
    pdf.ln(5)
    # -------------------------

    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, sanitize_text(title), 0, 1, 'C')
    pdf.ln(10)
    
    pdf.set_font("Arial", '', 12)
    # Divide o conteúdo por linhas para processar
    lines = content.split('\n')
    for line in lines:
        clean_line = line.strip()
        if clean_line.startswith('# '):
            pdf.set_font("Arial", 'B', 14)
            pdf.ln(5)
            pdf.multi_cell(0, 10, sanitize_text(clean_line.replace('# ', '')))
            pdf.set_font("Arial", '', 12)
        elif clean_line.startswith('## '):
            pdf.set_font("Arial", 'B', 12)
            pdf.ln(3)
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
    if 'cpf' not in df.columns or 'num_cartao' not in df.columns or df.empty:
        return pd.DataFrame()
    
    df_check = df.copy()
    df_check['cpf_clean'] = df_check['cpf'].astype(str).str.strip().str.replace(r'\D', '', regex=True)
    df_check = df_check[ (df_check['cpf_clean'] != '') & (df_check['cpf_clean'].str.lower() != 'nan') ]
    df_check['card_clean'] = df_check['num_cartao'].astype(str).str.strip().str.replace(r'^0+', '', regex=True).str.replace(r'\.0$', '', regex=True)
    df_check['nome_clean'] = df_check['nome'].apply(remove_accents)
    
    critical_errors = []

    cpf_groups = df_check.groupby('cpf_clean')
    for cpf, group in cpf_groups:
        unique_cards = group['card_clean'].unique()
        unique_names = group['nome_clean'].unique()
        
        has_card_conflict = len(unique_cards) > 1
        has_name_conflict = len(unique_names) > 1
        
        if has_card_conflict or has_name_conflict:
            motivo = []
            if has_card_conflict: 
                cards_orig = group['num_cartao'].unique()
                motivo.append(f"CONFLITO DE CARTÃO ({', '.join(map(str, cards_orig))})")
            if has_name_conflict: 
                motivo.append(f"CONFLITO DE NOME")
            
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

    card_groups = df_check.groupby('card_clean')
    for card, group in card_groups:
        if not card or card == 'NAN': continue
        unique_cpfs = group['cpf_clean'].unique()
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
    for i, datum in enumerate(data):
        col_width = widths[i]
        text_width = pdf.get_string_width(sanitize_text(str(datum)))
        if text_width > col_width - 2:
            lines_needed = int(text_width / (col_width - 2)) + 1
            if lines_needed > max_lines: max_lines = lines_needed
    row_height = max_lines * line_height
    if pdf.get_y() + row_height > 190: pdf.add_page(orientation='L')
    x_start = pdf.get_x()
    y_start = pdf.get_y()
    for i, width in enumerate(widths):
        pdf.set_xy(x_start + sum(widths[:i]), y_start)
        content = sanitize_text(str(data[i]))
        pdf.multi_cell(width, line_height, content, 1, align, fill)
    pdf.set_xy(x_start, y_start + row_height)

def generate_pdf_report(df_filtered):
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
    if plt and 'programa' in df_filtered.columns:
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
    if 'programa' in df_filtered.columns:
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
    critical_df = detect_critical_duplicates(df_filtered)
    if not critical_df.empty:
        pdf.set_text_color(255, 0, 0)
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, sanitize_text(f"⚠️ 4. ALERTA DE INCONSISTÊNCIAS ({len(critical_df)} Ocorrências)"), 0, 1)
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
        for _, row in critical_df.iterrows():
            data_row = [str(row['ARQUIVO']), str(row['LINHA']), str(row['CPF']), str(row['CARTÃO']), str(row['NOME']), str(row['ERRO'])]
            print_pdf_row_multiline(pdf, widths, data_row)
    else:
        pdf.set_text_color(0, 128, 0)
        pdf.set_font("Arial", 'B', 11)
        pdf.cell(0, 10, sanitize_text("✅ 4. Validação de Integridade: Nenhuma duplicidade crítica encontrada."), 0, 1)
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
    """Gera PDF das divergências bancárias."""
    if FPDF is None: return b"Erro: FPDF ausente."
    pdf = FPDF()
    pdf.add_page(orientation='L')
    
    # --- CABEÇALHO ---
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
    # Colunas: Cartão, Nome Sistema, Nome Banco, Divergência
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
    
    # Adicionar menu de Manuais
    menu.insert(1, "Manuais e Treinamento")
    
    if user['role'] in ['admin_ti', 'admin_equipe']: menu.append("Gestão de Equipe")
    if user['role'] == 'admin_ti': menu.append("Administração TI")
    
    choice = st.sidebar.radio("Menu", menu)
    
    if st.sidebar.button("Sair"):
        log_action(user['email'], "LOGOUT", "Usuário saiu do sistema")
        st.session_state.clear()
        st.rerun()

    if choice == "Dashboard":
        render_header()
        st.markdown("### 📊 Dashboard Executivo")
        conn = get_db_connection()
        df = pd.read_sql("SELECT * FROM payments", conn)
        conn.close()
        
        if not df.empty:
            k1, k2, k3, k4 = st.columns(4)
            total = df['valor_pagto'].sum()
            benef = df['num_cartao'].nunique()
            projs = df['programa'].nunique()
            gers = df['gerenciadora'].nunique()
            k1.metric("Total Pago", f"R$ {total:,.2f}")
            k2.metric("Beneficiários Únicos", benef)
            k3.metric("Projetos Ativos", projs)
            k4.metric("Gerenciadoras", gers)
            
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Total por Projeto")
                g1 = df.groupby('programa')['valor_pagto'].sum().reset_index()
                st.plotly_chart(px.bar(g1, x='valor_pagto', y='programa', orientation='h'), use_container_width=True)
            with c2:
                st.subheader("Por Gerenciadora")
                g2 = df.groupby('gerenciadora')['valor_pagto'].sum().reset_index()
                st.plotly_chart(px.pie(g2, names='gerenciadora', values='valor_pagto'), use_container_width=True)
        else: st.info("Sem dados.")

    elif choice == "Manuais e Treinamento":
        render_header()
        st.markdown("### 📚 Manuais e Treinamento")
        
        role = user['role']
        
        # Exibir manual básico para todos
        with st.expander("📘 Manual Operacional Básico (Usuário)", expanded=True):
            content_user = get_manual_content("usuario")
            st.markdown(content_user)
            pdf_user = create_manual_pdf("Manual Operacional Básico", content_user)
            if pdf_user:
                st.download_button("Baixar PDF (Básico)", pdf_user, "manual_usuario.pdf", "application/pdf")

        # Exibir manual de equipe se for admin
        if role in ['admin_equipe', 'admin_ti']:
            with st.expander("📗 Manual de Gestão e Correção (Líderes)"):
                content_team = get_manual_content("admin_equipe")
                st.markdown(content_team)
                pdf_team = create_manual_pdf("Manual de Gestão e Correção", content_team)
                if pdf_team:
                    st.download_button("Baixar PDF (Gestão)", pdf_team, "manual_gestao.pdf", "application/pdf")

        # Exibir manual técnico se for TI
        if role == 'admin_ti':
            with st.expander("📕 Manual Técnico e Auditoria (TI)"):
                content_ti = get_manual_content("admin_ti")
                st.markdown(content_ti)
                pdf_ti = create_manual_pdf("Manual Técnico", content_ti)
                if pdf_ti:
                    st.download_button("Baixar PDF (Técnico)", pdf_ti, "manual_tecnico.pdf", "application/pdf")

    elif choice == "Upload e Processamento":
        render_header()
        st.markdown("### 📂 Upload de Pagamentos")
        files = st.file_uploader("Arquivos (CSV/XLSX)", accept_multiple_files=True)
        
        if files and st.button("Processar Arquivos"):
            conn = get_db_connection()
            exist = pd.read_sql("SELECT DISTINCT arquivo_origem FROM payments", conn)['arquivo_origem'].tolist()
            conn.close()
            dfs = []
            for f in files:
                if f.name in exist:
                    st.warning(f"Ignorado (já existe): {f.name}")
                    continue
                if 'REL.CADASTRO' in f.name.upper():
                    st.warning(f"Ignorado (Arquivo Banco): {f.name}")
                    continue
                try:
                    if f.name.endswith('.csv'): 
                        try: df = pd.read_csv(f, sep=';', encoding='latin1', dtype=str, low_memory=False)
                        except: f.seek(0); df = pd.read_csv(f, sep=',', encoding='utf-8', dtype=str, low_memory=False)
                    else: df = pd.read_excel(f, dtype=str)
                    df_std = standardize_dataframe(df, f.name)
                    if not df_std.empty: dfs.append(df_std)
                except Exception as e: st.error(f"Erro {f.name}: {e}")
            
            if dfs:
                final = pd.concat(dfs, ignore_index=True)
                conn = get_db_connection()
                final.to_sql('payments', conn, if_exists='append', index=False)
                conn.close()
                log_action(user['email'], "UPLOAD", f"Upload de {len(files)} arquivos")
                st.success(f"{len(final)} registros salvos.")
                
                crit = detect_critical_duplicates(final)
                if not crit.empty:
                    st.error("🚨 ERROS CRÍTICOS ENCONTRADOS NO UPLOAD!")
                    st.dataframe(crit, use_container_width=True)

    elif choice == "Análise e Correção":
        render_header()
        st.markdown("### 🛠️ Análise e Auditoria")
        conn = get_db_connection()
        df = pd.read_sql("SELECT * FROM payments", conn)
        conn.close()
        
        if not df.empty:
            crit_all = detect_critical_duplicates(df)
            if not crit_all.empty:
                st.error(f"🚨 {len(crit_all)} Inconsistências Críticas Encontradas")
                st.dataframe(crit_all, use_container_width=True)
            else: st.success("✅ Base íntegra.")
            
            st.markdown("### Edição de Dados")
            if user['role'] in ['admin_ti', 'admin_equipe']:
                edited_df = st.data_editor(df, num_rows="dynamic", key="editor_analise")
                if st.button("Salvar Correções"):
                    conn = get_db_connection()
                    conn.execute("DELETE FROM payments")
                    edited_df.to_sql('payments', conn, if_exists='append', index=False)
                    conn.commit()
                    conn.close()
                    log_action(user['email'], "CORRECAO_DADOS", "Usuário aplicou correções")
                    st.success("Dados atualizados!")
                    st.rerun()
            else: st.dataframe(df)

    elif choice == "Relatórios e Exportação":
        render_header()
        st.markdown("### 📥 Relatórios e Exportação")
        conn = get_db_connection()
        df = pd.read_sql("SELECT * FROM payments", conn)
        conn.close()
        
        if not df.empty:
            projs = df['programa'].unique()
            sel_proj = st.multiselect("Filtrar Projeto", projs, default=projs)
            df_exp = df[df['programa'].isin(sel_proj)]
            
            st.markdown("---")
            
            c1, c2, c3, c4 = st.columns(4)
            
            # 1. PDF (Esquerda - Destaque)
            with c1:
                st.markdown("###### 📑 Relatório Executivo")
                if st.button("Gerar Relatório PDF"):
                    pdf_data = generate_pdf_report(df_exp)
                    if isinstance(pdf_data, bytes):
                        st.download_button("⬇️ Baixar PDF", pdf_data, "relatorio_executivo.pdf", "application/pdf")
                        log_action(user['email'], "RELATORIO_PDF", "Gerou relatório executivo")
                    else:
                        st.error(pdf_data)
            
            # 2. CSV
            with c2:
                st.markdown("###### 📄 Dados Completos")
                csv = df_exp.to_csv(index=False, sep=';').encode('utf-8-sig')
                st.download_button("⬇️ Baixar CSV", csv, "dados_pot.csv", "text/csv")
            
            # 3. Excel
            with c3:
                st.markdown("###### 📊 Planilha Excel")
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer: df_exp.to_excel(writer, index=False)
                st.download_button("⬇️ Baixar Excel", buffer.getvalue(), "dados_pot.xlsx", "application/vnd.ms-excel")
            
            # 4. TXT
            with c4:
                st.markdown("###### 🏦 Layout Banco (BB)")
                txt = generate_bb_txt(df_exp)
                st.download_button("⬇️ Baixar TXT", txt, "remessa_bb.txt", "text/plain")

    elif choice == "Conferência Bancária (BB)":
        render_header()
        st.markdown("### 🏦 Conferência BB")
        conn = get_db_connection()
        hist = pd.read_sql("SELECT * FROM bank_discrepancies", conn)
        conn.close()
        
        if not hist.empty:
            st.warning(f"{len(hist)} divergências no histórico.")
            st.dataframe(hist)
            if st.button("Limpar Histórico"):
                conn = get_db_connection()
                conn.execute("DELETE FROM bank_discrepancies")
                conn.commit()
                conn.close()
                st.rerun()
            
            pdf_conf = generate_conference_pdf(hist)
            if isinstance(pdf_conf, bytes):
                st.download_button("📑 Baixar Relatório PDF (Divergências)", pdf_conf, "divergencias_bb.pdf", "application/pdf")
                
        files = st.file_uploader("TXT Banco", accept_multiple_files=True)
        if files and st.button("Processar"):
            dfs = []
            for f in files:
                try:
                    d = parse_bb_txt_cadastro(f)
                    d['arquivo_bb'] = f.name
                    dfs.append(d)
                except: st.error(f"Erro {f.name}")
            
            if dfs:
                final_bb = pd.concat(dfs)
                conn = get_db_connection()
                df_sys = pd.read_sql("SELECT num_cartao, nome, cpf FROM payments", conn)
                
                final_bb['key'] = final_bb['num_cartao'].astype(str).str.replace(r'^0+','', regex=True)
                df_sys['key'] = df_sys['num_cartao'].astype(str).str.replace(r'^0+','', regex=True).str.replace(r'\.0$','', regex=True)
                
                merged = pd.merge(df_sys, final_bb, on='key', suffixes=('_sis', '_bb'))
                divs = []
                for _, row in merged.iterrows():
                    nm_s = str(row.get('nome_sis','')).strip().upper()
                    nm_b = str(row.get('nome_bb','')).strip().upper()
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
                    st.error(f"{len(dd)} divergências encontradas!")
                    st.rerun()
                else: st.success("Sucesso! Sem divergências.")
                conn.close()

    elif choice == "Gestão de Equipe":
        render_header()
        
        # --- SEÇÃO DE CADASTRO ---
        st.markdown("### Adicionar Novo Usuário")
        with st.expander("📝 Formulário de Cadastro", expanded=False):
            with st.form("add_user"):
                new_email = st.text_input("E-mail (Institucional)")
                new_name = st.text_input("Nome Completo")
                new_role = st.selectbox("Perfil de Acesso", ["user", "admin_equipe"])
                if st.form_submit_button("Criar Usuário"):
                    if new_email.endswith("@prefeitura.sp.gov.br"):
                        conn = get_db_connection()
                        try:
                            # Senha padrão 'mudar123'
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

        st.markdown("---")
        
        # --- SEÇÃO DE LISTAGEM E GERENCIAMENTO ---
        st.markdown("### 👥 Usuários Cadastrados")
        st.info("Utilize os botões à direita para resetar a senha (volta para 'mudar123') ou excluir o usuário.")

        # Buscar usuários do banco
        conn = get_db_connection()
        users_db = pd.read_sql("SELECT email, name, role FROM users", conn)
        conn.close()
        
        # Cabeçalho da Tabela Visual
        c1, c2, c3, c4, c5 = st.columns([3, 3, 2, 1.5, 1.5])
        c1.markdown("**Nome**")
        c2.markdown("**E-mail**")
        c3.markdown("**Perfil**")
        c4.markdown("**Resetar**")
        c5.markdown("**Excluir**")
        
        st.markdown("<hr style='margin: 5px 0'>", unsafe_allow_html=True)

        for index, row in users_db.iterrows():
            # Container para cada linha para manter o visual limpo
            with st.container():
                c1, c2, c3, c4, c5 = st.columns([3, 3, 2, 1.5, 1.5])
                
                c1.write(row['name'])
                c2.write(row['email'])
                
                # Formatar o papel para ficar mais legível
                role_display = "Admin TI" if row['role'] == 'admin_ti' else ("Líder/Admin" if row['role'] == 'admin_equipe' else "Analista")
                c3.write(role_display)
                
                # Lógica dos Botões
                # Não permitir ações sobre si mesmo para evitar trancar-se fora
                is_self = (row['email'] == user['email'])
                
                # Botão Resetar Senha
                if c4.button("🔄", key=f"btn_rst_{row['email']}", help="Reseta a senha para 'mudar123' e força troca no login", disabled=is_self):
                    conn = get_db_connection()
                    pass_reset = hashlib.sha256('mudar123'.encode()).hexdigest()
                    conn.execute("UPDATE users SET password = ?, first_login = 1 WHERE email = ?", (pass_reset, row['email']))
                    conn.commit()
                    conn.close()
                    log_action(user['email'], "RESET_SENHA", f"Resetou senha de {row['email']}")
                    st.toast(f"Senha de {row['name']} resetada para 'mudar123'!")
                    
                # Botão Excluir
                if c5.button("🗑️", key=f"btn_del_{row['email']}", help="Exclui o usuário permanentemente", disabled=is_self):
                    conn = get_db_connection()
                    conn.execute("DELETE FROM users WHERE email = ?", (row['email'],))
                    conn.commit()
                    conn.close()
                    log_action(user['email'], "EXCLUIR_USUARIO", f"Excluiu usuário {row['email']}")
                    st.success(f"Usuário {row['name']} removido.")
                    st.rerun()
                
                st.markdown("<div class='user-row'></div>", unsafe_allow_html=True)


    elif choice == "Administração TI" and user['role'] == 'admin_ti':
        render_header()
        st.markdown("### 🛡️ Painel de Auditoria e Controle")
        
        conn = get_db_connection()
        logs = pd.read_sql("SELECT * FROM audit_logs ORDER BY timestamp DESC", conn)
        conn.close()
        
        st.dataframe(logs, use_container_width=True)
        
        col_pdf, col_cls = st.columns(2)
        pdf_logs = generate_audit_log_pdf(logs)
        if isinstance(pdf_logs, bytes):
            col_pdf.download_button("📄 Baixar Logs (PDF)", pdf_logs, "auditoria_sistema.pdf", "application/pdf")
            
        if col_cls.button("⚠️ LIMPAR LOGS"):
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
            st.success("Banco limpo.")

if __name__ == "__main__":
    init_db()
    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
    
    if st.session_state['logged_in']: 
        if st.session_state['user_info']['first_login']: change_password_screen()
        else: main_app()
    else: login_screen()
