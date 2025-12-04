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
    page_title="SMDET-POT | Sistema de Gestão",
    page_icon="🏛️",
    layout="wide"
)

# Senha padrão: 'smdet2025'
SENHA_PADRAO_HASH = hashlib.sha256("smdet2025".encode()).hexdigest()

# TRAVA DE SEGURANÇA FINANCEIRA
# Qualquer linha no CSV com valor acima disso será considerada "Linha de Total" ou erro e será ignorada.
TETO_MAXIMO_BENEFICIO = 5000.00 

def hash_senha(senha):
    return hashlib.sha256(senha.encode()).hexdigest()

def validar_email_prefeitura(email):
    # Em produção, ative a validação de domínio
    # return email.endswith("@prefeitura.sp.gov.br")
    return True

# ==============================================================================
# 2. BANCO DE DADOS
# ==============================================================================
def init_db():
    conn = sqlite3.connect('pot_datastore.db')
    c = conn.cursor()
    
    # Tabela de Usuários
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        email TEXT PRIMARY KEY, nome TEXT, senha_hash TEXT, perfil TEXT, trocar_senha BOOLEAN)''')
    
    # Cria usuário Admin TI padrão se não existir
    c.execute("SELECT * FROM usuarios WHERE email = 'admin.ti@prefeitura.sp.gov.br'")
    if not c.fetchone():
        c.execute("INSERT INTO usuarios VALUES (?, ?, ?, ?, ?)", 
                  ('admin.ti@prefeitura.sp.gov.br', 'Admin TI', SENHA_PADRAO_HASH, 'ADMIN_TI', 1))
        conn.commit()

    # Tabela de Beneficiários
    c.execute('''CREATE TABLE IF NOT EXISTS beneficiarios (
        cpf TEXT PRIMARY KEY, nome TEXT, rg TEXT, projeto_atual TEXT, data_atualizacao DATETIME)''')

    # Tabela de Pagamentos (Adicionada coluna gerenciadora)
    # Verifica se a coluna gerenciadora existe, se não, adiciona (migração)
    try:
        c.execute("SELECT gerenciadora FROM pagamentos LIMIT 1")
    except sqlite3.OperationalError:
        try:
            c.execute("ALTER TABLE pagamentos ADD COLUMN gerenciadora TEXT")
        except:
            pass # Tabela pode não existir ainda, será criada abaixo

    c.execute('''CREATE TABLE IF NOT EXISTS pagamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cpf_beneficiario TEXT, num_cartao TEXT, projeto TEXT, gerenciadora TEXT,
        mes_referencia TEXT, ano_referencia INTEGER,
        valor_liquido REAL, data_pagamento TEXT, status TEXT, 
        arquivo_origem TEXT, data_importacao DATETIME,
        FOREIGN KEY(cpf_beneficiario) REFERENCES beneficiarios(cpf))''')
    
    conn.commit()
    return conn

def limpar_banco_dados():
    """Reseta as tabelas de dados, mantendo usuários"""
    try:
        conn = init_db() # Garante conexão
        c = conn.cursor()
        c.execute("DELETE FROM pagamentos")
        c.execute("DELETE FROM beneficiarios")
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Erro ao limpar banco: {e}")
        return False

# ==============================================================================
# 3. LÓGICA DE NEGÓCIO E LIMPEZA DE DADOS
# ==============================================================================

def normalizar_colunas(df):
    """Padroniza nomes de colunas"""
    df.columns = df.columns.str.strip()
    mapa = {
        'Num Cartao': 'num_cartao', 'NumCartao': 'num_cartao', 'Num Cartão': 'num_cartao', 'NumCartão': 'num_cartao',
        'Nome': 'nome', 'NOME': 'nome', 'Nome do beneficiário': 'nome',
        'RG': 'rg', 'CPF': 'cpf',
        'Valor Pagto': 'valor_liquido', 'ValorPagto': 'valor_liquido', 'Valor Pagto ': 'valor_liquido',
        'Valor Total': 'valor_bruto', # Mapeamos mas não usaremos para soma
        'Projeto': 'projeto', 'Data Pagto': 'data_pagto', 'DataPagto': 'data_pagto',
        'Gerenciadora': 'gerenciadora', 'GERENCIADORA': 'gerenciadora'
    }
    df.rename(columns=mapa, inplace=True)
    return df

def limpar_moeda(valor):
    """Converte string financeira (R$ 1.000,00) para float (1000.00)"""
    if pd.isna(valor): return 0.0
    if isinstance(valor, (int, float)): return float(valor)
    
    v = str(valor).replace('R$', '').replace('.', '').replace(',', '.').strip()
    try:
        return float(v)
    except:
        return 0.0

def inferir_metadados(filename):
    fn = filename.upper()
    projeto = "GERAL"
    
    # Inferência de Projeto
    if "ADS" in fn: projeto = "ADS"
    elif "ZELADORES" in fn: projeto = "ZELADORES"
    elif "ESPORTE" in fn: projeto = "ESPORTE"
    elif "GAE" in fn: projeto = "GAE"
    elif "ABAE" in fn: projeto = "BUSCA ATIVA" # Correção solicitada
    elif "ABASTECE" in fn: projeto = "ABASTECE"
    elif "DEFESA" in fn: projeto = "DEFESA CIVIL"
    elif "TELECENTRO" in fn: projeto = "TELECENTRO"
    
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
    
    # 1. Normalizar colunas
    df = normalizar_colunas(df)
    
    # 2. Validação Básica de Estrutura
    if 'num_cartao' not in df.columns or 'nome' not in df.columns:
        conn.close()
        return 0, 0.0, "Erro: Colunas 'Num Cartao' ou 'Nome' não encontradas."

    # 3. Remover registros anteriores DESTE MESMO ARQUIVO para evitar duplicação em re-upload
    c.execute("DELETE FROM pagamentos WHERE arquivo_origem = ?", (nome_arquivo,))

    # 4. FILTRO RIGOROSO (Anti-Total e Anti-Vazio)
    
    # a) Converter Num Cartao para numérico (força erros/textos a virarem NaN)
    df['num_cartao_limpo'] = pd.to_numeric(df['num_cartao'], errors='coerce')
    
    # b) Descartar linhas onde Num Cartao é NaN ou 0
    df_clean = df.dropna(subset=['num_cartao_limpo']).copy()
    df_clean = df_clean[df_clean['num_cartao_limpo'] > 0]
    
    # c) Descartar linhas onde Nome é vazio
    df_clean = df_clean.dropna(subset=['nome'])
    
    # d) Preparar Valor Líquido e Aplicar Teto
    # Garante que pegamos a coluna 'valor_liquido' (Valor Pagto) e não 'valor_bruto' (Valor Total)
    if 'valor_liquido' not in df_clean.columns:
         conn.close()
         return 0, 0.0, "Erro: Coluna 'Valor Pagto' não encontrada."
         
    df_clean['vlr_tratado'] = df_clean['valor_liquido'].apply(limpar_moeda)
    
    # === FILTRO CRÍTICO ===
    # Filtra valores inválidos (<= 0) ou linhas de Total (> 5000)
    df_clean = df_clean[
        (df_clean['vlr_tratado'] > 0) & 
        (df_clean['vlr_tratado'] < TETO_MAXIMO_BENEFICIO)
    ]
    
    total_registros = 0
    valor_acumulado = 0.0
    
    for _, row in df_clean.iterrows():
        # Definição do Projeto (Prioriza a coluna da planilha, depois o nome do arquivo)
        proj_linha = str(row.get('projeto', '')).strip().upper()
        if proj_linha and proj_linha not in ['NAN', 'NONE', '']:
            projeto_final = proj_linha
        else:
            projeto_final = projeto_inf

        # Definição da Gerenciadora
        gerenciadora = str(row.get('gerenciadora', 'N/D')).strip().upper()
        if gerenciadora in ['NAN', 'NONE', '']:
            gerenciadora = 'N/D'

        # Identificação (CPF ou RG)
        cpf_raw = str(row.get('cpf', ''))
        cpf_limpo = re.sub(r'\D', '', cpf_raw)
        
        identificador = None
        if len(cpf_limpo) > 5:
            identificador = cpf_limpo
        else:
            # Tenta RG se CPF falhar
            rg_raw = str(row.get('rg', ''))
            rg_limpo = re.sub(r'\D', '', rg_raw)
            if len(rg_limpo) > 4:
                identificador = rg_limpo
        
        if not identificador: 
            continue 

        nome = str(row.get('nome', 'Beneficiário')).upper()
        if "TOTAL" in nome: continue # Segurança extra
        
        # A. Atualiza/Cria Beneficiário
        c.execute('''
            INSERT INTO beneficiarios (cpf, nome, rg, projeto_atual, data_atualizacao)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(cpf) DO UPDATE SET
                nome=excluded.nome,
                projeto_atual=excluded.projeto_atual,
                data_atualizacao=excluded.data_atualizacao
        ''', (identificador, nome, str(row.get('rg','')), projeto_final, datetime.now()))
        
        # B. Processa Pagamento
        valor_float = row['vlr_tratado']
        
        # Verifica duplicidade REAL (Pessoa + Mês + Ano + Projeto já pagos?)
        # Isso previne duplicidade mesmo se o arquivo tiver nome diferente
        c.execute('''
            SELECT id FROM pagamentos 
            WHERE cpf_beneficiario=? AND mes_referencia=? AND ano_referencia=? AND projeto=?
        ''', (identificador, mes_inf, ano_selecionado, projeto_final))
        
        if not c.fetchone():
            c.execute('''
                INSERT INTO pagamentos (
                    cpf_beneficiario, num_cartao, projeto, gerenciadora,
                    mes_referencia, ano_referencia,
                    valor_liquido, data_pagamento, status, arquivo_origem, data_importacao
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (identificador, str(int(row['num_cartao_limpo'])), projeto_final, gerenciadora,
                  mes_inf, ano_selecionado, valor_float, str(row.get('data_pagto', '')),
                  'Processando', nome_arquivo, datetime.now()))
            
            total_registros += 1
            valor_acumulado += valor_float

    conn.commit()
    conn.close()
    return total_registros, valor_acumulado, "Sucesso"

