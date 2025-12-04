import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import warnings
import re
import json
from pathlib import Path
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
    /* ESTILOS BASE QUE FUNCIONAM EM AMBOS OS TEMAS */
    :root {
        --primary-color: #1E3A8A;
        --secondary-color: #3B82F6;
        --success-color: #10B981;
        --warning-color: #F59E0B;
        --danger-color: #EF4444;
        --info-color: #06B6D4;
        --text-primary: #111827;
        --text-secondary: #6B7280;
        --bg-primary: #FFFFFF;
        --bg-secondary: #F9FAFB;
        --border-color: #E5E7EB;
        --shadow-color: rgba(0, 0, 0, 0.1);
    }
    
    @media (prefers-color-scheme: dark) {
        :root {
            --primary-color: #3B82F6;
            --secondary-color: #60A5FA;
            --text-primary: #F9FAFB;
            --text-secondary: #D1D5DB;
            --bg-primary: #111827;
            --bg-secondary: #1F2937;
            --border-color: #374151;
            --shadow-color: rgba(0, 0, 0, 0.3);
        }
    }
    
    /* TÍTULO PRINCIPAL - VISÍVEL EM QUALQUER TEMA */
    .main-header {
        font-size: 2.2em;
        font-weight: 800;
        margin-bottom: 0.5em;
        text-align: center;
        color: var(--primary-color);
        padding-bottom: 15px;
        border-bottom: 3px solid var(--primary-color);
        text-shadow: 0 2px 4px var(--shadow-color);
        background: linear-gradient(90deg, var(--primary-color), var(--secondary-color));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    
    /* MÉTRICAS COM ALTO CONTRASTE */
    [data-testid="stMetric"] {
        background-color: var(--bg-secondary) !important;
        padding: 20px;
        border-radius: 12px;
        border: 2px solid var(--border-color);
        box-shadow: 0 4px 6px var(--shadow-color);
        transition: all 0.3s ease;
    }
    
    [data-testid="stMetric"]:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 12px var(--shadow-color);
        border-color: var(--primary-color);
    }
    
    [data-testid="stMetricLabel"] {
        color: var(--text-secondary) !important;
        font-weight: 600 !important;
        font-size: 0.95em !important;
    }
    
    [data-testid="stMetricValue"] {
        color: var(--text-primary) !important;
        font-size: 1.8em !important;
        font-weight: 700 !important;
    }
    
    [data-testid="stMetricDelta"] {
        color: var(--text-secondary) !important;
        font-weight: 600 !important;
    }
    
    /* BOTÕES VISÍVEIS EM QUALQUER TEMA */
    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.3s ease;
        padding: 0.85rem 1.5rem;
        border: 2px solid var(--primary-color);
        background-color: var(--bg-primary);
        color: var(--primary-color) !important;
        font-size: 1em;
    }
    
    .stButton > button:hover {
        transform: translateY(-3px);
        box-shadow: 0 6px 12px var(--shadow-color);
        background-color: var(--primary-color) !important;
        color: white !important;
        border-color: var(--primary-color);
    }
    
    .stButton > button:focus {
        box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.5);
    }
    
    .primary-button > button {
        background-color: var(--primary-color) !important;
        color: white !important;
        border: 2px solid var(--primary-color) !important;
    }
    
    .primary-button > button:hover {
        background-color: var(--secondary-color) !important;
        border-color: var(--secondary-color) !important;
    }
    
    /* TABELAS COM ALTA LEGIBILIDADE */
    .stDataFrame {
        border-radius: 10px;
        overflow: hidden;
        border: 2px solid var(--border-color);
        background-color: var(--bg-primary) !important;
    }
    
    .stDataFrame table {
        background-color: var(--bg-primary) !important;
    }
    
    .stDataFrame th {
        background-color: var(--bg-secondary) !important;
        color: var(--text-primary) !important;
        font-weight: 700 !important;
        border-bottom: 2px solid var(--border-color) !important;
        padding: 12px 15px !important;
    }
    
    .stDataFrame td {
        color: var(--text-primary) !important;
        border-bottom: 1px solid var(--border-color) !important;
        padding: 10px 15px !important;
    }
    
    .stDataFrame tr:hover {
        background-color: var(--bg-secondary) !important;
    }
    
    /* ABAS VISÍVEIS EM QUALQUER TEMA */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        background-color: var(--bg-secondary);
        padding: 8px;
        border-radius: 10px;
        margin-bottom: 20px;
    }
    
    .stTabs [data-baseweb="tab"] {
        height: 55px;
        white-space: pre-wrap;
        background-color: var(--bg-secondary);
        border-radius: 8px;
        padding: 15px 20px;
        color: var(--text-secondary);
        font-weight: 600;
        transition: all 0.3s ease;
        border: 2px solid transparent;
    }
    
    .stTabs [data-baseweb="tab"]:hover {
        background-color: var(--bg-primary);
        color: var(--text-primary);
        border-color: var(--border-color);
    }
    
    .stTabs [aria-selected="true"] {
        background-color: var(--primary-color) !important;
        color: white !important;
        border-color: var(--primary-color) !important;
        box-shadow: 0 4px 6px var(--shadow-color);
    }
    
    /* INPUTS E SELECTS */
    .stSelectbox, .stTextInput, .stNumberInput, .stDateInput, .stMultiselect {
        border-radius: 8px;
    }
    
    .stSelectbox > div > div, 
    .stTextInput > div > div, 
    .stNumberInput > div > div,
    .stDateInput > div > div,
    .stMultiselect > div > div {
        background-color: var(--bg-primary) !important;
        border: 2px solid var(--border-color) !important;
        border-radius: 8px !important;
        color: var(--text-primary) !important;
    }
    
    .stSelectbox > div > div:hover,
    .stTextInput > div > div:hover,
    .stNumberInput > div > div:hover,
    .stDateInput > div > div:hover,
    .stMultiselect > div > div:hover {
        border-color: var(--primary-color) !important;
    }
    
    .stSelectbox label, 
    .stTextInput label, 
    .stNumberInput label,
    .stDateInput label,
    .stMultiselect label,
    .stSlider label {
        color: var(--text-primary) !important;
        font-weight: 600 !important;
    }
    
    /* SLIDERS */
    .stSlider > div {
        padding: 10px 0;
    }
    
    .stSlider > div > div > div {
        background-color: var(--primary-color) !important;
    }
    
    .stSlider > div > div > div > div {
        background-color: var(--primary-color) !important;
        border-color: var(--primary-color) !important;
    }
    
    /* CHECKBOXES E RADIOS */
    .stCheckbox > label, .stRadio > label {
        color: var(--text-primary) !important;
        font-weight: 500 !important;
    }
    
    .stCheckbox span, .stRadio span {
        color: var(--text-primary) !important;
    }
    
    /* EXPANDERS */
    .streamlit-expanderHeader {
        background-color: var(--bg-secondary) !important;
        color: var(--text-primary) !important;
        font-weight: 600 !important;
        border-radius: 8px;
        border: 2px solid var(--border-color);
        margin-bottom: 10px;
    }
    
    .streamlit-expanderContent {
        background-color: var(--bg-primary) !important;
        border-radius: 0 0 8px 8px;
        border: 2px solid var(--border-color);
        border-top: none;
    }
    
    /* SIDEBAR */
    [data-testid="stSidebar"] {
        background-color: var(--bg-secondary) !important;
    }
    
    [data-testid="stSidebar"] .stButton > button {
        margin-bottom: 10px;
    }
    
    /* SPINNER */
    .stSpinner > div {
        border-color: var(--primary-color) !important;
    }
    
    /* MENSAGENS DE ALERTA */
    .stAlert {
        border-radius: 10px;
        border: 2px solid var(--border-color);
        background-color: var(--bg-secondary) !important;
    }
    
    /* SCROLLBAR PERSONALIZADA */
    ::-webkit-scrollbar {
        width: 10px;
        height: 10px;
    }
    
    ::-webkit-scrollbar-track {
        background: var(--bg-secondary);
        border-radius: 5px;
    }
    
    ::-webkit-scrollbar-thumb {
        background: var(--primary-color);
        border-radius: 5px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: var(--secondary-color);
    }
    
    /* CARDS PERSONALIZADOS */
    .custom-card {
        background-color: var(--bg-secondary);
        border-radius: 12px;
        padding: 20px;
        border: 2px solid var(--border-color);
        margin-bottom: 20px;
        box-shadow: 0 4px 6px var(--shadow-color);
    }
    
    .custom-card h3 {
        color: var(--primary-color);
        margin-top: 0;
        border-bottom: 2px solid var(--border-color);
        padding-bottom: 10px;
    }
    
    /* BADGES */
    .status-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.85em;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    .status-pago {
        background-color: rgba(16, 185, 129, 0.2);
        color: #10B981;
        border: 1px solid #10B981;
    }
    
    .status-pendente {
        background-color: rgba(239, 68, 68, 0.2);
        color: #EF4444;
        border: 1px solid #EF4444;
    }
    
    /* TOOLTIPS */
    [data-testid="stTooltip"] {
        background-color: var(--bg-primary) !important;
        color: var(--text-primary) !important;
        border: 2px solid var(--border-color) !important;
        border-radius: 8px !important;
        box-shadow: 0 4px 12px var(--shadow-color) !important;
    }
    
    /* HEADERS SECUNDÁRIOS */
    h1, h2, h3, h4, h5, h6 {
        color: var(--text-primary) !important;
    }
    
    /* LINHAS DIVISÓRIAS */
    hr {
        border-color: var(--border-color) !important;
        margin: 2rem 0 !important;
    }
    
    /* RODAPÉ */
    .footer {
        text-align: center;
        color: var(--text-secondary);
        font-size: 0.9em;
        padding: 20px;
        margin-top: 40px;
        border-top: 2px solid var(--border-color);
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
        'incluir_graficos': True,
        'tema_escuro': False,
        'mostrar_tutoriais': True
    }
