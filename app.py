# app.py - VERSÃO CORRIGIDA - DADOS NÃO SE APAGAM ENTRE UPLOADS
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timezone, timedelta
import io
from fpdf import FPDF
import numpy as np
import re
import hashlib
import sqlite3
import os
import json
import tempfile
import sys

# ========== CONFIGURAÇÃO ==========
st.set_page_config(
    page_title="Sistema POT - SMDET",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========== BANCO DE DADOS ==========
def init_database():
    """Inicializa o banco de dados SQLite"""
    try:
        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        
        db_path = os.path.join(base_path, 'pot_smdet.db')
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        
        # Tabela principal de pagamentos
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
                importado_por TEXT NOT NULL,
                UNIQUE(mes_referencia, ano_referencia, nome_arquivo)
            )
        ''')
        
        # Tabela de inscrições
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
                importado_por TEXT NOT NULL,
                UNIQUE(mes_referencia, ano_referencia, nome_arquivo)
            )
        ''')
        
        # Tabela de métricas
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
        
        # Tabela: Logs administrativos
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
        
        # Tabela de usuários
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
        
        # Criar índices para melhor performance
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pagamentos_mes_ano ON pagamentos(mes_referencia, ano_referencia)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_inscricoes_mes_ano ON inscricoes(mes_referencia, ano_referencia)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_metricas_tipo_mes_ano ON metricas_mensais(tipo, mes_referencia, ano_referencia)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_usuario ON logs_admin(usuario_email)")
        
        # Inserir administrador padrão se não existir
        cursor = conn.execute("SELECT * FROM usuarios WHERE LOWER(email) = 'admin@prefeitura.sp.gov.br'")
        if cursor.fetchone() is None:
            conn.execute('''
                INSERT INTO usuarios (email, nome, tipo, data_criacao, ativo)
                VALUES (?, ?, ?, ?, ?)
            ''', ('admin@prefeitura.sp.gov.br', 'Administrador', 'admin', data_hora_atual_brasilia(), 1))
        
        conn.commit()
        return conn
        
    except Exception as e:
        st.error(f"Erro ao inicializar banco de dados: {str(e)}")
        return None

# ========== FUNÇÕES UTILITÁRIAS ==========
def agora_brasilia():
    """Retorna data e hora atual no fuso de Brasília"""
    fuso_brasilia = timezone(timedelta(hours=-3))
    return datetime.now(timezone.utc).astimezone(fuso_brasilia)

def data_hora_atual_brasilia():
    """Retorna data e hora atual formatada"""
    return agora_brasilia().strftime("%d/%m/%Y às %H:%M")

def data_hora_arquivo_brasilia():
    """Retorna data e hora para nome de arquivo"""
    return agora_brasilia().strftime("%Y%m%d_%H%M")

def calcular_hash_arquivo(file_bytes):
    """Calcula hash do conteúdo do arquivo"""
    return hashlib.sha256(file_bytes).hexdigest()

def hash_senha(senha):
    """Gera hash SHA-256 da senha"""
    return hashlib.sha256(senha.encode()).hexdigest()

SENHA_AUTORIZADA_HASH = hash_senha("Smdetpot2025")
SENHA_ADMIN_HASH = hash_senha("AdminSmdet2025")

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

# ========== SISTEMA DE AUTENTICAÇÃO ==========
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

def autenticar(conn):
    """Sistema de autenticação"""
    st.sidebar.title("Sistema POT - SMDET")
    st.sidebar.markdown("**Prefeitura de São Paulo**")
    st.sidebar.markdown("**Secretaria Municipal do Desenvolvimento Econômico e Trabalho**")
    st.sidebar.markdown("---")
    
    # Inicializar estado de autenticação
    if 'autenticado' not in st.session_state:
        st.session_state.autenticado = False
    if 'email_autorizado' not in st.session_state:
        st.session_state.email_autorizado = None
    if 'tipo_usuario' not in st.session_state:
        st.session_state.tipo_usuario = None
    if 'tentativas_login' not in st.session_state:
        st.session_state.tentativas_login = 0
    
    # Se já está autenticado
    if st.session_state.autenticado and st.session_state.email_autorizado:
        tipo_usuario = "👑 Administrador" if st.session_state.tipo_usuario == 'admin' else "👤 Usuário"
        st.sidebar.success(f"✅ Acesso autorizado")
        st.sidebar.info(f"{tipo_usuario}: {st.session_state.email_autorizado}")
        
        if st.sidebar.button("🚪 Sair", key="sair_sistema"):
            for key in ['autenticado', 'email_autorizado', 'tipo_usuario', 'uploaded_data', 'processed_metrics']:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()
        
        return st.session_state.email_autorizado, st.session_state.tipo_usuario
    
    # Formulário de login
    with st.sidebar.form("login_form"):
        st.subheader("🔐 Acesso Restrito")
        email = st.text_input("Email institucional", placeholder="seu.email@prefeitura.sp.gov.br")
        senha = st.text_input("Senha", type="password", placeholder="Digite sua senha")
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
            
            if st.session_state.tentativas_login >= 3:
                st.sidebar.error("🚫 Muitas tentativas falhas. Sistema bloqueado por 5 minutos.")
    
    return None, None

# ========== FUNÇÕES DE PROCESSAMENTO DE ARQUIVOS ==========
def extrair_mes_ano_arquivo(nome_arquivo):
    """Extrai mês e ano do nome do arquivo"""
    if not nome_arquivo:
        return None, None
    
    nome_upper = nome_arquivo.upper()
    
    # Mapeamento direto e simples
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
    
    # Primeiro, procurar por padrão MES/ANO ou MES-ANO
    padroes = [
        # Formato: JANEIRO-2024, JANEIRO_2024, JANEIRO2024
        (r'(JANEIRO|FEVEREIRO|MAR[ÇC]O|ABRIL|MAIO|JUNHO|JULHO|AGOSTO|SETEMBRO|OUTUBRO|NOVEMBRO|DEZEMBRO)[_\- ]?(\d{4})', 1, 2),
        # Formato: JAN-2024, FEV-2024, etc
        (r'(JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)[_\- ]?(\d{4})', 1, 2),
        # Formato: 01-2024, 02-2024, etc
        (r'(\d{1,2})[_\-/](\d{4})', 1, 2),
        # Formato: 2024-01, 2024-02, etc
        (r'(\d{4})[_\-/](\d{1,2})', 2, 1),
    ]
    
    for padrao, idx_mes, idx_ano in padroes:
        match = re.search(padrao, nome_upper)
        if match:
            mes_str = match.group(idx_mes).upper()
            ano_str = match.group(idx_ano)
            
            # Converter mês
            mes = None
            
            # Se é número (01, 02, etc)
            if mes_str.isdigit():
                mes_num = int(mes_str)
                meses_numeros = {
                    1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
                    5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
                    9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
                }
                mes = meses_numeros.get(mes_num)
            else:
                # Procurar no mapeamento
                for key, value in meses_map.items():
                    if key in mes_str:
                        mes = value
                        break
            
            if mes and ano_str.isdigit():
                return mes, int(ano_str)
    
    # Se não encontrou padrão, procurar apenas o ano
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
    
    # Se não encontrou nada, usar mês e ano atual
    mes_atual_num = agora_brasilia().month
    meses_numeros = {
        1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
        5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
        9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
    }
    return meses_numeros.get(mes_atual_num, 'Janeiro'), agora_brasilia().year

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

def identificar_linha_totais(df):
    """Identifica se a última linha contém totais"""
    if df.empty or len(df) <= 1:
        return None, df
    
    ultima_linha = df.iloc[-1].copy()
    
    tem_conta_valida = False
    tem_nome_valido = False
    tem_cpf_valido = False
    
    coluna_conta = obter_coluna_conta(df)
    coluna_nome = obter_coluna_nome(df)
    coluna_cpf = 'CPF' if 'CPF' in df.columns else None
    
    if coluna_conta and coluna_conta in ultima_linha:
        valor_conta = str(ultima_linha[coluna_conta]) if pd.notna(ultima_linha[coluna_conta]) else ''
        tem_conta_valida = valor_conta.strip() != ''
    
    if coluna_nome and coluna_nome in ultima_linha:
        valor_nome = str(ultima_linha[coluna_nome]) if pd.notna(ultima_linha[coluna_nome]) else ''
        tem_nome_valido = valor_nome.strip() != ''
    
    if coluna_cpf and coluna_cpf in ultima_linha:
        valor_cpf = str(ultima_linha[coluna_cpf]) if pd.notna(ultima_linha[coluna_cpf]) else ''
        tem_cpf_valido = valor_cpf.strip() != ''
    
    if not tem_conta_valida and not tem_nome_valido and not tem_cpf_valido:
        colunas_texto = [col for col in df.columns if df[col].dtype == 'object']
        for coluna in colunas_texto[:3]:
            if coluna in ultima_linha and pd.notna(ultima_linha[coluna]):
                valor = str(ultima_linha[coluna]).upper()
                if any(palavra in valor for palavra in ['TOTAL', 'SOMA', 'GERAL', 'TOTAL GERAL', 'SOMATÓRIO']):
                    df_sem_totais = df.iloc[:-1].copy()
                    return ultima_linha, df_sem_totais
    
    return None, df