# ==============================================================================
# 4. INTERFACE GRÁFICA
# ==============================================================================

def tela_login():
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h2 style='text-align: center;'>🔐 Acesso SMDET-POT</h2>", unsafe_allow_html=True)
        with st.form("login"):
            email = st.text_input("E-mail Institucional")
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
                    st.error("Acesso negado. Verifique suas credenciais.")

def tela_upload():
    st.header("📂 Importação de Arquivos")
    st.markdown("---")
    
    colA, colB = st.columns([1, 3])
    with colA:
        ano = st.number_input("Ano de Referência", 2020, 2030, 2025)
    
    files = st.file_uploader("Arraste arquivos CSV aqui (Cadastros, Pagamentos ou Pendências)", accept_multiple_files=True)
    
    if files:
        if st.button("Processar Arquivos", type="primary"):
            bar = st.progress(0)
            log_container = st.container()
            
            for i, f in enumerate(files):
                try:
                    # Detecta separador e lê
                    content = f.getvalue().decode("utf-8", errors='replace')
                    sep = ';' if ';' in content.split('\n')[0] else ','
                    
                    df = pd.read_csv(io.StringIO(content), sep=sep)
                    qtd, val, status = processar_dataframe(df, f.name, ano)
                    
                    if "Erro" in status:
                        log_container.error(f"❌ {f.name}: {status}")
                    else:
                        log_container.success(f"✅ {f.name}: {qtd} pagamentos inseridos (Total: R$ {val:,.2f})")
                        
                except Exception as e:
                    log_container.error(f"❌ Erro crítico em {f.name}: {e}")
                
                bar.progress((i+1)/len(files))

