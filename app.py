# app.py
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
import hashlib
import sqlite3
from sqlite3 import Error
import os
import json

# Configuração da página
st.set_page_config(
    page_title="Sistema POT - SMDET",
    page_icon="🏛️",
    layout="wide"
)

# Sistema de banco de dados
def init_database():
    """Inicializa o banco de dados SQLite"""
    conn = sqlite3.connect('pot_smdet.db', check_same_thread=False)
    
    # Tabela para armazenar dados de pagamentos
    conn.execute('''
        CREATE TABLE IF NOT EXISTS pagamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes_referencia TEXT NOT NULL,
            ano_referencia INTEGER NOT NULL,
            data_importacao TEXT NOT NULL,
            nome_arquivo TEXT NOT NULL,
            dados_json TEXT NOT NULL,
            metadados_json TEXT NOT NULL
        )
    ''')
    
    # Tabela para armazenar dados de inscrições/contas
    conn.execute('''
        CREATE TABLE IF NOT EXISTS inscricoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes_referencia TEXT NOT NULL,
            ano_referencia INTEGER NOT NULL,
            data_importacao TEXT NOT NULL,
            nome_arquivo TEXT NOT NULL,
            dados_json TEXT NOT NULL,
            metadados_json TEXT NOT NULL
        )
    ''')
    
    # Tabela para métricas consolidadas
    conn.execute('''
        CREATE TABLE IF NOT EXISTS metricas_mensais (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            mes_referencia TEXT NOT NULL,
            ano_referencia INTEGER NOT NULL,
            total_registros INTEGER,
            beneficiarios_unicos INTEGER,
            contas_unicas INTEGER,
            valor_total REAL,
            pagamentos_duplicados INTEGER,
            valor_duplicados REAL,
            projetos_ativos INTEGER,
            registros_problema INTEGER,
            cpfs_ajuste INTEGER,
            data_calculo TEXT NOT NULL
        )
    ''')
    
    conn.commit()
    return conn

# Função para hash de senha
def hash_senha(senha):
    """Gera hash SHA-256 da senha"""
    return hashlib.sha256(senha.encode()).hexdigest()

# Senha autorizada (Smdetpot2025)
SENHA_AUTORIZADA_HASH = hash_senha("Smdetpot2025")

# Função para obter data/hora no fuso horário de Brasília (São Paulo)
def agora_brasilia():
    """Retorna a data e hora atual no fuso horário de Brasília"""
    fuso_brasilia = timezone(timedelta(hours=-3))
    return datetime.now(timezone.utc).astimezone(fuso_brasilia)

def data_atual_brasilia():
    """Retorna a data atual no formato dd/mm/aaaa no fuso de Brasília"""
    return agora_brasilia().strftime("%d/%m/%Y")

def data_hora_atual_brasilia():
    """Retorna a data e hora atual no formato dd/mm/aaaa às HH:MM no fuso de Brasília"""
    return agora_brasilia().strftime("%d/%m/%Y às %H:%M")

def data_hora_arquivo_brasilia():
    """Retorna a data e hora atual no formato para nome de arquivo no fuso de Brasília"""
    return agora_brasilia().strftime("%Y%m%d_%H%M")

# Sistema de autenticação seguro
def autenticar():
    st.sidebar.title("Sistema POT - SMDET")
    st.sidebar.markdown("**Prefeitura de São Paulo**")
    st.sidebar.markdown("**Secretaria Municipal do Desenvolvimento Econômico e Trabalho**")
    st.sidebar.markdown("---")
    
    # Inicializar estado de autenticação
    if 'autenticado' not in st.session_state:
        st.session_state.autenticado = False
    if 'tentativas_login' not in st.session_state:
        st.session_state.tentativas_login = 0
    if 'bloqueado' not in st.session_state:
        st.session_state.bloqueado = False
    
    # Verificar se está bloqueado
    if st.session_state.bloqueado:
        st.sidebar.error("🚫 Sistema temporariamente bloqueado. Tente novamente mais tarde.")
        return None
    
    # Se já está autenticado, mostrar informações
    if st.session_state.autenticado:
        st.sidebar.success(f"✅ Acesso autorizado")
        st.sidebar.info(f"👤 {st.session_state.email_autorizado}")
        if st.sidebar.button("🚪 Sair"):
            st.session_state.autenticado = False
            st.session_state.email_autorizado = None
            st.rerun()
        return st.session_state.email_autorizado
    
    # Formulário de login
    with st.sidebar.form("login_form"):
        st.subheader("🔐 Acesso Restrito")
        email = st.text_input("Email institucional", placeholder="seu.email@prefeitura.sp.gov.br")
        senha = st.text_input("Senha", type="password", placeholder="Digite sua senha")
        submit = st.form_submit_button("Entrar")
        
        if submit:
            if not email or not senha:
                st.sidebar.error("⚠️ Preencha email e senha")
                st.session_state.tentativas_login += 1
            elif not email.endswith('@prefeitura.sp.gov.br'):
                st.sidebar.error("🚫 Acesso restrito aos servidores da Prefeitura de São Paulo")
                st.session_state.tentativas_login += 1
            elif hash_senha(senha) != SENHA_AUTORIZADA_HASH:
                st.sidebar.error("❌ Senha incorreta")
                st.session_state.tentativas_login += 1
            else:
                # Login bem-sucedido
                st.session_state.autenticado = True
                st.session_state.email_autorizado = email
                st.session_state.tentativas_login = 0
                st.sidebar.success("✅ Login realizado com sucesso!")
                st.rerun()
            
            # Verificar se excedeu tentativas
            if st.session_state.tentativas_login >= 3:
                st.session_state.bloqueado = True
                st.sidebar.error("🚫 Muitas tentativas falhas. Sistema bloqueado temporariamente.")
    
    return None

# Funções de banco de dados
def salvar_pagamentos_db(conn, mes_ref, ano_ref, nome_arquivo, dados_df, metadados):
    """Salva dados de pagamentos no banco de dados"""
    dados_json = dados_df.to_json(orient='records', date_format='iso')
    metadados_json = json.dumps(metadados)
    
    conn.execute('''
        INSERT INTO pagamentos (mes_referencia, ano_referencia, data_importacao, nome_arquivo, dados_json, metadados_json)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (mes_ref, ano_ref, data_hora_atual_brasilia(), nome_arquivo, dados_json, metadados_json))
    
    conn.commit()

def salvar_inscricoes_db(conn, mes_ref, ano_ref, nome_arquivo, dados_df, metadados):
    """Salva dados de inscrições no banco de dados"""
    dados_json = dados_df.to_json(orient='records', date_format='iso')
    metadados_json = json.dumps(metadados)
    
    conn.execute('''
        INSERT INTO inscricoes (mes_referencia, ano_referencia, data_importacao, nome_arquivo, dados_json, metadados_json)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (mes_ref, ano_ref, data_hora_atual_brasilia(), nome_arquivo, dados_json, metadados_json))
    
    conn.commit()

