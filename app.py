import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
import hashlib
import io
import re
import os
import time
import tempfile
import unicodedata
from datetime import datetime, timedelta, timezone
from collections import Counter # Necessário para o Backfilling

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

# Estilo CSS Personalizado (Mantido o seu + Backfilling)
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
    
    /* ESTILOS DO BACKFILLING (ADICIONADO PARA O MÓDULO NOVO) */
    .backfill-container {
        background-color: #151922;
        padding: 25px;
        border-radius: 8px;
        border: 1px solid #334155;
        color: #f1f5f9;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.5);
    }
    .backfill-header {
        font-size: 1.1rem;
        font-weight: 600;
        margin-bottom: 15px;
        border-bottom: 1px solid #334155;
        padding-bottom: 10px;
        color: #60a5fa;
    }
    .console-log {
        font-family: 'Courier New', monospace;
        color: #4ade80;
        font-size: 0.9rem;
        margin-top: 10px;
        padding: 10px;
        background-color: #0f172a;
        border-radius: 5px;
        border-left: 4px solid #4ade80;
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
            competencia TEXT,
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
    
    try:
        c.execute("ALTER TABLE payments ADD COLUMN competencia TEXT")
        c.execute("ALTER TABLE payments ADD COLUMN mes_ref TEXT") # Garantir existencia
        c.execute("ALTER TABLE payments ADD COLUMN ano_ref TEXT") # Garantir existencia
    except sqlite3.OperationalError:
        pass 

    c.execute('''
        CREATE TABLE IF NOT EXISTS bank_discrepancies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cartao TEXT,
            nome_sis TEXT,
            nome_bb TEXT,
            cpf_sis TEXT,
            cpf_bb TEXT,
            rg_sis TEXT,
            rg_bb TEXT,
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
    
    c.execute("SELECT * FROM users WHERE email = 'admin@prefeitura.sp.gov.br'")
    if not c.fetchone():
        default_pass = hashlib.sha256('smdet2025'.encode()).hexdigest()
        c.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?)", 
                  ('admin@prefeitura.sp.gov.br', default_pass, 'admin_ti', 'Administrador TI', 0))
    
    conn.commit()
    conn.close()

def get_db_connection():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def log_action(user_email, action, details):
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
    if tipo == "usuario":
        return """
        # Manual Operacional Básico - Sistema POT
        ## 1. Visão Geral
        Bem-vindo ao Sistema de Gestão e Monitoramento de Pagamentos do POT.
        ## 2. Validação de Dados Críticos
        - **CPFs Ausentes:** O sistema alerta imediatamente se um registro não tiver CPF.
        - **Cartão Ausente:** Registros sem número de cartão são considerados críticos.
        ## 3. Upload e Processamento
        - Navegue até a aba **Upload e Processamento**.
        """
    elif tipo == "admin_equipe":
        return """
        # Manual de Gestão - Admin Equipe
        ## 1. Gestão de Usuários
        - Cadastre novos analistas com e-mail institucional.
        ## 2. Correção de Dados (Malha Fina)
        - Na aba **Análise e Correção**, use a ferramenta de Atribuição em Massa para correções automáticas.
        """
    elif tipo == "admin_ti":
        return "# Manual Técnico (TI)\n## 1. Auditoria e Logs\n- Todas as ações são logadas."
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

def normalize_name(name):
    if not name or str(name).lower() in ['nan', 'none', '']:
        return ""
    s = str(name)
    nfkd_form = unicodedata.normalize('NFKD', s)
    only_ascii = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
    return " ".join(only_ascii.upper().split())

def normalize_key(val):
    """Limpa CPF ou Cartão para uso como chave (Adicionado para Backfilling)"""
    if not val: return ""
    return str(val).replace('.', '').replace('-', '').replace('/', '').replace(' ', '').strip()

def get_brasilia_time():
    return datetime.now(timezone(timedelta(hours=-3)))

# Mapeamento Completo de Meses
MONTH_MAP_FULL = {
    'JAN': 'Janeiro', 'JANEIRO': 'Janeiro', '01': 'Janeiro', '1': 'Janeiro',
    'FEV': 'Fevereiro', 'FEVEREIRO': 'Fevereiro', '02': 'Fevereiro', '2': 'Fevereiro',
    'MAR': 'Março', 'MARCO': 'Março', 'MARÇO': 'Março', '03': 'Março', '3': 'Março',
    'ABR': 'Abril', 'ABRIL': 'Abril', '04': 'Abril', '4': 'Abril',
    'MAI': 'Maio', 'MAIO': 'Maio', '05': 'Maio', '5': 'Maio',
    'JUN': 'Junho', 'JUNHO': 'Junho', '06': 'Junho', '6': 'Junho',
    'JUL': 'Julho', 'JULHO': 'Julho', '07': 'Julho', '7': 'Julho',
    'AGO': 'Agosto', 'AGOSTO': 'Agosto', '08': 'Agosto', '8': 'Agosto',
    'SET': 'Setembro', 'SETEMBRO': 'Setembro', '09': 'Setembro', '9': 'Setembro',
    'OUT': 'Outubro', 'OUTUBRO': 'Outubro', '10': 'Outubro',
    'NOV': 'Novembro', 'NOVEMBRO': 'Novembro', '11': 'Novembro',
    'DEZ': 'Dezembro', 'DEZEMBRO': 'Dezembro', '12': 'Dezembro'
}

MONTH_NUM_MAP = {
    'JAN': '01', 'JANEIRO': '01', 'FEV': '02', 'FEVEREIRO': '02', 'MAR': '03', 'MARCO': '03', 'MARÇO': '03',
    'ABR': '04', 'ABRIL': '04', 'MAI': '05', 'MAIO': '05', 'JUN': '06', 'JUNHO': '06',
    'JUL': '07', 'JULHO': '07', 'AGO': '08', 'AGOSTO': '08', 'SET': '09', 'SETEMBRO': '09',
    'OUT': '10', 'OUTUBRO': '10', 'NOV': '11', 'NOVEMBRO': '11', 'DEZ': '12', 'DEZEMBRO': '12'
}

def format_competencia(mes, ano):
    if not mes or not ano: return "N/A"
    mes_str = str(mes).upper().strip()
    ano_str = str(ano).strip()
    nome_mes = MONTH_MAP_FULL.get(mes_str)
    if not nome_mes and mes_str.isdigit():
        mes_int = int(mes_str)
        mes_key = f"{mes_int:02d}"
        nome_mes = MONTH_MAP_FULL.get(mes_key, mes_str)
    if not nome_mes: nome_mes = mes_str
    return f"{nome_mes} {ano_str}"

# ===========================================
# PARSER INTELIGENTE BANCO DO BRASIL
# ===========================================

def parse_smart_bb(file_obj, filename):
    try:
        content = file_obj.getvalue().decode('latin-1', errors='ignore')
    except:
        content = file_obj.getvalue().decode('utf-8', errors='ignore')
        
    lines = content.split('\n')
    data = []
    filename_upper = filename.upper()
    data_arquivo = ""
    competencia_fmt = ""
    
    match_date_header = re.search(r'(\d{2})\s+([A-Za-z]{3})\s+(\d{4})', content[:500])
    if match_date_header:
        d, m_eng, y = match_date_header.groups()
        eng_map = {'DEC':'Dezembro','JAN':'Janeiro','FEB':'Fevereiro','MAR':'Março','APR':'Abril','MAY':'Maio','JUN':'Junho','JUL':'Julho','AUG':'Agosto','SEP':'Setembro','OCT':'Outubro','NOV':'Novembro'}
        m_pt = eng_map.get(m_eng.upper(), m_eng)
        data_arquivo = f"{d}/{m_eng}/{y}"
        competencia_fmt = f"{m_pt} {y}"
        
    if not data_arquivo:
        match_date_lote = re.search(r'20\d{6}', content[:500]) 
        if match_date_lote:
            ds = match_date_lote.group(0) 
            y, m, d = ds[:4], ds[4:6], ds[6:8]
            data_arquivo = f"{d}/{m}/{y}"
            competencia_fmt = format_competencia(m, y)

    if "REL.CADASTRO" in filename_upper or (len(lines) > 0 and lines[0].startswith('0') and 'Projeto' in lines[0]):
        for line in lines:
            if line.startswith('1'): 
                try:
                    dt_lote_match = re.search(r'(\d{2}/\d{2}/\d{4})', line[150:]) 
                    dt_row = dt_lote_match.group(1) if dt_lote_match else data_arquivo
                    comp_row = competencia_fmt
                    if dt_row and not comp_row:
                        parts = dt_row.split('/')
                        if len(parts) == 3: comp_row = format_competencia(parts[1], parts[2])

                    entry = {
                        'arquivo_origem': filename,
                        'tipo_arquivo': 'CADASTRO',
                        'projeto': line[11:42].strip(),
                        'num_cartao': line[42:52].strip(),
                        'nome_banco': line[52:92].strip(),
                        'rg_banco': line[92:104].strip(),
                        'cpf_banco': line[104:119].strip().replace('.', '').replace('-', ''),
                        'data_pagto': dt_row,
                        'competencia': comp_row
                    }
                    if entry['num_cartao']: data.append(entry)
                except: continue

    elif "RESUMO" in filename_upper or "Distrito    Agencia" in content:
        i = 0
        while i < len(lines):
            line = lines[i]
            match_main = re.search(r'^\s*(\d{6,})\s+([\d\.]+)\s+(.+)$', line)
            if match_main:
                cartao = match_main.group(1)
                valor = match_main.group(2)
                nome = match_main.group(3).strip()
                agencia = ''
                distrito = ''
                if i + 1 < len(lines):
                    next_line = lines[i+1]
                    parts = next_line.split()
                    if len(parts) >= 2:
                        distrito = parts[0]
                        agencia = parts[1]
                data.append({
                    'arquivo_origem': filename,
                    'tipo_arquivo': 'RESUMO_SPOOL',
                    'projeto': 'N/A', 
                    'num_cartao': cartao,
                    'nome_banco': nome,
                    'rg_banco': '',
                    'cpf_banco': '',
                    'agencia': agencia,
                    'distrito': distrito,
                    'valor_banco': valor,
                    'data_pagto': data_arquivo,
                    'competencia': competencia_fmt
                })
                i += 1 
            i += 1

    elif "LOTE" in filename_upper or (len(lines) > 1 and lines[1].startswith('2000')):
        for line in lines:
            if line.startswith('2'): 
                try:
                    cartao_candidato = line[13:20].strip()
                    match_nome = re.search(r'30000004(.+)$', line)
                    if match_nome: nome = match_nome.group(1).strip()
                    else:
                        nome_part = re.search(r'(\D+)$', line)
                        nome = nome_part.group(1).strip() if nome_part else ""
                    if cartao_candidato and nome:
                        data.append({
                            'arquivo_origem': filename,
                            'tipo_arquivo': 'LOTE_PROCESSAMENTO',
                            'projeto': 'LOTE',
                            'num_cartao': cartao_candidato,
                            'nome_banco': nome,
                            'rg_banco': '',
                            'cpf_banco': '',
                            'data_pagto': data_arquivo,
                            'competencia': competencia_fmt
                        })
                except: continue

    return pd.DataFrame(data)

# ===========================================
# LÓGICA DE NEGÓCIO E VALIDAÇÃO
# ===========================================

COLUMN_MAP = {
    'num cartao': 'num_cartao', 'numcartao': 'num_cartao', 'numcartão': 'num_cartao', 
    'código': 'num_cartao', 'codigo': 'num_cartao', 'cartao': 'num_cartao', 'cartão': 'num_cartao',
    'conta/código': 'num_cartao', 'conta/codigo': 'num_cartao',
    'nome': 'nome', 'nome do beneficiário': 'nome', 'participante': 'nome', 'beneficiário': 'nome', 'beneficiario': 'nome',
    'cpf': 'cpf', 'rg': 'rg',
    'valor pagto': 'valor_pagto', 'valorpagto': 'valor_pagto', 'valor total': 'valor_pagto', 'valor': 'valor_pagto',
    'dias a apagar': 'qtd_dias', 'dias': 'qtd_dias',
    'data pagto': 'data_pagto', 'datapagto': 'data_pagto', 'dt pagto': 'data_pagto', 
    'dt. pagto': 'data_pagto', 'data do pagamento': 'data_pagto', 'dt pagamento': 'data_pagto',
    'projeto': 'programa', 'mês': 'mes_ref', 'mes': 'mes_ref', 'competência': 'competencia', 'competencia': 'competencia',
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
        
    mes_ref = None
    ano_ref = str(datetime.now().year)
    
    for nome_mes, num_mes in MONTH_NUM_MAP.items():
        if nome_mes in filename_upper:
            mes_ref = num_mes
            break
            
    ano_match = re.search(r'(20\d{2})', filename_upper)
    if ano_match:
        ano_ref = ano_match.group(1)
        
    if (not mes_ref) and 'data_pagto' in df.columns:
        try:
            first_valid_date = pd.to_datetime(df['data_pagto'], dayfirst=True, errors='coerce').dropna().iloc[0]
            mes_ref = str(first_valid_date.month).zfill(2)
            if not ano_match:
                ano_ref = str(first_valid_date.year)
        except: pass
    
    if not mes_ref:
        mes_ref = str(datetime.now().month).zfill(2)
            
    df['mes_ref'] = mes_ref
    df['ano_ref'] = ano_ref
    
    if 'competencia' not in df.columns:
        df['competencia'] = format_competencia(mes_ref, ano_ref)
        
    if 'data_pagto' not in df.columns:
        df['data_pagto'] = datetime.now().strftime('%d/%m/%Y')
        
    essential_check = ['num_cartao', 'nome', 'cpf', 'rg', 'valor_pagto']
    for col in essential_check:
        if col not in df.columns: df[col] = None 

    df = remove_total_row(df)

    if 'num_cartao' in df.columns:
        df['num_cartao'] = df['num_cartao'].fillna('').astype(str).str.strip()
        df['num_cartao'] = df['num_cartao'].str.replace(r'\.0$', '', regex=True).replace(r'(?i)^nan$', '', regex=True)
        
    if 'cpf' in df.columns:
        df['cpf'] = df['cpf'].fillna('').astype(str).str.strip()
        df['cpf'] = df['cpf'].str.replace(r'\D', '', regex=True).replace(r'(?i)^nan$', '', regex=True)
    
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
    cols_to_keep = ['programa', 'gerenciadora', 'num_cartao', 'nome', 'cpf', 'rg', 'valor_pagto', 'data_pagto', 'competencia', 'qtd_dias', 'mes_ref', 'ano_ref', 'arquivo_origem', 'linha_arquivo']
    final_cols = [c for c in cols_to_keep if c in df.columns]
    return df[final_cols]

def detect_inconsistencies(df):
    if df is None or df.empty:
        return pd.DataFrame()
    
    needed = ['cpf', 'num_cartao', 'nome']
    for col in needed:
        if col not in df.columns:
            df[col] = ''
    
    df_check = df.copy()
    df_check['cpf_raw'] = df_check['cpf'].fillna('').astype(str).str.strip()
    df_check['card_raw'] = df_check['num_cartao'].fillna('').astype(str).str.strip()
    
    df_check['cpf_clean'] = df_check['cpf_raw'].str.replace(r'\D', '', regex=True)
    df_check['card_clean'] = df_check['card_raw'].str.replace(r'^0+', '', regex=True).str.replace(r'\.0$', '', regex=True)
    df_check['nome_clean'] = df_check['nome'].apply(remove_accents)
    
    errors = []

    for idx, row in df_check.iterrows():
        motivos = []
        is_error = False
        
        cpf_val = row['cpf_raw']
        if not cpf_val or str(cpf_val).lower() == 'nan':
            motivos.append("CPF NÃO INFORMADO")
            is_error = True
            
        card_val = row['card_raw']
        if not card_val or str(card_val).lower() == 'nan':
            motivos.append("CARTÃO NÃO INFORMADO")
            is_error = True
            
        if is_error:
            errors.append({
                'ID': row.get('id', None),
                'ARQUIVO': row.get('arquivo_origem', '-'),
                'LINHA': row.get('linha_arquivo', '-'),
                'CPF': cpf_val if cpf_val else "VAZIO",
                'CARTÃO': card_val if card_val else "VAZIO",
                'NOME': row.get('nome', '-'),
                'ERRO': " | ".join(motivos),
                'TIPO_ERRO': 'AUSENCIA'
            })

    df_valid = df_check[ 
        (df_check['cpf_clean'] != '') & 
        (df_check['cpf_clean'].str.len() > 5)
    ]

    cpf_groups = df_valid.groupby('cpf_clean')
    for cpf, group in cpf_groups:
        unique_cards = [c for c in group['card_clean'].unique() if c]
        unique_names = [n for n in group['nome_clean'].unique() if n]

        has_card_conflict = len(unique_cards) > 1
        has_name_conflict = len(unique_names) > 1
        
        if has_card_conflict or has_name_conflict:
            motivo_dup = []
            if has_card_conflict: 
                cards_orig = group['num_cartao'].unique()
                motivo_dup.append(f"CONFLITO CARTÃO ({', '.join(map(str, cards_orig))})")
            if has_name_conflict: 
                motivo_dup.append(f"CONFLITO NOME")
            
            err_msg = " | ".join(motivo_dup)
            for _, row in group.iterrows():
                errors.append({
                    'ID': row.get('id', None),
                    'ARQUIVO': row.get('arquivo_origem', '-'),
                    'LINHA': row.get('linha_arquivo', '-'),
                    'CPF': row.get('cpf', '-'),
                    'CARTÃO': row.get('num_cartao', '-'),
                    'NOME': row.get('nome', '-'),
                    'ERRO': err_msg,
                    'TIPO_ERRO': 'DUPLICIDADE'
                })

    card_groups = df_valid.groupby('card_clean')
    for card, group in card_groups:
        if not card: continue
        unique_cpfs = [c for c in group['cpf_clean'].unique() if c]
        
        if len(unique_cpfs) > 1:
            for _, row in group.iterrows():
                errors.append({
                    'ID': row.get('id', None),
                    'ARQUIVO': row.get('arquivo_origem', '-'),
                    'LINHA': row.get('linha_arquivo', '-'),
                    'CPF': row.get('cpf', '-'),
                    'CARTÃO': row.get('num_cartao', '-'),
                    'NOME': row.get('nome', '-'),
                    'ERRO': f"FRAUDE: CARTÃO USADO EM {len(unique_cpfs)} CPFs",
                    'TIPO_ERRO': 'FRAUDE'
                })

    if not errors: return pd.DataFrame()
    
    res_df = pd.DataFrame(errors)
    res_df['PRIORIDADE'] = res_df['TIPO_ERRO'].map({'AUSENCIA': 1, 'FRAUDE': 2, 'DUPLICIDADE': 3})
    res_df = res_df.sort_values('PRIORIDADE')
    
    return res_df.drop_duplicates(subset=['ARQUIVO', 'LINHA', 'CPF', 'CARTÃO', 'ERRO']).drop(columns=['PRIORIDADE', 'TIPO_ERRO'])

# ===========================================
# LÓGICA DE BACKFILLING (NOVA)
# ===========================================

def build_master_key(conn):
    """
    Cria a 'Chave Mestra' (Dicionário) usando Histórico + Retorno Bancário
    """
    # 1. Dados Históricos do Sistema
    df_pay = pd.read_sql("SELECT num_cartao, cpf, rg FROM payments WHERE num_cartao IS NOT NULL AND num_cartao != ''", conn)
    
    # 2. Dados de Retorno Bancário (considerados fonte de verdade para Docs)
    df_bank = pd.read_sql("SELECT cartao as num_cartao, cpf_bb as cpf, rg_bb as rg FROM bank_discrepancies WHERE cartao IS NOT NULL", conn)
    
    # Unifica
    df_all = pd.concat([df_pay, df_bank], ignore_index=True)
    
    master_map = {}
    
    groups = df_all.groupby('num_cartao')
    
    for card, group in groups:
        card_clean = normalize_key(card)
        if not card_clean: continue
        
        # Encontrar CPF mais frequente (Consenso)
        cpfs = [c for c in group['cpf'].dropna().astype(str) if len(normalize_key(c)) > 5 and 'NAN' not in c.upper()]
        best_cpf = Counter(cpfs).most_common(1)[0][0] if cpfs else None
        
        # Encontrar RG mais frequente
        rgs = [r for r in group['rg'].dropna().astype(str) if len(normalize_key(r)) > 3 and 'NAN' not in r.upper()]
        best_rg = Counter(rgs).most_common(1)[0][0] if rgs else None
        
        if best_cpf or best_rg:
            master_map[card_clean] = {'cpf': best_cpf, 'rg': best_rg}
            
    return master_map

# ===========================================
# GERAÇÃO DE RELATÓRIOS E PDF (MANTIDO)
# ===========================================

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
    
    if pdf.get_y() + row_height > 190: 
        pdf.add_page(orientation='L')
    
    x_start = pdf.get_x()
    y_start = pdf.get_y()
    for i, width in enumerate(widths):
        pdf.set_xy(x_start + sum(widths[:i]), y_start)
        content = sanitize_text(str(data[i]))
        pdf.multi_cell(width, line_height, content, 1, align, fill)
    pdf.set_xy(x_start, y_start + row_height)

def generate_pdf_report(df_filtered, inconsistency_df=None):
    if FPDF is None: return b"Erro: FPDF ausente."
    pdf = FPDF()
    pdf.add_page(orientation='L')
    
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 8, sanitize_text("Prefeitura de São Paulo"), 0, 1, 'C')
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 8, sanitize_text("Secretaria Municipal do Desenvolvimento Econômico e Trabalho"), 0, 1, 'C')
    pdf.ln(5)
    pdf.set_fill_color(220, 220, 220)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 12, sanitize_text("Relatório Executivo POT"), 1, 1, 'C', fill=True)
    
    comps = df_filtered['competencia'].unique()
    comp_str = ", ".join(str(c) for c in comps if c)
    
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 8, sanitize_text(f"Competência(s): {comp_str}"), 0, 1, 'C')
    pdf.ln(2)
    
    data_br = get_brasilia_time().strftime('%d/%m/%Y às %H:%M')
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 6, sanitize_text(f"Gerado em: {data_br}"), 0, 1, 'R')
    pdf.ln(5)

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

    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, sanitize_text("3. Detalhamento Financeiro e Competência"), 0, 1)
    if 'programa' in df_filtered.columns and not df_filtered.empty:
        group_proj = df_filtered.groupby(['programa', 'competencia']).agg({'valor_pagto': 'sum', 'num_cartao': 'count'}).reset_index().sort_values('valor_pagto', ascending=False)
        pdf.set_font("Arial", 'B', 9)
        pdf.set_fill_color(240, 240, 240)
        widths_det = [90, 40, 25, 40]
        cols_det = ['PROJETO', 'COMPETÊNCIA', 'QTD', 'VALOR TOTAL']
        for i, col in enumerate(cols_det): pdf.cell(widths_det[i], 8, sanitize_text(col), 1, 0, 'C', True)
        pdf.ln()
        pdf.set_font("Arial", '', 9)
        for _, row in group_proj.iterrows():
            pdf.cell(widths_det[0], 7, sanitize_text(str(row['programa'])[:45]), 1)
            pdf.cell(widths_det[1], 7, sanitize_text(str(row['competencia'])), 1, 0, 'C')
            pdf.cell(widths_det[2], 7, str(row['num_cartao']), 1, 0, 'C')
            pdf.cell(widths_det[3], 7, f"R$ {row['valor_pagto']:,.2f}", 1, 1, 'R')
    pdf.ln(10)

    if inconsistency_df is None:
        inconsistency_df = detect_inconsistencies(df_filtered)
        
    if not inconsistency_df.empty:
        pdf.set_text_color(255, 0, 0)
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, sanitize_text(f"⚠️ 4. ALERTA DE INCONSISTÊNCIAS E DADOS AUSENTES ({len(inconsistency_df)} Ocorrências)"), 0, 1)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", '', 10)
        pdf.multi_cell(0, 6, sanitize_text("Abaixo estão listados os registros contendo inconsistências críticas."))
        pdf.ln(2)
        
        pdf.set_font("Arial", 'B', 8)
        pdf.set_fill_color(255, 230, 230)
        widths = [45, 12, 28, 28, 60, 95]
        cols = ['ARQUIVO', 'LIN', 'CPF', 'CARTÃO', 'NOME', 'DESCRIÇÃO DO ERRO']
        for i, col in enumerate(cols): pdf.cell(widths[i], 8, sanitize_text(col), 1, 0, 'C', True)
        pdf.ln()
        pdf.set_font("Arial", '', 8)
        
        max_rows = 300
        count = 0
        for _, row in inconsistency_df.iterrows():
            if count >= max_rows:
                pdf.cell(0, 8, sanitize_text(f"... e mais {len(inconsistency_df)-max_rows} inconsistências (veja no sistema)."), 1, 1, 'C')
                break
            data_row = [str(row['ARQUIVO']), str(row['LINHA']), str(row['CPF']), str(row['CARTÃO']), str(row['NOME']), str(row['ERRO'])]
            print_pdf_row_multiline(pdf, widths, data_row)
            count += 1
    else:
        pdf.set_text_color(0, 128, 0)
        pdf.set_font("Arial", 'B', 11)
        pdf.cell(0, 10, sanitize_text("✅ 4. Validação de Integridade: Nenhuma pendência detectada."), 0, 1)
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
        row_data = [str(row.get('cartao','')), str(row.get('nome_sis','')), str(row.get('nome_bb','')), str(row.get('divergencia',''))]
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
    
    if user['role'] in ['admin_ti', 'admin_equipe']:
        menu.append("Gestão de Dados")
        menu.append("Gestão de Equipe")
        
    if user['role'] == 'admin_ti': 
        menu.append("Administração TI")
    
    choice = st.sidebar.radio("Menu", menu)
    
    if st.sidebar.button("Sair"):
        log_action(user['email'], "LOGOUT", "Usuário saiu do sistema")
        st.session_state.clear()
        st.rerun()

    conn = get_db_connection()
    try:
        df_payments = pd.read_sql("SELECT * FROM payments", conn)
    except:
        df_payments = pd.DataFrame()
    conn.close()

    if choice == "Dashboard":
        render_header()
        st.markdown("### 📊 Dashboard Executivo")
        
        if not df_payments.empty:
            periods = df_payments['competencia'].unique()
            period_str = ", ".join(str(p) for p in periods if p)
            st.info(f"📅 **Competência(s) em Análise:** {period_str}")
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
            with st.expander("📕 Manual de Gestão (Admin)"):
                content_team = get_manual_content("admin_equipe")
                st.markdown(content_team)
                pdf_team = create_manual_pdf("Manual de Gestão", content_team)
                if pdf_team: st.download_button("Baixar PDF (Gestão)", pdf_team, "manual_gestao.pdf", "application/pdf")

    elif choice == "Upload e Processamento":
        render_header()
        st.markdown("### 📂 Upload de Pagamentos")
        reg_count = len(df_payments)
        if reg_count > 0:
            st.info(f"💾 **Banco de Dados Ativo:** {reg_count} registros já carregados.")
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
                final.to_sql('payments', conn, if_exists='append', index=False)
                conn.close()
                log_action(user['email'], "UPLOAD", f"Upload de {len(files)} arquivos, {len(final)} registros")
                st.success(f"✅ {len(final)} registros salvos com sucesso!")
                inconsistencies = detect_inconsistencies(final)
                if not inconsistencies.empty:
                    st.markdown("---")
                    st.error("🚨 ATENÇÃO: ERROS DE DADOS AUSENTES OU INCONSISTÊNCIAS IDENTIFICADOS NO UPLOAD!")
                    st.dataframe(inconsistencies, use_container_width=True)
                st.warning("A tela será atualizada em instantes para consolidar os dados...")
                
    # ===========================================
    # ANÁLISE E CORREÇÃO (ATUALIZADA COM MALHA FINA E BACKFILLING)
    # ===========================================
    elif choice == "Análise e Correção":
        render_header()
        
        st.markdown('### 🕵️ Malha Fina e Auditoria')
        
        # Filtros no Estilo "Card" (Baseado no Print)
        with st.container():
            st.markdown("##### Filtros de Análise")
            c_type, c_year, c_month = st.columns([1, 2, 2])
            
            with c_type:
                st.radio("Período de Análise", ["Mês Único", "Intervalo"], horizontal=True)
            
            with c_year:
                anos_disp = sorted(df_payments['ano_ref'].unique().astype(str)) if not df_payments.empty else [str(datetime.now().year)]
                sel_ano = st.selectbox("Ano", anos_disp, index=len(anos_disp)-1 if anos_disp else 0)
            
            with c_month:
                meses_disp = sorted(df_payments['competencia'].unique().astype(str)) if not df_payments.empty else ["Outubro 2025"]
                sel_mes = st.selectbox("Mês/Competência", meses_disp)

        st.markdown("---")

        df_filtered = df_payments.copy()
        if not df_filtered.empty:
            df_filtered = df_filtered[df_filtered['competencia'] == sel_mes]

        tabs = st.tabs([
            "Visão Geral", 
            "Dados Faltantes & Saneamento", 
            "Padronização", 
            "Auditoria Identidade", 
            "Atribuição em Massa" 
        ])

        with tabs[0]:
            if not df_filtered.empty:
                st.metric("Total em Análise", len(df_filtered))
                st.dataframe(df_filtered.head(50), use_container_width=True)
            else:
                st.info("Nenhum dado encontrado para o filtro selecionado.")

        with tabs[1]:
            st.markdown("#### Registros com Pendências (CPF ou Cartão)")
            if not df_filtered.empty:
                # Usa a lógica já existente no seu app.py para detectar erros
                errors = detect_inconsistencies(df_filtered)
                if not errors.empty:
                    st.error(f"{len(errors)} registros inconsistentes encontrados.")
                    st.dataframe(errors, use_container_width=True)
                    
                    if user['role'] in ['admin_ti', 'admin_equipe']:
                         st.info("Utilize a aba 'Atribuição em Massa' para tentar corrigir automaticamente, ou edite abaixo:")
                         # Editor simples para correção pontual
                         ids_err = errors['ID'].dropna().tolist()
                         if ids_err:
                            to_edit = df_payments[df_payments['id'].isin(ids_err)]
                            edited = st.data_editor(to_edit, key='edit_missing_tab', use_container_width=True)
                            if st.button("Salvar Correções Pontuais"):
                                conn = get_db_connection()
                                conn.execute("DELETE FROM payments WHERE id IN (" + ",".join(map(str, ids_err)) + ")")
                                edited.to_sql('payments', conn, if_exists='append', index=False)
                                conn.close()
                                st.success("Salvo!")
                                st.rerun()
                else:
                    st.success("Nenhuma pendência crítica encontrada nesta competência.")

        with tabs[2]:
            st.info("Regras de padronização (nomes, caracteres especiais). Em desenvolvimento.")

        with tabs[3]:
            st.markdown("#### Cruzamento: Sistema vs Retorno Bancário")
            conn = get_db_connection()
            disc = pd.read_sql("SELECT * FROM bank_discrepancies", conn)
            conn.close()
            if not disc.empty:
                st.dataframe(disc, use_container_width=True)
            else:
                st.info("Nenhuma divergência registrada no histórico.")

        # ABA BACKFILLING (RESTABELECIDA CONFORME SOLICITAÇÃO)
        with tabs[4]:
            st.markdown('<div class="backfill-container">', unsafe_allow_html=True)
            st.markdown('<div class="backfill-header">🛠️ Ferramenta de Recuperação de CPFs (Backfilling)</div>', unsafe_allow_html=True)
            st.markdown("""
            <p style='color: #ccc;'>O sistema procurará no histórico completo ("Chave Mestra") e nos arquivos de retorno bancário
            todas as contas que possuem CPF válido em algum momento e preencherá onde está vazio na seleção atual.</p>
            """, unsafe_allow_html=True)
            
            if st.button("🚀 Executar Backfilling", type="primary"):
                status_box = st.empty()
                log_box = st.empty()
                logs_html = ""
                
                status_box.markdown("**🔄 Aplicando correções...**")
                logs_html += "<div class='console-log'>🔍 Mapeando histórico de contas (Chave Mestra)...</div>"
                log_box.markdown(logs_html, unsafe_allow_html=True)
                
                conn = get_db_connection()
                master_map = build_master_key(conn)
                time.sleep(1)
                
                logs_html += f"<div class='console-log'>✅ Histórico mapeado: {len(master_map)} contas únicas com dados.</div>"
                log_box.markdown(logs_html, unsafe_allow_html=True)
                
                cursor = conn.cursor()
                cursor.execute("SELECT id, num_cartao, cpf, rg FROM payments")
                rows = cursor.fetchall()
                
                logs_html += f"<div class='console-log'>🔍 Analisando {len(rows)} registros na base...</div>"
                log_box.markdown(logs_html, unsafe_allow_html=True)
                
                updated = 0
                rec_cpf = 0
                rec_rg = 0
                prog_bar = st.progress(0)
                
                for i, row in enumerate(rows):
                    rid, r_card, r_cpf, r_rg = row
                    key = normalize_key(r_card)
                    
                    if key in master_map:
                        info = master_map[key]
                        changes = []
                        n_cpf = r_cpf
                        n_rg = r_rg
                        
                        curr_cpf = normalize_key(r_cpf)
                        if (not curr_cpf or len(curr_cpf) < 5) and info['cpf']:
                            n_cpf = info['cpf']
                            changes.append('CPF')
                            rec_cpf += 1
                            
                        curr_rg = normalize_key(r_rg)
                        if (not curr_rg or len(curr_rg) < 3) and info['rg']:
                            n_rg = info['rg']
                            changes.append('RG')
                            rec_rg += 1
                            
                        if changes:
                            cursor.execute("UPDATE payments SET cpf = ?, rg = ? WHERE id = ?", (n_cpf, n_rg, rid))
                            updated += 1
                    
                    if i % 500 == 0: prog_bar.progress((i+1)/len(rows))
                
                conn.commit()
                conn.close()
                prog_bar.progress(100)
                
                logs_html += f"<div class='console-log'>🚀 Concluído! {updated} registros atualizados.<br>CPFs: {rec_cpf} | RGs: {rec_rg}</div>"
                log_box.markdown(logs_html, unsafe_allow_html=True)
                status_box.success("Processo Finalizado com Sucesso!")
                log_action(user['email'], "BACKFILL", f"Recuperados: {updated}")
            
            st.markdown('</div>', unsafe_allow_html=True)

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
            
            crit_subset = detect_inconsistencies(df_exp)
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

    elif choice == "Conferência Bancária (BB)":
        render_header()
        st.markdown("### 🏦 Conferência BB (Auditoria Avançada)")
        st.info("Suporte a: Relatórios de Cadastro, Arquivos de Lote (CNAB) e Resumos de Crédito (Spool).")
        
        conn = get_db_connection()
        try:
            hist = pd.read_sql("SELECT * FROM bank_discrepancies", conn)
        except: hist = pd.DataFrame()
        conn.close()
        
        if not hist.empty:
            st.warning(f"⚠️ {len(hist)} divergências encontradas no histórico.")
            st.dataframe(hist, use_container_width=True)
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
                
        files = st.file_uploader("Upload Arquivos Banco (TXT)", accept_multiple_files=True)
        if files and st.button("Executar Cruzamento (Malha Fina)"):
            dfs = []
            for f in files:
                try:
                    d = parse_smart_bb(f, f.name)
                    if not d.empty:
                        dfs.append(d)
                        st.toast(f"{f.name}: {len(d)} registros lidos.")
                    else:
                        st.warning(f"Arquivo {f.name} lido, mas sem dados reconhecidos.")
                except Exception as e: st.error(f"Erro ao ler {f.name}: {e}")
            
            if dfs:
                final_bb = pd.concat(dfs, ignore_index=True)
                final_bb['key'] = final_bb['num_cartao'].astype(str).str.replace(r'^0+', '', regex=True).str.replace(r'\.0$', '', regex=True).str.strip()
                
                conn = get_db_connection()
                df_sys = pd.read_sql("SELECT num_cartao, nome, cpf, rg FROM payments", conn)
                conn.close()
                df_sys['key'] = df_sys['num_cartao'].astype(str).str.replace(r'^0+', '', regex=True).str.replace(r'\.0$', '', regex=True).str.strip()
                
                merged = pd.merge(df_sys, final_bb, on='key', suffixes=('_sis', '_bb'))
                divs = []
                for _, row in merged.iterrows():
                    nm_s = normalize_name(row.get('nome_sis', ''))
                    nm_b = normalize_name(row.get('nome_bb', ''))
                    if nm_s != nm_b:
                        divs.append({
                            'cartao': row['key'],
                            'nome_sis': row.get('nome_sis', ''),
                            'nome_bb': row.get('nome_bb', ''),
                            'cpf_sis': row.get('cpf', ''),
                            'cpf_bb': row.get('cpf_banco', ''),
                            'rg_sis': row.get('rg', ''),
                            'rg_bb': row.get('rg_banco', ''),
                            'divergencia': 'ALERTA MÁXIMO: NOME DIVERGENTE',
                            'arquivo_origem': row['arquivo_origem'],
                            'tipo_erro': 'SUSPEITA_TROCA_TITULARIDADE'
                        })
                    cpf_bb = str(row.get('cpf_banco', '')).strip()
                    if cpf_bb and len(cpf_bb) > 5:
                        cpf_s_clean = str(row.get('cpf', '')).replace('.', '').replace('-', '').strip()
                        cpf_b_clean = cpf_bb.replace('.', '').replace('-', '').strip()
                        if cpf_s_clean != cpf_b_clean:
                            divs.append({
                                'cartao': row['key'],
                                'nome_sis': row.get('nome_sis', ''),
                                'nome_bb': row.get('nome_bb', ''),
                                'cpf_sis': row.get('cpf', ''),
                                'cpf_bb': cpf_bb,
                                'rg_sis': row.get('rg', ''),
                                'rg_bb': row.get('rg_banco', ''),
                                'divergencia': 'CPF DIVERGENTE (FRAUDE)',
                                'arquivo_origem': row['arquivo_origem'],
                                'tipo_erro': 'DADOS_CADASTRAIS'
                            })
                if divs:
                    dd = pd.DataFrame(divs)
                    conn = get_db_connection()
                    dd.to_sql('bank_discrepancies', conn, if_exists='append', index=False)
                    conn.close()
                    st.error(f"🚨 ALERTA DE FRAUDE: {len(dd)} divergências de titularidade identificadas!")
                    st.rerun()
                else: 
                    st.success(f"✅ Auditoria Blindada: {len(final_bb)} registros processados. Nenhuma troca de titularidade detectada.")
            else:
                st.warning("Nenhum dado válido extraído dos arquivos enviados.")

    elif choice == "Gestão de Dados":
        render_header()
        st.markdown("### 🗄️ Gerenciamento de Registros e Arquivos")
        tab_files, tab_records = st.tabs(["📂 Excluir Arquivos Inteiros", "🔍 Buscar e Excluir Registros"])
        
        with tab_files:
            conn = get_db_connection()
            try:
                file_stats = pd.read_sql("""
                    SELECT arquivo_origem, COUNT(*) as qtd_registros, MAX(created_at) as data_importacao 
                    FROM payments 
                    GROUP BY arquivo_origem 
                    ORDER BY created_at DESC
                """, conn)
            except:
                file_stats = pd.DataFrame()
            conn.close()
            
            if not file_stats.empty:
                st.dataframe(file_stats, use_container_width=True)
                file_to_del = st.selectbox("Selecione o arquivo para excluir TODOS os seus registros:", 
                                         file_stats['arquivo_origem'].unique())
                
                if st.button(f"🗑️ Excluir registros de: {file_to_del}"):
                    conn = get_db_connection()
                    conn.execute("DELETE FROM payments WHERE arquivo_origem = ?", (file_to_del,))
                    conn.commit()
                    conn.close()
                    log_action(user['email'], "EXCLUIR_ARQUIVO", f"Excluiu arquivo: {file_to_del}")
                    st.success(f"Todos os registros do arquivo '{file_to_del}' foram removidos.")
                    st.rerun()
            else:
                st.info("Nenhum arquivo importado no momento.")

        with tab_records:
            search_term = st.text_input("Buscar por Nome, CPF ou Cartão (mínimo 3 caracteres)", "")
            if len(search_term) >= 3:
                conn = get_db_connection()
                query = f"""
                    SELECT id, nome, cpf, num_cartao, programa, arquivo_origem 
                    FROM payments 
                    WHERE nome LIKE ? OR cpf LIKE ? OR num_cartao LIKE ?
                    LIMIT 50
                """
                like_term = f"%{search_term}%"
                results = pd.read_sql(query, conn, params=(like_term, like_term, like_term))
                conn.close()
                if not results.empty:
                    st.write(f"Encontrados {len(results)} registros (limitado a 50):")
                    event = st.dataframe(results, use_container_width=True, hide_index=True, selection_mode="multi-row", on_select="rerun", key="search_results")
                    selected_rows = event.selection.rows
                    if selected_rows:
                        ids_to_delete = results.iloc[selected_rows]['id'].tolist()
                        st.error(f"⚠️ Você selecionou {len(ids_to_delete)} registro(s) para exclusão permanente.")
                        if st.button("Confirmar Exclusão dos Selecionados"):
                            conn = get_db_connection()
                            id_list = ','.join(map(str, ids_to_delete))
                            conn.execute(f"DELETE FROM payments WHERE id IN ({id_list})")
                            conn.commit()
                            conn.close()
                            log_action(user['email'], "EXCLUIR_REGISTROS", f"Excluiu IDs: {id_list}")
                            st.success("Registros excluídos com sucesso!")
                            st.rerun()
                else: st.warning("Nenhum registro encontrado com este termo.")

    elif choice == "Gestão de Equipe":
        render_header()
        st.markdown("### 👥 Gestão de Acessos")
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
                if c[3].button("🔄", key=f"rst_{row['email']}", disabled=is_self):
                    conn = get_db_connection()
                    pass_reset = hashlib.sha256('mudar123'.encode()).hexdigest()
                    conn.execute("UPDATE users SET password = ?, first_login = 1 WHERE email = ?", (pass_reset, row['email']))
                    conn.commit()
                    conn.close()
                    st.toast(f"Senha de {row['name']} resetada!")
                    log_action(user['email'], "RESET_SENHA", f"Resetou {row['email']}")
                if c[4].button("🗑️", key=f"del_{row['email']}", disabled=is_self):
                    conn = get_db_connection()
                    conn.execute("DELETE FROM users WHERE email = ?", (row['email'],))
                    conn.commit()
                    conn.close()
                    st.success(f"Removido: {row['name']}")
                    log_action(user['email'], "EXCLUIR_USUARIO", f"Excluiu {row['email']}")
                    st.rerun()
                st.markdown("<div class='user-row'></div>", unsafe_allow_html=True)

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
