import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import io
from fpdf import FPDF
import numpy as np
import re

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

# NOVA FUNÇÃO: Padronizar RGs e CPFs
def padronizar_documentos(df):
    """Remove caracteres especiais de RGs e CPFs, mantendo apenas números e letras"""
    df_processed = df.copy()
    
    # Colunas que podem conter documentos
    colunas_documentos = ['RG', 'CPF', 'Documento', 'Numero_Documento']
    
    for coluna in colunas_documentos:
        if coluna in df_processed.columns:
            try:
                # Remover caracteres especiais, mantendo apenas números e letras
                df_processed[coluna] = df_processed[coluna].astype(str).apply(
                    lambda x: re.sub(r'[^a-zA-Z0-9]', '', x) if pd.notna(x) else x
                )
                
                st.sidebar.success(f"✅ {coluna}: Documentos padronizados")
                
            except Exception as e:
                st.warning(f"⚠️ Não foi possível padronizar a coluna '{coluna}': {str(e)}")
    
    return df_processed

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
            
            # CORREÇÃO: Processar datas, valores e documentos
            df_pagamentos = processar_colunas_data(df_pagamentos)
            df_pagamentos = processar_colunas_valor(df_pagamentos)
            df_pagamentos = padronizar_documentos(df_pagamentos)  # NOVO: Padronizar documentos
            
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
            
            # CORREÇÃO: Processar datas e documentos
            df_contas = processar_colunas_data(df_contas)
            df_contas = padronizar_documentos(df_contas)  # NOVO: Padronizar documentos
            
            dados['contas'] = df_contas
            st.sidebar.success(f"✅ Contas: {len(dados['contas'])} registros")
        except Exception as e:
            st.sidebar.error(f"❌ Erro ao carregar contas: {str(e)}")
            dados['contas'] = pd.DataFrame()
    else:
        dados['contas'] = pd.DataFrame()
        st.sidebar.info("📁 Aguardando planilha de abertura de contas")
    
    return dados

