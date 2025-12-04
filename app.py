import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import numpy as np

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Painel de Controle de Pagamentos",
    page_icon="💰",
    layout="wide"
)

# --- FUNÇÕES UTILITÁRIAS ---
def format_brl(value):
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# --- GERAÇÃO DE DADOS MOCK (SIMULAÇÃO DE ARQUIVOS) ---
# Em produção, isso seria substituído pela leitura real dos arquivos .REM ou Excel
@st.cache_data
def load_data():
    data = [
        # Arquivo 1 - Pagamentos Normais
        {"Arquivo": "ARQ_PAG_001.REM", "Beneficiário": "João Silva", "CPF": "123.456.789-00", "Valor Pagto": 1200.50, "Data": "2023-10-01"},
        {"Arquivo": "ARQ_PAG_001.REM", "Beneficiário": "Maria Oliveira", "CPF": "234.567.890-11", "Valor Pagto": 2500.00, "Data": "2023-10-01"},
        {"Arquivo": "ARQ_PAG_001.REM", "Beneficiário": "Transportes LTDA", "CPF": "12.345.678/0001-90", "Valor Pagto": 15800.00, "Data": "2023-10-01"},
        
        # Arquivo 2 - Contém um valor suspeito (fraude/delírio)
        {"Arquivo": "ARQ_PAG_002.REM", "Beneficiário": "Ana Santos", "CPF": "345.678.901-22", "Valor Pagto": 980.00, "Data": "2023-10-02"},
        {"Arquivo": "ARQ_PAG_002.REM", "Beneficiário": "GOLPE_DETECTADO_TESTE", "CPF": "000.000.000-00", "Valor Pagto": 5748240.96, "Data": "2023-10-02"}, # O valor alto que causava erro
        {"Arquivo": "ARQ_PAG_002.REM", "Beneficiário": "Carlos Souza", "CPF": "456.789.012-33", "Valor Pagto": 3200.10, "Data": "2023-10-02"},
        
        # Arquivo 3 - Pagamentos Recorrentes
        {"Arquivo": "ARQ_PAG_003.REM", "Beneficiário": "João Silva", "CPF": "123.456.789-00", "Valor Pagto": 1200.50, "Data": "2023-10-05"},
        {"Arquivo": "ARQ_PAG_003.REM", "Beneficiário": "Consultoria XYZ", "CPF": "98.765.432/0001-10", "Valor Pagto": 8500.00, "Data": "2023-10-05"},
    ]
    return pd.DataFrame(data)

# --- SIDEBAR E CONFIGURAÇÕES ---
st.sidebar.header("⚙️ Configurações de Controle")

# 1. Upload de Arquivos (Simulado)
uploaded_file = st.sidebar.file_uploader("Carregar Arquivo de Remessa (.REM/.CSV)", type=["csv", "txt", "rem"])

# Carrega os dados (simulados se não houver upload)
df_raw = load_data()

# 2. Filtro de Segurança (Anti-Fraude)
st.sidebar.markdown("---")
st.sidebar.subheader("🛡️ Segurança e Compliance")
limite_seguranca = st.sidebar.number_input(
    "Limite Máximo por Pagamento (R$)",
    min_value=0.0,
    value=20000.00, # Valor padrão seguro
    step=1000.00,
    help="Pagamentos acima deste valor serão segregados automaticamente para análise."
)

# 3. Área Admin TI
st.sidebar.markdown("---")
st.sidebar.subheader("🔧 Admin TI")
if st.sidebar.button("🗑️ Limpar Dados / Cache"):
    st.cache_data.clear()
    st.rerun()
    st.sidebar.success("Cache limpo com sucesso!")

# --- PROCESSAMENTO LÓGICO (CORE) ---

# Separar o joio do trigo
# df_aprovados: Pagamentos dentro do limite
# df_retidos: Pagamentos suspeitos/acima do limite
df_aprovados = df_raw[df_raw['Valor Pagto'] <= limite_seguranca].copy()
df_retidos = df_raw[df_raw['Valor Pagto'] > limite_seguranca].copy()

# Cálculos Totais (Baseados apenas nos aprovados para evitar o "dobro")
total_pagar = df_aprovados['Valor Pagto'].sum()
qtd_beneficiarios = df_aprovados['Beneficiário'].nunique() # Conta únicos, caso a mesma pessoa receba 2x
qtd_registros = len(df_aprovados)

