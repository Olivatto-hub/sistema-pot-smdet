import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import warnings
import re
from functools import wraps

warnings.filterwarnings('ignore')

# ============================================
# 1. CONFIGURAÇÃO DA PÁGINA (CORREÇÃO PONTO 1)
# ============================================
st.set_page_config(
    page_title="SMDET - POT Monitoramento de Pagamento de Benefícios",
    page_icon="🏙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================
# CSS MINIMALISTA - ADAPTA AO TEMA DO USUÁRIO
# ============================================
st.markdown("""
<style>
    /* MELHORIAS GERAIS - NÃO INTERFERE NO TEMA */
    .stDataFrame {
        border-radius: 8px;
        overflow: hidden;
    }
    
    /* MELHOR VISIBILIDADE PARA DATAFRAMES */
    .stDataFrame th {
        font-weight: 700 !important;
    }
    
    /* ESPAÇAMENTO MELHOR ENTRE WIDGETS */
    .stSlider, .stSelectbox, .stMultiSelect {
        margin-bottom: 1rem;
    }
    
    /* BOTÕES MAIS VISÍVEIS */
    .stButton > button {
        border-radius: 6px;
        font-weight: 600;
        transition: all 0.3s ease;
        padding: 0.75rem 1rem;
    }
    
    .stButton > button:hover {
        opacity: 0.9;
    }

    /* TÍTULO CENTRALIZADO PARA MELHORES VISUALIZAÇÕES */
    .chart-title {
        text-align: center;
        font-weight: 600;
        margin-bottom: 1rem;
        padding: 0.5rem;
        background-color: #f0f2f6; /* Light gray background for title area */
        border-radius: 8px;
    }

    /* CORREÇÃO PARA ALINHAMENTO DO BOTÃO DE DOWNLOAD */
    .stDownloadButton {
        display: flex;
        justify-content: center;
    }
</style>
""", unsafe_allow_html=True)


# ============================================
# ⚙️ FUNÇÕES DE UTILIDADE E PROCESSAMENTO
# ============================================

# Função para inicializar configurações padrão
def initialize_config():
    if 'config' not in st.session_state:
        st.session_state['config'] = {
            'auto_validar': True,
            'manter_historico': True,
            'limite_registros': 100000,
            # CORREÇÃO PONTO 5: Removido PDF do formato de exportação para evitar ModuleNotFoundError
            'formato_exportacao': 'Excel (.xlsx)', 
            'incluir_graficos': False # Mantido mas será ignorado para PDF
        }

# Função para aplicar filtros e gerar df_analise
def apply_filters(df, filters):
    df_filtered = df.copy()
    
    # Filtro de Projeto
    if filters['projeto']:
        df_filtered = df_filtered[df_filtered['Projeto'].isin(filters['projeto'])]
    
    # Filtro de Gerenciadora
    if filters['gerenciadora']:
        df_filtered = df_filtered[df_filtered['Gerenciadora'].isin(filters['gerenciadora'])]
        
    # Filtro de Valor Pagto Mínimo
    df_filtered = df_filtered[df_filtered['Valor Pagto'] >= filters['valor_min']]
    
    # Filtro de Valor Pagto Máximo
    df_filtered = df_filtered[df_filtered['Valor Pagto'] <= filters['valor_max']]

    # Filtro de Data
    if filters['data_inicio'] and filters['data_fim']:
        data_col = pd.to_datetime(df_filtered['Data Pagto'], format='%d/%m/%Y', errors='coerce')
        df_filtered = df_filtered[
            (data_col >= filters['data_inicio']) & (data_col <= filters['data_fim'])
        ]
    
    return df_filtered

# Função para carregar e processar os dados
@st.cache_data(show_spinner="Processando dados e realizando validações iniciais...")
def load_data(uploaded_file):
    try:
        # Tenta ler o arquivo CSV com delimitador ';' e encoding 'utf-8' (mais comum)
        df = pd.read_csv(uploaded_file, sep=';', encoding='utf-8', on_bad_lines='skip')
    except UnicodeDecodeError:
        try:
            # CORREÇÃO PARA O ERRO DE ENCODING: Tenta 'latin-1' (compatível com Windows/pt-br)
            uploaded_file.seek(0) # Volta o ponteiro do arquivo para o início
            df = pd.read_csv(uploaded_file, sep=';', encoding='latin-1', on_bad_lines='skip')
            st.warning("⚠️ Arquivo lido usando encoding 'latin-1' para corrigir problemas de caracteres.")
        except Exception as e:
            # Caso não funcione com latin-1, reporta o erro original
            st.error(f"Erro ao ler o arquivo: {e}")
            return pd.DataFrame()
    except Exception as e:
        st.error(f"Erro ao ler o arquivo: {e}")
        return pd.DataFrame()

    # Normalização dos nomes das colunas
    df.columns = df.columns.str.strip().str.replace(' ', '_').str.replace('ã', 'a').str.replace('ç', 'c')
    
    # Renomear para os nomes esperados
    col_map = {
        'Num_Cartao': 'Num Cartao', 'Valor_Total': 'Valor Total', 'Valor_Desconto': 'Valor Desconto', 
        'Valor_Pagto': 'Valor Pagto', 'Data_Pagto': 'Data Pagto', 'Valor_Dia': 'Valor Dia', 
        'Dias_a_apagar': 'Dias a apagar', 'Gerenciadora': 'Gerenciadora'
    }
    df.rename(columns=col_map, inplace=True)

    # Conversão de colunas numéricas
    for col in ['Valor Total', 'Valor Desconto', 'Valor Pagto', 'Valor Dia']:
        # Remove R$ and . and replace , with .
        df[col] = df[col].astype(str).str.replace('R$', '', regex=False).str.replace('.', '', regex=False).str.replace(',', '.', regex=False).str.replace(' ', '', regex=False)
        # Handle empty/NaN/invalid values before conversion
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0) # Convert to numeric
    
    # CORREÇÃO PONTO 2: Desduplicação para evitar contagem/soma duplicada de pagamentos.
    # Usamos uma combinação de colunas que identificam o pagamento de forma única.
    dedup_cols = ['Ordem', 'CPF', 'Valor Pagto', 'Data Pagto']
    initial_count = len(df)
    
    # Garante que as colunas de dedup existem
    if all(col in df.columns for col in dedup_cols):
        df.drop_duplicates(subset=dedup_cols, keep='first', inplace=True)
        final_count = len(df)
        
        if initial_count != final_count:
            st.warning(f"⚠️ {initial_count - final_count} linhas duplicadas foram removidas para garantir a precisão dos cálculos. O número final de pagamentos é: {final_count}.")
    else:
        st.warning("Colunas necessárias para desduplicação (Ordem, CPF, Valor Pagto, Data Pagto) não encontradas. Prossiga sem desduplicação forçada.")


    # Adicionar coluna de Mês/Ano para análise temporal
    df['Mes_Ano'] = pd.to_datetime(df['Data Pagto'], format='%d/%m/%Y', errors='coerce').dt.to_period('M')
    
    # Identificação de pendências básicas (exemplo: CPF em branco ou valor de pagamento zero)
    df['Pendencia'] = np.where(df['CPF'].isnull() | (df['CPF'] == 0) | (df['Valor Pagto'] <= 0), True, False)
    
    return df

