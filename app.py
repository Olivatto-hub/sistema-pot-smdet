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

# FUNÇÃO MELHORADA: Analisar ausência de dados com critérios realistas
def analisar_ausencia_dados(dados):
    """Analisa e reporta apenas dados críticos realmente ausentes"""
    analise_ausencia = {
        'registros_criticos_problematicos': [],
        'total_registros_criticos': 0,
        'colunas_com_ausencia_critica': {},
        'resumo_ausencias': pd.DataFrame(),
        'registros_problema_detalhados': pd.DataFrame(),
        'documentos_padronizados': 0,
        'tipos_problemas': {},
        'registros_validos_com_x': 0,
        'cpfs_com_zeros_adicional': 0,  # CPFs que receberam zeros à esquerda
        'cpfs_formatos_diferentes': 0   # CPFs com formatos especiais de outros estados
    }
    
    if not dados['pagamentos'].empty:
        df = dados['pagamentos'].copy()
        
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
            # CPFs que originalmente tinham menos de 11 dígitos
            cpfs_com_zeros = df[
                df['CPF'].notna() & 
                (df['CPF'].astype(str).str.len() < 11) &
                (df['CPF'].astype(str).str.strip() != '') &
                (df['CPF'].astype(str).str.strip() != 'NaN') &
                (df['CPF'].astype(str).str.strip() != 'None')
            ]
            analise_ausencia['cpfs_com_zeros_adicional'] = len(cpfs_com_zeros)
            
            # CPFs com formatos especiais (pontos, traços)
            cpfs_com_formatos = df[
                df['CPF'].notna() & 
                (df['CPF'].astype(str).str.contains(r'[.-]', na=False))
            ]
            analise_ausencia['cpfs_formatos_diferentes'] = len(cpfs_com_formatos)
        
        # CRITÉRIO CORRIGIDO: Apenas dados realmente críticos ausentes
        registros_problematicos = []
        
        # 1. CPF COMPLETAMENTE AUSENTE (não formato diferente)
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
        
        # 2. Número da conta ausente (critério importante para duplicidade)
        coluna_conta = obter_coluna_conta(df)
        if coluna_conta:
            mask_conta_ausente = (
                df[coluna_conta].isna() | 
                (df[coluna_conta].astype(str).str.strip() == '') |
                (df[coluna_conta].astype(str).str.strip() == 'NaN') |
                (df[coluna_conta].astype(str).str.strip() == 'None')
            )
            contas_ausentes = df[mask_conta_ausente]
            # Adicionar apenas os novos registros problemáticos
            for idx in contas_ausentes.index:
                if idx not in registros_problematicos:
                    registros_problematicos.append(idx)
        
        # 3. Valor ausente ou zero (problema financeiro)
        if 'Valor' in df.columns:
            mask_valor_invalido = (
                df['Valor'].isna() | 
                (df['Valor'].astype(str).str.strip() == '') |
                (df['Valor'].astype(str).str.strip() == 'NaN') |
                (df['Valor'].astype(str).str.strip() == 'None') |
                (df['Valor_Limpo'] == 0)  # Valor zerado
            )
            valores_invalidos = df[mask_valor_invalido]
            # Adicionar apenas os novos registros problemáticos
            for idx in valores_invalidos.index:
                if idx not in registros_problematicos:
                    registros_problematicos.append(idx)
        
        # Atualizar análise com registros realmente problemáticos
        analise_ausencia['registros_criticos_problematicos'] = registros_problematicos
        analise_ausencia['total_registros_criticos'] = len(registros_problematicos)
        
        if registros_problematicos:
            analise_ausencia['registros_problema_detalhados'] = df.loc[registros_problematicos].copy()
        
        # Analisar ausência por coluna crítica (apenas para informação)
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
        
        # Criar resumo de ausências para exibição (apenas registros realmente problemáticos)
        if registros_problematicos:
            resumo = []
            for idx in registros_problematicos[:50]:  # Limitar para performance
                registro = df.loc[idx]
                info_ausencia = {'Indice_Registro': idx}
                
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
                
                # Marcar campos problemáticos de forma precisa
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
            df_pagamentos = padronizar_documentos(df_pagamentos)
            
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
            df_contas = padronizar_documentos(df_contas)
            
            dados['contas'] = df_contas
            st.sidebar.success(f"✅ Contas: {len(dados['contas'])} registros")
        except Exception as e:
            st.sidebar.error(f"❌ Erro ao carregar contas: {str(e)}")
            dados['contas'] = pd.DataFrame()
    else:
        dados['contas'] = pd.DataFrame()
        st.sidebar.info("📁 Aguardando planilha de abertura de contas")
    
    return dados

# [As funções restantes permanecem iguais, apenas atualizando as mensagens no dashboard]

def mostrar_dashboard(dados):
    st.header("📊 Dashboard Executivo - POT")
    
    metrics = processar_dados(dados)
    
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
    
    # CORREÇÃO: Alertas mais específicos e informativos
    if metrics.get('total_registros_criticos', 0) > 0:
        st.error(f"🚨 **DADOS CRÍTICOS AUSENTES** - {formatar_brasileiro(metrics.get('total_registros_criticos', 0), 'numero')} registros com dados essenciais ausentes")
        
        col_alert1, col_alert2 = st.columns([3, 1])
        
        with col_alert1:
            st.warning("""
            **Apenas problemas críticos identificados:**
            - CPF completamente ausente
            - Número da conta ausente  
            - Valor ausente ou zerado
            """)
            
        with col_alert2:
            if not metrics['registros_problema_detalhados'].empty:
                csv_problemas = metrics['registros_problema_detalhados'].to_csv(index=False, sep=';')
                st.download_button(
                    label="📥 Exportar para Correção",
                    data=csv_problemas,
                    file_name=f"dados_criticos_ausentes_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    help="Baixe esta lista para corrigir apenas dados essenciais ausentes"
                )
    
    # NOVAS INFORMAÇÕES: Documentos processados corretamente
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

# [As funções restantes permanecem iguais...]

# Funções auxiliares (obter_coluna_beneficiario, obter_coluna_data, etc.) permanecem as mesmas
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

# [Restante do código permanece igual...]

def main():
    email = autenticar()
    
    if not email:
        st.info("👆 Informe seu email institucional para acessar o sistema")
        return
    
    st.success(f"✅ Acesso permitido: {email}")
    
    dados = carregar_dados()
    
    st.title("🏛️ Sistema POT - Programa Operação Trabalho")
    st.markdown("Desenvolvido para Secretaria Municipal do Desenvolvimento Econômico e Trabalho")
    st.markdown("---")
    
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