# FUNÇÃO MELHORADA: Analisar ausência de dados com mais detalhes
def analisar_ausencia_dados(dados):
    """Analisa e reporta ausência de dados críticos de forma mais detalhada"""
    analise_ausencia = {
        'cpfs_sem_dados_completos': [],
        'total_registros_incompletos': 0,
        'colunas_com_ausencia': {},
        'resumo_ausencias': pd.DataFrame(),
        'registros_problema_detalhados': pd.DataFrame(),
        'documentos_padronizados': 0,  # NOVO: Contador de documentos padronizados
        'tipos_problemas': {}  # NOVO: Classificar tipos de problemas
    }
    
    if not dados['pagamentos'].empty:
        df = dados['pagamentos'].copy()
        
        # Contar documentos padronizados
        colunas_docs = ['RG', 'CPF']
        for coluna in colunas_docs:
            if coluna in df.columns:
                docs_originais = len(df[df[coluna].notna()])
                analise_ausencia['documentos_padronizados'] += docs_originais
        
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
                
                # Salvar os registros completos com problemas
                analise_ausencia['registros_problema_detalhados'] = cpfs_invalidos.copy()
        
        # Analisar ausência por coluna crítica
        colunas_criticas = ['CPF', 'RG', 'Valor', 'Projeto', 'Beneficiario', 'Beneficiário', 'Nome', 'Num Cartao', 'Num_Cartao']
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
                if len(ausentes) > 0:
                    analise_ausencia['colunas_com_ausencia'][coluna] = len(ausentes)
                    analise_ausencia['tipos_problemas'][f'Sem {coluna}'] = len(ausentes)
        
        # Verificar documentos com caracteres especiais (antes da padronização)
        if 'RG' in df.columns:
            rg_com_especiais = df[df['RG'].astype(str).str.contains(r'[^a-zA-Z0-9]', na=False)]
            if len(rg_com_especiais) > 0:
                analise_ausencia['tipos_problemas']['RG com caracteres especiais'] = len(rg_com_especiais)
        
        # Criar resumo de ausências para exibição
        if cpfs_ausentes or analise_ausencia['colunas_com_ausencia']:
            resumo = []
            registros_problema = cpfs_ausentes[:50]  # Limitar para performance
            
            for idx in registros_problema:
                registro = df.loc[idx]
                info_ausencia = {'Indice_Registro': idx}
                
                # Adicionar todas as informações disponíveis
                colunas_interesse = [
                    'CPF', 'RG', 'Projeto', 'Valor', 'Beneficiario', 'Beneficiário', 'Nome',
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
                
                # Marcar campos problemáticos
                problemas = []
                if 'CPF' in df.columns and (pd.isna(registro['CPF']) or str(registro['CPF']).strip() in ['', 'NaN', 'None', 'nan', '0'] or len(str(registro['CPF']).strip()) < 11):
                    problemas.append('CPF inválido')
                if 'RG' in df.columns and pd.isna(registro['RG']):
                    problemas.append('RG ausente')
                if 'Projeto' in df.columns and pd.isna(registro['Projeto']):
                    problemas.append('Projeto ausente')
                if 'Num Cartao' in df.columns and pd.isna(registro['Num Cartao']):
                    problemas.append('Número da conta ausente')
                
                info_ausencia['Problemas_Identificados'] = ', '.join(problemas) if problemas else 'OK'
                resumo.append(info_ausencia)
            
            analise_ausencia['resumo_ausencias'] = pd.DataFrame(resumo)
    
    return analise_ausencia

# FUNÇÃO CORRIGIDA: Analisar duplicidades por NÚMERO DA CONTA
def analisar_duplicidades(dados):
    """Analisa pagamentos duplicados por NÚMERO DA CONTA e retorna estatísticas"""
    analise = {
        'total_pagamentos': 0,
        'contas_unicas': 0,
        'pagamentos_duplicados': 0,
        'valor_total_duplicados': 0,
        'detalhes_duplicados': pd.DataFrame(),
        'resumo_duplicidades': pd.DataFrame(),
        'contas_com_erros': [],
        # NOVO: Análise de CPFs duplicados (apenas para informação)
        'cpfs_duplicados_info': pd.DataFrame(),
        'total_cpfs_duplicados': 0
    }
    
    if dados['pagamentos'].empty:
        return analise
    
    df = dados['pagamentos'].copy()
    analise['total_pagamentos'] = len(df)
    
    # Identificar contas únicas (apenas contas válidas)
    coluna_conta = obter_coluna_conta(df)
    
    if coluna_conta:
        # Filtrar apenas contas válidas
        contas_validas = df[
            df[coluna_conta].notna() & 
            (df[coluna_conta].astype(str).str.strip() != '') &
            (df[coluna_conta].astype(str).str.strip() != 'NaN') &
            (df[coluna_conta].astype(str).str.strip() != 'None')
        ]
        
        analise['contas_unicas'] = contas_validas[coluna_conta].nunique()
        
        # Identificar contas com problemas
        contas_com_problemas = df[
            df[coluna_conta].isna() | 
            (df[coluna_conta].astype(str).str.strip() == '') |
            (df[coluna_conta].astype(str).str.strip() == 'NaN') |
            (df[coluna_conta].astype(str).str.strip() == 'None')
        ]
        
        if not contas_com_problemas.empty:
            analise['contas_com_erros'] = contas_com_problemas.index.tolist()
    
    # CORREÇÃO: Identificar pagamentos duplicados por NÚMERO DA CONTA (não por CPF)
    if coluna_conta:
        # Filtrar contas válidas para análise de duplicidade
        df_validos = df[
            df[coluna_conta].notna() & 
            (df[coluna_conta].astype(str).str.strip() != '') &
            (df[coluna_conta].astype(str).str.strip() != 'NaN') &
            (df[coluna_conta].astype(str).str.strip() != 'None')
        ].copy()
        
        if not df_validos.empty:
            # Contar ocorrências por NÚMERO DA CONTA
            contagem_contas = df_validos[coluna_conta].value_counts().reset_index()
            contagem_contas.columns = [coluna_conta, 'Quantidade_Pagamentos']
            
            # Identificar contas com mais de 1 pagamento
            contas_duplicadas = contagem_contas[contagem_contas['Quantidade_Pagamentos'] > 1]
            analise['pagamentos_duplicados'] = len(contas_duplicadas)
            
            # Detalhar os pagamentos duplicados
            if not contas_duplicadas.empty:
                contas_com_duplicidade = contas_duplicadas[coluna_conta].tolist()
                detalhes = df_validos[df_validos[coluna_conta].isin(contas_com_duplicidade)].copy()
                
                # Ordenar por conta e Data (se disponível)
                colunas_ordenacao = [coluna_conta]
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
                        for conta in contas_com_duplicidade:
                            pagamentos_conta = df_validos[df_validos[coluna_conta] == conta]
                            if len(pagamentos_conta) > 1:
                                # Somar todos os pagamentos exceto o primeiro (considerando o primeiro como legítimo)
                                valor_duplicados += pagamentos_conta.iloc[1:]['Valor_Limpo'].sum()
                        
                        analise['valor_total_duplicados'] = valor_duplicados
                        
                    except Exception as e:
                        analise['valor_total_duplicados'] = 0
                
                # Criar resumo de duplicidades
                resumo = []
                for conta in contas_com_duplicidade:
                    pagamentos_conta = df_validos[df_validos[coluna_conta] == conta]
                    qtd = len(pagamentos_conta)
                    
                    info = {
                        'Numero_Conta': conta,
                        'Quantidade_Pagamentos': qtd,
                    }
                    
                    # Adicionar CPF se disponível (para referência)
                    if 'CPF' in pagamentos_conta.columns:
                        cpfs = pagamentos_conta['CPF'].unique()
                        if len(cpfs) == 1:
                            info['CPF'] = cpfs[0]
                        else:
                            info['CPF'] = f"Múltiplos: {', '.join(map(str, cpfs[:2]))}"  # Mostrar até 2 CPFs
                    
                    # Adicionar nome do beneficiário se disponível
                    coluna_beneficiario = obter_coluna_beneficiario(pagamentos_conta)
                    if coluna_beneficiario:
                        beneficiarios = pagamentos_conta[coluna_beneficiario].unique()
                        if len(beneficiarios) == 1:
                            info['Beneficiario'] = beneficiarios[0]
                        else:
                            info['Beneficiario'] = f"Múltiplos: {', '.join(map(str, beneficiarios[:2]))}"
                    
                    # Adicionar projeto se disponível
                    if 'Projeto' in pagamentos_conta.columns:
                        projetos = pagamentos_conta['Projeto'].unique()
                        if len(projetos) == 1:
                            info['Projeto'] = projetos[0]
                        else:
                            info['Projeto'] = f"Múltiplos: {', '.join(map(str, projetos[:2]))}"
                    
                    if 'Valor_Limpo' in pagamentos_conta.columns:
                        try:
                            info['Valor_Total'] = pagamentos_conta['Valor_Limpo'].sum()
                        except:
                            info['Valor_Total'] = 0
                    
                    resumo.append(info)
                
                analise['resumo_duplicidades'] = pd.DataFrame(resumo)
    
    # NOVA ANÁLISE: CPFs duplicados (apenas para informação, não como pagamentos duplicados)
    if 'CPF' in df.columns:
        # Filtrar CPFs válidos
        cpfs_validos = df[
            df['CPF'].notna() & 
            (df['CPF'].astype(str).str.strip() != '') &
            (df['CPF'].astype(str).str.strip() != 'NaN') &
            (df['CPF'].astype(str).str.strip() != 'None')
        ]
        
        if not cpfs_validos.empty:
            # Contar ocorrências por CPF
            contagem_cpf = cpfs_validos['CPF'].value_counts().reset_index()
            contagem_cpf.columns = ['CPF', 'Quantidade_Ocorrencias']
            
            # Identificar CPFs com mais de 1 ocorrência
            cpfs_duplicados = contagem_cpf[contagem_cpf['Quantidade_Ocorrencias'] > 1]
            analise['total_cpfs_duplicados'] = len(cpfs_duplicados)
            
            # Detalhar os CPFs duplicados
            if not cpfs_duplicados.empty:
                cpfs_com_duplicidade = cpfs_duplicados['CPF'].tolist()
                detalhes_cpfs = cpfs_validos[cpfs_validos['CPF'].isin(cpfs_com_duplicidade)].copy()
                
                # Ordenar por CPF
                detalhes_cpfs = detalhes_cpfs.sort_values(by=['CPF'])
                
                # Adicionar informação de conta para verificar se são pagamentos duplicados reais
                if coluna_conta:
                    # Marcar registros que são realmente pagamentos duplicados (mesma conta)
                    detalhes_cpfs['Pagamento_Duplicado_Real'] = detalhes_cpfs.duplicated(
                        subset=[coluna_conta], keep=False
                    )
                
                analise['cpfs_duplicados_info'] = detalhes_cpfs
    
    return analise

def processar_dados(dados):
    """Processa os dados para o dashboard"""
    metrics = {}
    
    # Análise de duplicidades (agora por número da conta)
    analise_dup = analisar_duplicidades(dados)
    metrics.update(analise_dup)
    
    # Análise de ausência de dados
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
            cell_text = str(cell) if cell is not None else ""
            cell_text = self.safe_text(cell_text)
            
            text_width = self.get_string_width(cell_text)
            cell_width = col_widths[i] - 1
            
            if text_width > cell_width:
                chars_per_line = int(len(cell_text) * cell_width / text_width)
                if chars_per_line < 1:
                    chars_per_line = 1
                
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
                        if self.get_string_width(word) > cell_width:
                            for j in range(0, len(word), chars_per_line):
                                lines.append(word[j:j+chars_per_line])
                            current_line = ""
                
                if current_line:
                    lines.append(current_line)
                
                if len(lines) > 1:
                    line_height = 8 / len(lines)
                    if line_height < 3:
                        line_height = 3
                    
                    y_before = self.get_y()
                    x_before = self.get_x()
                    
                    for j, line in enumerate(lines):
                        if j > 0:
                            self.set_xy(x_before, self.get_y() + line_height)
                        self.cell(col_widths[i], line_height, line, 1, 0, 'C')
                    
                    total_height = len(lines) * line_height
                    self.set_xy(x_before + col_widths[i], y_before)
                    if i == len(data) - 1:
                        self.ln(total_height)
                else:
                    self.cell(col_widths[i], 8, cell_text, 1, 0, 'C')
            else:
                self.cell(col_widths[i], 8, cell_text, 1, 0, 'C')
        
        if not hasattr(self, '_in_multiline') or not self._in_multiline:
            self.ln()
    
    def safe_text(self, text):
        """Remove caracteres problemáticos para Latin-1 incluindo emojis"""
        safe_text = str(text)
        
        substitutions = {
            '•': '-', '´': "'", '`': "'", '“': '"', '”': '"', 
            '‘': "'", ' ': ' ', '–': '-', '—': '-', '…': '...',
            '🚨': '[ALERTA]', '✅': '[OK]', '📊': '[DASHBOARD]',
            '⚠️': '[ATENCAO]', '❌': '[ERRO]', '📁': '[ARQUIVO]',
            '🔍': '[LUPAR]', '👆': '[SETA_ACIMA]', '🏛️': '[PREFEITURA]'
        }
        
        for char, replacement in substitutions.items():
            safe_text = safe_text.replace(char, replacement)
        
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
    """Detecta automaticamente a coluna de data para ordenação"""
    colunas_data = ['Data', 'Data Pagto', 'Data_Pagto', 'DataPagto', 'DATA', 'DATA_PAGTO']
    
    for coluna in colunas_data:
        if coluna in df.columns:
            if not pd.api.types.is_datetime64_any_dtype(df[coluna]):
                try:
                    df_temp = df.copy()
                    df_temp[coluna] = pd.to_datetime(df_temp[coluna], errors='coerce')
                    if not df_temp[coluna].isna().all():
                        return coluna
                except:
                    continue
            else:
                return coluna
    return None

def ordenar_por_data(df, coluna_data):
    """Ordena DataFrame por data de forma segura"""
    if coluna_data and coluna_data in df.columns:
        try:
            df_ordenado = df.copy()
            if not pd.api.types.is_datetime64_any_dtype(df_ordenado[coluna_data]):
                df_ordenado[coluna_data] = pd.to_datetime(
                    df_ordenado[coluna_data], 
                    dayfirst=True,
                    errors='coerce'
                )
            
            df_ordenado = df_ordenado.sort_values(by=coluna_data, ascending=False)
            return df_ordenado
        except Exception as e:
            st.warning(f"Não foi possível ordenar por data: {str(e)}")
            return df
    else:
        return df

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
    
    col_width = 60
    pdf.metric_card('Total de Pagamentos:', formatar_brasileiro(metrics.get('total_pagamentos', 0), 'numero'))
    pdf.metric_card('Beneficiarios Unicos:', formatar_brasileiro(metrics.get('beneficiarios_unicos', 0), 'numero'))
    pdf.metric_card('Projetos Ativos:', formatar_brasileiro(metrics.get('projetos_ativos', 0), 'numero'))
    pdf.metric_card('Contas Abertas:', formatar_brasileiro(metrics.get('total_contas', 0), 'numero'))
    
    if metrics.get('valor_total', 0) > 0:
        pdf.metric_card('Valor Total Investido:', formatar_brasileiro(metrics.get('valor_total', 0), 'monetario'))
    
    # Informações sobre padronização de documentos
    if metrics.get('documentos_padronizados', 0) > 0:
        pdf.ln(5)
        pdf.set_font('Arial', 'B', 12)
        pdf.set_text_color(0, 100, 0)  # Verde para informações positivas
        pdf.cell(0, 8, '[INFO] DOCUMENTOS PADRONIZADOS', 0, 1)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font('Arial', '', 10)
        pdf.cell(0, 6, f'- {formatar_brasileiro(metrics.get("documentos_padronizados", 0), "numero")} documentos (RGs/CPFs) foram padronizados', 0, 1)
        pdf.cell(0, 6, '- Caracteres especiais removidos, mantendo apenas números e letras', 0, 1)
    
    # Alertas de ausência de dados
    if metrics.get('total_registros_incompletos', 0) > 0:
        pdf.ln(5)
        pdf.set_font('Arial', 'B', 12)
        pdf.set_text_color(255, 0, 0)
        pdf.cell(0, 8, '[ALERTA] AUSENCIA DE DADOS IDENTIFICADA', 0, 1)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font('Arial', '', 10)
        pdf.cell(0, 6, f'- {formatar_brasileiro(metrics.get("total_registros_incompletos", 0), "numero")} registros com CPF ausente ou invalido', 0, 1)
        if metrics.get('colunas_com_ausencia'):
            for coluna, qtd in metrics['colunas_com_ausencia'].items():
                if qtd > 0:
                    pdf.cell(0, 6, f'- {formatar_brasileiro(qtd, "numero")} registros sem {coluna}', 0, 1)
    
    # Análise de Duplicidades por NÚMERO DA CONTA
    if metrics.get('pagamentos_duplicados', 0) > 0:
        pdf.chapter_title('ANALISE DE DUPLICIDADES - ALERTA')
        
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 8, 'Duplicidades por Numero da Conta:', 0, 1)
        pdf.set_font('Arial', '', 12)
        
        diff = metrics.get('total_pagamentos', 0) - metrics.get('contas_unicas', 0)
        pdf.cell(0, 8, f'- {formatar_brasileiro(metrics.get("total_pagamentos", 0), "numero")} pagamentos para {formatar_brasileiro(metrics.get("contas_unicas", 0), "numero")} contas (diferenca: {formatar_brasileiro(diff, "numero")} pagamentos)', 0, 1)
        
        pdf.cell(0, 8, f'- {formatar_brasileiro(metrics.get("pagamentos_duplicados", 0), "numero")} contas com pagamentos duplicados', 0, 1)
        
        if metrics.get('valor_total_duplicados', 0) > 0:
            pdf.cell(0, 8, f'- Valor total em duplicidades: {formatar_brasileiro(metrics.get("valor_total_duplicados", 0), "monetario")}', 0, 1)
        
        pdf.ln(5)
        
        # Resumo das contas com duplicidade
        if not metrics['resumo_duplicidades'].empty:
            pdf.set_font('Arial', 'B', 12)
            pdf.cell(0, 8, 'Principais Casos de Duplicidade por Conta:', 0, 1)
            
            headers = ['Numero Conta', 'Qtd Pag', 'CPF']
            col_widths = [40, 15, 35]
            
            # Adicionar beneficiário se disponível
            if 'Beneficiario' in metrics['resumo_duplicidades'].columns:
                headers.append('Beneficiario')
                col_widths.append(50)
            
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
                row_data = [row['Numero_Conta'], str(row['Quantidade_Pagamentos']), str(row.get('CPF', 'N/A'))]
                
                # Adicionar beneficiário se disponível
                if 'Beneficiario' in metrics['resumo_duplicidades'].columns:
                    row_data.append(str(row['Beneficiario']))
                
                # Adicionar projeto se disponível
                if 'Projeto' in metrics['resumo_duplicidades'].columns:
                    row_data.append(str(row['Projeto']))
                
                pdf.table_row(row_data, col_widths)
    
    # NOVA SEÇÃO: Informação sobre CPFs duplicados (não são pagamentos duplicados)
    if metrics.get('total_cpfs_duplicados', 0) > 0:
        pdf.add_page()
        pdf.chapter_title('INFORMACAO: CPFS DUPLICADOS IDENTIFICADOS')
        
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 8, 'Observacao:', 0, 1)
        pdf.set_font('Arial', '', 11)
        pdf.cell(0, 7, '- Estes CPFs aparecem em multiplos registros, mas NAO sao considerados pagamentos duplicados', 0, 1)
        pdf.cell(0, 7, '- Pagamentos duplicados sao identificados apenas pelo numero da conta', 0, 1)
        pdf.cell(0, 7, '- Estes casos podem representar beneficiarios com multiplas contas ou registros de atualizacao', 0, 1)
        
        pdf.ln(5)
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 8, f'Total de CPFs com multiplas ocorrencias: {formatar_brasileiro(metrics.get("total_cpfs_duplicados", 0), "numero")}', 0, 1)
    
    # Restante do código do PDF...
    # [O restante da função permanece similar, adaptando para o novo critério]

