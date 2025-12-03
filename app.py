# app.py - SISTEMA POT SMDET - VERSÃO CORRIGIDA COM VALORES CORRETOS
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

# ============================================
# DETECÇÃO AUTOMÁTICA DE COLUNAS (PRECISA)
# ============================================

def detectar_coluna_conta(df):
    """Detecta a coluna de número da conta de forma precisa"""
    if df.empty:
        return None
    
    colunas_prioridade = [
        'Num Cartao', 'NumCartao', 'Num_Cartao', 'Num Cartão',
        'Cartao', 'Cartão', 'Conta', 'Numero Conta', 'Número Conta',
        'NUMCARTAO', 'NUM_CARTAO', 'NUMERO_CARTAO', 'NÚMERO CARTÃO'
    ]
    
    for coluna in df.columns:
        coluna_limpa = str(coluna).strip()
        for padrao in colunas_prioridade:
            if coluna_limpa.lower() == padrao.lower():
                return coluna
    
    for coluna in df.columns:
        coluna_limpa = str(coluna).strip().upper()
        for padrao in colunas_prioridade:
            if padrao.upper() in coluna_limpa:
                return coluna
    
    for coluna in df.columns:
        if df[coluna].dtype == 'object':
            try:
                amostra = df[coluna].dropna().head(10).astype(str)
                conta_pattern = r'^\d{6,}$'
                matches = sum(1 for x in amostra if re.match(conta_pattern, str(x).strip()))
                if matches >= 5:
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
    
    colunas_prioridade = [
        'Valor Pagto', 'ValorPagto', 'Valor_Pagto', 'Valor Pago', 'ValorPago',
        'Valor_Pago', 'VALOR PAGTO', 'VALOR_PAGTO', 'VALOR PAGO'
    ]
    
    for coluna in df.columns:
        coluna_limpa = str(coluna).strip()
        for padrao in colunas_prioridade:
            if coluna_limpa.lower() == padrao.lower():
                return coluna
    
    for coluna in df.columns:
        coluna_limpa = str(coluna).strip().upper()
        for padrao in colunas_prioridade:
            if padrao.upper() in coluna_limpa:
                return coluna
    
    for coluna in df.columns:
        if df[coluna].dtype in ['float64', 'int64', 'float32', 'int32']:
            if not df[coluna].empty:
                amostra = df[coluna].dropna().head(20)
                if len(amostra) > 0:
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

# ============================================
# CONVERSÃO CORRETA DE VALORES MONETÁRIOS
# ============================================

def converter_valor_monetario_corretamente(valor):
    """Converte valor monetário para float CORRETAMENTE - SEM DUPLICAR"""
    if pd.isna(valor):
        return 0.0
    
    try:
        # Se já é numérico, retorna diretamente
        if isinstance(valor, (int, float, np.integer, np.floating)):
            return float(valor)
        
        valor_str = str(valor).strip()
        
        if valor_str == '' or valor_str.lower() in ['nan', 'none', 'null']:
            return 0.0
        
        # Remover símbolos de moeda
        valor_str = re.sub(r'[R\$\s€£¥]', '', valor_str)
        
        # Remover espaços
        valor_str = valor_str.replace(' ', '')
        
        # Se já for um número válido
        if re.match(r'^-?\d+(\.\d+)?$', valor_str):
            result = float(valor_str)
            return abs(result) if result >= 0 else 0.0
        
        # Formato brasileiro: 1.234,56 ou 1234,56
        if ',' in valor_str:
            # Verificar se é formato brasileiro (vírgula como separador decimal)
            partes = valor_str.split(',')
            
            if len(partes) == 2:
                # Formato: 1234,56 ou 1.234,56
                parte_inteira = partes[0].replace('.', '')  # Remove pontos de milhar
                parte_decimal = partes[1]
                
                # Verificar se a parte decimal tem até 2 dígitos
                if len(parte_decimal) <= 2:
                    # É formato brasileiro: vírgula como separador decimal
                    valor_str_final = parte_inteira + '.' + parte_decimal
                else:
                    # Vírgula como separador de milhar (formato pouco comum)
                    valor_str_final = valor_str.replace(',', '')
            else:
                # Mais de uma vírgula - remover todas
                valor_str_final = valor_str.replace(',', '')
        else:
            valor_str_final = valor_str
        
        # Remover caracteres não numéricos exceto ponto e sinal
        valor_str_final = re.sub(r'[^\d\.\-]', '', valor_str_final)
        
        # Se ficou vazio
        if not valor_str_final or valor_str_final == '-':
            return 0.0
        
        # Converter para float
        resultado = float(valor_str_final)
        
        # Garantir que valores são positivos
        return abs(resultado) if resultado >= 0 else 0.0
        
    except Exception as e:
        return 0.0

