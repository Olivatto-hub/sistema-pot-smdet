import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO, StringIO
from datetime import datetime, timezone, timedelta
import warnings
import re
import traceback
import chardet
import base64
import math
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
    
    .stProgress > div > div > div > div {
        background-color: #1E3A8A;
    }
    
    .stDataFrame {
        border-radius: 10px;
        overflow: hidden;
    }
    
    .bar-chart {
        display: flex;
        flex-direction: column;
        gap: 8px;
        margin: 20px 0;
    }
    
    .bar-item {
        display: flex;
        align-items: center;
        gap: 10px;
    }
    
    .bar-label {
        min-width: 120px;
        font-weight: 500;
    }
    
    .bar-container {
        flex: 1;
        height: 30px;
        background-color: #e9ecef;
        border-radius: 4px;
        overflow: hidden;
    }
    
    .bar-fill {
        height: 100%;
        background: linear-gradient(90deg, #1E3A8A, #3B82F6);
        border-radius: 4px;
        transition: width 0.5s ease;
    }
    
    .bar-value {
        min-width: 80px;
        text-align: right;
        font-weight: 600;
        color: #1E3A8A;
    }
    
    .pie-chart {
        display: flex;
        flex-wrap: wrap;
        gap: 15px;
        margin: 20px 0;
        justify-content: center;
    }
    
    .pie-item {
        display: flex;
        flex-direction: column;
        align-items: center;
        min-width: 100px;
    }
    
    .pie-slice {
        width: 80px;
        height: 80px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        margin-bottom: 8px;
        font-weight: bold;
        color: white;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .pie-label {
        text-align: center;
        font-size: 0.9em;
    }
    
    .color-1 { background-color: #1E3A8A; }
    .color-2 { background-color: #3B82F6; }
    .color-3 { background-color: #10B981; }
    .color-4 { background-color: #F59E0B; }
    .color-5 { background-color: #EF4444; }
    .color-6 { background-color: #8B5CF6; }
    .color-7 { background-color: #EC4899; }
    .color-8 { background-color: #14B8A6; }
    .color-9 { background-color: #F97316; }
    .color-10 { background-color: #6366F1; }
</style>
""", unsafe_allow_html=True)

# ============================================
# FUNÇÕES AUXILIARES
# ============================================

def get_local_time():
    """Obtém o horário local correto."""
    try:
        utc_now = datetime.now(timezone.utc)
        brasilia_offset = timedelta(hours=-3)
        brasilia_tz = timezone(brasilia_offset)
        brasilia_now = utc_now.astimezone(brasilia_tz)
        return brasilia_now.strftime("%d/%m/%Y %H:%M")
    except:
        return datetime.now().strftime("%d/%m/%Y %H:%M")

def detect_encoding(file_content):
    """Detecta a codificação do arquivo."""
    try:
        result = chardet.detect(file_content[:10000])
        encoding = result['encoding']
        confidence = result['confidence']
        
        encoding_map = {
            'ISO-8859-1': 'latin-1',
            'Windows-1252': 'cp1252',
            'ascii': 'utf-8'
        }
        
        if encoding in encoding_map:
            encoding = encoding_map[encoding]
        
        if confidence < 0.7:
            encoding = 'utf-8'
            
        return encoding
    except:
        return 'utf-8'

def detect_delimiter(file_content, encoding='utf-8'):
    """Detecta o delimitador do CSV."""
    try:
        sample = file_content[:5000].decode(encoding, errors='ignore')
        
        delimiters = [';', ',', '\t', '|']
        counts = {}
        
        for delim in delimiters:
            counts[delim] = sample.count(delim)
        
        if sum(counts.values()) > 0:
            best_delim = max(counts, key=counts.get)
            return best_delim
        else:
            return ';'
    except:
        return ';'

def safe_convert_to_float(value):
    """Converte um valor para float de forma segura."""
    if pd.isna(value) or value is None:
        return 0.0
    
    try:
        if isinstance(value, (int, float, np.number)):
            return float(value)
        
        if isinstance(value, str):
            value = str(value).strip()
            value = re.sub(r'[R\$\s]', '', value)
            
            if not value or value == '':
                return 0.0
            
            if ',' in value and '.' in value:
                value = value.replace('.', '')
                value = value.replace(',', '.')
            elif ',' in value:
                parts = value.split(',')
                if len(parts[-1]) <= 2:
                    value = value.replace(',', '.')
                else:
                    value = value.replace(',', '')
            
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
        
        serie_processada = serie.apply(safe_convert_to_float)
        
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
        
        col_str = re.sub(r'[ÁÀÂÃ]', 'A', col_str)
        col_str = re.sub(r'[ÉÈÊ]', 'E', col_str)
        col_str = re.sub(r'[ÍÌÎ]', 'I', col_str)
        col_str = re.sub(r'[ÓÒÔÕ]', 'O', col_str)
        col_str = re.sub(r'[ÚÙÛ]', 'U', col_str)
        col_str = re.sub(r'[Ç]', 'C', col_str)
        
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
    
    if not tentativas or all(t[0] is None for t in tentativas):
        try:
            file_content.seek(0)
            lines = []
            for i, line in enumerate(file_content):
                if i >= limite_registros:
                    break
                lines.append(line.decode('latin-1', errors='ignore').strip())
            
            sample_line = lines[0] if lines else ''
            possible_delimiters = [';', ',', '\t', '|']
            
            for delim in possible_delimiters:
                if delim in sample_line:
                    data = []
                    for line in lines:
                        parts = line.split(delim)
                        data.append(parts)
                    
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
            
            df, metodo = ler_arquivo_com_tentativas(file_obj, limite_registros)
            
            if df is None:
                resultados['errors'].append(f"{file_name}: Não foi possível ler o arquivo")
                continue
            
            if df.empty:
                resultados['warnings'].append(f"{file_name}: Arquivo está vazio")
                continue
            
            resultados['metodos'][file_name] = metodo
            
            df.columns = [clean_column_name(col) for col in df.columns]
            
            colunas_antes = len(df.columns)
            df = df.dropna(axis=1, how='all')
            colunas_depois = len(df.columns)
            
            if colunas_antes != colunas_depois:
                resultados['warnings'].append(f"{file_name}: Removidas {colunas_antes - colunas_depois} colunas vazias")
            
            if df.empty:
                resultados['warnings'].append(f"{file_name}: Nenhum dado válido após limpeza")
                continue
            
            colunas_valor = []
            for col in df.columns:
                col_upper = col.upper()
                if any(term in col_upper for term in ['VALOR', 'VLR', 'TOTAL', 'PAGAMENTO', 'PAGTO', 'BRUTO', 'LIQUIDO']):
                    colunas_valor.append(col)
            
            for col in colunas_valor:
                if col in df.columns:
                    df[col] = processar_coluna_numerica(df[col])
                    if df[col].isna().sum() > len(df) * 0.5:
                        resultados['warnings'].append(f"{file_name}: Coluna '{col}' tem muitos valores não numéricos")
            
            for col in df.columns:
                if df[col].dtype == 'object':
                    df[col] = df[col].astype(str).str.strip()
                    
                    col_upper = col.upper()
                    if 'NOME' in col_upper:
                        df[col] = df[col].str.title()
                    elif 'PROJETO' in col_upper or 'PROGRAMA' in col_upper:
                        df[col] = df[col].str.upper()
                    elif 'CPF' in col_upper or 'CNPJ' in col_upper:
                        df[col] = df[col].str.replace(r'\D', '', regex=True)
            
            df['ARQUIVO_ORIGEM'] = file_name
            df['DATA_CARREGAMENTO'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            resultados['dataframes'][f"ARQUIVO_{file_idx}"] = df
            dados_consolidados.append(df)
            
            resultados['warnings'].append(f"✅ {file_name}: Processado com sucesso ({len(df)} registros)")
            
        except Exception as e:
            error_msg = f"{file_name}: {str(e)[:100]}"
            resultados['errors'].append(error_msg)
    
    if dados_consolidados:
        try:
            df_consolidado = pd.concat(dados_consolidados, ignore_index=True, sort=False)
            
            registros_antes = len(df_consolidado)
            df_consolidado = df_consolidado.drop_duplicates()
            registros_depois = len(df_consolidado)
            
            if registros_antes != registros_depois:
                resultados['warnings'].append(f"Removidas {registros_antes - registros_depois} duplicatas")
            
            colunas_valor = [col for col in df_consolidado.columns if 'VALOR' in col]
            
            if colunas_valor:
                ordem_preferencia = ['VALOR_PAGAMENTO', 'VALOR_TOTAL', 'VALOR', 'VLR_PAGTO', 'VLR_TOTAL']
                
                for col_pref in ordem_preferencia:
                    if col_pref in df_consolidado.columns:
                        if col_pref != 'VALOR_PAGAMENTO':
                            df_consolidado = df_consolidado.rename(columns={col_pref: 'VALOR_PAGAMENTO'})
                        break
                else:
                    df_consolidado = df_consolidado.rename(columns={colunas_valor[0]: 'VALOR_PAGAMENTO'})
            
            colunas_numericas = []
            for col in ['VALOR_TOTAL', 'VALOR_PAGAMENTO', 'VALOR_DESCONTO', 'VALOR_BRUTO', 'VALOR_LIQUIDO']:
                if col in df_consolidado.columns:
                    colunas_numericas.append(col)
            
            for col in colunas_numericas:
                df_consolidado[col] = processar_coluna_numerica(df_consolidado[col])
            
            if 'VALOR_PAGAMENTO' in df_consolidado.columns:
                df_consolidado['STATUS_PAGAMENTO'] = np.where(
                    df_consolidado['VALOR_PAGAMENTO'] > 0, 
                    'PAGO', 
                    'PENDENTE'
                )
            else:
                df_consolidado['STATUS_PAGAMENTO'] = 'PENDENTE'
                resultados['warnings'].append("Coluna 'VALOR_PAGAMENTO' não encontrada, todos marcados como PENDENTE")
            
            if 'VALOR_TOTAL' in df_consolidado.columns and 'VALOR_PAGAMENTO' in df_consolidado.columns:
                df_consolidado['VALOR_PENDENTE'] = df_consolidado['VALOR_TOTAL'] - df_consolidado['VALOR_PAGAMENTO'].fillna(0)
                
                if 'VALOR_DESCONTO' in df_consolidado.columns:
                    df_consolidado['VALOR_PENDENTE'] = df_consolidado['VALOR_PENDENTE'] - df_consolidado['VALOR_DESCONTO'].fillna(0)
            
            resultados['dataframes']['DADOS_CONSOLIDADOS'] = df_consolidado
            resultados['total_registros'] = len(df_consolidado)
            
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

def criar_grafico_barras_html(dados, titulo, x_label, y_label, cor='#1E3A8A'):
    """Cria um gráfico de barras usando HTML/CSS puro."""
    if not dados:
        return "<p>Sem dados para exibir</p>"
    
    max_valor = max(dados.values()) if dados.values() else 1
    
    html = f"""
    <div style="margin: 20px 0;">
        <h4 style="margin-bottom: 15px; color: #333;">{titulo}</h4>
        <div class="bar-chart">
    """
    
    for i, (label, valor) in enumerate(dados.items()):
        porcentagem = (valor / max_valor * 100) if max_valor > 0 else 0
        valor_formatado = formatar_valor_brl(valor) if 'R$' in y_label else formatar_numero(valor)
        
        html += f"""
            <div class="bar-item">
                <div class="bar-label" title="{label}">{label[:20]}{'...' if len(label) > 20 else ''}</div>
                <div class="bar-container">
                    <div class="bar-fill" style="width: {porcentagem}%"></div>
                </div>
                <div class="bar-value">{valor_formatado}</div>
            </div>
        """
    
    html += """
        </div>
    </div>
    """
    
    return html

def criar_grafico_pizza_html(labels, sizes, titulo):
    """Cria um gráfico de pizza usando HTML/CSS puro."""
    if not labels or not sizes:
        return "<p>Sem dados para exibir</p>"
    
    total = sum(sizes)
    if total == 0:
        return "<p>Sem dados para exibir</p>"
    
    html = f"""
    <div style="margin: 20px 0; text-align: center;">
        <h4 style="margin-bottom: 15px; color: #333;">{titulo}</h4>
        <div class="pie-chart">
    """
    
    cores = ['color-1', 'color-2', 'color-3', 'color-4', 'color-5', 
             'color-6', 'color-7', 'color-8', 'color-9', 'color-10']
    
    for i, (label, valor) in enumerate(zip(labels, sizes)):
        if i >= len(cores):
            break
            
        porcentagem = (valor / total * 100) if total > 0 else 0
        cor_classe = cores[i % len(cores)]
        
        html += f"""
            <div class="pie-item">
                <div class="pie-slice {cor_classe}" title="{label}: {valor} ({porcentagem:.1f}%)">
                    {porcentagem:.1f}%
                </div>
                <div class="pie-label">{label[:15]}{'...' if len(label) > 15 else ''}</div>
            </div>
        """
    
    html += """
        </div>
    </div>
    """
    
    return html

def criar_grafico_linha_html(datas, valores, titulo):
    """Cria um gráfico de linha usando HTML/CSS puro."""
    if not datas or not valores or len(datas) < 2:
        return "<p>Dados insuficientes para linha do tempo</p>"
    
    max_valor = max(valores)
    min_valor = min(valores)
    valor_range = max_valor - min_valor if max_valor != min_valor else 1
    
    html = f"""
    <div style="margin: 20px 0;">
        <h4 style="margin-bottom: 15px; color: #333;">{titulo}</h4>
        <div style="position: relative; height: 200px; border-left: 2px solid #dee2e6; border-bottom: 2px solid #dee2e6; padding-left: 40px;">
    """
    
    # Eixo Y
    html += """
        <div style="position: absolute; left: 0; top: 0; bottom: 0; width: 40px; display: flex; flex-direction: column; justify-content: space-between;">
    """
    
    num_ticks = 5
    for i in range(num_ticks + 1):
        valor_tick = min_valor + (i * valor_range / num_ticks)
        pos_y = 100 - (i * 100 / num_ticks)
        html += f"""
            <div style="position: absolute; left: 0; top: {pos_y}%; transform: translateY(-50%); font-size: 10px; color: #666;">
                {formatar_numero(int(valor_tick))}
            </div>
        """
    
    html += """
        </div>
    """
    
    # Linha do gráfico
    pontos = []
    for i, (data, valor) in enumerate(zip(datas, valores)):
        x_pos = (i / (len(datas) - 1)) * 100 if len(datas) > 1 else 0
        y_pos = ((valor - min_valor) / valor_range) * 100 if valor_range > 0 else 50
        pontos.append(f"{x_pos}% {100 - y_pos}%")
    
    pontos_str = ", ".join(pontos)
    
    html += f"""
        <div style="position: absolute; left: 40px; right: 0; top: 0; bottom: 0;">
            <svg width="100%" height="100%" style="overflow: visible;">
                <polyline 
                    points="{pontos_str}"
                    fill="none"
                    stroke="#3B82F6"
                    stroke-width="3"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                />
    """
    
    # Pontos
    for i, (data, valor) in enumerate(zip(datas, valores)):
        x_pos = (i / (len(datas) - 1)) * 100 if len(datas) > 1 else 0
        y_pos = ((valor - min_valor) / valor_range) * 100 if valor_range > 0 else 50
        
        html += f"""
                <circle 
                    cx="{x_pos}%" 
                    cy="{100 - y_pos}%" 
                    r="4" 
                    fill="#1E3A8A"
                    stroke="white"
                    stroke-width="2"
                />
        """
    
    # Labels das datas
    html += """
            </svg>
            
            <div style="position: absolute; left: 0; right: 0; bottom: -25px; display: flex; justify-content: space-between;">
    """
    
    for i, data in enumerate(datas):
        x_pos = (i / (len(datas) - 1)) * 100 if len(datas) > 1 else 0
        html += f"""
                <div style="position: absolute; left: {x_pos}%; transform: translateX(-50%); font-size: 10px; color: #666; white-space: nowrap;">
                    {str(data)[:10]}
                </div>
        """
    
    html += """
            </div>
        </div>
    </div>
    """
    
    return html

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

# ============================================
# LAYOUT PRINCIPAL
# ============================================

try:
    st.markdown("<p class='main-header'>💰 SMDET - POT Monitoramento de Pagamento de Benefícios</p>", unsafe_allow_html=True)
    
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
        
        processar_col1, processar_col2 = st.columns([3, 1])
        
        with processar_col1:
            if st.button("🚀 PROCESSAR DADOS", type="primary", use_container_width=True):
                if uploaded_files:
                    with st.spinner(f"Processando {len(uploaded_files)} arquivo(s)..."):
                        try:
                            st.session_state.config['limite_registros'] = limite_registros
                            
                            resultados = processar_arquivos(uploaded_files, limite_registros)
                            
                            st.session_state.dataframes = resultados['dataframes']
                            
                            if 'DADOS_CONSOLIDADOS' in resultados['dataframes']:
                                df_consolidado = resultados['dataframes']['DADOS_CONSOLIDADOS']
                                if not df_consolidado.empty:
                                    st.session_state.is_processed = True
                                    
                                    st.success(f"✅ Processamento concluído com {len(df_consolidado):,} registros!")
                                    
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
                                    
                                    if resultados.get('metodos'):
                                        with st.expander("📊 Métodos de leitura", expanded=False):
                                            for file_name, metodo in resultados['metodos'].items():
                                                st.write(f"**{file_name}:** {metodo}")
                                    
                                    if resultados.get('warnings'):
                                        with st.expander("⚠️ Avisos do processamento", expanded=False):
                                            for warning in resultados['warnings']:
                                                if warning.startswith("✅"):
                                                    st.success(warning)
                                                else:
                                                    st.warning(warning)
                                    
                                    if resultados.get('errors'):
                                        with st.expander("❌ Erros encontrados", expanded=False):
                                            for error in resultados['errors']:
                                                st.error(error)
                                    
                                else:
                                    st.warning("⚠️ Dados processados, mas dataset consolidado está vazio")
                            else:
                                st.error("❌ Não foi possível consolidar os dados")
                                
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
        
        st.markdown("### 📊 STATUS")
        
        if st.session_state.is_processed:
            st.success("✅ Dados processados")
        else:
            st.info("⏳ Aguardando dados")
        
        st.markdown("### ⚡ AÇÕES")
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🗑️ Limpar", use_container_width=True, help="Limpar todos os dados"):
                st.session_state.dataframes = {}
                st.session_state.is_processed = False
                st.success("✅ Dados limpos!")
                st.rerun()
        
        with col_btn2:
            if st.button("📊 Testar", use_container_width=True, help="Testar com dados de exemplo"):
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
                total_registros = len(df_consolidado)
                
                total_projetos = 0
                if 'PROJETO' in df_consolidado.columns:
                    total_projetos = df_consolidado['PROJETO'].nunique()
                
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
                
                col_g1, col_g2 = st.columns(2)
                
                with col_g1:
                    st.markdown("### 📈 Status de Pagamento")
                    
                    if 'STATUS_PAGAMENTO' in df_consolidado.columns:
                        status_counts = df_consolidado['STATUS_PAGAMENTO'].value_counts()
                        
                        if len(status_counts) > 0:
                            html_pizza = criar_grafico_pizza_html(
                                status_counts.index.tolist(),
                                status_counts.values.tolist(),
                                'Distribuição por Status'
                            )
                            st.markdown(html_pizza, unsafe_allow_html=True)
                            
                            # Tabela de detalhes
                            with st.expander("📋 Detalhes do Status", expanded=False):
                                status_df = pd.DataFrame({
                                    'Status': status_counts.index,
                                    'Quantidade': status_counts.values,
                                    '%': (status_counts.values / status_counts.sum() * 100).round(1)
                                })
                                st.dataframe(status_df, use_container_width=True)
                        else:
                            st.info("Sem dados de status para exibir")
                    else:
                        st.info("Coluna 'STATUS_PAGAMENTO' não encontrada")
                
                with col_g2:
                    st.markdown("### 🏗️ Top Projetos")
                    
                    if 'PROJETO' in df_consolidado.columns and 'VALOR_TOTAL' in df_consolidado.columns:
                        try:
                            projeto_summary = df_consolidado.groupby('PROJETO')['VALOR_TOTAL'].sum()
                            projeto_summary = projeto_summary.sort_values(ascending=False).head(10)
                            
                            if len(projeto_summary) > 0:
                                html_barras = criar_grafico_barras_html(
                                    projeto_summary.to_dict(),
                                    'Top 10 Projetos por Valor Total',
                                    'Projeto',
                                    'Valor Total (R$)',
                                    '#1E3A8A'
                                )
                                st.markdown(html_barras, unsafe_allow_html=True)
                                
                                # Tabela de detalhes
                                with st.expander("📋 Detalhes dos Projetos", expanded=False):
                                    projeto_df = pd.DataFrame({
                                        'Projeto': projeto_summary.index,
                                        'Valor Total': projeto_summary.values,
                                        '% do Total': (projeto_summary.values / projeto_summary.sum() * 100).round(1)
                                    })
                                    projeto_df['Valor Total'] = projeto_df['Valor Total'].apply(formatar_valor_brl)
                                    st.dataframe(projeto_df, use_container_width=True)
                            else:
                                st.info("Sem dados de projetos para exibir")
                        except Exception as e:
                            st.info(f"Não foi possível gerar gráfico: {str(e)[:50]}")
                    else:
                        st.info("Dados insuficientes para gráfico de projetos")
                
                st.markdown("---")
                st.markdown("### 📋 Resumo por Projeto")
                
                if 'PROJETO' in df_consolidado.columns:
                    try:
                        colunas_resumo = ['NOME']
                        for col in ['VALOR_TOTAL', 'VALOR_PAGAMENTO']:
                            if col in df_consolidado.columns:
                                colunas_resumo.append(col)
                        
                        resumo = df_consolidado.groupby('PROJETO').agg({
                            'NOME': 'count',
                            **{col: 'sum' for col in colunas_resumo if col != 'NOME'}
                        }).reset_index()
                        
                        resumo = resumo.rename(columns={'NOME': 'Beneficiários'})
                        
                        if 'VALOR_TOTAL' in resumo.columns and 'VALOR_PAGAMENTO' in resumo.columns:
                            resumo['% Pago'] = (resumo['VALOR_PAGAMENTO'] / resumo['VALOR_TOTAL'] * 100).round(1)
                            resumo['% Pago'] = resumo['% Pago'].apply(lambda x: f"{x}%")
                        
                        for col in ['VALOR_TOTAL', 'VALOR_PAGAMENTO']:
                            if col in resumo.columns:
                                resumo[col] = resumo[col].apply(formatar_valor_brl)
                        
                        if 'VALOR_TOTAL' in resumo.columns:
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
            
            st.markdown("### 👁️ Visualização")
            
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
                colunas_selecionadas = colunas_disponiveis[:10]
            
            inicio = (pagina - 1) * linhas_por_pagina
            fim = min(inicio + linhas_por_pagina, len(df_consolidado))
            
            df_exibir = df_consolidado[colunas_selecionadas].iloc[inicio:fim].copy()
            
            for col in df_exibir.columns:
                if 'VALOR' in col.upper():
                    try:
                        df_exibir[col] = df_exibir[col].apply(formatar_valor_brl)
                    except:
                        pass
            
            st.dataframe(df_exibir, use_container_width=True, height=400)
            
            st.caption(f"Mostrando {inicio + 1} a {fim} de {len(df_consolidado):,} registros")
            
            with st.expander("📊 Informações do Dataset", expanded=False):
                st.write(f"**Total de colunas:** {len(df_consolidado.columns)}")
                st.write(f"**Colunas:** {', '.join(df_consolidado.columns.tolist())}")
                
                st.write("**Tipos de dados:**")
                tipos = df_consolidado.dtypes.astype(str).value_counts()
                for tipo, count in tipos.items():
                    st.write(f"  - {tipo}: {count} colunas")
            
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
            st.markdown("### 🎯 Filtros")
            
            col_f1, col_f2, col_f3 = st.columns(3)
            
            with col_f1:
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
                
                st.markdown("---")
                st.markdown("### 📈 Análises")
                
                tab_a1, tab_a2, tab_a3 = st.tabs(["📊 Distribuição", "🏆 Agências", "📅 Linha do Tempo"])
                
                with tab_a1:
                    if 'PROJETO' in df_filtrado.columns and 'VALOR_TOTAL' in df_filtrado.columns:
                        try:
                            projeto_valores = df_filtrado.groupby('PROJETO')['VALOR_TOTAL'].sum()
                            projeto_valores = projeto_valores.sort_values(ascending=False).head(10)
                            
                            if len(projeto_valores) > 0:
                                html_barras = criar_grafico_barras_html(
                                    projeto_valores.to_dict(),
                                    'Top 10 Projetos por Valor Total',
                                    'Projeto',
                                    'Valor Total (R$)',
                                    '#3B82F6'
                                )
                                st.markdown(html_barras, unsafe_allow_html=True)
                                
                                # Estatísticas adicionais
                                col_stats1, col_stats2 = st.columns(2)
                                with col_stats1:
                                    st.metric("Total de Projetos", len(projeto_valores))
                                with col_stats2:
                                    st.metric("Valor Médio por Projeto", 
                                             formatar_valor_brl(projeto_valores.mean()))
                            else:
                                st.info("Sem dados para exibir")
                        except:
                            st.info("Não foi possível gerar análise de projetos")
                
                with tab_a2:
                    if 'AGENCIA' in df_filtrado.columns:
                        try:
                            agencia_counts = df_filtrado['AGENCIA'].value_counts().head(10)
                            if len(agencia_counts) > 0:
                                html_barras = criar_grafico_barras_html(
                                    agencia_counts.to_dict(),
                                    'Top 10 Agências',
                                    'Agência',
                                    'Quantidade',
                                    '#10B981'
                                )
                                st.markdown(html_barras, unsafe_allow_html=True)
                            else:
                                st.info("Sem dados de agências para exibir")
                        except:
                            st.info("Não foi possível gerar análise de agências")
                    else:
                        st.info("Coluna 'AGENCIA' não encontrada")
                
                with tab_a3:
                    if 'DATA_CARREGAMENTO' in df_filtrado.columns:
                        try:
                            df_filtrado['DATA'] = pd.to_datetime(df_filtrado['DATA_CARREGAMENTO']).dt.date
                            data_counts = df_filtrado.groupby('DATA').size().reset_index(name='Quantidade')
                            data_counts = data_counts.sort_values('DATA')
                            
                            if len(data_counts) > 1:
                                html_linha = criar_grafico_linha_html(
                                    data_counts['DATA'].tolist(),
                                    data_counts['Quantidade'].tolist(),
                                    'Registros por Data'
                                )
                                st.markdown(html_linha, unsafe_allow_html=True)
                                
                                # Estatísticas
                                col_stats1, col_stats2 = st.columns(2)
                                with col_stats1:
                                    st.metric("Período (dias)", len(data_counts))
                                with col_stats2:
                                    st.metric("Média diária", 
                                             formatar_numero(data_counts['Quantidade'].mean().round(1)))
                            else:
                                st.info("Dados insuficientes para linha do tempo")
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
