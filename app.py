import streamlit as st
import pandas as pd
import sqlite3
import hashlib
import io
import re
import os
from datetime import datetime
import time

# ==============================================================================
# 1. CONFIGURAÇÕES E SEGURANÇA
# ==============================================================================
st.set_page_config(
    page_title="SGM-POT | Sistema de Gerenciamento",
    page_icon="🏛️",
    layout="wide"
)

# Senha padrão: 'smdet2025'
SENHA_PADRAO_HASH = hashlib.sha256("smdet2025".encode()).hexdigest()

def hash_senha(senha):
    return hashlib.sha256(senha.encode()).hexdigest()

def validar_email_prefeitura(email):
    # Em produção, descomente a validação real:
    # return email.endswith("@prefeitura.sp.gov.br")
    return True

# ==============================================================================
# 2. BANCO DE DADOS
# ==============================================================================
def init_db():
    conn = sqlite3.connect('pot_datastore.db')
    c = conn.cursor()
    
    # Tabelas
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        email TEXT PRIMARY KEY, nome TEXT, senha_hash TEXT, perfil TEXT, trocar_senha BOOLEAN)''')
    
    # Admin padrão
    c.execute("SELECT * FROM usuarios WHERE email = 'admin.ti@prefeitura.sp.gov.br'")
    if not c.fetchone():
        c.execute("INSERT INTO usuarios VALUES (?, ?, ?, ?, ?)", 
                  ('admin.ti@prefeitura.sp.gov.br', 'Admin TI', SENHA_PADRAO_HASH, 'ADMIN_TI', 1))
        conn.commit()

    c.execute('''CREATE TABLE IF NOT EXISTS beneficiarios (
        cpf TEXT PRIMARY KEY, nome TEXT, rg TEXT, projeto_atual TEXT, data_atualizacao DATETIME)''')

    c.execute('''CREATE TABLE IF NOT EXISTS pagamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cpf_beneficiario TEXT, num_cartao TEXT, projeto TEXT, 
        mes_referencia TEXT, ano_referencia INTEGER,
        valor_liquido REAL, data_pagamento TEXT, status TEXT, 
        arquivo_origem TEXT, data_importacao DATETIME,
        FOREIGN KEY(cpf_beneficiario) REFERENCES beneficiarios(cpf))''')
    
    conn.commit()
    return conn

def limpar_banco_dados():
    """Função para resetar os dados em caso de erro de duplicação"""
    try:
        if os.path.exists('pot_datastore.db'):
            conn = sqlite3.connect('pot_datastore.db')
            c = conn.cursor()
            c.execute("DELETE FROM pagamentos")
            c.execute("DELETE FROM beneficiarios")
            # Não deletamos usuários para não perder o acesso
            conn.commit()
            conn.close()
            return True
    except Exception as e:
        return False

# ==============================================================================
# 3. LÓGICA DE NEGÓCIO (CORREÇÃO APLICADA)
# ==============================================================================

def normalizar_colunas(df):
    df.columns = df.columns.str.strip()
    mapa = {
        'Num Cartao': 'num_cartao', 'NumCartao': 'num_cartao', 'Num Cartão': 'num_cartao',
        'Nome': 'nome', 'NOME': 'nome',
        'RG': 'rg', 'CPF': 'cpf',
        'Valor Pagto': 'valor_liquido', 'ValorPagto': 'valor_liquido',
        'Projeto': 'projeto', 'Data Pagto': 'data_pagto'
    }
    df.rename(columns=mapa, inplace=True)
    return df

def limpar_moeda(valor):
    """Converte R$ 1.500,00 para float 1500.00"""
    if pd.isna(valor): return 0.0
    v = str(valor).replace('R$', '').replace('.', '').replace(',', '.').strip()
    try:
        return float(v)
    except:
        return 0.0

def inferir_metadados(filename):
    fn = filename.upper()
    projeto = "GERAL"
    if "ADS" in fn: projeto = "ADS"
    elif "ZELADORES" in fn: projeto = "ZELADORES"
    elif "ESPORTE" in fn: projeto = "ESPORTE"
    elif "GAE" in fn: projeto = "GAE"
    elif "ABASTECE" in fn: projeto = "ABASTECE"
    elif "DEFESA" in fn: projeto = "DEFESA CIVIL"
    
    mes = "ND"
    meses = ["JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO", 
             "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"]
    for m in meses:
        if m in fn: mes = m; break
    
    return projeto, mes

def processar_dataframe(df, nome_arquivo, ano_selecionado):
    conn = init_db()
    c = conn.cursor()
    projeto_inf, mes_inf = inferir_metadados(nome_arquivo)
    
    # === CORREÇÃO CRÍTICA: Remover linha de TOTAL ===
    # Removemos linhas onde Nome ou Num Cartão são vazios/NaN
    df_clean = df.dropna(subset=['nome', 'num_cartao']).copy()
    
    total_registros = 0
    valor_acumulado = 0.0
    
    for _, row in df_clean.iterrows():
        # Limpeza CPF
        cpf_raw = str(row.get('cpf', ''))
        if pd.isna(row.get('cpf')): cpf_raw = ''
        cpf_limpo = re.sub(r'\D', '', cpf_raw)
        
        # Se não tem CPF válido (ex: erro de leitura), tenta RG ou pula
        if len(cpf_limpo) < 5: 
            # Tenta usar RG apenas se CPF falhar
            rg_limpo = re.sub(r'\D', '', str(row.get('rg', '')))
            if len(rg_limpo) > 4:
                identificador = rg_limpo
            else:
                continue # Pula linha inválida/vazia
        else:
            identificador = cpf_limpo

        nome = str(row.get('nome', 'Beneficiário')).upper()
        
        # 1. Atualiza Beneficiário
        c.execute('''
            INSERT INTO beneficiarios (cpf, nome, rg, projeto_atual, data_atualizacao)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(cpf) DO UPDATE SET
                nome=excluded.nome,
                data_atualizacao=excluded.data_atualizacao
        ''', (identificador, nome, str(row.get('rg','')), projeto_inf, datetime.now()))
        
        # 2. Insere Pagamento
        valor_float = limpar_moeda(row.get('valor_liquido', 0))
        
        # Verifica duplicidade
        c.execute('''
            SELECT id FROM pagamentos 
            WHERE cpf_beneficiario=? AND mes_referencia=? AND ano_referencia=? AND projeto=?
        ''', (identificador, mes_inf, ano_selecionado, projeto_inf))
        
        if not c.fetchone() and valor_float > 0:
            c.execute('''
                INSERT INTO pagamentos (
                    cpf_beneficiario, num_cartao, projeto, mes_referencia, ano_referencia,
                    valor_liquido, data_pagamento, status, arquivo_origem, data_importacao
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (identificador, str(row.get('num_cartao', '')), projeto_inf,
                  mes_inf, ano_selecionado, valor_float, str(row.get('data_pagto', '')),
                  'Processando', nome_arquivo, datetime.now()))
            
            total_registros += 1
            valor_acumulado += valor_float

    conn.commit()
    conn.close()
    return total_registros, valor_acumulado

