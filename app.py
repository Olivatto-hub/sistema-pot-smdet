import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import warnings
import re
from typing import List, Dict, Any, Tuple
warnings.filterwarnings('ignore')

# ============================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================
st.set_page_config(
    page_title="Sistema POT-SMDET - Monitoramento e Análise",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================
# CSS MINIMALISTA E COM FOCO EM UX
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
        text-align: center;
    }
    
    /* ESPAÇAMENTO MELHOR ENTRE WIDGETS */
    .stSlider, .stSelectbox, .stMultiSelect, .stDateInput {
        margin-bottom: 1rem;
    }
    
    /* BOTÕES MAIS VISÍVEIS */
    .stButton > button {
        border-radius: 8px;
        font-weight: 700;
        transition: all 0.3s ease;
        padding: 0.5rem 1rem;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }

    /* TÍTULOS DE SEÇÃO */
    .stMarkdown h3 {
        border-bottom: 2px solid #333; /* Uma linha para separar seções */
        padding-bottom: 5px;
        margin-top: 20px;
    }
    
    /* INDICADORES (KPIs) */
    [data-testid="stMetricValue"] {
        font-size: 2.5rem;
        font-weight: 800;
        color: #1f77b4; /* Cor primária para destaque */
    }
    [data-testid="stMetricLabel"] {
        font-size: 1.0rem;
        font-weight: 600;
    }
    
    /* EXPANDER (Para Inconsistências) */
    .stExpander {
        border: 2px solid #ff4b4b; /* Vermelho para destaque de erro */
        border-radius: 8px;
        margin-top: 15px;
    }

