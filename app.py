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
    page_title="SMDET - POT Monitoramento de Pagamento de Benefícios",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================
# CSS PERSONALIZADO
# ============================================
st.markdown("""
<style>
    /* TÍTULO PRINCIPAL */
    .main-header {
        font-size: 2.2em;
        font-weight: 800;
        margin-bottom: 0.5em;
        text-align: center;
        color: #1E3A8A;
        padding-bottom: 10px;
        border-bottom: 3px solid #1E3A8A;
    }
    
    /* MÉTRICAS */
    [data-testid="stMetric"] {
        background-color: #f8f9fa;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #dee2e6;
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.05);
    }
    
    [data-testid="stMetricValue"] {
        font-size: 1.5em !important;
        font-weight: 700 !important;
    }
    
    /* BOTÕES */
    .stButton > button {
        border-radius: 6px;
        font-weight: 600;
        transition: all 0.3s ease;
        padding: 0.75rem 1rem;
        border: 1px solid #1E3A8A;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(30, 58, 138, 0.2);
    }
    
    .stButton > button:first-of-type {
        background-color: #1E3A8A;
        color: white;
    }
    
    /* TABELAS */
    .stDataFrame {
        border-radius: 8px;
        overflow: hidden;
        border: 1px solid #dee2e6;
    }
    
    /* ABAS */
    .stTabs [data-baseweb="tab-list"] {
        gap: 2px;
    }
    
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #f8f9fa;
        border-radius: 4px 4px 0px 0px;
        gap: 1px;
        padding-top: 10px;
        padding-bottom: 10px;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: #1E3A8A;
        color: white;
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
    col = re.sub(r'[^A-Z0-9_ÁÉÍÓÚÀÈÌÒÙÃÕÇ ]+', '', col)
    
    # Mapeamento de substituições
    replacements = {
        'CARTO': 'CARTAO',
        'CARTÃO': 'CARTAO',
        'AGENCIA': 'AGENCIA',
        'AGÊNCIA': 'AGENCIA',
        'VLR DIA': 'VALOR_DIA',
        'VL DIA': 'VALOR_DIA',
        'DIAS': 'DIAS_VALIDOS',
        'MÊS': 'MES',
        'OBS': 'OBSERVACOES',
        'VALORTOTAL': 'VALOR_TOTAL',
        'VALORDESCONTO': 'VALOR_DESCONTO',
        'VALORPAGTO': 'VALOR_PAGAMENTO',
        'VALOR PAGAMENTO': 'VALOR_PAGAMENTO',
        'VALOR PAGTO': 'VALOR_PAGAMENTO',
        'PAGAMENTO': 'VALOR_PAGAMENTO',
        'VLR PAGTO': 'VALOR_PAGAMENTO',
        'VLR PAGAMENTO': 'VALOR_PAGAMENTO'
    }
    
    for old, new in replacements.items():
        col = col.replace(old, new)
    
    return col.replace(' ', '_').replace('.', '').replace('__', '_')

def formatar_valor_brl(valor):
    """Formata valor para Real Brasileiro."""
    try:
        valor = float(valor)
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "R$ 0,00"

@st.cache_data(show_spinner="Carregando e processando dados...")
def load_and_process_files(uploaded_files, limite_registros):
    """Carrega, limpa e concatena todos os arquivos de pendência."""
    dataframes = {}
    
    if not uploaded_files:
        return dataframes

    all_pendencias = []
    
    for file in uploaded_files:
        try:
            # Detecta extensão e lê arquivo apropriadamente
            file_extension = file.name.lower().split('.')[-1]
            
            if file_extension == 'csv':
                # Tenta diferentes encodings e delimitadores
                try:
                    df = pd.read_csv(file, sep=';', encoding='utf-8', on_bad_lines='skip', nrows=limite_registros)
                except:
                    try:
                        df = pd.read_csv(file, sep=';', encoding='latin1', on_bad_lines='skip', nrows=limite_registros)
                    except:
                        df = pd.read_csv(file, sep=',', encoding='utf-8', on_bad_lines='skip', nrows=limite_registros)
            
            elif file_extension == 'txt':
                try:
                    df = pd.read_csv(file, sep='\t', encoding='utf-8', on_bad_lines='skip', nrows=limite_registros)
                except:
                    df = pd.read_csv(file, sep=';', encoding='latin1', on_bad_lines='skip', nrows=limite_registros)
            else:
                st.error(f"Formato não suportado: {file.name}")
                continue
            
            # Limpeza de nomes de colunas
            df.columns = [clean_column_name(col) for col in df.columns]
            
            # Padronização de colunas numéricas - CORREÇÃO DO PROBLEMA DE DUPLICAÇÃO
            value_cols = ['VALOR_TOTAL', 'VALOR_DESCONTO', 'VALOR_PAGAMENTO', 'VALOR_DIA']
            
            for col in value_cols:
                if col in df.columns:
                    # Converte para string e limpa
                    df[col] = df[col].astype(str)
                    
                    # Remove caracteres não numéricos exceto ponto e vírgula
                    df[col] = df[col].str.replace('R\$', '', regex=False)
                    df[col] = df[col].str.replace(' ', '', regex=False)
                    
                    # Verifica se já está no formato numérico correto
                    try:
                        # Tenta converter diretamente
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    except:
                        # Se falhar, tenta converter de formato BR
                        # Primeiro verifica se tem ponto como separador de milhar
                        if df[col].str.contains('\.\d{3}$', na=False).any():
                            # Remove pontos de milhar e substitui vírgula por ponto decimal
                            df[col] = df[col].str.replace('.', '', regex=False)
                            df[col] = df[col].str.replace(',', '.', regex=False)
                        else:
                            # Já está com ponto como decimal ou sem separadores
                            df[col] = df[col].str.replace(',', '.', regex=False)
                        
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    
                    df[col] = df[col].fillna(0)
                    
                    # VERIFICAÇÃO DE DUPLICAÇÃO - CORREÇÃO CRÍTICA
                    # Se os valores parecem muito altos, divide por 100 (caso estejam com 2 decimais extras)
                    if df[col].mean() > 1000000:  # Se a média for maior que 1 milhão
                        # Verifica se pode ser um problema de casas decimais
                        sample_val = df[col].iloc[0] if len(df) > 0 else 0
                        if sample_val > 1000 and str(sample_val)[-2:] == '00':
                            # Possível duplicação de casas decimais
                            df[col] = df[col] / 100

            # Padronização de coluna Projeto e Nome
            if 'PROJETO' in df.columns:
                df['PROJETO'] = df['PROJETO'].astype(str).str.strip().str.upper()
                df['PROJETO'] = df['PROJETO'].str.replace(r'\s+', ' ', regex=True)  # Remove múltiplos espaços
            
            if 'NOME' in df.columns:
                df['NOME'] = df['NOME'].astype(str).str.strip().str.title()
                df['NOME'] = df['NOME'].str.replace(r'\s+', ' ', regex=True)
                
            # Verifica se é um arquivo de Pendência
            is_pendencia = any(col in df.columns for col in ['VALOR_TOTAL', 'VALOR_PAGAMENTO', 'VALOR_PAGTO'])
            
            if is_pendencia:
                # Adiciona o nome do arquivo para rastreamento
                df['ARQUIVO_ORIGEM'] = file.name
                df['DATA_CARREGAMENTO'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                all_pendencias.append(df)
            else:
                # Trata como arquivo de Cadastro/Corretivo
                dataframes[file.name] = df
                
        except Exception as e:
            st.error(f"❌ Erro ao processar o arquivo {file.name}: {str(e)[:200]}")
            
    if all_pendencias:
        # Concatena todas as pendências em um único DataFrame
        df_final = pd.concat(all_pendencias, ignore_index=True)
        
        # Remove duplicatas baseado em colunas-chave (se existirem)
        colunas_chave = []
        for col in ['CODIGO', 'CPF', 'MATRICULA', 'NOME', 'PROJETO', 'VALOR_TOTAL']:
            if col in df_final.columns:
                colunas_chave.append(col)
        
        if len(colunas_chave) > 0:
            df_final = df_final.drop_duplicates(subset=colunas_chave, keep='first')
        
        # Cria uma coluna de status
        if 'VALOR_PAGAMENTO' in df_final.columns:
            df_final['STATUS_PAGAMENTO'] = np.where(df_final['VALOR_PAGAMENTO'] > 0, 'PAGO', 'PENDENTE')
        else:
            df_final['STATUS_PAGAMENTO'] = 'PENDENTE'
            
        # Calcula valor pendente
        if all(col in df_final.columns for col in ['VALOR_TOTAL', 'VALOR_PAGAMENTO', 'VALOR_DESCONTO']):
            df_final['VALOR_PENDENTE'] = df_final['VALOR_TOTAL'] - df_final['VALOR_PAGAMENTO'] - df_final['VALOR_DESCONTO'].fillna(0)
        elif 'VALOR_TOTAL' in df_final.columns and 'VALOR_PAGAMENTO' in df_final.columns:
            df_final['VALOR_PENDENTE'] = df_final['VALOR_TOTAL'] - df_final['VALOR_PAGAMENTO']
        else:
            df_final['VALOR_PENDENTE'] = 0
            
        dataframes['DADOS_CONSOLIDADOS_PENDENCIAS'] = df_final
        st.session_state['is_processed'] = True
    
    return dataframes

def create_download_link(df, filename, file_format):
    """Gera o link de download para o DataFrame."""
    try:
        if file_format == "CSV (.csv)":
            csv = df.to_csv(index=False, sep=';', encoding='latin1')
            return csv, "text/csv"
        
        elif file_format == "Excel (.xlsx)":
            output = BytesIO()
            # Usa openpyxl em vez de xlsxwriter para evitar dependência extra
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Dados_Consolidados')
            return output.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        
        return None, None
    except Exception as e:
        st.error(f"Erro ao criar arquivo de download: {str(e)}")
        return None, None

# ============================================
# LAYOUT PRINCIPAL
# ============================================

st.markdown("<p class='main-header'>💰 SMDET - POT Monitoramento de Pagamento de Benefícios</p>", unsafe_allow_html=True)

# 1. SIDEBAR PARA CARREGAMENTO DE DADOS
with st.sidebar:
    st.markdown("### 📥 CARREGAMENTO DE DADOS")
    st.markdown("Selecione os arquivos de **Cadastro (.TXT)** e **Pagamentos (.CSV)**.")
    
    uploaded_files = st.file_uploader(
        "Arraste ou clique para carregar arquivos",
        type=['csv', 'txt'],
        accept_multiple_files=True,
        help="Formatos aceitos: CSV (separador ; ou ,) e TXT (tab ou ;)"
    )
    
    # Botão para processar os dados
    if st.button("🚀 PROCESSAR DADOS", type="primary", use_container_width=True):
        if uploaded_files:
            with st.spinner("Processando arquivos..."):
                # Pega o limite de registros da configuração
                limite = st.session_state['config'].get('limite_registros', 100000)
                
                # Carrega e processa
                st.session_state['dataframes'] = load_and_process_files(uploaded_files, limite)
                
                if st.session_state['is_processed']:
                    st.success(f"✅ {len(uploaded_files)} arquivo(s) processado(s) com sucesso!")
                    
                    # Mostra estatísticas rápidas
                    df_pendencias = st.session_state['dataframes'].get('DADOS_CONSOLIDADOS_PENDENCIAS')
                    if df_pendencias is not None:
                        st.info(f"""
                        **Resumo do Processamento:**
                        - Registros: {len(df_pendencias):,}
                        - Projetos: {df_pendencias['PROJETO'].nunique()}
                        - Valor Total: {formatar_valor_brl(df_pendencias['VALOR_TOTAL'].sum())}
                        """)
                else:
                    st.warning("⚠️ Arquivos carregados, mas não foram identificados dados de pagamentos.")
        else:
            st.error("Por favor, carregue pelo menos um arquivo para processamento.")

    # Status e Limpeza
    st.markdown("---")
    st.markdown(f"**Arquivos Carregados:** {len(uploaded_files)}")
    
    if st.session_state['is_processed']:
        st.success("✅ Dados processados e prontos!")
    else:
        st.info("⏳ Aguardando carregamento de dados...")
        
    if st.button("🗑️ LIMPAR DADOS CARREGADOS", use_container_width=True):
        st.session_state['dataframes'] = {}
        st.session_state['is_processed'] = False
        st.cache_data.clear()
        st.rerun()
    
    # Informações do sistema
    st.markdown("---")
    st.markdown("### ℹ️ Sobre o Sistema")
    st.markdown("""
    **SMDET - POT**  
    Sistema de Monitoramento de  
    Pagamento de Benefícios
    
    **Funcionalidades:**
    - Dashboard de métricas
    - Análise de pagamentos
    - Exportação de relatórios
    - Filtros personalizados
    """)

# ============================================
# ABAS PRINCIPAIS
# ============================================
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 DASHBOARD - VISÃO GERAL", 
    "📁 DADOS E EXPORTAÇÃO", 
    "🔍 ANÁLISE DETALHADA", 
    "⚙️ CONFIGURAÇÕES"
])

# ============================================
# ABA 1: DASHBOARD
# ============================================
with tab1:
    st.markdown("## 📊 Dashboard de Monitoramento de Pagamentos")

    if not st.session_state['is_processed']:
        st.warning("Carregue e processe os arquivos na barra lateral para visualizar o Dashboard.")
    else:
        df_pendencias = st.session_state['dataframes'].get('DADOS_CONSOLIDADOS_PENDENCIAS')
        
        if df_pendencias is not None:
            # Cálculos de Métricas
            total_registros = len(df_pendencias)
            total_projetos = df_pendencias['PROJETO'].nunique()
            quantidade_pagamentos = df_pendencias['VALOR_PAGAMENTO'].count() if 'VALOR_PAGAMENTO' in df_pendencias.columns else 0
            valor_total_pago = df_pendencias['VALOR_PAGAMENTO'].sum() if 'VALOR_PAGAMENTO' in df_pendencias.columns else 0
            valor_total_desconto = df_pendencias['VALOR_DESCONTO'].sum() if 'VALOR_DESCONTO' in df_pendencias.columns else 0
            valor_pendente = (df_pendencias['VALOR_TOTAL'].sum() - valor_total_pago - valor_total_desconto) if 'VALOR_TOTAL' in df_pendencias.columns else 0
            
            # --- Seção de Métricas Chave ---
            st.markdown("### Métricas Financeiras Consolidadas")
            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            
            with col_m1:
                st.metric(
                    label="Quantidade de Pagamentos", 
                    value=f"{quantidade_pagamentos:,}",
                    help="Total de registros de pagamento processados"
                )
            with col_m2:
                st.metric(
                    label="Valor Total Pago", 
                    value=formatar_valor_brl(valor_total_pago),
                    delta=formatar_valor_brl(valor_total_pago),
                    delta_color="normal",
                    help="Soma de todos os valores pagos"
                )
            with col_m3:
                st.metric(
                    label="Valor de Descontos", 
                    value=formatar_valor_brl(valor_total_desconto),
                    help="Total de descontos aplicados"
                )
            with col_m4:
                st.metric(
                    label="Valor Pendente", 
                    value=formatar_valor_brl(valor_pendente),
                    delta=formatar_valor_brl(valor_pendente),
                    delta_color="inverse",
                    help="Valor total pendente de pagamento"
                )
                
            st.markdown("---")
            
            # --- Seção de Distribuição ---
            col_p1, col_p2 = st.columns(2)
            
            with col_p1:
                st.markdown("### Registros por Status de Pagamento")
                if 'STATUS_PAGAMENTO' in df_pendencias.columns:
                    status_counts = df_pendencias['STATUS_PAGAMENTO'].value_counts().reset_index()
                    status_counts.columns = ['Status', 'Contagem']
                    
                    fig_status = px.pie(
                        status_counts, 
                        values='Contagem', 
                        names='Status', 
                        title='Distribuição de Status de Pagamento',
                        color='Status',
                        color_discrete_map={'PENDENTE':'#EF553B', 'PAGO':'#00CC96'},
                        hole=0.3
                    )
                    fig_status.update_traces(
                        textposition='inside', 
                        textinfo='percent+label',
                        textfont_size=14
                    )
                    fig_status.update_layout(
                        showlegend=True,
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                    )
                    st.plotly_chart(fig_status, use_container_width=True)
                else:
                    st.info("Coluna 'STATUS_PAGAMENTO' não encontrada.")

            with col_p2:
                st.markdown("### Valores Totais por Projeto")
                if 'PROJETO' in df_pendencias.columns and 'VALOR_TOTAL' in df_pendencias.columns:
                    proj_summary = df_pendencias.groupby('PROJETO')['VALOR_TOTAL'].sum().reset_index()
                    proj_summary = proj_summary.sort_values('VALOR_TOTAL', ascending=False)
                    proj_summary.columns = ['Projeto', 'Valor Total']
                    
                    fig_proj = px.bar(
                        proj_summary, 
                        x='Projeto', 
                        y='Valor Total', 
                        title='Valor Total por Projeto',
                        color='Valor Total',
                        color_continuous_scale=px.colors.sequential.Blues,
                        text_auto='.2s'
                    )
                    fig_proj.update_layout(
                        xaxis_tickangle=-45,
                        xaxis_title="Projeto",
                        yaxis_title="Valor Total (R$)",
                        showlegend=False
                    )
                    fig_proj.update_traces(
                        texttemplate='R$ %{value:,.0f}',
                        textposition='outside'
                    )
                    st.plotly_chart(fig_proj, use_container_width=True)
                else:
                    st.info("Dados insuficientes para gráfico de projetos.")
            
            # --- Seção de Tabela Resumo ---
            st.markdown("---")
            st.markdown("### Resumo por Projeto")
            
            if 'PROJETO' in df_pendencias.columns:
                resumo_projetos = df_pendencias.groupby('PROJETO').agg({
                    'NOME': 'count',
                    'VALOR_TOTAL': 'sum',
                    'VALOR_PAGAMENTO': 'sum',
                    'VALOR_PENDENTE': 'sum',
                    'STATUS_PAGAMENTO': lambda x: (x == 'PAGO').sum()
                }).reset_index()
                
                resumo_projetos.columns = ['Projeto', 'Qtd Beneficiários', 'Valor Total', 'Valor Pago', 'Valor Pendente', 'Qtd Pagos']
                resumo_projetos['% Pago'] = (resumo_projetos['Valor Pago'] / resumo_projetos['Valor Total'] * 100).round(2)
                resumo_projetos = resumo_projetos.sort_values('Valor Total', ascending=False)
                
                # Formata valores
                for col in ['Valor Total', 'Valor Pago', 'Valor Pendente']:
                    resumo_projetos[col] = resumo_projetos[col].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                
                st.dataframe(resumo_projetos, use_container_width=True)
                
        else:
            st.warning("Nenhum dado consolidado encontrado. Verifique os arquivos carregados.")

# ============================================
# ABA 2: DADOS E EXPORTAÇÃO
# ============================================
with tab2:
    st.markdown("## 📁 Dados Carregados e Exportação")

    if not st.session_state['is_processed']:
        st.info("Carregue e processe os dados na barra lateral para ver os detalhes e exportar.")
    else:
        st.success("Dados consolidados e prontos para inspeção e exportação!")
        
        df_pendencias = st.session_state['dataframes'].get('DADOS_CONSOLIDADOS_PENDENCIAS')

        if df_pendencias is not None:
            st.markdown(f"### 📊 Dados Consolidados de Pagamentos ({len(df_pendencias):,} registros)")
            
            # Mostrar estatísticas rápidas
            col_stats1, col_stats2, col_stats3 = st.columns(3)
            with col_stats1:
                st.metric("Total de Registros", f"{len(df_pendencias):,}")
            with col_stats2:
                st.metric("Projetos Únicos", f"{df_pendencias['PROJETO'].nunique():,}")
            with col_stats3:
                st.metric("Valor Total", formatar_valor_brl(df_pendencias['VALOR_TOTAL'].sum()))
            
            # Visualização dos dados
            with st.expander("🔍 Visualizar Dados Consolidados (Primeiros 500 registros)", expanded=False):
                st.dataframe(df_pendencias.head(500), use_container_width=True)
            
            st.markdown("---")
            st.markdown("### 💾 Exportação de Dados")
            
            # Opções de exportação
            col_exp1, col_exp2 = st.columns(2)
            
            with col_exp1:
                export_format = st.selectbox(
                    "Selecione o formato de exportação:",
                    ["Excel (.xlsx)", "CSV (.csv)"],
                    index=0
                )
            
            with col_exp2:
                # Filtro para exportação
                if 'PROJETO' in df_pendencias.columns:
                    projetos_export = ['Todos'] + sorted(df_pendencias['PROJETO'].unique().tolist())
                    projeto_selecionado = st.selectbox(
                        "Exportar dados do projeto:",
                        projetos_export
                    )
                    
                    if projeto_selecionado != 'Todos':
                        df_export = df_pendencias[df_pendencias['PROJETO'] == projeto_selecionado]
                        nome_arquivo = f"Dados_{projeto_selecionado}_{datetime.now().strftime('%Y%m%d')}"
                    else:
                        df_export = df_pendencias
                        nome_arquivo = f"Dados_Consolidados_{datetime.now().strftime('%Y%m%d')}"
                else:
                    df_export = df_pendencias
                    nome_arquivo = f"Dados_Consolidados_{datetime.now().strftime('%Y%m%d')}"
            
            # Botão de download
            if st.button("⬇️ BAIXAR DADOS", type="primary", use_container_width=True):
                with st.spinner("Gerando arquivo para download..."):
                    data_to_download, mime_type = create_download_link(df_export, nome_arquivo, export_format)
                    
                    if data_to_download and mime_type:
                        extensao = 'xlsx' if export_format.startswith('Excel') else 'csv'
                        st.download_button(
                            label=f"💾 CLIQUE PARA BAIXAR ({export_format})",
                            data=data_to_download,
                            file_name=f"{nome_arquivo}.{extensao}",
                            mime=mime_type,
                            type="primary",
                            use_container_width=True
                        )
                        st.success("✅ Arquivo gerado com sucesso! Clique no botão acima para baixar.")
                    else:
                        st.error("❌ Erro ao gerar arquivo para download.")

        # Exibe outros arquivos carregados
        other_files = {k: v for k, v in st.session_state['dataframes'].items() if k != 'DADOS_CONSOLIDADOS_PENDENCIAS'}
        if other_files:
            st.markdown("---")
            st.markdown("### 📄 Outros Arquivos Carregados")
            
            for name, df in other_files.items():
                with st.expander(f"📋 {name} ({len(df):,} registros)"):
                    st.dataframe(df.head(), use_container_width=True)
                    
                    # Botão de download para arquivos individuais
                    col_dl1, col_dl2 = st.columns(2)
                    with col_dl1:
                        if st.button(f"Baixar {name} como CSV", key=f"csv_{name}"):
                            csv = df.to_csv(index=False, sep=';', encoding='latin1')
                            st.download_button(
                                label="Clique para baixar CSV",
                                data=csv,
                                file_name=f"{name.replace('.', '_')}.csv",
                                mime="text/csv",
                                key=f"dl_csv_{name}"
                            )
                    
                    with col_dl2:
                        if st.button(f"Baixar {name} como Excel", key=f"excel_{name}"):
                            output = BytesIO()
                            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                                df.to_excel(writer, index=False, sheet_name='Dados')
                            st.download_button(
                                label="Clique para baixar Excel",
                                data=output.getvalue(),
                                file_name=f"{name.replace('.', '_')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key=f"dl_excel_{name}"
                            )

# ============================================
# ABA 3: ANÁLISE DETALHADA
# ============================================
with tab3:
    st.markdown("## 🔍 Análise Detalhada de Pagamentos")

    if not st.session_state['is_processed'] or st.session_state['dataframes'].get('DADOS_CONSOLIDADOS_PENDENCIAS') is None:
        st.warning("Carregue e processe os dados consolidados para iniciar a análise.")
    else:
        df_pendencias = st.session_state['dataframes']['DADOS_CONSOLIDADOS_PENDENCIAS']
        
        # Filtros Interativos
        st.markdown("### 🛠️ Filtros para Análise")
        
        col_f1, col_f2, col_f3 = st.columns(3)
        
        with col_f1:
            # Filtro por Projeto
            all_projects = ['Todos'] + sorted(df_pendencias['PROJETO'].unique().tolist())
            selected_project = st.selectbox("Filtrar por Projeto:", all_projects)

        with col_f2:
            # Filtro por Status
            all_status = ['Todos', 'PAGO', 'PENDENTE']
            selected_status = st.selectbox("Filtrar por Status:", all_status)
            
        with col_f3:
            # Filtro por Valor
            min_val = float(df_pendencias['VALOR_TOTAL'].min()) if 'VALOR_TOTAL' in df_pendencias.columns else 0
            max_val = float(df_pendencias['VALOR_TOTAL'].max()) if 'VALOR_TOTAL' in df_pendencias.columns else 10000
            valor_range = st.slider(
                "Filtrar por Valor Total:",
                min_value=float(min_val),
                max_value=float(max_val),
                value=(float(min_val), float(max_val)),
                help="Selecione a faixa de valores para filtrar"
            )
        
        # Aplica Filtros
        df_filtered = df_pendencias.copy()
        
        if selected_project != 'Todos':
            df_filtered = df_filtered[df_filtered['PROJETO'] == selected_project]
            
        if selected_status != 'Todos':
            df_filtered = df_filtered[df_filtered['STATUS_PAGAMENTO'] == selected_status]
            
        # Filtro por valor
        if 'VALOR_TOTAL' in df_filtered.columns:
            df_filtered = df_filtered[
                (df_filtered['VALOR_TOTAL'] >= valor_range[0]) & 
                (df_filtered['VALOR_TOTAL'] <= valor_range[1])
            ]

        st.markdown("---")
        st.markdown(f"### 📈 Resultados da Análise: {len(df_filtered):,} Registros Filtrados")
        
        if len(df_filtered) == 0:
            st.info("Nenhum registro encontrado com os filtros selecionados.")
        else:
            # Métricas Filtradas
            col_fa1, col_fa2, col_fa3, col_fa4 = st.columns(4)
            with col_fa1:
                st.metric(
                    label="Registros Filtrados", 
                    value=f"{len(df_filtered):,}",
                    delta=f"{len(df_filtered) - len(df_pendencias):,}" if len(df_filtered) != len(df_pendencias) else None
                )
            with col_fa2:
                st.metric(
                    label="Valor Total Filtrado", 
                    value=formatar_valor_brl(df_filtered['VALOR_TOTAL'].sum())
                )
            with col_fa3:
                st.metric(
                    label="Valor Pago Filtrado", 
                    value=formatar_valor_brl(df_filtered['VALOR_PAGAMENTO'].sum() if 'VALOR_PAGAMENTO' in df_filtered.columns else 0)
                )
            with col_fa4:
                st.metric(
                    label="Beneficiários Únicos", 
                    value=f"{df_filtered['NOME'].nunique() if 'NOME' in df_filtered.columns else 0:,}"
                )
            
            st.markdown("---")
            
            # Visualização dos Dados Filtrados
            st.markdown("### 📋 Dados Detalhados Filtrados")
            
            # Seleção de colunas para exibição
            todas_colunas = list(df_filtered.columns)
            colunas_padrao = ['NOME', 'PROJETO', 'VALOR_TOTAL', 'VALOR_PAGAMENTO', 'STATUS_PAGAMENTO', 'VALOR_PENDENTE']
            colunas_disponiveis = [col for col in colunas_padrao if col in todas_colunas]
            
            colunas_selecionadas = st.multiselect(
                "Selecione as colunas para exibir:",
                todas_colunas,
                default=colunas_disponiveis
            )
            
            if colunas_selecionadas:
                df_exibir = df_filtered[colunas_selecionadas]
                
                # Paginação
                registros_por_pagina = 100
                total_paginas = max(1, len(df_exibir) // registros_por_pagina + (1 if len(df_exibir) % registros_por_pagina > 0 else 0))
                
                pagina_atual = st.number_input(
                    "Página:",
                    min_value=1,
                    max_value=total_paginas,
                    value=1,
                    step=1
                )
                
                inicio = (pagina_atual - 1) * registros_por_pagina
                fim = min(inicio + registros_por_pagina, len(df_exibir))
                
                st.dataframe(df_exibir.iloc[inicio:fim], use_container_width=True)
                st.caption(f"Mostrando registros {inicio+1} a {fim} de {len(df_exibir):,} ({pagina_atual}/{total_paginas})")
            
            # Gráficos de Análise
            st.markdown("---")
            st.markdown("### 📊 Análise Visual dos Dados Filtrados")
            
            col_g1, col_g2 = st.columns(2)
            
            with col_g1:
                if 'AGENCIA' in df_filtered.columns and len(df_filtered) > 0:
                    st.markdown("#### Distribuição por Agência")
                    agency_counts = df_filtered['AGENCIA'].value_counts().reset_index()
                    agency_counts.columns = ['Agência', 'Quantidade']
                    
                    fig_agency = px.bar(
                        agency_counts.head(20), 
                        x='Agência', 
                        y='Quantidade',
                        title='Top 20 Agências por Quantidade',
                        color='Quantidade',
                        color_continuous_scale=px.colors.sequential.Plasma
                    )
                    fig_agency.update_layout(xaxis_tickangle=-45)
                    st.plotly_chart(fig_agency, use_container_width=True)
                else:
                    st.info("Coluna 'AGENCIA' não encontrada para análise.")
            
            with col_g2:
                if 'PROJETO' in df_filtered.columns and len(df_filtered) > 0:
                    st.markdown("#### Distribuição de Valores por Projeto")
                    projeto_valores = df_filtered.groupby('PROJETO')['VALOR_TOTAL'].sum().nlargest(15).reset_index()
                    projeto_valores.columns = ['Projeto', 'Valor Total']
                    
                    fig_valores = px.bar(
                        projeto_valores,
                        x='Projeto',
                        y='Valor Total',
                        title='Top 15 Projetos por Valor Total',
                        color='Valor Total',
                        color_continuous_scale=px.colors.sequential.Viridis
                    )
                    fig_valores.update_layout(xaxis_tickangle=-45)
                    st.plotly_chart(fig_valores, use_container_width=True)
                else:
                    st.info("Dados insuficientes para análise por projeto.")

# ============================================
# ABA 4: CONFIGURAÇÕES
# ============================================
with tab4:
    st.markdown("## ⚙️ Configurações do Sistema")
    
    current_config = st.session_state['config']

    st.markdown("### 🔧 Opções de Processamento")
    
    col_p1, col_p2, col_p3 = st.columns(3)
    
    with col_p1:
        auto_validar = st.checkbox(
            "Validação automática",
            value=current_config['auto_validar'],
            help="Executa validação automática após carregar dados"
        )
        
    with col_p2:
        manter_historico = st.checkbox(
            "Manter histórico",
            value=current_config['manter_historico'],
            help="Armazena histórico de modificações"
        )
    
    with col_p3:
        limite_registros = st.number_input(
            "Limite de registros:",
            min_value=1000,
            max_value=1000000,
            value=current_config['limite_registros'],
            step=1000,
            help="Número máximo de registros para processamento"
        )
    
    st.markdown("### 💾 Opções de Exportação")
    
    col_e1, col_e2 = st.columns(2)
    
    with col_e1:
        formato_exportacao = st.selectbox(
            "Formato padrão:",
            ["Excel (.xlsx)", "CSV (.csv)"],
            index=0 if current_config['formato_exportacao'] == "Excel (.xlsx)" else 1
        )
    
    with col_e2:
        incluir_graficos = st.checkbox(
            "Incluir gráficos em relatórios",
            value=current_config['incluir_graficos'],
            help="Adiciona visualizações nos relatórios exportados (quando disponível)"
        )
    
    # Configurações avançadas
    st.markdown("### ⚡ Configurações Avançadas")
    
    with st.expander("Configurações de Validação", expanded=False):
        validar_cpf = st.checkbox("Validar formato de CPF", value=True)
        validar_valores = st.checkbox("Validar valores numéricos", value=True)
        corrigir_decimais = st.checkbox("Corrigir problemas de casas decimais", value=True,
                                       help="Corrige automaticamente valores que parecem ter problemas de formatação")
    
    # Botão para salvar configurações
    col_btn1, col_btn2 = st.columns(2)
    
    with col_btn1:
        if st.button("💾 SALVAR CONFIGURAÇÕES", type="primary", use_container_width=True):
            st.session_state['config'] = {
                'auto_validar': auto_validar,
                'manter_historico': manter_historico,
                'limite_registros': limite_registros,
                'formato_exportacao': formato_exportacao,
                'incluir_graficos': incluir_graficos,
                'validar_cpf': validar_cpf,
                'validar_valores': validar_valores,
                'corrigir_decimais': corrigir_decimais
            }
            st.success("✅ Configurações salvas com sucesso!")
            st.rerun()
    
    with col_btn2:
        if st.button("🔄 RESTAURAR PADRÕES", use_container_width=True):
            st.session_state['config'] = {
                'auto_validar': True,
                'manter_historico': True,
                'limite_registros': 100000,
                'formato_exportacao': "Excel (.xlsx)",
                'incluir_graficos': True,
                'validar_cpf': True,
                'validar_valores': True,
                'corrigir_decimais': True
            }
            st.success("✅ Configurações restauradas para os valores padrão!")
            st.rerun()
    
    # Informações do sistema
    st.markdown("---")
    st.markdown("### ℹ️ Informações do Sistema")
    
    col_info1, col_info2 = st.columns(2)
    
    with col_info1:
        st.markdown("""
        **Versão:** 2.0.1  
        **Última atualização:** Novembro 2024  
        **Desenvolvido para:** SMDET-POT  
        """)
    
    with col_info2:
        st.markdown("""
        **Funcionalidades principais:**
        - Processamento de arquivos CSV/TXT
        - Dashboard interativo
        - Análise detalhada
        - Exportação multiplataforma
        """)

# ============================================
# RODAPÉ
# ============================================
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #666; font-size: 0.9em;'>"
    "💰 SMDET - POT Monitoramento de Pagamento de Benefícios | "
    "Sistema desenvolvido para acompanhamento e análise de pagamentos"
    "</div>",
    unsafe_allow_html=True
)
