# app.py - SISTEMA POT SMDET - VERSÃO CORRIGIDA COM INDENTAÇÃO CORRETA
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
        self.cell(0, 10, 'Relatório de Análise de Pagamentos e Contas', 0, 1, 'C')
        self.ln(5)
    
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()} - Gerado em {datetime.now().strftime("%d/%m/%Y %H:%M")}', 0, 0, 'C')
    
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
        if df.empty:
            self.cell(0, 8, "Nenhum dado disponível", 0, 1)
            return
        
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
    return agora_brasilia().strftime("%d/%m/%Y às %H:%M")

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
# DETECÇÃO AUTOMÁTICA DE COLUNAS (PRECISA)
# ============================================

def detectar_coluna_conta(df):
    """Detecta a coluna de número da conta de forma precisa"""
    if df.empty:
        return None
    
    # Lista PRIORITÁRIA de nomes de coluna para conta
    colunas_prioridade = [
        'Num Cartao', 'NumCartao', 'Num_Cartao', 'Num Cartão',
        'Cartao', 'Cartão', 'Conta', 'Numero Conta', 'Número Conta',
        'NUMCARTAO', 'NUM_CARTAO', 'NUMERO_CARTAO', 'NÚMERO CARTÃO'
    ]
    
    # 1. Busca exata primeiro
    for coluna in df.columns:
        coluna_limpa = str(coluna).strip()
        for padrao in colunas_prioridade:
            if coluna_limpa.lower() == padrao.lower():
                return coluna
    
    # 2. Busca por substring
    for coluna in df.columns:
        coluna_limpa = str(coluna).strip().upper()
        for padrao in colunas_prioridade:
            if padrao.upper() in coluna_limpa:
                return coluna
    
    # 3. Busca por padrão de conteúdo (números de 6+ dígitos)
    for coluna in df.columns:
        if df[coluna].dtype == 'object':
            try:
                amostra = df[coluna].dropna().head(10).astype(str)
                # Verificar se a maioria tem números de conta
                conta_pattern = r'^\d{6,}$'
                matches = sum(1 for x in amostra if re.match(conta_pattern, str(x).strip()))
                if matches >= 5:  # Pelo menos 5 dos 10 são números de conta
                    return coluna
            except:
                continue
    
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

def detectar_coluna_valor_pagto(df):
    """Detecta PRECISAMENTE a coluna de valor pago"""
    if df.empty:
        return None
    
    # Colunas PRIORITÁRIAS - exatamente como aparecem nos arquivos
    colunas_prioridade = [
        'Valor Pagto', 'ValorPagto', 'Valor_Pagto', 'Valor Pago', 'ValorPago',
        'Valor_Pago', 'VALOR PAGTO', 'VALOR_PAGTO', 'VALOR PAGO'
    ]
    
    # 1. Busca exata primeiro
    for coluna in df.columns:
        coluna_limpa = str(coluna).strip()
        for padrao in colunas_prioridade:
            if coluna_limpa.lower() == padrao.lower():
                return coluna
    
    # 2. Busca por substring
    for coluna in df.columns:
        coluna_limpa = str(coluna).strip().upper()
        for padrao in colunas_prioridade:
            if padrao.upper() in coluna_limpa:
                return coluna
    
    # 3. Busca por colunas numéricas com valores positivos
    for coluna in df.columns:
        if df[coluna].dtype in ['float64', 'int64', 'float32', 'int32']:
            # Verificar se os valores são positivos (pagamentos são positivos)
            if not df[coluna].empty:
                amostra = df[coluna].dropna().head(20)
                if len(amostra) > 0:
                    # Pagamentos geralmente são valores positivos
                    if amostra.mean() > 0:
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
# PROCESSAMENTO DE VALORES MONETÁRIOS (CORRETO)
# ============================================

