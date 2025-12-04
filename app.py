import streamlit as st
import pandas as pd
import io
import unicodedata
import re

# --- Configuração da Página ---
st.set_page_config(
    page_title="Sistema POT - Processamento de Pagamentos", 
    page_icon="💰",
    layout="wide"
)

# --- CSS Personalizado ---
st.markdown("""
    <style>
    .stMetric {
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 5px;
        border: 1px solid #e0e0e0;
    }
    .css-1d391kg {
        padding-top: 1rem;
    }
    </style>
    """, unsafe_allow_html=True)

# --- GESTÃO DE ESTADO (SESSÃO) ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_role' not in st.session_state:
    st.session_state.user_role = None
if 'df_consolidado' not in st.session_state:
    st.session_state.df_consolidado = None

# --- FUNÇÕES DE LOGIN ---

def check_login(username, password):
    users = {
        "admin": ("admin123", "Administrador"),
        "operador": ("operador123", "Operador"),
        "admin.ti@prefeitura.sp.gov.br": ("smdet2025", "Administrador")
    }
    if username in users and users[username][0] == password:
        st.session_state.authenticated = True
        st.session_state.user_role = users[username][1]
        st.session_state.username = username
        return True
    return False

def logout():
    st.session_state.authenticated = False
    st.session_state.user_role = None
    st.session_state.username = None
    st.session_state.df_consolidado = None # Limpa dados ao sair
    st.rerun()

# --- FUNÇÕES DE LIMPEZA E PADRONIZAÇÃO ---

def remover_acentos(texto):
    if not isinstance(texto, str): return str(texto)
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')

def sanitizar_texto(texto):
    if pd.isna(texto): return ""
    texto = str(texto).strip()
    try:
        texto = texto.encode('cp1252').decode('utf-8')
    except:
        pass
    texto = " ".join(texto.split())
    return texto.title()

def limpar_string_coluna(coluna):
    coluna = remover_acentos(coluna.lower().strip())
    coluna = re.sub(r'[^a-z0-9]', '', coluna)
    return coluna

def limpar_valor_monetario(valor):
    if isinstance(valor, (pd.Series, list, tuple)): return 0.0
    if pd.isna(valor): return 0.0
    valor_str = str(valor).strip().lower().replace('r$', '').strip()
    if not valor_str: return 0.0
    try:
        valor_str = valor_str.replace('.', '').replace(',', '.')
        return float(valor_str)
    except ValueError:
        return 0.0

def normalizar_cabecalhos(df):
    df.columns = df.columns.str.strip()
    mapa_colunas = {
        'Num Cartao': ['numcartao', 'nrocartao', 'numerocartao', 'cartao', 'card', 'nrcartao', 'num'],
        'Nome': ['nome', 'beneficiario', 'favorecido', 'funcionario', 'nomedobeneficiario'],
        'CPF': ['cpf', 'cpfbeneficiario', 'doc', 'documento'],
        'Valor': ['valor', 'valorpagto', 'valorliquido', 'valortotal', 'total', 'liquido', 'vlrliquido'],
        'Data': ['data', 'dtpagto', 'datapagto', 'datamovimento'],
        'Gerenciadora': ['gerenciadora', 'banco', 'origem', 'rede']
    }
    
    colunas_renomeadas = {}
    colunas_originais = list(df.columns)
    
    for col_atual in colunas_originais:
        col_clean = limpar_string_coluna(col_atual)
        match_encontrado = False
        for col_padrao, termos_chave in mapa_colunas.items():
            if match_encontrado: break
            for termo in termos_chave:
                if termo in col_clean:
                    colunas_renomeadas[col_atual] = col_padrao
                    match_encontrado = True
                    break
    
    if colunas_renomeadas:
        df = df.rename(columns=colunas_renomeadas)
    
    # Remove duplicadas (ex: se tiver Valor Bruto e Liquido e ambos virarem Valor)
    df = df.loc[:, ~df.columns.duplicated()]
    return df, colunas_renomeadas

