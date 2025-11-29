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
    
    # Verificar e adicionar colunas faltantes
    try:
        conn.execute("SELECT cpfs_ajuste FROM metricas_mensais LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE metricas_mensais ADD COLUMN cpfs_ajuste INTEGER")
    
    conn.commit()
    return conn

# FUNÇÃO PARA LIMPAR BANCO DE DADOS
def limpar_banco_dados(conn):
    """Remove todos os dados do banco para recomeçar do zero"""
    try:
        # Confirmar com o usuário antes de limpar
        st.sidebar.markdown("---")
        st.sidebar.header("🗑️ Limpar Banco de Dados")
        
        with st.sidebar.expander("⚠️ ÁREA DE LIMPEZA (CLIQUE PARA EXPANDIR)"):
            st.warning("**ATENÇÃO:** Esta operação é IRREVERSÍVEL!")
            st.info("""
            **Use esta função para:**
            - Remover dados duplicados
            - Recomeçar análises do zero
            - Corrigir problemas de importação
            """)
            
            senha_confirmacao = st.text_input("Digite 'LIMPAR' para confirmar:", type="password")
            botao_limpar = st.button("🚨 LIMPAR TODOS OS DADOS", type="secondary")
            
            if botao_limpar:
                if senha_confirmacao == "LIMPAR":
                    # Executar limpeza
                    conn.execute("DELETE FROM pagamentos")
                    conn.execute("DELETE FROM inscricoes")
                    conn.execute("DELETE FROM metricas_mensais")
                    conn.commit()
                    
                    st.sidebar.success("✅ Banco de dados limpo com sucesso!")
                    st.sidebar.info("🔄 Recarregue a página para começar novamente")
                    return True
                else:
                    st.sidebar.error("❌ Confirmação incorreta. Operação cancelada.")
                    return False
    except Exception as e:
        st.sidebar.error(f"❌ Erro ao limpar banco: {str(e)}")
        return False

# FUNÇÃO PARA VISUALIZAR E EXCLUIR REGISTROS ESPECÍFICOS
def gerenciar_registros(conn):
    """Permite visualizar e excluir registros específicos"""
    try:
        st.sidebar.markdown("---")
        st.sidebar.header("🔍 Gerenciar Registros")
        
        with st.sidebar.expander("Visualizar/Excluir Registros Específicos"):
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
                    resumo = dados[['mes_referencia', 'ano_referencia', 'nome_arquivo', 'data_importacao']].copy()
                    st.dataframe(resumo.head(10))
                    
                    # Opção de excluir por mês/ano
                    st.subheader("Excluir por Período")
                    meses_unicos = dados['mes_referencia'].unique()
                    anos_unicos = dados['ano_referencia'].unique()
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        mes_excluir = st.selectbox("Mês:", meses_unicos)
                    with col2:
                        ano_excluir = st.selectbox("Ano:", anos_unicos)
                    
                    if st.button("🗑️ Excluir Período Selecionado", type="secondary"):
                        if tipo_dados == "Pagamentos":
                            conn.execute("DELETE FROM pagamentos WHERE mes_referencia = ? AND ano_referencia = ?", 
                                       (mes_excluir, ano_excluir))
                        else:
                            conn.execute("DELETE FROM inscricoes WHERE mes_referencia = ? AND ano_referencia = ?", 
                                       (mes_excluir, ano_excluir))
                        
                        # Excluir métricas correspondentes
                        conn.execute("DELETE FROM metricas_mensais WHERE mes_referencia = ? AND ano_referencia = ?", 
                                   (mes_excluir, ano_excluir))
                        
                        conn.commit()
                        st.success(f"✅ Período {mes_excluir}/{ano_excluir} excluído!")
                        st.rerun()
                
                elif tipo_dados == "Métricas":
                    st.dataframe(dados.head(10))
            
            else:
                st.info("Nenhum registro encontrado.")
                
    except Exception as e:
        st.sidebar.error(f"Erro no gerenciamento: {str(e)}")

# ... (mantenha todas as outras funções existentes como hash_senha, autenticar, etc.)

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
    
    # NOVO: Adicionar funções de gerenciamento do banco de dados
    limpar_banco_dados(conn)
    gerenciar_registros(conn)
    
    st.sidebar.markdown("---")
    
    # Resto do código continua igual...
    # Carregar dados
    dados, nomes_arquivos, mes_ref, ano_ref = carregar_dados(conn)
    
    # Verificar se há dados para processar
    tem_dados_pagamentos = 'pagamentos' in dados and not dados['pagamentos'].empty
    tem_dados_contas = 'contas' in dados and not dados['contas'].empty
    
    # Abas principais do sistema
    tab_principal, tab_dashboard, tab_relatorios, tab_historico, tab_estatisticas = st.tabs([
        "📊 Análise Mensal", 
        "📈 Dashboard Evolutivo", 
        "📋 Relatórios Comparativos", 
        "🗃️ Dados Históricos",
        "📊 Estatísticas Detalhadas"
    ])
    
    # ... (mantenha o resto do código da função main igual)

if __name__ == "__main__":
    main()