def converter_valor_monetario(valor):
    """Converte valor monetário para float CORRETAMENTE"""
    if pd.isna(valor):
        return 0.0
    
    try:
        # Se já é numérico, retorna diretamente
        if isinstance(valor, (int, float, np.integer, np.floating)):
            return float(valor)
        
        valor_str = str(valor).strip()
        
        if valor_str == '' or valor_str.lower() in ['nan', 'none', 'null']:
            return 0.0
        
        # Remover símbolos de moeda e espaços
        valor_str = re.sub(r'[R\$\s€£¥]', '', valor_str)
        
        # Verificar se tem formato brasileiro (1.234,56)
        # Contar vírgulas e pontos
        tem_virgula = ',' in valor_str
        tem_ponto = '.' in valor_str
        
        if tem_virgula and tem_ponto:
            # Formato 1.234,56 -> pontos são separadores de milhar
            # Verificar posição da vírgula
            pos_virgula = valor_str.find(',')
            pos_ponto = valor_str.find('.')
            
            if pos_virgula > pos_ponto:
                # Vírgula está depois do ponto -> 1.234,56
                valor_str = valor_str.replace('.', '').replace(',', '.')
            else:
                # Ponto está depois da vírgula -> 1,234.56 (formato americano)
                valor_str = valor_str.replace(',', '')
        
        elif tem_virgula and not tem_ponto:
            # Formato 1234,56
            # Verificar se é separador decimal ou de milhar
            partes = valor_str.split(',')
            if len(partes) == 2 and len(partes[1]) <= 2:
                # Provavelmente decimal (1234,56)
                valor_str = valor_str.replace(',', '.')
            else:
                # Provavelmente separador de milhar (1,234)
                valor_str = valor_str.replace(',', '')
        
        # Remover qualquer caractere não numérico exceto ponto e sinal negativo
        valor_str = re.sub(r'[^\d\.\-]', '', valor_str)
        
        # Se ficou vazio
        if not valor_str or valor_str == '-' or valor_str == '.':
            return 0.0
        
        # Converter para float
        resultado = float(valor_str)
        
        # Garantir que valores de pagamento são positivos
        # (valores negativos podem indicar desconto ou estorno)
        return abs(resultado)
        
    except Exception as e:
        return 0.0

def processar_valores_dataframe(df, coluna_valor):
    """Processa todos os valores de uma coluna e calcula total CORRETAMENTE"""
    if df.empty or coluna_valor not in df.columns:
        return df, 0.0
    
    try:
        df_processado = df.copy()
        
        # Converter todos os valores
        valores_convertidos = []
        for valor in df_processado[coluna_valor]:
            valor_convertido = converter_valor_monetario(valor)
            valores_convertidos.append(valor_convertido)
        
        # Adicionar coluna com valores convertidos
        df_processado[f'{coluna_valor}_Numerico'] = valores_convertidos
        
        # Calcular soma total
        soma_total = sum(valores_convertidos)
        
        return df_processado, soma_total
        
    except Exception as e:
        return df, 0.0

# ============================================
# CARREGAMENTO DE PLANILHAS
# ============================================

def carregar_planilha(arquivo):
    try:
        nome_arquivo = arquivo.name
        
        if nome_arquivo.endswith('.csv') or nome_arquivo.endswith('.txt'):
            encoding = detectar_encoding(arquivo)
            
            try:
                # Primeiro tentar com ponto-e-vírgula
                arquivo.seek(0)
                df = pd.read_csv(arquivo, delimiter=';', encoding=encoding, 
                                low_memory=False, on_bad_lines='skip')
                
                # Remover linhas completamente vazias
                df = df.dropna(how='all')
                
                if len(df) == 0:
                    return pd.DataFrame()
                
                # Remover linhas que são só ponto-e-vírgula
                df = df[df.apply(lambda row: row.astype(str).str.strip().ne('').any(), axis=1)]
                
                return df
                
            except Exception as e:
                # Tentar com vírgula
                try:
                    arquivo.seek(0)
                    df = pd.read_csv(arquivo, delimiter=',', encoding=encoding,
                                    low_memory=False, on_bad_lines='skip')
                    
                    if len(df) > 0:
                        return df
                except:
                    return pd.DataFrame()
        
        elif nome_arquivo.endswith(('.xlsx', '.xls')):
            try:
                df = pd.read_excel(arquivo)
                df = df.dropna(how='all')
                return df
            except:
                return pd.DataFrame()
        
        return pd.DataFrame()
        
    except Exception as e:
        return pd.DataFrame()

# ============================================
# ANÁLISE PRECISA DE PAGAMENTOS
# ============================================