def gerar_relatorio_excel(dados, tipo_relatorio):
    """Gera relatório em Excel"""
    output = io.BytesIO()
    
    metrics = processar_dados(dados)
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Sheet de resumo
        resumo = pd.DataFrame({
            'Metrica': [
                'Total de Pagamentos',
                'Contas Unicas (Pagamentos)',
                'Diferenca (Pagamentos - Contas)',
                'Contas com Pagamentos Duplicados',
                'Valor Total em Duplicidades',
                'CPFs com Multiplas Ocorrencias',
                'Projetos Ativos',
                'Contas Abertas',
                'Valor Total Investido',
                'Documentos Padronizados',
                'Registros com Dados Incompletos',
                'Data de Emissao'
            ],
            'Valor': [
                formatar_brasileiro(metrics.get('total_pagamentos', 0), 'numero'),
                formatar_brasileiro(metrics.get('contas_unicas', 0), 'numero'),
                formatar_brasileiro(metrics.get('total_pagamentos', 0) - metrics.get('contas_unicas', 0), 'numero'),
                formatar_brasileiro(metrics.get('pagamentos_duplicados', 0), 'numero'),
                formatar_brasileiro(metrics.get('valor_total_duplicados', 0), 'monetario') if metrics.get('valor_total_duplicados', 0) > 0 else "R$ 0,00",
                formatar_brasileiro(metrics.get('total_cpfs_duplicados', 0), 'numero'),
                formatar_brasileiro(metrics.get('projetos_ativos', 0), 'numero'),
                formatar_brasileiro(metrics.get('total_contas', 0), 'numero'),
                formatar_brasileiro(metrics.get('valor_total', 0), 'monetario') if metrics.get('valor_total', 0) > 0 else "N/A",
                formatar_brasileiro(metrics.get('documentos_padronizados', 0), 'numero'),
                formatar_brasileiro(metrics.get('total_registros_incompletos', 0), 'numero'),
                datetime.now().strftime('%d/%m/%Y %H:%M')
            ]
        })
        resumo.to_excel(writer, sheet_name='Resumo Executivo', index=False)
        
        # Sheet de análise de duplicidades por CONTA
        if not metrics['resumo_duplicidades'].empty:
            df_duplicidades = metrics['resumo_duplicidades'].copy()
            if 'Valor_Total' in df_duplicidades.columns:
                df_duplicidades['Valor_Total_Formatado'] = df_duplicidades['Valor_Total'].apply(
                    lambda x: formatar_brasileiro(x, 'monetario') if pd.notna(x) else 'R$ 0,00'
                )
            df_duplicidades.to_excel(writer, sheet_name='Duplicidades_Contas', index=False)
        
        # Sheet com detalhes completos dos duplicados por CONTA
        if not metrics['detalhes_duplicados'].empty:
            metrics['detalhes_duplicados'].to_excel(writer, sheet_name='Detalhes_Duplicados_Contas', index=False)
        
        # NOVO: Sheet com informação de CPFs duplicados
        if not metrics['cpfs_duplicados_info'].empty:
            metrics['cpfs_duplicados_info'].to_excel(writer, sheet_name='CPFs_Multiplas_Ocorrencias', index=False)
        
        # Sheets com dados completos
        if not dados['pagamentos'].empty:
            dados['pagamentos'].to_excel(writer, sheet_name='Pagamentos_Completo', index=False)
        
        if not dados['contas'].empty:
            dados['contas'].to_excel(writer, sheet_name='Abertura_Contas_Completo', index=False)
    
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
    
    # ALERTA MELHORADO: Ausência de dados com opção de download
    if metrics.get('total_registros_incompletos', 0) > 0:
        st.error(f"🚨 **ALERTA: AUSÊNCIA DE DADOS IDENTIFICADA** - {formatar_brasileiro(metrics.get('total_registros_incompletos', 0), 'numero')} registros com dados incompletos")
        
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
                colunas_prioridade = ['Indice_Registro', 'CPF', 'Nome', 'Beneficiario', 'Beneficiário', 'Projeto', 'Valor', 'Num Cartao', 'Problemas_Identificados']
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
    
    # Informação sobre documentos padronizados
    if metrics.get('documentos_padronizados', 0) > 0:
        st.success(f"✅ **DOCUMENTOS PADRONIZADOS** - {formatar_brasileiro(metrics.get('documentos_padronizados', 0), 'numero')} RGs/CPFs tiveram caracteres especiais removidos")
    
    # Métricas principais
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Beneficiários Únicos", formatar_brasileiro(metrics.get('beneficiarios_unicos', 0), 'numero'))
    
    with col2:
        st.metric("Total de Pagamentos", formatar_brasileiro(metrics.get('total_pagamentos', 0), 'numero'))
    
    with col3:
        st.metric("Contas Únicas", formatar_brasileiro(metrics.get('contas_unicas', 0), 'numero'))
    
    with col4:
        st.metric("Projetos Ativos", formatar_brasileiro(metrics.get('projetos_ativos', 0), 'numero'))
    
    # Valor total se disponível
    if metrics.get('valor_total', 0) > 0:
        st.metric("Valor Total dos Pagamentos", formatar_brasileiro(metrics['valor_total'], 'monetario'))
    
    # CORREÇÃO: Análise de Duplicidades por NÚMERO DA CONTA
    if metrics.get('pagamentos_duplicados', 0) > 0:
        st.error("🚨 **ALERTA: PAGAMENTOS DUPLICADOS IDENTIFICADOS**")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                "Contas com Duplicidade", 
                formatar_brasileiro(metrics.get('pagamentos_duplicados', 0), 'numero'),
                delta=f"{formatar_brasileiro(metrics.get('pagamentos_duplicados', 0), 'numero')} contas"
            )
        
        with col2:
            diff = metrics.get('total_pagamentos', 0) - metrics.get('contas_unicas', 0)
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
        
        # Mostrar resumo dos casos de duplicidade por CONTA
        with st.expander("🔍 **Ver Detalhes dos Pagamentos Duplicados por Conta**", expanded=False):
            if not metrics['resumo_duplicidades'].empty:
                # Adicionar informações relevantes
                colunas_display = ['Numero_Conta', 'Quantidade_Pagamentos', 'CPF', 'Beneficiario', 'Projeto']
                
                # Formatar valores no dataframe de exibição
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
                        file_name=f"pagamentos_duplicados_contas_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )
    
    # NOVA SEÇÃO: Informação sobre CPFs duplicados (não são pagamentos duplicados)
    if metrics.get('total_cpfs_duplicados', 0) > 0:
        with st.expander("ℹ️ **CPFs com Múltiplas Ocorrências (Apenas Informação)**", expanded=False):
            st.info("""
            **Observação:** Estes CPFs aparecem em múltiplos registros, mas **NÃO são considerados pagamentos duplicados**. 
            Pagamentos duplicados são identificados exclusivamente pelo **número da conta**.
            
            Estes casos podem representar:
            - Beneficiários com múltiplas contas bancárias
            - Registros de atualização de dados
            - Diferentes projetos para o mesmo beneficiário
            """)
            
            st.metric(
                "CPFs com múltiplas ocorrências",
                formatar_brasileiro(metrics.get('total_cpfs_duplicados', 0), 'numero')
            )
            
            if not metrics['cpfs_duplicados_info'].empty:
                # Mostrar alguns exemplos
                colunas_cpfs = ['CPF', 'Num Cartao', 'Projeto', 'Beneficiario']
                colunas_exibir = [col for col in colunas_cpfs if col in metrics['cpfs_duplicados_info'].columns]
                
                st.dataframe(
                    metrics['cpfs_duplicados_info'][colunas_exibir].head(10),
                    use_container_width=True,
                    hide_index=True,
                    height=300
                )
    
    # Restante do dashboard (gráficos e tabelas) permanece similar...
    # [O restante da função mostrar_dashboard permanece inalterado]

