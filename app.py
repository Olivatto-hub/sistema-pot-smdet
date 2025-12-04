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

# --- GERAÇÃO DE DADOS (SIMULAÇÃO FIEL AOS 2054 REGISTROS) ---
@st.cache_data
def load_data_pot():
    """
    Gera um dataset simulando o arquivo mestre do Programa Operação Trabalho.
    Contém 2054 registros, múltiplos projetos e casos de teste para a regra de R$ 5k.
    """
    np.random.seed(42) # Semente para reprodutibilidade
    n_rows = 2054
    
    # 1. Projetos do Programa (Simulando arquivos iniciais variados)
    projetos = [
        "POT - Redenção", "POT - Oportunidades", "POT - Zeladoria", 
        "POT - Horta", "POT - Mães Guardiãs"
    ]
    
    # 2. Geração de Cartões (Beneficiários Únicos)
    # Criamos menos cartões que linhas para forçar repetições (múltiplos pagamentos por cartão)
    unique_cards = np.random.randint(1000000000, 9999999999, size=1800, dtype=np.int64)
    
    # Distribui os cartões nas 2054 linhas
    cards_column = np.random.choice(unique_cards, size=n_rows)
    
    # 3. Valores de Pagamento
    # A maioria recebe valores baixos (bolsas padrão), alguns recebem acumulado
    base_values = [600.00, 850.00, 920.00, 1200.00, 1500.00]
    values_column = np.random.choice(base_values, size=n_rows).astype(float)
    
    # Adicionar ruído/variações de centavos como nas planilhas reais
    noise = np.random.random(size=n_rows) * 10 
    values_column += noise
    
    # 4. Inserir casos específicos para testar a regra de > 5000
    # Forçamos alguns cartões a terem valores altos somados
    # Cartão X vai receber um pagamento alto
    cards_column[0] = 1234567890
    values_column[0] = 5500.00 # Estoura o limite sozinho
    
    # Cartão Y vai receber 3 pagamentos que somam > 5000
    cards_column[1:4] = 9876543210
    values_column[1] = 2000.00
    values_column[2] = 2000.00
    values_column[3] = 1500.00 # Soma 5500 -> Deve cair na malha fina
    
    # Montagem do DataFrame
    df = pd.DataFrame({
        "Num Cartao": cards_column,
        "Nome Beneficiário": [f"Beneficiário {i}" for i in range(n_rows)],
        "Projeto Origem": np.random.choice(projetos, size=n_rows),
        "Valor Pagto": values_column,
        "Data Processamento": pd.date_range(start="2023-10-01", periods=n_rows, freq="T"),
        "Status Planilha": "Importado"
    })
    
    # Converter Num Cartao para string para evitar somar o número do cartão
    df["Num Cartao"] = df["Num Cartao"].astype(str)
    
    return df

# --- LÓGICA DE NEGÓCIO (A "REGRA DE OURO") ---
def process_business_rules(df, threshold=5000.00):
    """
    Aplica a regra: Agrupar por 'Num Cartao'. 
    Se Soma(Valor Pagto) > threshold, marca TODOS os registros desse cartão para validação Admin.
    """
    if df.empty:
        return df

    # Garantir que estamos usando float limpo
    # (No mock já é float, mas num upload real precisaria limpar)
    # df['Valor_Calculo'] = df['Valor Pagto'].apply(clean_currency) 
    # Como o mock já gera float, usamos direto:
    df['Valor_Calculo'] = df['Valor Pagto']

    # 1. Agrupamento por Cartão (Beneficiário Único)
    grouped = df.groupby('Num Cartao')['Valor_Calculo'].sum().reset_index()
    grouped.rename(columns={'Valor_Calculo': 'Soma_Total_Cartao'}, inplace=True)
    
    # 2. Determinar Status por Cartão
    grouped['Status_Validacao'] = grouped['Soma_Total_Cartao'].apply(
        lambda x: '⚠️ Análise Admin' if x > threshold else '✅ Liberado'
    )
    
    # 3. Cruzar de volta com a base original (Merge)
    # Isso garante que mantemos os 2054 registros, mas cada um agora sabe o status do seu "dono"
    df_final = df.merge(grouped[['Num Cartao', 'Soma_Total_Cartao', 'Status_Validacao']], on='Num Cartao', how='left')
    
    return df_final

# --- SIDEBAR: CONTROLES ADMIN ---
st.sidebar.title("🔧 Painel de Controle")

st.sidebar.markdown("### Configurações de Regra")
limite_teto = st.sidebar.number_input(
    "Teto Máximo por Cartão (R$)",
    value=5000.00,
    step=100.00,
    help="Valores acumulados por cartão acima deste montante exigirão validação."
)

st.sidebar.markdown("---")
st.sidebar.markdown("### Gestão de Dados")