def analisar_pagamentos_preciso(df):
    """Análise PRECISA dos pagamentos com cálculos corretos"""
    resultados = {
        'total_linhas': 0,
        'total_pagamentos_validos': 0,
        'pagamentos_sem_conta': 0,
        'valor_total_correto': 0.0,
        'valor_medio': 0.0,
        'pagamentos_duplicados': 0,
        'valor_duplicados': 0.0,
        'coluna_conta_detectada': None,
        'coluna_valor_detectada': None,
        'linhas_sem_conta': [],  # Linhas que não têm conta
        'pagamentos_duplicados_detalhes': []  # Detalhes das duplicidades
    }
    
    if df.empty:
        return resultados
    
    # Contagem EXATA de linhas
    resultados['total_linhas'] = len(df)
    
    # Detectar colunas importantes
    coluna_conta = detectar_coluna_conta(df)
    coluna_valor = detectar_coluna_valor_pagto(df)
    
    resultados['coluna_conta_detectada'] = coluna_conta
    resultados['coluna_valor_detectada'] = coluna_valor
    
    if coluna_conta:
        # Identificar EXATAMENTE quais linhas têm conta válida
        df[coluna_conta] = df[coluna_conta].astype(str).str.strip()
        
        # Conta válida: não vazia e não é nan/null
        def conta_valida(valor):
            valor_str = str(valor)
            return valor_str not in ['', 'nan', 'NaN', 'None', 'null', 'NaT'] and valor_str.strip() != ''
        
        # Aplicar a função
        contas_validas = df[coluna_conta].apply(conta_valida)
        
        # Contagem EXATA
        resultados['total_pagamentos_validos'] = contas_validas.sum()
        resultados['pagamentos_sem_conta'] = (~contas_validas).sum()
        
        # Identificar as linhas sem conta
        linhas_sem_conta = df[~contas_validas]
        if not linhas_sem_conta.empty:
            resultados['linhas_sem_conta'] = linhas_sem_conta.index.tolist()
        
        # Análise de duplicidades APENAS entre contas válidas
        df_validos = df[contas_validas]
        if not df_validos.empty:
            # Encontrar duplicidades exatas
            duplicados = df_validos[df_validos.duplicated(subset=[coluna_conta], keep=False)]
            
            if not duplicados.empty:
                # Contar número de contas duplicadas
                contas_duplicadas = duplicados[coluna_conta].unique()
                resultados['pagamentos_duplicados'] = len(contas_duplicadas)
                
                # Salvar detalhes das duplicidades
                resultados['pagamentos_duplicados_detalhes'] = duplicados.head(50).to_dict('records')
    
    # Cálculo PRECISO do valor total
    if coluna_valor:
        # Processar valores
        df_processado, valor_total = processar_valores_dataframe(df, coluna_valor)
        resultados['valor_total_correto'] = valor_total
        
        # Calcular valor médio apenas entre pagamentos válidos
        if resultados['total_pagamentos_validos'] > 0:
            resultados['valor_medio'] = valor_total / resultados['total_pagamentos_validos']
        
        # Calcular valor das duplicidades
        if resultados['pagamentos_duplicados'] > 0 and coluna_conta:
            df_validos = df[df[coluna_conta].apply(lambda x: str(x).strip() not in ['', 'nan', 'NaN', 'None', 'null'])]
            duplicados = df_validos[df_validos.duplicated(subset=[coluna_conta], keep=False)]
            if not duplicados.empty:
                duplicados_processado, valor_dup = processar_valores_dataframe(duplicados, coluna_valor)
                resultados['valor_duplicados'] = valor_dup
    
    return resultados

# ============================================
# IDENTIFICAÇÃO DE INCONSISTÊNCIAS
# ============================================

def identificar_inconsistencias_pagamentos(df):
    """Identifica TODAS as inconsistências nos pagamentos"""
    inconsistencias = []
    
    if df.empty:
        return inconsistencias
    
    # Detectar colunas
    coluna_conta = detectar_coluna_conta(df)
    coluna_valor = detectar_coluna_valor_pagto(df)
    coluna_nome = detectar_coluna_nome(df)
    coluna_data = detectar_coluna_data(df)
    
    # 1. Pagamentos sem número de conta
    if coluna_conta:
        df[coluna_conta] = df[coluna_conta].astype(str).str.strip()
        sem_conta = df[df[coluna_conta].isin(['', 'nan', 'NaN', 'None', 'null'])]
        
        if not sem_conta.empty:
            # Criar DataFrame detalhado das inconsistências
            for idx, row in sem_conta.iterrows():
                inconsistencia = {
                    'tipo': 'SEM CONTA',
                    'linha': idx + 2,  # +2 porque CSV: linha 1 = cabeçalho
                    'descricao': 'Pagamento sem número de conta',
                    'detalhes': {}
                }
                
                # Adicionar informações disponíveis
                if coluna_nome and coluna_nome in row:
                    inconsistencia['detalhes']['nome'] = str(row[coluna_nome])
                
                if coluna_valor and coluna_valor in row:
                    inconsistencia['detalhes']['valor'] = str(row[coluna_valor])
                
                if coluna_data and coluna_data[0] in row if coluna_data else False:
                    inconsistencia['detalhes']['data'] = str(row[coluna_data[0]])
                
                inconsistencias.append(inconsistencia)
    
    # 2. Valores zerados ou negativos
    if coluna_valor:
        try:
            df_processado, _ = processar_valores_dataframe(df, coluna_valor)
            coluna_numerica = f'{coluna_valor}_Numerico'
            
            if coluna_numerica in df_processado.columns:
                # Valores zerados
                valores_zerados = df_processado[df_processado[coluna_numerica] == 0]
                
                for idx, row in valores_zerados.iterrows():
                    inconsistencia = {
                        'tipo': 'VALOR ZERADO',
                        'linha': idx + 2,
                        'descricao': 'Pagamento com valor zerado',
                        'detalhes': {
                            'conta': str(row[coluna_conta]) if coluna_conta and coluna_conta in row else 'N/A',
                            'valor': 'R$ 0,00'
                        }
                    }
                    
                    if coluna_nome and coluna_nome in row:
                        inconsistencia['detalhes']['nome'] = str(row[coluna_nome])
                    
                    inconsistencias.append(inconsistencia)
                
                # Valores negativos
                valores_negativos = df_processado[df_processado[coluna_numerica] < 0]
                
                for idx, row in valores_negativos.iterrows():
                    inconsistencia = {
                        'tipo': 'VALOR NEGATIVO',
                        'linha': idx + 2,
                        'descricao': 'Pagamento com valor negativo',
                        'detalhes': {
                            'conta': str(row[coluna_conta]) if coluna_conta and coluna_conta in row else 'N/A',
                            'valor': formatar_brasileiro(row[coluna_numerica], 'monetario')
                        }
                    }
                    
                    if coluna_nome and coluna_nome in row:
                        inconsistencia['detalhes']['nome'] = str(row[coluna_nome])
                    
                    inconsistencias.append(inconsistencia)
        except:
            pass
    
    # 3. Nomes em branco (apenas para registros com conta)
    if coluna_nome and coluna_conta:
        try:
            # Primeiro filtrar registros com conta válida
            contas_validas = df[~df[coluna_conta].isin(['', 'nan', 'NaN', 'None', 'null'])]
            
            # Agora verificar nomes em branco apenas entre contas válidas
            nomes_em_branco = contas_validas[contas_validas[coluna_nome].isna() | 
                                           (contas_validas[coluna_nome].astype(str).str.strip() == '')]
            
            for idx, row in nomes_em_branco.iterrows():
                inconsistencia = {
                    'tipo': 'NOME EM BRANCO',
                    'linha': idx + 2,
                    'descricao': 'Beneficiário sem nome',
                    'detalhes': {
                        'conta': str(row[coluna_conta]),
                        'nome': 'EM BRANCO'
                    }
                }
                
                if coluna_valor and coluna_valor in row:
                    inconsistencia['detalhes']['valor'] = str(row[coluna_valor])
                
                inconsistencias.append(inconsistencia)
        except:
            pass
    
    return inconsistencias

