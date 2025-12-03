# app.py - SISTEMA POT SMDET COMPLETO COM TRATAMENTO DE ARQUIVOS VAZIOS
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
        # Usar fonte padrão para evitar problemas
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
    # Substituir caracteres problemáticos
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
        'NumeroCartao', 'NrCartao', 'NRCartao', 'Numero do Cartao'
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
        'NOME_BENEFICIARIO', 'NOME DO BENEFICIARIO'
    ]
    
    for coluna in df.columns:
        coluna_limpa = str(coluna).strip().upper()
        for padrao in colunas_possiveis:
            if padrao.upper() in coluna_limpa:
                return coluna
    
    return None

def detectar_coluna_valor(df):
    if df.empty:
        return None
    
    colunas_prioridade = [
        'Valor', 'Valor Pago', 'ValorPagto', 'Valor_Pagto', 'VALOR',
        'VALOR PAGO', 'VALOR_PAGO', 'VALOR PGTO', 'VLR_PAGO',
        'Valor Total', 'ValorTotal', 'Valor_Total', 'VALOR TOTAL'
    ]
    
    for coluna in df.columns:
        coluna_limpa = str(coluna).strip().upper()
        for padrao in colunas_prioridade:
            if padrao.upper() in coluna_limpa:
                return coluna
    
    # Procurar por colunas numéricas
    for coluna in df.columns:
        if df[coluna].dtype in ['float64', 'int64', 'float32', 'int32']:
            return coluna
    
    return None

