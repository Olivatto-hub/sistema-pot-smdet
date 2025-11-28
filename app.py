import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import io
from fpdf import FPDF
import numpy as np

# Configuração da página
st.set_page_config(
    page_title="Sistema POT - SMDET",
    page_icon="🏛️",
    layout="wide"
)

# Sistema de autenticação simples
def autenticar():
    st.sidebar.title("Sistema POT - SMDET")
    email = st.sidebar.text_input("Email @prefeitura.sp.gov.br")
    
    if email and not email.endswith('@prefeitura.sp.gov.br'):
        st.error("🚫 Acesso restrito aos servidores da Prefeitura de São Paulo")
        st.stop()
    
    return email

# CORREÇÃO: Nova função para processar colunas de data
def processar_colunas_data(df):
    """Converte colunas de data de formato numérico do Excel para datas legíveis"""
    df_processed = df.copy()
    
    # Identificar colunas de data
    colunas_data = ['Data', 'Data Pagto', 'Data_Pagto', 'DataPagto']
    
    for coluna in colunas_data:
        if coluna in df_processed.columns:
            try:
                # Tentar converter de número do Excel (formato serial)
                if df_processed[coluna].dtype in ['int64', 'float64']:
                    # Converter de número do Excel para data
                    df_processed[coluna] = pd.to_datetime(
                        df_processed[coluna], 
                        unit='D', 
                        origin='1899-12-30',  # Data base do Excel
                        errors='coerce'
                    )
                else:
                    # Tentar converter de string
                    df_processed[coluna] = pd.to_datetime(
                        df_processed[coluna], 
                        errors='coerce'
                    )
                
                # Formatar para string legível
                df_processed[coluna] = df_processed[coluna].dt.strftime('%d/%m/%Y')
                
            except Exception as e:
                st.warning(f"⚠️ Não foi possível processar a coluna de data '{coluna}': {str(e)}")
    
    return df_processed

# CORREÇÃO: Nova função para processar colunas de valor
def processar_colunas_valor(df):
    """Processa colunas de valor para formato brasileiro"""
    df_processed = df.copy()
    
    if 'Valor' in df_processed.columns:
        try:
            # Se for string, limpar e converter
            if df_processed['Valor'].dtype == 'object':
                df_processed['Valor_Limpo'] = (
                    df_processed['Valor']
                    .astype(str)
                    .str.replace('R$', '')
                    .str.replace('R$ ', '')
                    .str.replace('.', '')  # Remove separador de milhar
                    .str.replace(',', '.')  # Converte decimal para padrão numérico
                    .str.replace(' ', '')
                    .astype(float)
                )
            else:
                df_processed['Valor_Limpo'] = df_processed['Valor'].astype(float)
                
        except Exception as e:
            st.warning(f"⚠️ Erro ao processar valores: {str(e)}")
            df_processed['Valor_Limpo'] = 0.0
    
    return df_processed

# Sistema de upload de dados
def carregar_dados():
    st.sidebar.header("📤 Carregar Dados Reais")
    
    # Upload para pagamentos
    upload_pagamentos = st.sidebar.file_uploader(
        "Planilha de Pagamentos", 
        type=['xlsx', 'csv'],
        key="pagamentos"
    )
    
    # Upload para abertura de contas
    upload_contas = st.sidebar.file_uploader(
        "Planilha de Abertura de Contas", 
        type=['xlsx', 'csv'],
        key="contas"
    )
    
    dados = {}
    
    # Carregar dados de pagamentos
    if upload_pagamentos is not None:
        try:
            if upload_pagamentos.name.endswith('.xlsx'):
                df_pagamentos = pd.read_excel(upload_pagamentos)
            else:
                df_pagamentos = pd.read_csv(upload_pagamentos)
            
            # CORREÇÃO: Processar datas e valores
            df_pagamentos = processar_colunas_data(df_pagamentos)
            df_pagamentos = processar_colunas_valor(df_pagamentos)
            
            dados['pagamentos'] = df_pagamentos
            st.sidebar.success(f"✅ Pagamentos: {len(dados['pagamentos'])} registros")
        except Exception as e:
            st.sidebar.error(f"❌ Erro ao carregar pagamentos: {str(e)}")
            dados['pagamentos'] = pd.DataFrame()
    else:
        dados['pagamentos'] = pd.DataFrame()
        st.sidebar.info("📁 Aguardando planilha de pagamentos")
    
    # Carregar dados de abertura de contas
    if upload_contas is not None:
        try:
            if upload_contas.name.endswith('.xlsx'):
                df_contas = pd.read_excel(upload_contas)
            else:
                df_contas = pd.read_csv(upload_contas)
            
            # CORREÇÃO: Processar datas
            df_contas = processar_colunas_data(df_contas)
            
            dados['contas'] = df_contas
            st.sidebar.success(f"✅ Contas: {len(dados['contas'])} registros")
        except Exception as e:
            st.sidebar.error(f"❌ Erro ao carregar contas: {str(e)}")
            dados['contas'] = pd.DataFrame()
    else:
        dados['contas'] = pd.DataFrame()
        st.sidebar.info("📁 Aguardando planilha de abertura de contas")
    
    return dados

# NOVA FUNÇÃO: Analisar ausência de dados
def analisar_ausencia_dados(dados):
    """Analisa e reporta ausência de dados críticos de forma mais detalhada"""
    analise_ausencia = {
        'cpfs_sem_dados_completos': [],
        'total_registros_incompletos': 0,
        'colunas_com_ausencia': {},
        'resumo_ausencias': pd.DataFrame(),
        'registros_problema_detalhados': pd.DataFrame()  # NOVO: dados completos dos registros problemáticos
    }
    
    if not dados['pagamentos'].empty:
        df = dados['pagamentos'].copy()
        
        # Identificar registros com CPF ausente ou inválido
        cpfs_ausentes = []
        if 'CPF' in df.columns:
            # CPFs vazios, nulos ou inválidos
            mask_cpf_invalido = (
                df['CPF'].isna() | 
                (df['CPF'].astype(str).str.strip() == '') |
                (df['CPF'].astype(str).str.strip() == 'NaN') |
                (df['CPF'].astype(str).str.strip() == 'None') |
                (df['CPF'].astype(str).str.strip() == 'nan') |
                (df['CPF'].astype(str).str.strip() == '0') |
                (df['CPF'].astype(str).str.strip().str.len() < 11)  # CPF incompleto
            )
            
            cpfs_invalidos = df[mask_cpf_invalido]
            
            if not cpfs_invalidos.empty:
                cpfs_ausentes = cpfs_invalidos.index.tolist()
                analise_ausencia['cpfs_sem_dados_completos'] = cpfs_ausentes
                analise_ausencia['total_registros_incompletos'] = len(cpfs_ausentes)
                
                # NOVO: Salvar os registros completos com problemas
                analise_ausencia['registros_problema_detalhados'] = cpfs_invalidos.copy()
        
        # Analisar ausência por coluna crítica
        colunas_criticas = ['CPF', 'Valor', 'Projeto', 'Beneficiario', 'Beneficiário', 'Nome']
        for coluna in colunas_criticas:
            if coluna in df.columns:
                # Verificar valores ausentes ou inválidos
                mask_ausente = (
                    df[coluna].isna() | 
                    (df[coluna].astype(str).str.strip() == '') |
                    (df[coluna].astype(str).str.strip() == 'NaN') |
                    (df[coluna].astype(str).str.strip() == 'None') |
                    (df[coluna].astype(str).str.strip() == 'nan')
                )
                ausentes = df[mask_ausente]
                analise_ausencia['colunas_com_ausencia'][coluna] = len(ausentes)
        
        # Criar resumo de ausências para exibição
        if cpfs_ausentes:
            resumo = []
            for idx in cpfs_ausentes[:50]:  # Aumentar para 50 registros
                registro = df.loc[idx]
                info_ausencia = {'Indice_Registro': idx}
                
                # Adicionar todas as informações disponíveis
                colunas_interesse = [
                    'CPF', 'Projeto', 'Valor', 'Beneficiario', 'Beneficiário', 'Nome',
                    'Data', 'Data Pagto', 'Data_Pagto', 'DataPagto',
                    'Num Cartao', 'Num_Cartao', 'Conta', 'Status'
                ]
                
                for col in colunas_interesse:
                    if col in df.columns and pd.notna(registro[col]):
                        # Truncar valores muito longos
                        valor = str(registro[col])
                        if len(valor) > 50:
                            valor = valor[:47] + "..."
                        info_ausencia[col] = valor
                    else:
                        info_ausencia[col] = 'N/A'
                
                resumo.append(info_ausencia)
            
            analise_ausencia['resumo_ausencias'] = pd.DataFrame(resumo)
    
    return analise_ausencia