def salvar_metricas_db(conn, tipo, mes_ref, ano_ref, metrics):
    """Salva métricas no banco de dados para relatórios comparativos"""
    conn.execute('''
        INSERT INTO metricas_mensais (tipo, mes_referencia, ano_referencia, total_registros, 
                    beneficiarios_unicos, contas_unicas, valor_total, pagamentos_duplicados, 
                    valor_duplicados, projetos_ativos, registros_problema, cpfs_ajuste, data_calculo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (tipo, mes_ref, ano_ref, 
          metrics.get('total_pagamentos', 0),
          metrics.get('beneficiarios_unicos', 0),
          metrics.get('contas_unicas', 0),
          metrics.get('valor_total', 0),
          metrics.get('pagamentos_duplicados', 0),
          metrics.get('valor_total_duplicados', 0),
          metrics.get('projetos_ativos', 0),
          metrics.get('total_registros_criticos', 0),
          metrics.get('total_cpfs_ajuste', 0),
          data_hora_atual_brasilia()))
    
    conn.commit()

def carregar_pagamentos_db(conn, mes_ref=None, ano_ref=None):
    """Carrega dados de pagamentos do banco de dados"""
    query = "SELECT * FROM pagamentos"
    params = []
    
    if mes_ref and ano_ref:
        query += " WHERE mes_referencia = ? AND ano_referencia = ?"
        params = [mes_ref, ano_ref]
    
    query += " ORDER BY ano_referencia DESC, mes_referencia DESC"
    
    df_result = pd.read_sql_query(query, conn, params=params)
    return df_result

def carregar_inscricoes_db(conn, mes_ref=None, ano_ref=None):
    """Carrega dados de inscrições do banco de dados"""
    query = "SELECT * FROM inscricoes"
    params = []
    
    if mes_ref and ano_ref:
        query += " WHERE mes_referencia = ? AND ano_referencia = ?"
        params = [mes_ref, ano_ref]
    
    query += " ORDER BY ano_referencia DESC, mes_referencia DESC"
    
    df_result = pd.read_sql_query(query, conn, params=params)
    return df_result

def carregar_metricas_db(conn, tipo=None, periodo=None):
    """Carrega métricas do banco de dados para relatórios comparativos"""
    query = "SELECT * FROM metricas_mensais"
    params = []
    
    if tipo:
        query += " WHERE tipo = ?"
        params = [tipo]
    
    if periodo == 'trimestral':
        # Últimos 3 meses
        query += " ORDER BY ano_referencia DESC, mes_referencia DESC LIMIT 3"
    elif periodo == 'semestral':
        # Últimos 6 meses
        query += " ORDER BY ano_referencia DESC, mes_referencia DESC LIMIT 6"
    elif periodo == 'anual':
        # Últimos 12 meses
        query += " ORDER BY ano_referencia DESC, mes_referencia DESC LIMIT 12"
    else:
        query += " ORDER BY ano_referencia DESC, mes_referencia DESC"
    
    df_result = pd.read_sql_query(query, conn, params=params)
    return df_result

# Função auxiliar para obter coluna de conta
def obter_coluna_conta(df):
    """Identifica a coluna que contém o número da conta"""
    colunas_conta = ['Num Cartao', 'Num_Cartao', 'Conta', 'Número da Conta', 'Numero_Conta']
    for coluna in colunas_conta:
        if coluna in df.columns:
            return coluna
    return None

# Função auxiliar para obter coluna de nome/beneficiário
def obter_coluna_nome(df):
    """Identifica a coluna que contém o nome do beneficiário"""
    colunas_nome = ['Beneficiario', 'Beneficiário', 'Nome', 'Nome Completo']
    for coluna in colunas_nome:
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

# FUNÇÃO CORRIGIDA: Identificar e remover linha de totais - SEMPRE REMOVE A ÚLTIMA LINHA
def remover_linha_totais(df):
    """Identifica e remove a linha de totais da planilha (última linha com valores somados)"""
    if df.empty or len(df) <= 1:
        return df
    
    df_limpo = df.copy()
    
    # SEMPRE remover a última linha (linha de totais)
    df_limpo = df_limpo.iloc[:-1].copy()
    
    return df_limpo

# FUNÇÃO CORRIGIDA: Filtrar apenas pagamentos válidos (com número de conta)
def filtrar_pagamentos_validos(df):
    """Filtra apenas os registros que possuem número da conta (pagamentos válidos)"""
    coluna_conta = obter_coluna_conta(df)
    
    if not coluna_conta:
        return df
    
    # Filtrar apenas registros com número de conta preenchido
    df_filtrado = df[df[coluna_conta].notna() & (df[coluna_conta].astype(str).str.strip() != '')].copy()
    
    return df_filtrado

# FUNÇÃO CORRIGIDA: Detectar pagamentos duplicados com detalhes COMPLETOS
def detectar_pagamentos_duplicados(df):
    """Detecta pagamentos duplicados por número de conta e retorna detalhes completos"""
    duplicidades = {
        'contas_duplicadas': pd.DataFrame(),
        'total_contas_duplicadas': 0,
        'total_pagamentos_duplicados': 0,
        'valor_total_duplicados': 0,
        'resumo_duplicidades': pd.DataFrame(),
        'contas_com_multiplos_pagamentos': [],
        'detalhes_completos_duplicidades': pd.DataFrame()
    }
    
    # CORREÇÃO: Filtrar apenas pagamentos válidos (com número de conta)
    df = filtrar_pagamentos_validos(df)
    
    if df.empty:
        return duplicidades
    
    coluna_conta = obter_coluna_conta(df)
    coluna_nome = obter_coluna_nome(df)
    
    if not coluna_conta:
        return duplicidades
    
    # Encontrar contas com múltiplos pagamentos
    contagem_por_conta = df[coluna_conta].value_counts()
    contas_com_multiplos = contagem_por_conta[contagem_por_conta > 1].index.tolist()
    
    duplicidades['contas_com_multiplos_pagamentos'] = contas_com_multiplos
    
    if not contas_com_multiplos:
        return duplicidades
    
    # Filtrar apenas os registros duplicados
    df_duplicados = df[df[coluna_conta].isin(contas_com_multiplos)].copy()
    
    # Ordenar por conta e data (se disponível)
    colunas_ordenacao = [coluna_conta]
    colunas_data = ['Data', 'Data Pagto', 'Data_Pagto', 'DataPagto']
    for col_data in colunas_data:
        if col_data in df_duplicados.columns:
            colunas_ordenacao.append(col_data)
            break
    
    df_duplicados = df_duplicados.sort_values(by=colunas_ordenacao)
    
    # Adicionar contador de ocorrências por conta
    df_duplicados['Ocorrencia'] = df_duplicados.groupby(coluna_conta).cumcount() + 1
    df_duplicados['Total_Ocorrencias'] = df_duplicados.groupby(coluna_conta)[coluna_conta].transform('count')
    
    # Preparar dados completos para exibição - APENAS COLUNAS EXISTENTES
    colunas_exibicao_completas = [coluna_conta, 'Ocorrencia', 'Total_Ocorrencias']
    
    if coluna_nome and coluna_nome in df_duplicados.columns:
        colunas_exibicao_completas.append(coluna_nome)
    
    if 'CPF' in df_duplicados.columns:
        colunas_exibicao_completas.append('CPF')
    
    # Adicionar colunas de data EXISTENTES
    for col_data in colunas_data:
        if col_data in df_duplicados.columns:
            colunas_exibicao_completas.append(col_data)
            break
    
    if 'Valor' in df_duplicados.columns:
        colunas_exibicao_completas.append('Valor')
    
    if 'Valor_Limpo' in df_duplicados.columns:
        colunas_exibicao_completas.append('Valor_Limpo')
    
    if 'Projeto' in df_duplicados.columns:
        colunas_exibicao_completas.append('Projeto')
    
    if 'Status' in df_duplicados.columns:
        colunas_exibicao_completas.append('Status')
    
    # Garantir que só colunas existentes sejam usadas
    colunas_exibicao_completas = [col for col in colunas_exibicao_completas if col in df_duplicados.columns]
    
    # Atualizar métricas
    duplicidades['contas_duplicadas'] = df_duplicados[colunas_exibicao_completas]
    duplicidades['detalhes_completos_duplicidades'] = df_duplicados[colunas_exibicao_completas]
    duplicidades['total_contas_duplicadas'] = len(contas_com_multiplos)
    duplicidades['total_pagamentos_duplicados'] = len(df_duplicados)
    
    if 'Valor_Limpo' in df_duplicados.columns:
        duplicidades['valor_total_duplicados'] = df_duplicados['Valor_Limpo'].sum()
    
    # Criar resumo por conta
    resumo = []
    for conta in contas_com_multiplos:
        registros_conta = df_duplicados[df_duplicados[coluna_conta] == conta]
        primeiro_registro = registros_conta.iloc[0]
        
        info_conta = {
            'Conta': conta,
            'Total_Pagamentos': len(registros_conta),
            'Valor_Total': registros_conta['Valor_Limpo'].sum() if 'Valor_Limpo' in registros_conta.columns else 0,
            'Pagamentos_Extras': len(registros_conta) - 1
        }
        
        if coluna_nome and coluna_nome in primeiro_registro:
            info_conta['Nome'] = primeiro_registro[coluna_nome]
        
        if 'CPF' in registros_conta.columns:
            info_conta['CPF'] = primeiro_registro.get('CPF', '')
        
        # Datas dos pagamentos
        datas = []
        for col_data in colunas_data:
            if col_data in registros_conta.columns:
                datas = registros_conta[col_data].dropna().unique().tolist()
                if datas:
                    info_conta['Datas_Pagamentos'] = ', '.join([str(d) for d in datas])
                    break
        
        resumo.append(info_conta)
    
    duplicidades['resumo_duplicidades'] = pd.DataFrame(resumo)
    
    return duplicidades

# FUNÇÃO: Detectar pagamentos pendentes
def detectar_pagamentos_pendentes(dados):
    """Detecta possíveis pagamentos pendentes comparando contas abertas com pagamentos realizados"""
    pendentes = {
        'contas_sem_pagamento': pd.DataFrame(),
        'total_contas_sem_pagamento': 0,
        'beneficiarios_sem_pagamento': 0
    }
    
    # Só funciona se tivermos ambas as planilhas
    if 'contas' not in dados or dados['contas'].empty or 'pagamentos' not in dados or dados['pagamentos'].empty:
        return pendentes
    
    df_contas = dados['contas']
    df_pagamentos = dados['pagamentos']
    
    coluna_conta_contas = obter_coluna_conta(df_contas)
    coluna_conta_pagamentos = obter_coluna_conta(df_pagamentos)
    coluna_nome_contas = obter_coluna_nome(df_contas)
    
    if not coluna_conta_contas or not coluna_conta_pagamentos:
        return pendentes
    
    # CORREÇÃO: Filtrar apenas pagamentos válidos (com número de conta)
    df_pagamentos_validos = filtrar_pagamentos_validos(df_pagamentos)
    
    # Encontrar contas que estão na planilha de contas mas não na de pagamentos
    contas_com_pagamento = df_pagamentos_validos[coluna_conta_pagamentos].dropna().unique()
    contas_abertas = df_contas[coluna_conta_contas].dropna().unique()
    
    contas_sem_pagamento = [conta for conta in contas_abertas if conta not in contas_com_pagamento]
    
    if not contas_sem_pagamento:
        return pendentes
    
    # Filtrar contas sem pagamento
    df_contas_sem_pagamento = df_contas[df_contas[coluna_conta_contas].isin(contas_sem_pagamento)].copy()
    
    # Preparar colunas para exibição - APENAS COLUNAS EXISTENTES
    colunas_exibicao = [coluna_conta_contas]
    
    if coluna_nome_contas and coluna_nome_contas in df_contas_sem_pagamento.columns:
        colunas_exibicao.append(coluna_nome_contas)
    
    if 'CPF' in df_contas_sem_pagamento.columns:
        colunas_exibicao.append('CPF')
    
    if 'Projeto' in df_contas_sem_pagamento.columns:
        colunas_exibicao.append('Projeto')
    
    if 'Data_Abertura' in df_contas_sem_pagamento.columns:
        colunas_exibicao.append('Data_Abertura')
    elif 'Data' in df_contas_sem_pagamento.columns:
        colunas_exibicao.append('Data')
    
    # Garantir que só colunas existentes sejam usadas
    colunas_exibicao = [col for col in colunas_exibicao if col in df_contas_sem_pagamento.columns]
    
    # Adicionar status
    df_contas_sem_pagamento['Status'] = 'Aguardando Pagamento'
    
    pendentes['contas_sem_pagamento'] = df_contas_sem_pagamento[colunas_exibicao + ['Status']]
    pendentes['total_contas_sem_pagamento'] = len(contas_sem_pagamento)
    pendentes['beneficiarios_sem_pagamento'] = df_contas_sem_pagamento[coluna_nome_contas].nunique() if coluna_nome_contas and coluna_nome_contas in df_contas_sem_pagamento.columns else 0
    
    return pendentes

# NOVA FUNÇÃO: Processar CPF para manter apenas números
def processar_cpf(cpf):
    """Processa CPF, mantendo apenas números e completando com zeros à esquerda"""
    if pd.isna(cpf) or cpf in ['', 'NaN', 'None', 'nan', 'None', 'NULL']:
        return ''  # Manter como string vazia para campos em branco
    
    cpf_str = str(cpf).strip()
    
    # Remover TODOS os caracteres não numéricos
    cpf_limpo = re.sub(r'[^\d]', '', cpf_str)
    
    # Se ficou vazio após limpeza, retornar vazio
    if cpf_limpo == '':
        return ''
    
    # Completar com zeros à esquerda se tiver menos de 11 dígitos
    if len(cpf_limpo) < 11:
        cpf_limpo = cpf_limpo.zfill(11)
    
    return cpf_limpo

# FUNÇÃO ATUALIZADA: Padronizar documentos - CPF apenas números
def padronizar_documentos(df):
    """Padroniza RGs e CPFs, CPF apenas números"""
    df_processed = df.copy()
    
    # Colunas que podem conter documentos
    colunas_documentos = ['RG', 'CPF', 'Documento', 'Numero_Documento']
    
    for coluna in colunas_documentos:
        if coluna in df_processed.columns:
            try:
                if coluna == 'CPF':
                    # Para CPF: manter apenas números
                    df_processed[coluna] = df_processed[coluna].astype(str).apply(
                        lambda x: processar_cpf(x) if pd.notna(x) and str(x).strip() != '' else ''
                    )
                elif coluna == 'RG':
                    # Para RG: manter números e letras (podem ter letras em RGs)
                    df_processed[coluna] = df_processed[coluna].astype(str).apply(
                        lambda x: re.sub(r'[^a-zA-Z0-9/]', '', x) if pd.notna(x) and str(x).strip() != '' else ''
                    )
                else:
                    # Para outros documentos: tratamento genérico
                    df_processed[coluna] = df_processed[coluna].astype(str).apply(
                        lambda x: re.sub(r'[^\w]', '', x) if pd.notna(x) and str(x).strip() != '' else ''
                    )
                
            except Exception as e:
                st.warning(f"⚠️ Não foi possível padronizar a coluna '{coluna}': {str(e)}")
    
    return df_processed

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

# FUNÇÃO MELHORADA: Analisar ausência de dados considerando apenas pagamentos válidos
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
        'registros_validos_com_letras': 0,
        'cpfs_com_zeros_adicional': 0,
        'cpfs_formatos_diferentes': 0,
        'nome_arquivo_pagamentos': nome_arquivo_pagamentos,
        'nome_arquivo_contas': nome_arquivo_contas,
        'rgs_com_letras_especificas': {}
    }
    
    if 'pagamentos' in dados and not dados['pagamentos'].empty:
        # CORREÇÃO: Usar dados SEM linha de totais para análise de ausência
        df = dados['pagamentos_sem_totais'] if 'pagamentos_sem_totais' in dados else dados['pagamentos']
        
        # NOVO: Adicionar coluna com número da linha original
        df['Linha_Planilha_Original'] = df.index + 2
        
        # Contar documentos padronizados - APENAS COLUNAS EXISTENTES
        colunas_docs = ['RG', 'CPF']
        for coluna in colunas_docs:
            if coluna in df.columns:
                docs_originais = len(df[df[coluna].notna()])
                analise_ausencia['documentos_padronizados'] += docs_originais
        
        # CORREÇÃO: Contar RGs válidos com QUALQUER letra - APENAS SE A COLUNA EXISTIR
        if 'RG' in df.columns:
            rgs_com_letras = df[df['RG'].astype(str).str.contains(r'[A-Za-z]', na=False)]
            analise_ausencia['registros_validos_com_letras'] = len(rgs_com_letras)
            
            # Detalhar quais letras específicas foram encontradas
            letras_encontradas = {}
            for _, row in rgs_com_letras.iterrows():
                rg_str = str(row['RG'])
                letras = re.findall(r'[A-Za-z]', rg_str)
                for letra in letras:
                    letra_upper = letra.upper()
                    letras_encontradas[letra_upper] = letras_encontradas.get(letra_upper, 0) + 1
            
            analise_ausencia['rgs_com_letras_especificas'] = letras_encontradas
        
        # Contar CPFs que receberam zeros à esquerda - APENAS SE A COLUNA EXISTIR
        if 'CPF' in df.columns:
            cpfs_com_zeros = df[
                df['CPF'].notna() & 
                (df['CPF'].astype(str).str.len() < 11) &
                (df['CPF'].astype(str).str.strip() != '')
            ]
            analise_ausencia['cpfs_com_zeros_adicional'] = len(cpfs_com_zeros)
            
            cpfs_com_formatos = df[
                df['CPF'].notna() & 
                (df['CPF'].astype(str).str.contains(r'[.-]', na=False))
            ]
            analise_ausencia['cpfs_formatos_diferentes'] = len(cpfs_com_formatos)
        
        # CRITÉRIO CORRIGIDO: Apenas dados realmente críticos ausentes
        registros_problematicos = []
        
        # 1. Número da conta ausente - ESTE É CRÍTICO (registro inválido)
        coluna_conta = obter_coluna_conta(df)
        if coluna_conta:
            mask_conta_ausente = (
                df[coluna_conta].isna() | 
                (df[coluna_conta].astype(str).str.strip() == '')
            )
            contas_ausentes = df[mask_conta_ausente]
            for idx in contas_ausentes.index:
                if idx not in registros_problematicos:
                    registros_problematicos.append(idx)
        
        # 2. Valor ausente ou zero - APENAS SE A COLUNA EXISTIR - ESTE É CRÍTICO
        if 'Valor' in df.columns:
            mask_valor_invalido = (
                df['Valor'].isna() | 
                (df['Valor'].astype(str).str.strip() == '') |
                (df['Valor_Limpo'] == 0)
            )
            valores_invalidos = df[mask_valor_invalido]
            for idx in valores_invalidos.index:
                if idx not in registros_problematicos:
                    registros_problematicos.append(idx)
        
        # CORREÇÃO: CPF AUSENTE NÃO É MAIS CONSIDERADO CRÍTICO - APENAS PRECISA DE AJUSTE
        # 3. CPF COMPLETAMENTE AUSENTE - APENAS SE A COLUNA EXISTIR - AGORA É "PRECISA DE AJUSTE"
        if 'CPF' in df.columns:
            mask_cpf_ausente = (
                df['CPF'].isna() | 
                (df['CPF'].astype(str).str.strip() == '')
            )
            cpfs_ausentes = df[mask_cpf_ausente]
            # NÃO adicionamos aos registros problemáticos críticos - apenas marcamos para ajuste
        
        # Atualizar análise
        analise_ausencia['registros_criticos_problematicos'] = registros_problematicos
        analise_ausencia['total_registros_criticos'] = len(registros_problematicos)
        
        if registros_problematicos:
            analise_ausencia['registros_problema_detalhados'] = df.loc[registros_problematicos].copy()
        
        # Analisar ausência por coluna crítica - APENAS COLUNAS EXISTENTES
        colunas_criticas = ['Num Cartao', 'Num_Cartao', 'Valor']  # REMOVIDO CPF DAS COLUNAS CRÍTICAS
        for coluna in colunas_criticas:
            if coluna in df.columns:
                mask_ausente = (
                    df[coluna].isna() | 
                    (df[coluna].astype(str).str.strip() == '')
                )
                ausentes = df[mask_ausente]
                if len(ausentes) > 0:
                    analise_ausencia['colunas_com_ausencia_critica'][coluna] = len(ausentes)
                    analise_ausencia['tipos_problemas'][f'Sem {coluna}'] = len(ausentes)
        
        # Criar resumo de ausências com informações da planilha original - APENAS COLUNAS EXISTENTES
        if registros_problematicos:
            resumo = []
            for idx in registros_problematicos[:100]:
                registro = df.loc[idx]
                info_ausencia = {
                    'Indice_Registro': idx,
                    'Linha_Planilha': registro.get('Linha_Planilha_Original', idx + 2),
                    'Planilha_Origem': nome_arquivo_pagamentos or 'Pagamentos',
                    'Status_Registro': 'INVÁLIDO - Precisa de correção'  # Status claro
                }
                
                # COLUNAS DINÂMICAS BASEADAS NO QUE REALMENTE EXISTE NA PLANILHA
                colunas_interesse = []
                
                # Adicionar apenas colunas que existem na planilha
                colunas_possiveis = [
                    'CPF', 'RG', 'Projeto', 'Valor', 'Beneficiario', 'Beneficiário', 'Nome',
                    'Data', 'Data Pagto', 'Data_Pagto', 'DataPagto',
                    'Num Cartao', 'Num_Cartao', 'Conta', 'Status'
                ]
                
                for col in colunas_possiveis:
                    if col in df.columns:
                        colunas_interesse.append(col)
                
                # Adicionar coluna de conta se existir
                coluna_conta = obter_coluna_conta(df)
                if coluna_conta and coluna_conta not in colunas_interesse:
                    colunas_interesse.append(coluna_conta)
                
                # Adicionar coluna de nome se existir
                coluna_nome = obter_coluna_nome(df)
                if coluna_nome and coluna_nome not in colunas_interesse:
                    colunas_interesse.append(coluna_nome)
                
                for col in colunas_interesse:
                    if pd.notna(registro[col]):
                        valor = str(registro[col])
                        if len(valor) > 50:
                            valor = valor[:47] + "..."
                        info_ausencia[col] = valor
                    else:
                        info_ausencia[col] = ''
                
                # Marcar campos problemáticos - APENAS PARA CAMPOS EXISTENTES
                problemas = []
                if coluna_conta and (pd.isna(registro[coluna_conta]) or str(registro[coluna_conta]).strip() == ''):
                    problemas.append('Número da conta ausente')
                
                if 'Valor' in df.columns and (pd.isna(registro['Valor']) or registro.get('Valor_Limpo', 0) == 0):
                    problemas.append('Valor ausente ou zero')
                
                info_ausencia['Problemas_Identificados'] = ', '.join(problemas) if problemas else 'Dados OK'
                resumo.append(info_ausencia)
            
            analise_ausencia['resumo_ausencias'] = pd.DataFrame(resumo)
    
    return analise_ausencia

# FUNÇÃO CORRIGIDA: Identificar CPFs problemáticos - REGISTROS SÃO VÁLIDOS, APENAS PRECISAM DE CORREÇÃO
def identificar_cpfs_problematicos(df):
    """Identifica CPFs com problemas de formatação - REGISTROS SÃO VÁLIDOS, apenas precisam de correção"""
    problemas_cpf = {
        'cpfs_com_caracteres_invalidos': [],
        'cpfs_com_tamanho_incorreto': [],
        'cpfs_vazios': [],
        'total_problemas_cpf': 0,
        'detalhes_cpfs_problematicos': pd.DataFrame(),
        'registros_afetados': [],  # Lista de registros que precisam de correção
        'status': 'validos_com_problema'  # Indicador que são registros válidos
    }
    
    if 'CPF' not in df.columns or df.empty:
        return problemas_cpf
    
    # Adicionar coluna com número da linha original
    df_analise = df.copy()
    df_analise['Linha_Planilha_Original'] = df_analise.index + 2
    
    # Identificar problemas - MAS MANTENDO OS REGISTROS COMO VÁLIDOS
    for idx, row in df_analise.iterrows():
        cpf = str(row['CPF']) if pd.notna(row['CPF']) and str(row['CPF']).strip() != '' else ''
        problemas = []
        
        # CPF vazio - AINDA É UM REGISTRO VÁLIDO, só precisa ser preenchido
        if cpf == '':
            problemas.append('CPF vazio')
            problemas_cpf['cpfs_vazios'].append(idx)
            problemas_cpf['registros_afetados'].append(idx)
        
        # CPF com caracteres não numéricos - REGISTRO VÁLIDO, precisa de formatação
        elif not cpf.isdigit() and cpf != '':
            problemas.append('Caracteres inválidos')
            problemas_cpf['cpfs_com_caracteres_invalidos'].append(idx)
            problemas_cpf['registros_afetados'].append(idx)
        
        # CPF com tamanho incorreto - REGISTRO VÁLIDO, precisa de correção
        elif len(cpf) != 11 and cpf != '':
            problemas.append(f'Tamanho incorreto ({len(cpf)} dígitos)')
            problemas_cpf['cpfs_com_tamanho_incorreto'].append(idx)
            problemas_cpf['registros_afetados'].append(idx)
        
        # Se há problemas, adicionar aos detalhes - MAS REGISTRO CONTINUA VÁLIDO
        if problemas:
            info_problema = {
                'Linha_Planilha': row.get('Linha_Planilha_Original', idx + 2),
                'CPF_Original': row.get('CPF', ''),
                'CPF_Processado': cpf,
                'Problemas': ', '.join(problemas),
                'Status_Registro': 'VÁLIDO - Precisa de correção'  # Status claro
            }
            
            # Adicionar informações adicionais para identificação - APENAS COLUNAS EXISTENTES
            coluna_conta = obter_coluna_conta(df)
            if coluna_conta and coluna_conta in df.columns and pd.notna(row.get(coluna_conta)):
                info_problema['Numero_Conta'] = row[coluna_conta]
            
            coluna_nome = obter_coluna_nome(df)
            if coluna_nome and coluna_nome in df.columns and pd.notna(row.get(coluna_nome)):
                info_problema['Nome'] = row[coluna_nome]
            
            # Adicionar outras colunas importantes que existam na planilha
            colunas_adicionais = ['Projeto', 'Valor', 'Data', 'Status']
            for coluna in colunas_adicionais:
                if coluna in df.columns and pd.notna(row.get(coluna)):
                    valor = str(row[coluna])
                    if len(valor) > 30:  # Limitar tamanho para exibição
                        valor = valor[:27] + "..."
                    info_problema[coluna] = valor
            
            # Corrigir a concatenação do DataFrame
            if problemas_cpf['detalhes_cpfs_problematicos'].empty:
                problemas_cpf['detalhes_cpfs_problematicos'] = pd.DataFrame([info_problema])
            else:
                problemas_cpf['detalhes_cpfs_problematicos'] = pd.concat([
                    problemas_cpf['detalhes_cpfs_problematicos'],
                    pd.DataFrame([info_problema])
                ], ignore_index=True)
    
    problemas_cpf['total_problemas_cpf'] = len(problemas_cpf['cpfs_com_caracteres_invalidos']) + \
                                         len(problemas_cpf['cpfs_com_tamanho_incorreto']) + \
                                         len(problemas_cpf['cpfs_vazios'])
    
    return problemas_cpf

# CORREÇÃO: Função para processar dados principais - Considera apenas pagamentos válidos SEM TOTAIS
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
        'total_cpfs_duplicados': 0,
        'total_contas_abertas': 0,
        'beneficiarios_contas': 0,
        'duplicidades_detalhadas': {},
        'pagamentos_pendentes': {},
        'total_registros_invalidos': 0,
        'problemas_cpf': {},  # Análise de problemas com CPF
        'linha_totais_removida': False,  # Indicador se linha de totais foi removida
        'total_registros_originais': 0,  # Total original antes de remover totais
        'total_registros_sem_totais': 0,  # Total após remover totais
        'total_cpfs_ajuste': 0  # NOVO: Total de CPFs que precisam de ajuste (não são inválidos)
    }
    
    # Combinar com análise de ausência de dados
    analise_ausencia = analisar_ausencia_dados(dados, nomes_arquivos.get('pagamentos'), nomes_arquivos.get('contas'))
    metrics.update(analise_ausencia)
    
    # CORREÇÃO: Processar planilha de PAGAMENTOS - apenas válidos SEM TOTAIS
    if 'pagamentos' in dados and not dados['pagamentos'].empty:
        df_original = dados['pagamentos']
        metrics['total_registros_originais'] = len(df_original)
        
        # NOVO: Remover linha de totais antes de qualquer processamento
        df_sem_totais = remover_linha_totais(df_original)
        metrics['total_registros_sem_totais'] = len(df_sem_totais)
        
        if len(df_sem_totais) < len(df_original):
            metrics['linha_totais_removida'] = True
        
        # CORREÇÃO: Filtrar apenas pagamentos válidos (com número de conta)
        df = filtrar_pagamentos_validos(df_sem_totais)
        
        # NOVO: Contar registros inválidos (sem número de conta)
        coluna_conta = obter_coluna_conta(df_sem_totais)
        if coluna_conta:
            registros_invalidos = df_sem_totais[
                df_sem_totais[coluna_conta].isna() | 
                (df_sem_totais[coluna_conta].astype(str).str.strip() == '')
            ]
            metrics['total_registros_invalidos'] = len(registros_invalidos)
        
        # Se não há pagamentos válidos após filtrar, retornar métricas vazias
        if df.empty:
            return metrics
        
        # NOVO: Analisar problemas com CPF - AGORA SÃO REGISTROS VÁLIDOS QUE PRECISAM DE AJUSTE
        problemas_cpf = identificar_cpfs_problematicos(df)
        metrics['problemas_cpf'] = problemas_cpf
        metrics['total_cpfs_ajuste'] = problemas_cpf['total_problemas_cpf']
        
        # Beneficiários únicos - APENAS SE A COLUNA EXISTIR
        coluna_beneficiario = obter_coluna_nome(df)
        if coluna_beneficiario and coluna_beneficiario in df.columns:
            metrics['beneficiarios_unicos'] = df[coluna_beneficiario].nunique()
        
        # Total de pagamentos VÁLIDOS (já sem linha de totais)
        metrics['total_pagamentos'] = len(df)
        
        # Contas únicas (da planilha de pagamentos VÁLIDOS)
        coluna_conta = obter_coluna_conta(df)
        if coluna_conta and coluna_conta in df.columns:
            metrics['contas_unicas'] = df[coluna_conta].nunique()
            
            # Detectar duplicidades detalhadas
            duplicidades = detectar_pagamentos_duplicados(df)
            metrics['duplicidades_detalhadas'] = duplicidades
            metrics['pagamentos_duplicados'] = duplicidades['total_contas_duplicadas']
            metrics['valor_total_duplicados'] = duplicidades['valor_total_duplicados']
        
        # Projetos ativos - APENAS SE A COLUNA EXISTIR
        if 'Projeto' in df.columns:
            metrics['projetos_ativos'] = df['Projeto'].nunique()
        
        # Valor total - APENAS SE A COLUNA EXISTIR
        if 'Valor_Limpo' in df.columns:
            metrics['valor_total'] = df['Valor_Limpo'].sum()
        
        # CPFs duplicados - APENAS SE A COLUNA EXISTIR
        if 'CPF' in df.columns:
            cpfs_duplicados = df[df.duplicated(['CPF'], keep=False)]
            metrics['total_cpfs_duplicados'] = cpfs_duplicados['CPF'].nunique()
    
    # CORREÇÃO: Processar planilha de ABERTURA DE CONTAS
    if 'contas' in dados and not dados['contas'].empty:
        df_contas = dados['contas']
        
        # Total de contas abertas
        metrics['total_contas_abertas'] = len(df_contas)
        
        # Beneficiários únicos na planilha de contas - APENAS SE A COLUNA EXISTIR
        coluna_nome = obter_coluna_nome(df_contas)
        if coluna_nome and coluna_nome in df_contas.columns:
            metrics['beneficiarios_contas'] = df_contas[coluna_nome].nunique()
        
        # Se não há planilha de pagamentos, usar contas como referência
        if 'pagamentos' not in dados or dados['pagamentos'].empty:
            metrics['contas_unicas'] = metrics['total_contas_abertas']
            if 'Projeto' in df_contas.columns:
                metrics['projetos_ativos'] = df_contas['Projeto'].nunique()
    
    # Detectar pagamentos pendentes
    pendentes = detectar_pagamentos_pendentes(dados)
    metrics['pagamentos_pendentes'] = pendentes
    
    return metrics

# FUNÇÕES PARA DASHBOARDS E RELATÓRIOS COMPARATIVOS
def criar_dashboard_evolucao(conn, periodo='mensal'):
    """Cria dashboard com evolução temporal dos indicadores"""
    metricas = carregar_metricas_db(conn, 'pagamentos', periodo)
    
    if metricas.empty:
        return None
    
    # Criar gráficos
    fig_evolucao = go.Figure()
    
    # Gráfico de evolução de pagamentos
    fig_evolucao.add_trace(go.Scatter(
        x=metricas['mes_referencia'] + '/' + metricas['ano_referencia'].astype(str),
        y=metricas['total_registros'],
        name='Total Pagamentos',
        line=dict(color='blue', width=3)
    ))
    
    fig_evolucao.add_trace(go.Scatter(
        x=metricas['mes_referencia'] + '/' + metricas['ano_referencia'].astype(str),
        y=metricas['beneficiarios_unicos'],
        name='Beneficiários Únicos',
        line=dict(color='green', width=3)
    ))
    
    fig_evolucao.update_layout(
        title='Evolução Mensal de Pagamentos e Beneficiários',
        xaxis_title='Mês/Ano',
        yaxis_title='Quantidade',
        height=400
    )
    
    # Gráfico de valor total
    fig_valor = go.Figure()
    
    fig_valor.add_trace(go.Bar(
        x=metricas['mes_referencia'] + '/' + metricas['ano_referencia'].astype(str),
        y=metricas['valor_total'],
        name='Valor Total',
        marker_color='orange'
    ))
    
    fig_valor.update_layout(
        title='Evolução do Valor Total Mensal',
        xaxis_title='Mês/Ano',
        yaxis_title='Valor (R$)',
        height=400
    )
    
    # Gráfico de problemas
    fig_problemas = go.Figure()
    
    fig_problemas.add_trace(go.Bar(
        x=metricas['mes_referencia'] + '/' + metricas['ano_referencia'].astype(str),
        y=metricas['registros_problema'],
        name='Registros Críticos',
        marker_color='red'
    ))
    
    fig_problemas.add_trace(go.Bar(
        x=metricas['mes_referencia'] + '/' + metricas['ano_referencia'].astype(str),
        y=metricas['cpfs_ajuste'],
        name='CPFs p/ Ajuste',
        marker_color='yellow'
    ))
    
    fig_problemas.update_layout(
        title='Evolução de Problemas Identificados',
        xaxis_title='Mês/Ano',
        yaxis_title='Quantidade',
        height=400,
        barmode='group'
    )
    
    return {
        'evolucao': fig_evolucao,
        'valor': fig_valor,
        'problemas': fig_problemas,
        'dados': metricas
    }

def gerar_relatorio_comparativo(conn, periodo):
    """Gera relatório comparativo entre períodos"""
    metricas = carregar_metricas_db(conn, 'pagamentos', periodo)
    
    if metricas.empty:
        return None
    
    # Calcular variações
    if len(metricas) > 1:
        ultimo = metricas.iloc[0]
        anterior = metricas.iloc[1]
        
        variacoes = {
            'total_pagamentos': ((ultimo['total_registros'] - anterior['total_registros']) / anterior['total_registros']) * 100,
            'beneficiarios': ((ultimo['beneficiarios_unicos'] - anterior['beneficiarios_unicos']) / anterior['beneficiarios_unicos']) * 100,
            'valor_total': ((ultimo['valor_total'] - anterior['valor_total']) / anterior['valor_total']) * 100,
            'duplicidades': ((ultimo['pagamentos_duplicados'] - anterior['pagamentos_duplicados']) / anterior['pagamentos_duplicados']) * 100 if anterior['pagamentos_duplicados'] > 0 else 0,
            'cpfs_ajuste': ((ultimo['cpfs_ajuste'] - anterior['cpfs_ajuste']) / anterior['cpfs_ajuste']) * 100 if anterior['cpfs_ajuste'] > 0 else 0
        }
    else:
        variacoes = {}
    
    return {
        'metricas': metricas,
        'variacoes': variacoes,
        'periodo': periodo
    }

# FUNÇÃO RESTAURADA: Gerar PDF Executivo
def gerar_pdf_executivo(metrics, dados, nomes_arquivos, tipo_relatorio='pagamentos'):
    """Gera relatório executivo em PDF"""
    pdf = FPDF()
    pdf.add_page()
    
    # Configurar fonte
    pdf.set_font("Arial", 'B', 16)
    
    # Cabeçalho
    pdf.cell(0, 10, "Prefeitura de São Paulo", 0, 1, 'C')
    pdf.cell(0, 10, "Secretaria Municipal do Desenvolvimento Econômico e Trabalho - SMDET", 0, 1, 'C')
    
    if tipo_relatorio == 'pagamentos':
        pdf.cell(0, 10, "Relatório Executivo - Sistema POT (Pagamentos)", 0, 1, 'C')
    else:
        pdf.cell(0, 10, "Relatório Executivo - Sistema POT (Inscrições)", 0, 1, 'C')
    
    pdf.ln(10)
    
    # Data da análise
    pdf.set_font("Arial", '', 12)
    pdf.cell(0, 10, f"Data da análise: {data_hora_atual_brasilia()}", 0, 1)
    pdf.ln(5)
    
    # Informações das planilhas
    if nomes_arquivos.get('pagamentos'):
        pdf.cell(0, 10, f"Planilha de Pagamentos: {nomes_arquivos['pagamentos']}", 0, 1)
    if nomes_arquivos.get('contas'):
        pdf.cell(0, 10, f"Planilha de Inscrições: {nomes_arquivos['contas']}", 0, 1)
    pdf.ln(10)
    
    # Métricas principais
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "Métricas Principais", 0, 1)
    pdf.set_font("Arial", '', 12)
    
    if tipo_relatorio == 'pagamentos':
        metricas = [
            ("Total de Pagamentos", formatar_brasileiro(metrics['total_pagamentos'])),
            ("Beneficiários Únicos", formatar_brasileiro(metrics['beneficiarios_unicos'])),
            ("Contas Únicas", formatar_brasileiro(metrics['contas_unicas'])),
            ("Valor Total", formatar_brasileiro(metrics['valor_total'], 'monetario')),
            ("Pagamentos Duplicados", formatar_brasileiro(metrics['pagamentos_duplicados'])),
            ("Valor em Duplicidades", formatar_brasileiro(metrics['valor_total_duplicados'], 'monetario')),
            ("Projetos Ativos", formatar_brasileiro(metrics['projetos_ativos'])),
            ("CPFs p/ Ajuste", formatar_brasileiro(metrics['total_cpfs_ajuste'])),
            ("Registros Críticos", formatar_brasileiro(metrics['total_registros_criticos']))
        ]
    else:
        metricas = [
            ("Total de Inscrições", formatar_brasileiro(metrics['total_contas_abertas'])),
            ("Beneficiários Únicos", formatar_brasileiro(metrics['beneficiarios_contas'])),
            ("Projetos Ativos", formatar_brasileiro(metrics['projetos_ativos']))
        ]
    
    for nome, valor in metricas:
        pdf.cell(100, 10, nome, 0, 0)
        pdf.cell(0, 10, str(valor), 0, 1)
    
    pdf.ln(10)
    
    # Alertas e problemas
    if tipo_relatorio == 'pagamentos':
        if metrics['pagamentos_duplicados'] > 0:
            pdf.set_font("Arial", 'B', 12)
            pdf.set_text_color(255, 0, 0)
            pdf.cell(0, 10, f"ALERTA: {metrics['pagamentos_duplicados']} contas com pagamentos duplicados", 0, 1)
            pdf.set_text_color(0, 0, 0)
        
        if metrics['total_registros_criticos'] > 0:
            pdf.set_font("Arial", 'B', 12)
            pdf.set_text_color(255, 165, 0)
            pdf.cell(0, 10, f"ATENÇÃO: {metrics['total_registros_criticos']} registros com problemas críticos", 0, 1)
            pdf.set_text_color(0, 0, 0)
        
        if metrics['total_cpfs_ajuste'] > 0:
            pdf.set_font("Arial", 'B', 12)
            pdf.set_text_color(0, 100, 0)
            pdf.cell(0, 10, f"INFO: {metrics['total_cpfs_ajuste']} CPFs precisam de ajuste (registros válidos)", 0, 1)
            pdf.set_text_color(0, 0, 0)
    
    return pdf.output(dest='S').encode('latin1')

# FUNÇÃO RESTAURADA: Gerar Excel Completo
def gerar_excel_completo(metrics, dados, tipo_relatorio='pagamentos'):
    """Gera planilha Excel com todas as análises"""
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Resumo Executivo
        if tipo_relatorio == 'pagamentos':
            resumo_data = {
                'Métrica': [
                    'Data da Análise',
                    'Total de Pagamentos Válidos',
                    'Beneficiários Únicos',
                    'Contas Únicas', 
                    'Valor Total',
                    'Pagamentos Duplicados',
                    'Valor em Duplicidades',
                    'Projetos Ativos',
                    'CPFs para Ajuste',
                    'Registros Críticos'
                ],
                'Valor': [
                    data_hora_atual_brasilia(),
                    metrics['total_pagamentos'],
                    metrics['beneficiarios_unicos'],
                    metrics['contas_unicas'],
                    metrics['valor_total'],
                    metrics['pagamentos_duplicados'],
                    metrics['valor_total_duplicados'],
                    metrics['projetos_ativos'],
                    metrics['total_cpfs_ajuste'],
                    metrics['total_registros_criticos']
                ]
            }
        else:
            resumo_data = {
                'Métrica': [
                    'Data da Análise',
                    'Total de Inscrições',
                    'Beneficiários Únicos',
                    'Projetos Ativos',
                    'Registros com Problemas'
                ],
                'Valor': [
                    data_hora_atual_brasilia(),
                    metrics['total_contas_abertas'],
                    metrics['beneficiarios_contas'],
                    metrics['projetos_ativos'],
                    metrics['total_registros_criticos']
                ]
            }
        
        pd.DataFrame(resumo_data).to_excel(writer, sheet_name='Resumo Executivo', index=False)
        
        if tipo_relatorio == 'pagamentos':
            # Duplicidades detalhadas
            if not metrics['duplicidades_detalhadas']['resumo_duplicidades'].empty:
                metrics['duplicidades_detalhadas']['resumo_duplicidades'].to_excel(
                    writer, sheet_name='Duplicidades', index=False
                )
            
            # Pagamentos pendentes
            if not metrics['pagamentos_pendentes']['contas_sem_pagamento'].empty:
                metrics['pagamentos_pendentes']['contas_sem_pagamento'].to_excel(
                    writer, sheet_name='Pagamentos Pendentes', index=False
                )
        
        # Problemas de dados CRÍTICOS
        if not metrics['resumo_ausencias'].empty:
            metrics['resumo_ausencias'].to_excel(
                writer, sheet_name='Problemas Críticos', index=False
            )
        
        # CPFs para ajuste (NÃO SÃO CRÍTICOS)
        if not metrics['problemas_cpf']['detalhes_cpfs_problematicos'].empty:
            metrics['problemas_cpf']['detalhes_cpfs_problematicos'].to_excel(
                writer, sheet_name='CPFs para Ajuste', index=False
            )
    
    return output.getvalue()

# FUNÇÃO RESTAURADA: Gerar Planilha de Ajustes
def gerar_planilha_ajustes(metrics, tipo_relatorio='pagamentos'):
    """Gera planilha com ações recomendadas"""
    output = io.BytesIO()
    
    acoes = []
    
    if tipo_relatorio == 'pagamentos':
        # Ações para duplicidades
        if metrics['pagamentos_duplicados'] > 0:
            acoes.append({
                'Tipo': 'Duplicidade',
                'Descrição': f'Verificar {metrics["pagamentos_duplicados"]} contas com pagamentos duplicados',
                'Ação Recomendada': 'Auditar pagamentos e ajustar contas duplicadas',
                'Prioridade': 'Alta',
                'Impacto Financeiro': formatar_brasileiro(metrics['valor_total_duplicados'], 'monetario')
            })
        
        # Ações para pagamentos pendentes
        if metrics['pagamentos_pendentes']['total_contas_sem_pagamento'] > 0:
            acoes.append({
                'Tipo': 'Pagamento Pendente',
                'Descrição': f'{metrics["pagamentos_pendentes"]["total_contas_sem_pagamento"]} contas aguardando pagamento',
                'Ação Recomendada': 'Regularizar pagamentos pendentes',
                'Prioridade': 'Média',
                'Impacto Financeiro': 'A definir'
            })
    
    # Ações para problemas CRÍTICOS de dados
    if metrics['total_registros_criticos'] > 0:
        acoes.append({
            'Tipo': 'Dados Críticos Incompletos',
            'Descrição': f'{metrics["total_registros_criticos"]} registros com problemas críticos (sem conta ou valor)',
            'Ação Recomendada': 'Completar informações faltantes essenciais',
            'Prioridade': 'Alta',
            'Impacto Financeiro': 'Risco operacional'
        })
    
    # Ações para CPFs problemáticos - PRIORIDADE MÉDIA (não são críticos)
    if metrics['total_cpfs_ajuste'] > 0:
        acoes.append({
            'Tipo': 'CPF para Ajuste',
            'Descrição': f'{metrics["total_cpfs_ajuste"]} CPFs precisam de correção (registros válidos)',
            'Ação Recomendada': 'Corrigir formatação dos CPFs',
            'Prioridade': 'Média',
            'Impacto Financeiro': 'Risco fiscal/documental'
        })
    
    df_acoes = pd.DataFrame(acoes)
    df_acoes.to_excel(output, index=False)
    
    return output.getvalue()

# Sistema de upload de dados MELHORADO: capturar nomes dos arquivos
def carregar_dados(conn):
    st.sidebar.header("📤 Carregar Dados Mensais")
    
    # Seleção de mês e ano de referência
    col1, col2 = st.sidebar.columns(2)
    with col1:
        mes_ref = st.selectbox("Mês de Referência", 
                             ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                              'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'])
    with col2:
        ano_atual = datetime.now().year
        ano_ref = st.selectbox("Ano de Referência", 
                             [ano_atual, ano_atual-1, ano_atual-2])
    
    st.sidebar.markdown("---")
    
    upload_pagamentos = st.sidebar.file_uploader(
        "Planilha de Pagamentos", 
        type=['xlsx', 'csv'],
        key="pagamentos",
        help="Arraste e solte o arquivo aqui ou clique para procurar"
    )
    
    upload_contas = st.sidebar.file_uploader(
        "Planilha de Inscrições/Contas", 
        type=['xlsx', 'csv'],
        key="contas",
        help="Arraste e solte o arquivo aqui ou clique para procurar"
    )
    
    dados = {}
    nomes_arquivos = {}
    
    # Carregar dados de pagamentos
    if upload_pagamentos is not None:
        try:
            if upload_pagamentos.name.endswith('.xlsx'):
                df_pagamentos = pd.read_excel(upload_pagamentos)
            else:
                df_pagamentos = pd.read_csv(upload_pagamentos, encoding='utf-8', sep=';')
            
            nomes_arquivos['pagamentos'] = upload_pagamentos.name
            
            # Mostrar colunas disponíveis para debug
            st.sidebar.info(f"📊 Colunas na planilha: {', '.join(df_pagamentos.columns.tolist()[:5])}{'...' if len(df_pagamentos.columns) > 5 else ''}")
            
            # Guardar versão original e versão sem totais
            dados['pagamentos_original'] = df_pagamentos.copy()
            
            # Remover linha de totais antes do processamento - SEMPRE REMOVE
            df_pagamentos_sem_totais = remover_linha_totais(df_pagamentos)
            dados['pagamentos'] = df_pagamentos_sem_totais
            
            df_pagamentos_sem_totais = processar_colunas_data(df_pagamentos_sem_totais)
            df_pagamentos_sem_totais = processar_colunas_valor(df_pagamentos_sem_totais)
            df_pagamentos_sem_totais = padronizar_documentos(df_pagamentos_sem_totais)
            
            dados['pagamentos'] = df_pagamentos_sem_totais
            
            # Salvar no banco de dados
            metadados = {
                'total_registros_originais': len(df_pagamentos),
                'total_registros_sem_totais': len(df_pagamentos_sem_totais),
                'colunas_disponiveis': df_pagamentos.columns.tolist()
            }
            
            salvar_pagamentos_db(conn, mes_ref, ano_ref, upload_pagamentos.name, df_pagamentos_sem_totais, metadados)
            
            # Mostrar estatísticas de pagamentos válidos vs inválidos (JÁ SEM TOTAIS)
            df_pagamentos_validos = filtrar_pagamentos_validos(df_pagamentos_sem_totais)
            total_validos = len(df_pagamentos_validos)
            total_invalidos = len(df_pagamentos_sem_totais) - total_validos
            
            st.sidebar.success(f"✅ Pagamentos: {total_validos} válidos + {total_invalidos} sem conta - {upload_pagamentos.name}")
            
        except Exception as e:
            st.sidebar.error(f"❌ Erro ao carregar pagamentos: {str(e)}")
    
    # Carregar dados de abertura de contas
    if upload_contas is not None:
        try:
            if upload_contas.name.endswith('.xlsx'):
                df_contas = pd.read_excel(upload_contas)
            else:
                df_contas = pd.read_csv(upload_contas, encoding='utf-8', sep=';')
            
            nomes_arquivos['contas'] = upload_contas.name
            
            df_contas = processar_colunas_data(df_contas)
            df_contas = padronizar_documentos(df_contas)
            
            dados['contas'] = df_contas
            
            # Salvar no banco de dados
            metadados = {
                'total_registros': len(df_contas),
                'colunas_disponiveis': df_contas.columns.tolist()
            }
            
            salvar_inscricoes_db(conn, mes_ref, ano_ref, upload_contas.name, df_contas, metadados)
            
            st.sidebar.success(f"✅ Inscrições: {len(dados['contas'])} registros - {upload_contas.name}")
        except Exception as e:
            st.sidebar.error(f"❌ Erro ao carregar inscrições: {str(e)}")
    
    return dados, nomes_arquivos, mes_ref, ano_ref

# Interface principal do sistema CORRIGIDA
def main():
    # Inicializar banco de dados
    conn = init_database()
    
    # Autenticação - AGORA É OBRIGATÓRIA
    email_autorizado = autenticar()
    
    # Se não está autenticado, não mostra o conteúdo principal
    if not email_autorizado:
        # Mostrar apenas informações básicas sem dados
        st.title("🏛️ Sistema POT - SMDET")
        st.markdown("### Análise de Pagamentos e Contas")
        st.info("🔐 **Acesso Restrito** - Faça login para acessar o sistema")
        st.markdown("---")
        st.write("Este sistema é restrito aos servidores autorizados da Prefeitura de São Paulo.")
        st.write("**Credenciais necessárias:**")
        st.write("- Email institucional @prefeitura.sp.gov.br")
        st.write("- Senha de acesso autorizada")
        return
    
    # A partir daqui, só usuários autenticados têm acesso
    
    st.sidebar.markdown("---")
    
    # Carregar dados
    dados, nomes_arquivos, mes_ref, ano_ref = carregar_dados(conn)
    
    # Verificar se há dados para processar
    tem_dados_pagamentos = 'pagamentos' in dados and not dados['pagamentos'].empty
    tem_dados_contas = 'contas' in dados and not dados['contas'].empty
    
    # Abas principais do sistema
    tab_principal, tab_dashboard, tab_relatorios, tab_historico = st.tabs([
        "📊 Análise Mensal", 
        "📈 Dashboard Evolutivo", 
        "📋 Relatórios Comparativos", 
        "🗃️ Dados Históricos"
    ])
    
    with tab_principal:
        if not tem_dados_pagamentos and not tem_dados_contas:
            st.info("📊 Faça o upload das planilhas de pagamentos e/ou inscrições para iniciar a análise")
            
            # Mostrar exemplo de interface mesmo sem dados
            st.title("🏛️ Sistema POT - SMDET")
            st.markdown("### Análise de Pagamentos e Inscrições")
            st.markdown(f"**Mês de referência:** {mes_ref}/{ano_ref}")
            st.markdown("---")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Total de Pagamentos", "0")
            with col2:
                st.metric("Beneficiários Únicos", "0")
            with col3:
                st.metric("Valor Total", "R$ 0,00")
            
        else:
            # Processar dados
            with st.spinner("🔄 Processando dados..."):
                metrics = processar_dados(dados, nomes_arquivos)
                
                # Salvar métricas no banco de dados
                if tem_dados_pagamentos:
                    salvar_metricas_db(conn, 'pagamentos', mes_ref, ano_ref, metrics)
                if tem_dados_contas:
                    salvar_metricas_db(conn, 'inscricoes', mes_ref, ano_ref, metrics)
            
            # Interface principal
            st.title("🏛️ Sistema POT - SMDET")
            st.markdown("### Análise de Pagamentos e Inscrições")
            st.markdown(f"**Mês de referência:** {mes_ref}/{ano_ref}")
            st.markdown(f"**Data da análise:** {data_hora_atual_brasilia()}")
            
            # Informação sobre linha de totais removida
            if metrics.get('linha_totais_removida', False):
                st.info(f"📝 **Nota:** Linha de totais da planilha foi identificada e excluída da análise ({metrics['total_registros_originais']} → {metrics['total_registros_sem_totais']} registros)")
            
            # SEÇÃO RESTAURADA: Download de Relatórios
            st.sidebar.markdown("---")
            st.sidebar.header("📥 Exportar Relatórios")
            
            col1, col2, col3 = st.sidebar.columns(3)
            
            with col1:
                if tem_dados_pagamentos:
                    pdf_bytes = gerar_pdf_executivo(metrics, dados, nomes_arquivos, 'pagamentos')
                else:
                    pdf_bytes = gerar_pdf_executivo(metrics, dados, nomes_arquivos, 'inscricoes')
                
                st.download_button(
                    label="📄 PDF",
                    data=pdf_bytes,
                    file_name=f"relatorio_executivo_pot_{mes_ref}_{ano_ref}_{data_hora_arquivo_brasilia()}.pdf",
                    mime="application/pdf"
                )
            
            with col2:
                if tem_dados_pagamentos:
                    excel_bytes = gerar_excel_completo(metrics, dados, 'pagamentos')
                else:
                    excel_bytes = gerar_excel_completo(metrics, dados, 'inscricoes')
                
                st.download_button(
                    label="📊 Excel",
                    data=excel_bytes,
                    file_name=f"analise_completa_pot_{mes_ref}_{ano_ref}_{data_hora_arquivo_brasilia()}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            
            with col3:
                if tem_dados_pagamentos:
                    ajustes_bytes = gerar_planilha_ajustes(metrics, 'pagamentos')
                else:
                    ajustes_bytes = gerar_planilha_ajustes(metrics, 'inscricoes')
                
                st.download_button(
                    label="🔧 Ajustes",
                    data=ajustes_bytes,
                    file_name=f"plano_ajustes_pot_{mes_ref}_{ano_ref}_{data_hora_arquivo_brasilia()}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            
            st.markdown("---")
            
            # Métricas principais
            if tem_dados_pagamentos:
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric(
                        "Total de Pagamentos", 
                        formatar_brasileiro(metrics['total_pagamentos']),
                        help="Pagamentos válidos com número de conta (já excluindo linha de totais)"
                    )
                
                with col2:
                    st.metric(
                        "Beneficiários Únicos", 
                        formatar_brasileiro(metrics['beneficiarios_unicos'])
                    )
                
                with col3:
                    st.metric(
                        "Contas Únicas", 
                        formatar_brasileiro(metrics['contas_unicas'])
                    )
                
                with col4:
                    st.metric(
                        "Valor Total", 
                        formatar_brasileiro(metrics['valor_total'], 'monetario')
                    )
                
                # Segunda linha de métricas
                col5, col6, col7, col8 = st.columns(4)
                
                with col5:
                    st.metric(
                        "Pagamentos Duplicados", 
                        formatar_brasileiro(metrics['pagamentos_duplicados']),
                        delta=f"-{formatar_brasileiro(metrics['valor_total_duplicados'], 'monetario')}",
                        delta_color="inverse",
                        help="Contas com múltiplos pagamentos"
                    )
                
                with col6:
                    st.metric(
                        "Projetos Ativos", 
                        formatar_brasileiro(metrics['projetos_ativos'])
                    )
                
                with col7:
                    st.metric(
                        "CPFs p/ Ajuste", 
                        formatar_brasileiro(metrics['total_cpfs_ajuste']),
                        help="Registros VÁLIDOS que precisam de correção no CPF"
                    )
                
                with col8:
                    st.metric(
                        "Registros Críticos", 
                        formatar_brasileiro(metrics['total_registros_criticos']),
                        delta_color="inverse" if metrics['total_registros_criticos'] > 0 else "off",
                        help="Registros INVÁLIDOS (sem conta ou valor)"
                    )
            
            if tem_dados_contas:
                st.markdown("---")
                st.subheader("📋 Dados de Inscrições/Contas")
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric(
                        "Total de Inscrições", 
                        formatar_brasileiro(metrics['total_contas_abertas'])
                    )
                
                with col2:
                    st.metric(
                        "Beneficiários Únicos", 
                        formatar_brasileiro(metrics['beneficiarios_contas'])
                    )
                
                with col3:
                    st.metric(
                        "Projetos Ativos", 
                        formatar_brasileiro(metrics['projetos_ativos'])
                    )
            
            st.markdown("---")
            
            # Abas para análises detalhadas
            tab1, tab2, tab3, tab4, tab5 = st.tabs([
                "📋 Visão Geral", 
                "⚠️ Duplicidades", 
                "⏳ Pagamentos Pendentes", 
                "🔴 Problemas Críticos",
                "📝 CPFs p/ Ajuste"
            ])
            
            with tab1:
                st.subheader("Resumo dos Dados")
                
                if tem_dados_pagamentos:
                    st.write(f"**Planilha de Pagamentos:** {nomes_arquivos.get('pagamentos', 'N/A')}")
                    
                    # Mostrar apenas total SEM linha de totais
                    st.write(f"**Total de registros válidos:** {metrics['total_registros_sem_totais']}")
                    
                    # Mostrar informação sobre remoção de totais se aplicável
                    if metrics.get('linha_totais_removida', False):
                        st.write(f"🔍 **Observação:** Linha de totais removida (originalmente {metrics['total_registros_originais']} registros)")
                    
                    st.write(f"**Pagamentos válidos:** {metrics['total_pagamentos']}")
                    st.write(f"**Registros sem conta:** {metrics['total_registros_invalidos']}")
                    
                    # Mostrar colunas disponíveis na planilha
                    if 'pagamentos' in dados:
                        colunas_disponiveis = dados['pagamentos'].columns.tolist()
                        st.write(f"**Colunas disponíveis:** {', '.join(colunas_disponiveis[:8])}{'...' if len(colunas_disponiveis) > 8 else ''}")
                
                if tem_dados_contas:
                    st.write(f"**Planilha de Inscrições:** {nomes_arquivos.get('contas', 'N/A')}")
                    st.write(f"**Total de inscrições:** {metrics['total_contas_abertas']}")
                    st.write(f"**Beneficiários únicos:** {metrics['beneficiarios_contas']}")
            
            with tab2:
                if tem_dados_pagamentos:
                    st.subheader("Pagamentos Duplicados")
                    
                    if metrics['duplicidades_detalhadas']['total_contas_duplicadas'] > 0:
                        st.warning(f"🚨 Foram encontradas {metrics['duplicidades_detalhadas']['total_contas_duplicadas']} contas com pagamentos duplicados")
                        
                        # Mostrar resumo das duplicidades
                        if not metrics['duplicidades_detalhadas']['resumo_duplicidades'].empty:
                            st.write("**Resumo das Duplicidades:**")
                            st.dataframe(metrics['duplicidades_detalhadas']['resumo_duplicidades'])
                        
                        # Mostrar detalhes completos
                        if not metrics['duplicidades_detalhadas']['detalhes_completos_duplicidades'].empty:
                            st.write("**Detalhes Completos dos Pagamentos Duplicados:**")
                            st.dataframe(metrics['duplicidades_detalhadas']['detalhes_completos_duplicidades'])
                    else:
                        st.success("✅ Nenhum pagamento duplicado encontrado")
                else:
                    st.info("ℹ️ Esta análise está disponível apenas para dados de pagamentos")
            
            with tab3:
                if tem_dados_pagamentos and tem_dados_contas:
                    st.subheader("Pagamentos Pendentes")
                    
                    if metrics['pagamentos_pendentes']['total_contas_sem_pagamento'] > 0:
                        st.info(f"ℹ️ {metrics['pagamentos_pendentes']['total_contas_sem_pagamento']} contas aguardando pagamento")
                        
                        if not metrics['pagamentos_pendentes']['contas_sem_pagamento'].empty:
                            st.write("**Contas sem Pagamento:**")
                            st.dataframe(metrics['pagamentos_pendentes']['contas_sem_pagamento'])
                    else:
                        st.success("✅ Todas as contas abertas possuem pagamentos registrados")
                else:
                    st.info("ℹ️ Esta análise requer ambas as planilhas (pagamentos e inscrições)")
            
            with tab4:
                st.subheader("Problemas Críticos")
                
                if metrics['total_registros_criticos'] > 0:
                    st.error(f"❌ {metrics['total_registros_criticos']} registros com problemas críticos (INVÁLIDOS)")
                    
                    if not metrics['resumo_ausencias'].empty:
                        st.write("**Registros com Problemas Críticos:**")
                        st.dataframe(metrics['resumo_ausencias'])
                else:
                    st.success("✅ Nenhum registro com problemas críticos encontrado")
            
            with tab5:
                st.subheader("CPFs para Ajuste")
                
                if metrics['total_cpfs_ajuste'] > 0:
                    st.warning(f"⚠️ {metrics['total_cpfs_ajuste']} CPFs precisam de ajuste (registros VÁLIDOS)")
                    
                    if not metrics['problemas_cpf']['detalhes_cpfs_problematicos'].empty:
                        st.write("**Detalhes dos CPFs para Ajuste:**")
                        st.dataframe(metrics['problemas_cpf']['detalhes_cpfs_problematicos'])
                else:
                    st.success("✅ Todos os CPFs estão corretamente formatados")
    
    with tab_dashboard:
        st.header("📈 Dashboard Evolutivo")
        
        periodo = st.selectbox("Selecione o período", 
                             ['mensal', 'trimestral', 'semestral', 'anual'],
                             key='dashboard_periodo')
        
        dashboard = criar_dashboard_evolucao(conn, periodo)
        
        if dashboard:
            st.plotly_chart(dashboard['evolucao'], use_container_width=True)
            st.plotly_chart(dashboard['valor'], use_container_width=True)
            st.plotly_chart(dashboard['problemas'], use_container_width=True)
            
            # Mostrar tabela com dados
            st.subheader("Dados Detalhados")
            st.dataframe(dashboard['dados'])
        else:
            st.info("ℹ️ Não há dados suficientes para gerar o dashboard. Carregue dados de pelo menos 2 meses diferentes.")
    
    with tab_relatorios:
        st.header("📋 Relatórios Comparativos")
        
        periodo_comparativo = st.selectbox("Selecione o período comparativo", 
                                         ['trimestral', 'semestral', 'anual'],
                                         key='relatorio_periodo')
        
        relatorio = gerar_relatorio_comparativo(conn, periodo_comparativo)
        
        if relatorio:
            st.subheader(f"Relatório Comparativo - {periodo_comparativo.title()}")
            
            # Métricas comparativas
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                if 'variacoes' in relatorio and 'total_pagamentos' in relatorio['variacoes']:
                    variacao = relatorio['variacoes']['total_pagamentos']
                    st.metric(
                        "Variação Pagamentos",
                        f"{variacao:+.1f}%",
                        delta=f"{variacao:+.1f}%"
                    )
            
            with col2:
                if 'variacoes' in relatorio and 'beneficiarios' in relatorio['variacoes']:
                    variacao = relatorio['variacoes']['beneficiarios']
                    st.metric(
                        "Variação Beneficiários",
                        f"{variacao:+.1f}%",
                        delta=f"{variacao:+.1f}%"
                    )
            
            with col3:
                if 'variacoes' in relatorio and 'valor_total' in relatorio['variacoes']:
                    variacao = relatorio['variacoes']['valor_total']
                    st.metric(
                        "Variação Valor Total",
                        f"{variacao:+.1f}%",
                        delta=f"{variacao:+.1f}%"
                    )
            
            with col4:
                if 'variacoes' in relatorio and 'cpfs_ajuste' in relatorio['variacoes']:
                    variacao = relatorio['variacoes']['cpfs_ajuste']
                    st.metric(
                        "Variação CPFs p/ Ajuste",
                        f"{variacao:+.1f}%",
                        delta=f"{variacao:+.1f}%",
                        delta_color="inverse" if variacao > 0 else "normal"
                    )
            
            # Tabela comparativa
            st.subheader("Dados Comparativos")
            st.dataframe(relatorio['metricas'])
            
            # Download do relatório comparativo
            st.download_button(
                label="📥 Baixar Relatório Comparativo",
                data=relatorio['metricas'].to_csv(index=False).encode('utf-8'),
                file_name=f"relatorio_comparativo_{periodo_comparativo}_{data_hora_arquivo_brasilia()}.csv",
                mime="text/csv"
            )
        else:
            st.info("ℹ️ Não há dados suficientes para gerar relatório comparativo. Carregue dados de períodos diferentes.")
    
    with tab_historico:
        st.header("🗃️ Dados Históricos")
        
        # Seleção de tipo de dados
        tipo_dados = st.radio("Selecione o tipo de dados", 
                            ['Pagamentos', 'Inscrições'], 
                            horizontal=True)
        
        if tipo_dados == 'Pagamentos':
            dados_historicos = carregar_pagamentos_db(conn)
        else:
            dados_historicos = carregar_inscricoes_db(conn)
        
        if not dados_historicos.empty:
            st.subheader(f"Histórico de {tipo_dados}")
            
            # Mostrar dados históricos
            for _, row in dados_historicos.iterrows():
                with st.expander(f"{row['mes_referencia']}/{row['ano_referencia']} - {row['nome_arquivo']}"):
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.write(f"**Data de importação:** {row['data_importacao']}")
                    
                    with col2:
                        st.write(f"**Mês/Ano:** {row['mes_referencia']}/{row['ano_referencia']}")
                    
                    with col3:
                        # Botão para visualizar dados
                        if st.button("📊 Visualizar Dados", key=f"view_{row['id']}"):
                            # Carregar dados do JSON
                            dados_json = json.loads(row['dados_json'])
                            df_visualizacao = pd.DataFrame(dados_json)
                            
                            st.dataframe(df_visualizacao.head(10))
                            
                            # Botão para baixar dados específicos
                            csv = df_visualizacao.to_csv(index=False)
                            st.download_button(
                                label="📥 Baixar Dados",
                                data=csv,
                                file_name=f"{tipo_dados.lower()}_{row['mes_referencia']}_{row['ano_referencia']}.csv",
                                mime="text/csv"
                            )
        else:
            st.info(f"ℹ️ Não há dados históricos de {tipo_dados.lower()} no sistema.")

    # Fechar conexão com o banco de dados
    conn.close()

if __name__ == "__main__":
    main()
