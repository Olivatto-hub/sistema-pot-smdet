import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import plotly.express as px
from datetime import datetime, timezone
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
# CSS OTIMIZADO
# ============================================
st.markdown("""
<style>
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
    
    [data-testid="stMetric"] {
        background-color: #f8f9fa !important;
        padding: 20px;
        border-radius: 12px;
        border: 2px solid #dee2e6;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    
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
</style>
""", unsafe_allow_html=True)

# ============================================
# FUNÇÕES AUXILIARES
# ============================================

def get_local_time():
    """Obtém o horário local correto."""
    # Obtém o horário UTC atual
    utc_now = datetime.now(timezone.utc)
    
    # Converte para o fuso horário de Brasília (UTC-3)
    # Nota: Streamlit Cloud roda em UTC, então precisamos ajustar
    try:
        # Tenta criar um fuso horário para Brasília
        brasilia_tz = timezone.utc  # Default para UTC
        # Ajusta manualmente para UTC-3 (Brasília)
        brasilia_now = utc_now.astimezone(timezone.utc)
        # Adiciona 3 horas para converter UTC para Brasília
        brasilia_now = brasilia_now.replace(hour=(brasilia_now.hour - 3) % 24)
    except:
        # Fallback: usa horário local do servidor
        brasilia_now = datetime.now()
    
    return brasilia_now.strftime("%d/%m/%Y %H:%M")

def safe_convert_to_float(value):
    """Converte um valor para float de forma segura."""
    if pd.isna(value) or value is None:
        return 0.0
    
    try:
        # Se já for numérico
        if isinstance(value, (int, float, np.number)):
            return float(value)
        
        # Se for string, tenta limpar
        if isinstance(value, str):
            # Remove caracteres não numéricos, exceto ponto, vírgula e sinal negativo
            value_str = re.sub(r'[^\d\.,\-]', '', value.strip())
            
            if not value_str:
                return 0.0
            
            # Verifica formato
            if ',' in value_str and '.' in value_str:
                # Tem ambos, assume que vírgula é decimal e ponto é milhar
                value_str = value_str.replace('.', '')
                value_str = value_str.replace(',', '.')
            elif ',' in value_str:
                # Só tem vírgula
                parts = value_str.split(',')
                if len(parts) == 2 and len(parts[1]) <= 2:
                    # Vírgula como separador decimal
                    value_str = value_str.replace(',', '.')
                else:
                    # Vírgula como separador de milhar
                    value_str = value_str.replace(',', '')
            
            return float(value_str)
        
        return float(value)
    
    except:
        return 0.0

def processar_coluna_numerica(serie):
    """Processa uma coluna numérica de forma robusta."""
    try:
        if serie.empty:
            return pd.Series([], dtype='float64')
        
        # Converte todos os valores para float
        serie_processada = serie.apply(safe_convert_to_float)
        
        # Verifica valores extremamente altos
        if len(serie_processada) > 0:
            max_val = serie_processada.max()
            if max_val > 10000000:
                # Verifica se são múltiplos de 100
                if (serie_processada % 100 == 0).all():
                    serie_processada = serie_processada / 100
        
        return serie_processada
    
    except:
        return pd.Series([0.0] * len(serie), index=serie.index)

def clean_column_name(col):
    """Limpa nomes de colunas de forma segura."""
    try:
        if pd.isna(col):
            return "COLUNA_DESCONHECIDA"
        
        col_str = str(col).strip().upper()
        col_str = re.sub(r'[^A-Z0-9_]+', '_', col_str)
        col_str = re.sub(r'_+', '_', col_str)
        col_str = col_str.strip('_')
        
        if not col_str:
            return f"COLUNA_{abs(hash(str(col))) % 10000}"
        
        return col_str
    
    except:
        return f"COLUNA_ERRO_{abs(hash(str(col))) % 10000}"