# Função para criar o gráfico de pizza de Gerenciadoras
def create_gerenciadora_pie_chart(df):
    df_counts = df.groupby('Gerenciadora')['Valor Pagto'].sum().reset_index()
    df_counts.columns = ['Gerenciadora', 'Valor Pago']
    
    fig = px.pie(
        df_counts, 
        values='Valor Pago', 
        names='Gerenciadora', 
        title='Distribuição de Pagamentos por Gerenciadora',
        hole=0.4,
        color_discrete_sequence=px.colors.sequential.Teal
    )
    fig.update_traces(textinfo='percent+label', marker=dict(line=dict(color='#000000', width=1)))
    fig.update_layout(showlegend=True, margin=dict(t=50, b=0, l=0, r=0))
    return fig

# Função para criar o gráfico de barras dos projetos (CORREÇÃO PONTO 4)
def create_project_bar_chart(df_proj):
    fig = px.bar(
        df_proj.sort_values(by='Valor Total Pago', ascending=True), 
        x='Valor Total Pago', 
        y='Projeto', 
        orientation='h',
        title='Distribuição de Pagamentos por Projeto',
        color='Valor Total Pago',
        color_continuous_scale=px.colors.sequential.Agsunset,
        text='Valor Total Pago'
    )
    
    fig.update_traces(
        texttemplate='R$ %{text:$.2s}',  # Formata o texto como R$ com milhar (e.g., $1.5M)
        textposition='outside',
        marker_line_color='rgb(8,48,107)',
        marker_line_width=1.5
    )
    
    fig.update_layout(
        uniformtext_minsize=8, 
        uniformtext_mode='hide',
        xaxis_title="Valor Total Pago (R$)",
        yaxis_title="Projeto",
        margin=dict(l=0, r=0, t=50, b=0),
        xaxis={'tickformat': ',.2f'} # Formato de número com 2 casas decimais
    )
    
    return fig