def analisar_duplicidades(dados):
    """Analisa pagamentos duplicados e retorna estatísticas"""
    analise = {
        'total_pagamentos': 0,
        'beneficiarios_unicos': 0,
        'pagamentos_duplicados': 0,
        'valor_total_duplicados': 0,
        'detalhes_duplicados': pd.DataFrame(),
        'resumo_duplicidades': pd.DataFrame(),
        'cpfs_com_erros': []  # NOVO: CPFs com possíveis problemas
    }
    
    if dados['pagamentos'].empty:
        return analise
    
    df = dados['pagamentos'].copy()
    analise['total_pagamentos'] = len(df)
    
    # Identificar beneficiários únicos (apenas CPFs válidos)
    if 'CPF' in df.columns:
        # Filtrar apenas CPFs válidos
        cpfs_validos = df[
            df['CPF'].notna() & 
            (df['CPF'].astype(str).str.strip() != '') &
            (df['CPF'].astype(str).str.strip() != 'NaN') &
            (df['CPF'].astype(str).str.strip() != 'None')
        ]
        
        analise['beneficiarios_unicos'] = cpfs_validos['CPF'].nunique()
        
        # Identificar CPFs com problemas
        cpfs_com_problemas = df[
            df['CPF'].isna() | 
            (df['CPF'].astype(str).str.strip() == '') |
            (df['CPF'].astype(str).str.strip() == 'NaN') |
            (df['CPF'].astype(str).str.strip() == 'None')
        ]
        
        if not cpfs_com_problemas.empty:
            analise['cpfs_com_erros'] = cpfs_com_problemas.index.tolist()
    
    # Identificar pagamentos duplicados por CPF (apenas CPFs válidos)
    if 'CPF' in df.columns:
        # Filtrar CPFs válidos para análise de duplicidade
        df_validos = df[
            df['CPF'].notna() & 
            (df['CPF'].astype(str).str.strip() != '') &
            (df['CPF'].astype(str).str.strip() != 'NaN') &
            (df['CPF'].astype(str).str.strip() != 'None')
        ].copy()
        
        if not df_validos.empty:
            # Contar ocorrências por CPF
            contagem_cpf = df_validos['CPF'].value_counts().reset_index()
            contagem_cpf.columns = ['CPF', 'Quantidade_Pagamentos']
            
            # Identificar CPFs com mais de 1 pagamento
            cpf_duplicados = contagem_cpf[contagem_cpf['Quantidade_Pagamentos'] > 1]
            analise['pagamentos_duplicados'] = len(cpf_duplicados)
            
            # Detalhar os pagamentos duplicados
            if not cpf_duplicados.empty:
                cpfs_com_duplicidade = cpf_duplicados['CPF'].tolist()
                detalhes = df_validos[df_validos['CPF'].isin(cpfs_com_duplicidade)].copy()
                
                # Ordenar por CPF e Data (se disponível)
                colunas_ordenacao = ['CPF']
                if 'Data' in detalhes.columns:
                    colunas_ordenacao.append('Data')
                elif 'Data Pagto' in detalhes.columns:
                    colunas_ordenacao.append('Data Pagto')
                detalhes = detalhes.sort_values(by=colunas_ordenacao)
                
                analise['detalhes_duplicados'] = detalhes
                
                # Calcular valor total dos duplicados
                if 'Valor_Limpo' in df_validos.columns:
                    try:
                        valor_duplicados = 0
                        for cpf in cpfs_com_duplicidade:
                            pagamentos_cpf = df_validos[df_validos['CPF'] == cpf]
                            if len(pagamentos_cpf) > 1:
                                # Somar todos os pagamentos exceto o primeiro (considerando o primeiro como legítimo)
                                valor_duplicados += pagamentos_cpf.iloc[1:]['Valor_Limpo'].sum()
                        
                        analise['valor_total_duplicados'] = valor_duplicados
                        
                    except Exception as e:
                        analise['valor_total_duplicados'] = 0
                
                # Criar resumo de duplicidades
                resumo = []
                for cpf in cpfs_com_duplicidade:
                    pagamentos_cpf = df_validos[df_validos['CPF'] == cpf]
                    qtd = len(pagamentos_cpf)
                    
                    info = {
                        'CPF': cpf,
                        'Quantidade_Pagamentos': qtd,
                    }
                    
                    # Adicionar nome do beneficiário se disponível
                    coluna_beneficiario = obter_coluna_beneficiario(pagamentos_cpf)
                    if coluna_beneficiario:
                        info['Beneficiario'] = pagamentos_cpf.iloc[0][coluna_beneficiario]
                    else:
                        info['Beneficiario'] = 'N/A'
                    
                    # Adicionar projeto se disponível
                    if 'Projeto' in pagamentos_cpf.columns:
                        info['Projeto'] = pagamentos_cpf.iloc[0]['Projeto']
                    else:
                        info['Projeto'] = 'N/A'
                    
                    # Adicionar número da conta se disponível
                    coluna_conta = obter_coluna_conta(pagamentos_cpf)
                    if coluna_conta:
                        info['Num_Cartao'] = pagamentos_cpf.iloc[0][coluna_conta]
                    else:
                        info['Num_Cartao'] = 'N/A'
                    
                    if 'Valor_Limpo' in pagamentos_cpf.columns:
                        try:
                            info['Valor_Total'] = pagamentos_cpf['Valor_Limpo'].sum()
                        except:
                            info['Valor_Total'] = 0
                    
                    resumo.append(info)
                
                analise['resumo_duplicidades'] = pd.DataFrame(resumo)
    
    return analise

def processar_dados(dados):
    """Processa os dados para o dashboard"""
    metrics = {}
    
    # Análise de duplicidades
    analise_dup = analisar_duplicidades(dados)
    metrics.update(analise_dup)
    
    # NOVO: Análise de ausência de dados
    analise_ausencia = analisar_ausencia_dados(dados)
    metrics.update(analise_ausencia)
    
    # Métricas básicas
    if not dados['pagamentos'].empty:
        metrics['total_pagamentos'] = len(dados['pagamentos'])
        if 'Valor_Limpo' in dados['pagamentos'].columns:
            metrics['valor_total'] = dados['pagamentos']['Valor_Limpo'].sum()
        else:
            metrics['valor_total'] = 0
        
        if 'Projeto' in dados['pagamentos'].columns:
            metrics['projetos_ativos'] = dados['pagamentos']['Projeto'].nunique()
        else:
            metrics['projetos_ativos'] = 0
            
        if 'CPF' in dados['pagamentos'].columns:
            metrics['beneficiarios_unicos'] = dados['pagamentos']['CPF'].nunique()
        else:
            metrics['beneficiarios_unicos'] = 0
    
    if not dados['contas'].empty:
        metrics['total_contas'] = len(dados['contas'])
        if 'CPF' in dados['contas'].columns:
            metrics['contas_unicas'] = dados['contas']['CPF'].nunique()
        else:
            metrics['contas_unicas'] = 0
    
    return metrics

