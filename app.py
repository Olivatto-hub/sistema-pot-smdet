[file name]: deepseek_python_20251128_6f44cc.py
[file content begin]
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

# Função auxiliar para obter coluna de conta
def obter_coluna_conta(df):
    """Identifica a coluna que contém o número da conta"""
    colunas_conta = ['Num Cartao', 'Num_Cartao', 'Conta', 'Número da Conta', 'Numero_Conta']
    for coluna in colunas_conta:
        if coluna in df.columns:
            return coluna
    return None

# Função auxiliar para formatar valores no padrão brasileiro
def formatar_brasileiro(valor, tipo='numero'):
    """Formata valores no padrão brasileiro"""
    if tipo == 'monetario':
        return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    elif tipo == 'numero':
        return f"{valor:,}".replace(',', '.')
    else:
        return str(valor)

# Função para processar dados principais
def processar_dados(dados, nomes_arquivos=None):
    """Processa os dados para gerar métricas e análises"""
    metrics = {
        'beneficiarios_unicos': 0,
        'total_pagamentos': 0,
        'contas_unicas': 0,
        'projetos_ativos': 0,
        'valor_total': 0,
        'pagamentos_duplicados': 0,
        'valor_total_duplicados': 0,
        'total_cpfs_duplicados': 0
    }
    
    # Combinar com análise de ausência de dados
    analise_ausencia = analisar_ausencia_dados(dados, nomes_arquivos.get('pagamentos'), nomes_arquivos.get('contas'))
    metrics.update(analise_ausencia)
    
    if not dados['pagamentos'].empty:
        df = dados['pagamentos']
        
        # Beneficiários únicos
        coluna_beneficiario = 'Beneficiario' if 'Beneficiario' in df.columns else 'Beneficiário'
        if coluna_beneficiario in df.columns:
            metrics['beneficiarios_unicos'] = df[coluna_beneficiario].nunique()
        
        # Total de pagamentos
        metrics['total_pagamentos'] = len(df)
        
        # Contas únicas
        coluna_conta = obter_coluna_conta(df)
        if coluna_conta:
            metrics['contas_unicas'] = df[coluna_conta].nunique()
            
            # Verificar duplicidades
            contas_duplicadas = df[df.duplicated([coluna_conta], keep=False)]
            if not contas_duplicadas.empty:
                metrics['pagamentos_duplicados'] = contas_duplicadas[coluna_conta].nunique()
                
                # Calcular valor total das duplicidades
                if 'Valor_Limpo' in contas_duplicadas.columns:
                    metrics['valor_total_duplicados'] = contas_duplicadas['Valor_Limpo'].sum()
        
        # Projetos ativos
        if 'Projeto' in df.columns:
            metrics['projetos_ativos'] = df['Projeto'].nunique()
        
        # Valor total
        if 'Valor_Limpo' in df.columns:
            metrics['valor_total'] = df['Valor_Limpo'].sum()
        
        # CPFs duplicados
        if 'CPF' in df.columns:
            cpfs_duplicados = df[df.duplicated(['CPF'], keep=False)]
            metrics['total_cpfs_duplicados'] = cpfs_duplicados['CPF'].nunique()
    
    return metrics

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

# FUNÇÃO CORRIGIDA: Padronizar documentos considerando TODAS as letras válidas em RGs
def padronizar_documentos(df):
    """Padroniza RGs e CPFs, aceitando todas as letras válidas em RGs"""
    df_processed = df.copy()
    
    # Colunas que podem conter documentos
    colunas_documentos = ['RG', 'CPF', 'Documento', 'Numero_Documento']
    
    for coluna in colunas_documentos:
        if coluna in df_processed.columns:
            try:
                if coluna == 'RG':
                    # CORREÇÃO: Para RG: manter números e TODAS as letras (A-Z) que podem aparecer em RGs
                    # Inclui X, V, W, Y, Z e outras letras que podem ser usadas em RGs
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