def filtrar_pagamentos_validos(df):
    """Filtra apenas os registros que possuem número da conta"""
    coluna_conta = obter_coluna_conta(df)
    
    if not coluna_conta:
        return df
    
    df_filtrado = df[df[coluna_conta].notna() & (df[coluna_conta].astype(str).str.strip() != '')].copy()
    
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
                
                valor_limpo_str = re.sub(r'[^\d,.]', '', valor_str)
                valor_limpo_str = valor_limpo_str.replace(',', '.')
                
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
            st.sidebar.info("📝 Registro de pagamentos atualizado")
        else:
            conn.execute('''
                INSERT INTO pagamentos (mes_referencia, ano_referencia, data_importacao, 
                          nome_arquivo, dados_json, metadados_json, hash_arquivo, importado_por)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (mes_ref, ano_ref, data_hora_atual_brasilia(), nome_arquivo, 
                  dados_json, metadados_json, file_hash, importado_por.lower()))
            st.sidebar.success("✅ Novo registro de pagamentos salvo")
        
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
            st.sidebar.info("📝 Registro de inscrições atualizado")
        else:
            conn.execute('''
                INSERT INTO inscricoes (mes_referencia, ano_referencia, data_importacao, 
                          nome_arquivo, dados_json, metadados_json, hash_arquivo, importado_por)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (mes_ref, ano_ref, data_hora_atual_brasilia(), nome_arquivo, 
                  dados_json, metadados_json, file_hash, importado_por.lower()))
            st.sidebar.success("✅ Novo registro de inscrições salvo")
        
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar inscrições: {str(e)}")
        return False

def salvar_metricas_db(conn, tipo, mes_ref, ano_ref, metrics):
    """Salva métricas no banco"""
    try:
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
                metrics.get('total_registros_criticos', 0),
                metrics.get('total_cpfs_ajuste', 0),
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
                  metrics.get('total_registros_criticos', 0),
                  metrics.get('total_cpfs_ajuste', 0),
                  data_hora_atual_brasilia()))
        
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar métricas: {str(e)}")
        return False

# ========== FUNÇÕES DE ANÁLISE ==========
def identificar_cpfs_problematicos(df):
    """Identifica CPFs com problemas"""
    problemas = {
        'detalhes_cpfs_problematicos': pd.DataFrame(),
        'detalhes_inconsistencias': pd.DataFrame(),
        'total_problemas_cpf': 0,
        'total_cpfs_inconsistentes': 0,
        'cpfs_vazios': [],
        'cpfs_com_caracteres_invalidos': [],
        'cpfs_com_tamanho_incorreto': [],
        'cpfs_com_nomes_diferentes': [],
        'cpfs_com_contas_diferentes': [],
        'cpfs_duplicados': [],
        'detalhes_cpfs_vazios': pd.DataFrame(),
        'detalhes_cpfs_invalidos': pd.DataFrame(),
        'detalhes_cpfs_tamanho_incorreto': pd.DataFrame()
    }
    
    if 'CPF' not in df.columns or df.empty:
        return problemas
    
    df_analise = df.copy()
    df_analise['Linha_Planilha_Original'] = df_analise.index + 2
    
    detalhes_problemas = []
    cpfs_vazios_detalhes = []
    cpfs_invalidos_detalhes = []
    cpfs_tamanho_detalhes = []
    
    for idx, row in df_analise.iterrows():
        cpf = str(row['CPF']) if pd.notna(row['CPF']) and str(row['CPF']).strip() != '' else ''
        problemas_lista = []
        
        if cpf == '':
            problemas_lista.append('CPF vazio')
            problemas['cpfs_vazios'].append(idx)
            
            detalhe_vazio = {
                'Linha_Planilha': idx + 2,
                'CPF_Original': row.get('CPF', ''),
                'CPF_Processado': '',
                'Problema': 'CPF vazio'
            }
            
            coluna_nome = obter_coluna_nome(df_analise)
            if coluna_nome and coluna_nome in row:
                detalhe_vazio['Nome'] = row[coluna_nome]
            
            coluna_conta = obter_coluna_conta(df_analise)
            if coluna_conta and coluna_conta in row:
                detalhe_vazio['Numero_Conta'] = row[coluna_conta]
            
            cpfs_vazios_detalhes.append(detalhe_vazio)
            
        elif not cpf.isdigit():
            problemas_lista.append('Caracteres inválidos')
            problemas['cpfs_com_caracteres_invalidos'].append(idx)
            
            detalhe_invalido = {
                'Linha_Planilha': idx + 2,
                'CPF_Original': row.get('CPF', ''),
                'CPF_Processado': cpf,
                'Problema': 'Caracteres inválidos'
            }
            
            coluna_nome = obter_coluna_nome(df_analise)
            if coluna_nome and coluna_nome in row:
                detalhe_invalido['Nome'] = row[coluna_nome]
            
            coluna_conta = obter_coluna_conta(df_analise)
            if coluna_conta and coluna_conta in row:
                detalhe_invalido['Numero_Conta'] = row[coluna_conta]
            
            cpfs_invalidos_detalhes.append(detalhe_invalido)
            
        elif len(cpf) != 11:
            problemas_lista.append(f'Tamanho incorreto ({len(cpf)} dígitos)')
            problemas['cpfs_com_tamanho_incorreto'].append(idx)
            
            detalhe_tamanho = {
                'Linha_Planilha': idx + 2,
                'CPF_Original': row.get('CPF', ''),
                'CPF_Processado': cpf,
                'Problema': f'Tamanho incorreto ({len(cpf)} dígitos)'
            }
            
            coluna_nome = obter_coluna_nome(df_analise)
            if coluna_nome and coluna_nome in row:
                detalhe_tamanho['Nome'] = row[coluna_nome]
            
            coluna_conta = obter_coluna_conta(df_analise)
            if coluna_conta and coluna_conta in row:
                detalhe_tamanho['Numero_Conta'] = row[coluna_conta]
            
            cpfs_tamanho_detalhes.append(detalhe_tamanho)
        
        if problemas_lista:
            info = {
                'Linha_Planilha': idx + 2,
                'CPF_Original': row.get('CPF', ''),
                'CPF_Processado': cpf,
                'Problemas_Formatacao': ', '.join(problemas_lista),
                'Status_Registro': 'VÁLIDO - Precisa de correção'
            }
            
            coluna_nome = obter_coluna_nome(df_analise)
            if coluna_nome and coluna_nome in row:
                info['Nome'] = row[coluna_nome]
            
            coluna_conta = obter_coluna_conta(df_analise)
            if coluna_conta and coluna_conta in row:
                info['Numero_Conta'] = row[coluna_conta]
            
            detalhes_problemas.append(info)
    
    if cpfs_vazios_detalhes:
        problemas['detalhes_cpfs_vazios'] = pd.DataFrame(cpfs_vazios_detalhes)
    
    if cpfs_invalidos_detalhes:
        problemas['detalhes_cpfs_invalidos'] = pd.DataFrame(cpfs_invalidos_detalhes)
    
    if cpfs_tamanho_detalhes:
        problemas['detalhes_cpfs_tamanho_incorreto'] = pd.DataFrame(cpfs_tamanho_detalhes)
    
    if detalhes_problemas:
        problemas['detalhes_cpfs_problematicos'] = pd.DataFrame(detalhes_problemas)
        problemas['total_problemas_cpf'] = len(detalhes_problemas)
    
    cpfs_duplicados = df_analise[df_analise.duplicated(['CPF'], keep=False)]
    
    if not cpfs_duplicados.empty:
        detalhes_inconsistencias = []
        
        for cpf, grupo in cpfs_duplicados.groupby('CPF'):
            if len(grupo) > 1:
                problemas['cpfs_duplicados'].append(cpf)
                
                coluna_nome = obter_coluna_nome(grupo)
                coluna_conta = obter_coluna_conta(grupo)
                
                tem_nomes_diferentes = False
                tem_contas_diferentes = False
                
                if coluna_nome and coluna_nome in grupo.columns:
                    nomes_unicos = grupo[coluna_nome].dropna().unique()
                    if len(nomes_unicos) > 1:
                        problemas['cpfs_com_nomes_diferentes'].append(cpf)
                        tem_nomes_diferentes = True
                
                if coluna_conta and coluna_conta in grupo.columns:
                    contas_unicas = grupo[coluna_conta].dropna().unique()
                    if len(contas_unicas) > 1:
                        problemas['cpfs_com_contas_diferentes'].append(cpf)
                        tem_contas_diferentes = True
                
                if tem_nomes_diferentes or tem_contas_diferentes:
                    for idx, registro in grupo.iterrows():
                        info = {
                            'CPF': cpf,
                            'Linha_Planilha': registro['Linha_Planilha_Original'],
                            'Ocorrencia_CPF': f"{list(grupo.index).index(idx) + 1}/{len(grupo)}",
                            'Problemas_Inconsistencia': '',
                            'Status': 'CRÍTICO - Correção urgente necessária'
                        }
                        
                        if coluna_nome:
                            info['Nome'] = registro[coluna_nome]
                        if coluna_conta:
                            info['Numero_Conta'] = registro[coluna_conta]
                        
                        problemas_lista = ['CPF DUPLICADO']
                        if tem_nomes_diferentes:
                            problemas_lista.append('NOMES DIFERENTES')
                        if tem_contas_diferentes:
                            problemas_lista.append('CONTAS DIFERENTES')
                        
                        info['Problemas_Inconsistencia'] = ', '.join(problemas_lista)
                        detalhes_inconsistencias.append(info)
        
        if detalhes_inconsistencias:
            problemas['detalhes_inconsistencias'] = pd.DataFrame(detalhes_inconsistencias)
            problemas['total_cpfs_inconsistentes'] = len(set(
                problemas['cpfs_com_nomes_diferentes'] + 
                problemas['cpfs_com_contas_diferentes']
            ))
    
    return problemas

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
    
    df = filtrar_pagamentos_validos(df)
    
    if df.empty:
        return duplicidades
    
    coluna_conta = obter_coluna_conta(df)
    
    if not coluna_conta:
        return duplicidades
    
    contagem_por_conta = df[coluna_conta].value_counts()
    contas_com_multiplos = contagem_por_conta[contagem_por_conta > 1].index.tolist()
    
    duplicidades['contas_com_multiplos_pagamentos'] = contas_com_multiplos
    
    if not contas_com_multiplos:
        return duplicidades
    
    df_duplicados = df[df[coluna_conta].isin(contas_com_multiplos)].copy()
    
    df_duplicados['Ocorrencia'] = df_duplicados.groupby(coluna_conta).cumcount() + 1
    df_duplicados['Total_Ocorrencias'] = df_duplicados.groupby(coluna_conta)[coluna_conta].transform('count')
    
    colunas_exibicao = [coluna_conta, 'Ocorrencia', 'Total_Ocorrencias']
    
    coluna_nome = obter_coluna_nome(df_duplicados)
    if coluna_nome:
        colunas_exibicao.append(coluna_nome)
    
    if 'CPF' in df_duplicados.columns:
        colunas_exibicao.append('CPF')
    
    if 'Valor_Limpo' in df_duplicados.columns:
        colunas_exibicao.append('Valor_Limpo')
        duplicidades['valor_total_duplicados'] = df_duplicados['Valor_Limpo'].sum()
    
    duplicidades['detalhes_completos_duplicidades'] = df_duplicados[colunas_exibicao]
    duplicidades['total_contas_duplicadas'] = len(contas_com_multiplos)
    duplicidades['total_pagamentos_duplicados'] = len(df_duplicados)
    
    resumo = []
    for conta in contas_com_multiplos:
        registros_conta = df_duplicados[df_duplicados[coluna_conta] == conta]
        info = {
            'Conta': conta,
            'Total_Pagamentos': len(registros_conta),
            'Valor_Total': registros_conta['Valor_Limpo'].sum() if 'Valor_Limpo' in registros_conta.columns else 0,
            'Pagamentos_Extras': len(registros_conta) - 1
        }
        
        if coluna_nome:
            info['Nome'] = registros_conta.iloc[0][coluna_nome] if not registros_conta.empty else ''
        
        resumo.append(info)
    
    duplicidades['resumo_duplicidades'] = pd.DataFrame(resumo)
    
    return duplicidades

