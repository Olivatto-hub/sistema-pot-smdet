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
            linha_arquivo INTEGER, -- Nova coluna para rastreamento
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
            tipo_erro TEXT, 
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Migrações
    try:
        c.execute("SELECT linha_arquivo FROM payments LIMIT 1")
    except sqlite3.OperationalError:
        try:
            c.execute("ALTER TABLE payments ADD COLUMN linha_arquivo INTEGER")
            conn.commit()
        except Exception: pass

    try:
        c.execute("SELECT gerenciadora FROM payments LIMIT 1")
    except sqlite3.OperationalError:
        try:
            c.execute("ALTER TABLE payments ADD COLUMN gerenciadora TEXT")
            conn.commit()
        except Exception: pass
            
    try:
        c.execute("SELECT tipo_erro FROM bank_discrepancies LIMIT 1")
    except sqlite3.OperationalError:
        try:
            c.execute("ALTER TABLE bank_discrepancies ADD COLUMN tipo_erro TEXT")
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

# ===========================================
# LÓGICA DE NEGÓCIO E PROCESSAMENTO
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
    """Verifica e remove linha de totalização."""
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
    """Padroniza colunas e adiciona número da linha original."""
    
    # Adicionar Rastreamento de Linha (Index + 2 assumindo header na linha 1)
    # Se o arquivo tiver header em outra linha, isso pode variar, mas +2 é o padrão seguro
    df['linha_arquivo'] = df.index + 2
    
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
    
    cols_to_keep = ['programa', 'gerenciadora', 'num_cartao', 'nome', 'cpf', 'rg', 'valor_pagto', 'data_pagto', 'qtd_dias', 'mes_ref', 'ano_ref', 'arquivo_origem', 'linha_arquivo']
    final_cols = [c for c in cols_to_keep if c in df.columns]
    
    return df[final_cols]

def detect_critical_duplicates(df):
    """
    Detecta CPFs duplicados que possuem Nomes diferentes ou Cartões diferentes.
    Retorna um DataFrame apenas com os registros problemáticos.
    """
    if 'cpf' not in df.columns or df.empty:
        return pd.DataFrame()
    
    # Filtrar CPFs válidos (ignorar vazios)
    df_valid = df[ (df['cpf'].notna()) & (df['cpf'].astype(str).str.strip() != '') ].copy()
    
    # Agrupar por CPF e filtrar quem aparece mais de uma vez
    dupes = df_valid[df_valid.duplicated('cpf', keep=False)]
    
    critical_errors = []
    
    if not dupes.empty:
        for cpf, group in dupes.groupby('cpf'):
            unique_cards = group['num_cartao'].unique()
            unique_names = group['nome'].astype(str).str.strip().str.upper().unique()
            
            # Se houver variação de cartão OU variação de nome para o mesmo CPF
            if len(unique_cards) > 1 or len(unique_names) > 1:
                motivo = []
                if len(unique_cards) > 1: motivo.append("CARTÕES DIFERENTES")
                if len(unique_names) > 1: motivo.append("NOMES DIFERENTES")
                
                motivo_str = " | ".join(motivo)
                
                for _, row in group.iterrows():
                    critical_errors.append({
                        'ARQUIVO': row.get('arquivo_origem', '-'),
                        'LINHA': row.get('linha_arquivo', '-'),
                        'CPF': cpf,
                        'CARTÃO': row.get('num_cartao', '-'),
                        'NOME': row.get('nome', '-'),
                        'ERRO': motivo_str
                    })
                    
    return pd.DataFrame(critical_errors)

def get_brasilia_time():
    return datetime.now(timezone(timedelta(hours=-3)))

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

