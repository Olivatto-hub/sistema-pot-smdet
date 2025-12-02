# app.py - SISTEMA POT COMPLETO COM RETIFICAÇÃO DE DADOS
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
from collections import defaultdict

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
        
        # Tabela de abertura de contas
        conn.execute('''
            CREATE TABLE IF NOT EXISTS abertura_contas (
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
        
        # Tabela de gestão de documentos
        conn.execute('''
            CREATE TABLE IF NOT EXISTS gestao_doc (
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
                total_contas_abertas INTEGER DEFAULT 0,
                beneficiarios_contas INTEGER DEFAULT 0,
                dados_retificados INTEGER DEFAULT 0,
                dados_corrigidos_json TEXT,
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_abertura_contas_mes_ano ON abertura_contas(mes_referencia, ano_referencia)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_gestao_doc_mes_ano ON gestao_doc(mes_referencia, ano_referencia)")
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

# ========== PADRONIZAÇÃO DE CABEÇALHOS ==========
def padronizar_cabecalhos(df):
    """Padroniza cabeçalhos removendo caracteres especiais e espaços"""
    if df.empty:
        return df
    
    novo_cabecalhos = {}
    
    for col in df.columns:
        if not isinstance(col, str):
            novo_cabecalhos[col] = str(col)
            continue
        
        col_limpa = str(col).strip()
        
        # Remover acentos e caracteres especiais
        col_limpa = re.sub(r'[áàâãä]', 'a', col_limpa, flags=re.IGNORECASE)
        col_limpa = re.sub(r'[éèêë]', 'e', col_limpa, flags=re.IGNORECASE)
        col_limpa = re.sub(r'[íìîï]', 'i', col_limpa, flags=re.IGNORECASE)
        col_limpa = re.sub(r'[óòôõö]', 'o', col_limpa, flags=re.IGNORECASE)
        col_limpa = re.sub(r'[úùûü]', 'u', col_limpa, flags=re.IGNORECASE)
        col_limpa = re.sub(r'[ç]', 'c', col_limpa, flags=re.IGNORECASE)
        col_limpa = re.sub(r'[ñ]', 'n', col_limpa, flags=re.IGNORECASE)
        
        # Remover caracteres especiais e manter apenas letras, números e espaço
        col_limpa = re.sub(r'[^\w\s]', '', col_limpa)
        
        # Remover espaços extras e substituir por underscore
        col_limpa = re.sub(r'\s+', '_', col_limpa.strip())
        
        # Converter para minúsculas
        col_limpa = col_limpa.lower()
        
        # Mapeamento de nomes comuns
        mapeamento = {
            'num_cartao': 'numero_conta',
            'numcartao': 'numero_conta',
            'n_cartao': 'numero_conta',
            'ncartao': 'numero_conta',
            'cartao': 'numero_conta',
            'conta': 'numero_conta',
            'n_conta': 'numero_conta',
            'nconta': 'numero_conta',
            'beneficiario': 'nome',
            'beneficiário': 'nome',
            'nome_completo': 'nome',
            'nome_beneficiario': 'nome',
            'valor_pagto': 'valor',
            'valor_pagamento': 'valor',
            'valor_pago': 'valor',
            'valor_pgto': 'valor',
            'data_pagto': 'data_pagamento',
            'data_pagamento': 'data_pagamento',
            'data_pgto': 'data_pagamento',
            'data_abertura': 'data_conta',
            'data_conta': 'data_conta',
            'dt_abertura': 'data_conta',
            'cpf': 'cpf',
            'rg': 'rg',
            'projeto': 'projeto',
            'banco': 'banco',
            'agencia': 'agencia',
            'conta_corrente': 'conta_corrente',
            'status': 'status',
            'observacao': 'observacao',
            'obs': 'observacao',
            'telefone': 'telefone',
            'celular': 'telefone',
            'email': 'email',
            'endereco': 'endereco',
            'bairro': 'bairro',
            'cidade': 'cidade',
            'uf': 'uf',
            'cep': 'cep'
        }
        
        # Aplicar mapeamento
        col_limpa = mapeamento.get(col_limpa, col_limpa)
        
        novo_cabecalhos[col] = col_limpa
    
    df = df.rename(columns=novo_cabecalhos)
    return df

# ========== DETECÇÃO AUTOMÁTICA DE MÊS/ANO ==========
def extrair_mes_ano_arquivo(nome_arquivo):
    """Extrai mês e ano do nome do arquivo"""
    if not nome_arquivo:
        return None, None
    
    nome_upper = nome_arquivo.upper()
    
    # Mapeamento completo
    meses_map = {
        'JAN': 'Janeiro', 'JANEIRO': 'Janeiro',
        'FEV': 'Fevereiro', 'FEVEREIRO': 'Fevereiro',
        'MAR': 'Março', 'MARCO': 'Março', 'MARÇO': 'Março', 'MAR.C': 'Março',
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
    
    # Padrões mais abrangentes
    padroes = [
        # Formato: JANEIRO-2024, JANEIRO_2024, JANEIRO2024
        (r'(JANEIRO|FEVEREIRO|MAR[ÇCCO]O|ABRIL|MAIO|JUNHO|JULHO|AGOSTO|SETEMBRO|OUTUBRO|NOVEMBRO|DEZEMBRO)[_\- ]?(\d{4})', 1, 2),
        # Formato: JAN-2024, FEV-2024, etc
        (r'(JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)[_\- ]?(\d{4})', 1, 2),
        # Formato: 01-2024, 02-2024, etc
        (r'(\d{1,2})[_\-/](\d{4})', 1, 2),
        # Formato: 2024-01, 2024-02, etc
        (r'(\d{4})[_\-/](\d{1,2})', 2, 1),
        # Formato: 012024, 022024, etc
        (r'(\d{2})(\d{4})', 1, 2),
        # Formato: 202401, 202402, etc
        (r'(\d{4})(\d{2})', 2, 1),
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
        
        # Se não encontrou mês, retornar apenas ano
        return None, ano
    
    return None, None

def detectar_mes_ano_dados(df, tipo_planilha):
    """Detecta mês e ano dos dados nas colunas de data"""
    if df.empty:
        return None, None
    
    # Lista de colunas de data para verificar
    colunas_data = []
    
    for col in df.columns:
        col_lower = str(col).lower()
        if any(termo in col_lower for termo in ['data', 'dt', 'date']):
            colunas_data.append(col)
    
    if not colunas_data:
        return None, None
    
    meses = []
    anos = []
    
    for col_data in colunas_data:
        try:
            # Converter para datetime
            df[col_data] = pd.to_datetime(df[col_data], errors='coerce', dayfirst=True)
            
            # Remover valores nulos
            datas_validas = df[col_data].dropna()
            
            if not datas_validas.empty:
                # Encontrar moda (valor mais comum)
                try:
                    mes_comum = datas_validas.dt.month.mode()
                    ano_comum = datas_validas.dt.year.mode()
                    
                    if not mes_comum.empty:
                        meses.append(int(mes_comum.iloc[0]))
                    if not ano_comum.empty:
                        anos.append(int(ano_comum.iloc[0]))
                except:
                    # Se não conseguir moda, pega o mais frequente
                    try:
                        mes_comum = datas_validas.dt.month.value_counts().index[0]
                        ano_comum = datas_validas.dt.year.value_counts().index[0]
                        meses.append(mes_comum)
                        anos.append(ano_comum)
                    except:
                        pass
        except:
            continue
    
    if meses and anos:
        # Usar o mês e ano mais frequentes
        from collections import Counter
        mes_final = Counter(meses).most_common(1)[0][0] if meses else None
        ano_final = Counter(anos).most_common(1)[0][0] if anos else None
        
        if mes_final and ano_final:
            meses_numeros = {
                1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
                5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
                9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
            }
            return meses_numeros.get(mes_final), ano_final
    
    return None, None

def detectar_mes_ano_completo(nome_arquivo, df, tipo_planilha):
    """Detecta mês e ano de forma completa"""
    # Tentar do nome do arquivo primeiro
    mes_nome, ano_nome = extrair_mes_ano_arquivo(nome_arquivo)
    
    # Se não encontrou no nome, tentar dos dados
    if not mes_nome or not ano_nome:
        mes_dados, ano_dados = detectar_mes_ano_dados(df, tipo_planilha)
        
        # Priorizar dados se encontrou
        if mes_dados and ano_dados:
            return mes_dados, ano_dados
        elif ano_dados:
            # Se só tem ano, usar mês atual como fallback
            mes_atual = agora_brasilia().month
            meses_numeros = {
                1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
                5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
                9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
            }
            return meses_numeros.get(mes_atual), ano_dados
    
    return mes_nome, ano_nome

# ========== FUNÇÕES DE PROCESSAMENTO DE ARQUIVOS ==========
def processar_arquivo(uploaded_file, tipo_arquivo='pagamentos'):
    """Processa arquivo de forma robusta com padronização"""
    try:
        if uploaded_file is None:
            return None
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_path = tmp_file.name
        
        try:
            if uploaded_file.name.endswith('.xlsx'):
                try:
                    df = pd.read_excel(tmp_path, engine='openpyxl', dtype=str)
                except:
                    df = pd.read_excel(tmp_path, engine='xlrd', dtype=str)
            elif uploaded_file.name.endswith('.csv'):
                try:
                    # Tentar diferentes encodings e separadores
                    df = pd.read_csv(tmp_path, encoding='utf-8', sep=None, engine='python', dtype=str)
                except:
                    try:
                        df = pd.read_csv(tmp_path, encoding='latin-1', sep=None, engine='python', dtype=str)
                    except:
                        df = pd.read_csv(tmp_path, encoding='cp1252', sep=None, engine='python', dtype=str)
            else:
                st.error(f"Formato não suportado: {uploaded_file.name}")
                os.unlink(tmp_path)
                return None
            
            os.unlink(tmp_path)
            
            if df.empty:
                st.warning(f"Arquivo {uploaded_file.name} está vazio")
                return None
            
            # Padronizar cabeçalhos
            df = padronizar_cabecalhos(df)
            
            return df
            
        except Exception as e:
            st.error(f"Erro ao processar {uploaded_file.name}: {str(e)}")
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            return None
            
    except Exception as e:
        st.error(f"Erro crítico: {str(e)}")
        return None

# ========== FUNÇÕES DE RETIFICAÇÃO DE DADOS ==========
def cruzar_dados_retificacao(dados_pagamentos, dados_contas, dados_gestao):
    """Cruza dados entre as planilhas para retificação"""
    retificacoes = {
        'total_retificacoes': 0,
        'detalhes_retificacoes': [],
        'dados_completados': {},
        'contas_sem_dados': [],
        'inconsistencias': []
    }
    
    # Verificar se temos dados suficientes
    if dados_contas.empty and dados_gestao.empty:
        return retificacoes
    
    # Criar dicionário de referência por número de conta
    dados_referencia = {}
    
    # Prioridade 1: Gestão de documentos (dados mais confiáveis)
    if not dados_gestao.empty and 'numero_conta' in dados_gestao.columns:
        for idx, row in dados_gestao.iterrows():
            conta = str(row['numero_conta']).strip() if pd.notna(row['numero_conta']) else None
            if conta and conta != 'nan':
                dados_referencia[conta] = {
                    'cpf': str(row['cpf']).strip() if 'cpf' in row and pd.notna(row['cpf']) else None,
                    'nome': str(row['nome']).strip() if 'nome' in row and pd.notna(row['nome']) else None,
                    'rg': str(row['rg']).strip() if 'rg' in row and pd.notna(row['rg']) else None,
                    'projeto': str(row['projeto']).strip() if 'projeto' in row and pd.notna(row['projeto']) else None,
                    'fonte': 'gestao_doc'
                }
    
    # Prioridade 2: Abertura de contas
    if not dados_contas.empty and 'numero_conta' in dados_contas.columns:
        for idx, row in dados_contas.iterrows():
            conta = str(row['numero_conta']).strip() if pd.notna(row['numero_conta']) else None
            if conta and conta != 'nan' and conta not in dados_referencia:
                dados_referencia[conta] = {
                    'cpf': str(row['cpf']).strip() if 'cpf' in row and pd.notna(row['cpf']) else None,
                    'nome': str(row['nome']).strip() if 'nome' in row and pd.notna(row['nome']) else None,
                    'rg': str(row['rg']).strip() if 'rg' in row and pd.notna(row['rg']) else None,
                    'projeto': str(row['projeto']).strip() if 'projeto' in row and pd.notna(row['projeto']) else None,
                    'fonte': 'abertura_contas'
                }
    
    # Aplicar retificações aos pagamentos
    if not dados_pagamentos.empty and 'numero_conta' in dados_pagamentos.columns:
        dados_pagamentos_ret = dados_pagamentos.copy()
        contas_sem_dados = []
        
        for idx, row in dados_pagamentos_ret.iterrows():
            conta = str(row['numero_conta']).strip() if pd.notna(row['numero_conta']) else None
            
            if not conta or conta == 'nan':
                continue
            
            if conta in dados_referencia:
                ref = dados_referencia[conta]
                retificacoes_aplicadas = []
                
                # Retificar CPF
                if 'cpf' in dados_pagamentos_ret.columns:
                    cpf_original = str(row['cpf']).strip() if pd.notna(row['cpf']) else ''
                    cpf_referencia = ref['cpf']
                    
                    if cpf_referencia and cpf_referencia != 'nan' and cpf_referencia != cpf_original:
                        if not cpf_original or cpf_original == 'nan':
                            dados_pagamentos_ret.at[idx, 'cpf'] = cpf_referencia
                            retificacoes_aplicadas.append(f"CPF: '{cpf_original}' → '{cpf_referencia}'")
                
                # Retificar Nome
                if 'nome' in dados_pagamentos_ret.columns:
                    nome_original = str(row['nome']).strip() if pd.notna(row['nome']) else ''
                    nome_referencia = ref['nome']
                    
                    if nome_referencia and nome_referencia != 'nan' and nome_referencia != nome_original:
                        if not nome_original or nome_original == 'nan':
                            dados_pagamentos_ret.at[idx, 'nome'] = nome_referencia
                            retificacoes_aplicadas.append(f"Nome: '{nome_original}' → '{nome_referencia}'")
                
                # Retificar RG
                if 'rg' in dados_pagamentos_ret.columns:
                    rg_original = str(row['rg']).strip() if pd.notna(row['rg']) else ''
                    rg_referencia = ref['rg']
                    
                    if rg_referencia and rg_referencia != 'nan' and rg_referencia != rg_original:
                        if not rg_original or rg_original == 'nan':
                            dados_pagamentos_ret.at[idx, 'rg'] = rg_referencia
                            retificacoes_aplicadas.append(f"RG: '{rg_original}' → '{rg_referencia}'")
                
                # Retificar Projeto
                if 'projeto' in dados_pagamentos_ret.columns:
                    projeto_original = str(row['projeto']).strip() if pd.notna(row['projeto']) else ''
                    projeto_referencia = ref['projeto']
                    
                    if projeto_referencia and projeto_referencia != 'nan' and projeto_referencia != projeto_original:
                        if not projeto_original or projeto_original == 'nan':
                            dados_pagamentos_ret.at[idx, 'projeto'] = projeto_referencia
                            retificacoes_aplicadas.append(f"Projeto: '{projeto_original}' → '{projeto_referencia}'")
                
                if retificacoes_aplicadas:
                    retificacoes['detalhes_retificacoes'].append({
                        'numero_conta': conta,
                        'retificacoes': retificacoes_aplicadas,
                        'fonte_dados': ref['fonte']
                    })
                    retificacoes['total_retificacoes'] += len(retificacoes_aplicadas)
            else:
                contas_sem_dados.append(conta)
        
        retificacoes['contas_sem_dados'] = list(set(contas_sem_dados))
        retificacoes['dados_completados'] = dados_pagamentos_ret
    
    return retificacoes

def processar_cpf_para_retificacao(cpf):
    """Processa CPF para padronização"""
    if pd.isna(cpf) or cpf in ['', 'NaN', 'None', 'nan', 'NULL']:
        return ''
    
    cpf_str = str(cpf).strip()
    cpf_limpo = re.sub(r'[^\d]', '', cpf_str)
    
    if cpf_limpo == '':
        return ''
    
    if len(cpf_limpo) < 11:
        cpf_limpo = cpf_limpo.zfill(11)
    
    return cpf_limpo

def aplicar_retificacoes_cpf(dados):
    """Aplica padronização de CPFs"""
    if 'cpf' not in dados.columns:
        return dados, 0
    
    dados_ret = dados.copy()
    retificacoes = 0
    
    for idx, row in dados_ret.iterrows():
        cpf_original = row['cpf'] if pd.notna(row['cpf']) else ''
        cpf_processado = processar_cpf_para_retificacao(cpf_original)
        
        if cpf_processado != str(cpf_original):
            dados_ret.at[idx, 'cpf'] = cpf_processado
            retificacoes += 1
    
    return dados_ret, retificacoes

# ========== FUNÇÕES DE SALVAMENTO NO BANCO ==========
def salvar_dados_db(conn, tabela, mes_ref, ano_ref, nome_arquivo, file_bytes, dados_df, metadados, importado_por):
    """Salva dados no banco de forma genérica"""
    try:
        file_hash = calcular_hash_arquivo(file_bytes)
        
        cursor = conn.execute(f"SELECT id FROM {tabela} WHERE hash_arquivo = ?", (file_hash,))
        existe = cursor.fetchone()
        
        # Verificar duplicidade por nome e período
        cursor = conn.execute(f"""
            SELECT id, nome_arquivo, data_importacao 
            FROM {tabela} 
            WHERE mes_referencia = ? AND ano_referencia = ? AND nome_arquivo = ?
        """, (mes_ref, ano_ref, nome_arquivo))
        
        duplicado_periodo = cursor.fetchone()
        
        if duplicado_periodo:
            return False, f"Arquivo '{nome_arquivo}' já existe para {mes_ref}/{ano_ref}"
        
        dados_json = dados_df.to_json(orient='records', date_format='iso', force_ascii=False)
        metadados_json = json.dumps(metadados, ensure_ascii=False)
        
        if existe:
            conn.execute(f'''
                UPDATE {tabela} SET data_importacao = ?, dados_json = ?, metadados_json = ?,
                          mes_referencia = ?, ano_referencia = ?, nome_arquivo = ?, importado_por = ?
                WHERE hash_arquivo = ?
            ''', (data_hora_atual_brasilia(), dados_json, metadados_json, 
                  mes_ref, ano_ref, nome_arquivo, importado_por.lower(), file_hash))
        else:
            conn.execute(f'''
                INSERT INTO {tabela} (mes_referencia, ano_referencia, data_importacao, 
                          nome_arquivo, dados_json, metadados_json, hash_arquivo, importado_por)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (mes_ref, ano_ref, data_hora_atual_brasilia(), nome_arquivo, 
                  dados_json, metadados_json, file_hash, importado_por.lower()))
        
        conn.commit()
        return True, "✅ Dados salvos com sucesso"
        
    except Exception as e:
        return False, f"Erro ao salvar dados: {str(e)}"

def salvar_metricas_db(conn, tipo, mes_ref, ano_ref, metrics):
    """Salva métricas no banco"""
    try:
        cursor = conn.execute(
            "SELECT id FROM metricas_mensais WHERE tipo = ? AND mes_referencia = ? AND ano_referencia = ?",
            (tipo, mes_ref, ano_ref)
        )
        existe = cursor.fetchone()
        
        # Preparar dados para salvar
        dados_corrigidos_json = json.dumps(metrics.get('detalhes_retificacoes', []), ensure_ascii=False) if metrics.get('detalhes_retificacoes') else '[]'
        
        if existe:
            conn.execute('''
                UPDATE metricas_mensais 
                SET total_registros = ?, beneficiarios_unicos = ?, contas_unicas = ?, 
                    valor_total = ?, pagamentos_duplicados = ?, valor_duplicados = ?, 
                    projetos_ativos = ?, registros_problema = ?, cpfs_ajuste = ?, 
                    total_contas_abertas = ?, beneficiarios_contas = ?, 
                    dados_retificados = ?, dados_corrigidos_json = ?, data_calculo = ?
                WHERE tipo = ? AND mes_referencia = ? AND ano_referencia = ?
            ''', (
                metrics.get('total_registros', 0),
                metrics.get('beneficiarios_unicos', 0),
                metrics.get('contas_unicas', 0),
                metrics.get('valor_total', 0),
                metrics.get('pagamentos_duplicados', 0),
                metrics.get('valor_total_duplicados', 0),
                metrics.get('projetos_ativos', 0),
                metrics.get('registros_problema', 0),
                metrics.get('total_cpfs_ajuste', 0),
                metrics.get('total_contas_abertas', 0),
                metrics.get('beneficiarios_contas', 0),
                metrics.get('dados_retificados', 0),
                dados_corrigidos_json,
                data_hora_atual_brasilia(),
                tipo, mes_ref, ano_ref
            ))
        else:
            conn.execute('''
                INSERT INTO metricas_mensais (tipo, mes_referencia, ano_referencia, total_registros, 
                            beneficiarios_unicos, contas_unicas, valor_total, pagamentos_duplicados, 
                            valor_duplicados, projetos_ativos, registros_problema, cpfs_ajuste,
                            total_contas_abertas, beneficiarios_contas, dados_retificados,
                            dados_corrigidos_json, data_calculo)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (tipo, mes_ref, ano_ref, 
                  metrics.get('total_registros', 0),
                  metrics.get('beneficiarios_unicos', 0),
                  metrics.get('contas_unicas', 0),
                  metrics.get('valor_total', 0),
                  metrics.get('pagamentos_duplicados', 0),
                  metrics.get('valor_total_duplicados', 0),
                  metrics.get('projetos_ativos', 0),
                  metrics.get('registros_problema', 0),
                  metrics.get('total_cpfs_ajuste', 0),
                  metrics.get('total_contas_abertas', 0),
                  metrics.get('beneficiarios_contas', 0),
                  metrics.get('dados_retificados', 0),
                  dados_corrigidos_json,
                  data_hora_atual_brasilia()))
        
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar métricas: {str(e)}")
        return False

# ========== FUNÇÕES DE CARREGAMENTO ==========
def carregar_dados(conn, email_usuario):
    """Carrega dados do usuário com detecção automática de mês/ano"""
    st.sidebar.header("📤 Carregar Dados Mensais")
    
    # Upload de arquivos
    upload_pagamentos = st.sidebar.file_uploader(
        "Planilha de Pagamentos", 
        type=['xlsx', 'csv', 'xls'],
        key="pagamentos_upload"
    )
    
    upload_contas = st.sidebar.file_uploader(
        "Planilha de Abertura de Contas", 
        type=['xlsx', 'csv', 'xls'],
        key="contas_upload"
    )
    
    upload_gestao = st.sidebar.file_uploader(
        "Planilha de Gestão de Documentos", 
        type=['xlsx', 'csv', 'xls'],
        key="gestao_upload"
    )
    
    # Inicializar dados no session_state
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
    if 'retificacoes_aplicadas' not in st.session_state:
        st.session_state.retificacoes_aplicadas = {}
    
    # Detectar mês/ano dos arquivos
    arquivos_para_processar = []
    deteccoes = []
    
    if upload_pagamentos:
        arquivos_para_processar.append(('pagamentos', upload_pagamentos))
    if upload_contas:
        arquivos_para_processar.append(('contas', upload_contas))
    if upload_gestao:
        arquivos_para_processar.append(('gestao', upload_gestao))
    
    # Processar detecção para cada arquivo
    mes_detectado = None
    ano_detectado = None
    
    for tipo, arquivo in arquivos_para_processar:
        # Primeiro ler o arquivo para detectar mês/ano dos dados
        df_temp = processar_arquivo(arquivo, tipo)
        if df_temp is not None:
            mes, ano = detectar_mes_ano_completo(arquivo.name, df_temp, tipo)
            
            if mes and ano:
                deteccoes.append({
                    'tipo': tipo,
                    'arquivo': arquivo.name,
                    'mes': mes,
                    'ano': ano
                })
                
                # Priorizar detecção de pagamentos, depois gestão, depois contas
                if tipo == 'pagamentos' or (tipo == 'gestao' and not mes_detectado):
                    mes_detectado = mes
                    ano_detectado = ano
                elif tipo == 'contas' and not mes_detectado:
                    mes_detectado = mes
                    ano_detectado = ano
    
    # Mostrar detecções
    if deteccoes:
        st.sidebar.subheader("📅 Detecção Automática")
        for det in deteccoes:
            st.sidebar.info(f"{det['tipo'].title()}: {det['mes']}/{det['ano']}")
    
    # Seleção de mês e ano - usar valores detectados como padrão
    col1, col2 = st.sidebar.columns(2)
    with col1:
        meses = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
        
        if mes_detectado:
            mes_ref_padrao = mes_detectado
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
        
        mes_index = meses.index(mes_ref_padrao) if mes_ref_padrao in meses else 0
        mes_ref = st.selectbox("Mês de Referência", meses, index=mes_index)
        
    with col2:
        if ano_detectado:
            ano_ref_padrao = ano_detectado
        elif st.session_state.ano_ref_carregado:
            ano_ref_padrao = st.session_state.ano_ref_carregado
        else:
            ano_ref_padrao = agora_brasilia().year
        
        ano_atual = agora_brasilia().year
        anos = list(range(ano_atual, ano_atual - 5, -1))
        
        ano_index = anos.index(ano_ref_padrao) if ano_ref_padrao in anos else 0
        ano_ref = st.selectbox("Ano de Referência", anos, index=ano_index)
    
    st.sidebar.markdown("---")
    
    # Inicializar variáveis
    dados = st.session_state.dados_carregados.copy()
    nomes_arquivos = st.session_state.nomes_arquivos_carregados.copy()
    dados_processados = False
    
    # Processar cada tipo de arquivo
    for tipo, arquivo in arquivos_para_processar:
        tabela_db = {
            'pagamentos': 'pagamentos',
            'contas': 'abertura_contas',
            'gestao': 'gestao_doc'
        }.get(tipo)
        
        if not tabela_db:
            continue
        
        # Verificar duplicidade
        cursor = conn.execute(f"""
            SELECT nome_arquivo, data_importacao 
            FROM {tabela_db} 
            WHERE mes_referencia = ? AND ano_referencia = ? AND nome_arquivo = ?
        """, (mes_ref, ano_ref, arquivo.name))
        
        duplicado = cursor.fetchone()
        
        if duplicado:
            st.sidebar.warning(f"⚠️ Arquivo '{arquivo.name}' já existe para {mes_ref}/{ano_ref}")
            sobrescrever = st.sidebar.checkbox(f"Sobrescrever '{arquivo.name}'?", key=f"sobrescrever_{tipo}")
            if not sobrescrever:
                continue
        
        # Processar arquivo
        df = processar_arquivo(arquivo, tipo)
        if df is not None:
            nomes_arquivos[tipo] = arquivo.name
            
            # Aplicar padronização de CPFs
            if 'cpf' in df.columns:
                df, _ = aplicar_retificacoes_cpf(df)
            
            # Salvar no banco
            metadados = {
                'total_registros': len(df),
                'colunas_disponiveis': df.columns.tolist(),
                'tipo_arquivo': tipo,
                'detecao_mes_ano': f"{mes_ref}/{ano_ref}"
            }
            
            sucesso, mensagem = salvar_dados_db(conn, tabela_db, mes_ref, ano_ref, 
                                              arquivo.name, arquivo.getvalue(), df, metadados, email_usuario)
            
            if sucesso:
                st.sidebar.success(f"✅ {tipo.title()}: {mensagem}")
                dados[tipo] = df
                dados_processados = True
                
                registrar_log_admin(conn, email_usuario, "IMPORTACAO", tipo, None, 
                                  f"Arquivo: {arquivo.name}, Mês/Ano: {mes_ref}/{ano_ref}")
            else:
                st.sidebar.error(f"❌ {tipo.title()}: {mensagem}")
    
    # Aplicar retificações se temos dados de pagamentos e referência
    if 'pagamentos' in dados and ('contas' in dados or 'gestao' in dados):
        with st.sidebar:
            with st.spinner("🔄 Aplicando retificações..."):
                retificacoes = cruzar_dados_retificacao(
                    dados.get('pagamentos', pd.DataFrame()),
                    dados.get('contas', pd.DataFrame()),
                    dados.get('gestao', pd.DataFrame())
                )
                
                if retificacoes['total_retificacoes'] > 0:
                    st.sidebar.success(f"✅ {retificacoes['total_retificacoes']} dados retificados!")
                    
                    # Atualizar dados com retificações
                    if 'dados_completados' in retificacoes and not retificacoes['dados_completados'].empty:
                        dados['pagamentos_retificado'] = retificacoes['dados_completados']
                    
                    st.session_state.retificacoes_aplicadas = retificacoes
                else:
                    st.sidebar.info("ℹ️ Nenhuma retificação necessária")
    
    # Atualizar session_state se houve processamento
    if dados_processados:
        st.session_state.dados_carregados = dados.copy()
        st.session_state.nomes_arquivos_carregados = nomes_arquivos.copy()
        st.session_state.mes_ref_carregado = mes_ref
        st.session_state.ano_ref_carregado = ano_ref
        
        # Processar métricas
        with st.spinner("🔄 Calculando métricas..."):
            metrics = processar_dados_completos(dados, retificacoes, nomes_arquivos)
            
            # Salvar métricas no banco
            if 'pagamentos' in dados or 'pagamentos_retificado' in dados:
                salvar_metricas_db(conn, 'pagamentos', mes_ref, ano_ref, metrics)
            
            if 'contas' in dados:
                salvar_metricas_db(conn, 'contas', mes_ref, ano_ref, metrics)
            
            st.session_state.processed_metrics = metrics
        
        st.sidebar.success("✅ Dados processados e salvos!")
    
    return dados, nomes_arquivos, mes_ref, ano_ref, dados_processados

# ========== FUNÇÕES DE ANÁLISE ==========
def processar_dados_completos(dados, retificacoes, nomes_arquivos):
    """Processa os dados para gerar métricas completas"""
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
        'total_registros_criticos': 0,
        'total_cpfs_ajuste': 0,
        'dados_retificados': 0,
        'detalhes_retificacoes': retificacoes.get('detalhes_retificacoes', []) if retificacoes else [],
        'contas_sem_dados': retificacoes.get('contas_sem_dados', []) if retificacoes else []
    }
    
    # Usar dados retificados se disponível
    df_pagamentos = dados.get('pagamentos_retificado', dados.get('pagamentos', pd.DataFrame()))
    
    # Processar pagamentos
    if not df_pagamentos.empty:
        if 'numero_conta' in df_pagamentos.columns:
            # Filtrar registros válidos
            df_validos = df_pagamentos[
                df_pagamentos['numero_conta'].notna() & 
                (df_pagamentos['numero_conta'].astype(str).str.strip() != '')
            ].copy()
            
            metrics['total_pagamentos'] = len(df_validos)
            metrics['contas_unicas'] = df_validos['numero_conta'].nunique()
            
            if 'nome' in df_validos.columns:
                metrics['beneficiarios_unicos'] = df_validos['nome'].nunique()
            
            if 'projeto' in df_validos.columns:
                metrics['projetos_ativos'] = df_validos['projeto'].nunique()
            
            if 'valor' in df_validos.columns:
                try:
                    # Converter valores para numérico
                    df_validos['valor'] = pd.to_numeric(df_validos['valor'], errors='coerce')
                    metrics['valor_total'] = df_validos['valor'].sum()
                except:
                    metrics['valor_total'] = 0
            
            # Verificar duplicidades
            if 'numero_conta' in df_validos.columns:
                contas_duplicadas = df_validos[df_validos.duplicated(['numero_conta'], keep=False)]
                metrics['pagamentos_duplicados'] = contas_duplicadas['numero_conta'].nunique() if not contas_duplicadas.empty else 0
            
            # Verificar CPFs problemáticos
            if 'cpf' in df_validos.columns:
                cpfs_problematicos = df_validos[
                    df_validos['cpf'].isna() | 
                    (df_validos['cpf'].astype(str).str.strip() == '') |
                    (df_validos['cpf'].astype(str).str.len() != 11)
                ]
                metrics['total_cpfs_ajuste'] = len(cpfs_problematicos)
    
    # Processar abertura de contas
    df_contas = dados.get('contas', pd.DataFrame())
    if not df_contas.empty:
        metrics['total_contas_abertas'] = len(df_contas)
        
        if 'nome' in df_contas.columns:
            metrics['beneficiarios_contas'] = df_contas['nome'].nunique()
        
        if 'projeto' in df_contas.columns:
            metrics['projetos_ativos'] = max(metrics.get('projetos_ativos', 0), df_contas['projeto'].nunique())
    
    # Adicionar dados de retificações
    if retificacoes:
        metrics['dados_retificados'] = retificacoes.get('total_retificacoes', 0)
    
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

class PDFRelatorio(FPDF):
    """Classe para gerar PDFs com relatórios"""
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=15)
        # Usar fonte que suporte UTF-8
        self.add_font('DejaVu', '', 'DejaVuSans.ttf', uni=True)
        self.add_font('DejaVu', 'B', 'DejaVuSans-Bold.ttf', uni=True)
        self.add_font('DejaVu', 'I', 'DejaVuSans-Oblique.ttf', uni=True)
    
    def header(self):
        self.set_font('DejaVu', 'B', 12)
        self.cell(0, 10, 'Prefeitura de São Paulo - SMDET', 0, 1, 'C')
        self.cell(0, 10, 'Sistema POT - Relatório de Análise', 0, 1, 'C')
        self.ln(5)
    
    def footer(self):
        self.set_y(-15)
        self.set_font('DejaVu', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')
    
    def add_section_title(self, title):
        self.set_font('DejaVu', 'B', 14)
        self.cell(0, 10, title, 0, 1)
        self.ln(2)
    
    def add_metric_row(self, label, value):
        self.set_font('DejaVu', '', 11)
        self.cell(100, 8, label, 0, 0)
        self.set_font('DejaVu', 'B', 11)
        self.cell(0, 8, str(value), 0, 1)
    
    def add_table(self, headers, data, col_widths):
        self.set_font('DejaVu', 'B', 10)
        
        # Cabeçalho
        self.set_fill_color(200, 200, 200)
        for i, header in enumerate(headers):
            self.cell(col_widths[i], 10, header, 1, 0, 'C', True)
        self.ln()
        
        # Dados
        self.set_font('DejaVu', '', 9)
        for row in data:
            for i, cell in enumerate(row):
                # Garantir que o texto seja string e substituir caracteres problemáticos
                cell_str = str(cell) if cell is not None else ''
                self.cell(col_widths[i], 8, cell_str, 1, 0, 'L')
            self.ln()

def remover_caracteres_nao_ascii(texto):
    """Remove caracteres não-ASCII do texto"""
    if texto is None:
        return ""
    return ''.join(char for char in str(texto) if ord(char) < 128)

def gerar_pdf_relatorio(metrics, dados, nomes_arquivos, mes_ref, ano_ref, retificacoes):
    """Gera relatório completo em PDF com tratamento de caracteres especiais"""
    try:
        pdf = PDFRelatorio()
        pdf.add_page()
        
        # Cabeçalho
        pdf.set_font('DejaVu', 'B', 16)
        pdf.cell(0, 10, 'RELATORIO DE ANALISE - SISTEMA POT', 0, 1, 'C')
        pdf.ln(5)
        
        # Informações básicas (remover acentos para evitar problemas)
        pdf.set_font('DejaVu', '', 12)
        pdf.cell(0, 8, f'Periodo de Referencia: {remover_caracteres_nao_ascii(mes_ref)}/{ano_ref}', 0, 1)
        pdf.cell(0, 8, f'Data da Analise: {data_hora_atual_brasilia()}', 0, 1)
        pdf.ln(5)
        
        # Arquivos processados
        if nomes_arquivos:
            pdf.add_section_title('Arquivos Processados')
            pdf.set_font('DejaVu', '', 11)
            for tipo, nome in nomes_arquivos.items():
                pdf.cell(0, 8, f'• {tipo.title()}: {remover_caracteres_nao_ascii(nome)}', 0, 1)
            pdf.ln(5)
        
        # Métricas principais
        pdf.add_section_title('Metricas Principais')
        
        pdf.add_metric_row('Total de Pagamentos:', formatar_brasileiro(metrics.get('total_pagamentos', 0)))
        pdf.add_metric_row('Beneficiarios Unicos:', formatar_brasileiro(metrics.get('beneficiarios_unicos', 0)))
        pdf.add_metric_row('Contas Unicas:', formatar_brasileiro(metrics.get('contas_unicas', 0)))
        pdf.add_metric_row('Valor Total:', formatar_brasileiro(metrics.get('valor_total', 0), 'monetario'))
        pdf.add_metric_row('Projetos Ativos:', formatar_brasileiro(metrics.get('projetos_ativos', 0)))
        pdf.ln(5)
        
        # Retificações aplicadas
        if metrics.get('dados_retificados', 0) > 0:
            pdf.add_section_title('Retificacoes Aplicadas')
            pdf.add_metric_row('Dados Retificados:', formatar_brasileiro(metrics['dados_retificados']))
            
            if metrics.get('detalhes_retificacoes'):
                pdf.add_page()
                pdf.add_section_title('Detalhes das Retificacoes')
                
                headers = ['Numero da Conta', 'Retificacoes Aplicadas', 'Fonte dos Dados']
                col_widths = [40, 120, 30]
                
                data = []
                for ret in metrics['detalhes_retificacoes'][:50]:  # Limitar a 50 registros
                    data.append([
                        ret['numero_conta'],
                        ', '.join([remover_caracteres_nao_ascii(r) for r in ret['retificacoes']]),
                        ret['fonte_dados']
                    ])
                
                pdf.add_table(headers, data, col_widths)
                
                if len(metrics['detalhes_retificacoes']) > 50:
                    pdf.ln(5)
                    pdf.set_font('DejaVu', 'I', 10)
                    pdf.cell(0, 8, f'... e mais {len(metrics["detalhes_retificacoes"]) - 50} retificacoes', 0, 1)
        
        # Problemas identificados
        pdf.add_page()
        pdf.add_section_title('Problemas Identificados')
        
        pdf.add_metric_row('Pagamentos Duplicados:', formatar_brasileiro(metrics.get('pagamentos_duplicados', 0)))
        pdf.add_metric_row('CPFs para Ajuste:', formatar_brasileiro(metrics.get('total_cpfs_ajuste', 0)))
        pdf.add_metric_row('Registros Criticos:', formatar_brasileiro(metrics.get('total_registros_criticos', 0)))
        
        if metrics.get('contas_sem_dados'):
            pdf.ln(5)
            pdf.set_font('DejaVu', 'B', 12)
            pdf.cell(0, 10, 'Contas sem Dados de Referencia:', 0, 1)
            pdf.set_font('DejaVu', '', 10)
            
            # Limitar a 20 contas e remover caracteres especiais
            contas_limpas = [remover_caracteres_nao_ascii(c) for c in metrics['contas_sem_dados'][:20]]
            contas_texto = ', '.join(contas_limpas)
            if len(metrics['contas_sem_dados']) > 20:
                contas_texto += f'... e mais {len(metrics["contas_sem_dados"]) - 20} contas'
            
            pdf.multi_cell(0, 8, contas_texto)
        
        # Recomendações
        pdf.add_page()
        pdf.add_section_title('Recomendacoes e Acoes')
        
        recomendacoes = []
        
        if metrics.get('pagamentos_duplicados', 0) > 0:
            recomendacoes.append(f'Verificar {metrics["pagamentos_duplicados"]} contas com pagamentos duplicados')
        
        if metrics.get('total_cpfs_ajuste', 0) > 0:
            recomendacoes.append(f'Corrigir {metrics["total_cpfs_ajuste"]} CPFs com problemas de formatacao')
        
        if metrics.get('dados_retificados', 0) > 0:
            recomendacoes.append(f'Validar {metrics["dados_retificados"]} dados retificados automaticamente')
        
        if not recomendacoes:
            recomendacoes.append('Nenhuma acao critica necessaria')
        
        pdf.set_font('DejaVu', '', 11)
        for i, rec in enumerate(recomendacoes, 1):
            pdf.cell(0, 8, f'{i}. {rec}', 0, 1)
        
        # Usar codificação UTF-8 para o output
        return pdf.output(dest='S').encode('utf-8')
        
    except Exception as e:
        st.error(f"Erro ao gerar PDF: {str(e)}")
        # Criar um PDF simples de fallback
        pdf_fallback = FPDF()
        pdf_fallback.add_page()
        pdf_fallback.set_font("Arial", size=12)
        pdf_fallback.cell(200, 10, txt="Relatorio do Sistema POT", ln=1, align="C")
        pdf_fallback.cell(200, 10, txt=f"Periodo: {mes_ref}/{ano_ref}", ln=1, align="L")
        return pdf_fallback.output(dest='S').encode('latin-1')

# ========== FUNÇÕES DE VISUALIZAÇÃO ==========
def mostrar_analise_principal(dados, metrics, nomes_arquivos, mes_ref, ano_ref, retificacoes):
    """Mostra análise principal com retificações"""
    st.title("🏛️ Sistema POT - SMDET")
    st.markdown(f"**Mês de referência:** {mes_ref}/{ano_ref}")
    st.markdown(f"**Data da análise:** {data_hora_atual_brasilia()}")
    st.markdown("---")
    
    # Métricas principais
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total de Pagamentos", 
                 formatar_brasileiro(metrics.get('total_pagamentos', 0)))
    
    with col2:
        st.metric("Beneficiários Únicos", 
                 formatar_brasileiro(metrics.get('beneficiarios_unicos', 0)))
    
    with col3:
        st.metric("Contas Únicas", 
                 formatar_brasileiro(metrics.get('contas_unicas', 0)))
    
    with col4:
        st.metric("Valor Total", 
                 formatar_brasileiro(metrics.get('valor_total', 0), 'monetario'))
    
    # Métricas de retificação
    st.markdown("---")
    st.subheader("📝 Retificação de Dados")
    
    col5, col6, col7 = st.columns(3)
    
    with col5:
        dados_retificados = metrics.get('dados_retificados', 0)
        st.metric("Dados Retificados", 
                 formatar_brasileiro(dados_retificados),
                 delta_color="normal" if dados_retificados > 0 else "off")
    
    with col6:
        st.metric("CPFs para Ajuste", 
                 formatar_brasileiro(metrics.get('total_cpfs_ajuste', 0)),
                 delta_color="inverse" if metrics.get('total_cpfs_ajuste', 0) > 0 else "off")
    
    with col7:
        st.metric("Contas sem Dados", 
                 formatar_brasileiro(len(metrics.get('contas_sem_dados', []))),
                 delta_color="inverse" if metrics.get('contas_sem_dados', []) else "off")
    
    # Tabs de análise
    tab1, tab2, tab3, tab4 = st.tabs([
        "📋 Visão Geral", "🔍 Retificações", "⚠️ Problemas", "📊 Dados"
    ])
    
    with tab1:
        st.subheader("Resumo dos Dados")
        
        if nomes_arquivos:
            for tipo, nome in nomes_arquivos.items():
                st.info(f"**{tipo.title()}:** {nome}")
        
        st.write(f"**Projetos Ativos:** {metrics.get('projetos_ativos', 0)}")
        st.write(f"**Pagamentos Duplicados:** {metrics.get('pagamentos_duplicados', 0)}")
    
    with tab2:
        st.subheader("Detalhes das Retificações")
        
        if metrics.get('dados_retificados', 0) > 0:
            st.success(f"✅ {metrics['dados_retificados']} dados foram retificados automaticamente")
            
            if metrics.get('detalhes_retificacoes'):
                df_retificacoes = pd.DataFrame(metrics['detalhes_retificacoes'])
                st.dataframe(df_retificacoes, use_container_width=True)
        else:
            st.info("ℹ️ Nenhuma retificação necessária")
        
        if metrics.get('contas_sem_dados'):
            st.warning(f"⚠️ {len(metrics['contas_sem_dados'])} contas sem dados de referência")
            st.write("Contas:", ', '.join(metrics['contas_sem_dados'][:10]))
            if len(metrics['contas_sem_dados']) > 10:
                st.write(f"... e mais {len(metrics['contas_sem_dados']) - 10} contas")
    
    with tab3:
        st.subheader("Problemas Identificados")
        
        problemas = []
        
        if metrics.get('pagamentos_duplicados', 0) > 0:
            problemas.append(f"**Pagamentos Duplicados:** {metrics['pagamentos_duplicados']} contas")
        
        if metrics.get('total_cpfs_ajuste', 0) > 0:
            problemas.append(f"**CPFs Problemáticos:** {metrics['total_cpfs_ajuste']} registros")
        
        if metrics.get('total_registros_criticos', 0) > 0:
            problemas.append(f"**Registros Críticos:** {metrics['total_registros_criticos']} registros")
        
        if problemas:
            for problema in problemas:
                st.error(problema)
        else:
            st.success("✅ Nenhum problema crítico identificado")
    
    with tab4:
        st.subheader("Visualização dos Dados")
        
        tipo_dados = st.selectbox("Selecione os dados para visualizar:", 
                                ["Pagamentos", "Abertura de Contas", "Gestão de Documentos"])
        
        df_para_mostrar = None
        
        if tipo_dados == "Pagamentos":
            df_para_mostrar = dados.get('pagamentos_retificado', dados.get('pagamentos', pd.DataFrame()))
        elif tipo_dados == "Abertura de Contas":
            df_para_mostrar = dados.get('contas', pd.DataFrame())
        elif tipo_dados == "Gestão de Documentos":
            df_para_mostrar = dados.get('gestao', pd.DataFrame())
        
        if df_para_mostrar is not None and not df_para_mostrar.empty:
            st.dataframe(df_para_mostrar.head(100), use_container_width=True)
            st.write(f"Total de registros: {len(df_para_mostrar)}")
        else:
            st.info("Nenhum dado disponível para visualização")

# ========== FUNÇÕES ADMINISTRATIVAS ==========
def gerenciar_usuarios(conn):
    """Interface para gerenciamento de usuários"""
    st.header("👥 Gerenciamento de Usuários")
    
    # Adicionar novo usuário
    with st.expander("➕ Adicionar Novo Usuário"):
        with st.form("novo_usuario"):
            col1, col2 = st.columns(2)
            
            with col1:
                novo_email = st.text_input("Email institucional", placeholder="usuario@prefeitura.sp.gov.br")
                novo_nome = st.text_input("Nome completo")
            
            with col2:
                novoTipo = st.selectbox("Tipo de usuário", ["usuario", "admin"])
                ativo = st.checkbox("Usuário ativo", value=True)
            
            if st.form_submit_button("Adicionar"):
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
    
    # Listar usuários
    st.subheader("📋 Lista de Usuários")
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
    
    # Carregar dados
    dados, nomes_arquivos, mes_ref, ano_ref, dados_processados = carregar_dados(conn, email_autorizado)
    
    # Obter métricas e retificações
    retificacoes = st.session_state.get('retificacoes_aplicadas', {})
    metrics = st.session_state.get('processed_metrics', {})
    
    # Sidebar - Exportação
    st.sidebar.markdown("---")
    st.sidebar.header("📥 EXPORTAR RELATÓRIOS")
    
    if dados_processados or st.session_state.get('dados_carregados'):
        # Gerar PDF com tratamento de erro
        try:
            pdf_bytes = gerar_pdf_relatorio(metrics, dados, nomes_arquivos, mes_ref, ano_ref, retificacoes)
            
            st.sidebar.download_button(
                label="📄 Gerar Relatório PDF",
                data=pdf_bytes,
                file_name=f"relatorio_pot_{mes_ref}_{ano_ref}_{data_hora_arquivo_brasilia()}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        except Exception as e:
            st.sidebar.error(f"Erro ao gerar PDF: {str(e)}")
            # Botão de fallback com PDF simples
            pdf_simples = FPDF()
            pdf_simples.add_page()
            pdf_simples.set_font("Arial", size=12)
            pdf_simples.cell(200, 10, txt=f"Relatorio POT {mes_ref}/{ano_ref}", ln=1, align="C")
            pdf_bytes_simples = pdf_simples.output(dest='S').encode('latin-1')
            
            st.sidebar.download_button(
                label="📄 Gerar PDF Simples",
                data=pdf_bytes_simples,
                file_name=f"relatorio_simples_pot_{mes_ref}_{ano_ref}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        
        # Exportar dados tratados
        st.sidebar.markdown("---")
        st.sidebar.subheader("💾 Exportar Dados")
        
        if 'pagamentos' in dados or 'pagamentos_retificado' in dados:
            df_exportar = dados.get('pagamentos_retificado', dados.get('pagamentos', pd.DataFrame()))
            if not df_exportar.empty:
                csv_data = df_exportar.to_csv(index=False, encoding='utf-8-sig')
                st.sidebar.download_button(
                    label="📋 Dados de Pagamentos (CSV)",
                    data=csv_data,
                    file_name=f"pagamentos_{mes_ref}_{ano_ref}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
    
    # Sidebar - Administração
    if tipo_usuario == 'admin':
        st.sidebar.markdown("---")
        st.sidebar.subheader("⚙️ Administração")
        
        if st.sidebar.button("👥 Gerenciar Usuários"):
            st.session_state.admin_page = 'usuarios'
        
        if st.sidebar.button("🗑️ Limpar Dados da Sessão"):
            for key in ['dados_carregados', 'nomes_arquivos_carregados', 'processed_metrics', 'retificacoes_aplicadas']:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()
    
    # Mostrar página apropriada
    if tipo_usuario == 'admin' and st.session_state.get('admin_page') == 'usuarios':
        gerenciar_usuarios(conn)
    else:
        mostrar_analise_principal(dados, metrics, nomes_arquivos, mes_ref, ano_ref, retificacoes)

if __name__ == "__main__":
    main()
