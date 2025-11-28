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

# NOVA FUNÇÃO: Processar CPF de forma inteligente
def processar_cpf(cpf):
    """Processa CPF, completando com zeros à esquerda e removendo caracteres especiais"""
    if pd.isna(cpf) or cpf in ['', 'NaN', 'None', 'nan']:
        return cpf
    
    cpf_str = str(cpf).strip()
    
    # Remover todos os caracteres não numéricos
    cpf_limpo = re.sub(r'[^\d]', '', cpf_str)
    
    # Completar com zeros à esquerda se tiver menos de 11 dígitos
    if cpf_limpo and len(cpf_limpo) < 11:
        cpf_limpo = cpf_limpo.zfill(11)
    
    return cpf_limpo

# FUNÇÃO CORRIGIDA: Padronizar documentos de forma inteligente
def padronizar_documentos(df):
    """Padroniza RGs e CPFs, completando com zeros à esquerda quando necessário"""
    df_processed = df.copy()
    
    # Colunas que podem conter documentos
    colunas_documentos = ['RG', 'CPF', 'Documento', 'Numero_Documento']
    
    for coluna in colunas_documentos:
        if coluna in df_processed.columns:
            try:
                if coluna == 'RG':
                    # Para RG: manter números, X e / (válidos em RGs)
                    df_processed[coluna] = df_processed[coluna].astype(str).apply(
                        lambda x: re.sub(r'[^a-zA-Z0-9/]', '', x) if pd.notna(x) else x
                    )
                else:
                    # Para CPF: tratamento especial para diferentes formatos
                    df_processed[coluna] = df_processed[coluna].astype(str).apply(
                        lambda x: processar_cpf(x) if pd.notna(x) else x
                    )
                
            except Exception as e:
                st.warning(f"⚠️ Não foi possível padronizar a coluna '{coluna}': {str(e)}")
    
    return df_processed

