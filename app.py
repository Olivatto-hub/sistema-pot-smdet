import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import hashlib
import re
import io
from datetime import datetime
import plotly.express as px
from fpdf import FPDF

# ==============================================================================
# CONFIGURAÇÃO INICIAL E ESTILOS
# ==============================================================================
st.set_page_config(
    page_title="POT - Sistema de Gerenciamento",
    page_icon="🏙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS Personalizados
st.markdown("""
<style>
    .main-header {font-size: 2.5rem; color: #004e92; text-align: center; margin-bottom: 1rem;}
    .sub-header {font-size: 1.5rem; color: #333; margin-top: 2rem; border-bottom: 2px solid #004e92;}
    .card {background-color: #f8f9fa; padding: 1.5rem; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 1rem;}
    .metric-value {font-size: 2rem; font-weight: bold; color: #004e92;}
    .metric-label {font-size: 1rem; color: #666;}
    .stButton>button {width: 100%; border-radius: 5px;}
    .success-msg {padding: 1rem; background-color: #d4edda; color: #155724; border-radius: 5px;}
    .error-msg {padding: 1rem; background-color: #f8d7da; color: #721c24; border-radius: 5px;}
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# BANCO DE DADOS E LOGS
# ==============================================================================
class DatabaseManager:
    def __init__(self, db_name="pot_system.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.create_tables()
        self.check_default_admin()

    def create_tables(self):
        cursor = self.conn.cursor()
        
        # Tabela Principal de Dados Unificados
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dados_pot (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                projeto TEXT,
                num_cartao TEXT,
                nome TEXT,
                cpf TEXT,
                rg TEXT,
                valor_pago REAL,
                data_referencia DATE,
                mes INTEGER,
                ano INTEGER,
                arquivo_origem TEXT,
                data_upload TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status_pagamento TEXT
            )
        """)
        
        # Tabela de Usuários
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                email TEXT PRIMARY KEY,
                password_hash TEXT,
                role TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Tabela de Logs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT,
                acao TEXT,
                detalhes TEXT,
                data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()

    def _hash_password(self, password):
        """Gera hash SHA-256 da senha."""
        return hashlib.sha256(password.encode()).hexdigest()

    def check_default_admin(self):
        """Cria o usuário admin padrão se a tabela de usuários estiver vazia."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT count(*) FROM usuarios")
        count = cursor.fetchone()[0]
        
        if count == 0:
            # Senha padrão: Smdetpot2025
            default_email = "admin@prefeitura.sp.gov.br"
            default_pass_hash = self._hash_password("Smdetpot2025")
            cursor.execute("INSERT INTO usuarios (email, password_hash, role) VALUES (?, ?, ?)", 
                           (default_email, default_pass_hash, "admin"))
            self.conn.commit()

    def authenticate_user(self, email, password):
        """Verifica credenciais no banco."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT password_hash, role FROM usuarios WHERE email = ?", (email,))
        result = cursor.fetchone()
        
        if result:
            stored_hash, role = result
            if stored_hash == self._hash_password(password):
                return True, role
        return False, None

    def add_user(self, creator_email, new_email, new_password, role):
        """Adiciona novo usuário."""
        if not new_email.endswith("@prefeitura.sp.gov.br"):
            return False, "O e-mail deve ser @prefeitura.sp.gov.br"
            
        try:
            pwd_hash = self._hash_password(new_password)
            cursor = self.conn.cursor()
            cursor.execute("INSERT INTO usuarios (email, password_hash, role) VALUES (?, ?, ?)", 
                           (new_email, pwd_hash, role))
            self.conn.commit()
            self.log_action(creator_email, "ADD_USER", f"Adicionou usuário {new_email} como {role}")
            return True, "Usuário criado com sucesso!"
        except sqlite3.IntegrityError:
            return False, "E-mail já cadastrado."
        except Exception as e:
            return False, str(e)

    def delete_user(self, admin_email, target_email):
        """Remove um usuário."""
        if admin_email == target_email:
            return False, "Você não pode excluir a si mesmo."
            
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM usuarios WHERE email = ?", (target_email,))
        self.conn.commit()
        self.log_action(admin_email, "DELETE_USER", f"Excluiu usuário {target_email}")
        return True, "Usuário excluído."

    def get_users(self):
        """Retorna lista de usuários."""
        return pd.read_sql("SELECT email, role, created_at FROM usuarios", self.conn)

    def log_action(self, usuario, acao, detalhes):
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO logs (usuario, acao, detalhes) VALUES (?, ?, ?)", 
                       (usuario, acao, detalhes))
        self.conn.commit()

    def insert_data(self, df, usuario):
        try:
            df.to_sql('dados_pot', self.conn, if_exists='append', index=False)
            self.log_action(usuario, "UPLOAD", f"Inseridos {len(df)} registros.")
            return True, f"{len(df)} registros importados com sucesso."
        except Exception as e:
            return False, str(e)

    def get_data(self, start_date=None, end_date=None):
        query = "SELECT * FROM dados_pot"
        params = []
        
        if start_date and end_date:
            query += " WHERE data_referencia BETWEEN ? AND ?"
            params = [start_date, end_date]
            
        return pd.read_sql(query, self.conn, params=params)

    def delete_all_data(self, usuario):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM dados_pot")
        self.conn.commit()
        self.log_action(usuario, "DELETE_ALL", "Todos os dados operacionais foram excluídos.")

    def get_logs(self):
        return pd.read_sql("SELECT * FROM logs ORDER BY data_hora DESC", self.conn)

