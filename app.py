# app.py - VERSÃO CORRIGIDA E OTIMIZADA
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
import tempfile
import sys

# Configuração da página
st.set_page_config(
    page_title="Sistema POT - SMDET",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========== SISTEMA DE BANCO DE DADOS MELHORADO ==========
def init_database():
    """Inicializa o banco de dados SQLite com melhor persistência"""
    try:
        # Usar caminho absoluto para garantir persistência
        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        
        db_path = os.path.join(base_path, 'pot_smdet.db')
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        
        # Tabelas principais
        conn.execute('''
            CREATE TABLE IF NOT EXISTS pagamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mes_referencia TEXT NOT NULL,
                ano_referencia INTEGER NOT NULL,
                data_importacao TEXT NOT NULL,
                nome_arquivo TEXT NOT NULL,
                dados_json TEXT NOT NULL,
                metadados_json TEXT NOT NULL,
                hash_arquivo TEXT UNIQUE,
                importado_por TEXT NOT NULL
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS inscricoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mes_referencia TEXT NOT NULL,
                ano_referencia INTEGER NOT NULL,
                data_importacao TEXT NOT NULL,
                nome_arquivo TEXT NOT NULL,
                dados_json TEXT NOT NULL,
                metadados_json TEXT NOT NULL,
                hash_arquivo TEXT UNIQUE,
                importado_por TEXT NOT NULL
            )
        ''')
        
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
        
        # NOVA TABELA: Logs administrativos
        conn.execute('''
            CREATE TABLE IF NOT EXISTS logs_admin (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_hora TEXT NOT NULL,
                usuario_email TEXT NOT NULL,
                acao TEXT NOT NULL,
                tipo_registro TEXT,
                registro_id INTEGER,
                detalhes TEXT
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                nome TEXT NOT NULL,
                tipo TEXT NOT NULL DEFAULT 'usuario',
                data_criacao TEXT NOT NULL,
                ativo INTEGER DEFAULT 1,
                ultimo_login TEXT
            )
        ''')
        
        # Verificar e adicionar colunas faltantes
        cursor = conn.execute("PRAGMA table_info(pagamentos)")
        colunas_pagamentos = [col[1] for col in cursor.fetchall()]
        
        if 'importado_por' not in colunas_pagamentos:
            try:
                conn.execute("ALTER TABLE pagamentos ADD COLUMN importado_por TEXT NOT NULL DEFAULT 'sistema'")
            except:
                pass
        
        # Verificar colunas em inscricoes
        cursor = conn.execute("PRAGMA table_info(inscricoes)")
        colunas_inscricoes = [col[1] for col in cursor.fetchall()]
        
        if 'importado_por' not in colunas_inscricoes:
            try:
                conn.execute("ALTER TABLE inscricoes ADD COLUMN importado_por TEXT NOT NULL DEFAULT 'sistema'")
            except:
                pass
        
        # Inserir administrador padrão se não existir
        cursor = conn.execute("SELECT * FROM usuarios WHERE email = 'admin@prefeitura.sp.gov.br'")
        if cursor.fetchone() is None:
            conn.execute('''
                INSERT INTO usuarios (email, nome, tipo, data_criacao, ativo)
                VALUES (?, ?, ?, ?, ?)
            ''', ('admin@prefeitura.sp.gov.br', 'Administrador', 'admin', data_hora_atual_brasilia(), 1))
        
        conn.commit()
        return conn
        
    except Exception as e:
        st.error(f"Erro crítico ao inicializar banco de dados: {str(e)}")
        return None

# ========== FUNÇÕES DE UTILIDADE ==========
def agora_brasilia():
    """Retorna a data e hora atual no fuso horário de Brasília"""
    fuso_brasilia = timezone(timedelta(hours=-3))
    return datetime.now(timezone.utc).astimezone(fuso_brasilia)

def data_hora_atual_brasilia():
    """Retorna a data e hora atual no formato dd/mm/aaaa às HH:MM"""
    return agora_brasilia().strftime("%d/%m/%Y às %H:%M")

def data_hora_arquivo_brasilia():
    """Retorna a data e hora atual no formato para nome de arquivo"""
    return agora_brasilia().strftime("%Y%m%d_%H%M")

def calcular_hash_arquivo(file_bytes):
    """Calcula hash do conteúdo do arquivo para evitar duplicatas"""
    return hashlib.sha256(file_bytes).hexdigest()

def hash_senha(senha):
    """Gera hash SHA-256 da senha"""
    return hashlib.sha256(senha.encode()).hexdigest()

SENHA_AUTORIZADA_HASH = hash_senha("Smdetpot2025")
SENHA_ADMIN_HASH = hash_senha("AdminSmdet2025")

# ========== SISTEMA DE AUTENTICAÇÃO MELHORADO ==========
def verificar_usuario_autorizado(conn, email):
    """Verifica se o usuário está autorizado (case-insensitive)"""
    try:
        email_lower = email.lower()
        cursor = conn.execute("SELECT * FROM usuarios WHERE LOWER(email) = ? AND ativo = 1", (email_lower,))
        return cursor.fetchone() is not None
    except Exception as e:
        st.error(f"Erro ao verificar usuário: {str(e)}")
        return False

def obter_tipo_usuario(conn, email):
    """Obtém o tipo do usuário (case-insensitive)"""
    try:
        email_lower = email.lower()
        cursor = conn.execute("SELECT tipo FROM usuarios WHERE LOWER(email) = ? AND ativo = 1", (email_lower,))
        resultado = cursor.fetchone()
        return resultado[0] if resultado else None
    except Exception as e:
        st.error(f"Erro ao obter tipo de usuário: {str(e)}")
        return None

def atualizar_ultimo_login(conn, email):
    """Atualiza a data do último login do usuário"""
    try:
        email_lower = email.lower()
        conn.execute("UPDATE usuarios SET ultimo_login = ? WHERE LOWER(email) = ?", 
                    (data_hora_atual_brasilia(), email_lower))
        conn.commit()
    except Exception as e:
        st.error(f"Erro ao atualizar último login: {str(e)}")

def registrar_log_admin(conn, usuario_email, acao, tipo_registro=None, registro_id=None, detalhes=None):
    """Registra ação administrativa no log"""
    try:
        conn.execute('''
            INSERT INTO logs_admin (data_hora, usuario_email, acao, tipo_registro, registro_id, detalhes)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (data_hora_atual_brasilia(), usuario_email.lower(), acao, tipo_registro, registro_id, detalhes))
        conn.commit()
    except Exception as e:
        st.error(f"Erro ao registrar log: {str(e)}")

def autenticar(conn):
    """Sistema de autenticação melhorado"""
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
    if 'email_autorizado' not in st.session_state:
        st.session_state.email_autorizado = None
    if 'tipo_usuario' not in st.session_state:
        st.session_state.tipo_usuario = None
    
    # Verificar se está bloqueado
    if st.session_state.bloqueado:
        st.sidebar.error("🚫 Sistema temporariamente bloqueado. Tente novamente em 5 minutos.")
        return None, None
    
    # Se já está autenticado, mostrar informações
    if st.session_state.autenticado and st.session_state.email_autorizado:
        tipo_usuario = "👑 Administrador" if st.session_state.tipo_usuario == 'admin' else "👤 Usuário"
        st.sidebar.success(f"✅ Acesso autorizado")
        st.sidebar.info(f"{tipo_usuario}: {st.session_state.email_autorizado}")
        
        if st.sidebar.button("🚪 Sair", key="sair_sistema"):
            for key in ['autenticado', 'email_autorizado', 'tipo_usuario', 'tentativas_login', 
                       'uploaded_data', 'processed_metrics']:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()
        
        return st.session_state.email_autorizado, st.session_state.tipo_usuario
    
    # Formulário de login
    with st.sidebar.form("login_form"):
        st.subheader("🔐 Acesso Restrito")
        email = st.text_input("Email institucional", placeholder="seu.email@prefeitura.sp.gov.br", key="email_login")
        senha = st.text_input("Senha", type="password", placeholder="Digite sua senha", key="senha_login")
        submit = st.form_submit_button("Entrar")
        
        if submit:
            email_lower = email.lower().strip() if email else ""
            
            if not email_lower or not senha:
                st.sidebar.error("⚠️ Preencha email e senha")
                st.session_state.tentativas_login += 1
            elif not email_lower.endswith('@prefeitura.sp.gov.br'):
                st.sidebar.error("🚫 Acesso restrito aos servidores da Prefeitura de São Paulo")
                st.session_state.tentativas_login += 1
            elif not verificar_usuario_autorizado(conn, email_lower):
                st.sidebar.error("🚫 Usuário não autorizado. Contate o administrador.")
                st.session_state.tentativas_login += 1
            else:
                senha_hash = hash_senha(senha)
                
                # Verificar se é admin
                if email_lower == 'admin@prefeitura.sp.gov.br' and senha_hash == SENHA_ADMIN_HASH:
                    st.session_state.autenticado = True
                    st.session_state.email_autorizado = email_lower
                    st.session_state.tipo_usuario = 'admin'
                    st.session_state.tentativas_login = 0
                    atualizar_ultimo_login(conn, email_lower)
                    st.sidebar.success("✅ Login de administrador realizado com sucesso!")
                    st.rerun()
                elif senha_hash == SENHA_AUTORIZADA_HASH:
                    st.session_state.autenticado = True
                    st.session_state.email_autorizado = email_lower
                    st.session_state.tipo_usuario = obter_tipo_usuario(conn, email_lower)
                    st.session_state.tentativas_login = 0
                    atualizar_ultimo_login(conn, email_lower)
                    st.sidebar.success("✅ Login realizado com sucesso!")
                    st.rerun()
                else:
                    st.sidebar.error("❌ Senha incorreta")
                    st.session_state.tentativas_login += 1
            
            # Verificar se excedeu tentativas
            if st.session_state.tentativas_login >= 3:
                st.session_state.bloqueado = True
                st.sidebar.error("🚫 Muitas tentativas falhas. Sistema bloqueado por 5 minutos.")
    
    return None, None

# ========== FUNÇÕES DE PROCESSAMENTO DE ARQUIVOS ==========
def extrair_mes_ano_arquivo(nome_arquivo):
    """Extrai mês e ano do nome do arquivo de forma robusta"""
    if not nome_arquivo:
        return None, None
    
    nome_upper = nome_arquivo.upper()
    
    # Mapeamento de meses
    meses_map = {
        'JAN': 'Janeiro', 'JANEIRO': 'Janeiro', '01': 'Janeiro',
        'FEV': 'Fevereiro', 'FEVEREIRO': 'Fevereiro', '02': 'Fevereiro',
        'MAR': 'Março', 'MARCO': 'Março', 'MARÇO': 'Março', '03': 'Março',
        'ABR': 'Abril', 'ABRIL': 'Abril', '04': 'Abril',
        'MAI': 'Maio', 'MAIO': 'Maio', '05': 'Maio',
        'JUN': 'Junho', 'JUNHO': 'Junho', '06': 'Junho',
        'JUL': 'Julho', 'JULHO': 'Julho', '07': 'Julho',
        'AGO': 'Agosto', 'AGOSTO': 'Agosto', '08': 'Agosto',
        'SET': 'Setembro', 'SETEMBRO': 'Setembro', '09': 'Setembro',
        'OUT': 'Outubro', 'OUTUBRO': 'Outubro', '10': 'Outubro',
        'NOV': 'Novembro', 'NOVEMBRO': 'Novembro', '11': 'Novembro',
        'DEZ': 'Dezembro', 'DEZEMBRO': 'Dezembro', '12': 'Dezembro'
    }
    
    # Procurar primeiro por padrão MES-ANO ou ANO-MES
    padroes = [
        (r'(JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)[^\d]*(\d{4})', 1, 2),
        (r'(\d{4})[^\d]*(JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)', 2, 1),
        (r'(\d{1,2})[\.\-/](\d{4})', 1, 2),  # MM/AAAA
        (r'(\d{4})[\.\-/](\d{1,2})', 2, 1),  # AAAA/MM
    ]
    
    for padrao, idx_mes, idx_ano in padroes:
        match = re.search(padrao, nome_upper, re.IGNORECASE)
        if match:
            mes_str = match.group(idx_mes).upper()
            ano_str = match.group(idx_ano)
            
            # Converter mês
            if mes_str.isdigit():
                mes_num = int(mes_str)
                meses_numeros = {
                    1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
                    5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
                    9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
                }
                mes = meses_numeros.get(mes_num)
            else:
                for key, value in meses_map.items():
                    if key in mes_str:
                        mes = value
                        break
                else:
                    mes = None
            
            if mes and ano_str.isdigit():
                return mes, int(ano_str)
    
    # Tentar extrair apenas o ano
    ano_match = re.search(r'(\d{4})', nome_upper)
    if ano_match:
        ano = int(ano_match.group(1))
        # Tentar identificar mês pelo nome
        for key, value in meses_map.items():
            if key in nome_upper and not key.isdigit():
                return value, ano
        
        # Se não encontrou mês, usar o mês atual
        mes_atual_num = agora_brasilia().month
        meses_numeros = {
            1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
            5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
            9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
        }
        return meses_numeros.get(mes_atual_num, 'Janeiro'), ano
    
    return None, None

def processar_arquivo(uploaded_file, tipo_arquivo='pagamentos'):
    """Processa arquivo de forma robusta"""
    try:
        if uploaded_file is None:
            return None
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_path = tmp_file.name
        
        try:
            if uploaded_file.name.endswith('.xlsx'):
                try:
                    df = pd.read_excel(tmp_path, engine='openpyxl')
                except:
                    df = pd.read_excel(tmp_path, engine='xlrd')
            elif uploaded_file.name.endswith('.csv'):
                try:
                    df = pd.read_csv(tmp_path, encoding='utf-8', sep=None, engine='python')
                except:
                    df = pd.read_csv(tmp_path, encoding='latin-1', sep=None, engine='python')
            else:
                st.error(f"Formato não suportado: {uploaded_file.name}")
                os.unlink(tmp_path)
                return None
            
            os.unlink(tmp_path)
            
            if df.empty:
                st.warning(f"Arquivo {uploaded_file.name} está vazio")
                return None
            
            return df
            
        except Exception as e:
            st.error(f"Erro ao processar {uploaded_file.name}: {str(e)}")
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            return None
            
    except Exception as e:
        st.error(f"Erro crítico: {str(e)}")
        return None

def obter_coluna_conta(df):
    """Identifica a coluna que contém o número da conta"""
    colunas_conta = ['Num Cartao', 'Num_Cartao', 'Conta', 'Número da Conta', 
                    'Numero_Conta', 'Número do Cartão', 'Nº Cartão', 'Cartão']
    for coluna in colunas_conta:
        if coluna in df.columns:
            return coluna
    return None

def obter_coluna_nome(df):
    """Identifica a coluna que contém o nome do beneficiário"""
    colunas_nome = ['Beneficiario', 'Beneficiário', 'Nome', 'Nome Completo', 
                   'Nome do Beneficiário', 'Nome_Beneficiario']
    for coluna in colunas_nome:
        if coluna in df.columns:
            return coluna
    return None

def obter_coluna_valor(df):
    """Identifica a coluna que contém o valor pago"""
    colunas_valor = ['Valor Pagto', 'Valor_Pagto', 'Valor Pgto', 'Valor_Pgto', 
                    'Valor', 'Valor_Pago', 'Valor Pagamento']
    for coluna in colunas_valor:
        if coluna in df.columns:
            return coluna
    return None

def remover_linha_totais(df):
    """Remove linha de totais da planilha"""
    if df.empty or len(df) <= 1:
        return df
    
    df_limpo = df.copy()
    ultima_linha = df_limpo.iloc[-1]
    
    # Verificar se última linha contém palavras indicativas de totais
    colunas_texto = [col for col in df_limpo.columns if df_limpo[col].dtype == 'object']
    for coluna in colunas_texto[:3]:
        if pd.notna(ultima_linha[coluna]):
            valor = str(ultima_linha[coluna]).upper()
            if any(palavra in valor for palavra in ['TOTAL', 'SOMA', 'GERAL', 'TOTAL GERAL', 'TOTAL:']):
                df_limpo = df_limpo.iloc[:-1].copy()
                break
    
    return df_limpo

def filtrar_pagamentos_validos(df):
    """Filtra apenas os registros que possuem número da conta"""
    coluna_conta = obter_coluna_conta(df)
    
    if not coluna_conta:
        return df
    
    df_filtrado = df[df[coluna_conta].notna() & (df[coluna_conta].astype(str).str.strip() != '')].copy()
    
    # Remover linhas que contenham palavras de totais
    palavras_totais = ['TOTAL', 'SOMA', 'GERAL']
    for palavra in palavras_totais:
        mask = df_filtrado[coluna_conta].astype(str).str.upper().str.contains(palavra, na=False)
        df_filtrado = df_filtrado[~mask]
    
    return df_filtrado

def processar_cpf(cpf):
    """Processa CPF, mantendo apenas números"""
    if pd.isna(cpf) or cpf in ['', 'NaN', 'None', 'nan', 'NULL']:
        return ''
    
    cpf_str = str(cpf).strip()
    cpf_limpo = re.sub(r'[^\d]', '', cpf_str)
    
    if cpf_limpo == '':
        return ''
    
    if len(cpf_limpo) < 11:
        cpf_limpo = cpf_limpo.zfill(11)
    
    return cpf_limpo

def padronizar_documentos(df):
    """Padroniza RGs e CPFs"""
    df_processed = df.copy()
    
    if 'CPF' in df_processed.columns:
        df_processed['CPF'] = df_processed['CPF'].apply(lambda x: processar_cpf(x))
    
    if 'RG' in df_processed.columns:
        df_processed['RG'] = df_processed['RG'].apply(
            lambda x: re.sub(r'[^a-zA-Z0-9/]', '', str(x)) if pd.notna(x) and str(x).strip() != '' else ''
        )
    
    return df_processed

def processar_colunas_data(df):
    """Converte colunas de data"""
    df_processed = df.copy()
    
    colunas_data = ['Data', 'Data Pagto', 'Data_Pagto', 'DataPagto', 'Data Pagamento', 'Data_Abertura']
    
    for coluna in colunas_data:
        if coluna in df_processed.columns:
            try:
                if df_processed[coluna].dtype in ['int64', 'float64']:
                    df_processed[coluna] = pd.to_datetime(df_processed[coluna], unit='D', origin='1899-12-30', errors='coerce')
                else:
                    df_processed[coluna] = pd.to_datetime(df_processed[coluna], errors='coerce')
                
                df_processed[coluna] = df_processed[coluna].dt.strftime('%d/%m/%Y')
            except:
                pass
    
    return df_processed

def processar_colunas_valor(df):
    """Processa colunas de valor para formato brasileiro"""
    df_processed = df.copy()
    
    coluna_valor = obter_coluna_valor(df)
    
    if coluna_valor and coluna_valor in df_processed.columns:
        try:
            valores_limpos = []
            for valor in df_processed[coluna_valor]:
                if pd.isna(valor):
                    valores_limpos.append(0.0)
                    continue
                
                if isinstance(valor, (int, float)):
                    valores_limpos.append(float(valor))
                    continue
                
                valor_str = str(valor).strip()
                if valor_str == '':
                    valores_limpos.append(0.0)
                    continue
                
                # Remover R$, pontos e substituir vírgula por ponto
                valor_limpo_str = re.sub(r'[^\d,.]', '', valor_str)
                valor_limpo_str = valor_limpo_str.replace(',', '.')
                
                # Lidar com múltiplos pontos (formato brasileiro)
                if valor_limpo_str.count('.') > 1:
                    partes = valor_limpo_str.split('.')
                    valor_limpo_str = ''.join(partes[:-1]) + '.' + partes[-1]
                
                try:
                    valor_float = float(valor_limpo_str) if valor_limpo_str else 0.0
                    valores_limpos.append(valor_float)
                except:
                    valores_limpos.append(0.0)
            
            df_processed['Valor_Limpo'] = valores_limpos
        except:
            df_processed['Valor_Limpo'] = 0.0
    else:
        df_processed['Valor_Limpo'] = 0.0
    
    return df_processed

# ========== FUNÇÕES DE SALVAMENTO NO BANCO ==========
def salvar_pagamentos_db(conn, mes_ref, ano_ref, nome_arquivo, file_bytes, dados_df, metadados, importado_por):
    """Salva dados de pagamentos no banco"""
    try:
        file_hash = calcular_hash_arquivo(file_bytes)
        
        # Verificar duplicidade por hash
        cursor = conn.execute("SELECT id FROM pagamentos WHERE hash_arquivo = ?", (file_hash,))
        existe = cursor.fetchone()
        
        dados_json = dados_df.to_json(orient='records', date_format='iso', force_ascii=False)
        metadados_json = json.dumps(metadados, ensure_ascii=False)
        
        if existe:
            conn.execute('''
                UPDATE pagamentos SET data_importacao = ?, dados_json = ?, metadados_json = ?,
                          mes_referencia = ?, ano_referencia = ?, nome_arquivo = ?, importado_por = ?
                WHERE hash_arquivo = ?
            ''', (data_hora_atual_brasilia(), dados_json, metadados_json, 
                  mes_ref, ano_ref, nome_arquivo, importado_por.lower(), file_hash))
            st.sidebar.info("📝 Registro atualizado")
        else:
            conn.execute('''
                INSERT INTO pagamentos (mes_referencia, ano_referencia, data_importacao, 
                          nome_arquivo, dados_json, metadados_json, hash_arquivo, importado_por)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (mes_ref, ano_ref, data_hora_atual_brasilia(), nome_arquivo, 
                  dados_json, metadados_json, file_hash, importado_por.lower()))
            st.sidebar.success("✅ Novo registro salvo")
        
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar pagamentos: {str(e)}")
        return False

def salvar_inscricoes_db(conn, mes_ref, ano_ref, nome_arquivo, file_bytes, dados_df, metadados, importado_por):
    """Salva dados de inscrições no banco"""
    try:
        file_hash = calcular_hash_arquivo(file_bytes)
        
        cursor = conn.execute("SELECT id FROM inscricoes WHERE hash_arquivo = ?", (file_hash,))
        existe = cursor.fetchone()
        
        dados_json = dados_df.to_json(orient='records', date_format='iso', force_ascii=False)
        metadados_json = json.dumps(metadados, ensure_ascii=False)
        
        if existe:
            conn.execute('''
                UPDATE inscricoes SET data_importacao = ?, dados_json = ?, metadados_json = ?,
                         mes_referencia = ?, ano_referencia = ?, nome_arquivo = ?, importado_por = ?
                WHERE hash_arquivo = ?
            ''', (data_hora_atual_brasilia(), dados_json, metadados_json, 
                  mes_ref, ano_ref, nome_arquivo, importado_por.lower(), file_hash))
            st.sidebar.info("📝 Registro atualizado")
        else:
            conn.execute('''
                INSERT INTO inscricoes (mes_referencia, ano_referencia, data_importacao, 
                          nome_arquivo, dados_json, metadados_json, hash_arquivo, importado_por)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (mes_ref, ano_ref, data_hora_atual_brasilia(), nome_arquivo, 
                  dados_json, metadados_json, file_hash, importado_por.lower()))
            st.sidebar.success("✅ Novo registro salvo")
        
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar inscrições: {str(e)}")
        return False

# ========== FUNÇÕES DE ANÁLISE ==========
def identificar_cpfs_problematicos(df):
    """Identifica CPFs com problemas"""
    problemas = {
        'detalhes_problemas': pd.DataFrame(),
        'detalhes_inconsistencias': pd.DataFrame(),
        'total_problemas': 0,
        'total_inconsistentes': 0
    }
    
    if 'CPF' not in df.columns or df.empty:
        return problemas
    
    df_analise = df.copy()
    
    # Problemas de formatação
    detalhes_problemas = []
    for idx, row in df_analise.iterrows():
        cpf = str(row['CPF']) if pd.notna(row['CPF']) and str(row['CPF']).strip() != '' else ''
        problemas_lista = []
        
        if cpf == '':
            problemas_lista.append('CPF vazio')
        elif not cpf.isdigit():
            problemas_lista.append('Caracteres inválidos')
        elif len(cpf) != 11:
            problemas_lista.append(f'Tamanho incorreto ({len(cpf)} dígitos)')
        
        if problemas_lista:
            info = {
                'Linha_Planilha': idx + 2,
                'CPF_Original': row.get('CPF', ''),
                'CPF_Processado': cpf,
                'Problemas': ', '.join(problemas_lista)
            }
            
            coluna_nome = obter_coluna_nome(df_analise)
            if coluna_nome and coluna_nome in row:
                info['Nome'] = row[coluna_nome]
            
            coluna_conta = obter_coluna_conta(df_analise)
            if coluna_conta and coluna_conta in row:
                info['Conta'] = row[coluna_conta]
            
            detalhes_problemas.append(info)
    
    if detalhes_problemas:
        problemas['detalhes_problemas'] = pd.DataFrame(detalhes_problemas)
        problemas['total_problemas'] = len(detalhes_problemas)
    
    # Inconsistências (CPFs duplicados com diferentes dados)
    cpfs_duplicados = df_analise[df_analise.duplicated(['CPF'], keep=False)]
    
    if not cpfs_duplicados.empty:
        detalhes_inconsistencias = []
        
        for cpf, grupo in cpfs_duplicados.groupby('CPF'):
            if len(grupo) > 1:
                coluna_nome = obter_coluna_nome(grupo)
                coluna_conta = obter_coluna_conta(grupo)
                
                tem_nomes_diferentes = False
                tem_contas_diferentes = False
                
                if coluna_nome and coluna_nome in grupo.columns:
                    nomes_unicos = grupo[coluna_nome].dropna().unique()
                    if len(nomes_unicos) > 1:
                        tem_nomes_diferentes = True
                
                if coluna_conta and coluna_conta in grupo.columns:
                    contas_unicas = grupo[coluna_conta].dropna().unique()
                    if len(contas_unicas) > 1:
                        tem_contas_diferentes = True
                
                if tem_nomes_diferentes or tem_contas_diferentes:
                    for idx, registro in grupo.iterrows():
                        info = {
                            'CPF': cpf,
                            'Linha_Planilha': idx + 2,
                            'Ocorrencia': f"{list(grupo.index).index(idx) + 1}/{len(grupo)}"
                        }
                        
                        if coluna_nome:
                            info['Nome'] = registro[coluna_nome]
                        if coluna_conta:
                            info['Conta'] = registro[coluna_conta]
                        
                        problemas_lista = ['CPF DUPLICADO']
                        if tem_nomes_diferentes:
                            problemas_lista.append('NOMES DIFERENTES')
                        if tem_contas_diferentes:
                            problemas_lista.append('CONTAS DIFERENTES')
                        
                        info['Problemas'] = ', '.join(problemas_lista)
                        detalhes_inconsistencias.append(info)
        
        if detalhes_inconsistencias:
            problemas['detalhes_inconsistencias'] = pd.DataFrame(detalhes_inconsistencias)
            problemas['total_inconsistentes'] = len(set([d['CPF'] for d in detalhes_inconsistencias]))
    
    return problemas

def detectar_pagamentos_duplicados(df):
    """Detecta pagamentos duplicados por número de conta"""
    duplicidades = {
        'detalhes': pd.DataFrame(),
        'resumo': pd.DataFrame(),
        'total_contas': 0,
        'total_pagamentos': 0,
        'valor_total': 0
    }
    
    df = filtrar_pagamentos_validos(df)
    
    if df.empty:
        return duplicidades
    
    coluna_conta = obter_coluna_conta(df)
    
    if not coluna_conta:
        return duplicidades
    
    contagem_por_conta = df[coluna_conta].value_counts()
    contas_duplicadas = contagem_por_conta[contagem_por_conta > 1].index.tolist()
    
    if not contas_duplicadas:
        return duplicidades
    
    df_duplicados = df[df[coluna_conta].isin(contas_duplicadas)].copy()
    
    # Adicionar número de ocorrência
    df_duplicados['Ocorrencia'] = df_duplicados.groupby(coluna_conta).cumcount() + 1
    df_duplicados['Total_Ocorrencias'] = df_duplicados.groupby(coluna_conta)[coluna_conta].transform('count')
    
    # Preparar colunas para exibição
    colunas_exibicao = [coluna_conta, 'Ocorrencia', 'Total_Ocorrencias']
    
    coluna_nome = obter_coluna_nome(df_duplicados)
    if coluna_nome:
        colunas_exibicao.append(coluna_nome)
    
    if 'CPF' in df_duplicados.columns:
        colunas_exibicao.append('CPF')
    
    if 'Valor_Limpo' in df_duplicados.columns:
        colunas_exibicao.append('Valor_Limpo')
        duplicidades['valor_total'] = df_duplicados['Valor_Limpo'].sum()
    
    duplicidades['detalhes'] = df_duplicados[colunas_exibicao]
    duplicidades['total_contas'] = len(contas_duplicadas)
    duplicidades['total_pagamentos'] = len(df_duplicados)
    
    # Resumo por conta
    resumo = []
    for conta in contas_duplicadas:
        registros_conta = df_duplicados[df_duplicados[coluna_conta] == conta]
        info = {
            'Conta': conta,
            'Total_Pagamentos': len(registros_conta),
            'Valor_Total': registros_conta['Valor_Limpo'].sum() if 'Valor_Limpo' in registros_conta.columns else 0
        }
        
        if coluna_nome:
            info['Nome'] = registros_conta.iloc[0][coluna_nome] if not registros_conta.empty else ''
        
        resumo.append(info)
    
    duplicidades['resumo'] = pd.DataFrame(resumo)
    
    return duplicidades

def analisar_ausencia_dados(dados):
    """Analisa ausência de dados críticos"""
    analise = {
        'registros_criticos': pd.DataFrame(),
        'total_criticos': 0
    }
    
    if 'pagamentos' in dados and not dados['pagamentos'].empty:
        df = dados['pagamentos']
        
        registros_criticos = []
        
        # Verificar conta ausente
        coluna_conta = obter_coluna_conta(df)
        if coluna_conta:
            mask_conta_ausente = df[coluna_conta].isna() | (df[coluna_conta].astype(str).str.strip() == '')
            mask_nao_totais = ~df[coluna_conta].astype(str).str.upper().str.contains('TOTAL|SOMA|GERAL', na=False)
            contas_ausentes = df[mask_conta_ausente & mask_nao_totais]
            
            for idx, row in contas_ausentes.iterrows():
                info = {
                    'Linha_Planilha': idx + 2,
                    'Problema': 'Conta ausente'
                }
                
                coluna_nome = obter_coluna_nome(df)
                if coluna_nome:
                    info['Nome'] = row[coluna_nome] if pd.notna(row[coluna_nome]) else ''
                
                if 'CPF' in df.columns:
                    info['CPF'] = row['CPF'] if pd.notna(row['CPF']) else ''
                
                registros_criticos.append(info)
        
        # Verificar valor ausente
        if 'Valor_Limpo' in df.columns:
            mask_valor_ausente = df['Valor_Limpo'].isna() | (df['Valor_Limpo'] == 0)
            valores_ausentes = df[mask_valor_ausente]
            
            for idx, row in valores_ausentes.iterrows():
                # Verificar se já foi identificado por outro problema
                ja_existe = any(r['Linha_Planilha'] == idx + 2 for r in registros_criticos)
                
                if not ja_existe:
                    info = {
                        'Linha_Planilha': idx + 2,
                        'Problema': 'Valor ausente ou zero'
                    }
                    
                    coluna_nome = obter_coluna_nome(df)
                    if coluna_nome:
                        info['Nome'] = row[coluna_nome] if pd.notna(row[coluna_nome]) else ''
                    
                    if coluna_conta:
                        info['Conta'] = row[coluna_conta] if pd.notna(row[coluna_conta]) else ''
                    
                    registros_criticos.append(info)
        
        if registros_criticos:
            analise['registros_criticos'] = pd.DataFrame(registros_criticos)
            analise['total_criticos'] = len(registros_criticos)
    
    return analise

def processar_dados(dados, nomes_arquivos):
    """Processa dados para gerar métricas"""
    metrics = {
        'beneficiarios_unicos': 0,
        'total_pagamentos': 0,
        'contas_unicas': 0,
        'projetos_ativos': 0,
        'valor_total': 0,
        'pagamentos_duplicados': 0,
        'valor_total_duplicados': 0,
        'total_contas_abertas': 0,
        'beneficiarios_contas': 0,
        'problemas_cpf': {},
        'ausencia_dados': {},
        'duplicidades': {}
    }
    
    # Processar pagamentos
    if 'pagamentos' in dados and not dados['pagamentos'].empty:
        df = dados['pagamentos']
        
        coluna_nome = obter_coluna_nome(df)
        if coluna_nome:
            metrics['beneficiarios_unicos'] = df[coluna_nome].nunique()
        
        metrics['total_pagamentos'] = len(filtrar_pagamentos_validos(df))
        
        coluna_conta = obter_coluna_conta(df)
        if coluna_conta:
            metrics['contas_unicas'] = df[coluna_conta].nunique()
        
        if 'Projeto' in df.columns:
            metrics['projetos_ativos'] = df['Projeto'].nunique()
        
        if 'Valor_Limpo' in df.columns:
            metrics['valor_total'] = df['Valor_Limpo'].sum()
        
        # Análises
        metrics['problemas_cpf'] = identificar_cpfs_problematicos(df)
        metrics['duplicidades'] = detectar_pagamentos_duplicados(df)
        metrics['ausencia_dados'] = analisar_ausencia_dados(dados)
        
        metrics['pagamentos_duplicados'] = metrics['duplicidades']['total_contas']
        metrics['valor_total_duplicados'] = metrics['duplicidades']['valor_total']
    
    # Processar inscrições
    if 'contas' in dados and not dados['contas'].empty:
        df_contas = dados['contas']
        
        metrics['total_contas_abertas'] = len(df_contas)
        
        coluna_nome = obter_coluna_nome(df_contas)
        if coluna_nome:
            metrics['beneficiarios_contas'] = df_contas[coluna_nome].nunique()
        
        if 'Projeto' in df_contas.columns:
            metrics['projetos_ativos'] = max(metrics.get('projetos_ativos', 0), df_contas['Projeto'].nunique())
    
    return metrics

def salvar_metricas_db(conn, tipo, mes_ref, ano_ref, metrics):
    """Salva métricas no banco com verificação de duplicidade"""
    try:
        # Verificar se já existe
        cursor = conn.execute(
            "SELECT id FROM metricas_mensais WHERE tipo = ? AND mes_referencia = ? AND ano_referencia = ?",
            (tipo, mes_ref, ano_ref)
        )
        existe = cursor.fetchone()
        
        if existe:
            conn.execute('''
                UPDATE metricas_mensais 
                SET total_registros = ?, beneficiarios_unicos = ?, contas_unicas = ?, 
                    valor_total = ?, pagamentos_duplicados = ?, valor_duplicados = ?, 
                    projetos_ativos = ?, registros_problema = ?, cpfs_ajuste = ?, data_calculo = ?
                WHERE tipo = ? AND mes_referencia = ? AND ano_referencia = ?
            ''', (
                metrics.get('total_pagamentos', 0) if tipo == 'pagamentos' else metrics.get('total_contas_abertas', 0),
                metrics.get('beneficiarios_unicos', 0) if tipo == 'pagamentos' else metrics.get('beneficiarios_contas', 0),
                metrics.get('contas_unicas', 0),
                metrics.get('valor_total', 0),
                metrics.get('pagamentos_duplicados', 0),
                metrics.get('valor_total_duplicados', 0),
                metrics.get('projetos_ativos', 0),
                metrics.get('ausencia_dados', {}).get('total_criticos', 0),
                metrics.get('problemas_cpf', {}).get('total_problemas', 0) + 
                metrics.get('problemas_cpf', {}).get('total_inconsistentes', 0),
                data_hora_atual_brasilia(),
                tipo, mes_ref, ano_ref
            ))
        else:
            conn.execute('''
                INSERT INTO metricas_mensais (tipo, mes_referencia, ano_referencia, total_registros, 
                            beneficiarios_unicos, contas_unicas, valor_total, pagamentos_duplicados, 
                            valor_duplicados, projetos_ativos, registros_problema, cpfs_ajuste, data_calculo)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (tipo, mes_ref, ano_ref, 
                  metrics.get('total_pagamentos', 0) if tipo == 'pagamentos' else metrics.get('total_contas_abertas', 0),
                  metrics.get('beneficiarios_unicos', 0) if tipo == 'pagamentos' else metrics.get('beneficiarios_contas', 0),
                  metrics.get('contas_unicas', 0),
                  metrics.get('valor_total', 0),
                  metrics.get('pagamentos_duplicados', 0),
                  metrics.get('valor_total_duplicados', 0),
                  metrics.get('projetos_ativos', 0),
                  metrics.get('ausencia_dados', {}).get('total_criticos', 0),
                  metrics.get('problemas_cpf', {}).get('total_problemas', 0) + 
                  metrics.get('problemas_cpf', {}).get('total_inconsistentes', 0),
                  data_hora_atual_brasilia()))
        
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar métricas: {str(e)}")
        return False

# ========== FUNÇÕES DE CARREGAMENTO DE DADOS ==========
def carregar_dados(conn, email_usuario):
    """Carrega dados do usuário"""
    st.sidebar.header("📤 Carregar Dados Mensais")
    
    # Upload de arquivos
    upload_pagamentos = st.sidebar.file_uploader(
        "Planilha de Pagamentos", 
        type=['xlsx', 'csv', 'xls'],
        key="pagamentos_upload"
    )
    
    upload_contas = st.sidebar.file_uploader(
        "Planilha de Inscrições/Contas", 
        type=['xlsx', 'csv', 'xls'],
        key="contas_upload"
    )
    
    # Detectar mês/ano dos nomes dos arquivos
    mes_ref_detectado = None
    ano_ref_detectado = None
    
    if upload_pagamentos:
        mes_ref, ano_ref = extrair_mes_ano_arquivo(upload_pagamentos.name)
        if mes_ref and ano_ref:
            mes_ref_detectado = mes_ref
            ano_ref_detectado = ano_ref
            st.sidebar.info(f"📅 Mês/ano detectado: {mes_ref}/{ano_ref}")
    
    if upload_contas and (not mes_ref_detectado or not ano_ref_detectado):
        mes_ref, ano_ref = extrair_mes_ano_arquivo(upload_contas.name)
        if mes_ref and ano_ref:
            mes_ref_detectado = mes_ref
            ano_ref_detectado = ano_ref
            st.sidebar.info(f"📅 Mês/ano detectado: {mes_ref}/{ano_ref}")
    
    # Seleção de mês e ano
    col1, col2 = st.sidebar.columns(2)
    with col1:
        meses = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
        mes_ref_padrao = mes_ref_detectado if mes_ref_detectado else 'Janeiro'
        mes_ref = st.selectbox("Mês de Referência", meses, 
                              index=meses.index(mes_ref_padrao) if mes_ref_padrao in meses else 0)
    with col2:
        ano_atual = datetime.now().year
        anos = list(range(ano_atual, ano_atual - 5, -1))
        ano_ref_padrao = ano_ref_detectado if ano_ref_detectado else ano_atual
        ano_ref = st.selectbox("Ano de Referência", anos, 
                              index=anos.index(ano_ref_padrao) if ano_ref_padrao in anos else 0)
    
    st.sidebar.markdown("---")
    
    dados = {}
    nomes_arquivos = {}
    dados_processados = False
    
    # Processar pagamentos
    if upload_pagamentos:
        df = processar_arquivo(upload_pagamentos, 'pagamentos')
        if df is not None:
            nomes_arquivos['pagamentos'] = upload_pagamentos.name
            
            # Processar dados
            df = remover_linha_totais(df)
            df = processar_colunas_valor(df)
            df = processar_colunas_data(df)
            df = padronizar_documentos(df)
            
            dados['pagamentos'] = df
            
            # Salvar no banco
            metadados = {
                'total_registros': len(df),
                'colunas': df.columns.tolist(),
                'tipo': 'pagamentos'
            }
            
            if salvar_pagamentos_db(conn, mes_ref, ano_ref, upload_pagamentos.name, 
                                   upload_pagamentos.getvalue(), df, metadados, email_usuario):
                dados_processados = True
            
            df_validos = filtrar_pagamentos_validos(df)
            st.sidebar.success(f"✅ Pagamentos: {len(df_validos)} válidos")
    
    # Processar inscrições
    if upload_contas:
        df = processar_arquivo(upload_contas, 'inscrições')
        if df is not None:
            nomes_arquivos['contas'] = upload_contas.name
            
            df = processar_colunas_data(df)
            df = padronizar_documentos(df)
            
            dados['contas'] = df
            
            # Salvar no banco
            metadados = {
                'total_registros': len(df),
                'colunas': df.columns.tolist(),
                'tipo': 'inscricoes'
            }
            
            if salvar_inscricoes_db(conn, mes_ref, ano_ref, upload_contas.name, 
                                   upload_contas.getvalue(), df, metadados, email_usuario):
                dados_processados = True
            
            st.sidebar.success(f"✅ Inscrições: {len(df)} registros")
    
    return dados, nomes_arquivos, mes_ref, ano_ref, dados_processados

# ========== FUNÇÕES DE RELATÓRIOS ==========
class PDFWithTables(FPDF):
    """Classe para gerar PDFs com tabelas"""
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=15)
    
    def add_table_header(self, headers, col_widths):
        self.set_fill_color(200, 200, 200)
        self.set_font('Arial', 'B', 10)
        for i, header in enumerate(headers):
            self.cell(col_widths[i], 10, header, 1, 0, 'C', True)
        self.ln()
    
    def add_table_row(self, data, col_widths):
        self.set_font('Arial', '', 8)
        for i, cell_data in enumerate(data):
            text = str(cell_data)[:30] + "..." if len(str(cell_data)) > 30 else str(cell_data)
            self.cell(col_widths[i], 10, text, 1, 0, 'L')
        self.ln()

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

