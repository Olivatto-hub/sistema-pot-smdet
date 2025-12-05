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
    /* Ajuste para tema escuro automático do Streamlit */
    @media (prefers-color-scheme: dark) {
        .metric-card {
            background-color: #262730;
            border-color: #444;
        }
        .header-secretaria { color: #bbb; }
        .header-programa { color: #93C5FD; }
        .header-sistema { color: #60A5FA; }
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
    """Inicializa o banco de dados e atualiza esquema se necessário."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Tabela de Usuários
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            password TEXT,
            role TEXT,
            name TEXT,
            first_login INTEGER DEFAULT 1
        )
    ''')
    
    # Tabela de Dados (Beneficiários/Pagamentos)
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
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Tabela de Divergências Bancárias
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
            tipo_erro TEXT, -- 'CRITICO' ou 'DIVERGENCIA'
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Verificação de Migração (coluna gerenciadora)
    try:
        c.execute("SELECT gerenciadora FROM payments LIMIT 1")
    except sqlite3.OperationalError:
        try:
            c.execute("ALTER TABLE payments ADD COLUMN gerenciadora TEXT")
            conn.commit()
        except Exception as e:
            pass 
            
    # Verificação de Migração (coluna tipo_erro na tabela bank_discrepancies)
    try:
        c.execute("SELECT tipo_erro FROM bank_discrepancies LIMIT 1")
    except sqlite3.OperationalError:
        try:
            c.execute("ALTER TABLE bank_discrepancies ADD COLUMN tipo_erro TEXT")
            conn.commit()
        except Exception as e:
            pass

    # Criar usuário Admin padrão se não existir
    c.execute("SELECT * FROM users WHERE email = 'admin@prefeitura.sp.gov.br'")
    if not c.fetchone():
        # Senha padrão hash: smdet2025
        default_pass = hashlib.sha256('smdet2025'.encode()).hexdigest()
        c.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?)", 
                  ('admin@prefeitura.sp.gov.br', default_pass, 'admin_ti', 'Administrador TI', 0))
    
    conn.commit()
    conn.close()

def get_db_connection():
    return sqlite3.connect(DB_FILE)

# ===========================================
# LÓGICA DE NEGÓCIO E PROCESSAMENTO
# ===========================================

# Mapeamento de Colunas
COLUMN_MAP = {
    # Chaves Principais
    'num cartao': 'num_cartao', 'numcartao': 'num_cartao', 'numcartão': 'num_cartao', 
    'código': 'num_cartao', 'codigo': 'num_cartao', 'c?igo': 'num_cartao',
    # Dados Pessoais
    'nome': 'nome', 'nome do beneficiário': 'nome', 'participante': 'nome',
    'cpf': 'cpf',
    'rg': 'rg',
    # Financeiro e Estrutural
    'valor pagto': 'valor_pagto', 'valorpagto': 'valor_pagto', 'valor total': 'valor_pagto',
    'dias a apagar': 'qtd_dias', 'dias': 'qtd_dias',
    'data pagto': 'data_pagto', 'datapagto': 'data_pagto',
    'projeto': 'programa',
    'mês': 'mes_ref', 'mes': 'mes_ref',
    'gerenciadora': 'gerenciadora', 'entidade': 'gerenciadora', 'parceiro': 'gerenciadora', 'os': 'gerenciadora'
}

def normalize_text(text):
    if isinstance(text, str):
        return text.strip().lower()
    return text

def remove_total_row(df):
    """Verifica e remove linha de totalização."""
    if df.empty:
        return df

    last_idx = df.index[-1]
    id_cols = ['num_cartao', 'cpf', 'nome', 'rg']
    
    is_id_empty = True
    for col in id_cols:
        if col in df.columns:
            val = df.at[last_idx, col]
            if pd.notna(val) and str(val).strip() != '' and str(val).strip().lower() != 'nan':
                is_id_empty = False
                break
    
    if is_id_empty:
        df = df.drop(last_idx)
        
    return df

def parse_bb_txt_cadastro(file):
    """Lê arquivos de Cadastro do BB (Layout Posicional)."""
    colspecs = [
        (0, 11),   # Tipo / ID
        (11, 42),  # Projeto
        (42, 52),  # NumCartao
        (52, 92),  # Nome
        (92, 104), # RG
        (104, 119) # CPF
    ]
    names = ['tipo', 'projeto_bb', 'num_cartao', 'nome_bb', 'rg_bb', 'cpf_bb']
    
    file.seek(0)
    # Adicionado low_memory=False para evitar warnings em arquivos grandes
    df = pd.read_fwf(file, colspecs=colspecs, names=names, dtype=str, encoding='latin1')
    
    if 'tipo' in df.columns:
        df = df[df['tipo'].astype(str).str.strip() == '1'].copy()
        
    df['num_cartao'] = df['num_cartao'].str.strip()
    df['nome_bb'] = df['nome_bb'].str.strip()
    df['cpf_bb'] = df['cpf_bb'].str.replace(r'\D', '', regex=True)
    
    return df

def standardize_dataframe(df, filename):
    """Padroniza colunas, extrai metadados e trata Gerenciadoras."""
    df.columns = [str(c).strip() for c in df.columns]
    
    rename_dict = {}
    for col in df.columns:
        col_lower = col.lower()
        if col_lower in COLUMN_MAP:
            rename_dict[col] = COLUMN_MAP[col_lower]
        else:
            for key, val in COLUMN_MAP.items():
                if key == col_lower:
                    rename_dict[col] = val
                    break
            if col not in rename_dict:
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
        if col not in df.columns:
            df[col] = None 

    df = remove_total_row(df)

    if 'num_cartao' in df.columns:
        df['num_cartao'] = df['num_cartao'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    
    if 'cpf' in df.columns:
        df['cpf'] = df['cpf'].astype(str).str.replace(r'\D', '', regex=True).replace('nan', '')
    
    def clean_currency(x):
        if isinstance(x, str):
            x = x.replace('R$', '').replace(' ', '')
            if ',' in x and '.' in x: 
                x = x.replace('.', '').replace(',', '.')
            elif ',' in x: 
                x = x.replace(',', '.')
        try:
            return float(x)
        except:
            return 0.0
            
    if 'valor_pagto' in df.columns:
        df['valor_pagto'] = df['valor_pagto'].apply(clean_currency)
        
    df['arquivo_origem'] = filename
    
    cols_to_keep = ['programa', 'gerenciadora', 'num_cartao', 'nome', 'cpf', 'rg', 'valor_pagto', 'data_pagto', 'qtd_dias', 'mes_ref', 'ano_ref', 'arquivo_origem']
    final_cols = [c for c in cols_to_keep if c in df.columns]
    
    return df[final_cols]

def get_brasilia_time():
    """Retorna a data e hora atual no fuso horário de Brasília (UTC-3)."""
    return datetime.now(timezone(timedelta(hours=-3)))

def generate_bb_txt(df):
    """Gera string no formato Fixed-Width do Banco do Brasil."""
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

def generate_pdf_report(df_filtered):
    """Gera Relatório Executivo em PDF."""
    if FPDF is None:
        return b"Erro: Biblioteca FPDF nao instalada."
        
    pdf = FPDF()
    pdf.add_page()
    
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 8, "Prefeitura de São Paulo", 0, 1, 'C')
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 8, "Secretaria Municipal do Desenvolvimento Econômico e Trabalho", 0, 1, 'C')
    pdf.ln(5)
    
    pdf.set_fill_color(220, 220, 220)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 12, "Relatório Executivo POT", 1, 1, 'C', fill=True)
    pdf.ln(10)
    
    total_valor = df_filtered['valor_pagto'].sum() if 'valor_pagto' in df_filtered.columns else 0.0
    total_benef = df_filtered['num_cartao'].nunique() if 'num_cartao' in df_filtered.columns else 0
    total_projetos = df_filtered['programa'].nunique() if 'programa' in df_filtered.columns else 0
    total_gerenciadoras = df_filtered['gerenciadora'].nunique() if 'gerenciadora' in df_filtered.columns else 0
    total_registros = len(df_filtered)
    
    # Data com Fuso Horário de Brasília
    data_br = get_brasilia_time().strftime('%d/%m/%Y às %H:%M')
    
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 6, f"Data de Geração: {data_br}", 0, 1, 'R')
    pdf.ln(5)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "1. Resumo Analítico Consolidado", 0, 1)
    
    pdf.set_font("Arial", '', 12)
    pdf.cell(100, 8, "Total de Valores Pagos:", 1)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 8, f"R$ {total_valor:,.2f}", 1, 1)
    
    pdf.set_font("Arial", '', 12)
    pdf.cell(100, 8, "Total de Beneficiários Únicos:", 1)
    pdf.cell(0, 8, str(total_benef), 1, 1)
    
    pdf.cell(100, 8, "Total de Projetos Ativos:", 1)
    pdf.cell(0, 8, str(total_projetos), 1, 1)

    pdf.cell(100, 8, "Total de Gerenciadoras:", 1)
    pdf.cell(0, 8, str(total_gerenciadoras), 1, 1)
    
    pdf.cell(100, 8, "Total de Registros Processados:", 1)
    pdf.cell(0, 8, str(total_registros), 1, 1)
    
    pdf.ln(5)

    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "2. Visualização Gráfica (Por Projeto e Gerenciadora)", 0, 1)
    
    if plt is not None and 'programa' in df_filtered.columns and 'valor_pagto' in df_filtered.columns:
        try:
            plt.figure(figsize=(10, 8))
            
            plt.subplot(2, 1, 1)
            group_proj = df_filtered.groupby('programa')['valor_pagto'].sum().sort_values(ascending=True)
            colors_p = plt.cm.Paired(range(len(group_proj)))
            plt.barh(group_proj.index, group_proj.values, color=colors_p)
            plt.xlabel('Valor Pago (R$)')
            plt.title('Total Pago por Projeto')
            plt.grid(axis='x', linestyle='--', alpha=0.7)
            
            if 'gerenciadora' in df_filtered.columns:
                plt.subplot(2, 1, 2)
                group_ger = df_filtered.groupby('gerenciadora')['valor_pagto'].sum().sort_values(ascending=True)
                colors_g = plt.cm.Pastel1(range(len(group_ger)))
                plt.barh(group_ger.index, group_ger.values, color=colors_g)
                plt.xlabel('Valor Pago (R$)')
                plt.title('Total Pago por Gerenciadora')
                plt.grid(axis='x', linestyle='--', alpha=0.7)

            plt.tight_layout()
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
                plt.savefig(tmpfile.name, dpi=100)
                tmp_filename = tmpfile.name
            
            pdf.image(tmp_filename, x=10, w=190)
            pdf.ln(5)
            plt.close()
            os.remove(tmp_filename)
        except Exception as e:
            pdf.set_font("Arial", 'I', 10)
            pdf.cell(0, 10, f"Erro ao gerar gráfico: {str(e)}", 0, 1)
    else:
        pdf.set_font("Arial", 'I', 12)
        pdf.cell(0, 10, "Dados insuficientes ou biblioteca gráfica indisponível.", 0, 1)

    pdf.add_page()
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "3. Detalhamento Financeiro por Projeto", 0, 1)
    
    if 'programa' in df_filtered.columns and 'valor_pagto' in df_filtered.columns:
        group_proj_det = df_filtered.groupby('programa').agg({
            'valor_pagto': 'sum',
            'num_cartao': 'count'
        }).reset_index().sort_values('valor_pagto', ascending=False)
        
        pdf.set_font("Arial", 'B', 10)
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(90, 8, "PROJETO", 1, 0, 'L', True)
        pdf.cell(40, 8, "QTD REGISTROS", 1, 0, 'C', True)
        pdf.cell(60, 8, "VALOR TOTAL (R$)", 1, 1, 'R', True)
        
        pdf.set_font("Arial", '', 10)
        for _, row in group_proj_det.iterrows():
            pdf.cell(90, 8, str(row['programa'])[:40], 1)
            pdf.cell(40, 8, str(row['num_cartao']), 1, 0, 'C')
            pdf.cell(60, 8, f"{row['valor_pagto']:,.2f}", 1, 1, 'R')
    else:
        pdf.cell(0, 10, "Dados insuficientes.", 0, 1)
        
    pdf.ln(5)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "4. Detalhamento por Gerenciadora", 0, 1)
    
    if 'gerenciadora' in df_filtered.columns:
        group_ger_det = df_filtered.groupby('gerenciadora').agg({
            'valor_pagto': 'sum',
            'num_cartao': 'count'
        }).reset_index().sort_values('valor_pagto', ascending=False)
        
        pdf.set_font("Arial", 'B', 10)
        pdf.set_fill_color(230, 240, 255)
        pdf.cell(90, 8, "GERENCIADORA", 1, 0, 'L', True)
        pdf.cell(40, 8, "QTD REGISTROS", 1, 0, 'C', True)
        pdf.cell(60, 8, "VALOR TOTAL (R$)", 1, 1, 'R', True)
        
        pdf.set_font("Arial", '', 10)
        for _, row in group_ger_det.iterrows():
            pdf.cell(90, 8, str(row['gerenciadora'])[:40], 1)
            pdf.cell(40, 8, str(row['num_cartao']), 1, 0, 'C')
            pdf.cell(60, 8, f"{row['valor_pagto']:,.2f}", 1, 1, 'R')
    else:
        pdf.cell(0, 10, "Coluna de gerenciadora não encontrada.", 0, 1)

    pdf.ln(10)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "5. Relatório de Inconsistências (Ação Necessária)", 0, 1)
    
    cols_check = [c for c in ['cpf', 'nome', 'num_cartao'] if c in df_filtered.columns]
    
    if cols_check:
        sem_cpf = df_filtered[ (df_filtered['cpf'].isnull()) | (df_filtered['cpf'].astype(str).str.strip() == '') | (df_filtered['cpf'].astype(str).str.lower() == 'nan') ].shape[0]
        sem_nome = df_filtered[ (df_filtered['nome'].isnull()) | (df_filtered['nome'].astype(str).str.strip() == '') | (df_filtered['nome'].astype(str).str.lower() == 'nan') ].shape[0]
        sem_cartao = df_filtered[ (df_filtered['num_cartao'].isnull()) | (df_filtered['num_cartao'].astype(str).str.strip() == '') | (df_filtered['num_cartao'].astype(str).str.lower() == 'nan') ].shape[0]
        
        total_inconsistentes = sem_cpf + sem_nome + sem_cartao
        
        pdf.set_font("Arial", '', 10)
        
        if sem_cpf > 0:
            pdf.set_text_color(200, 0, 0)
            pdf.multi_cell(0, 6, f"Foram encontrados {sem_cpf} registros com dados cadastrais incompletos, CPFs ausentes. Estes registros devem ser corrigidos.")
            pdf.set_text_color(0, 0, 0)
        
        if sem_nome > 0:
            pdf.multi_cell(0, 6, f"Foram encontrados {sem_nome} registros sem NOME do beneficiário.")
            
        if sem_cartao > 0:
            pdf.multi_cell(0, 6, f"Foram encontrados {sem_cartao} registros sem NÚMERO DO CARTÃO.")
            
        if total_inconsistentes == 0:
             pdf.cell(0, 10, "Nenhuma inconsistência de cadastro (CPF/Nome/Cartão) identificada.", 0, 1)
        else:
            pdf.ln(5)
            mask = pd.Series(False, index=df_filtered.index)
            for col in cols_check:
                mask |= (df_filtered[col].isnull()) | (df_filtered[col].astype(str).str.strip() == '') | (df_filtered[col].astype(str).str.lower() == 'nan')
            
            inconsistent_df = df_filtered[mask]
            projetos_errados = inconsistent_df['programa'].unique()
            
            for proj in projetos_errados:
                pdf.set_font("Arial", 'B', 10)
                pdf.cell(0, 8, f"Projeto: {proj}", 0, 1)
                
                pdf.set_font("Arial", 'B', 8)
                pdf.set_fill_color(255, 230, 230)
                pdf.cell(70, 6, "NOME", 1, 0, 'L', True)
                pdf.cell(40, 6, "CPF", 1, 0, 'C', True)
                pdf.cell(40, 6, "CARTÃO", 1, 0, 'C', True)
                pdf.cell(40, 6, "OBSERVAÇÃO", 1, 1, 'L', True)
                
                pdf.set_font("Arial", '', 8)
                subset = inconsistent_df[inconsistent_df['programa'] == proj]
                
                for _, row in subset.iterrows():
                    nome = str(row.get('nome', ''))[:35]
                    cpf = str(row.get('cpf', ''))
                    cartao = str(row.get('num_cartao', ''))
                    
                    obs = []
                    if not nome or nome.lower() == 'nan': obs.append("Sem Nome")
                    if not cpf or cpf.lower() == 'nan': obs.append("Sem CPF")
                    if not cartao or cartao.lower() == 'nan': obs.append("Sem Cartão")
                    obs_str = ", ".join(obs)
                    
                    pdf.cell(70, 6, nome, 1)
                    pdf.cell(40, 6, cpf, 1, 0, 'C')
                    pdf.cell(40, 6, cartao, 1, 0, 'C')
                    pdf.cell(40, 6, obs_str, 1, 1)
                pdf.ln(5)

    else:
        pdf.cell(0, 10, "Colunas de verificação não encontradas.", 0, 1)
    
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "6. Observações de Processamento", 0, 1)
    pdf.set_font("Arial", '', 10)
    
    pdf.multi_cell(0, 6, 
        f"O presente relatório consolida os dados disponíveis na base do sistema. "
        "A integridade dos dados é fundamental para o sucesso dos pagamentos."
    )
    
    return pdf.output(dest='S').encode('latin-1')

def generate_conference_pdf(df_div):
    """Gera Relatório PDF específico para Divergências Bancárias."""
    if FPDF is None:
        return b"Erro: Biblioteca FPDF nao instalada."
        
    pdf = FPDF()
    pdf.add_page(orientation='L') # Paisagem para caber mais colunas
    
    # Cabeçalho
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 8, "Prefeitura de São Paulo", 0, 1, 'C')
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 8, "Secretaria Municipal do Desenvolvimento Econômico e Trabalho", 0, 1, 'C')
    pdf.ln(5)
    
    pdf.set_fill_color(255, 200, 200) # Fundo avermelhado
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 12, "Relatório de Conferência Bancária (Divergências)", 1, 1, 'C', fill=True)
    pdf.ln(10)
    
    # Data Brasilia
    data_br = get_brasilia_time().strftime('%d/%m/%Y às %H:%M')
    
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 6, f"Data de Geração: {data_br}", 0, 1, 'R')
    pdf.ln(5)
    
    # KPIs de Erros
    criticos = df_div[df_div['tipo_erro'] == 'CRITICO'].shape[0]
    gerais = df_div[df_div['tipo_erro'] == 'DIVERGENCIA'].shape[0]
    total_erros = len(df_div)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, f"Total de Inconsistências: {total_erros} (Críticas: {criticos} | Gerais: {gerais})", 0, 1)
    pdf.set_font("Arial", '', 10)
    pdf.multi_cell(0, 6, "Abaixo estão listados os beneficiários com problemas cadastrais ou conflitos entre o sistema e o retorno bancário.")
    pdf.ln(5)
    
    # Tabela
    pdf.set_font("Arial", 'B', 9)
    pdf.set_fill_color(240, 240, 240)
    
    # Ajuste de larguras para Paisagem
    w_cartao = 35
    w_nome = 60
    w_div = 100
    w_tipo = 30
    w_arq = 50
    
    pdf.cell(w_cartao, 8, "CARTÃO", 1, 0, 'C', True)
    pdf.cell(w_nome, 8, "NOME", 1, 0, 'L', True)
    pdf.cell(w_div, 8, "DESCRIÇÃO DO ERRO", 1, 0, 'L', True)
    pdf.cell(w_tipo, 8, "TIPO", 1, 0, 'C', True)
    pdf.cell(w_arq, 8, "ARQUIVO", 1, 1, 'C', True)
    
    pdf.set_font("Arial", '', 8)
    for _, row in df_div.iterrows():
        cartao = str(row['cartao'])
        nome = str(row['nome_bb'])[:30] # Nome do banco é a referência da falha
        div = str(row['divergencia'])[:60]
        tipo = str(row['tipo_erro'])
        arq = str(row['arquivo_origem'])[:25]
        
        # Highlight Crítico em Vermelho
        if tipo == 'CRITICO':
            pdf.set_text_color(200, 0, 0)
        else:
            pdf.set_text_color(0, 0, 0)
            
        pdf.cell(w_cartao, 6, cartao, 1, 0, 'C')
        pdf.cell(w_nome, 6, nome, 1, 0, 'L')
        pdf.cell(w_div, 6, div, 1, 0, 'L')
        pdf.cell(w_tipo, 6, tipo, 1, 0, 'C')
        pdf.cell(w_arq, 6, arq, 1, 1, 'C')
        
    return pdf.output(dest='S').encode('latin-1')

# ===========================================
# INTERFACE E FLUXO DO USUÁRIO
# ===========================================

def login_screen():
    render_header()
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        with st.form("login_form"):
            st.markdown("<h3 style='text-align: center;'>Acesso Restrito</h3>", unsafe_allow_html=True)
            email = st.text_input("E-mail (@prefeitura.sp.gov.br)")
            password = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar")
            
            if submitted:
                if not email.endswith("@prefeitura.sp.gov.br"):
                    st.error("Apenas e-mails institucionais permitidos.")
                    return

                pass_hash = hashlib.sha256(password.encode()).hexdigest()
                
                conn = get_db_connection()
                user = conn.execute("SELECT * FROM users WHERE email = ? AND password = ?", (email, pass_hash)).fetchone()
                conn.close()
                
                if user:
                    st.session_state['logged_in'] = True
                    st.session_state['user_info'] = {
                        'email': user[0],
                        'role': user[2],
                        'name': user[3],
                        'first_login': user[4]
                    }
                    st.rerun()
                else:
                    st.error("Credenciais inválidas.")

def change_password_screen():
    render_header()
    st.warning("⚠️ Este é seu primeiro acesso. Por favor, defina uma nova senha.")
    with st.form("new_pass_form"):
        new_pass = st.text_input("Nova Senha", type="password")
        confirm_pass = st.text_input("Confirmar Senha", type="password")
        submit = st.form_submit_button("Alterar Senha")
        
        if submit:
            if new_pass == confirm_pass and len(new_pass) > 5:
                conn = get_db_connection()
                new_hash = hashlib.sha256(new_pass.encode()).hexdigest()
                conn.execute("UPDATE users SET password = ?, first_login = 0 WHERE email = ?", 
                             (new_hash, st.session_state['user_info']['email']))
                conn.commit()
                conn.close()
                st.success("Senha alterada com sucesso! Recarregando...")
                st.session_state['user_info']['first_login'] = 0
                st.rerun()
            else:
                st.error("As senhas não coincidem ou são muito curtas.")

def main_app():
    user = st.session_state['user_info']
    
    st.sidebar.markdown(f"### Olá, {user['name']}")
    st.sidebar.caption(f"Perfil: {user['role'].upper().replace('_', ' ')}")
    
    menu_options = ["Dashboard", "Upload e Processamento", "Análise e Correção", "Conferência Bancária (BB)", "Relatórios e Exportação"]
    
    if user['role'] in ['admin_ti', 'admin_equipe']:
        menu_options.append("Gestão de Equipe")
    if user['role'] == 'admin_ti':
        menu_options.append("Administração TI (DB)")
        
    choice = st.sidebar.radio("Navegação", menu_options)
    
    if st.sidebar.button("Sair"):
        st.session_state.clear()
        st.rerun()
        
    # --- PÁGINAS ---
    
    if choice == "Upload e Processamento":
        render_header()
        st.markdown("<h3 class='main-header'>📂 Upload de Arquivos de Pagamento</h3>", unsafe_allow_html=True)
        st.info("Arraste arquivos CSV ou Excel contendo valores a pagar.")
        
        uploaded_files = st.file_uploader("Selecione os arquivos", accept_multiple_files=True, type=['csv', 'xlsx', 'txt'])
        
        if uploaded_files:
            if st.button(f"Processar {len(uploaded_files)} Arquivos"):
                conn = get_db_connection()
                existing_files_df = pd.read_sql("SELECT DISTINCT arquivo_origem FROM payments", conn)
                conn.close()
                existing_files = set(existing_files_df['arquivo_origem'].tolist()) if not existing_files_df.empty else set()
                
                all_data = []
                progress_bar = st.progress(0)
                
                for idx, file in enumerate(uploaded_files):
                    if file.name in existing_files:
                        st.warning(f"⚠️ O arquivo '{file.name}' já consta no banco de dados e foi ignorado.")
                        continue
                    
                    if 'REL.CADASTRO' in file.name.upper():
                        st.warning(f"⚠️ Arquivo '{file.name}' identificado como relatório de cadastro (sem valor). Utilize a aba 'Conferência Bancária (BB)' para processá-lo.")
                        continue
                        
                    try:
                        # Adicionado low_memory=False para evitar DtypeWarning
                        if file.name.endswith('.csv'):
                            try:
                                df = pd.read_csv(file, sep=';', encoding='latin1', dtype=str, low_memory=False)
                            except:
                                file.seek(0)
                                df = pd.read_csv(file, sep=',', encoding='utf-8', dtype=str, low_memory=False)
                        elif file.name.endswith('.xlsx'):
                            df = pd.read_excel(file, dtype=str)
                        elif file.name.endswith('.txt'):
                            df = pd.read_csv(file, sep=r'\s+', encoding='latin1', on_bad_lines='skip', dtype=str, low_memory=False)
                            
                        df_std = standardize_dataframe(df, file.name)
                        
                        if not df_std.empty:
                            all_data.append(df_std)
                        
                    except Exception as e:
                        st.error(f"Erro ao ler {file.name}: {e}")
                    
                    progress_bar.progress((idx + 1) / len(uploaded_files))
                
                if all_data:
                    final_df = pd.concat(all_data, ignore_index=True)
                    
                    conn = get_db_connection()
                    
                    db_cols = ['programa', 'gerenciadora', 'num_cartao', 'nome', 'cpf', 'rg', 'valor_pagto', 'mes_ref', 'arquivo_origem']
                    cols_to_save = [c for c in db_cols if c in final_df.columns]
                    
                    df_to_save = final_df[cols_to_save].copy()
                    df_to_save['status'] = 'IMPORTADO'
                    
                    df_to_save.to_sql('payments', conn, if_exists='append', index=False)
                    conn.close()
                    
                    st.success(f"Sucesso! {len(final_df)} novos registros processados e salvos.")
                    
                    if 'valor_pagto' in final_df.columns:
                        total_importado = final_df['valor_pagto'].sum()
                        st.metric(
                            label="💰 Valor Total nos Novos Arquivos", 
                            value=f"R$ {total_importado:,.2f}"
                        )
                    else:
                        st.warning("Coluna de valor não encontrada para cálculo do total.")
                    
                    st.markdown("### Prévia dos Dados:")
                    st.dataframe(final_df.head())
                else:
                    st.info("Nenhum dado financeiro novo processado.")

    elif choice == "Análise e Correção":
        render_header()
        st.markdown("<h3 class='main-header'>🛠️ Análise e Correção de Dados</h3>", unsafe_allow_html=True)
        
        conn = get_db_connection()
        try:
            df = pd.read_sql("SELECT * FROM payments", conn)
        except:
            df = pd.DataFrame()
        conn.close()
        
        if df.empty:
            st.warning("Banco de Dados vazio. Faça upload de arquivos primeiro.")
        else:
            col_f1, col_f2 = st.columns(2)
            projs = df['programa'].unique() if 'programa' in df.columns else []
            meses = df['mes_ref'].unique() if 'mes_ref' in df.columns else []
            
            filtro_proj = col_f1.multiselect("Filtrar Projeto", projs)
            filtro_mes = col_f2.multiselect("Filtrar Mês", meses)
            
            if filtro_proj: df = df[df['programa'].isin(filtro_proj)]
            if filtro_mes: df = df[df['mes_ref'].isin(filtro_mes)]
            
            df_display = df.fillna('')
            
            def highlight_issues(row):
                if not row.get('num_cartao') or not row.get('cpf') or not row.get('nome'):
                    return ['background-color: #ffcccc'] * len(row)
                return [''] * len(row)
            
            st.subheader("Registros")
            
            if user['role'] in ['admin_ti', 'admin_equipe']:
                edited_df = st.data_editor(df_display, num_rows="dynamic", key="data_editor")
                if st.button("Salvar Alterações (Simulado)"):
                    st.info("Update em lote simulado com sucesso.")
            else:
                st.dataframe(df_display.style.apply(highlight_issues, axis=1))
            
            if 'cpf' in df.columns:
                missing_cpf = df[ (df['cpf'] == '') | (df['cpf'].isnull()) ]
                if not missing_cpf.empty:
                    st.error(f"⚠️ {len(missing_cpf)} Registros sem CPF!")
                    st.dataframe(missing_cpf)

    elif choice == "Conferência Bancária (BB)":
        render_header()
        st.markdown("<h3 class='main-header'>🏦 Cruzamento de Dados e Malha Fina (BB)</h3>", unsafe_allow_html=True)
        
        # Recuperar dados persistidos
        conn = get_db_connection()
        try:
            stored_discrepancies = pd.read_sql("SELECT * FROM bank_discrepancies ORDER BY created_at DESC", conn)
        except:
            stored_discrepancies = pd.DataFrame()
        conn.close()
        
        # Mostrar Histórico se existir
        if not stored_discrepancies.empty:
            
            # Filtra Críticos
            criticos = stored_discrepancies[stored_discrepancies['tipo_erro'] == 'CRITICO']
            
            if not criticos.empty:
                st.error(f"🚨 ALERTA CRÍTICO: {len(criticos)} Inconsistências Graves de CPF/Cartão Encontradas!")
                st.dataframe(criticos)
                st.markdown("---")
            
            st.warning(f"⚠️ Histórico Geral: {len(stored_discrepancies)} divergências salvas.")
            st.dataframe(stored_discrepancies)
            
            col_d1, col_d2 = st.columns(2)
            
            if col_d1.button("🗑️ Limpar Histórico de Conferência"):
                conn = get_db_connection()
                conn.execute("DELETE FROM bank_discrepancies")
                conn.commit()
                conn.close()
                st.success("Histórico limpo!")
                st.rerun()
                
            # Gerar PDF das divergências salvas
            pdf_bytes_conf = generate_conference_pdf(stored_discrepancies)
            if isinstance(pdf_bytes_conf, bytes):
                col_d2.download_button("📑 Baixar Relatório PDF (Divergências)", pdf_bytes_conf, "relatorio_divergencias_bb.pdf", "application/pdf")
            else:
                col_d2.error(pdf_bytes_conf)
                
            st.markdown("---")

        st.info("Faça upload de novos arquivos 'REL.CADASTRO.OT' para comparar e atualizar a base.")
        
        bb_files = st.file_uploader("Arquivos de Retorno BB (.TXT)", accept_multiple_files=True, type=['txt'])
        
        if bb_files:
            if st.button("Processar, Cruzar Dados e Salvar"):
                all_bb_data = []
                for file in bb_files:
                    try:
                        df_bb = parse_bb_txt_cadastro(file)
                        df_bb['arquivo_bb'] = file.name
                        all_bb_data.append(df_bb)
                    except Exception as e:
                        st.error(f"Erro ao ler {file.name}: {e}")
                
                if all_bb_data:
                    final_bb = pd.concat(all_bb_data, ignore_index=True)
                    st.success(f"{len(final_bb)} registros lidos dos arquivos do Banco.")
                    
                    divergencias_to_save = []
                    
                    # 1. VERIFICAÇÃO DE DUPLICIDADE INTERNA (CPF Repetido no Arquivo)
                    # Verifica se o mesmo CPF aparece mais de uma vez com nomes ou cartões diferentes
                    if 'cpf_bb' in final_bb.columns:
                        dup_cpf_group = final_bb.groupby('cpf_bb')
                        for cpf, group in dup_cpf_group:
                            if len(group) > 1:
                                unique_cards = group['num_cartao'].unique()
                                unique_names = group['nome_bb'].unique()
                                
                                # Se houver variação de cartão ou nome para o mesmo CPF
                                if len(unique_cards) > 1 or len(unique_names) > 1:
                                    for _, row in group.iterrows():
                                         divergencias_to_save.append({
                                            'cartao': row['num_cartao'],
                                            'nome_sis': 'DUPLICIDADE INTERNA',
                                            'nome_bb': row['nome_bb'],
                                            'cpf_sis': row['cpf_bb'],
                                            'cpf_bb': row['cpf_bb'],
                                            'divergencia': f"CPF DUPLICADO NO ARQUIVO BB ({len(unique_cards)} cartões distintos)",
                                            'arquivo_origem': row['arquivo_bb'],
                                            'tipo_erro': 'CRITICO'
                                         })

                    # 2. CRUZAMENTO COM O SISTEMA (Baseado em Cartão E CPF)
                    conn = get_db_connection()
                    df_db = pd.read_sql("SELECT num_cartao, nome, cpf, programa FROM payments", conn)
                    conn.close()
                    
                    if df_db.empty:
                        st.error("Base de dados do sistema vazia. Não é possível comparar com DB.")
                    else:
                        # Padronização
                        final_bb['match_cartao'] = final_bb['num_cartao'].astype(str).str.strip().str.replace(r'^0+', '', regex=True)
                        final_bb['match_cpf'] = final_bb['cpf_bb'].astype(str).str.strip().str.replace(r'\D', '', regex=True).str.zfill(11) # Padroniza CPF 11 digitos
                        
                        df_db['match_cartao'] = df_db['num_cartao'].astype(str).str.strip().str.replace(r'^0+', '', regex=True).str.replace(r'\.0$', '', regex=True)
                        df_db['match_cpf'] = df_db['cpf'].astype(str).str.strip().str.replace(r'\D', '', regex=True).str.zfill(11)

                        # A) Merge por Cartão (Checa divergência de Nome/CPF para o mesmo cartão)
                        merged_card = pd.merge(df_db, final_bb, on='match_cartao', how='inner', suffixes=('_sis', '_bb'))
                        
                        for _, row in merged_card.iterrows():
                            nome_sis = str(row['nome_sis']).strip().upper() if 'nome_sis' in row else ''
                            nome_bb = str(row['nome_bb']).strip().upper()
                            cpf_sis = str(row.get('match_cpf_sis', '')).strip()
                            cpf_bb = str(row.get('match_cpf_bb', '')).strip()
                            
                            motivos = []
                            if nome_sis and nome_sis != nome_bb:
                                motivos.append(f"Nome Diferente")
                            if cpf_sis and cpf_bb and cpf_sis != cpf_bb:
                                motivos.append(f"CPF Diferente (SIS:{cpf_sis} != BB:{cpf_bb})")
                                
                            if motivos:
                                divergencias_to_save.append({
                                    'cartao': row['num_cartao_sis'] if 'num_cartao_sis' in row else row.get('num_cartao', 'N/A'),
                                    'nome_sis': nome_sis,
                                    'nome_bb': nome_bb,
                                    'cpf_sis': cpf_sis,
                                    'cpf_bb': cpf_bb,
                                    'divergencia': ", ".join(motivos),
                                    'arquivo_origem': row['arquivo_bb'],
                                    'tipo_erro': 'DIVERGENCIA'
                                })

                        # B) Merge por CPF (Checa se a mesma pessoa tem Cartão diferente no Banco vs Sistema)
                        # Isso pega o caso: "Subi um documento onde CPFs duplicados... contas diferentes"
                        merged_cpf = pd.merge(df_db, final_bb, on='match_cpf', how='inner', suffixes=('_sis', '_bb'))
                        
                        for _, row in merged_cpf.iterrows():
                            cartao_sis = str(row['match_cartao_sis'])
                            cartao_bb = str(row['match_cartao_bb'])
                            
                            # Se o CPF é o mesmo, mas o cartão no banco é diferente do sistema
                            if cartao_sis != cartao_bb:
                                divergencias_to_save.append({
                                    'cartao': f"SIS:{cartao_sis} / BB:{cartao_bb}",
                                    'nome_sis': row['nome_sis'],
                                    'nome_bb': row['nome_bb'],
                                    'cpf_sis': row['match_cpf'],
                                    'cpf_bb': row['match_cpf'],
                                    'divergencia': "MESMO CPF COM CARTÃO DIFERENTE NO BANCO",
                                    'arquivo_origem': row['arquivo_bb'],
                                    'tipo_erro': 'CRITICO' # Erro grave
                                })

                        # SALVAR TUDO
                        if divergencias_to_save:
                            # Remove duplicatas exatas na lista antes de salvar
                            unique_divs = {f"{d['cartao']}-{d['divergencia']}": d for d in divergencias_to_save}.values()
                            
                            df_div_save = pd.DataFrame(unique_divs)
                            df_div_save.to_sql('bank_discrepancies', conn, if_exists='append', index=False)
                            conn.commit()
                            conn.close()
                            
                            criticos_count = len(df_div_save[df_div_save['tipo_erro'] == 'CRITICO'])
                            if criticos_count > 0:
                                st.error(f"🚨 FORAM ENCONTRADOS {criticos_count} ERROS CRÍTICOS (DUPLICIDADE/CONFLITO CPF)!")
                            
                            st.success(f"✅ Processamento concluído. {len(df_div_save)} divergências registradas.")
                            st.rerun()
                        else:
                            st.success("✅ Nenhuma divergência encontrada nos cruzamentos.")
                            conn.close()

    elif choice == "Dashboard":
        render_header()
        st.markdown("<h3 class='main-header'>📊 Dashboard Executivo</h3>", unsafe_allow_html=True)
        
        conn = get_db_connection()
        try:
            df = pd.read_sql("SELECT * FROM payments", conn)
        except:
            df = pd.DataFrame()
        conn.close()
        
        if not df.empty and 'valor_pagto' in df.columns:
            filtro_ger = st.multiselect("Filtrar por Gerenciadora", df['gerenciadora'].unique())
            if filtro_ger:
                df = df[df['gerenciadora'].isin(filtro_ger)]

            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            kpi1.metric("Total Pagamentos", f"R$ {df['valor_pagto'].sum():,.2f}")
            kpi2.metric("Beneficiários Únicos", df['num_cartao'].nunique() if 'num_cartao' in df.columns else 0)
            kpi3.metric("Projetos Ativos", df['programa'].nunique() if 'programa' in df.columns else 0)
            kpi4.metric("Gerenciadoras", df['gerenciadora'].nunique() if 'gerenciadora' in df.columns else 0)
            
            st.markdown("---")
            
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Valor por Projeto")
                if 'programa' in df.columns:
                    proj_group = df.groupby('programa')['valor_pagto'].sum().reset_index()
                    fig_bar = px.bar(proj_group, x='programa', y='valor_pagto', color='programa', title="Total Pago por Projeto")
                    st.plotly_chart(fig_bar, use_container_width=True)
                
            with c2:
                st.subheader("Valor por Gerenciadora")
                if 'gerenciadora' in df.columns:
                    ger_group = df.groupby('gerenciadora')['valor_pagto'].sum().reset_index()
                    fig_pie = px.pie(ger_group, names='gerenciadora', values='valor_pagto', title="Distribuição por Gerenciadora")
                    st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("Sem dados suficientes para exibir dashboard.")

    elif choice == "Relatórios e Exportação":
        render_header()
        st.markdown("<h3 class='main-header'>📥 Exportação</h3>", unsafe_allow_html=True)
        
        conn = get_db_connection()
        try:
            df = pd.read_sql("SELECT * FROM payments", conn)
        except:
            df = pd.DataFrame()
        conn.close()
        
        if not df.empty:
            st.markdown("### Selecione os Filtros")
            c1, c2 = st.columns(2)
            projs = df['programa'].unique() if 'programa' in df.columns else []
            prog_filter = c1.multiselect("Projetos", projs, default=projs)
            
            if 'programa' in df.columns:
                df_export = df[df['programa'].isin(prog_filter)]
            else:
                df_export = df
            
            st.markdown("### Baixar Arquivos")
            c_csv, c_xls, c_txt, c_pdf = st.columns(4)
            
            csv = df_export.to_csv(index=False, sep=';').encode('utf-8-sig')
            c_csv.download_button("📄 Baixar CSV", csv, "pagamentos_pot.csv", "text/csv")
            
            buffer_xls = io.BytesIO()
            with pd.ExcelWriter(buffer_xls, engine='xlsxwriter') as writer:
                df_export.to_excel(writer, sheet_name='Pagamentos', index=False)
            c_xls.download_button("📊 Baixar Excel", buffer_xls.getvalue(), "pagamentos_pot.xlsx", "application/vnd.ms-excel")
            
            txt_content = generate_bb_txt(df_export)
            c_txt.download_button("🏦 Baixar TXT (BB)", txt_content, "remessa_bb.txt", "text/plain")
            
            if st.button("📑 Gerar Relatório PDF"):
                pdf_bytes = generate_pdf_report(df_export)
                if isinstance(pdf_bytes, str): # Erro retornado
                    st.error(pdf_bytes)
                else:
                    st.download_button("Baixar PDF", pdf_bytes, "relatorio_executivo.pdf", "application/pdf")
                
        else:
            st.warning("Sem dados.")

    elif choice == "Administração TI (DB)":
        render_header()
        st.markdown("<h3 class='main-header'>⚙️ Administração TI</h3>", unsafe_allow_html=True)
        st.error("Zona de Perigo! Ações irreversíveis.")
        
        if st.button("🗑️ LIMPAR TODO O BANCO DE DADOS"):
            conn = get_db_connection()
            conn.execute("DELETE FROM payments")
            conn.commit()
            conn.close()
            st.success("Banco limpo.")
            
        st.markdown("---")
        query = st.text_area("SQL Query", "SELECT * FROM users")
        if st.button("Executar"):
            try:
                conn = get_db_connection()
                res = pd.read_sql(query, conn)
                conn.close()
                st.dataframe(res)
            except Exception as e:
                st.error(f"Erro SQL: {e}")

    elif choice == "Gestão de Equipe":
        render_header()
        st.markdown("### Adicionar Usuário")
        with st.form("add_user"):
            new_email = st.text_input("E-mail")
            new_name = st.text_input("Nome")
            new_role = st.selectbox("Perfil", ["user", "admin_equipe"])
            sub_add = st.form_submit_button("Criar Usuário")
            
            if sub_add:
                if not new_email.endswith("@prefeitura.sp.gov.br"):
                    st.error("Domínio inválido.")
                else:
                    conn = get_db_connection()
                    try:
                        pass_temp = hashlib.sha256('mudar123'.encode()).hexdigest()
                        conn.execute("INSERT INTO users VALUES (?, ?, ?, ?, 1)", (new_email, pass_temp, new_role, new_name))
                        conn.commit()
                        st.success(f"Usuário {new_email} criado.")
                    except Exception as e:
                        st.error(f"Erro: {e}")
                    conn.close()

# ===========================================
# EXECUÇÃO PRINCIPAL
# ===========================================

if __name__ == "__main__":
    init_db()
    
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
        
    if not st.session_state['logged_in']:
        login_screen()
    else:
        if st.session_state['user_info']['first_login'] == 1:
            change_password_screen()
        else:
            main_app()