# FUNÇÃO MELHORADA: Analisar ausência de dados com informações da planilha original
def analisar_ausencia_dados(dados, nome_arquivo_pagamentos=None, nome_arquivo_contas=None):
    """Analisa e reporta apenas dados críticos realmente ausentes com info da planilha original"""
    analise_ausencia = {
        'registros_criticos_problematicos': [],
        'total_registros_criticos': 0,
        'colunas_com_ausencia_critica': {},
        'resumo_ausencias': pd.DataFrame(),
        'registros_problema_detalhados': pd.DataFrame(),
        'documentos_padronizados': 0,
        'tipos_problemas': {},
        'registros_validos_com_x': 0,
        'cpfs_com_zeros_adicional': 0,
        'cpfs_formatos_diferentes': 0,
        'nome_arquivo_pagamentos': nome_arquivo_pagamentos,  # NOVO: nome do arquivo
        'nome_arquivo_contas': nome_arquivo_contas
    }
    
    if not dados['pagamentos'].empty:
        df = dados['pagamentos'].copy()
        
        # NOVO: Adicionar coluna com número da linha original (considerando que a planilha começa na linha 2 - linha 1 é cabeçalho)
        df['Linha_Planilha_Original'] = df.index + 2
        
        # Contar documentos padronizados
        colunas_docs = ['RG', 'CPF']
        for coluna in colunas_docs:
            if coluna in df.columns:
                docs_originais = len(df[df[coluna].notna()])
                analise_ausencia['documentos_padronizados'] += docs_originais
        
        # Contar RGs válidos com X
        if 'RG' in df.columns:
            rgs_com_x = df[df['RG'].astype(str).str.contains('X', case=False, na=False)]
            analise_ausencia['registros_validos_com_x'] = len(rgs_com_x)
        
        # Contar CPFs que receberam zeros à esquerda
        if 'CPF' in df.columns:
            cpfs_com_zeros = df[
                df['CPF'].notna() & 
                (df['CPF'].astype(str).str.len() < 11) &
                (df['CPF'].astype(str).str.strip() != '') &
                (df['CPF'].astype(str).str.strip() != 'NaN') &
                (df['CPF'].astype(str).str.strip() != 'None')
            ]
            analise_ausencia['cpfs_com_zeros_adicional'] = len(cpfs_com_zeros)
            
            cpfs_com_formatos = df[
                df['CPF'].notna() & 
                (df['CPF'].astype(str).str.contains(r'[.-]', na=False))
            ]
            analise_ausencia['cpfs_formatos_diferentes'] = len(cpfs_com_formatos)
        
        # CRITÉRIO CORRIGIDO: Apenas dados realmente críticos ausentes
        registros_problematicos = []
        
        # 1. CPF COMPLETAMENTE AUSENTE
        if 'CPF' in df.columns:
            mask_cpf_ausente = (
                df['CPF'].isna() | 
                (df['CPF'].astype(str).str.strip() == '') |
                (df['CPF'].astype(str).str.strip() == 'NaN') |
                (df['CPF'].astype(str).str.strip() == 'None') |
                (df['CPF'].astype(str).str.strip() == 'nan')
            )
            
            cpfs_ausentes = df[mask_cpf_ausente]
            registros_problematicos.extend(cpfs_ausentes.index.tolist())
        
        # 2. Número da conta ausente
        coluna_conta = obter_coluna_conta(df)
        if coluna_conta:
            mask_conta_ausente = (
                df[coluna_conta].isna() | 
                (df[coluna_conta].astype(str).str.strip() == '') |
                (df[coluna_conta].astype(str).str.strip() == 'NaN') |
                (df[coluna_conta].astype(str).str.strip() == 'None')
            )
            contas_ausentes = df[mask_conta_ausente]
            for idx in contas_ausentes.index:
                if idx not in registros_problematicos:
                    registros_problematicos.append(idx)
        
        # 3. Valor ausente ou zero
        if 'Valor' in df.columns:
            mask_valor_invalido = (
                df['Valor'].isna() | 
                (df['Valor'].astype(str).str.strip() == '') |
                (df['Valor'].astype(str).str.strip() == 'NaN') |
                (df['Valor'].astype(str).str.strip() == 'None') |
                (df['Valor_Limpo'] == 0)
            )
            valores_invalidos = df[mask_valor_invalido]
            for idx in valores_invalidos.index:
                if idx not in registros_problematicos:
                    registros_problematicos.append(idx)
        
        # Atualizar análise
        analise_ausencia['registros_criticos_problematicos'] = registros_problematicos
        analise_ausencia['total_registros_criticos'] = len(registros_problematicos)
        
        if registros_problematicos:
            analise_ausencia['registros_problema_detalhados'] = df.loc[registros_problematicos].copy()
        
        # Analisar ausência por coluna crítica
        colunas_criticas = ['CPF', 'Num Cartao', 'Num_Cartao', 'Valor']
        for coluna in colunas_criticas:
            if coluna in df.columns:
                mask_ausente = (
                    df[coluna].isna() | 
                    (df[coluna].astype(str).str.strip() == '') |
                    (df[coluna].astype(str).str.strip() == 'NaN') |
                    (df[coluna].astype(str).str.strip() == 'None')
                )
                ausentes = df[mask_ausente]
                if len(ausentes) > 0:
                    analise_ausencia['colunas_com_ausencia_critica'][coluna] = len(ausentes)
                    analise_ausencia['tipos_problemas'][f'Sem {coluna}'] = len(ausentes)
        
        # Criar resumo de ausências com informações da planilha original
        if registros_problematicos:
            resumo = []
            for idx in registros_problematicos[:100]:  # Aumentei para 100 registros
                registro = df.loc[idx]
                info_ausencia = {
                    'Indice_Registro': idx,
                    'Linha_Planilha': registro.get('Linha_Planilha_Original', idx + 2),  # NOVO: linha da planilha
                    'Planilha_Origem': nome_arquivo_pagamentos or 'Pagamentos'  # NOVO: nome do arquivo
                }
                
                colunas_interesse = [
                    'CPF', 'RG', 'Projeto', 'Valor', 'Beneficiario', 'Beneficiário', 'Nome',
                    'Data', 'Data Pagto', 'Data_Pagto', 'DataPagto',
                    'Num Cartao', 'Num_Cartao', 'Conta', 'Status'
                ]
                
                for col in colunas_interesse:
                    if col in df.columns and pd.notna(registro[col]):
                        valor = str(registro[col])
                        if len(valor) > 50:
                            valor = valor[:47] + "..."
                        info_ausencia[col] = valor
                    else:
                        info_ausencia[col] = 'N/A'
                
                # Marcar campos problemáticos
                problemas = []
                if 'CPF' in df.columns and (pd.isna(registro['CPF']) or str(registro['CPF']).strip() in ['', 'NaN', 'None', 'nan']):
                    problemas.append('CPF ausente')
                
                if coluna_conta and (pd.isna(registro[coluna_conta]) or str(registro[coluna_conta]).strip() in ['', 'NaN', 'None', 'nan']):
                    problemas.append('Número da conta ausente')
                
                if 'Valor' in df.columns and (pd.isna(registro['Valor']) or registro.get('Valor_Limpo', 0) == 0):
                    problemas.append('Valor ausente ou zero')
                
                info_ausencia['Problemas_Identificados'] = ', '.join(problemas) if problemas else 'Dados OK'
                resumo.append(info_ausencia)
            
            analise_ausencia['resumo_ausencias'] = pd.DataFrame(resumo)
    
    return analise_ausencia