def ler_arquivo_com_tentativas(file_obj, limite_registros):
    """Tenta ler um arquivo com diferentes métodos."""
    file_name = file_obj.name.lower()
    
    try:
        if file_name.endswith('.csv'):
            # Tenta diferentes encodings e delimitadores
            encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252', 'utf-8-sig']
            delimitadores = [';', ',', '\t']
            
            for encoding in encodings:
                for delimitador in delimitadores:
                    try:
                        file_obj.seek(0)
                        df = pd.read_csv(
                            file_obj,
                            sep=delimitador,
                            encoding=encoding,
                            on_bad_lines='skip',
                            nrows=limite_registros,
                            dtype=str,
                            low_memory=False,
                            engine='python'
                        )
                        if len(df.columns) > 1:
                            return df, f"CSV ({delimitador}, {encoding})"
                    except:
                        continue
        
        elif file_name.endswith(('.xlsx', '.xls')):
            try:
                file_obj.seek(0)
                engine = 'openpyxl' if file_name.endswith('.xlsx') else None
                df = pd.read_excel(file_obj, nrows=limite_registros, dtype=str, engine=engine)
                return df, "Excel"
            except:
                pass
        
        return None, "Não foi possível ler o arquivo"
    
    except:
        return None, "Erro ao ler arquivo"