# Instancia o DB
db = DatabaseManager()

# ==============================================================================
# FUNÇÕES DE UTILIDADE E LIMPEZA
# ==============================================================================
def clean_cpf(cpf):
    """Remove caracteres não numéricos e padroniza para 11 dígitos com zeros à esquerda."""
    if pd.isna(cpf):
        return ""
    cpf_str = str(cpf)
    # Remove tudo que não é dígito
    cpf_clean = re.sub(r'\D', '', cpf_str)
    # Preenche com zeros à esquerda até 11 dígitos
    return cpf_clean.zfill(11)

def extract_month_year_from_filename(filename):
    """Tenta extrair mês e ano do nome do arquivo."""
    meses = {
        'JANEIRO': 1, 'FEVEREIRO': 2, 'MARÇO': 3, 'ABRIL': 4, 'MAIO': 5, 'JUNHO': 6,
        'JULHO': 7, 'AGOSTO': 8, 'SETEMBRO': 9, 'OUTUBRO': 10, 'NOVEMBRO': 11, 'DEZEMBRO': 12,
        'JAN': 1, 'FEV': 2, 'MAR': 3, 'ABR': 4, 'MAI': 5, 'JUN': 6,
        'JUL': 7, 'AGO': 8, 'SET': 9, 'OUT': 10, 'NOV': 11, 'DEZ': 12
    }
    
    filename_upper = filename.upper()
    mes_detectado = None
    ano_detectado = datetime.now().year # Default ano atual

    # Busca mês
    for nome_mes, num_mes in meses.items():
        if nome_mes in filename_upper:
            mes_detectado = num_mes
            break
    
    # Busca ano (4 dígitos)
    anos = re.findall(r'20\d{2}', filename)
    if anos:
        ano_detectado = int(anos[0])
        
    return mes_detectado, ano_detectado