# CORREÇÃO: Nova função para processar colunas de data
def processar_colunas_data(df):
    """Converte colunas de data de formato numérico do Excel para datas legíveis"""
    df_processed = df.copy()
    
    colunas_data = ['Data', 'Data Pagto', 'Data_Pagto', 'DataPagto']
    
    for coluna in colunas_data:
        if coluna in df_processed.columns:
            try:
                if df_processed[coluna].dtype in ['int64', 'float64']:
                    df_processed[coluna] = pd.to_datetime(
                        df_processed[coluna], 
                        unit='D', 
                        origin='1899-12-30',
                        errors='coerce'
                    )
                else:
                    df_processed[coluna] = pd.to_datetime(
                        df_processed[coluna], 
                        errors='coerce'
                    )
                
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
            if df_processed['Valor'].dtype == 'object':
                df_processed['Valor_Limpo'] = (
                    df_processed['Valor']
                    .astype(str)
                    .str.replace('R$', '')
                    .str.replace('R$ ', '')
                    .str.replace('.', '')
                    .str.replace(',', '.')
                    .str.replace(' ', '')
                    .astype(float)
                )
            else:
                df_processed['Valor_Limpo'] = df_processed['Valor'].astype(float)
                
        except Exception as e:
            st.warning(f"⚠️ Erro ao processar valores: {str(e)}")
            df_processed['Valor_Limpo'] = 0.0
    
    return df_processed