def detectar_pagamentos_pendentes(dados):
    """Detecta possíveis pagamentos pendentes comparando contas abertas com pagamentos realizados"""
    pendentes = {
        'contas_sem_pagamento': pd.DataFrame(),
        'total_contas_sem_pagamento': 0,
        'beneficiarios_sem_pagamento': 0
    }
    
    if 'contas' not in dados or dados['contas'].empty or 'pagamentos' not in dados or dados['pagamentos'].empty:
        return pendentes
    
    df_contas = dados['contas']
    df_pagamentos = dados['pagamentos']
    
    coluna_conta_contas = obter_coluna_conta(df_contas)
    coluna_conta_pagamentos = obter_coluna_conta(df_pagamentos)
    coluna_nome_contas = obter_coluna_nome(df_contas)
    
    if not coluna_conta_contas or not coluna_conta_pagamentos:
        return pendentes
    
    df_pagamentos_validos = filtrar_pagamentos_validos(df_pagamentos)
    
    contas_com_pagamento = df_pagamentos_validos[coluna_conta_pagamentos].dropna().unique()
    contas_abertas = df_contas[coluna_conta_contas].dropna().unique()
    
    contas_sem_pagamento = [conta for conta in contas_abertas if conta not in contas_com_pagamento]
    
    if not contas_sem_pagamento:
        return pendentes
    
    df_contas_sem_pagamento = df_contas[df_contas[coluna_conta_contas].isin(contas_sem_pagamento)].copy()
    
    colunas_exibicao = [coluna_conta_contas]
    
    if coluna_nome_contas:
        colunas_exibicao.append(coluna_nome_contas)
    
    if 'CPF' in df_contas_sem_pagamento.columns:
        colunas_exibicao.append('CPF')
    
    if 'Projeto' in df_contas_sem_pagamento.columns:
        colunas_exibicao.append('Projeto')
    
    if 'Data_Abertura' in df_contas_sem_pagamento.columns:
        colunas_exibicao.append('Data_Abertura')
    elif 'Data' in df_contas_sem_pagamento.columns:
        colunas_exibicao.append('Data')
    
    df_contas_sem_pagamento['Status'] = 'Aguardando Pagamento'
    
    pendentes['contas_sem_pagamento'] = df_contas_sem_pagamento[colunas_exibicao + ['Status']]
    pendentes['total_contas_sem_pagamento'] = len(contas_sem_pagamento)
    pendentes['beneficiarios_sem_pagamento'] = df_contas_sem_pagamento[coluna_nome_contas].nunique() if coluna_nome_contas else 0
    
    return pendentes

def analisar_ausencia_dados(dados, nome_arquivo_pagamentos=None, nome_arquivo_contas=None):
    """Analisa e reporta apenas dados críticos realmente ausentes"""
    analise_ausencia = {
        'registros_criticos_problematicos': [],
        'total_registros_criticos': 0,
        'resumo_ausencias': pd.DataFrame(),
        'registros_problema_detalhados': pd.DataFrame(),
        'nome_arquivo_pagamentos': nome_arquivo_pagamentos,
        'nome_arquivo_contas': nome_arquivo_contas
    }
    
    if 'pagamentos' in dados and not dados['pagamentos'].empty:
        df = dados['pagamentos']
        df = df.reset_index(drop=True)
        
        registros_problematicos = []
        
        coluna_conta = obter_coluna_conta(df)
        coluna_nome = obter_coluna_nome(df)
        coluna_cpf = 'CPF' if 'CPF' in df.columns else None
        
        if coluna_conta:
            for idx, row in df.iterrows():
                tem_conta_valida = coluna_conta in row and pd.notna(row[coluna_conta]) and str(row[coluna_conta]).strip() != ''
                tem_nome_valido = coluna_nome and coluna_nome in row and pd.notna(row[coluna_nome]) and str(row[coluna_nome]).strip() != ''
                tem_cpf_valido = coluna_cpf and coluna_cpf in row and pd.notna(row[coluna_cpf]) and str(row[coluna_cpf]).strip() != ''
                
                if not tem_conta_valida and not tem_nome_valido and not tem_cpf_valido:
                    continue
                
                if not tem_conta_valida and (tem_nome_valido or tem_cpf_valido):
                    registros_problematicos.append(idx)
        
        if 'Valor_Limpo' in df.columns:
            for idx, row in df.iterrows():
                if pd.isna(row['Valor_Limpo']) or row['Valor_Limpo'] == 0:
                    conta_val = str(row[coluna_conta]) if coluna_conta and coluna_conta in row else ''
                    if any(palavra in str(conta_val).upper() for palavra in ['TOTAL', 'SOMA', 'GERAL']):
                        continue
                    
                    if idx not in registros_problematicos:
                        registros_problematicos.append(idx)
        
        analise_ausencia['registros_criticos_problematicos'] = registros_problematicos
        analise_ausencia['total_registros_criticos'] = len(registros_problematicos)
        
        if registros_problematicos:
            analise_ausencia['registros_problema_detalhados'] = df.loc[registros_problematicos].copy()
        
        if registros_problematicos:
            resumo = []
            for idx in registros_problematicos[:100]:
                registro = df.loc[idx]
                
                info_ausencia = {
                    'Indice_Registro': idx,
                    'Linha_Planilha': idx + 2,
                    'Planilha_Origem': nome_arquivo_pagamentos or 'Pagamentos',
                    'Status_Registro': 'INVÁLIDO - Precisa de correção'
                }
                
                colunas_interesse = []
                colunas_possiveis = ['CPF', 'RG', 'Projeto', 'Valor', 'Beneficiario', 
                                   'Beneficiário', 'Nome', 'Data', 'Data Pagto', 'Status']
                
                for col in colunas_possiveis:
                    if col in df.columns:
                        colunas_interesse.append(col)
                
                if coluna_conta and coluna_conta not in colunas_interesse:
                    colunas_interesse.append(coluna_conta)
                
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
                
                problemas = []
                if coluna_conta and (pd.isna(registro[coluna_conta]) or str(registro[coluna_conta]).strip() == ''):
                    problemas.append('Número da conta ausente')
                
                if 'Valor_Limpo' in df.columns and (pd.isna(registro['Valor_Limpo']) or registro.get('Valor_Limpo', 0) == 0):
                    problemas.append('Valor ausente ou zero')
                
                info_ausencia['Problemas_Identificados'] = ', '.join(problemas) if problemas else 'Dados OK'
                resumo.append(info_ausencia)
            
            analise_ausencia['resumo_ausencias'] = pd.DataFrame(resumo)
    
    return analise_ausencia