def gerar_pdf_periodo(conn, mes_inicio, ano_inicio, mes_fim, ano_fim, tipo_relatorio='pagamentos'):
    """Gera relatório PDF para período específico"""
    # Carregar métricas do período
    metricas = carregar_metricas_periodo(conn, mes_inicio, ano_inicio, mes_fim, ano_fim, tipo_relatorio)
    
    if metricas.empty:
        return None
    
    pdf = PDFWithTables()
    pdf.add_page()
    
    # Cabeçalho
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "Prefeitura de São Paulo", 0, 1, 'C')
    pdf.cell(0, 10, "Secretaria Municipal do Desenvolvimento Econômico e Trabalho - SMDET", 0, 1, 'C')
    pdf.cell(0, 10, f"Relatório Executivo - Período: {mes_inicio}/{ano_inicio} a {mes_fim}/{ano_fim}", 0, 1, 'C')
    pdf.ln(10)
    
    pdf.set_font("Arial", '', 12)
    pdf.cell(0, 10, f"Data do relatório: {data_hora_atual_brasilia()}", 0, 1)
    pdf.ln(10)
    
    # Resumo do período
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "Resumo do Período", 0, 1)
    pdf.set_font("Arial", '', 12)
    
    total_registros = metricas['total_registros'].sum()
    total_valor = metricas['valor_total'].sum()
    media_mensal = metricas['total_registros'].mean()
    
    pdf.cell(0, 10, f"Total de registros no período: {formatar_brasileiro(total_registros)}", 0, 1)
    pdf.cell(0, 10, f"Valor total no período: {formatar_brasileiro(total_valor, 'monetario')}", 0, 1)
    pdf.cell(0, 10, f"Média mensal: {formatar_brasileiro(int(media_mensal))}", 0, 1)
    pdf.ln(10)
    
    # Tabela mensal
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "Detalhamento Mensal", 0, 1)
    pdf.ln(5)
    
    # Cabeçalho da tabela
    headers = ['Mês/Ano', 'Registros', 'Beneficiários', 'Valor Total', 'Duplicidades']
    col_widths = [40, 30, 40, 40, 40]
    
    pdf.add_table_header(headers, col_widths)
    
    # Dados da tabela
    for _, row in metricas.iterrows():
        periodo = f"{row['mes_referencia']}/{row['ano_referencia']}"
        dados = [
            periodo,
            formatar_brasileiro(row['total_registros']),
            formatar_brasileiro(row['beneficiarios_unicos']),
            formatar_brasileiro(row['valor_total'], 'monetario'),
            formatar_brasileiro(row['pagamentos_duplicados'])
        ]
        pdf.add_table_row(dados, col_widths)
    
    return pdf.output(dest='S').encode('latin1')