</style>
""", unsafe_allow_html=True)

# ============================================
# VARIÁVEIS DE ESTADO
# ============================================
if 'data' not in st.session_state:
    st.session_state['data'] = pd.DataFrame()
if 'inconsistencias' not in st.session_state:
    st.session_state['inconsistencias'] = []
if 'arquivos_carregados' not in st.session_state:
    st.session_state['arquivos_carregados'] = {}

# ============================================
# FUNÇÕES AUXILIARES
# ============================================

def formatar_moeda_brl(valor: Any) -> str:
    """Formata um valor numérico para o padrão monetário brasileiro (R$ 9.999.999,99)."""
    if pd.isna(valor) or valor in ('', 'nan', 'NaT'):
        return 'R$ 0,00'
    try:
        # Tenta limpar string (remove separador de milhares americano e substitui decimal por ponto)
        if isinstance(valor, str):
            # Tenta tratar a inversão de notação americana/europeia. Prioriza BRL.
            # Se tiver mais de uma vírgula ou ponto (ex: 1.000,00 ou 1,000.00), trata.
            if len(re.findall(r'[.,]', valor)) > 1:
                valor_limpo = valor.replace('.', '').replace(',', '.') # Assume padrão BR/EUR (1.000,00)
            else:
                valor_limpo = valor.replace(',', '.') # Assume notação simples 1000,00

            valor_float = float(re.sub(r'[^\d.]', '', valor_limpo))
        elif isinstance(valor, (int, float)):
            valor_float = valor
        else:
            return str(valor)

        # Formata para BRL (usando o truque de replace para trocar . por , e adicionar .)
        texto = f"{valor_float:,.2f}"
        return f"R$ {texto.replace(',', '_').replace('.', ',').replace('_', '.')}"
    except Exception as e:
        # st.error(f"Erro ao formatar valor '{valor}': {e}")
        return str(valor) # Retorna original se falhar

def limpar_colunas_monetarias(df: pd.DataFrame, colunas: List[str]) -> pd.DataFrame:
    """Limpa e converte colunas de valor para float, tratando padrões BRL/EUA."""
    for col in colunas:
        if col in df.columns:
            # 1. Tenta tratar strings como BRL (1.000,00) ou EUA (1,000.00)
            df[col] = df[col].astype(str).str.replace(r'[^0-9,.]', '', regex=True)
            
            # Função de limpeza para aplicação
            def clean_value(val):
                if pd.isna(val) or val in ('', 'nan', 'NaT'):
                    return np.nan
                s_val = str(val)
                # Se tiver mais de um separador (ponto e vírgula), assume BRL (1.000,00)
                if s_val.count('.') > 0 and s_val.count(',') > 0:
                    s_val = s_val.replace('.', '').replace(',', '.')
                # Se tiver apenas vírgula, assume separador decimal BRL (100,00)
                elif s_val.count(',') == 1 and s_val.count('.') == 0:
                    s_val = s_val.replace(',', '.')
                # Se tiver apenas ponto e for o último, assume separador decimal EUA (100.00)
                # Caso contrário, pode ser separador de milhar.
                try:
                    return float(s_val)
                except:
                    return np.nan
            
            df[col] = df[col].apply(clean_value)
    return df

def normalizar_coluna_data(df: pd.DataFrame, coluna: str) -> pd.DataFrame:
    """Tenta converter uma coluna para datetime, tratando diferentes formatos."""
    if coluna in df.columns:
        # Lista de formatos comuns, priorizando o BR
        formatos = ['%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%m/%d/%Y', '%d/%m/%y']
        
        for fmt in formatos:
            try:
                # Tenta converter o restante que não foi convertido com o formato atual
                df[coluna] = pd.to_datetime(df[coluna], format=fmt, errors='coerce')
                # Se a conversão for bem sucedida, sai do loop
                if df[coluna].notna().sum() > 0:
                    break
            except Exception:
                continue
        
        # O que sobrar (ou seja, não conseguiu converter), fica como NaT
        df[coluna] = pd.to_datetime(df[coluna], errors='coerce')
    return df

def encontrar_inconsistencias_criticas(df: pd.DataFrame, nome_arquivo: str) -> List[Dict[str, Any]]:
    """
    Identifica inconsistências críticas de CPF repetido com dados divergentes.
    CPFs repetidos com diferentes Nomes OU diferentes Números de Cartão.
    """
    df_temp = df.copy()
    inconsistencias = []
    
    # Padronização e Limpeza
    if 'CPF' in df_temp.columns:
        df_temp['CPF_Limpo'] = df_temp['CPF'].astype(str).str.replace(r'[^0-9]', '', regex=True).replace('', np.nan)
    else:
        return inconsistencias # Se não tem CPF, não verifica este tipo de erro

    for col in ['Nome', 'Num Cartao', 'NumCartao']:
        if col in df_temp.columns:
            if col.startswith('NumCartao'): # Normalizar Num Cartão
                df_temp[col] = df_temp[col].astype(str).str.replace(r'[^0-9]', '', regex=True).replace('', np.nan)
            elif col == 'Nome': # Normalizar Nome
                df_temp[col] = df_temp[col].astype(str).str.strip().str.upper()

    # Garantir que 'Num Cartao' exista (usando 'NumCartao' como fallback)
    if 'Num Cartao' not in df_temp.columns and 'NumCartao' in df_temp.columns:
        df_temp.rename(columns={'NumCartao': 'Num Cartao'}, inplace=True)
    
    # 1. Filtrar CPFs duplicados e válidos
    df_duplicados = df_temp.dropna(subset=['CPF_Limpo']).duplicated(subset=['CPF_Limpo'], keep=False)
    df_duplicados = df_temp[df_duplicados].sort_values(by='CPF_Limpo')
    
    if df_duplicados.empty:
        return inconsistencias
        
    # Colunas chave para verificação
    colunas_chave = ['Nome']
    if 'Num Cartao' in df_temp.columns:
        colunas_chave.append('Num Cartao')
        
    colunas_relatorio = [c for c in ['Projeto', 'Nome', 'CPF', 'Num Cartao', 'DataPagto', 'Valor Pagto'] if c in df_temp.columns]

    # 2. Agrupar por CPF_Limpo para identificar divergências
    for cpf_limpo, grupo in df_duplicados.groupby('CPF_Limpo'):
        is_inconsistent = False
        detalhes = []
        
        # Verifica divergência de Nome
        if 'Nome' in grupo.columns and grupo['Nome'].nunique() > 1:
            is_inconsistent = True
            detalhes.append(f'Nomes Diferentes ({grupo["Nome"].nunique()} variantes)')
        
        # Verifica divergência de Num Cartao
        if 'Num Cartao' in grupo.columns and grupo['Num Cartao'].nunique() > 1:
            is_inconsistent = True
            detalhes.append(f'Números de Cartão Diferentes ({grupo["Num Cartao"].nunique()} variantes)')

        if is_inconsistent:
            for index, row in grupo.iterrows():
                inconsistencias.append({
                    'Arquivo': nome_arquivo,
                    'Tipo Inconsistência': 'CPF Duplicado',
                    'Detalhes': ', '.join(detalhes),
                    'CPF_Limpo': cpf_limpo,
                    'Registro': {col: row.get(col, 'N/A') for col in colunas_relatorio}
                })

    return inconsistencias

@st.cache_data(show_spinner="Analisando dados e inconsistências...")
def processar_e_analisar_dados(uploaded_files: List[st.runtime.uploaded_file_manager.UploadedFile]) -> Tuple[pd.DataFrame, List[Dict[str, Any]], Dict[str, str]]:
    """Carrega, limpa, padroniza e analisa todos os arquivos carregados."""
    todos_dados = []
    todas_inconsistencias = []
    
    # Mapeamento para padronizar nomes de colunas (caso haja variações)
    coluna_map_valores = {
        'valortotal': 'Valor Total',
        'valordesconto': 'Valor Desconto',
        'valorpagto': 'Valor Pagto',
        'valordia': 'Valor Dia',
        'data pagto': 'DataPagto',
        'num cartao': 'Num Cartao',
        'numcartao': 'Num Cartao',
        'data pagto': 'DataPagto',
        'cpf': 'CPF',
        'nome': 'Nome',
        'projeto': 'Projeto',
    }

    arquivos_info = {}

    for file in uploaded_files:
        try:
            # 1. Leitura do arquivo
            if file.name.lower().endswith('.csv'):
                df = pd.read_csv(file, sep=';', encoding='latin1', skip_blank_lines=True)
            elif file.name.lower().endswith('.txt'):
                df = pd.read_csv(file, sep='\t', encoding='latin1', skip_blank_lines=True)
            else:
                st.warning(f"Formato de arquivo não suportado para {file.name}. Ignorando.")
                continue

            # 2. Limpeza e Padronização de Colunas
            df.columns = df.columns.str.strip().str.lower().str.replace('[^a-z0-9]', '', regex=True)
            df.rename(columns=lambda c: coluna_map_valores.get(c, c), inplace=True)
            
            # Limpa colunas que só contêm valores vazios/nulos
            df.dropna(axis=1, how='all', inplace=True)
            df.dropna(axis=0, how='all', inplace=True)
            
            # 3. Tratamento de Tipos
            colunas_monetarias = ['Valor Total', 'Valor Desconto', 'Valor Pagto', 'Valor Dia']
            df = limpar_colunas_monetarias(df, colunas_monetarias)
            
            # 4. Normalização de Datas
            df = normalizar_coluna_data(df, 'DataPagto')
            
            # 5. Análise de Inconsistências
            inconsistencias_do_arquivo = encontrar_inconsistencias_criticas(df, file.name)
            todas_inconsistencias.extend(inconsistencias_do_arquivo)
            
            # Adicionar coluna de origem e metadados
            df['Arquivo_Origem'] = file.name
            df['Mes_Ano'] = df['DataPagto'].dt.strftime('%Y-%m') if 'DataPagto' in df.columns else 'N/A'

            todos_dados.append(df)
            arquivos_info[file.name] = "OK"

        except Exception as e:
            st.error(f"❌ Erro ao processar o arquivo '{file.name}': {e}")
            arquivos_info[file.name] = f"Erro: {e}"
            continue

    if not todos_dados:
        return pd.DataFrame(), [], arquivos_info

    # Combina todos os DataFrames
    df_final = pd.concat(todos_dados, ignore_index=True)
    
    # Garante colunas mínimas e preenche NaN se necessário (importante para evitar falhas em colunas ausentes)
    colunas_padrao = ['Projeto', 'Nome', 'Num Cartao', 'CPF', 'DataPagto', 'Valor Pagto', 'Arquivo_Origem', 'Mes_Ano']
    for col in colunas_padrao:
        if col not in df_final.columns:
            df_final[col] = np.nan
    
    # Remove NaN da coluna de data para evitar problemas no filtro
    df_final.dropna(subset=['DataPagto'], inplace=True)
    
    return df_final, todas_inconsistencias, arquivos_info

# ============================================
# LAYOUT DA BARRA LATERAL (FILTROS)
# ============================================

with st.sidebar:
    st.title("⚙️ Controles e Filtros")
    
    uploaded_files = st.file_uploader(
        "📂 Carregar Arquivos de Dados (.csv, .txt)",
        type=['csv', 'txt'],
        accept_multiple_files=True
    )
    
    if uploaded_files:
        st.subheader("Processamento de Dados")
        # Força o reprocessamento se os arquivos mudarem ou o botão for clicado
        if st.button("🔄 Processar Novamente"):
            st.session_state['data'], st.session_state['inconsistencias'], st.session_state['arquivos_carregados'] = processar_e_analisar_dados(uploaded_files)
        
        # Carrega/recarrega os dados na sessão
        if not st.session_state['data'].empty or len(uploaded_files) != len(st.session_state['arquivos_carregados']):
            st.session_state['data'], st.session_state['inconsistencias'], st.session_state['arquivos_carregados'] = processar_e_analisar_dados(uploaded_files)

        df_original = st.session_state['data']
        
        if not df_original.empty:
            
            # ----------------------------------------------------
            # 1. FILTROS DE PROJETO E ARQUIVO
            # ----------------------------------------------------
            st.markdown("### 🏷️ Filtros de Contexto")
            
            # Filtro de Arquivo
            arquivos_unicos = ['TODOS'] + sorted(df_original['Arquivo_Origem'].unique().tolist())
            arquivo_selecionado = st.selectbox(
                "Filtrar por Arquivo:",
                arquivos_unicos
            )
            
            # Filtro de Projeto
            projetos_unicos = ['TODOS'] + sorted(df_original['Projeto'].astype(str).str.strip().unique().tolist())
            projeto_selecionado = st.selectbox(
                "Filtrar por Projeto:",
                projetos_unicos
            )
            
            # ----------------------------------------------------
            # 2. FILTROS DE PERÍODO (NOVIDADE)
            # ----------------------------------------------------
            st.markdown("### 📅 Filtros de Período")

            tipo_filtro_data = st.radio(
                "Escolha o Tipo de Filtro:",
                ('Período Específico', 'Mês e Ano'),
                key='tipo_filtro_data'
            )

            df_filtrado = df_original.copy()
            
            if tipo_filtro_data == 'Período Específico':
                col_d_start, col_d_end = st.columns(2)
                
                # Encontrar a data mínima e máxima no conjunto de dados
                min_date = df_original['DataPagto'].min()
                max_date = df_original['DataPagto'].max()
                
                with col_d_start:
                    data_inicio = st.date_input(
                        "Data Início:",
                        value=min_date,
                        min_value=min_date,
                        max_value=max_date,
                        key='data_inicio'
                    )
                
                with col_d_end:
                    data_fim = st.date_input(
                        "Data Fim:",
                        value=max_date,
                        min_value=min_date,
                        max_value=max_date,
                        key='data_fim'
                    )
                
                # Aplicar filtro de período
                if data_inicio and data_fim:
                    df_filtrado = df_filtrado[
                        (df_filtrado['DataPagto'].dt.date >= data_inicio) & 
                        (df_filtrado['DataPagto'].dt.date <= data_fim)
                    ]

            elif tipo_filtro_data == 'Mês e Ano':
                col_m, col_a = st.columns(2)
                
                # Obter meses e anos únicos do Mes_Ano
                meses_anos_disponiveis = sorted(df_original['Mes_Ano'].unique().tolist())
                mes_ano_selecionado = st.selectbox(
                    "Selecione o Mês/Ano:",
                    ['TODOS'] + meses_anos_disponiveis,
                    key='mes_ano_selecionado'
                )

                if mes_ano_selecionado != 'TODOS':
                    df_filtrado = df_filtrado[df_filtrado['Mes_Ano'] == mes_ano_selecionado]

            # Aplica filtros de Arquivo e Projeto ao DF filtrado por data
            if arquivo_selecionado != 'TODOS':
                df_filtrado = df_filtrado[df_filtrado['Arquivo_Origem'] == arquivo_selecionado]
            
            if projeto_selecionado != 'TODOS':
                df_filtrado = df_filtrado[df_filtrado['Projeto'] == projeto_selecionado]

            # Armazena o DataFrame filtrado para uso no Main Content
            st.session_state['df_filtrado'] = df_filtrado
            
            # Exibir resumo dos arquivos processados
            st.markdown("---")
            st.markdown("#### Status dos Arquivos")
            for arquivo, status in st.session_state['arquivos_carregados'].items():
                icon = "✅" if status == "OK" else "❌"
                st.caption(f"{icon} **{arquivo}**: {status}")

        else:
            st.warning("Aguardando o carregamento e processamento dos dados.")
            st.session_state['df_filtrado'] = pd.DataFrame() # Garante que o df filtrado está vazio

    else:
        st.session_state['df_filtrado'] = pd.DataFrame()
        st.session_state['data'] = pd.DataFrame()
        st.session_state['inconsistencias'] = []


# ============================================
# LAYOUT PRINCIPAL (CONTEÚDO)
# ============================================

st.title("Sistema de Análise e Monitoramento de Projetos")

df_filtrado = st.session_state.get('df_filtrado', pd.DataFrame())
todas_inconsistencias = st.session_state.get('inconsistencias', [])

if df_filtrado.empty:
    st.info("Carregue e processe um ou mais arquivos na barra lateral para iniciar a análise.")
else:
    # ----------------------------------------------------
    # ABAS DE NAVEGAÇÃO
    # ----------------------------------------------------
    tab_analise, tab_inconsistencias, tab_dados, tab_config = st.tabs(
        [
            "📊 Análise Geral", 
            f"🚨 Inconsistências Críticas ({len(todas_inconsistencias)})", 
            "📝 Dados Detalhados", 
            "⚙️ Configurações"
        ]
    )

    # ============================================
    # ABA 1: ANÁLISE GERAL
    # ============================================
    with tab_analise:
        st.header("Resumo Financeiro e Distribuição")
        
        # 1. KPIs
        df_kpi = df_filtrado.copy()
        
        # Calcula KPIs após a filtragem
        total_pago = df_kpi['Valor Pagto'].sum() if 'Valor Pagto' in df_kpi.columns else 0
        total_registros = len(df_kpi)
        projetos_ativos = df_kpi['Projeto'].nunique() if 'Projeto' in df_kpi.columns else 0
        
        col_k1, col_k2, col_k3, col_k4 = st.columns(4)
        
        with col_k1:
            st.metric("Total Pago (Período Filtrado)", formatar_moeda_brl(total_pago))
        with col_k2:
            st.metric("Total de Registros", total_registros)
        with col_k3:
            st.metric("Projetos Envolvidos", projetos_ativos)
        with col_k4:
            media_pagto = total_pago / total_registros if total_registros > 0 else 0
            st.metric("Média por Registro", formatar_moeda_brl(media_pagto))
            
        st.markdown("---")

        # 2. GRÁFICOS
        if 'Valor Pagto' in df_kpi.columns and 'Projeto' in df_kpi.columns:
            st.subheader("Distribuição do Valor Pago por Projeto")
            
            # Agrupamento de dados para o gráfico
            df_projeto = df_kpi.groupby('Projeto')['Valor Pagto'].sum().reset_index()
            df_projeto['Valor Pagto Formatado'] = df_projeto['Valor Pagto'].apply(formatar_moeda_brl)
            
            fig_proj = px.bar(
                df_projeto.sort_values(by='Valor Pagto', ascending=False),
                x='Projeto',
                y='Valor Pagto',
                text='Valor Pagto Formatado',
                title='Soma Total de Pagamentos por Projeto',
                color='Projeto',
                template='plotly_white'
            )
            fig_proj.update_traces(textposition='outside')
            fig_proj.update_layout(showlegend=False, yaxis_title="Valor Pago (R$)", xaxis_title="Projeto")
            st.plotly_chart(fig_proj, use_container_width=True)

        if 'DataPagto' in df_kpi.columns and 'Valor Pagto' in df_kpi.columns:
            st.subheader("Evolução Mensal do Pagamento")
            
            df_mensal = df_kpi.set_index('DataPagto').resample('M')['Valor Pagto'].sum().reset_index()
            df_mensal['Mes_Ano'] = df_mensal['DataPagto'].dt.strftime('%Y-%m')
            
            fig_time = px.line(
                df_mensal,
                x='Mes_Ano',
                y='Valor Pagto',
                markers=True,
                title='Série Histórica do Pagamento Mensal',
                template='plotly_white'
            )
            fig_time.update_layout(xaxis_title="Mês/Ano", yaxis_title="Valor Pago (R$)")
            st.plotly_chart(fig_time, use_container_width=True)


    # ============================================
    # ABA 2: INCONSISTÊNCIAS CRÍTICAS (NOVIDADE)
    # ============================================
    with tab_inconsistencias:
        st.header("🚨 Inconsistências Críticas Detectadas")
        
        if todas_inconsistencias:
            st.warning(f"Foram encontradas **{len(todas_inconsistencias)}** inconsistências que requerem atenção da equipe.")
            
            # Conversão da lista de dicionários de inconsistências para DataFrame para exibição
            # Transformamos os dados aninhados para exibição plana
            dados_inconsistentes = []
            for inc in todas_inconsistencias:
                registro = inc['Registro']
                dados_inconsistentes.append({
                    'Arquivo Origem': inc['Arquivo'],
                    'Tipo': inc['Tipo Inconsistência'],
                    'Detalhes do Erro': inc['Detalhes'],
                    'CPF Duplicado': inc['CPF_Limpo'],
                    'Nome no Registro': registro.get('Nome', 'N/A'),
                    'Cartão no Registro': registro.get('Num Cartao', 'N/A'),
                    'Projeto': registro.get('Projeto', 'N/A'),
                    'Data Pagto': registro.get('DataPagto', 'N/A'),
                    'Valor Pagto': formatar_moeda_brl(registro.get('Valor Pagto', 0)),
                })
            
            df_inconsistencias = pd.DataFrame(dados_inconsistentes)
            
            st.markdown("### Tabela de Registros Inconsistentes")
            st.caption("Filtre o DataFrame abaixo para priorizar as ações de correção. **Os valores monetários estão no padrão BRL.**")
            
            # Exibe a tabela de inconsistências com filtro e formatação
            st.dataframe(
                df_inconsistencias,
                use_container_width=True,
                height=500
            )

            # Exportação do relatório de inconsistências (Ação Imediata)
            csv_inconsistencias = df_inconsistencias.to_csv(index=False, sep=';', encoding='utf-8-sig')
            st.download_button(
                label="📥 Exportar Relatório de Inconsistências (CSV)",
                data=csv_inconsistencias,
                file_name=f"RELATORIO_INCONSISTENCIAS_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime='text/csv',
                type="secondary"
            )

        else:
            st.success("🎉 Não foram encontradas inconsistências críticas (CPFs repetidos com dados divergentes) no conjunto de dados filtrado.")

    # ============================================
    # ABA 3: DADOS DETALHADOS
    # ============================================
    with tab_dados:
        st.header("Visualização e Detalhamento dos Dados")
        
        st.caption(f"Exibindo {len(df_filtrado)} registros (após filtros de período e contexto).")
        
        # Prepara a visualização: aplica a formatação BRL
        df_display = df_filtrado.copy()
        
        colunas_monetarias = ['Valor Total', 'Valor Desconto', 'Valor Pagto', 'Valor Dia']
        for col in colunas_monetarias:
            if col in df_display.columns:
                df_display[col] = df_display[col].apply(formatar_moeda_brl)
                
        # Formata a data para BR
        if 'DataPagto' in df_display.columns:
            df_display['DataPagto'] = df_display['DataPagto'].dt.strftime('%d/%m/%Y')
        
        st.dataframe(
            df_display, 
            use_container_width=True,
            height=600
        )

    # ============================================
    # ABA 4: CONFIGURAÇÕES E EXPORTAÇÃO
    # ============================================
    with tab_config:
        st.header("Opções do Sistema e Exportação de Relatórios")

        # ----------------------------------------------------
        # SIMULAÇÃO DE EXPORTAÇÃO AVANÇADA
        # ----------------------------------------------------
        st.markdown("### 💾 OPÇÕES DE EXPORTAÇÃO DE RELATÓRIOS")
        st.markdown("""
        **Aviso:** O relatório exportado incluirá:
        1.  O resumo da **Análise Geral** (KPIs e Gráficos).
        2.  A lista completa de **Inconsistências Críticas** (com o nome do arquivo original e informações do registro).
        3.  Os **Dados Detalhados** do período e contexto filtrados.
        """)

        col_e1, col_e2 = st.columns(2)
        
        with col_e1:
            formato_exportacao = st.selectbox(
                "Formato padrão de exportação:",
                ["PDF (Recomendado)", "Excel (.xlsx)", "CSV (.csv)"]
            )
        
        with col_e2:
            incluir_graficos = st.checkbox(
                "Incluir gráficos nos relatórios",
                value=True
            )
        
        st.button("⚙️ GERAR RELATÓRIO (EMULAÇÃO)", type="primary", use_container_width=True)
        
        if formato_exportacao == "PDF (Recomendado)":
            st.info("A geração de PDF com inclusão de inconsistências e metadados foi solicitada e será integrada na próxima atualização do sistema.")
        
        # Botão real de exportação para CSV/Excel do DF Filtrado (somente para dados limpos, não o relatório complexo)
        
        def to_excel(df):
            output = BytesIO()
            writer = pd.ExcelWriter(output, engine='xlsxwriter')
            df.to_excel(writer, index=False, sheet_name='Dados Filtrados')
            writer.close()
            return output.getvalue()
        
        # Prepara o DF para exportação (voltando a notação numérica padrão para software)
        df_export_num = df_filtrado.copy()
        for col in ['Valor Total', 'Valor Desconto', 'Valor Pagto', 'Valor Dia']:
            if col in df_export_num.columns:
                # Remove a formatação BRL para que o software que ler o arquivo reconheça o número
                df_export_num[col] = pd.to_numeric(df_export_num[col], errors='coerce')

        st.download_button(
            label="📥 Exportar Dados Filtrados para Excel (.xlsx)",
            data=to_excel(df_export_num),
            file_name=f"DADOS_FILTRADOS_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_excel"
        )


        # ----------------------------------------------------
        # OPÇÕES DO SISTEMA (MANTIDAS DO CÓDIGO ANTERIOR)
        # ----------------------------------------------------
        st.markdown("### 🖥️ OPÇÕES DE VALIDAÇÃO")
        
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            auto_validar = st.checkbox(
                "Validação automática ao carregar",
                value=True,
                help="Executa validação automática após carregar dados"
            )
            
            manter_historico = st.checkbox(
                "Manter histórico de alterações",
                value=True,
                help="Armazena histórico de modificações nos dados"
            )
        
        with col_s2:
            limite_registros = st.number_input(
                "Limite de registros para processamento:",
                min_value=1000,
                max_value=1000000,
                value=100000,
                step=1000,
                help="Define o número máximo de registros para processamento otimizado"
            )
        
        # Botão para salvar configurações
        if st.button("💾 SALVAR CONFIGURAÇÕES", type="secondary", use_container_width=True):
            st.success("✅ Configurações salvas com sucesso!")
            # Aqui você implementaria a lógica para salvar as configurações
            
# ============================================
# FIM DO CÓDIGO
# ============================================
