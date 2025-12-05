import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sqlite3
import hashlib
import io
import re
from datetime import datetime
from fpdf import FPDF

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
    .main-header {
        font-size: 2rem;
        color: #1E3A8A;
        text-align: center;
        margin-bottom: 20px;
        border-bottom: 2px solid #ddd;
        padding-bottom: 10px;
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
        .main-header {
            color: #60A5FA;
        }
    }
</style>
""", unsafe_allow_html=True)

# ===========================================
# GESTÃO DE BANCO DE DADOS (SQLite)
# ===========================================

DB_FILE = 'pot_system.db'

def init_db():
    """Inicializa o banco de dados e cria tabelas se não existirem."""
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
    # Armazena os dados processados para persistência
    c.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            programa TEXT,
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
            status TEXT, -- 'VALIDO', 'CORRECAO', 'PAGO'
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
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

# Mapeamento de Colunas (Inteligência desenvolvida nas análises anteriores)
COLUMN_MAP = {
    # Chaves Principais
    'num cartao': 'num_cartao', 'numcartao': 'num_cartao', 'numcartão': 'num_cartao', 
    'código': 'num_cartao', 'codigo': 'num_cartao', 'c?igo': 'num_cartao',
    # Dados Pessoais
    'nome': 'nome', 'nome do beneficiário': 'nome', 'participante': 'nome', 'nome do benefici?io': 'nome',
    'cpf': 'cpf',
    'rg': 'rg',
    # Financeiro
    'valor pagto': 'valor_pagto', 'valorpagto': 'valor_pagto', 'valor total': 'valor_pagto',
    'dias a apagar': 'qtd_dias', 'dias': 'qtd_dias', 'dias validos': 'qtd_dias',
    'data pagto': 'data_pagto', 'datapagto': 'data_pagto',
    'projeto': 'programa',
    'mês': 'mes_ref', 'mes': 'mes_ref'
}

def normalize_text(text):
    if isinstance(text, str):
        return text.strip().lower()
    return text

def standardize_dataframe(df, filename):
    """Padroniza colunas e extrai metadados do arquivo."""
    
    # 1. Limpeza de Colunas (strip e lower para match)
    df.columns = [str(c).strip() for c in df.columns]
    
    # 2. Renomear colunas usando o mapa
    rename_dict = {}
    for col in df.columns:
        col_lower = col.lower()
        if col_lower in COLUMN_MAP:
            rename_dict[col] = COLUMN_MAP[col_lower]
        else:
            # Tentar match parcial
            for key, val in COLUMN_MAP.items():
                if key in col_lower:
                    rename_dict[col] = val
                    break
    
    df = df.rename(columns=rename_dict)
    
    # 3. Extrair Projeto e Data do Nome do Arquivo se não existir nas colunas
    filename_upper = filename.upper()
    
    # Identificar Programa
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
        
    # Identificar Mês/Ano (Simplificado)
    meses = ['JANEIRO', 'FEVEREIRO', 'MARÇO', 'ABRIL', 'MAIO', 'JUNHO', 'JULHO', 'AGOSTO', 'SETEMBRO', 'OUTUBRO', 'NOVEMBRO', 'DEZEMBRO']
    mes_ref = 'N/A'
    for mes in meses:
        if mes in filename_upper:
            mes_ref = mes
            break
            
    if 'mes_ref' not in df.columns:
        df['mes_ref'] = mes_ref
        
    # 4. Garantir colunas essenciais
    essential_cols = ['num_cartao', 'nome', 'cpf', 'rg', 'valor_pagto', 'programa', 'mes_ref']
    for col in essential_cols:
        if col not in df.columns:
            df[col] = None

    # 5. Limpeza de Dados
    # Num Cartão: Remover .0 e converter para string
    df['num_cartao'] = df['num_cartao'].astype(str).str.replace(r'\.0$', '', regex=True).replace('nan', '')
    
    # CPF: Remover caracteres não numéricos
    df['cpf'] = df['cpf'].astype(str).str.replace(r'\D', '', regex=True).replace('nan', '')
    
    # Valor: Converter para float
    def clean_currency(x):
        if isinstance(x, str):
            x = x.replace('R$', '').replace('.', '').replace(',', '.')
        try:
            return float(x)
        except:
            return 0.0
            
    if 'valor_pagto' in df.columns:
        df['valor_pagto'] = df['valor_pagto'].apply(clean_currency)
        
    df['arquivo_origem'] = filename
    
    return df

def generate_bb_txt(df):
    """Gera string no formato Fixed-Width do Banco do Brasil (Simulado para Comparação)."""
    # Formato Baseado nos arquivos REL.CADASTRO enviados
    # 0          Projeto                        NumCartão Nome...
    buffer = io.StringIO()
    
    # Header Simulado (ou linha de cada registro)
    # Layout estimado:
    # Pos 0: '0' ou '1'
    # Pos 1-29: Projeto (30 chars)
    # Pos 30-44: NumCartao (15 chars)
    # Pos 45-94: Nome (50 chars)
    # Pos 95-109: RG (15 chars)
    # Pos 110-124: CPF (15 chars)
    
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
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "Relatório Executivo - Monitoramento POT", 0, 1, 'C')
    pdf.ln(10)
    
    # Métricas
    total_valor = df_filtered['valor_pagto'].sum()
    total_benef = df_filtered['num_cartao'].nunique()
    total_projetos = df_filtered['programa'].nunique()
    
    pdf.set_font("Arial", '', 12)
    pdf.cell(0, 10, f"Data de Geração: {datetime.now().strftime('%d/%m/%Y %H:%M')}", 0, 1)
    pdf.ln(5)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "Resumo Financeiro e Operacional:", 0, 1)
    pdf.set_font("Arial", '', 12)
    pdf.cell(0, 10, f"Valor Total de Pagamentos: R$ {total_valor:,.2f}", 0, 1)
    pdf.cell(0, 10, f"Total de Beneficiários Únicos: {total_benef}", 0, 1)
    pdf.cell(0, 10, f"Projetos Ativos: {total_projetos}", 0, 1)
    pdf.ln(10)
    
    # Detalhe por Projeto
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "Detalhamento por Projeto:", 0, 1)
    
    group_proj = df_filtered.groupby('programa')['valor_pagto'].sum().reset_index()
    
    pdf.set_font("Courier", '', 10)
    pdf.cell(50, 10, "PROJETO", 1)
    pdf.cell(50, 10, "VALOR TOTAL", 1)
    pdf.ln()
    
    for _, row in group_proj.iterrows():
        pdf.cell(50, 10, str(row['programa'])[:20], 1)
        pdf.cell(50, 10, f"R$ {row['valor_pagto']:,.2f}", 1)
        pdf.ln()
        
    return pdf.output(dest='S').encode('latin-1')

# ===========================================
# INTERFACE E FLUXO DO USUÁRIO
# ===========================================

def login_screen():
    st.markdown("<div class='main-header'>🔐 Acesso ao Sistema POT</div>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        with st.form("login_form"):
            email = st.text_input("E-mail (@prefeitura.sp.gov.br)")
            password = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar", use_container_width=True)
            
            if submitted:
                # Validação simples de domínio
                if not email.endswith("@prefeitura.sp.gov.br"):
                    st.error("Apenas e-mails institucionais permitidos.")
                    return

                # Hash da senha
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
    
    # Sidebar
    st.sidebar.markdown(f"### Olá, {user['name']}")
    st.sidebar.caption(f"Perfil: {user['role'].upper().replace('_', ' ')}")
    
    menu_options = ["Dashboard", "Upload e Processamento", "Análise e Correção", "Relatórios e Exportação"]
    
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
        st.markdown("<h2 class='main-header'>📂 Upload de Arquivos</h2>", unsafe_allow_html=True)
        st.info("Arraste arquivos CSV ou Excel. O sistema padronizará automaticamente as colunas.")
        
        uploaded_files = st.file_uploader("Selecione os arquivos", accept_multiple_files=True, type=['csv', 'xlsx', 'txt'])
        
        if uploaded_files:
            if st.button(f"Processar {len(uploaded_files)} Arquivos"):
                all_data = []
                progress_bar = st.progress(0)
                
                for idx, file in enumerate(uploaded_files):
                    try:
                        # Ler arquivo dependendo do tipo
                        if file.name.endswith('.csv'):
                            # Tentar ; primeiro, depois ,
                            try:
                                df = pd.read_csv(file, sep=';', encoding='latin1')
                            except:
                                file.seek(0)
                                df = pd.read_csv(file, sep=',', encoding='utf-8')
                        elif file.name.endswith('.xlsx'):
                            df = pd.read_excel(file)
                        elif file.name.endswith('.txt'):
                            # Ler TXT (assumindo formato do banco ou tabular simples)
                            df = pd.read_csv(file, sep=r'\s+', encoding='latin1', error_bad_lines=False)
                            
                        # Padronizar
                        df_std = standardize_dataframe(df, file.name)
                        all_data.append(df_std)
                        
                    except Exception as e:
                        st.error(f"Erro ao ler {file.name}: {e}")
                    
                    progress_bar.progress((idx + 1) / len(uploaded_files))
                
                if all_data:
                    final_df = pd.concat(all_data, ignore_index=True)
                    
                    # Salvar no Banco de Dados
                    conn = get_db_connection()
                    
                    # Para simplificar, usamos pandas to_sql
                    # Mapear colunas do DF para o Banco
                    db_cols = ['programa', 'num_cartao', 'nome', 'cpf', 'rg', 'valor_pagto', 'mes_ref', 'arquivo_origem']
                    df_to_save = final_df[ [c for c in db_cols if c in final_df.columns] ].copy()
                    
                    df_to_save['status'] = 'IMPORTADO'
                    df_to_save.to_sql('payments', conn, if_exists='append', index=False)
                    conn.close()
                    
                    st.success(f"Sucesso! {len(final_df)} registros importados para o Banco de Dados.")
                    st.dataframe(final_df.head())
                else:
                    st.warning("Nenhum dado válido processado.")

    elif choice == "Análise e Correção":
        st.markdown("<h2 class='main-header'>🛠️ Análise e Correção de Dados</h2>", unsafe_allow_html=True)
        
        conn = get_db_connection()
        df = pd.read_sql("SELECT * FROM payments", conn)
        conn.close()
        
        if df.empty:
            st.warning("Banco de Dados vazio. Faça upload de arquivos primeiro.")
        else:
            # Filtros
            col_f1, col_f2 = st.columns(2)
            filtro_proj = col_f1.multiselect("Filtrar Projeto", df['programa'].unique())
            filtro_mes = col_f2.multiselect("Filtrar Mês", df['mes_ref'].unique())
            
            if filtro_proj: df = df[df['programa'].isin(filtro_proj)]
            if filtro_mes: df = df[df['mes_ref'].isin(filtro_mes)]
            
            # Identificação de Problemas
            # Critério: Num Cartão é obrigatório. CPF/Nome/RG avisar se vazio.
            
            # Tratamento de NaNs para exibição
            df_display = df.fillna('')
            
            # Função de estilo para destacar linhas com problemas
            def highlight_issues(row):
                # Se faltar Num Cartão (o que é crítico, mas o código já limpa), ou faltar CPF/Nome
                if not row['num_cartao'] or not row['cpf'] or not row['nome']:
                    return ['background-color: #ffcccc'] * len(row)
                return [''] * len(row)
            
            st.subheader("Registros (Editável para Admin Equipe/TI)")
            
            # Se for Admin, permite editar
            if user['role'] in ['admin_ti', 'admin_equipe']:
                edited_df = st.data_editor(df_display, num_rows="dynamic", key="data_editor")
                
                if st.button("Salvar Alterações no Banco"):
                    # Lógica simplificada de atualização (na prática, requer update por ID)
                    # Aqui vamos substituir tudo pelos dados editados (CUIDADO em produção)
                    conn = get_db_connection()
                    # Limpar filtrados e reinserir (simplificação para o protótipo)
                    # O ideal seria update row by row pelo ID
                    st.info("Funcionalidade de Update em lote simulada.")
                    # Em produção: iterar rows modificadas e dar UPDATE payments SET ... WHERE id = ...
                    conn.close()
            else:
                st.dataframe(df_display.style.apply(highlight_issues, axis=1))
            
            # Exibir Inconsistências Específicas
            missing_cpf = df[ (df['cpf'] == '') | (df['cpf'].isnull()) ]
            if not missing_cpf.empty:
                st.error(f"⚠️ {len(missing_cpf)} Registros sem CPF!")
                st.dataframe(missing_cpf)

    elif choice == "Dashboard":
        st.markdown("<h2 class='main-header'>📊 Dashboard Executivo</h2>", unsafe_allow_html=True)
        
        conn = get_db_connection()
        df = pd.read_sql("SELECT * FROM payments", conn)
        conn.close()
        
        if not df.empty:
            # KPIS
            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            kpi1.metric("Total Pagamentos", f"R$ {df['valor_pagto'].sum():,.2f}")
            kpi2.metric("Beneficiários Únicos", df['num_cartao'].nunique())
            kpi3.metric("Projetos Ativos", df['programa'].nunique())
            kpi4.metric("Registros Totais", len(df))
            
            st.markdown("---")
            
            # Gráficos
            c1, c2 = st.columns(2)
            
            with c1:
                st.subheader("Valor por Projeto")
                proj_group = df.groupby('programa')['valor_pagto'].sum().reset_index()
                fig_bar = px.bar(proj_group, x='programa', y='valor_pagto', color='programa', title="Total Pago por Projeto")
                st.plotly_chart(fig_bar, use_container_width=True)
                
            with c2:
                st.subheader("Distribuição de Valores")
                fig_hist = px.histogram(df, x='valor_pagto', nbins=20, title="Histograma de Valores de Benefício")
                st.plotly_chart(fig_hist, use_container_width=True)
                
        else:
            st.info("Sem dados para exibir.")

    elif choice == "Relatórios e Exportação":
        st.markdown("<h2 class='main-header'>📥 Exportação</h2>", unsafe_allow_html=True)
        
        conn = get_db_connection()
        df = pd.read_sql("SELECT * FROM payments", conn)
        conn.close()
        
        if not df.empty:
            st.markdown("### Selecione os Filtros para Exportação")
            c1, c2 = st.columns(2)
            prog_filter = c1.multiselect("Projetos", df['programa'].unique(), default=df['programa'].unique())
            df_export = df[df['programa'].isin(prog_filter)]
            
            st.markdown("### Baixar Arquivos")
            
            c_csv, c_xls, c_txt, c_pdf = st.columns(4)
            
            # CSV
            csv = df_export.to_csv(index=False, sep=';').encode('utf-8-sig')
            c_csv.download_button("📄 Baixar CSV", csv, "pagamentos_pot.csv", "text/csv")
            
            # Excel
            buffer_xls = io.BytesIO()
            with pd.ExcelWriter(buffer_xls, engine='xlsxwriter') as writer:
                df_export.to_excel(writer, sheet_name='Pagamentos', index=False)
            c_xls.download_button("📊 Baixar Excel", buffer_xls.getvalue(), "pagamentos_pot.xlsx", "application/vnd.ms-excel")
            
            # TXT (BB)
            txt_content = generate_bb_txt(df_export)
            c_txt.download_button("🏦 Baixar TXT (Layout BB)", txt_content, "remessa_bb.txt", "text/plain")
            
            # PDF
            if st.button("📑 Gerar Relatório PDF"):
                pdf_bytes = generate_pdf_report(df_export)
                # Hack para download direto do PDF gerado em memória
                b64 = re.sub(r'b\'|\'', '', str(pd.Series([pdf_bytes]).apply(lambda x: io.BytesIO(x).getvalue()).values[0])) # Simplificação
                # Usando st.download_button direto é melhor
                st.download_button("Baixar PDF Gerado", pdf_bytes, "relatorio_executivo.pdf", "application/pdf")
                
        else:
            st.warning("Sem dados.")

    elif choice == "Administração TI (DB)":
        st.markdown("<h2 class='main-header'>⚙️ Administração TI</h2>", unsafe_allow_html=True)
        st.error("Zona de Perigo! Ações irreversíveis.")
        
        if st.button("🗑️ LIMPAR TODO O BANCO DE DADOS (TRUNCATE)"):
            conn = get_db_connection()
            conn.execute("DELETE FROM payments")
            conn.commit()
            conn.close()
            st.success("Banco de dados limpo com sucesso.")
            
        st.markdown("---")
        st.subheader("Consulta SQL Direta")
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
                        # Senha temp: mudar123
                        pass_temp = hashlib.sha256('mudar123'.encode()).hexdigest()
                        conn.execute("INSERT INTO users VALUES (?, ?, ?, ?, 1)", (new_email, pass_temp, new_role, new_name))
                        conn.commit()
                        st.success(f"Usuário {new_email} criado com senha temporária 'mudar123'.")
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
        # Verificar troca de senha obrigatória
        if st.session_state['user_info']['first_login'] == 1:
            change_password_screen()
        else:
            main_app()