# ============================================
# ANÁLISE DE CONTAS
# ============================================

def analisar_contas_preciso(df):
    """Análise precisa das contas"""
    resultados = {
        'total_contas': 0,
        'contas_unicas': 0,
        'contas_duplicadas': 0,
        'contas_sem_nome': 0
    }
    
    if df.empty:
        return resultados
    
    resultados['total_contas'] = len(df)
    
    coluna_conta = detectar_coluna_conta(df)
    coluna_nome = detectar_coluna_nome(df)
    
    if coluna_conta:
        # Limpar dados
        df[coluna_conta] = df[coluna_conta].astype(str).str.strip()
        
        # Filtrar contas válidas
        contas_validas = df[~df[coluna_conta].isin(['', 'nan', 'NaN', 'None', 'null'])]
        
        if not contas_validas.empty:
            # Contas únicas
            resultados['contas_unicas'] = contas_validas[coluna_conta].nunique()
            
            # Contas duplicadas
            duplicados = contas_validas[contas_validas.duplicated(subset=[coluna_conta], keep=False)]
            if not duplicados.empty:
                resultados['contas_duplicadas'] = duplicados[coluna_conta].nunique()
    
    if coluna_nome:
        # Contas sem nome (apenas entre contas válidas)
        if coluna_conta:
            contas_validas = df[~df[coluna_conta].isin(['', 'nan', 'NaN', 'None', 'null'])]
            sem_nome = contas_validas[contas_validas[coluna_nome].isna() | 
                                    (contas_validas[coluna_nome].astype(str).str.strip() == '')]
            resultados['contas_sem_nome'] = len(sem_nome)
    
    return resultados

# ============================================
# COMPARAÇÃO PAGAMENTOS VS CONTAS
# ============================================