def normalize_columns(df):
    """Padroniza os nomes das colunas baseado nas variações conhecidas."""
    # Mapeamento de Colunas (Baseado na análise dos arquivos)
    mapa_colunas = {
        # Identificadores
        'Num Cartao': 'num_cartao', 'NumCartão': 'num_cartao', 'NumCartao': 'num_cartao', 
        'NumCart?': 'num_cartao', 'CODIGO': 'num_cartao', 'Cartão': 'num_cartao',
        
        # Nomes
        'Nome': 'nome', 'Nome do beneficiário': 'nome', 'Nome do benefici?io': 'nome', 
        'NOME': 'nome', 'NomeMãe': 'nome_mae', 'NomeM?': 'nome_mae', 'NOME DA MAE': 'nome_mae',
        
        # Documentos
        'CPF': 'cpf', 'RG': 'rg', 'DataNasc': 'data_nasc', 'DATA DE NASC': 'data_nasc',
        
        # Valores
        'Valor Pagto': 'valor_pago', 'ValorPagto': 'valor_pago', 'Valor Total': 'valor_total',
        'ValorTotal': 'valor_total', 'Valor Dia': 'valor_dia', 'vlr dia': 'valor_dia', 'valor': 'valor_dia',
        
        # Datas e Períodos
        'Data Pagto': 'data_pagto', 'DataPagto': 'data_pagto', 'DtLote': 'data_lote',
        'Mês': 'mes_ref', 'mês': 'mes_ref', 'm?': 'mes_ref',
        
        # Outros
        'Projeto': 'projeto', 'PROJETO': 'projeto', 'Distrito': 'distrito', 
        'Agência': 'agencia', 'Agencia': 'agencia', 'Ag?cia': 'agencia'
    }
    
    # Remove espaços extras dos nomes das colunas originais
    df.columns = [str(c).strip() for c in df.columns]
    
    # Renomeia
    df = df.rename(columns=mapa_colunas)
    
    return df

def process_file(uploaded_file):
    """Lê o arquivo, detecta formato, normaliza e retorna DataFrame limpo."""
    filename = uploaded_file.name
    file_ext = filename.split('.')[-1].lower()
    
    try:
        if file_ext == 'csv':
            # Tenta separador ; primeiro, depois ,
            try:
                df = pd.read_csv(uploaded_file, sep=';', encoding='latin1', on_bad_lines='skip')
                if len(df.columns) < 2:
                    uploaded_file.seek(0)
                    df = pd.read_csv(uploaded_file, sep=',', encoding='latin1', on_bad_lines='skip')
            except:
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file, sep=',', encoding='utf-8', on_bad_lines='skip')
                
        elif file_ext == 'txt':
            # Tenta ler largura fixa ou espaço (baseado no REL.CADASTRO)
            try:
                # read_csv com separador de espaços múltiplos (\s+) é melhor para arquivos formatados
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file, sep=r'\s+', encoding='latin1', on_bad_lines='skip')
            except:
                 # Fallback
                 uploaded_file.seek(0)
                 df = pd.read_csv(uploaded_file, sep='\t', encoding='latin1', on_bad_lines='skip')

        else:
            return None, "Formato não suportado."
    except Exception as e:
        return None, f"Erro ao ler arquivo: {e}"

    # 1. Normalizar Colunas
    df = normalize_columns(df)
    
    # 2. Garantir Colunas Essenciais (cria vazias se não existirem)
    required_cols = ['num_cartao', 'nome', 'cpf', 'projeto', 'valor_pago']
    for col in required_cols:
        if col not in df.columns:
            df[col] = None

    # 3. Limpeza de CPF
    if 'cpf' in df.columns:
        df['cpf'] = df['cpf'].apply(clean_cpf)
    
    # 4. Tratamento de Valores
    if 'valor_pago' in df.columns:
        # Remove R$, troca , por . e converte para float
        df['valor_pago'] = df['valor_pago'].astype(str).str.replace('R$', '', regex=False)
        df['valor_pago'] = df['valor_pago'].str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
        df['valor_pago'] = pd.to_numeric(df['valor_pago'], errors='coerce').fillna(0.0)

    # 5. Identificação de Data (Mês/Ano)
    mes_file, ano_file = extract_month_year_from_filename(filename)
    
    # Define Mês/Ano final
    current_date = datetime.now()
    
    # Cria colunas finais padronizadas para o banco
    df['mes'] = mes_file if mes_file else current_date.month
    df['ano'] = ano_file if ano_file else current_date.year
    
    # Cria uma data de referência (dia 1 do mês/ano)
    try:
        df['data_referencia'] = df.apply(lambda x: datetime(int(x['ano']), int(x['mes']), 1).date(), axis=1)
    except:
        df['data_referencia'] = current_date.date()

    df['arquivo_origem'] = filename
    
    # Filtra apenas colunas que existem na tabela do banco para evitar erro
    cols_db = ['projeto', 'num_cartao', 'nome', 'cpf', 'rg', 'valor_pago', 'data_referencia', 'mes', 'ano', 'arquivo_origem']
    cols_to_keep = [c for c in cols_db if c in df.columns]
    
    return df[cols_to_keep], None

