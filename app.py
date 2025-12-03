# app.py - SISTEMA POT SMDET COMPLETO COM PDF E ANÁLISE DE INCONSISTÊNCIAS
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
        self.set_font('Arial', '', 9)
        
        # Calcular larguras das colunas
        col_widths = []
        for col in df.columns:
            max_len = max(df[col].astype(str).apply(len).max(), len(col)) * 2
            col_widths.append(min(max_len, 40))
        
        # Cabeçalho
        self.set_fill_color(200, 200, 200)
        self.set_font('Arial', 'B', 9)
        for i, col in enumerate(df.columns):
            self.cell(col_widths[i], 8, str(col)[:30], 1, 0, 'C', True)
        self.ln()
        
        # Dados
        self.set_font('Arial', '', 9)
        for idx, row in df.head(max_rows).iterrows():
            for i, col in enumerate(df.columns):
                self.cell(col_widths[i], 8, str(row[col])[:30], 1, 0, 'C')
            self.ln()
        
        if len(df) > max_rows:
            self.ln(5)
            self.set_font('Arial', 'I', 9)
            self.cell(0, 8, f'... e mais {len(df) - max_rows} registros', 0, 1)
    
    def add_problem_list(self, problems):
        self.set_font('Arial', 'B', 11)
        self.cell(0, 8, "Problemas Críticos Encontrados:", 0, 1)
        self.ln(2)
        
        self.set_font('Arial', '', 10)
        for i, problem in enumerate(problems[:20], 1):
            self.multi_cell(0, 6, f"{i}. {problem}")
            self.ln(1)
        
        if len(problems) > 20:
            self.ln(2)
            self.set_font('Arial', 'I', 9)
            self.cell(0, 8, f'... e mais {len(problems) - 20} problemas', 0, 1)

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
# DETECÇÃO AUTOMÁTICA DE COLUNAS (APRIMORADA)
# ============================================

def detectar_coluna_conta(df):
    colunas_possiveis = [
        'NumCartão', 'NumCartao', 'Num_Cartao', 'Num Cartao', 'Cartao',
        'Cartão', 'Conta', 'Numero Conta', 'Número Conta', 'NRO_CONTA',
        'CARTAO', 'CONTA', 'NUMCARTAO', 'NUM_CARTAO', 'NUMERO_CARTAO',
        'NumeroCartao', 'NrCartao', 'NRCartao'
    ]
    
    for coluna in df.columns:
        coluna_limpa = str(coluna).strip().upper()
        for padrao in colunas_possiveis:
            if padrao.upper() in coluna_limpa:
                return coluna
    
    for coluna in df.columns:
        if df[coluna].dtype == 'object':
            amostra = df[coluna].dropna().head(5).astype(str)
            if any(re.search(r'^\d{6,}$', str(x).strip()) for x in amostra):
                return coluna
    
    return None

def detectar_coluna_nome(df):
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
    colunas_prioridade = [
        'Valor', 'Valor Pago', 'ValorPagto', 'Valor_Pagto', 'VALOR',
        'VALOR PAGO', 'VALOR_PAGO', 'VALOR PGTO', 'VLR_PAGO'
    ]
    
    for coluna in df.columns:
        coluna_limpa = str(coluna).strip().upper()
        for padrao in colunas_prioridade:
            if padrao.upper() in coluna_limpa:
                return coluna
    
    for coluna in df.columns:
        if df[coluna].dtype in ['float64', 'int64']:
            return coluna
    
    return None