# ============================================
# 🏠 INICIALIZAÇÃO DE ESTADO E BARRA LATERAL
# ============================================

initialize_config()

# 1. SIDEBAR (CORREÇÃO PONTO 1)
st.sidebar.markdown("# SMDET - POT Monitoramento de Pagamento de Benefícios")
st.sidebar.markdown("---")

uploaded_file = st.sidebar.file_uploader(
    "📤 CARREGAR BASE DE DADOS (CSV)", 
    type=['csv'],
    help="Carregue o arquivo de pagamentos no formato CSV com ';' como delimitador."
)

if uploaded_file and 'data' not in st.session_state:
    st.session_state['data'] = load_data(uploaded_file)
    st.session_state['analise_pronta'] = False # Reinicia a análise

if 'data' in st.session_state and not st.session_state['data'].empty:
    df = st.session_state['data']
    
    # Informações básicas na sidebar
    st.sidebar.markdown("### 📊 STATUS DA BASE")
    st.sidebar.metric("Linhas Carregadas", len(df))
    st.sidebar.metric("Projetos Únicos", df['Projeto'].nunique())
    
    # Botão de Limpar Dados
    if st.sidebar.button("🧹 Limpar dados carregados", type="secondary", use_container_width=True):
        # Limpa o estado da sessão de dados e da análise
        keys_to_delete = ['data', 'df_analise', 'df_pendencias', 'analise_pronta', 'filters']
        for key in keys_to_delete:
            if key in st.session_state:
                del st.session_state[key]
        st.info("Dados removidos com sucesso. Reiniciando a aplicação...")
        st.rerun() # CORREÇÃO PONTO 6: Substituído st.experimental_rerun() por st.rerun()

# ============================================
# ⚠️ FLUXO PRINCIPAL: CARREGAMENTO DE DADOS
# ============================================

if 'data' not in st.session_state or st.session_state['data'].empty:
    st.info("Por favor, carregue um arquivo CSV de pagamentos na barra lateral para iniciar o monitoramento.")
    st.stop()

df = st.session_state['data']

# ============================================
# 🎛️ BARRA LATERAL: FILTROS DE ANÁLISE
# ============================================

st.sidebar.markdown("### 🔍 FILTROS DE ANÁLISE")

# Filtro de Múltipla Seleção (Projeto)
unique_projects = sorted(df['Projeto'].unique())
selected_projects = st.sidebar.multiselect(
    "Projetos:",
    options=unique_projects,
    default=unique_projects,
    help="Selecione os projetos para análise."
)

# Filtro de Múltipla Seleção (Gerenciadora)
unique_gerenciadoras = sorted(df['Gerenciadora'].dropna().unique())
selected_gerenciadoras = st.sidebar.multiselect(
    "Gerenciadoras:",
    options=unique_gerenciadoras,
    default=unique_gerenciadoras,
    help="Selecione as gerenciadoras para análise."
)

# Filtro de Range de Valor
valor_min, valor_max = float(df['Valor Pagto'].min()), float(df['Valor Pagto'].max())
selected_min_value, selected_max_value = st.sidebar.slider(
    "Valor de Pagamento (R$):",
    min_value=valor_min,
    max_value=valor_max,
    value=(valor_min, valor_max),
    step=100.0,
    format='R$ %.2f'
)

# Filtro de Range de Data
data_col_dt = pd.to_datetime(df['Data Pagto'], format='%d/%m/%Y', errors='coerce').dropna()
min_date = data_col_dt.min().date() if not data_col_dt.empty else datetime.now().date()
max_date = data_col_dt.max().date() if not data_col_dt.empty else datetime.now().date()

try:
    selected_date_range = st.sidebar.date_input(
        "Período de Pagamento:",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )
    if len(selected_date_range) == 2:
        start_date = selected_date_range[0]
        end_date = selected_date_range[1]
    else:
        start_date, end_date = None, None