# FUNÇÃO MELHORADA: Analisar ausência de dados considerando TODAS as letras válidas em RGs
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
        'registros_validos_com_letras': 0,  # CORREÇÃO: Agora conta TODAS as letras válidas
        'cpfs_com_zeros_adicional': 0,
        'cpfs_formatos_diferentes': 0,
        'nome_arquivo_pagamentos': nome_arquivo_pagamentos,
        'nome_arquivo_contas': nome_arquivo_contas,
        'rgs_com_letras_especificas': {}  # NOVO: Detalha quais letras foram encontradas
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
        
        # CORREÇÃO: Contar RGs válidos com QUALQUER letra (não apenas X)
        if 'RG' in df.columns:
            # Expressão regular para encontrar RGs com qualquer letra (A-Z)
            rgs_com_letras = df[df['RG'].astype(str).str.contains(r'[A-Za-z]', na=False)]
            analise_ausencia['registros_validos_com_letras'] = len(rgs_com_letras)
            
            # NOVO: Detalhar quais letras específicas foram encontradas
            letras_encontradas = {}
            for _, row in rgs_com_letras.iterrows():
                rg_str = str(row['RG'])
                # Encontrar todas as letras no RG
                letras = re.findall(r'[A-Za-z]', rg_str)
                for letra in letras:
                    letra_upper = letra.upper()
                    letras_encontradas[letra_upper] = letras_encontradas.get(letra_upper, 0) + 1
            
            analise_ausencia['rgs_com_letras_especificas'] = letras_encontradas
        
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
            for idx in registros_problematicos[:100]:
                registro = df.loc[idx]
                info_ausencia = {
                    'Indice_Registro': idx,
                    'Linha_Planilha': registro.get('Linha_Planilha_Original', idx + 2),
                    'Planilha_Origem': nome_arquivo_pagamentos or 'Pagamentos'
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
    nomes_arquivos = {}
    
    # Carregar dados de pagamentos
    if upload_pagamentos is not None:
        try:
            if upload_pagamentos.name.endswith('.xlsx'):
                df_pagamentos = pd.read_excel(upload_pagamentos)
            else:
                df_pagamentos = pd.read_csv(upload_pagamentos)
            
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
    
    return dados, nomes_arquivos

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
    
    # Mostrar nomes dos arquivos carregados
    if nomes_arquivos:
        col_arq1, col_arq2 = st.columns(2)
        with col_arq1:
            if 'pagamentos' in nomes_arquivos:
                st.info(f"📋 **Planilha de Pagamentos:** {nomes_arquivos['pagamentos']}")
        with col_arq2:
            if 'contas' in nomes_arquivos:
                st.info(f"🏦 **Planilha de Contas:** {nomes_arquivos['contas']}")
    
    # CORREÇÃO: Alertas com informações sobre TODAS as letras em RGs
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
        
        with st.expander("🔍 **Ver Detalhes dos Dados Ausentes com Localização na Planilha**", expanded=False):
            if not metrics['resumo_ausencias'].empty:
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
    
    # CORREÇÃO: Informações sobre RGs com TODAS as letras válidas
    if metrics.get('registros_validos_com_letras', 0) > 0:
        st.success(f"✅ **RGS VÁLIDOS IDENTIFICADOS** - {formatar_brasileiro(metrics.get('registros_validos_com_letras', 0), 'numero')} RGs com letras válidas processados")
        
        # NOVO: Mostrar detalhes das letras específicas encontradas
        if metrics.get('rgs_com_letras_especificas'):
            letras_info = []
            for letra, quantidade in metrics['rgs_com_letras_especificas'].items():
                letras_info.append(f"{letra}: {quantidade}")
            
            if letras_info:
                st.info(f"🔤 **Letras encontradas em RGs:** {', '.join(letras_info)}")
    
    if metrics.get('cpfs_com_zeros_adicional', 0) > 0:
        st.success(f"✅ **CPFS NORMALIZADOS** - {formatar_brasileiro(metrics.get('cpfs_com_zeros_adicional', 0), 'numero')} CPFs receberam zeros à esquerda")
    
    if metrics.get('cpfs_formatos_diferentes', 0) > 0:
        st.info(f"ℹ️ **CPFS DE OUTROS ESTADOS** - {formatar_brasileiro(metrics.get('cpfs_formatos_diferentes', 0), 'numero')} CPFs com formatos especiais processados")
    
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

def mostrar_importacao():
    st.header("📥 Estrutura das Planilhas")
    
    st.info("""
    **💡 USE O MENU LATERAL PARA CARREGAR AS PLANILHAS!**
    
    **📍 NOVO:** O sistema agora mostra a linha exata da planilha original onde estão os dados ausentes!
    
    **🔤 MELHORIA:** Aceita TODAS as letras válidas em RGs (X, V, W, Y, Z, etc.)
    """)
    
    with st.expander("📋 Estrutura das Planilhas Necessárias"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**📋 Planilha de Pagamentos:**")
            st.code("""
Data ou Data Pagto (dd/mm/aaaa)
Beneficiário (texto)
CPF (número - aceita formatos de todos os estados)
RG (número, pode conter X, V, W, Y, Z, etc.)
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
RG (número, pode conter X, V, W, Y, Z, etc.)
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
    
    # CORREÇÃO: Informações sobre RGs com todas as letras
    if metrics.get('registros_validos_com_letras', 0) > 0:
        st.success(f"✅ **INFORMAÇÃO:** {formatar_brasileiro(metrics.get('registros_validos_com_letras', 0), 'numero')} RGs com letras válidas identificados")
    
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
        if st.button("📄 Gerar PDF Executivo", use_container_width=True):
            st.info("Funcionalidade de PDF em desenvolvimento...")
    
    with col2:
        if st.button("📊 Gerar Excel Completo", use_container_width=True):
            if not dados['pagamentos'].empty:
                # Criar um arquivo Excel com múltiplas abas
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    dados['pagamentos'].to_excel(writer, sheet_name='Pagamentos', index=False)
                    if not dados['contas'].empty:
                        dados['contas'].to_excel(writer, sheet_name='Contas', index=False)
                    
                    # Adicionar aba de métricas
                    metricas_df = pd.DataFrame([metrics])
                    metricas_df.to_excel(writer, sheet_name='Métricas', index=False)
                
                output.seek(0)
                
                st.download_button(
                    label="📥 Baixar Excel",
                    data=output,
                    file_name=f"relatorio_pot_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.warning("Nenhum dado disponível para exportar")

# Função principal
def main():
    # Autenticação
    email = autenticar()
    
    if email:
        st.sidebar.success(f"👤 Logado como: {email}")
        
        # Carregar dados
        dados, nomes_arquivos = carregar_dados()
        
        # Menu de navegação
        st.sidebar.markdown("---")
        pagina = st.sidebar.radio(
            "Navegação:",
            ["📊 Dashboard", "📥 Importar Dados", "🔍 Consultas", "📋 Relatórios"]
        )
        
        # Navegação entre páginas
        if pagina == "📊 Dashboard":
            mostrar_dashboard(dados, nomes_arquivos)
        elif pagina == "📥 Importar Dados":
            mostrar_importacao()
        elif pagina == "🔍 Consultas":
            mostrar_consultas(dados)
        elif pagina == "📋 Relatórios":
            mostrar_relatorios(dados, nomes_arquivos)
    
    # Rodapé
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "**Sistema POT - SMDET**  \n"
        "Prefeitura de São Paulo  \n"
        f"© {datetime.now().year} - Versão 2.0"
    )

if __name__ == "__main__":
    main()
[file content end]