def carregar_arquivo(uploaded_file):
    filename = uploaded_file.name.lower()
    try:
        if filename.endswith('.csv'):
            try: return pd.read_csv(uploaded_file, sep=';', encoding='utf-8', dtype=str)
            except: 
                uploaded_file.seek(0)
                try: return pd.read_csv(uploaded_file, sep=';', encoding='latin-1', dtype=str)
                except:
                    uploaded_file.seek(0)
                    return pd.read_csv(uploaded_file, sep=',', encoding='utf-8', dtype=str)
        else:
            return pd.read_excel(uploaded_file, dtype=str)
    except Exception as e:
        raise Exception(f"Erro de leitura: {str(e)}")

def processar_dados(uploaded_file):
    try:
        df = carregar_arquivo(uploaded_file)
        df, mudancas = normalizar_cabecalhos(df)
        
        colunas_obrigatorias = ['Num Cartao', 'Nome', 'Valor']
        faltantes = [c for c in colunas_obrigatorias if c not in df.columns]
        
        if faltantes:
            return None, f"Colunas ausentes: {', '.join(faltantes)}", mudancas
        
        df['Valor'] = df['Valor'].apply(limpar_valor_monetario)
        df['Num Cartao'] = df['Num Cartao'].astype(str).str.replace(r'\D', '', regex=True)
        df['Nome'] = df['Nome'].apply(sanitizar_texto)
        if 'Gerenciadora' in df.columns:
            df['Gerenciadora'] = df['Gerenciadora'].apply(sanitizar_texto)
        
        df['Arquivo Origem'] = uploaded_file.name
        
        cols_finais = ['Arquivo Origem', 'Num Cartao', 'Nome', 'Valor']
        opcionais = ['CPF', 'Data', 'Gerenciadora']
        for col in opcionais:
            if col in df.columns: cols_finais.append(col)
        
        return df[cols_finais], None, mudancas
    except Exception as e:
        return None, f"Erro: {str(e)}", {}

# --- INTERFACE PRINCIPAL ---

if not st.session_state.authenticated:
    # --- TELA DE LOGIN ---
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🔒 Sistema POT")
        st.info("Acesso Restrito - Folha de Pagamento")
        with st.form("login_form"):
            username = st.text_input("Usuário")
            password = st.text_input("Senha", type="password")
            submit = st.form_submit_button("Entrar", use_container_width=True)
            if submit:
                if check_login(username, password):
                    st.rerun()
                else:
                    st.error("Credenciais inválidas.")