# Sistema de upload de dados MELHORADO: capturar nomes dos arquivos
def carregar_dados():
    st.sidebar.header("📤 Carregar Dados Reais")
    
    upload_pagamentos = st.sidebar.file_uploader(
        "Planilha de Pagamentos", 
        type=['xlsx', 'csv'],
        key="pagamentos"
    )
    
    upload_contas = st.sidebar.file_uploader(
        "Planilha de Abertura de Contas", 
        type=['xlsx', 'csv'],
        key="contas"
    )
    
    dados = {}
    nomes_arquivos = {}  # NOVO: armazenar nomes dos arquivos
    
    # Carregar dados de pagamentos
    if upload_pagamentos is not None:
        try:
            if upload_pagamentos.name.endswith('.xlsx'):
                df_pagamentos = pd.read_excel(upload_pagamentos)
            else:
                df_pagamentos = pd.read_csv(upload_pagamentos)
            
            # NOVO: Salvar nome do arquivo
            nomes_arquivos['pagamentos'] = upload_pagamentos.name
            
            df_pagamentos = processar_colunas_data(df_pagamentos)
            df_pagamentos = processar_colunas_valor(df_pagamentos)
            df_pagamentos = padronizar_documentos(df_pagamentos)
            
            dados['pagamentos'] = df_pagamentos
            st.sidebar.success(f"✅ Pagamentos: {len(dados['pagamentos'])} registros - {upload_pagamentos.name}")
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
            
            # NOVO: Salvar nome do arquivo
            nomes_arquivos['contas'] = upload_contas.name
            
            df_contas = processar_colunas_data(df_contas)
            df_contas = padronizar_documentos(df_contas)
            
            dados['contas'] = df_contas
            st.sidebar.success(f"✅ Contas: {len(dados['contas'])} registros - {upload_contas.name}")
        except Exception as e:
            st.sidebar.error(f"❌ Erro ao carregar contas: {str(e)}")
            dados['contas'] = pd.DataFrame()
    else:
        dados['contas'] = pd.DataFrame()
        st.sidebar.info("📁 Aguardando planilha de abertura de contas")
    
    # NOVO: Retornar também os nomes dos arquivos
    return dados, nomes_arquivos

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
        'cpfs_duplicados_info': pd.DataFrame(),
        'total_cpfs_duplicados': 0
    }
    
    if dados['pagamentos'].empty:
        return analise
    
    df = dados['pagamentos'].copy()
    analise['total_pagamentos'] = len(df)
    
    coluna_conta = obter_coluna_conta(df)
    
    if coluna_conta:
        contas_validas = df[
            df[coluna_conta].notna() & 
            (df[coluna_conta].astype(str).str.strip() != '') &
            (df[coluna_conta].astype(str).str.strip() != 'NaN') &
            (df[coluna_conta].astype(str).str.strip() != 'None')
        ]
        
        analise['contas_unicas'] = contas_validas[coluna_conta].nunique()
        
        contas_com_problemas = df[
            df[coluna_conta].isna() | 
            (df[coluna_conta].astype(str).str.strip() == '') |
            (df[coluna_conta].astype(str).str.strip() == 'NaN') |
            (df[coluna_conta].astype(str).str.strip() == 'None')
        ]
        
        if not contas_com_problemas.empty:
            analise['contas_com_erros'] = contas_com_problemas.index.tolist()
    
    if coluna_conta:
        df_validos = df[
            df[coluna_conta].notna() & 
            (df[coluna_conta].astype(str).str.strip() != '') &
            (df[coluna_conta].astype(str).str.strip() != 'NaN') &
            (df[coluna_conta].astype(str).str.strip() != 'None')
        ].copy()
        
        if not df_validos.empty:
            contagem_contas = df_validos[coluna_conta].value_counts().reset_index()
            contagem_contas.columns = [coluna_conta, 'Quantidade_Pagamentos']
            
            contas_duplicadas = contagem_contas[contagem_contas['Quantidade_Pagamentos'] > 1]
            analise['pagamentos_duplicados'] = len(contas_duplicadas)
            
            if not contas_duplicadas.empty:
                contas_com_duplicidade = contas_duplicadas[coluna_conta].tolist()
                detalhes = df_validos[df_validos[coluna_conta].isin(contas_com_duplicidade)].copy()
                
                colunas_ordenacao = [coluna_conta]
                if 'Data' in detalhes.columns:
                    colunas_ordenacao.append('Data')
                elif 'Data Pagto' in detalhes.columns:
                    colunas_ordenacao.append('Data Pagto')
                detalhes = detalhes.sort_values(by=colunas_ordenacao)
                
                analise['detalhes_duplicados'] = detalhes
                
                if 'Valor_Limpo' in df_validos.columns:
                    try:
                        valor_duplicados = 0
                        for conta in contas_com_duplicidade:
                            pagamentos_conta = df_validos[df_validos[coluna_conta] == conta]
                            if len(pagamentos_conta) > 1:
                                valor_duplicados += pagamentos_conta.iloc[1:]['Valor_Limpo'].sum()
                        
                        analise['valor_total_duplicados'] = valor_duplicados
                    except Exception as e:
                        analise['valor_total_duplicados'] = 0
                
                resumo = []
                for conta in contas_com_duplicidade:
                    pagamentos_conta = df_validos[df_validos[coluna_conta] == conta]
                    qtd = len(pagamentos_conta)
                    
                    info = {
                        'Numero_Conta': conta,
                        'Quantidade_Pagamentos': qtd,
                    }
                    
                    if 'CPF' in pagamentos_conta.columns:
                        cpfs = pagamentos_conta['CPF'].unique()
                        if len(cpfs) == 1:
                            info['CPF'] = cpfs[0]
                        else:
                            info['CPF'] = f"Múltiplos: {', '.join(map(str, cpfs[:2]))}"
                    
                    coluna_beneficiario = obter_coluna_beneficiario(pagamentos_conta)
                    if coluna_beneficiario:
                        beneficiarios = pagamentos_conta[coluna_beneficiario].unique()
                        if len(beneficiarios) == 1:
                            info['Beneficiario'] = beneficiarios[0]
                        else:
                            info['Beneficiario'] = f"Múltiplos: {', '.join(map(str, beneficiarios[:2]))}"
                    
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
    
    if 'CPF' in df.columns:
        cpfs_validos = df[
            df['CPF'].notna() & 
            (df['CPF'].astype(str).str.strip() != '') &
            (df['CPF'].astype(str).str.strip() != 'NaN') &
            (df['CPF'].astype(str).str.strip() != 'None')
        ]
        
        if not cpfs_validos.empty:
            contagem_cpf = cpfs_validos['CPF'].value_counts().reset_index()
            contagem_cpf.columns = ['CPF', 'Quantidade_Ocorrencias']
            
            cpfs_duplicados = contagem_cpf[contagem_cpf['Quantidade_Ocorrencias'] > 1]
            analise['total_cpfs_duplicados'] = len(cpfs_duplicados)
            
            if not cpfs_duplicados.empty:
                cpfs_com_duplicidade = cpfs_duplicados['CPF'].tolist()
                detalhes_cpfs = cpfs_validos[cpfs_validos['CPF'].isin(cpfs_com_duplicidade)].copy()
                detalhes_cpfs = detalhes_cpfs.sort_values(by=['CPF'])
                
                if coluna_conta:
                    detalhes_cpfs['Pagamento_Duplicado_Real'] = detalhes_cpfs.duplicated(
                        subset=[coluna_conta], keep=False
                    )
                
                analise['cpfs_duplicados_info'] = detalhes_cpfs
    
    return analise