def verificar_duplicidade_periodo(conn, mes_ref, ano_ref, tipo_arquivo):
    """Verifica se já existe arquivo para o mesmo período"""
    try:
        if tipo_arquivo == 'pagamentos':
            cursor = conn.execute(
                "SELECT nome_arquivo, data_importacao FROM pagamentos WHERE mes_referencia = ? AND ano_referencia = ?",
                (mes_ref, ano_ref)
            )
        else:
            cursor = conn.execute(
                "SELECT nome_arquivo, data_importacao FROM inscricoes WHERE mes_referencia = ? AND ano_referencia = ?",
                (mes_ref, ano_ref)
            )
        
        resultado = cursor.fetchall()
        return resultado
    except Exception as e:
        # Se a tabela não existir ainda, retorna lista vazia
        return []

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
        'total_contas_abertas': 0,
        'beneficiarios_contas': 0,
        'duplicidades_detalhadas': {},
        'pagamentos_pendentes': {},
        'total_registros_invalidos': 0,
        'problemas_cpf': {},
        'total_registros_criticos': 0,
        'total_cpfs_ajuste': 0,
        'linha_totais_removida': False,
        'dados_linha_totais': None
    }
    
    # Identificar linha de totais
    if 'pagamentos' in dados and not dados['pagamentos'].empty:
        linha_totais, df_sem_totais = identificar_linha_totais(dados['pagamentos'])
        if linha_totais is not None:
            dados['pagamentos'] = df_sem_totais
            metrics['linha_totais_removida'] = True
            metrics['dados_linha_totais'] = linha_totais
    
    analise_ausencia = analisar_ausencia_dados(dados, nomes_arquivos.get('pagamentos'), nomes_arquivos.get('contas'))
    metrics.update(analise_ausencia)
    
    # Processar pagamentos
    if 'pagamentos' in dados and not dados['pagamentos'].empty:
        df = dados['pagamentos']
        
        coluna_conta = obter_coluna_conta(df)
        if coluna_conta:
            registros_invalidos = df[
                df[coluna_conta].isna() | 
                (df[coluna_conta].astype(str).str.strip() == '')
            ]
            metrics['total_registros_invalidos'] = len(registros_invalidos)
        
        df_validos = filtrar_pagamentos_validos(df)
        
        if not df_validos.empty:
            coluna_nome = obter_coluna_nome(df_validos)
            if coluna_nome:
                metrics['beneficiarios_unicos'] = df_validos[coluna_nome].nunique()
            
            metrics['total_pagamentos'] = len(df_validos)
            
            if coluna_conta:
                metrics['contas_unicas'] = df_validos[coluna_conta].nunique()
            
            if 'Projeto' in df_validos.columns:
                metrics['projetos_ativos'] = df_validos['Projeto'].nunique()
            
            if 'Valor_Limpo' in df_validos.columns:
                metrics['valor_total'] = df_validos['Valor_Limpo'].sum()
            
            metrics['problemas_cpf'] = identificar_cpfs_problematicos(df_validos)
            metrics['duplicidades_detalhadas'] = detectar_pagamentos_duplicados(df_validos)
            
            metrics['pagamentos_duplicados'] = metrics['duplicidades_detalhadas']['total_contas_duplicadas']
            metrics['valor_total_duplicados'] = metrics['duplicidades_detalhadas']['valor_total_duplicados']
            
            problemas_cpf = metrics['problemas_cpf']
            metrics['total_cpfs_ajuste'] = (
                problemas_cpf.get('total_problemas_cpf', 0) + 
                problemas_cpf.get('total_cpfs_inconsistentes', 0)
            )
    
    # Processar inscrições
    if 'contas' in dados and not dados['contas'].empty:
        df_contas = dados['contas']
        
        metrics['total_contas_abertas'] = len(df_contas)
        
        coluna_nome = obter_coluna_nome(df_contas)
        if coluna_nome:
            metrics['beneficiarios_contas'] = df_contas[coluna_nome].nunique()
        
        if 'Projeto' in df_contas.columns:
            metrics['projetos_ativos'] = max(metrics.get('projetos_ativos', 0), df_contas['Projeto'].nunique())
    
    # Detectar pagamentos pendentes
    if 'pagamentos' in dados and 'contas' in dados:
        metrics['pagamentos_pendentes'] = detectar_pagamentos_pendentes(dados)
    
    return metrics

# ========== FUNÇÕES DE GERAÇÃO DE RELATÓRIOS ==========
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
    
    def add_table_row(self, data, col_widths, row_height=10):
        self.set_font('Arial', '', 8)
        
        max_lines = 1
        cell_data_lines = []
        
        for i, cell_data in enumerate(data):
            if cell_data:
                text = str(cell_data)
                text_width = self.get_string_width(text)
                available_width = col_widths[i] - 2
                
                if text_width > available_width:
                    lines = self._split_text(text, available_width)
                    max_lines = max(max_lines, len(lines))
                    cell_data_lines.append(lines)
                else:
                    cell_data_lines.append([text])
            else:
                cell_data_lines.append([''])
        
        y_start = self.get_y()
        
        for i in range(len(data)):
            x = self.get_x()
            y = y_start
            
            lines = cell_data_lines[i]
            cell_height = row_height * max(1, len(lines) * 0.5)
            
            self.set_xy(x, y)
            self.cell(col_widths[i], cell_height, '', 1, 0, 'L')
            
            self.set_xy(x + 1, y + 1)
            for j, line in enumerate(lines):
                self.set_xy(x + 1, y + 1 + (j * row_height/2))
                self.cell(col_widths[i] - 2, row_height/2, line, 0, 0, 'L')
            
            self.set_xy(x + col_widths[i], y_start)
        
        self.set_y(y_start + (max_lines * row_height/2))
    
    def _split_text(self, text, max_width):
        words = text.split(' ')
        lines = []
        current_line = []
        
        for word in words:
            test_line = ' '.join(current_line + [word])
            if self.get_string_width(test_line) < max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                if self.get_string_width(word) < max_width:
                    current_line = [word]
                else:
                    current_line = []
                    current_chars = ''
                    for char in word:
                        if self.get_string_width(current_chars + char) < max_width:
                            current_chars += char
                        else:
                            if current_chars:
                                lines.append(current_chars)
                            current_chars = char
                    if current_chars:
                        current_line = [current_chars]
        
        if current_line:
            lines.append(' '.join(current_line))
        
        return lines