# ==============================================================================
# GERAÇÃO DE RELATÓRIOS (PDF)
# ==============================================================================
class PDFReport(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'PREFEITURA DE SÃO PAULO - SMDET', 0, 1, 'C')
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, 'Programa Operação Trabalho (POT) - Relatório Executivo', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

def generate_pdf(df, period_str):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    
    # Info do Período
    pdf.cell(0, 10, f"Período de Referência: {period_str}", 0, 1)
    pdf.cell(0, 10, f"Data de Geração: {datetime.now().strftime('%d/%m/%Y %H:%M')}", 0, 1)
    pdf.ln(5)
    
    # Resumo Executivo
    total_valor = df['valor_pago'].sum()
    total_benef = df['num_cartao'].nunique()
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "Resumo Financeiro", 0, 1)
    pdf.set_font("Arial", size=10)
    pdf.cell(0, 10, f"Total de Beneficiários Únicos: {total_benef}", 0, 1)
    pdf.cell(0, 10, f"Valor Total de Pagamentos: R$ {total_valor:,.2f}", 0, 1)
    pdf.ln(5)
    
    # Tabela por Projeto (Agrupada)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "Detalhamento por Projeto", 0, 1)
    pdf.ln(2)
    
    # Header Tabela
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(100, 10, "Projeto", 1)
    pdf.cell(40, 10, "Qtd Pessoas", 1)
    pdf.cell(50, 10, "Valor Total (R$)", 1)
    pdf.ln()
    
    # Dados Tabela
    if 'projeto' in df.columns:
        agrupado = df.groupby('projeto').agg({'num_cartao': 'nunique', 'valor_pago': 'sum'}).reset_index()
        pdf.set_font("Arial", size=10)
        for _, row in agrupado.iterrows():
            proj_name = str(row['projeto'])[:40] # Truncate
            pdf.cell(100, 10, proj_name, 1)
            pdf.cell(40, 10, str(row['num_cartao']), 1)
            pdf.cell(50, 10, f"{row['valor_pago']:,.2f}", 1)
            pdf.ln()
            
    return pdf.output(dest='S').encode('latin-1')

# ==============================================================================
# LÓGICA DE AUTENTICAÇÃO
# ==============================================================================
def login_screen():
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown("<h2 style='text-align: center;'>🔐 Acesso ao Sistema POT</h2>", unsafe_allow_html=True)
        
        # Info padrão para primeiro acesso
        if len(db.get_users()) <= 1:
            st.info("Primeiro acesso? Use admin@prefeitura.sp.gov.br / Smdetpot2025")

        with st.form("login_form"):
            username = st.text_input("E-mail Corporativo (@prefeitura.sp.gov.br)")
            password = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar")
            
            if submitted:
                success, role = db.authenticate_user(username, password)
                if success:
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = username
                    st.session_state['role'] = role
                    st.success("Login realizado com sucesso!")
                    st.rerun()
                else:
                    st.error("Credenciais inválidas.")

# ==============================================================================
# TELAS DO SISTEMA
# ==============================================================================

