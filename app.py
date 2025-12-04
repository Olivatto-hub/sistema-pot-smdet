import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import time

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Gestão de Pagamentos - Programa Operação Trabalho",
    page_icon="💼",
    layout="wide"
)

# --- INICIALIZAÇÃO DO ESTADO (SESSION STATE) ---
if 'df_pagamentos' not in st.session_state:
    st.session_state['df_pagamentos'] = pd.DataFrame()

# --- FUNÇÕES DE LIMPEZA E FORMATAÇÃO ---
def clean_currency(value):
    """
    Remove R$, espaços e converte formato BR (1.000,00) para float (1000.00).
    """
    if isinstance(value, (int, float, np.number)):
        return float(value)
    if isinstance(value, str):
        clean_str = value.replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
        try:
            return float(clean_str)
        except ValueError:
            return 0.0
    return 0.0

def format_brl(value):
    """Formata float para moeda BRL visual."""
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# --- GERAÇÃO DE DADOS (SIMULAÇÃO) ---
def generate_mock_data():
    """
    Gera um dataset simulando o arquivo mestre do Programa Operação Trabalho.
    Contém 2054 registros, múltiplos projetos e casos de teste para a regra de R$ 5k.
    """
    np.random.seed(42) # Semente para reprodutibilidade
    n_rows = 2054
    
    projetos = [
        "POT - Redenção", "POT - Oportunidades", "POT - Zeladoria", 
        "POT - Horta", "POT - Mães Guardiãs"
    ]
    
    # Geração de Cartões (Beneficiários Únicos)
    unique_cards = np.random.randint(1000000000, 9999999999, size=1800, dtype=np.int64)
    cards_column = np.random.choice(unique_cards, size=n_rows)
    
    # Valores de Pagamento
    base_values = [600.00, 850.00, 920.00, 1200.00, 1500.00]
    values_column = np.random.choice(base_values, size=n_rows).astype(float)
    
    noise = np.random.random(size=n_rows) * 10 
    values_column += noise
    
    # Casos de Teste (Regra > 5k)
    cards_column[0] = 1234567890
    values_column[0] = 5500.00 
    
    cards_column[1:4] = 9876543210
    values_column[1] = 2000.00
    values_column[2] = 2000.00
    values_column[3] = 1500.00 
    
    df = pd.DataFrame({
        "Num Cartao": cards_column,
        "Nome Beneficiário": [f"Beneficiário {i}" for i in range(n_rows)],
        "Projeto Origem": np.random.choice(projetos, size=n_rows),
        "Valor Pagto": values_column,
        "Data Processamento": pd.date_range(start="2023-10-01", periods=n_rows, freq="T"),
        "Status Planilha": "Importado"
    })
    
    df["Num Cartao"] = df["Num Cartao"].astype(str)
    return df

def load_from_file(uploaded_file):
    """Carrega e normaliza arquivo real enviado pelo usuário"""
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        
        # Tentativa de normalizar colunas caso venham com nomes diferentes
        cols_map = {c.lower(): c for c in df.columns}
        rename_dict = {}
        
        if 'num cartao' not in df.columns:
            # Procura variantes
            for key in cols_map:
                if 'cartao' in key or 'cartão' in key:
                    rename_dict[cols_map[key]] = 'Num Cartao'
                    break
        
        if 'valor pagto' not in df.columns:
            for key in cols_map:
                if 'valor' in key:
                    rename_dict[cols_map[key]] = 'Valor Pagto'
                    break
                    
        df = df.rename(columns=rename_dict)
        
        # Força conversão de Num Cartao para string para agrupar corretamente
        if 'Num Cartao' in df.columns:
            df['Num Cartao'] = df['Num Cartao'].astype(str)
            
        return df
    except Exception as e:
        st.error(f"Erro ao ler arquivo: {e}")
        return pd.DataFrame()

# --- LÓGICA DE NEGÓCIO ---
def process_business_rules(df, threshold=5000.00):
    if df.empty:
        return df

    # Limpeza/Conversão do Valor
    # Verifica se a coluna é object/string e limpa, senão usa direto
    if df['Valor Pagto'].dtype == 'object':
        df['Valor_Calculo'] = df['Valor Pagto'].apply(clean_currency)
    else:
        df['Valor_Calculo'] = df['Valor Pagto']

    # 1. Agrupamento por Cartão
    grouped = df.groupby('Num Cartao')['Valor_Calculo'].sum().reset_index()
    grouped.rename(columns={'Valor_Calculo': 'Soma_Total_Cartao'}, inplace=True)
    
    # 2. Status
    grouped['Status_Validacao'] = grouped['Soma_Total_Cartao'].apply(
        lambda x: '⚠️ Análise Admin' if x > threshold else '✅ Liberado'
    )
    
    # 3. Merge
    df_final = df.merge(grouped[['Num Cartao', 'Soma_Total_Cartao', 'Status_Validacao']], on='Num Cartao', how='left')
    
    return df_final