# ========== FUNÇÕES DE CONSULTA AO BANCO ==========
def carregar_pagamentos_db(conn, mes_ref=None, ano_ref=None):
    """Carrega dados de pagamentos do banco"""
    try:
        query = "SELECT * FROM pagamentos"
        params = []
        
        if mes_ref and ano_ref:
            query += " WHERE mes_referencia = ? AND ano_referencia = ?"
            params = [mes_ref, ano_ref]
        
        query += " ORDER BY ano_referencia DESC, mes_referencia DESC"
        
        return pd.read_sql_query(query, conn, params=params)
    except Exception as e:
        st.error(f"Erro ao carregar pagamentos: {e}")
        return pd.DataFrame()

def carregar_inscricoes_db(conn, mes_ref=None, ano_ref=None):
    """Carrega dados de inscrições do banco"""
    try:
        query = "SELECT * FROM inscricoes"
        params = []
        
        if mes_ref and ano_ref:
            query += " WHERE mes_referencia = ? AND ano_referencia = ?"
            params = [mes_ref, ano_ref]
        
        query += " ORDER BY ano_referencia DESC, mes_referencia DESC"
        
        return pd.read_sql_query(query, conn, params=params)
    except Exception as e:
        st.error(f"Erro ao carregar inscrições: {e}")
        return pd.DataFrame()