def comparar_pagamentos_contas(df_pagamentos, df_contas):
    """Comparação precisa entre pagamentos e contas"""
    comparacao = {
        'contas_sem_pagamento': [],
        'total_contas_sem_pagamento': 0,
        'detalhes_contas_sem_pagamento': []
    }
    
    if df_pagamentos.empty or df_contas.empty:
        return comparacao
    
    coluna_conta_pag = detectar_coluna_conta(df_pagamentos)
    coluna_conta_cont = detectar_coluna_conta(df_contas)
    
    if not coluna_conta_pag or not coluna_conta_cont:
        return comparacao
    
    try:
        # Extrair contas válidas de pagamentos
        df_pagamentos[coluna_conta_pag] = df_pagamentos[coluna_conta_pag].astype(str).str.strip()
        contas_pag_validas = set(
            df_pagamentos[~df_pagamentos[coluna_conta_pag].isin(['', 'nan', 'NaN', 'None', 'null'])][coluna_conta_pag]
        )
        
        # Extrair contas válidas de contas
        df_contas[coluna_conta_cont] = df_contas[coluna_conta_cont].astype(str).str.strip()
        df_contas_validas = df_contas[~df_contas[coluna_conta_cont].isin(['', 'nan', 'NaN', 'None', 'null'])]
        contas_cont_validas = set(df_contas_validas[coluna_conta_cont])
        
        # Encontrar contas sem pagamento
        contas_sem_pagamento = contas_cont_validas - contas_pag_validas
        comparacao['total_contas_sem_pagamento'] = len(contas_sem_pagamento)
        comparacao['contas_sem_pagamento'] = list(contas_sem_pagamento)
        
        # Detalhar contas sem pagamento
        coluna_nome_cont = detectar_coluna_nome(df_contas)
        
        for conta in contas_sem_pagamento:
            detalhe = {'conta': conta}
            
            # Encontrar linha correspondente
            linha_conta = df_contas_validas[df_contas_validas[coluna_conta_cont] == conta]
            
            if not linha_conta.empty and coluna_nome_cont and coluna_nome_cont in linha_conta.columns:
                detalhe['nome'] = str(linha_conta.iloc[0][coluna_nome_cont])
            
            comparacao['detalhes_contas_sem_pagamento'].append(detalhe)
            
    except Exception as e:
        pass
    
    return comparacao

# ============================================
# GERAR RELATÓRIO PDF COM DETALHES
# ============================================