# --- SIDEBAR ---
st.sidebar.title("🔧 Painel de Controle")

st.sidebar.markdown("### 1. Fonte de Dados")
uploaded_file = st.sidebar.file_uploader("📂 Carregar Arquivo (.xlsx, .csv)", type=['xlsx', 'csv'])

if st.sidebar.button("🎲 Usar Dados de Teste (Simulação)"):
    st.session_state['df_pagamentos'] = generate_mock_data()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("### 2. Regras e Ações")
limite_teto = st.sidebar.number_input(
    "Teto Máximo por Cartão (R$)",
    value=5000.00,
    step=100.00
)

# Botão de Limpeza com Lógica de Session State
if st.sidebar.button("🗑️ Limpar Banco de Dados (Admin)", type="primary"):
    st.session_state['df_pagamentos'] = pd.DataFrame()
    st.cache_data.clear()
    st.rerun()

# --- PROCESSAMENTO DO UPLOAD ---
# Se o usuário subiu um arquivo, ele tem prioridade sobre o estado atual
if uploaded_file is not None:
    # Só carrega se o dataframe estiver vazio ou se o arquivo mudou
    # (Streamlit reloda o script a cada interação, então carregamos e salvamos no state)
    df_loaded = load_from_file(uploaded_file)
    if not df_loaded.empty:
        st.session_state['df_pagamentos'] = df_loaded

# --- APP PRINCIPAL ---

st.title("Sistema de Gestão Financeira - POT")

# Verifica se há dados no estado
df_raw = st.session_state['df_pagamentos']

if df_raw.empty:
    # TELA DE ESPERA / ESTADO VAZIO
    st.info("""
        ℹ️ **Sistema Aguardando Dados**
        
        Utilize o menu lateral para:
        1. **Carregar um arquivo real** (Excel ou CSV) com as colunas 'Num Cartao' e 'Valor Pagto'.
        2. Ou clique em **'Usar Dados de Teste'** para gerar uma simulação de 2054 registros.
    """)
    
    # Mostra um placeholder visual
    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    with c2:
        st.markdown("### 🚫 Nenhum dado carregado")

else:
    # TELA DE DASHBOARD (SÓ APARECE SE TIVER DADOS)
    
    # Processamento
    try:
        df_processed = process_business_rules(df_raw, threshold=limite_teto)
        
        # Separação
        df_analise = df_processed[df_processed['Status_Validacao'] == '⚠️ Análise Admin']
        
        # 2. DASHBOARD (KPIs)
        col1, col2, col3, col4 = st.columns(4)
        
        total_valor = df_processed['Valor_Calculo'].sum()
        total_analise = df_analise['Valor_Calculo'].sum()
        
        with col1:
            st.metric("Total de Registros", len(df_processed))
        with col2:
            st.metric("Valor Total da Folha", format_brl(total_valor))
        with col3:
            st.metric("Cartões Únicos", df_processed['Num Cartao'].nunique())
        with col4:
            st.metric("Retido para Validação", format_brl(total_analise), delta_color="inverse")
            
        st.markdown("---")
        
        # 3. ALERTAS
        if not df_analise.empty:
            st.error(f"🚨 **Atenção:** {df_analise['Num Cartao'].nunique()} cartões excederam o teto de R$ {limite_teto:,.2f} (Soma acumulada).")
            with st.expander("Ver Detalhes da Malha Fina"):
                st.dataframe(
                    df_analise[['Num Cartao', 'Nome Beneficiário', 'Valor Pagto', 'Soma_Total_Cartao']]
                    .sort_values(by='Soma_Total_Cartao', ascending=False),
                    use_container_width=True
                )
        else:
            st.success("✅ Nenhum pagamento excedeu o limite acumulado por cartão.")
            
        # 4. GRÁFICOS
        tab1, tab2 = st.tabs(["📊 Visão Gráfica", "📋 Dados Brutos"])
        
        with tab1:
            c1, c2 = st.columns(2)
            if 'Projeto Origem' in df_processed.columns:
                with c1:
                    fig = px.bar(df_processed.groupby("Projeto Origem")['Valor_Calculo'].sum().reset_index(), 
                                x="Projeto Origem", y="Valor_Calculo", title="Por Projeto")
                    st.plotly_chart(fig, use_container_width=True)
            
            with c2:
                fig2 = px.pie(df_processed, names='Status_Validacao', title="Status da Validação")
                st.plotly_chart(fig2, use_container_width=True)
                
        with tab2:
            st.dataframe(df_processed, use_container_width=True)
            
    except KeyError as e:
        st.error(f"Erro de Estrutura: O arquivo carregado não possui as colunas esperadas. ({str(e)})")
        st.warning("Certifique-se que o arquivo tem as colunas 'Num Cartao' e 'Valor Pagto'.")