def carregar_metricas_db(conn, tipo=None):
    """Carrega métricas do banco"""
    try:
        query = "SELECT * FROM metricas_mensais"
        params = []
        
        if tipo:
            query += " WHERE tipo = ?"
            params = [tipo]
        
        query += " ORDER BY ano_referencia DESC, mes_referencia DESC"
        
        return pd.read_sql_query(query, conn, params=params)
    except Exception as e:
        st.error(f"Erro ao carregar métricas: {e}")
        return pd.DataFrame()

def carregar_metricas_periodo(conn, mes_inicio, ano_inicio, mes_fim, ano_fim, tipo):
    """Carrega métricas de um período específico"""
    try:
        # Converter meses para números para comparação
        meses_num = {
            'Janeiro': 1, 'Fevereiro': 2, 'Março': 3, 'Abril': 4,
            'Maio': 5, 'Junho': 6, 'Julho': 7, 'Agosto': 8,
            'Setembro': 9, 'Outubro': 10, 'Novembro': 11, 'Dezembro': 12
        }
        
        mes_inicio_num = meses_num.get(mes_inicio, 1)
        mes_fim_num = meses_num.get(mes_fim, 12)
        
        query = """
            SELECT * FROM metricas_mensais 
            WHERE tipo = ? AND (
                (ano_referencia = ? AND ? >= ?) OR
                (ano_referencia = ? AND ? <= ?) OR
                (ano_referencia > ? AND ano_referencia < ?)
            )
            ORDER BY ano_referencia, ?
        """
        
        # Ordenar por número do mês
        params = [tipo, ano_inicio, meses_num.get('mes_referencia', 1), mes_inicio_num,
                 ano_fim, meses_num.get('mes_referencia', 12), mes_fim_num,
                 ano_inicio, ano_fim, mes_inicio_num]
        
        df = pd.read_sql_query(query, conn, params=params)
        
        # Filtrar para garantir período correto
        if not df.empty:
            df['mes_num'] = df['mes_referencia'].map(meses_num)
            df = df[
                ((df['ano_referencia'] == ano_inicio) & (df['mes_num'] >= mes_inicio_num)) |
                ((df['ano_referencia'] == ano_fim) & (df['mes_num'] <= mes_fim_num)) |
                ((df['ano_referencia'] > ano_inicio) & (df['ano_referencia'] < ano_fim))
            ]
        
        return df
    except Exception as e:
        st.error(f"Erro ao carregar métricas do período: {e}")
        return pd.DataFrame()