# ==============================================================================
# 4. INTERFACE
# ==============================================================================

def tela_login():
    st.markdown("<h2 style='text-align: center;'>🔐 Acesso SGM-POT</h2>", unsafe_allow_html=True)
    with st.form("login"):
        col1, col2 = st.columns([3, 1])
        email = st.text_input("E-mail")
        senha = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar", use_container_width=True):
            conn = init_db()
            user = conn.execute("SELECT * FROM usuarios WHERE email=?", (email,)).fetchone()
            conn.close()
            if user and user[2] == hash_senha(senha):
                st.session_state['logado'] = True
                st.session_state['usuario'] = {'email': user[0], 'nome': user[1], 'perfil': user[3]}
                st.session_state['trocar_senha'] = (user[4] == 1)
                st.rerun()
            else:
                st.error("Credenciais inválidas.")

def tela_upload():
    st.header("📂 Ingestão de Arquivos")
    ano = st.number_input("Ano de Referência", 2020, 2030, 2025)
    files = st.file_uploader("Arquivos CSV", accept_multiple_files=True)
    
    if files:
        st.info("Pré-visualização da Importação:")
        for f in files:
            # Leitura prévia para validação
            f.seek(0)
            try:
                df_prev = pd.read_csv(f, sep=';' if b';' in f.readline() else ',')
                f.seek(0) # Reset ponteiro
                df_prev = normalizar_colunas(df_prev)
                
                # Simula a limpeza
                df_clean = df_prev.dropna(subset=['nome', 'num_cartao'])
                
                # Calcula total real
                df_clean['vlr_float'] = df_clean['valor_liquido'].apply(limpar_moeda)
                total_arquivo = df_clean['vlr_float'].sum()
                qtd_linhas = len(df_clean)
                
                col1, col2, col3 = st.columns(3)
                col1.text(f"Arquivo: {f.name}")
                col2.metric("Registros Válidos", qtd_linhas)
                col3.metric("Valor Total Real", f"R$ {total_arquivo:,.2f}")
                
            except Exception as e:
                st.error(f"Erro ao ler {f.name}: {e}")

        if st.button("Confirmar e Processar"):
            bar = st.progress(0)
            for i, f in enumerate(files):
                f.seek(0)
                try:
                    df = pd.read_csv(f, sep=';' if b';' in f.readline() else ',')
                    f.seek(0)
                    df = normalizar_colunas(df)
                    qtd, val = processar_dataframe(df, f.name, ano)
                    st.success(f"✅ {f.name}: {qtd} registros importados (R$ {val:,.2f})")
                except Exception as e:
                    st.error(f"❌ {f.name}: {e}")
                bar.progress((i+1)/len(files))