class PDFReport(FPDF):
    def header(self):
        # Logo ou título
        self.set_font('Arial', 'B', 16)
        self.cell(0, 10, 'RELATORIO EXECUTIVO - PROGRAMA OPERACAO TRABALHO', 0, 1, 'C')
        self.set_font('Arial', 'I', 10)
        self.cell(0, 5, f'Data de emissao: {datetime.now().strftime("%d/%m/%Y %H:%M")}', 0, 1, 'C')
        self.ln(10)
    
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Pagina {self.page_no()}', 0, 0, 'C')
    
    def chapter_title(self, title):
        self.set_font('Arial', 'B', 14)
        self.set_fill_color(200, 220, 255)
        self.cell(0, 10, title, 0, 1, 'L', 1)
        self.ln(4)
    
    def metric_card(self, label, value, width=45):
        self.set_font('Arial', 'B', 12)
        self.cell(width, 8, label, 0, 0, 'L')
        self.set_font('Arial', '', 12)
        self.cell(0, 8, str(value), 0, 1, 'R')
    
    def table_header(self, headers, col_widths):
        self.set_font('Arial', 'B', 10)
        self.set_fill_color(180, 200, 255)
        for i, header in enumerate(headers):
            self.cell(col_widths[i], 8, header, 1, 0, 'C', 1)
        self.ln()
    
    def table_row(self, data, col_widths):
        self.set_font('Arial', '', 9)
        for i, cell in enumerate(data):
            # CORREÇÃO MELHORADA: Ajustar texto longo quebrando em múltiplas linhas
            cell_text = str(cell) if cell is not None else ""
            cell_text = self.safe_text(cell_text)
            
            # Se o texto for muito longo para a célula, quebrar automaticamente
            text_width = self.get_string_width(cell_text)
            cell_width = col_widths[i] - 1  # Margem de segurança
            
            if text_width > cell_width:
                # Calcular quantas linhas serão necessárias
                chars_per_line = int(len(cell_text) * cell_width / text_width)
                if chars_per_line < 1:
                    chars_per_line = 1
                
                # Quebrar o texto
                lines = []
                words = cell_text.split(' ')
                current_line = ""
                
                for word in words:
                    test_line = current_line + " " + word if current_line else word
                    if self.get_string_width(test_line) <= cell_width:
                        current_line = test_line
                    else:
                        if current_line:
                            lines.append(current_line)
                        current_line = word
                        # Se uma palavra individual for muito longa, quebrar ela
                        if self.get_string_width(word) > cell_width:
                            # Quebrar palavra longa
                            for j in range(0, len(word), chars_per_line):
                                lines.append(word[j:j+chars_per_line])
                            current_line = ""
                
                if current_line:
                    lines.append(current_line)
                
                # Escrever múltiplas linhas
                if len(lines) > 1:
                    line_height = 8 / len(lines)  # Altura proporcional
                    if line_height < 3:  # Mínimo de 3mm por linha
                        line_height = 3
                    
                    y_before = self.get_y()
                    x_before = self.get_x()
                    
                    for j, line in enumerate(lines):
                        if j > 0:
                            self.set_xy(x_before, self.get_y() + line_height)
                        self.cell(col_widths[i], line_height, line, 1, 0, 'C')
                    
                    # Ajustar posição para próxima célula
                    total_height = len(lines) * line_height
                    self.set_xy(x_before + col_widths[i], y_before)
                    # Pular para a próxima linha após todas as células
                    if i == len(data) - 1:  # Última célula da linha
                        self.ln(total_height)
                else:
                    self.cell(col_widths[i], 8, cell_text, 1, 0, 'C')
            else:
                self.cell(col_widths[i], 8, cell_text, 1, 0, 'C')
        
        # Só faz ln() se não estamos no meio de uma quebra de linha múltipla
        if not hasattr(self, '_in_multiline') or not self._in_multiline:
            self.ln()
    
    def safe_text(self, text):
    """Remove caracteres problemáticos para Latin-1 incluindo emojis"""
    # Primeiro, converter para string se não for
    safe_text = str(text)
    
    # Dicionário de substituições
    substitutions = {
        '•': '-', '´': "'", '`': "'", '“': '"', '”': '"', 
        '•': "'", ' ': ' ', '–': '-', '—': '-', '…': '...',
        '🚨': '[ALERTA]', '✅': '[OK]', '📊': '[DASHBOARD]',
        '⚠️': '[ATENCAO]', '❌': '[ERRO]', '📁': '[ARQUIVO]',
        '🔍': '[LUPAR]', '👆': '[SETA_ACIMA]', '🏛️': '[PREFEITURA]'
    }
    
    # Aplicar substituições
    for char, replacement in substitutions.items():
        safe_text = safe_text.replace(char, replacement)
    
    # Remover qualquer outro caractere Unicode problemático
    safe_text = safe_text.encode('latin-1', 'replace').decode('latin-1')
    
    return safe_text

def obter_coluna_beneficiario(df):
    """Detecta automaticamente a coluna do beneficiário"""
    for col in ['Beneficiario', 'Beneficiário', 'Nome', 'Nome Beneficiario']:
        if col in df.columns:
            return col
    return None

def obter_coluna_data(df):
    """Detecta automaticamente a coluna de data"""
    for col in ['Data', 'Data Pagto', 'Data_Pagto', 'DataPagto']:
        if col in df.columns:
            return col
    return None

def obter_coluna_conta(df):
    """Detecta automaticamente a coluna do número da conta"""
    for col in ['Num Cartao', 'Num_Cartao', 'Conta', 'Numero Conta', 'Numero_Cartao']:
        if col in df.columns:
            return col
    return None


def obter_coluna_data_ordenacao(df):
    """Detecta automaticamente a coluna de data para ordenação, considerando múltiplos formatos"""
    colunas_data = ['Data', 'Data Pagto', 'Data_Pagto', 'DataPagto', 'DATA', 'DATA_PAGTO']
    
    for coluna in colunas_data:
        if coluna in df.columns:
            # Tentar converter para datetime se ainda não estiver
            if not pd.api.types.is_datetime64_any_dtype(df[coluna]):
                try:
                    # Tentar diferentes formatos de data
                    df_temp = df.copy()
                    df_temp[coluna] = pd.to_datetime(df_temp[coluna], errors='coerce')
                    # Verificar se a conversão foi bem sucedida (não todos NaT)
                    if not df_temp[coluna].isna().all():
                        return coluna
                except:
                    continue
            else:
                return coluna
    
    # Se não encontrou coluna de data, usar o índice
    return None

# NOVA FUNÇÃO: Ordenar dados por data
def ordenar_por_data(df, coluna_data):
    """Ordena DataFrame por data de forma segura"""
    if coluna_data and coluna_data in df.columns:
        try:
            df_ordenado = df.copy()
            # Converter para datetime se necessário
            if not pd.api.types.is_datetime64_any_dtype(df_ordenado[coluna_data]):
                df_ordenado[coluna_data] = pd.to_datetime(
                    df_ordenado[coluna_data], 
                    dayfirst=True,  # Importante para formato brasileiro
                    errors='coerce'
                )
            
            # Ordenar por data (mais recente primeiro)
            df_ordenado = df_ordenado.sort_values(by=coluna_data, ascending=False)
            return df_ordenado
        except Exception as e:
            st.warning(f"Não foi possível ordenar por data: {str(e)}")
            return df
    else:
        return df

# CORREÇÃO: Nova função para formatar números no padrão brasileiro
def formatar_brasileiro(valor, tipo='monetario'):
    """Formata números no padrão brasileiro"""
    try:
        if isinstance(valor, (int, float)):
            if tipo == 'monetario':
                return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            else:
                return f"{valor:,.0f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        else:
            return str(valor)
    except:
        return str(valor)

def gerar_pdf_executivo(dados, tipo_relatorio):
    """Gera PDF executivo profissional"""
    pdf = PDFReport()
    pdf.add_page()
    
    metrics = processar_dados(dados)
    
    # Capa
    pdf.set_font('Arial', 'B', 20)
    pdf.cell(0, 40, '', 0, 1, 'C')
    pdf.cell(0, 15, 'RELATORIO EXECUTIVO', 0, 1, 'C')
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 10, 'PROGRAMA OPERACAO TRABALHO', 0, 1, 'C')
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 10, f'Tipo: {tipo_relatorio}', 0, 1, 'C')
    pdf.cell(0, 10, f'Data: {datetime.now().strftime("%d/%m/%Y")}', 0, 1, 'C')
    pdf.cell(0, 10, 'Secretaria Municipal do Desenvolvimento Economico e Trabalho', 0, 1, 'C')
    
    pdf.add_page()
    
    # Resumo Executivo
    pdf.chapter_title('RESUMO EXECUTIVO')
    
    # Métricas principais - CORREÇÃO: Usando formatação brasileira
    col_width = 60
    pdf.metric_card('Total de Pagamentos:', formatar_brasileiro(metrics.get('total_pagamentos', 0), 'numero'))
    pdf.metric_card('Beneficiarios Unicos:', formatar_brasileiro(metrics.get('beneficiarios_unicos', 0), 'numero'))
    pdf.metric_card('Projetos Ativos:', formatar_brasileiro(metrics.get('projetos_ativos', 0), 'numero'))
    pdf.metric_card('Contas Abertas:', formatar_brasileiro(metrics.get('total_contas', 0), 'numero'))
    
    if metrics.get('valor_total', 0) > 0:
        pdf.metric_card('Valor Total Investido:', formatar_brasileiro(metrics.get('valor_total', 0), 'monetario'))
    
    # NOVO: Alertas de ausência de dados
    # ALERTA MELHORADO: Ausência de dados com opção de download