def gerar_pdf_executivo(metrics, dados, nomes_arquivos, tipo_relatorio='pagamentos'):
    """Gera relatório executivo em PDF"""
    pdf = PDFWithTables()
    pdf.add_page()
    
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "Prefeitura de São Paulo", 0, 1, 'C')
    pdf.cell(0, 10, "Secretaria Municipal do Desenvolvimento Econômico e Trabalho - SMDET", 0, 1, 'C')
    
    if tipo_relatorio == 'pagamentos':
        pdf.cell(0, 10, "Relatório Executivo - Sistema POT (Pagamentos)", 0, 1, 'C')
    else:
        pdf.cell(0, 10, "Relatório Executivo - Sistema POT (Inscrições)", 0, 1, 'C')
    
    pdf.ln(10)
    
    pdf.set_font("Arial", '', 12)
    pdf.cell(0, 10, f"Data da análise: {data_hora_atual_brasilia()}", 0, 1)
    pdf.ln(5)
    
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
            ("Total de Pagamentos", formatar_brasileiro(metrics.get('total_pagamentos', 0))),
            ("Beneficiários Únicos", formatar_brasileiro(metrics.get('beneficiarios_unicos', 0))),
            ("Contas Únicas", formatar_brasileiro(metrics.get('contas_unicas', 0))),
            ("Valor Total (Valor Pagto)", formatar_brasileiro(metrics.get('valor_total', 0), 'monetario')),
            ("Pagamentos Duplicados", formatar_brasileiro(metrics.get('pagamentos_duplicados', 0))),
            ("Valor em Duplicidades", formatar_brasileiro(metrics.get('valor_total_duplicados', 0), 'monetario')),
            ("Projetos Ativos", formatar_brasileiro(metrics.get('projetos_ativos', 0))),
            ("CPFs p/ Ajuste", formatar_brasileiro(metrics.get('total_cpfs_ajuste', 0))),
            ("Registros Críticos", formatar_brasileiro(metrics.get('total_registros_criticos', 0)))
        ]
    else:
        metricas = [
            ("Total de Inscrições", formatar_brasileiro(metrics.get('total_contas_abertas', 0))),
            ("Beneficiários Únicos", formatar_brasileiro(metrics.get('beneficiarios_contas', 0))),
            ("Projetos Ativos", formatar_brasileiro(metrics.get('projetos_ativos', 0)))
        ]
    
    for nome, valor in metricas:
        pdf.cell(100, 10, nome, 0, 0)
        pdf.cell(0, 10, str(valor), 0, 1)
    
    pdf.ln(10)
    
    # Alertas e problemas
    if tipo_relatorio == 'pagamentos':
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 10, "Alertas e Problemas Identificados", 0, 1)
        pdf.set_font("Arial", '', 12)
        
        pagamentos_duplicados = metrics.get('pagamentos_duplicados', 0)
        if pagamentos_duplicados > 0:
            pdf.set_font("Arial", 'B', 12)
            pdf.set_text_color(255, 0, 0)
            pdf.cell(0, 10, f"ALERTA: {pagamentos_duplicados} contas com pagamentos duplicados", 0, 1)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(0, 10, f"Valor total em duplicidades: {formatar_brasileiro(metrics.get('valor_total_duplicados', 0), 'monetario')}", 0, 1)
            pdf.ln(5)
        
        problemas_cpf = metrics.get('problemas_cpf', {})
        total_cpfs_ajuste = metrics.get('total_cpfs_ajuste', 0)
        
        if total_cpfs_ajuste > 0:
            pdf.set_font("Arial", 'B', 12)
            pdf.set_text_color(255, 0, 0)
            pdf.cell(0, 10, f"ALERTA CRÍTICO: {total_cpfs_ajuste} CPFs precisam de correção", 0, 1)
            pdf.set_text_color(0, 0, 0)
            
            total_problemas_cpf = problemas_cpf.get('total_problemas_cpf', 0)
            if total_problemas_cpf > 0:
                pdf.cell(0, 10, f"  - {total_problemas_cpf} CPFs com problemas de formatação", 0, 1)
            
            total_cpfs_inconsistentes = problemas_cpf.get('total_cpfs_inconsistentes', 0)
            if total_cpfs_inconsistentes > 0:
                pdf.cell(0, 10, f"  - {total_cpfs_inconsistentes} CPFs com inconsistências críticas", 0, 1)
            
            pdf.ln(5)
            
            # Adicionar tabelas detalhadas
            if not problemas_cpf.get('detalhes_cpfs_vazios', pd.DataFrame()).empty:
                pdf.add_page()
                pdf.set_font("Arial", 'B', 12)
                pdf.cell(0, 10, "Tabela 1: CPFs Vazios", 0, 1)
                pdf.set_font("Arial", '', 10)
                
                df_cpfs_vazios = problemas_cpf['detalhes_cpfs_vazios'].head(50)
                headers = ['Linha', 'CPF Original', 'Nome', 'Número da Conta']
                col_widths = [20, 40, 80, 50]
                
                pdf.add_table_header(headers, col_widths)
                
                for idx, row in df_cpfs_vazios.iterrows():
                    pdf.add_table_row([
                        str(row['Linha_Planilha']),
                        str(row['CPF_Original']),
                        str(row.get('Nome', '')),
                        str(row.get('Numero_Conta', ''))
                    ], col_widths)
            
            if not problemas_cpf.get('detalhes_cpfs_invalidos', pd.DataFrame()).empty:
                pdf.add_page()
                pdf.set_font("Arial", 'B', 12)
                pdf.cell(0, 10, "Tabela 2: CPFs com Caracteres Inválidos", 0, 1)
                pdf.set_font("Arial", '', 10)
                
                df_cpfs_invalidos = problemas_cpf['detalhes_cpfs_invalidos'].head(50)
                headers = ['Linha', 'CPF Original', 'CPF Processado', 'Nome']
                col_widths = [20, 40, 40, 90]
                
                pdf.add_table_header(headers, col_widths)
                
                for idx, row in df_cpfs_invalidos.iterrows():
                    pdf.add_table_row([
                        str(row['Linha_Planilha']),
                        str(row['CPF_Original']),
                        str(row['CPF_Processado']),
                        str(row.get('Nome', ''))
                    ], col_widths)
            
            if not problemas_cpf.get('detalhes_inconsistencias', pd.DataFrame()).empty:
                pdf.add_page()
                pdf.set_font("Arial", 'B', 12)
                pdf.cell(0, 10, "Tabela 3: CPFs com Inconsistências Críticas", 0, 1)
                pdf.set_font("Arial", '', 10)
                
                df_inconsistencias = problemas_cpf['detalhes_inconsistencias'].head(50)
                headers = ['CPF', 'Linha', 'Ocorrência', 'Problemas', 'Nome']
                col_widths = [40, 20, 30, 60, 50]
                
                pdf.add_table_header(headers, col_widths)
                
                for idx, row in df_inconsistencias.iterrows():
                    pdf.add_table_row([
                        str(row['CPF']),
                        str(row['Linha_Planilha']),
                        str(row['Ocorrencia_CPF']),
                        str(row['Problemas_Inconsistencia']),
                        str(row.get('Nome', ''))
                    ], col_widths)
    
    return pdf.output(dest='S').encode('latin1')

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
                    'Valor Total (Valor Pagto)',
                    'Pagamentos Duplicados',
                    'Valor em Duplicidades',
                    'Projetos Ativos',
                    'CPFs para Ajuste',
                    'Registros Críticos'
                ],
                'Valor': [
                    data_hora_atual_brasilia(),
                    metrics.get('total_pagamentos', 0),
                    metrics.get('beneficiarios_unicos', 0),
                    metrics.get('contas_unicas', 0),
                    metrics.get('valor_total', 0),
                    metrics.get('pagamentos_duplicados', 0),
                    metrics.get('valor_total_duplicados', 0),
                    metrics.get('projetos_ativos', 0),
                    metrics.get('total_cpfs_ajuste', 0),
                    metrics.get('total_registros_criticos', 0)
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
                    metrics.get('total_contas_abertas', 0),
                    metrics.get('beneficiarios_contas', 0),
                    metrics.get('projetos_ativos', 0),
                    metrics.get('total_registros_criticos', 0)
                ]
            }
        
        pd.DataFrame(resumo_data).to_excel(writer, sheet_name='Resumo Executivo', index=False)
        
        if tipo_relatorio == 'pagamentos':
            # Duplicidades detalhadas
            duplicidades_detalhadas = metrics.get('duplicidades_detalhadas', {})
            resumo_duplicidades = duplicidades_detalhadas.get('resumo_duplicidades', pd.DataFrame())
            if not resumo_duplicidades.empty:
                resumo_duplicidades.to_excel(writer, sheet_name='Duplicidades', index=False)
            
            # Pagamentos pendentes
            pagamentos_pendentes = metrics.get('pagamentos_pendentes', {})
            contas_sem_pagamento = pagamentos_pendentes.get('contas_sem_pagamento', pd.DataFrame())
            if not contas_sem_pagamento.empty:
                contas_sem_pagamento.to_excel(writer, sheet_name='Pagamentos Pendentes', index=False)
        
        # Problemas de CPF
        problemas_cpf = metrics.get('problemas_cpf', {})
        
        # Tabela de CPFs vazios
        detalhes_cpfs_vazios = problemas_cpf.get('detalhes_cpfs_vazios', pd.DataFrame())
        if not detalhes_cpfs_vazios.empty:
            detalhes_cpfs_vazios.to_excel(writer, sheet_name='CPFs Vazios', index=False)
        
        # Tabela de CPFs com caracteres inválidos
        detalhes_cpfs_invalidos = problemas_cpf.get('detalhes_cpfs_invalidos', pd.DataFrame())
        if not detalhes_cpfs_invalidos.empty:
            detalhes_cpfs_invalidos.to_excel(writer, sheet_name='CPFs Inválidos', index=False)
        
        # Tabela de CPFs com tamanho incorreto
        detalhes_cpfs_tamanho = problemas_cpf.get('detalhes_cpfs_tamanho_incorreto', pd.DataFrame())
        if not detalhes_cpfs_tamanho.empty:
            detalhes_cpfs_tamanho.to_excel(writer, sheet_name='CPFs Tamanho', index=False)
        
        # Tabela original de problemas de CPF
        detalhes_cpfs_problematicos = problemas_cpf.get('detalhes_cpfs_problematicos', pd.DataFrame())
        if not detalhes_cpfs_problematicos.empty:
            detalhes_cpfs_problematicos.to_excel(writer, sheet_name='CPFs Formatação', index=False)
        
        detalhes_inconsistencias = problemas_cpf.get('detalhes_inconsistencias', pd.DataFrame())
        if not detalhes_inconsistencias.empty:
            detalhes_inconsistencias.to_excel(writer, sheet_name='CPFs Inconsistentes', index=False)
        
        # Problemas críticos
        resumo_ausencias = metrics.get('resumo_ausencias', pd.DataFrame())
        if not resumo_ausencias.empty:
            resumo_ausencias.to_excel(writer, sheet_name='Problemas Críticos', index=False)
    
    return output.getvalue()

def gerar_planilha_ajustes(metrics, tipo_relatorio='pagamentos'):
    """Gera planilha com ações recomendadas"""
    output = io.BytesIO()
    
    acoes = []
    
    if tipo_relatorio == 'pagamentos':
        # Ações para duplicidades
        pagamentos_duplicados = metrics.get('pagamentos_duplicados', 0)
        if pagamentos_duplicados > 0:
            acoes.append({
                'Tipo': 'Duplicidade',
                'Descrição': f'Verificar {pagamentos_duplicados} contas com pagamentos duplicados',
                'Ação Recomendada': 'Auditar pagamentos e ajustar contas duplicadas',
                'Prioridade': 'Alta',
                'Impacto Financeiro': formatar_brasileiro(metrics.get('valor_total_duplicados', 0), 'monetario')
            })
        
        # Ações para CPFs problemáticos
        problemas_cpf = metrics.get('problemas_cpf', {})
        
        total_cpfs_inconsistentes = problemas_cpf.get('total_cpfs_inconsistentes', 0)
        if total_cpfs_inconsistentes > 0:
            acoes.append({
                'Tipo': 'CPF Inconsistente',
                'Descrição': f'{total_cpfs_inconsistentes} CPFs com nomes ou contas diferentes',
                'Ação Recomendada': 'Verificar e corrigir inconsistências nos CPFs duplicados',
                'Prioridade': 'Crítica',
                'Impacto Financeiro': 'Risco de fraude e irregularidade'
            })
        
        total_problemas_cpf = problemas_cpf.get('total_problemas_cpf', 0)
        if total_problemas_cpf > 0:
            acoes.append({
                'Tipo': 'CPF Formatação',
                'Descrição': f'{total_problemas_cpf} CPFs com problemas de formatação',
                'Ação Recomendada': 'Corrigir formatação dos CPFs (apenas números, 11 dígitos)',
                'Prioridade': 'Alta',
                'Impacto Financeiro': 'Risco fiscal/documental'
            })
        
        # Ações para pagamentos pendentes
        pagamentos_pendentes = metrics.get('pagamentos_pendentes', {})
        total_contas_sem_pagamento = pagamentos_pendentes.get('total_contas_sem_pagamento', 0)
        if total_contas_sem_pagamento > 0:
            acoes.append({
                'Tipo': 'Pagamento Pendente',
                'Descrição': f'{total_contas_sem_pagamento} contas aguardando pagamento',
                'Ação Recomendada': 'Regularizar pagamentos pendentes',
                'Prioridade': 'Média',
                'Impacto Financeiro': 'A definir'
            })
    
    # Ações para problemas críticos
    total_registros_criticos = metrics.get('total_registros_criticos', 0)
    if total_registros_criticos > 0:
        acoes.append({
            'Tipo': 'Dados Críticos Incompletos',
            'Descrição': f'{total_registros_criticos} registros com problemas críticos (sem conta ou valor)',
            'Ação Recomendada': 'Completar informações faltantes essenciais',
            'Prioridade': 'Alta',
            'Impacto Financeiro': 'Risco operacional'
        })
    
    df_acoes = pd.DataFrame(acoes)
    df_acoes.to_excel(output, index=False)
    
    return output.getvalue()

def gerar_csv_dados_tratados(dados, tipo_dados='pagamentos'):
    """Gera arquivos CSV com dados tratados"""
    if tipo_dados == 'pagamentos' and 'pagamentos' in dados and not dados['pagamentos'].empty:
        df = dados['pagamentos'].copy()
        return df
    
    elif tipo_dados == 'inscricoes' and 'contas' in dados and not dados['contas'].empty:
        df = dados['contas'].copy()
        return df
    
    return pd.DataFrame()