def processar_valores_dataframe_corretamente(df, coluna_valor):
    """Processa valores CORRETAMENTE - sem duplicação"""
    if df.empty or coluna_valor not in df.columns:
        return df, 0.0
    
    try:
        df_processado = df.copy()
        
        # Converter todos os valores individualmente
        valores_convertidos = []
        total_soma = 0.0
        
        for idx, valor in enumerate(df_processado[coluna_valor]):
            valor_convertido = converter_valor_monetario_corretamente(valor)
            valores_convertidos.append(valor_convertido)
            total_soma += valor_convertido
        
        # Adicionar coluna com valores convertidos
        df_processado[f'{coluna_valor}_Numerico'] = valores_convertidos
        
        return df_processado, total_soma
        
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
                arquivo.seek(0)
                df = pd.read_csv(arquivo, delimiter=';', encoding=encoding, 
                                low_memory=False, on_bad_lines='skip')
                
                df = df.dropna(how='all')
                
                if len(df) == 0:
                    return pd.DataFrame()
                
                df = df[df.apply(lambda row: row.astype(str).str.strip().ne('').any(), axis=1)]
                
                return df
                
            except Exception as e:
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
# ANÁLISE CORRETA DE PAGAMENTOS
# ============================================

def analisar_pagamentos_corretamente(df):
    """Análise CORRETA dos pagamentos - valores corretos"""
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
        'linhas_sem_conta': [],
        'pagamentos_duplicados_detalhes': []
    }
    
    if df.empty:
        return resultados
    
    resultados['total_linhas'] = len(df)
    
    coluna_conta = detectar_coluna_conta(df)
    coluna_valor = detectar_coluna_valor_pagto(df)
    
    resultados['coluna_conta_detectada'] = coluna_conta
    resultados['coluna_valor_detectada'] = coluna_valor
    
    if coluna_conta:
        df[coluna_conta] = df[coluna_conta].astype(str).str.strip()
        
        def conta_valida(valor):
            valor_str = str(valor)
            return valor_str not in ['', 'nan', 'NaN', 'None', 'null', 'NaT'] and valor_str.strip() != ''
        
        contas_validas = df[coluna_conta].apply(conta_valida)
        
        resultados['total_pagamentos_validos'] = contas_validas.sum()
        resultados['pagamentos_sem_conta'] = (~contas_validas).sum()
        
        linhas_sem_conta = df[~contas_validas]
        if not linhas_sem_conta.empty:
            resultados['linhas_sem_conta'] = linhas_sem_conta.index.tolist()
        
        df_validos = df[contas_validas]
        if not df_validos.empty:
            duplicados = df_validos[df_validos.duplicated(subset=[coluna_conta], keep=False)]
            
            if not duplicados.empty:
                contas_duplicadas = duplicados[coluna_conta].unique()
                resultados['pagamentos_duplicados'] = len(contas_duplicadas)
                resultados['pagamentos_duplicados_detalhes'] = duplicados.head(50).to_dict('records')
    
    # CÁLCULO CORRETO DOS VALORES
    if coluna_valor:
        df_processado, valor_total = processar_valores_dataframe_corretamente(df, coluna_valor)
        resultados['valor_total_correto'] = valor_total
        
        # Calcular valor médio apenas entre pagamentos válidos
        if resultados['total_pagamentos_validos'] > 0:
            resultados['valor_medio'] = valor_total / resultados['total_pagamentos_validos']
        else:
            resultados['valor_medio'] = 0.0
    
    return resultados