def generate_pdf_report(df_filtered):
    if FPDF is None: return b"Erro: FPDF ausente."
    
    pdf = FPDF()
    pdf.add_page(orientation='L') # Paisagem para caber mais dados
    
    # Cabeçalho
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 8, "Prefeitura de São Paulo", 0, 1, 'C')
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 8, "Secretaria Municipal do Desenvolvimento Econômico e Trabalho", 0, 1, 'C')
    pdf.ln(5)
    pdf.set_fill_color(220, 220, 220)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 12, "Relatório Executivo POT", 1, 1, 'C', fill=True)
    pdf.ln(5)
    
    # Data
    data_br = get_brasilia_time().strftime('%d/%m/%Y às %H:%M')
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 6, f"Gerado em: {data_br}", 0, 1, 'R')
    pdf.ln(5)

    # === ALERTA CRÍTICO DE DUPLICIDADES (NOVO) ===
    # Verificar erros
    critical_df = detect_critical_duplicates(df_filtered)
    
    if not critical_df.empty:
        pdf.set_text_color(255, 0, 0)
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, f"⚠️ ALERTA CRÍTICO: {len(critical_df)} REGISTROS COM DUPLICIDADE DE CPF CONFLITANTE", 0, 1)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", '', 10)
        pdf.multi_cell(0, 6, "Os registros abaixo apresentam o mesmo CPF associado a Nomes ou Cartões diferentes. Verifique a linha original do arquivo.")
        pdf.ln(2)
        
        # Tabela de Erros
        pdf.set_font("Arial", 'B', 9)
        pdf.set_fill_color(255, 230, 230)
        # Larguras
        w = [45, 15, 30, 25, 70, 50] # Arq, Linha, CPF, Cartao, Nome, Erro
        cols = ['ARQUIVO', 'LINHA', 'CPF', 'CARTÃO', 'NOME', 'ERRO']
        
        for i, col in enumerate(cols):
            pdf.cell(w[i], 8, col, 1, 0, 'C', True)
        pdf.ln()
        
        pdf.set_font("Arial", '', 8)
        for _, row in critical_df.iterrows():
            pdf.cell(w[0], 6, str(row['ARQUIVO'])[:20], 1, 0, 'L')
            pdf.cell(w[1], 6, str(row['LINHA']), 1, 0, 'C')
            pdf.cell(w[2], 6, str(row['CPF']), 1, 0, 'C')
            pdf.cell(w[3], 6, str(row['CARTÃO']), 1, 0, 'C')
            pdf.cell(w[4], 6, str(row['NOME'])[:35], 1, 0, 'L')
            pdf.set_text_color(200, 0, 0)
            pdf.cell(w[5], 6, str(row['ERRO']), 1, 1, 'C')
            pdf.set_text_color(0, 0, 0)
        pdf.ln(10)
    else:
        pdf.set_text_color(0, 128, 0)
        pdf.set_font("Arial", 'B', 11)
        pdf.cell(0, 10, "✅ Nenhuma duplicidade crítica (Mesmo CPF com dados divergentes) encontrada.", 0, 1)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(5)

    # --- RESTANTE DO RELATÓRIO ---
    total_valor = df_filtered['valor_pagto'].sum() if 'valor_pagto' in df_filtered.columns else 0.0
    total_benef = df_filtered['num_cartao'].nunique() if 'num_cartao' in df_filtered.columns else 0
    total_registros = len(df_filtered)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "1. Resumo Analítico", 0, 1)
    pdf.set_font("Arial", '', 11)
    pdf.cell(100, 8, f"Total Pago: R$ {total_valor:,.2f}", 1)
    pdf.cell(0, 8, f"Beneficiários: {total_benef}", 1, 1)
    pdf.cell(100, 8, f"Total Registros: {total_registros}", 1, 1)
    pdf.ln(5)

    # Gráficos
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "2. Visualização Gráfica", 0, 1)
    if plt and 'programa' in df_filtered.columns:
        try:
            plt.figure(figsize=(10, 4))
            grp = df_filtered.groupby('programa')['valor_pagto'].sum().sort_values()
            plt.barh(grp.index, grp.values, color='skyblue')
            plt.title('Total por Projeto')
            plt.tight_layout()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                plt.savefig(tmp.name, dpi=90)
                img_path = tmp.name
            pdf.image(img_path, x=10, w=180)
            plt.close()
            os.remove(img_path)
        except: pass
    else:
        pdf.set_font("Arial", 'I', 10)
        pdf.cell(0, 10, "Gráfico indisponível.", 0, 1)
        
    return pdf.output(dest='S').encode('latin-1')