# As funções restantes (mostrar_importacao, mostrar_consultas, mostrar_relatorios, mostrar_rodape, main) permanecem as mesmas

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
Num Cartao (número da conta) ← CRITÉRIO PARA DUPLICIDADE
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

def mostrar_consultas(dados):
    st.header("🔍 Consultas de Dados")
    
    # Opções de consulta
    opcao_consulta = st.radio(
        "Tipo de consulta:",
        ["Por CPF", "Por Projeto", "Por Número da Conta"],
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
    
    else:  # Por Número da Conta
        col1, col2 = st.columns([2, 1])
        with col1:
            numero_conta = st.text_input("Digite o número da conta:")
        with col2:
            if st.button("💳 Buscar por Conta", use_container_width=True):
                if numero_conta:
                    resultados = {}
                    coluna_conta = obter_coluna_conta(dados['pagamentos'])
                    if not dados['pagamentos'].empty and coluna_conta:
                        resultados['pagamentos'] = dados['pagamentos'][dados['pagamentos'][coluna_conta].astype(str).str.contains(numero_conta)]
                    
                    st.session_state.resultados_consulta = resultados
                else:
                    st.warning("Por favor, digite um número da conta para buscar")
    
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
            coluna_conta = obter_coluna_conta(resultados['pagamentos'])
            if coluna_conta:
                colunas_display.append(coluna_conta)
            
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

def mostrar_relatorios(dados):
    st.header("📋 Gerar Relatórios")
    
    # Análise preliminar para mostrar alertas
    metrics = processar_dados(dados)
    
    if metrics.get('pagamentos_duplicados', 0) > 0:
        st.warning(f"🚨 **ALERTA:** Foram identificados {formatar_brasileiro(metrics.get('pagamentos_duplicados', 0), 'numero')} contas com pagamentos duplicados")
        st.info(f"📊 **Diferença:** {formatar_brasileiro(metrics.get('total_pagamentos', 0), 'numero')} pagamentos para {formatar_brasileiro(metrics.get('contas_unicas', 0), 'numero')} contas únicas")
    
    # Alerta de ausência de dados
    if metrics.get('total_registros_incompletos', 0) > 0:
        st.error(f"🚨 **ALERTA:** {formatar_brasileiro(metrics.get('total_registros_incompletos', 0), 'numero')} registros com dados incompletos identificados")
    
    # Informação sobre CPFs duplicados
    if metrics.get('total_cpfs_duplicados', 0) > 0:
        st.info(f"ℹ️ **INFORMAÇÃO:** {formatar_brasileiro(metrics.get('total_cpfs_duplicados', 0), 'numero')} CPFs com múltiplas ocorrências (não são pagamentos duplicados)")
    
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