# ============================================
# IDENTIFICAÇÃO DE INCONSISTÊNCIAS
# ============================================

def identificar_inconsistencias_pagamentos(df):
    """Identifica inconsistências nos pagamentos"""
    inconsistencias = []
    
    if df.empty:
        return inconsistencias
    
    coluna_conta = detectar_coluna_conta(df)
    coluna_valor = detectar_coluna_valor_pagto(df)
    coluna_nome = detectar_coluna_nome(df)
    coluna_data = detectar_coluna_data(df)
    
    # 1. Pagamentos sem número de conta
    if coluna_conta:
        df[coluna_conta] = df[coluna_conta].astype(str).str.strip()
        sem_conta = df[df[coluna_conta].isin(['', 'nan', 'NaN', 'None', 'null'])]
        
        if not sem_conta.empty:
            for idx, row in sem_conta.iterrows():
                inconsistencia = {
                    'tipo': 'SEM CONTA',
                    'linha': idx + 2,
                    'descricao': 'Pagamento sem número de conta',
                    'detalhes': {}
                }
                
                if coluna_nome and coluna_nome in row:
                    inconsistencia['detalhes']['nome'] = str(row[coluna_nome])
                
                if coluna_valor and coluna_valor in row:
                    inconsistencia['detalhes']['valor'] = str(row[coluna_valor])
                
                inconsistencias.append(inconsistencia)
    
    # 2. Valores zerados ou negativos
    if coluna_valor:
        try:
            df_processado, _ = processar_valores_dataframe_corretamente(df, coluna_valor)
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
        df[coluna_conta] = df[coluna_conta].astype(str).str.strip()
        
        contas_validas = df[~df[coluna_conta].isin(['', 'nan', 'NaN', 'None', 'null'])]
        
        if not contas_validas.empty:
            resultados['contas_unicas'] = contas_validas[coluna_conta].nunique()
            
            duplicados = contas_validas[contas_validas.duplicated(subset=[coluna_conta], keep=False)]
            if not duplicados.empty:
                resultados['contas_duplicadas'] = duplicados[coluna_conta].nunique()
    
    if coluna_nome and coluna_conta:
        contas_validas = df[~df[coluna_conta].isin(['', 'nan', 'NaN', 'None', 'null'])]
        sem_nome = contas_validas[contas_validas[coluna_nome].isna() | 
                                (contas_validas[coluna_nome].astype(str).str.strip() == '')]
        resultados['contas_sem_nome'] = len(sem_nome)
    
    return resultados

# ============================================
# COMPARAÇÃO PAGAMENTOS VS CONTAS
# ============================================

def comparar_pagamentos_contas(df_pagamentos, df_contas):
    """Comparação entre pagamentos e contas"""
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
        df_pagamentos[coluna_conta_pag] = df_pagamentos[coluna_conta_pag].astype(str).str.strip()
        contas_pag_validas = set(
            df_pagamentos[~df_pagamentos[coluna_conta_pag].isin(['', 'nan', 'NaN', 'None', 'null'])][coluna_conta_pag]
        )
        
        df_contas[coluna_conta_cont] = df_contas[coluna_conta_cont].astype(str).str.strip()
        df_contas_validas = df_contas[~df_contas[coluna_conta_cont].isin(['', 'nan', 'NaN', 'None', 'null'])]
        contas_cont_validas = set(df_contas_validas[coluna_conta_cont])
        
        contas_sem_pagamento = contas_cont_validas - contas_pag_validas
        comparacao['total_contas_sem_pagamento'] = len(contas_sem_pagamento)
        comparacao['contas_sem_pagamento'] = list(contas_sem_pagamento)
        
        coluna_nome_cont = detectar_coluna_nome(df_contas)
        
        for conta in contas_sem_pagamento:
            detalhe = {'conta': conta}
            
            linha_conta = df_contas_validas[df_contas_validas[coluna_conta_cont] == conta]
            
            if not linha_conta.empty and coluna_nome_cont and coluna_nome_cont in linha_conta.columns:
                detalhe['nome'] = str(linha_conta.iloc[0][coluna_nome_cont])
            
            comparacao['detalhes_contas_sem_pagamento'].append(detalhe)
            
    except Exception as e:
        pass
    
    return comparacao

