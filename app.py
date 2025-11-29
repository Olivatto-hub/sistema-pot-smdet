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
    layout="wide",
    initial_sidebar_state="expanded"
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
            metadados_json TEXT NOT NULL,
            hash_arquivo TEXT UNIQUE
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
            metadados_json TEXT NOT NULL,
            hash_arquivo TEXT UNIQUE
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
            data_calculo TEXT NOT NULL,
            UNIQUE(tipo, mes_referencia, ano_referencia)
        )
    ''')
    
    conn.commit()
    return conn

# Função para hash de arquivo
def hash_arquivo(file_content):
    """Gera hash MD5 do conteúdo do arquivo"""
    return hashlib.md5(file_content).hexdigest()

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
    st.sidebar.title("🔐 Sistema POT - SMDET")
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
        if st.sidebar.button("🚪 Sair", use_container_width=True):
            st.session_state.autenticado = False
            st.session_state.email_autorizado = None
            st.rerun()
        return st.session_state.email_autorizado
    
    # Formulário de login
    with st.sidebar.form("login_form"):
        st.subheader("Acesso Restrito")
        email = st.text_input("Email institucional", placeholder="seu.email@prefeitura.sp.gov.br")
        senha = st.text_input("Senha", type="password", placeholder="Digite sua senha")
        submit = st.form_submit_button("Entrar", use_container_width=True)
        
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
def verificar_arquivo_existente(conn, tabela, hash_arquivo):
    """Verifica se um arquivo já foi importado anteriormente"""
    cursor = conn.cursor()
    cursor.execute(f'SELECT COUNT(*) FROM {tabela} WHERE hash_arquivo = ?', (hash_arquivo,))
    return cursor.fetchone()[0] > 0

def salvar_pagamentos_db(conn, mes_ref, ano_ref, nome_arquivo, dados_df, metadados, file_hash):
    """Salva dados de pagamentos no banco de dados"""
    dados_json = dados_df.to_json(orient='records', date_format='iso')
    metadados_json = json.dumps(metadados)
    
    conn.execute('''
        INSERT OR REPLACE INTO pagamentos (mes_referencia, ano_referencia, data_importacao, nome_arquivo, dados_json, metadados_json, hash_arquivo)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (mes_ref, ano_ref, data_hora_atual_brasilia(), nome_arquivo, dados_json, metadados_json, file_hash))
    
    conn.commit()