except Exception:
    start_date, end_date = None, None
    st.sidebar.error("Problema ao carregar o filtro de datas. Verifique a coluna 'Data Pagto'.")


current_filters = {
    'projeto': selected_projects,
    'gerenciadora': selected_gerenciadoras,
    'valor_min': selected_min_value,
    'valor_max': selected_max_value,
    'data_inicio': start_date,
    'data_fim': end_date
}

# Botão para aplicar filtros
if st.sidebar.button("✅ APLICAR FILTROS E RECALCULAR", type="primary", use_container_width=True):
    st.session_state['filters'] = current_filters
    st.session_state['df_analise'] = apply_filters(df, current_filters)
    st.session_state['df_pendencias'] = st.session_state['df_analise'][st.session_state['df_analise']['Pendencia'] == True].copy()
    st.session_state['analise_pronta'] = True
    st.success("Filtros aplicados e análise recalculada!")

# Garante que a análise inicial esteja pronta se os filtros não foram tocados
if 'analise_pronta' not in st.session_state:
    st.session_state['df_analise'] = df.copy()
    st.session_state['df_pendencias'] = st.session_state['df_analise'][st.session_state['df_analise']['Pendencia'] == True].copy()
    st.session_state['analise_pronta'] = True
    st.session_state['filters'] = current_filters


df_analise = st.session_state['df_analise']
df_pendencias = st.session_state['df_pendencias']

# ============================================
# 🖥️ VISUALIZAÇÃO PRINCIPAL (ABAS)
# ============================================

aba_dashboard, aba_processamento, aba_pendencias, aba_config = st.tabs([
    "📊 Dashboard", "🛠️ Processamento e Exportação", "🚨 Análise de Pendências", "⚙️ Configurações"
])

# ===========================================
# 📊 Aba Dashboard - Métricas Principais
# ===========================================
with aba_dashboard:
    if df_analise.empty:
        st.warning("Nenhum dado corresponde aos filtros aplicados.")
        st.stop()

    col1, col2, col3, col4 = st.columns(4)

    # CORREÇÃO PONTO 3: Cálculo e exibição da Quantidade de Pagamentos
    total_pago = df_analise['Valor Pagto'].sum()
    num_pagamentos = len(df_analise) 
    num_beneficiarios = df_analise['CPF'].nunique()
    num_pendencias = len(df_pendencias)
    
    # Função de formatação BRL
    def format_brl(value):
        return f"R$ {value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")

    # Métricas Principais
    with col1:
        st.metric(label="💰 VALOR TOTAL PAGO", 
                  value=format_brl(total_pago))
    
    with col2:
        # CORREÇÃO PONTO 3: Substituído Valor Total Bruto por Quantidade de Pagamentos
        st.metric(label="👤 QUANTIDADE DE PAGAMENTOS", 
                  value=f"{num_pagamentos:,.0f}".replace(",", "_").replace(".", ",").replace("_", "."))
    
    with col3:
        st.metric(label="👥 BENEFICIÁRIOS ÚNICOS", 
                  value=f"{num_beneficiarios:,.0f}".replace(",", "_").replace(".", ",").replace("_", "."))
    
    with col4:
        st.metric(label="🚨 PAGAMENTOS C/ PENDÊNCIA", 
                  value=f"{num_pendencias:,.0f} ({num_pendencias/num_pagamentos:.2%})".replace(",", "_").replace(".", ",").replace("_", "."))
    
    st.markdown("---")
    
    # 2. Análise por Projeto e Gerenciadora
    col_g1, col_g2 = st.columns([1, 2])
    
    with col_g1:
        st.markdown('<p class="chart-title">Distribuição por Gerenciadora</p>', unsafe_allow_html=True)
        fig_pie = create_gerenciadora_pie_chart(df_analise)
        st.plotly_chart(fig_pie, use_container_width=True)
        
    with col_g2:
        # CORREÇÃO PONTO 4: Remover TOP 10 e mostrar todos os projetos
        st.markdown('<p class="chart-title">🏛️ VALORES TOTAIS POR PROJETO</p>', unsafe_allow_html=True)
        
        df_proj = df_analise.groupby('Projeto').agg(
            Valor_Total_Pago=('Valor Pagto', 'sum'),
            Valor_Total_Bruto=('Valor Total', 'sum'),
            Total_Beneficiarios=('CPF', 'nunique'),
            Media_Pagto=('Valor Pagto', 'mean')
        ).reset_index().sort_values(by='Valor_Total_Pago', ascending=False) # Removido .head(10)
        
        # Renaming for display
        df_proj.columns = ['Projeto', 'Valor Total Pago', 'Valor Total Bruto', 'Total de Beneficiários', 'Média de Pagamento']
        
        fig_bar = create_project_bar_chart(df_proj)
        st.plotly_chart(fig_bar, use_container_width=True)
        
    st.markdown("---")

    # 3. Análise Temporal
    st.markdown("### 📈 ANÁLISE TEMPORAL (PAGAMENTO MÊS/ANO)")
    
    df_tempo = df_analise.groupby('Mes_Ano').agg(
        Valor_Total_Pago=('Valor Pagto', 'sum'),
        Total_Pagamentos=('Ordem', 'nunique')
    ).reset_index()
    
    df_tempo['Mes_Ano_str'] = df_tempo['Mes_Ano'].astype(str)
    
    fig_line = px.line(
        df_tempo,
        x='Mes_Ano_str',
        y='Valor_Total_Pago',
        title='Evolução Mensal do Valor Total Pago',
        markers=True,
        text='Valor_Total_Pago'
    )
    
    fig_line.update_traces(
        texttemplate='R$ %{text:,.2s}', 
        textposition="top center",
        line=dict(color=px.colors.qualitative.Dark24[0], width=3),
    )
    fig_line.update_layout(
        xaxis_title="Mês/Ano",
        yaxis_title="Valor Total Pago (R$)",
        xaxis_tickangle=-45
    )
    st.plotly_chart(fig_line, use_container_width=True)

