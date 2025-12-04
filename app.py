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
        # Remove caracteres não numéricos exceto vírgula e ponto
        clean_str = value.replace('R$', '').replace(' ', '').strip()
        # Se for formato BR (1.000,00)
        if ',' in clean_str and '.' in clean_str:
            clean_str = clean_str.replace('.', '').replace(',', '.')
        elif ',' in clean_str:
            clean_str = clean_str.replace(',', '.')
        
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
    Agora ajustado para ter pagamentos únicos altos, ao invés de focar na soma.
    """
    np.random.seed(42) # Semente para reprodutibilidade
    n_rows = 2054
    
    projetos = [
        "POT - Redenção", "POT - Oportunidades", "POT - Zeladoria", 
        "POT - Horta", "POT - Mães Guardiãs"
    ]
    
    # Geração de Cartões
    unique_cards = np.random.randint(1000000000, 9999999999, size=1800, dtype=np.int64)
    cards_column = np.random.choice(unique_cards, size=n_rows)
    
    # Valores de Pagamento
    base_values = [600.00, 850.00, 920.00, 1200.00, 1500.00]
    values_column = np.random.choice(base_values, size=n_rows).astype(float)
    
    noise = np.random.random(size=n_rows) * 10 
    values_column += noise
    
    # Casos de Teste (Valor Único > 5k)
    # Linha específica com valor alto (suspeito individual)
    values_column[0] = 5500.00 
    
    # Linha com valor alto mas abaixo do limite
    values_column[1] = 4900.00
    
    # Mesmo cartão com vários pagamentos (Total > 5k, mas linhas individuais < 5k -> DEVE PASSAR)
    cards_column[2:5] = 9876543210
    values_column[2] = 2000.00
    values_column[3] = 2000.00
    values_column[4] = 2000.00
    
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
    """
    Carrega e normaliza arquivo real enviado pelo usuário.
    Implementa tratamento de encoding para evitar erros com arquivos BR (Latin-1).
    """
    df = pd.DataFrame()
    try:
        if uploaded_file.name.endswith('.csv'):
            # Tenta ler como UTF-8 padrão
            try:
                df = pd.read_csv(uploaded_file)
            except UnicodeDecodeError:
                # Se falhar, tenta Latin-1 (comum em Excel BR) e separador de ponto e vírgula
                uploaded_file.seek(0)
                try:
                    df = pd.read_csv(uploaded_file, encoding='latin-1', sep=';')
                except:
                    # Última tentativa com encoding comum
                    uploaded_file.seek(0)
                    df = pd.read_csv(uploaded_file, encoding='iso-8859-1', sep=';')
        else:
            df = pd.read_excel(uploaded_file)
        
        # 1. Limpeza inicial de nomes de colunas (strip)
        df.columns = [str(c).strip() for c in df.columns]

        # 2. Remoção de colunas duplicadas (evita AttributeError na seleção)
        df = df.loc[:, ~df.columns.duplicated()]

        # 3. Mapeamento Inteligente
        cols_map = {c.lower(): c for c in df.columns}
        rename_dict = {}
        
        # Mapeia Num Cartao
        if 'Num Cartao' not in df.columns:
            for key in cols_map:
                if 'cartao' in key or 'cartão' in key or 'conta' in key:
                    rename_dict[cols_map[key]] = 'Num Cartao'
                    break
        
        # Mapeia Valor Pagto
        if 'Valor Pagto' not in df.columns:
            for key in cols_map:
                if 'valor' in key or 'liquido' in key or 'líquido' in key:
                    rename_dict[cols_map[key]] = 'Valor Pagto'
                    break
                    
        df = df.rename(columns=rename_dict)
        
        # 4. Validação Crítica
        required_cols = ['Num Cartao', 'Valor Pagto']
        missing = [c for c in required_cols if c not in df.columns]
        
        if missing:
            st.error(f"❌ Erro de Formato: Não foi possível identificar as colunas obrigatórias: {missing}. Verifique se o arquivo possui colunas com 'Cartão' e 'Valor'.")
            return pd.DataFrame() # Retorna vazio para não quebrar o app
            
        # Força conversão de Num Cartao para string
        if 'Num Cartao' in df.columns:
            df['Num Cartao'] = df['Num Cartao'].astype(str)
            
        return df

    except Exception as e:
        st.error(f"Erro Crítico ao ler arquivo: {str(e)}")
        return pd.DataFrame()

# --- LÓGICA DE NEGÓCIO ---
def process_business_rules(df, threshold=5000.00):
    if df.empty:
        return df

    # Verificação de segurança adicional
    if 'Valor Pagto' not in df.columns:
        st.error("Erro interno: Coluna 'Valor Pagto' perdida no processamento.")
        return df

    # Limpeza/Conversão do Valor
    # Verifica o tipo da coluna para decidir como limpar
    try:
        if df['Valor Pagto'].dtype == 'object':
            df['Valor_Calculo'] = df['Valor Pagto'].apply(clean_currency)
        else:
            df['Valor_Calculo'] = pd.to_numeric(df['Valor Pagto'], errors='coerce').fillna(0.0)
    except Exception as e:
        st.error(f"Erro ao processar valores monetários: {e}")
        df['Valor_Calculo'] = 0.0

    # --- REGRA ATUALIZADA ---
    # Validação LINHA A LINHA.
    # O limite de R$ 5.000,00 se aplica ao valor individual do pagamento.
    
    df['Status_Validacao'] = df['Valor_Calculo'].apply(
        lambda x: '⚠️ Análise Admin' if x > threshold else '✅ Liberado'
    )
    
    # Opcional: Calcula total por cartão para informação
    try:
        grouped = df.groupby('Num Cartao')['Valor_Calculo'].sum().reset_index()
        grouped.rename(columns={'Valor_Calculo': 'Info_Total_Acumulado'}, inplace=True)
        
        # Merge apenas para trazer a info de acumulado
        df_final = df.merge(grouped, on='Num Cartao', how='left')
        return df_final
    except Exception as e:
        st.warning(f"Não foi possível calcular o acumulado por cartão: {e}")
        return df

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
    "Teto Máximo por Pagamento Único (R$)",
    value=5000.00,
    step=100.00,
    help="Qualquer linha de pagamento acima deste valor será retida para análise."
)

if st.sidebar.button("🗑️ Limpar Banco de Dados (Admin)", type="primary"):
    st.session_state['df_pagamentos'] = pd.DataFrame()
    st.cache_data.clear()
    st.rerun()

# --- PROCESSAMENTO DO UPLOAD ---
if uploaded_file is not None:
    # Apenas carrega se o dataframe estiver vazio ou se o usuário estiver explicitamente subindo algo novo
    # Isso evita recargas desnecessárias, mas garante que o upload funcione
    df_loaded = load_from_file(uploaded_file)
    if not df_loaded.empty:
        st.session_state['df_pagamentos'] = df_loaded

# --- APP PRINCIPAL ---

st.title("Sistema de Gestão Financeira - POT")

df_raw = st.session_state['df_pagamentos']

if df_raw.empty:
    st.info("""
        ℹ️ **Sistema Aguardando Dados**
        
        Carregue um arquivo .xlsx/.csv ou use os dados de teste.
    """)
    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    with c2:
        st.markdown("### 🚫 Nenhum dado carregado")

else:
    # Processamento com tratamento de erro
    try:
        df_processed = process_business_rules(df_raw, threshold=limite_teto)
        
        if 'Status_Validacao' in df_processed.columns:
            # Filtros
            df_analise = df_processed[df_processed['Status_Validacao'] == '⚠️ Análise Admin']
            
            # KPIs
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
            
            # ALERTAS
            if not df_analise.empty:
                st.error(f"🚨 **Atenção:** {len(df_analise)} pagamentos individuais excedem o teto de R$ {limite_teto:,.2f}.")
                with st.expander("Ver Detalhes da Malha Fina (Valores Individuais Altos)"):
                    cols_to_show = ['Num Cartao', 'Nome Beneficiário', 'Valor Pagto', 'Info_Total_Acumulado']
                    # Garante que as colunas existem antes de mostrar
                    cols_existing = [c for c in cols_to_show if c in df_analise.columns]
                    
                    st.dataframe(
                        df_analise[cols_existing].sort_values(by='Valor Pagto', ascending=False),
                        column_config={
                            "Valor Pagto": st.column_config.NumberColumn("Valor do Pagamento (Alerta)", format="R$ %.2f"),
                            "Info_Total_Acumulado": st.column_config.NumberColumn("Total Acumulado (Info)", format="R$ %.2f")
                        },
                        use_container_width=True
                    )
            else:
                st.success("✅ Nenhum pagamento individual excede o limite estabelecido.")
                
            # GRÁFICOS
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
        else:
            st.warning("Não foi possível processar o status de validação. Verifique os dados.")
            st.dataframe(df_raw)
            
    except Exception as e:
        st.error(f"Erro inesperado no processamento visual: {str(e)}")
