# app.py
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timezone, timedelta
import io# app.py
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
            metadados_json TEXT NOT NULL,
            UNIQUE(mes_referencia, ano_referencia, nome_arquivo)
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
            UNIQUE(mes_referencia, ano_referencia, nome_arquivo)
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
    
    # Tabela para usuários autorizados
    conn.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            nome TEXT NOT NULL,
            tipo TEXT NOT NULL DEFAULT 'usuario',
            data_criacao TEXT NOT NULL,
            ativo INTEGER DEFAULT 1
        )
    ''')
    
    # Verificar e adicionar colunas faltantes
    try:
        conn.execute("SELECT cpfs_ajuste FROM metricas_mensais LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE metricas_mensais ADD COLUMN cpfs_ajuste INTEGER")
    
    # Inserir administrador padrão se não existir
    cursor = conn.execute("SELECT * FROM usuarios WHERE email = 'admin@prefeitura.sp.gov.br'")
    if cursor.fetchone() is None:
        conn.execute('''
            INSERT INTO usuarios (email, nome, tipo, data_criacao, ativo)
            VALUES (?, ?, ?, ?, ?)
        ''', ('admin@prefeitura.sp.gov.br', 'Administrador', 'admin', data_hora_atual_brasilia(), 1))
    
    conn.commit()
    return conn

# Função para hash de senha
def hash_senha(senha):
    """Gera hash SHA-256 da senha"""
    return hashlib.sha256(senha.encode()).hexdigest()

# Senha autorizada (Smdetpot2025)
SENHA_AUTORIZADA_HASH = hash_senha("Smdetpot2025")
SENHA_ADMIN_HASH = hash_senha("AdminSmdet2025")

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

# SISTEMA DE AUTENTICAÇÃO MELHORADO
def verificar_usuario_autorizado(conn, email):
    """Verifica se o usuário está autorizado no banco de dados"""
    cursor = conn.execute("SELECT * FROM usuarios WHERE email = ? AND ativo = 1", (email,))
    return cursor.fetchone() is not None

def obter_tipo_usuario(conn, email):
    """Obtém o tipo do usuário (admin ou usuario)"""
    cursor = conn.execute("SELECT tipo FROM usuarios WHERE email = ? AND ativo = 1", (email,))
    resultado = cursor.fetchone()
    return resultado[0] if resultado else None

def autenticar(conn):
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
        st.sidebar.error("🚫 Sistema temporariamente bloqueado. Tente novamente mais tarde.")
        return None, None
    
    # Se já está autenticado, mostrar informações
    if st.session_state.autenticado and st.session_state.email_autorizado:
        tipo_usuario = "👑 Administrador" if st.session_state.tipo_usuario == 'admin' else "👤 Usuário"
        st.sidebar.success(f"✅ Acesso autorizado")
        st.sidebar.info(f"{tipo_usuario}: {st.session_state.email_autorizado}")
        
        if st.sidebar.button("🚪 Sair"):
            st.session_state.autenticado = False
            st.session_state.email_autorizado = None
            st.session_state.tipo_usuario = None
            st.session_state.tentativas_login = 0
            st.rerun()
        
        return st.session_state.email_autorizado, st.session_state.tipo_usuario
    
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
            elif not verificar_usuario_autorizado(conn, email):
                st.sidebar.error("🚫 Usuário não autorizado. Contate o administrador.")
                st.session_state.tentativas_login += 1
            elif hash_senha(senha) != SENHA_AUTORIZADA_HASH:
                # Verificar se é admin tentando login
                if email == 'admin@prefeitura.sp.gov.br' and hash_senha(senha) == SENHA_ADMIN_HASH:
                    # Login de admin bem-sucedido
                    st.session_state.autenticado = True
                    st.session_state.email_autorizado = email
                    st.session_state.tipo_usuario = 'admin'
                    st.session_state.tentativas_login = 0
                    st.sidebar.success("✅ Login de administrador realizado com sucesso!")
                    st.rerun()
                else:
                    st.sidebar.error("❌ Senha incorreta")
                    st.session_state.tentativas_login += 1
            else:
                # Login de usuário normal bem-sucedido
                st.session_state.autenticado = True
                st.session_state.email_autorizado = email
                st.session_state.tipo_usuario = obter_tipo_usuario(conn, email)
                st.session_state.tentativas_login = 0
                st.sidebar.success("✅ Login realizado com sucesso!")
                st.rerun()
            
            # Verificar se excedeu tentativas
            if st.session_state.tentativas_login >= 3:
                st.session_state.bloqueado = True
                st.sidebar.error("🚫 Muitas tentativas falhas. Sistema bloqueado temporariamente.")
    
    return None, None

# FUNÇÃO PARA GERENCIAR USUÁRIOS (APENAS ADMIN)
def gerenciar_usuarios(conn):
    """Interface para gerenciamento de usuários - APENAS ADMIN"""
    st.header("👥 Gerenciamento de Usuários")
    
    # Listar usuários existentes
    st.subheader("Usuários Cadastrados")
    usuarios_df = pd.read_sql_query("SELECT id, email, nome, tipo, data_criacao, ativo FROM usuarios ORDER BY tipo, email", conn)
    
    if not usuarios_df.empty:
        st.dataframe(usuarios_df, use_container_width=True)
    else:
        st.info("Nenhum usuário cadastrado.")
    
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
        
        adicionar = st.form_submit_button("Adicionar Usuário")
        
        if adicionar:
            if not novo_email or not novo_nome:
                st.error("Preencha todos os campos obrigatórios.")
            elif not novo_email.endswith('@prefeitura.sp.gov.br'):
                st.error("O email deve ser institucional (@prefeitura.sp.gov.br).")
            else:
                try:
                    conn.execute('''
                        INSERT INTO usuarios (email, nome, tipo, data_criacao, ativo)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (novo_email, novo_nome, novoTipo, data_hora_atual_brasilia(), 1 if ativo else 0))
                    conn.commit()
                    st.success(f"✅ Usuário {novo_email} adicionado com sucesso!")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("❌ Este email já está cadastrado.")
    
    # Gerenciar usuários existentes
    st.subheader("Gerenciar Usuários Existentes")
    
    if not usuarios_df.empty:
        usuario_selecionado = st.selectbox("Selecione um usuário:", usuarios_df['email'].tolist())
        usuario_info = usuarios_df[usuarios_df['email'] == usuario_selecionado].iloc[0]
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write(f"**ID:** {usuario_info['id']}")
            st.write(f"**Email:** {usuario_info['email']}")
            st.write(f"**Nome:** {usuario_info['nome']}")
        
        with col2:
            st.write(f"**Tipo:** {usuario_info['tipo']}")
            st.write(f"**Data de criação:** {usuario_info['data_criacao']}")
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
            if st.button("🗑️ Excluir Usuário", type="secondary"):
                conn.execute("DELETE FROM usuarios WHERE email = ?", (usuario_selecionado,))
                conn.commit()
                st.success(f"✅ Usuário {usuario_selecionado} excluído!")
                st.rerun()

# FUNÇÃO MELHORADA: LIMPAR BANCO DE DADOS COMPLETAMENTE (APENAS ADMIN)
def limpar_banco_dados_completo(conn, tipo_usuario):
    """Remove TODOS os dados do banco para recomeçar do zero - APENAS ADMIN"""
    
    if tipo_usuario != 'admin':
        st.error("🚫 Acesso negado. Apenas administradores podem executar esta operação.")
        return False
    
    try:
        st.error("**ATENÇÃO CRÍTICA:** Esta operação é IRREVERSÍVEL e deve ser usada APENAS durante testes!")
        st.warning("""
        **Efeitos desta operação:**
        - ❌ Todos os dados de pagamentos serão PERDIDOS
        - ❌ Todos os dados de inscrições serão PERDIDOS  
        - ❌ Todas as métricas históricas serão PERDIDAS
        - 🔄 O sistema recomeçará do ZERO
        """)
        
        # Dupla confirmação
        senha_confirmacao1 = st.text_input("Digite 'LIMPAR TUDO' para confirmar:", type="password", key="confirm1")
        senha_confirmacao2 = st.text_input("Digite novamente 'LIMPAR TUDO':", type="password", key="confirm2")
        
        col1, col2 = st.columns(2)
        with col1:
            botao_limpar = st.button("🗑️ LIMPAR TODOS OS DADOS", type="secondary", use_container_width=True)
        with col2:
            botao_cancelar = st.button("❌ Cancelar", use_container_width=True)
        
        if botao_limpar:
            if senha_confirmacao1 == "LIMPAR TUDO" and senha_confirmacao2 == "LIMPAR TUDO":
                # Executar limpeza COMPLETA
                conn.execute("DELETE FROM pagamentos")
                conn.execute("DELETE FROM inscricoes")
                conn.execute("DELETE FROM metricas_mensais")
                
                # Reiniciar sequências de ID
                conn.execute("DELETE FROM sqlite_sequence WHERE name='pagamentos'")
                conn.execute("DELETE FROM sqlite_sequence WHERE name='inscricoes'") 
                conn.execute("DELETE FROM sqlite_sequence WHERE name='metricas_mensais'")
                
                conn.commit()
                
                st.success("✅ Banco de dados limpo COMPLETAMENTE!")
                st.info("🔄 Recarregue a página para começar novamente")
                return True
            else:
                st.error("❌ Confirmação incorreta. Operação cancelada.")
                return False
        
        if botao_cancelar:
            st.info("Operação de limpeza cancelada.")
            return False
            
    except Exception as e:
        st.error(f"❌ Erro ao limpar banco: {str(e)}")
        return False

# FUNÇÃO PARA VISUALIZAR E EXCLUIR REGISTROS ESPECÍFICOS (APENAS ADMIN)
def gerenciar_registros(conn, tipo_usuario):
    """Permite visualizar e excluir registros específicos - APENAS ADMIN"""
    
    if tipo_usuario != 'admin':
        st.error("🚫 Acesso negado. Apenas administradores podem executar esta operação.")
        return
    
    try:
        st.warning("Área administrativa - Use com cuidado!")
        
        # Selecionar tipo de dados
        tipo_dados = st.selectbox("Tipo de dados:", ["Pagamentos", "Inscrições", "Métricas"])
        
        if tipo_dados == "Pagamentos":
            dados = carregar_pagamentos_db(conn)
        elif tipo_dados == "Inscrições":
            dados = carregar_inscricoes_db(conn)
        else:
            dados = carregar_metricas_db(conn)
        
        if not dados.empty:
            st.write(f"**Total de registros:** {len(dados)}")
            
            # Mostrar resumo
            if tipo_dados in ["Pagamentos", "Inscrições"]:
                resumo = dados[['id', 'mes_referencia', 'ano_referencia', 'nome_arquivo', 'data_importacao']].copy()
                st.dataframe(resumo.head(10))
                
                # Opção de excluir por ID específico
                st.subheader("Excluir Registro Específico")
                id_excluir = st.number_input("ID do registro a excluir:", min_value=1, step=1)
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("🗑️ Excluir por ID", type="secondary", use_container_width=True):
                        if id_excluir:
                            if tipo_dados == "Pagamentos":
                                conn.execute("DELETE FROM pagamentos WHERE id = ?", (int(id_excluir),))
                                # Excluir métricas correspondentes se existirem
                                registro = dados[dados['id'] == int(id_excluir)]
                                if not registro.empty:
                                    mes = registro.iloc[0]['mes_referencia']
                                    ano = registro.iloc[0]['ano_referencia']
                                    conn.execute("DELETE FROM metricas_mensais WHERE mes_referencia = ? AND ano_referencia = ? AND tipo = 'pagamentos'", 
                                               (mes, ano))
                            else:
                                conn.execute("DELETE FROM inscricoes WHERE id = ?", (int(id_excluir),))
                                # Excluir métricas correspondentes se existirem
                                registro = dados[dados['id'] == int(id_excluir)]
                                if not registro.empty:
                                    mes = registro.iloc[0]['mes_referencia']
                                    ano = registro.iloc[0]['ano_referencia']
                                    conn.execute("DELETE FROM metricas_mensais WHERE mes_referencia = ? AND ano_referencia = ? AND tipo = 'inscricoes'", 
                                               (mes, ano))
                            
                            conn.commit()
                            st.success(f"✅ Registro ID {id_excluir} excluído!")
                            st.rerun()
                
                with col2:
                    if st.button("🔄 Atualizar Lista", use_container_width=True):
                        st.rerun()
            
            elif tipo_dados == "Métricas":
                st.dataframe(dados.head(10))
        
        else:
            st.info("Nenhum registro encontrado.")
            
    except Exception as e:
        st.error(f"Erro no gerenciamento: {str(e)}")

# FUNÇÕES CORRIGIDAS: Salvar dados com verificação de duplicidade
def salvar_pagamentos_db(conn, mes_ref, ano_ref, nome_arquivo, dados_df, metadados):
    """Salva dados de pagamentos no banco de dados com verificação de duplicidade"""
    # Verificar se já existe registro para este mês/ano/arquivo
    cursor = conn.execute(
        "SELECT id FROM pagamentos WHERE mes_referencia = ? AND ano_referencia = ? AND nome_arquivo = ?",
        (mes_ref, ano_ref, nome_arquivo)
    )
    existe = cursor.fetchone()
    
    dados_json = dados_df.to_json(orient='records', date_format='iso')
    metadados_json = json.dumps(metadados)
    
    if existe:
        # Atualizar registro existente
        conn.execute('''
            UPDATE pagamentos 
            SET data_importacao = ?, dados_json = ?, metadados_json = ?
            WHERE mes_referencia = ? AND ano_referencia = ? AND nome_arquivo = ?
        ''', (data_hora_atual_brasilia(), dados_json, metadados_json, mes_ref, ano_ref, nome_arquivo))
        st.sidebar.info("📝 Registro de pagamentos atualizado (evitada duplicidade)")
    else:
        # Inserir novo registro
        conn.execute('''
            INSERT INTO pagamentos (mes_referencia, ano_referencia, data_importacao, nome_arquivo, dados_json, metadados_json)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (mes_ref, ano_ref, data_hora_atual_brasilia(), nome_arquivo, dados_json, metadados_json))
        st.sidebar.success("✅ Novo registro de pagamentos salvo")
    
    conn.commit()

def salvar_inscricoes_db(conn, mes_ref, ano_ref, nome_arquivo, dados_df, metadados):
    """Salva dados de inscrições no banco de dados com verificação de duplicidade"""
    # Verificar se já existe registro para este mês/ano/arquivo
    cursor = conn.execute(
        "SELECT id FROM inscricoes WHERE mes_referencia = ? AND ano_referencia = ? AND nome_arquivo = ?",
        (mes_ref, ano_ref, nome_arquivo)
    )
    existe = cursor.fetchone()
    
    dados_json = dados_df.to_json(orient='records', date_format='iso')
    metadados_json = json.dumps(metadados)
    
    if existe:
        # Atualizar registro existente
        conn.execute('''
            UPDATE inscricoes 
            SET data_importacao = ?, dados_json = ?, metadados_json = ?
            WHERE mes_referencia = ? AND ano_referencia = ? AND nome_arquivo = ?
        ''', (data_hora_atual_brasilia(), dados_json, metadados_json, mes_ref, ano_ref, nome_arquivo))
        st.sidebar.info("📝 Registro de inscrições atualizado (evitada duplicidade)")
    else:
        # Inserir novo registro
        conn.execute('''
            INSERT INTO inscricoes (mes_referencia, ano_referencia, data_importacao, nome_arquivo, dados_json, metadados_json)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (mes_ref, ano_ref, data_hora_atual_brasilia(), nome_arquivo, dados_json, metadados_json))
        st.sidebar.success("✅ Novo registro de inscrições salvo")
    
    conn.commit()