# ===========================================
# 🛠️ Aba Processamento e Exportação
# ===========================================
with aba_processamento:
    st.markdown("### STATUS DO PROCESSAMENTO")
    col_p1, col_p2 = st.columns(2)
    
    with col_p1:
        st.metric("Status Atual", "Análise Completa", help="Reflete o estado após a aplicação dos filtros.")
    with col_p2:
        st.metric("Registros na Análise", len(df_analise), help="Número de pagamentos após a aplicação dos filtros.")
        
    st.markdown("---")
    
    st.markdown("### ⬇️ EXPORTAÇÃO DE DADOS FILTRADOS")
    
    # CORREÇÃO PONTO 5: Otimização da lógica de exportação usando st.download_button
    export_format = st.session_state['config']['formato_exportacao']
    
    if not df_analise.empty:
        
        data_to_download = None
        mime_type = None
        
        if export_format == "Excel (.xlsx)":
            output = BytesIO()
            # Uso de 'openpyxl' como engine mais robusto em ambientes Streamlit
            try:
                with pd.ExcelWriter(output, engine='openpyxl') as writer: 
                    df_analise.to_excel(writer, index=False, sheet_name='Dados Analisados')
                data_to_download = output.getvalue()
                mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            except ImportError:
                 st.error("O motor 'openpyxl' não está instalado. Por favor, exporte como CSV.")
                 export_format = "CSV (.csv)" # Fallback
            
        elif export_format == "CSV (.csv)":
            data_to_download = df_analise.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')
            mime_type = "text/csv"
        
        # O PDF foi removido do menu de configurações para evitar erros.
        
        filename = f"analise_smdet_pot_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if export_format == "Excel (.xlsx)":
            filename += ".xlsx"
        elif export_format == "CSV (.csv)":
            filename += ".csv"

        if data_to_download is not None and mime_type is not None:
             st.download_button(
                label=f"⬇️ EXPORTAR DADOS FILTRADOS ({export_format.split('(')[1][:-1].upper()})",
                data=data_to_download,
                file_name=filename,
                mime=mime_type,
                type="primary",
                use_container_width=True
            )
        else:
            st.warning("Selecione um formato de exportação válido nas Configurações.")