if 'filtros_ativos' not in st.session_state:
    st.session_state['filtros_ativos'] = {}
if 'pagina_atual' not in st.session_state:
    st.session_state['pagina_atual'] = 1

# ============================================
# FUNÇÕES AUXILIARES
# ============================================

def get_theme_colors():
    """Retorna cores baseadas no tema atual."""
    return {
        'primary': '#1E3A8A',
        'secondary': '#3B82F6',
        'success': '#10B981',
        'warning': '#F59E0B',
        'danger': '#EF4444',
        'text_primary': st.get_option('theme.textColor') or '#111827',
        'bg_primary': st.get_option('theme.backgroundColor') or '#FFFFFF'
    }

def create_badge(status):
    """Cria um badge colorido para status."""
    if status == 'PAGO':
        return f'<span class="status-badge status-pago">✅ {status}</span>'
    else:
        return f'<span class="status-badge status-pendente">⏳ {status}</span>'

def formatar_valor_brl(valor):
    """Formata valor para Real Brasileiro."""
    try:
        valor = float(valor)
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "R$ 0,00"

def formatar_numero(numero):
    """Formata número com separadores de milhar."""
    try:
        return f"{int(numero):,}".replace(",", ".")
    except:
        return str(numero)

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

@st.cache_data(show_spinner="🔄 Carregando e processando dados...")
def load_and_process_files(uploaded_files, limite_registros):
    """Carrega, limpa e concatena todos os arquivos."""
    dataframes = {}
    
    if not uploaded_files:
        return dataframes

    all_pendencias = []
    
    for file in uploaded_files:
        try:
            # Detecta extensão e lê arquivo
            file_extension = file.name.lower().split('.')[-1]
            file_size = len(file.getvalue()) / 1024 / 1024  # Tamanho em MB
            
            if file_extension == 'csv':
                # Tenta diferentes encodings
                encodings = ['utf-8', 'latin1', 'ISO-8859-1', 'cp1252']
                for encoding in encodings:
                    try:
                        # Tenta com delimitador ;
                        df = pd.read_csv(file, sep=';', encoding=encoding, 
                                        on_bad_lines='skip', nrows=limite_registros,
                                        dtype=str, low_memory=False)
                        break
                    except:
                        try:
                            # Tenta com delimitador ,
                            df = pd.read_csv(file, sep=',', encoding=encoding,
                                           on_bad_lines='skip', nrows=limite_registros,
                                           dtype=str, low_memory=False)
                            break
                        except:
                            continue
                else:
                    st.error(f"❌ Não foi possível ler o arquivo {file.name}")
                    continue
            
            elif file_extension == 'txt':
                # Para arquivos TXT, tenta diferentes delimitadores
                try:
                    df = pd.read_csv(file, sep='\t', encoding='utf-8', 
                                    on_bad_lines='skip', nrows=limite_registros,
                                    dtype=str, low_memory=False)
                except:
                    try:
                        df = pd.read_csv(file, sep=';', encoding='latin1',
                                       on_bad_lines='skip', nrows=limite_registros,
                                       dtype=str, low_memory=False)
                    except:
                        st.error(f"❌ Não foi possível ler o arquivo TXT {file.name}")
                        continue
            else:
                st.error(f"❌ Formato não suportado: {file.name}")
                continue
            
            # Limpeza de nomes de colunas
            df.columns = [clean_column_name(col) for col in df.columns]
            
            # Padronização de colunas numéricas
            value_cols = ['VALOR_TOTAL', 'VALOR_DESCONTO', 'VALOR_PAGAMENTO', 'VALOR_DIA']
            
            for col in value_cols:
                if col in df.columns:
                    # Converte para string e limpa
                    df[col] = df[col].astype(str)
                    
                    # Remove caracteres não numéricos
                    df[col] = df[col].str.replace(r'[^\d.,-]', '', regex=True)
                    df[col] = df[col].str.replace(r'\.(?=\d{3})', '', regex=True)  # Remove pontos de milhar
                    df[col] = df[col].str.replace(',', '.', regex=False)  # Substitui vírgula por ponto
                    
                    # Converte para numérico
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                    df[col] = df[col].fillna(0)
                    
                    # Verificação de valores anômalos
                    if df[col].mean() > 1000000:  # Valores muito altos
                        # Verifica se pode ser problema de formatação
                        if (df[col] % 100 == 0).all():  # Todos terminam em 00
                            df[col] = df[col] / 100  # Corrige casas decimais
            
            # Padronização de outras colunas
            if 'PROJETO' in df.columns:
                df['PROJETO'] = df['PROJETO'].astype(str).str.strip().str.upper()
                df['PROJETO'] = df['PROJETO'].str.replace(r'\s+', ' ', regex=True)
            
            if 'NOME' in df.columns:
                df['NOME'] = df['NOME'].astype(str).str.strip().str.title()
                df['NOME'] = df['NOME'].str.replace(r'\s+', ' ', regex=True)
            
            # Identifica se é arquivo de pagamentos
            is_pagamento = any(col in df.columns for col in ['VALOR_PAGAMENTO', 'VALOR_PAGTO', 'PAGAMENTO'])
            
            if is_pagamento:
                df['ARQUIVO_ORIGEM'] = file.name
                df['DATA_CARREGAMENTO'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                all_pendencias.append(df)
            else:
                dataframes[f"Cadastro_{file.name}"] = df
                
        except Exception as e:
            st.error(f"❌ Erro ao processar {file.name}: {str(e)[:100]}")
    
    if all_pendencias:
        # Concatena todas as pendências
        df_final = pd.concat(all_pendencias, ignore_index=True)
        
        # Remove duplicatas
        colunas_chave = [col for col in ['CODIGO', 'CPF', 'MATRICULA', 'NOME', 'PROJETO'] if col in df_final.columns]
        if colunas_chave:
            df_final = df_final.drop_duplicates(subset=colunas_chave, keep='first')
        
        # Cria coluna de status
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
        
        dataframes['DADOS_CONSOLIDADOS_PAGAMENTOS'] = df_final
        st.session_state['is_processed'] = True
    
    return dataframes

def create_download_link(df, filename, file_format):
    """Gera link de download para DataFrame."""
    try:
        if file_format == "CSV (.csv)":
            csv = df.to_csv(index=False, sep=';', encoding='latin1', decimal=',')
            return csv, "text/csv"
        
        elif file_format == "Excel (.xlsx)":
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Dados')
            
            output.seek(0)
            return output.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        
        return None, None
    except Exception as e:
        st.error(f"Erro ao criar arquivo: {str(e)}")
        return None, None

def create_summary_card(title, value, delta=None, icon="📊", help_text=""):
    """Cria um card de resumo estilizado."""
    colors = get_theme_colors()
    
    delta_html = ""
    if delta:
        delta_color = "green" if delta > 0 else "red"
        delta_html = f'<div style="color: {delta_color}; font-size: 0.9em; margin-top: 5px;">{delta}</div>'
    
    return f"""
    <div class="custom-card">
        <div style="display: flex; align-items: center; margin-bottom: 10px;">
            <div style="font-size: 1.5em; margin-right: 10px;">{icon}</div>
            <h3 style="margin: 0;">{title}</h3>
        </div>
        <div style="font-size: 1.8em; font-weight: 700; color: {colors['primary']};">
            {value}
        </div>
        {delta_html}
        <div style="font-size: 0.85em; color: var(--text-secondary); margin-top: 10px;">
            {help_text}
        </div>
    </div>
    """

# ============================================
# LAYOUT PRINCIPAL
# ============================================

st.markdown("<p class='main-header'>💰 SMDET - POT Monitoramento de Pagamento de Benefícios</p>", unsafe_allow_html=True)

# Barra de status no topo
col_status1, col_status2, col_status3, col_status4 = st.columns(4)
with col_status1:
    if st.session_state['is_processed']:
        st.markdown("✅ **Status:** Dados Processados")
    else:
        st.markdown("⏳ **Status:** Aguardando Dados")
with col_status2:
    if 'dataframes' in st.session_state:
        total_files = len(st.session_state['dataframes'])
        st.markdown(f"📁 **Arquivos:** {total_files}")
with col_status3:
    st.markdown(f"👤 **Usuário:** Sistema")
with col_status4:
    current_time = datetime.now().strftime("%d/%m/%Y %H:%M")
    st.markdown(f"🕒 **Horário:** {current_time}")

# ============================================
# SIDEBAR OTIMIZADA
# ============================================
with st.sidebar:
    st.markdown("### 📥 CARREGAMENTO DE DADOS")
    
    # Upload de arquivos com melhor UX
    uploaded_files = st.file_uploader(
        "**Arraste ou clique para selecionar arquivos**",
        type=['csv', 'txt', 'xlsx', 'xls'],
        accept_multiple_files=True,
        help="Formatos suportados: CSV, TXT, Excel"
    )
    
    if uploaded_files:
        file_list = "\n".join([f"• {f.name} ({f.size/1024:.1f} KB)" for f in uploaded_files[:5]])
        if len(uploaded_files) > 5:
            file_list += f"\n• ... e mais {len(uploaded_files) - 5} arquivos"
        
        with st.expander(f"📋 Arquivos Selecionados ({len(uploaded_files)})", expanded=True):
            st.markdown(file_list)
    
    # Botão de processamento
    if st.button("🚀 PROCESSAR DADOS", type="primary", use_container_width=True, 
                help="Clique para processar todos os arquivos carregados"):
        if uploaded_files:
            with st.spinner("Processando arquivos..."):
                limite = st.session_state['config'].get('limite_registros', 100000)
                st.session_state['dataframes'] = load_and_process_files(uploaded_files, limite)
                
                if st.session_state['is_processed']:
                    st.success(f"✅ {len(uploaded_files)} arquivo(s) processado(s)!")
                    st.balloons()
                else:
                    st.warning("⚠️ Arquivos carregados, mas sem dados de pagamentos identificados.")
        else:
            st.error("❌ Selecione pelo menos um arquivo.")
    
    st.markdown("---")
    
    # Status do sistema
    st.markdown("### 📊 STATUS DO SISTEMA")
    
    if st.session_state['is_processed']:
        df_pagamentos = st.session_state['dataframes'].get('DADOS_CONSOLIDADOS_PAGAMENTOS')
        if df_pagamentos is not None:
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Registros", formatar_numero(len(df_pagamentos)))
            with col2:
                st.metric("Projetos", df_pagamentos['PROJETO'].nunique())
    
    # Ações rápidas
    st.markdown("### ⚡ AÇÕES RÁPIDAS")
    
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("🗑️ Limpar Dados", use_container_width=True, 
                    help="Remove todos os dados carregados"):
            st.session_state['dataframes'] = {}
            st.session_state['is_processed'] = False
            st.session_state['filtros_ativos'] = {}
            st.cache_data.clear()
            st.success("✅ Dados limpos!")
            st.rerun()
    
    with col_btn2:
        if st.button("🔄 Recarregar", use_container_width=True,
                    help="Recarrega a página mantendo dados"):
            st.rerun()
    
    # Tutorial rápido
    if st.session_state['config'].get('mostrar_tutoriais', True):
        with st.expander("❓ Como usar o sistema", expanded=False):
            st.markdown("""
            **Passo a passo:**
            1. **Carregue** arquivos CSV/TXT
            2. **Processe** os dados
            3. **Analise** no Dashboard
            4. **Filtre** conforme necessidade
            5. **Exporte** relatórios
            
            **Dica:** Use temas escuros/claros conforme preferência nas configurações.
            """)
    
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: var(--text-secondary); font-size: 0.85em;">
    <strong>SMDET - POT</strong><br>
    Sistema de Monitoramento<br>
    Versão 2.1.0
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
    
    if not st.session_state['is_processed']:
        col_empty1, col_empty2, col_empty3 = st.columns([1, 2, 1])
        with col_empty2:
            st.info("""
            ### 👋 Bem-vindo ao Dashboard!
            
            Para começar:
            1. Carregue arquivos na barra lateral 📥
            2. Clique em **PROCESSAR DADOS** 🚀
            3. Visualize as métricas aqui 📊
            
            **Dica:** Suporte a CSV, TXT e Excel.
            """, icon="ℹ️")
    else:
        df_pagamentos = st.session_state['dataframes'].get('DADOS_CONSOLIDADOS_PAGAMENTOS')
        
        if df_pagamentos is not None:
            # Métricas principais em cards
            total_registros = len(df_pagamentos)
            total_projetos = df_pagamentos['PROJETO'].nunique()
            qtd_pagamentos = (df_pagamentos['VALOR_PAGAMENTO'] > 0).sum()
            valor_total_pago = df_pagamentos['VALOR_PAGAMENTO'].sum()
            valor_total = df_pagamentos['VALOR_TOTAL'].sum() if 'VALOR_TOTAL' in df_pagamentos.columns else valor_total_pago
            valor_pendente = valor_total - valor_total_pago
            
            # Cards principais
            col_c1, col_c2, col_c3, col_c4 = st.columns(4)
            
            with col_c1:
                st.markdown(create_summary_card(
                    "Total de Registros",
                    formatar_numero(total_registros),
                    icon="📋",
                    help_text="Total de registros processados"
                ), unsafe_allow_html=True)
            
            with col_c2:
                st.markdown(create_summary_card(
                    "Projetos Ativos",
                    formatar_numero(total_projetos),
                    icon="🏗️",
                    help_text="Quantidade de projetos diferentes"
                ), unsafe_allow_html=True)
            
            with col_c3:
                st.markdown(create_summary_card(
                    "Pagamentos Realizados",
                    formatar_numero(qtd_pagamentos),
                    icon="💰",
                    help_text="Quantidade de pagamentos efetuados"
                ), unsafe_allow_html=True)
            
            with col_c4:
                st.markdown(create_summary_card(
                    "Valor Total Pago",
                    formatar_valor_brl(valor_total_pago),
                    icon="💳",
                    help_text="Soma de todos os pagamentos"
                ), unsafe_allow_html=True)
            
            st.markdown("---")
            
            # Gráficos
            col_g1, col_g2 = st.columns(2)
            
            with col_g1:
                st.markdown("### 📈 Distribuição por Status")
                if 'STATUS_PAGAMENTO' in df_pagamentos.columns:
                    status_counts = df_pagamentos['STATUS_PAGAMENTO'].value_counts()
                    
                    # Gráfico de pizza com cores temáticas
                    colors = get_theme_colors()
                    fig_status = px.pie(
                        values=status_counts.values,
                        names=status_counts.index,
                        title='',
                        color=status_counts.index,
                        color_discrete_map={
                            'PAGO': colors['success'],
                            'PENDENTE': colors['warning']
                        },
                        hole=0.4
                    )
                    
                    fig_status.update_traces(
                        textposition='inside',
                        textinfo='percent+label',
                        textfont_size=14,
                        marker=dict(line=dict(color='white', width=2))
                    )
                    
                    fig_status.update_layout(
                        showlegend=True,
                        legend=dict(
                            orientation="h",
                            yanchor="bottom",
                            y=-0.1,
                            xanchor="center",
                            x=0.5
                        ),
                        height=400
                    )
                    
                    st.plotly_chart(fig_status, use_container_width=True)
            
            with col_g2:
                st.markdown("### 🏗️ Valores por Projeto")
                if 'PROJETO' in df_pagamentos.columns:
                    projeto_summary = df_pagamentos.groupby('PROJETO').agg({
                        'VALOR_TOTAL': 'sum',
                        'VALOR_PAGAMENTO': 'sum',
                        'NOME': 'count'
                    }).reset_index()
                    
                    projeto_summary = projeto_summary.sort_values('VALOR_TOTAL', ascending=False).head(15)
                    
                    fig_projeto = px.bar(
                        projeto_summary,
                        x='PROJETO',
                        y='VALOR_TOTAL',
                        title='',
                        color='VALOR_TOTAL',
                        color_continuous_scale=px.colors.sequential.Blues,
                        text_auto='.2s'
                    )
                    
                    fig_projeto.update_layout(
                        xaxis_tickangle=-45,
                        xaxis_title="Projeto",
                        yaxis_title="Valor Total (R$)",
                        showlegend=False,
                        height=400
                    )
                    
                    fig_projeto.update_traces(
                        texttemplate='R$ %{value:,.0f}',
                        textposition='outside'
                    )
                    
                    st.plotly_chart(fig_projeto, use_container_width=True)
            
            # Tabela de resumo
            st.markdown("---")
            st.markdown("### 📋 Resumo por Projeto")
            
            with st.expander("Visualizar Tabela Detalhada", expanded=True):
                resumo = df_pagamentos.groupby('PROJETO').agg({
                    'NOME': 'count',
                    'VALOR_TOTAL': 'sum',
                    'VALOR_PAGAMENTO': 'sum',
                    'VALOR_PENDENTE': 'sum',
                    'STATUS_PAGAMENTO': lambda x: (x == 'PAGO').sum()
                }).reset_index()
                
                resumo.columns = ['Projeto', 'Beneficiários', 'Valor Total', 'Valor Pago', 'Valor Pendente', 'Pagamentos Realizados']
                
                # Calcular porcentagem
                resumo['% Pago'] = (resumo['Valor Pago'] / resumo['Valor Total'] * 100).round(2)
                
                # Formatar valores
                for col in ['Valor Total', 'Valor Pago', 'Valor Pendente']:
                    resumo[col] = resumo[col].apply(formatar_valor_brl)
                
                # Adicionar badges de status
                resumo['Status'] = resumo['% Pago'].apply(
                    lambda x: "🟢 Completo" if x >= 100 else "🟡 Parcial" if x > 0 else "🔴 Pendente"
                )
                
                st.dataframe(
                    resumo.sort_values('Valor Total', key=lambda x: x.str.replace('R\$ ', '').str.replace('.', '').str.replace(',', '.').astype(float), ascending=False),
                    use_container_width=True,
                    height=400
                )
        
        else:
            st.warning("Nenhum dado de pagamento encontrado.")

# ============================================
# ABA 2: DADOS E EXPORTAÇÃO
# ============================================
with tab2:
    st.markdown("## 📁 Dados Carregados e Exportação")
    
    if not st.session_state['is_processed']:
        st.info("Carregue e processe dados na barra lateral para visualizar informações detalhadas.")
    else:
        df_pagamentos = st.session_state['dataframes'].get('DADOS_CONSOLIDADOS_PAGAMENTOS')
        
        if df_pagamentos is not None:
            # Estatísticas rápidas
            col_stats1, col_stats2, col_stats3, col_stats4 = st.columns(4)
            with col_stats1:
                st.metric("Registros", formatar_numero(len(df_pagamentos)))
            with col_stats2:
                st.metric("Colunas", len(df_pagamentos.columns))
            with col_stats3:
                st.metric("Valor Total", formatar_valor_brl(df_pagamentos['VALOR_TOTAL'].sum()))
            with col_stats4:
                st.metric("Última Atualização", datetime.now().strftime("%H:%M"))
            
            # Visualização dos dados
            st.markdown("### 👁️ Visualização dos Dados")
            
            # Filtro rápido para visualização
            col_filter1, col_filter2, col_filter3 = st.columns(3)
            with col_filter1:
                show_columns = st.multiselect(
                    "Colunas para exibir:",
                    df_pagamentos.columns.tolist(),
                    default=df_pagamentos.columns.tolist()[:8]
                )
            
            with col_filter2:
                rows_to_show = st.slider(
                    "Linhas por página:",
                    min_value=10,
                    max_value=200,
                    value=50,
                    step=10
                )
            
            with col_filter3:
                # Paginação
                total_pages = max(1, len(df_pagamentos) // rows_to_show + (1 if len(df_pagamentos) % rows_to_show > 0 else 0))
                page_number = st.number_input(
                    "Página:",
                    min_value=1,
                    max_value=total_pages,
                    value=st.session_state.get('pagina_atual', 1),
                    step=1
                )
                st.session_state['pagina_atual'] = page_number
            
            # Exibir dados com paginação
            start_idx = (page_number - 1) * rows_to_show
            end_idx = min(start_idx + rows_to_show, len(df_pagamentos))
            
            if show_columns:
                df_display = df_pagamentos[show_columns].iloc[start_idx:end_idx]
                
                # Adicionar formatação condicional para valores
                styled_df = df_display.style.format({
                    'VALOR_TOTAL': lambda x: formatar_valor_brl(x),
                    'VALOR_PAGAMENTO': lambda x: formatar_valor_brl(x),
                    'VALOR_PENDENTE': lambda x: formatar_valor_brl(x)
                })
                
                st.dataframe(styled_df, use_container_width=True, height=500)
                
                st.caption(f"Mostrando linhas {start_idx + 1} a {end_idx} de {len(df_pagamentos):,} (Página {page_number}/{total_pages})")
            
            # Seção de exportação
            st.markdown("---")
            st.markdown("### 💾 Exportação de Dados")
            
            col_exp1, col_exp2, col_exp3 = st.columns(3)
            
            with col_exp1:
                export_format = st.selectbox(
                    "Formato de exportação:",
                    ["Excel (.xlsx)", "CSV (.csv)"],
                    index=0
                )
            
            with col_exp2:
                # Filtro para exportação
                if 'PROJETO' in df_pagamentos.columns:
                    projetos = ['Todos'] + df_pagamentos['PROJETO'].unique().tolist()
                    projeto_export = st.selectbox(
                        "Filtrar por projeto:",
                        projetos
                    )
                    
                    if projeto_export != 'Todos':
                        df_export = df_pagamentos[df_pagamentos['PROJETO'] == projeto_export]
                        nome_base = f"dados_{projeto_export.lower().replace(' ', '_')}"
                    else:
                        df_export = df_pagamentos
                        nome_base = "dados_consolidados"
                else:
                    df_export = df_pagamentos
                    nome_base = "dados_consolidados"
            
            with col_exp3:
                # Opções adicionais
                incluir_index = st.checkbox("Incluir índice", value=False)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                nome_arquivo = st.text_input(
                    "Nome do arquivo:",
                    value=f"{nome_base}_{timestamp}"
                )
            
            # Botões de exportação
            col_btn_exp1, col_btn_exp2 = st.columns(2)
            
            with col_btn_exp1:
                if st.button("📥 Exportar Dados Completos", type="primary", use_container_width=True):
                    with st.spinner("Gerando arquivo..."):
                        data, mime_type = create_download_link(df_export, nome_arquivo, export_format)
                        
                        if data:
                            extensao = "xlsx" if export_format.startswith("Excel") else "csv"
                            st.download_button(
                                label="⬇️ Clique para Baixar",
                                data=data,
                                file_name=f"{nome_arquivo}.{extensao}",
                                mime=mime_type,
                                type="primary",
                                use_container_width=True
                            )
            
            with col_btn_exp2:
                if st.button("📊 Exportar Resumo", use_container_width=True):
                    # Cria resumo para exportação
                    if 'PROJETO' in df_pagamentos.columns:
                        resumo_export = df_pagamentos.groupby('PROJETO').agg({
                            'NOME': 'count',
                            'VALOR_TOTAL': 'sum',
                            'VALOR_PAGAMENTO': 'sum'
                        }).reset_index()
                        
                        resumo_export.columns = ['Projeto', 'Qtd_Beneficiarios', 'Valor_Total', 'Valor_Pago']
                        resumo_export['%_Pago'] = (resumo_export['Valor_Pago'] / resumo_export['Valor_Total'] * 100).round(2)
                        
                        output = BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            resumo_export.to_excel(writer, sheet_name='Resumo', index=False)
                        
                        st.download_button(
                            label="⬇️ Baixar Resumo (Excel)",
                            data=output.getvalue(),
                            file_name=f"resumo_{timestamp}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
        
        # Outros arquivos carregados
        outros_arquivos = {k: v for k, v in st.session_state['dataframes'].items() 
                         if k != 'DADOS_CONSOLIDADOS_PAGAMENTOS'}
        
        if outros_arquivos:
            st.markdown("---")
            st.markdown("### 📄 Outros Arquivos Carregados")
            
            for nome, df in outros_arquivos.items():
                with st.expander(f"{nome} ({len(df):,} registros)"):
                    st.dataframe(df.head(), use_container_width=True)

# ============================================
# ABA 3: ANÁLISE DETALHADA
# ============================================
with tab3:
    st.markdown("## 🔍 Análise Detalhada")
    
    if not st.session_state['is_processed']:
        st.info("Processe dados primeiro para acessar ferramentas de análise.")
    else:
        df_pagamentos = st.session_state['dataframes']['DADOS_CONSOLIDADOS_PAGAMENTOS']
        
        # Filtros avançados
        st.markdown("### 🎯 Filtros Avançados")
        
        col_filt1, col_filt2, col_filt3 = st.columns(3)
        
        with col_filt1:
            # Filtro por projeto
            projetos = ['Todos'] + sorted(df_pagamentos['PROJETO'].unique().tolist())
            projeto_filtro = st.selectbox(
                "Projeto:",
                projetos,
                key="filtro_projeto"
            )
        
        with col_filt2:
            # Filtro por status
            status_opcoes = ['Todos', 'PAGO', 'PENDENTE']
            status_filtro = st.selectbox(
                "Status:",
                status_opcoes,
                key="filtro_status"
            )
        
        with col_filt3:
            # Filtro por valor
            if 'VALOR_TOTAL' in df_pagamentos.columns:
                min_val = float(df_pagamentos['VALOR_TOTAL'].min())
                max_val = float(df_pagamentos['VALOR_TOTAL'].max())
                valor_filtro = st.slider(
                    "Faixa de valores:",
                    min_val, max_val,
                    (min_val, max_val),
                    key="filtro_valor"
                )
        
        # Aplicar filtros
        df_filtrado = df_pagamentos.copy()
        
        if projeto_filtro != 'Todos':
            df_filtrado = df_filtrado[df_filtrado['PROJETO'] == projeto_filtro]
        
        if status_filtro != 'Todos':
            df_filtrado = df_filtrado[df_filtrado['STATUS_PAGAMENTO'] == status_filtro]
        
        if 'VALOR_TOTAL' in df_pagamentos.columns:
            df_filtrado = df_filtrado[
                (df_filtrado['VALOR_TOTAL'] >= valor_filtro[0]) & 
                (df_filtrado['VALOR_TOTAL'] <= valor_filtro[1])
            ]
        
        # Mostrar resultados
        st.markdown(f"### 📊 Resultados: {len(df_filtrado):,} registros encontrados")
        
        if len(df_filtrado) == 0:
            st.warning("Nenhum registro encontrado com os filtros aplicados.")
        else:
            # Métricas dos dados filtrados
            col_met1, col_met2, col_met3, col_met4 = st.columns(4)
            
            with col_met1:
                valor_total_filtrado = df_filtrado['VALOR_TOTAL'].sum()
                st.metric("Valor Total", formatar_valor_brl(valor_total_filtrado))
            
            with col_met2:
                valor_pago_filtrado = df_filtrado['VALOR_PAGAMENTO'].sum()
                st.metric("Valor Pago", formatar_valor_brl(valor_pago_filtrado))
            
            with col_met3:
                valor_pendente_filtrado = valor_total_filtrado - valor_pago_filtrado
                st.metric("Valor Pendente", formatar_valor_brl(valor_pendente_filtrado))
            
            with col_met4:
                st.metric("Beneficiários Únicos", df_filtrado['NOME'].nunique())
            
            # Visualização dos dados filtrados
            st.markdown("### 📋 Dados Filtrados")
            
            # Seleção de colunas para exibição
            colunas_disponiveis = df_filtrado.columns.tolist()
            colunas_padrao = ['NOME', 'PROJETO', 'VALOR_TOTAL', 'VALOR_PAGAMENTO', 'STATUS_PAGAMENTO']
            colunas_selecionadas = st.multiselect(
                "Selecione colunas para visualizar:",
                colunas_disponiveis,
                default=[c for c in colunas_padrao if c in colunas_disponiveis]
            )
            
            if colunas_selecionadas:
                st.dataframe(
                    df_filtrado[colunas_selecionadas].head(100),
                    use_container_width=True,
                    height=400
                )
            
            # Análises específicas
            st.markdown("---")
            st.markdown("### 📈 Análises Específicas")
            
            tab_analise1, tab_analise2, tab_analise3 = st.tabs(["📊 Distribuição", "🏆 Top Projetos", "📅 Evolução"])
            
            with tab_analise1:
                # Distribuição por agência
                if 'AGENCIA' in df_filtrado.columns:
                    st.markdown("#### Distribuição por Agência")
                    
                    agencia_counts = df_filtrado['AGENCIA'].value_counts().head(15).reset_index()
                    agencia_counts.columns = ['Agência', 'Quantidade']
                    
                    fig_agencia = px.bar(
                        agencia_counts,
                        x='Agência',
                        y='Quantidade',
                        color='Quantidade',
                        color_continuous_scale=px.colors.sequential.Viridis
                    )
                    
                    fig_agencia.update_layout(
                        xaxis_tickangle=-45,
                        height=400
                    )
                    
                    st.plotly_chart(fig_agencia, use_container_width=True)
            
            with tab_analise2:
                # Top projetos por valor
                st.markdown("#### Top Projetos por Valor")
                
                top_projetos = df_filtrado.groupby('PROJETO')['VALOR_TOTAL'].sum().nlargest(10).reset_index()
                top_projetos.columns = ['Projeto', 'Valor Total']
                
                fig_top = px.pie(
                    top_projetos,
                    values='Valor Total',
                    names='Projeto',
                    hole=0.3
                )
                
                st.plotly_chart(fig_top, use_container_width=True)
            
            with tab_analise3:
                # Análise temporal (se houver data)
                st.markdown("#### Análise de Evolução")
                
                # Verifica se há coluna de data
                colunas_data = [col for col in df_filtrado.columns if 'DATA' in col or 'DT' in col]
                
                if colunas_data:
                    col_data = colunas_data[0]
                    try:
                        df_filtrado[col_data] = pd.to_datetime(df_filtrado[col_data], errors='coerce')
                        evolucao = df_filtrado.groupby(df_filtrado[col_data].dt.to_period('M')).agg({
                            'VALOR_TOTAL': 'sum',
                            'VALOR_PAGAMENTO': 'sum'
                        }).reset_index()
                        
                        evolucao[col_data] = evolucao[col_data].astype(str)
                        
                        fig_evolucao = px.line(
                            evolucao,
                            x=col_data,
                            y=['VALOR_TOTAL', 'VALOR_PAGAMENTO'],
                            title='Evolução Mensal'
                        )
                        
                        st.plotly_chart(fig_evolucao, use_container_width=True)
                    except:
                        st.info("Não foi possível analisar dados temporais.")
                else:
                    st.info("Nenhuma coluna de data encontrada para análise temporal.")

# ============================================
# ABA 4: CONFIGURAÇÕES
# ============================================
with tab4:
    st.markdown("## ⚙️ Configurações do Sistema")
    
    current_config = st.session_state['config']
    
    # Tema visual
    st.markdown("### 🎨 Aparência")
    
    col_theme1, col_theme2 = st.columns(2)
    
    with col_theme1:
        tema_escuro = st.checkbox(
            "Usar tema escuro (recomendado)",
            value=current_config.get('tema_escuro', False),
            help="Aplica tema escuro para melhor visibilidade"
        )
    
    with col_theme2:
        mostrar_tutoriais = st.checkbox(
            "Mostrar tutoriais",
            value=current_config.get('mostrar_tutoriais', True),
            help="Exibe dicas e orientações no sistema"
        )
    
    # Processamento
    st.markdown("### ⚡ Processamento")
    
    col_proc1, col_proc2, col_proc3 = st.columns(3)
    
    with col_proc1:
        auto_validar = st.checkbox(
            "Validação automática",
            value=current_config['auto_validar'],
            help="Valida dados automaticamente ao carregar"
        )
    
    with col_proc2:
        manter_historico = st.checkbox(
            "Manter histórico",
            value=current_config['manter_historico'],
            help="Armazena histórico de alterações"
        )
    
    with col_proc3:
        limite_registros = st.number_input(
            "Limite de registros:",
            min_value=1000,
            max_value=500000,
            value=current_config['limite_registros'],
            step=1000,
            help="Máximo de registros por arquivo"
        )
    
    # Exportação
    st.markdown("### 💾 Exportação")
    
    col_exp1, col_exp2 = st.columns(2)
    
    with col_exp1:
        formato_exportacao = st.selectbox(
            "Formato padrão:",
            ["Excel (.xlsx)", "CSV (.csv)"],
            index=0 if current_config['formato_exportacao'] == "Excel (.xlsx)" else 1
        )
    
    with col_exp2:
        incluir_graficos = st.checkbox(
            "Incluir gráficos em relatórios",
            value=current_config['incluir_graficos'],
            help="Adiciona visualizações aos relatórios exportados"
        )
    
    # Validação avançada
    st.markdown("### 🔍 Validação Avançada")
    
    with st.expander("Configurações de validação", expanded=False):
        col_val1, col_val2 = st.columns(2)
        
        with col_val1:
            validar_cpf = st.checkbox("Validar CPF", value=True)
            validar_valores = st.checkbox("Validar valores", value=True)
        
        with col_val2:
            corrigir_decimais = st.checkbox("Corrigir decimais", value=True)
            normalizar_nomes = st.checkbox("Normalizar nomes", value=True)
    
    # Botões de ação
    st.markdown("---")
    
    col_save1, col_save2, col_save3 = st.columns(3)
    
    with col_save1:
        if st.button("💾 SALVAR CONFIGURAÇÕES", type="primary", use_container_width=True):
            st.session_state['config'] = {
                'auto_validar': auto_validar,
                'manter_historico': manter_historico,
                'limite_registros': limite_registros,
                'formato_exportacao': formato_exportacao,
                'incluir_graficos': incluir_graficos,
                'tema_escuro': tema_escuro,
                'mostrar_tutoriais': mostrar_tutoriais,
                'validar_cpf': validar_cpf,
                'validar_valores': validar_valores,
                'corrigir_decimais': corrigir_decimais,
                'normalizar_nomes': normalizar_nomes
            }
            st.success("✅ Configurações salvas com sucesso!")
            st.rerun()
    
    with col_save2:
        if st.button("🔄 RESTAURAR PADRÕES", use_container_width=True):
            st.session_state['config'] = {
                'auto_validar': True,
                'manter_historico': True,
                'limite_registros': 100000,
                'formato_exportacao': "Excel (.xlsx)",
                'incluir_graficos': True,
                'tema_escuro': False,
                'mostrar_tutoriais': True,
                'validar_cpf': True,
                'validar_valores': True,
                'corrigir_decimais': True,
                'normalizar_nomes': True
            }
            st.success("✅ Configurações padrão restauradas!")
            st.rerun()
    
    with col_save3:
        if st.button("📋 RELATÓRIO DE SISTEMA", use_container_width=True):
            with st.expander("Informações do Sistema", expanded=True):
                st.markdown(f"""
                **Versão:** 2.1.0
                **Python:** 3.11+
                **Streamlit:** {st.__version__}
                **Pandas:** {pd.__version__}
                
                **Status:**
                - Processamento: {'✅ Ativo' if st.session_state['is_processed'] else '⏳ Aguardando'}
                - Arquivos carregados: {len(st.session_state.get('dataframes', {}))}
                - Tema: {'🌙 Escuro' if tema_escuro else '☀️ Claro'}
                
                **Configurações ativas:**
                - Limite de registros: {limite_registros:,}
                - Formato exportação: {formato_exportacao}
                - Validação: {'✅ Ativa' if auto_validar else '❌ Inativa'}
                """)

# ============================================
# RODAPÉ
# ============================================
st.markdown("---")
st.markdown(
    """
    <div class="footer">
        <strong>💰 SMDET - POT Monitoramento de Pagamento de Benefícios</strong><br>
        Sistema desenvolvido para acompanhamento, análise e gestão de pagamentos<br>
        <small>© 2024 - Versão 2.1.0 | Otimizado para temas claros e escuros</small>
    </div>
    """,
    unsafe_allow_html=True
)