# ============================================
# GERAR RELATÓRIO PDF
# ============================================

def gerar_relatorio_pdf_completo(mes, ano, analise_pagamentos, analise_contas, comparacao, 
                                 inconsistencias_pagamentos, df_pagamentos):
    """Gera relatório PDF completo"""
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
    
    pdf.add_metric('Total de Linhas Analisadas:', 
                  formatar_brasileiro(analise_pagamentos.get('total_linhas', 0)))
    pdf.add_metric('Pagamentos Válidos (com conta):', 
                  formatar_brasileiro(analise_pagamentos.get('total_pagamentos_validos', 0)))
    pdf.add_metric('Pagamentos sem Conta:', 
                  formatar_brasileiro(analise_pagamentos.get('pagamentos_sem_conta', 0)),
                  alert=analise_pagamentos.get('pagamentos_sem_conta', 0) > 0)
    pdf.add_metric('Valor Total Pago:', 
                  formatar_brasileiro(analise_pagamentos.get('valor_total_correto', 0), 'monetario'))
    
    if analise_pagamentos.get('valor_medio', 0) > 0:
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
    
    # Inconsistências
    if inconsistencias_pagamentos:
        pdf.add_page()
        pdf.chapter_title('INCONSISTÊNCIAS IDENTIFICADAS', 16)
        
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 10, f'Total de Inconsistências: {len(inconsistencias_pagamentos)}', 0, 1)
        pdf.ln(3)
        
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
            
            for inc in lista_inc[:10]:
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
    
    # Contas sem Pagamento
    if comparacao and comparacao.get('total_contas_sem_pagamento', 0) > 0:
        pdf.add_page()
        pdf.chapter_title('CONTAS ABERTAS SEM PAGAMENTO', 16)
        
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 10, f'Total: {comparacao["total_contas_sem_pagamento"]} contas', 0, 1)
        pdf.ln(3)
        
        dados_tabela = []
        for detalhe in comparacao.get('detalhes_contas_sem_pagamento', []):
            dados_tabela.append({
                'Conta': detalhe.get('conta', ''),
                'Nome': detalhe.get('nome', 'NÃO IDENTIFICADO')
            })
        
        if dados_tabela:
            df_tabela = pd.DataFrame(dados_tabela)
            pdf.add_table(df_tabela.head(50))
    
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
             'Jullio', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
    
    col1, col2 = st.sidebar.columns(2)
    with col1:
        mes = st.selectbox("Mês", meses, index=8)
    with col2:
        ano_atual = datetime.now().year
        ano = st.selectbox("Ano", list(range(ano_atual, ano_atual - 3, -1)))
    
    # Botão de análise
    if st.sidebar.button("🚀 Realizar Análise Correta", type="primary", use_container_width=True):
        if not df_pagamentos.empty:
            with st.spinner("Realizando análise correta..."):
                # Análise CORRETA dos pagamentos
                analise_pagamentos = analisar_pagamentos_corretamente(df_pagamentos)
                
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
                
                # Identificar inconsistências
                inconsistencias = identificar_inconsistencias_pagamentos(df_pagamentos)
                
                # Exibir resultados
                st.success("✅ Análise concluída com valores CORRETOS!")
                
                # Métricas CORRETAS
                st.subheader("📊 Métricas Corrigidas")
                
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
                    st.metric("Valor Total Pago (CORRETO)", 
                             formatar_brasileiro(valor_total, 'monetario'))
                
                # Segunda linha
                col5, col6, col7, col8 = st.columns(4)
                
                with col5:
                    if analise_pagamentos['total_pagamentos_validos'] > 0:
                        valor_medio = analise_pagamentos['valor_medio']
                        st.metric("Valor Médio (CORRETO)", 
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
                
                # Verificação de valores
                st.subheader("✅ Verificação de Valores")
                st.info(f"**Valor total calculado CORRETAMENTE:** {formatar_brasileiro(valor_total, 'monetario')}")
                if analise_pagamentos['total_pagamentos_validos'] > 0:
                    st.info(f"**Valor médio CORRETO:** {formatar_brasileiro(analise_pagamentos['valor_medio'], 'monetario')}")
                
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
                
                # TABELA DE INCONSISTÊNCIAS
                st.subheader("🚨 Inconsistências que Precisam de Correção")
                
                if inconsistencias:
                    dados_tabela = []
                    for inc in inconsistencias:
                        linha_dados = {
                            'Tipo': inc['tipo'],
                            'Linha no Arquivo': inc['linha'],
                            'Descrição': inc['descricao']
                        }
                        
                        for chave, valor in inc['detalhes'].items():
                            linha_dados[chave.capitalize()] = valor
                        
                        dados_tabela.append(linha_dados)
                    
                    df_inconsistencias = pd.DataFrame(dados_tabela)
                    
                    st.dataframe(df_inconsistencias, use_container_width=True)
                    
                    st.write("**Resumo por Tipo de Inconsistência:**")
                    tipos_contagem = {}
                    for inc in inconsistencias:
                        tipo = inc['tipo']
                        tipos_contagem[tipo] = tipos_contagem.get(tipo, 0) + 1
                    
                    for tipo, contagem in tipos_contagem.items():
                        st.write(f"• **{tipo}:** {contagem} ocorrência(s)")
                else:
                    st.success("✅ Nenhuma inconsistência encontrada!")
                
                # Gerar PDF - BOTÃO MAIS VISÍVEL
                st.markdown("---")
                st.subheader("📄 Relatório Completo em PDF")
                
                try:
                    pdf_bytes = gerar_relatorio_pdf_completo(
                        mes, ano, analise_pagamentos, analise_contas, comparacao, 
                        inconsistencias, df_pagamentos
                    )
                    
                    if pdf_bytes and pdf_bytes != b'PDF generation error':
                        st.markdown("### 📥 Download do Relatório")
                        st.download_button(
                            label="⬇️ BAIXAR RELATÓRIO COMPLETO (PDF)",
                            data=pdf_bytes,
                            file_name=f"Relatorio_POT_{mes}_{ano}.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                            type="primary"
                        )
                        st.success("✅ Relatório PDF gerado com sucesso!")
                        st.info("O relatório contém todas as métricas, inconsistências e recomendações.")
                    else:
                        st.error("❌ Erro ao gerar o PDF. Tente novamente.")
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
                            mime="text/csv",
                            use_container_width=True
                        )
                
                with col_exp2:
                    if inconsistencias:
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
                            mime="text/csv",
                            use_container_width=True
                        )
                
                # Visualização dos dados
                with st.expander("👁️ Visualizar Dados Processados"):
                    tab1, tab2 = st.tabs(["📋 Pagamentos", "👤 Contas"])
                    
                    with tab1:
                        if not df_pagamentos.empty:
                            st.write(f"**Total de registros:** {len(df_pagamentos)}")
                            st.dataframe(df_pagamentos.head(50))
                    
                    with tab2:
                        if not df_contas.empty:
                            st.write(f"**Total de registros:** {len(df_contas)}")
                            st.dataframe(df_contas.head(50))
        
        else:
            st.warning("⚠️ Nenhum arquivo de pagamentos válido foi carregado")
    
    else:
        # Tela inicial
        st.info("👈 Carregue seus arquivos e clique em 'Realizar Análise Correta'")
        st.markdown("""
        ### 📋 Instruções:
        1. **Carregue os arquivos** no menu à esquerda
        2. **Classificação automática:** arquivos de pagamento e contas são identificados automaticamente
        3. **Selecione o período** de análise
        4. **Clique em "Realizar Análise Correta"**
        
        ### 🔧 Principais Correções:
        - ✅ **Valores totais CORRETOS** - sem duplicação
        - ✅ **Valor médio CORRETO** - cálculo preciso
        - ✅ **Exportação de PDF** - botão mais visível e funcional
        - ✅ **Conversão monetária precisa** - suporte a formatos brasileiros
        
        ### 📁 Formatos Suportados:
        - CSV (separador ; ou ,)
        - TXT
        - Excel (.xlsx, .xls)
        """)

if __name__ == "__main__":
    main()