# ===========================================
# 🚨 Aba Análise de Pendências
# ===========================================
with aba_pendencias:
    st.markdown("### 🚨 REGISTROS COM PENDÊNCIAS IDENTIFICADAS")
    st.info("A identificação de pendência é baseada em: CPF nulo/zero ou Valor de Pagamento <= R$ 0,00.")
    
    if df_pendencias.empty:
        st.success("🎉 Nenhum registro com pendência de validação básica encontrado na seleção atual.")
    else:
        st.metric("Total de Pendências", len(df_pendencias))
        st.dataframe(df_pendencias[['Ordem', 'Nome', 'CPF', 'Valor Pagto', 'Data Pagto', 'Projeto', 'Gerenciadora', 'Pendencia']], 
                     use_container_width=True)
        
        st.markdown("---")
        
        st.markdown("### ⬇️ EXPORTAR LISTA DE PENDÊNCIAS")
        
        # Lógica de exportação para a lista de pendências (reutilizando a lógica do Ponto 5)
        pendencias_export_format = st.session_state['config']['formato_exportacao']
        
        data_to_download_pend = None
        mime_type_pend = None
        
        if pendencias_export_format == "Excel (.xlsx)":
            output_pend = BytesIO()
            try:
                with pd.ExcelWriter(output_pend, engine='openpyxl') as writer: 
                    df_pendencias.to_excel(writer, index=False, sheet_name='Pendências')
                data_to_download_pend = output_pend.getvalue()
                mime_type_pend = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            except ImportError:
                 st.error("O motor 'openpyxl' não está instalado. Por favor, exporte como CSV.")
                 pendencias_export_format = "CSV (.csv)" # Fallback
            
        elif pendencias_export_format == "CSV (.csv)":
            data_to_download_pend = df_pendencias.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')
            mime_type_pend = "text/csv"
        
        
        filename_pend = f"pendencias_smdet_pot_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if pendencias_export_format == "Excel (.xlsx)":
            filename_pend += ".xlsx"
        elif pendencias_export_format == "CSV (.csv)":
            filename_pend += ".csv"

        if data_to_download_pend is not None and mime_type_pend is not None:
             st.download_button(
                label=f"⬇️ EXPORTAR PENDÊNCIAS ({pendencias_export_format.split('(')[1][:-1].upper()})",
                data=data_to_download_pend,
                file_name=filename_pend,
                mime=mime_type_pend,
                type="secondary",
                use_container_width=True
            )

# ===========================================
# ⚙️ Aba Configurações
# ===========================================
with aba_config:
    st.markdown("### 🛠️ CONFIGURAÇÕES DE PROCESSAMENTO E EXIBIÇÃO")
    current_config = st.session_state['config']
    
    st.markdown("### ⚙️ OPÇÕES DE PROCESSAMENTO")
    
    col_p1, col_p2, col_p3 = st.columns(3)
    
    with col_p1:
        auto_validar = st.checkbox(
            "Validação automática de formato na carga",
            value=current_config['auto_validar'],
            help="Tenta corrigir automaticamente colunas de valor e data."
        )
        
    with col_p2:
        manter_historico = st.checkbox(
            "Manter histórico de filtros e ações",
            value=current_config['manter_historico'],
            help="Preserva o estado da sessão ao recarregar a página."
        )
        
    with col_p3:
        limite_registros = st.number_input(
            "Limite de registros para processamento:",
            min_value=1000,
            max_value=1000000,
            value=current_config['limite_registros'],
            step=1000,
            help="Define o número máximo de registros para processamento otimizado"
        )
    
    st.markdown("### 💾 OPÇÕES DE EXPORTAÇÃO")
    
    col_e1, col_e2 = st.columns(2)
    
    with col_e1:
        # CORREÇÃO PONTO 5: Removido PDF
        export_options = ["Excel (.xlsx)", "CSV (.csv)"]
        formato_exportacao = st.selectbox(
            "Formato padrão de exportação:",
            export_options,
            index=export_options.index(current_config['formato_exportacao']) if current_config['formato_exportacao'] in export_options else 0
        )
    
    with col_e2:
        incluir_graficos = st.checkbox(
            "Incluir gráficos nos relatórios (Opção desativada para exportação)",
            value=current_config['incluir_graficos'],
            disabled=True # Desabilitado pois o PDF foi removido
        )
    
    # Botão para salvar configurações
    if st.button("💾 SALVAR CONFIGURAÇÕES", type="primary", use_container_width=True):
        st.session_state['config'] = {
            'auto_validar': auto_validar,
            'manter_historico': manter_historico,
            'limite_registros': limite_registros,
            'formato_exportacao': formato_exportacao,
            'incluir_graficos': incluir_graficos
        }
        st.success("Configurações salvas com sucesso!")
