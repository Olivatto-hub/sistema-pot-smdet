import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO, StringIO
import plotly.express as px
from datetime import datetime, timezone, timedelta
import warnings
import re
import traceback
import chardet
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
    
    .error-box {
        background-color: #fee;
        border-left: 4px solid #ff6b6b;
        padding: 10px 15px;
        margin: 10px 0;
        border-radius: 4px;
    }
    
    .warning-box {
        background-color: #fff3cd;
        border-left: 4px solid #ffc107;
        padding: 10px 15px;
        margin: 10px 0;
        border-radius: 4px;
    }
</style>
""", unsafe_allow_html=True)

# ============================================
# FUNÇÕES AUXILIARES
# ============================================

def get_local_time():
    """Obtém o horário local correto."""
    try:
        # Tenta usar o fuso horário de Brasília
        utc_now = datetime.now(timezone.utc)
        # Brasília é UTC-3 (ou UTC-2 durante horário de verão)
        brasilia_offset = timedelta(hours=-3)
        brasilia_tz = timezone(brasilia_offset)
        brasilia_now = utc_now.astimezone(brasilia_tz)
        return brasilia_now.strftime("%d/%m/%Y %H:%M")
    except:
        # Fallback para horário do servidor
        return datetime.now().strftime("%d/%m/%Y %H:%M")

def detect_encoding(file_content):
    """Detecta a codificação do arquivo."""
    try:
        result = chardet.detect(file_content[:10000])  # Analisa os primeiros 10KB
        encoding = result['encoding']
        confidence = result['confidence']
        
        # Mapeia encodings comuns
        encoding_map = {
            'ISO-8859-1': 'latin-1',
            'Windows-1252': 'cp1252',
            'ascii': 'utf-8'
        }
        
        if encoding in encoding_map:
            encoding = encoding_map[encoding]
        
        # Se confiança baixa, tenta utf-8
        if confidence < 0.7:
            encoding = 'utf-8'
            
        return encoding
    except:
        return 'utf-8'

def detect_delimiter(file_content, encoding='utf-8'):
    """Detecta o delimitador do CSV."""
    try:
        # Converte para string
        sample = file_content[:5000].decode(encoding, errors='ignore')
        
        # Conta ocorrências de delimitadores comuns
        delimiters = [';', ',', '\t', '|']
        counts = {}
        
        for delim in delimiters:
            counts[delim] = sample.count(delim)
        
        # Encontra o delimitador mais comum
        if sum(counts.values()) > 0:
            best_delim = max(counts, key=counts.get)
            return best_delim
        else:
            return ';'  # Default para CSV brasileiro
    except:
        return ';'

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
            value = str(value).strip()
            
            # Remove R$, $ e outros símbolos
            value = re.sub(r'[R\$\s]', '', value)
            
            if not value or value == '':
                return 0.0
            
            # Substitui vírgula por ponto se for decimal brasileiro
            if ',' in value and '.' in value:
                # Se tem ambos, assume que vírgula é decimal e ponto é milhar
                value = value.replace('.', '')
                value = value.replace(',', '.')
            elif ',' in value:
                # Verifica se vírgula é separador decimal ou milhar
                parts = value.split(',')
                if len(parts[-1]) <= 2:  # Provavelmente decimal
                    value = value.replace(',', '.')
                else:  # Provavelmente milhar
                    value = value.replace(',', '')
            
            # Remove caracteres não numéricos restantes
            value = re.sub(r'[^\d\.\-]', '', value)
            
            if not value:
                return 0.0
            
            return float(value)
        
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
        
        # Remove outliers extremos (acima de 100 milhões)
        if len(serie_processada) > 0:
            q99 = serie_processada.quantile(0.99)
            if q99 > 10000000:
                serie_processada = serie_processada.clip(upper=q99)
        
        return serie_processada
    
    except:
        return pd.Series([0.0] * len(serie), index=serie.index)

def clean_column_name(col):
    """Limpa nomes de colunas de forma segura."""
    try:
        if pd.isna(col):
            return "COLUNA_DESCONHECIDA"
        
        col_str = str(col).strip().upper()
        
        # Remove acentos
        col_str = re.sub(r'[ÁÀÂÃ]', 'A', col_str)
        col_str = re.sub(r'[ÉÈÊ]', 'E', col_str)
        col_str = re.sub(r'[ÍÌÎ]', 'I', col_str)
        col_str = re.sub(r'[ÓÒÔÕ]', 'O', col_str)
        col_str = re.sub(r'[ÚÙÛ]', 'U', col_str)
        col_str = re.sub(r'[Ç]', 'C', col_str)
        
        # Remove caracteres especiais
        col_str = re.sub(r'[^A-Z0-9_]+', '_', col_str)
        col_str = re.sub(r'_+', '_', col_str)
        col_str = col_str.strip('_')
        
        if not col_str:
            return f"COLUNA_{abs(hash(str(col))) % 10000}"
        
        return col_str
    
    except:
        return f"COLUNA_ERRO_{abs(hash(str(col))) % 10000}"

def ler_csv_com_tentativas(file_content, limite_registros):
    """Tenta ler um arquivo CSV com diferentes abordagens."""
    tentativas = []
    
    # Tentativa 1: Detectar encoding e delimitador
    try:
        encoding = detect_encoding(file_content)
        delimiter = detect_delimiter(file_content, encoding)
        
        file_content.seek(0)
        df = pd.read_csv(
            file_content,
            sep=delimiter,
            encoding=encoding,
            on_bad_lines='skip',
            nrows=limite_registros,
            dtype=str,
            low_memory=False,
            engine='python'
        )
        
        if len(df.columns) > 1 and len(df) > 0:
            tentativas.append((df, f"CSV - Delimitador: '{delimiter}' - Encoding: {encoding}"))
    except Exception as e:
        tentativas.append((None, f"Tentativa 1 falhou: {str(e)[:50]}"))
    
    # Tentativa 2: Leitura com diferentes encodings
    encodings_to_try = ['latin-1', 'iso-8859-1', 'cp1252', 'utf-8', 'utf-8-sig']
    delimiters_to_try = [';', ',', '\t']
    
    for encoding in encodings_to_try:
        for delimiter in delimiters_to_try:
            try:
                file_content.seek(0)
                df = pd.read_csv(
                    file_content,
                    sep=delimiter,
                    encoding=encoding,
                    on_bad_lines='skip',
                    nrows=limite_registros,
                    dtype=str,
                    low_memory=False,
                    engine='python'
                )
                
                if len(df.columns) > 1 and len(df) > 0:
                    tentativas.append((df, f"CSV - Delimitador: '{delimiter}' - Encoding: {encoding}"))
                    break
            except:
                continue
        
        if tentativas and tentativas[-1][0] is not None:
            break
    
    # Tentativa 3: Leitura linha por linha
    if not tentativas or all(t[0] is None for t in tentativas):
        try:
            file_content.seek(0)
            lines = []
            for i, line in enumerate(file_content):
                if i >= limite_registros:
                    break
                lines.append(line.decode('latin-1', errors='ignore').strip())
            
            # Tenta encontrar um delimitador comum
            sample_line = lines[0] if lines else ''
            possible_delimiters = [';', ',', '\t', '|']
            
            for delim in possible_delimiters:
                if delim in sample_line:
                    # Processa manualmente
                    data = []
                    for line in lines:
                        parts = line.split(delim)
                        data.append(parts)
                    
                    # Cria DataFrame com número consistente de colunas
                    max_cols = max(len(row) for row in data) if data else 0
                    for i, row in enumerate(data):
                        if len(row) < max_cols:
                            data[i] = row + [''] * (max_cols - len(row))
                    
                    df = pd.DataFrame(data)
                    if len(df.columns) > 0 and len(df) > 0:
                        tentativas.append((df, f"Processamento manual - Delimitador: '{delim}'"))
                        break
        except:
            pass
    
    # Retorna a melhor tentativa
    for df, metodo in tentativas:
        if df is not None and not df.empty:
            return df, metodo
    
    return None, "Não foi possível ler o arquivo CSV"

def ler_arquivo_com_tentativas(file_obj, limite_registros):
    """Tenta ler um arquivo com diferentes métodos."""
    file_name = file_obj.name.lower()
    
    try:
        file_content = file_obj.getvalue()
        
        if file_name.endswith('.csv') or file_name.endswith('.txt'):
            return ler_csv_com_tentativas(BytesIO(file_content), limite_registros)
        
        elif file_name.endswith(('.xlsx', '.xls')):
            try:
                file_obj.seek(0)
                engine = 'openpyxl' if file_name.endswith('.xlsx') else None
                df = pd.read_excel(file_obj, nrows=limite_registros, dtype=str, engine=engine)
                if not df.empty:
                    return df, "Excel"
                else:
                    return None, "Arquivo Excel vazio"
            except Exception as e:
                return None, f"Erro Excel: {str(e)[:50]}"
        
        return None, "Formato não suportado"
    
    except Exception as e:
        return None, f"Erro geral: {str(e)[:50]}"

@st.cache_data(show_spinner="🔄 Processando arquivos...")
def processar_arquivos(uploaded_files, limite_registros):
    """Processa todos os arquivos carregados."""
    resultados = {
        'dataframes': {},
        'errors': [],
        'warnings': [],
        'total_registros': 0,
        'metodos': {}
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
            
            if df is None:
                resultados['errors'].append(f"{file_name}: Não foi possível ler o arquivo")
                continue
            
            if df.empty:
                resultados['warnings'].append(f"{file_name}: Arquivo está vazio")
                continue
            
            # Registra método usado
            resultados['metodos'][file_name] = metodo
            
            # Limpa nomes das colunas
            df.columns = [clean_column_name(col) for col in df.columns]
            
            # Remove colunas completamente vazias
            colunas_antes = len(df.columns)
            df = df.dropna(axis=1, how='all')
            colunas_depois = len(df.columns)
            
            if colunas_antes != colunas_depois:
                resultados['warnings'].append(f"{file_name}: Removidas {colunas_antes - colunas_depois} colunas vazias")
            
            if df.empty:
                resultados['warnings'].append(f"{file_name}: Nenhum dado válido após limpeza")
                continue
            
            # Identifica colunas de valor
            colunas_valor = []
            for col in df.columns:
                col_upper = col.upper()
                if any(term in col_upper for term in ['VALOR', 'VLR', 'TOTAL', 'PAGAMENTO', 'PAGTO', 'BRUTO', 'LIQUIDO']):
                    colunas_valor.append(col)
            
            # Processa colunas de valor
            for col in colunas_valor:
                if col in df.columns:
                    df[col] = processar_coluna_numerica(df[col])
                    # Verifica se há valores não numéricos
                    if df[col].isna().sum() > len(df) * 0.5:  # Mais de 50% nulos
                        resultados['warnings'].append(f"{file_name}: Coluna '{col}' tem muitos valores não numéricos")
            
            # Processa colunas de texto
            for col in df.columns:
                if df[col].dtype == 'object':
                    # Limpa strings
                    df[col] = df[col].astype(str).str.strip()
                    
                    # Aplica formatação específica
                    col_upper = col.upper()
                    if 'NOME' in col_upper:
                        df[col] = df[col].str.title()
                    elif 'PROJETO' in col_upper or 'PROGRAMA' in col_upper:
                        df[col] = df[col].str.upper()
                    elif 'CPF' in col_upper or 'CNPJ' in col_upper:
                        # Remove caracteres não numéricos
                        df[col] = df[col].str.replace(r'\D', '', regex=True)
            
            # Adiciona metadados
            df['ARQUIVO_ORIGEM'] = file_name
            df['DATA_CARREGAMENTO'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Salva individualmente
            resultados['dataframes'][f"ARQUIVO_{file_idx}"] = df
            dados_consolidados.append(df)
            
            # Log de sucesso
            resultados['warnings'].append(f"✅ {file_name}: Processado com sucesso ({len(df)} registros)")
            
        except Exception as e:
            error_msg = f"{file_name}: {str(e)[:100]}"
            resultados['errors'].append(error_msg)
    
    # Consolida todos os dados
    if dados_consolidados:
        try:
            # Concatena todos os DataFrames
            df_consolidado = pd.concat(dados_consolidados, ignore_index=True, sort=False)
            
            # Remove duplicatas completas
            registros_antes = len(df_consolidado)
            df_consolidado = df_consolidado.drop_duplicates()
            registros_depois = len(df_consolidado)
            
            if registros_antes != registros_depois:
                resultados['warnings'].append(f"Removidas {registros_antes - registros_depois} duplicatas")
            
            # Garante colunas essenciais
            # Encontra coluna de valor principal
            colunas_valor = [col for col in df_consolidado.columns if 'VALOR' in col]
            
            if colunas_valor:
                # Ordena por preferência
                ordem_preferencia = ['VALOR_PAGAMENTO', 'VALOR_TOTAL', 'VALOR', 'VLR_PAGTO', 'VLR_TOTAL']
                
                for col_pref in ordem_preferencia:
                    if col_pref in df_consolidado.columns:
                        # Renomeia para padronizar
                        if col_pref != 'VALOR_PAGAMENTO':
                            df_consolidado = df_consolidado.rename(columns={col_pref: 'VALOR_PAGAMENTO'})
                        break
                else:
                    # Usa a primeira coluna de valor
                    df_consolidado = df_consolidado.rename(columns={colunas_valor[0]: 'VALOR_PAGAMENTO'})
            
            # Processa colunas numéricas novamente
            colunas_numericas = []
            for col in ['VALOR_TOTAL', 'VALOR_PAGAMENTO', 'VALOR_DESCONTO', 'VALOR_BRUTO', 'VALOR_LIQUIDO']:
                if col in df_consolidado.columns:
                    colunas_numericas.append(col)
            
            for col in colunas_numericas:
                df_consolidado[col] = processar_coluna_numerica(df_consolidado[col])
            
            # Cria coluna de status
            if 'VALOR_PAGAMENTO' in df_consolidado.columns:
                df_consolidado['STATUS_PAGAMENTO'] = np.where(
                    df_consolidado['VALOR_PAGAMENTO'] > 0, 
                    'PAGO', 
                    'PENDENTE'
                )
            else:
                df_consolidado['STATUS_PAGAMENTO'] = 'PENDENTE'
                resultados['warnings'].append("Coluna 'VALOR_PAGAMENTO' não encontrada, todos marcados como PENDENTE")
            
            # Calcula valor pendente se tiver total
            if 'VALOR_TOTAL' in df_consolidado.columns and 'VALOR_PAGAMENTO' in df_consolidado.columns:
                df_consolidado['VALOR_PENDENTE'] = df_consolidado['VALOR_TOTAL'] - df_consolidado['VALOR_PAGAMENTO'].fillna(0)
                
                if 'VALOR_DESCONTO' in df_consolidado.columns:
                    df_consolidado['VALOR_PENDENTE'] = df_consolidado['VALOR_PENDENTE'] - df_consolidado['VALOR_DESCONTO'].fillna(0)
            
            # Adiciona ao dicionário de resultados
            resultados['dataframes']['DADOS_CONSOLIDADOS'] = df_consolidado
            resultados['total_registros'] = len(df_consolidado)
            
            # Log de consolidação
            resultados['warnings'].append(f"✅ Consolidação concluída: {len(df_consolidado)} registros")
            
        except Exception as e:
            error_msg = f"Erro ao consolidar dados: {str(e)[:100]}"
            resultados['errors'].append(error_msg)
            traceback.print_exc()
    
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
            csv = df.to_csv(index=False, sep=';', encoding='latin1', errors='replace')
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
            help="Suporta arquivos CSV (com ; ou ,), TXT e Excel",
            key="file_uploader_main"
        )
        
        if uploaded_files:
            with st.expander(f"📋 Arquivos ({len(uploaded_files)})", expanded=False):
                for file in uploaded_files:
                    size_mb = len(file.getvalue()) / 1024 / 1024
                    st.markdown(f"• {file.name} ({size_mb:.1f} MB)")
        
        st.markdown("### ⚙️ CONFIGURAÇÕES")
        
        config = st.session_state.config
        limite_registros = st.number_input(
            "Limite de registros por arquivo:",
            min_value=1000,
            max_value=500000,
            value=config.get('limite_registros', 100000),
            step=1000,
            help="Limita a leitura para evitar sobrecarga",
            key="limite_registros_input"
        )
        
        st.markdown("---")
        
        # Botão de processamento
        processar_col1, processar_col2 = st.columns([3, 1])
        
        with processar_col1:
            if st.button("🚀 PROCESSAR DADOS", type="primary", use_container_width=True):
                if uploaded_files:
                    with st.spinner(f"Processando {len(uploaded_files)} arquivo(s)..."):
                        try:
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
                                    st.success(f"✅ Processamento concluído com {len(df_consolidado):,} registros!")
                                    
                                    # Mostra resumo
                                    col_res1, col_res2, col_res3 = st.columns(3)
                                    with col_res1:
                                        st.metric("Registros", formatar_numero(len(df_consolidado)))
                                    with col_res2:
                                        if 'PROJETO' in df_consolidado.columns:
                                            st.metric("Projetos", df_consolidado['PROJETO'].nunique())
                                        else:
                                            st.metric("Projetos", "-")
                                    with col_res3:
                                        if 'STATUS_PAGAMENTO' in df_consolidado.columns:
                                            pagos = (df_consolidado['STATUS_PAGAMENTO'] == 'PAGO').sum()
                                            st.metric("Pagamentos", formatar_numero(pagos))
                                    
                                    # Mostra métodos usados
                                    if resultados.get('metodos'):
                                        with st.expander("📊 Métodos de leitura", expanded=False):
                                            for file_name, metodo in resultados['metodos'].items():
                                                st.write(f"**{file_name}:** {metodo}")
                                    
                                    # Mostra avisos se houver
                                    if resultados.get('warnings'):
                                        with st.expander("⚠️ Avisos do processamento", expanded=False):
                                            for warning in resultados['warnings']:
                                                if warning.startswith("✅"):
                                                    st.success(warning)
                                                else:
                                                    st.warning(warning)
                                    
                                    # Mostra erros se houver
                                    if resultados.get('errors'):
                                        with st.expander("❌ Erros encontrados", expanded=False):
                                            for error in resultados['errors']:
                                                st.error(error)
                                    
                                else:
                                    st.warning("⚠️ Dados processados, mas dataset consolidado está vazio")
                            else:
                                st.error("❌ Não foi possível consolidar os dados")
                                
                                # Mostra erros detalhados
                                if resultados.get('errors'):
                                    with st.expander("❌ Erros detalhados", expanded=True):
                                        for error in resultados['errors']:
                                            st.error(error)
                                
                                if resultados.get('warnings'):
                                    with st.expander("⚠️ Avisos", expanded=True):
                                        for warning in resultados['warnings']:
                                            st.warning(warning)
                        except Exception as e:
                            st.error(f"❌ Erro no processamento: {str(e)}")
                            with st.expander("Detalhes do erro"):
                                st.code(traceback.format_exc())
                else:
                    st.error("❌ Selecione pelo menos um arquivo")
        
        with processar_col2:
            if st.button("🔄", use_container_width=True, help="Atualizar página"):
                st.rerun()
        
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
            if st.button("🗑️ Limpar", use_container_width=True, help="Limpar todos os dados"):
                st.session_state.dataframes = {}
                st.session_state.is_processed = False
                st.session_state.current_page = 1
                st.success("✅ Dados limpos!")
                st.rerun()
        
        with col_btn2:
            if st.button("📊 Testar", use_container_width=True, help="Testar com dados de exemplo"):
                # Cria dados de exemplo
                dados_exemplo = pd.DataFrame({
                    'NOME': ['João Silva', 'Maria Santos', 'Pedro Oliveira'],
                    'PROJETO': ['PROJETO A', 'PROJETO B', 'PROJETO A'],
                    'VALOR_TOTAL': [1500.00, 2000.00, 1800.00],
                    'VALOR_PAGAMENTO': [1500.00, 0.00, 1800.00],
                    'STATUS': ['PAGO', 'PENDENTE', 'PAGO']
                })
                st.session_state.dataframes['DADOS_CONSOLIDADOS'] = dados_exemplo
                st.session_state.is_processed = True
                st.success("✅ Dados de exemplo carregados!")
                st.rerun()
        
        st.markdown("---")
        st.markdown("""
        <div style="text-align: center; font-size: 0.9em; color: #666;">
        <strong>SMDET - POT</strong><br>
        Sistema de Monitoramento<br>
        Versão 2.5.0
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
            
            **Formato recomendado:** CSV com colunas como NOME, PROJETO, VALOR_TOTAL, VALOR_PAGAMENTO
            """)
            
            # Botão para dados de exemplo
            if st.button("📋 Carregar dados de exemplo", type="secondary"):
                dados_exemplo = pd.DataFrame({
                    'NOME': ['João Silva', 'Maria Santos', 'Pedro Oliveira', 'Ana Costa', 'Carlos Lima'],
                    'PROJETO': ['PROJETO A', 'PROJETO B', 'PROJETO A', 'PROJETO C', 'PROJETO B'],
                    'VALOR_TOTAL': [1500.00, 2000.00, 1800.00, 2200.00, 1900.00],
                    'VALOR_PAGAMENTO': [1500.00, 0.00, 1800.00, 2200.00, 950.00],
                    'STATUS_PAGAMENTO': ['PAGO', 'PENDENTE', 'PAGO', 'PAGO', 'PARCIAL']
                })
                st.session_state.dataframes['DADOS_CONSOLIDADOS'] = dados_exemplo
                st.session_state.is_processed = True
                st.success("✅ Dados de exemplo carregados!")
                st.rerun()
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
                            title='Distribuição por Status',
                            color_discrete_sequence=px.colors.qualitative.Set2,
                            hole=0.4
                        )
                        
                        fig_status.update_traces(
                            textposition='inside',
                            textinfo='percent+label',
                            hovertemplate='<b>%{label}</b><br>%{value} registros<br>%{percent}'
                        )
                        
                        st.plotly_chart(fig_status, use_container_width=True)
                    else:
                        st.info("Coluna 'STATUS_PAGAMENTO' não encontrada")
                
                with col_g2:
                    st.markdown("### 🏗️ Top Projetos")
                    
                    if 'PROJETO' in df_consolidado.columns and 'VALOR_TOTAL' in df_consolidado.columns:
                        try:
                            projeto_summary = df_consolidado.groupby('PROJETO')['VALOR_TOTAL'].sum()
                            projeto_summary = projeto_summary.sort_values(ascending=False).head(10)
                            
                            fig_projeto = px.bar(
                                x=projeto_summary.index,
                                y=projeto_summary.values,
                                title='Top 10 Projetos por Valor Total',
                                labels={'x': 'Projeto', 'y': 'Valor Total (R$)'},
                                color=projeto_summary.values,
                                color_continuous_scale='Viridis'
                            )
                            
                            fig_projeto.update_layout(
                                xaxis_tickangle=-45,
                                coloraxis_showscale=False
                            )
                            st.plotly_chart(fig_projeto, use_container_width=True)
                        except:
                            st.info("Não foi possível gerar gráfico")
                    else:
                        st.info("Dados insuficientes para gráfico de projetos")
                
                # Tabela de resumo
                st.markdown("---")
                st.markdown("### 📋 Resumo por Projeto")
                
                if 'PROJETO' in df_consolidado.columns:
                    try:
                        # Prepara dados para resumo
                        colunas_resumo = ['NOME']
                        for col in ['VALOR_TOTAL', 'VALOR_PAGAMENTO']:
                            if col in df_consolidado.columns:
                                colunas_resumo.append(col)
                        
                        resumo = df_consolidado.groupby('PROJETO').agg({
                            'NOME': 'count',
                            **{col: 'sum' for col in colunas_resumo if col != 'NOME'}
                        }).reset_index()
                        
                        # Renomeia colunas
                        resumo = resumo.rename(columns={'NOME': 'Beneficiários'})
                        
                        # Adiciona coluna de % pago
                        if 'VALOR_TOTAL' in resumo.columns and 'VALOR_PAGAMENTO' in resumo.columns:
                            resumo['% Pago'] = (resumo['VALOR_PAGAMENTO'] / resumo['VALOR_TOTAL'] * 100).round(1)
                            resumo['% Pago'] = resumo['% Pago'].apply(lambda x: f"{x}%")
                        
                        # Formata valores
                        for col in ['VALOR_TOTAL', 'VALOR_PAGAMENTO']:
                            if col in resumo.columns:
                                resumo[col] = resumo[col].apply(formatar_valor_brl)
                        
                        # Ordena por valor total
                        if 'VALOR_TOTAL' in resumo.columns:
                            # Extrai valor numérico para ordenação
                            resumo['VALOR_TOTAL_NUM'] = resumo['VALOR_TOTAL'].str.replace('R\$ ', '').str.replace('.', '').str.replace(',', '.').astype(float)
                            resumo = resumo.sort_values('VALOR_TOTAL_NUM', ascending=False)
                            resumo = resumo.drop('VALOR_TOTAL_NUM', axis=1)
                        
                        st.dataframe(resumo, use_container_width=True, height=300)
                    except Exception as e:
                        st.info(f"Não foi possível gerar resumo: {str(e)[:100]}")
                    
            except Exception as e:
                st.error(f"Erro no dashboard: {str(e)}")
                with st.expander("Detalhes do erro"):
                    st.code(traceback.format_exc())
    
    # ============================================
    # ABA 2: DADOS E EXPORTAÇÃO
    # ============================================
    with tab2:
        st.markdown("## 📁 Dados Carregados")
        
        df_consolidado = st.session_state.dataframes.get('DADOS_CONSOLIDADOS')
        
        if df_consolidado is None or df_consolidado.empty:
            st.info("Nenhum dado disponível. Processe arquivos primeiro.")
        else:
            # Estatísticas
            col_s1, col_s2, col_s3, col_s4 = st.columns(4)
            with col_s1:
                st.metric("Registros", formatar_numero(len(df_consolidado)))
            with col_s2:
                st.metric("Colunas", len(df_consolidado.columns))
            with col_s3:
                if 'VALOR_TOTAL' in df_consolidado.columns:
                    valor_total = df_consolidado['VALOR_TOTAL'].sum()
                    st.metric("Valor Total", formatar_valor_brl(valor_total))
                else:
                    st.metric("Valor Total", "-")
            with col_s4:
                if 'STATUS_PAGAMENTO' in df_consolidado.columns:
                    pagos = (df_consolidado['STATUS_PAGAMENTO'] == 'PAGO').sum()
                    st.metric("Pagamentos Efetuados", formatar_numero(pagos))
                else:
                    st.metric("Status", "-")
            
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
                    key="linhas_por_pagina_tab2"
                )
            
            with col_v2:
                total_paginas = max(1, len(df_consolidado) // linhas_por_pagina + 
                                  (1 if len(df_consolidado) % linhas_por_pagina > 0 else 0))
                pagina = st.number_input(
                    "Página:",
                    min_value=1,
                    max_value=total_paginas,
                    value=1,
                    step=1,
                    key="pagina_tab2"
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
                key="colunas_tab2"
            )
            
            if not colunas_selecionadas:
                colunas_selecionadas = colunas_disponiveis[:10]  # Limita a 10 colunas se nenhuma selecionada
            
            inicio = (pagina - 1) * linhas_por_pagina
            fim = min(inicio + linhas_por_pagina, len(df_consolidado))
            
            df_exibir = df_consolidado[colunas_selecionadas].iloc[inicio:fim].copy()
            
            # Formata valores monetários
            for col in df_exibir.columns:
                if 'VALOR' in col.upper():
                    try:
                        df_exibir[col] = df_exibir[col].apply(formatar_valor_brl)
                    except:
                        pass
            
            st.dataframe(df_exibir, use_container_width=True, height=400)
            
            st.caption(f"Mostrando {inicio + 1} a {fim} de {len(df_consolidado):,} registros")
            
            # Informações sobre os dados
            with st.expander("📊 Informações do Dataset", expanded=False):
                st.write(f"**Total de colunas:** {len(df_consolidado.columns)}")
                st.write(f"**Colunas:** {', '.join(df_consolidado.columns.tolist())}")
                
                # Tipos de dados
                st.write("**Tipos de dados:**")
                tipos = df_consolidado.dtypes.astype(str).value_counts()
                for tipo, count in tipos.items():
                    st.write(f"  - {tipo}: {count} colunas")
            
            # Exportação
            st.markdown("---")
            st.markdown("### 💾 Exportação")
            
            col_e1, col_e2 = st.columns(2)
            
            with col_e1:
                formato = st.selectbox(
                    "Formato:",
                    ["Excel (.xlsx)", "CSV (.csv)"],
                    index=0,
                    key="formato_export_tab2"
                )
            
            with col_e2:
                nome_arquivo = st.text_input(
                    "Nome do arquivo:",
                    value=f"dados_smdet_{datetime.now().strftime('%Y%m%d_%H%M')}",
                    key="nome_arquivo_tab2"
                )
            
            if st.button("📥 Exportar Dados", type="primary", use_container_width=True, key="exportar_tab2"):
                with st.spinner("Gerando arquivo..."):
                    data, mime_type, error = create_download_link(df_consolidado, nome_arquivo, formato)
                    
                    if data and mime_type:
                        extensao = "xlsx" if formato.startswith("Excel") else "csv"
                        
                        st.download_button(
                            label=f"⬇️ Baixar {formato}",
                            data=data,
                            file_name=f"{nome_arquivo}.{extensao}",
                            mime=mime_type,
                            use_container_width=True,
                            key="download_tab2"
                        )
                        st.success(f"✅ Arquivo '{nome_arquivo}.{extensao}' pronto para download!")
                    else:
                        st.error(f"❌ {error}")
    
    # ============================================
    # ABA 3: ANÁLISE
    # ============================================
    with tab3:
        st.markdown("## 🔍 Análise Detalhada")
        
        df_consolidado = st.session_state.dataframes.get('DADOS_CONSOLIDADOS')
        
        if df_consolidado is None or df_consolidado.empty:
            st.info("Carregue dados primeiro na barra lateral.")
        else:
            # Filtros
            st.markdown("### 🎯 Filtros")
            
            col_f1, col_f2, col_f3 = st.columns(3)
            
            with col_f1:
                # Filtro por projeto
                if 'PROJETO' in df_consolidado.columns:
                    projetos = ['Todos'] + sorted(df_consolidado['PROJETO'].dropna().unique().tolist())
                    projeto_selecionado = st.selectbox(
                        "Projeto:", 
                        projetos,
                        key="projeto_select_tab3"
                    )
                else:
                    projeto_selecionado = 'Todos'
                    st.info("Coluna 'PROJETO' não encontrada")
            
            with col_f2:
                # Filtro por status
                if 'STATUS_PAGAMENTO' in df_consolidado.columns:
                    status_opcoes = ['Todos'] + sorted(df_consolidado['STATUS_PAGAMENTO'].dropna().unique().tolist())
                    status_selecionado = st.selectbox(
                        "Status:", 
                        status_opcoes,
                        key="status_select_tab3"
                    )
                else:
                    status_selecionado = 'Todos'
                    st.info("Coluna 'STATUS_PAGAMENTO' não encontrada")
            
            with col_f3:
                # Filtro por valor mínimo
                if 'VALOR_PAGAMENTO' in df_consolidado.columns:
                    valor_min = st.number_input(
                        "Valor mínimo:",
                        min_value=0.0,
                        max_value=1000000.0,
                        value=0.0,
                        step=100.0,
                        key="valor_min_tab3"
                    )
                else:
                    valor_min = 0.0
            
            # Aplicar filtros
            df_filtrado = df_consolidado.copy()
            
            if projeto_selecionado != 'Todos' and 'PROJETO' in df_filtrado.columns:
                df_filtrado = df_filtrado[df_filtrado['PROJETO'] == projeto_selecionado]
            
            if status_selecionado != 'Todos' and 'STATUS_PAGAMENTO' in df_filtrado.columns:
                df_filtrado = df_filtrado[df_filtrado['STATUS_PAGAMENTO'] == status_selecionado]
            
            if valor_min > 0 and 'VALOR_PAGAMENTO' in df_filtrado.columns:
                df_filtrado = df_filtrado[df_filtrado['VALOR_PAGAMENTO'] >= valor_min]
            
            st.markdown(f"### 📊 Resultados: {len(df_filtrado):,} registros")
            
            if df_filtrado.empty:
                st.warning("Nenhum registro encontrado com os filtros aplicados.")
            else:
                # Métricas
                col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                
                with col_m1:
                    if 'VALOR_TOTAL' in df_filtrado.columns:
                        valor_total = df_filtrado['VALOR_TOTAL'].sum()
                        st.metric("Valor Total", formatar_valor_brl(valor_total))
                    else:
                        st.metric("Valor Total", "-")
                
                with col_m2:
                    if 'VALOR_PAGAMENTO' in df_filtrado.columns:
                        valor_pago = df_filtrado['VALOR_PAGAMENTO'].sum()
                        st.metric("Valor Pago", formatar_valor_brl(valor_pago))
                    else:
                        st.metric("Valor Pago", "-")
                
                with col_m3:
                    if 'NOME' in df_filtrado.columns:
                        beneficiarios = df_filtrado['NOME'].nunique()
                        st.metric("Beneficiários", formatar_numero(beneficiarios))
                    else:
                        st.metric("Beneficiários", "-")
                
                with col_m4:
                    if 'VALOR_TOTAL' in df_filtrado.columns and 'VALOR_PAGAMENTO' in df_filtrado.columns:
                        if df_filtrado['VALOR_TOTAL'].sum() > 0:
                            percentual = (df_filtrado['VALOR_PAGAMENTO'].sum() / df_filtrado['VALOR_TOTAL'].sum()) * 100
                            st.metric("% Pago", f"{percentual:.1f}%")
                        else:
                            st.metric("% Pago", "0%")
                    else:
                        st.metric("% Pago", "-")
                
                # Dados filtrados
                st.markdown("### 📋 Dados Filtrados")
                
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
                else:
                    st.info("Colunas importantes não encontradas")
                
                # Análises
                st.markdown("---")
                st.markdown("### 📈 Análises")
                
                tab_a1, tab_a2, tab_a3 = st.tabs(["📊 Distribuição", "🏆 Agências", "📅 Linha do Tempo"])
                
                with tab_a1:
                    if 'PROJETO' in df_filtrado.columns and 'VALOR_TOTAL' in df_filtrado.columns:
                        try:
                            projeto_valores = df_filtrado.groupby('PROJETO')['VALOR_TOTAL'].sum()
                            projeto_valores = projeto_valores.sort_values(ascending=False).head(10)
                            
                            fig = px.bar(
                                x=projeto_valores.index,
                                y=projeto_valores.values,
                                title='Top 10 Projetos por Valor Total',
                                labels={'x': 'Projeto', 'y': 'Valor Total (R$)'},
                                color=projeto_valores.values,
                                color_continuous_scale='Blues'
                            )
                            fig.update_layout(coloraxis_showscale=False)
                            st.plotly_chart(fig, use_container_width=True)
                        except:
                            st.info("Não foi possível gerar análise de projetos")
                
                with tab_a2:
                    if 'AGENCIA' in df_filtrado.columns:
                        try:
                            agencia_counts = df_filtrado['AGENCIA'].value_counts().head(10)
                            fig = px.bar(
                                x=agencia_counts.index,
                                y=agencia_counts.values,
                                title='Top 10 Agências',
                                labels={'x': 'Agência', 'y': 'Quantidade'}
                            )
                            st.plotly_chart(fig, use_container_width=True)
                        except:
                            st.info("Não foi possível gerar análise de agências")
                    else:
                        st.info("Coluna 'AGENCIA' não encontrada")
                
                with tab_a3:
                    if 'DATA_CARREGAMENTO' in df_filtrado.columns:
                        try:
                            # Extrai data
                            df_filtrado['DATA'] = pd.to_datetime(df_filtrado['DATA_CARREGAMENTO']).dt.date
                            data_counts = df_filtrado.groupby('DATA').size().reset_index(name='Quantidade')
                            
                            fig = px.line(
                                data_counts,
                                x='DATA',
                                y='Quantidade',
                                title='Registros por Data',
                                markers=True
                            )
                            st.plotly_chart(fig, use_container_width=True)
                        except:
                            st.info("Não foi possível gerar linha do tempo")
                    else:
                        st.info("Coluna de data não disponível")
    
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
                "Limite de registros por arquivo:",
                min_value=1000,
                max_value=500000,
                value=config.get('limite_registros', 100000),
                step=1000,
                help="Limita a leitura para evitar sobrecarga de memória",
                key="limite_tab4"
            )
        
        with col_c2:
            formato_exp = st.selectbox(
                "Formato de exportação padrão:",
                ["Excel (.xlsx)", "CSV (.csv)"],
                index=0 if config.get('formato_exportacao', '').startswith('Excel') else 1,
                key="formato_tab4"
            )
        
        st.markdown("### 🔧 Opções Avançadas")
        
        col_c3, col_c4 = st.columns(2)
        
        with col_c3:
            auto_validar = st.checkbox(
                "Validação automática",
                value=config.get('auto_validar', True),
                help="Valida automaticamente os dados durante o processamento",
                key="autovalidar_tab4"
            )
        
        with col_c4:
            manter_originais = st.checkbox(
                "Manter arquivos originais",
                value=config.get('manter_originais', True),
                help="Mantém os DataFrames individuais dos arquivos originais",
                key="manter_originais_tab4"
            )
        
        # Botões
        st.markdown("---")
        
        col_b1, col_b2 = st.columns(2)
        
        with col_b1:
            if st.button("💾 Salvar Configurações", type="primary", use_container_width=True, key="salvar_tab4"):
                st.session_state.config = {
                    'limite_registros': novo_limite,
                    'formato_exportacao': formato_exp,
                    'auto_validar': auto_validar,
                    'manter_originais': manter_originais
                }
                st.success("✅ Configurações salvas!")
        
        with col_b2:
            if st.button("🔄 Restaurar Padrões", use_container_width=True, key="padroes_tab4"):
                st.session_state.config = {
                    'limite_registros': 100000,
                    'formato_exportacao': "Excel (.xlsx)",
                    'auto_validar': True,
                    'manter_originais': True
                }
                st.success("✅ Configurações padrão restauradas!")
                st.rerun()
        
        # Informações do sistema
        st.markdown("---")
        st.markdown("### 📊 Sistema")
        
        col_info1, col_info2 = st.columns(2)
        
        with col_info1:
            st.info(f"""
            **Versão:** 2.5.0  
            **Status:** {'✅ Processado' if st.session_state.is_processed else '⏳ Aguardando'}  
            **Limite atual:** {formatar_numero(config.get('limite_registros', 100000))}
            """)
        
        with col_info2:
            st.info(f"""
            **Arquivos:** {len([k for k in st.session_state.dataframes.keys() if k.startswith('ARQUIVO_')])}  
            **Registros:** {formatar_numero(len(st.session_state.dataframes.get('DADOS_CONSOLIDADOS', pd.DataFrame())))}  
            **Horário:** {get_local_time()}
            """)
        
        # Depuração
        with st.expander("🐛 Depuração (Avançado)", expanded=False):
            st.write("**Session State:**")
            st.json({k: str(type(v)) for k, v in st.session_state.items()})
            
            if st.button("Limpar Cache", key="limpar_cache_tab4"):
                st.cache_data.clear()
                st.success("Cache limpo!")

except Exception as e:
    st.error("### ⚠️ Ocorreu um erro crítico")
    
    col_err1, col_err2 = st.columns([2, 1])
    
    with col_err1:
        st.markdown(f"""
        <div class="error-box">
        <strong>Erro:</strong> {str(e)[:200]}
        </div>
        """, unsafe_allow_html=True)
    
    with col_err2:
        if st.button("🔄 Reiniciar Aplicação", type="primary"):
            st.session_state.clear()
            st.rerun()
    
    with st.expander("🔧 Detalhes Técnicos do Erro"):
        st.code(traceback.format_exc())
    
    st.markdown("""
    <div class="warning-box">
    <strong>Soluções recomendadas:</strong>
    1. Clique em <strong>🗑️ Limpar</strong> na barra lateral
    2. Verifique o formato dos arquivos (CSV com ; ou ,)
    3. Tente com arquivos menores primeiro
    4. Entre em contato com o suporte
    </div>
    """, unsafe_allow_html=True)

# ============================================
# RODAPÉ
# ============================================
st.markdown("---")
st.markdown(
    """
    <div style="text-align: center; color: #666; padding: 20px;">
    <strong>💰 SMDET - POT Monitoramento de Pagamento de Benefícios</strong><br>
    Sistema desenvolvido para acompanhamento e análise de pagamentos<br>
    <small>Versão 2.5.0 | Horário local: """ + get_local_time() + """ | Suporte: suporte@smdet.gov.br</small>
    </div>
    """,
    unsafe_allow_html=True
)
