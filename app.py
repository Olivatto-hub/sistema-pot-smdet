import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import time

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Sistema Integrado de Gestão - POT",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS PERSONALIZADO ---
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        color: #1E3D59;
        font-weight: bold;
    }
    .sub-header {
        font-size: 1.5rem;
        color: #1E3D59;
    }
    .metric-container {
        background-color: #F0F2F6;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #E0E0E0;
    }
    div.stButton > button:first-child {
        background-color: #1E3D59;
        color: white;
        border-radius: 5px;
    }
    div.stButton > button:hover {
        background-color: #155a8a;
    }
</style>
""", unsafe_allow_html=True)

# --- INICIALIZAÇÃO DO ESTADO ---
if 'df_pagamentos' not in st.session_state:
    st.session_state['df_pagamentos'] = pd.DataFrame()

# --- FUNÇÕES AUXILIARES ---
def clean_currency(value):
    """Converte valores monetários (R$ 1.000,00) para float (1000.00)."""
    if isinstance(value, (int, float, np.number)):
        return float(value)
    if isinstance(value, str):
        clean = value.replace('R$', '').replace(' ', '').strip()
        if ',' in clean and '.' in clean:
            clean = clean.replace('.', '').replace(',', '.')
        elif ',' in clean:
            clean = clean.replace(',', '.')
        try:
            return float(clean)
        except ValueError:
            return 0.0
    return 0.0

def format_brl(value):
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def load_from_file(uploaded_file):
    """Carrega arquivo, detecta encoding e normaliza colunas."""
    df = pd.DataFrame()
    try:
        if uploaded_file.name.endswith('.csv'):
            try:
                df = pd.read_csv(uploaded_file)
            except UnicodeDecodeError:
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file, encoding='latin-1', sep=';')
        else:
            df = pd.read_excel(uploaded_file)
        
        # Normalização de Colunas
        df.columns = [str(c).strip() for c in df.columns]
        
        # Mapeamento de Colunas Inteligente
        cols_map = {c.lower(): c for c in df.columns}
        rename_dict = {}
        
        # Tentativa de identificar colunas chave
        for key, original in cols_map.items():
            if 'cartao' in key or 'cartão' in key or 'conta' in key:
                rename_dict[original] = 'Num Cartao'
            elif 'valor' in key or 'liquido' in key:
                rename_dict[original] = 'Valor Pagto'
            elif 'nome' in key or 'beneficiario' in key:
                rename_dict[original] = 'Nome Beneficiário'
                
        df = df.rename(columns=rename_dict)
        
        # Validação
        if 'Num Cartao' not in df.columns or 'Valor Pagto' not in df.columns:
            st.error("Erro: Arquivo deve conter colunas de 'Cartão' e 'Valor'.")
            return pd.DataFrame()
            
        # Limpeza de Linhas de Total/Lixo
        df['Num Cartao'] = df['Num Cartao'].astype(str).str.strip()
        invalid_tokens = ['nan', 'none', '', 'nat', 'total', 'soma']
        df = df[~df['Num Cartao'].str.lower().isin(invalid_tokens)]
        df = df[~df['Num Cartao'].str.lower().str.contains('total', na=False)]
        
        return df
    except Exception as e:
        st.error(f"Erro ao processar arquivo: {e}")
        return pd.DataFrame()

def generate_mock_data():
    """Gera dados simulados para teste do sistema."""
    np.random.seed(42)
    n_rows = 2054
    projetos = ["POT - Redenção", "POT - Oportunidades", "POT - Zeladoria", "POT - Mães Guardiãs"]
    
    unique_cards = np.random.randint(1000000000, 9999999999, size=1800, dtype=np.int64)
    cards = np.random.choice(unique_cards, size=n_rows)
    values = np.random.choice([600.0, 850.0, 920.0, 1200.0, 1500.0], size=n_rows)
    values += np.random.random(size=n_rows) * 10
    
    # Inserção de Casos de Borda (Teto e Duplicidade)
    values[0] = 5500.00 # Acima do teto
    values[1] = 4900.00 # Próximo ao teto
    
    # Duplicidade para teste
    cards[2:5] = 9876543210
    values[2:5] = 2000.00
    
    df = pd.DataFrame({
        "Num Cartao": cards,
        "Nome Beneficiário": [f"Beneficiário {i}" for i in range(n_rows)],
        "Projeto Origem": np.random.choice(projetos, size=n_rows),
        "Valor Pagto": values,
        "Data Processamento": pd.date_range("2023-10-01", periods=n_rows, freq="T"),
        "Status Planilha": "Importado"
    })
    return df

def process_data(df, teto):
    """Aplica regras de negócio e validações."""
    if df.empty: return df
    
    # Tratamento de Valor
    if df['Valor Pagto'].dtype == 'object':
        df['Valor_Calculo'] = df['Valor Pagto'].apply(clean_currency)
    else:
        df['Valor_Calculo'] = pd.to_numeric(df['Valor Pagto'], errors='coerce').fillna(0.0)
        
    # Regra de Teto (Correção solicitada: Validação por item)
    df['Status_Validacao'] = df['Valor_Calculo'].apply(
        lambda x: '⚠️ Análise Admin' if x > teto else '✅ Liberado'
    )
    
    # Cálculo de Acumulado por Cartão (Informativo)
    grouped = df.groupby('Num Cartao')['Valor_Calculo'].sum().reset_index()
    grouped.rename(columns={'Valor_Calculo': 'Info_Total_Acumulado'}, inplace=True)
    df = df.merge(grouped, on='Num Cartao', how='left')
    
    return df

# --- LAYOUT PRINCIPAL ---

st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=60)
st.sidebar.title("SMDET - POT")
st.sidebar.write("Gestão de Benefícios")
st.sidebar.markdown("---")

# Menu Sidebar
uploaded_file = st.sidebar.file_uploader("📂 Importar Arquivo Mestre", type=['xlsx', 'csv'])
usar_mock = st.sidebar.button("🎲 Carregar Dados de Simulação")
st.sidebar.markdown("---")
teto_maximo = st.sidebar.number_input("Teto Máximo (R$)", value=5000.00, step=100.00)
limpar_dados = st.sidebar.button("🗑️ Limpar Sistema")

if limpar_dados:
    st.session_state['df_pagamentos'] = pd.DataFrame()
    st.rerun()

if usar_mock:
    st.session_state['df_pagamentos'] = generate_mock_data()
    st.rerun()

if uploaded_file:
    df_new = load_from_file(uploaded_file)
    if not df_new.empty:
        st.session_state['df_pagamentos'] = df_new

# CORPO DA PÁGINA
st.markdown("<h1 class='main-header'>Sistema de Gestão Financeira - POT</h1>", unsafe_allow_html=True)
st.markdown("Painel de Controle e Auditoria de Folha de Pagamento")

df = st.session_state['df_pagamentos']

if not df.empty:
    # Processamento
    df_proc = process_data(df, teto_maximo)
    
    # Filtros de Auditoria
    df_retidos = df_proc[df_proc['Status_Validacao'] == '⚠️ Análise Admin']
    duplicados = df_proc[df_proc.duplicated(subset=['Num Cartao'], keep=False)]
    has_duplicados = not duplicados.empty
    
    # KPI Cards
    col1, col2, col3, col4 = st.columns(4)
    total_pgto = df_proc['Valor_Calculo'].sum()
    total_retido = df_retidos['Valor_Calculo'].sum()
    
    col1.metric("Total de Registros", len(df_proc))
    # Correção de Nomenclatura aplicada: Total de Pagamentos
    col2.metric("Total de Pagamentos", format_brl(total_pgto))
    # Correção de Nomenclatura aplicada: Contas Únicas
    col3.metric("Contas Únicas", df_proc['Num Cartao'].nunique())
    col4.metric("Volume em Análise", format_brl(total_retido), delta_color="inverse")
    
    st.divider()
    
    # Abas de Gestão
    tab1, tab2, tab3 = st.tabs(["📊 Dashboard & Auditoria", "⚠️ Malha Fina & Duplicidades", "📋 Base de Dados"])
    
    with tab1:
        c1, c2 = st.columns([2, 1])
        with c1:
            st.subheader("Distribuição por Projeto")
            if 'Projeto Origem' in df_proc.columns:
                fig_bar = px.bar(df_proc.groupby("Projeto Origem")['Valor_Calculo'].sum().reset_index(),
                                 x="Projeto Origem", y="Valor_Calculo", text_auto=True,
                                 color_discrete_sequence=['#1E3D59'])
                st.plotly_chart(fig_bar, use_container_width=True)
        with c2:
            st.subheader("Status da Validação")
            fig_pie = px.pie(df_proc, names='Status_Validacao', 
                             color='Status_Validacao',
                             color_discrete_map={'✅ Liberado': '#2ecc71', '⚠️ Análise Admin': '#e74c3c'})
            st.plotly_chart(fig_pie, use_container_width=True)
            
    with tab2:
        st.subheader("Central de Auditoria")
        
        # Auditoria de Teto (Valores individuais altos)
        if not df_retidos.empty:
            st.error(f"🚨 **Teto Excedido:** {len(df_retidos)} pagamentos ultrapassam R$ {teto_maximo:,.2f}")
            st.dataframe(
                df_retidos[['Num Cartao', 'Nome Beneficiário', 'Valor_Calculo', 'Info_Total_Acumulado']].sort_values('Valor_Calculo', ascending=False),
                column_config={
                    "Valor_Calculo": st.column_config.NumberColumn("Valor Pagamento", format="R$ %.2f"),
                    "Info_Total_Acumulado": st.column_config.NumberColumn("Total no Cartão", format="R$ %.2f")
                }, use_container_width=True
            )
        else:
            st.success("✅ Nenhum pagamento individual excede o teto estipulado.")
            
        st.divider()
        
        # Auditoria de Duplicidade (Contas recebendo mais de uma vez)
        if has_duplicados:
            st.warning(f"⚠️ **Duplicidade Detectada:** {duplicados['Num Cartao'].nunique()} contas receberam múltiplos pagamentos.")
            st.dataframe(
                duplicados[['Num Cartao', 'Nome Beneficiário', 'Projeto Origem', 'Valor_Calculo']].sort_values('Num Cartao'),
                column_config={"Valor_Calculo": st.column_config.NumberColumn("Valor", format="R$ %.2f")},
                use_container_width=True
            )
        else:
            st.success("✅ Não foram encontradas duplicidades de contas na folha.")

    with tab3:
        st.subheader("Base de Dados Completa")
        st.dataframe(df_proc, use_container_width=True)
        
        csv = df_proc.to_csv(index=False).encode('utf-8')
        st.download_button("⬇️ Exportar Relatório (CSV)", data=csv, file_name="relatorio_auditoria_pot.csv", mime="text/csv")

else:
    st.info("Aguardando importação de dados para iniciar a auditoria.")