# FUNÇÃO processar_dados ATUALIZADA: receber nomes dos arquivos
def processar_dados(dados, nomes_arquivos=None):
    """Processa os dados para o dashboard"""
    metrics = {}
    
    # Análise de duplicidades
    analise_dup = analisar_duplicidades(dados)
    metrics.update(analise_dup)
    
    # Análise de ausência de dados COM INFORMAÇÕES DA PLANILHA
    analise_ausencia = analisar_ausencia_dados(
        dados, 
        nome_arquivo_pagamentos=nomes_arquivos.get('pagamentos') if nomes_arquivos else None,
        nome_arquivo_contas=nomes_arquivos.get('contas') if nomes_arquivos else None
    )
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

# Funções auxiliares
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

# Dashboard MELHORADO: mostrar informações da planilha original
def mostrar_dashboard(dados, nomes_arquivos=None):
    st.header("📊 Dashboard Executivo - POT")
    
    metrics = processar_dados(dados, nomes_arquivos)
    
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
    
    # NOVO: Mostrar nomes dos arquivos carregados
    if nomes_arquivos:
        col_arq1, col_arq2 = st.columns(2)
        with col_arq1:
            if 'pagamentos' in nomes_arquivos:
                st.info(f"📋 **Planilha de Pagamentos:** {nomes_arquivos['pagamentos']}")
        with col_arq2:
            if 'contas' in nomes_arquivos:
                st.info(f"🏦 **Planilha de Contas:** {nomes_arquivos['contas']}")
    
    # CORREÇÃO: Alertas com informações da planilha original
    if metrics.get('total_registros_criticos', 0) > 0:
        st.error(f"🚨 **DADOS CRÍTICOS AUSENTES** - {formatar_brasileiro(metrics.get('total_registros_criticos', 0), 'numero')} registros com dados essenciais ausentes")
        
        col_alert1, col_alert2 = st.columns([3, 1])
        
        with col_alert1:
            st.warning("""
            **Apenas problemas críticos identificados:**
            - CPF completamente ausente
            - Número da conta ausente  
            - Valor ausente ou zerado
            
            **📍 Localização na planilha:** 
            - A coluna 'Linha_Planilha' mostra a linha exata na planilha original
            - A coluna 'Planilha_Origem' mostra o arquivo de origem
            """)
            
        with col_alert2:
            if not metrics['registros_problema_detalhados'].empty:
                # NOVO: Incluir informações da planilha no CSV de exportação
                df_export = metrics['registros_problema_detalhados'].copy()
                if 'Linha_Planilha_Original' not in df_export.columns:
                    df_export['Linha_Planilha_Original'] = df_export.index + 2
                df_export['Planilha_Origem'] = metrics.get('nome_arquivo_pagamentos', 'Pagamentos')
                
                csv_problemas = df_export.to_csv(index=False, sep=';')
                st.download_button(
                    label="📥 Exportar para Correção",
                    data=csv_problemas,
                    file_name=f"dados_criticos_ausentes_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    help="Baixe esta lista com informações da planilha original para correção"
                )
        
        # NOVO: Expandir para mostrar detalhes com informações da planilha
        with st.expander("🔍 **Ver Detalhes dos Dados Ausentes com Localização na Planilha**", expanded=False):
            if not metrics['resumo_ausencias'].empty:
                # Ordenar colunas para mostrar primeiro as informações de localização
                colunas_ordenadas = ['Linha_Planilha', 'Planilha_Origem', 'Problemas_Identificados']
                colunas_restantes = [col for col in metrics['resumo_ausencias'].columns if col not in colunas_ordenadas]
                colunas_exibir = colunas_ordenadas + colunas_restantes
                
                st.dataframe(
                    metrics['resumo_ausencias'][colunas_exibir],
                    use_container_width=True,
                    hide_index=True,
                    height=400
                )
                
                st.info(f"📍 **Localização para correção:** Mostrando {len(metrics['resumo_ausencias'])} de {metrics['total_registros_criticos']} registros problemáticos. Use a coluna 'Linha_Planilha' para encontrar rapidamente os registros na planilha original.")
    
    # Informações sobre documentos processados
    if metrics.get('cpfs_com_zeros_adicional', 0) > 0:
        st.success(f"✅ **CPFS NORMALIZADOS** - {formatar_brasileiro(metrics.get('cpfs_com_zeros_adicional', 0), 'numero')} CPFs receberam zeros à esquerda")
    
    if metrics.get('cpfs_formatos_diferentes', 0) > 0:
        st.info(f"ℹ️ **CPFS DE OUTROS ESTADOS** - {formatar_brasileiro(metrics.get('cpfs_formatos_diferentes', 0), 'numero')} CPFs com formatos especiais processados")
    
    if metrics.get('registros_validos_com_x', 0) > 0:
        st.success(f"✅ **RGS VÁLIDOS** - {formatar_brasileiro(metrics.get('registros_validos_com_x', 0), 'numero')} RGs com 'X' identificados como válidos")
    
    if metrics.get('documentos_padronizados', 0) > 0:
        st.success(f"✅ **DOCUMENTOS PROCESSADOS** - {formatar_brasileiro(metrics.get('documentos_padronizados', 0), 'numero')} documentos padronizados")

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
    
    if metrics.get('valor_total', 0) > 0:
        st.metric("Valor Total dos Pagamentos", formatar_brasileiro(metrics['valor_total'], 'monetario'))
    
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