def salvar_inscricoes_db(conn, mes_ref, ano_ref, nome_arquivo, dados_df, metadados, file_hash):
    """Salva dados de inscrições no banco de dados"""
    dados_json = dados_df.to_json(orient='records', date_format='iso')
    metadados_json = json.dumps(metadados)
    
    conn.execute('''
        INSERT OR REPLACE INTO inscricoes (mes_referencia, ano_referencia, data_importacao, nome_arquivo, dados_json, metadados_json, hash_arquivo)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (mes_ref, ano_ref, data_hora_atual_brasilia(), nome_arquivo, dados_json, metadados_json, file_hash))
    
    conn.commit()

def salvar_metricas_db(conn, tipo, mes_ref, ano_ref, metrics):
    """Salva métricas no banco de dados para relatórios comparativos"""
    conn.execute('''
        INSERT OR REPLACE INTO metricas_mensais 
        (tipo, mes_referencia, ano_referencia, total_registros, 
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
        # Últimos 3 meses completos (excluindo o mês atual)
        query += " ORDER BY ano_referencia DESC, mes_referencia DESC LIMIT 3"
    elif periodo == 'semestral':
        # Últimos 6 meses completos
        query += " ORDER BY ano_referencia DESC, mes_referencia DESC LIMIT 6"
    elif periodo == 'anual':
        # Últimos 12 meses completos
        query += " ORDER BY ano_referencia DESC, mes_referencia DESC LIMIT 12"
    else:
        query += " ORDER BY ano_referencia DESC, mes_referencia DESC"
    
    df_result = pd.read_sql_query(query, conn, params=params)
    return df_result

# Função para extrair mês e ano do nome do arquivo
def extrair_mes_ano_arquivo(nome_arquivo):
    """Extrai mês e ano do nome do arquivo automaticamente"""
    if not nome_arquivo:
        return None, None
    
    nome_upper = nome_arquivo.upper()
    
    # Mapeamento de meses
    meses_map = {
        'JAN': 'Janeiro', 'JANEIRO': 'Janeiro',
        'FEV': 'Fevereiro', 'FEVEREIRO': 'Fevereiro',
        'MAR': 'Março', 'MARCO': 'Março', 'MARÇO': 'Março',
        'ABR': 'Abril', 'ABRIL': 'Abril',
        'MAI': 'Maio', 'MAIO': 'Maio',
        'JUN': 'Junho', 'JUNHO': 'Junho',
        'JUL': 'Julho', 'JULHO': 'Julho',
        'AGO': 'Agosto', 'AGOSTO': 'Agosto',
        'SET': 'Setembro', 'SETEMBRO': 'Setembro',
        'OUT': 'Outubro', 'OUTUBRO': 'Outubro',
        'NOV': 'Novembro', 'NOVEMBRO': 'Novembro',
        'DEZ': 'Dezembro', 'DEZEMBRO': 'Dezembro'
    }
    
    # Procurar por padrões de data no nome do arquivo
    padroes_data = [
        r'(\d{1,2})[\.\-/](\d{1,2})[\.\-/](\d{4})',  # DD-MM-AAAA
        r'(\d{4})[\.\-/](\d{1,2})[\.\-/](\d{1,2})',  # AAAA-MM-DD
        r'(\w+)[\.\-/]?(\d{4})',  # MES-AAAA
        r'(\d{4})[\.\-/]?(\w+)',  # AAAA-MES
    ]
    
    for padrao in padroes_data:
        match = re.search(padrao, nome_upper)
        if match:
            grupos = match.groups()
            if len(grupos) == 3:
                # Formato DD-MM-AAAA ou AAAA-MM-DD
                if len(grupos[0]) == 4:  # AAAA-MM-DD
                    ano = int(grupos[0])
                    mes_num = int(grupos[1])
                else:  # DD-MM-AAAA
                    ano = int(grupos[2])
                    mes_num = int(grupos[1])
                
                meses_numeros = {
                    1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
                    5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
                    9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
                }
                return meses_numeros.get(mes_num, 'Janeiro'), ano
                
            elif len(grupos) == 2:
                # Formato MES-AAAA ou AAAA-MES
                if grupos[0].isdigit():  # AAAA-MES
                    ano = int(grupos[0])
                    mes_str = grupos[1]
                else:  # MES-AAAA
                    mes_str = grupos[0]
                    ano = int(grupos[1])
                
                for key, value in meses_map.items():
                    if key in mes_str:
                        return value, ano
    
    # Se não encontrou padrão específico, procurar por nomes de meses
    for key, value in meses_map.items():
        if key in nome_upper:
            # Procurar ano (4 dígitos)
            ano_match = re.search(r'(\d{4})', nome_upper)
            ano = int(ano_match.group(1)) if ano_match else datetime.now().year
            return value, ano
    
    return None, None

# Função auxiliar para obter coluna de conta
def obter_coluna_conta(df):
    """Identifica a coluna que contém o número da conta"""
    colunas_conta = ['Num Cartao', 'Num_Cartao', 'Conta', 'Número da Conta', 'Numero_Conta', 'Número do Cartão']
    for coluna in colunas_conta:
        if coluna in df.columns:
            return coluna
    return None

# Função auxiliar para obter coluna de nome/beneficiário
def obter_coluna_nome(df):
    """Identifica a coluna que contém o nome do beneficiário"""
    colunas_nome = ['Beneficiario', 'Beneficiário', 'Nome', 'Nome Completo', 'Nome do Beneficiário']
    for coluna in colunas_nome:
        if coluna in df.columns:
            return coluna
    return None

# Função auxiliar para obter coluna de valor (priorizando "Valor Pagto")
def obter_coluna_valor(df):
    """Identifica a coluna que contém o valor pago, priorizando 'Valor Pagto'"""
    colunas_valor_prioridade = ['Valor Pagto', 'Valor_Pagto', 'Valor Pgto', 'Valor_Pgto', 'Valor', 'Valor_Pago', 'Valor Pagamento']
    for coluna in colunas_valor_prioridade:
        if coluna in df.columns:
            return coluna
    return None

# Função auxiliar para formatar valores no padrão brasileiro
def formatar_brasileiro(valor, tipo='numero'):
    """Formata valores no padrão brasileiro"""
    if pd.isna(valor):
        valor = 0
    
    if tipo == 'monetario':
        return f"R$ {float(valor):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    elif tipo == 'numero':
        return f"{int(valor):,}".replace(',', '.')
    else:
        return str(valor)

# Identificar e remover linha de totais
def remover_linha_totais(df):
    """Identifica e remove a linha de totais da planilha de forma inteligente"""
    if df.empty or len(df) <= 1:
        return df
    
    df_limpo = df.copy()
    
    # Verificar se a última linha parece ser uma linha de totais
    ultima_linha = df_limpo.iloc[-1]
    
    criterios_totais = 0
    
    # Verificar colunas de texto
    colunas_texto = [col for col in df_limpo.columns if df_limpo[col].dtype == 'object']
    for coluna in colunas_texto[:3]:
        if pd.notna(ultima_linha[coluna]):
            valor = str(ultima_linha[coluna]).upper()
            if any(palavra in valor for palavra in ['TOTAL', 'SOMA', 'GERAL', 'TOTAL GERAL']):
                criterios_totais += 2
                break
    
    # Verificar colunas numéricas
    colunas_numericas = [col for col in df_limpo.columns if df_limpo[col].dtype in ['int64', 'float64']]
    if colunas_numericas:
        medias = df_limpo.iloc[:-1][colunas_numericas].mean()
        
        for coluna in colunas_numericas:
            if pd.notna(ultima_linha[coluna]) and pd.notna(medias[coluna]):
                if ultima_linha[coluna] > medias[coluna] * 10:
                    criterios_totais += 1
    
    # Se atende a pelo menos 2 critérios, remover a última linha
    if criterios_totais >= 2:
        df_limpo = df_limpo.iloc[:-1].copy()
        st.sidebar.info("📝 Linha de totais identificada e removida automaticamente")
    
    return df_limpo

# Filtrar apenas pagamentos válidos (com número de conta)
def filtrar_pagamentos_validos(df):
    """Filtra apenas os registros que possuem número da conta (pagamentos válidos)"""
    coluna_conta = obter_coluna_conta(df)
    
    if not coluna_conta:
        return df
    
    # Filtrar apenas registros com número de conta preenchido
    df_filtrado = df[df[coluna_conta].notna() & (df[coluna_conta].astype(str).str.strip() != '')].copy()
    
    # Remover possíveis valores "TOTAL", "SOMA", etc.
    palavras_totais = ['TOTAL', 'SOMA', 'GERAL', 'TOTAL GERAL']
    for palavra in palavras_totais:
        mask = df_filtrado[coluna_conta].astype(str).str.upper().str.contains(palavra, na=False)
        df_filtrado = df_filtrado[~mask]
    
    return df_filtrado

# Processar CPF para manter apenas números
def processar_cpf(cpf):
    """Processa CPF, mantendo apenas números e completando com zeros à esquerda"""
    if pd.isna(cpf) or cpf in ['', 'NaN', 'None', 'nan', 'None', 'NULL']:
        return ''
    
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

# Detectar CPFs problemáticos incluindo inconsistências
def identificar_cpfs_problematicos(df):
    """Identifica CPFs com problemas de formatação E inconsistências"""
    problemas_cpf = {
        'cpfs_com_caracteres_invalidos': [],
        'cpfs_com_tamanho_incorreto': [],
        'cpfs_vazios': [],
        'cpfs_duplicados': [],
        'cpfs_com_nomes_diferentes': [],
        'cpfs_com_contas_diferentes': [],
        'total_problemas_cpf': 0,
        'total_cpfs_inconsistentes': 0,
        'detalhes_cpfs_problematicos': pd.DataFrame(),
        'detalhes_inconsistencias': pd.DataFrame(),
        'registros_afetados': [],
        'status': 'validos_com_problema'
    }
    
    if 'CPF' not in df.columns or df.empty:
        return problemas_cpf
    
    # Adicionar coluna com número da linha original
    df_analise = df.copy()
    df_analise['Linha_Planilha_Original'] = df_analise.index + 2
    
    # PRIMEIRO: Identificar problemas de formatação
    for idx, row in df_analise.iterrows():
        cpf = str(row['CPF']) if pd.notna(row['CPF']) and str(row['CPF']).strip() != '' else ''
        problemas = []
        
        # CPF vazio
        if cpf == '':
            problemas.append('CPF vazio')
            problemas_cpf['cpfs_vazios'].append(idx)
            problemas_cpf['registros_afetados'].append(idx)
        
        # CPF com caracteres não numéricos
        elif not cpf.isdigit() and cpf != '':
            problemas.append('Caracteres inválidos')
            problemas_cpf['cpfs_com_caracteres_invalidos'].append(idx)
            problemas_cpf['registros_afetados'].append(idx)
        
        # CPF com tamanho incorreto
        elif len(cpf) != 11 and cpf != '':
            problemas.append(f'Tamanho incorreto ({len(cpf)} dígitos)')
            problemas_cpf['cpfs_com_tamanho_incorreto'].append(idx)
            problemas_cpf['registros_afetados'].append(idx)
        
        # Se há problemas de formatação, adicionar aos detalhes
        if problemas:
            info_problema = {
                'Linha_Planilha': row.get('Linha_Planilha_Original', idx + 2),
                'CPF_Original': row.get('CPF', ''),
                'CPF_Processado': cpf,
                'Problemas_Formatacao': ', '.join(problemas),
                'Status_Registro': 'VÁLIDO - Precisa de correção'
            }
            
            # Adicionar informações adicionais
            coluna_conta = obter_coluna_conta(df)
            if coluna_conta and coluna_conta in df.columns and pd.notna(row.get(coluna_conta)):
                info_problema['Numero_Conta'] = row[coluna_conta]
            
            coluna_nome = obter_coluna_nome(df)
            if coluna_nome and coluna_nome in df.columns and pd.notna(row.get(coluna_nome)):
                info_problema['Nome'] = row[coluna_nome]
            
            # Adicionar outras colunas importantes
            colunas_adicionais = ['Projeto', 'Valor', 'Data', 'Status']
            for coluna in colunas_adicionais:
                if coluna in df.columns and pd.notna(row.get(coluna)):
                    valor = str(row[coluna])
                    if len(valor) > 30:
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
    
    # SEGUNDO: Identificar CPFs duplicados com inconsistências
    cpfs_duplicados = df_analise[df_analise.duplicated(['CPF'], keep=False)]
    
    if not cpfs_duplicados.empty:
        grupos_cpf = cpfs_duplicados.groupby('CPF')
        
        detalhes_inconsistencias = []
        
        for cpf, grupo in grupos_cpf:
            if len(grupo) > 1:
                problemas_cpf['cpfs_duplicados'].append(cpf)
                
                # Verificar se há nomes diferentes para o mesmo CPF
                coluna_nome = obter_coluna_nome(grupo)
                tem_nomes_diferentes = False
                if coluna_nome and coluna_nome in grupo.columns:
                    nomes_unicos = grupo[coluna_nome].dropna().unique()
                    if len(nomes_unicos) > 1:
                        problemas_cpf['cpfs_com_nomes_diferentes'].append(cpf)
                        tem_nomes_diferentes = True
                
                # Verificar se há números de conta diferentes para o mesmo CPF
                coluna_conta = obter_coluna_conta(grupo)
                tem_contas_diferentes = False
                if coluna_conta and coluna_conta in grupo.columns:
                    contas_unicas = grupo[coluna_conta].dropna().unique()
                    if len(contas_unicas) > 1:
                        problemas_cpf['cpfs_com_contas_diferentes'].append(cpf)
                        tem_contas_diferentes = True
                
                # Se há qualquer inconsistência, adicionar aos detalhes
                if tem_nomes_diferentes or tem_contas_diferentes:
                    for idx, registro in grupo.iterrows():
                        info_inconsistencia = {
                            'CPF': cpf,
                            'Linha_Planilha': registro['Linha_Planilha_Original'],
                            'Ocorrencia_CPF': f"{list(grupo.index).index(idx) + 1}/{len(grupo)}"
                        }
                        
                        # Adicionar informações do registro
                        if coluna_nome and coluna_nome in registro:
                            info_inconsistencia['Nome'] = registro[coluna_nome]
                        
                        if coluna_conta and coluna_conta in registro:
                            info_inconsistencia['Numero_Conta'] = registro[coluna_conta]
                        
                        if 'Projeto' in registro:
                            info_inconsistencia['Projeto'] = registro['Projeto']
                        
                        if 'Valor_Limpo' in registro:
                            info_inconsistencia['Valor'] = formatar_brasileiro(registro['Valor_Limpo'], 'monetario')
                        
                        # Marcar inconsistências específicas
                        problemas_inconsistencia = []
                        if tem_nomes_diferentes:
                            problemas_inconsistencia.append('NOMES DIF')
                        if tem_contas_diferentes:
                            problemas_inconsistencia.append('CONTAS DIF')
                        
                        info_inconsistencia['Problemas_Inconsistencia'] = 'CPF DUP' + (', ' + ', '.join(problemas_inconsistencia) if problemas_inconsistencia else '')
                        info_inconsistencia['Status'] = 'CRÍTICO'
                        
                        detalhes_inconsistencias.append(info_inconsistencia)
        
        if detalhes_inconsistencias:
            problemas_cpf['detalhes_inconsistencias'] = pd.DataFrame(detalhes_inconsistencias)
            problemas_cpf['total_cpfs_inconsistentes'] = len(set(
                problemas_cpf['cpfs_com_nomes_diferentes'] + 
                problemas_cpf['cpfs_com_contas_diferentes']
            ))
    
    # Calcular totais
    problemas_cpf['total_problemas_cpf'] = (
        len(problemas_cpf['cpfs_com_caracteres_invalidos']) +
        len(problemas_cpf['cpfs_com_tamanho_incorreto']) +
        len(problemas_cpf['cpfs_vazios'])
    )
    
    return problemas_cpf

# Detectar pagamentos duplicados
def detectar_pagamentos_duplicados(df):
    """Detecta pagamentos duplicados por número de conta"""
    duplicidades = {
        'contas_duplicadas': pd.DataFrame(),
        'total_contas_duplicadas': 0,
        'total_pagamentos_duplicados': 0,
        'valor_total_duplicados': 0,
        'resumo_duplicidades': pd.DataFrame(),
        'contas_com_multiplos_pagamentos': [],
        'detalhes_completos_duplicidades': pd.DataFrame()
    }
    
    # Filtrar apenas pagamentos válidos (com número de conta)
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
    colunas_data = ['Data', 'Data Pagto', 'Data_Pagto', 'DataPagto', 'Data Pagamento']
    for col_data in colunas_data:
        if col_data in df_duplicados.columns:
            colunas_ordenacao.append(col_data)
            break
    
    df_duplicados = df_duplicados.sort_values(by=colunas_ordenacao)
    
    # Adicionar contador de ocorrências por conta
    df_duplicados['Ocorrencia'] = df_duplicados.groupby(coluna_conta).cumcount() + 1
    df_duplicados['Total_Ocorrencias'] = df_duplicados.groupby(coluna_conta)[coluna_conta].transform('count')
    
    # Preparar dados completos para exibição
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
    
    # Usar coluna de valor correta
    coluna_valor = obter_coluna_valor(df_duplicados)
    if coluna_valor:
        colunas_exibicao_completas.append(coluna_valor)
    
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

# Detectar pagamentos pendentes
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
    
    # Filtrar apenas pagamentos válidos (com número de conta)
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

# Padronizar documentos - CPF apenas números
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

# Nova função para processar colunas de data
def processar_colunas_data(df):
    """Converte colunas de data de formato numérico do Excel para datas legíveis"""
    df_processed = df.copy()
    
    colunas_data = ['Data', 'Data Pagto', 'Data_Pagto', 'DataPagto', 'Data Pagamento']
    
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

# Função para processar colunas de valor (priorizando "Valor Pagto")
def processar_colunas_valor(df):
    """Processa colunas de valor para formato brasileiro, priorizando 'Valor Pagto'"""
    df_processed = df.copy()
    
    # ORDEM DE PRIORIDADE para colunas de valor
    colunas_valor_prioridade = ['Valor Pagto', 'Valor_Pagto', 'Valor Pgto', 'Valor_Pgto', 'Valor', 'Valor_Pago', 'Valor Pagamento']
    
    coluna_valor_encontrada = None
    for coluna_valor in colunas_valor_prioridade:
        if coluna_valor in df_processed.columns:
            coluna_valor_encontrada = coluna_valor
            break
    
    if coluna_valor_encontrada:
        try:
            # Processar todos os valores, não apenas strings
            valores_limpos = []
            
            for valor in df_processed[coluna_valor_encontrada]:
                if pd.isna(valor):
                    valores_limpos.append(0.0)
                    continue
                
                # Se já é numérico, usar diretamente
                if isinstance(valor, (int, float)):
                    valores_limpos.append(float(valor))
                    continue
                
                # Se é string, processar
                valor_str = str(valor).strip()
                if valor_str == '':
                    valores_limpos.append(0.0)
                    continue
                
                # Remover caracteres não numéricos exceto ponto e vírgula
                valor_limpo_str = re.sub(r'[^\d,.]', '', valor_str)
                
                # Substituir vírgula por ponto para conversão float
                valor_limpo_str = valor_limpo_str.replace(',', '.')
                
                # Se tem múltiplos pontos, manter apenas o último como decimal
                if valor_limpo_str.count('.') > 1:
                    partes = valor_limpo_str.split('.')
                    valor_limpo_str = ''.join(partes[:-1]) + '.' + partes[-1]
                
                try:
                    valor_float = float(valor_limpo_str) if valor_limpo_str else 0.0
                    valores_limpos.append(valor_float)
                except:
                    valores_limpos.append(0.0)
            
            df_processed['Valor_Limpo'] = valores_limpos
            st.sidebar.success(f"💰 Coluna de valor utilizada: '{coluna_valor_encontrada}'")
                
        except Exception as e:
            st.warning(f"⚠️ Erro ao processar valores da coluna '{coluna_valor_encontrada}': {str(e)}")
            df_processed['Valor_Limpo'] = 0.0
    else:
        st.warning("⚠️ Nenhuma coluna de valor encontrada na planilha")
        df_processed['Valor_Limpo'] = 0.0
    
    return df_processed

# Analisar ausência de dados - APENAS REGISTROS REALMENTE INVÁLIDOS
def analisar_ausencia_dados(dados, nome_arquivo_pagamentos=None, nome_arquivo_contas=None):
    """Analisa e reporta apenas dados críticos realmente ausentes"""
    analise_ausencia = {
        'registros_criticos_problematicos': [],
        'total_registros_criticos': 0,
        'colunas_com_ausencia_critica': {},
        'resumo_ausencias': pd.DataFrame(),
        'registros_problema_detalhados': pd.DataFrame(),
        'nome_arquivo_pagamentos': nome_arquivo_pagamentos,
        'nome_arquivo_contas': nome_arquivo_contas
    }
    
    if 'pagamentos' in dados and not dados['pagamentos'].empty:
        # Usar dados SEM linha de totais para análise de ausência
        df = dados['pagamentos_sem_totais'] if 'pagamentos_sem_totais' in dados else dados['pagamentos']
        
        # Adicionar coluna com número da linha original
        df = df.reset_index(drop=True)
        df['Linha_Planilha_Original'] = df.index + 2
        
        # Apenas dados REALMENTE críticos ausentes
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
        if 'Valor_Limpo' in df.columns:
            mask_valor_invalido = (
                df['Valor_Limpo'].isna() | 
                (df['Valor_Limpo'] == 0)
            )
            valores_invalidos = df[mask_valor_invalido]
            for idx in valores_invalidos.index:
                if idx not in registros_problematicos:
                    registros_problematicos.append(idx)
        
        # REMOVER registros que já foram ajustados (com CPF válido)
        # Um registro NÃO é crítico se tem conta e valor válidos, mesmo com CPF problemático
        registros_problematicos_filtrados = []
        for idx in registros_problematicos:
            registro = df.loc[idx]
            # Verificar se o registro tem conta e valor válidos
            tem_conta_valida = coluna_conta and pd.notna(registro[coluna_conta]) and str(registro[coluna_conta]).strip() != ''
            tem_valor_valido = 'Valor_Limpo' in df.columns and pd.notna(registro['Valor_Limpo']) and registro['Valor_Limpo'] > 0
            
            # Se não tem conta OU não tem valor válido, é crítico
            if not tem_conta_valida or not tem_valor_valido:
                registros_problematicos_filtrados.append(idx)
        
        # Atualizar análise com apenas registros realmente críticos
        analise_ausencia['registros_criticos_problematicos'] = registros_problematicos_filtrados
        analise_ausencia['total_registros_criticos'] = len(registros_problematicos_filtrados)
        
        if registros_problematicos_filtrados:
            analise_ausencia['registros_problema_detalhados'] = df.loc[registros_problematicos_filtrados].copy()
        
        # Criar resumo de ausências com informações da planilha original
        if registros_problematicos_filtrados:
            resumo = []
            for idx in registros_problematicos_filtrados[:100]:  # Limitar a 100 registros
                registro = df.loc[idx]
                info_ausencia = {
                    'Indice_Registro': idx,
                    'Linha_Planilha': registro.get('Linha_Planilha_Original', idx + 2),
                    'Planilha_Origem': nome_arquivo_pagamentos or 'Pagamentos',
                    'Status_Registro': 'INVÁLIDO - Precisa de correção'
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
                
                # Marcar campos problemáticos
                problemas = []
                if coluna_conta and (pd.isna(registro[coluna_conta]) or str(registro[coluna_conta]).strip() == ''):
                    problemas.append('Número da conta ausente')
                
                if 'Valor_Limpo' in df.columns and (pd.isna(registro['Valor_Limpo']) or registro.get('Valor_Limpo', 0) == 0):
                    problemas.append('Valor ausente ou zero')
                
                info_ausencia['Problemas_Identificados'] = ', '.join(problemas) if problemas else 'Dados OK'
                resumo.append(info_ausencia)
            
            analise_ausencia['resumo_ausencias'] = pd.DataFrame(resumo)
    
    return analise_ausencia

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
        'total_cpfs_duplicados': 0,
        'total_contas_abertas': 0,
        'beneficiarios_contas': 0,
        'duplicidades_detalhadas': {},
        'pagamentos_pendentes': {},
        'total_registros_invalidos': 0,
        'problemas_cpf': {},
        'linha_totais_removida': False,
        'total_registros_originais': 0,
        'total_registros_sem_totais': 0,
        'total_cpfs_ajuste': 0
    }
    
    # Combinar com análise de ausência de dados
    analise_ausencia = analisar_ausencia_dados(dados, nomes_arquivos.get('pagamentos'), nomes_arquivos.get('contas'))
    metrics.update(analise_ausencia)
    
    # Processar planilha de PAGAMENTOS
    if 'pagamentos' in dados and not dados['pagamentos'].empty:
        df_original = dados['pagamentos']
        metrics['total_registros_originais'] = len(df_original)
        
        # Remover linha de totais antes de qualquer processamento
        df_sem_totais = remover_linha_totais(df_original)
        metrics['total_registros_sem_totais'] = len(df_sem_totais)
        
        if len(df_sem_totais) < len(df_original):
            metrics['linha_totais_removida'] = True
        
        # Filtrar apenas pagamentos válidos (com número de conta)
        df = filtrar_pagamentos_validos(df_sem_totais)
        
        # Contar registros inválidos (sem número de conta)
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
        
        # Analisar problemas com CPF - INCLUI INCONSISTÊNCIAS
        problemas_cpf = identificar_cpfs_problematicos(df)
        metrics['problemas_cpf'] = problemas_cpf
        
        # Total de CPFs que precisam de ajuste (formatação + inconsistências)
        metrics['total_cpfs_ajuste'] = (
            problemas_cpf['total_problemas_cpf'] + 
            problemas_cpf['total_cpfs_inconsistentes']
        )
        
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
        
        # Valor total - SOMA DE TODOS OS PAGAMENTOS VÁLIDOS
        if 'Valor_Limpo' in df.columns:
            # Garantir que estamos somando apenas valores válidos
            valores_validos = df['Valor_Limpo'].fillna(0)
            metrics['valor_total'] = valores_validos.sum()
            
            # Informar qual coluna foi usada para o cálculo
            coluna_valor_origem = obter_coluna_valor(df)
            if coluna_valor_origem:
                st.sidebar.success(f"💰 Total calculado a partir de: '{coluna_valor_origem}' = R$ {metrics['valor_total']:,.2f}")
        
        # CPFs duplicados - APENAS SE A COLUNA EXISTIR
        if 'CPF' in df.columns:
            cpfs_duplicados = df[df.duplicated(['CPF'], keep=False)]
            metrics['total_cpfs_duplicados'] = cpfs_duplicados['CPF'].nunique()
    
    # Processar planilha de ABERTURA DE CONTAS
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
    
    if metricas.empty or len(metricas) < 2:
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
        title='Evolução do Valor Total Mensal (Valor Pagto)',
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
    
    # Verificar se a coluna cpfs_ajuste existe
    if 'cpfs_ajuste' in metricas.columns:
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

# Criar dashboard de estatísticas
def criar_dashboard_estatisticas(metrics, dados):
    """Cria dashboard com estatísticas detalhadas dos dados atuais"""
    if 'pagamentos' not in dados or dados['pagamentos'].empty:
        return None
    
    df = dados['pagamentos']
    
    # Verificar se temos dados válidos para gráficos
    dashboard_data = {}
    
    # Gráfico de distribuição de valores (se disponível)
    if 'Valor_Limpo' in df.columns and not df['Valor_Limpo'].empty:
        try:
            # Filtrar valores válidos e positivos
            valores_validos = df[df['Valor_Limpo'] > 0]['Valor_Limpo']
            if len(valores_validos) > 0:
                fig_valores = px.histogram(
                    x=valores_validos,
                    title='Distribuição de Valores dos Pagamentos (Valor Pagto)',
                    labels={'x': 'Valor (R$)', 'y': 'Quantidade'},
                    nbins=20
                )
                dashboard_data['valores'] = fig_valores
        except Exception as e:
            st.warning(f"Não foi possível criar gráfico de distribuição de valores: {e}")
    
    # Gráfico de projetos (se disponível)
    if 'Projeto' in df.columns and not df['Projeto'].empty:
        try:
            projetos_count = df['Projeto'].value_counts().head(10)
            if len(projetos_count) > 0:
                fig_projetos = px.bar(
                    x=projetos_count.index,
                    y=projetos_count.values,
                    title='Top 10 Projetos por Quantidade de Pagamentos',
                    labels={'x': 'Projeto', 'y': 'Quantidade de Pagamentos'}
                )
                dashboard_data['projetos'] = fig_projetos
        except Exception as e:
            st.warning(f"Não foi possível criar gráfico de projetos: {e}")
    
    # Gráfico de status (se disponível)
    if 'Status' in df.columns and not df['Status'].empty:
        try:
            status_count = df['Status'].value_counts()
            if len(status_count) > 0:
                fig_status = px.pie(
                    values=status_count.values,
                    names=status_count.index,
                    title='Distribuição por Status'
                )
                dashboard_data['status'] = fig_status
        except Exception as e:
            st.warning(f"Não foi possível criar gráfico de status: {e}")
    
    # Métricas estatísticas
    if 'Valor_Limpo' in df.columns:
        valores = df[df['Valor_Limpo'] > 0]['Valor_Limpo']
        if len(valores) > 0:
            stats = {
                'media': valores.mean(),
                'mediana': valores.median(),
                'desvio_padrao': valores.std(),
                'minimo': valores.min(),
                'maximo': valores.max()
            }
            dashboard_data['estatisticas'] = stats
    
    return dashboard_data

# Classe PDF para relatórios
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, 'Relatório de Análise - Sistema POT SMDET', 0, 1, 'C')
        self.ln(5)
    
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')
    
    def chapter_title(self, title):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, title, 0, 1, 'L')
        self.ln(5)
    
    def chapter_body(self, body):
        self.set_font('Arial', '', 10)
        self.multi_cell(0, 8, body)
        self.ln()

