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
    }
    .stAlert {
        padding: 10px;
        border-radius: 5px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- GESTÃO DE SESSÃO E LOGIN ---

if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_role' not in st.session_state:
    st.session_state.user_role = None

def check_login(username, password):
    # Credenciais simples (em produção, usar banco de dados ou env vars)
    users = {
        "admin": ("admin123", "Administrador"),
        "operador": ("operador123", "Operador"),
        "admin.ti@prefeitura.sp.gov.br": ("smdet2025", "Administrador")
    }
    
    # Verifica credenciais diretas
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
    st.rerun()

# --- FUNÇÕES DE LIMPEZA E PADRONIZAÇÃO ---

def remover_acentos(texto):
    """Remove acentos e caracteres especiais para normalização de chaves."""
    if not isinstance(texto, str):
        return str(texto)
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')

def sanitizar_texto(texto):
    """
    Limpa caracteres estranhos visualmente (ex: Ã£ -> ã) e espaços extras.
    Útil para nomes de beneficiários e gerenciadoras.
    """
    if pd.isna(texto):
        return ""
    
    texto = str(texto).strip()
    
    # Tenta corrigir problemas comuns de encoding (UTF-8 lido como Latin-1)
    try:
        texto = texto.encode('cp1252').decode('utf-8')
    except:
        pass # Se falhar, mantém o original
        
    # Remove caracteres de controle e espaços extras
    texto = " ".join(texto.split())
    
    # Converte para Title Case (primeira letra maiúscula)
    return texto.title()

def limpar_string_coluna(coluna):
    """Padroniza nome da coluna para comparação (minusculo, sem acento/espaço)."""
    coluna = remover_acentos(coluna.lower().strip())
    coluna = re.sub(r'[^a-z0-9]', '', coluna)
    return coluna

def limpar_valor_monetario(valor):
    """
    Converte strings de dinheiro (R$ 1.500,00) para float (1500.00).
    Robusto contra erros de tipo.
    """
    # Proteção contra Series/Listas passadas por engano (Causa do erro ValueError anterior)
    if isinstance(valor, (pd.Series, list, tuple)):
        return 0.0
        
    if pd.isna(valor):
        return 0.0
    
    valor_str = str(valor).strip()
    valor_str = valor_str.lower().replace('r$', '').strip()
    
    if not valor_str:
        return 0.0
        
    try:
        # Formato PT-BR: remove ponto milhar, troca vírgula decimal
        valor_str = valor_str.replace('.', '').replace(',', '.')
        return float(valor_str)
    except ValueError:
        return 0.0

def normalizar_cabecalhos(df):
    """
    Renomeia colunas e remove duplicatas para evitar erros de processamento.
    """
    df.columns = df.columns.str.strip()
    
    mapa_colunas = {
        'Num Cartao': ['numcartao', 'nrocartao', 'numerocartao', 'cartao', 'card', 'nrcartao', 'num'],
        'Nome': ['nome', 'beneficiario', 'favorecido', 'funcionario', 'nomedobeneficiario', 'nomefavorecido'],
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
    
    # 1. Renomear
    if colunas_renomeadas:
        df = df.rename(columns=colunas_renomeadas)
    
    # 2. CRÍTICO: Remover colunas duplicadas após renomear
    # (Ex: se tinha "Valor Bruto" e "Valor Liquido" e ambos viraram "Valor", mantém só o primeiro)
    df = df.loc[:, ~df.columns.duplicated()]
        
    return df, colunas_renomeadas

# --- PROCESSAMENTO DE ARQUIVOS ---

def carregar_arquivo(uploaded_file):
    filename = uploaded_file.name.lower()
    try:
        if filename.endswith('.csv'):
            try:
                return pd.read_csv(uploaded_file, sep=';', encoding='utf-8', dtype=str)
            except:
                uploaded_file.seek(0)
                try:
                    return pd.read_csv(uploaded_file, sep=';', encoding='latin-1', dtype=str)
                except:
                    uploaded_file.seek(0)
                    return pd.read_csv(uploaded_file, sep=',', encoding='utf-8', dtype=str)
        else:
            return pd.read_excel(uploaded_file, dtype=str)
    except Exception as e:
        raise Exception(f"Erro de leitura: {str(e)}")

def processar_dados(uploaded_file):
    try:
        # 1. Carregar
        df = carregar_arquivo(uploaded_file)
        
        # 2. Normalizar e Desduplicar Colunas
        df, mudancas = normalizar_cabecalhos(df)
        
        # 3. Validação
        colunas_obrigatorias = ['Num Cartao', 'Nome', 'Valor']
        faltantes = [c for c in colunas_obrigatorias if c not in df.columns]
        
        if faltantes:
            return None, f"Colunas não encontradas: {', '.join(faltantes)}", mudancas
        
        # 4. Limpezas Específicas
        
        # Valor Monetário
        df['Valor'] = df['Valor'].apply(limpar_valor_monetario)
        
        # Num Cartão (apenas dígitos)
        df['Num Cartao'] = df['Num Cartao'].astype(str).str.replace(r'\D', '', regex=True)
        
        # Sanitização de Texto (Nome e Gerenciadora) para corrigir caracteres estranhos
        df['Nome'] = df['Nome'].apply(sanitizar_texto)
        if 'Gerenciadora' in df.columns:
            df['Gerenciadora'] = df['Gerenciadora'].apply(sanitizar_texto)
            
        # Adicionar origem
        df['Arquivo Origem'] = uploaded_file.name
        
        # Seleção Final de Colunas
        cols_finais = ['Arquivo Origem', 'Num Cartao', 'Nome', 'Valor']
        opcionais = ['CPF', 'Data', 'Gerenciadora']
        for col in opcionais:
            if col in df.columns:
                cols_finais.append(col)
        
        return df[cols_finais], None, mudancas

    except Exception as e:
        # Captura erro genérico e retorna string amigável
        return None, f"Erro interno ao processar: {str(e)}", {}

# --- INTERFACE DO USUÁRIO ---

if not st.session_state.authenticated:
    # TELA DE LOGIN
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🔒 Sistema POT")
        st.subheader("Login de Acesso")
        
        with st.form("login_form"):
            username = st.text_input("Usuário")
            password = st.text_input("Senha", type="password")
            submit = st.form_submit_button("Entrar")
            
            if submit:
                if check_login(username, password):
                    st.rerun()
                else:
                    st.error("Usuário ou senha incorretos")
else:
    # TELA PRINCIPAL (LOGADO)
    st.sidebar.title(f"👤 {st.session_state.user_role}")
    st.sidebar.text(f"Usuário: {st.session_state.username}")
    if st.sidebar.button("Sair"):
        logout()
    
    st.sidebar.divider()
    
    st.title("📂 Consolidação de Pagamentos")
    
    # Upload apenas se logado
    uploaded_files = st.file_uploader(
        "Arraste seus arquivos (CSV/Excel) aqui", 
        accept_multiple_files=True,
        type=['csv', 'xlsx', 'xls']
    )
    
    if uploaded_files:
        dfs_validos = []
        
        st.divider()
        st.subheader("Processamento Individual")
        
        for arquivo in uploaded_files:
            with st.expander(f"📄 {arquivo.name}", expanded=True):
                df_proc, erro, mudancas = processar_dados(arquivo)
                
                if erro:
                    st.error(f"❌ Falha: {erro}")
                    # Debug: mostra cabeçalho original se possível
                    try:
                        arquivo.seek(0)
                        if arquivo.name.endswith('.csv'):
                            line = arquivo.readline().decode('latin-1')
                        else:
                            line = "Arquivo Excel (binário)"
                        st.caption(f"Cabeçalho bruto detectado: {line[:100]}...")
                    except:
                        pass
                else:
                    colA, colB = st.columns([3, 1])
                    with colA:
                        msg_cols = f"Colunas ajustadas: {mudancas}" if mudancas else "Colunas padrão identificadas."
                        st.success(f"✅ Sucesso! {msg_cols}")
                    with colB:
                        st.metric("Total", f"R$ {df_proc['Valor'].sum():,.2f}")
                    
                    st.dataframe(df_proc.head(3), use_container_width=True)
                    dfs_validos.append(df_proc)
        
        if dfs_validos:
            st.divider()
            st.header("📊 Relatório Consolidado")
            
            df_final = pd.concat(dfs_validos, ignore_index=True)
            
            # Métricas
            c1, c2, c3 = st.columns(3)
            c1.metric("Arquivos", len(dfs_validos))
            c2.metric("Beneficiários", len(df_final))
            c3.metric("Valor Total", f"R$ {df_final['Valor'].sum():,.2f}")
            
            # Visualização
            st.dataframe(df_final, use_container_width=True)
            
            # Exportação
            df_export = df_final.copy()
            df_export['Valor'] = df_export['Valor'].apply(lambda x: f"{x:.2f}".replace('.', ','))
            
            csv = df_export.to_csv(index=False, sep=';', encoding='utf-8-sig')
            
            st.download_button(
                label="⬇️ Baixar Consolidado (.csv)",
                data=csv,
                file_name="folha_pot_consolidada.csv",
                mime="text/csv",
                type="primary"
            )
    else:
        st.info("Aguardando arquivos para processamento...")