def salvar_metricas_db(conn, tipo, mes_ref, ano_ref, metrics):
    """Salva métricas no banco de dados para relatórios comparativos com verificação de duplicidade"""
    # Verificar se já existe métrica para este tipo/mês/ano
    cursor = conn.execute(
        "SELECT id FROM metricas_mensais WHERE tipo = ? AND mes_referencia = ? AND ano_referencia = ?",
        (tipo, mes_ref, ano_ref)
    )
    existe = cursor.fetchone()
    
    try:
        if existe:
            # Atualizar métrica existente
            conn.execute('''
                UPDATE metricas_mensais 
                SET total_registros = ?, beneficiarios_unicos = ?, contas_unicas = ?, 
                    valor_total = ?, pagamentos_duplicados = ?, valor_duplicados = ?, 
                    projetos_ativos = ?, registros_problema = ?, cpfs_ajuste = ?, data_calculo = ?
                WHERE tipo = ? AND mes_referencia = ? AND ano_referencia = ?
            ''', (
                metrics.get('total_pagamentos', 0),
                metrics.get('beneficiarios_unicos', 0),
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
            # Inserir nova métrica
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
    except sqlite3.OperationalError as e:
        try:
            conn.execute("ALTER TABLE metricas_mensais ADD COLUMN cpfs_ajuste INTEGER")
            conn.commit()
            salvar_metricas_db(conn, tipo, mes_ref, ano_ref, metrics)
        except:
            conn.execute('''
                INSERT INTO metricas_mensais (tipo, mes_referencia, ano_referencia, total_registros, 
                            beneficiarios_unicos, contas_unicas, valor_total, pagamentos_duplicados, 
                            valor_duplicados, projetos_ativos, registros_problema, data_calculo)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (tipo, mes_ref, ano_ref, 
                  metrics.get('total_pagamentos', 0),
                  metrics.get('beneficiarios_unicos', 0),
                  metrics.get('contas_unicas', 0),
                  metrics.get('valor_total', 0),
                  metrics.get('pagamentos_duplicados', 0),
                  metrics.get('valor_total_duplicados', 0),
                  metrics.get('projetos_ativos', 0),
                  metrics.get('total_registros_criticos', 0),
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
        query += " ORDER BY ano_referencia DESC, mes_referencia DESC LIMIT 3"
    elif periodo == 'semestral':
        query += " ORDER BY ano_referencia DESC, mes_referencia DESC LIMIT 6"
    elif periodo == 'anual':
        query += " ORDER BY ano_referencia DESC, mes_referencia DESC LIMIT 12"
    else:
        query += " ORDER BY ano_referencia DESC, mes_referencia DESC"
    
    try:
        df_result = pd.read_sql_query(query, conn, params=params)
        return df_result
    except Exception as e:
        st.error(f"Erro ao carregar métricas: {e}")
        return pd.DataFrame()

# CORREÇÃO: Função para extrair mês e ano do nome do arquivo
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
                if len(grupos[0]) == 4:
                    ano = int(grupos[0])
                    mes_num = int(grupos[1])
                else:
                    ano = int(grupos[2])
                    mes_num = int(grupos[1])
                
                meses_numeros = {
                    1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
                    5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
                    9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
                }
                return meses_numeros.get(mes_num, 'Janeiro'), ano
                
            elif len(grupos) == 2:
                if grupos[0].isdigit():
                    ano = int(grupos[0])
                    mes_str = grupos[1]
                else:
                    mes_str = grupos[0]
                    ano = int(grupos[1])
                
                for key, value in meses_map.items():
                    if key in mes_str:
                        return value, ano
    
    for key, value in meses_map.items():
        if key in nome_upper:
            ano_match = re.search(r'(\d{4})', nome_upper)
            ano = int(ano_match.group(1)) if ano_match else datetime.now().year
            return value, ano
    
    return None, None

# Funções auxiliares (mantidas iguais)
def obter_coluna_conta(df):
    """Identifica a coluna que contém o número da conta"""
    colunas_conta = ['Num Cartao', 'Num_Cartao', 'Conta', 'Número da Conta', 'Numero_Conta', 'Número do Cartão']
    for coluna in colunas_conta:
        if coluna in df.columns:
            return coluna
    return None

def obter_coluna_nome(df):
    """Identifica a coluna que contém o nome do beneficiário"""
    colunas_nome = ['Beneficiario', 'Beneficiário', 'Nome', 'Nome Completo', 'Nome do Beneficiário']
    for coluna in colunas_nome:
        if coluna in df.columns:
            return coluna
    return None

def obter_coluna_valor(df):
    """Identifica a coluna que contém o valor pago, priorizando 'Valor Pagto'"""
    colunas_valor_prioridade = ['Valor Pagto', 'Valor_Pagto', 'Valor Pgto', 'Valor_Pgto', 'Valor', 'Valor_Pago', 'Valor Pagamento']
    for coluna in colunas_valor_prioridade:
        if coluna in df.columns:
            return coluna
    return None

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

# FUNÇÃO CORRIGIDA: Identificar e remover linha de totais
def remover_linha_totais(df):
    """Identifica e remove a linha de totais da planilha de forma inteligente"""
    if df.empty or len(df) <= 1:
        return df
    
    df_limpo = df.copy()
    
    ultima_linha = df_limpo.iloc[-1]
    criterios_totais = 0
    
    colunas_texto = [col for col in df_limpo.columns if df_limpo[col].dtype == 'object']
    for coluna in colunas_texto[:3]:
        if pd.notna(ultima_linha[coluna]):
            valor = str(ultima_linha[coluna]).upper()
            if any(palavra in valor for palavra in ['TOTAL', 'SOMA', 'GERAL', 'TOTAL GERAL']):
                criterios_totais += 2
                break
    
    colunas_numericas = [col for col in df_limpo.columns if df_limpo[col].dtype in ['int64', 'float64']]
    if colunas_numericas:
        medias = df_limpo.iloc[:-1][colunas_numericas].mean()
        
        for coluna in colunas_numericas:
            if pd.notna(ultima_linha[coluna]) and pd.notna(medias[coluna]):
                if ultima_linha[coluna] > medias[coluna] * 10:
                    criterios_totais += 1
    
    if criterios_totais >= 2:
        df_limpo = df_limpo.iloc[:-1].copy()
        st.sidebar.info("📝 Linha de totais identificada e removida automaticamente")
    
    return df_limpo

def filtrar_pagamentos_validos(df):
    """Filtra apenas os registros que possuem número da conta (pagamentos válidos)"""
    coluna_conta = obter_coluna_conta(df)
    
    if not coluna_conta:
        return df
    
    df_filtrado = df[df[coluna_conta].notna() & (df[coluna_conta].astype(str).str.strip() != '')].copy()
    
    palavras_totais = ['TOTAL', 'SOMA', 'GERAL', 'TOTAL GERAL']
    for palavra in palavras_totais:
        mask = df_filtrado[coluna_conta].astype(str).str.upper().str.contains(palavra, na=False)
        df_filtrado = df_filtrado[~mask]
    
    return df_filtrado

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
    
    df_analise = df.copy()
    df_analise['Linha_Planilha_Original'] = df_analise.index + 2
    
    for idx, row in df_analise.iterrows():
        cpf = str(row['CPF']) if pd.notna(row['CPF']) and str(row['CPF']).strip() != '' else ''
        problemas = []
        
        if cpf == '':
            problemas.append('CPF vazio')
            problemas_cpf['cpfs_vazios'].append(idx)
            problemas_cpf['registros_afetados'].append(idx)
        
        elif not cpf.isdigit() and cpf != '':
            problemas.append('Caracteres inválidos')
            problemas_cpf['cpfs_com_caracteres_invalidos'].append(idx)
            problemas_cpf['registros_afetados'].append(idx)
        
        elif len(cpf) != 11 and cpf != '':
            problemas.append(f'Tamanho incorreto ({len(cpf)} dígitos)')
            problemas_cpf['cpfs_com_tamanho_incorreto'].append(idx)
            problemas_cpf['registros_afetados'].append(idx)
        
        if problemas:
            info_problema = {
                'Linha_Planilha': row.get('Linha_Planilha_Original', idx + 2),
                'CPF_Original': row.get('CPF', ''),
                'CPF_Processado': cpf,
                'Problemas_Formatacao': ', '.join(problemas),
                'Status_Registro': 'VÁLIDO - Precisa de correção'
            }
            
            coluna_conta = obter_coluna_conta(df)
            if coluna_conta and coluna_conta in df.columns and pd.notna(row.get(coluna_conta)):
                info_problema['Numero_Conta'] = row[coluna_conta]
            
            coluna_nome = obter_coluna_nome(df)
            if coluna_nome and coluna_nome in df.columns and pd.notna(row.get(coluna_nome)):
                info_problema['Nome'] = row[coluna_nome]
            
            colunas_adicionais = ['Projeto', 'Valor', 'Data', 'Status']
            for coluna in colunas_adicionais:
                if coluna in df.columns and pd.notna(row.get(coluna)):
                    valor = str(row[coluna])
                    if len(valor) > 30:
                        valor = valor[:27] + "..."
                    info_problema[coluna] = valor
            
            if problemas_cpf['detalhes_cpfs_problematicos'].empty:
                problemas_cpf['detalhes_cpfs_problematicos'] = pd.DataFrame([info_problema])
            else:
                problemas_cpf['detalhes_cpfs_problematicos'] = pd.concat([
                    problemas_cpf['detalhes_cpfs_problematicos'],
                    pd.DataFrame([info_problema])
                ], ignore_index=True)
    
    cpfs_duplicados = df_analise[df_analise.duplicated(['CPF'], keep=False)]
    
    if not cpfs_duplicados.empty:
        grupos_cpf = cpfs_duplicados.groupby('CPF')
        
        detalhes_inconsistencias = []
        
        for cpf, grupo in grupos_cpf:
            if len(grupo) > 1:
                problemas_cpf['cpfs_duplicados'].append(cpf)
                
                coluna_nome = obter_coluna_nome(grupo)
                tem_nomes_diferentes = False
                if coluna_nome and coluna_nome in grupo.columns:
                    nomes_unicos = grupo[coluna_nome].dropna().unique()
                    if len(nomes_unicos) > 1:
                        problemas_cpf['cpfs_com_nomes_diferentes'].append(cpf)
                        tem_nomes_diferentes = True
                
                coluna_conta = obter_coluna_conta(grupo)
                tem_contas_diferentes = False
                if coluna_conta and coluna_conta in grupo.columns:
                    contas_unicas = grupo[coluna_conta].dropna().unique()
                    if len(contas_unicas) > 1:
                        problemas_cpf['cpfs_com_contas_diferentes'].append(cpf)
                        tem_contas_diferentes = True
                
                if tem_nomes_diferentes or tem_contas_diferentes:
                    for idx, registro in grupo.iterrows():
                        info_inconsistencia = {
                            'CPF': cpf,
                            'Linha_Planilha': registro['Linha_Planilha_Original'],
                            'Ocorrencia_CPF': f"{list(grupo.index).index(idx) + 1}/{len(grupo)}"
                        }
                        
                        if coluna_nome and coluna_nome in registro:
                            info_inconsistencia['Nome'] = registro[coluna_nome]
                        
                        if coluna_conta and coluna_conta in registro:
                            info_inconsistencia['Numero_Conta'] = registro[coluna_conta]
                        
                        if 'Projeto' in registro:
                            info_inconsistencia['Projeto'] = registro['Projeto']
                        
                        if 'Valor_Limpo' in registro:
                            info_inconsistencia['Valor'] = registro['Valor_Limpo']
                        
                        problemas_inconsistencia = ['CPF DUPLICADO']
                        if tem_nomes_diferentes:
                            problemas_inconsistencia.append('NOMES DIFERENTES')
                        if tem_contas_diferentes:
                            problemas_inconsistencia.append('CONTAS DIFERENTES')
                        
                        info_inconsistencia['Problemas_Inconsistencia'] = ', '.join(problemas_inconsistencia)
                        info_inconsistencia['Status'] = 'CRÍTICO - Correção urgente necessária'
                        
                        detalhes_inconsistencias.append(info_inconsistencia)
        
        if detalhes_inconsistencias:
            problemas_cpf['detalhes_inconsistencias'] = pd.DataFrame(detalhes_inconsistencias)
            problemas_cpf['total_cpfs_inconsistentes'] = len(set(
                problemas_cpf['cpfs_com_nomes_diferentes'] + 
                problemas_cpf['cpfs_com_contas_diferentes']
            ))
    
    problemas_cpf['total_problemas_cpf'] = (
        len(problemas_cpf['cpfs_com_caracteres_invalidos']) +
        len(problemas_cpf['cpfs_com_tamanho_incorreto']) +
        len(problemas_cpf['cpfs_vazios'])
    )
    
    return problemas_cpf

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
    coluna_nome = obter_coluna_nome(df)
    
    if not coluna_conta:
        return duplicidades
    
    contagem_por_conta = df[coluna_conta].value_counts()
    contas_com_multiplos = contagem_por_conta[contagem_por_conta > 1].index.tolist()
    
    duplicidades['contas_com_multiplos_pagamentos'] = contas_com_multiplos
    
    if not contas_com_multiplos:
        return duplicidades
    
    df_duplicados = df[df[coluna_conta].isin(contas_com_multiplos)].copy()
    
    colunas_ordenacao = [coluna_conta]
    colunas_data = ['Data', 'Data Pagto', 'Data_Pagto', 'DataPagto', 'Data Pagamento']
    for col_data in colunas_data:
        if col_data in df_duplicados.columns:
            colunas_ordenacao.append(col_data)
            break
    
    df_duplicados = df_duplicados.sort_values(by=colunas_ordenacao)
    
    df_duplicados['Ocorrencia'] = df_duplicados.groupby(coluna_conta).cumcount() + 1
    df_duplicados['Total_Ocorrencias'] = df_duplicados.groupby(coluna_conta)[coluna_conta].transform('count')
    
    colunas_exibicao_completas = [coluna_conta, 'Ocorrencia', 'Total_Ocorrencias']
    
    if coluna_nome and coluna_nome in df_duplicados.columns:
        colunas_exibicao_completas.append(coluna_nome)
    
    if 'CPF' in df_duplicados.columns:
        colunas_exibicao_completas.append('CPF')
    
    for col_data in colunas_data:
        if col_data in df_duplicados.columns:
            colunas_exibicao_completas.append(col_data)
            break
    
    coluna_valor = obter_coluna_valor(df_duplicados)
    if coluna_valor:
        colunas_exibicao_completas.append(coluna_valor)
    
    if 'Valor_Limpo' in df_duplicados.columns:
        colunas_exibicao_completas.append('Valor_Limpo')
    
    if 'Projeto' in df_duplicados.columns:
        colunas_exibicao_completas.append('Projeto')
    
    if 'Status' in df_duplicados.columns:
        colunas_exibicao_completas.append('Status')
    
    colunas_exibicao_completas = [col for col in colunas_exibicao_completas if col in df_duplicados.columns]
    
    duplicidades['contas_duplicadas'] = df_duplicados[colunas_exibicao_completas]
    duplicidades['detalhes_completos_duplicidades'] = df_duplicados[colunas_exibicao_completas]
    duplicidades['total_contas_duplicadas'] = len(contas_com_multiplos)
    duplicidades['total_pagamentos_duplicados'] = len(df_duplicados)
    
    if 'Valor_Limpo' in df_duplicados.columns:
        duplicidades['valor_total_duplicados'] = df_duplicados['Valor_Limpo'].sum()
    
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
    
    colunas_exibicao = [col for col in colunas_exibicao if col in df_contas_sem_pagamento.columns]
    
    df_contas_sem_pagamento['Status'] = 'Aguardando Pagamento'
    
    pendentes['contas_sem_pagamento'] = df_contas_sem_pagamento[colunas_exibicao + ['Status']]
    pendentes['total_contas_sem_pagamento'] = len(contas_sem_pagamento)
    pendentes['beneficiarios_sem_pagamento'] = df_contas_sem_pagamento[coluna_nome_contas].nunique() if coluna_nome_contas and coluna_nome_contas in df_contas_sem_pagamento.columns else 0
    
    return pendentes

def processar_cpf(cpf):
    """Processa CPF, mantendo apenas números e completando com zeros à esquerda"""
    if pd.isna(cpf) or cpf in ['', 'NaN', 'None', 'nan', 'None', 'NULL']:
        return ''
    
    cpf_str = str(cpf).strip()
    cpf_limpo = re.sub(r'[^\d]', '', cpf_str)
    
    if cpf_limpo == '':
        return ''
    
    if len(cpf_limpo) < 11:
        cpf_limpo = cpf_limpo.zfill(11)
    
    return cpf_limpo

def padronizar_documentos(df):
    """Padroniza RGs e CPFs, CPF apenas números"""
    df_processed = df.copy()
    
    colunas_documentos = ['RG', 'CPF', 'Documento', 'Numero_Documento']
    
    for coluna in colunas_documentos:
        if coluna in df_processed.columns:
            try:
                if coluna == 'CPF':
                    df_processed[coluna] = df_processed[coluna].astype(str).apply(
                        lambda x: processar_cpf(x) if pd.notna(x) and str(x).strip() != '' else ''
                    )
                elif coluna == 'RG':
                    df_processed[coluna] = df_processed[coluna].astype(str).apply(
                        lambda x: re.sub(r'[^a-zA-Z0-9/]', '', x) if pd.notna(x) and str(x).strip() != '' else ''
                    )
                else:
                    df_processed[coluna] = df_processed[coluna].astype(str).apply(
                        lambda x: re.sub(r'[^\w]', '', x) if pd.notna(x) and str(x).strip() != '' else ''
                    )
                
            except Exception as e:
                st.warning(f"⚠️ Não foi possível padronizar a coluna '{coluna}': {str(e)}")
    
    return df_processed

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

def processar_colunas_valor(df):
    """Processa colunas de valor para formato brasileiro, priorizando 'Valor Pagto'"""
    df_processed = df.copy()
    
    colunas_valor_prioridade = ['Valor Pagto', 'Valor_Pagto', 'Valor Pgto', 'Valor_Pgto', 'Valor', 'Valor_Pago', 'Valor Pagamento']
    
    coluna_valor_encontrada = None
    for coluna_valor in colunas_valor_prioridade:
        if coluna_valor in df_processed.columns:
            coluna_valor_encontrada = coluna_valor
            break
    
    if coluna_valor_encontrada:
        try:
            valores_limpos = []
            
            for valor in df_processed[coluna_valor_encontrada]:
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
            st.sidebar.success(f"💰 Coluna de valor utilizada: '{coluna_valor_encontrada}'")
                
        except Exception as e:
            st.warning(f"⚠️ Erro ao processar valores da coluna '{coluna_valor_encontrada}': {str(e)}")
            df_processed['Valor_Limpo'] = 0.0
    else:
        st.warning("⚠️ Nenhuma coluna de valor encontrada na planilha")
        df_processed['Valor_Limpo'] = 0.0
    
    return df_processed

def analisar_ausencia_dados(dados, nome_arquivo_pagamentos=None, nome_arquivo_contas=None):
    """Analisa e reporta apenas dados críticos realmente ausentes"""
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
        df = dados['pagamentos_sem_totais'] if 'pagamentos_sem_totais' in dados else dados['pagamentos']
        
        df = df.reset_index(drop=True)
        df['Linha_Planilha_Original'] = df.index + 2
        
        registros_problematicos = []
        
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
        
        if 'Valor_Limpo' in df.columns:
            mask_valor_invalido = (
                df['Valor_Limpo'].isna() | 
                (df['Valor_Limpo'] == 0)
            )
            valores_invalidos = df[mask_valor_invalido]
            for idx in valores_invalidos.index:
                if idx not in registros_problematicos:
                    registros_problematicos.append(idx)
        
        registros_problematicos_filtrados = []
        for idx in registros_problematicos:
            registro = df.loc[idx]
            tem_conta_valida = coluna_conta and pd.notna(registro[coluna_conta]) and str(registro[coluna_conta]).strip() != ''
            tem_valor_valido = 'Valor_Limpo' in df.columns and pd.notna(registro['Valor_Limpo']) and registro['Valor_Limpo'] > 0
            
            if not tem_conta_valida or not tem_valor_valido:
                registros_problematicos_filtrados.append(idx)
        
        analise_ausencia['registros_criticos_problematicos'] = registros_problematicos_filtrados
        analise_ausencia['total_registros_criticos'] = len(registros_problematicos_filtrados)
        
        if registros_problematicos_filtrados:
            analise_ausencia['registros_problema_detalhados'] = df.loc[registros_problematicos_filtrados].copy()
        
        if registros_problematicos_filtrados:
            resumo = []
            for idx in registros_problematicos_filtrados[:100]:
                registro = df.loc[idx]
                info_ausencia = {
                    'Indice_Registro': idx,
                    'Linha_Planilha': registro.get('Linha_Planilha_Original', idx + 2),
                    'Planilha_Origem': nome_arquivo_pagamentos or 'Pagamentos',
                    'Status_Registro': 'INVÁLIDO - Precisa de correção'
                }
                
                colunas_interesse = []
                colunas_possiveis = [
                    'CPF', 'RG', 'Projeto', 'Valor', 'Beneficiario', 'Beneficiário', 'Nome',
                    'Data', 'Data Pagto', 'Data_Pagto', 'DataPagto',
                    'Num Cartao', 'Num_Cartao', 'Conta', 'Status'
                ]
                
                for col in colunas_possiveis:
                    if col in df.columns:
                        colunas_interesse.append(col)
                
                coluna_conta = obter_coluna_conta(df)
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
    
    analise_ausencia = analisar_ausencia_dados(dados, nomes_arquivos.get('pagamentos'), nomes_arquivos.get('contas'))
    metrics.update(analise_ausencia)
    
    if 'pagamentos' in dados and not dados['pagamentos'].empty:
        df_original = dados['pagamentos']
        metrics['total_registros_originais'] = len(df_original)
        
        df_sem_totais = remover_linha_totais(df_original)
        metrics['total_registros_sem_totais'] = len(df_sem_totais)
        
        if len(df_sem_totais) < len(df_original):
            metrics['linha_totais_removida'] = True
        
        df = filtrar_pagamentos_validos(df_sem_totais)
        
        coluna_conta = obter_coluna_conta(df_sem_totais)
        if coluna_conta:
            registros_invalidos = df_sem_totais[
                df_sem_totais[coluna_conta].isna() | 
                (df_sem_totais[coluna_conta].astype(str).str.strip() == '')
            ]
            metrics['total_registros_invalidos'] = len(registros_invalidos)
        
        if df.empty:
            return metrics
        
        problemas_cpf = identificar_cpfs_problematicos(df)
        metrics['problemas_cpf'] = problemas_cpf
        
        metrics['total_cpfs_ajuste'] = (
            problemas_cpf['total_problemas_cpf'] + 
            problemas_cpf['total_cpfs_inconsistentes']
        )
        
        coluna_beneficiario = obter_coluna_nome(df)
        if coluna_beneficiario and coluna_beneficiario in df.columns:
            metrics['beneficiarios_unicos'] = df[coluna_beneficiario].nunique()
        
        metrics['total_pagamentos'] = len(df)
        
        coluna_conta = obter_coluna_conta(df)
        if coluna_conta and coluna_conta in df.columns:
            metrics['contas_unicas'] = df[coluna_conta].nunique()
            
            duplicidades = detectar_pagamentos_duplicados(df)
            metrics['duplicidades_detalhadas'] = duplicidades
            metrics['pagamentos_duplicados'] = duplicidades['total_contas_duplicadas']
            metrics['valor_total_duplicados'] = duplicidades['valor_total_duplicados']
        
        if 'Projeto' in df.columns:
            metrics['projetos_ativos'] = df['Projeto'].nunique()
        
        if 'Valor_Limpo' in df.columns:
            valores_validos = df['Valor_Limpo'].fillna(0)
            metrics['valor_total'] = valores_validos.sum()
            
            coluna_valor_origem = obter_coluna_valor(df)
            if coluna_valor_origem:
                st.sidebar.success(f"💰 Total calculado a partir de: '{coluna_valor_origem}' = R$ {metrics['valor_total']:,.2f}")
        
        if 'CPF' in df.columns:
            cpfs_duplicados = df[df.duplicated(['CPF'], keep=False)]
            metrics['total_cpfs_duplicados'] = cpfs_duplicados['CPF'].nunique()
    
    if 'contas' in dados and not dados['contas'].empty:
        df_contas = dados['contas']
        
        metrics['total_contas_abertas'] = len(df_contas)
        
        coluna_nome = obter_coluna_nome(df_contas)
        if coluna_nome and coluna_nome in df_contas.columns:
            metrics['beneficiarios_contas'] = df_contas[coluna_nome].nunique()
        
        if 'pagamentos' not in dados or dados['pagamentos'].empty:
            metrics['contas_unicas'] = metrics['total_contas_abertas']
            if 'Projeto' in df_contas.columns:
                metrics['projetos_ativos'] = df_contas['Projeto'].nunique()
    
    pendentes = detectar_pagamentos_pendentes(dados)
    metrics['pagamentos_pendentes'] = pendentes
    
    return metrics

# CLASSE PDF MELHORADA COM TABELAS
class PDFWithTables(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=15)
    
    def add_table_header(self, headers, col_widths):
        """Adiciona cabeçalho da tabela"""
        self.set_fill_color(200, 200, 200)
        self.set_font('Arial', 'B', 10)
        for i, header in enumerate(headers):
            self.cell(col_widths[i], 10, header, 1, 0, 'C', True)
        self.ln()
    
    def add_table_row(self, data, col_widths, row_height=10):
        """Adiciona linha da tabela com quebra de texto"""
        self.set_font('Arial', '', 8)
        
        # Calcular altura necessária para a linha
        max_lines = 1
        for i, cell_data in enumerate(data):
            if cell_data:
                text_width = self.get_string_width(str(cell_data))
                available_width = col_widths[i] - 2  # Margem interna
                if text_width > available_width:
                    lines = self._split_text(str(cell_data), available_width)
                    max_lines = max(max_lines, len(lines))
        
        # Desenhar células
        y_start = self.get_y()
        for i, cell_data in enumerate(data):
            x = self.get_x()
            y = y_start
            
            if cell_data:
                text_width = self.get_string_width(str(cell_data))
                available_width = col_widths[i] - 2
                
                if text_width <= available_width:
                    # Texto cabe em uma linha
                    self.set_xy(x, y)
                    self.cell(col_widths[i], row_height, str(cell_data), 1, 0, 'L')
                else:
                    # Texto precisa de múltiplas linhas
                    lines = self._split_text(str(cell_data), available_width)
                    for j, line in enumerate(lines):
                        self.set_xy(x, y + (j * row_height/2))
                        self.cell(col_widths[i], row_height/2, line, 1, 0, 'L')
            
            else:
                self.set_xy(x, y)
                self.cell(col_widths[i], row_height, '', 1, 0, 'L')
            
            self.set_xy(x + col_widths[i], y_start)
        
        # Mover para próxima linha
        self.set_y(y_start + (max_lines * row_height/2))
    
    def _split_text(self, text, max_width):
        """Divide texto em múltiplas linhas para caber na célula"""
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
                current_line = [word]
        
        if current_line:
            lines.append(' '.join(current_line))
        
        return lines

# FUNÇÃO MELHORADA: Gerar PDF Executivo COM TABELAS ORGANIZADAS
def gerar_pdf_executivo(metrics, dados, nomes_arquivos, tipo_relatorio='pagamentos'):
    """Gera relatório executivo em PDF com tabelas organizadas"""
    pdf = PDFWithTables()
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
                cpfs_com_nomes_diferentes = problemas_cpf.get('cpfs_com_nomes_diferentes', [])
                if cpfs_com_nomes_diferentes:
                    pdf.cell(0, 10, f"    * {len(cpfs_com_nomes_diferentes)} CPFs com nomes diferentes", 0, 1)
                cpfs_com_contas_diferentes = problemas_cpf.get('cpfs_com_contas_diferentes', [])
                if cpfs_com_contas_diferentes:
                    pdf.cell(0, 10, f"    * {len(cpfs_com_contas_diferentes)} CPFs com contas diferentes", 0, 1)
            
            pdf.ln(10)
            
            # TABELA PARA CPFs COM PROBLEMAS DE FORMATAÇÃO
            detalhes_cpfs_problematicos = problemas_cpf.get('detalhes_cpfs_problematicos', pd.DataFrame())
            if not detalhes_cpfs_problematicos.empty:
                pdf.set_font("Arial", 'B', 12)
                pdf.cell(0, 10, "CPFs com Problemas de Formatação:", 0, 1)
                pdf.ln(5)
                
                # Preparar dados para tabela
                table_data = []
                for idx, row in detalhes_cpfs_problematicos.head(15).iterrows():
                    linha_data = [
                        str(row.get('Linha_Planilha', '')),
                        str(row.get('Nome', ''))[:30],  # Limitar tamanho do nome
                        str(row.get('Numero_Conta', ''))[:15],
                        str(row.get('Projeto', ''))[:20],
                        str(row.get('CPF_Original', ''))[:15],
                        str(row.get('Problemas_Formatacao', ''))
                    ]
                    table_data.append(linha_data)
                
                # Definir larguras das colunas
                col_widths = [15, 40, 25, 30, 25, 55]
                headers = ['Linha', 'Nome', 'Conta', 'Projeto', 'CPF', 'Problema']
                
                # Adicionar tabela
                pdf.add_table_header(headers, col_widths)
                for data_row in table_data:
                    if pdf.get_y() > 250:  # Verificar se precisa de nova página
                        pdf.add_page()
                    pdf.add_table_row(data_row, col_widths, row_height=8)
                
                if len(detalhes_cpfs_problematicos) > 15:
                    pdf.ln(5)
                    pdf.set_font("Arial", 'I', 10)
                    pdf.cell(0, 10, f"... e mais {len(detalhes_cpfs_problematicos) - 15} registros", 0, 1)
                
                pdf.ln(10)
            
            # TABELA PARA CPFs COM INCONSISTÊNCIAS CRÍTICAS
            detalhes_inconsistencias = problemas_cpf.get('detalhes_inconsistencias', pd.DataFrame())
            if not detalhes_inconsistencias.empty:
                # Verificar se precisa de nova página
                if pdf.get_y() > 150:
                    pdf.add_page()
                
                pdf.set_font("Arial", 'B', 12)
                pdf.cell(0, 10, "CPFs com Inconsistências Críticas:", 0, 1)
                pdf.ln(5)
                
                # Preparar dados para tabela
                table_data = []
                for idx, row in detalhes_inconsistencias.head(10).iterrows():
                    linha_data = [
                        str(row.get('CPF', ''))[:15],
                        str(row.get('Linha_Planilha', '')),
                        str(row.get('Ocorrencia_CPF', '')),
                        str(row.get('Nome', ''))[:25],
                        str(row.get('Numero_Conta', ''))[:15],
                        str(row.get('Problemas_Inconsistencia', ''))[:40]
                    ]
                    table_data.append(linha_data)
                
                # Definir larguras das colunas
                col_widths = [25, 15, 20, 35, 25, 50]
                headers = ['CPF', 'Linha', 'Ocorrência', 'Nome', 'Conta', 'Problemas']
                
                # Adicionar tabela
                pdf.add_table_header(headers, col_widths)
                for data_row in table_data:
                    if pdf.get_y() > 250:  # Verificar se precisa de nova página
                        pdf.add_page()
                    pdf.add_table_row(data_row, col_widths, row_height=8)
                
                if len(detalhes_inconsistencias) > 10:
                    pdf.ln(5)
                    pdf.set_font("Arial", 'I', 10)
                    pdf.cell(0, 10, f"... e mais {len(detalhes_inconsistencias) - 10} registros", 0, 1)
                
                pdf.ln(10)
        
        total_registros_criticos = metrics.get('total_registros_criticos', 0)
        if total_registros_criticos > 0:
            # Verificar se precisa de nova página
            if pdf.get_y() > 150:
                pdf.add_page()
            
            pdf.set_font("Arial", 'B', 12)
            pdf.set_text_color(255, 165, 0)
            pdf.cell(0, 10, f"ATENÇÃO: {total_registros_criticos} registros com problemas críticos", 0, 1)
            pdf.set_text_color(0, 0, 0)
            
            resumo_ausencias = metrics.get('resumo_ausencias', pd.DataFrame())
            if not resumo_ausencias.empty:
                pdf.set_font("Arial", 'B', 12)
                pdf.cell(0, 10, "Registros Críticos (sem conta ou valor):", 0, 1)
                pdf.ln(5)
                
                # Preparar dados para tabela
                table_data = []
                for idx, row in resumo_ausencias.head(10).iterrows():
                    linha_data = [
                        str(row.get('Linha_Planilha', '')),
                        str(row.get('Nome', ''))[:25],
                        str(row.get('CPF', ''))[:15],
                        str(row.get('Projeto', ''))[:20],
                        str(row.get('Problemas_Identificados', ''))[:40]
                    ]
                    table_data.append(linha_data)
                
                # Definir larguras das colunas
                col_widths = [15, 35, 25, 30, 65]
                headers = ['Linha', 'Nome', 'CPF', 'Projeto', 'Problemas']
                
                # Adicionar tabela
                pdf.add_table_header(headers, col_widths)
                for data_row in table_data:
                    if pdf.get_y() > 250:  # Verificar se precisa de nova página
                        pdf.add_page()
                    pdf.add_table_row(data_row, col_widths, row_height=8)
                
                if len(resumo_ausencias) > 10:
                    pdf.ln(5)
                    pdf.set_font("Arial", 'I', 10)
                    pdf.cell(0, 10, f"... e mais {len(resumo_ausencias) - 10} registros", 0, 1)
    
    return pdf.output(dest='S').encode('latin1')

# FUNÇÃO CORRIGIDA: Gerar Excel Completo com verificação de métricas
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
        
        # Problemas de CPF UNIFICADOS
        problemas_cpf = metrics.get('problemas_cpf', {})
        
        # CPFs com problemas de formatação
        detalhes_cpfs_problematicos = problemas_cpf.get('detalhes_cpfs_problematicos', pd.DataFrame())
        if not detalhes_cpfs_problematicos.empty:
            detalhes_cpfs_problematicos.to_excel(writer, sheet_name='CPFs Formatação', index=False)
        
        # CPFs com inconsistências
        detalhes_inconsistencias = problemas_cpf.get('detalhes_inconsistencias', pd.DataFrame())
        if not detalhes_inconsistencias.empty:
            detalhes_inconsistencias.to_excel(writer, sheet_name='CPFs Inconsistentes', index=False)
        
        # Problemas de dados CRÍTICOS
        resumo_ausencias = metrics.get('resumo_ausencias', pd.DataFrame())
        if not resumo_ausencias.empty:
            resumo_ausencias.to_excel(writer, sheet_name='Problemas Críticos', index=False)
    
    return output.getvalue()

# FUNÇÃO CORRIGIDA: Gerar Planilha de Ajustes com verificação
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
        
        # Ações para CPFs problemáticos (UNIFICADO)
        problemas_cpf = metrics.get('problemas_cpf', {})
        
        total_cpfs_inconsistentes = problemas_cpf.get('total_cpfs_inconsistentes', 0)
        if total_cpfs_inconsistentes > 0:
            acoes.append({
                'Tipo': 'CPF Inconsistente',
                'Descrição': f'{total_cpfs_inconsistentes} CPFs com nomes ou contas diferentes',
                'Ação Recomendada': 'Verificar e corrigir inconsistências nos CPFs duplicados - CORREÇÃO URGENTE',
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
    
    # Ações para problemas CRÍTICOS de dados
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

# NOVA FUNÇÃO: Gerar CSV dos dados tratados por projeto
def gerar_csv_dados_tratados(dados, tipo_dados='pagamentos'):
    """Gera arquivos CSV com dados tratados, organizados por projeto"""
    if tipo_dados == 'pagamentos' and 'pagamentos' in dados and not dados['pagamentos'].empty:
        df = dados['pagamentos'].copy()
        
        # Adicionar coluna de projeto se não existir
        if 'Projeto' not in df.columns:
            df['Projeto'] = 'Geral'
        
        # Processar dados para CSV
        df_csv = df.copy()
        
        # Garantir que todas as colunas importantes estejam presentes
        colunas_padrao = ['CPF', 'Nome', 'Projeto', 'Valor_Limpo']
        coluna_conta = obter_coluna_conta(df)
        if coluna_conta:
            colunas_padrao.insert(2, coluna_conta)
        
        # Selecionar apenas colunas que existem
        colunas_finais = [col for col in colunas_padrao if col in df_csv.columns]
        
        # Adicionar outras colunas relevantes
        colunas_adicionais = ['RG', 'Data', 'Status', 'Beneficiario', 'Beneficiário']
        for col in colunas_adicionais:
            if col in df_csv.columns and col not in colunas_finais:
                colunas_finais.append(col)
        
        return df_csv[colunas_finais]
    
    elif tipo_dados == 'inscricoes' and 'contas' in dados and not dados['contas'].empty:
        df = dados['contas'].copy()
        
        # Adicionar coluna de projeto se não existir
        if 'Projeto' not in df.columns:
            df['Projeto'] = 'Geral'
        
        # Processar dados para CSV
        df_csv = df.copy()
        
        # Garantir que todas as colunas importantes estejam presentes
        colunas_padrao = ['CPF', 'Nome', 'Projeto']
        coluna_conta = obter_coluna_conta(df)
        if coluna_conta:
            colunas_padrao.insert(2, coluna_conta)
        
        # Selecionar apenas colunas que existem
        colunas_finais = [col for col in colunas_padrao if col in df_csv.columns]
        
        # Adicionar outras colunas relevantes
        colunas_adicionais = ['RG', 'Data', 'Status', 'Beneficiario', 'Beneficiário', 'Data_Abertura']
        for col in colunas_adicionais:
            if col in df_csv.columns and col not in colunas_finais:
                colunas_finais.append(col)
        
        return df_csv[colunas_finais]
    
    return pd.DataFrame()

# CORREÇÃO: Sistema de upload de dados - EVITAR DUPLICIDADE
def carregar_dados(conn):
    st.sidebar.header("📤 Carregar Dados Mensais")
    
    # Inicializar variáveis de mês/ano
    mes_ref_detectado = None
    ano_ref_detectado = None
    
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
    
    # CORREÇÃO: Detectar mês/ano automaticamente dos nomes dos arquivos
    if upload_pagamentos is not None:
        mes_ref_detectado, ano_ref_detectado = extrair_mes_ano_arquivo(upload_pagamentos.name)
        if mes_ref_detectado and ano_ref_detectado:
            st.sidebar.info(f"📅 Mês/ano detectado: {mes_ref_detectado}/{ano_ref_detectado}")
    
    if upload_contas is not None and (not mes_ref_detectado or not ano_ref_detectado):
        mes_contas, ano_contas = extrair_mes_ano_arquivo(upload_contas.name)
        if mes_contas and ano_contas:
            mes_ref_detectado = mes_contas
            ano_ref_detectado = ano_contas
            st.sidebar.info(f"📅 Mês/ano detectado: {mes_ref_detectado}/{ano_ref_detectado}")
    
    # Seleção de mês e ano de referência com valores detectados como padrão
    col1, col2 = st.sidebar.columns(2)
    with col1:
        meses = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
        mes_ref_padrao = mes_ref_detectado if mes_ref_detectado else 'Outubro'
        mes_ref = st.selectbox("Mês de Referência", meses, index=meses.index(mes_ref_padrao) if mes_ref_padrao in meses else 9)
    with col2:
        ano_atual = datetime.now().year
        anos = [ano_atual, ano_atual-1, ano_atual-2]
        ano_ref_padrao = ano_ref_detectado if ano_ref_detectado else ano_atual
        ano_ref = st.selectbox("Ano de Referência", anos, index=anos.index(ano_ref_padrao) if ano_ref_padrao in anos else 0)
    
    st.sidebar.markdown("---")
    
    dados = {}
    nomes_arquivos = {}
    
    # CORREÇÃO: Variável para controlar se dados foram processados
    dados_processados = False
    
    # Carregar dados de pagamentos
    if upload_pagamentos is not None:
        try:
            if upload_pagamentos.name.endswith('.xlsx'):
                df_pagamentos = pd.read_excel(upload_pagamentos)
            else:
                df_pagamentos = pd.read_csv(upload_pagamentos, encoding='utf-8', sep=';')
            
            nomes_arquivos['pagamentos'] = upload_pagamentos.name
            
            # Guardar versão original e versão sem totais
            dados['pagamentos_original'] = df_pagamentos.copy()
            
            # Remover linha de totais antes do processamento
            df_pagamentos_sem_totais = remover_linha_totais(df_pagamentos)
            dados['pagamentos_sem_totais'] = df_pagamentos_sem_totais
            
            # CORREÇÃO: Processar valores ANTES de outras operações
            df_pagamentos_sem_totais = processar_colunas_valor(df_pagamentos_sem_totais)
            df_pagamentos_sem_totais = processar_colunas_data(df_pagamentos_sem_totais)
            df_pagamentos_sem_totais = padronizar_documentos(df_pagamentos_sem_totais)
            
            dados['pagamentos'] = df_pagamentos_sem_totais
            
            # Salvar no banco de dados (AGORA COM CONTROLE DE DUPLICIDADE)
            metadados = {
                'total_registros_originais': len(df_pagamentos),
                'total_registros_sem_totais': len(df_pagamentos_sem_totais),
                'colunas_disponiveis': df_pagamentos.columns.tolist()
            }
            
            salvar_pagamentos_db(conn, mes_ref, ano_ref, upload_pagamentos.name, df_pagamentos_sem_totais, metadados)
            dados_processados = True
            
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
            
            # Salvar no banco de dados (AGORA COM CONTROLE DE DUPLICIDADE)
            metadados = {
                'total_registros': len(df_contas),
                'colunas_disponiveis': df_contas.columns.tolist()
            }
            
            salvar_inscricoes_db(conn, mes_ref, ano_ref, upload_contas.name, df_contas, metadados)
            dados_processados = True
            
            st.sidebar.success(f"✅ Inscrições: {len(dados['contas'])} registros - {upload_contas.name}")
        except Exception as e:
            st.sidebar.error(f"❌ Erro ao carregar inscrições: {str(e)}")
    
    return dados, nomes_arquivos, mes_ref, ano_ref, dados_processados

# FUNÇÕES PARA AS OUTRAS ABAS
def mostrar_dashboard_evolutivo(conn):
    """Mostra dashboard com evolução temporal dos dados"""
    st.header("📈 Dashboard Evolutivo")
    
    # Carregar métricas históricas
    metricas_pagamentos = carregar_metricas_db(conn, tipo='pagamentos')
    metricas_inscricoes = carregar_metricas_db(conn, tipo='inscricoes')
    
    if metricas_pagamentos.empty and metricas_inscricoes.empty:
        st.info("📊 Nenhum dado histórico disponível. Faça upload de dados mensais para ver a evolução.")
        return
    
    # Criar período para exibição
    if not metricas_pagamentos.empty:
        metricas_pagamentos['periodo'] = metricas_pagamentos['mes_referencia'] + '/' + metricas_pagamentos['ano_referencia'].astype(str)
        metricas_pagamentos = metricas_pagamentos.sort_values(['ano_referencia', 'mes_referencia'])
    
    if not metricas_inscricoes.empty:
        metricas_inscricoes['periodo'] = metricas_inscricoes['mes_referencia'] + '/' + metricas_inscricoes['ano_referencia'].astype(str)
        metricas_inscricoes = metricas_inscricoes.sort_values(['ano_referencia', 'mes_referencia'])
    
    # Gráficos de evolução
    col1, col2 = st.columns(2)
    
    with col1:
        if not metricas_pagamentos.empty:
            st.subheader("Evolução de Pagamentos")
            
            fig = px.line(metricas_pagamentos, x='periodo', y='total_registros',
                         title='Total de Pagamentos por Mês',
                         labels={'total_registros': 'Total de Pagamentos', 'periodo': 'Período'})
            st.plotly_chart(fig, use_container_width=True)
            
            fig2 = px.line(metricas_pagamentos, x='periodo', y='valor_total',
                         title='Valor Total dos Pagamentos',
                         labels={'valor_total': 'Valor Total (R$)', 'periodo': 'Período'})
            st.plotly_chart(fig2, use_container_width=True)
    
    with col2:
        if not metricas_inscricoes.empty:
            st.subheader("Evolução de Inscrições")
            
            fig = px.line(metricas_inscricoes, x='periodo', y='total_registros',
                         title='Total de Inscrições por Mês',
                         labels={'total_registros': 'Total de Inscrições', 'periodo': 'Período'})
            st.plotly_chart(fig, use_container_width=True)
            
            fig2 = px.line(metricas_inscricoes, x='periodo', y='beneficiarios_unicos',
                         title='Beneficiários Únicos por Mês',
                         labels={'beneficiarios_unicos': 'Beneficiários Únicos', 'periodo': 'Período'})
            st.plotly_chart(fig2, use_container_width=True)
    
    # Métricas comparativas
    st.subheader("Métricas Comparativas")
    
    if not metricas_pagamentos.empty:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            ultimo_mes = metricas_pagamentos.iloc[-1]
            penultimo_mes = metricas_pagamentos.iloc[-2] if len(metricas_pagamentos) > 1 else ultimo_mes
            
            variacao = ((ultimo_mes['total_registros'] - penultimo_mes['total_registros']) / penultimo_mes['total_registros']) * 100
            st.metric("Pagamentos (último mês)", 
                     formatar_brasileiro(ultimo_mes['total_registros']),
                     f"{variacao:.1f}%")
        
        with col2:
            variacao_valor = ((ultimo_mes['valor_total'] - penultimo_mes['valor_total']) / penultimo_mes['valor_total']) * 100
            st.metric("Valor Total (último mês)", 
                     formatar_brasileiro(ultimo_mes['valor_total'], 'monetario'),
                     f"{variacao_valor:.1f}%")
        
        with col3:
            variacao_benef = ((ultimo_mes['beneficiarios_unicos'] - penultimo_mes['beneficiarios_unicos']) / penultimo_mes['beneficiarios_unicos']) * 100
            st.metric("Beneficiários (último mês)", 
                     formatar_brasileiro(ultimo_mes['beneficiarios_unicos']),
                     f"{variacao_benef:.1f}%")
        
        with col4:
            variacao_dupl = ((ultimo_mes['pagamentos_duplicados'] - penultimo_mes['pagamentos_duplicados']) / max(penultimo_mes['pagamentos_duplicados'], 1)) * 100
            st.metric("Duplicidades (último mês)", 
                     formatar_brasileiro(ultimo_mes['pagamentos_duplicados']),
                     f"{variacao_dupl:.1f}%")

def mostrar_relatorios_comparativos(conn):
    """Mostra relatórios comparativos entre períodos"""
    st.header("📋 Relatórios Comparativos")
    
    # Carregar métricas
    metricas_pagamentos = carregar_metricas_db(conn, tipo='pagamentos')
    
    if metricas_pagamentos.empty:
        st.info("📊 Nenhum dado disponível para comparação. Faça upload de dados mensais.")
        return
    
    # Seleção de períodos para comparação
    col1, col2 = st.columns(2)
    
    with col1:
        periodos_disponiveis = metricas_pagamentos['mes_referencia'] + '/' + metricas_pagamentos['ano_referencia'].astype(str)
        periodo1 = st.selectbox("Selecione o primeiro período:", periodos_disponiveis.unique())
    
    with col2:
        periodo2 = st.selectbox("Selecione o segundo período:", periodos_disponiveis.unique(), 
                               index=1 if len(periodos_disponiveis.unique()) > 1 else 0)
    
    if periodo1 == periodo2:
        st.warning("Selecione períodos diferentes para comparação.")
        return
    
    # Extrair dados dos períodos selecionados
    dados_periodo1 = metricas_pagamentos[periodos_disponiveis == periodo1].iloc[0]
    dados_periodo2 = metricas_pagamentos[periodos_disponiveis == periodo2].iloc[0]
    
    # Tabela comparativa
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
        ],
        'Variação (%)': [
            f"{((dados_periodo2['total_registros'] - dados_periodo1['total_registros']) / dados_periodo1['total_registros'] * 100):.1f}%",
            f"{((dados_periodo2['beneficiarios_unicos'] - dados_periodo1['beneficiarios_unicos']) / dados_periodo1['beneficiarios_unicos'] * 100):.1f}%",
            f"{((dados_periodo2['contas_unicas'] - dados_periodo1['contas_unicas']) / dados_periodo1['contas_unicas'] * 100):.1f}%",
            f"{((dados_periodo2['valor_total'] - dados_periodo1['valor_total']) / dados_periodo1['valor_total'] * 100):.1f}%",
            f"{((dados_periodo2['pagamentos_duplicados'] - dados_periodo1['pagamentos_duplicados']) / max(dados_periodo1['pagamentos_duplicados'], 1) * 100):.1f}%",
            f"{((dados_periodo2['valor_duplicados'] - dados_periodo1['valor_duplicados']) / max(dados_periodo1['valor_duplicados'], 1) * 100):.1f}%",
            f"{((dados_periodo2['projetos_ativos'] - dados_periodo1['projetos_ativos']) / max(dados_periodo1['projetos_ativos'], 1) * 100):.1f}%",
            f"{((dados_periodo2.get('cpfs_ajuste', 0) - dados_periodo1.get('cpfs_ajuste', 0)) / max(dados_periodo1.get('cpfs_ajuste', 1), 1) * 100):.1f}%",
            f"{((dados_periodo2['registros_problema'] - dados_periodo1['registros_problema']) / max(dados_periodo1['registros_problema'], 1) * 100):.1f}%"
        ]
    }
    
    df_comparativo = pd.DataFrame(comparativo_data)
    st.dataframe(df_comparativo, use_container_width=True)
    
    # Gráfico de comparação
    st.subheader("Gráfico Comparativo")
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        name=periodo1,
        x=comparativo_data['Métrica'],
        y=[dados_periodo1['total_registros'], dados_periodo1['beneficiarios_unicos'], 
           dados_periodo1['contas_unicas'], dados_periodo1['valor_total']/1000,  # Dividir valor por 1000 para escala
           dados_periodo1['pagamentos_duplicados'], dados_periodo1['valor_duplicados']/1000,
           dados_periodo1['projetos_ativos'], dados_periodo1.get('cpfs_ajuste', 0),
           dados_periodo1['registros_problema']],
        marker_color='blue'
    ))
    
    fig.add_trace(go.Bar(
        name=periodo2,
        x=comparativo_data['Métrica'],
        y=[dados_periodo2['total_registros'], dados_periodo2['beneficiarios_unicos'],
           dados_periodo2['contas_unicas'], dados_periodo2['valor_total']/1000,
           dados_periodo2['pagamentos_duplicados'], dados_periodo2['valor_duplicados']/1000,
           dados_periodo2['projetos_ativos'], dados_periodo2.get('cpfs_ajuste', 0),
           dados_periodo2['registros_problema']],
        marker_color='red'
    ))
    
    fig.update_layout(
        title=f"Comparação entre {periodo1} e {periodo2}",
        xaxis_tickangle=-45,
        barmode='group'
    )
    
    st.plotly_chart(fig, use_container_width=True)

def mostrar_dados_historicos(conn):
    """Mostra dados históricos armazenados"""
    st.header("🗃️ Dados Históricos")
    
    # Seleção de tipo de dados
    tipo_dados = st.radio("Selecione o tipo de dados:", ["Pagamentos", "Inscrições", "Métricas"], horizontal=True)
    
    if tipo_dados == "Pagamentos":
        dados = carregar_pagamentos_db(conn)
        if not dados.empty:
            st.subheader("Histórico de Pagamentos")
            st.write(f"Total de registros: {len(dados)}")
            
            # Resumo dos dados
            resumo = dados[['id', 'mes_referencia', 'ano_referencia', 'nome_arquivo', 'data_importacao']].copy()
            st.dataframe(resumo, use_container_width=True)
            
            # Seleção de registro específico para detalhes
            if len(dados) > 0:
                registro_id = st.selectbox("Selecione um registro para ver detalhes:", dados['id'].tolist())
                registro_selecionado = dados[dados['id'] == registro_id].iloc[0]
                
                st.subheader(f"Detalhes do Registro {registro_id}")
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write(f"**Mês/Ano:** {registro_selecionado['mes_referencia']}/{registro_selecionado['ano_referencia']}")
                    st.write(f"**Arquivo:** {registro_selecionado['nome_arquivo']}")
                    st.write(f"**Data de Importação:** {registro_selecionado['data_importacao']}")
                
                with col2:
                    # Carregar dados JSON
                    try:
                        dados_json = json.loads(registro_selecionado['dados_json'])
                        df_detalhes = pd.DataFrame(dados_json)
                        st.write(f"**Total de registros no arquivo:** {len(df_detalhes)}")
                        
                        if len(df_detalhes) > 0:
                            st.write("**Primeiras linhas:**")
                            st.dataframe(df_detalhes.head(5), use_container_width=True)
                    except:
                        st.write("**Erro ao carregar dados detalhados**")
        else:
            st.info("Nenhum dado de pagamentos histórico encontrado.")
    
    elif tipo_dados == "Inscrições":
        dados = carregar_inscricoes_db(conn)
        if not dados.empty:
            st.subheader("Histórico de Inscrições")
            st.write(f"Total de registros: {len(dados)}")
            
            resumo = dados[['id', 'mes_referencia', 'ano_referencia', 'nome_arquivo', 'data_importacao']].copy()
            st.dataframe(resumo, use_container_width=True)
        else:
            st.info("Nenhum dado de inscrições histórico encontrado.")
    
    else:  # Métricas
        dados = carregar_metricas_db(conn)
        if not dados.empty:
            st.subheader("Histórico de Métricas")
            st.write(f"Total de registros: {len(dados)}")
            
            # Filtrar por tipo
            tipo_metricas = st.selectbox("Filtrar por tipo:", ["Todos", "pagamentos", "inscricoes"])
            if tipo_metricas != "Todos":
                dados = dados[dados['tipo'] == tipo_metricas]
            
            st.dataframe(dados, use_container_width=True)
        else:
            st.info("Nenhuma métrica histórica encontrada.")

def mostrar_estatisticas_detalhadas(conn):
    """Mostra estatísticas detalhadas e análises avançadas"""
    st.header("📊 Estatísticas Detalhadas")
    
    # Carregar métricas
    metricas_pagamentos = carregar_metricas_db(conn, tipo='pagamentos')
    
    if metricas_pagamentos.empty:
        st.info("📊 Nenhum dado disponível para análise estatística. Faça upload de dados mensais.")
        return
    
    # Estatísticas gerais
    st.subheader("Estatísticas Gerais")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        total_pagamentos = metricas_pagamentos['total_registros'].sum()
        st.metric("Total de Pagamentos (Histórico)", formatar_brasileiro(total_pagamentos))
    
    with col2:
        valor_total = metricas_pagamentos['valor_total'].sum()
        st.metric("Valor Total (Histórico)", formatar_brasileiro(valor_total, 'monetario'))
    
    with col3:
        media_mensal = metricas_pagamentos['total_registros'].mean()
        st.metric("Média Mensal de Pagamentos", formatar_brasileiro(int(media_mensal)))
    
    # Distribuição por mês
    st.subheader("Distribuição por Mês")
    
    metricas_pagamentos['periodo'] = metricas_pagamentos['mes_referencia'] + '/' + metricas_pagamentos['ano_referencia'].astype(str)
    
    fig = px.bar(metricas_pagamentos, x='periodo', y='total_registros',
                 title='Distribuição de Pagamentos por Mês',
                 labels={'total_registros': 'Total de Pagamentos', 'periodo': 'Período'})
    st.plotly_chart(fig, use_container_width=True)
    
    # Análise de tendência
    st.subheader("Análise de Tendência")
    
    # Calcular tendência linear
    x = np.arange(len(metricas_pagamentos))
    y = metricas_pagamentos['total_registros'].values
    
    if len(metricas_pagamentos) > 1:
        z = np.polyfit(x, y, 1)
        p = np.poly1d(z)
        tendencia = p(x)
        
        fig_tendencia = go.Figure()
        fig_tendencia.add_trace(go.Scatter(x=metricas_pagamentos['periodo'], y=y, mode='lines+markers', name='Pagamentos'))
        fig_tendencia.add_trace(go.Scatter(x=metricas_pagamentos['periodo'], y=tendencia, mode='lines', name='Tendência', line=dict(dash='dash')))
        fig_tendencia.update_layout(title='Tendência de Pagamentos')
        st.plotly_chart(fig_tendencia, use_container_width=True)
        
        # Interpretação da tendência
        inclinacao = z[0]
        if inclinacao > 0:
            st.success(f"📈 Tendência de crescimento: {inclinacao:.1f} pagamentos/mês")
        elif inclinacao < 0:
            st.warning(f"📉 Tendência de decrescimento: {inclinacao:.1f} pagamentos/mês")
        else:
            st.info("➡️ Tendência estável")
    
    # Análise de sazonalidade
    if len(metricas_pagamentos) >= 12:
        st.subheader("Análise de Sazonalidade")
        
        # Agrupar por mês (ignorando ano)
        metricas_pagamentos['mes_num'] = metricas_pagamentos['mes_referencia'].map({
            'Janeiro': 1, 'Fevereiro': 2, 'Março': 3, 'Abril': 4, 'Maio': 5, 'Junho': 6,
            'Julho': 7, 'Agosto': 8, 'Setembro': 9, 'Outubro': 10, 'Novembro': 11, 'Dezembro': 12
        })
        
        media_por_mes = metricas_pagamentos.groupby('mes_num')['total_registros'].mean().reset_index()
        media_por_mes['mes_nome'] = media_por_mes['mes_num'].map({
            1: 'Jan', 2: 'Fev', 3: 'Mar', 4: 'Abr', 5: 'Mai', 6: 'Jun',
            7: 'Jul', 8: 'Ago', 9: 'Set', 10: 'Out', 11: 'Nov', 12: 'Dez'
        })
        
        fig_sazonal = px.line(media_por_mes, x='mes_nome', y='total_registros',
                             title='Padrão Sazonal - Média de Pagamentos por Mês',
                             labels={'total_registros': 'Média de Pagamentos', 'mes_nome': 'Mês'})
        st.plotly_chart(fig_sazonal, use_container_width=True)

# Interface principal do sistema CORRIGIDA
def main():
    # Inicializar banco de dados
    conn = init_database()
    
    # Autenticação
    email_autorizado, tipo_usuario = autenticar(conn)
    
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
        st.write("- Usuário cadastrado pelo administrador")
        return
    
    # A partir daqui, só usuários autenticados têm acesso
    
    # Carregar dados - AGORA COM CONTROLE DE PROCESSAMENTO
    dados, nomes_arquivos, mes_ref, ano_ref, dados_processados = carregar_dados(conn)
    
    # Verificar se há dados para processar
    tem_dados_pagamentos = 'pagamentos' in dados and not dados['pagamentos'].empty
    tem_dados_contas = 'contas' in dados and not dados['contas'].empty
    
    # SEÇÃO MELHORADA: Download de Relatórios
    st.sidebar.markdown("---")
    st.sidebar.header("📥 EXPORTAR RELATÓRIOS")
    
    # PROCESSAR DADOS APENAS SE FORAM CARREGADOS NOVOS DADOS
    metrics = {}
    if dados_processados and (tem_dados_pagamentos or tem_dados_contas):
        with st.spinner("🔄 Processando dados para relatórios..."):
            metrics = processar_dados(dados, nomes_arquivos)
            # Salvar métricas no banco (AGORA COM CONTROLE DE DUPLICIDADE)
            if tem_dados_pagamentos:
                salvar_metricas_db(conn, 'pagamentos', mes_ref, ano_ref, metrics)
            if tem_dados_contas:
                salvar_metricas_db(conn, 'inscricoes', mes_ref, ano_ref, metrics)
    
    # Botões de download sempre visíveis e organizados
    if tem_dados_pagamentos or tem_dados_contas:
        col1, col2 = st.sidebar.columns(2)
        
        with col1:
            if tem_dados_pagamentos:
                pdf_bytes = gerar_pdf_executivo(metrics, dados, nomes_arquivos, 'pagamentos')
            else:
                pdf_bytes = gerar_pdf_executivo(metrics, dados, nomes_arquivos, 'inscricoes')
            
            st.download_button(
                label="📄 PDF Executivo",
                data=pdf_bytes,
                file_name=f"relatorio_executivo_pot_{mes_ref}_{ano_ref}_{data_hora_arquivo_brasilia()}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        
        with col2:
            if tem_dados_pagamentos:
                excel_bytes = gerar_excel_completo(metrics, dados, 'pagamentos')
            else:
                excel_bytes = gerar_excel_completo(metrics, dados, 'inscricoes')
            
            st.download_button(
                label="📊 Excel Completo",
                data=excel_bytes,
                file_name=f"analise_completa_pot_{mes_ref}_{ano_ref}_{data_hora_arquivo_brasilia()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        
        # Botão para planilha de ajustes
        st.sidebar.markdown("---")
        if tem_dados_pagamentos:
            ajustes_bytes = gerar_planilha_ajustes(metrics, 'pagamentos')
        else:
            ajustes_bytes = gerar_planilha_ajustes(metrics, 'inscricoes')
        
        st.download_button(
            label="🔧 Planilha de Ajustes",
            data=ajustes_bytes,
            file_name=f"plano_ajustes_pot_{mes_ref}_{ano_ref}_{data_hora_arquivo_brasilia()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
        
        # Botões para CSV dos dados tratados - SEMPRE VISÍVEIS
        st.sidebar.markdown("---")
        st.sidebar.subheader("💾 Dados Tratados (CSV)")
        
        col3, col4 = st.sidebar.columns(2)
        
        with col3:
            if tem_dados_pagamentos:
                csv_pagamentos = gerar_csv_dados_tratados(dados, 'pagamentos')
                if not csv_pagamentos.empty:
                    st.download_button(
                        label="📋 Pagamentos CSV",
                        data=csv_pagamentos.to_csv(index=False, encoding='utf-8-sig'),
                        file_name=f"pagamentos_tratados_{mes_ref}_{ano_ref}_{data_hora_arquivo_brasilia()}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
        
        with col4:
            if tem_dados_contas:
                csv_inscricoes = gerar_csv_dados_tratados(dados, 'inscricoes')
                if not csv_inscricoes.empty:
                    st.download_button(
                        label="📝 Inscrições CSV",
                        data=csv_inscricoes.to_csv(index=False, encoding='utf-8-sig'),
                        file_name=f"inscricoes_tratadas_{mes_ref}_{ano_ref}_{data_hora_arquivo_brasilia()}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
    else:
        st.sidebar.info("📊 Faça upload dos dados para gerar relatórios")
    
    # ÁREAS ADMINISTRATIVAS - APENAS PARA ADMIN
    st.sidebar.markdown("---")
    
    if tipo_usuario == 'admin':
        # Expander para funções administrativas
        with st.sidebar.expander("⚙️ Administração do Sistema", expanded=False):
            st.success("👑 **MODO ADMINISTRADOR**")
            
            # Sub-expander para gerenciamento de usuários
            with st.expander("👥 Gerenciar Usuários", expanded=False):
                if st.button("Abrir Gerenciador de Usuários"):
                    st.session_state.gerenciar_usuarios = True
            
            # Sub-expander para limpeza de dados
            with st.expander("🚨 Limpeza do Banco de Dados", expanded=False):
                if st.button("Abrir Limpeza de Dados"):
                    st.session_state.limpar_dados = True
            
            # Sub-expander para gerenciamento de registros
            with st.expander("🔍 Gerenciamento de Registros", expanded=False):
                if st.button("Abrir Gerenciador de Registros"):
                    st.session_state.gerenciar_registros = True
    
    # Abas principais do sistema - TODAS IMPLEMENTADAS
    tab_principal, tab_dashboard, tab_relatorios, tab_historico, tab_estatisticas = st.tabs([
        "📊 Análise Mensal", 
        "📈 Dashboard Evolutivo", 
        "📋 Relatórios Comparativos", 
        "🗃️ Dados Históricos",
        "📊 Estatísticas Detalhadas"
    ])
    
    # Aba administrativa apenas para admin
    if tipo_usuario == 'admin':
        if hasattr(st.session_state, 'gerenciar_usuarios') and st.session_state.gerenciar_usuarios:
            gerenciar_usuarios(conn)
            if st.button("Voltar para Análise Principal"):
                st.session_state.gerenciar_usuarios = False
                st.rerun()
            return
        
        if hasattr(st.session_state, 'limpar_dados') and st.session_state.limpar_dados:
            limpar_banco_dados_completo(conn, tipo_usuario)
            if st.button("Voltar para Análise Principal"):
                st.session_state.limpar_dados = False
                st.rerun()
            return
        
        if hasattr(st.session_state, 'gerenciar_registros') and st.session_state.gerenciar_registros:
            gerenciar_registros(conn, tipo_usuario)
            if st.button("Voltar para Análise Principal"):
                st.session_state.gerenciar_registros = False
                st.rerun()
            return
    
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
            # Interface principal
            st.title("🏛️ Sistema POT - SMDET")
            st.markdown("### Análise de Pagamentos e Inscrições")
            st.markdown(f"**Mês de referência:** {mes_ref}/{ano_ref}")
            st.markdown(f"**Data da análise:** {data_hora_atual_brasilia()}")
            
            # Informação sobre linha de totais removida
            if metrics.get('linha_totais_removida', False):
                st.info(f"📝 **Nota:** Linha de totais da planilha foi identificada e excluída da análise ({metrics['total_registros_originais']} → {metrics['total_registros_sem_totais']} registros)")
            
            st.markdown("---")
            
            # Métricas principais
            if tem_dados_pagamentos:
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric(
                        "Total de Pagamentos", 
                        formatar_brasileiro(metrics.get('total_pagamentos', 0)),
                        help="Pagamentos válidos com número de conta (já excluindo linha de totais)"
                    )
                
                with col2:
                    st.metric(
                        "Beneficiários Únicos", 
                        formatar_brasileiro(metrics.get('beneficiarios_unicos', 0))
                    )
                
                with col3:
                    st.metric(
                        "Contas Únicas", 
                        formatar_brasileiro(metrics.get('contas_unicas', 0))
                    )
                
                with col4:
                    st.metric(
                        "Valor Total (Valor Pagto)", 
                        formatar_brasileiro(metrics.get('valor_total', 0), 'monetario'),
                        help="Somatória dos valores da coluna Valor Pagto"
                    )
                
                # Segunda linha de métricas
                col5, col6, col7, col8 = st.columns(4)
                
                with col5:
                    st.metric(
                        "Pagamentos Duplicados", 
                        formatar_brasileiro(metrics.get('pagamentos_duplicados', 0)),
                        delta=f"-{formatar_brasileiro(metrics.get('valor_total_duplicados', 0), 'monetario')}",
                        delta_color="inverse",
                        help="Contas com múltiplos pagamentos"
                    )
                
                with col6:
                    st.metric(
                        "Projetos Ativos", 
                        formatar_brasileiro(metrics.get('projetos_ativos', 0))
                    )
                
                with col7:
                    # Métrica UNIFICADA para CPFs problemáticos
                    problemas_cpf = metrics.get('problemas_cpf', {})
                    total_cpfs_problema = metrics.get('total_cpfs_ajuste', 0)
                    
                    st.metric(
                        "CPFs p/ Ajuste", 
                        formatar_brasileiro(total_cpfs_problema),
                        delta_color="inverse" if total_cpfs_problema > 0 else "off",
                        help=f"CPFs com problemas: {problemas_cpf.get('total_problemas_cpf', 0)} formatação + {problemas_cpf.get('total_cpfs_inconsistentes', 0)} inconsistências"
                    )
                
                with col8:
                    st.metric(
                        "Registros Críticos", 
                        formatar_brasileiro(metrics.get('total_registros_criticos', 0)),
                        delta_color="inverse" if metrics.get('total_registros_criticos', 0) > 0 else "off",
                        help="Registros INVÁLIDOS (sem conta ou valor)"
                    )
            
            if tem_dados_contas:
                st.markdown("---")
                st.subheader("📋 Dados de Inscrições/Contas")
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric(
                        "Total de Inscrições", 
                        formatar_brasileiro(metrics.get('total_contas_abertas', 0))
                    )
                
                with col2:
                    st.metric(
                        "Beneficiários Únicos", 
                        formatar_brasileiro(metrics.get('beneficiarios_contas', 0))
                    )
                
                with col3:
                    st.metric(
                        "Projetos Ativos", 
                        formatar_brasileiro(metrics.get('projetos_ativos', 0))
                    )
            
            st.markdown("---")
            
            # Abas para análises detalhadas
            tab1, tab2, tab3, tab4, tab5 = st.tabs([
                "📋 Visão Geral", 
                "⚠️ Duplicidades", 
                "🔴 CPFs Problemáticos",
                "⏳ Pagamentos Pendentes", 
                "🚨 Problemas Críticos"
            ])
            
            with tab1:
                st.subheader("Resumo dos Dados")
                
                if tem_dados_pagamentos:
                    st.write(f"**Planilha de Pagamentos:** {nomes_arquivos.get('pagamentos', 'N/A')}")
                    
                    # Mostrar apenas total SEM linha de totais
                    st.write(f"**Total de registros válidos:** {metrics.get('total_registros_sem_totais', 0)}")
                    
                    # Mostrar informação sobre remoção de totais se aplicável
                    if metrics.get('linha_totais_removida', False):
                        st.write(f"🔍 **Observação:** Linha de totais removida (originalmente {metrics.get('total_registros_originais', 0)} registros)")
                    
                    st.write(f"**Pagamentos válidos:** {metrics.get('total_pagamentos', 0)}")
                    st.write(f"**Registros sem conta:** {metrics.get('total_registros_invalidos', 0)}")
                
                if tem_dados_contas:
                    st.write(f"**Planilha de Inscrições:** {nomes_arquivos.get('contas', 'N/A')}")
                    st.write(f"**Total de inscrições:** {metrics.get('total_contas_abertas', 0)}")
                    st.write(f"**Beneficiários únicos:** {metrics.get('beneficiarios_contas', 0)}")
            
            with tab2:
                if tem_dados_pagamentos:
                    st.subheader("Pagamentos Duplicados")
                    
                    duplicidades_detalhadas = metrics.get('duplicidades_detalhadas', {})
                    total_contas_duplicadas = duplicidades_detalhadas.get('total_contas_duplicadas', 0)
                    
                    if total_contas_duplicadas > 0:
                        st.warning(f"🚨 Foram encontradas {total_contas_duplicadas} contas com pagamentos duplicados")
                        
                        # Mostrar resumo das duplicidades
                        resumo_duplicidades = duplicidades_detalhadas.get('resumo_duplicidades', pd.DataFrame())
                        if not resumo_duplicidades.empty:
                            st.write("**Resumo das Duplicidades:**")
                            st.dataframe(resumo_duplicidades)
                        
                        # Mostrar detalhes completos
                        detalhes_completos = duplicidades_detalhadas.get('detalhes_completos_duplicidades', pd.DataFrame())
                        if not detalhes_completos.empty:
                            st.write("**Detalhes Completos dos Pagamentos Duplicados:**")
                            st.dataframe(detalhes_completos)
                    else:
                        st.success("✅ Nenhum pagamento duplicado encontrado")
                else:
                    st.info("ℹ️ Esta análise está disponível apenas para dados de pagamentos")
            
            with tab3:
                if tem_dados_pagamentos:
                    st.subheader("CPFs Problemáticos - Correção Necessária")
                    
                    problemas_cpf = metrics.get('problemas_cpf', {})
                    total_problemas = metrics.get('total_cpfs_ajuste', 0)
                    
                    if total_problemas > 0:
                        # Alertas visuais diferenciados
                        col_critico, col_alerta = st.columns(2)
                        
                        with col_critico:
                            total_cpfs_inconsistentes = problemas_cpf.get('total_cpfs_inconsistentes', 0)
                            if total_cpfs_inconsistentes > 0:
                                st.error(f"❌ CRÍTICO: {total_cpfs_inconsistentes} CPFs com INCONSISTÊNCIAS")
                                st.write(f"**CPFs com nomes diferentes:** {len(problemas_cpf.get('cpfs_com_nomes_diferentes', []))}")
                                st.write(f"**CPFs com contas diferentes:** {len(problemas_cpf.get('cpfs_com_contas_diferentes', []))}")
                        
                        with col_alerta:
                            total_problemas_cpf = problemas_cpf.get('total_problemas_cpf', 0)
                            if total_problemas_cpf > 0:
                                st.warning(f"⚠️ ALERTA: {total_problemas_cpf} CPFs com problemas de FORMATAÇÃO")
                                st.write(f"**CPFs vazios:** {len(problemas_cpf.get('cpfs_vazios', []))}")
                                st.write(f"**CPFs com caracteres inválidos:** {len(problemas_cpf.get('cpfs_com_caracteres_invalidos', []))}")
                                st.write(f"**CPFs com tamanho incorreto:** {len(problemas_cpf.get('cpfs_com_tamanho_incorreto', []))}")
                        
                        # Abas para detalhes específicos
                        tab_inconsistentes, tab_formatacao = st.tabs([
                            "🔴 CPFs Inconsistentes", 
                            "📝 CPFs com Problemas de Formatação"
                        ])
                        
                        with tab_inconsistentes:
                            detalhes_inconsistencias = problemas_cpf.get('detalhes_inconsistencias', pd.DataFrame())
                            if not detalhes_inconsistencias.empty:
                                st.write("**CPFs com Inconsistências Críticas:**")
                                st.dataframe(detalhes_inconsistencias)
                            else:
                                st.info("Nenhum CPF com inconsistências críticas encontrado")
                        
                        with tab_formatacao:
                            detalhes_cpfs_problematicos = problemas_cpf.get('detalhes_cpfs_problematicos', pd.DataFrame())
                            if not detalhes_cpfs_problematicos.empty:
                                st.write("**CPFs com Problemas de Formatação:**")
                                st.dataframe(detalhes_cpfs_problematicos)
                            else:
                                st.info("Nenhum CPF com problemas de formatação encontrado")
                    else:
                        st.success("✅ Nenhum problema com CPFs encontrado")
                else:
                    st.info("ℹ️ Esta análise está disponível apenas para dados de pagamentos")
            
            with tab4:
                if tem_dados_pagamentos and tem_dados_contas:
                    st.subheader("Pagamentos Pendentes")
                    
                    pagamentos_pendentes = metrics.get('pagamentos_pendentes', {})
                    total_contas_sem_pagamento = pagamentos_pendentes.get('total_contas_sem_pagamento', 0)
                    
                    if total_contas_sem_pagamento > 0:
                        st.warning(f"⏳ {total_contas_sem_pagamento} contas aguardando pagamento")
                        
                        contas_sem_pagamento = pagamentos_pendentes.get('contas_sem_pagamento', pd.DataFrame())
                        if not contas_sem_pagamento.empty:
                            st.write("**Contas Aguardando Pagamento:**")
                            st.dataframe(contas_sem_pagamento)
                    else:
                        st.success("✅ Todas as contas abertas possuem pagamentos registrados")
                else:
                    st.info("ℹ️ Esta análise requer ambas as planilhas (pagamentos e inscrições)")
            
            with tab5:
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
    
    # IMPLEMENTAÇÃO DAS OUTRAS ABAS
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
    
    # Tabela para usuários autorizados
    conn.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            nome TEXT NOT NULL,
            tipo TEXT NOT NULL DEFAULT 'usuario',
            data_criacao TEXT NOT NULL,
            ativo INTEGER DEFAULT 1
        )
    ''')
    
    # Verificar e adicionar colunas faltantes
    try:
        conn.execute("SELECT cpfs_ajuste FROM metricas_mensais LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE metricas_mensais ADD COLUMN cpfs_ajuste INTEGER")
    
    # Inserir administrador padrão se não existir
    cursor = conn.execute("SELECT * FROM usuarios WHERE email = 'admin@prefeitura.sp.gov.br'")
    if cursor.fetchone() is None:
        conn.execute('''
            INSERT INTO usuarios (email, nome, tipo, data_criacao, ativo)
            VALUES (?, ?, ?, ?, ?)
        ''', ('admin@prefeitura.sp.gov.br', 'Administrador', 'admin', data_hora_atual_brasilia(), 1))
    
    conn.commit()
    return conn

# Função para hash de senha
def hash_senha(senha):
    """Gera hash SHA-256 da senha"""
    return hashlib.sha256(senha.encode()).hexdigest()

# Senha autorizada (Smdetpot2025)
SENHA_AUTORIZADA_HASH = hash_senha("Smdetpot2025")
SENHA_ADMIN_HASH = hash_senha("AdminSmdet2025")

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

# SISTEMA DE AUTENTICAÇÃO MELHORADO
def verificar_usuario_autorizado(conn, email):
    """Verifica se o usuário está autorizado no banco de dados"""
    cursor = conn.execute("SELECT * FROM usuarios WHERE email = ? AND ativo = 1", (email,))
    return cursor.fetchone() is not None

def obter_tipo_usuario(conn, email):
    """Obtém o tipo do usuário (admin ou usuario)"""
    cursor = conn.execute("SELECT tipo FROM usuarios WHERE email = ? AND ativo = 1", (email,))
    resultado = cursor.fetchone()
    return resultado[0] if resultado else None

def autenticar(conn):
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
        st.sidebar.error("🚫 Sistema temporariamente bloqueado. Tente novamente mais tarde.")
        return None, None
    
    # Se já está autenticado, mostrar informações
    if st.session_state.autenticado and st.session_state.email_autorizado:
        tipo_usuario = "👑 Administrador" if st.session_state.tipo_usuario == 'admin' else "👤 Usuário"
        st.sidebar.success(f"✅ Acesso autorizado")
        st.sidebar.info(f"{tipo_usuario}: {st.session_state.email_autorizado}")
        
        if st.sidebar.button("🚪 Sair"):
            st.session_state.autenticado = False
            st.session_state.email_autorizado = None
            st.session_state.tipo_usuario = None
            st.session_state.tentativas_login = 0
            st.rerun()
        
        return st.session_state.email_autorizado, st.session_state.tipo_usuario
    
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
            elif not verificar_usuario_autorizado(conn, email):
                st.sidebar.error("🚫 Usuário não autorizado. Contate o administrador.")
                st.session_state.tentativas_login += 1
            elif hash_senha(senha) != SENHA_AUTORIZADA_HASH:
                # Verificar se é admin tentando login
                if email == 'admin@prefeitura.sp.gov.br' and hash_senha(senha) == SENHA_ADMIN_HASH:
                    # Login de admin bem-sucedido
                    st.session_state.autenticado = True
                    st.session_state.email_autorizado = email
                    st.session_state.tipo_usuario = 'admin'
                    st.session_state.tentativas_login = 0
                    st.sidebar.success("✅ Login de administrador realizado com sucesso!")
                    st.rerun()
                else:
                    st.sidebar.error("❌ Senha incorreta")
                    st.session_state.tentativas_login += 1
            else:
                # Login de usuário normal bem-sucedido
                st.session_state.autenticado = True
                st.session_state.email_autorizado = email
                st.session_state.tipo_usuario = obter_tipo_usuario(conn, email)
                st.session_state.tentativas_login = 0
                st.sidebar.success("✅ Login realizado com sucesso!")
                st.rerun()
            
            # Verificar se excedeu tentativas
            if st.session_state.tentativas_login >= 3:
                st.session_state.bloqueado = True
                st.sidebar.error("🚫 Muitas tentativas falhas. Sistema bloqueado temporariamente.")
    
    return None, None

# FUNÇÃO PARA GERENCIAR USUÁRIOS (APENAS ADMIN)
def gerenciar_usuarios(conn):
    """Interface para gerenciamento de usuários - APENAS ADMIN"""
    st.header("👥 Gerenciamento de Usuários")
    
    # Listar usuários existentes
    st.subheader("Usuários Cadastrados")
    usuarios_df = pd.read_sql_query("SELECT id, email, nome, tipo, data_criacao, ativo FROM usuarios ORDER BY tipo, email", conn)
    
    if not usuarios_df.empty:
        st.dataframe(usuarios_df, use_container_width=True)
    else:
        st.info("Nenhum usuário cadastrado.")
    
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
        
        adicionar = st.form_submit_button("Adicionar Usuário")
        
        if adicionar:
            if not novo_email or not novo_nome:
                st.error("Preencha todos os campos obrigatórios.")
            elif not novo_email.endswith('@prefeitura.sp.gov.br'):
                st.error("O email deve ser institucional (@prefeitura.sp.gov.br).")
            else:
                try:
                    conn.execute('''
                        INSERT INTO usuarios (email, nome, tipo, data_criacao, ativo)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (novo_email, novo_nome, novoTipo, data_hora_atual_brasilia(), 1 if ativo else 0))
                    conn.commit()
                    st.success(f"✅ Usuário {novo_email} adicionado com sucesso!")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("❌ Este email já está cadastrado.")
    
    # Gerenciar usuários existentes
    st.subheader("Gerenciar Usuários Existentes")
    
    if not usuarios_df.empty:
        usuario_selecionado = st.selectbox("Selecione um usuário:", usuarios_df['email'].tolist())
        usuario_info = usuarios_df[usuarios_df['email'] == usuario_selecionado].iloc[0]
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write(f"**ID:** {usuario_info['id']}")
            st.write(f"**Email:** {usuario_info['email']}")
            st.write(f"**Nome:** {usuario_info['nome']}")
        
        with col2:
            st.write(f"**Tipo:** {usuario_info['tipo']}")
            st.write(f"**Data de criação:** {usuario_info['data_criacao']}")
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
            if st.button("🗑️ Excluir Usuário", type="secondary"):
                conn.execute("DELETE FROM usuarios WHERE email = ?", (usuario_selecionado,))
                conn.commit()
                st.success(f"✅ Usuário {usuario_selecionado} excluído!")
                st.rerun()

# FUNÇÃO MELHORADA: LIMPAR BANCO DE DADOS COMPLETAMENTE (APENAS ADMIN)
def limpar_banco_dados_completo(conn, tipo_usuario):
    """Remove TODOS os dados do banco para recomeçar do zero - APENAS ADMIN"""
    
    if tipo_usuario != 'admin':
        st.error("🚫 Acesso negado. Apenas administradores podem executar esta operação.")
        return False
    
    try:
        st.error("**ATENÇÃO CRÍTICA:** Esta operação é IRREVERSÍVEL e deve ser usada APENAS durante testes!")
        st.warning("""
        **Efeitos desta operação:**
        - ❌ Todos os dados de pagamentos serão PERDIDOS
        - ❌ Todos os dados de inscrições serão PERDIDOS  
        - ❌ Todas as métricas históricas serão PERDIDAS
        - 🔄 O sistema recomeçará do ZERO
        """)
        
        # Dupla confirmação
        senha_confirmacao1 = st.text_input("Digite 'LIMPAR TUDO' para confirmar:", type="password", key="confirm1")
        senha_confirmacao2 = st.text_input("Digite novamente 'LIMPAR TUDO':", type="password", key="confirm2")
        
        col1, col2 = st.columns(2)
        with col1:
            botao_limpar = st.button("🗑️ LIMPAR TODOS OS DADOS", type="secondary", use_container_width=True)
        with col2:
            botao_cancelar = st.button("❌ Cancelar", use_container_width=True)
        
        if botao_limpar:
            if senha_confirmacao1 == "LIMPAR TUDO" and senha_confirmacao2 == "LIMPAR TUDO":
                # Executar limpeza COMPLETA
                conn.execute("DELETE FROM pagamentos")
                conn.execute("DELETE FROM inscricoes")
                conn.execute("DELETE FROM metricas_mensais")
                
                # Reiniciar sequências de ID
                conn.execute("DELETE FROM sqlite_sequence WHERE name='pagamentos'")
                conn.execute("DELETE FROM sqlite_sequence WHERE name='inscricoes'") 
                conn.execute("DELETE FROM sqlite_sequence WHERE name='metricas_mensais'")
                
                conn.commit()
                
                st.success("✅ Banco de dados limpo COMPLETAMENTE!")
                st.info("🔄 Recarregue a página para começar novamente")
                return True
            else:
                st.error("❌ Confirmação incorreta. Operação cancelada.")
                return False
        
        if botao_cancelar:
            st.info("Operação de limpeza cancelada.")
            return False
            
    except Exception as e:
        st.error(f"❌ Erro ao limpar banco: {str(e)}")
        return False

# FUNÇÃO PARA VISUALIZAR E EXCLUIR REGISTROS ESPECÍFICOS (APENAS ADMIN)
def gerenciar_registros(conn, tipo_usuario):
    """Permite visualizar e excluir registros específicos - APENAS ADMIN"""
    
    if tipo_usuario != 'admin':
        st.error("🚫 Acesso negado. Apenas administradores podem executar esta operação.")
        return
    
    try:
        st.warning("Área administrativa - Use com cuidado!")
        
        # Selecionar tipo de dados
        tipo_dados = st.selectbox("Tipo de dados:", ["Pagamentos", "Inscrições", "Métricas"])
        
        if tipo_dados == "Pagamentos":
            dados = carregar_pagamentos_db(conn)
        elif tipo_dados == "Inscrições":
            dados = carregar_inscricoes_db(conn)
        else:
            dados = carregar_metricas_db(conn)
        
        if not dados.empty:
            st.write(f"**Total de registros:** {len(dados)}")
            
            # Mostrar resumo
            if tipo_dados in ["Pagamentos", "Inscrições"]:
                resumo = dados[['id', 'mes_referencia', 'ano_referencia', 'nome_arquivo', 'data_importacao']].copy()
                st.dataframe(resumo.head(10))
                
                # Opção de excluir por ID específico
                st.subheader("Excluir Registro Específico")
                id_excluir = st.number_input("ID do registro a excluir:", min_value=1, step=1)
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("🗑️ Excluir por ID", type="secondary", use_container_width=True):
                        if id_excluir:
                            if tipo_dados == "Pagamentos":
                                conn.execute("DELETE FROM pagamentos WHERE id = ?", (int(id_excluir),))
                                # Excluir métricas correspondentes se existirem
                                registro = dados[dados['id'] == int(id_excluir)]
                                if not registro.empty:
                                    mes = registro.iloc[0]['mes_referencia']
                                    ano = registro.iloc[0]['ano_referencia']
                                    conn.execute("DELETE FROM metricas_mensais WHERE mes_referencia = ? AND ano_referencia = ? AND tipo = 'pagamentos'", 
                                               (mes, ano))
                            else:
                                conn.execute("DELETE FROM inscricoes WHERE id = ?", (int(id_excluir),))
                                # Excluir métricas correspondentes se existirem
                                registro = dados[dados['id'] == int(id_excluir)]
                                if not registro.empty:
                                    mes = registro.iloc[0]['mes_referencia']
                                    ano = registro.iloc[0]['ano_referencia']
                                    conn.execute("DELETE FROM metricas_mensais WHERE mes_referencia = ? AND ano_referencia = ? AND tipo = 'inscricoes'", 
                                               (mes, ano))
                            
                            conn.commit()
                            st.success(f"✅ Registro ID {id_excluir} excluído!")
                            st.rerun()
                
                with col2:
                    if st.button("🔄 Atualizar Lista", use_container_width=True):
                        st.rerun()
            
            elif tipo_dados == "Métricas":
                st.dataframe(dados.head(10))
        
        else:
            st.info("Nenhum registro encontrado.")
            
    except Exception as e:
        st.error(f"Erro no gerenciamento: {str(e)}")

# Funções de banco de dados (mantidas iguais)
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
    try:
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
    except sqlite3.OperationalError as e:
        try:
            conn.execute("ALTER TABLE metricas_mensais ADD COLUMN cpfs_ajuste INTEGER")
            conn.commit()
            salvar_metricas_db(conn, tipo, mes_ref, ano_ref, metrics)
        except:
            conn.execute('''
                INSERT INTO metricas_mensais (tipo, mes_referencia, ano_referencia, total_registros, 
                            beneficiarios_unicos, contas_unicas, valor_total, pagamentos_duplicados, 
                            valor_duplicados, projetos_ativos, registros_problema, data_calculo)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (tipo, mes_ref, ano_ref, 
                  metrics.get('total_pagamentos', 0),
                  metrics.get('beneficiarios_unicos', 0),
                  metrics.get('contas_unicas', 0),
                  metrics.get('valor_total', 0),
                  metrics.get('pagamentos_duplicados', 0),
                  metrics.get('valor_total_duplicados', 0),
                  metrics.get('projetos_ativos', 0),
                  metrics.get('total_registros_criticos', 0),
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
        query += " ORDER BY ano_referencia DESC, mes_referencia DESC LIMIT 3"
    elif periodo == 'semestral':
        query += " ORDER BY ano_referencia DESC, mes_referencia DESC LIMIT 6"
    elif periodo == 'anual':
        query += " ORDER BY ano_referencia DESC, mes_referencia DESC LIMIT 12"
    else:
        query += " ORDER BY ano_referencia DESC, mes_referencia DESC"
    
    try:
        df_result = pd.read_sql_query(query, conn, params=params)
        return df_result
    except Exception as e:
        st.error(f"Erro ao carregar métricas: {e}")
        return pd.DataFrame()

# CORREÇÃO: Função para extrair mês e ano do nome do arquivo
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
                if len(grupos[0]) == 4:
                    ano = int(grupos[0])
                    mes_num = int(grupos[1])
                else:
                    ano = int(grupos[2])
                    mes_num = int(grupos[1])
                
                meses_numeros = {
                    1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
                    5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
                    9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
                }
                return meses_numeros.get(mes_num, 'Janeiro'), ano
                
            elif len(grupos) == 2:
                if grupos[0].isdigit():
                    ano = int(grupos[0])
                    mes_str = grupos[1]
                else:
                    mes_str = grupos[0]
                    ano = int(grupos[1])
                
                for key, value in meses_map.items():
                    if key in mes_str:
                        return value, ano
    
    for key, value in meses_map.items():
        if key in nome_upper:
            ano_match = re.search(r'(\d{4})', nome_upper)
            ano = int(ano_match.group(1)) if ano_match else datetime.now().year
            return value, ano
    
    return None, None

# Funções auxiliares (mantidas iguais)
def obter_coluna_conta(df):
    """Identifica a coluna que contém o número da conta"""
    colunas_conta = ['Num Cartao', 'Num_Cartao', 'Conta', 'Número da Conta', 'Numero_Conta', 'Número do Cartão']
    for coluna in colunas_conta:
        if coluna in df.columns:
            return coluna
    return None

def obter_coluna_nome(df):
    """Identifica a coluna que contém o nome do beneficiário"""
    colunas_nome = ['Beneficiario', 'Beneficiário', 'Nome', 'Nome Completo', 'Nome do Beneficiário']
    for coluna in colunas_nome:
        if coluna in df.columns:
            return coluna
    return None

def obter_coluna_valor(df):
    """Identifica a coluna que contém o valor pago, priorizando 'Valor Pagto'"""
    colunas_valor_prioridade = ['Valor Pagto', 'Valor_Pagto', 'Valor Pgto', 'Valor_Pgto', 'Valor', 'Valor_Pago', 'Valor Pagamento']
    for coluna in colunas_valor_prioridade:
        if coluna in df.columns:
            return coluna
    return None

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

# FUNÇÃO CORRIGIDA: Identificar e remover linha de totais
def remover_linha_totais(df):
    """Identifica e remove a linha de totais da planilha de forma inteligente"""
    if df.empty or len(df) <= 1:
        return df
    
    df_limpo = df.copy()
    
    ultima_linha = df_limpo.iloc[-1]
    criterios_totais = 0
    
    colunas_texto = [col for col in df_limpo.columns if df_limpo[col].dtype == 'object']
    for coluna in colunas_texto[:3]:
        if pd.notna(ultima_linha[coluna]):
            valor = str(ultima_linha[coluna]).upper()
            if any(palavra in valor for palavra in ['TOTAL', 'SOMA', 'GERAL', 'TOTAL GERAL']):
                criterios_totais += 2
                break
    
    colunas_numericas = [col for col in df_limpo.columns if df_limpo[col].dtype in ['int64', 'float64']]
    if colunas_numericas:
        medias = df_limpo.iloc[:-1][colunas_numericas].mean()
        
        for coluna in colunas_numericas:
            if pd.notna(ultima_linha[coluna]) and pd.notna(medias[coluna]):
                if ultima_linha[coluna] > medias[coluna] * 10:
                    criterios_totais += 1
    
    if criterios_totais >= 2:
        df_limpo = df_limpo.iloc[:-1].copy()
        st.sidebar.info("📝 Linha de totais identificada e removida automaticamente")
    
    return df_limpo

def filtrar_pagamentos_validos(df):
    """Filtra apenas os registros que possuem número da conta (pagamentos válidos)"""
    coluna_conta = obter_coluna_conta(df)
    
    if not coluna_conta:
        return df
    
    df_filtrado = df[df[coluna_conta].notna() & (df[coluna_conta].astype(str).str.strip() != '')].copy()
    
    palavras_totais = ['TOTAL', 'SOMA', 'GERAL', 'TOTAL GERAL']
    for palavra in palavras_totais:
        mask = df_filtrado[coluna_conta].astype(str).str.upper().str.contains(palavra, na=False)
        df_filtrado = df_filtrado[~mask]
    
    return df_filtrado

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
    
    df_analise = df.copy()
    df_analise['Linha_Planilha_Original'] = df_analise.index + 2
    
    for idx, row in df_analise.iterrows():
        cpf = str(row['CPF']) if pd.notna(row['CPF']) and str(row['CPF']).strip() != '' else ''
        problemas = []
        
        if cpf == '':
            problemas.append('CPF vazio')
            problemas_cpf['cpfs_vazios'].append(idx)
            problemas_cpf['registros_afetados'].append(idx)
        
        elif not cpf.isdigit() and cpf != '':
            problemas.append('Caracteres inválidos')
            problemas_cpf['cpfs_com_caracteres_invalidos'].append(idx)
            problemas_cpf['registros_afetados'].append(idx)
        
        elif len(cpf) != 11 and cpf != '':
            problemas.append(f'Tamanho incorreto ({len(cpf)} dígitos)')
            problemas_cpf['cpfs_com_tamanho_incorreto'].append(idx)
            problemas_cpf['registros_afetados'].append(idx)
        
        if problemas:
            info_problema = {
                'Linha_Planilha': row.get('Linha_Planilha_Original', idx + 2),
                'CPF_Original': row.get('CPF', ''),
                'CPF_Processado': cpf,
                'Problemas_Formatacao': ', '.join(problemas),
                'Status_Registro': 'VÁLIDO - Precisa de correção'
            }
            
            coluna_conta = obter_coluna_conta(df)
            if coluna_conta and coluna_conta in df.columns and pd.notna(row.get(coluna_conta)):
                info_problema['Numero_Conta'] = row[coluna_conta]
            
            coluna_nome = obter_coluna_nome(df)
            if coluna_nome and coluna_nome in df.columns and pd.notna(row.get(coluna_nome)):
                info_problema['Nome'] = row[coluna_nome]
            
            colunas_adicionais = ['Projeto', 'Valor', 'Data', 'Status']
            for coluna in colunas_adicionais:
                if coluna in df.columns and pd.notna(row.get(coluna)):
                    valor = str(row[coluna])
                    if len(valor) > 30:
                        valor = valor[:27] + "..."
                    info_problema[coluna] = valor
            
            if problemas_cpf['detalhes_cpfs_problematicos'].empty:
                problemas_cpf['detalhes_cpfs_problematicos'] = pd.DataFrame([info_problema])
            else:
                problemas_cpf['detalhes_cpfs_problematicos'] = pd.concat([
                    problemas_cpf['detalhes_cpfs_problematicos'],
                    pd.DataFrame([info_problema])
                ], ignore_index=True)
    
    cpfs_duplicados = df_analise[df_analise.duplicated(['CPF'], keep=False)]
    
    if not cpfs_duplicados.empty:
        grupos_cpf = cpfs_duplicados.groupby('CPF')
        
        detalhes_inconsistencias = []
        
        for cpf, grupo in grupos_cpf:
            if len(grupo) > 1:
                problemas_cpf['cpfs_duplicados'].append(cpf)
                
                coluna_nome = obter_coluna_nome(grupo)
                tem_nomes_diferentes = False
                if coluna_nome and coluna_nome in grupo.columns:
                    nomes_unicos = grupo[coluna_nome].dropna().unique()
                    if len(nomes_unicos) > 1:
                        problemas_cpf['cpfs_com_nomes_diferentes'].append(cpf)
                        tem_nomes_diferentes = True
                
                coluna_conta = obter_coluna_conta(grupo)
                tem_contas_diferentes = False
                if coluna_conta and coluna_conta in grupo.columns:
                    contas_unicas = grupo[coluna_conta].dropna().unique()
                    if len(contas_unicas) > 1:
                        problemas_cpf['cpfs_com_contas_diferentes'].append(cpf)
                        tem_contas_diferentes = True
                
                if tem_nomes_diferentes or tem_contas_diferentes:
                    for idx, registro in grupo.iterrows():
                        info_inconsistencia = {
                            'CPF': cpf,
                            'Linha_Planilha': registro['Linha_Planilha_Original'],
                            'Ocorrencia_CPF': f"{list(grupo.index).index(idx) + 1}/{len(grupo)}"
                        }
                        
                        if coluna_nome and coluna_nome in registro:
                            info_inconsistencia['Nome'] = registro[coluna_nome]
                        
                        if coluna_conta and coluna_conta in registro:
                            info_inconsistencia['Numero_Conta'] = registro[coluna_conta]
                        
                        if 'Projeto' in registro:
                            info_inconsistencia['Projeto'] = registro['Projeto']
                        
                        if 'Valor_Limpo' in registro:
                            info_inconsistencia['Valor'] = registro['Valor_Limpo']
                        
                        problemas_inconsistencia = ['CPF DUPLICADO']
                        if tem_nomes_diferentes:
                            problemas_inconsistencia.append('NOMES DIFERENTES')
                        if tem_contas_diferentes:
                            problemas_inconsistencia.append('CONTAS DIFERENTES')
                        
                        info_inconsistencia['Problemas_Inconsistencia'] = ', '.join(problemas_inconsistencia)
                        info_inconsistencia['Status'] = 'CRÍTICO - Correção urgente necessária'
                        
                        detalhes_inconsistencias.append(info_inconsistencia)
        
        if detalhes_inconsistencias:
            problemas_cpf['detalhes_inconsistencias'] = pd.DataFrame(detalhes_inconsistencias)
            problemas_cpf['total_cpfs_inconsistentes'] = len(set(
                problemas_cpf['cpfs_com_nomes_diferentes'] + 
                problemas_cpf['cpfs_com_contas_diferentes']
            ))
    
    problemas_cpf['total_problemas_cpf'] = (
        len(problemas_cpf['cpfs_com_caracteres_invalidos']) +
        len(problemas_cpf['cpfs_com_tamanho_incorreto']) +
        len(problemas_cpf['cpfs_vazios'])
    )
    
    return problemas_cpf

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
    coluna_nome = obter_coluna_nome(df)
    
    if not coluna_conta:
        return duplicidades
    
    contagem_por_conta = df[coluna_conta].value_counts()
    contas_com_multiplos = contagem_por_conta[contagem_por_conta > 1].index.tolist()
    
    duplicidades['contas_com_multiplos_pagamentos'] = contas_com_multiplos
    
    if not contas_com_multiplos:
        return duplicidades
    
    df_duplicados = df[df[coluna_conta].isin(contas_com_multiplos)].copy()
    
    colunas_ordenacao = [coluna_conta]
    colunas_data = ['Data', 'Data Pagto', 'Data_Pagto', 'DataPagto', 'Data Pagamento']
    for col_data in colunas_data:
        if col_data in df_duplicados.columns:
            colunas_ordenacao.append(col_data)
            break
    
    df_duplicados = df_duplicados.sort_values(by=colunas_ordenacao)
    
    df_duplicados['Ocorrencia'] = df_duplicados.groupby(coluna_conta).cumcount() + 1
    df_duplicados['Total_Ocorrencias'] = df_duplicados.groupby(coluna_conta)[coluna_conta].transform('count')
    
    colunas_exibicao_completas = [coluna_conta, 'Ocorrencia', 'Total_Ocorrencias']
    
    if coluna_nome and coluna_nome in df_duplicados.columns:
        colunas_exibicao_completas.append(coluna_nome)
    
    if 'CPF' in df_duplicados.columns:
        colunas_exibicao_completas.append('CPF')
    
    for col_data in colunas_data:
        if col_data in df_duplicados.columns:
            colunas_exibicao_completas.append(col_data)
            break
    
    coluna_valor = obter_coluna_valor(df_duplicados)
    if coluna_valor:
        colunas_exibicao_completas.append(coluna_valor)
    
    if 'Valor_Limpo' in df_duplicados.columns:
        colunas_exibicao_completas.append('Valor_Limpo')
    
    if 'Projeto' in df_duplicados.columns:
        colunas_exibicao_completas.append('Projeto')
    
    if 'Status' in df_duplicados.columns:
        colunas_exibicao_completas.append('Status')
    
    colunas_exibicao_completas = [col for col in colunas_exibicao_completas if col in df_duplicados.columns]
    
    duplicidades['contas_duplicadas'] = df_duplicados[colunas_exibicao_completas]
    duplicidades['detalhes_completos_duplicidades'] = df_duplicados[colunas_exibicao_completas]
    duplicidades['total_contas_duplicadas'] = len(contas_com_multiplos)
    duplicidades['total_pagamentos_duplicados'] = len(df_duplicados)
    
    if 'Valor_Limpo' in df_duplicados.columns:
        duplicidades['valor_total_duplicados'] = df_duplicados['Valor_Limpo'].sum()
    
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
    
    colunas_exibicao = [col for col in colunas_exibicao if col in df_contas_sem_pagamento.columns]
    
    df_contas_sem_pagamento['Status'] = 'Aguardando Pagamento'
    
    pendentes['contas_sem_pagamento'] = df_contas_sem_pagamento[colunas_exibicao + ['Status']]
    pendentes['total_contas_sem_pagamento'] = len(contas_sem_pagamento)
    pendentes['beneficiarios_sem_pagamento'] = df_contas_sem_pagamento[coluna_nome_contas].nunique() if coluna_nome_contas and coluna_nome_contas in df_contas_sem_pagamento.columns else 0
    
    return pendentes

def processar_cpf(cpf):
    """Processa CPF, mantendo apenas números e completando com zeros à esquerda"""
    if pd.isna(cpf) or cpf in ['', 'NaN', 'None', 'nan', 'None', 'NULL']:
        return ''
    
    cpf_str = str(cpf).strip()
    cpf_limpo = re.sub(r'[^\d]', '', cpf_str)
    
    if cpf_limpo == '':
        return ''
    
    if len(cpf_limpo) < 11:
        cpf_limpo = cpf_limpo.zfill(11)
    
    return cpf_limpo

def padronizar_documentos(df):
    """Padroniza RGs e CPFs, CPF apenas números"""
    df_processed = df.copy()
    
    colunas_documentos = ['RG', 'CPF', 'Documento', 'Numero_Documento']
    
    for coluna in colunas_documentos:
        if coluna in df_processed.columns:
            try:
                if coluna == 'CPF':
                    df_processed[coluna] = df_processed[coluna].astype(str).apply(
                        lambda x: processar_cpf(x) if pd.notna(x) and str(x).strip() != '' else ''
                    )
                elif coluna == 'RG':
                    df_processed[coluna] = df_processed[coluna].astype(str).apply(
                        lambda x: re.sub(r'[^a-zA-Z0-9/]', '', x) if pd.notna(x) and str(x).strip() != '' else ''
                    )
                else:
                    df_processed[coluna] = df_processed[coluna].astype(str).apply(
                        lambda x: re.sub(r'[^\w]', '', x) if pd.notna(x) and str(x).strip() != '' else ''
                    )
                
            except Exception as e:
                st.warning(f"⚠️ Não foi possível padronizar a coluna '{coluna}': {str(e)}")
    
    return df_processed

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

def processar_colunas_valor(df):
    """Processa colunas de valor para formato brasileiro, priorizando 'Valor Pagto'"""
    df_processed = df.copy()
    
    colunas_valor_prioridade = ['Valor Pagto', 'Valor_Pagto', 'Valor Pgto', 'Valor_Pgto', 'Valor', 'Valor_Pago', 'Valor Pagamento']
    
    coluna_valor_encontrada = None
    for coluna_valor in colunas_valor_prioridade:
        if coluna_valor in df_processed.columns:
            coluna_valor_encontrada = coluna_valor
            break
    
    if coluna_valor_encontrada:
        try:
            valores_limpos = []
            
            for valor in df_processed[coluna_valor_encontrada]:
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
            st.sidebar.success(f"💰 Coluna de valor utilizada: '{coluna_valor_encontrada}'")
                
        except Exception as e:
            st.warning(f"⚠️ Erro ao processar valores da coluna '{coluna_valor_encontrada}': {str(e)}")
            df_processed['Valor_Limpo'] = 0.0
    else:
        st.warning("⚠️ Nenhuma coluna de valor encontrada na planilha")
        df_processed['Valor_Limpo'] = 0.0
    
    return df_processed

def analisar_ausencia_dados(dados, nome_arquivo_pagamentos=None, nome_arquivo_contas=None):
    """Analisa e reporta apenas dados críticos realmente ausentes"""
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
        df = dados['pagamentos_sem_totais'] if 'pagamentos_sem_totais' in dados else dados['pagamentos']
        
        df = df.reset_index(drop=True)
        df['Linha_Planilha_Original'] = df.index + 2
        
        registros_problematicos = []
        
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
        
        if 'Valor_Limpo' in df.columns:
            mask_valor_invalido = (
                df['Valor_Limpo'].isna() | 
                (df['Valor_Limpo'] == 0)
            )
            valores_invalidos = df[mask_valor_invalido]
            for idx in valores_invalidos.index:
                if idx not in registros_problematicos:
                    registros_problematicos.append(idx)
        
        registros_problematicos_filtrados = []
        for idx in registros_problematicos:
            registro = df.loc[idx]
            tem_conta_valida = coluna_conta and pd.notna(registro[coluna_conta]) and str(registro[coluna_conta]).strip() != ''
            tem_valor_valido = 'Valor_Limpo' in df.columns and pd.notna(registro['Valor_Limpo']) and registro['Valor_Limpo'] > 0
            
            if not tem_conta_valida or not tem_valor_valido:
                registros_problematicos_filtrados.append(idx)
        
        analise_ausencia['registros_criticos_problematicos'] = registros_problematicos_filtrados
        analise_ausencia['total_registros_criticos'] = len(registros_problematicos_filtrados)
        
        if registros_problematicos_filtrados:
            analise_ausencia['registros_problema_detalhados'] = df.loc[registros_problematicos_filtrados].copy()
        
        if registros_problematicos_filtrados:
            resumo = []
            for idx in registros_problematicos_filtrados[:100]:
                registro = df.loc[idx]
                info_ausencia = {
                    'Indice_Registro': idx,
                    'Linha_Planilha': registro.get('Linha_Planilha_Original', idx + 2),
                    'Planilha_Origem': nome_arquivo_pagamentos or 'Pagamentos',
                    'Status_Registro': 'INVÁLIDO - Precisa de correção'
                }
                
                colunas_interesse = []
                colunas_possiveis = [
                    'CPF', 'RG', 'Projeto', 'Valor', 'Beneficiario', 'Beneficiário', 'Nome',
                    'Data', 'Data Pagto', 'Data_Pagto', 'DataPagto',
                    'Num Cartao', 'Num_Cartao', 'Conta', 'Status'
                ]
                
                for col in colunas_possiveis:
                    if col in df.columns:
                        colunas_interesse.append(col)
                
                coluna_conta = obter_coluna_conta(df)
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
    
    analise_ausencia = analisar_ausencia_dados(dados, nomes_arquivos.get('pagamentos'), nomes_arquivos.get('contas'))
    metrics.update(analise_ausencia)
    
    if 'pagamentos' in dados and not dados['pagamentos'].empty:
        df_original = dados['pagamentos']
        metrics['total_registros_originais'] = len(df_original)
        
        df_sem_totais = remover_linha_totais(df_original)
        metrics['total_registros_sem_totais'] = len(df_sem_totais)
        
        if len(df_sem_totais) < len(df_original):
            metrics['linha_totais_removida'] = True
        
        df = filtrar_pagamentos_validos(df_sem_totais)
        
        coluna_conta = obter_coluna_conta(df_sem_totais)
        if coluna_conta:
            registros_invalidos = df_sem_totais[
                df_sem_totais[coluna_conta].isna() | 
                (df_sem_totais[coluna_conta].astype(str).str.strip() == '')
            ]
            metrics['total_registros_invalidos'] = len(registros_invalidos)
        
        if df.empty:
            return metrics
        
        problemas_cpf = identificar_cpfs_problematicos(df)
        metrics['problemas_cpf'] = problemas_cpf
        
        metrics['total_cpfs_ajuste'] = (
            problemas_cpf['total_problemas_cpf'] + 
            problemas_cpf['total_cpfs_inconsistentes']
        )
        
        coluna_beneficiario = obter_coluna_nome(df)
        if coluna_beneficiario and coluna_beneficiario in df.columns:
            metrics['beneficiarios_unicos'] = df[coluna_beneficiario].nunique()
        
        metrics['total_pagamentos'] = len(df)
        
        coluna_conta = obter_coluna_conta(df)
        if coluna_conta and coluna_conta in df.columns:
            metrics['contas_unicas'] = df[coluna_conta].nunique()
            
            duplicidades = detectar_pagamentos_duplicados(df)
            metrics['duplicidades_detalhadas'] = duplicidades
            metrics['pagamentos_duplicados'] = duplicidades['total_contas_duplicadas']
            metrics['valor_total_duplicados'] = duplicidades['valor_total_duplicados']
        
        if 'Projeto' in df.columns:
            metrics['projetos_ativos'] = df['Projeto'].nunique()
        
        if 'Valor_Limpo' in df.columns:
            valores_validos = df['Valor_Limpo'].fillna(0)
            metrics['valor_total'] = valores_validos.sum()
            
            coluna_valor_origem = obter_coluna_valor(df)
            if coluna_valor_origem:
                st.sidebar.success(f"💰 Total calculado a partir de: '{coluna_valor_origem}' = R$ {metrics['valor_total']:,.2f}")
        
        if 'CPF' in df.columns:
            cpfs_duplicados = df[df.duplicated(['CPF'], keep=False)]
            metrics['total_cpfs_duplicados'] = cpfs_duplicados['CPF'].nunique()
    
    if 'contas' in dados and not dados['contas'].empty:
        df_contas = dados['contas']
        
        metrics['total_contas_abertas'] = len(df_contas)
        
        coluna_nome = obter_coluna_nome(df_contas)
        if coluna_nome and coluna_nome in df_contas.columns:
            metrics['beneficiarios_contas'] = df_contas[coluna_nome].nunique()
        
        if 'pagamentos' not in dados or dados['pagamentos'].empty:
            metrics['contas_unicas'] = metrics['total_contas_abertas']
            if 'Projeto' in df_contas.columns:
                metrics['projetos_ativos'] = df_contas['Projeto'].nunique()
    
    pendentes = detectar_pagamentos_pendentes(dados)
    metrics['pagamentos_pendentes'] = pendentes
    
    return metrics

# CLASSE PDF MELHORADA COM TABELAS
class PDFWithTables(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=15)
    
    def add_table_header(self, headers, col_widths):
        """Adiciona cabeçalho da tabela"""
        self.set_fill_color(200, 200, 200)
        self.set_font('Arial', 'B', 10)
        for i, header in enumerate(headers):
            self.cell(col_widths[i], 10, header, 1, 0, 'C', True)
        self.ln()
    
    def add_table_row(self, data, col_widths, row_height=10):
        """Adiciona linha da tabela com quebra de texto"""
        self.set_font('Arial', '', 8)
        
        # Calcular altura necessária para a linha
        max_lines = 1
        for i, cell_data in enumerate(data):
            if cell_data:
                text_width = self.get_string_width(str(cell_data))
                available_width = col_widths[i] - 2  # Margem interna
                if text_width > available_width:
                    lines = self._split_text(str(cell_data), available_width)
                    max_lines = max(max_lines, len(lines))
        
        # Desenhar células
        y_start = self.get_y()
        for i, cell_data in enumerate(data):
            x = self.get_x()
            y = y_start
            
            if cell_data:
                text_width = self.get_string_width(str(cell_data))
                available_width = col_widths[i] - 2
                
                if text_width <= available_width:
                    # Texto cabe em uma linha
                    self.set_xy(x, y)
                    self.cell(col_widths[i], row_height, str(cell_data), 1, 0, 'L')
                else:
                    # Texto precisa de múltiplas linhas
                    lines = self._split_text(str(cell_data), available_width)
                    for j, line in enumerate(lines):
                        self.set_xy(x, y + (j * row_height/2))
                        self.cell(col_widths[i], row_height/2, line, 1, 0, 'L')
            
            else:
                self.set_xy(x, y)
                self.cell(col_widths[i], row_height, '', 1, 0, 'L')
            
            self.set_xy(x + col_widths[i], y_start)
        
        # Mover para próxima linha
        self.set_y(y_start + (max_lines * row_height/2))
    
    def _split_text(self, text, max_width):
        """Divide texto em múltiplas linhas para caber na célula"""
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
                current_line = [word]
        
        if current_line:
            lines.append(' '.join(current_line))
        
        return lines

# FUNÇÃO MELHORADA: Gerar PDF Executivo COM TABELAS ORGANIZADAS
def gerar_pdf_executivo(metrics, dados, nomes_arquivos, tipo_relatorio='pagamentos'):
    """Gera relatório executivo em PDF com tabelas organizadas"""
    pdf = PDFWithTables()
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
                cpfs_com_nomes_diferentes = problemas_cpf.get('cpfs_com_nomes_diferentes', [])
                if cpfs_com_nomes_diferentes:
                    pdf.cell(0, 10, f"    * {len(cpfs_com_nomes_diferentes)} CPFs com nomes diferentes", 0, 1)
                cpfs_com_contas_diferentes = problemas_cpf.get('cpfs_com_contas_diferentes', [])
                if cpfs_com_contas_diferentes:
                    pdf.cell(0, 10, f"    * {len(cpfs_com_contas_diferentes)} CPFs com contas diferentes", 0, 1)
            
            pdf.ln(10)
            
            # TABELA PARA CPFs COM PROBLEMAS DE FORMATAÇÃO
            detalhes_cpfs_problematicos = problemas_cpf.get('detalhes_cpfs_problematicos', pd.DataFrame())
            if not detalhes_cpfs_problematicos.empty:
                pdf.set_font("Arial", 'B', 12)
                pdf.cell(0, 10, "CPFs com Problemas de Formatação:", 0, 1)
                pdf.ln(5)
                
                # Preparar dados para tabela
                table_data = []
                for idx, row in detalhes_cpfs_problematicos.head(15).iterrows():
                    linha_data = [
                        str(row.get('Linha_Planilha', '')),
                        str(row.get('Nome', ''))[:30],  # Limitar tamanho do nome
                        str(row.get('Numero_Conta', ''))[:15],
                        str(row.get('Projeto', ''))[:20],
                        str(row.get('CPF_Original', ''))[:15],
                        str(row.get('Problemas_Formatacao', ''))
                    ]
                    table_data.append(linha_data)
                
                # Definir larguras das colunas
                col_widths = [15, 40, 25, 30, 25, 55]
                headers = ['Linha', 'Nome', 'Conta', 'Projeto', 'CPF', 'Problema']
                
                # Adicionar tabela
                pdf.add_table_header(headers, col_widths)
                for data_row in table_data:
                    if pdf.get_y() > 250:  # Verificar se precisa de nova página
                        pdf.add_page()
                    pdf.add_table_row(data_row, col_widths, row_height=8)
                
                if len(detalhes_cpfs_problematicos) > 15:
                    pdf.ln(5)
                    pdf.set_font("Arial", 'I', 10)
                    pdf.cell(0, 10, f"... e mais {len(detalhes_cpfs_problematicos) - 15} registros", 0, 1)
                
                pdf.ln(10)
            
            # TABELA PARA CPFs COM INCONSISTÊNCIAS CRÍTICAS
            detalhes_inconsistencias = problemas_cpf.get('detalhes_inconsistencias', pd.DataFrame())
            if not detalhes_inconsistencias.empty:
                # Verificar se precisa de nova página
                if pdf.get_y() > 150:
                    pdf.add_page()
                
                pdf.set_font("Arial", 'B', 12)
                pdf.cell(0, 10, "CPFs com Inconsistências Críticas:", 0, 1)
                pdf.ln(5)
                
                # Preparar dados para tabela
                table_data = []
                for idx, row in detalhes_inconsistencias.head(10).iterrows():
                    linha_data = [
                        str(row.get('CPF', ''))[:15],
                        str(row.get('Linha_Planilha', '')),
                        str(row.get('Ocorrencia_CPF', '')),
                        str(row.get('Nome', ''))[:25],
                        str(row.get('Numero_Conta', ''))[:15],
                        str(row.get('Problemas_Inconsistencia', ''))[:40]
                    ]
                    table_data.append(linha_data)
                
                # Definir larguras das colunas
                col_widths = [25, 15, 20, 35, 25, 50]
                headers = ['CPF', 'Linha', 'Ocorrência', 'Nome', 'Conta', 'Problemas']
                
                # Adicionar tabela
                pdf.add_table_header(headers, col_widths)
                for data_row in table_data:
                    if pdf.get_y() > 250:  # Verificar se precisa de nova página
                        pdf.add_page()
                    pdf.add_table_row(data_row, col_widths, row_height=8)
                
                if len(detalhes_inconsistencias) > 10:
                    pdf.ln(5)
                    pdf.set_font("Arial", 'I', 10)
                    pdf.cell(0, 10, f"... e mais {len(detalhes_inconsistencias) - 10} registros", 0, 1)
                
                pdf.ln(10)
        
        total_registros_criticos = metrics.get('total_registros_criticos', 0)
        if total_registros_criticos > 0:
            # Verificar se precisa de nova página
            if pdf.get_y() > 150:
                pdf.add_page()
            
            pdf.set_font("Arial", 'B', 12)
            pdf.set_text_color(255, 165, 0)
            pdf.cell(0, 10, f"ATENÇÃO: {total_registros_criticos} registros com problemas críticos", 0, 1)
            pdf.set_text_color(0, 0, 0)
            
            resumo_ausencias = metrics.get('resumo_ausencias', pd.DataFrame())
            if not resumo_ausencias.empty:
                pdf.set_font("Arial", 'B', 12)
                pdf.cell(0, 10, "Registros Críticos (sem conta ou valor):", 0, 1)
                pdf.ln(5)
                
                # Preparar dados para tabela
                table_data = []
                for idx, row in resumo_ausencias.head(10).iterrows():
                    linha_data = [
                        str(row.get('Linha_Planilha', '')),
                        str(row.get('Nome', ''))[:25],
                        str(row.get('CPF', ''))[:15],
                        str(row.get('Projeto', ''))[:20],
                        str(row.get('Problemas_Identificados', ''))[:40]
                    ]
                    table_data.append(linha_data)
                
                # Definir larguras das colunas
                col_widths = [15, 35, 25, 30, 65]
                headers = ['Linha', 'Nome', 'CPF', 'Projeto', 'Problemas']
                
                # Adicionar tabela
                pdf.add_table_header(headers, col_widths)
                for data_row in table_data:
                    if pdf.get_y() > 250:  # Verificar se precisa de nova página
                        pdf.add_page()
                    pdf.add_table_row(data_row, col_widths, row_height=8)
                
                if len(resumo_ausencias) > 10:
                    pdf.ln(5)
                    pdf.set_font("Arial", 'I', 10)
                    pdf.cell(0, 10, f"... e mais {len(resumo_ausencias) - 10} registros", 0, 1)
    
    return pdf.output(dest='S').encode('latin1')

# FUNÇÃO CORRIGIDA: Gerar Excel Completo com verificação de métricas
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
        
        # Problemas de CPF UNIFICADOS
        problemas_cpf = metrics.get('problemas_cpf', {})
        
        # CPFs com problemas de formatação
        detalhes_cpfs_problematicos = problemas_cpf.get('detalhes_cpfs_problematicos', pd.DataFrame())
        if not detalhes_cpfs_problematicos.empty:
            detalhes_cpfs_problematicos.to_excel(writer, sheet_name='CPFs Formatação', index=False)
        
        # CPFs com inconsistências
        detalhes_inconsistencias = problemas_cpf.get('detalhes_inconsistencias', pd.DataFrame())
        if not detalhes_inconsistencias.empty:
            detalhes_inconsistencias.to_excel(writer, sheet_name='CPFs Inconsistentes', index=False)
        
        # Problemas de dados CRÍTICOS
        resumo_ausencias = metrics.get('resumo_ausencias', pd.DataFrame())
        if not resumo_ausencias.empty:
            resumo_ausencias.to_excel(writer, sheet_name='Problemas Críticos', index=False)
    
    return output.getvalue()

# FUNÇÃO CORRIGIDA: Gerar Planilha de Ajustes com verificação
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
        
        # Ações para CPFs problemáticos (UNIFICADO)
        problemas_cpf = metrics.get('problemas_cpf', {})
        
        total_cpfs_inconsistentes = problemas_cpf.get('total_cpfs_inconsistentes', 0)
        if total_cpfs_inconsistentes > 0:
            acoes.append({
                'Tipo': 'CPF Inconsistente',
                'Descrição': f'{total_cpfs_inconsistentes} CPFs com nomes ou contas diferentes',
                'Ação Recomendada': 'Verificar e corrigir inconsistências nos CPFs duplicados - CORREÇÃO URGENTE',
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
    
    # Ações para problemas CRÍTICOS de dados
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

# NOVA FUNÇÃO: Gerar CSV dos dados tratados por projeto
def gerar_csv_dados_tratados(dados, tipo_dados='pagamentos'):
    """Gera arquivos CSV com dados tratados, organizados por projeto"""
    if tipo_dados == 'pagamentos' and 'pagamentos' in dados and not dados['pagamentos'].empty:
        df = dados['pagamentos'].copy()
        
        # Adicionar coluna de projeto se não existir
        if 'Projeto' not in df.columns:
            df['Projeto'] = 'Geral'
        
        # Processar dados para CSV
        df_csv = df.copy()
        
        # Garantir que todas as colunas importantes estejam presentes
        colunas_padrao = ['CPF', 'Nome', 'Projeto', 'Valor_Limpo']
        coluna_conta = obter_coluna_conta(df)
        if coluna_conta:
            colunas_padrao.insert(2, coluna_conta)
        
        # Selecionar apenas colunas que existem
        colunas_finais = [col for col in colunas_padrao if col in df_csv.columns]
        
        # Adicionar outras colunas relevantes
        colunas_adicionais = ['RG', 'Data', 'Status', 'Beneficiario', 'Beneficiário']
        for col in colunas_adicionais:
            if col in df_csv.columns and col not in colunas_finais:
                colunas_finais.append(col)
        
        return df_csv[colunas_finais]
    
    elif tipo_dados == 'inscricoes' and 'contas' in dados and not dados['contas'].empty:
        df = dados['contas'].copy()
        
        # Adicionar coluna de projeto se não existir
        if 'Projeto' not in df.columns:
            df['Projeto'] = 'Geral'
        
        # Processar dados para CSV
        df_csv = df.copy()
        
        # Garantir que todas as colunas importantes estejam presentes
        colunas_padrao = ['CPF', 'Nome', 'Projeto']
        coluna_conta = obter_coluna_conta(df)
        if coluna_conta:
            colunas_padrao.insert(2, coluna_conta)
        
        # Selecionar apenas colunas que existem
        colunas_finais = [col for col in colunas_padrao if col in df_csv.columns]
        
        # Adicionar outras colunas relevantes
        colunas_adicionais = ['RG', 'Data', 'Status', 'Beneficiario', 'Beneficiário', 'Data_Abertura']
        for col in colunas_adicionais:
            if col in df_csv.columns and col not in colunas_finais:
                colunas_finais.append(col)
        
        return df_csv[colunas_finais]
    
    return pd.DataFrame()

# CORREÇÃO: Sistema de upload de dados
def carregar_dados(conn):
    st.sidebar.header("📤 Carregar Dados Mensais")
    
    # Inicializar variáveis de mês/ano
    mes_ref_detectado = None
    ano_ref_detectado = None
    
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
    
    # CORREÇÃO: Detectar mês/ano automaticamente dos nomes dos arquivos
    if upload_pagamentos is not None:
        mes_ref_detectado, ano_ref_detectado = extrair_mes_ano_arquivo(upload_pagamentos.name)
        if mes_ref_detectado and ano_ref_detectado:
            st.sidebar.info(f"📅 Mês/ano detectado: {mes_ref_detectado}/{ano_ref_detectado}")
    
    if upload_contas is not None and (not mes_ref_detectado or not ano_ref_detectado):
        mes_contas, ano_contas = extrair_mes_ano_arquivo(upload_contas.name)
        if mes_contas and ano_contas:
            mes_ref_detectado = mes_contas
            ano_ref_detectado = ano_contas
            st.sidebar.info(f"📅 Mês/ano detectado: {mes_ref_detectado}/{ano_ref_detectado}")
    
    # Seleção de mês e ano de referência com valores detectados como padrão
    col1, col2 = st.sidebar.columns(2)
    with col1:
        meses = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
        mes_ref_padrao = mes_ref_detectado if mes_ref_detectado else 'Outubro'
        mes_ref = st.selectbox("Mês de Referência", meses, index=meses.index(mes_ref_padrao) if mes_ref_padrao in meses else 9)
    with col2:
        ano_atual = datetime.now().year
        anos = [ano_atual, ano_atual-1, ano_atual-2]
        ano_ref_padrao = ano_ref_detectado if ano_ref_detectado else ano_atual
        ano_ref = st.selectbox("Ano de Referência", anos, index=anos.index(ano_ref_padrao) if ano_ref_padrao in anos else 0)
    
    st.sidebar.markdown("---")
    
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
            
            # Guardar versão original e versão sem totais
            dados['pagamentos_original'] = df_pagamentos.copy()
            
            # Remover linha de totais antes do processamento
            df_pagamentos_sem_totais = remover_linha_totais(df_pagamentos)
            dados['pagamentos_sem_totais'] = df_pagamentos_sem_totais
            
            # CORREÇÃO: Processar valores ANTES de outras operações
            df_pagamentos_sem_totais = processar_colunas_valor(df_pagamentos_sem_totais)
            df_pagamentos_sem_totais = processar_colunas_data(df_pagamentos_sem_totais)
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

# FUNÇÕES PARA AS OUTRAS ABAS
def mostrar_dashboard_evolutivo(conn):
    """Mostra dashboard com evolução temporal dos dados"""
    st.header("📈 Dashboard Evolutivo")
    
    # Carregar métricas históricas
    metricas_pagamentos = carregar_metricas_db(conn, tipo='pagamentos')
    metricas_inscricoes = carregar_metricas_db(conn, tipo='inscricoes')
    
    if metricas_pagamentos.empty and metricas_inscricoes.empty:
        st.info("📊 Nenhum dado histórico disponível. Faça upload de dados mensais para ver a evolução.")
        return
    
    # Criar período para exibição
    if not metricas_pagamentos.empty:
        metricas_pagamentos['periodo'] = metricas_pagamentos['mes_referencia'] + '/' + metricas_pagamentos['ano_referencia'].astype(str)
        metricas_pagamentos = metricas_pagamentos.sort_values(['ano_referencia', 'mes_referencia'])
    
    if not metricas_inscricoes.empty:
        metricas_inscricoes['periodo'] = metricas_inscricoes['mes_referencia'] + '/' + metricas_inscricoes['ano_referencia'].astype(str)
        metricas_inscricoes = metricas_inscricoes.sort_values(['ano_referencia', 'mes_referencia'])
    
    # Gráficos de evolução
    col1, col2 = st.columns(2)
    
    with col1:
        if not metricas_pagamentos.empty:
            st.subheader("Evolução de Pagamentos")
            
            fig = px.line(metricas_pagamentos, x='periodo', y='total_registros',
                         title='Total de Pagamentos por Mês',
                         labels={'total_registros': 'Total de Pagamentos', 'periodo': 'Período'})
            st.plotly_chart(fig, use_container_width=True)
            
            fig2 = px.line(metricas_pagamentos, x='periodo', y='valor_total',
                         title='Valor Total dos Pagamentos',
                         labels={'valor_total': 'Valor Total (R$)', 'periodo': 'Período'})
            st.plotly_chart(fig2, use_container_width=True)
    
    with col2:
        if not metricas_inscricoes.empty:
            st.subheader("Evolução de Inscrições")
            
            fig = px.line(metricas_inscricoes, x='periodo', y='total_registros',
                         title='Total de Inscrições por Mês',
                         labels={'total_registros': 'Total de Inscrições', 'periodo': 'Período'})
            st.plotly_chart(fig, use_container_width=True)
            
            fig2 = px.line(metricas_inscricoes, x='periodo', y='beneficiarios_unicos',
                         title='Beneficiários Únicos por Mês',
                         labels={'beneficiarios_unicos': 'Beneficiários Únicos', 'periodo': 'Período'})
            st.plotly_chart(fig2, use_container_width=True)
    
    # Métricas comparativas
    st.subheader("Métricas Comparativas")
    
    if not metricas_pagamentos.empty:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            ultimo_mes = metricas_pagamentos.iloc[-1]
            penultimo_mes = metricas_pagamentos.iloc[-2] if len(metricas_pagamentos) > 1 else ultimo_mes
            
            variacao = ((ultimo_mes['total_registros'] - penultimo_mes['total_registros']) / penultimo_mes['total_registros']) * 100
            st.metric("Pagamentos (último mês)", 
                     formatar_brasileiro(ultimo_mes['total_registros']),
                     f"{variacao:.1f}%")
        
        with col2:
            variacao_valor = ((ultimo_mes['valor_total'] - penultimo_mes['valor_total']) / penultimo_mes['valor_total']) * 100
            st.metric("Valor Total (último mês)", 
                     formatar_brasileiro(ultimo_mes['valor_total'], 'monetario'),
                     f"{variacao_valor:.1f}%")
        
        with col3:
            variacao_benef = ((ultimo_mes['beneficiarios_unicos'] - penultimo_mes['beneficiarios_unicos']) / penultimo_mes['beneficiarios_unicos']) * 100
            st.metric("Beneficiários (último mês)", 
                     formatar_brasileiro(ultimo_mes['beneficiarios_unicos']),
                     f"{variacao_benef:.1f}%")
        
        with col4:
            variacao_dupl = ((ultimo_mes['pagamentos_duplicados'] - penultimo_mes['pagamentos_duplicados']) / max(penultimo_mes['pagamentos_duplicados'], 1)) * 100
            st.metric("Duplicidades (último mês)", 
                     formatar_brasileiro(ultimo_mes['pagamentos_duplicados']),
                     f"{variacao_dupl:.1f}%")

def mostrar_relatorios_comparativos(conn):
    """Mostra relatórios comparativos entre períodos"""
    st.header("📋 Relatórios Comparativos")
    
    # Carregar métricas
    metricas_pagamentos = carregar_metricas_db(conn, tipo='pagamentos')
    
    if metricas_pagamentos.empty:
        st.info("📊 Nenhum dado disponível para comparação. Faça upload de dados mensais.")
        return
    
    # Seleção de períodos para comparação
    col1, col2 = st.columns(2)
    
    with col1:
        periodos_disponiveis = metricas_pagamentos['mes_referencia'] + '/' + metricas_pagamentos['ano_referencia'].astype(str)
        periodo1 = st.selectbox("Selecione o primeiro período:", periodos_disponiveis.unique())
    
    with col2:
        periodo2 = st.selectbox("Selecione o segundo período:", periodos_disponiveis.unique(), 
                               index=1 if len(periodos_disponiveis.unique()) > 1 else 0)
    
    if periodo1 == periodo2:
        st.warning("Selecione períodos diferentes para comparação.")
        return
    
    # Extrair dados dos períodos selecionados
    dados_periodo1 = metricas_pagamentos[periodos_disponiveis == periodo1].iloc[0]
    dados_periodo2 = metricas_pagamentos[periodos_disponiveis == periodo2].iloc[0]
    
    # Tabela comparativa
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
        ],
        'Variação (%)': [
            f"{((dados_periodo2['total_registros'] - dados_periodo1['total_registros']) / dados_periodo1['total_registros'] * 100):.1f}%",
            f"{((dados_periodo2['beneficiarios_unicos'] - dados_periodo1['beneficiarios_unicos']) / dados_periodo1['beneficiarios_unicos'] * 100):.1f}%",
            f"{((dados_periodo2['contas_unicas'] - dados_periodo1['contas_unicas']) / dados_periodo1['contas_unicas'] * 100):.1f}%",
            f"{((dados_periodo2['valor_total'] - dados_periodo1['valor_total']) / dados_periodo1['valor_total'] * 100):.1f}%",
            f"{((dados_periodo2['pagamentos_duplicados'] - dados_periodo1['pagamentos_duplicados']) / max(dados_periodo1['pagamentos_duplicados'], 1) * 100):.1f}%",
            f"{((dados_periodo2['valor_duplicados'] - dados_periodo1['valor_duplicados']) / max(dados_periodo1['valor_duplicados'], 1) * 100):.1f}%",
            f"{((dados_periodo2['projetos_ativos'] - dados_periodo1['projetos_ativos']) / max(dados_periodo1['projetos_ativos'], 1) * 100):.1f}%",
            f"{((dados_periodo2.get('cpfs_ajuste', 0) - dados_periodo1.get('cpfs_ajuste', 0)) / max(dados_periodo1.get('cpfs_ajuste', 1), 1) * 100):.1f}%",
            f"{((dados_periodo2['registros_problema'] - dados_periodo1['registros_problema']) / max(dados_periodo1['registros_problema'], 1) * 100):.1f}%"
        ]
    }
    
    df_comparativo = pd.DataFrame(comparativo_data)
    st.dataframe(df_comparativo, use_container_width=True)
    
    # Gráfico de comparação
    st.subheader("Gráfico Comparativo")
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        name=periodo1,
        x=comparativo_data['Métrica'],
        y=[dados_periodo1['total_registros'], dados_periodo1['beneficiarios_unicos'], 
           dados_periodo1['contas_unicas'], dados_periodo1['valor_total']/1000,  # Dividir valor por 1000 para escala
           dados_periodo1['pagamentos_duplicados'], dados_periodo1['valor_duplicados']/1000,
           dados_periodo1['projetos_ativos'], dados_periodo1.get('cpfs_ajuste', 0),
           dados_periodo1['registros_problema']],
        marker_color='blue'
    ))
    
    fig.add_trace(go.Bar(
        name=periodo2,
        x=comparativo_data['Métrica'],
        y=[dados_periodo2['total_registros'], dados_periodo2['beneficiarios_unicos'],
           dados_periodo2['contas_unicas'], dados_periodo2['valor_total']/1000,
           dados_periodo2['pagamentos_duplicados'], dados_periodo2['valor_duplicados']/1000,
           dados_periodo2['projetos_ativos'], dados_periodo2.get('cpfs_ajuste', 0),
           dados_periodo2['registros_problema']],
        marker_color='red'
    ))
    
    fig.update_layout(
        title=f"Comparação entre {periodo1} e {periodo2}",
        xaxis_tickangle=-45,
        barmode='group'
    )
    
    st.plotly_chart(fig, use_container_width=True)

def mostrar_dados_historicos(conn):
    """Mostra dados históricos armazenados"""
    st.header("🗃️ Dados Históricos")
    
    # Seleção de tipo de dados
    tipo_dados = st.radio("Selecione o tipo de dados:", ["Pagamentos", "Inscrições", "Métricas"], horizontal=True)
    
    if tipo_dados == "Pagamentos":
        dados = carregar_pagamentos_db(conn)
        if not dados.empty:
            st.subheader("Histórico de Pagamentos")
            st.write(f"Total de registros: {len(dados)}")
            
            # Resumo dos dados
            resumo = dados[['id', 'mes_referencia', 'ano_referencia', 'nome_arquivo', 'data_importacao']].copy()
            st.dataframe(resumo, use_container_width=True)
            
            # Seleção de registro específico para detalhes
            if len(dados) > 0:
                registro_id = st.selectbox("Selecione um registro para ver detalhes:", dados['id'].tolist())
                registro_selecionado = dados[dados['id'] == registro_id].iloc[0]
                
                st.subheader(f"Detalhes do Registro {registro_id}")
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write(f"**Mês/Ano:** {registro_selecionado['mes_referencia']}/{registro_selecionado['ano_referencia']}")
                    st.write(f"**Arquivo:** {registro_selecionado['nome_arquivo']}")
                    st.write(f"**Data de Importação:** {registro_selecionado['data_importacao']}")
                
                with col2:
                    # Carregar dados JSON
                    try:
                        dados_json = json.loads(registro_selecionado['dados_json'])
                        df_detalhes = pd.DataFrame(dados_json)
                        st.write(f"**Total de registros no arquivo:** {len(df_detalhes)}")
                        
                        if len(df_detalhes) > 0:
                            st.write("**Primeiras linhas:**")
                            st.dataframe(df_detalhes.head(5), use_container_width=True)
                    except:
                        st.write("**Erro ao carregar dados detalhados**")
        else:
            st.info("Nenhum dado de pagamentos histórico encontrado.")
    
    elif tipo_dados == "Inscrições":
        dados = carregar_inscricoes_db(conn)
        if not dados.empty:
            st.subheader("Histórico de Inscrições")
            st.write(f"Total de registros: {len(dados)}")
            
            resumo = dados[['id', 'mes_referencia', 'ano_referencia', 'nome_arquivo', 'data_importacao']].copy()
            st.dataframe(resumo, use_container_width=True)
        else:
            st.info("Nenhum dado de inscrições histórico encontrado.")
    
    else:  # Métricas
        dados = carregar_metricas_db(conn)
        if not dados.empty:
            st.subheader("Histórico de Métricas")
            st.write(f"Total de registros: {len(dados)}")
            
            # Filtrar por tipo
            tipo_metricas = st.selectbox("Filtrar por tipo:", ["Todos", "pagamentos", "inscricoes"])
            if tipo_metricas != "Todos":
                dados = dados[dados['tipo'] == tipo_metricas]
            
            st.dataframe(dados, use_container_width=True)
        else:
            st.info("Nenhuma métrica histórica encontrada.")

def mostrar_estatisticas_detalhadas(conn):
    """Mostra estatísticas detalhadas e análises avançadas"""
    st.header("📊 Estatísticas Detalhadas")
    
    # Carregar métricas
    metricas_pagamentos = carregar_metricas_db(conn, tipo='pagamentos')
    
    if metricas_pagamentos.empty:
        st.info("📊 Nenhum dado disponível para análise estatística. Faça upload de dados mensais.")
        return
    
    # Estatísticas gerais
    st.subheader("Estatísticas Gerais")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        total_pagamentos = metricas_pagamentos['total_registros'].sum()
        st.metric("Total de Pagamentos (Histórico)", formatar_brasileiro(total_pagamentos))
    
    with col2:
        valor_total = metricas_pagamentos['valor_total'].sum()
        st.metric("Valor Total (Histórico)", formatar_brasileiro(valor_total, 'monetario'))
    
    with col3:
        media_mensal = metricas_pagamentos['total_registros'].mean()
        st.metric("Média Mensal de Pagamentos", formatar_brasileiro(int(media_mensal)))
    
    # Distribuição por mês
    st.subheader("Distribuição por Mês")
    
    metricas_pagamentos['periodo'] = metricas_pagamentos['mes_referencia'] + '/' + metricas_pagamentos['ano_referencia'].astype(str)
    
    fig = px.bar(metricas_pagamentos, x='periodo', y='total_registros',
                 title='Distribuição de Pagamentos por Mês',
                 labels={'total_registros': 'Total de Pagamentos', 'periodo': 'Período'})
    st.plotly_chart(fig, use_container_width=True)
    
    # Análise de tendência
    st.subheader("Análise de Tendência")
    
    # Calcular tendência linear
    x = np.arange(len(metricas_pagamentos))
    y = metricas_pagamentos['total_registros'].values
    
    if len(metricas_pagamentos) > 1:
        z = np.polyfit(x, y, 1)
        p = np.poly1d(z)
        tendencia = p(x)
        
        fig_tendencia = go.Figure()
        fig_tendencia.add_trace(go.Scatter(x=metricas_pagamentos['periodo'], y=y, mode='lines+markers', name='Pagamentos'))
        fig_tendencia.add_trace(go.Scatter(x=metricas_pagamentos['periodo'], y=tendencia, mode='lines', name='Tendência', line=dict(dash='dash')))
        fig_tendencia.update_layout(title='Tendência de Pagamentos')
        st.plotly_chart(fig_tendencia, use_container_width=True)
        
        # Interpretação da tendência
        inclinacao = z[0]
        if inclinacao > 0:
            st.success(f"📈 Tendência de crescimento: {inclinacao:.1f} pagamentos/mês")
        elif inclinacao < 0:
            st.warning(f"📉 Tendência de decrescimento: {inclinacao:.1f} pagamentos/mês")
        else:
            st.info("➡️ Tendência estável")
    
    # Análise de sazonalidade
    if len(metricas_pagamentos) >= 12:
        st.subheader("Análise de Sazonalidade")
        
        # Agrupar por mês (ignorando ano)
        metricas_pagamentos['mes_num'] = metricas_pagamentos['mes_referencia'].map({
            'Janeiro': 1, 'Fevereiro': 2, 'Março': 3, 'Abril': 4, 'Maio': 5, 'Junho': 6,
            'Julho': 7, 'Agosto': 8, 'Setembro': 9, 'Outubro': 10, 'Novembro': 11, 'Dezembro': 12
        })
        
        media_por_mes = metricas_pagamentos.groupby('mes_num')['total_registros'].mean().reset_index()
        media_por_mes['mes_nome'] = media_por_mes['mes_num'].map({
            1: 'Jan', 2: 'Fev', 3: 'Mar', 4: 'Abr', 5: 'Mai', 6: 'Jun',
            7: 'Jul', 8: 'Ago', 9: 'Set', 10: 'Out', 11: 'Nov', 12: 'Dez'
        })
        
        fig_sazonal = px.line(media_por_mes, x='mes_nome', y='total_registros',
                             title='Padrão Sazonal - Média de Pagamentos por Mês',
                             labels={'total_registros': 'Média de Pagamentos', 'mes_nome': 'Mês'})
        st.plotly_chart(fig_sazonal, use_container_width=True)

# Interface principal do sistema CORRIGIDA
def main():
    # Inicializar banco de dados
    conn = init_database()
    
    # Autenticação
    email_autorizado, tipo_usuario = autenticar(conn)
    
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
        st.write("- Usuário cadastrado pelo administrador")
        return
    
    # A partir daqui, só usuários autenticados têm acesso
    
    # Carregar dados
    dados, nomes_arquivos, mes_ref, ano_ref = carregar_dados(conn)
    
    # Verificar se há dados para processar
    tem_dados_pagamentos = 'pagamentos' in dados and not dados['pagamentos'].empty
    tem_dados_contas = 'contas' in dados and not dados['contas'].empty
    
    # SEÇÃO MELHORADA: Download de Relatórios
    st.sidebar.markdown("---")
    st.sidebar.header("📥 EXPORTAR RELATÓRIOS")
    
    # PROCESSAR DADOS ANTES DE GERAR RELATÓRIOS
    metrics = {}
    if tem_dados_pagamentos or tem_dados_contas:
        with st.spinner("🔄 Processando dados para relatórios..."):
            metrics = processar_dados(dados, nomes_arquivos)
            # Salvar métricas no banco
            if tem_dados_pagamentos:
                salvar_metricas_db(conn, 'pagamentos', mes_ref, ano_ref, metrics)
            if tem_dados_contas:
                salvar_metricas_db(conn, 'inscricoes', mes_ref, ano_ref, metrics)
    
    # Botões de download sempre visíveis e organizados
    if tem_dados_pagamentos or tem_dados_contas:
        col1, col2 = st.sidebar.columns(2)
        
        with col1:
            if tem_dados_pagamentos:
                pdf_bytes = gerar_pdf_executivo(metrics, dados, nomes_arquivos, 'pagamentos')
            else:
                pdf_bytes = gerar_pdf_executivo(metrics, dados, nomes_arquivos, 'inscricoes')
            
            st.download_button(
                label="📄 PDF Executivo",
                data=pdf_bytes,
                file_name=f"relatorio_executivo_pot_{mes_ref}_{ano_ref}_{data_hora_arquivo_brasilia()}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        
        with col2:
            if tem_dados_pagamentos:
                excel_bytes = gerar_excel_completo(metrics, dados, 'pagamentos')
            else:
                excel_bytes = gerar_excel_completo(metrics, dados, 'inscricoes')
            
            st.download_button(
                label="📊 Excel Completo",
                data=excel_bytes,
                file_name=f"analise_completa_pot_{mes_ref}_{ano_ref}_{data_hora_arquivo_brasilia()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        
        # Botão para planilha de ajustes
        st.sidebar.markdown("---")
        if tem_dados_pagamentos:
            ajustes_bytes = gerar_planilha_ajustes(metrics, 'pagamentos')
        else:
            ajustes_bytes = gerar_planilha_ajustes(metrics, 'inscricoes')
        
        st.download_button(
            label="🔧 Planilha de Ajustes",
            data=ajustes_bytes,
            file_name=f"plano_ajustes_pot_{mes_ref}_{ano_ref}_{data_hora_arquivo_brasilia()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
        
        # Botões para CSV dos dados tratados - SEMPRE VISÍVEIS
        st.sidebar.markdown("---")
        st.sidebar.subheader("💾 Dados Tratados (CSV)")
        
        col3, col4 = st.sidebar.columns(2)
        
        with col3:
            if tem_dados_pagamentos:
                csv_pagamentos = gerar_csv_dados_tratados(dados, 'pagamentos')
                if not csv_pagamentos.empty:
                    st.download_button(
                        label="📋 Pagamentos CSV",
                        data=csv_pagamentos.to_csv(index=False, encoding='utf-8-sig'),
                        file_name=f"pagamentos_tratados_{mes_ref}_{ano_ref}_{data_hora_arquivo_brasilia()}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
        
        with col4:
            if tem_dados_contas:
                csv_inscricoes = gerar_csv_dados_tratados(dados, 'inscricoes')
                if not csv_inscricoes.empty:
                    st.download_button(
                        label="📝 Inscrições CSV",
                        data=csv_inscricoes.to_csv(index=False, encoding='utf-8-sig'),
                        file_name=f"inscricoes_tratadas_{mes_ref}_{ano_ref}_{data_hora_arquivo_brasilia()}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
    else:
        st.sidebar.info("📊 Faça upload dos dados para gerar relatórios")
    
    # ÁREAS ADMINISTRATIVAS - APENAS PARA ADMIN
    st.sidebar.markdown("---")
    
    if tipo_usuario == 'admin':
        # Expander para funções administrativas
        with st.sidebar.expander("⚙️ Administração do Sistema", expanded=False):
            st.success("👑 **MODO ADMINISTRADOR**")
            
            # Sub-expander para gerenciamento de usuários
            with st.expander("👥 Gerenciar Usuários", expanded=False):
                if st.button("Abrir Gerenciador de Usuários"):
                    st.session_state.gerenciar_usuarios = True
            
            # Sub-expander para limpeza de dados
            with st.expander("🚨 Limpeza do Banco de Dados", expanded=False):
                if st.button("Abrir Limpeza de Dados"):
                    st.session_state.limpar_dados = True
            
            # Sub-expander para gerenciamento de registros
            with st.expander("🔍 Gerenciamento de Registros", expanded=False):
                if st.button("Abrir Gerenciador de Registros"):
                    st.session_state.gerenciar_registros = True
    
    # Abas principais do sistema - TODAS IMPLEMENTADAS
    tab_principal, tab_dashboard, tab_relatorios, tab_historico, tab_estatisticas = st.tabs([
        "📊 Análise Mensal", 
        "📈 Dashboard Evolutivo", 
        "📋 Relatórios Comparativos", 
        "🗃️ Dados Históricos",
        "📊 Estatísticas Detalhadas"
    ])
    
    # Aba administrativa apenas para admin
    if tipo_usuario == 'admin':
        if hasattr(st.session_state, 'gerenciar_usuarios') and st.session_state.gerenciar_usuarios:
            gerenciar_usuarios(conn)
            if st.button("Voltar para Análise Principal"):
                st.session_state.gerenciar_usuarios = False
                st.rerun()
            return
        
        if hasattr(st.session_state, 'limpar_dados') and st.session_state.limpar_dados:
            limpar_banco_dados_completo(conn, tipo_usuario)
            if st.button("Voltar para Análise Principal"):
                st.session_state.limpar_dados = False
                st.rerun()
            return
        
        if hasattr(st.session_state, 'gerenciar_registros') and st.session_state.gerenciar_registros:
            gerenciar_registros(conn, tipo_usuario)
            if st.button("Voltar para Análise Principal"):
                st.session_state.gerenciar_registros = False
                st.rerun()
            return
    
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
            # Interface principal
            st.title("🏛️ Sistema POT - SMDET")
            st.markdown("### Análise de Pagamentos e Inscrições")
            st.markdown(f"**Mês de referência:** {mes_ref}/{ano_ref}")
            st.markdown(f"**Data da análise:** {data_hora_atual_brasilia()}")
            
            # Informação sobre linha de totais removida
            if metrics.get('linha_totais_removida', False):
                st.info(f"📝 **Nota:** Linha de totais da planilha foi identificada e excluída da análise ({metrics['total_registros_originais']} → {metrics['total_registros_sem_totais']} registros)")
            
            st.markdown("---")
            
            # Métricas principais
            if tem_dados_pagamentos:
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric(
                        "Total de Pagamentos", 
                        formatar_brasileiro(metrics.get('total_pagamentos', 0)),
                        help="Pagamentos válidos com número de conta (já excluindo linha de totais)"
                    )
                
                with col2:
                    st.metric(
                        "Beneficiários Únicos", 
                        formatar_brasileiro(metrics.get('beneficiarios_unicos', 0))
                    )
                
                with col3:
                    st.metric(
                        "Contas Únicas", 
                        formatar_brasileiro(metrics.get('contas_unicas', 0))
                    )
                
                with col4:
                    st.metric(
                        "Valor Total (Valor Pagto)", 
                        formatar_brasileiro(metrics.get('valor_total', 0), 'monetario'),
                        help="Somatória dos valores da coluna Valor Pagto"
                    )
                
                # Segunda linha de métricas
                col5, col6, col7, col8 = st.columns(4)
                
                with col5:
                    st.metric(
                        "Pagamentos Duplicados", 
                        formatar_brasileiro(metrics.get('pagamentos_duplicados', 0)),
                        delta=f"-{formatar_brasileiro(metrics.get('valor_total_duplicados', 0), 'monetario')}",
                        delta_color="inverse",
                        help="Contas com múltiplos pagamentos"
                    )
                
                with col6:
                    st.metric(
                        "Projetos Ativos", 
                        formatar_brasileiro(metrics.get('projetos_ativos', 0))
                    )
                
                with col7:
                    # Métrica UNIFICADA para CPFs problemáticos
                    problemas_cpf = metrics.get('problemas_cpf', {})
                    total_cpfs_problema = metrics.get('total_cpfs_ajuste', 0)
                    
                    st.metric(
                        "CPFs p/ Ajuste", 
                        formatar_brasileiro(total_cpfs_problema),
                        delta_color="inverse" if total_cpfs_problema > 0 else "off",
                        help=f"CPFs com problemas: {problemas_cpf.get('total_problemas_cpf', 0)} formatação + {problemas_cpf.get('total_cpfs_inconsistentes', 0)} inconsistências"
                    )
                
                with col8:
                    st.metric(
                        "Registros Críticos", 
                        formatar_brasileiro(metrics.get('total_registros_criticos', 0)),
                        delta_color="inverse" if metrics.get('total_registros_criticos', 0) > 0 else "off",
                        help="Registros INVÁLIDOS (sem conta ou valor)"
                    )
            
            if tem_dados_contas:
                st.markdown("---")
                st.subheader("📋 Dados de Inscrições/Contas")
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric(
                        "Total de Inscrições", 
                        formatar_brasileiro(metrics.get('total_contas_abertas', 0))
                    )
                
                with col2:
                    st.metric(
                        "Beneficiários Únicos", 
                        formatar_brasileiro(metrics.get('beneficiarios_contas', 0))
                    )
                
                with col3:
                    st.metric(
                        "Projetos Ativos", 
                        formatar_brasileiro(metrics.get('projetos_ativos', 0))
                    )
            
            st.markdown("---")
            
            # Abas para análises detalhadas
            tab1, tab2, tab3, tab4, tab5 = st.tabs([
                "📋 Visão Geral", 
                "⚠️ Duplicidades", 
                "🔴 CPFs Problemáticos",
                "⏳ Pagamentos Pendentes", 
                "🚨 Problemas Críticos"
            ])
            
            with tab1:
                st.subheader("Resumo dos Dados")
                
                if tem_dados_pagamentos:
                    st.write(f"**Planilha de Pagamentos:** {nomes_arquivos.get('pagamentos', 'N/A')}")
                    
                    # Mostrar apenas total SEM linha de totais
                    st.write(f"**Total de registros válidos:** {metrics.get('total_registros_sem_totais', 0)}")
                    
                    # Mostrar informação sobre remoção de totais se aplicável
                    if metrics.get('linha_totais_removida', False):
                        st.write(f"🔍 **Observação:** Linha de totais removida (originalmente {metrics.get('total_registros_originais', 0)} registros)")
                    
                    st.write(f"**Pagamentos válidos:** {metrics.get('total_pagamentos', 0)}")
                    st.write(f"**Registros sem conta:** {metrics.get('total_registros_invalidos', 0)}")
                
                if tem_dados_contas:
                    st.write(f"**Planilha de Inscrições:** {nomes_arquivos.get('contas', 'N/A')}")
                    st.write(f"**Total de inscrições:** {metrics.get('total_contas_abertas', 0)}")
                    st.write(f"**Beneficiários únicos:** {metrics.get('beneficiarios_contas', 0)}")
            
            with tab2:
                if tem_dados_pagamentos:
                    st.subheader("Pagamentos Duplicados")
                    
                    duplicidades_detalhadas = metrics.get('duplicidades_detalhadas', {})
                    total_contas_duplicadas = duplicidades_detalhadas.get('total_contas_duplicadas', 0)
                    
                    if total_contas_duplicadas > 0:
                        st.warning(f"🚨 Foram encontradas {total_contas_duplicadas} contas com pagamentos duplicados")
                        
                        # Mostrar resumo das duplicidades
                        resumo_duplicidades = duplicidades_detalhadas.get('resumo_duplicidades', pd.DataFrame())
                        if not resumo_duplicidades.empty:
                            st.write("**Resumo das Duplicidades:**")
                            st.dataframe(resumo_duplicidades)
                        
                        # Mostrar detalhes completos
                        detalhes_completos = duplicidades_detalhadas.get('detalhes_completos_duplicidades', pd.DataFrame())
                        if not detalhes_completos.empty:
                            st.write("**Detalhes Completos dos Pagamentos Duplicados:**")
                            st.dataframe(detalhes_completos)
                    else:
                        st.success("✅ Nenhum pagamento duplicado encontrado")
                else:
                    st.info("ℹ️ Esta análise está disponível apenas para dados de pagamentos")
            
            with tab3:
                if tem_dados_pagamentos:
                    st.subheader("CPFs Problemáticos - Correção Necessária")
                    
                    problemas_cpf = metrics.get('problemas_cpf', {})
                    total_problemas = metrics.get('total_cpfs_ajuste', 0)
                    
                    if total_problemas > 0:
                        # Alertas visuais diferenciados
                        col_critico, col_alerta = st.columns(2)
                        
                        with col_critico:
                            total_cpfs_inconsistentes = problemas_cpf.get('total_cpfs_inconsistentes', 0)
                            if total_cpfs_inconsistentes > 0:
                                st.error(f"❌ CRÍTICO: {total_cpfs_inconsistentes} CPFs com INCONSISTÊNCIAS")
                                st.write(f"**CPFs com nomes diferentes:** {len(problemas_cpf.get('cpfs_com_nomes_diferentes', []))}")
                                st.write(f"**CPFs com contas diferentes:** {len(problemas_cpf.get('cpfs_com_contas_diferentes', []))}")
                        
                        with col_alerta:
                            total_problemas_cpf = problemas_cpf.get('total_problemas_cpf', 0)
                            if total_problemas_cpf > 0:
                                st.warning(f"⚠️ ALERTA: {total_problemas_cpf} CPFs com problemas de FORMATAÇÃO")
                                st.write(f"**CPFs vazios:** {len(problemas_cpf.get('cpfs_vazios', []))}")
                                st.write(f"**CPFs com caracteres inválidos:** {len(problemas_cpf.get('cpfs_com_caracteres_invalidos', []))}")
                                st.write(f"**CPFs com tamanho incorreto:** {len(problemas_cpf.get('cpfs_com_tamanho_incorreto', []))}")
                        
                        # Abas para detalhes específicos
                        tab_inconsistentes, tab_formatacao = st.tabs([
                            "🔴 CPFs Inconsistentes", 
                            "📝 CPFs com Problemas de Formatação"
                        ])
                        
                        with tab_inconsistentes:
                            detalhes_inconsistencias = problemas_cpf.get('detalhes_inconsistencias', pd.DataFrame())
                            if not detalhes_inconsistencias.empty:
                                st.write("**CPFs com Inconsistências Críticas:**")
                                st.dataframe(detalhes_inconsistencias)
                            else:
                                st.info("Nenhum CPF com inconsistências críticas encontrado")
                        
                        with tab_formatacao:
                            detalhes_cpfs_problematicos = problemas_cpf.get('detalhes_cpfs_problematicos', pd.DataFrame())
                            if not detalhes_cpfs_problematicos.empty:
                                st.write("**CPFs com Problemas de Formatação:**")
                                st.dataframe(detalhes_cpfs_problematicos)
                            else:
                                st.info("Nenhum CPF com problemas de formatação encontrado")
                    else:
                        st.success("✅ Nenhum problema com CPFs encontrado")
                else:
                    st.info("ℹ️ Esta análise está disponível apenas para dados de pagamentos")
            
            with tab4:
                if tem_dados_pagamentos and tem_dados_contas:
                    st.subheader("Pagamentos Pendentes")
                    
                    pagamentos_pendentes = metrics.get('pagamentos_pendentes', {})
                    total_contas_sem_pagamento = pagamentos_pendentes.get('total_contas_sem_pagamento', 0)
                    
                    if total_contas_sem_pagamento > 0:
                        st.warning(f"⏳ {total_contas_sem_pagamento} contas aguardando pagamento")
                        
                        contas_sem_pagamento = pagamentos_pendentes.get('contas_sem_pagamento', pd.DataFrame())
                        if not contas_sem_pagamento.empty:
                            st.write("**Contas Aguardando Pagamento:**")
                            st.dataframe(contas_sem_pagamento)
                    else:
                        st.success("✅ Todas as contas abertas possuem pagamentos registrados")
                else:
                    st.info("ℹ️ Esta análise requer ambas as planilhas (pagamentos e inscrições)")
            
            with tab5:
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
    
    # IMPLEMENTAÇÃO DAS OUTRAS ABAS
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
