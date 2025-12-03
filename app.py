# app.py - SISTEMA POT SMDET COMPLETO COM CÁLCULO CORRETO DE VALORES
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timezone, timedelta
import io
from fpdf import FPDF
import numpy as np
import re
import base64
from io import BytesIO
import warnings
warnings.filterwarnings('ignore')

# Configuração da página
st.set_page_config(
    page_title="Sistema POT - SMDET",
    page_icon="🏛️",
    layout="wide"
)

# ============================================
# CLASSE PDF PERSONALIZADA
# ============================================

class RelatorioPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=15)
    
    def header(self):
        self.set_font('Arial', 'B', 16)
        self.cell(0, 10, 'SISTEMA POT - SMDET', 0, 1, 'C')
        self.set_font('Arial', 'I', 12)
        self.cell(0, 10, 'Relatorio de Analise de Pagamentos e Contas', 0, 1, 'C')
        self.ln(5)
    
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Pagina {self.page_no()} - Gerado em {datetime.now().strftime("%d/%m/%Y %H:%M")}', 0, 0, 'C')
    
    def chapter_title(self, title, size=14):
        self.set_font('Arial', 'B', size)
        self.set_fill_color(240, 240, 240)
        self.cell(0, 10, title, 0, 1, 'L', True)
        self.ln(3)
    
    def add_metric(self, label, value, alert=False):
        self.set_font('Arial', 'B', 11)
        self.cell(70, 8, label, 0, 0)
        self.set_font('Arial', '', 11)
        if alert:
            self.set_text_color(255, 0, 0)
        self.cell(0, 8, str(value), 0, 1)
        self.set_text_color(0, 0, 0)
    
    def add_table(self, df, max_rows=50):
        self.set_font('Arial', '', 9)
        
        # Calcular larguras das colunas
        col_widths = []
        for col in df.columns:
            max_len = max(df[col].astype(str).apply(lambda x: len(str(x))).max(), len(col)) * 1.5
            col_widths.append(min(max_len, 40))
        
        # Cabeçalho
        self.set_fill_color(200, 200, 200)
        self.set_font('Arial', 'B', 9)
        for i, col in enumerate(df.columns):
            cell_text = str(col)[:30]
            self.cell(col_widths[i], 8, cell_text, 1, 0, 'C', True)
        self.ln()
        
        # Dados
        self.set_font('Arial', '', 9)
        for idx, row in df.head(max_rows).iterrows():
            for i, col in enumerate(df.columns):
                cell_text = str(row[col])[:30]
                self.cell(col_widths[i], 8, cell_text, 1, 0, 'C')
            self.ln()
        
        if len(df) > max_rows:
            self.ln(5)
            self.set_font('Arial', 'I', 9)
            self.cell(0, 8, f'... e mais {len(df) - max_rows} registros', 0, 1)

# ============================================
# FUNÇÕES AUXILIARES
# ============================================

def agora_brasilia():
    fuso_brasilia = timezone(timedelta(hours=-3))
    return datetime.now(timezone.utc).astimezone(fuso_brasilia)

def data_hora_atual_brasilia():
    return agora_brasilia().strftime("%d/%m/%Y as %H:%M")

def detectar_encoding(arquivo):
    encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252', 'windows-1252']
    raw_data = arquivo.read(10000)
    arquivo.seek(0)
    
    for encoding in encodings:
        try:
            raw_data.decode(encoding)
            arquivo.seek(0)
            return encoding
        except:
            continue
    
    arquivo.seek(0)
    return 'utf-8'

def formatar_brasileiro(valor, tipo='numero'):
    if pd.isna(valor):
        valor = 0
    
    try:
        if tipo == 'monetario':
            return f"R$ {float(valor):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        elif tipo == 'numero':
            return f"{int(valor):,}".replace(',', '.')
        else:
            return str(valor)
    except:
        return str(valor)

def limpar_texto_para_pdf(texto):
    """Limpa texto para ser seguro no PDF"""
    if pd.isna(texto):
        return ""
    
    texto = str(texto)
    caracteres_problematicos = {
        '•': '-', '–': '-', '—': '-', '"': "'", "'": "'",
        '\u2022': '-', '\u2013': '-', '\u2014': '-',
        '\u2018': "'", '\u2019': "'", '\u201c': '"', '\u201d': '"',
        'á': 'a', 'à': 'a', 'â': 'a', 'ã': 'a', 'ä': 'a',
        'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
        'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
        'ó': 'o', 'ò': 'o', 'ô': 'o', 'õ': 'o', 'ö': 'o',
        'ú': 'u', 'ù': 'u', 'û': 'u', 'ü': 'u',
        'ç': 'c', 'ñ': 'n',
        'Á': 'A', 'À': 'A', 'Â': 'A', 'Ã': 'A', 'Ä': 'A',
        'É': 'E', 'È': 'E', 'Ê': 'E', 'Ë': 'E',
        'Í': 'I', 'Ì': 'I', 'Î': 'I', 'Ï': 'I',
        'Ó': 'O', 'Ò': 'O', 'Ô': 'O', 'Õ': 'O', 'Ö': 'O',
        'Ú': 'U', 'Ù': 'U', 'Û': 'U', 'Ü': 'U',
        'Ç': 'C', 'Ñ': 'N'
    }
    
    for char_errado, char_certo in caracteres_problematicos.items():
        texto = texto.replace(char_errado, char_certo)
    
    return texto

# ============================================
# DETECÇÃO AUTOMÁTICA DE COLUNAS (APRIMORADA)
# ============================================

def detectar_coluna_conta(df):
    if df.empty:
        return None
    
    colunas_possiveis = [
        'Num Cartao', 'NumCartao', 'Num_Cartao', 'Num Cartão', 'Cartao',
        'Cartão', 'Conta', 'Numero Conta', 'Número Conta', 'NRO_CONTA',
        'CARTAO', 'CONTA', 'NUMCARTAO', 'NUM_CARTAO', 'NUMERO_CARTAO',
        'NumeroCartao', 'NrCartao', 'NRCartao', 'Numero do Cartao',
        'NUMERO CARTAO', 'NÚMERO CARTAO', 'NÚMERO CARTÃO'
    ]
    
    for coluna in df.columns:
        coluna_limpa = str(coluna).strip().upper()
        for padrao in colunas_possiveis:
            if padrao.upper() in coluna_limpa:
                return coluna
    
    return None