def tela_dashboard():
    st.header("📊 Sistema de Gestão e Monitoramento de Pagamentos POT")
    st.markdown("---")
    
    conn = init_db()
    
    # Filtros
    c1, c2 = st.columns(2)
    ano = c1.selectbox("Ano", [2025, 2024, 2023])
    mes = c2.selectbox("Mês", ["TODOS", "JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO", 
                               "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"])
    
    # Query Base
    sql = """
        SELECT p.projeto, p.gerenciadora, p.valor_liquido, p.status, p.mes_referencia, p.cpf_beneficiario, b.nome as nome_beneficiario
        FROM pagamentos p
        LEFT JOIN beneficiarios b ON p.cpf_beneficiario = b.cpf
        WHERE p.ano_referencia = ?
    """
    params = [ano]
    
    if mes != "TODOS":
        sql += " AND p.mes_referencia = ?"
        params.append(mes)
        
    df = pd.read_sql_query(sql, conn, params=params)
    conn.close()
    
    if df.empty:
        st.info("ℹ️ Nenhum dado encontrado para os filtros selecionados.")
        return

    # KPIs
    total_pago = df['valor_liquido'].sum()
    total_benef = df['cpf_beneficiario'].nunique()
    
    k1, k2, k3 = st.columns(3)
    k1.metric("Total Pago", f"R$ {total_pago:,.2f}")
    k2.metric("Beneficiários Únicos", total_benef)
    k3.metric("Ticket Médio", f"R$ {total_pago/total_benef:,.2f}" if total_benef else "R$ 0,00")
    
    st.divider()
    
    # Gráficos e Tabelas
    g1, g2 = st.columns([2, 1])
    
    with g1:
        st.subheader("Evolução por Projeto")
        st.bar_chart(df.groupby("projeto")['valor_liquido'].sum())
        
    with g2:
        st.subheader("Status")
        st.write(df['status'].value_counts())

    st.subheader("Detalhamento dos Pagamentos")
    st.dataframe(df[['nome_beneficiario', 'projeto', 'gerenciadora', 'valor_liquido', 'status', 'mes_referencia']].head(1000))

