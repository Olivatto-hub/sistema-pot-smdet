import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import warnings
import re
import traceback
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
# CSS OTIMIZADO PARA TEMAS CLAROS E ESCUROS
# ============================================
st.markdown("""
<style>
    /* ESTILOS BASE */
    .main-header {
        font-size: 2.2em;
        font-weight: 800;
        margin-bottom: 0.5em;
        text-align: center;
        padding-bottom: 15px;
        border-bottom: 3px solid #1E3A8A;
        background: linear-gradient(90deg, #1E3A8A, #3B82F6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    
    /* MÉTRICAS */
    [data-testid="stMetric"] {
        background-color: #f8f9fa !important;
        padding: 20px;
        border-radius: 12px;
        border: 2px solid #dee2e6;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    
    [data-testid="stMetricValue"] {
        font-size: 1.8em !important;
        font-weight: 700 !important;
    }
    
    /* BOTÕES */
    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
        padding: 0.85rem 1.5rem;
        border: 2px solid #1E3A8A;
        background-color: white;
        color: #1E3A8A !important;
    }
    
    .stButton > button:hover {
        background-color: #1E3A8A !important;
        color: white !important;
    }
    
    /* TEMA ESCURO */
    @media (prefers-color-scheme: dark) {
        [data-testid="stMetric"] {
            background-color: #2d3748 !important;
            border-color: #4a5568;
        }
        
        .stButton > button {
            background-color: #2d3748;
            color: #e2e8f0 !important;
            border-color: #4a5568;
        }
        
        .stButton > button:hover {
            background-color: #1E3A8A !important;
            color: white !important;
        }
    }
    
    /* CUSTOM CARDS */
    .custom-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 15px;
        padding: 25px;
        color: white;
        margin-bottom: 20px;
        box-shadow: 0 10px 20px rgba(0,0,0,0.2);
    }
    
    /* BADGES */
    .badge {
        display: inline-block;
        padding: 5px 15px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.85em;
        margin: 2px;
    }
    
    .badge-success {
        background: linear-gradient(135deg, #10b981 0%, #059669 100%);
        color: white;
    }
    
    .badge-warning {
        background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
        color: white;
    }
    
    .badge-danger {
        background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# ============================================
# INICIALIZAÇÃO ROBUSTA DO ESTADO
# ============================================
def initialize_session_state():
    """Inicializa todas as variáveis de estado com valores padrão."""
    defaults = {
        'dataframes': {},
        'is_processed': False,
        'config': {
            'auto_validar': True,
            'manter_historico': True,
            'limite_registros': 100000,
            'formato_exportacao': "Excel (.xlsx)",
            'incluir_graficos': True
        },
        'filtros_ativos': {},
        'pagina_atual': 1,
        'uploaded_files': [],
        'processing_error': None
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

initialize_session_state()

# ============================================
# FUNÇÕES AUXILIARES COM TRATAMENTO DE ERROS
# ============================================

def safe_get(data, key, default=None):
    """Obtém valor de forma segura de dicionários aninhados."""
    try:
        if isinstance(data, dict):
            return data.get(key, default)
        return default
    except:
        return default

def formatar_valor_brl(valor):
    """Formata valor para Real Brasileiro de forma segura."""
    try:
        if pd.isna(valor):
            return "R$ 0,00"
        valor = float(valor)
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return "R$ 0,00"

def formatar_numero(numero):
    """Formata número com separadores de milhar de forma segura."""
    try:
        if pd.isna(numero):
            return "0"
        return f"{int(float(numero)):,}".replace(",", ".")
    except:
        return str(numero)

def clean_column_name(col):
    """Limpa e normaliza nomes de colunas de forma segura."""
    try:
        col = str(col).strip().upper()
        col = re.sub(r'[^A-Z0-9_ÁÉÍÓÚÀÈÌÒÙÃÕÇ ]+', '', col)
        
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
            'VLR PAGAMENTO': 'VALOR_PAGAMENTO',
            'NOME DO BENEFICIARIO': 'NOME',
            'NOME BENEFICIARIO': 'NOME',
            'BENEFICIARIO': 'NOME',
            'CODIGO BENEFICIARIO': 'CODIGO',
            'MATRICULA': 'MATRICULA',
            'MATRÍCULA': 'MATRICULA'
        }
        
        for old, new in replacements.items():
            col = col.replace(old, new)
        
        return col.replace(' ', '_').replace('.', '').replace('__', '_').strip('_')
    except:
        return str(col)

def processar_valor_coluna(serie):
    """Processa uma coluna de valores de forma segura."""
    try:
        if serie.dtype == 'object':
            # Remove caracteres não numéricos
            serie = serie.astype(str).str.replace(r'[^\d.,-]', '', regex=True)
            
            # Verifica formato brasileiro (ponto como separador de milhar, vírgula como decimal)
            if serie.str.contains(r'\d{1,3}(\.\d{3})*,\d{2}').any():
                serie = serie.str.replace('.', '', regex=False)
                serie = serie.str.replace(',', '.', regex=False)
            # Verifica formato americano (vírgula como separador de milhar)
            elif serie.str.contains(r'\d{1,3}(,\d{3})*\.\d{2}').any():
                serie = serie.str.replace(',', '', regex=False)
        
        # Converte para numérico
        serie_numerica = pd.to_numeric(serie, errors='coerce')
        
        # Verifica valores extremamente altos (possível erro de formatação)
        if serie_numerica.max() > 10000000:  # Valores acima de 10 milhões
            # Verifica se podem ser valores com casas decimais duplicadas
            if (serie_numerica % 100 == 0).all():
                serie_numerica = serie_numerica / 100
        
        return serie_numerica.fillna(0)
    except:
        return pd.Series([0] * len(serie), index=serie.index)

@st.cache_data(show_spinner="🔄 Processando arquivos...")
def load_and_process_files(uploaded_files, limite_registros):
    """Carrega e processa arquivos com tratamento de erros robusto."""
    dataframes = {}
    
    if not uploaded_files:
        return dataframes, None

    all_pagamentos = []
    errors = []
    
    for idx, file in enumerate(uploaded_files):
        try:
            # Verifica tamanho do arquivo
            file_size = len(file.getvalue()) / 1024 / 1024  # MB
            if file_size > 100:  # Limite de 100MB
                errors.append(f"Arquivo {file.name} muito grande ({file_size:.1f}MB). Máximo: 100MB")
                continue
            
            # Detecta extensão
            file_extension = file.name.lower().split('.')[-1]
            
            # Tenta diferentes métodos de leitura
            df = None
            if file_extension == 'csv':
                # Tenta diferentes encodings e delimitadores
                encodings = ['utf-8', 'latin1', 'ISO-8859-1', 'cp1252']
                delimiters = [';', ',', '\t']
                
                for encoding in encodings:
                    for delimiter in delimiters:
                        try:
                            file.seek(0)  # Reset file pointer
                            df = pd.read_csv(
                                file, 
                                sep=delimiter, 
                                encoding=encoding, 
                                on_bad_lines='skip',
                                nrows=limite_registros,
                                dtype=str,
                                low_memory=False
                            )
                            if len(df.columns) > 1:  # Se encontrou múltiplas colunas
                                break
                        except:
                            continue
                    if df is not None and len(df.columns) > 1:
                        break
            
            elif file_extension in ['xlsx', 'xls']:
                try:
                    file.seek(0)
                    df = pd.read_excel(file, nrows=limite_registros, dtype=str)
                except Exception as e:
                    errors.append(f"Erro ao ler Excel {file.name}: {str(e)}")
                    continue
            
            elif file_extension == 'txt':
                try:
                    file.seek(0)
                    # Tenta diferentes delimitadores
                    content = file.getvalue().decode('utf-8', errors='ignore')
                    if ';' in content[:1000]:
                        df = pd.read_csv(file, sep=';', encoding='utf-8', nrows=limite_registros, dtype=str)
                    elif '\t' in content[:1000]:
                        df = pd.read_csv(file, sep='\t', encoding='utf-8', nrows=limite_registros, dtype=str)
                    else:
                        df = pd.read_csv(file, sep=',', encoding='utf-8', nrows=limite_registros, dtype=str)
                except Exception as e:
                    errors.append(f"Erro ao ler TXT {file.name}: {str(e)}")
                    continue
            
            if df is None or df.empty:
                errors.append(f"Não foi possível ler {file.name} ou arquivo vazio")
                continue
            
            # Limpa nomes das colunas
            df.columns = [clean_column_name(col) for col in df.columns]
            
            # Remove colunas completamente vazias
            df = df.dropna(axis=1, how='all')
            
            if df.empty:
                errors.append(f"Arquivo {file.name} vazio após limpeza")
                continue
            
            # Processa colunas de valores
            value_columns = ['VALOR_TOTAL', 'VALOR_DESCONTO', 'VALOR_PAGAMENTO', 'VALOR_DIA']
            for col in value_columns:
                if col in df.columns:
                    df[col] = processar_valor_coluna(df[col])
            
            # Padroniza outras colunas importantes
            if 'PROJETO' in df.columns:
                df['PROJETO'] = df['PROJETO'].astype(str).str.strip().str.upper()
            
            if 'NOME' in df.columns:
                df['NOME'] = df['NOME'].astype(str).str.strip().str.title()
            
            # Identifica se é arquivo de pagamentos
            pagamento_cols = ['VALOR_PAGAMENTO', 'VALORPAGTO', 'PAGAMENTO', 'VALOR_TOTAL']
            is_pagamento = any(col in df.columns for col in pagamento_cols)
            
            if is_pagamento:
                # Adiciona metadados
                df['ARQUIVO_ORIGEM'] = file.name
                df['DATA_CARREGAMENTO'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                all_pagamentos.append(df)
            else:
                dataframes[f"CADASTRO_{file.name}"] = df
                
        except Exception as e:
            error_msg = f"Erro ao processar {file.name}: {str(e)[:200]}"
            errors.append(error_msg)
            continue
    
    # Processa dados consolidados se houver pagamentos
    if all_pagamentos:
        try:
            df_final = pd.concat(all_pagamentos, ignore_index=True, sort=False)
            
            # Remove duplicatas completas
            df_final = df_final.drop_duplicates()
            
            # Garante colunas essenciais
            if 'VALOR_PAGAMENTO' not in df_final.columns:
                # Procura por colunas alternativas
                for col in df_final.columns:
                    if 'PAG' in col.upper() and 'VALOR' in col.upper():
                        df_final = df_final.rename(columns={col: 'VALOR_PAGAMENTO'})
                        break
            
            if 'VALOR_TOTAL' not in df_final.columns:
                # Cria se não existir
                df_final['VALOR_TOTAL'] = df_final.get('VALOR_PAGAMENTO', 0)
            
            # Cria coluna de status
            if 'VALOR_PAGAMENTO' in df_final.columns:
                df_final['STATUS_PAGAMENTO'] = np.where(
                    df_final['VALOR_PAGAMENTO'] > 0, 
                    'PAGO', 
                    'PENDENTE'
                )
            else:
                df_final['STATUS_PAGAMENTO'] = 'PENDENTE'
            
            # Calcula valor pendente
            if all(col in df_final.columns for col in ['VALOR_TOTAL', 'VALOR_PAGAMENTO']):
                desconto = df_final.get('VALOR_DESCONTO', 0)
                df_final['VALOR_PENDENTE'] = df_final['VALOR_TOTAL'] - df_final['VALOR_PAGAMENTO'] - desconto
            
            dataframes['DADOS_CONSOLIDADOS'] = df_final
            
        except Exception as e:
            errors.append(f"Erro ao consolidar dados: {str(e)}")
    
    error_message = "\n".join(errors) if errors else None
    return dataframes, error_message

def create_download_link(df, filename, file_format):
    """Cria link de download com tratamento de erros."""
    try:
        if df.empty:
            return None, None, "DataFrame vazio"
        
        if file_format == "CSV (.csv)":
            csv = df.to_csv(index=False, sep=';', encoding='latin1', decimal=',')
            return csv, "text/csv", None
        
        elif file_format == "Excel (.xlsx)":
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Dados')
            output.seek(0)
            return output.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", None
        
        return None, None, "Formato não suportado"
    except Exception as e:
        return None, None, f"Erro ao criar arquivo: {str(e)}"

def get_dataframe_safe(key, default_key=None):
    """Obtém DataFrame de forma segura do session state."""
    try:
        dataframes = st.session_state.get('dataframes', {})
        
        # Tenta obter pela chave principal
        if key in dataframes:
            df = dataframes[key]
            if df is not None and not df.empty:
                return df
        
        # Tenta chave alternativa
        if default_key and default_key in dataframes:
            df = dataframes[default_key]
            if df is not None and not df.empty:
                return df
        
        # Procura por qualquer DataFrame que contenha 'CONSOLIDADO' ou 'PAGAMENTO'
        for df_key, df in dataframes.items():
            if df is not None and not df.empty:
                if 'CONSOLIDADO' in df_key.upper() or 'PAGAMENTO' in df_key.upper():
                    return df
        
        # Retorna o primeiro DataFrame não vazio
        for df_key, df in dataframes.items():
            if df is not None and not df.empty:
                return df
        
        return None
    except:
        return None

# ============================================
# LAYOUT PRINCIPAL
# ============================================

try:
    st.markdown("<p class='main-header'>💰 SMDET - POT Monitoramento de Pagamento de Benefícios</p>", unsafe_allow_html=True)
    
    # Barra de status
    with st.container():
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            status = "✅ Processado" if st.session_state.get('is_processed') else "⏳ Aguardando"
            st.markdown(f"**Status:** {status}")
        with col2:
            file_count = len(st.session_state.get('uploaded_files', []))
            st.markdown(f"**Arquivos:** {file_count}")
        with col3:
            data_count = len(st.session_state.get('dataframes', {}))
            st.markdown(f"**Datasets:** {data_count}")
        with col4:
            current_time = datetime.now().strftime("%d/%m/%Y %H:%M")
            st.markdown(f"**Hora:** {current_time}")
    
    # ============================================
    # SIDEBAR
    # ============================================
    with st.sidebar:
        st.markdown("### 📥 CARREGAMENTO DE DADOS")
        
        uploaded_files = st.file_uploader(
            "Selecione arquivos (CSV, TXT, Excel)",
            type=['csv', 'txt', 'xlsx', 'xls'],
            accept_multiple_files=True,
            key="file_uploader"
        )
        
        # Atualiza lista de arquivos
        if uploaded_files:
            st.session_state['uploaded_files'] = uploaded_files
            
            with st.expander(f"📋 Arquivos selecionados ({len(uploaded_files)})", expanded=True):
                for file in uploaded_files[:5]:
                    size_kb = len(file.getvalue()) / 1024
                    st.markdown(f"• `{file.name}` ({size_kb:.1f} KB)")
                if len(uploaded_files) > 5:
                    st.markdown(f"• ... e mais {len(uploaded_files) - 5} arquivos")
        
        # Configurações de processamento
        st.markdown("### ⚙️ CONFIGURAÇÕES")
        
        limite_registros = st.number_input(
            "Limite de registros por arquivo:",
            min_value=1000,
            max_value=500000,
            value=st.session_state['config'].get('limite_registros', 100000),
            step=1000
        )
        
        auto_validar = st.checkbox(
            "Validação automática",
            value=st.session_state['config'].get('auto_validar', True)
        )
        
        # Botão de processamento
        if st.button("🚀 PROCESSAR DADOS", type="primary", use_container_width=True):
            if uploaded_files:
                with st.spinner("Processando..."):
                    try:
                        dataframes, error_message = load_and_process_files(
                            uploaded_files, 
                            limite_registros
                        )
                        
                        if error_message:
                            st.error(f"⚠️ Foram encontrados erros:\n{error_message}")
                        
                        if dataframes:
                            st.session_state['dataframes'] = dataframes
                            st.session_state['is_processed'] = True
                            st.session_state['config']['limite_registros'] = limite_registros
                            st.session_state['config']['auto_validar'] = auto_validar
                            
                            df_principal = get_dataframe_safe('DADOS_CONSOLIDADOS')
                            if df_principal is not None:
                                record_count = len(df_principal)
                                st.success(f"✅ Processamento concluído! {record_count:,} registros carregados.")
                                st.balloons()
                            else:
                                st.warning("⚠️ Dados processados, mas nenhum dataset principal encontrado.")
                        else:
                            st.error("❌ Não foi possível processar os arquivos.")
                    except Exception as e:
                        st.error(f"❌ Erro durante o processamento: {str(e)}")
            else:
                st.error("❌ Selecione arquivos para processar.")
        
        st.markdown("---")
        
        # Ações rápidas
        st.markdown("### ⚡ AÇÕES RÁPIDAS")
        
        col_a1, col_a2 = st.columns(2)
        with col_a1:
            if st.button("🗑️ Limpar Dados", use_container_width=True):
                for key in ['dataframes', 'is_processed', 'filtros_ativos']:
                    if key in st.session_state:
                        st.session_state[key] = {} if key == 'dataframes' else False
                st.success("✅ Dados limpos!")
                st.rerun()
        
        with col_a2:
            if st.button("🔄 Recarregar", use_container_width=True):
                st.rerun()
        
        # Informações do sistema
        st.markdown("---")
        st.markdown("""
        <div style="text-align: center; font-size: 0.9em; color: #666;">
        <strong>SMDET - POT</strong><br>
        Sistema de Monitoramento<br>
        Versão 2.2.0
        </div>
        """, unsafe_allow_html=True)
    
    # ============================================
    # ABAS PRINCIPAIS
    # ============================================
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 DASHBOARD", 
        "📁 DADOS", 
        "🔍 ANÁLISE", 
        "⚙️ CONFIGURAÇÕES"
    ])
    
    # ============================================
    # ABA 1: DASHBOARD
    # ============================================
    with tab1:
        st.markdown("## 📊 Dashboard de Monitoramento")
        
        df_principal = get_dataframe_safe('DADOS_CONSOLIDADOS')
        
        if df_principal is None or df_principal.empty:
            st.info("""
            ### 👋 Bem-vindo ao Dashboard!
            
            Para começar:
            1. 📥 Carregue arquivos na barra lateral
            2. 🚀 Clique em **PROCESSAR DADOS**
            3. 📊 Visualize as métricas aqui
            
            **Formatos suportados:** CSV, TXT, Excel
            """)
        else:
            # Métricas principais
            try:
                total_registros = len(df_principal)
                total_projetos = df_principal.get('PROJETO', pd.Series([0])).nunique()
                
                # Conta pagamentos
                if 'VALOR_PAGAMENTO' in df_principal.columns:
                    qtd_pagamentos = (df_principal['VALOR_PAGAMENTO'] > 0).sum()
                    valor_total_pago = df_principal['VALOR_PAGAMENTO'].sum()
                else:
                    qtd_pagamentos = 0
                    valor_total_pago = 0
                
                # Calcula valores totais
                if 'VALOR_TOTAL' in df_principal.columns:
                    valor_total = df_principal['VALOR_TOTAL'].sum()
                else:
                    valor_total = valor_total_pago
                
                valor_pendente = valor_total - valor_total_pago
                
                # Cards de métricas
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric(
                        "Total de Registros",
                        formatar_numero(total_registros),
                        help="Quantidade total de registros processados"
                    )
                
                with col2:
                    st.metric(
                        "Projetos Ativos",
                        formatar_numero(total_projetos),
                        help="Número de projetos diferentes"
                    )
                
                with col3:
                    st.metric(
                        "Pagamentos Realizados",
                        formatar_numero(qtd_pagamentos),
                        help="Quantidade de pagamentos efetuados"
                    )
                
                with col4:
                    st.metric(
                        "Valor Total Pago",
                        formatar_valor_brl(valor_total_pago),
                        help="Soma de todos os valores pagos"
                    )
                
                st.markdown("---")
                
                # Gráficos
                col_g1, col_g2 = st.columns(2)
                
                with col_g1:
                    st.markdown("### 📈 Distribuição por Status")
                    if 'STATUS_PAGAMENTO' in df_principal.columns:
                        status_counts = df_principal['STATUS_PAGAMENTO'].value_counts()
                        
                        fig_status = px.pie(
                            values=status_counts.values,
                            names=status_counts.index,
                            title='Status de Pagamento',
                            color=status_counts.index,
                            color_discrete_map={
                                'PAGO': '#10B981',
                                'PENDENTE': '#F59E0B'
                            },
                            hole=0.4
                        )
                        
                        fig_status.update_traces(
                            textposition='inside',
                            textinfo='percent+label'
                        )
                        
                        st.plotly_chart(fig_status, use_container_width=True)
                    else:
                        st.info("Coluna de status não encontrada")
                
                with col_g2:
                    st.markdown("### 🏗️ Valores por Projeto")
                    if 'PROJETO' in df_principal.columns and 'VALOR_TOTAL' in df_principal.columns:
                        projeto_summary = df_principal.groupby('PROJETO')['VALOR_TOTAL'].sum()
                        projeto_summary = projeto_summary.sort_values(ascending=False).head(10)
                        
                        fig_projeto = px.bar(
                            x=projeto_summary.index,
                            y=projeto_summary.values,
                            title='Top 10 Projetos por Valor',
                            labels={'x': 'Projeto', 'y': 'Valor Total (R$)'},
                            color=projeto_summary.values,
                            color_continuous_scale='Blues'
                        )
                        
                        fig_projeto.update_layout(xaxis_tickangle=-45)
                        st.plotly_chart(fig_projeto, use_container_width=True)
                    else:
                        st.info("Dados insuficientes para gráfico de projetos")
                
                # Tabela de resumo
                st.markdown("---")
                st.markdown("### 📋 Resumo por Projeto")
                
                if 'PROJETO' in df_principal.columns:
                    try:
                        resumo = df_principal.groupby('PROJETO').agg({
                            'NOME': 'count',
                            'VALOR_TOTAL': 'sum',
                            'VALOR_PAGAMENTO': 'sum'
                        }).reset_index()
                        
                        resumo.columns = ['Projeto', 'Beneficiários', 'Valor Total', 'Valor Pago']
                        
                        # Calcula valor pendente e porcentagem
                        resumo['Valor Pendente'] = resumo['Valor Total'] - resumo['Valor Pago']
                        resumo['% Pago'] = (resumo['Valor Pago'] / resumo['Valor Total'] * 100).round(2)
                        
                        # Formata valores
                        resumo['Valor Total'] = resumo['Valor Total'].apply(formatar_valor_brl)
                        resumo['Valor Pago'] = resumo['Valor Pago'].apply(formatar_valor_brl)
                        resumo['Valor Pendente'] = resumo['Valor Pendente'].apply(formatar_valor_brl)
                        
                        st.dataframe(
                            resumo.sort_values('Projeto'),
                            use_container_width=True,
                            height=400
                        )
                    except Exception as e:
                        st.warning(f"Não foi possível gerar resumo: {str(e)}")
                else:
                    st.info("Coluna 'PROJETO' não encontrada nos dados")
                    
            except Exception as e:
                st.error(f"Erro ao gerar dashboard: {str(e)}")
    
    # ============================================
    # ABA 2: DADOS E EXPORTAÇÃO
    # ============================================
    with tab2:
        st.markdown("## 📁 Dados Carregados e Exportação")
        
        df_principal = get_dataframe_safe('DADOS_CONSOLIDADOS')
        
        if df_principal is None or df_principal.empty:
            st.info("Nenhum dado disponível para visualização. Carregue e processe dados primeiro.")
        else:
            # Estatísticas
            col_s1, col_s2, col_s3 = st.columns(3)
            with col_s1:
                st.metric("Registros", formatar_numero(len(df_principal)))
            with col_s2:
                st.metric("Colunas", len(df_principal.columns))
            with col_s3:
                if 'VALOR_TOTAL' in df_principal.columns:
                    st.metric("Valor Total", formatar_valor_brl(df_principal['VALOR_TOTAL'].sum()))
            
            # Visualização dos dados
            st.markdown("### 👁️ Visualização dos Dados")
            
            # Configuração da visualização
            col_v1, col_v2 = st.columns(2)
            with col_v1:
                linhas_por_pagina = st.slider(
                    "Linhas por página:",
                    min_value=10,
                    max_value=200,
                    value=50,
                    step=10
                )
            
            with col_v2:
                total_paginas = max(1, len(df_principal) // linhas_por_pagina + 
                                  (1 if len(df_principal) % linhas_por_pagina > 0 else 0))
                pagina = st.number_input(
                    "Página:",
                    min_value=1,
                    max_value=total_paginas,
                    value=1,
                    step=1
                )
            
            # Seleção de colunas
            colunas_disponiveis = df_principal.columns.tolist()
            colunas_selecionadas = st.multiselect(
                "Selecione colunas para exibir:",
                colunas_disponiveis,
                default=colunas_disponiveis[:min(8, len(colunas_disponiveis))]
            )
            
            if colunas_selecionadas:
                # Calcula intervalo para paginação
                inicio = (pagina - 1) * linhas_por_pagina
                fim = min(inicio + linhas_por_pagina, len(df_principal))
                
                # Exibe dados
                df_exibir = df_principal[colunas_selecionadas].iloc[inicio:fim]
                
                # Formata valores monetários
                colunas_monetarias = [col for col in df_exibir.columns 
                                    if 'VALOR' in col.upper()]
                for col in colunas_monetarias:
                    if pd.api.types.is_numeric_dtype(df_exibir[col]):
                        df_exibir[col] = df_exibir[col].apply(formatar_valor_brl)
                
                st.dataframe(df_exibir, use_container_width=True, height=500)
                
                st.caption(f"Mostrando linhas {inicio + 1} a {fim} de {len(df_principal):,} "
                          f"(Página {pagina}/{total_paginas})")
            
            # Exportação
            st.markdown("---")
            st.markdown("### 💾 Exportação de Dados")
            
            col_e1, col_e2 = st.columns(2)
            
            with col_e1:
                formato = st.selectbox(
                    "Formato de exportação:",
                    ["Excel (.xlsx)", "CSV (.csv)"],
                    index=0
                )
            
            with col_e2:
                nome_arquivo = st.text_input(
                    "Nome do arquivo:",
                    value=f"dados_smdet_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                )
            
            if st.button("📥 Exportar Dados", type="primary", use_container_width=True):
                with st.spinner("Gerando arquivo..."):
                    data, mime_type, error = create_download_link(df_principal, nome_arquivo, formato)
                    
                    if data and mime_type:
                        extensao = "xlsx" if formato.startswith("Excel") else "csv"
                        st.download_button(
                            label="⬇️ Clique para Baixar",
                            data=data,
                            file_name=f"{nome_arquivo}.{extensao}",
                            mime=mime_type,
                            type="primary",
                            use_container_width=True
                        )
                        st.success("✅ Arquivo pronto para download!")
                    else:
                        st.error(f"❌ {error}")
            
            # Outros datasets
            outros_datasets = {k: v for k, v in st.session_state.get('dataframes', {}).items() 
                             if k != 'DADOS_CONSOLIDADOS' and v is not None and not v.empty}
            
            if outros_datasets:
                st.markdown("---")
                st.markdown("### 📄 Outros Datasets")
                
                for nome, df in outros_datasets.items():
                    with st.expander(f"{nome} ({len(df):,} registros)"):
                        st.dataframe(df.head(), use_container_width=True)
    
    # ============================================
    # ABA 3: ANÁLISE DETALHADA
    # ============================================
    with tab3:
        st.markdown("## 🔍 Análise Detalhada")
        
        df_principal = get_dataframe_safe('DADOS_CONSOLIDADOS')
        
        if df_principal is None or df_principal.empty:
            st.info("Processe dados primeiro para acessar ferramentas de análise.")
        else:
            # Filtros
            st.markdown("### 🎯 Filtros de Análise")
            
            col_f1, col_f2 = st.columns(2)
            
            with col_f1:
                # Filtro por projeto
                if 'PROJETO' in df_principal.columns:
                    projetos = ['Todos'] + sorted(df_principal['PROJETO'].dropna().unique().tolist())
                    projeto_selecionado = st.selectbox("Projeto:", projetos)
                else:
                    projeto_selecionado = 'Todos'
            
            with col_f2:
                # Filtro por status
                if 'STATUS_PAGAMENTO' in df_principal.columns:
                    status_opcoes = ['Todos'] + sorted(df_principal['STATUS_PAGAMENTO'].dropna().unique().tolist())
                    status_selecionado = st.selectbox("Status:", status_opcoes)
                else:
                    status_selecionado = 'Todos'
            
            # Aplicar filtros
            df_filtrado = df_principal.copy()
            
            if projeto_selecionado != 'Todos' and 'PROJETO' in df_filtrado.columns:
                df_filtrado = df_filtrado[df_filtrado['PROJETO'] == projeto_selecionado]
            
            if status_selecionado != 'Todos' and 'STATUS_PAGAMENTO' in df_filtrado.columns:
                df_filtrado = df_filtrado[df_filtrado['STATUS_PAGAMENTO'] == status_selecionado]
            
            st.markdown(f"### 📊 Resultados: {len(df_filtrado):,} registros encontrados")
            
            if df_filtrado.empty:
                st.warning("Nenhum registro encontrado com os filtros aplicados.")
            else:
                # Métricas dos dados filtrados
                col_m1, col_m2, col_m3 = st.columns(3)
                
                with col_m1:
                    if 'VALOR_TOTAL' in df_filtrado.columns:
                        valor_total = df_filtrado['VALOR_TOTAL'].sum()
                        st.metric("Valor Total", formatar_valor_brl(valor_total))
                
                with col_m2:
                    if 'VALOR_PAGAMENTO' in df_filtrado.columns:
                        valor_pago = df_filtrado['VALOR_PAGAMENTO'].sum()
                        st.metric("Valor Pago", formatar_valor_brl(valor_pago))
                
                with col_m3:
                    if 'NOME' in df_filtrado.columns:
                        beneficiarios = df_filtrado['NOME'].nunique()
                        st.metric("Beneficiários Únicos", formatar_numero(beneficiarios))
                
                # Visualização dos dados filtrados
                st.markdown("### 📋 Dados Filtrados")
                
                colunas_importantes = ['NOME', 'PROJETO', 'VALOR_TOTAL', 'VALOR_PAGAMENTO', 'STATUS_PAGAMENTO']
                colunas_disponiveis = [col for col in colunas_importantes if col in df_filtrado.columns]
                
                if colunas_disponiveis:
                    st.dataframe(
                        df_filtrado[colunas_disponiveis].head(100),
                        use_container_width=True,
                        height=400
                    )
                
                # Análises gráficas
                st.markdown("---")
                st.markdown("### 📈 Análises Gráficas")
                
                tab_a1, tab_a2 = st.tabs(["📊 Distribuição", "🏆 Top Valores"])
                
                with tab_a1:
                    if 'AGENCIA' in df_filtrado.columns:
                        st.markdown("#### Distribuição por Agência")
                        
                        agencia_counts = df_filtrado['AGENCIA'].value_counts().head(15)
                        
                        fig_agencia = px.bar(
                            x=agencia_counts.index,
                            y=agencia_counts.values,
                            title='Top 15 Agências',
                            labels={'x': 'Agência', 'y': 'Quantidade'}
                        )
                        
                        fig_agencia.update_layout(xaxis_tickangle=-45)
                        st.plotly_chart(fig_agencia, use_container_width=True)
                    else:
                        st.info("Coluna 'AGENCIA' não encontrada")
                
                with tab_a2:
                    if 'PROJETO' in df_filtrado.columns and 'VALOR_TOTAL' in df_filtrado.columns:
                        st.markdown("#### Distribuição de Valores por Projeto")
                        
                        projeto_valores = df_filtrado.groupby('PROJETO')['VALOR_TOTAL'].sum()
                        projeto_valores = projeto_valores.sort_values(ascending=False).head(10)
                        
                        fig_valores = px.pie(
                            values=projeto_valores.values,
                            names=projeto_valores.index,
                            title='Top 10 Projetos por Valor'
                        )
                        
                        st.plotly_chart(fig_valores, use_container_width=True)
                    else:
                        st.info("Dados insuficientes para análise")
    
    # ============================================
    # ABA 4: CONFIGURAÇÕES
    # ============================================
    with tab4:
        st.markdown("## ⚙️ Configurações do Sistema")
        
        config = st.session_state.get('config', {})
        
        # Configurações de processamento
        st.markdown("### ⚡ Processamento")
        
        col_c1, col_c2, col_c3 = st.columns(3)
        
        with col_c1:
            novo_limite = st.number_input(
                "Limite de registros:",
                min_value=1000,
                max_value=500000,
                value=config.get('limite_registros', 100000),
                step=1000
            )
        
        with col_c2:
            formato_exp = st.selectbox(
                "Formato de exportação:",
                ["Excel (.xlsx)", "CSV (.csv)"],
                index=0 if config.get('formato_exportacao', '').startswith('Excel') else 1
            )
        
        with col_c3:
            incluir_graficos = st.checkbox(
                "Incluir gráficos",
                value=config.get('incluir_graficos', True)
            )
        
        # Configurações de validação
        st.markdown("### 🔍 Validação")
        
        col_v1, col_v2 = st.columns(2)
        
        with col_v1:
            auto_validar = st.checkbox(
                "Validação automática",
                value=config.get('auto_validar', True)
            )
        
        with col_v2:
            manter_historico = st.checkbox(
                "Manter histórico",
                value=config.get('manter_historico', True)
            )
        
        # Botões de ação
        st.markdown("---")
        
        col_b1, col_b2 = st.columns(2)
        
        with col_b1:
            if st.button("💾 Salvar Configurações", type="primary", use_container_width=True):
                st.session_state['config'] = {
                    'limite_registros': novo_limite,
                    'formato_exportacao': formato_exp,
                    'incluir_graficos': incluir_graficos,
                    'auto_validar': auto_validar,
                    'manter_historico': manter_historico
                }
                st.success("✅ Configurações salvas!")
                st.rerun()
        
        with col_b2:
            if st.button("🔄 Restaurar Padrões", use_container_width=True):
                st.session_state['config'] = {
                    'auto_validar': True,
                    'manter_historico': True,
                    'limite_registros': 100000,
                    'formato_exportacao': "Excel (.xlsx)",
                    'incluir_graficos': True
                }
                st.success("✅ Configurações padrão restauradas!")
                st.rerun()
        
        # Informações do sistema
        st.markdown("---")
        st.markdown("### 📊 Informações do Sistema")
        
        with st.expander("Detalhes técnicos", expanded=False):
            st.markdown(f"""
            **Versão:** 2.2.0  
            **Python:** {pd.__version__}  
            **Streamlit:** {st.__version__}  
            
            **Status atual:**  
            • Dados carregados: {len(st.session_state.get('dataframes', {}))}  
            • Processado: {'Sim' if st.session_state.get('is_processed') else 'Não'}  
            • Arquivos: {len(st.session_state.get('uploaded_files', []))}  
            
            **Configurações ativas:**  
            • Limite de registros: {config.get('limite_registros', 100000):,}  
            • Formato exportação: {config.get('formato_exportacao', 'Excel')}  
            • Validação automática: {'Sim' if config.get('auto_validar', True) else 'Não'}  
            """)
            
except Exception as e:
    st.error("### ⚠️ Ocorreu um erro no sistema")
    st.error(f"**Erro:** {str(e)}")
    
    with st.expander("🔧 Detalhes técnicos do erro"):
        st.code(traceback.format_exc())
    
    st.info("""
    **Soluções sugeridas:**
    1. Clique em **🗑️ Limpar Dados** na barra lateral
    2. Recarregue a página
    3. Tente carregar os arquivos novamente
    
    Se o problema persistir, verifique:
    • Formato dos arquivos (CSV, TXT, Excel)
    • Tamanho dos arquivos (máximo 100MB)
    • Estrutura dos dados (colunas esperadas)
    """)

# ============================================
# RODAPÉ
# ============================================
st.markdown("---")
st.markdown(
    """
    <div style="text-align: center; color: #666; padding: 20px; font-size: 0.9em;">
    <strong>💰 SMDET - POT Monitoramento de Pagamento de Benefícios</strong><br>
    Sistema desenvolvido para acompanhamento e análise de pagamentos<br>
    <small>© 2024 - Versão 2.2.0 | Tratamento robusto de erros</small>
    </div>
    """,
    unsafe_allow_html=True
)