# Função para gerar relatório PDF
def gerar_relatorio_pdf(metrics, dados, mes_ref, ano_ref):
    """Gera relatório PDF com os resultados da análise"""
    pdf = PDF()
    pdf.add_page()
    
    # Cabeçalho
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 10, 'RELATÓRIO DE ANÁLISE - SISTEMA POT SMDET', 0, 1, 'C')
    pdf.ln(5)
    
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 10, f'Período de Referência: {mes_ref}/{ano_ref}', 0, 1, 'C')
    pdf.cell(0, 10, f'Data de Emissão: {data_atual_brasilia()}', 0, 1, 'C')
    pdf.ln(10)
    
    # Resumo Executivo
    pdf.chapter_title('RESUMO EXECUTIVO')
    
    resumo_texto = f"""
    Total de Pagamentos Válidos: {metrics.get('total_pagamentos', 0)}
    Beneficiários Únicos: {metrics.get('beneficiarios_unicos', 0)}
    Valor Total Distribuído: {formatar_brasileiro(metrics.get('valor_total', 0), 'monetario')}
    Contas Únicas: {metrics.get('contas_unicas', 0)}
    Projetos Ativos: {metrics.get('projetos_ativos', 0)}
    
    PROBLEMAS IDENTIFICADOS:
    - Registros Críticos: {metrics.get('total_registros_criticos', 0)}
    - CPFs com Problemas: {metrics.get('total_cpfs_ajuste', 0)}
    - Pagamentos Duplicados: {metrics.get('pagamentos_duplicados', 0)}
    - Valor em Duplicidades: {formatar_brasileiro(metrics.get('valor_total_duplicados', 0), 'monetario')}
    """
    
    pdf.chapter_body(resumo_texto)
    
    # Detalhes de Problemas de CPF
    if metrics.get('problemas_cpf', {}).get('total_problemas_cpf', 0) > 0:
        pdf.chapter_title('PROBLEMAS DE CPF IDENTIFICADOS')
        
        problemas_cpf = metrics['problemas_cpf']
        problemas_texto = f"""
        CPFs com Caracteres Inválidos: {len(problemas_cpf.get('cpfs_com_caracteres_invalidos', []))}
        CPFs com Tamanho Incorreto: {len(problemas_cpf.get('cpfs_com_tamanho_incorreto', []))}
        CPFs Vazios: {len(problemas_cpf.get('cpfs_vazios', []))}
        CPFs Duplicados com Inconsistências: {problemas_cpf.get('total_cpfs_inconsistentes', 0)}
        """
        
        pdf.chapter_body(problemas_texto)
        
        # Detalhes de inconsistências
        if not problemas_cpf.get('detalhes_inconsistencias', pd.DataFrame()).empty:
            pdf.chapter_title('DETALHES DE INCONSISTÊNCIAS EM CPFs DUPLICADOS')
            
            df_inconsistencias = problemas_cpf['detalhes_inconsistencias']
            for _, row in df_inconsistencias.iterrows():
                inconsistencia_text = f"""
                CPF: {row.get('CPF', '')} | Linha: {row.get('Linha_Planilha', '')}
                Problema: {row.get('Problemas_Inconsistencia', '')}
                Nome: {row.get('Nome', '')} | Conta: {row.get('Numero_Conta', '')}
                """
                pdf.chapter_body(inconsistencia_text)
    
    # Pagamentos Pendentes
    if metrics.get('pagamentos_pendentes', {}).get('total_contas_sem_pagamento', 0) > 0:
        pdf.chapter_title('PAGAMENTOS PENDENTES')
        
        pendentes = metrics['pagamentos_pendentes']
        pendentes_texto = f"""
        Total de Contas sem Pagamento: {pendentes.get('total_contas_sem_pagamento', 0)}
        Beneficiários sem Pagamento: {pendentes.get('beneficiarios_sem_pagamento', 0)}
        """
        
        pdf.chapter_body(pendentes_texto)
    
    # Métricas Estatísticas
    dashboard = criar_dashboard_estatisticas(metrics, dados)
    if dashboard and 'estatisticas' in dashboard:
        pdf.chapter_title('ESTATÍSTICAS DOS VALORES')
        
        stats = dashboard['estatisticas']
        stats_texto = f"""
        Valor Médio: {formatar_brasileiro(stats.get('media', 0), 'monetario')}
        Valor Mediano: {formatar_brasileiro(stats.get('mediana', 0), 'monetario')}
        Menor Valor: {formatar_brasileiro(stats.get('minimo', 0), 'monetario')}
        Maior Valor: {formatar_brasileiro(stats.get('maximo', 0), 'monetario')}
        Desvio Padrão: {formatar_brasileiro(stats.get('desvio_padrao', 0), 'monetario')}
        """
        
        pdf.chapter_body(stats_texto)
    
    return pdf