if metrics.get('total_registros_incompletos', 0) > 0:
    st.error(f"🚨 **ALERTA: AUSÊNCIA DE DADOS IDENTIFICADA** - {formatar_brasileiro(metrics.get('total_registros_incompletos', 0), 'numero')} registros com CPF ausente ou inválido")
    
    col_alert1, col_alert2 = st.columns([3, 1])
    
    with col_alert1:
        st.warning("**Estes registros precisam ser corrigidos para análise completa dos dados**")
        
    with col_alert2:
        # Botão para exportar registros problemáticos
        if not metrics['registros_problema_detalhados'].empty:
            csv_problemas = metrics['registros_problema_detalhados'].to_csv(index=False, sep=';')
            st.download_button(
                label="📥 Exportar Registros Problemáticos",
                data=csv_problemas,
                file_name=f"registros_problema_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                help="Baixe esta lista para corrigir os dados ausentes"
            )
    
    with st.expander("🔍 **Ver Detalhes dos Dados Ausentes**", expanded=False):
        st.subheader("Resumo de Ausências por Campo")
        
        if metrics.get('colunas_com_ausencia'):
            col_aus1, col_aus2, col_aus3 = st.columns(3)
            colunas_ausencia = list(metrics['colunas_com_ausencia'].items())
            
            for i, (coluna, qtd) in enumerate(colunas_ausencia):
                if qtd > 0:
                    with [col_aus1, col_aus2, col_aus3][i % 3]:
                        st.metric(
                            label=f"Sem {coluna}",
                            value=formatar_brasileiro(qtd, 'numero'),
                            delta=f"{qtd/len(dados['pagamentos'])*100:.1f}% do total"
                        )
        
        st.subheader("Exemplos de Registros com Problemas")
        if not metrics['resumo_ausencias'].empty:
            # Mostrar colunas mais relevantes primeiro
            colunas_prioridade = ['Indice_Registro', 'CPF', 'Nome', 'Beneficiario', 'Beneficiário', 'Projeto', 'Valor']
            colunas_exibir = [col for col in colunas_prioridade if col in metrics['resumo_ausencias'].columns]
            colunas_restantes = [col for col in metrics['resumo_ausencias'].columns if col not in colunas_exibir]
            colunas_exibir.extend(colunas_restantes)
            
            st.dataframe(
                metrics['resumo_ausencias'][colunas_exibir],
                use_container_width=True,
                hide_index=True,
                height=400
            )
            
            st.info(f"Mostrando {len(metrics['resumo_ausencias'])} de {metrics['total_registros_incompletos']} registros com problemas. Use o botão de exportação acima para baixar a lista completa.")
    
    # Análise de Duplicidades
    if metrics.get('pagamentos_duplicados', 0) > 0:
        pdf.chapter_title('ANALISE DE DUPLICIDADES - ALERTA')
        
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 8, 'Diferenca Identificada:', 0, 1)
        pdf.set_font('Arial', '', 12)
        diff = metrics.get('total_pagamentos', 0) - metrics.get('beneficiarios_unicos', 0)
        pdf.cell(0, 8, f'- {formatar_brasileiro(metrics.get("total_pagamentos", 0), "numero")} pagamentos para {formatar_brasileiro(metrics.get("beneficiarios_unicos", 0), "numero")} beneficiarios (diferenca: {formatar_brasileiro(diff, "numero")} pagamentos)', 0, 1)
        
        pdf.cell(0, 8, f'- {formatar_brasileiro(metrics.get("pagamentos_duplicados", 0), "numero")} CPFs com pagamentos duplicados', 0, 1)
        
        if metrics.get('valor_total_duplicados', 0) > 0:
            pdf.cell(0, 8, f'- Valor total em duplicidades: {formatar_brasileiro(metrics.get("valor_total_duplicados", 0), "monetario")}', 0, 1)
        
        pdf.ln(5)
        
        # Resumo dos CPFs com duplicidade
        if not metrics['resumo_duplicidades'].empty:
            pdf.set_font('Arial', 'B', 12)
            pdf.cell(0, 8, 'Principais Casos de Duplicidade:', 0, 1)
            
            # CORREÇÃO: Ajustar larguras das colunas para nomes longos
            headers = ['CPF', 'Qtd Pag']
            col_widths = [30, 15]  # Reduzir largura de colunas numéricas
            
            # Adicionar beneficiário se disponível com largura maior
            if 'Beneficiario' in metrics['resumo_duplicidades'].columns:
                headers.append('Beneficiario')
                col_widths.append(50)  # Espaço adequado para nomes
            
            # Adicionar número da conta se disponível
            if 'Num_Cartao' in metrics['resumo_duplicidades'].columns:
                headers.append('Num Conta')
                col_widths.append(25)
            
            # Adicionar projeto se disponível
            if 'Projeto' in metrics['resumo_duplicidades'].columns:
                headers.append('Projeto')
                col_widths.append(40)
            
            # Ajustar para total de 180mm
            total_width = sum(col_widths)
            if total_width > 180:
                fator = 180 / total_width
                col_widths = [int(w * fator) for w in col_widths]
            
            pdf.table_header(headers, col_widths)
            
            # Mostrar os 10 primeiros casos
            for _, row in metrics['resumo_duplicidades'].head(10).iterrows():
                row_data = [row['CPF'], str(row['Quantidade_Pagamentos'])]
                
                # Adicionar beneficiário se disponível
                if 'Beneficiario' in metrics['resumo_duplicidades'].columns:
                    row_data.append(str(row['Beneficiario']))
                
                # Adicionar número da conta se disponível
                if 'Num_Cartao' in metrics['resumo_duplicidades'].columns:
                    row_data.append(str(row['Num_Cartao']))
                
                # Adicionar projeto se disponível
                if 'Projeto' in metrics['resumo_duplicidades'].columns:
                    row_data.append(str(row['Projeto']))
                
                pdf.table_row(row_data, col_widths)
    
    # NOVA SEÇÃO: Análise de Ausência de Dados
    if metrics.get('total_registros_incompletos', 0) > 0:
        pdf.add_page()
        pdf.chapter_title('ANALISE DE AUSENCIA DE DADOS - ALERTA')
        
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 8, 'Resumo de Ausencias Identificadas:', 0, 1)
        pdf.set_font('Arial', '', 11)
        
        pdf.cell(0, 7, f'- Total de registros com dados incompletos: {formatar_brasileiro(metrics.get("total_registros_incompletos", 0), "numero")}', 0, 1)
        
        if metrics.get('colunas_com_ausencia'):
            pdf.cell(0, 7, '- Ausencias por coluna:', 0, 1)
            for coluna, qtd in metrics['colunas_com_ausencia'].items():
                if qtd > 0:
                    pdf.cell(10, 7, '', 0, 0)  # Indentação
                    pdf.cell(0, 7, f'{coluna}: {formatar_brasileiro(qtd, "numero")} registros', 0, 1)
        
        pdf.ln(5)
        
        # Mostrar exemplos de registros com problemas
        if not metrics['resumo_ausencias'].empty:
            pdf.set_font('Arial', 'B', 12)
            pdf.cell(0, 8, 'Exemplos de Registros com Dados Ausentes:', 0, 1)
            
            headers = ['Indice', 'Nome Disponivel', 'Projeto', 'Valor']
            col_widths = [20, 60, 60, 40]
            
            pdf.table_header(headers, col_widths)
            
            for _, row in metrics['resumo_ausencias'].head(15).iterrows():
                row_data = [
                    str(row['Indice_Registro']),
                    str(row['Nome_Disponivel']),
                    str(row['Projeto']),
                    str(row['Valor'])
                ]
                pdf.table_row(row_data, col_widths)
    
    # Análise de Projetos
    if not dados['pagamentos'].empty and 'Projeto' in dados['pagamentos'].columns:
        pdf.add_page()
        pdf.chapter_title('DISTRIBUICAO POR PROJETO')
        
        projetos_count = dados['pagamentos']['Projeto'].value_counts().reset_index()
        projetos_count.columns = ['Projeto', 'Quantidade']
        
        # Cabeçalho da tabela
        headers = ['Projeto', 'Quantidade', '% do Total']
        col_widths = [100, 30, 30]  # Mais espaço para nome do projeto
        pdf.table_header(headers, col_widths)
        
        # Dados da tabela - CORREÇÃO: Formatação brasileira
        total = projetos_count['Quantidade'].sum()
        for _, row in projetos_count.iterrows():
            projeto = row['Projeto']
            quantidade = row['Quantidade']
            percentual = (quantidade / total) * 100
            pdf.table_row([
                projeto, 
                formatar_brasileiro(quantidade, 'numero'), 
                f"{percentual:.1f}%"
            ], col_widths)
    
    # Detalhes de Duplicidades (página separada) - CORREÇÃO MELHORADA
    if not metrics['detalhes_duplicados'].empty:
        pdf.add_page()
        pdf.chapter_title('DETALHES DOS PAGAMENTOS DUPLICADOS')
        
        # Usar funções de detecção automática de colunas
        colunas_base = ['CPF']
        
        # Adicionar beneficiário se disponível
        coluna_benef = obter_coluna_beneficiario(metrics['detalhes_duplicados'])
        if coluna_benef:
            colunas_base.append(coluna_benef)
        
        # Adicionar projeto se disponível
        if 'Projeto' in metrics['detalhes_duplicados'].columns:
            colunas_base.append('Projeto')
        
        # Adicionar colunas de data
        coluna_data = obter_coluna_data(metrics['detalhes_duplicados'])
        if coluna_data:
            colunas_base.append(coluna_data)
        
        # Adicionar colunas de número da conta
        coluna_conta = obter_coluna_conta(metrics['detalhes_duplicados'])
        if coluna_conta:
            colunas_base.append(coluna_conta)
        
        # Adicionar valor
        if 'Valor' in metrics['detalhes_duplicados'].columns:
            colunas_base.append('Valor')
        
        if colunas_base:
            dados_exibir = metrics['detalhes_duplicados'][colunas_base].head(30)  # Aumentado para 30 registros
            
            # CORREÇÃO MELHORADA: Ajustar larguras dinamicamente considerando conteúdo
            num_cols = len(colunas_base)
            
            # Larguras base por tipo de coluna
            col_widths = []
            for col in colunas_base:
                if col == 'CPF':
                    col_widths.append(25)
                elif col in ['Beneficiario', 'Beneficiário', 'Nome']:
                    col_widths.append(45)  # Mais espaço para nomes, mas não excessivo
                elif col == 'Projeto':
                    col_widths.append(35)
                elif 'Data' in col:
                    col_widths.append(20)
                elif 'Valor' in col:
                    col_widths.append(25)
                elif 'Num' in col or 'Conta' in col:
                    col_widths.append(25)
                else:
                    col_widths.append(30)
            
            # Ajustar para total de 180mm
            total_width = sum(col_widths)
            if total_width != 180:
                fator = 180 / total_width
                col_widths = [int(w * fator) for w in col_widths]
            
            # Garantir que a soma seja 180
            diff = 180 - sum(col_widths)
            if diff != 0 and len(col_widths) > 0:
                col_widths[-1] += diff
            
            # Cabeçalho
            pdf.table_header(colunas_base, col_widths)
            
            # Dados
            for _, row in dados_exibir.iterrows():
                row_data = []
                for col in colunas_base:
                    cell_value = str(row[col]) if pd.notna(row[col]) else ""
                    # CORREÇÃO: Formatar valores monetários
                    if col == 'Valor' and 'Valor_Limpo' in metrics['detalhes_duplicados'].columns:
                        idx = row.name
                        if idx in metrics['detalhes_duplicados'].index:
                            valor_limpo = metrics['detalhes_duplicados'].loc[idx, 'Valor_Limpo']
                            cell_value = formatar_brasileiro(valor_limpo, 'monetario')
                    
                    # Limpar caracteres especiais e truncar se necessário
                    cell_value = pdf.safe_text(cell_value)
                    
                    # Truncar texto muito longo para evitar problemas de layout
                    if len(cell_value) > 50:
                        cell_value = cell_value[:47] + "..."
                    
                    row_data.append(cell_value)
                pdf.table_row(row_data, col_widths)
    
    # Últimos Pagamentos com dados completos
    if not dados['pagamentos'].empty:
        pdf.add_page()
        pdf.chapter_title('ULTIMOS PAGAMENTOS REGISTRADOS')
        
        # Usar funções de detecção automática de colunas
        colunas_base = ['CPF']
        
        # Adicionar beneficiário se disponível
        coluna_benef = obter_coluna_beneficiario(dados['pagamentos'])
        if coluna_benef:
            colunas_base.append(coluna_benef)
        
        # Adicionar projeto se disponível
        if 'Projeto' in dados['pagamentos'].columns:
            colunas_base.append('Projeto')
        
        # Adicionar colunas de data
        coluna_data = obter_coluna_data(dados['pagamentos'])
        if coluna_data:
            colunas_base.append(coluna_data)
        
        # Adicionar colunas de número da conta
        coluna_conta = obter_coluna_conta(dados['pagamentos'])
        if coluna_conta:
            colunas_base.append(coluna_conta)
        
        # Adicionar valor e status
        if 'Valor' in dados['pagamentos'].columns:
            colunas_base.append('Valor')
        if 'Status' in dados['pagamentos'].columns:
            colunas_base.append('Status')
        
        if not colunas_base:
            colunas_base = dados['pagamentos'].columns[:6].tolist()
        
        dados_exibir = dados['pagamentos'][colunas_base].head(15)
        
        # CORREÇÃO: Ajustar larguras considerando tipos de conteúdo
        num_cols = len(colunas_base)
        base_width = 180 // num_cols
        col_widths = []
        
        for col in colunas_base:
            if col in ['Beneficiario', 'Beneficiário', 'Nome']:
                col_widths.append(base_width + 15)
            elif col == 'Projeto':
                col_widths.append(base_width + 10)
            elif col == 'CPF':
                col_widths.append(25)
            elif 'Data' in col:
                col_widths.append(20)
            elif 'Valor' in col:
                col_widths.append(25)
            else:
                col_widths.append(base_width)
        
        # Ajustar para total de 180mm
        total_width = sum(col_widths)
        if total_width > 180:
            fator = 180 / total_width
            col_widths = [int(w * fator) for w in col_widths]
        
        # Garantir que a soma seja 180
        diff = 180 - sum(col_widths)
        if diff != 0 and len(col_widths) > 0:
            col_widths[-1] += diff
        
        # Cabeçalho
        pdf.table_header(colunas_base, col_widths)
        
        # Dados
        for _, row in dados_exibir.iterrows():
            row_data = []
            for col in colunas_base:
                cell_value = str(row[col]) if pd.notna(row[col]) else ""
                
                # CORREÇÃO: Formatar valores monetários
                if col == 'Valor' and 'Valor_Limpo' in dados['pagamentos'].columns:
                    idx = row.name
                    if idx in dados['pagamentos'].index:
                        valor_limpo = dados['pagamentos'].loc[idx, 'Valor_Limpo']
                        cell_value = formatar_brasileiro(valor_limpo, 'monetario')
                
                # Limpar caracteres especiais
                cell_value = pdf.safe_text(cell_value)
                
                # Truncar texto muito longo
                if len(cell_value) > 50:
                    cell_value = cell_value[:47] + "..."
                
                row_data.append(cell_value)
            pdf.table_row(row_data, col_widths)
    
    # Conclusão
    pdf.add_page()
    pdf.chapter_title('CONCLUSOES E RECOMENDACOES')
    
    pdf.set_font('Arial', '', 12)
    conclusoes = [
        f"- O programa atendeu {formatar_brasileiro(metrics.get('beneficiarios_unicos', 0), 'numero')} beneficiarios unicos",
        f"- Foram realizados {formatar_brasileiro(metrics.get('total_pagamentos', 0), 'numero')} pagamentos",
        f"- {formatar_brasileiro(metrics.get('projetos_ativos', 0), 'numero')} projetos em operacao",
        f"- {formatar_brasileiro(metrics.get('total_contas', 0), 'numero')} contas bancarias abertas"
    ]
    
    if metrics.get('valor_total', 0) > 0:
        conclusoes.append(f"- Investimento total de {formatar_brasileiro(metrics.get('valor_total', 0), 'monetario')}")
    
    # Adicionar conclusões sobre duplicidades
    if metrics.get('pagamentos_duplicados', 0) > 0:
        conclusoes.append("")
        conclusoes.append("*** ALERTA: DUPLICIDADES IDENTIFICADAS ***")
        conclusoes.append(f"- {formatar_brasileiro(metrics.get('pagamentos_duplicados', 0), 'numero')} beneficiarios com pagamentos duplicados")
        conclusoes.append(f"- Diferenca: {formatar_brasileiro(metrics.get('total_pagamentos', 0) - metrics.get('beneficiarios_unicos', 0), 'numero')} pagamentos extras")
        if metrics.get('valor_total_duplicados', 0) > 0:
            conclusoes.append(f"- Valor em duplicidades: {formatar_brasileiro(metrics.get('valor_total_duplicados', 0), 'monetario')}")
    
    # NOVO: Adicionar conclusões sobre ausência de dados
    if metrics.get('total_registros_incompletos', 0) > 0:
        conclusoes.append("")
        conclusoes.append("*** ALERTA: AUSENCIA DE DADOS IDENTIFICADA ***")
        conclusoes.append(f"- {formatar_brasileiro(metrics.get('total_registros_incompletos', 0), 'numero')} registros com dados incompletos")
        conclusoes.append("- Necessario revisao manual dos registros afetados")
    
    for conclusao in conclusoes:
        pdf.cell(0, 8, pdf.safe_text(conclusao), 0, 1)
    
    pdf.ln(10)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 8, 'Recomendacoes:', 0, 1)
    pdf.set_font('Arial', '', 11)
    
    recomendacoes = [
        "- Manter monitoramento continuo dos projetos",
        "- Expandir para novas regioes da cidade",
        "- Avaliar impacto social do programa",
        "- Otimizar processos de pagamento"
    ]
    
    # Adicionar recomendações específicas para duplicidades
    if metrics.get('pagamentos_duplicados', 0) > 0:
        recomendacoes.append("")
        recomendacoes.append("- *** URGENTE: Investigar pagamentos duplicados ***")
        recomendacoes.append("- Revisar processos de controle de pagamentos")
        recomendacoes.append("- Implementar validacao anti-duplicidade em tempo real")
        recomendacoes.append("- Auditoria nos casos identificados")
    
    # NOVO: Adicionar recomendações para ausência de dados
    if metrics.get('total_registros_incompletos', 0) > 0:
        recomendacoes.append("")
        recomendacoes.append("- *** ATENCAO: Corrigir dados ausentes ***")
        recomendacoes.append("- Revisar processos de coleta de dados")
        recomendacoes.append("- Implementar validacao de campos obrigatorios")
        recomendacoes.append("- Treinamento da equipe de insercao de dados")
    
    for recomendacao in recomendacoes:
        pdf.cell(0, 7, pdf.safe_text(recomendacao), 0, 1)
    
    # Salvar PDF em buffer
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1', 'replace')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)
    
    return pdf_output