def generate_conference_pdf(df_div):
    """Gera Relatório PDF específico para Divergências Bancárias."""
    if FPDF is None: return b"Erro: FPDF ausente."
    pdf = FPDF()
    pdf.add_page(orientation='L')
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 8, "Prefeitura de São Paulo", 0, 1, 'C')
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 12, "Conferência Bancária (Divergências)", 1, 1, 'C')
    pdf.ln(5)
    
    # Tabela
    pdf.set_font("Arial", 'B', 8)
    pdf.set_fill_color(240, 240, 240)
    w = [30, 60, 60, 80, 40]
    headers = ["CARTÃO", "NOME SIS", "NOME BB", "DIVERGÊNCIA", "ARQUIVO"]
    for i, h in enumerate(headers):
        pdf.cell(w[i], 8, h, 1, 0, 'C', True)
    pdf.ln()
    
    pdf.set_font("Arial", '', 8)
    for _, row in df_div.iterrows():
        pdf.cell(w[0], 6, str(row['cartao']), 1, 0, 'C')
        pdf.cell(w[1], 6, str(row['nome_sis'])[:30], 1, 0, 'L')
        pdf.cell(w[2], 6, str(row['nome_bb'])[:30], 1, 0, 'L')
        pdf.cell(w[3], 6, str(row['divergencia'])[:50], 1, 0, 'L')
        pdf.cell(w[4], 6, str(row['arquivo_origem'])[:20], 1, 1, 'C')
        
    return pdf.output(dest='S').encode('latin-1')

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
                        st.rerun()
                    else: st.error("Inválido.")
                else: st.error("Domínio inválido.")