# Botão de Reset Real
if st.sidebar.button("🗑️ Limpar Cache e Reiniciar Sistema"):
    st.cache_data.clear()
    if 'data_loaded' in st.session_state:
        del st.session_state['data_loaded']
    st.rerun()

# --- APP PRINCIPAL ---

st.title("Sistema de Gestão Financeira - Programa Operação Trabalho")
st.markdown(f"**Base de Dados Ativa:** Arquivo Mestre (Simulação dos Arquivos Iniciais)")

# 1. CARREGAMENTO E PROCESSAMENTO
df_raw = load_data_pot()
df_processed = process_business_rules(df_raw, threshold=limite_teto)

# Separação dos grupos para exibição
df_analise = df_processed[df_processed['Status_Validacao'] == '⚠️ Análise Admin']
df_liberados = df_processed[df_processed['Status_Validacao'] == '✅ Liberado']

# 2. DASHBOARD (KPIs)
col1, col2, col3, col4 = st.columns(4)

total_valor = df_processed['Valor_Calculo'].sum()
total_analise = df_analise['Valor_Calculo'].sum()

with col1:
    st.metric("Total de Registros", len(df_processed), delta="100% dos dados")

with col2:
    st.metric("Valor Total da Folha", format_brl(total_valor))

with col3:
    st.metric(
        "Cartões Únicos", 
        df_processed['Num Cartao'].nunique(),
        help="Quantidade de cartões distintos identificados no arquivo."
    )

with col4:
    st.metric(
        "Retido para Validação (>5k)", 
        format_brl(total_analise), 
        delta=f"{df_analise['Num Cartao'].nunique()} cartões",
        delta_color="inverse"
    )

st.markdown("---")

# 3. ALERTA DE VALIDAÇÃO (SE HOUVER)
if not df_analise.empty:
    st.error(f"""
    🚨 **Ação Necessária:** Foram detectados {df_analise['Num Cartao'].nunique()} cartões cujo somatório de pagamentos excede R$ {limite_teto:,.2f}.
    Estes registros totalizam {format_brl(total_analise)} e precisam de validação por perfil Admin/TI.
    """)
    
    with st.expander("🔍 Visualizar Itens em Análise (Detalhado por Cartão)", expanded=True):
        # Mostra apenas as colunas relevantes para decisão
        st.dataframe(
            df_analise[['Num Cartao', 'Nome Beneficiário', 'Projeto Origem', 'Valor Pagto', 'Soma_Total_Cartao']]
            .sort_values(by='Soma_Total_Cartao', ascending=False),
            column_config={
                "Valor Pagto": st.column_config.NumberColumn("Valor do Item", format="R$ %.2f"),
                "Soma_Total_Cartao": st.column_config.NumberColumn("Acumulado no Cartão", format="R$ %.2f"),
            },
            use_container_width=True
        )
else:
    st.success("✅ Todos os pagamentos estão dentro dos limites estabelecidos por cartão.")

# 4. VISÃO GERAL (GRÁFICOS)
st.subheader("Visão Geral do Processamento")
tab1, tab2 = st.tabs(["📊 Gráficos Gerenciais", "📋 Base Completa (2054 Registros)"])

with tab1:
    c1, c2 = st.columns(2)
    with c1:
        # Gráfico de Barras: Valor por Projeto
        df_proj = df_processed.groupby("Projeto Origem")['Valor_Calculo'].sum().reset_index()
        fig_bar = px.bar(
            df_proj, 
            x="Projeto Origem", 
            y="Valor_Calculo", 
            title="Distribuição Financeira por Projeto",
            text_auto=True,
            color="Valor_Calculo"
        )
        fig_bar.update_traces(texttemplate='R$ %{y:,.2s}', textposition='outside')
        st.plotly_chart(fig_bar, use_container_width=True)
    
    with c2:
        # Gráfico de Pizza: Status da Validação
        df_status = df_processed['Status_Validacao'].value_counts().reset_index()
        df_status.columns = ['Status', 'Quantidade']
        fig_pie = px.pie(
            df_status, 
            names='Status', 
            values='Quantidade', 
            title=f"Proporção de Registros (Total: {len(df_processed)})",
            color='Status',
            color_discrete_map={'✅ Liberado': '#2ecc71', '⚠️ Análise Admin': '#e74c3c'}
        )
        st.plotly_chart(fig_pie, use_container_width=True)

with tab2:
    st.dataframe(
        df_processed,
        column_config={
            "Valor Pagto": st.column_config.NumberColumn("Valor Item", format="R$ %.2f"),
            "Soma_Total_Cartao": st.column_config.NumberColumn("Total Cartão", format="R$ %.2f"),
            "Valor_Calculo": None # Esconde coluna auxiliar
        },
        use_container_width=True,
        hide_index=True
    )