def gerar_relatorio_excel(dados, tipo_relatorio):
    """Gera relatório em Excel"""
    output = io.BytesIO()
    
    metrics = processar_dados(dados)
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Sheet de resumo - CORREÇÃO: Formatação brasileira
        resumo = pd.DataFrame({
            'Metrica': [
                'Total de Pagamentos',
                'Beneficiarios Unicos (Pagamentos)',
                'Diferenca (Pagamentos - Beneficiarios)',
                'CPFs com Pagamentos Duplicados',
                'Valor Total em Duplicidades',
                'Projetos Ativos',
                'Contas Abertas',
                'Contas Unicas',
                'Valor Total Investido',
                'Data de Emissao'
            ],
            'Valor': [
                formatar_brasileiro(metrics.get('total_pagamentos', 0), 'numero'),
                formatar_brasileiro(metrics.get('beneficiarios_unicos', 0), 'numero'),
                formatar_brasileiro(metrics.get('total_pagamentos', 0) - metrics.get('beneficiarios_unicos', 0), 'numero'),
                formatar_brasileiro(metrics.get('pagamentos_duplicados', 0), 'numero'),
                formatar_brasileiro(metrics.get('valor_total_duplicados', 0), 'monetario') if metrics.get('valor_total_duplicados', 0) > 0 else "R$ 0,00",
                formatar_brasileiro(metrics.get('projetos_ativos', 0), 'numero'),
                formatar_brasileiro(metrics.get('total_contas', 0), 'numero'),
                formatar_brasileiro(metrics.get('contas_unicas', 0), 'numero'),
                formatar_brasileiro(metrics.get('valor_total', 0), 'monetario') if metrics.get('valor_total', 0) > 0 else "N/A",
                datetime.now().strftime('%d/%m/%Y %H:%M')
            ]
        })
        resumo.to_excel(writer, sheet_name='Resumo Executivo', index=False)
        
        # Sheet de análise de duplicidades
        if not metrics['resumo_duplicidades'].empty:
            # CORREÇÃO: Formatar valores monetários no resumo
            df_duplicidades = metrics['resumo_duplicidades'].copy()
            if 'Valor_Total' in df_duplicidades.columns:
                df_duplicidades['Valor_Total_Formatado'] = df_duplicidades['Valor_Total'].apply(
                    lambda x: formatar_brasileiro(x, 'monetario') if pd.notna(x) else 'R$ 0,00'
                )
            df_duplicidades.to_excel(writer, sheet_name='Resumo_Duplicidades', index=False)
        
        # Sheet com detalhes completos dos duplicados
        if not metrics['detalhes_duplicados'].empty:
            metrics['detalhes_duplicados'].to_excel(writer, sheet_name='Detalhes_Duplicados', index=False)
        
        # Sheets com dados completos de pagamentos
        if not dados['pagamentos'].empty:
            dados['pagamentos'].to_excel(writer, sheet_name='Pagamentos_Completo', index=False)
            
            # Sheet adicional com colunas principais
            colunas_principais = []
            # Adicionar colunas base
            for col in ['CPF', 'Projeto', 'Valor', 'Status']:
                if col in dados['pagamentos'].columns:
                    colunas_principais.append(col)
            
            # Adicionar beneficiário
            coluna_benef = obter_coluna_beneficiario(dados['pagamentos'])
            if coluna_benef:
                colunas_principais.append(coluna_benef)
            
            # Adicionar data
            coluna_data = obter_coluna_data(dados['pagamentos'])
            if coluna_data:
                colunas_principais.append(coluna_data)
            
            # Adicionar número da conta
            coluna_conta = obter_coluna_conta(dados['pagamentos'])
            if coluna_conta:
                colunas_principais.append(coluna_conta)
            
            if colunas_principais:
                dados['pagamentos'][colunas_principais].to_excel(writer, sheet_name='Pagamentos_Principais', index=False)
        
        if not dados['contas'].empty:
            dados['contas'].to_excel(writer, sheet_name='Abertura_Contas_Completo', index=False)
        
        # Sheet de estatísticas detalhadas - CORREÇÃO: Formatação brasileira
        estatisticas = pd.DataFrame({
            'Estatistica': [
                'Tipo de Relatorio',
                'Total de Registros Processados',
                'Valor Total dos Pagamentos',
                'Media por Beneficiario',
                'Taxa de Duplicidade',
                'Data de Geracao',
                'Status do Relatorio'
            ],
            'Valor': [
                tipo_relatorio,
                formatar_brasileiro(metrics.get('total_pagamentos', 0) + metrics.get('total_contas', 0), 'numero'),
                formatar_brasileiro(metrics.get('valor_total', 0), 'monetario') if metrics.get('valor_total', 0) > 0 else "N/A",
                formatar_brasileiro(metrics.get('valor_total', 0)/metrics.get('beneficiarios_unicos', 1), 'monetario') if metrics.get('valor_total', 0) > 0 else "N/A",
                f"{(metrics.get('pagamentos_duplicados', 0)/metrics.get('beneficiarios_unicos', 1)*100 if metrics.get('beneficiarios_unicos', 0) > 0 else 0):.1f}%" if metrics.get('pagamentos_duplicados', 0) > 0 else "0%",
                datetime.now().strftime('%d/%m/%Y %H:%M'),
                'CONCLUIDO'
            ]
        })
        estatisticas.to_excel(writer, sheet_name='Estatisticas_Detalhadas', index=False)
    
    output.seek(0)
    return output