# [As funções restantes de interface permanecem similares, atualizando para receber nomes_arquivos]

def mostrar_importacao():
    st.header("📥 Estrutura das Planilhas")
    
    st.info("""
    **💡 USE O MENU LATERAL PARA CARREGAR AS PLANILHAS!**
    
    **📍 NOVO:** O sistema agora mostra a linha exata da planilha original onde estão os dados ausentes!
    """)
    
    with st.expander("📋 Estrutura das Planilhas Necessárias"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**📋 Planilha de Pagamentos:**")
            st.code("""
Data ou Data Pagto (dd/mm/aaaa)
Beneficiário (texto)
CPF (número - aceita formatos de todos os estados)
RG (número, pode conter X)
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
CPF (número - aceita formatos de todos os estados)
RG (número, pode conter X)
Projeto (texto)
Agência (texto/número)
*Outras colunas opcionais*
            """)

def mostrar_consultas(dados):
    st.header("🔍 Consultas de Dados")
    
    opcao_consulta = st.radio(
        "Tipo de consulta:",
        ["Por CPF", "Por Projeto", "Por Número da Conta"],
        horizontal=True
    )
    
    if opcao_consulta == "Por CPF":
        col1, col2 = st.columns([2, 1])
        with col1:
            cpf = st.text_input("Digite o CPF (qualquer formato):", placeholder="123.456.789-00 ou 12345678900")
        with col2:
            if st.button("🔍 Buscar CPF", use_container_width=True):
                if cpf:
                    resultados = {}
                    if not dados['pagamentos'].empty and 'CPF' in dados['pagamentos'].columns:
                        cpf_busca = processar_cpf(cpf)
                        resultados['pagamentos'] = dados['pagamentos'][dados['pagamentos']['CPF'].astype(str).str.contains(cpf_busca)]
                    if not dados['contas'].empty and 'CPF' in dados['contas'].columns:
                        cpf_busca = processar_cpf(cpf)
                        resultados['contas'] = dados['contas'][dados['contas']['CPF'].astype(str).str.contains(cpf_busca)]
                    
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
    
    else:
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
    
    st.markdown("---")
    st.subheader("Resultados da Consulta")
    
    if 'resultados_consulta' in st.session_state:
        resultados = st.session_state.resultados_consulta
        
        if resultados.get('pagamentos') is not None and not resultados['pagamentos'].empty:
            st.markdown("**📋 Pagamentos Encontrados:**")
            
            colunas_display = [col for col in ['Data', 'Data Pagto', 'Beneficiário', 'CPF', 'Projeto', 'Valor', 'Status'] 
                             if col in resultados['pagamentos'].columns]
            
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

def mostrar_relatorios(dados, nomes_arquivos=None):
    st.header("📋 Gerar Relatórios")
    
    metrics = processar_dados(dados, nomes_arquivos)
    
    if metrics.get('pagamentos_duplicados', 0) > 0:
        st.warning(f"🚨 **ALERTA:** Foram identificados {formatar_brasileiro(metrics.get('pagamentos_duplicados', 0), 'numero')} contas com pagamentos duplicados")
    
    if metrics.get('total_registros_criticos', 0) > 0:
        st.error(f"🚨 **ALERTA:** {formatar_brasileiro(metrics.get('total_registros_criticos', 0), 'numero')} registros com dados críticos ausentes")
    
    if metrics.get('cpfs_com_zeros_adicional', 0) > 0:
        st.success(f"✅ **INFORMAÇÃO:** {formatar_brasileiro(metrics.get('cpfs_com_zeros_adicional', 0), 'numero')} CPFs receberam zeros à esquerda")
    
    if metrics.get('total_cpfs_duplicados', 0) > 0:
        st.info(f"ℹ️ **INFORMAÇÃO:** {formatar_brasileiro(metrics.get('total_cpfs_duplicados', 0), 'numero')} CPFs com múltiplas ocorrências")
    
    st.info("""
    **Escolha o formato do relatório:**
    - **📄 PDF Executivo**: Relatório visual e profissional para apresentações
    - **📊 Excel Completo**: Dados detalhados para análise técnica
    """)
    
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
        if st.button("📄 Gerar PDF Executivo", type="primary", use_container_width=True):
            st.info("📄 Funcionalidade de PDF em desenvolvimento...")
    
    with col2:
        if st.button("📊 Gerar Excel Completo", type="secondary", use_container_width=True):
            st.info("📊 Funcionalidade de Excel em desenvolvimento...")

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
        st.markdown("3.0 - Com localização na planilha original")

def main():
    email = autenticar()
    
    if not email:
        st.info("👆 Informe seu email institucional para acessar o sistema")
        return
    
    st.success(f"✅ Acesso permitido: {email}")
    
    # NOVO: Receber tanto os dados quanto os nomes dos arquivos
    dados, nomes_arquivos = carregar_dados()
    
    st.title("🏛️ Sistema POT - Programa Operação Trabalho")
    st.markdown("**📍 NOVO: Mostra a linha exata da planilha onde estão os dados ausentes!**")
    st.markdown("---")
    
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Dashboard", 
        "📥 Importar Dados", 
        "🔍 Consultas", 
        "📋 Relatórios"
    ])
    
    with tab1:
        mostrar_dashboard(dados, nomes_arquivos)
    
    with tab2:
        mostrar_importacao()
    
    with tab3:
        mostrar_consultas(dados)
    
    with tab4:
        mostrar_relatorios(dados, nomes_arquivos)
    
    mostrar_rodape()

if __name__ == "__main__":
    main()