def gerar_relatorio_pdf_detalhado(mes, ano, analise_pagamentos, analise_contas, comparacao, 
                                 inconsistencias_pagamentos, df_pagamentos):
    """Gera relatório PDF com todos os detalhes"""
    pdf = RelatorioPDF()
    pdf.add_page()
    
    # Capa
    pdf.set_font('Arial', 'B', 20)
    pdf.cell(0, 20, 'RELATÓRIO DE ANÁLISE', 0, 1, 'C')
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 15, 'SISTEMA POT - SMDET', 0, 1, 'C')
    pdf.set_font('Arial', 'I', 14)
    pdf.cell(0, 10, f'Período: {mes} de {ano}', 0, 1, 'C')
    pdf.ln(20)
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 10, f'Data de geração: {data_hora_atual_brasilia()}', 0, 1, 'C')
    
    # Resumo Executivo
    pdf.add_page()
    pdf.chapter_title('RESUMO EXECUTIVO', 16)
    
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, 'Métricas Principais:', 0, 1)
    pdf.ln(3)
    
    # Métricas de pagamentos
    pdf.add_metric('Total de Linhas Analisadas:', 
                  formatar_brasileiro(analise_pagamentos.get('total_linhas', 0)))
    pdf.add_metric('Pagamentos Válidos (com conta):', 
                  formatar_brasileiro(analise_pagamentos.get('total_pagamentos_validos', 0)))
    pdf.add_metric('Pagamentos sem Conta:', 
                  formatar_brasileiro(analise_pagamentos.get('pagamentos_sem_conta', 0)),
                  alert=analise_pagamentos.get('pagamentos_sem_conta', 0) > 0)
    pdf.add_metric('Valor Total Pago:', 
                  formatar_brasileiro(analise_pagamentos.get('valor_total_correto', 0), 'monetario'))
    
    if analise_pagamentos.get('total_pagamentos_validos', 0) > 0:
        pdf.add_metric('Valor Médio por Pagamento:', 
                      formatar_brasileiro(analise_pagamentos.get('valor_medio', 0), 'monetario'))
    
    pdf.add_metric('Contas com Pagamentos Duplicados:', 
                  formatar_brasileiro(analise_pagamentos.get('pagamentos_duplicados', 0)),
                  alert=analise_pagamentos.get('pagamentos_duplicados', 0) > 0)
    
    if analise_contas:
        pdf.add_metric('Contas Abertas:', 
                      formatar_brasileiro(analise_contas.get('total_contas', 0)))
    
    if comparacao:
        pdf.add_metric('Contas sem Pagamento:', 
                      formatar_brasileiro(comparacao.get('total_contas_sem_pagamento', 0)),
                      alert=comparacao.get('total_contas_sem_pagamento', 0) > 0)
    
    # Detecção de Colunas
    pdf.ln(10)
    pdf.chapter_title('DETECÇÃO DE COLUNAS', 14)
    
    pdf.set_font('Arial', 'B', 11)
    pdf.cell(0, 8, 'Colunas detectadas nos pagamentos:', 0, 1)
    pdf.set_font('Arial', '', 11)
    
    if analise_pagamentos.get('coluna_conta_detectada'):
        pdf.cell(0, 7, f"• Conta: {analise_pagamentos['coluna_conta_detectada']}", 0, 1)
    
    if analise_pagamentos.get('coluna_valor_detectada'):
        pdf.cell(0, 7, f"• Valor: {analise_pagamentos['coluna_valor_detectada']}", 0, 1)
    
    # Inconsistências Detalhadas
    if inconsistencias_pagamentos:
        pdf.add_page()
        pdf.chapter_title('INCONSISTÊNCIAS IDENTIFICADAS', 16)
        
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 10, f'Total de Inconsistências: {len(inconsistencias_pagamentos)}', 0, 1)
        pdf.ln(3)
        
        # Agrupar por tipo
        tipos_inconsistencia = {}
        for inc in inconsistencias_pagamentos:
            tipo = inc['tipo']
            if tipo not in tipos_inconsistencia:
                tipos_inconsistencia[tipo] = []
            tipos_inconsistencia[tipo].append(inc)
        
        for tipo, lista_inc in tipos_inconsistencia.items():
            pdf.set_font('Arial', 'B', 11)
            pdf.cell(0, 8, f'{tipo} ({len(lista_inc)} ocorrências):', 0, 1)
            pdf.set_font('Arial', '', 10)
            
            for inc in lista_inc[:10]:  # Limitar a 10 por tipo para não sobrecarregar
                pdf.multi_cell(0, 6, f"Linha {inc['linha']}: {inc['descricao']}")
                
                detalhes_texto = []
                for chave, valor in inc['detalhes'].items():
                    detalhes_texto.append(f"{chave}: {valor}")
                
                if detalhes_texto:
                    pdf.multi_cell(0, 6, f"  Detalhes: {', '.join(detalhes_texto)}")
                
                pdf.ln(1)
            
            if len(lista_inc) > 10:
                pdf.set_font('Arial', 'I', 9)
                pdf.cell(0, 6, f'... e mais {len(lista_inc) - 10} registros', 0, 1)
            
            pdf.ln(3)
    
    # Contas sem Pagamento (se houver)
    if comparacao and comparacao.get('total_contas_sem_pagamento', 0) > 0:
        pdf.add_page()
        pdf.chapter_title('CONTAS ABERTAS SEM PAGAMENTO', 16)
        
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 10, f'Total: {comparacao["total_contas_sem_pagamento"]} contas', 0, 1)
        pdf.ln(3)
        
        # Criar DataFrame para tabela
        dados_tabela = []
        for detalhe in comparacao.get('detalhes_contas_sem_pagamento', []):
            dados_tabela.append({
                'Conta': detalhe.get('conta', ''),
                'Nome': detalhe.get('nome', 'NÃO IDENTIFICADO')
            })
        
        if dados_tabela:
            df_tabela = pd.DataFrame(dados_tabela)
            pdf.add_table(df_tabela.head(50))
    
    # Recomendações
    pdf.add_page()
    pdf.chapter_title('RECOMENDAÇÕES PARA CORREÇÃO', 14)
    
    recomendacoes = []
    
    if analise_pagamentos.get('pagamentos_sem_conta', 0) > 0:
        recomendacoes.append(f"Regularizar {analise_pagamentos['pagamentos_sem_conta']} pagamento(s) sem número de conta")
    
    if analise_pagamentos.get('pagamentos_duplicados', 0) > 0:
        recomendacoes.append(f"Verificar {analise_pagamentos['pagamentos_duplicados']} conta(s) com pagamentos duplicados")
    
    if inconsistencias_pagamentos:
        cont_zerados = sum(1 for inc in inconsistencias_pagamentos if inc['tipo'] == 'VALOR ZERADO')
        cont_negativos = sum(1 for inc in inconsistencias_pagamentos if inc['tipo'] == 'VALOR NEGATIVO')
        
        if cont_zerados > 0:
            recomendacoes.append(f"Investigar {cont_zerados} pagamento(s) com valor zerado")
        
        if cont_negativos > 0:
            recomendacoes.append(f"Verificar {cont_negativos} pagamento(s) com valor negativo")
    
    if comparacao and comparacao.get('total_contas_sem_pagamento', 0) > 0:
        recomendacoes.append(f"Regularizar pagamentos para {comparacao['total_contas_sem_pagamento']} conta(s) sem pagamento")
    
    if not recomendacoes:
        recomendacoes.append("Nenhuma ação corretiva necessária identificada")
    
    pdf.set_font('Arial', '', 11)
    for i, rec in enumerate(recomendacoes, 1):
        pdf.multi_cell(0, 7, f"{i}. {rec}")
    
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
    st.markdown("### Sistema de Análise de Pagamentos e Contas - Versão Corrigida")
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
        for arquivo in uploaded_files:
            nome = arquivo.name.upper()
            
            if any(palavra in nome for palavra in ['PGTO', 'PAGTO', 'PAGAMENTO', 'VALOR']):
                arquivos_pagamentos.append(arquivo)
                st.sidebar.success(f"📊 {arquivo.name} (Pagamentos)")
            elif any(palavra in nome for palavra in ['CADASTRO', 'CONTA', 'ABERTURA', 'REL.CADASTRO']):
                arquivos_contas.append(arquivo)
                st.sidebar.success(f"📋 {arquivo.name} (Contas)")
    
    # Processar arquivos
    dfs_pagamentos = []
    dfs_contas = []
    
    if arquivos_pagamentos:
        with st.spinner("Processando pagamentos..."):
            for arquivo in arquivos_pagamentos:
                df = carregar_planilha(arquivo)
                if not df.empty:
                    dfs_pagamentos.append({
                        'nome': arquivo.name,
                        'dataframe': df
                    })
    
    if arquivos_contas:
        with st.spinner("Processando contas..."):
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
    if st.sidebar.button("🚀 Realizar Análise Precisa", type="primary", use_container_width=True):
        if not df_pagamentos.empty:
            with st.spinner("Realizando análise precisa..."):
                # Análise PRECISA dos pagamentos
                analise_pagamentos = analisar_pagamentos_preciso(df_pagamentos)
                
                # Análise de contas
                if not df_contas.empty:
                    analise_contas = analisar_contas_preciso(df_contas)
                else:
                    analise_contas = {}
                
                # Comparação
                if not df_pagamentos.empty and not df_contas.empty:
                    comparacao = comparar_pagamentos_contas(df_pagamentos, df_contas)
                else:
                    comparacao = {}
                
                # Identificar TODAS as inconsistências
                inconsistencias = identificar_inconsistencias_pagamentos(df_pagamentos)
                
                # Exibir resultados
                st.success("✅ Análise precisa concluída!")
                
                # Métricas PRECISAS
                st.subheader("📊 Métricas Precisas")
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Total de Linhas", 
                             formatar_brasileiro(analise_pagamentos['total_linhas']))
                
                with col2:
                    st.metric("Pagamentos Válidos", 
                             formatar_brasileiro(analise_pagamentos['total_pagamentos_validos']))
                
                with col3:
                    st.metric("Pagamentos sem Conta", 
                             formatar_brasileiro(analise_pagamentos['pagamentos_sem_conta']),
                             delta_color="inverse")
                
                with col4:
                    valor_total = analise_pagamentos['valor_total_correto']
                    st.metric("Valor Total Pago", 
                             formatar_brasileiro(valor_total, 'monetario'))
                
                # Segunda linha
                col5, col6, col7, col8 = st.columns(4)
                
                with col5:
                    if analise_pagamentos['total_pagamentos_validos'] > 0:
                        valor_medio = analise_pagamentos['valor_medio']
                        st.metric("Valor Médio", 
                                 formatar_brasileiro(valor_medio, 'monetario'))
                
                with col6:
                    st.metric("Contas Duplicadas", 
                             formatar_brasileiro(analise_pagamentos['pagamentos_duplicados']),
                             delta_color="inverse")
                
                with col7:
                    if analise_contas:
                        st.metric("Contas Abertas", 
                                 formatar_brasileiro(analise_contas.get('total_contas', 0)))
                
                with col8:
                    if comparacao:
                        st.metric("Contas sem Pagamento", 
                                 formatar_brasileiro(comparacao.get('total_contas_sem_pagamento', 0)),
                                 delta_color="inverse")
                
                # Informações de Detecção
                st.subheader("🔍 Informações de Detecção")
                
                col_det1, col_det2 = st.columns(2)
                
                with col_det1:
                    if analise_pagamentos['coluna_conta_detectada']:
                        st.info(f"**Coluna de Conta:** {analise_pagamentos['coluna_conta_detectada']}")
                    else:
                        st.error("❌ Coluna de conta NÃO detectada!")
                
                with col_det2:
                    if analise_pagamentos['coluna_valor_detectada']:
                        st.info(f"**Coluna de Valor:** {analise_pagamentos['coluna_valor_detectada']}")
                    else:
                        st.error("❌ Coluna de valor NÃO detectada!")
                
                # TABELA DE INCONSISTÊNCIAS DETALHADA
                st.subheader("🚨 Inconsistências que Precisam de Correção")
                
                if inconsistencias:
                    # Converter para DataFrame para exibição
                    dados_tabela = []
                    for inc in inconsistencias:
                        linha_dados = {
                            'Tipo': inc['tipo'],
                            'Linha no Arquivo': inc['linha'],
                            'Descrição': inc['descricao']
                        }
                        
                        # Adicionar detalhes
                        for chave, valor in inc['detalhes'].items():
                            linha_dados[chave.capitalize()] = valor
                        
                        dados_tabela.append(linha_dados)
                    
                    df_inconsistencias = pd.DataFrame(dados_tabela)
                    
                    # Mostrar tabela
                    st.dataframe(df_inconsistencias, use_container_width=True)
                    
                    # Resumo por tipo
                    st.write("**Resumo por Tipo de Inconsistência:**")
                    tipos_contagem = {}
                    for inc in inconsistencias:
                        tipo = inc['tipo']
                        tipos_contagem[tipo] = tipos_contagem.get(tipo, 0) + 1
                    
                    for tipo, contagem in tipos_contagem.items():
                        st.write(f"• **{tipo}:** {contagem} ocorrência(s)")
                else:
                    st.success("✅ Nenhuma inconsistência encontrada!")
                
                # Abas detalhadas
                tab1, tab2, tab3 = st.tabs([
                    "📋 Detalhes dos Dados", 
                    "⚠️ Duplicidades", 
                    "🔍 Comparação Completa"
                ])
                
                with tab1:
                    st.subheader("Dados Processados")
                    
                    if not df_pagamentos.empty:
                        st.write(f"**Pagamentos:** {len(df_pagamentos)} linhas totais")
                        with st.expander("Ver primeiras linhas"):
                            st.dataframe(df_pagamentos.head(20))
                    
                    if not df_contas.empty:
                        st.write(f"**Contas:** {len(df_contas)} registros")
                        with st.expander("Ver primeiras linhas"):
                            st.dataframe(df_contas.head(20))
                
                with tab2:
                    st.subheader("Análise de Duplicidades")
                    
                    if analise_pagamentos['pagamentos_duplicados'] > 0:
                        st.warning(f"🚨 {analise_pagamentos['pagamentos_duplicados']} contas com pagamentos duplicados")
                        
                        if analise_pagamentos.get('pagamentos_duplicados_detalhes'):
                            # Criar DataFrame das duplicidades
                            coluna_conta = analise_pagamentos['coluna_conta_detectada']
                            coluna_valor = analise_pagamentos['coluna_valor_detectada']
                            coluna_nome = detectar_coluna_nome(df_pagamentos)
                            
                            dados_duplicados = []
                            for detalhe in analise_pagamentos['pagamentos_duplicados_detalhes']:
                                linha = {
                                    'Conta': detalhe.get(coluna_conta, '') if coluna_conta else 'N/A'
                                }
                                
                                if coluna_nome and coluna_nome in detalhe:
                                    linha['Nome'] = detalhe[coluna_nome]
                                
                                if coluna_valor and coluna_valor in detalhe:
                                    linha['Valor'] = detalhe[coluna_valor]
                                
                                dados_duplicados.append(linha)
                            
                            if dados_duplicados:
                                df_duplicados = pd.DataFrame(dados_duplicados)
                                st.dataframe(df_duplicados.head(30))
                    else:
                        st.success("✅ Nenhuma duplicidade encontrada")
                
                with tab3:
                    st.subheader("Comparação Pagamentos vs Contas")
                    
                    if comparacao and comparacao.get('total_contas_sem_pagamento', 0) > 0:
                        st.error(f"⚠️ {comparacao['total_contas_sem_pagamento']} contas abertas sem pagamento registrado")
                        
                        # Mostrar detalhes
                        if comparacao.get('detalhes_contas_sem_pagamento'):
                            dados_comparacao = []
                            for detalhe in comparacao['detalhes_contas_sem_pagamento']:
                                dados_comparacao.append({
                                    'Conta': detalhe.get('conta', ''),
                                    'Nome': detalhe.get('nome', 'Não identificado')
                                })
                            
                            df_comparacao = pd.DataFrame(dados_comparacao)
                            st.dataframe(df_comparacao.head(50))
                    else:
                        if not df_contas.empty:
                            st.success("✅ Todas as contas abertas possuem pagamento registrado")
                        else:
                            st.info("ℹ️ Nenhum arquivo de contas carregado para comparação")
                
                # Gerar PDF
                st.subheader("📄 Relatório Completo em PDF")
                
                try:
                    pdf_bytes = gerar_relatorio_pdf_detalhado(
                        mes, ano, analise_pagamentos, analise_contas, comparacao, 
                        inconsistencias, df_pagamentos
                    )
                    
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
                    if inconsistencias:
                        # Exportar inconsistências
                        df_inc_export = pd.DataFrame([
                            {
                                'Tipo': inc['tipo'],
                                'Linha': inc['linha'],
                                'Descrição': inc['descricao'],
                                **inc['detalhes']
                            }
                            for inc in inconsistencias
                        ])
                        csv_inc = df_inc_export.to_csv(index=False, sep=';', encoding='utf-8')
                        st.download_button(
                            label="⚠️ Exportar Inconsistências (CSV)",
                            data=csv_inc,
                            file_name=f"inconsistencias_{mes}_{ano}.csv",
                            mime="text/csv"
                        )
        
        else:
            st.warning("⚠️ Nenhum arquivo de pagamentos válido foi carregado")
    
    else:
        # Tela inicial
        st.info("👈 Carregue seus arquivos e clique em 'Realizar Análise Precisa'")

if __name__ == "__main__":
    main()