def tela_dashboard():
    st.header("📊 Dashboard Executivo")
    conn = init_db()
    
    colA, colB = st.columns(2)
    ano = colA.selectbox("Ano", [2025, 2024, 2023])
    mes = colB.selectbox("Mês", ["TODOS", "JANEIRO", "SETEMBRO", "OUTUBRO", "NOVEMBRO"])
    
    query = f"SELECT * FROM pagamentos WHERE ano_referencia = {ano}"
    if mes != "TODOS": query += f" AND mes_referencia = '{mes}'"
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if df.empty:
        st.warning("Sem dados para o período.")
        return

    total = df['valor_liquido'].sum()
    benef = df['cpf_beneficiario'].nunique()
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Pago", f"R$ {total:,.2f}")
    m2.metric("Beneficiários", benef)
    m3.metric("Ticket Médio", f"R$ {total/benef:,.2f}" if benef else 0)
    
    st.divider()
    c1, c2 = st.columns(2)
    c1.subheader("Por Projeto")
    c1.bar_chart(df.groupby("projeto")['valor_liquido'].sum())
    
    c2.subheader("Dados Detalhados")
    c2.dataframe(df[['nome_beneficiario', 'projeto', 'valor_liquido', 'status']].head(100))

def tela_admin():
    st.header("⚙️ Administração")
    
    st.subheader("⚠️ Zona de Perigo")
    if st.button("LIMPAR TODO BANCO DE DADOS (RESET)", type="primary"):
        if limpar_banco_dados():
            st.success("Banco de dados limpo com sucesso! Todos os registros duplicados foram removidos.")
            time.sleep(2)
            st.rerun()
        else:
            st.error("Erro ao limpar banco.")
            
    st.subheader("Usuários")
    conn = init_db()
    st.dataframe(pd.read_sql("SELECT email, nome, perfil FROM usuarios", conn))
    conn.close()

# ==============================================================================
# 5. EXECUÇÃO
# ==============================================================================
if 'logado' not in st.session_state: st.session_state['logado'] = False

if not st.session_state['logado']:
    tela_login()
else:
    if st.session_state.get('trocar_senha'):
        st.warning("Troque sua senha.")
        with st.form("pw"):
            ns = st.text_input("Nova Senha", type="password")
            if st.form_submit_button("Salvar"):
                conn = init_db()
                conn.execute("UPDATE usuarios SET senha_hash=?, trocar_senha=0 WHERE email=?", 
                             (hash_senha(ns), st.session_state['usuario']['email']))
                conn.commit(); conn.close()
                st.session_state['trocar_senha'] = False
                st.rerun()
    else:
        with st.sidebar:
            st.title("Menu")
            opt = st.radio("Ir para", ["Dashboard", "Importação", "Administração", "Sair"])
            if opt == "Sair": 
                st.session_state['logado'] = False
                st.rerun()
        
        if opt == "Dashboard": tela_dashboard()
        elif opt == "Importação": tela_upload()
        elif opt == "Administração": tela_admin()