def detectar_coluna_nome(df):
    if df.empty:
        return None
    
    colunas_possiveis = [
        'Nome', 'Nome do beneficiário', 'Beneficiario', 'Beneficiário',
        'NOME', 'BENEFICIARIO', 'BENEFICIÁRIO', 'NOME BENEFICIARIO',
        'NOME_BENEFICIARIO', 'NOME DO BENEFICIARIO', 'NOME BENEFICIÁRIO'
    ]
    
    for coluna in df.columns:
        coluna_limpa = str(coluna).strip().upper()
        for padrao in colunas_possiveis:
            if padrao.upper() in coluna_limpa:
                return coluna
    
    return None

def detectar_coluna_valor(df):
    """Detecta automaticamente colunas de valor para pagamentos"""
    if df.empty:
        return None
    
    # Lista completa de possíveis nomes de colunas de valor
    colunas_prioridade = [
        'Valor Pagto', 'ValorPagto', 'Valor_Pagto', 'Valor Pago', 'ValorPago',
        'Valor_Pago', 'Valor Pagamento', 'ValorPagamento', 'Valor_Pagamento',
        'Valor', 'Valor Total', 'ValorTotal', 'Valor_Total', 'VALOR',
        'VALOR PAGO', 'VALOR_PAGO', 'VALOR PGTO', 'VLR_PAGO', 'VLR PAGO',
        'Valor a Pagar', 'ValoraPagar', 'Valor_a_Pagar', 'VALOR A PAGAR',
        'ValorLiquido', 'Valor Liquido', 'VALOR LIQUIDO'
    ]
    
    # Primeiro, procurar por nomes exatos ou similares
    for coluna in df.columns:
        coluna_limpa = str(coluna).strip().upper()
        for padrao in colunas_prioridade:
            if padrao.upper() in coluna_limpa:
                return coluna
    
    # Se não encontrou por nome, procurar por colunas que contenham valores monetários
    for coluna in df.columns:
        # Verificar se é coluna numérica
        if df[coluna].dtype in ['float64', 'int64', 'float32', 'int32']:
            # Verificar se os valores parecem ser monetários
            if not df[coluna].empty:
                amostra = df[coluna].dropna().head(10)
                if len(amostra) > 0:
                    # Se há valores maiores que 0, provavelmente é monetário
                    if amostra.mean() > 0:
                        return coluna
    
    # Última tentativa: verificar conteúdo da coluna
    for coluna in df.columns:
        if df[coluna].dtype == 'object':
            amostra = df[coluna].dropna().head(10).astype(str)
            # Verificar se contém padrões de valores monetários
            padroes_monetarios = [r'[\d.,]+\s*[R$]?', r'R\$\s*[\d.,]+', r'[\d.,]+\s*[R\$]']
            for padrao in padroes_monetarios:
                if any(re.search(padrao, str(x), re.IGNORECASE) for x in amostra):
                    return coluna
    
    return None

def detectar_coluna_data(df):
    if df.empty:
        return []
    
    colunas_data = [
        'Data', 'DataPagto', 'Data_Pagto', 'DtLote', 'DATA',
        'DATA PGTO', 'DT_LOTE', 'DATALOTE', 'DataPagamento',
        'Data Pagto', 'Data_Pagamento', 'Data Pagamento'
    ]
    
    datas_encontradas = []
    for coluna in df.columns:
        coluna_limpa = str(coluna).strip().upper()
        for padrao in colunas_data:
            if padrao.upper() in coluna_limpa:
                datas_encontradas.append(coluna)
                break
    
    return datas_encontradas

def detectar_coluna_projeto(df):
    if df.empty:
        return None
    
    colunas_possiveis = ['Projeto', 'PROJETO', 'PROGRAMA', 'NOME PROJETO']
    
    for coluna in df.columns:
        coluna_limpa = str(coluna).strip().upper()
        for padrao in colunas_possiveis:
            if padrao.upper() in coluna_limpa:
                return coluna
    
    return None

def detectar_coluna_cpf(df):
    if df.empty:
        return None
    
    colunas_possiveis = ['CPF', 'CPF BENEFICIARIO', 'CPF_BENEF', 'CPF/CNPJ']
    
    for coluna in df.columns:
        coluna_limpa = str(coluna).strip().upper()
        for padrao in colunas_possiveis:
            if padrao.upper() == coluna_limpa:
                return coluna
    
    return None

# ============================================
# PROCESSAMENTO DE VALORES MONETÁRIOS
# ============================================

def converter_para_numerico_seguro(valor):
    """Converte qualquer valor para numérico de forma segura"""
    if pd.isna(valor):
        return 0.0
    
    try:
        # Se já é numérico
        if isinstance(valor, (int, float, np.integer, np.floating)):
            return float(valor)
        
        valor_str = str(valor).strip()
        
        if valor_str == '':
            return 0.0
        
        # Remover caracteres não numéricos exceto ponto, vírgula e sinal negativo
        valor_limpo = re.sub(r'[^\d,\-\.]', '', valor_str)
        
        if not valor_limpo:
            return 0.0
        
        # Verificar formato brasileiro (1.234,56)
        if ',' in valor_limpo and valor_limpo.count('.') > 0:
            # Formato 1.234,56 -> remover pontos de milhar e trocar vírgula por ponto
            valor_limpo = valor_limpo.replace('.', '').replace(',', '.')
        elif ',' in valor_limpo:
            # Formato 1234,56
            valor_limpo = valor_limpo.replace(',', '.')
        
        # Garantir que só temos números, ponto decimal e sinal negativo
        valor_limpo = re.sub(r'[^\d\.\-]', '', valor_limpo)
        
        # Se depois da limpeza ficou vazio
        if not valor_limpo or valor_limpo == '-' or valor_limpo == '.':
            return 0.0
        
        return float(valor_limpo)
    except Exception as e:
        return 0.0