# ========== FUNÇÕES DE CARREGAMENTO DE DADOS ==========
def carregar_dados(conn, email_usuario):
    """Carrega dados do usuário - CORREÇÃO: MANTÉM DADOS EXISTENTES NO session_state"""
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
    
    # Inicializar dados no session_state se não existirem
    if 'dados_carregados' not in st.session_state:
        st.session_state.dados_carregados = {}
    if 'nomes_arquivos_carregados' not in st.session_state:
        st.session_state.nomes_arquivos_carregados = {}
    if 'mes_ref_carregado' not in st.session_state:
        st.session_state.mes_ref_carregado = None
    if 'ano_ref_carregado' not in st.session_state:
        st.session_state.ano_ref_carregado = None
    
    # Detectar mês/ano dos nomes dos arquivos
    mes_ref_detectado = None
    ano_ref_detectado = None
    arquivo_que_detectou = None
    
    # PRIORIDADE: Usar nome do arquivo para detectar mês/ano
    if upload_pagamentos:
        mes_ref, ano_ref = extrair_mes_ano_arquivo(upload_pagamentos.name)
        if mes_ref and ano_ref:
            mes_ref_detectado = mes_ref
            ano_ref_detectado = ano_ref
            arquivo_que_detectou = upload_pagamentos.name
            st.sidebar.info(f"📅 Detectado no arquivo '{upload_pagamentos.name}': {mes_ref}/{ano_ref}")
    
    if upload_contas and (not mes_ref_detectado or not ano_ref_detectado):
        mes_ref, ano_ref = extrair_mes_ano_arquivo(upload_contas.name)
        if mes_ref and ano_ref:
            mes_ref_detectado = mes_ref
            ano_ref_detectado = ano_ref
            arquivo_que_detectou = upload_contas.name
            st.sidebar.info(f"📅 Detectado no arquivo '{upload_contas.name}': {mes_ref}/{ano_ref}")
    
    # Seleção de mês e ano - CORREÇÃO: Usar valores detectados OU valores já carregados
    col1, col2 = st.sidebar.columns(2)
    with col1:
        meses = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
        
        # Prioridade: 1. Detectado no arquivo, 2. Já carregado, 3. Mês atual
        if mes_ref_detectado:
            mes_ref_padrao = mes_ref_detectado
        elif st.session_state.mes_ref_carregado:
            mes_ref_padrao = st.session_state.mes_ref_carregado
        else:
            mes_atual_num = agora_brasilia().month
            meses_numeros = {
                1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
                5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
                9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
            }
            mes_ref_padrao = meses_numeros.get(mes_atual_num, 'Janeiro')
        
        # Encontrar índice correto
        if mes_ref_padrao in meses:
            mes_index = meses.index(mes_ref_padrao)
        else:
            mes_index = 0
            
        mes_ref = st.selectbox("Mês de Referência", meses, index=mes_index)
        
    with col2:
        # Prioridade: 1. Detectado no arquivo, 2. Já carregado, 3. Ano atual
        if ano_ref_detectado:
            ano_ref_padrao = ano_ref_detectado
        elif st.session_state.ano_ref_carregado:
            ano_ref_padrao = st.session_state.ano_ref_carregado
        else:
            ano_ref_padrao = agora_brasilia().year
        
        ano_atual = agora_brasilia().year
        anos = list(range(ano_atual, ano_atual - 5, -1))
        
        # Encontrar índice correto
        if ano_ref_padrao in anos:
            ano_index = anos.index(ano_ref_padrao)
        else:
            ano_index = 0
            
        ano_ref = st.selectbox("Ano de Referência", anos, index=ano_index)
    
    st.sidebar.markdown("---")
    
    # Inicializar variáveis com dados já carregados
    dados = st.session_state.dados_carregados.copy()
    nomes_arquivos = st.session_state.nomes_arquivos_carregados.copy()
    dados_processados = False
    
    # CORREÇÃO: SÓ VERIFICAR DUPLICIDADE DEPOIS DE PROCESSAR O ARQUIVO
    # Processar pagamentos
    if upload_pagamentos:
        df = processar_arquivo(upload_pagamentos, 'pagamentos')
        if df is not None:
            # AGORA verificar duplicidade
            arquivos_existentes = verificar_duplicidade_periodo(conn, mes_ref, ano_ref, 'pagamentos')
            
            if arquivos_existentes:
                st.sidebar.warning(f"⚠️ Já existem {len(arquivos_existentes)} arquivo(s) de pagamentos para {mes_ref}/{ano_ref}:")
                for arquivo in arquivos_existentes:
                    st.sidebar.info(f"• {arquivo[0]} (importado em {arquivo[1]})")
                
                # Pedir confirmação para continuar
                if st.sidebar.checkbox(f"Continuar mesmo assim (sobrescreverá dados existentes para {mes_ref}/{ano_ref})", key="pagamentos_checkbox"):
                    pass
                else:
                    st.sidebar.error("Upload cancelado pelo usuário.")
                    # Retornar dados existentes sem processar novo upload
                    return dados, nomes_arquivos, mes_ref, ano_ref, False
            
            nomes_arquivos['pagamentos'] = upload_pagamentos.name
            
            # Identificar e remover linha de totais
            linha_totais, df_sem_totais = identificar_linha_totais(df)
            df = df_sem_totais
            
            # Processar dados
            df = processar_colunas_valor(df)
            df = processar_colunas_data(df)
            df = padronizar_documentos(df)
            
            # CORREÇÃO: Adicionar dados SEM apagar os existentes
            dados['pagamentos'] = df
            
            # Salvar no banco
            metadados = {
                'total_registros_originais': len(df),
                'colunas_disponiveis': df.columns.tolist(),
                'tipo_arquivo': 'pagamentos',
                'linha_totais_removida': linha_totais is not None
            }
            
            if salvar_pagamentos_db(conn, mes_ref, ano_ref, upload_pagamentos.name, 
                                   upload_pagamentos.getvalue(), df, metadados, email_usuario):
                dados_processados = True
            
            df_validos = filtrar_pagamentos_validos(df)
            total_invalidos = len(df) - len(df_validos)
            st.sidebar.success(f"✅ Pagamentos: {len(df_validos)} válidos + {total_invalidos} sem conta")
            
            if linha_totais is not None:
                st.sidebar.info("📝 Linha de totais identificada e removida da análise")
    
    # Processar inscrições
    if upload_contas:
        df = processar_arquivo(upload_contas, 'inscrições')
        if df is not None:
            # AGORA verificar duplicidade
            arquivos_existentes = verificar_duplicidade_periodo(conn, mes_ref, ano_ref, 'inscricoes')
            
            if arquivos_existentes:
                st.sidebar.warning(f"⚠️ Já existem {len(arquivos_existentes)} arquivo(s) de inscrições para {mes_ref}/{ano_ref}:")
                for arquivo in arquivos_existentes:
                    st.sidebar.info(f"• {arquivo[0]} (importado em {arquivo[1]})")
                
                # Pedir confirmação para continuar
                if st.sidebar.checkbox(f"Continuar mesmo assim (sobrescreverá dados existentes para {mes_ref}/{ano_ref})", key="inscricoes_checkbox"):
                    pass
                else:
                    st.sidebar.error("Upload cancelado pelo usuário.")
                    # Retornar dados existentes sem processar novo upload
                    return dados, nomes_arquivos, mes_ref, ano_ref, False
            
            nomes_arquivos['contas'] = upload_contas.name
            
            df = processar_colunas_data(df)
            df = padronizar_documentos(df)
            
            # CORREÇÃO: Adicionar dados SEM apagar os existentes
            dados['contas'] = df
            
            # Salvar no banco
            metadados = {
                'total_registros': len(df),
                'colunas_disponiveis': df.columns.tolist(),
                'tipo_arquivo': 'inscricoes'
            }
            
            if salvar_inscricoes_db(conn, mes_ref, ano_ref, upload_contas.name, 
                                   upload_contas.getvalue(), df, metadados, email_usuario):
                dados_processados = True
            
            st.sidebar.success(f"✅ Inscrições: {len(df)} registros")
    
    # CORREÇÃO: Atualizar session_state apenas se houve processamento bem-sucedido
    if dados_processados:
        st.session_state.dados_carregados = dados.copy()
        st.session_state.nomes_arquivos_carregados = nomes_arquivos.copy()
        st.session_state.mes_ref_carregado = mes_ref
        st.session_state.ano_ref_carregado = ano_ref
    
    return dados, nomes_arquivos, mes_ref, ano_ref, dados_processados

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

# ========== FUNÇÕES ADMINISTRATIVAS ==========
def gerenciar_usuarios(conn):
    """Interface para gerenciamento de usuários"""
    st.header("👥 Gerenciamento de Usuários")
    
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