def detectar_coluna_data(df):
    if df.empty:
        return []
    
    colunas_data = [
        'Data', 'DataPagto', 'Data_Pagto', 'DtLote', 'DATA',
        'DATA PGTO', 'DT_LOTE', 'DATALOTE', 'DataPagamento',
        'Data Pagto', 'Data_Pagamento'
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
# PROCESSAMENTO DE DADOS COM TRATAMENTO DE ERROS
# ============================================

def processar_valor_seguro(valor):
    """Processa valores monetários com tratamento de erros"""
    if pd.isna(valor):
        return 0.0
    
    try:
        if isinstance(valor, (int, float, np.integer, np.floating)):
            return float(valor)
        
        valor_str = str(valor).strip()
        
        if valor_str == '':
            return 0.0
        
        # Remover símbolos de moeda e espaços
        valor_str = re.sub(r'[R\$\s€£¥]', '', valor_str)
        
        # Verificar se tem formato brasileiro (1.234,56)
        if ',' in valor_str and '.' in valor_str:
            # Formato 1.234,56 -> remover pontos de milhar
            valor_str = valor_str.replace('.', '').replace(',', '.')
        elif ',' in valor_str:
            # Formato 1234,56
            valor_str = valor_str.replace(',', '.')
        
        # Remover caracteres não numéricos exceto ponto e sinal negativo
        valor_str = re.sub(r'[^\d\.\-]', '', valor_str)
        
        # Se a string ficou vazia, retornar 0
        if not valor_str:
            return 0.0
        
        return float(valor_str)
    except Exception as e:
        return 0.0

def converter_coluna_valor(df, coluna_valor):
    """Converte coluna de valor para numérico de forma segura"""
    if coluna_valor and coluna_valor in df.columns:
        try:
            # Criar cópia para não modificar o original
            df_copy = df.copy()
            
            # Tentar converter para numérico
            df_copy[coluna_valor] = pd.to_numeric(df_copy[coluna_valor], errors='coerce')
            
            # Preencher valores NaN com 0
            df_copy[coluna_valor] = df_copy[coluna_valor].fillna(0)
            
            return df_copy
        except:
            return df
    return df

# ============================================
# CARREGAMENTO DE PLANILHAS COM TRATAMENTO DE ARQUIVOS VAZIOS
# ============================================

def carregar_planilha(arquivo):
    try:
        nome_arquivo = arquivo.name
        
        # Para arquivos CSV e TXT
        if nome_arquivo.endswith('.csv') or nome_arquivo.endswith('.txt'):
            encoding = detectar_encoding(arquivo)
            
            # Tentar ler o arquivo
            try:
                arquivo.seek(0)
                df = pd.read_csv(arquivo, delimiter=';', encoding=encoding, 
                                low_memory=False, on_bad_lines='skip')
                
                # Verificar se o arquivo está vazio ou só tem cabeçalho
                if len(df) == 0:
                    st.warning(f"Arquivo {nome_arquivo} está vazio (sem dados)")
                    return pd.DataFrame()
                
                # Verificar se todas as linhas estão vazias
                linhas_validas = df.apply(lambda row: row.astype(str).str.strip().ne('').any(), axis=1).sum()
                if linhas_validas == 0:
                    st.warning(f"Arquivo {nome_arquivo} contém apenas linhas vazias")
                    return pd.DataFrame()
                
                return df
                
            except Exception as e:
                # Tentar com delimitador diferente
                try:
                    arquivo.seek(0)
                    df = pd.read_csv(arquivo, delimiter=',', encoding=encoding,
                                    low_memory=False, on_bad_lines='skip')
                    
                    if len(df) > 0:
                        return df
                except:
                    pass
                
                # Última tentativa com engine python
                try:
                    arquivo.seek(0)
                    df = pd.read_csv(arquivo, sep=None, engine='python', encoding=encoding,
                                    low_memory=False, on_bad_lines='skip')
                    return df
                except:
                    st.error(f"Erro ao ler arquivo {nome_arquivo}: Formato não suportado")
                    return pd.DataFrame()
        
        # Para arquivos Excel
        elif nome_arquivo.endswith(('.xlsx', '.xls')):
            try:
                df = pd.read_excel(arquivo)
                if len(df) == 0:
                    st.warning(f"Arquivo {nome_arquivo} está vazio (sem dados)")
                return df
            except Exception as e:
                st.error(f"Erro ao ler arquivo Excel {nome_arquivo}: {str(e)}")
                return pd.DataFrame()
        
        return pd.DataFrame()
        
    except Exception as e:
        st.error(f"Erro ao processar {arquivo.name}: {str(e)}")
        return pd.DataFrame()

# ============================================
# ANÁLISE DE PROBLEMAS CRÍTICOS (CORRIGIDA)
# ============================================

def analisar_problemas_criticos(df, tipo):
    """Analisa problemas críticos nos dados com tratamento de erros"""
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
                # Converter para string e limpar
                df[coluna_conta] = df[coluna_conta].astype(str).str.strip()
                contas_vazias = df[coluna_conta].isin(['', 'nan', 'NaN', 'None', 'null']).sum()
                if contas_vazias > 0:
                    problemas.append(f"{contas_vazias} registros sem número de conta")
            except:
                problemas.append("Erro ao analisar coluna de conta")
        
        # 2. Valores zerados ou negativos (COM TRATAMENTO DE ERROS)
        if coluna_valor and coluna_valor in df.columns:
            try:
                # Primeiro converter para numérico
                df_valor = converter_coluna_valor(df, coluna_valor)
                
                if not df_valor.empty and coluna_valor in df_valor.columns:
                    # Agora podemos fazer comparações numéricas
                    valores_zerados = df_valor[df_valor[coluna_valor] == 0].shape[0]
                    valores_negativos = df_valor[df_valor[coluna_valor] < 0].shape[0]
                    
                    if valores_zerados > 0:
                        problemas.append(f"{valores_zerados} pagamentos com valor zerado")
                    if valores_negativos > 0:
                        problemas.append(f"{valores_negativos} pagamentos com valor negativo")
            except Exception as e:
                problemas.append(f"Erro ao analisar valores: {str(e)}")
        
        # 3. Nomes em branco
        if coluna_nome and coluna_nome in df.columns:
            try:
                df[coluna_nome] = df[coluna_nome].astype(str).str.strip()
                nomes_vazios = df[coluna_nome].isin(['', 'nan', 'NaN', 'None', 'null']).sum()
                if nomes_vazios > 0:
                    problemas.append(f"{nomes_vazios} registros sem nome do beneficiário")
            except:
                problemas.append("Erro ao analisar coluna de nome")
    
    elif tipo == 'contas':
        coluna_conta = detectar_coluna_conta(df)
        coluna_nome = detectar_coluna_nome(df)
        coluna_cpf = detectar_coluna_cpf(df)
        
        # 1. Contas duplicadas
        if coluna_conta and coluna_conta in df.columns:
            try:
                # Limpar dados antes de verificar duplicatas
                df[coluna_conta] = df[coluna_conta].astype(str).str.strip()
                df_sem_vazios = df[~df[coluna_conta].isin(['', 'nan', 'NaN', 'None', 'null'])]
                
                if not df_sem_vazios.empty:
                    duplicados = df_sem_vazios[df_sem_vazios.duplicated(subset=[coluna_conta], keep=False)]
                    if not duplicados.empty:
                        problemas.append(f"{duplicados[coluna_conta].nunique()} contas duplicadas")
            except:
                problemas.append("Erro ao verificar contas duplicadas")
        
        # 2. Nomes em branco
        if coluna_nome and coluna_nome in df.columns:
            try:
                df[coluna_nome] = df[coluna_nome].astype(str).str.strip()
                nomes_vazios = df[coluna_nome].isin(['', 'nan', 'NaN', 'None', 'null']).sum()
                if nomes_vazios > 0:
                    problemas.append(f"{nomes_vazios} registros sem nome")
            except:
                problemas.append("Erro ao analisar coluna de nome")
        
        # 3. CPFs inválidos
        if coluna_cpf and coluna_cpf in df.columns:
            try:
                # Limpar CPFs
                df['CPF_Limpo'] = df[coluna_cpf].astype(str).apply(lambda x: re.sub(r'[^\d]', '', str(x)))
                cpf_invalidos = df[~df['CPF_Limpo'].str.match(r'^\d{11}$')].shape[0]
                if cpf_invalidos > 0:
                    problemas.append(f"{cpf_invalidos} CPFs com formato inválido")
            except:
                pass
    
    return problemas

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
    
    if metrics_pagamentos:
        pdf.add_metric('Total de Pagamentos:', formatar_brasileiro(metrics_pagamentos.get('total_registros', 0)))
        pdf.add_metric('Valor Total Pago:', formatar_brasileiro(metrics_pagamentos.get('valor_total', 0), 'monetario'))
        pdf.add_metric('Pagamentos Validos:', formatar_brasileiro(metrics_pagamentos.get('registros_validos', 0)))
        pdf.add_metric('Pagamentos Duplicados:', formatar_brasileiro(metrics_pagamentos.get('pagamentos_duplicados', 0)), 
                      alert=metrics_pagamentos.get('pagamentos_duplicados', 0) > 0)
    
    if metrics_contas:
        pdf.add_metric('Contas Abertas:', formatar_brasileiro(metrics_contas.get('total_contas', 0)))
    
    if comparacao:
        pdf.add_metric('Contas sem Pagamento:', formatar_brasileiro(comparacao.get('total_contas_sem_pagamento', 0)),
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
    if not df_pagamentos.empty:
        pdf.add_page()
        pdf.chapter_title('ANALISE DETALHADA DE PAGAMENTOS', 16)
        
        # Estatísticas
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 10, 'Estatisticas:', 0, 1)
        pdf.ln(3)
        
        coluna_valor = detectar_coluna_valor(df_pagamentos)
        if coluna_valor and coluna_valor in df_pagamentos.columns:
            try:
                # Converter para numérico primeiro
                df_temp = converter_coluna_valor(df_pagamentos, coluna_valor)
                estatisticas = df_temp[coluna_valor].describe()
                
                pdf.set_font('Arial', '', 11)
                pdf.add_metric('Media:', formatar_brasileiro(estatisticas.get('mean', 0), 'monetario'))
                pdf.add_metric('Mediana:', formatar_brasileiro(estatisticas.get('50%', 0), 'monetario'))
                pdf.add_metric('Minimo:', formatar_brasileiro(estatisticas.get('min', 0), 'monetario'))
                pdf.add_metric('Maximo:', formatar_brasileiro(estatisticas.get('max', 0), 'monetario'))
                if 'std' in estatisticas:
                    pdf.add_metric('Desvio Padrao:', formatar_brasileiro(estatisticas['std'], 'monetario'))
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
                    contas_sem_pagamento = df_contas[
                        df_contas[coluna_conta].astype(str).isin(
                            [str(c) for c in comparacao.get('contas_sem_pagamento', [])]
                        )
                    ][[coluna_conta, coluna_nome]].head(20)
                    
                    if not contas_sem_pagamento.empty:
                        # Limpar texto
                        for col in [coluna_conta, coluna_nome]:
                            contas_sem_pagamento[col] = contas_sem_pagamento[col].apply(limpar_texto_para_pdf)
                        
                        pdf.add_table(contas_sem_pagamento)
                except:
                    pass
    
    # Recomendações
    pdf.add_page()
    pdf.chapter_title('RECOMENDACOES', 14)
    
    recomendacoes = []
    
    if problemas_pagamentos:
        if any("zerado" in p for p in problemas_pagamentos):
            recomendacoes.append("Regularizar pagamentos com valores zerados")
        if any("negativo" in p for p in problemas_pagamentos):
            recomendacoes.append("Verificar pagamentos com valores negativos")
        if any("sem nome" in p for p in problemas_pagamentos):
            recomendacoes.append("Completar informacoes de beneficiarios sem nome")
    
    if problemas_contas:
        if any("duplicadas" in p for p in problemas_contas):
            recomendacoes.append("Verificar e corrigir contas duplicadas")
        if any("CPFs" in p for p in problemas_contas):
            recomendacoes.append("Validar CPFs com formato invalido")
    
    if comparacao and comparacao.get('total_contas_sem_pagamento', 0) > 0:
        recomendacoes.append(f"Regularizar pagamentos para {comparacao['total_contas_sem_pagamento']} contas sem pagamento")
    
    if not recomendacoes:
        recomendacoes.append("Nenhuma acao corretiva necessaria identificada")
    
    pdf.set_font('Arial', '', 11)
    for i, rec in enumerate(recomendacoes[:10], 1):
        rec_limpa = limpar_texto_para_pdf(rec)
        pdf.multi_cell(0, 7, f"{i}. {rec_limpa}")
    
    # Gerar PDF em bytes
    try:
        pdf_output = pdf.output(dest='S')
        return pdf_output.encode('latin-1', 'replace')
    except:
        try:
            pdf_output = pdf.output(dest='S')
            return pdf_output.encode('utf-8')
        except Exception as e:
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
    
    # Upload múltiplo
    uploaded_files = st.sidebar.file_uploader(
        "Carregue suas planilhas (CSV, TXT, Excel)",
        type=['csv', 'txt', 'xlsx', 'xls'],
        accept_multiple_files=True,
        help="Arraste ou selecione arquivos"
    )
    
    # Classificação automática de arquivos
    arquivos_pagamentos = []
    arquivos_contas = []
    
    if uploaded_files:
        with st.spinner("Analisando arquivos..."):
            for arquivo in uploaded_files:
                nome = arquivo.name.upper()
                
                # Classificar por nome do arquivo
                if any(palavra in nome for palavra in ['PGTO', 'PAGTO', 'PAGAMENTO', 'PAGTO', 'VALOR', 'PGTO.', 'PAGTO.']):
                    arquivos_pagamentos.append(arquivo)
                    st.sidebar.success(f"📊 {arquivo.name} (Pagamentos)")
                elif any(palavra in nome for palavra in ['CADASTRO', 'CONTA', 'ABERTURA', 'REL.CADASTRO', 'CADASTRO.']):
                    arquivos_contas.append(arquivo)
                    st.sidebar.success(f"📋 {arquivo.name} (Contas)")
                else:
                    # Tentar classificar pelo conteúdo
                    try:
                        df_temp = carregar_planilha(arquivo)
                        if not df_temp.empty and len(df_temp) > 0:
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
                        # Se não conseguir classificar, colocar como pagamentos por padrão
                        arquivos_pagamentos.append(arquivo)
                        st.sidebar.warning(f"⚠️ {arquivo.name} (Não classificado - tratado como Pagamentos)")
    
    # Processar arquivos
    dfs_pagamentos = []
    dfs_contas = []
    
    if arquivos_pagamentos:
        with st.spinner("Processando arquivos de pagamentos..."):
            for arquivo in arquivos_pagamentos:
                df = carregar_planilha(arquivo)
                if not df.empty and len(df) > 0:
                    dfs_pagamentos.append({
                        'nome': arquivo.name,
                        'dataframe': df
                    })
                    st.sidebar.info(f"✓ {arquivo.name}: {len(df)} registros")
                else:
                    st.sidebar.warning(f"✗ {arquivo.name}: Arquivo vazio ou inválido")
    
    if arquivos_contas:
        with st.spinner("Processando arquivos de contas..."):
            for arquivo in arquivos_contas:
                df = carregar_planilha(arquivo)
                if not df.empty and len(df) > 0:
                    dfs_contas.append({
                        'nome': arquivo.name,
                        'dataframe': df
                    })
                    st.sidebar.info(f"✓ {arquivo.name}: {len(df)} registros")
                else:
                    st.sidebar.warning(f"✗ {arquivo.name}: Arquivo vazio ou inválido")
    
    # Combinar dados
    df_pagamentos = pd.DataFrame()
    if dfs_pagamentos:
        df_pagamentos = pd.concat([d['dataframe'] for d in dfs_pagamentos], ignore_index=True)
        st.info(f"📊 Total de registros de pagamentos: {len(df_pagamentos)}")
    
    df_contas = pd.DataFrame()
    if dfs_contas:
        df_contas = pd.concat([d['dataframe'] for d in dfs_contas], ignore_index=True)
        st.info(f"📋 Total de registros de contas: {len(df_contas)}")
    
    # Configuração do período
    st.sidebar.markdown("---")
    st.sidebar.header("📅 Período de Análise")
    
    meses = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
             'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
    
    col1, col2 = st.sidebar.columns(2)
    with col1:
        mes = st.selectbox("Mês", meses, index=8)  # Setembro como padrão
    with col2:
        ano_atual = datetime.now().year
        ano = st.selectbox("Ano", list(range(ano_atual, ano_atual - 3, -1)))
    
    # Botão de análise
    if st.sidebar.button("🚀 Realizar Análise Completa", type="primary", use_container_width=True):
        if not df_pagamentos.empty or not df_contas.empty:
            with st.spinner("Realizando análise completa..."):
                # Análises básicas
                metrics_pagamentos = {}
                metrics_contas = {}
                comparacao = {}
                
                if not df_pagamentos.empty:
                    # Métricas de pagamentos
                    coluna_conta = detectar_coluna_conta(df_pagamentos)
                    coluna_valor = detectar_coluna_valor(df_pagamentos)
                    
                    metrics_pagamentos['total_registros'] = len(df_pagamentos)
                    
                    if coluna_conta and coluna_conta in df_pagamentos.columns:
                        # Converter para string e limpar
                        df_pagamentos[coluna_conta] = df_pagamentos[coluna_conta].astype(str).str.strip()
                        validos = ~df_pagamentos[coluna_conta].isin(['', 'nan', 'NaN', 'None', 'null'])
                        metrics_pagamentos['registros_validos'] = validos.sum()
                        
                        # Duplicados (apenas entre registros válidos)
                        df_validos = df_pagamentos[validos]
                        if not df_validos.empty:
                            duplicados = df_validos[df_validos.duplicated(subset=[coluna_conta], keep=False)]
                            metrics_pagamentos['pagamentos_duplicados'] = duplicados[coluna_conta].nunique() if not duplicados.empty else 0
                    
                    if coluna_valor and coluna_valor in df_pagamentos.columns:
                        # Converter coluna de valor para numérico
                        df_pagamentos_num = converter_coluna_valor(df_pagamentos, coluna_valor)
                        metrics_pagamentos['valor_total'] = df_pagamentos_num[coluna_valor].sum()
                
                if not df_contas.empty:
                    metrics_contas['total_contas'] = len(df_contas)
                    coluna_conta_cont = detectar_coluna_conta(df_contas)
                    if coluna_conta_cont and coluna_conta_cont in df_contas.columns:
                        df_contas[coluna_conta_cont] = df_contas[coluna_conta_cont].astype(str).str.strip()
                        validos = ~df_contas[coluna_conta_cont].isin(['', 'nan', 'NaN', 'None', 'null'])
                        df_validos = df_contas[validos]
                        metrics_contas['contas_unicas'] = df_validos[coluna_conta_cont].nunique()
                
                # Comparação entre pagamentos e contas
                if not df_pagamentos.empty and not df_contas.empty:
                    coluna_conta_pag = detectar_coluna_conta(df_pagamentos)
                    coluna_conta_cont = detectar_coluna_conta(df_contas)
                    
                    if coluna_conta_pag and coluna_conta_cont:
                        # Limpar e extrair contas válidas
                        contas_pag = set(df_pagamentos[coluna_conta_pag].dropna().astype(str).str.strip())
                        contas_pag = {c for c in contas_pag if c and c not in ['', 'nan', 'NaN', 'None', 'null']}
                        
                        contas_cont = set(df_contas[coluna_conta_cont].dropna().astype(str).str.strip())
                        contas_cont = {c for c in contas_cont if c and c not in ['', 'nan', 'NaN', 'None', 'null']}
                        
                        comparacao['total_contas_abertas'] = len(contas_cont)
                        comparacao['total_contas_com_pagamento'] = len(contas_pag)
                        comparacao['total_contas_sem_pagamento'] = len(contas_cont - contas_pag)
                        comparacao['contas_sem_pagamento'] = list(contas_cont - contas_pag)
                
                # Análise de problemas críticos
                problemas_pagamentos = analisar_problemas_criticos(df_pagamentos, 'pagamentos')
                problemas_contas = analisar_problemas_criticos(df_contas, 'contas')
                
                # Exibir resultados
                st.success("✅ Análise completa concluída!")
                
                # Métricas principais
                st.subheader("📊 Métricas Principais")
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    if 'total_registros' in metrics_pagamentos:
                        st.metric("Total de Pagamentos", 
                                 formatar_brasileiro(metrics_pagamentos['total_registros']))
                    else:
                        st.metric("Total de Pagamentos", "0")
                
                with col2:
                    if 'valor_total' in metrics_pagamentos:
                        st.metric("Valor Total", 
                                 formatar_brasileiro(metrics_pagamentos['valor_total'], 'monetario'))
                    else:
                        st.metric("Valor Total", "R$ 0,00")
                
                with col3:
                    if 'total_contas' in metrics_contas:
                        st.metric("Contas Abertas", 
                                 formatar_brasileiro(metrics_contas['total_contas']))
                    else:
                        st.metric("Contas Abertas", "0")
                
                with col4:
                    if 'total_contas_sem_pagamento' in comparacao:
                        st.metric("Contas sem Pagamento", 
                                 formatar_brasileiro(comparacao['total_contas_sem_pagamento']),
                                 delta_color="inverse")
                    else:
                        st.metric("Contas sem Pagamento", "0")
                
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
                        coluna_conta = detectar_coluna_conta(df_pagamentos)
                        coluna_valor = detectar_coluna_valor(df_pagamentos)
                        
                        if coluna_conta:
                            st.write(f"Coluna de conta detectada: **{coluna_conta}**")
                        if coluna_valor:
                            st.write(f"Coluna de valor detectada: **{coluna_valor}**")
                        
                        with st.expander("Ver primeiros registros"):
                            st.dataframe(df_pagamentos.head(10))
                    
                    if not df_contas.empty:
                        st.write(f"**Contas:** {len(df_contas)} registros")
                        with st.expander("Ver primeiros registros"):
                            st.dataframe(df_contas.head(10))
                
                with tab2:
                    st.subheader("Análise de Duplicidades")
                    
                    if not df_pagamentos.empty:
                        coluna_conta = detectar_coluna_conta(df_pagamentos)
                        
                        if coluna_conta and coluna_conta in df_pagamentos.columns:
                            # Limpar dados
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
                                    st.dataframe(duplicados[colunas_mostrar].head(20))
                                else:
                                    st.success("✅ Nenhuma duplicidade encontrada")
                            else:
                                st.info("ℹ️ Nenhum número de conta válido encontrado para análise de duplicidades")
                
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
                                    st.warning("Não foi possível filtrar as contas sem pagamento")
                    else:
                        st.success("✅ Nenhuma inconsistência grave encontrada")
                
                with tab4:
                    st.subheader("Estatísticas Detalhadas")
                    
                    if not df_pagamentos.empty:
                        coluna_valor = detectar_coluna_valor(df_pagamentos)
                        
                        if coluna_valor and coluna_valor in df_pagamentos.columns:
                            # Converter para numérico
                            df_pagamentos_num = converter_coluna_valor(df_pagamentos, coluna_valor)
                            
                            # Gráfico de distribuição
                            try:
                                valores_validos = df_pagamentos_num[coluna_valor].dropna()
                                if len(valores_validos) > 0:
                                    fig = px.histogram(valores_validos, 
                                                     title='Distribuição dos Valores de Pagamento',
                                                     nbins=20,
                                                     labels={'value': 'Valor (R$)', 'count': 'Quantidade'})
                                    st.plotly_chart(fig, use_container_width=True)
                            except:
                                st.info("Não foi possível gerar o gráfico de distribuição")
                            
                            # Estatísticas
                            try:
                                estat = df_pagamentos_num[coluna_valor].describe()
                                st.write("**Estatísticas Descritivas:**")
                                st.dataframe(pd.DataFrame({
                                    'Estatística': estat.index,
                                    'Valor': estat.values
                                }))
                            except:
                                st.info("Não foi possível calcular estatísticas descritivas")
                
                # Gerar e oferecer download do PDF
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
                    else:
                        st.warning("⚠️ Não foi possível gerar o relatório PDF")
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
        
        with st.expander("📚 Instruções de uso"):
            st.markdown("""
            1. **Faça upload dos arquivos** na sidebar
            2. **Classificação automática**: O sistema identifica se são arquivos de pagamentos ou contas
            3. **Configure o período**: Selecione o mês e ano de referência
            4. **Clique em "Realizar Análise Completa"**
            5. **Revise os resultados**: Métricas, problemas críticos e inconsistências
            6. **Exporte os resultados**: PDF e CSV
            """)
        
        with st.expander("⚠️ Problemas comuns e soluções"):
            st.markdown("""
            ### Arquivo vazio ou só com cabeçalho
            - O sistema detecta arquivos vazios e os ignora
            - Verifique se o arquivo realmente contém dados
            
            ### Erro de encoding
            - O sistema tenta diferentes encodings automaticamente
            - Use UTF-8 ou Latin-1 sempre que possível
            
            ### Colunas não detectadas
            - Use nomes padrão como "Num Cartao", "Valor", "Nome"
            - O sistema reconhece variações comuns
            
            ### Valores não numéricos
            - O sistema converte valores automaticamente
            - Use formato brasileiro: 1.234,56 ou 1234,56
            """)

if __name__ == "__main__":
    main()