def processar_coluna_valor(df, nome_coluna):
    """Processa uma coluna de valor específica"""
    if df.empty or nome_coluna not in df.columns:
        return df, 0.0
    
    try:
        df_processado = df.copy()
        
        # Converter todos os valores da coluna para numérico
        df_processado[f'{nome_coluna}_Numerico'] = df_processado[nome_coluna].apply(
            converter_para_numerico_seguro
        )
        
        # Calcular soma total
        soma_total = df_processado[f'{nome_coluna}_Numerico'].sum()
        
        return df_processado, soma_total
    except Exception as e:
        return df, 0.0

def detectar_e_processar_valores(df):
    """Detecta e processa todas as colunas de valor"""
    if df.empty:
        return df, 0.0, None
    
    # Detectar coluna de valor
    coluna_valor = detectar_coluna_valor(df)
    
    if not coluna_valor:
        return df, 0.0, None
    
    # Processar a coluna de valor
    df_processado, soma_total = processar_coluna_valor(df, coluna_valor)
    
    return df_processado, soma_total, coluna_valor

# ============================================
# CARREGAMENTO DE PLANILHAS
# ============================================

def carregar_planilha(arquivo):
    try:
        nome_arquivo = arquivo.name
        
        # Para arquivos CSV e TXT
        if nome_arquivo.endswith('.csv') or nome_arquivo.endswith('.txt'):
            encoding = detectar_encoding(arquivo)
            
            try:
                # Tentar com delimitador ponto-e-vírgula (padrão brasileiro)
                arquivo.seek(0)
                df = pd.read_csv(arquivo, delimiter=';', encoding=encoding, 
                                low_memory=False, on_bad_lines='skip')
                
                # Se tiver muitas colunas com nomes estranhos, pode ser vírgula
                if len(df.columns) == 1 and ';' in str(df.iloc[0, 0]):
                    # Tentar dividir por ponto-e-vírgula manualmente
                    arquivo.seek(0)
                    linhas = arquivo.read().decode(encoding).split('\n')
                    if linhas:
                        cabecalho = linhas[0].strip().split(';')
                        dados = []
                        for linha in linhas[1:]:
                            if linha.strip():
                                valores = linha.strip().split(';')
                                if len(valores) == len(cabecalho):
                                    dados.append(valores)
                        df = pd.DataFrame(dados, columns=cabecalho)
                
                # Verificar se o arquivo tem dados válidos
                if len(df) == 0:
                    st.warning(f"⚠️ Arquivo {nome_arquivo} está vazio")
                    return pd.DataFrame()
                
                # Remover linhas completamente vazias
                df = df.dropna(how='all')
                
                if len(df) == 0:
                    st.warning(f"⚠️ Arquivo {nome_arquivo} contém apenas linhas vazias")
                    return pd.DataFrame()
                
                return df
                
            except Exception as e:
                # Tentar com delimitador vírgula
                try:
                    arquivo.seek(0)
                    df = pd.read_csv(arquivo, delimiter=',', encoding=encoding,
                                    low_memory=False, on_bad_lines='skip')
                    
                    if len(df) > 0:
                        return df
                except:
                    pass
                
                # Última tentativa
                try:
                    arquivo.seek(0)
                    df = pd.read_csv(arquivo, sep=None, engine='python', encoding=encoding,
                                    low_memory=False, on_bad_lines='skip')
                    return df
                except:
                    st.error(f"❌ Erro ao ler arquivo {nome_arquivo}")
                    return pd.DataFrame()
        
        # Para arquivos Excel
        elif nome_arquivo.endswith(('.xlsx', '.xls')):
            try:
                df = pd.read_excel(arquivo)
                if len(df) == 0:
                    st.warning(f"⚠️ Arquivo {nome_arquivo} está vazio")
                return df
            except Exception as e:
                st.error(f"❌ Erro ao ler arquivo Excel {nome_arquivo}: {str(e)}")
                return pd.DataFrame()
        
        return pd.DataFrame()
        
    except Exception as e:
        st.error(f"❌ Erro ao processar {arquivo.name}: {str(e)}")
        return pd.DataFrame()

# ============================================
# ANÁLISE DE PROBLEMAS CRÍTICOS
# ============================================

def analisar_problemas_criticos(df, tipo):
    """Analisa problemas críticos nos dados"""
    problemas = []
    
    if df.empty:
        problemas.append("Arquivo vazio ou sem dados válidos")
        return problemas
    
    if tipo == 'pagamentos':
        coluna_conta = detectar_coluna_conta(df)
        coluna_valor = detectar_coluna_valor(df)
        coluna_nome = detectar_coluna_nome(df)
        
        # 1. Contas sem número
        if coluna_conta and coluna_conta in df.columns:
            try:
                contas_vazias = df[coluna_conta].isna().sum() + df[df[coluna_conta].astype(str).str.strip().isin(['', 'nan', 'NaN', 'None', 'null'])].shape[0]
                if contas_vazias > 0:
                    problemas.append(f"{contas_vazias} registros sem número de conta")
            except:
                pass
        
        # 2. Valores problemáticos
        if coluna_valor and coluna_valor in df.columns:
            try:
                # Processar valores para análise
                df_processado, soma_total, _ = detectar_e_processar_valores(df)
                
                if f'{coluna_valor}_Numerico' in df_processado.columns:
                    valores_zerados = (df_processado[f'{coluna_valor}_Numerico'] == 0).sum()
                    valores_negativos = (df_processado[f'{coluna_valor}_Numerico'] < 0).sum()
                    
                    if valores_zerados > 0:
                        problemas.append(f"{valores_zerados} pagamentos com valor zerado")
                    if valores_negativos > 0:
                        problemas.append(f"{valores_negativos} pagamentos com valor negativo")
            except:
                pass
        
        # 3. Nomes em branco
        if coluna_nome and coluna_nome in df.columns:
            try:
                nomes_vazios = df[coluna_nome].isna().sum() + df[df[coluna_nome].astype(str).str.strip().isin(['', 'nan', 'NaN', 'None', 'null'])].shape[0]
                if nomes_vazios > 0:
                    problemas.append(f"{nomes_vazios} registros sem nome do beneficiário")
            except:
                pass
    
    elif tipo == 'contas':
        coluna_conta = detectar_coluna_conta(df)
        coluna_nome = detectar_coluna_nome(df)
        coluna_cpf = detectar_coluna_cpf(df)
        
        # 1. Contas duplicadas
        if coluna_conta and coluna_conta in df.columns:
            try:
                df_limpo = df.copy()
                df_limpo[coluna_conta] = df_limpo[coluna_conta].astype(str).str.strip()
                df_sem_vazios = df_limpo[~df_limpo[coluna_conta].isin(['', 'nan', 'NaN', 'None', 'null'])]
                
                if not df_sem_vazios.empty:
                    duplicados = df_sem_vazios[df_sem_vazios.duplicated(subset=[coluna_conta], keep=False)]
                    if not duplicados.empty:
                        problemas.append(f"{duplicados[coluna_conta].nunique()} contas duplicadas")
            except:
                pass
        
        # 2. Nomes em branco
        if coluna_nome and coluna_nome in df.columns:
            try:
                nomes_vazios = df[coluna_nome].isna().sum() + df[df[coluna_nome].astype(str).str.strip().isin(['', 'nan', 'NaN', 'None', 'null'])].shape[0]
                if nomes_vazios > 0:
                    problemas.append(f"{nomes_vazios} registros sem nome")
            except:
                pass
        
        # 3. CPFs inválidos
        if coluna_cpf and coluna_cpf in df.columns:
            try:
                df_limpo = df.copy()
                df_limpo['CPF_Limpo'] = df_limpo[coluna_cpf].astype(str).apply(lambda x: re.sub(r'[^\d]', '', str(x)))
                cpf_invalidos = df_limpo[~df_limpo['CPF_Limpo'].str.match(r'^\d{11}$')].shape[0]
                if cpf_invalidos > 0:
                    problemas.append(f"{cpf_invalidos} CPFs com formato inválido")
            except:
                pass
    
    return problemas