def mostrar_dashboard(dados):
    st.header("📊 Dashboard Executivo - POT")
    
    # Processar dados
    metrics = processar_dados(dados)
    
    # Verificar se há dados carregados
    dados_carregados = any([not df.empty for df in dados.values()])
    
    if not dados_carregados:
        st.warning("📁 **Nenhum dado carregado ainda**")
        st.info("""
        **Para ver o dashboard:**
        1. Use o menu lateral para carregar as planilhas de Pagamentos e Abertura de Contas
        2. Formato suportado: XLSX ou CSV
        3. Os gráficos serão atualizados automaticamente
        """)
        return
    
    # NOVO: Alertas de ausência de dados
    if metrics.get('total_registros_incompletos', 0) > 0:
        st.error(f"🚨 **ALERTA: AUSÊNCIA DE DADOS IDENTIFICADA** - {formatar_brasileiro(metrics.get('total_registros_incompletos', 0), 'numero')} registros com CPF ausente ou inválido")
        
        with st.expander("🔍 **Ver Detalhes dos Dados Ausentes**", expanded=False):
            st.warning("**Registros com dados incompletos:**")
            
            if metrics.get('colunas_com_ausencia'):
                for coluna, qtd in metrics['colunas_com_ausencia'].items():
                    if qtd > 0:
                        st.write(f"- {formatar_brasileiro(qtd, 'numero')} registros sem {coluna}")
            
            if not metrics['resumo_ausencias'].empty:
                st.dataframe(
                    metrics['resumo_ausencias'],
                    use_container_width=True,
                    hide_index=True
                )
    
    # Métricas principais - CORREÇÃO: Formatação brasileira
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Beneficiários Únicos", formatar_brasileiro(metrics.get('beneficiarios_unicos', 0), 'numero'))
    
    with col2:
        st.metric("Total de Pagamentos", formatar_brasileiro(metrics.get('total_pagamentos', 0), 'numero'))
    
    with col3:
        st.metric("Contas Abertas", formatar_brasileiro(metrics.get('total_contas', 0), 'numero'))
    
    with col4:
        st.metric("Projetos Ativos", formatar_brasileiro(metrics.get('projetos_ativos', 0), 'numero'))
    
    # Valor total se disponível - CORREÇÃO: Formatação brasileira
    if metrics.get('valor_total', 0) > 0:
        st.metric("Valor Total dos Pagamentos", formatar_brasileiro(metrics['valor_total'], 'monetario'))
    
    # Análise de Duplicidades - DESTAQUE
    if metrics.get('pagamentos_duplicados', 0) > 0:
        st.error("🚨 **ALERTA: PAGAMENTOS DUPLICADOS IDENTIFICADOS**")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                "CPFs com Duplicidade", 
                formatar_brasileiro(metrics.get('pagamentos_duplicados', 0), 'numero'),
                delta=f"{formatar_brasileiro(metrics.get('pagamentos_duplicados', 0), 'numero')} casos"
            )
        
        with col2:
            diff = metrics.get('total_pagamentos', 0) - metrics.get('beneficiarios_unicos', 0)
            st.metric(
                "Diferença Identificada", 
                formatar_brasileiro(diff, 'numero'),
                delta=f"{formatar_brasileiro(diff, 'numero')} pagamentos extras"
            )
        
        with col3:
            if metrics.get('valor_total_duplicados', 0) > 0:
                st.metric(
                    "Valor em Duplicidades", 
                    formatar_brasileiro(metrics.get('valor_total_duplicados', 0), 'monetario'),
                    delta="Valor a investigar"
                )
        
        # Mostrar resumo dos casos de duplicidade
        with st.expander("🔍 **Ver Detalhes dos Pagamentos Duplicados**", expanded=False):
            if not metrics['resumo_duplicidades'].empty:
                # Adicionar número da conta ao display se disponível
                colunas_display = ['CPF', 'Quantidade_Pagamentos', 'Beneficiario', 'Projeto']
                if 'Num_Cartao' in metrics['resumo_duplicidades'].columns:
                    colunas_display.append('Num_Cartao')
                
                # CORREÇÃO: Formatar valores no dataframe de exibição
                df_display = metrics['resumo_duplicidades'][colunas_display].copy()
                if 'Valor_Total' in metrics['resumo_duplicidades'].columns:
                    df_display['Valor_Total'] = metrics['resumo_duplicidades']['Valor_Total'].apply(
                        lambda x: formatar_brasileiro(x, 'monetario') if pd.notna(x) else 'R$ 0,00'
                    )
                    colunas_display.append('Valor_Total')
                
                st.dataframe(
                    df_display,
                    use_container_width=True,
                    hide_index=True
                )
                
                # Botão para download dos detalhes
                if not metrics['detalhes_duplicados'].empty:
                    csv = metrics['detalhes_duplicados'].to_csv(index=False, sep=';')
                    st.download_button(
                        label="📥 Baixar Detalhes Completos (CSV)",
                        data=csv,
                        file_name=f"pagamentos_duplicados_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )
    
    # Gráficos
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Distribuição por Projeto (Pagamentos)")
        if not dados['pagamentos'].empty and 'Projeto' in dados['pagamentos'].columns:
            # Usar value_counts() para agrupar por projeto único
            projetos_count = dados['pagamentos']['Projeto'].value_counts().reset_index()
            projetos_count.columns = ['Projeto', 'Quantidade']
            
            fig = px.pie(projetos_count, values='Quantidade', names='Projeto',
                        title="Pagamentos por Projeto")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("📊 Gráfico de projetos aparecerá aqui após carregar os dados de pagamentos")
    
    with col2:
        st.subheader("Evolução Mensal de Pagamentos")
        if not dados['pagamentos'].empty and 'Data' in dados['pagamentos'].columns:
            try:
                # CORREÇÃO: Usar datas já processadas
                dados_pagamentos = dados['pagamentos'].copy()
                
                # Tentar converter para data (já deve estar processada)
                dados_pagamentos['Data_Processada'] = pd.to_datetime(
                    dados_pagamentos['Data'], 
                    format='%d/%m/%Y', 
                    errors='coerce'
                )
                
                # Se não conseguir, tentar formato original
                if dados_pagamentos['Data_Processada'].isna().all():
                    dados_pagamentos['Data_Processada'] = pd.to_datetime(
                        dados_pagamentos['Data'], 
                        errors='coerce'
                    )
                
                dados_pagamentos = dados_pagamentos.dropna(subset=['Data_Processada'])
                dados_pagamentos['Mês'] = dados_pagamentos['Data_Processada'].dt.to_period('M').astype(str)
                
                evolucao = dados_pagamentos.groupby('Mês').size().reset_index()
                evolucao.columns = ['Mês', 'Pagamentos']
                
                fig = px.line(evolucao, x='Mês', y='Pagamentos', 
                             markers=True, line_shape='spline',
                             title="Evolução de Pagamentos por Mês")
                st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.info(f"📊 Formato de data não reconhecido. Erro: {str(e)}")
        else:
            st.info("📊 Gráfico de evolução aparecerá aqui após carregar os dados")
    
    # Tabelas recentes
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Últimos Pagamentos")
        if not dados['pagamentos'].empty:
            # Mostrar colunas mais relevantes incluindo número da conta e data
            colunas_pagamentos = [col for col in ['Data', 'Data Pagto', 'Beneficiário', 'CPF', 'Projeto', 'Valor', 'Status'] 
                                if col in dados['pagamentos'].columns]
            
            # Adicionar número da conta se disponível
            for col_conta in ['Num Cartao', 'Num_Cartao', 'Conta', 'Numero Conta']:
                if col_conta in dados['pagamentos'].columns:
                    colunas_pagamentos.append(col_conta)
                    break
            
            if colunas_pagamentos:
                # CORREÇÃO: Formatar valores monetários na exibição
                df_display = dados['pagamentos'][colunas_pagamentos].head(10).copy()
                if 'Valor' in df_display.columns and 'Valor_Limpo' in dados['pagamentos'].columns:
                    # Usar os índices para mapear os valores limpos
                    for idx in df_display.index:
                        if idx in dados['pagamentos'].index:
                            valor_limpo = dados['pagamentos'].loc[idx, 'Valor_Limpo']
                            df_display.loc[idx, 'Valor'] = formatar_brasileiro(valor_limpo, 'monetario')
                
                st.dataframe(df_display, use_container_width=True)
            else:
                st.dataframe(dados['pagamentos'].head(10), use_container_width=True)
        else:
            st.info("📋 Tabela de pagamentos aparecerá aqui")
    
    with col2:
        st.subheader("Últimas Contas Abertas")
        if not dados['contas'].empty:
            # Mostrar colunas mais relevantes
            colunas_contas = [col for col in ['Data', 'Nome', 'CPF', 'Projeto', 'Agência'] 
                            if col in dados['contas'].columns]
            if colunas_contas:
                st.dataframe(dados['contas'][colunas_contas].head(10), use_container_width=True)
            else:
                st.dataframe(dados['contas'].head(10), use_container_width=True)
        else:
            st.info("📋 Tabela de contas aparecerá aqui")

# FUNÇÃO: mostrar_importacao
def mostrar_importacao():
    st.header("📥 Estrutura das Planilhas")
    
    st.info("""
    **💡 USE O MENU LATERAL PARA CARREGAR AS PLANILHAS!**
    """)
    
    # Estrutura esperada das planilhas
    with st.expander("📋 Estrutura das Planilhas Necessárias"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**📋 Planilha de Pagamentos:**")
            st.code("""
Data ou Data Pagto (dd/mm/aaaa)
Beneficiário (texto)
CPF (número)
Projeto (texto)
Valor (número)
Num Cartao (número da conta)
Status (texto)
*Outras colunas opcionais*
            """)
        
        with col2:
            st.markdown("**🏦 Planilha de Abertura de Contas:**")
            st.code("""
Data (dd/mm/aaaa)
Nome (texto)
CPF (número)
Projeto (texto)
Agência (texto/número)
*Outras colunas opcionais*
            """)

# FUNÇÃO: mostrar_consultas
def mostrar_consultas(dados):
    st.header("🔍 Consultas de Dados")
    
    # Opções de consulta
    opcao_consulta = st.radio(
        "Tipo de consulta:",
        ["Por CPF", "Por Projeto", "Por Período"],
        horizontal=True
    )
    
    if opcao_consulta == "Por CPF":
        col1, col2 = st.columns([2, 1])
        with col1:
            cpf = st.text_input("Digite o CPF (apenas números):", placeholder="12345678900")
        with col2:
            if st.button("🔍 Buscar CPF", use_container_width=True):
                if cpf:
                    resultados = {}
                    if not dados['pagamentos'].empty and 'CPF' in dados['pagamentos'].columns:
                        resultados['pagamentos'] = dados['pagamentos'][dados['pagamentos']['CPF'].astype(str).str.contains(cpf)]
                    if not dados['contas'].empty and 'CPF' in dados['contas'].columns:
                        resultados['contas'] = dados['contas'][dados['contas']['CPF'].astype(str).str.contains(cpf)]
                    
                    st.session_state.resultados_consulta = resultados
                else:
                    st.warning("Por favor, digite um CPF para buscar")
    
    elif opcao_consulta == "Por Projeto":
        projeto = st.text_input("Digite o nome do projeto:")
        if st.button("🏢 Buscar por Projeto"):
            if projeto:
                resultados = {}
                if not dados['pagamentos'].empty and 'Projeto' in dados['pagamentos'].columns:
                    resultados['pagamentos'] = dados['pagamentos'][dados['pagamentos']['Projeto'].str.contains(projeto, case=False, na=False)]
                if not dados['contas'].empty and 'Projeto' in dados['contas'].columns:
                    resultados['contas'] = dados['contas'][dados['contas']['Projeto'].str.contains(projeto, case=False, na=False)]
                
                st.session_state.resultados_consulta = resultados
            else:
                st.warning("Por favor, digite um projeto para buscar")
    
    else:  # Por Período
        col1, col2 = st.columns(2)
        with col1:
            data_inicio = st.date_input("Data início:")
        with col2:
            data_fim = st.date_input("Data fim:")
        
        if st.button("📅 Buscar por Período"):
            if data_inicio and data_fim:
                st.info(f"Buscando dados de {data_inicio} a {data_fim}")
    
    # Área de resultados
    st.markdown("---")
    st.subheader("Resultados da Consulta")
    
    if 'resultados_consulta' in st.session_state:
        resultados = st.session_state.resultados_consulta
        
        if resultados.get('pagamentos') is not None and not resultados['pagamentos'].empty:
            st.markdown("**📋 Pagamentos Encontrados:**")
            
            # Mostrar colunas incluindo número da conta e data
            colunas_display = [col for col in ['Data', 'Data Pagto', 'Beneficiário', 'CPF', 'Projeto', 'Valor', 'Status'] 
                             if col in resultados['pagamentos'].columns]
            
            # Adicionar número da conta se disponível
            for col_conta in ['Num Cartao', 'Num_Cartao', 'Conta', 'Numero Conta']:
                if col_conta in resultados['pagamentos'].columns:
                    colunas_display.append(col_conta)
                    break
            
            if colunas_display:
                st.dataframe(resultados['pagamentos'][colunas_display], use_container_width=True)
            else:
                st.dataframe(resultados['pagamentos'], use_container_width=True)
        
        if resultados.get('contas') is not None and not resultados['contas'].empty:
            st.markdown("**🏦 Contas Encontradas:**")
            st.dataframe(resultados['contas'], use_container_width=True)
        
        if not any([not df.empty if df is not None else False for df in resultados.values()]):
            st.info("Nenhum resultado encontrado para a consulta.")
    else:
        st.info("Os resultados aparecerão aqui após a busca")

# FUNÇÃO: mostrar_relatorios
def mostrar_relatorios(dados):
    st.header("📋 Gerar Relatórios")
    
    # Análise preliminar para mostrar alertas
    metrics = processar_dados(dados)
    
    if metrics.get('pagamentos_duplicados', 0) > 0:
        st.warning(f"🚨 **ALERTA:** Foram identificados {formatar_brasileiro(metrics.get('pagamentos_duplicados', 0), 'numero')} CPFs com pagamentos duplicados")
        st.info(f"📊 **Diferença:** {formatar_brasileiro(metrics.get('total_pagamentos', 0), 'numero')} pagamentos para {formatar_brasileiro(metrics.get('beneficiarios_unicos', 0), 'numero')} beneficiários")
    
    # NOVO: Alerta de ausência de dados
    if metrics.get('total_registros_incompletos', 0) > 0:
        st.error(f"🚨 **ALERTA:** {formatar_brasileiro(metrics.get('total_registros_incompletos', 0), 'numero')} registros com dados incompletos identificados")
    
    st.info("""
    **Escolha o formato do relatório:**
    - **📄 PDF Executivo**: Relatório visual e profissional para apresentações
    - **📊 Excel Completo**: Dados detalhados para análise técnica
    """)
    
    # Opções de relatório
    tipo_relatorio = st.selectbox(
        "Selecione o tipo de relatório:",
        [
            "Relatório Geral Completo",
            "Relatório de Pagamentos", 
            "Relatório de Abertura de Contas",
            "Relatório por Projeto",
            "Dashboard Executivo"
        ]
    )
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Botão para gerar PDF Executivo
        if st.button("📄 Gerar PDF Executivo", type="primary", use_container_width=True):
            with st.spinner("Gerando relatório PDF executivo..."):
                try:
                    pdf_buffer = gerar_pdf_executivo(dados, tipo_relatorio)
                    
                    st.success("✅ PDF Executivo gerado com sucesso!")
                    st.info("💡 **Ideal para:** Apresentações, reuniões e análise executiva")
                    
                    st.download_button(
                        label="📥 Baixar PDF Executivo",
                        data=pdf_buffer.getvalue(),
                        file_name=f"relatorio_executivo_pot_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                        mime="application/pdf",
                        type="primary"
                    )
                except Exception as e:
                    st.error(f"❌ Erro ao gerar PDF: {str(e)}")
    
    with col2:
        # Botão para gerar Excel
        if st.button("📊 Gerar Excel Completo", type="secondary", use_container_width=True):
            with st.spinner("Gerando relatório Excel completo..."):
                try:
                    excel_buffer = gerar_relatorio_excel(dados, tipo_relatorio)
                    
                    st.success("✅ Excel Completo gerado com sucesso!")
                    st.info("💡 **Ideal para:** Análise detalhada e processamento de dados")
                    
                    st.download_button(
                        label="📥 Baixar Excel Completo",
                        data=excel_buffer.getvalue(),
                        file_name=f"relatorio_completo_pot_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary"
                    )
                except Exception as e:
                    st.error(f"❌ Erro ao gerar Excel: {str(e)}")

# FUNÇÃO: mostrar_rodape
def mostrar_rodape():
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**SMDET**")
        st.markdown("Secretaria Municipal do Desenvolvimento Econômico e Trabalho")
    
    with col2:
        st.markdown("**Suporte Técnico**")
        st.markdown("rolivatto@prefeitura.sp.gov.br")
    
    with col3:
        st.markdown("**Versão**")
        st.markdown("1.0 - Novembro 2024")

def main():
    email = autenticar()
    
    if not email:
        st.info("👆 Informe seu email institucional para acessar o sistema")
        return
    
    st.success(f"✅ Acesso permitido: {email}")
    
    # Carregar dados
    dados = carregar_dados()
    
    # Menu principal
    st.title("🏛️ Sistema POT - Programa Operação Trabalho")
    st.markdown("Desenvolvido para Secretaria Municipal do Desenvolvimento Econômico e Trabalho")
    st.markdown("---")
    
    # Abas
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Dashboard", 
        "📥 Importar Dados", 
        "🔍 Consultas", 
        "📋 Relatórios"
    ])
    
    with tab1:
        mostrar_dashboard(dados)
    
    with tab2:
        mostrar_importacao()
    
    with tab3:
        mostrar_consultas(dados)
    
    with tab4:
        mostrar_relatorios(dados)
    
    mostrar_rodape()

if __name__ == "__main__":
    main()
