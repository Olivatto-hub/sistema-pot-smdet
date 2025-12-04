import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import warnings
import re
warnings.filterwarnings('ignore')

# ============================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================
st.set_page_config(
    page_title="Sistema POT-SMDET - Monitoramento Avançado",
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
        transform: translateY(-2px);
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    
    /* MÉTRICAS MAIS IMPACTANTES */
    [data-testid="stMetric"] {
        background-color: var(--background-color);
        padding: 15px;
        border-radius: 10px;
        border: 1px solid var(--border-color);
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.05);
    }
    
    .main-header {
        font-size: 2.5em;
        font-weight: 800;
        margin-bottom: 0.5em;
        text-align: center;
        color: var(--primary-color);
    }
</style>
""", unsafe_allow_html=True)

# ============================================
# INICIALIZAÇÃO DO ESTADO DA SESSÃO
# ============================================
if 'dataframes' not in st.session_state:
    st.session_state['dataframes'] = {}
if 'is_processed' not in st.session_state:
    st.session_state['is_processed'] = False
if 'config' not in st.session_state:
    st.session_state['config'] = {
        'auto_validar': True,
        'manter_historico': True,
        'limite_registros': 100000,
        'formato_exportacao': "Excel (.xlsx)",
        'incluir_graficos': True
    }


# ============================================
# FUNÇÕES DE PROCESSAMENTO E UTILIDADE
# ============================================

def clean_column_name(col):
    """Limpa e normaliza os nomes das colunas."""
    col = str(col).strip().upper()
    col = re.sub(r'[^A-Z0-9_]+', '', col)  # Remove caracteres especiais
    col = col.replace('CARTO', 'CARTAO')
    col = col.replace('AGENCIA', 'AGENCIA')
    col = col.replace('VLR DIA', 'VALOR_DIA')
    col = col.replace('DIAS', 'DIAS_VALIDOS')
    col = col.replace('MÊS', 'MES')
    col = col.replace('OBS', 'OBSERVACOES')
    col = col.replace('VALORTOTAL', 'VALOR_TOTAL')
    col = col.replace('VALORDESCONTO', 'VALOR_DESCONTO')
    col = col.replace('VALORPAGTO', 'VALOR_PAGAMENTO')
    return col.replace(' ', '_').replace('.', '')

@st.cache_data(show_spinner="Carregando e processando dados...")
def load_and_process_files(uploaded_files, limite_registros):
    """Carrega, limpa e concatena todos os arquivos de pendência."""
    dataframes = {}
    
    if not uploaded_files:
        return dataframes

    all_pendencias = []
    
    for file in uploaded_files:
        try:
            # Tenta ler CSV com delimitador ';'
            df = pd.read_csv(file, sep=';', encoding='latin1', on_bad_lines='skip', nrows=limite_registros)
            
            # Limpeza de nomes de colunas
            df.columns = [clean_column_name(col) for col in df.columns]
            
            # Padronização de colunas numéricas de valores
            value_cols = ['VALOR_TOTAL', 'VALOR_DESCONTO', 'VALOR_PAGAMENTO', 'VALOR_DIA']
            for col in value_cols:
                if col in df.columns:
                    # Tenta converter para numérico, tratando vírgulas como separador decimal
                    df[col] = df[col].astype(str).str.replace('.', '', regex=False).str.replace(',', '.', regex=False).str.replace(r'[^\d.]', '', regex=True)
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

            # Padronização de coluna Projeto e Nome
            if 'PROJETO' in df.columns:
                df['PROJETO'] = df['PROJETO'].astype(str).str.strip().str.upper()
            if 'NOME' in df.columns:
                df['NOME'] = df['NOME'].astype(str).str.strip().str.title()
                
            # Verifica se é um arquivo de Pendência
            is_pendencia = any(col in df.columns for col in ['VALOR_TOTAL', 'VALOR_PAGAMENTO'])
            
            if is_pendencia:
                # Adiciona o nome do arquivo para rastreamento
                df['ARQUIVO_ORIGEM'] = file.name
                all_pendencias.append(df)
            else:
                # Trata como arquivo de Cadastro/Corretivo (se houver necessidade)
                dataframes[file.name] = df
                
        except Exception as e:
            st.error(f"❌ Erro ao processar o arquivo {file.name}: {e}")
            
    if all_pendencias:
        # Concatena todas as pendências em um único DataFrame
        df_final = pd.concat(all_pendencias, ignore_index=True)
        # Cria uma coluna de status
        df_final['STATUS_PAGAMENTO'] = np.where(df_final['VALOR_PAGAMENTO'] > 0, 'PAGO', 'PENDENTE')
        dataframes['DADOS_CONSOLIDADOS_PENDENCIAS'] = df_final
        st.session_state['is_processed'] = True
    
    return dataframes


def create_download_link(df, filename, file_format):
    """Gera o link de download para o DataFrame."""
    if file_format == "CSV (.csv)":
        csv = df.to_csv(index=False, sep=';', encoding='latin1')
        return csv, "text/csv"
    
    elif file_format == "Excel (.xlsx)":
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Dados')
        return output.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    
    # PDF não é implementado aqui, mas o formato existe nas configurações.
    return None, None

# ============================================
# LAYOUT PRINCIPAL
# ============================================

st.markdown("<p class='main-header'>🏙️ POT-SMDET: Monitoramento de Projetos</p>", unsafe_allow_html=True)

# 1. SIDEBAR PARA CARREGAMENTO DE DADOS
with st.sidebar:
    st.markdown("### 📥 CARREGAMENTO DE DADOS")
    st.markdown("Selecione os arquivos de **Cadastro (.TXT)** e **Pendências (.CSV)**.")
    
    uploaded_files = st.file_uploader(
        "Arraste ou clique para carregar arquivos",
        type=['csv', 'txt'],
        accept_multiple_files=True
    )
    
    # Botão para processar os dados
    if st.button("🚀 PROCESSAR DADOS", type="primary", use_container_width=True):
        if uploaded_files:
            # Pega o limite de registros da configuração
            limite = st.session_state['config'].get('limite_registros', 100000)
            
            # Carrega e processa
            st.session_state['dataframes'] = load_and_process_files(uploaded_files, limite)
            
            if st.session_state['is_processed']:
                st.success(f"✅ {len(uploaded_files)} arquivos processados com sucesso! Dados consolidados disponíveis.")
            else:
                st.warning("⚠️ Arquivos carregados, mas não foi possível consolidar dados de pendências.")
        else:
            st.error("Por favor, carregue pelo menos um arquivo para processamento.")

    # Status e Limpeza
    st.markdown("---")
    st.markdown(f"**Arquivos Carregados:** {len(uploaded_files)}")
    
    if st.session_state['is_processed']:
        st.success("Dados prontos para análise!")
    else:
        st.info("Aguardando carregamento e processamento de dados...")
        
    if st.button("🗑️ LIMPAR DADOS CARREGADOS"):
        st.session_state['dataframes'] = {}
        st.session_state['is_processed'] = False
        st.cache_data.clear() # Limpa o cache para recarregar
        st.success("Dados e cache limpos. Recarregue a página se necessário.")
        st.experimental_rerun()
    
# 2. ABAS DO CONTEÚDO PRINCIPAL
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 DASHBOARD - VISÃO GERAL", 
    "📁 PROCESSAMENTO E EXPORTAÇÃO", 
    "🔍 ANÁLISE DE PENDÊNCIAS", 
    "⚙️ CONFIGURAÇÕES"
])

# ============================================
# ABA 1: DASHBOARD
# ============================================
with tab1:
    st.markdown("## 📊 Dashboard de Monitoramento")

    if not st.session_state['is_processed']:
        st.warning("Carregue e processe os arquivos na aba 'PROCESSAMENTO' ou na barra lateral para visualizar o Dashboard.")
    else:
        df_pendencias = st.session_state['dataframes'].get('DADOS_CONSOLIDADOS_PENDENCIAS')
        
        if df_pendencias is not None:
            total_registros = len(df_pendencias)
            total_projetos = df_pendencias['PROJETO'].nunique()
            
            # Cálculos de Métricas
            valor_total_bruto = df_pendencias['VALOR_TOTAL'].sum()
            valor_total_pago = df_pendencias['VALOR_PAGAMENTO'].sum()
            valor_total_desconto = df_pendencias['VALOR_DESCONTO'].sum()
            valor_pendente = valor_total_bruto - valor_total_pago - valor_total_desconto
            
            # --- Seção de Métricas Chave ---
            st.markdown("### Métricas Financeiras Consolidadas")
            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            
            with col_m1:
                st.metric(label="Valor Total Bruto", value=f"R$ {valor_total_bruto:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            with col_m2:
                st.metric(label="Valor Pago", value=f"R$ {valor_total_pago:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), delta=f"R$ {valor_total_pago:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), delta_color="inverse")
            with col_m3:
                st.metric(label="Valor de Desconto", value=f"R$ {valor_total_desconto:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            with col_m4:
                st.metric(label="Valor Pendente Estimado", value=f"R$ {valor_pendente:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), delta=f"R$ {valor_pendente:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), delta_color="inverse")
                
            st.markdown("---")
            
            # --- Seção de Distribuição de Projetos ---
            col_p1, col_p2 = st.columns(2)
            
            with col_p1:
                st.markdown("### Registros por Status de Pagamento")
                status_counts = df_pendencias['STATUS_PAGAMENTO'].value_counts().reset_index()
                status_counts.columns = ['Status', 'Contagem']
                fig_status = px.pie(
                    status_counts, 
                    values='Contagem', 
                    names='Status', 
                    title='Distribuição de Registros (Pendente vs. Pago)',
                    color='Status',
                    color_discrete_map={'PENDENTE':'#EF553B', 'PAGO':'#00CC96'} # Cores mais vibrantes
                )
                fig_status.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig_status, use_container_width=True)

            with col_p2:
                st.markdown("### Top 10 Projetos por Valor Total Bruto")
                proj_summary = df_pendencias.groupby('PROJETO')['VALOR_TOTAL'].sum().nlargest(10).reset_index()
                proj_summary.columns = ['Projeto', 'Valor']
                
                fig_proj = px.bar(
                    proj_summary, 
                    x='Projeto', 
                    y='Valor', 
                    title='Valores Totais por Projeto',
                    color='Valor',
                    color_continuous_scale=px.colors.sequential.Plotly3
                )
                fig_proj.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig_proj, use_container_width=True)
                
        else:
            st.warning("Nenhum dado consolidado de pendências encontrado. Verifique os arquivos carregados.")

# ============================================
# ABA 2: PROCESSAMENTO E EXPORTAÇÃO
# ============================================
with tab2:
    st.markdown("## 📁 Visão Geral dos Dados Carregados")

    if not st.session_state['is_processed']:
        st.info("Carregue e processe os dados na barra lateral para ver os detalhes e exportar.")
    else:
        st.success("Dados consolidados e prontos para inspeção!")
        
        df_pendencias = st.session_state['dataframes'].get('DADOS_CONSOLIDADOS_PENDENCIAS')

        if df_pendencias is not None:
            st.markdown(f"### DADOS CONSOLIDADOS DE PENDÊNCIAS ({len(df_pendencias):,} Registros)")
            st.dataframe(df_pendencias.head(100), use_container_width=True)
            
            st.markdown("### Exportação")
            export_format = st.session_state['config'].get('formato_exportacao', "Excel (.xlsx)")
            
            data_to_download, mime_type = create_download_link(df_pendencias, "dados_consolidados", export_format)

            if data_to_download and mime_type:
                st.download_button(
                    label=f"⬇️ BAIXAR DADOS CONSOLIDADOS ({export_format})",
                    data=data_to_download,
                    file_name=f"Dados_Consolidados_POT_{datetime.now().strftime('%Y%m%d')}.{'xlsx' if export_format.startswith('Excel') else 'csv'}",
                    mime=mime_type,
                    type="primary",
                    use_container_width=True
                )
            elif export_format == "PDF (.pdf)":
                st.warning("A exportação para PDF é uma funcionalidade futura (com inclusão de gráficos, conforme configurado). Por favor, use Excel ou CSV.")

        # Exibe outros arquivos carregados (Cadastro/Corretivos)
        other_files = {k: v for k, v in st.session_state['dataframes'].items() if k != 'DADOS_CONSOLIDADOS_PENDENCIAS'}
        if other_files:
            st.markdown("### Outros Arquivos (Cadastro/Corretivos)")
            for name, df in other_files.items():
                with st.expander(f"Mostrar {name} ({len(df):,} registros)"):
                    st.dataframe(df.head(), use_container_width=True)


# ============================================
# ABA 3: ANÁLISE DE PENDÊNCIAS
# ============================================
with tab3:
    st.markdown("## 🔍 Análise Detalhada de Pendências")

    if not st.session_state['is_processed'] or st.session_state['dataframes'].get('DADOS_CONSOLIDADOS_PENDENCIAS') is None:
        st.warning("Carregue e processe os dados consolidados de pendências para iniciar a análise.")
    else:
        df_pendencias = st.session_state['dataframes']['DADOS_CONSOLIDADOS_PENDENCIAS']
        
        # Filtros Interativos (Melhoria de UX)
        st.markdown("### 🛠️ Filtros de Análise")
        
        col_f1, col_f2 = st.columns(2)
        
        with col_f1:
            all_projects = ['Todos'] + sorted(df_pendencias['PROJETO'].unique().tolist())
            selected_project = st.selectbox("Filtrar por Projeto:", all_projects)

        with col_f2:
            all_status = ['Todos', 'PAGO', 'PENDENTE']
            selected_status = st.selectbox("Filtrar por Status de Pagamento:", all_status)
            
        # Aplica Filtros
        df_filtered = df_pendencias.copy()
        
        if selected_project != 'Todos':
            df_filtered = df_filtered[df_filtered['PROJETO'] == selected_project]
            
        if selected_status != 'Todos':
            df_filtered = df_filtered[df_filtered['STATUS_PAGAMENTO'] == selected_status]

        st.markdown("---")
        st.markdown(f"### Resultados da Análise: {len(df_filtered):,} Registros Filtrados")
        
        if len(df_filtered) == 0:
            st.info("Nenhum registro encontrado com os filtros selecionados.")
        else:
            # 1. Novas Métricas Filtradas
            col_fa1, col_fa2, col_fa3, col_fa4 = st.columns(4)
            with col_fa1:
                st.metric(label="Valor Total (Filtrado)", value=f"R$ {df_filtered['VALOR_TOTAL'].sum():,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            with col_fa2:
                st.metric(label="Valor Pago (Filtrado)", value=f"R$ {df_filtered['VALOR_PAGAMENTO'].sum():,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            with col_fa3:
                st.metric(label="Valor Pendente (Filtrado)", value=f"R$ {(df_filtered['VALOR_TOTAL'] - df_filtered['VALOR_PAGAMENTO'] - df_filtered['VALOR_DESCONTO']).sum():,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            with col_fa4:
                st.metric(label="Total de Pessoas Únicas", value=f"{df_filtered['NOME'].nunique()}")
                
            st.markdown("---")
            
            # 2. Tabela Detalhada (Top 100)
            st.markdown("### Amostra Detalhada (Primeiros 100)")
            st.dataframe(df_filtered.head(100), use_container_width=True)
            
            # 3. Gráfico de Agências/Distritos
            st.markdown("### Distribuição de Pendências por Agência/Distrito")
            
            if 'AGENCIA' in df_filtered.columns:
                agency_counts = df_filtered['AGENCIA'].value_counts().reset_index()
                agency_counts.columns = ['Agencia', 'Contagem']
                
                fig_agency = px.bar(
                    agency_counts.nlargest(15, 'Contagem'), 
                    x='Agencia', 
                    y='Contagem', 
                    color='Contagem',
                    title='Top 15 Agências/Distritos com Pendências',
                    color_continuous_scale=px.colors.sequential.Viridis
                )
                fig_agency.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig_agency, use_container_width=True)
            else:
                st.info("Coluna 'AGENCIA' não encontrada para esta visualização.")


# ============================================
# ABA 4: CONFIGURAÇÕES (MANTIDAS E SALVAS)
# ============================================
with tab4:
    st.markdown("## ⚙️ Configurações do Sistema (Funcionalidade Mantida)")
    
    current_config = st.session_state['config']

    st.markdown("### 🔧 OPÇÕES DE PROCESSAMENTO")
    col_p1, col_p2, col_p3 = st.columns(3)
    
    with col_p1:
        auto_validar = st.checkbox(
            "Validação automática ao carregar",
            value=current_config['auto_validar'],
            help="Executa validação automática após carregar dados"
        )
        
    with col_p2:
        manter_historico = st.checkbox(
            "Manter histórico de alterações",
            value=current_config['manter_historico'],
            help="Armazena histórico de modificações nos dados"
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
        formato_exportacao = st.selectbox(
            "Formato padrão de exportação:",
            ["Excel (.xlsx)", "CSV (.csv)", "PDF (.pdf)"],
            index=["Excel (.xlsx)", "CSV (.csv)", "PDF (.pdf)"].index(current_config['formato_exportacao'])
        )
    
    with col_e2:
        incluir_graficos = st.checkbox(
            "Incluir gráficos nos relatórios (Exportação PDF)",
            value=current_config['incluir_graficos']
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
        st.success("✅ Configurações salvas com sucesso!")

# ============================================
# FIM DO APLICATIVO
# ============================================