# ============================================
# ANÁLISE DE PAGAMENTOS (COMPLETA)
# ============================================

def analisar_pagamentos_completos(df):
    """Análise completa dos pagamentos incluindo valores totais"""
    resultados = {
        'total_registros': 0,
        'registros_validos': 0,
        'valor_total': 0.0,
        'pagamentos_duplicados': 0,
        'valor_duplicados': 0.0,
        'projetos_ativos': 0,
        'beneficiarios_unicos': 0,
        'coluna_valor_detectada': None,
        'coluna_conta_detectada': None
    }
    
    if df.empty:
        return resultados
    
    resultados['total_registros'] = len(df)
    
    # Detectar colunas importantes
    coluna_conta = detectar_coluna_conta(df)
    coluna_nome = detectar_coluna_nome(df)
    coluna_projeto = detectar_coluna_projeto(df)
    
    resultados['coluna_conta_detectada'] = coluna_conta
    
    # Detectar e processar valores
    df_processado, valor_total, coluna_valor = detectar_e_processar_valores(df)
    
    resultados['coluna_valor_detectada'] = coluna_valor
    resultados['valor_total'] = valor_total
    
    # Contas válidas
    if coluna_conta and coluna_conta in df.columns:
        try:
            df[coluna_conta] = df[coluna_conta].astype(str).str.strip()
            validos = ~df[coluna_conta].isin(['', 'nan', 'NaN', 'None', 'null'])
            resultados['registros_validos'] = validos.sum()
            
            # Duplicidades
            df_validos = df[validos]
            if not df_validos.empty:
                duplicados = df_validos[df_validos.duplicated(subset=[coluna_conta], keep=False)]
                resultados['pagamentos_duplicados'] = duplicados[coluna_conta].nunique() if not duplicados.empty else 0
                
                # Calcular valor dos duplicados
                if coluna_valor and not duplicados.empty:
                    try:
                        duplicados_processados, valor_dup, _ = detectar_e_processar_valores(duplicados)
                        resultados['valor_duplicados'] = valor_dup
                    except:
                        pass
        except:
            pass
    
    # Beneficiários únicos
    if coluna_nome and coluna_nome in df.columns:
        try:
            df[coluna_nome] = df[coluna_nome].astype(str).str.strip()
            df_validos_nome = df[~df[coluna_nome].isin(['', 'nan', 'NaN', 'None', 'null'])]
            resultados['beneficiarios_unicos'] = df_validos_nome[coluna_nome].nunique()
        except:
            pass
    
    # Projetos ativos
    if coluna_projeto and coluna_projeto in df.columns:
        try:
            df[coluna_projeto] = df[coluna_projeto].astype(str).str.strip()
            df_validos_proj = df[~df[coluna_projeto].isin(['', 'nan', 'NaN', 'None', 'null'])]
            resultados['projetos_ativos'] = df_validos_proj[coluna_projeto].nunique()
        except:
            pass
    
    return resultados

# ============================================
# ANÁLISE DE CONTAS
# ============================================

def analisar_contas_completas(df):
    """Análise completa das contas"""
    resultados = {
        'total_contas': 0,
        'contas_unicas': 0,
        'beneficiarios_unicos': 0,
        'projetos_ativos': 0
    }
    
    if df.empty:
        return resultados
    
    resultados['total_contas'] = len(df)
    
    # Detectar colunas
    coluna_conta = detectar_coluna_conta(df)
    coluna_nome = detectar_coluna_nome(df)
    coluna_projeto = detectar_coluna_projeto(df)
    
    # Contas únicas
    if coluna_conta and coluna_conta in df.columns:
        try:
            df[coluna_conta] = df[coluna_conta].astype(str).str.strip()
            df_validos = df[~df[coluna_conta].isin(['', 'nan', 'NaN', 'None', 'null'])]
            resultados['contas_unicas'] = df_validos[coluna_conta].nunique()
        except:
            pass
    
    # Beneficiários únicos
    if coluna_nome and coluna_nome in df.columns:
        try:
            df[coluna_nome] = df[coluna_nome].astype(str).str.strip()
            df_validos = df[~df[coluna_nome].isin(['', 'nan', 'NaN', 'None', 'null'])]
            resultados['beneficiarios_unicos'] = df_validos[coluna_nome].nunique()
        except:
            pass
    
    # Projetos ativos
    if coluna_projeto and coluna_projeto in df.columns:
        try:
            df[coluna_projeto] = df[coluna_projeto].astype(str).str.strip()
            df_validos = df[~df[coluna_projeto].isin(['', 'nan', 'NaN', 'None', 'null'])]
            resultados['projetos_ativos'] = df_validos[coluna_projeto].nunique()
        except:
            pass
    
    return resultados