def main_app():
    user = st.session_state['user_info']
    st.sidebar.markdown(f"### Olá, {user['name']}")
    
    menu = ["Dashboard", "Upload e Processamento", "Análise e Correção", "Conferência Bancária (BB)", "Relatórios e Exportação"]
    if user['role'] == 'admin_ti': menu.append("Administração TI")
    
    choice = st.sidebar.radio("Menu", menu)
    
    if st.sidebar.button("Sair"):
        st.session_state.clear()
        st.rerun()

    if choice == "Upload e Processamento":
        render_header()
        st.markdown("### 📂 Upload de Pagamentos")
        files = st.file_uploader("Arquivos (CSV/XLSX)", accept_multiple_files=True)
        
        if files and st.button("Processar Arquivos"):
            conn = get_db_connection()
            exist = pd.read_sql("SELECT DISTINCT arquivo_origem FROM payments", conn)['arquivo_origem'].tolist()
            conn.close()
            
            dfs = []
            bar = st.progress(0)
            for i, f in enumerate(files):
                if f.name in exist:
                    st.warning(f"Ignorado (já existe): {f.name}")
                    continue
                try:
                    if f.name.endswith('.csv'): 
                        # Try/Except para encoding e separador
                        try:
                            df = pd.read_csv(f, sep=';', encoding='latin1', dtype=str, low_memory=False)
                        except:
                            f.seek(0)
                            df = pd.read_csv(f, sep=',', encoding='utf-8', dtype=str, low_memory=False)
                    else: df = pd.read_excel(f, dtype=str)
                    
                    df_std = standardize_dataframe(df, f.name)
                    if not df_std.empty: dfs.append(df_std)
                except Exception as e: st.error(f"Erro {f.name}: {e}")
                bar.progress((i+1)/len(files))
            
            if dfs:
                final = pd.concat(dfs, ignore_index=True)
                
                # === VALIDAÇÃO CRÍTICA NA TELA ===
                critical_errors = detect_critical_duplicates(final)
                if not critical_errors.empty:
                    st.error(f"🚨 ATENÇÃO: {len(critical_errors)} Registros com DUPLICIDADE DE CPF CONFLITANTE encontrados!")
                    st.markdown("**Estes registros apresentam o mesmo CPF mas nomes ou cartões diferentes no arquivo enviado.**")
                    st.dataframe(critical_errors, use_container_width=True)
                    st.warning("Verifique as linhas indicadas no arquivo original antes de prosseguir.")
                else:
                    st.success("✅ Nenhuma duplicidade crítica encontrada nos arquivos.")

                conn = get_db_connection()
                final.to_sql('payments', conn, if_exists='append', index=False)
                conn.close()
                st.success(f"{len(final)} registros salvos.")
            else: st.info("Nada a salvar.")

    elif choice == "Análise e Correção":
        render_header()
        st.markdown("### 🛠️ Análise")
        conn = get_db_connection()
        df = pd.read_sql("SELECT * FROM payments", conn)
        conn.close()
        
        if not df.empty:
            # Re-verificação na base completa
            st.subheader("Verificação de Integridade (Base Completa)")
            crit_all = detect_critical_duplicates(df)
            if not crit_all.empty:
                st.error("🚨 Inconsistências Críticas na Base de Dados")
                st.dataframe(crit_all)
            else:
                st.success("Base de dados íntegra quanto a duplicidades de CPF.")
            
            st.dataframe(df.head())

    elif choice == "Relatórios e Exportação":
        render_header()
        st.markdown("### 📥 Relatórios")
        conn = get_db_connection()
        df = pd.read_sql("SELECT * FROM payments", conn)
        conn.close()
        
        if not df.empty:
            # Filtros
            projs = df['programa'].unique()
            sel_proj = st.multiselect("Filtrar Projeto", projs, default=projs)
            df_exp = df[df['programa'].isin(sel_proj)]
            
            if st.button("Gerar Relatório PDF"):
                pdf_data = generate_pdf_report(df_exp)
                if isinstance(pdf_data, bytes):
                    st.download_button("Baixar PDF", pdf_data, "relatorio_executivo.pdf", "application/pdf")
                else: st.error(pdf_data)

    elif choice == "Dashboard":
        render_header()
        st.markdown("### 📊 Dashboard")
        conn = get_db_connection()
        df = pd.read_sql("SELECT * FROM payments", conn)
        conn.close()
        if not df.empty:
            total = df['valor_pagto'].sum()
            st.metric("Total", f"R$ {total:,.2f}")
            
            g1 = df.groupby('programa')['valor_pagto'].sum().reset_index()
            st.plotly_chart(px.bar(g1, x='valor_pagto', y='programa', orientation='h'))

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
                
                # Normalização para Cruzamento
                final_bb['key'] = final_bb['num_cartao'].astype(str).str.replace(r'^0+','', regex=True)
                df_sys['key'] = df_sys['num_cartao'].astype(str).str.replace(r'^0+','', regex=True).str.replace(r'\.0$','', regex=True)
                
                merged = pd.merge(df_sys, final_bb, on='key', suffixes=('_sis', '_bb'))
                
                # Lógica de Divergência
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
                else: st.success("Sucesso! Sem divergências.")
                conn.close()

    elif choice == "Administração TI" and user['role'] == 'admin_ti':
        render_header()
        if st.button("Limpar Dados Pagamento"):
            conn = get_db_connection()
            conn.execute("DELETE FROM payments")
            conn.commit()
            conn.close()
            st.success("Limpo.")

if __name__ == "__main__":
    init_db()
    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
    
    if st.session_state['logged_in']: 
        if st.session_state['user_info']['first_login']: change_password_screen()
        else: main_app()
    else: login_screen()