def gerenciar_registros(conn, email_admin):
    """Permite visualizar e excluir registros específicos"""
    st.header("🔍 Gerenciamento de Registros")
    
    tipo_dados = st.selectbox("Tipo de dados:", ["Pagamentos", "Inscrições", "Métricas", "Logs"])
    
    if tipo_dados == "Pagamentos":
        dados = carregar_pagamentos_db(conn)
    elif tipo_dados == "Inscrições":
        dados = carregar_inscricoes_db(conn)
    elif tipo_dados == "Métricas":
        dados = carregar_metricas_db(conn)
    else:
        dados = pd.read_sql_query("SELECT * FROM logs_admin ORDER BY data_hora DESC", conn)
    
    if not dados.empty:
        st.write(f"**Total de registros:** {len(dados)}")
        st.dataframe(dados.head(20), use_container_width=True)
        
        if tipo_dados in ["Pagamentos", "Inscrições", "Métricas"]:
            st.subheader("Excluir Registro Específico")
            id_excluir = st.number_input("ID do registro a excluir:", min_value=1, step=1)
            
            if st.button("🗑️ Excluir Registro", type="secondary"):
                if id_excluir:
                    try:
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
    st.header("🚨 Limpeza do Banco de Dados")
    st.error("**ATENÇÃO CRÍTICA:** Esta operação é IRREVERSÍVEL!")
    
    st.warning("""
    **Efeitos desta operação:**
    - ❌ Todos os dados de pagamentos serão PERDIDOS
    - ❌ Todos os dados de inscrições serão PERDIDOS  
    - ❌ Todas as métricas históricas serão PERDIDAS
    - 🔄 O sistema recomeçará do ZERO
    """)
    
    senha_confirmacao1 = st.text_input("Digite 'LIMPAR TUDO' para confirmar:", type="password")
    senha_confirmacao2 = st.text_input("Digite novamente 'LIMPAR TUDO':", type="password")
    
    if st.button("🗑️ LIMPAR TODOS OS DADOS", type="secondary"):
        if senha_confirmacao1 == "LIMPAR TUDO" and senha_confirmacao2 == "LIMPAR TUDO":
            try:
                registrar_log_admin(conn, email_admin, "LIMPEZA_COMPLETA", "TODOS", None, "Limpeza completa do banco")
                
                conn.execute("DELETE FROM pagamentos")
                conn.execute("DELETE FROM inscricoes")
                conn.execute("DELETE FROM metricas_mensais")
                
                conn.commit()
                st.success("✅ Banco de dados limpo COMPLETAMENTE!")
                st.info("🔄 Recarregue a página para começar novamente")
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
    
    metricas_pag = metricas[metricas['tipo'] == 'pagamentos']
    metricas_ins = metricas[metricas['tipo'] == 'inscricoes']
    
    if not metricas_pag.empty:
        metricas_pag['periodo'] = metricas_pag['mes_referencia'] + '/' + metricas_pag['ano_referencia'].astype(str)
        metricas_pag = metricas_pag.sort_values(['ano_referencia', 'mes_referencia'])
    
    if not metricas_ins.empty:
        metricas_ins['periodo'] = metricas_ins['mes_referencia'] + '/' + metricas_ins['ano_referencia'].astype(str)
        metricas_ins = metricas_ins.sort_values(['ano_referencia', 'mes_referencia'])
    
    col1, col2 = st.columns(2)
    
    with col1:
        if not metricas_pag.empty:
            st.subheader("Evolução de Pagamentos")
            fig = px.line(metricas_pag, x='periodo', y='total_registros',
                         title='Total de Pagamentos por Mês')
            st.plotly_chart(fig, use_container_width=True)
            
            if 'valor_total' in metricas_pag.columns:
                fig2 = px.line(metricas_pag, x='periodo', y='valor_total',
                             title='Valor Total dos Pagamentos')
                st.plotly_chart(fig2, use_container_width=True)
    
    with col2:
        if not metricas_ins.empty:
            st.subheader("Evolução de Inscrições")
            fig = px.line(metricas_ins, x='periodo', y='total_registros',
                         title='Total de Inscrições por Mês')
            st.plotly_chart(fig, use_container_width=True)
            
            if 'beneficiarios_unicos' in metricas_ins.columns:
                fig2 = px.line(metricas_ins, x='periodo', y='beneficiarios_unicos',
                             title='Beneficiários Únicos por Mês')
                st.plotly_chart(fig2, use_container_width=True)

def mostrar_relatorios_comparativos(conn):
    """Mostra relatórios comparativos"""
    st.header("📋 Relatórios Comparativos")
    
    metricas = carregar_metricas_db(conn, tipo='pagamentos')
    
    if metricas.empty:
        st.info("📊 Nenhum dado disponível para comparação.")
        return
    
    # Comparação entre períodos
    st.subheader("Comparação entre Períodos")
    
    metricas['periodo'] = metricas['mes_referencia'] + '/' + metricas['ano_referencia'].astype(str)
    periodos_disponiveis = metricas['periodo'].unique()
    
    if len(periodos_disponiveis) < 2:
        st.info("É necessário pelo menos 2 períodos para comparação.")
        return
    
    col1, col2 = st.columns(2)
    
    with col1:
        periodo1 = st.selectbox("Selecione o primeiro período:", periodos_disponiveis, key="periodo1")
    
    with col2:
        periodo2 = st.selectbox("Selecione o segundo período:", periodos_disponiveis, 
                               index=1 if len(periodos_disponiveis) > 1 else 0, key="periodo2")
    
    if periodo1 == periodo2:
        st.warning("Selecione períodos diferentes para comparação.")
        return
    
    dados_periodo1 = metricas[metricas['periodo'] == periodo1].iloc[0]
    dados_periodo2 = metricas[metricas['periodo'] == periodo2].iloc[0]
    
    st.subheader(f"Comparação: {periodo1} vs {periodo2}")
    
    comparativo_data = {
        'Métrica': [
            'Total de Pagamentos',
            'Beneficiários Únicos',
            'Contas Únicas',
            'Valor Total',
            'Pagamentos Duplicados',
            'Valor em Duplicidades',
            'Projetos Ativos',
            'CPFs para Ajuste',
            'Registros Críticos'
        ],
        periodo1: [
            formatar_brasileiro(dados_periodo1['total_registros']),
            formatar_brasileiro(dados_periodo1['beneficiarios_unicos']),
            formatar_brasileiro(dados_periodo1['contas_unicas']),
            formatar_brasileiro(dados_periodo1['valor_total'], 'monetario'),
            formatar_brasileiro(dados_periodo1['pagamentos_duplicados']),
            formatar_brasileiro(dados_periodo1['valor_duplicados'], 'monetario'),
            formatar_brasileiro(dados_periodo1['projetos_ativos']),
            formatar_brasileiro(dados_periodo1.get('cpfs_ajuste', 0)),
            formatar_brasileiro(dados_periodo1['registros_problema'])
        ],
        periodo2: [
            formatar_brasileiro(dados_periodo2['total_registros']),
            formatar_brasileiro(dados_periodo2['beneficiarios_unicos']),
            formatar_brasileiro(dados_periodo2['contas_unicas']),
            formatar_brasileiro(dados_periodo2['valor_total'], 'monetario'),
            formatar_brasileiro(dados_periodo2['pagamentos_duplicados']),
            formatar_brasileiro(dados_periodo2['valor_duplicados'], 'monetario'),
            formatar_brasileiro(dados_periodo2['projetos_ativos']),
            formatar_brasileiro(dados_periodo2.get('cpfs_ajuste', 0)),
            formatar_brasileiro(dados_periodo2['registros_problema'])
        ]
    }
    
    df_comparativo = pd.DataFrame(comparativo_data)
    st.dataframe(df_comparativo, use_container_width=True)

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
    
    metricas['periodo'] = metricas['mes_referencia'] + '/' + metricas['ano_referencia'].astype(str)
    
    fig = px.bar(metricas, x='periodo', y='total_registros',
                 title='Distribuição de Pagamentos por Mês')
    st.plotly_chart(fig, use_container_width=True)

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
        
        if metrics.get('linha_totais_removida', False):
            st.info(f"📝 **Nota:** Linha de totais da planilha foi identificada e excluída da análise")
        
        st.markdown("---")
        
        if tem_pagamentos:
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total de Pagamentos", 
                         formatar_brasileiro(metrics.get('total_pagamentos', 0)),
                         help="Pagamentos válidos com número de conta")
            
            with col2:
                st.metric("Beneficiários Únicos", 
                         formatar_brasileiro(metrics.get('beneficiarios_unicos', 0)))
            
            with col3:
                st.metric("Contas Únicas", 
                         formatar_brasileiro(metrics.get('contas_unicas', 0)))
            
            with col4:
                st.metric("Valor Total (Valor Pagto)", 
                         formatar_brasileiro(metrics.get('valor_total', 0), 'monetario'),
                         help="Somatória dos valores da coluna Valor Pagto")
            
            col5, col6, col7, col8 = st.columns(4)
            
            with col5:
                st.metric("Pagamentos Duplicados", 
                         formatar_brasileiro(metrics.get('pagamentos_duplicados', 0)),
                         delta=f"-{formatar_brasileiro(metrics.get('valor_total_duplicados', 0), 'monetario')}",
                         delta_color="inverse",
                         help="Contas com múltiplos pagamentos")
            
            with col6:
                st.metric("Projetos Ativos", 
                         formatar_brasileiro(metrics.get('projetos_ativos', 0)))
            
            with col7:
                total_cpfs = metrics.get('total_cpfs_ajuste', 0)
                problemas_cpf = metrics.get('problemas_cpf', {})
                help_text = f"CPFs com problemas: {problemas_cpf.get('total_problemas_cpf', 0)} formatação + {problemas_cpf.get('total_cpfs_inconsistentes', 0)} inconsistências"
                st.metric("CPFs p/ Ajuste", 
                         formatar_brasileiro(total_cpfs),
                         delta_color="inverse" if total_cpfs > 0 else "off",
                         help=help_text)
            
            with col8:
                st.metric("Registros Críticos", 
                         formatar_brasileiro(metrics.get('total_registros_criticos', 0)),
                         delta_color="inverse" if metrics.get('total_registros_criticos', 0) > 0 else "off",
                         help="Registros INVÁLIDOS (sem conta ou valor)")
        
        if tem_contas:
            st.markdown("---")
            st.subheader("📋 Dados de Inscrições/Contas")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total de Inscrições", formatar_brasileiro(metrics.get('total_contas_abertas', 0)))
            with col2:
                st.metric("Beneficiários Únicos", formatar_brasileiro(metrics.get('beneficiarios_contas', 0)))
            with col3:
                st.metric("Projetos Ativos", formatar_brasileiro(metrics.get('projetos_ativos', 0)))
        
        st.markdown("---")
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "📋 Visão Geral", "⚠️ Duplicidades", "🔴 CPFs Problemáticos", 
            "📋 CPFs Vazios", "⏳ Pagamentos Pendentes", "🚨 Problemas Críticos"
        ])
        
        with tab1:
            st.subheader("Resumo dos Dados")
            if tem_pagamentos:
                st.write(f"**Planilha de Pagamentos:** {nomes_arquivos.get('pagamentos', 'N/A')}")
                st.write(f"**Total de registros válidos:** {metrics.get('total_pagamentos', 0)}")
                st.write(f"**Registros sem conta:** {metrics.get('total_registros_invalidos', 0)}")
            
            if tem_contas:
                st.write(f"**Planilha de Inscrições:** {nomes_arquivos.get('contas', 'N/A')}")
                st.write(f"**Total de inscrições:** {metrics.get('total_contas_abertas', 0)}")
                st.write(f"**Beneficiários únicos:** {metrics.get('beneficiarios_contas', 0)}")
        
        with tab2:
            if tem_pagamentos:
                st.subheader("Pagamentos Duplicados")
                duplicidades = metrics.get('duplicidades_detalhadas', {})
                
                if duplicidades.get('total_contas_duplicadas', 0) > 0:
                    st.warning(f"🚨 {duplicidades['total_contas_duplicadas']} contas com pagamentos duplicados")
                    
                    if not duplicidades.get('resumo_duplicidades', pd.DataFrame()).empty:
                        st.write("**Resumo das Duplicidades:**")
                        st.dataframe(duplicidades['resumo_duplicidades'])
                else:
                    st.success("✅ Nenhum pagamento duplicado encontrado")
        
        with tab3:
            if tem_pagamentos:
                st.subheader("CPFs Problemáticos - Visão Geral")
                problemas = metrics.get('problemas_cpf', {})
                
                if problemas.get('total_problemas_cpf', 0) > 0 or problemas.get('total_cpfs_inconsistentes', 0) > 0:
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.error(f"❌ {problemas.get('total_cpfs_inconsistentes', 0)} CPFs com INCONSISTÊNCIAS")
                        if problemas.get('cpfs_com_nomes_diferentes'):
                            st.write(f"**CPFs com nomes diferentes:** {len(problemas['cpfs_com_nomes_diferentes'])}")
                        if problemas.get('cpfs_com_contas_diferentes'):
                            st.write(f"**CPFs com contas diferentes:** {len(problemas['cpfs_com_contas_diferentes'])}")
                    
                    with col2:
                        st.warning(f"⚠️ {problemas.get('total_problemas_cpf', 0)} CPFs com problemas de FORMATAÇÃO")
                        if problemas.get('cpfs_vazios'):
                            st.write(f"**CPFs vazios:** {len(problemas['cpfs_vazios'])}")
                        if problemas.get('cpfs_com_caracteres_invalidos'):
                            st.write(f"**CPFs com caracteres inválidos:** {len(problemas['cpfs_com_caracteres_invalidos'])}")
                        if problemas.get('cpfs_com_tamanho_incorreto'):
                            st.write(f"**CPFs com tamanho incorreto:** {len(problemas['cpfs_com_tamanho_incorreto'])}")
                    
                    # Detalhes de inconsistências
                    if not problemas.get('detalhes_inconsistencias', pd.DataFrame()).empty:
                        st.write("**CPFs com Inconsistências Críticas:**")
                        st.dataframe(problemas['detalhes_inconsistencias'])
                else:
                    st.success("✅ Nenhum problema com CPFs encontrado")
        
        with tab4:
            if tem_pagamentos:
                st.subheader("CPFs Vazios - Detalhes para Correção")
                problemas = metrics.get('problemas_cpf', {})
                
                if not problemas.get('detalhes_cpfs_vazios', pd.DataFrame()).empty:
                    st.warning(f"⚠️ {len(problemas['detalhes_cpfs_vazios'])} registros com CPFs vazios")
                    st.write("**Detalhes dos CPFs Vazios:**")
                    st.dataframe(problemas['detalhes_cpfs_vazios'], use_container_width=True)
                else:
                    st.success("✅ Nenhum CPF vazio encontrado")
                
                if not problemas.get('detalhes_cpfs_invalidos', pd.DataFrame()).empty:
                    st.write("**CPFs com Caracteres Inválidos:**")
                    st.dataframe(problemas['detalhes_cpfs_invalidos'], use_container_width=True)
                
                if not problemas.get('detalhes_cpfs_tamanho_incorreto', pd.DataFrame()).empty:
                    st.write("**CPFs com Tamanho Incorreto:**")
                    st.dataframe(problemas['detalhes_cpfs_tamanho_incorreto'], use_container_width=True)
        
        with tab5:
            if tem_pagamentos and tem_contas:
                st.subheader("Pagamentos Pendentes")
                pendentes = metrics.get('pagamentos_pendentes', {})
                
                if pendentes.get('total_contas_sem_pagamento', 0) > 0:
                    st.warning(f"⏳ {pendentes['total_contas_sem_pagamento']} contas aguardando pagamento")
                    
                    if not pendentes.get('contas_sem_pagamento', pd.DataFrame()).empty:
                        st.write("**Contas Aguardando Pagamento:**")
                        st.dataframe(pendentes['contas_sem_pagamento'])
                else:
                    st.success("✅ Todas as contas abertas possuem pagamentos registrados")
        
        with tab6:
            st.subheader("Problemas Críticos de Dados")
            
            total_registros_criticos = metrics.get('total_registros_criticos', 0)
            
            if total_registros_criticos > 0:
                st.error(f"🚨 {total_registros_criticos} registros com problemas críticos")
                
                resumo_ausencias = metrics.get('resumo_ausencias', pd.DataFrame())
                if not resumo_ausencias.empty:
                    st.write("**Registros com Problemas Críticos:**")
                    st.dataframe(resumo_ausencias)
            else:
                st.success("✅ Nenhum registro crítico encontrado")