def tela_admin():
    st.header("⚙️ Administração do Sistema")
    st.markdown("---")
    
    usuario_atual = st.session_state['usuario']
    
    # Abas condicionais
    if usuario_atual['perfil'] == 'ADMIN_TI':
        tab1, tab2 = st.tabs(["Gestão de Usuários", "Manutenção de Banco"])
    else:
        tab1, = st.tabs(["Gestão de Usuários"])
    
    with tab1:
        with st.form("novo_user"):
            st.subheader("Cadastrar Novo Usuário")
            nome = st.text_input("Nome")
            email = st.text_input("E-mail (@prefeitura)")
            perfil = st.selectbox("Perfil", ["USUARIO", "ADMIN_AREA"])
            if st.form_submit_button("Cadastrar"):
                if validar_email_prefeitura(email):
                    conn = init_db()
                    try:
                        conn.execute("INSERT INTO usuarios VALUES (?, ?, ?, ?, ?)", 
                                     (email, nome, SENHA_PADRAO_HASH, perfil, 1))
                        conn.commit()
                        st.success("Usuário cadastrado! Senha provisória: smdet2025")
                    except Exception as e:
                        st.error(f"Erro: {e}")
                    conn.close()
                else:
                    st.error("E-mail inválido.")
        
        conn = init_db()
        st.dataframe(pd.read_sql("SELECT nome, email, perfil FROM usuarios", conn))
        conn.close()

    if usuario_atual['perfil'] == 'ADMIN_TI':
        with tab2:
            st.error("⚠️ **Zona de Perigo (TI)**")
            st.warning("Esta ação apagará TODOS os dados. Use com cautela.")
            if st.button("LIMPAR TODO O BANCO DE DADOS", type="primary"):
                if limpar_banco_dados():
                    st.success("Banco limpo com sucesso!")
                    time.sleep(2)
                    st.rerun()

# ==============================================================================
# 5. CONTROLE DE NAVEGAÇÃO
# ==============================================================================
if 'logado' not in st.session_state: st.session_state['logado'] = False

if not st.session_state['logado']:
    tela_login()
else:
    # Troca de Senha Obrigatória
    if st.session_state.get('trocar_senha'):
        st.warning("🔒 Por segurança, redefina sua senha.")
        with st.form("nova_senha"):
            s1 = st.text_input("Nova Senha", type="password")
            s2 = st.text_input("Confirme a Senha", type="password")
            if st.form_submit_button("Salvar Nova Senha"):
                if s1 == s2 and len(s1) > 5:
                    conn = init_db()
                    conn.execute("UPDATE usuarios SET senha_hash=?, trocar_senha=0 WHERE email=?", 
                                 (hash_senha(s1), st.session_state['usuario']['email']))
                    conn.commit(); conn.close()
                    st.session_state['trocar_senha'] = False
                    st.success("Senha alterada!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Senhas não conferem ou muito curtas.")
    else:
        # Menu Lateral
        with st.sidebar:
            st.title("SMDET-POT")
            st.write(f"👤 {st.session_state['usuario']['nome']}")
            st.caption(f"Perfil: {st.session_state['usuario']['perfil']}")
            st.markdown("---")
            menu = st.radio("Navegação", ["Dashboard", "Importação", "Administração", "Sair"])
            
            if menu == "Sair":
                st.session_state['logado'] = False
                st.rerun()
        
        # Roteador
        if menu == "Dashboard": tela_dashboard()
        elif menu == "Importação": tela_upload()
        elif menu == "Administração": tela_admin()
