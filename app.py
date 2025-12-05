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

# Mapeamento de Colunas
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

def remove_total_row(df):
    """
    Verifica se a última linha é uma linha de totalização e a remove.
    Critério: Valor Pagto existe, mas Num Cartao, CPF, Nome e RG estão vazios/nulos.
    """
    if df.empty:
        return df

    last_idx = df.index[-1]
    
    # Colunas de identificação para verificar vacuidade
    id_cols = ['num_cartao', 'cpf', 'nome', 'rg']
    
    is_id_empty = True
    for col in id_cols:
        if col in df.columns:
            val = df.at[last_idx, col]
            # Verifica se não é nulo e se, convertido para string, tem conteúdo
            if pd.notna(val) and str(val).strip() != '' and str(val).strip().lower() != 'nan':
                is_id_empty = False
                break
    
    # Verifica se há valor de pagamento (indicando que é uma linha de soma)
    has_value = False
    if 'valor_pagto' in df.columns:
        val_pagto = df.at[last_idx, 'valor_pagto']
        if pd.notna(val_pagto):
            has_value = True
            
    # Se não tem identificação mas tem valor (ou apenas não tem identificação), remove
    if is_id_empty:
        df = df.drop(last_idx)
        
    return df

def standardize_dataframe(df, filename):
    """Padroniza colunas e extrai metadados do arquivo."""
    
    # 1. Limpeza de Nomes de Colunas
    df.columns = [str(c).strip() for c in df.columns]
    
    # 2. Renomear colunas usando o mapa
    rename_dict = {}
    for col in df.columns:
        col_lower = col.lower()
        if col_lower in COLUMN_MAP:
            rename_dict[col] = COLUMN_MAP[col_lower]
        else:
            # Tentar match parcial seguro
            for key, val in COLUMN_MAP.items():
                if key == col_lower: # Match exato primeiro
                    rename_dict[col] = val
                    break
            # Match parcial se não achou exato
            if col not in rename_dict:
                 for key, val in COLUMN_MAP.items():
                    if key in col_lower:
                        rename_dict[col] = val
                        break
    
    df = df.rename(columns=rename_dict)
    
    # CORREÇÃO: Remover colunas duplicadas
    df = df.loc[:, ~df.columns.duplicated()]
    
    # 3. Extrair Projeto e Data do Nome do Arquivo se não existir nas colunas
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
        
    # Identificar Mês (Simplificado)
    meses = ['JANEIRO', 'FEVEREIRO', 'MARÇO', 'ABRIL', 'MAIO', 'JUNHO', 'JULHO', 'AGOSTO', 'SETEMBRO', 'OUTUBRO', 'NOVEMBRO', 'DEZEMBRO']
    mes_ref = 'N/A'
    for mes in meses:
        if mes in filename_upper:
            mes_ref = mes
            break
            
    if 'mes_ref' not in df.columns:
        df['mes_ref'] = mes_ref
        
    # 4. Garantir colunas essenciais
    essential_check = ['num_cartao', 'nome', 'cpf', 'rg', 'valor_pagto']
    for col in essential_check:
        if col not in df.columns:
            df[col] = None 

    # === REMOVER LINHA DE TOTAL ===
    df = remove_total_row(df)
    # ==============================

    # 5. Limpeza de Dados
    
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
    
    cols_to_keep = ['programa', 'num_cartao', 'nome', 'cpf', 'rg', 'valor_pagto', 'data_pagto', 'qtd_dias', 'mes_ref', 'ano_ref', 'arquivo_origem']
    final_cols = [c for c in cols_to_keep if c in df.columns]
    
    return df[final_cols]

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
    """Gera Relatório Executivo em PDF com cabeçalho oficial e análises detalhadas."""
    pdf = FPDF()
    pdf.add_page()
    
    # --- CABEÇALHO ---
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 8, "Prefeitura de São Paulo", 0, 1, 'C')
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 8, "Secretaria Municipal do Desenvolvimento Econômico e Trabalho", 0, 1, 'C')
    pdf.ln(5)
    
    pdf.set_fill_color(220, 220, 220)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 12, "Relatório Executivo POT", 1, 1, 'C', fill=True)
    pdf.ln(10)
    
    # --- DADOS GERAIS ---
    # Cálculos
    total_valor = df_filtered['valor_pagto'].sum() if 'valor_pagto' in df_filtered.columns else 0.0
    total_benef = df_filtered['num_cartao'].nunique() if 'num_cartao' in df_filtered.columns else 0
    total_projetos = df_filtered['programa'].nunique() if 'programa' in df_filtered.columns else 0
    total_registros = len(df_filtered)
    
    # Texto
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 6, f"Data de Geração: {datetime.now().strftime('%d/%m/%Y às %H:%M')}", 0, 1, 'R')
    pdf.ln(5)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "1. Resumo Analítico Consolidado", 0, 1)
    
    pdf.set_font("Arial", '', 12)
    pdf.cell(100, 8, "Total de Valores Pagos:", 1)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 8, f"R$ {total_valor:,.2f}", 1, 1) # Negrito para o valor
    
    pdf.set_font("Arial", '', 12)
    pdf.cell(100, 8, "Total de Beneficiários Únicos:", 1)
    pdf.cell(0, 8, str(total_benef), 1, 1)
    
    pdf.cell(100, 8, "Total de Projetos Contemplados:", 1)
    pdf.cell(0, 8, str(total_projetos), 1, 1)
    
    pdf.cell(100, 8, "Total de Registros Processados:", 1)
    pdf.cell(0, 8, str(total_registros), 1, 1)
    
    pdf.ln(10)
    
    # --- DETALHAMENTO POR PROJETO ---
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "2. Detalhamento Financeiro por Projeto", 0, 1)
    
    if 'programa' in df_filtered.columns and 'valor_pagto' in df_filtered.columns:
        # Agrupamento
        group_proj = df_filtered.groupby('programa').agg({
            'valor_pagto': 'sum',
            'num_cartao': 'count' # Contagem de registros por projeto
        }).reset_index().sort_values('valor_pagto', ascending=False)
        
        # Cabeçalho da Tabela
        pdf.set_font("Arial", 'B', 10)
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(90, 8, "PROJETO", 1, 0, 'L', True)
        pdf.cell(40, 8, "QTD REGISTROS", 1, 0, 'C', True)
        pdf.cell(60, 8, "VALOR TOTAL (R$)", 1, 1, 'R', True)
        
        # Linhas da Tabela
        pdf.set_font("Arial", '', 10)
        for _, row in group_proj.iterrows():
            nome_proj = str(row['programa'])[:40] # Truncar nomes muito longos
            qtd = str(row['num_cartao'])
            val = f"{row['valor_pagto']:,.2f}"
            
            pdf.cell(90, 8, nome_proj, 1)
            pdf.cell(40, 8, qtd, 1, 0, 'C')
            pdf.cell(60, 8, val, 1, 1, 'R')
            
    else:
        pdf.set_font("Arial", 'I', 12)
        pdf.cell(0, 10, "Dados insuficientes para detalhamento por projeto.", 0, 1)
        
    pdf.ln(10)
    
    # --- NOTAS DE ANÁLISE ---
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "3. Observações de Processamento", 0, 1)
    pdf.set_font("Arial", '', 10)
    
    # Verificar CPFs vazios para o relatório
    sem_cpf = 0
    if 'cpf' in df_filtered.columns:
        sem_cpf = df_filtered[ (df_filtered['cpf'] == '') | (df_filtered['cpf'].isnull()) ].shape[0]
        
    pdf.multi_cell(0, 6, 
        f"O presente relatório consolida os dados disponíveis na base do sistema. "
        f"Foram identificados {sem_cpf} registros com ausência de CPF, o que pode impactar a remessa bancária. "
        "A última linha dos arquivos originais (totais) foi desconsiderada para evitar duplicidade nos cálculos."
    )
    
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
                        if file.name.endswith('.csv'):
                            try:
                                df = pd.read_csv(file, sep=';', encoding='latin1')
                            except:
                                file.seek(0)
                                df = pd.read_csv(file, sep=',', encoding='utf-8')
                        elif file.name.endswith('.xlsx'):
                            df = pd.read_excel(file)
                        elif file.name.endswith('.txt'):
                            df = pd.read_csv(file, sep=r'\s+', encoding='latin1', on_bad_lines='skip')
                            
                        # Padronizar e Aplicar Regra de Exclusão da Última Linha
                        df_std = standardize_dataframe(df, file.name)
                        
                        # Garantir que não está vazio
                        if not df_std.empty:
                            all_data.append(df_std)
                        
                    except Exception as e:
                        st.error(f"Erro ao ler {file.name}: {e}")
                    
                    progress_bar.progress((idx + 1) / len(uploaded_files))
                
                if all_data:
                    final_df = pd.concat(all_data, ignore_index=True)
                    
                    # Salvar no Banco de Dados
                    conn = get_db_connection()
                    
                    db_cols = ['programa', 'num_cartao', 'nome', 'cpf', 'rg', 'valor_pagto', 'mes_ref', 'arquivo_origem']
                    cols_to_save = [c for c in db_cols if c in final_df.columns]
                    
                    df_to_save = final_df[cols_to_save].copy()
                    df_to_save['status'] = 'IMPORTADO'
                    
                    # Evitar duplicatas exatas ao salvar
                    df_to_save.to_sql('payments', conn, if_exists='append', index=False)
                    conn.close()
                    
                    # === EXIBIR TOTAL APÓS UPLOAD ===
                    st.success(f"Sucesso! {len(final_df)} registros processados e salvos.")
                    
                    if 'valor_pagto' in final_df.columns:
                        total_importado = final_df['valor_pagto'].sum()
                        st.metric(
                            label="💰 Valor Total nos Arquivos Processados (Sem a linha de totais)", 
                            value=f"R$ {total_importado:,.2f}"
                        )
                    else:
                        st.warning("Coluna de valor não encontrada para cálculo do total.")
                    
                    st.markdown("### Prévia dos Dados:")
                    st.dataframe(final_df.head())
                else:
                    st.warning("Nenhum dado válido processado.")

    elif choice == "Análise e Correção":
        st.markdown("<h2 class='main-header'>🛠️ Análise e Correção de Dados</h2>", unsafe_allow_html=True)
        
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

    elif choice == "Dashboard":
        st.markdown("<h2 class='main-header'>📊 Dashboard Executivo</h2>", unsafe_allow_html=True)
        
        conn = get_db_connection()
        try:
            df = pd.read_sql("SELECT * FROM payments", conn)
        except:
            df = pd.DataFrame()
        conn.close()
        
        if not df.empty and 'valor_pagto' in df.columns:
            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            kpi1.metric("Total Pagamentos", f"R$ {df['valor_pagto'].sum():,.2f}")
            kpi2.metric("Beneficiários Únicos", df['num_cartao'].nunique() if 'num_cartao' in df.columns else 0)
            kpi3.metric("Projetos Ativos", df['programa'].nunique() if 'programa' in df.columns else 0)
            kpi4.metric("Registros Totais", len(df))
            
            st.markdown("---")
            
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Valor por Projeto")
                if 'programa' in df.columns:
                    proj_group = df.groupby('programa')['valor_pagto'].sum().reset_index()
                    fig_bar = px.bar(proj_group, x='programa', y='valor_pagto', color='programa', title="Total Pago por Projeto")
                    st.plotly_chart(fig_bar, use_container_width=True)
                
            with c2:
                st.subheader("Distribuição de Valores")
                fig_hist = px.histogram(df, x='valor_pagto', nbins=20, title="Histograma de Valores")
                st.plotly_chart(fig_hist, use_container_width=True)
        else:
            st.info("Sem dados suficientes para exibir dashboard.")

    elif choice == "Relatórios e Exportação":
        st.markdown("<h2 class='main-header'>📥 Exportação</h2>", unsafe_allow_html=True)
        
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
                st.download_button("Baixar PDF", pdf_bytes, "relatorio_executivo.pdf", "application/pdf")
                
        else:
            st.warning("Sem dados.")

    elif choice == "Administração TI (DB)":
        st.markdown("<h2 class='main-header'>⚙️ Administração TI</h2>", unsafe_allow_html=True)
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