# Função para criar tabela de download
def criar_tabela_download(df, nome_arquivo):
    """Cria um link para download de DataFrame como CSV"""
    csv = df.to_csv(index=False, encoding='utf-8-sig')
    b64 = base64.b64encode(csv.encode('utf-8-sig')).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="{nome_arquivo}.csv">📥 Baixar {nome_arquivo}</a>'
    return href

# Função principal da aplicação
def main():
    """Função principal da aplicação Streamlit"""
    
    # Autenticação
    usuario = autenticar()
    if not usuario:
        st.warning("🔒 Acesso não autorizado. Faça login para continuar.")
        return
    
    # Inicializar banco de dados
    conn = init_database()
    
    st.title("🏛️ Sistema POT - SMDET")
    st.markdown("**Secretaria Municipal do Desenvolvimento Econômico e Trabalho**")
    st.markdown("---")
    
    # Menu principal
    menu = st.sidebar.selectbox(
        "📊 Navegação",
        ["Importar Dados", "Dashboard Principal", "Relatórios Comparativos", "Gestão de Dados"]
    )
    
    if menu == "Importar Dados":
        st.header("📁 Importação de Dados")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Planilha de Pagamentos")
            arquivo_pagamentos = st.file_uploader(
                "Carregar planilha de pagamentos realizados",
                type=['xlsx', 'xls', 'csv'],
                key="pagamentos"
            )
            
            if arquivo_pagamentos:
                try:
                    # Ler arquivo
                    if arquivo_pagamentos.name.endswith('.csv'):
                        df_pagamentos = pd.read_csv(arquivo_pagamentos)
                    else:
                        df_pagamentos = pd.read_excel(arquivo_pagamentos)
                    
                    st.success(f"✅ Arquivo carregado: {arquivo_pagamentos.name}")
                    st.info(f"📊 Total de registros: {len(df_pagamentos)}")
                    
                    # Extrair mês e ano do nome do arquivo
                    mes_ref, ano_ref = extrair_mes_ano_arquivo(arquivo_pagamentos.name)
                    
                    if not mes_ref or not ano_ref:
                        mes_ref = st.selectbox(
                            "Mês de referência",
                            ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                             'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'],
                            key="mes_pag"
                        )
                        ano_ref = st.number_input("Ano de referência", min_value=2020, max_value=2030, value=datetime.now().year, key="ano_pag")
                    
                    # Processar dados
                    with st.spinner("Processando dados de pagamentos..."):
                        # Processar valores
                        df_pagamentos_processado = processar_colunas_valor(df_pagamentos)
                        # Processar datas
                        df_pagamentos_processado = processar_colunas_data(df_pagamentos_processado)
                        # Padronizar documentos
                        df_pagamentos_processado = padronizar_documentos(df_pagamentos_processado)
                        
                        # Verificar duplicidade de arquivo
                        file_hash = hash_arquivo(arquivo_pagamentos.getvalue())
                        if verificar_arquivo_existente(conn, 'pagamentos', file_hash):
                            st.warning("⚠️ Este arquivo já foi importado anteriormente.")
                            sobrescrever = st.checkbox("Sobrescrever dados existentes?")
                            if not sobrescrever:
                                st.stop()
                        
                        # Salvar no banco de dados
                        metadados = {
                            'usuario_importacao': usuario,
                            'total_registros_originais': len(df_pagamentos),
                            'colunas_identificadas': list(df_pagamentos.columns),
                            'coluna_conta': obter_coluna_conta(df_pagamentos),
                            'coluna_valor': obter_coluna_valor(df_pagamentos),
                            'coluna_nome': obter_coluna_nome(df_pagamentos)
                        }
                        
                        salvar_pagamentos_db(conn, mes_ref, ano_ref, arquivo_pagamentos.name, df_pagamentos_processado, metadados, file_hash)
                        st.success("✅ Dados de pagamentos salvos com sucesso!")
                        
                        # Processar métricas e salvar
                        dados_temp = {'pagamentos': df_pagamentos_processado}
                        metrics = processar_dados(dados_temp, {'pagamentos': arquivo_pagamentos.name})
                        salvar_metricas_db(conn, 'pagamentos', mes_ref, ano_ref, metrics)
                        
                except Exception as e:
                    st.error(f"❌ Erro ao processar arquivo: {str(e)}")
        
        with col2:
            st.subheader("Planilha de Abertura de Contas")
            arquivo_contas = st.file_uploader(
                "Carregar planilha de abertura de contas/inscrições",
                type=['xlsx', 'xls', 'csv'],
                key="contas"
            )
            
            if arquivo_contas:
                try:
                    # Ler arquivo
                    if arquivo_contas.name.endswith('.csv'):
                        df_contas = pd.read_csv(arquivo_contas)
                    else:
                        df_contas = pd.read_excel(arquivo_contas)
                    
                    st.success(f"✅ Arquivo carregado: {arquivo_contas.name}")
                    st.info(f"📊 Total de registros: {len(df_contas)}")
                    
                    # Extrair mês e ano do nome do arquivo
                    mes_ref, ano_ref = extrair_mes_ano_arquivo(arquivo_contas.name)
                    
                    if not mes_ref or not ano_ref:
                        mes_ref = st.selectbox(
                            "Mês de referência",
                            ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                             'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'],
                            key="mes_cont"
                        )
                        ano_ref = st.number_input("Ano de referência", min_value=2020, max_value=2030, value=datetime.now().year, key="ano_cont")
                    
                    # Processar dados
                    with st.spinner("Processando dados de contas..."):
                        # Processar datas
                        df_contas_processado = processar_colunas_data(df_contas)
                        # Padronizar documentos
                        df_contas_processado = padronizar_documentos(df_contas_processado)
                        
                        # Verificar duplicidade de arquivo
                        file_hash = hash_arquivo(arquivo_contas.getvalue())
                        if verificar_arquivo_existente(conn, 'inscricoes', file_hash):
                            st.warning("⚠️ Este arquivo já foi importado anteriormente.")
                            sobrescrever = st.checkbox("Sobrescrever dados existentes?", key="sob_cont")
                            if not sobrescrever:
                                st.stop()
                        
                        # Salvar no banco de dados
                        metadados = {
                            'usuario_importacao': usuario,
                            'total_registros_originais': len(df_contas),
                            'colunas_identificadas': list(df_contas.columns),
                            'coluna_conta': obter_coluna_conta(df_contas),
                            'coluna_nome': obter_coluna_nome(df_contas)
                        }
                        
                        salvar_inscricoes_db(conn, mes_ref, ano_ref, arquivo_contas.name, df_contas_processado, metadados, file_hash)
                        st.success("✅ Dados de contas salvos com sucesso!")
                        
                except Exception as e:
                    st.error(f"❌ Erro ao processar arquivo: {str(e)}")
    
    elif menu == "Dashboard Principal":
        st.header("📊 Dashboard Principal")
        
        # Selecionar período para análise
        col1, col2 = st.columns(2)
        
        with col1:
            mes_selecionado = st.selectbox(
                "Mês de referência",
                ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
            )
        
        with col2:
            ano_selecionado = st.number_input("Ano de referência", min_value=2020, max_value=2030, value=datetime.now().year)
        
        # Carregar dados do período selecionado
        df_pagamentos_periodo = carregar_pagamentos_db(conn, mes_selecionado, ano_selecionado)
        df_contas_periodo = carregar_inscricoes_db(conn, mes_selecionado, ano_selecionado)
        
        if df_pagamentos_periodo.empty:
            st.warning("ℹ️ Nenhum dado encontrado para o período selecionado.")
            return
        
        # Processar dados
        dados = {}
        
        if not df_pagamentos_periodo.empty:
            # Carregar dados JSON da primeira linha (assumindo que todos os registros são do mesmo período)
            dados_json = json.loads(df_pagamentos_periodo.iloc[0]['dados_json'])
            dados['pagamentos'] = pd.DataFrame(dados_json)
        
        if not df_contas_periodo.empty:
            dados_json = json.loads(df_contas_periodo.iloc[0]['dados_json'])
            dados['contas'] = pd.DataFrame(dados_json)
        
        # Processar métricas
        with st.spinner("Calculando métricas..."):
            nomes_arquivos = {
                'pagamentos': df_pagamentos_periodo.iloc[0]['nome_arquivo'] if not df_pagamentos_periodo.empty else None,
                'contas': df_contas_periodo.iloc[0]['nome_arquivo'] if not df_contas_periodo.empty else None
            }
            
            metrics = processar_dados(dados, nomes_arquivos)
        
        # Exibir métricas principais
        st.subheader("📈 Métricas Principais")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "Total de Pagamentos",
                formatar_brasileiro(metrics.get('total_pagamentos', 0)),
                help="Número total de pagamentos válidos processados"
            )
        
        with col2:
            st.metric(
                "Beneficiários Únicos",
                formatar_brasileiro(metrics.get('beneficiarios_unicos', 0)),
                help="Número de beneficiários distintos que receberam pagamentos"
            )
        
        with col3:
            st.metric(
                "Valor Total",
                formatar_brasileiro(metrics.get('valor_total', 0), 'monetario'),
                help="Soma total dos valores pagos"
            )
        
        with col4:
            st.metric(
                "Projetos Ativos",
                formatar_brasileiro(metrics.get('projetos_ativos', 0)),
                help="Número de projetos com pagamentos realizados"
            )
        
        # Alertas e problemas
        st.subheader("⚠️ Alertas e Problemas Identificados")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            cor = "red" if metrics.get('total_registros_criticos', 0) > 0 else "green"
            st.metric(
                "Registros Críticos",
                formatar_brasileiro(metrics.get('total_registros_criticos', 0)),
                delta=None,
                delta_color="off",
                help="Registros com dados essenciais faltantes",
            )
            if metrics.get('total_registros_criticos', 0) > 0:
                st.error("🚨 Registros inválidos detectados")
        
        with col2:
            cor = "red" if metrics.get('total_cpfs_ajuste', 0) > 0 else "green"
            st.metric(
                "CPFs p/ Ajuste",
                formatar_brasileiro(metrics.get('total_cpfs_ajuste', 0)),
                delta=None,
                delta_color="off",
                help="CPFs com problemas de formatação ou inconsistências"
            )
            if metrics.get('total_cpfs_ajuste', 0) > 0:
                st.warning("📝 CPFs precisam de correção")
        
        with col3:
            cor = "red" if metrics.get('pagamentos_duplicados', 0) > 0 else "green"
            st.metric(
                "Pagamentos Duplicados",
                formatar_brasileiro(metrics.get('pagamentos_duplicados', 0)),
                delta=None,
                delta_color="off",
                help="Contas com múltiplos pagamentos no mesmo período"
            )
            if metrics.get('pagamentos_duplicados', 0) > 0:
                st.warning("🔍 Possíveis duplicidades detectadas")
        
        with col4:
            pendentes = metrics.get('pagamentos_pendentes', {})
            cor = "orange" if pendentes.get('total_contas_sem_pagamento', 0) > 0 else "green"
            st.metric(
                "Pagamentos Pendentes",
                formatar_brasileiro(pendentes.get('total_contas_sem_pagamento', 0)),
                delta=None,
                delta_color="off",
                help="Contas abertas sem pagamento correspondente"
            )
            if pendentes.get('total_contas_sem_pagamento', 0) > 0:
                st.info("⏳ Contas aguardando pagamento")
        
        # Dashboard visual
        st.subheader("📊 Visualizações")
        
        dashboard = criar_dashboard_estatisticas(metrics, dados)
        
        if dashboard:
            col1, col2 = st.columns(2)
            
            with col1:
                if 'valores' in dashboard:
                    st.plotly_chart(dashboard['valores'], use_container_width=True)
            
            with col2:
                if 'projetos' in dashboard:
                    st.plotly_chart(dashboard['projetos'], use_container_width=True)
            
            if 'status' in dashboard:
                st.plotly_chart(dashboard['status'], use_container_width=True)
        
        # Detalhamento de problemas
        st.subheader("🔍 Detalhamento de Problemas")
        
        # Problemas de CPF
        problemas_cpf = metrics.get('problemas_cpf', {})
        if problemas_cpf.get('total_problemas_cpf', 0) > 0 or problemas_cpf.get('total_cpfs_inconsistentes', 0) > 0:
            with st.expander("Problemas com CPF"):
                st.write(f"**Total de problemas de formatação:** {problemas_cpf.get('total_problemas_cpf', 0)}")
                st.write(f"**CPFs com inconsistências:** {problemas_cpf.get('total_cpfs_inconsistentes', 0)}")
                
                if not problemas_cpf.get('detalhes_cpfs_problematicos', pd.DataFrame()).empty:
                    st.write("**Detalhes dos problemas de formatação:**")
                    st.dataframe(problemas_cpf['detalhes_cpfs_problematicos'], use_container_width=True)
                
                if not problemas_cpf.get('detalhes_inconsistencias', pd.DataFrame()).empty:
                    st.write("**Detalhes das inconsistências:**")
                    st.dataframe(problemas_cpf['detalhes_inconsistencias'], use_container_width=True)
        
        # Duplicidades
        duplicidades = metrics.get('duplicidades_detalhadas', {})
        if duplicidades.get('total_contas_duplicadas', 0) > 0:
            with st.expander("Pagamentos Duplicados"):
                st.write(f"**Contas com pagamentos duplicados:** {duplicidades.get('total_contas_duplicadas', 0)}")
                st.write(f"**Total de pagamentos duplicados:** {duplicidades.get('total_pagamentos_duplicados', 0)}")
                st.write(f"**Valor total em duplicidades:** {formatar_brasileiro(duplicidades.get('valor_total_duplicados', 0), 'monetario')}")
                
                if not duplicidades.get('resumo_duplicidades', pd.DataFrame()).empty:
                    st.write("**Resumo por conta:**")
                    st.dataframe(duplicidades['resumo_duplicidades'], use_container_width=True)
        
        # Pagamentos pendentes
        pendentes = metrics.get('pagamentos_pendentes', {})
        if pendentes.get('total_contas_sem_pagamento', 0) > 0:
            with st.expander("Pagamentos Pendentes"):
                st.write(f"**Contas sem pagamento:** {pendentes.get('total_contas_sem_pagamento', 0)}")
                st.write(f"**Beneficiários sem pagamento:** {pendentes.get('beneficiarios_sem_pagamento', 0)}")
                
                if not pendentes.get('contas_sem_pagamento', pd.DataFrame()).empty:
                    st.write("**Detalhes das contas pendentes:**")
                    st.dataframe(pendentes['contas_sem_pagamento'], use_container_width=True)
        
        # Gerar relatório PDF
        st.subheader("📄 Relatório")
        
        if st.button("🖨️ Gerar Relatório PDF", type="primary"):
            with st.spinner("Gerando relatório PDF..."):
                pdf = gerar_relatorio_pdf(metrics, dados, mes_selecionado, ano_selecionado)
                
                # Salvar PDF em buffer
                pdf_buffer = io.BytesIO()
                pdf.output(pdf_buffer)
                pdf_buffer.seek(0)
                
                # Criar link de download
                b64_pdf = base64.b64encode(pdf_buffer.read()).decode()
                href = f'<a href="data:application/pdf;base64,{b64_pdf}" download="relatorio_pot_{mes_selecionado}_{ano_selecionado}.pdf">📥 Baixar Relatório PDF</a>'
                st.markdown(href, unsafe_allow_html=True)
    
    elif menu == "Relatórios Comparativos":
        st.header("📈 Relatórios Comparativos")
        
        periodo = st.selectbox(
            "Período de análise",
            ['mensal', 'trimestral', 'semestral', 'anual'],
            help="Selecione o período para análise comparativa"
        )
        
        dashboard_evolucao = criar_dashboard_evolucao(conn, periodo)
        
        if not dashboard_evolucao:
            st.warning("ℹ️ Dados insuficientes para análise comparativa.")
            return
        
        # Exibir gráficos
        st.subheader("Evolução Temporal")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.plotly_chart(dashboard_evolucao['evolucao'], use_container_width=True)
        
        with col2:
            st.plotly_chart(dashboard_evolucao['valor'], use_container_width=True)
        
        st.plotly_chart(dashboard_evolucao['problemas'], use_container_width=True)
        
        # Tabela comparativa
        st.subheader("Tabela Comparativa")
        
        df_metricas = dashboard_evolucao['dados']
        
        # Calcular variações - CORREÇÃO: Evitar NaN%
        if len(df_metricas) > 1:
            df_metricas = df_metricas.sort_values(['ano_referencia', 'mes_referencia'])
            
            # Calcular variações percentuais
            for col in ['total_registros', 'beneficiarios_unicos', 'valor_total', 'registros_problema', 'cpfs_ajuste']:
                if col in df_metricas.columns:
                    # CORREÇÃO: Substituir NaN por 0
                    variacoes = df_metricas[col].pct_change() * 100
                    variacoes = variacoes.fillna(0)  # Substituir NaN por 0
                    df_metricas[f'variacao_{col}'] = variacoes.round(2)
        
        st.dataframe(df_metricas, use_container_width=True)
        
        # Exportar dados
        st.subheader("Exportar Dados")
        
        csv = df_metricas.to_csv(index=False, encoding='utf-8-sig')
        b64 = base64.b64encode(csv.encode('utf-8-sig')).decode()
        href = f'<a href="data:file/csv;base64,{b64}" download="dados_comparativos_{periodo}.csv">📥 Baixar Dados Comparativos</a>'
        st.markdown(href, unsafe_allow_html=True)
    
    elif menu == "Gestão de Dados":
        st.header("🗃️ Gestão de Dados")
        
        tab1, tab2, tab3 = st.tabs(["Dados Importados", "Limpar Dados", "Backup/Restauração"])
        
        with tab1:
            st.subheader("Dados Importados")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**Pagamentos Importados**")
                df_pagamentos = carregar_pagamentos_db(conn)
                if not df_pagamentos.empty:
                    st.dataframe(df_pagamentos[['mes_referencia', 'ano_referencia', 'nome_arquivo', 'data_importacao']], use_container_width=True)
                else:
                    st.info("Nenhum dado de pagamentos importado.")
            
            with col2:
                st.write("**Inscrições/Contas Importadas**")
                df_inscricoes = carregar_inscricoes_db(conn)
                if not df_inscricoes.empty:
                    st.dataframe(df_inscricoes[['mes_referencia', 'ano_referencia', 'nome_arquivo', 'data_importacao']], use_container_width=True)
                else:
                    st.info("Nenhum dado de inscrições importado.")
        
        with tab2:
            st.subheader("Limpar Dados")
            st.warning("🚨 Esta ação é irreversível!")
            
            tipo_dados = st.selectbox("Tipo de dados para limpar", ["Pagamentos", "Inscrições", "Todos os dados"])
            
            if st.button("🗑️ Limpar Dados Selecionados", type="secondary"):
                try:
                    if tipo_dados == "Pagamentos" or tipo_dados == "Todos os dados":
                        conn.execute("DELETE FROM pagamentos")
                    
                    if tipo_dados == "Inscrições" or tipo_dados == "Todos os dados":
                        conn.execute("DELETE FROM inscricoes")
                    
                    if tipo_dados == "Todos os dados":
                        conn.execute("DELETE FROM metricas_mensais")
                    
                    conn.commit()
                    st.success("✅ Dados limpos com sucesso!")
                    st.rerun()
                
                except Exception as e:
                    st.error(f"❌ Erro ao limpar dados: {str(e)}")
        
        with tab3:
            st.subheader("Backup e Restauração")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**Backup do Banco de Dados**")
                if st.button("💾 Criar Backup"):
                    try:
                        # Copiar arquivo do banco de dados
                        import shutil
                        backup_name = f"backup_pot_{data_hora_arquivo_brasilia()}.db"
                        shutil.copy2('pot_smdet.db', backup_name)
                        st.success(f"✅ Backup criado: {backup_name}")
                    except Exception as e:
                        st.error(f"❌ Erro ao criar backup: {str(e)}")
            
            with col2:
                st.write("**Restaurar Banco de Dados**")
                arquivo_backup = st.file_uploader("Selecionar arquivo de backup", type=['db'])
                
                if arquivo_backup and st.button("🔄 Restaurar Backup"):
                    try:
                        with open('pot_smdet.db', 'wb') as f:
                            f.write(arquivo_backup.getvalue())
                        st.success("✅ Backup restaurado com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erro ao restaurar backup: {str(e)}")
    
    # Rodapé
    st.markdown("---")
    st.markdown(f"👤 Usuário: {usuario} | 🕐 Último acesso: {data_hora_atual_brasilia()}")
    st.markdown("**Sistema POT - Secretaria Municipal do Desenvolvimento Econômico e Trabalho**")

if __name__ == "__main__":
    main()