def dashboard_screen():
    st.markdown("<h1 class='main-header'>📊 Dashboard Executivo</h1>", unsafe_allow_html=True)
    
    # Filtros
    st.sidebar.header("Filtros de Período")
    start_date = st.sidebar.date_input("Data Início", value=pd.to_datetime("2024-01-01"))
    end_date = st.sidebar.date_input("Data Fim", value=datetime.now())
    
    # Carrega Dados
    df = db.get_data(start_date, end_date)
    
    if df.empty:
        st.info("Nenhum dado encontrado para o período selecionado. Faça upload de arquivos.")
        return

    # KPIs Principais
    col1, col2, col3 = st.columns(3)
    total_pago = df['valor_pago'].sum()
    total_beneficiarios = df['num_cartao'].nunique()
    total_projetos = df['projeto'].nunique()
    
    with col1:
        st.markdown(f"<div class='card'><div class='metric-label'>Valor Total Pago</div><div class='metric-value'>R$ {total_pago:,.2f}</div></div>", unsafe_allow_html=True)
    with col2:
        st.markdown(f"<div class='card'><div class='metric-label'>Beneficiários Únicos</div><div class='metric-value'>{total_beneficiarios}</div></div>", unsafe_allow_html=True)
    with col3:
        st.markdown(f"<div class='card'><div class='metric-label'>Projetos Ativos</div><div class='metric-value'>{total_projetos}</div></div>", unsafe_allow_html=True)

    # Gráficos
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.subheader("Pagamentos por Projeto")
        if 'projeto' in df.columns:
            fig_proj = px.bar(df.groupby('projeto')['valor_pago'].sum().reset_index(), 
                              x='projeto', y='valor_pago', title="Total por Projeto")
            st.plotly_chart(fig_proj, use_container_width=True)
            
    with col_chart2:
        st.subheader("Evolução Mensal")
        if 'mes' in df.columns:
            df_evo = df.groupby(['ano', 'mes'])['valor_pago'].sum().reset_index()
            df_evo['periodo'] = df_evo['mes'].astype(str) + '/' + df_evo['ano'].astype(str)
            fig_evo = px.line(df_evo, x='periodo', y='valor_pago', title="Evolução de Pagamentos", markers=True)
            st.plotly_chart(fig_evo, use_container_width=True)

    # Exportação Rápida da Tela
    st.markdown("### 📥 Exportar Dados Atuais")
    col_exp1, col_exp2, col_exp3 = st.columns(3)
    
    # CSV
    csv = df.to_csv(index=False).encode('utf-8')
    col_exp1.download_button("Baixar CSV", data=csv, file_name="relatorio_pot.csv", mime="text/csv")
    
    # Excel - COM CORREÇÃO PARA EVITAR ERRO DE ENGINE
    buffer = io.BytesIO()
    try:
        # Não especificamos engine, o pandas tentará usar openpyxl se disponível
        with pd.ExcelWriter(buffer) as writer:
            df.to_excel(writer, index=False, sheet_name='Dados')
        col_exp2.download_button("Baixar Excel", data=buffer, file_name="relatorio_pot.xlsx", mime="application/vnd.ms-excel")
    except Exception as e:
        col_exp2.warning(f"Excel indisponível: {e}")
        col_exp2.info("Use a opção CSV ao lado.")
    
    # PDF
    try:
        pdf_bytes = generate_pdf(df, f"{start_date} a {end_date}")
        col_exp3.download_button("Baixar Relatório PDF", data=pdf_bytes, file_name="relatorio_executivo.pdf", mime="application/pdf")
    except Exception as e:
        col_exp3.error(f"Erro PDF: {e}")