else:
    # --- ÁREA LOGADA ---
    
    # Menu Lateral
    with st.sidebar:
        st.title(f"👤 {st.session_state.user_role}")
        st.caption(f"Logado como: {st.session_state.username}")
        
        st.divider()
        menu_opcao = st.radio(
            "Navegação", 
            ["📂 Upload & Consolidação", "📊 Dashboard Financeiro", "⚙️ Configurações"]
        )
        st.divider()
        if st.button("Sair do Sistema", use_container_width=True):
            logout()

    # --- PÁGINA 1: UPLOAD & CONSOLIDAÇÃO ---
    if menu_opcao == "📂 Upload & Consolidação":
        st.title("📂 Processamento de Arquivos")
        st.markdown("Faça o upload das planilhas para padronização e consolidação.")
        
        uploaded_files = st.file_uploader(
            "Selecione arquivos CSV ou Excel", 
            accept_multiple_files=True,
            type=['csv', 'xlsx', 'xls']
        )
        
        if uploaded_files:
            if st.button("Processar Arquivos", type="primary"):
                dfs_validos = []
                bar = st.progress(0)
                
                for i, arquivo in enumerate(uploaded_files):
                    df_proc, erro, mudancas = processar_dados(arquivo)
                    
                    if erro:
                        st.error(f"❌ {arquivo.name}: {erro}")
                    else:
                        dfs_validos.append(df_proc)
                        with st.expander(f"✅ {arquivo.name} - Processado com sucesso"):
                            c1, c2 = st.columns(2)
                            c1.info(f"Colunas detectadas: {len(df_proc.columns)}")
                            c2.metric("Total do Arquivo", f"R$ {df_proc['Valor'].sum():,.2f}")
                            if mudancas:
                                st.caption(f"Adaptações: {mudancas}")
                    
                    bar.progress((i + 1) / len(uploaded_files))
                
                if dfs_validos:
                    df_final = pd.concat(dfs_validos, ignore_index=True)
                    st.session_state.df_consolidado = df_final # Salva na sessão
                    st.success("Processamento concluído! Vá para o Dashboard para ver os resultados.")
                    st.balloons()
        
        # Mostra prévia se já houver dados processados
        if st.session_state.df_consolidado is not None:
            st.divider()
            st.subheader("Prévia dos Dados Consolidados")
            st.dataframe(st.session_state.df_consolidado.head(10), use_container_width=True)
            st.info(f"Total de {len(st.session_state.df_consolidado)} registros carregados em memória.")

    # --- PÁGINA 2: DASHBOARD ---
    elif menu_opcao == "📊 Dashboard Financeiro":
        st.title("📊 Dashboard Financeiro")
        
        if st.session_state.df_consolidado is None:
            st.warning("⚠️ Nenhum dado carregado. Vá para a aba 'Upload & Consolidação' primeiro.")
        else:
            df = st.session_state.df_consolidado
            
            # KPI Cards
            col1, col2, col3, col4 = st.columns(4)
            
            valor_total = df['Valor'].sum()
            qtd_beneficiarios = df['Num Cartao'].nunique()
            qtd_registros = len(df)
            media_pgto = valor_total / qtd_registros if qtd_registros > 0 else 0
            
            col1.metric("Valor Total da Folha", f"R$ {valor_total:,.2f}")
            col2.metric("Beneficiários Únicos", qtd_beneficiarios)
            col3.metric("Total de Registros", qtd_registros)
            col4.metric("Ticket Médio", f"R$ {media_pgto:,.2f}")
            
            st.divider()
            
            # Gráficos e Tabelas
            c_chart, c_table = st.columns([2, 1])
            
            with c_chart:
                st.subheader("Distribuição por Arquivo de Origem")
                df_grouped = df.groupby('Arquivo Origem')['Valor'].sum().reset_index()
                st.bar_chart(df_grouped, x='Arquivo Origem', y='Valor', color='#0068c9')
            
            with c_table:
                st.subheader("Resumo por Arquivo")
                st.dataframe(
                    df.groupby('Arquivo Origem').agg(
                        Qtd=('Num Cartao', 'count'),
                        Total=('Valor', 'sum')
                    ).style.format({'Total': 'R$ {:,.2f}'}),
                    use_container_width=True
                )

            # Área de Download
            st.divider()
            st.subheader("📥 Exportação de Dados")
            
            df_export = df.copy()
            # Formata para Excel BR
            df_export['Valor'] = df_export['Valor'].apply(lambda x: f"{x:.2f}".replace('.', ','))
            csv = df_export.to_csv(index=False, sep=';', encoding='utf-8-sig')
            
            st.download_button(
                label="Baixar Relatório Completo (.csv)",
                data=csv,
                file_name="relatorio_pagamentos_consolidado.csv",
                mime="text/csv",
                type="primary"
            )

    # --- PÁGINA 3: CONFIGURAÇÕES (Placeholder) ---
    elif menu_opcao == "⚙️ Configurações":
        st.title("⚙️ Configurações do Sistema")
        st.info("Funcionalidades de administração de usuários e logs seriam implementadas aqui.")
        st.text_input("Email para relatórios automáticos")
        st.button("Salvar Preferências")