def detectar_coluna_data(df):
    colunas_data = [
        'Data', 'DataPagto', 'Data_Pagto', 'DtLote', 'DATA',
        'DATA PGTO', 'DT_LOTE', 'DATALOTE', 'DataPagamento'
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
    colunas_possiveis = ['Projeto', 'PROJETO', 'PROGRAMA', 'NOME PROJETO']
    
    for coluna in df.columns:
        coluna_limpa = str(coluna).strip().upper()
        for padrao in colunas_possiveis:
            if padrao.upper() in coluna_limpa:
                return coluna
    
    return None

def detectar_coluna_cpf(df):
    colunas_possiveis = ['CPF', 'CPF BENEFICIARIO', 'CPF_BENEF', 'CPF/CNPJ']
    
    for coluna in df.columns:
        coluna_limpa = str(coluna).strip().upper()
        for padrao in colunas_possiveis:
            if padrao.upper() == coluna_limpa:
                return coluna
    
    return None

# ============================================
# PROCESSAMENTO DE ARQUIVOS TXT DO BANCO DO BRASIL
# ============================================

def processar_arquivo_bb_txt(conteudo, encoding):
    """Processa arquivos TXT específicos do Banco do Brasil"""
    linhas = conteudo.split('\n')
    
    # Encontrar linha de cabeçalho
    cabecalho_idx = -1
    for i, linha in enumerate(linhas):
        if 'NumCartão' in linha or 'NumCartao' in linha:
            cabecalho_idx = i
            break
    
    if cabecalho_idx >= 0:
        # Extrair nomes das colunas
        cabecalho = linhas[cabecalho_idx].strip()
        colunas = cabecalho.split()
        
        # Processar dados
        dados = []
        for linha in linhas[cabecalho_idx + 1:]:
            linha = linha.strip()
            if linha:
                valores = linha.split()
                if len(valores) >= len(colunas):
                    dados.append(valores[:len(colunas)])
        
        df = pd.DataFrame(dados, columns=colunas)
        return df
    
    return pd.DataFrame()

# ============================================
# CARREGAMENTO DE PLANILHAS
# ============================================

def carregar_planilha(arquivo):
    try:
        nome_arquivo = arquivo.name
        
        # Verificar se é arquivo TXT do Banco do Brasil
        if nome_arquivo.upper().startswith('REL.CADASTRO') and nome_arquivo.endswith('.TXT'):
            encoding = detectar_encoding(arquivo)
            conteudo = arquivo.read().decode(encoding)
            df = processar_arquivo_bb_txt(conteudo, encoding)
            
            if not df.empty:
                st.success(f"✅ Arquivo BB TXT processado: {nome_arquivo} ({len(df)} registros)")
                return df
        
        # Para arquivos CSV normais
        if nome_arquivo.endswith('.csv') or nome_arquivo.endswith('.txt'):
            encoding = detectar_encoding(arquivo)
            
            # Tentar diferentes delimitadores
            for delimiter in [';', ',', '\t', '|']:
                try:
                    arquivo.seek(0)
                    df = pd.read_csv(arquivo, delimiter=delimiter, encoding=encoding,
                                    low_memory=False, on_bad_lines='skip')
                    if len(df.columns) > 1:
                        return df
                except:
                    continue
            
            # Última tentativa com engine python
            try:
                arquivo.seek(0)
                df = pd.read_csv(arquivo, sep=None, engine='python', encoding=encoding,
                                low_memory=False, on_bad_lines='skip')
                return df
            except:
                pass
        
        # Para arquivos Excel
        elif nome_arquivo.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(arquivo)
            return df
        
        return pd.DataFrame()
        
    except Exception as e:
        st.error(f"Erro ao carregar {arquivo.name}: {str(e)}")
        return pd.DataFrame()

# ============================================
# ANÁLISE DE PROBLEMAS CRÍTICOS
# ============================================

def analisar_problemas_criticos(df, tipo):
    """Analisa problemas críticos nos dados"""
    problemas = []
    
    if df.empty:
        return problemas
    
    if tipo == 'pagamentos':
        coluna_conta = detectar_coluna_conta(df)
        coluna_valor = detectar_coluna_valor(df)
        coluna_nome = detectar_coluna_nome(df)
        
        # 1. Contas sem número
        if coluna_conta:
            contas_vazias = df[coluna_conta].isna().sum() + df[df[coluna_conta].astype(str).str.strip() == ''].shape[0]
            if contas_vazias > 0:
                problemas.append(f"{contas_vazias} registros sem número de conta")
        
        # 2. Valores zerados ou negativos
        if coluna_valor:
            if coluna_valor in df.columns:
                valores_zerados = df[df[coluna_valor] == 0].shape[0]
                valores_negativos = df[df[coluna_valor] < 0].shape[0]
                
                if valores_zerados > 0:
                    problemas.append(f"{valores_zerados} pagamentos com valor zerado")
                if valores_negativos > 0:
                    problemas.append(f"{valores_negativos} pagamentos com valor negativo")
        
        # 3. Nomes em branco
        if coluna_nome and coluna_nome in df.columns:
            nomes_vazios = df[coluna_nome].isna().sum() + df[df[coluna_nome].astype(str).str.strip() == ''].shape[0]
            if nomes_vazios > 0:
                problemas.append(f"{nomes_vazios} registros sem nome do beneficiário")
    
    elif tipo == 'contas':
        coluna_conta = detectar_coluna_conta(df)
        coluna_nome = detectar_coluna_nome(df)
        coluna_cpf = detectar_coluna_cpf(df)
        
        # 1. Contas duplicadas
        if coluna_conta and coluna_conta in df.columns:
            duplicados = df[df.duplicated(subset=[coluna_conta], keep=False)]
            if not duplicados.empty:
                problemas.append(f"{duplicados[coluna_conta].nunique()} contas duplicadas")
        
        # 2. Nomes em branco
        if coluna_nome and coluna_nome in df.columns:
            nomes_vazios = df[coluna_nome].isna().sum() + df[df[coluna_nome].astype(str).str.strip() == ''].shape[0]
            if nomes_vazios > 0:
                problemas.append(f"{nomes_vazios} registros sem nome")
        
        # 3. CPFs inválidos
        if coluna_cpf and coluna_cpf in df.columns:
            try:
                # Contar CPFs com formato inválido
                df['CPF_Limpo'] = df[coluna_cpf].astype(str).apply(lambda x: re.sub(r'[^\d]', '', x))
                cpf_invalidos = df[df['CPF_Limpo'].str.len() != 11].shape[0]
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
    pdf.cell(0, 20, 'RELATÓRIO DE ANÁLISE', 0, 1, 'C')
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 15, f'SISTEMA POT - SMDET', 0, 1, 'C')
    pdf.set_font('Arial', 'I', 14)
    pdf.cell(0, 10, f'Período: {mes} de {ano}', 0, 1, 'C')
    pdf.ln(20)
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 10, f'Data de geração: {data_hora_atual_brasilia()}', 0, 1, 'C')
    
    # Resumo Executivo
    pdf.add_page()
    pdf.chapter_title('RESUMO EXECUTIVO', 16)
    
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, 'Principais Métricas:', 0, 1)
    pdf.ln(3)
    
    if metrics_pagamentos:
        pdf.add_metric('Total de Pagamentos:', formatar_brasileiro(metrics_pagamentos.get('total_registros', 0)))
        pdf.add_metric('Valor Total Pago:', formatar_brasileiro(metrics_pagamentos.get('valor_total', 0), 'monetario'))
        pdf.add_metric('Pagamentos Válidos:', formatar_brasileiro(metrics_pagamentos.get('registros_validos', 0)))
        pdf.add_metric('Pagamentos Duplicados:', formatar_brasileiro(metrics_pagamentos.get('pagamentos_duplicados', 0)), 
                      alert=metrics_pagamentos.get('pagamentos_duplicados', 0) > 0)
    
    if metrics_contas:
        pdf.add_metric('Contas Abertas:', formatar_brasileiro(metrics_contas.get('total_contas', 0)))
    
    if comparacao:
        pdf.add_metric('Contas sem Pagamento:', formatar_brasileiro(comparacao.get('total_contas_sem_pagamento', 0)),
                      alert=comparacao.get('total_contas_sem_pagamento', 0) > 0)
    
    # Problemas Críticos
    pdf.ln(10)
    pdf.chapter_title('PROBLEMAS CRÍTICOS IDENTIFICADOS', 14)
    
    if problemas_pagamentos:
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 10, 'Nos Pagamentos:', 0, 1)
        pdf.set_font('Arial', '', 11)
        for problema in problemas_pagamentos[:10]:
            pdf.cell(0, 7, f"• {problema}", 0, 1)
        pdf.ln(5)
    
    if problemas_contas:
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 10, 'Nas Contas:', 0, 1)
        pdf.set_font('Arial', '', 11)
        for problema in problemas_contas[:10]:
            pdf.cell(0, 7, f"• {problema}", 0, 1)
    
    # Análise Detalhada de Pagamentos
    if not df_pagamentos.empty:
        pdf.add_page()
        pdf.chapter_title('ANÁLISE DETALHADA DE PAGAMENTOS', 16)
        
        # Estatísticas
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 10, 'Estatísticas:', 0, 1)
        pdf.ln(3)
        
        coluna_valor = detectar_coluna_valor(df_pagamentos)
        if coluna_valor and coluna_valor in df_pagamentos.columns:
            try:
                estatisticas = df_pagamentos[coluna_valor].describe()
                pdf.set_font('Arial', '', 11)
                pdf.add_metric('Média:', formatar_brasileiro(estatisticas['mean'], 'monetario'))
                pdf.add_metric('Mediana:', formatar_brasileiro(estatisticas['50%'], 'monetario'))
                pdf.add_metric('Mínimo:', formatar_brasileiro(estatisticas['min'], 'monetario'))
                pdf.add_metric('Máximo:', formatar_brasileiro(estatisticas['max'], 'monetario'))
                pdf.add_metric('Desvio Padrão:', formatar_brasileiro(estatisticas['std'], 'monetario'))
            except:
                pass
        
        # Top 10 maiores pagamentos
        pdf.ln(10)
        pdf.chapter_title('TOP 10 MAIORES PAGAMENTOS', 14)
        
        if coluna_valor and coluna_valor in df_pagamentos.columns:
            coluna_nome = detectar_coluna_nome(df_pagamentos)
            coluna_conta = detectar_coluna_conta(df_pagamentos)
            
            if coluna_nome and coluna_conta:
                top_pagamentos = df_pagamentos.nlargest(10, coluna_valor)[[coluna_conta, coluna_nome, coluna_valor]]
                top_pagamentos = top_pagamentos.copy()
                top_pagamentos[coluna_valor] = top_pagamentos[coluna_valor].apply(
                    lambda x: formatar_brasileiro(x, 'monetario')
                )
                pdf.add_table(top_pagamentos)
    
    # Análise de Inconsistências
    pdf.add_page()
    pdf.chapter_title('INCONSISTÊNCIAS PARA CORREÇÃO', 16)
    
    if comparacao and comparacao.get('total_contas_sem_pagamento', 0) > 0:
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 10, f'Contas Abertas sem Pagamento ({comparacao["total_contas_sem_pagamento"]}):', 0, 1)
        pdf.ln(3)
        
        if not df_contas.empty:
            coluna_conta = detectar_coluna_conta(df_contas)
            coluna_nome = detectar_coluna_nome(df_contas)
            
            if coluna_conta and coluna_nome:
                contas_sem_pagamento = df_contas[
                    df_contas[coluna_conta].astype(str).isin([str(c) for c in comparacao.get('contas_sem_pagamento', [])])
                ][[coluna_conta, coluna_nome]].head(20)
                
                if not contas_sem_pagamento.empty:
                    pdf.add_table(contas_sem_pagamento)
    
    # Recomendações
    pdf.ln(15)
    pdf.chapter_title('RECOMENDAÇÕES', 14)
    
    recomendacoes = []
    
    if problemas_pagamentos:
        recomendacoes.append("Regularizar pagamentos com valores zerados ou negativos")
        recomendacoes.append("Completar informações de beneficiários sem nome")
    
    if problemas_contas:
        recomendacoes.append("Verificar e corrigir contas duplicadas")
        recomendacoes.append("Validar CPFs com formato inválido")
    
    if comparacao and comparacao.get('total_contas_sem_pagamento', 0) > 0:
        recomendacoes.append(f"Regularizar pagamentos para {comparacao['total_contas_sem_pagamento']} contas sem pagamento")
    
    pdf.set_font('Arial', '', 11)
    for i, rec in enumerate(recomendacoes[:10], 1):
        pdf.cell(0, 7, f"{i}. {rec}", 0, 1)
    
    return pdf