# ========== FUNÇÕES ADMINISTRATIVAS ==========
def gerenciar_usuarios(conn):
    """Interface para gerenciamento de usuários"""
    st.header("👥 Gerenciamento de Usuários")
    
    # Listar usuários
    try:
        usuarios_df = pd.read_sql_query(
            "SELECT id, email, nome, tipo, data_criacao, ativo, ultimo_login FROM usuarios ORDER BY tipo, email", 
            conn
        )
        
        if not usuarios_df.empty:
            st.dataframe(usuarios_df, use_container_width=True)
        else:
            st.info("Nenhum usuário cadastrado.")
    except Exception as e:
        st.error(f"Erro ao carregar usuários: {str(e)}")
    
    # Adicionar novo usuário
    st.subheader("Adicionar Novo Usuário")
    
    with st.form("adicionar_usuario"):
        col1, col2 = st.columns(2)
        
        with col1:
            novo_email = st.text_input("Email institucional", placeholder="novo.usuario@prefeitura.sp.gov.br")
            novo_nome = st.text_input("Nome completo")
        
        with col2:
            novoTipo = st.selectbox("Tipo de usuário", ["usuario", "admin"])
            ativo = st.checkbox("Usuário ativo", value=True)
        
        if st.form_submit_button("Adicionar Usuário"):
            if not novo_email or not novo_nome:
                st.error("Preencha todos os campos obrigatórios.")
            elif not novo_email.lower().endswith('@prefeitura.sp.gov.br'):
                st.error("O email deve ser institucional (@prefeitura.sp.gov.br).")
            else:
                try:
                    conn.execute('''
                        INSERT INTO usuarios (email, nome, tipo, data_criacao, ativo)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (novo_email.lower(), novo_nome, novoTipo, data_hora_atual_brasilia(), 1 if ativo else 0))
                    conn.commit()
                    st.success(f"✅ Usuário {novo_email} adicionado com sucesso!")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("❌ Este email já está cadastrado.")
                except Exception as e:
                    st.error(f"Erro ao adicionar usuário: {str(e)}")
    
    # Gerenciar usuários existentes
    st.subheader("Gerenciar Usuários Existentes")
    
    try:
        usuarios_df = pd.read_sql_query(
            "SELECT id, email, nome, tipo, ativo FROM usuarios ORDER BY email", 
            conn
        )
        
        if not usuarios_df.empty:
            usuario_selecionado = st.selectbox("Selecione um usuário:", usuarios_df['email'].tolist())
            usuario_info = usuarios_df[usuarios_df['email'] == usuario_selecionado].iloc[0]
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.write(f"**Email:** {usuario_info['email']}")
                st.write(f"**Nome:** {usuario_info['nome']}")
                st.write(f"**Tipo:** {usuario_info['tipo']}")
            
            with col2:
                st.write(f"**Status:** {'Ativo' if usuario_info['ativo'] else 'Inativo'}")
                
                col3, col4, col5 = st.columns(3)
                
                with col3:
                    if st.button("🔒 Tornar Admin", key="tornar_admin"):
                        conn.execute("UPDATE usuarios SET tipo = 'admin' WHERE email = ?", (usuario_selecionado,))
                        conn.commit()
                        st.success(f"✅ {usuario_selecionado} agora é administrador!")
                        st.rerun()
                
                with col4:
                    if st.button("👤 Tornar Usuário", key="tornar_usuario"):
                        conn.execute("UPDATE usuarios SET tipo = 'usuario' WHERE email = ?", (usuario_selecionado,))
                        conn.commit()
                        st.success(f"✅ {usuario_selecionado} agora é usuário normal!")
                        st.rerun()
                
                with col5:
                    if st.button("🔄 Alternar Status", key="alternar_status"):
                        novo_status = 0 if usuario_info['ativo'] else 1
                        conn.execute("UPDATE usuarios SET ativo = ? WHERE email = ?", (novo_status, usuario_selecionado))
                        conn.commit()
                        st.success(f"✅ Status de {usuario_selecionado} alterado!")
                        st.rerun()
    except Exception as e:
        st.error(f"Erro ao gerenciar usuários: {str(e)}")

def gerenciar_registros(conn, email_admin):
    """Permite visualizar e excluir registros específicos"""
    st.warning("Área administrativa - Use com cuidado!")
    
    # Selecionar tipo de dados
    tipo_dados = st.selectbox("Tipo de dados:", ["Pagamentos", "Inscrições", "Métricas", "Logs"])
    
    if tipo_dados == "Pagamentos":
        dados = carregar_pagamentos_db(conn)
    elif tipo_dados == "Inscrições":
        dados = carregar_inscricoes_db(conn)
    elif tipo_dados == "Métricas":
        dados = carregar_metricas_db(conn)
    else:  # Logs
        dados = pd.read_sql_query("SELECT * FROM logs_admin ORDER BY data_hora DESC", conn)
    
    if not dados.empty:
        st.write(f"**Total de registros:** {len(dados)}")
        st.dataframe(dados.head(20))
        
        if tipo_dados in ["Pagamentos", "Inscrições", "Métricas"]:
            st.subheader("Excluir Registro Específico")
            id_excluir = st.number_input("ID do registro a excluir:", min_value=1, step=1)
            
            if st.button("🗑️ Excluir Registro", type="secondary"):
                if id_excluir:
                    try:
                        # Registrar log antes de excluir
                        detalhes = f"Excluído registro ID {id_excluir} do tipo {tipo_dados}"
                        registrar_log_admin(conn, email_admin, "EXCLUSAO", tipo_dados, id_excluir, detalhes)
                        
                        if tipo_dados == "Pagamentos":
                            conn.execute("DELETE FROM pagamentos WHERE id = ?", (int(id_excluir),))
                        elif tipo_dados == "Inscrições":
                            conn.execute("DELETE FROM inscricoes WHERE id = ?", (int(id_excluir),))
                        else:
                            conn.execute("DELETE FROM metricas_mensais WHERE id = ?", (int(id_excluir),))
                        
                        conn.commit()
                        st.success(f"✅ Registro ID {id_excluir} excluído!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao excluir: {str(e)}")
    
    else:
        st.info("Nenhum registro encontrado.")

def limpar_banco_dados(conn, email_admin):
    """Remove dados do banco - APENAS ADMIN"""
    st.error("**ATENÇÃO CRÍTICA:** Esta operação é IRREVERSÍVEL!")
    
    # Dupla confirmação
    senha_confirmacao1 = st.text_input("Digite 'LIMPAR TUDO' para confirmar:", type="password")
    senha_confirmacao2 = st.text_input("Digite novamente 'LIMPAR TUDO':", type="password")
    
    if st.button("🗑️ LIMPAR TODOS OS DADOS", type="secondary"):
        if senha_confirmacao1 == "LIMPAR TUDO" and senha_confirmacao2 == "LIMPAR TUDO":
            try:
                # Registrar log
                registrar_log_admin(conn, email_admin, "LIMPEZA_COMPLETA", "TODOS", None, "Limpeza completa do banco")
                
                conn.execute("DELETE FROM pagamentos")
                conn.execute("DELETE FROM inscricoes")
                conn.execute("DELETE FROM metricas_mensais")
                
                conn.commit()
                st.success("✅ Banco de dados limpo COMPLETAMENTE!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erro ao limpar banco: {str(e)}")
        else:
            st.error("❌ Confirmação incorreta.")

# ========== INTERFACES DAS ABAS ==========
def mostrar_dashboard_evolutivo(conn):
    """Mostra dashboard com evolução temporal"""
    st.header("📈 Dashboard Evolutivo")
    
    metricas = carregar_metricas_db(conn)
    
    if metricas.empty:
        st.info("📊 Nenhum dado histórico disponível.")
        return
    
    # Separar por tipo
    metricas_pag = metricas[metricas['tipo'] == 'pagamentos']
    metricas_ins = metricas[metricas['tipo'] == 'inscricoes']
    
    if not metricas_pag.empty:
        metricas_pag['periodo'] = metricas_pag['mes_referencia'] + '/' + metricas_pag['ano_referencia'].astype(str)
        metricas_pag = metricas_pag.sort_values(['ano_referencia', 'mes_referencia'])
    
    if not metricas_ins.empty:
        metricas_ins['periodo'] = metricas_ins['mes_referencia'] + '/' + metricas_ins['ano_referencia'].astype(str)
        metricas_ins = metricas_ins.sort_values(['ano_referencia', 'mes_referencia'])
    
    # Gráficos
    col1, col2 = st.columns(2)
    
    with col1:
        if not metricas_pag.empty:
            st.subheader("Evolução de Pagamentos")
            fig = px.line(metricas_pag, x='periodo', y='total_registros',
                         title='Total de Pagamentos por Mês')
            st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        if not metricas_ins.empty:
            st.subheader("Evolução de Inscrições")
            fig = px.line(metricas_ins, x='periodo', y='total_registros',
                         title='Total de Inscrições por Mês')
            st.plotly_chart(fig, use_container_width=True)

def mostrar_relatorios_comparativos(conn):
    """Mostra relatórios comparativos"""
    st.header("📋 Relatórios Comparativos")
    
    # Novo: Gerar relatório por período
    st.subheader("Gerar Relatório por Período")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        meses = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
        mes_inicio = st.selectbox("Mês Início", meses, index=0)
    
    with col2:
        ano_atual = datetime.now().year
        anos = list(range(ano_atual, ano_atual - 5, -1))
        ano_inicio = st.selectbox("Ano Início", anos, index=0)
    
    with col3:
        mes_fim = st.selectbox("Mês Fim", meses, index=11)
    
    with col4:
        ano_fim = st.selectbox("Ano Fim", anos, index=0)
    
    tipo_relatorio = st.selectbox("Tipo de Relatório", ["pagamentos", "inscricoes"])
    
    if st.button("📄 Gerar Relatório PDF do Período"):
        pdf_bytes = gerar_pdf_periodo(conn, mes_inicio, ano_inicio, mes_fim, ano_fim, tipo_relatorio)
        
        if pdf_bytes:
            st.download_button(
                label="📥 Baixar Relatório PDF",
                data=pdf_bytes,
                file_name=f"relatorio_periodo_{mes_inicio}_{ano_inicio}_a_{mes_fim}_{ano_fim}.pdf",
                mime="application/pdf"
            )
        else:
            st.error("Nenhum dado encontrado para o período selecionado.")

def mostrar_dados_historicos(conn):
    """Mostra dados históricos"""
    st.header("🗃️ Dados Históricos")
    
    tipo_dados = st.radio("Tipo de dados:", ["Pagamentos", "Inscrições", "Métricas", "Logs"], horizontal=True)
    
    if tipo_dados == "Pagamentos":
        dados = carregar_pagamentos_db(conn)
    elif tipo_dados == "Inscrições":
        dados = carregar_inscricoes_db(conn)
    elif tipo_dados == "Métricas":
        dados = carregar_metricas_db(conn)
    else:
        dados = pd.read_sql_query("SELECT * FROM logs_admin ORDER BY data_hora DESC", conn)
    
    if not dados.empty:
        st.write(f"Total de registros: {len(dados)}")
        st.dataframe(dados, use_container_width=True)
    else:
        st.info("Nenhum dado encontrado.")

def mostrar_estatisticas_detalhadas(conn):
    """Mostra estatísticas detalhadas"""
    st.header("📊 Estatísticas Detalhadas")
    
    metricas = carregar_metricas_db(conn, tipo='pagamentos')
    
    if metricas.empty:
        st.info("Nenhum dado disponível para análise.")
        return
    
    # Estatísticas gerais
    st.subheader("Estatísticas Gerais")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        total = metricas['total_registros'].sum()
        st.metric("Total de Pagamentos", formatar_brasileiro(total))
    
    with col2:
        valor = metricas['valor_total'].sum()
        st.metric("Valor Total", formatar_brasileiro(valor, 'monetario'))
    
    with col3:
        media = metricas['total_registros'].mean()
        st.metric("Média Mensal", formatar_brasileiro(int(media)))
    
    # Gráfico de distribuição
    metricas['periodo'] = metricas['mes_referencia'] + '/' + metricas['ano_referencia'].astype(str)
    
    fig = px.bar(metricas, x='periodo', y='total_registros',
                 title='Distribuição de Pagamentos por Mês')
    st.plotly_chart(fig, use_container_width=True)

# ========== FUNÇÃO PRINCIPAL ==========
def main():
    # Inicializar banco
    conn = init_database()
    
    if conn is None:
        st.error("❌ Não foi possível inicializar o banco de dados.")
        return
    
    # Autenticação
    email_autorizado, tipo_usuario = autenticar(conn)
    
    if not email_autorizado:
        st.title("🏛️ Sistema POT - SMDET")
        st.markdown("### Análise de Pagamentos e Contas")
        st.info("🔐 **Acesso Restrito** - Faça login para acessar")
        return
    
    # Inicializar session_state
    if 'uploaded_data' not in st.session_state:
        st.session_state.uploaded_data = {}
    if 'processed_metrics' not in st.session_state:
        st.session_state.processed_metrics = {}
    
    # Carregar dados
    dados, nomes_arquivos, mes_ref, ano_ref, dados_processados = carregar_dados(conn, email_autorizado)
    
    # Processar métricas se há dados novos
    tem_dados_pagamentos = 'pagamentos' in dados and not dados['pagamentos'].empty
    tem_dados_contas = 'contas' in dados and not dados['contas'].empty
    
    metrics = st.session_state.processed_metrics
    
    if dados_processados and (tem_dados_pagamentos or tem_dados_contas):
        with st.spinner("🔄 Processando dados..."):
            metrics = processar_dados(dados, nomes_arquivos)
            
            # Salvar métricas no banco
            if tem_dados_pagamentos:
                salvar_metricas_db(conn, 'pagamentos', mes_ref, ano_ref, metrics)
            if tem_dados_contas:
                salvar_metricas_db(conn, 'inscricoes', mes_ref, ano_ref, metrics)
            
            st.session_state.processed_metrics = metrics
    
    # Sidebar - Exportação
    st.sidebar.markdown("---")
    st.sidebar.header("📥 EXPORTAR RELATÓRIOS")
    
    if tem_dados_pagamentos or tem_dados_contas:
        # Botão para relatório PDF do período (substitui o Excel Completo)
        st.sidebar.subheader("📊 Relatório por Período")
        
        col1, col2 = st.sidebar.columns(2)
        with col1:
            mes_inicio = st.sidebar.selectbox("Mês Início", 
                ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'],
                key="mes_inicio_rel")
        with col2:
            ano_atual = datetime.now().year
            anos = list(range(ano_atual, ano_atual - 5, -1))
            ano_inicio = st.sidebar.selectbox("Ano Início", anos, key="ano_inicio_rel")
        
        col3, col4 = st.sidebar.columns(2)
        with col3:
            mes_fim = st.sidebar.selectbox("Mês Fim", 
                ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'],
                index=11, key="mes_fim_rel")
        with col4:
            ano_fim = st.sidebar.selectbox("Ano Fim", anos, key="ano_fim_rel")
        
        tipo_rel = st.sidebar.selectbox("Tipo", ["pagamentos", "inscricoes"], key="tipo_rel")
        
        if st.sidebar.button("📄 Gerar Relatório PDF", use_container_width=True):
            pdf_bytes = gerar_pdf_periodo(conn, mes_inicio, ano_inicio, mes_fim, ano_fim, tipo_rel)
            if pdf_bytes:
                st.sidebar.download_button(
                    label="📥 Baixar PDF",
                    data=pdf_bytes,
                    file_name=f"relatorio_{mes_inicio}_{ano_inicio}_a_{mes_fim}_{ano_fim}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
    
    # Sidebar - Funções administrativas
    if tipo_usuario == 'admin':
        st.sidebar.markdown("---")
        st.sidebar.subheader("⚙️ Administração")
        
        admin_opcao = st.sidebar.selectbox(
            "Selecione uma opção:",
            ["Análise Principal", "Gerenciar Usuários", "Gerenciar Registros", "Limpar Banco"]
        )
        
        if admin_opcao != "Análise Principal":
            if admin_opcao == "Gerenciar Usuários":
                gerenciar_usuarios(conn)
                return
            elif admin_opcao == "Gerenciar Registros":
                gerenciar_registros(conn, email_autorizado)
                return
            elif admin_opcao == "Limpar Banco":
                limpar_banco_dados(conn, email_autorizado)
                return
    
    # Abas principais
    tab_principal, tab_dashboard, tab_relatorios, tab_historico, tab_estatisticas = st.tabs([
        "📊 Análise Mensal", "📈 Dashboard", "📋 Relatórios", "🗃️ Histórico", "📊 Estatísticas"
    ])
    
    with tab_principal:
        mostrar_analise_principal(dados, metrics, nomes_arquivos, mes_ref, ano_ref, 
                                 tem_dados_pagamentos, tem_dados_contas)
    
    with tab_dashboard:
        mostrar_dashboard_evolutivo(conn)
    
    with tab_relatorios:
        mostrar_relatorios_comparativos(conn)
    
    with tab_historico:
        mostrar_dados_historicos(conn)
    
    with tab_estatisticas:
        mostrar_estatisticas_detalhadas(conn)

def mostrar_analise_principal(dados, metrics, nomes_arquivos, mes_ref, ano_ref, 
                             tem_pagamentos, tem_contas):
    """Mostra análise principal"""
    if not tem_pagamentos and not tem_contas:
        st.info("📊 Faça upload das planilhas para iniciar a análise")
        
        st.title("🏛️ Sistema POT - SMDET")
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
        st.title("🏛️ Sistema POT - SMDET")
        st.markdown(f"**Mês de referência:** {mes_ref}/{ano_ref}")
        st.markdown(f"**Data da análise:** {data_hora_atual_brasilia()}")
        st.markdown("---")
        
        # Métricas principais
        if tem_pagamentos:
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total de Pagamentos", formatar_brasileiro(metrics.get('total_pagamentos', 0)))
            with col2:
                st.metric("Beneficiários Únicos", formatar_brasileiro(metrics.get('beneficiarios_unicos', 0)))
            with col3:
                st.metric("Contas Únicas", formatar_brasileiro(metrics.get('contas_unicas', 0)))
            with col4:
                st.metric("Valor Total", formatar_brasileiro(metrics.get('valor_total', 0), 'monetario'))
            
            # Segunda linha
            col5, col6, col7, col8 = st.columns(4)
            
            with col5:
                st.metric("Pagamentos Duplicados", formatar_brasileiro(metrics.get('pagamentos_duplicados', 0)),
                         delta=f"-{formatar_brasileiro(metrics.get('valor_total_duplicados', 0), 'monetario')}",
                         delta_color="inverse")
            with col6:
                st.metric("Projetos Ativos", formatar_brasileiro(metrics.get('projetos_ativos', 0)))
            with col7:
                total_cpfs = (metrics.get('problemas_cpf', {}).get('total_problemas', 0) + 
                            metrics.get('problemas_cpf', {}).get('total_inconsistentes', 0))
                st.metric("CPFs p/ Ajuste", formatar_brasileiro(total_cpfs),
                         delta_color="inverse" if total_cpfs > 0 else "off")
            with col8:
                st.metric("Registros Críticos", 
                         formatar_brasileiro(metrics.get('ausencia_dados', {}).get('total_criticos', 0)),
                         delta_color="inverse" if metrics.get('ausencia_dados', {}).get('total_criticos', 0) > 0 else "off")
        
        if tem_contas:
            st.markdown("---")
            st.subheader("📋 Dados de Inscrições")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total de Inscrições", formatar_brasileiro(metrics.get('total_contas_abertas', 0)))
            with col2:
                st.metric("Beneficiários Únicos", formatar_brasileiro(metrics.get('beneficiarios_contas', 0)))
            with col3:
                st.metric("Projetos Ativos", formatar_brasileiro(metrics.get('projetos_ativos', 0)))
        
        # Abas de análise detalhada
        st.markdown("---")
        tab1, tab2, tab3, tab4 = st.tabs(["📋 Visão Geral", "⚠️ Duplicidades", "🔴 CPFs Problemáticos", "🚨 Problemas Críticos"])
        
        with tab1:
            st.subheader("Resumo dos Dados")
            if tem_pagamentos:
                st.write(f"**Planilha de Pagamentos:** {nomes_arquivos.get('pagamentos', 'N/A')}")
                st.write(f"**Total de registros:** {len(dados.get('pagamentos', pd.DataFrame()))}")
                st.write(f"**Pagamentos válidos:** {metrics.get('total_pagamentos', 0)}")
            
            if tem_contas:
                st.write(f"**Planilha de Inscrições:** {nomes_arquivos.get('contas', 'N/A')}")
                st.write(f"**Total de inscrições:** {metrics.get('total_contas_abertas', 0)}")
        
        with tab2:
            if tem_pagamentos:
                st.subheader("Pagamentos Duplicados")
                duplicidades = metrics.get('duplicidades', {})
                
                if duplicidades.get('total_contas', 0) > 0:
                    st.warning(f"🚨 {duplicidades['total_contas']} contas com pagamentos duplicados")
                    
                    if not duplicidades.get('resumo', pd.DataFrame()).empty:
                        st.dataframe(duplicidades['resumo'])
                else:
                    st.success("✅ Nenhum pagamento duplicado encontrado")
        
        with tab3:
            if tem_pagamentos:
                st.subheader("CPFs Problemáticos")
                problemas = metrics.get('problemas_cpf', {})
                
                if problemas.get('total_problemas', 0) > 0 or problemas.get('total_inconsistentes', 0) > 0:
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.error(f"❌ {problemas.get('total_inconsistentes', 0)} CPFs com INCONSISTÊNCIAS")
                    
                    with col2:
                        st.warning(f"⚠️ {problemas.get('total_problemas', 0)} CPFs com problemas de FORMATAÇÃO")
                    
                    # Mostrar detalhes
                    if not problemas.get('detalhes_inconsistencias', pd.DataFrame()).empty:
                        st.write("**CPFs Inconsistentes:**")
                        st.dataframe(problemas['detalhes_inconsistencias'])
                else:
                    st.success("✅ Nenhum problema com CPFs encontrado")
        
        with tab4:
            st.subheader("Problemas Críticos")
            ausencia = metrics.get('ausencia_dados', {})
            
            if ausencia.get('total_criticos', 0) > 0:
                st.error(f"🚨 {ausencia['total_criticos']} registros com problemas críticos")
                
                if not ausencia.get('registros_criticos', pd.DataFrame()).empty:
                    st.dataframe(ausencia['registros_criticos'])
            else:
                st.success("✅ Nenhum registro crítico encontrado")

if __name__ == "__main__":
    main()