# Cálculos de Retenção
total_retido = df_retidos['Valor Pagto'].sum()
qtd_retidos = len(df_retidos)

# --- INTERFACE PRINCIPAL ---

st.title("📊 Dashboard de Controle de Pagamentos")
st.markdown(f"*Status do Sistema: **Operacional** | Data Base: {datetime.now().strftime('%d/%m/%Y')}*")

# 1. CARDS DE KPI (MÉTRICAS)
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        label="💰 Valor Total Aprovado",
        value=format_brl(total_pagar),
        delta="Confirmado"
    )

with col2:
    st.metric(
        label="👥 Beneficiários Únicos",
        value=qtd_beneficiarios,
        help="Quantidade de CPF/CNPJs distintos que receberão pagamentos."
    )

with col3:
    st.metric(
        label="📄 Registros Processados",
        value=qtd_registros,
        delta=f"{len(df_raw)} Total Lido"
    )

with col4:
    st.metric(
        label="🚫 Valor Retido (Suspeito)",
        value=format_brl(total_retido),
        delta=f"- {qtd_retidos} itens",
        delta_color="inverse",
        help=f"Valores acima do limite de {format_brl(limite_seguranca)}."
    )

st.markdown("---")

# 2. ALERTA DE SEGURANÇA
if not df_retidos.empty:
    st.error(f"⚠️ **ATENÇÃO:** Foram detectados {qtd_retidos} pagamentos acima do limite de segurança ({format_brl(limite_seguranca)}). O valor total de {format_brl(total_retido)} foi removido do fluxo de pagamento principal e aguarda aprovação manual.")
    with st.expander("Verificar Pagamentos Retidos/Suspeitos"):
        # Formatar coluna para exibição
        df_display_retidos = df_retidos.copy()
        df_display_retidos['Valor Pagto'] = df_display_retidos['Valor Pagto'].apply(format_brl)
        st.dataframe(df_display_retidos, use_container_width=True)

# 3. GRÁFICOS

col_chart_1, col_chart_2 = st.columns(2)

with col_chart_1:
    st.subheader("Distribuição por Arquivo")
    # Agrupamento correto para evitar duplicação
    df_por_arquivo = df_aprovados.groupby("Arquivo")['Valor Pagto'].sum().reset_index()
    
    fig_bar = px.bar(
        df_por_arquivo,
        x="Arquivo",
        y="Valor Pagto",
        text_auto=True,
        title="Total a Pagar por Arquivo (R$)",
        color="Valor Pagto",
        color_continuous_scale="Blues"
    )
    # Ajuste fino para formato BR no gráfico
    fig_bar.update_traces(texttemplate='R$ %{y:,.2f}', textposition='outside')
    fig_bar.update_layout(yaxis_tickformat = ",.2f") # Tenta aproximar formato
    st.plotly_chart(fig_bar, use_container_width=True)

with col_chart_2:
    st.subheader("Faixa de Valores (Histograma)")
    fig_hist = px.histogram(
        df_aprovados,
        x="Valor Pagto",
        nbins=10,
        title="Concentração dos Pagamentos",
        color_discrete_sequence=['#00CC96']
    )
    # Formatação BR no eixo X
    fig_hist.update_layout(xaxis_tickprefix="R$ ", yaxis_title="Quantidade de Pagamentos")
    st.plotly_chart(fig_hist, use_container_width=True)

# 4. TABELA DETALHADA
st.subheader("📋 Detalhamento de Pagamentos Aprovados")

# Filtro rápido na tabela
filtro_beneficiario = st.text_input("🔍 Buscar Beneficiário ou CPF:")
if filtro_beneficiario:
    df_aprovados = df_aprovados[
        df_aprovados['Beneficiário'].str.contains(filtro_beneficiario, case=False) | 
        df_aprovados['CPF'].str.contains(filtro_beneficiario)
    ]

# Tabela formatada
df_tabela = df_aprovados.copy()
df_tabela['Valor Pagto'] = df_tabela['Valor Pagto'].apply(format_brl)

st.dataframe(
    df_tabela,
    column_config={
        "Valor Pagto": st.column_config.TextColumn("Valor Líquido"),
        "Data": st.column_config.DateColumn("Data Vencimento", format="DD/MM/YYYY")
    },
    use_container_width=True,
    hide_index=True
)