# ============================================
# COMPARAÇÃO ENTRE PAGAMENTOS E CONTAS
# ============================================

def comparar_pagamentos_contas(df_pagamentos, df_contas):
    """Compara pagamentos com abertura de contas"""
    comparacao = {
        'total_contas_abertas': 0,
        'total_contas_com_pagamento': 0,
        'total_contas_sem_pagamento': 0,
        'contas_sem_pagamento': []
    }
    
    if df_pagamentos.empty or df_contas.empty:
        return comparacao
    
    coluna_conta_pag = detectar_coluna_conta(df_pagamentos)
    coluna_conta_cont = detectar_coluna_conta(df_contas)
    
    if not coluna_conta_pag or not coluna_conta_cont:
        return comparacao
    
    try:
        # Limpar e extrair contas
        df_pagamentos[coluna_conta_pag] = df_pagamentos[coluna_conta_pag].astype(str).str.strip()
        df_contas[coluna_conta_cont] = df_contas[coluna_conta_cont].astype(str).str.strip()
        
        contas_pag = set(df_pagamentos[~df_pagamentos[coluna_conta_pag].isin(['', 'nan', 'NaN', 'None', 'null'])][coluna_conta_pag])
        contas_cont = set(df_contas[~df_contas[coluna_conta_cont].isin(['', 'nan', 'NaN', 'None', 'null'])][coluna_conta_cont])
        
        comparacao['total_contas_abertas'] = len(contas_cont)
        comparacao['total_contas_com_pagamento'] = len(contas_pag)
        comparacao['total_contas_sem_pagamento'] = len(contas_cont - contas_pag)
        comparacao['contas_sem_pagamento'] = list(contas_cont - contas_pag)
        
    except Exception as e:
        pass
    
    return comparacao

# ============================================
# GERAR RELATÓRIO PDF
# ============================================

def gerar_relatorio_pdf(mes, ano, metrics_pagamentos, metrics_contas, comparacao, 
                       problemas_pagamentos, problemas_contas, df_pagamentos, df_contas):
    """Gera relatório completo em PDF"""
    pdf = RelatorioPDF()
    pdf.add_page()
    
    # Capa
    pdf.set_font('Arial', 'B', 20)
    pdf.cell(0, 20, 'RELATORIO DE ANALISE', 0, 1, 'C')
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 15, 'SISTEMA POT - SMDET', 0, 1, 'C')
    pdf.set_font('Arial', 'I', 14)
    pdf.cell(0, 10, f'Periodo: {mes} de {ano}', 0, 1, 'C')
    pdf.ln(20)
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 10, f'Data de geracao: {data_hora_atual_brasilia()}', 0, 1, 'C')
    
    # Resumo Executivo
    pdf.add_page()
    pdf.chapter_title('RESUMO EXECUTIVO', 16)
    
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, 'Principais Metricas:', 0, 1)
    pdf.ln(3)
    
    # Métricas de pagamentos
    if metrics_pagamentos:
        pdf.add_metric('Total de Pagamentos:', 
                      formatar_brasileiro(metrics_pagamentos.get('total_registros', 0)))
        pdf.add_metric('Valor Total Pago:', 
                      formatar_brasileiro(metrics_pagamentos.get('valor_total', 0), 'monetario'))
        pdf.add_metric('Pagamentos Validos:', 
                      formatar_brasileiro(metrics_pagamentos.get('registros_validos', 0)))
        
        if metrics_pagamentos.get('valor_total', 0) > 0:
            pdf.add_metric('Valor Medio por Pagamento:', 
                          formatar_brasileiro(metrics_pagamentos.get('valor_total', 0) / 
                                             max(metrics_pagamentos.get('registros_validos', 1), 1), 
                                             'monetario'))
        
        pdf.add_metric('Pagamentos Duplicados:', 
                      formatar_brasileiro(metrics_pagamentos.get('pagamentos_duplicados', 0)), 
                      alert=metrics_pagamentos.get('pagamentos_duplicados', 0) > 0)
    
    # Métricas de contas
    if metrics_contas:
        pdf.add_metric('Contas Abertas:', 
                      formatar_brasileiro(metrics_contas.get('total_contas', 0)))
    
    # Comparação
    if comparacao:
        pdf.add_metric('Contas sem Pagamento:', 
                      formatar_brasileiro(comparacao.get('total_contas_sem_pagamento', 0)),
                      alert=comparacao.get('total_contas_sem_pagamento', 0) > 0)
    
    # Problemas Críticos
    if problemas_pagamentos or problemas_contas:
        pdf.ln(10)
        pdf.chapter_title('PROBLEMAS CRITICOS IDENTIFICADOS', 14)
        
        if problemas_pagamentos:
            pdf.set_font('Arial', 'B', 12)
            pdf.cell(0, 10, 'Nos Pagamentos:', 0, 1)
            pdf.set_font('Arial', '', 11)
            for problema in problemas_pagamentos[:10]:
                problema_limpo = limpar_texto_para_pdf(problema)
                pdf.multi_cell(0, 7, f"- {problema_limpo}")
            pdf.ln(5)
        
        if problemas_contas:
            pdf.set_font('Arial', 'B', 12)
            pdf.cell(0, 10, 'Nas Contas:', 0, 1)
            pdf.set_font('Arial', '', 11)
            for problema in problemas_contas[:10]:
                problema_limpo = limpar_texto_para_pdf(problema)
                pdf.multi_cell(0, 7, f"- {problema_limpo}")
    
    # Análise Detalhada de Pagamentos
    if not df_pagamentos.empty and 'valor_total' in metrics_pagamentos and metrics_pagamentos['valor_total'] > 0:
        pdf.add_page()
        pdf.chapter_title('ANALISE DETALHADA DE PAGAMENTOS', 16)
        
        # Estatísticas
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 10, 'Estatisticas:', 0, 1)
        pdf.ln(3)
        
        coluna_valor = metrics_pagamentos.get('coluna_valor_detectada')
        if coluna_valor:
            try:
                df_processado, valor_total, _ = detectar_e_processar_valores(df_pagamentos)
                if f'{coluna_valor}_Numerico' in df_processado.columns:
                    valores = df_processado[f'{coluna_valor}_Numerico']
                    
                    pdf.set_font('Arial', '', 11)
                    pdf.add_metric('Valor Minimo:', 
                                  formatar_brasileiro(valores.min(), 'monetario'))
                    pdf.add_metric('Valor Maximo:', 
                                  formatar_brasileiro(valores.max(), 'monetario'))
                    pdf.add_metric('Valor Medio:', 
                                  formatar_brasileiro(valores.mean(), 'monetario'))
                    pdf.add_metric('Valor Mediano:', 
                                  formatar_brasileiro(valores.median(), 'monetario'))
            except:
                pass
    
    # Análise de Inconsistências
    if comparacao and comparacao.get('total_contas_sem_pagamento', 0) > 0:
        pdf.add_page()
        pdf.chapter_title('INCONSISTENCIAS PARA CORRECAO', 16)
        
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 10, f'Contas Abertas sem Pagamento ({comparacao["total_contas_sem_pagamento"]}):', 0, 1)
        pdf.ln(3)
        
        if not df_contas.empty:
            coluna_conta = detectar_coluna_conta(df_contas)
            coluna_nome = detectar_coluna_nome(df_contas)
            
            if coluna_conta and coluna_nome:
                try:
                    contas_sem_pag = df_contas[
                        df_contas[coluna_conta].astype(str).isin(
                            [str(c) for c in comparacao.get('contas_sem_pagamento', [])]
                        )
                    ][[coluna_conta, coluna_nome]].head(20)
                    
                    if not contas_sem_pag.empty:
                        pdf.add_table(contas_sem_pag)
                except:
                    pass
    
    # Recomendações
    pdf.add_page()
    pdf.chapter_title('RECOMENDACOES', 14)
    
    recomendacoes = []
    
    if problemas_pagamentos:
        if any("zerado" in p.lower() for p in problemas_pagamentos):
            recomendacoes.append("Regularizar pagamentos com valores zerados")
        if any("negativo" in p.lower() for p in problemas_pagamentos):
            recomendacoes.append("Verificar pagamentos com valores negativos")
        if any("sem nome" in p.lower() for p in problemas_pagamentos):
            recomendacoes.append("Completar informacoes de beneficiarios sem nome")
    
    if problemas_contas:
        if any("duplicadas" in p.lower() for p in problemas_contas):
            recomendacoes.append("Verificar e corrigir contas duplicadas")
        if any("cpf" in p.lower() for p in problemas_contas):
            recomendacoes.append("Validar CPFs com formato invalido")
    
    if comparacao and comparacao.get('total_contas_sem_pagamento', 0) > 0:
        recomendacoes.append(f"Regularizar pagamentos para {comparacao['total_contas_sem_pagamento']} contas sem pagamento")
    
    if not recomendacoes:
        recomendacoes.append("Nenhuma acao corretiva necessaria identificada")
    
    pdf.set_font('Arial', '', 11)
    for i, rec in enumerate(recomendacoes[:10], 1):
        rec_limpa = limpar_texto_para_pdf(rec)
        pdf.multi_cell(0, 7, f"{i}. {rec_limpa}")
    
    # Gerar PDF
    try:
        pdf_output = pdf.output(dest='S')
        return pdf_output.encode('latin-1', 'replace')
    except:
        try:
            pdf_output = pdf.output(dest='S')
            return pdf_output.encode('utf-8')
        except:
            return b'PDF generation error'