# ========== FUNÇÃO PRINCIPAL ==========
def main():
    conn = init_database()
    
    if conn is None:
        st.error("❌ Não foi possível inicializar o banco de dados.")
        return
    
    email_autorizado, tipo_usuario = autenticar(conn)
    
    if not email_autorizado:
        st.title("🏛️ Sistema POT - SMDET")
        st.markdown("### Análise de Pagamentos e Contas")
        st.info("🔐 **Acesso Restrito** - Faça login para acessar")
        return
    
    # Inicializar session_state para dados persistentes
    if 'dados_carregados' not in st.session_state:
        st.session_state.dados_carregados = {}
    if 'nomes_arquivos_carregados' not in st.session_state:
        st.session_state.nomes_arquivos_carregados = {}
    if 'mes_ref_carregado' not in st.session_state:
        st.session_state.mes_ref_carregado = None
    if 'ano_ref_carregado' not in st.session_state:
        st.session_state.ano_ref_carregado = None
    if 'processed_metrics' not in st.session_state:
        st.session_state.processed_metrics = {}
    
    # Carregar dados (agora mantém dados anteriores)
    dados, nomes_arquivos, mes_ref, ano_ref, dados_processados = carregar_dados(conn, email_autorizado)
    
    tem_dados_pagamentos = 'pagamentos' in dados and not dados['pagamentos'].empty
    tem_dados_contas = 'contas' in dados and not dados['contas'].empty
    
    metrics = st.session_state.processed_metrics
    
    # CORREÇÃO: Processar métricas apenas se houve processamento bem-sucedido
    if dados_processados:
        with st.spinner("🔄 Processando dados..."):
            metrics = processar_dados(dados, nomes_arquivos)
            
            if tem_dados_pagamentos:
                salvar_metricas_db(conn, 'pagamentos', mes_ref, ano_ref, metrics)
            if tem_dados_contas:
                salvar_metricas_db(conn, 'inscricoes', mes_ref, ano_ref, metrics)
            
            st.session_state.processed_metrics = metrics
    elif st.session_state.processed_metrics:
        # Usar métricas já processadas se não houve novo processamento
        metrics = st.session_state.processed_metrics
    
    # Sidebar - Exportação de relatórios
    st.sidebar.markdown("---")
    st.sidebar.header("📥 EXPORTAR RELATÓRIOS")
    
    if tem_dados_pagamentos or tem_dados_contas:
        # Botão para PDF Executivo
        if tem_dados_pagamentos:
            pdf_bytes = gerar_pdf_executivo(metrics, dados, nomes_arquivos, 'pagamentos')
        elif tem_dados_contas:
            pdf_bytes = gerar_pdf_executivo(metrics, dados, nomes_arquivos, 'inscricoes')
        else:
            pdf_bytes = None
        
        if pdf_bytes:
            st.sidebar.download_button(
                label="📄 PDF Executivo",
                data=pdf_bytes,
                file_name=f"relatorio_executivo_pot_{mes_ref}_{ano_ref}_{data_hora_arquivo_brasilia()}.pdf",
                mime="application/pdf",
                use_container_width=True,
                key="pdf_executivo"
            )
        
        st.sidebar.markdown("---")
        
        if tem_dados_pagamentos:
            ajustes_bytes = gerar_planilha_ajustes(metrics, 'pagamentos')
        elif tem_dados_contas:
            ajustes_bytes = gerar_planilha_ajustes(metrics, 'inscricoes')
        else:
            ajustes_bytes = None
        
        if ajustes_bytes:
            st.sidebar.download_button(
                label="🔧 Planilha de Ajustes",
                data=ajustes_bytes,
                file_name=f"plano_ajustes_pot_{mes_ref}_{ano_ref}_{data_hora_arquivo_brasilia()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="planilha_ajustes"
            )
        
        # CSV dos dados tratados
        st.sidebar.markdown("---")
        st.sidebar.subheader("💾 Dados Tratados (CSV)")
        
        col3, col4 = st.sidebar.columns(2)
        
        with col3:
            if tem_dados_pagamentos:
                csv_pagamentos = gerar_csv_dados_tratados(dados, 'pagamentos')
                if not csv_pagamentos.empty:
                    st.sidebar.download_button(
                        label="📋 Pagamentos CSV",
                        data=csv_pagamentos.to_csv(index=False, encoding='utf-8-sig'),
                        file_name=f"pagamentos_tratados_{mes_ref}_{ano_ref}_{data_hora_arquivo_brasilia()}.csv",
                        mime="text/csv",
                        use_container_width=True,
                        key="csv_pagamentos"
                    )
        
        with col4:
            if tem_dados_contas:
                csv_inscricoes = gerar_csv_dados_tratados(dados, 'inscricoes')
                if not csv_inscricoes.empty:
                    st.sidebar.download_button(
                        label="📝 Inscrições CSV",
                        data=csv_inscricoes.to_csv(index=False, encoding='utf-8-sig'),
                        file_name=f"inscricoes_tratadas_{mes_ref}_{ano_ref}_{data_hora_arquivo_brasilia()}.csv",
                        mime="text/csv",
                        use_container_width=True,
                        key="csv_inscricoes"
                    )
    else:
        st.sidebar.info("📊 Faça upload dos dados para gerar relatórios")
    
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

if __name__ == "__main__":
    main()