# ============================================
# INTERFACE PRINCIPAL
# ============================================

def main():
    st.title("🏛️ Sistema POT - SMDET")
    st.markdown("### Sistema Completo de Análise de Pagamentos e Contas")
    st.markdown("---")
    
    # Sidebar
    st.sidebar.header("📤 Upload de Arquivos")
    
    # Upload múltiplo para diferentes tipos de arquivos
    uploaded_files = st.sidebar.file_uploader(
        "Carregue suas planilhas (CSV, TXT, Excel)",
        type=['csv', 'txt', 'xlsx', 'xls'],
        accept_multiple_files=True,
        help="Arraste ou selecione arquivos do Banco do Brasil e outros sistemas"
    )
    
    # Classificação automática de arquivos
    arquivos_pagamentos = []
    arquivos_contas = []
    
    if uploaded_files:
        with st.spinner("Analisando arquivos..."):
            for arquivo in uploaded_files:
                nome = arquivo.name.upper()
                
                # Classificar por nome do arquivo
                if any(palavra in nome for palavra in ['PGTO', 'PAGTO', 'PAGAMENTO', 'PAGTO', 'VALOR']):
                    arquivos_pagamentos.append(arquivo)
                    st.sidebar.success(f"📊 {arquivo.name} (Pagamentos)")
                elif any(palavra in nome for palavra in ['CADASTRO', 'CONTA', 'ABERTURA', 'REL.CADASTRO']):
                    arquivos_contas.append(arquivo)
                    st.sidebar.success(f"📋 {arquivo.name} (Contas)")
                else:
                    # Tentar classificar pelo conteúdo
                    df_temp = carregar_planilha(arquivo)
                    if not df_temp.empty:
                        coluna_valor = detectar_coluna_valor(df_temp)
                        if coluna_valor:
                            arquivos_pagamentos.append(arquivo)
                            st.sidebar.info(f"📊 {arquivo.name} (Pagamentos - detectado)")
                        else:
                            arquivos_contas.append(arquivo)
                            st.sidebar.info(f"📋 {arquivo.name} (Contas - detectado)")
    
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
        mes = st.selectbox("Mês", meses, index=9)
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
                        validos = df_pagamentos[coluna_conta].notna() & (df_pagamentos[coluna_conta].astype(str).str.strip() != '')
                        metrics_pagamentos['registros_validos'] = validos.sum()
                        
                        # Duplicados
                        duplicados = df_pagamentos[df_pagamentos.duplicated(subset=[coluna_conta], keep=False)]
                        metrics_pagamentos['pagamentos_duplicados'] = duplicados[coluna_conta].nunique() if not duplicados.empty else 0
                    
                    if coluna_valor and coluna_valor in df_pagamentos.columns:
                        metrics_pagamentos['valor_total'] = df_pagamentos[coluna_valor].sum()
                
                if not df_contas.empty:
                    metrics_contas['total_contas'] = len(df_contas)
                    coluna_conta_cont = detectar_coluna_conta(df_contas)
                    if coluna_conta_cont and coluna_conta_cont in df_contas.columns:
                        metrics_contas['contas_unicas'] = df_contas[coluna_conta_cont].nunique()
                
                # Comparação
                if not df_pagamentos.empty and not df_contas.empty:
                    coluna_conta_pag = detectar_coluna_conta(df_pagamentos)
                    coluna_conta_cont = detectar_coluna_conta(df_contas)
                    
                    if coluna_conta_pag and coluna_conta_cont:
                        contas_pag = set(df_pagamentos[coluna_conta_pag].dropna().astype(str).str.strip())
                        contas_cont = set(df_contas[coluna_conta_cont].dropna().astype(str).str.strip())
                        
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
                
                with col2:
                    if 'valor_total' in metrics_pagamentos:
                        st.metric("Valor Total", 
                                 formatar_brasileiro(metrics_pagamentos['valor_total'], 'monetario'))
                
                with col3:
                    if 'total_contas' in metrics_contas:
                        st.metric("Contas Abertas", 
                                 formatar_brasileiro(metrics_contas['total_contas']))
                
                with col4:
                    if 'total_contas_sem_pagamento' in comparacao:
                        st.metric("Contas sem Pagamento", 
                                 formatar_brasileiro(comparacao['total_contas_sem_pagamento']),
                                 delta_color="inverse")
                
                # Problemas Críticos
                st.subheader("🚨 Problemas Críticos Identificados")
                
                if problemas_pagamentos or problemas_contas:
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
                            st.write(f"Coluna de conta: {coluna_conta}")
                        if coluna_valor:
                            st.write(f"Coluna de valor: {coluna_valor}")
                        
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
                            duplicados = df_pagamentos[df_pagamentos.duplicated(subset=[coluna_conta], keep=False)]
                            
                            if not duplicados.empty:
                                st.warning(f"🚨 {duplicados[coluna_conta].nunique()} contas com pagamentos duplicados")
                                st.dataframe(duplicados[[coluna_conta, detectar_coluna_nome(df_pagamentos) if detectar_coluna_nome(df_pagamentos) else coluna_conta]].head(20))
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
                                contas_sem_pag = df_contas[
                                    df_contas[coluna_conta].astype(str).isin([str(c) for c in comparacao['contas_sem_pagamento']])
                                ][[coluna_conta, coluna_nome]]
                                
                                st.dataframe(contas_sem_pag.head(50))
                    else:
                        st.success("✅ Nenhuma inconsistência grave encontrada")
                
                with tab4:
                    st.subheader("Estatísticas Detalhadas")
                    
                    if not df_pagamentos.empty:
                        coluna_valor = detectar_coluna_valor(df_pagamentos)
                        
                        if coluna_valor and coluna_valor in df_pagamentos.columns:
                            # Gráfico de distribuição
                            fig = px.histogram(df_pagamentos, x=coluna_valor, 
                                             title='Distribuição dos Valores de Pagamento',
                                             nbins=20)
                            st.plotly_chart(fig, use_container_width=True)
                            
                            # Estatísticas
                            estat = df_pagamentos[coluna_valor].describe()
                            st.write("**Estatísticas Descritivas:**")
                            st.dataframe(pd.DataFrame({
                                'Estatística': estat.index,
                                'Valor': estat.values
                            }))
                
                # Gerar e oferecer download do PDF
                st.subheader("📄 Relatório Completo em PDF")
                
                try:
                    pdf = gerar_relatorio_pdf(mes, ano, metrics_pagamentos, metrics_contas, comparacao,
                                            problemas_pagamentos, problemas_contas, df_pagamentos, df_contas)
                    
                    # Converter PDF para bytes
                    pdf_bytes = pdf.output(dest='S').encode('latin-1')
                    
                    # Botão de download
                    st.download_button(
                        label="📥 Baixar Relatório Completo (PDF)",
                        data=pdf_bytes,
                        file_name=f"Relatorio_POT_{mes}_{ano}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
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
            st.warning("⚠️ Carregue pelo menos um arquivo para análise")
    
    else:
        # Tela inicial
        st.info("👈 Carregue seus arquivos e clique em 'Realizar Análise Completa'")
        
        with st.expander("📚 Tipos de arquivos suportados"):
            st.markdown("""
            ### Arquivos do Banco do Brasil:
            - **REL.CADASTRO.OT.VXXXX.TXT** (Cadastros/Contas)
            - Arquivos TXT com layout fixo
            
            ### Outros formatos:
            - **CSV** (com delimitadores: ; , \\t |)
            - **Excel** (.xlsx, .xls)
            - **TXT** (dados tabulares)
            
            ### Colunas reconhecidas automaticamente:
            - `NumCartão`, `NumCartao` (Número da conta)
            - `Nome`, `Beneficiario` (Nome do beneficiário)
            - `Valor`, `ValorPagto` (Valor do pagamento)
            - `Data`, `DtLote` (Data)
            - `Projeto` (Nome do projeto)
            - `CPF` (CPF do beneficiário)
            """)
        
        with st.expander("🎯 Funcionalidades do sistema"):
            st.markdown("""
            ### 1. Análise Automática
            - Detecção automática de colunas
            - Identificação de problemas críticos
            - Análise de duplicidades
            
            ### 2. Relatórios em PDF
            - Relatório executivo completo
            - Lista de inconsistências
            - Recomendações de correção
            
            ### 3. Validações
            - CPFs inválidos
            - Contas sem pagamento
            - Valores zerados/negativos
            - Dados incompletos
            
            ### 4. Exportação
            - Dados brutos em CSV
            - Relatórios em PDF
            - Listas para correção
            """)

if __name__ == "__main__":
    main()