@st.cache_data(show_spinner="🔄 Processando arquivos...")
def processar_arquivos(uploaded_files, limite_registros):
    """Processa todos os arquivos carregados."""
    resultados = {
        'dataframes': {},
        'errors': [],
        'total_registros': 0
    }
    
    if not uploaded_files:
        resultados['errors'].append("Nenhum arquivo carregado")
        return resultados
    
    dados_consolidados = []
    
    for file_idx, file_obj in enumerate(uploaded_files):
        try:
            file_name = file_obj.name
            
            # Tenta ler o arquivo
            df, metodo = ler_arquivo_com_tentativas(file_obj, limite_registros)
            
            if df is None or df.empty:
                resultados['errors'].append(f"{file_name}: Arquivo vazio ou não pôde ser lido")
                continue
            
            # Limpa nomes das colunas
            df.columns = [clean_column_name(col) for col in df.columns]
            
            # Remove colunas completamente vazias
            df = df.dropna(axis=1, how='all')
            
            if df.empty:
                resultados['errors'].append(f"{file_name}: Nenhum dado válido após limpeza")
                continue
            
            # Processa colunas numéricas
            colunas_valor = [col for col in df.columns if 'VALOR' in col]
            for col in colunas_valor:
                if col in df.columns:
                    df[col] = processar_coluna_numerica(df[col])
            
            # Processa colunas de texto
            for col in ['NOME', 'PROJETO', 'AGENCIA']:
                if col in df.columns:
                    df[col] = df[col].astype(str).str.strip()
                    if col == 'PROJETO':
                        df[col] = df[col].str.upper()
                    elif col == 'NOME':
                        df[col] = df[col].str.title()
            
            # Adiciona metadados
            df['ARQUIVO_ORIGEM'] = file_name
            df['DATA_CARREGAMENTO'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Salva individualmente
            resultados['dataframes'][f"ARQUIVO_{file_idx}"] = df
            dados_consolidados.append(df)
            
        except Exception as e:
            resultados['errors'].append(f"{file_obj.name}: {str(e)[:100]}")
    
    # Consolida todos os dados
    if dados_consolidados:
        try:
            # Concatena todos os DataFrames
            df_consolidado = pd.concat(dados_consolidados, ignore_index=True, sort=False)
            
            # Remove duplicatas completas
            df_consolidado = df_consolidado.drop_duplicates()
            
            # Garante colunas essenciais
            colunas_valor_consolidado = [col for col in df_consolidado.columns if 'VALOR' in col]
            
            if 'VALOR_PAGAMENTO' not in df_consolidado.columns and colunas_valor_consolidado:
                # Renomeia a primeira coluna de valor para VALOR_PAGAMENTO
                df_consolidado = df_consolidado.rename(
                    columns={colunas_valor_consolidado[0]: 'VALOR_PAGAMENTO'}
                )
            
            # Processa colunas numéricas novamente para garantir
            for col in ['VALOR_TOTAL', 'VALOR_PAGAMENTO', 'VALOR_DESCONTO']:
                if col in df_consolidado.columns:
                    df_consolidado[col] = processar_coluna_numerica(df_consolidado[col])
            
            # Cria coluna de status - CORREÇÃO DO ERRO CRÍTICO
            if 'VALOR_PAGAMENTO' in df_consolidado.columns:
                # Garante que é numérico
                df_consolidado['VALOR_PAGAMENTO'] = processar_coluna_numerica(df_consolidado['VALOR_PAGAMENTO'])
                # Agora podemos fazer a comparação numérica
                df_consolidado['STATUS_PAGAMENTO'] = np.where(
                    df_consolidado['VALOR_PAGAMENTO'] > 0, 
                    'PAGO', 
                    'PENDENTE'
                )
            else:
                df_consolidado['STATUS_PAGAMENTO'] = 'PENDENTE'
            
            # Calcula valor pendente
            if 'VALOR_TOTAL' in df_consolidado.columns and 'VALOR_PAGAMENTO' in df_consolidado.columns:
                # Garante que são numéricos
                df_consolidado['VALOR_TOTAL'] = processar_coluna_numerica(df_consolidado['VALOR_TOTAL'])
                df_consolidado['VALOR_PAGAMENTO'] = processar_coluna_numerica(df_consolidado['VALOR_PAGAMENTO'])
                
                if 'VALOR_DESCONTO' in df_consolidado.columns:
                    df_consolidado['VALOR_DESCONTO'] = processar_coluna_numerica(df_consolidado['VALOR_DESCONTO'])
                    df_consolidado['VALOR_PENDENTE'] = (
                        df_consolidado['VALOR_TOTAL'] - 
                        df_consolidado['VALOR_PAGAMENTO'] - 
                        df_consolidado['VALOR_DESCONTO'].fillna(0)
                    )
                else:
                    df_consolidado['VALOR_PENDENTE'] = (
                        df_consolidado['VALOR_TOTAL'] - 
                        df_consolidado['VALOR_PAGAMENTO']
                    )
            
            # Adiciona ao dicionário de resultados
            resultados['dataframes']['DADOS_CONSOLIDADOS'] = df_consolidado
            resultados['total_registros'] = len(df_consolidado)
            
        except Exception as e:
            resultados['errors'].append(f"Erro ao consolidar dados: {str(e)}")
    
    return resultados

def formatar_valor_brl(valor):
    """Formata valor para Real Brasileiro."""
    try:
        valor_float = safe_convert_to_float(valor)
        return f"R$ {valor_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "R$ 0,00"

def formatar_numero(numero):
    """Formata número com separadores de milhar."""
    try:
        numero_int = int(safe_convert_to_float(numero))
        return f"{numero_int:,}".replace(",", ".")
    except:
        return "0"

def create_download_link(df, filename, file_format):
    """Cria link de download."""
    try:
        if df.empty:
            return None, None, "DataFrame vazio"
        
        if file_format == "CSV (.csv)":
            csv = df.to_csv(index=False, sep=';', encoding='latin1')
            return csv, "text/csv", None
        
        elif file_format == "Excel (.xlsx)":
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Dados')
            output.seek(0)
            return output.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", None
        
        return None, None, "Formato não suportado"
    
    except Exception as e:
        return None, None, f"Erro: {str(e)}"

# ============================================
# INICIALIZAÇÃO DO ESTADO
# ============================================
if 'dataframes' not in st.session_state:
    st.session_state.dataframes = {}
if 'is_processed' not in st.session_state:
    st.session_state.is_processed = False
if 'config' not in st.session_state:
    st.session_state.config = {
        'limite_registros': 100000,
        'formato_exportacao': "Excel (.xlsx)",
        'auto_validar': True
    }
if 'current_page' not in st.session_state:
    st.session_state.current_page = 1

# ============================================
# LAYOUT PRINCIPAL
# ============================================

try:
    st.markdown("<p class='main-header'>💰 SMDET - POT Monitoramento de Pagamento de Benefícios</p>", unsafe_allow_html=True)
    
    # Barra de status com horário corrigido
    with st.container():
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            status = "✅ Processado" if st.session_state.get('is_processed', False) else "⏳ Aguardando"
            st.markdown(f"**Status:** {status}")
        with col2:
            file_count = len([k for k in st.session_state.dataframes.keys() if k.startswith('ARQUIVO_')])
            st.markdown(f"**Arquivos:** {file_count}")
        with col3:
            if 'DADOS_CONSOLIDADOS' in st.session_state.dataframes:
                df_len = len(st.session_state.dataframes['DADOS_CONSOLIDADOS'])
                st.markdown(f"**Registros:** {formatar_numero(df_len)}")
            else:
                st.markdown("**Registros:** 0")
        with col4:
            # Usa a função corrigida para obter horário local
            current_time = get_local_time()
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
            key="file_uploader_main"  # Chave única
        )
        
        if uploaded_files:
            with st.expander(f"📋 Arquivos ({len(uploaded_files)})", expanded=True):
                for file in uploaded_files[:3]:
                    size_mb = len(file.getvalue()) / 1024 / 1024
                    st.markdown(f"• {file.name} ({size_mb:.2f} MB)")
                if len(uploaded_files) > 3:
                    st.markdown(f"• ... e mais {len(uploaded_files) - 3} arquivos")
        
        st.markdown("### ⚙️ CONFIGURAÇÕES")
        
        config = st.session_state.config
        limite_registros = st.number_input(
            "Limite de registros por arquivo:",
            min_value=1000,
            max_value=500000,
            value=config.get('limite_registros', 100000),
            step=1000,
            key="limite_registros_input"  # Chave única
        )
        
        # Botão de processamento
        if st.button("🚀 PROCESSAR DADOS", type="primary", use_container_width=True):
            if uploaded_files:
                with st.spinner("Processando arquivos..."):
                    # Atualiza configurações
                    st.session_state.config['limite_registros'] = limite_registros
                    
                    # Processa arquivos
                    resultados = processar_arquivos(uploaded_files, limite_registros)
                    
                    # Atualiza session state
                    st.session_state.dataframes = resultados['dataframes']
                    
                    # Verifica se há dados consolidados
                    if 'DADOS_CONSOLIDADOS' in resultados['dataframes']:
                        df_consolidado = resultados['dataframes']['DADOS_CONSOLIDADOS']
                        if not df_consolidado.empty:
                            st.session_state.is_processed = True
                            
                            # Mostra sucesso
                            st.success(f"✅ Processamento concluído!")
                            
                            # Mostra resumo
                            col_res1, col_res2 = st.columns(2)
                            with col_res1:
                                st.metric("Registros", formatar_numero(len(df_consolidado)))
                            with col_res2:
                                if 'PROJETO' in df_consolidado.columns:
                                    st.metric("Projetos", df_consolidado['PROJETO'].nunique())
                            
                            # Mostra erros se houver
                            if resultados['errors']:
                                with st.expander("⚠️ Alguns avisos", expanded=False):
                                    for error in resultados['errors']:
                                        st.warning(error)
                        else:
                            st.warning("⚠️ Dados processados, mas dataset consolidado está vazio")
                    else:
                        st.warning("⚠️ Não foi possível consolidar os dados")
                        
                        # Mostra erros detalhados
                        if resultados['errors']:
                            with st.expander("❌ Erros encontrados", expanded=True):
                                for error in resultados['errors']:
                                    st.error(error)
            else:
                st.error("❌ Selecione pelo menos um arquivo")
        
        st.markdown("---")
        
        # Status do sistema
        st.markdown("### 📊 STATUS")
        
        if st.session_state.is_processed:
            st.success("✅ Dados processados")
        else:
            st.info("⏳ Aguardando dados")
        
        # Ações rápidas
        st.markdown("### ⚡ AÇÕES")
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🗑️ Limpar", use_container_width=True):
                st.session_state.dataframes = {}
                st.session_state.is_processed = False
                st.session_state.current_page = 1
                st.success("✅ Dados limpos!")
                st.rerun()
        
        with col_btn2:
            if st.button("🔄 Atualizar", use_container_width=True):
                st.rerun()
        
        st.markdown("---")
        st.markdown("""
        <div style="text-align: center; font-size: 0.9em; color: #666;">
        <strong>SMDET - POT</strong><br>
        Sistema de Monitoramento<br>
        Versão 2.4.0
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
        
        df_consolidado = st.session_state.dataframes.get('DADOS_CONSOLIDADOS')
        
        if df_consolidado is None or df_consolidado.empty:
            st.info("""
            ### 👋 Bem-vindo ao Dashboard!
            
            **Para começar:**
            1. 📥 Carregue arquivos na barra lateral
            2. 🚀 Clique em **PROCESSAR DADOS**
            3. 📊 Visualize as métricas aqui
            """)
        else:
            try:
                # Métricas principais
                total_registros = len(df_consolidado)
                
                # Conta projetos
                total_projetos = 0
                if 'PROJETO' in df_consolidado.columns:
                    total_projetos = df_consolidado['PROJETO'].nunique()
                
                # Calcula valores
                if 'VALOR_PAGAMENTO' in df_consolidado.columns:
                    df_consolidado['VALOR_PAGAMENTO'] = processar_coluna_numerica(df_consolidado['VALOR_PAGAMENTO'])
                    valor_total_pago = df_consolidado['VALOR_PAGAMENTO'].sum()
                    qtd_pagos = (df_consolidado['VALOR_PAGAMENTO'] > 0).sum()
                else:
                    valor_total_pago = 0.0
                    qtd_pagos = 0
                
                if 'VALOR_TOTAL' in df_consolidado.columns:
                    df_consolidado['VALOR_TOTAL'] = processar_coluna_numerica(df_consolidado['VALOR_TOTAL'])
                    valor_total = df_consolidado['VALOR_TOTAL'].sum()
                else:
                    valor_total = valor_total_pago
                
                # Cards de métricas
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Total de Registros", formatar_numero(total_registros))
                
                with col2:
                    st.metric("Projetos", formatar_numero(total_projetos))
                
                with col3:
                    st.metric("Pagamentos", formatar_numero(qtd_pagos))
                
                with col4:
                    st.metric("Valor Pago", formatar_valor_brl(valor_total_pago))
                
                st.markdown("---")
                
                # Gráficos
                col_g1, col_g2 = st.columns(2)
                
                with col_g1:
                    st.markdown("### 📈 Status de Pagamento")
                    
                    if 'STATUS_PAGAMENTO' in df_consolidado.columns:
                        status_counts = df_consolidado['STATUS_PAGAMENTO'].value_counts()
                        
                        fig_status = px.pie(
                            values=status_counts.values,
                            names=status_counts.index,
                            title='',
                            color_discrete_sequence=['#10B981', '#F59E0B'],
                            hole=0.4
                        )
                        
                        fig_status.update_traces(
                            textposition='inside',
                            textinfo='percent+label'
                        )
                        
                        st.plotly_chart(fig_status, use_container_width=True)
                
                with col_g2:
                    st.markdown("### 🏗️ Top Projetos")
                    
                    if 'PROJETO' in df_consolidado.columns and 'VALOR_TOTAL' in df_consolidado.columns:
                        try:
                            projeto_summary = df_consolidado.groupby('PROJETO')['VALOR_TOTAL'].sum()
                            projeto_summary = projeto_summary.sort_values(ascending=False).head(10)
                            
                            fig_projeto = px.bar(
                                x=projeto_summary.index,
                                y=projeto_summary.values,
                                title='',
                                labels={'x': 'Projeto', 'y': 'Valor Total (R$)'}
                            )
                            
                            fig_projeto.update_layout(xaxis_tickangle=-45)
                            st.plotly_chart(fig_projeto, use_container_width=True)
                        except:
                            st.info("Não foi possível gerar gráfico")
                
                # Tabela de resumo
                st.markdown("---")
                st.markdown("### 📋 Resumo por Projeto")
                
                if 'PROJETO' in df_consolidado.columns:
                    try:
                        resumo = df_consolidado.groupby('PROJETO').agg({
                            'NOME': 'count',
                            'VALOR_TOTAL': 'sum',
                            'VALOR_PAGAMENTO': 'sum'
                        }).reset_index()
                        
                        resumo.columns = ['Projeto', 'Beneficiários', 'Valor Total', 'Valor Pago']
                        
                        # Formata valores
                        resumo['Valor Total'] = resumo['Valor Total'].apply(formatar_valor_brl)
                        resumo['Valor Pago'] = resumo['Valor Pago'].apply(formatar_valor_brl)
                        
                        st.dataframe(resumo, use_container_width=True, height=300)
                    except:
                        st.info("Não foi possível gerar resumo")
                    
            except Exception as e:
                st.error(f"Erro no dashboard: {str(e)}")
    
    # ============================================
    # ABA 2: DADOS E EXPORTAÇÃO
    # ============================================
    with tab2:
        st.markdown("## 📁 Dados Carregados")
        
        df_consolidado = st.session_state.dataframes.get('DADOS_CONSOLIDADOS')
        
        if df_consolidado is None or df_consolidado.empty:
            st.info("Nenhum dado disponível.")
        else:
            # Estatísticas
            col_s1, col_s2, col_s3 = st.columns(3)
            with col_s1:
                st.metric("Registros", formatar_numero(len(df_consolidado)))
            with col_s2:
                st.metric("Colunas", len(df_consolidado.columns))
            with col_s3:
                if 'VALOR_TOTAL' in df_consolidado.columns:
                    valor_total = df_consolidado['VALOR_TOTAL'].sum()
                    st.metric("Valor Total", formatar_valor_brl(valor_total))
            
            # Visualização dos dados
            st.markdown("### 👁️ Visualização")
            
            # Configurações
            col_v1, col_v2 = st.columns(2)
            with col_v1:
                linhas_por_pagina = st.slider(
                    "Linhas por página:",
                    min_value=10,
                    max_value=200,
                    value=50,
                    step=10,
                    key="linhas_por_pagina_tab2"  # Chave única
                )
            
            with col_v2:
                total_paginas = max(1, len(df_consolidado) // linhas_por_pagina + 
                                  (1 if len(df_consolidado) % linhas_por_pagina > 0 else 0))
                pagina = st.number_input(
                    "Página:",
                    min_value=1,
                    max_value=total_paginas,
                    value=st.session_state.current_page,
                    step=1,
                    key="pagina_tab2"  # Chave única
                )
            
            # Seleção de colunas
            colunas_disponiveis = df_consolidado.columns.tolist()
            colunas_padrao = []
            for col in ['NOME', 'PROJETO', 'VALOR_TOTAL', 'VALOR_PAGAMENTO', 'STATUS_PAGAMENTO']:
                if col in colunas_disponiveis:
                    colunas_padrao.append(col)
            
            colunas_selecionadas = st.multiselect(
                "Colunas para exibir:",
                colunas_disponiveis,
                default=colunas_padrao,
                key="colunas_tab2"  # Chave única
            )
            
            if colunas_selecionadas:
                inicio = (pagina - 1) * linhas_por_pagina
                fim = min(inicio + linhas_por_pagina, len(df_consolidado))
                
                df_exibir = df_consolidado[colunas_selecionadas].iloc[inicio:fim].copy()
                
                # Formata valores monetários
                for col in df_exibir.columns:
                    if 'VALOR' in col:
                        df_exibir[col] = df_exibir[col].apply(formatar_valor_brl)
                
                st.dataframe(df_exibir, use_container_width=True, height=400)
                
                st.caption(f"Mostrando {inicio + 1} a {fim} de {len(df_consolidado):,}")
            
            # Exportação
            st.markdown("---")
            st.markdown("### 💾 Exportação")
            
            col_e1, col_e2 = st.columns(2)
            
            with col_e1:
                formato = st.selectbox(
                    "Formato:",
                    ["Excel (.xlsx)", "CSV (.csv)"],
                    index=0,
                    key="formato_export_tab2"  # Chave única
                )
            
            with col_e2:
                nome_arquivo = st.text_input(
                    "Nome do arquivo:",
                    value=f"dados_smdet_{datetime.now().strftime('%Y%m%d_%H%M')}",
                    key="nome_arquivo_tab2"  # Chave única
                )
            
            if st.button("📥 Exportar Dados", type="primary", use_container_width=True, key="exportar_tab2"):
                with st.spinner("Gerando arquivo..."):
                    data, mime_type, error = create_download_link(df_consolidado, nome_arquivo, formato)
                    
                    if data and mime_type:
                        extensao = "xlsx" if formato.startswith("Excel") else "csv"
                        st.download_button(
                            label="⬇️ Baixar",
                            data=data,
                            file_name=f"{nome_arquivo}.{extensao}",
                            mime=mime_type,
                            use_container_width=True,
                            key="download_tab2"  # Chave única
                        )
                        st.success("✅ Arquivo pronto!")
                    else:
                        st.error(f"❌ {error}")
    
    # ============================================
    # ABA 3: ANÁLISE
    # ============================================
    with tab3:
        st.markdown("## 🔍 Análise Detalhada")
        
        df_consolidado = st.session_state.dataframes.get('DADOS_CONSOLIDADOS')
        
        if df_consolidado is None or df_consolidado.empty:
            st.info("Carregue dados primeiro.")
        else:
            # Filtros
            st.markdown("### 🎯 Filtros")
            
            col_f1, col_f2 = st.columns(2)
            
            with col_f1:
                # Filtro por projeto com chave única
                if 'PROJETO' in df_consolidado.columns:
                    projetos = ['Todos'] + sorted(df_consolidado['PROJETO'].dropna().unique().tolist())
                    projeto_selecionado = st.selectbox(
                        "Projeto:", 
                        projetos,
                        key="projeto_select_tab3"  # Chave única
                    )
                else:
                    projeto_selecionado = 'Todos'
            
            with col_f2:
                # Filtro por status com chave única
                if 'STATUS_PAGAMENTO' in df_consolidado.columns:
                    status_opcoes = ['Todos'] + sorted(df_consolidado['STATUS_PAGAMENTO'].dropna().unique().tolist())
                    status_selecionado = st.selectbox(
                        "Status:", 
                        status_opcoes,
                        key="status_select_tab3"  # Chave única
                    )
                else:
                    status_selecionado = 'Todos'
            
            # Aplicar filtros
            df_filtrado = df_consolidado.copy()
            
            if projeto_selecionado != 'Todos' and 'PROJETO' in df_filtrado.columns:
                df_filtrado = df_filtrado[df_filtrado['PROJETO'] == projeto_selecionado]
            
            if status_selecionado != 'Todos' and 'STATUS_PAGAMENTO' in df_filtrado.columns:
                df_filtrado = df_filtrado[df_filtrado['STATUS_PAGAMENTO'] == status_selecionado]
            
            st.markdown(f"### 📊 Resultados: {len(df_filtrado):,} registros")
            
            if df_filtrado.empty:
                st.warning("Nenhum registro encontrado.")
            else:
                # Métricas
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
                        st.metric("Beneficiários", formatar_numero(beneficiarios))
                
                # Dados filtrados
                st.markdown("### 📋 Dados")
                
                colunas_importantes = []
                for col in ['NOME', 'PROJETO', 'VALOR_TOTAL', 'VALOR_PAGAMENTO', 'STATUS_PAGAMENTO']:
                    if col in df_filtrado.columns:
                        colunas_importantes.append(col)
                
                if colunas_importantes:
                    st.dataframe(
                        df_filtrado[colunas_importantes].head(100),
                        use_container_width=True,
                        height=300
                    )
                
                # Análises
                st.markdown("---")
                st.markdown("### 📈 Análises")
                
                tab_a1, tab_a2 = st.tabs(["📊 Distribuição", "🏆 Agências"])
                
                with tab_a1:
                    if 'PROJETO' in df_filtrado.columns and 'VALOR_TOTAL' in df_filtrado.columns:
                        try:
                            projeto_valores = df_filtrado.groupby('PROJETO')['VALOR_TOTAL'].sum()
                            projeto_valores = projeto_valores.sort_values(ascending=False).head(10)
                            
                            fig = px.bar(
                                x=projeto_valores.index,
                                y=projeto_valores.values,
                                title='Top Projetos por Valor'
                            )
                            st.plotly_chart(fig, use_container_width=True)
                        except:
                            st.info("Não foi possível gerar análise")
                
                with tab_a2:
                    if 'AGENCIA' in df_filtrado.columns:
                        try:
                            agencia_counts = df_filtrado['AGENCIA'].value_counts().head(10)
                            fig = px.bar(
                                x=agencia_counts.index,
                                y=agencia_counts.values,
                                title='Top Agências'
                            )
                            st.plotly_chart(fig, use_container_width=True)
                        except:
                            st.info("Não foi possível gerar análise")
    
    # ============================================
    # ABA 4: CONFIGURAÇÕES
    # ============================================
    with tab4:
        st.markdown("## ⚙️ Configurações")
        
        config = st.session_state.config
        
        st.markdown("### ⚡ Processamento")
        
        col_c1, col_c2 = st.columns(2)
        
        with col_c1:
            novo_limite = st.number_input(
                "Limite de registros:",
                min_value=1000,
                max_value=500000,
                value=config.get('limite_registros', 100000),
                step=1000,
                key="limite_tab4"  # Chave única
            )
        
        with col_c2:
            formato_exp = st.selectbox(
                "Formato de exportação:",
                ["Excel (.xlsx)", "CSV (.csv)"],
                index=0 if config.get('formato_exportacao', '').startswith('Excel') else 1,
                key="formato_tab4"  # Chave única
            )
        
        st.markdown("### 🔧 Opções")
        
        auto_validar = st.checkbox(
            "Validação automática",
            value=config.get('auto_validar', True),
            key="autovalidar_tab4"  # Chave única
        )
        
        # Botões
        st.markdown("---")
        
        col_b1, col_b2 = st.columns(2)
        
        with col_b1:
            if st.button("💾 Salvar", type="primary", use_container_width=True, key="salvar_tab4"):
                st.session_state.config = {
                    'limite_registros': novo_limite,
                    'formato_exportacao': formato_exp,
                    'auto_validar': auto_validar
                }
                st.success("✅ Configurações salvas!")
        
        with col_b2:
            if st.button("🔄 Padrões", use_container_width=True, key="padroes_tab4"):
                st.session_state.config = {
                    'limite_registros': 100000,
                    'formato_exportacao': "Excel (.xlsx)",
                    'auto_validar': True
                }
                st.success("✅ Configurações padrão restauradas!")
                st.rerun()
        
        # Informações
        st.markdown("---")
        st.markdown("### 📊 Sistema")
        
        st.info(f"""
        **Versão:** 2.4.0  
        **Status:** {'✅ Processado' if st.session_state.is_processed else '⏳ Aguardando'}  
        **Registros:** {formatar_numero(len(st.session_state.dataframes.get('DADOS_CONSOLIDADOS', pd.DataFrame())))}  
        **Horário local:** {get_local_time()}
        """)

except Exception as e:
    st.error("### ⚠️ Ocorreu um erro")
    st.error(f"**Detalhes:** {str(e)}")
    
    with st.expander("🔧 Ver detalhes técnicos"):
        st.code(traceback.format_exc())
    
    st.info("""
    **Soluções:**
    1. Clique em **🗑️ Limpar** na barra lateral
    2. Recarregue a página
    3. Tente novamente com arquivos menores
    """)

# ============================================
# RODAPÉ
# ============================================
st.markdown("---")
st.markdown(
    """
    <div style="text-align: center; color: #666; padding: 20px;">
    <strong>💰 SMDET - POT Monitoramento de Pagamento de Benefícios</strong><br>
    Sistema desenvolvido para acompanhamento e análise de pagamentos<br>
    <small>Versão 2.4.0 | Horário local: """ + get_local_time() + """</small>
    </div>
    """,
    unsafe_allow_html=True
)