def upload_screen():
    st.markdown("<h1 class='main-header'>📂 Importação de Arquivos</h1>", unsafe_allow_html=True)
    
    uploaded_files = st.file_uploader(
        "Arraste arquivos CSV ou TXT (Cadastro, Pendências, Pagamentos)", 
        accept_multiple_files=True,
        type=['csv', 'txt']
    )
    
    if st.button("Processar e Salvar no Banco de Dados"):
        if not uploaded_files:
            st.warning("Selecione arquivos primeiro.")
            return
            
        progress_bar = st.progress(0)
        
        for i, file in enumerate(uploaded_files):
            st.write(f"Processando: **{file.name}**...")
            df_processed, error = process_file(file)
            
            if error:
                st.error(f"Erro em {file.name}: {error}")
            else:
                # Salvar no DB
                success, msg = db.insert_data(df_processed, st.session_state['username'])
                if success:
                    st.success(f"✅ {file.name}: {msg}")
                else:
                    st.error(f"❌ {file.name}: {msg}")
            
            progress_bar.progress((i + 1) / len(uploaded_files))
            
        st.success("Processamento concluído!")

def admin_screen():
    st.markdown("<h1 class='main-header'>🛠️ Painel Administrativo</h1>", unsafe_allow_html=True)
    
    if st.session_state['role'] != 'admin':
        st.error("Acesso Negado. Apenas administradores.")
        return

    tab1, tab2, tab3 = st.tabs(["Gerenciar Usuários", "Logs do Sistema", "Zona de Perigo"])

    # TAB 1: Gerenciar Usuários
    with tab1:
        st.subheader("Cadastrar Novo Usuário")
        with st.form("add_user_form"):
            new_email = st.text_input("E-mail (@prefeitura.sp.gov.br)")
            new_pass = st.text_input("Senha Inicial", type="password")
            new_role = st.selectbox("Perfil", ["user", "admin"])
            submit_user = st.form_submit_button("Criar Usuário")
            
            if submit_user:
                if new_email and new_pass:
                    ok, msg = db.add_user(st.session_state['username'], new_email, new_pass, new_role)
                    if ok:
                        st.success(msg)
                    else:
                        st.error(msg)
                else:
                    st.warning("Preencha todos os campos.")
        
        st.divider()
        st.subheader("Usuários Existentes")
        users_df = db.get_users()
        
        # Display users with delete button
        for index, row in users_df.iterrows():
            c1, c2, c3, c4 = st.columns([3, 1, 2, 1])
            c1.write(f"**{row['email']}**")
            c2.write(row['role'].upper())
            c3.write(row['created_at'])
            if c4.button("Excluir", key=f"del_{row['email']}"):
                ok, msg = db.delete_user(st.session_state['username'], row['email'])
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

    # TAB 2: Logs
    with tab2:
        st.subheader("Auditoria de Ações")
        logs = db.get_logs()
        st.dataframe(logs, use_container_width=True)
    
    # TAB 3: Perigo
    with tab3:
        st.subheader("Limpeza de Dados")
        st.warning("Cuidado: A exclusão de dados operacionais é irreversível.")
        if st.button("🗑️ EXCLUIR DADOS DE IMPORTAÇÃO (Mantém Usuários)", type="primary"):
            db.delete_all_data(st.session_state['username'])
            st.success("Banco de dados operacional limpo com sucesso.")
            st.rerun()

# ==============================================================================
# MAIN APP FLOW
# ==============================================================================
def main():
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
        st.session_state['role'] = None
        st.session_state['username'] = None

    if not st.session_state['logged_in']:
        login_screen()
    else:
        # Sidebar Navigation
        with st.sidebar:
            st.image("https://www.prefeitura.sp.gov.br/cidade/secretarias/upload/trabalho/logo_smdet.png", width=200) # Placeholder logo
            st.write(f"Bem-vindo, **{st.session_state['username']}**")
            st.write(f"Perfil: **{st.session_state['role'].upper()}**")
            
            menu = st.radio("Navegação", ["Dashboard", "Importação", "Admin" if st.session_state['role'] == 'admin' else None])
            
            if st.button("Sair"):
                st.session_state['logged_in'] = False
                st.session_state['role'] = None
                st.session_state['username'] = None
                st.rerun()
        
        # Router
        if menu == "Dashboard":
            dashboard_screen()
        elif menu == "Importação":
            upload_screen()
        elif menu == "Admin" and st.session_state['role'] == 'admin':
            admin_screen()

if __name__ == "__main__":
    main()