# ============================================
# INTERFACE PRINCIPAL
# ============================================

def main():
    st.title("🏛️ Sistema POT - SMDET")
    st.markdown("### Sistema Completo de Análise de Pagamentos e Contas")
    st.markdown("---")
    
    # Sidebar
    st.sidebar.header("📤 Upload de Arquivos")
    
    uploaded_files = st.sidebar.file_uploader(
        "Carregue suas planilhas (CSV, TXT, Excel)",
        type=['csv', 'txt', 'xlsx', 'xls'],
        accept_multiple_files=True,
        help="Arraste ou selecione arquivos"
    )
    
    # Classificação automática
    arquivos_pagamentos = []
    arquivos_contas = []
    
    if uploaded_files:
        with st.spinner("Analisando arquivos..."):
            for arquivo in uploaded_files:
                nome = arquivo.name.upper()
                
                # Classificar por nome
                if any(palavra in nome for palavra in ['PGTO', 'PAGTO', 'PAGAMENTO', 'PAGTO.', 'PGTO.']):
                    arquivos_pagamentos.append(arquivo)
                    st.sidebar.success(f"📊 {arquivo.name} (Pagamentos)")
                elif any(palavra in nome for palavra in ['CADASTRO', 'CONTA', 'ABERTURA', 'REL.CADASTRO']):
                    arquivos_contas.append(arquivo)
                    st.sidebar.success(f"📋 {arquivo.name} (Contas)")
                else:
                    # Tentar classificar pelo conteúdo
                    try:
                        df_temp = carregar_planilha(arquivo)
                        if not df_temp.empty:
                            coluna_valor = detectar_coluna_valor(df_temp)
                            if coluna_valor:
                                arquivos_pagamentos.append(arquivo)
                                st.sidebar.info(f"📊 {arquivo.name} (Pagamentos - detectado)")
                            else:
                                coluna_conta = detectar_coluna_conta(df_temp)
                                if coluna_conta:
                                    arquivos_contas.append(arquivo)
                                    st.sidebar.info(f"📋 {arquivo.name} (Contas - detectado)")
                    except:
                        arquivos_pagamentos.append(arquivo)
                        st.sidebar.warning(f"⚠️ {arquivo.name} (Não classificado)")
    
    # Processar arquivos
    dfs_pagamentos = []
    dfs_contas = []
    
    if arquivos_pagamentos:
        with st.spinner("Processando arquivos de pagamentos..."):
            for arquivo in arquivos_pagamentos:
                df = carregar_planilha(arquivo)
                if not df.empty:
                    dfs_pagamentos.append({
                        'nome': arquivo.name,
                        'dataframe': df
                    })
    
    if arquivos_contas:
        with st.spinner("Processando arquivos de contas..."):
            for arquivo in arquivos_contas:
                df = carregar_planilha(arquivo)
                if not df.empty:
                    dfs_contas.append({
                        'nome': arquivo.name,
                        'dataframe': df
                    })
    
    # Combinar dados
    df_pagamentos = pd.DataFrame()
    if dfs_pagamentos:
        df_pagamentos = pd.concat([d['dataframe'] for d in dfs_pagamentos], ignore_index=True)
    
    df_contas = pd.DataFrame()
    if dfs_contas:
        df_contas = pd.concat([d['dataframe'] for d in dfs_contas], ignore_index=True)
    
    # Configuração do período
    st.sidebar.markdown("---")
    st.sidebar.header("📅 Período de Análise")
    
    meses = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
             'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
    
    col1, col2 = st.sidebar.columns(2)
    with col1:
        mes = st.selectbox("Mês", meses, index=8)
    with col2:
        ano_atual = datetime.now().year
        ano = st.selectbox("Ano", list(range(ano_atual, ano_atual - 3, -1)))
    
    # Botão de análise
    if st.sidebar.button("🚀 Realizar Análise Completa", type="primary", use_container_width=True):
        if not df_pagamentos.empty or not df_contas.empty:
            with st.spinner("Realizando análise completa..."):
                # Análise de pagamentos (INCLUINDO VALORES)
                if not df_pagamentos.empty:
                    metrics_pagamentos = analisar_pagamentos_completos(df_pagamentos)
                else:
                    metrics_pagamentos = {}
                
                # Análise de contas
                if not df_contas.empty:
                    metrics_contas = analisar_contas_completas(df_contas)
                else:
                    metrics_contas = {}
                
                # Comparação
                if not df_pagamentos.empty and not df_contas.empty:
                    comparacao = comparar_pagamentos_contas(df_pagamentos, df_contas)
                else:
                    comparacao = {}
                
                # Problemas críticos
                problemas_pagamentos = analisar_problemas_criticos(df_pagamentos, 'pagamentos')
                problemas_contas = analisar_problemas_criticos(df_contas, 'contas')
                
                # Exibir resultados
                st.success("✅ Análise completa concluída!")
                
                # Métricas principais
                st.subheader("📊 Métricas Principais")
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Total de Pagamentos", 
                             formatar_brasileiro(metrics_pagamentos.get('total_registros', 0)))
                
                with col2:
                    valor_total = metrics_pagamentos.get('valor_total', 0)
                    st.metric("Valor Total Pago", 
                             formatar_brasileiro(valor_total, 'monetario'))
                
                with col3:
                    if metrics_pagamentos.get('valor_total', 0) > 0 and metrics_pagamentos.get('registros_validos', 0) > 0:
                        valor_medio = valor_total / metrics_pagamentos['registros_validos']
                        st.metric("Valor Médio", 
                                 formatar_brasileiro(valor_medio, 'monetario'))
                    else:
                        st.metric("Valor Médio", "R$ 0,00")
                
                with col4:
                    st.metric("Contas Abertas", 
                             formatar_brasileiro(metrics_contas.get('total_contas', 0)))
                
                # Segunda linha de métricas
                col5, col6, col7, col8 = st.columns(4)
                
                with col5:
                    st.metric("Pagamentos Válidos", 
                             formatar_brasileiro(metrics_pagamentos.get('registros_validos', 0)))
                
                with col6:
                    st.metric("Pagamentos Duplicados", 
                             formatar_brasileiro(metrics_pagamentos.get('pagamentos_duplicados', 0)),
                             delta_color="inverse" if metrics_pagamentos.get('pagamentos_duplicados', 0) > 0 else "off")
                
                with col7:
                    st.metric("Beneficiários Únicos", 
                             formatar_brasileiro(metrics_pagamentos.get('beneficiarios_unicos', 
                                                                       metrics_contas.get('beneficiarios_unicos', 0))))
                
                with col8:
                    st.metric("Contas sem Pagamento", 
                             formatar_brasileiro(comparacao.get('total_contas_sem_pagamento', 0)),
                             delta_color="inverse" if comparacao.get('total_contas_sem_pagamento', 0) > 0 else "off")
                
                # Detalhes da detecção
                st.subheader("🔍 Detecção Automática")
                
                col_det1, col_det2 = st.columns(2)
                
                with col_det1:
                    if metrics_pagamentos.get('coluna_valor_detectada'):
                        st.info(f"**Coluna de valor detectada:** {metrics_pagamentos['coluna_valor_detectada']}")
                    else:
                        st.warning("❌ Coluna de valor não detectada")
                
                with col_det2:
                    if metrics_pagamentos.get('coluna_conta_detectada'):
                        st.info(f"**Coluna de conta detectada:** {metrics_pagamentos['coluna_conta_detectada']}")
                    else:
                        st.warning("❌ Coluna de conta não detectada")
                
                # Problemas Críticos
                if problemas_pagamentos or problemas_contas:
                    st.subheader("🚨 Problemas Críticos Identificados")
                    
                    col_prob1, col_prob2 = st.columns(2)
                    
                    with col_prob1:
                        if problemas_pagamentos:
                            st.error("**Nos Pagamentos:**")
                            for problema in problemas_pagamentos:
                                st.write(f"• {problema}")
                    
                    with col_prob2:
                        if problemas_contas:
                            st.warning("**Nas Contas:**")
                            for problema in problemas_contas:
                                st.write(f"• {problema}")
                else:
                    st.success("✅ Nenhum problema crítico identificado!")
                
                # Abas detalhadas
                tab1, tab2, tab3, tab4 = st.tabs([
                    "📋 Detalhes dos Dados", 
                    "⚠️ Duplicidades", 
                    "🔍 Inconsistências", 
                    "📈 Estatísticas"
                ])
                
                with tab1:
                    st.subheader("Dados Processados")
                    
                    if not df_pagamentos.empty:
                        st.write(f"**Pagamentos:** {len(df_pagamentos)} registros")
                        
                        coluna_valor = metrics_pagamentos.get('coluna_valor_detectada')
                        coluna_conta = metrics_pagamentos.get('coluna_conta_detectada')
                        
                        if coluna_valor:
                            st.write(f"Coluna de valor: **{coluna_valor}**")
                        if coluna_conta:
                            st.write(f"Coluna de conta: **{coluna_conta}**")
                        
                        with st.expander("Ver primeiros registros"):
                            st.dataframe(df_pagamentos.head(10))
                    
                    if not df_contas.empty:
                        st.write(f"**Contas:** {len(df_contas)} registros")
                        with st.expander("Ver primeiros registros"):
                            st.dataframe(df_contas.head(10))
                
                with tab2:
                    st.subheader("Análise de Duplicidades")
                    
                    if not df_pagamentos.empty:
                        coluna_conta = metrics_pagamentos.get('coluna_conta_detectada')
                        
                        if coluna_conta and coluna_conta in df_pagamentos.columns:
                            df_pagamentos[coluna_conta] = df_pagamentos[coluna_conta].astype(str).str.strip()
                            df_validos = df_pagamentos[~df_pagamentos[coluna_conta].isin(['', 'nan', 'NaN', 'None', 'null'])]
                            
                            if not df_validos.empty:
                                duplicados = df_validos[df_validos.duplicated(subset=[coluna_conta], keep=False)]
                                
                                if not duplicados.empty:
                                    st.warning(f"🚨 {duplicados[coluna_conta].nunique()} contas com pagamentos duplicados")
                                    coluna_nome = detectar_coluna_nome(duplicados)
                                    colunas_mostrar = [coluna_conta]
                                    if coluna_nome and coluna_nome in duplicados.columns:
                                        colunas_mostrar.append(coluna_nome)
                                    
                                    # Adicionar valor se disponível
                                    coluna_valor = metrics_pagamentos.get('coluna_valor_detectada')
                                    if coluna_valor and coluna_valor in duplicados.columns:
                                        colunas_mostrar.append(coluna_valor)
                                    
                                    st.dataframe(duplicados[colunas_mostrar].head(20))
                                else:
                                    st.success("✅ Nenhuma duplicidade encontrada")
                
                with tab3:
                    st.subheader("Inconsistências para Correção")
                    
                    if comparacao and comparacao.get('total_contas_sem_pagamento', 0) > 0:
                        st.error(f"⚠️ {comparacao['total_contas_sem_pagamento']} contas abertas sem pagamento registrado")
                        
                        if not df_contas.empty:
                            coluna_conta = detectar_coluna_conta(df_contas)
                            coluna_nome = detectar_coluna_nome(df_contas)
                            
                            if coluna_conta and coluna_nome:
                                try:
                                    contas_sem_pag = df_contas[
                                        df_contas[coluna_conta].astype(str).isin(
                                            [str(c) for c in comparacao['contas_sem_pagamento']]
                                        )
                                    ][[coluna_conta, coluna_nome]]
                                    
                                    if not contas_sem_pag.empty:
                                        st.dataframe(contas_sem_pag.head(50))
                                except:
                                    pass
                    else:
                        st.success("✅ Nenhuma inconsistência grave encontrada")
                
                with tab4:
                    st.subheader("Estatísticas Detalhadas")
                    
                    if not df_pagamentos.empty and metrics_pagamentos.get('valor_total', 0) > 0:
                        coluna_valor = metrics_pagamentos.get('coluna_valor_detectada')
                        
                        if coluna_valor:
                            try:
                                df_processado, valor_total, _ = detectar_e_processar_valores(df_pagamentos)
                                
                                if f'{coluna_valor}_Numerico' in df_processado.columns:
                                    valores = df_processado[f'{coluna_valor}_Numerico']
                                    
                                    # Gráfico de distribuição
                                    fig = px.histogram(valores, 
                                                     title='Distribuição dos Valores de Pagamento',
                                                     nbins=20,
                                                     labels={'value': 'Valor (R$)', 'count': 'Quantidade'})
                                    st.plotly_chart(fig, use_container_width=True)
                                    
                                    # Estatísticas
                                    st.write("**Estatísticas Descritivas:**")
                                    estat_df = pd.DataFrame({
                                        'Estatística': ['Mínimo', 'Máximo', 'Média', 'Mediana', 'Soma Total'],
                                        'Valor': [
                                            formatar_brasileiro(valores.min(), 'monetario'),
                                            formatar_brasileiro(valores.max(), 'monetario'),
                                            formatar_brasileiro(valores.mean(), 'monetario'),
                                            formatar_brasileiro(valores.median(), 'monetario'),
                                            formatar_brasileiro(valores.sum(), 'monetario')
                                        ]
                                    })
                                    st.dataframe(estat_df)
                            except:
                                st.info("Não foi possível gerar estatísticas detalhadas")
                
                # Gerar PDF
                st.subheader("📄 Relatório Completo em PDF")
                
                try:
                    pdf_bytes = gerar_relatorio_pdf(mes, ano, metrics_pagamentos, metrics_contas, comparacao,
                                                  problemas_pagamentos, problemas_contas, df_pagamentos, df_contas)
                    
                    if pdf_bytes and pdf_bytes != b'PDF generation error':
                        st.download_button(
                            label="📥 Baixar Relatório Completo (PDF)",
                            data=pdf_bytes,
                            file_name=f"Relatorio_POT_{mes}_{ano}.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )
                        st.success("✅ Relatório PDF gerado com sucesso!")
                except Exception as e:
                    st.error(f"Erro ao gerar PDF: {str(e)}")
                
                # Exportar dados
                st.subheader("📤 Exportar Dados")
                
                col_exp1, col_exp2 = st.columns(2)
                
                with col_exp1:
                    if not df_pagamentos.empty:
                        csv_pag = df_pagamentos.to_csv(index=False, sep=';', encoding='utf-8')
                        st.download_button(
                            label="📊 Exportar Pagamentos (CSV)",
                            data=csv_pag,
                            file_name=f"pagamentos_{mes}_{ano}.csv",
                            mime="text/csv"
                        )
                
                with col_exp2:
                    if not df_contas.empty:
                        csv_cont = df_contas.to_csv(index=False, sep=';', encoding='utf-8')
                        st.download_button(
                            label="📋 Exportar Contas (CSV)",
                            data=csv_cont,
                            file_name=f"contas_{mes}_{ano}.csv",
                            mime="text/csv"
                        )
        
        else:
            st.warning("⚠️ Nenhum arquivo com dados válidos foi carregado")
    
    else:
        # Tela inicial
        st.info("👈 Carregue seus arquivos e clique em 'Realizar Análise Completa'")

if __name__ == "__main__":
    main()
