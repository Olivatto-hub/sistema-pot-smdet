import streamlit as st
import pandas as pd
import sqlite3
import hashlib
import io
import re
from datetime import datetime
import time

# ==============================================================================
# 1. CONFIGURAÇÕES INICIAIS E SEGURANÇA
# ==============================================================================
st.set_page_config(
    page_title="SGM-POT | Sistema de Gerenciamento",
    page_icon="🏛️",
    layout="wide"
)

# Senha padrão inicial (Hash SHA256 de 'smdet2025')
SENHA_PADRAO_HASH = hashlib.sha256("smdet2025".encode()).hexdigest()

def hash_senha(senha):
    """Gera o hash SHA256 da senha."""
    return hashlib.sha256(senha.encode()).hexdigest()

def validar_email_prefeitura(email):
    """Verifica se o e-mail pertence ao domínio da prefeitura."""
    # Para testes, você pode comentar a linha abaixo se não tiver e-mail prefeitura
    # return email.endswith("@prefeitura.sp.gov.br") 
    return True # Deixei True para você testar, mas em produção mude para a linha acima.

# ==============================================================================
# 2. BANCO DE DADOS (SQLite)
# ==============================================================================
def init_db():
    conn = sqlite3.connect('pot_datastore.db')
    c = conn.cursor()
    
    # Tabela de Usuários
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            email TEXT PRIMARY KEY,
            nome TEXT,
            senha_hash TEXT,
            perfil TEXT, -- 'ADMIN_TI', 'ADMIN_AREA', 'USUARIO'
            trocar_senha BOOLEAN
        )
    ''')
    
    # Cria o Admin TI padrão se não existir
    c.execute("SELECT * FROM usuarios WHERE email = 'admin.ti@prefeitura.sp.gov.br'")
    if not c.fetchone():
        c.execute("INSERT INTO usuarios VALUES (?, ?, ?, ?, ?)", 
                  ('admin.ti@prefeitura.sp.gov.br', 'Administrador TI', SENHA_PADRAO_HASH, 'ADMIN_TI', 1))
        conn.commit()

    # Tabela Mestra de Beneficiários (Histórico Cadastral)
    c.execute('''
        CREATE TABLE IF NOT EXISTS beneficiarios (
            cpf TEXT PRIMARY KEY,
            nome TEXT,
            rg TEXT,
            nome_mae TEXT,
            data_nascimento TEXT,
            projeto_atual TEXT,
            data_atualizacao DATETIME
        )
    ''')

    # Tabela Fato de Pagamentos (Histórico Financeiro)
    c.execute('''
        CREATE TABLE IF NOT EXISTS pagamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cpf_beneficiario TEXT,
            num_cartao TEXT,
            projeto TEXT,
            mes_referencia TEXT,
            ano_referencia INTEGER,
            valor_bruto REAL,
            valor_liquido REAL,
            dias_trabalhados INTEGER,
            data_pagamento TEXT,
            status TEXT, -- 'Processando', 'Pago', 'Pendente', 'Cancelado'
            arquivo_origem TEXT,
            data_importacao DATETIME,
            FOREIGN KEY(cpf_beneficiario) REFERENCES beneficiarios(cpf)
        )
    ''')
    
    conn.commit()
    return conn

# ==============================================================================
# 3. LÓGICA DE NEGÓCIO E NORMALIZAÇÃO
# ==============================================================================

def normalizar_colunas(df):
    """Padroniza os nomes das colunas vindas dos arquivos CSV variados."""
    # Remove espaços em branco antes e depois dos nomes das colunas
    df.columns = df.columns.str.strip()
    
    mapa = {
        # Identificação
        'Num Cartao': 'num_cartao', 'NumCartao': 'num_cartao', 'Num Cartão': 'num_cartao',
        'Nome': 'nome', 'NOME': 'nome',
        'RG': 'rg', 'CPF': 'cpf',
        'NomeMãe': 'nome_mae', 'Nome Mãe': 'nome_mae',
        'DataNasc': 'data_nasc', 'Data Nasc': 'data_nasc',
        
        # Financeiro
        'Valor Total': 'valor_bruto', 'ValorTotal': 'valor_bruto',
        'Valor Pagto': 'valor_liquido', 'ValorPagto': 'valor_liquido', 'Valor Pagto ': 'valor_liquido',
        'Valor Desconto': 'valor_desconto', 'ValorDesconto': 'valor_desconto',
        
        # Operacional
        'Projeto': 'projeto',
        'Distrito': 'distrito',
        'Dias': 'dias', 'Dia': 'dias', 'DIAS': 'dias',
        'Data Pagto': 'data_pagto', 'DataPagto': 'data_pagto',
        'Mês': 'mes_ref', 'mês': 'mes_ref', 'MêS': 'mes_ref'
    }
    
    # Renomeia usando o mapa
    df.rename(columns=mapa, inplace=True)
    return df

def inferir_metadados(filename):
    """Extrai Projeto e Mês do nome do arquivo."""
    fn = filename.upper()
    
    # Projetos
    projeto = "GERAL"
    if "ADS" in fn: projeto = "ADS"
    elif "ZELADORES" in fn: projeto = "ZELADORES"
    elif "ESPORTE" in fn: projeto = "ESPORTE"
    elif "DEFESA CIVIL" in fn: projeto = "DEFESA CIVIL"
    elif "GAE" in fn: projeto = "GAE"
    elif "ABASTECE" in fn: projeto = "ABASTECE"
    elif "TELECENTRO" in fn: projeto = "TELECENTRO"
    
    # Meses
    mes = "ND"
    meses = ["JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO", 
             "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"]
    for m in meses:
        if m in fn:
            mes = m
            break
            
    # Tipo de Arquivo
    tipo = "PAGAMENTO" # Default
    if "ABERTURA" in fn or "CADASTRO" in fn or "GESTÃO DE DOC" in fn:
        tipo = "CADASTRO"
    elif "PENDÊNCIA" in fn or "PENDENCIA" in fn or "CORREÇÃO" in fn:
        tipo = "PENDENCIA"
    elif ".TXT" in fn and "REL.CADASTRO" in fn:
        tipo = "RETORNO_BANCO"
        
    return projeto, mes, tipo

def processar_upload(file, ano_selecionado):
    conn = init_db()
    c = conn.cursor()
    log = []
    
    try:
        nome_arquivo = file.name
        projeto_inf, mes_inf, tipo_arq = inferir_metadados(nome_arquivo)
        
        # Leitura do arquivo (tenta CSV com ; ou ,)
        content = file.getvalue().decode("utf-8", errors='replace')
        if ';' in content.split('\n')[0]:
            df = pd.read_csv(io.StringIO(content), sep=';')
        else:
            df = pd.read_csv(io.StringIO(content), sep=',')
            
        df = normalizar_colunas(df)
        
        # Loop pelos registros
        for _, row in df.iterrows():
            # Limpeza de CPF e Chaves
            cpf_raw = str(row.get('cpf', ''))
            rg_raw = str(row.get('rg', ''))
            # Remove caracteres não numéricos
            cpf_limpo = re.sub(r'\D', '', cpf_raw)
            
            # Se não tem CPF, tenta usar o RG como identificador provisório (Cuidado aqui)
            identificador = cpf_limpo if len(cpf_limpo) > 5 else rg_raw
            
            if len(identificador) < 3:
                continue # Pula registros vazios
            
            nome = str(row.get('nome', 'Beneficiário Não Identificado')).upper()
            
            # --- FLUXO 1: CADASTRO / ATUALIZAÇÃO MESTRA ---
            c.execute('''
                INSERT INTO beneficiarios (cpf, nome, rg, projeto_atual, data_atualizacao)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cpf) DO UPDATE SET
                    nome=excluded.nome,
                    projeto_atual=excluded.projeto_atual,
                    data_atualizacao=excluded.data_atualizacao
            ''', (identificador, nome, rg_raw, projeto_inf, datetime.now()))
            
            # --- FLUXO 2: PAGAMENTOS E FOLHA ---
            if tipo_arq == "PAGAMENTO":
                valor = str(row.get('valor_liquido', '0')).replace('R$','').replace('.','').replace(',','.')
                try: valor_float = float(valor)
                except: valor_float = 0.0
                
                # Verifica duplicidade (CPF + Mes + Ano + Projeto)
                c.execute('''
                    SELECT id FROM pagamentos 
                    WHERE cpf_beneficiario=? AND mes_referencia=? AND ano_referencia=? AND projeto=?
                ''', (identificador, mes_inf, ano_selecionado, projeto_inf))
                
                existe = c.fetchone()
                
                if not existe:
                    c.execute('''
                        INSERT INTO pagamentos (
                            cpf_beneficiario, num_cartao, projeto, mes_referencia, ano_referencia,
                            valor_liquido, data_pagamento, status, arquivo_origem, data_importacao
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        identificador, str(row.get('num_cartao', '')), projeto_inf,
                        mes_inf, ano_selecionado, valor_float, str(row.get('data_pagto', '')),
                        'Processando', nome_arquivo, datetime.now()
                    ))
                
            # --- FLUXO 3: PENDÊNCIAS (Correção de Status) ---
            elif tipo_arq == "PENDENCIA":
                # Procura o pagamento original para corrigir ou insere novo como pendente
                # Aqui simplificado: Insere registro de pendência para auditoria
                valor = str(row.get('valor_liquido', '0')).replace('R$','').replace('.','').replace(',','.')
                try: valor_float = float(valor)
                except: valor_float = 0.0

                c.execute('''
                     INSERT INTO pagamentos (
                            cpf_beneficiario, num_cartao, projeto, mes_referencia, ano_referencia,
                            valor_liquido, data_pagamento, status, arquivo_origem, data_importacao
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (identificador, str(row.get('num_cartao','')), projeto_inf, mes_inf, ano_selecionado,
                      valor_float, str(row.get('data_pagto','')), 'Pendente', nome_arquivo, datetime.now()))

        conn.commit()
        conn.close()
        return True, f"Arquivo {nome_arquivo} ({tipo_arq}) processado com sucesso!"
        
    except Exception as e:
        return False, f"Erro ao processar {file.name}: {str(e)}"

# ==============================================================================
# 4. INTERFACE GRÁFICA (VIEWS)
# ==============================================================================

def tela_login():
    st.markdown("<h1 style='text-align: center;'>🔐 POT - Acesso Restrito</h1>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        with st.form("login_form"):
            email = st.text_input("E-mail Institucional")
            senha = st.text_input("Senha", type="password")
            submit = st.form_submit_button("Entrar")
            
            if submit:
                conn = init_db()
                c = conn.cursor()
                c.execute("SELECT * FROM usuarios WHERE email = ?", (email,))
                user = c.fetchone()
                conn.close()
                
                if user:
                    # user[2] é a senha hash
                    if user[2] == hash_senha(senha):
                        if not validar_email_prefeitura(email):
                             st.error("Apenas e-mails @prefeitura.sp.gov.br são permitidos.")
                             return

                        st.session_state['logado'] = True
                        st.session_state['usuario'] = {'email': user[0], 'nome': user[1], 'perfil': user[3]}
                        st.session_state['trocar_senha'] = (user[4] == 1)
                        st.rerun()
                    else:
                        st.error("Senha incorreta.")
                else:
                    st.error("Usuário não encontrado.")

def tela_troca_senha():
    st.warning("⚠️ Primeiro acesso ou redefinição detectada. Você deve alterar sua senha.")
    with st.form("troca_senha"):
        nova_senha = st.text_input("Nova Senha", type="password")
        confirma_senha = st.text_input("Confirme a Nova Senha", type="password")
        btn = st.form_submit_button("Atualizar Senha")
        
        if btn:
            if nova_senha == confirma_senha and len(nova_senha) > 5:
                conn = init_db()
                c = conn.cursor()
                c.execute("UPDATE usuarios SET senha_hash = ?, trocar_senha = 0 WHERE email = ?", 
                          (hash_senha(nova_senha), st.session_state['usuario']['email']))
                conn.commit()
                conn.close()
                st.session_state['trocar_senha'] = False
                st.success("Senha atualizada! Redirecionando...")
                time.sleep(1)
                st.rerun()
            else:
                st.error("As senhas não conferem ou são muito curtas.")

def dashboard_executivo():
    st.header(f"📊 Painel Executivo - POT")
    
    # Filtros de Dashboard
    colA, colB = st.columns(2)
    with colA:
        ano_dash = st.selectbox("Ano de Referência", [2025, 2024, 2023])
    with colB:
        mes_dash = st.selectbox("Mês", ["TODOS", "JANEIRO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"])

    conn = init_db()
    
    # Query Dinâmica
    query_base = f"SELECT * FROM pagamentos WHERE ano_referencia = {ano_dash}"
    if mes_dash != "TODOS":
        query_base += f" AND mes_referencia = '{mes_dash}'"
        
    df_pgto = pd.read_sql_query(query_base, conn)
    
    # Métricas
    col1, col2, col3, col4 = st.columns(4)
    valor_total = df_pgto['valor_liquido'].sum()
    qtd_benef = df_pgto['cpf_beneficiario'].nunique()
    
    col1.metric("Total Pago (Líquido)", f"R$ {valor_total:,.2f}")
    col2.metric("Beneficiários Únicos", qtd_benef)
    col3.metric("Ticket Médio", f"R$ {valor_total/qtd_benef:,.2f}" if qtd_benef > 0 else "0")
    col4.metric("Registros Processados", len(df_pgto))
    
    st.markdown("---")
    
    # Gráficos e Tabelas
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Pagamentos por Projeto")
        if not df_pgto.empty:
            st.bar_chart(df_pgto.groupby("projeto")['valor_liquido'].sum())
        else:
            st.info("Sem dados para este período.")
            
    with c2:
        st.subheader("Status dos Lançamentos")
        if not df_pgto.empty:
            status_cont = df_pgto['status'].value_counts()
            st.write(status_cont)
            
            # Alerta de Pendências
            pendentes = df_pgto[df_pgto['status'] == 'Pendente']
            if not pendentes.empty:
                st.error(f"⚠️ Existem {len(pendentes)} pagamentos com pendências/erros neste período!")
    
    # Botão de Exportação
    st.subheader("📥 Exportar Dados Processados")
    if not df_pgto.empty:
        csv = df_pgto.to_csv(index=False).encode('utf-8')
        st.download_button("Baixar Relatório (CSV)", csv, "relatorio_pot.csv", "text/csv")

def tela_upload():
    st.header("📂 Ingestão de Arquivos")
    st.info("Suporta arquivos de Cadastro, Pagamentos e Pendências.")
    
    ano_arq = st.number_input("Ano de Referência dos Arquivos", 2020, 2030, 2025)
    files = st.file_uploader("Arraste os arquivos CSV aqui", accept_multiple_files=True)
    
    if st.button("Processar Arquivos") and files:
        bar = st.progress(0)
        for i, f in enumerate(files):
            sucesso, msg = processar_upload(f, ano_arq)
            if sucesso: st.success(msg)
            else: st.error(msg)
            bar.progress((i+1)/len(files))

def tela_consulta():
    st.header("🔍 Consultar Beneficiário (Histórico)")
    busca = st.text_input("Digite CPF ou Nome")
    if st.button("Pesquisar"):
        conn = init_db()
        # Busca Cadastro
        res = pd.read_sql_query(f"SELECT * FROM beneficiarios WHERE cpf LIKE '%{busca}%' OR nome LIKE '%{busca}%'", conn)
        
        if not res.empty:
            st.success(f"{len(res)} beneficiários encontrados.")
            st.dataframe(res)
            
            # Se encontrou um único, mostra detalhes financeiros
            if len(res) == 1:
                cpf_alvo = res.iloc[0]['cpf']
                st.subheader(f"Extrato Financeiro: {res.iloc[0]['nome']}")
                hist = pd.read_sql_query(f"SELECT * FROM pagamentos WHERE cpf_beneficiario = '{cpf_alvo}' ORDER BY ano_referencia DESC, mes_referencia DESC", conn)
                st.dataframe(hist)
        else:
            st.warning("Nada encontrado.")

def tela_admin():
    st.header("⚙️ Administração de Usuários")
    
    with st.expander("Cadastrar Novo Usuário"):
        with st.form("new_user"):
            novo_email = st.text_input("E-mail (@prefeitura)")
            novo_nome = st.text_input("Nome")
            novo_perfil = st.selectbox("Perfil", ["ADMIN_AREA", "USUARIO"])
            if st.form_submit_button("Criar Usuário"):
                if not validar_email_prefeitura(novo_email):
                    st.error("Domínio de e-mail inválido.")
                else:
                    conn = init_db()
                    try:
                        conn.execute("INSERT INTO usuarios VALUES (?, ?, ?, ?, ?)", 
                                     (novo_email, novo_nome, SENHA_PADRAO_HASH, novo_perfil, 1))
                        conn.commit()
                        st.success(f"Usuário {novo_nome} criado! Senha temporária: smdet2025")
                    except Exception as e:
                        st.error(f"Erro: {e}")
                    conn.close()
    
    st.subheader("Usuários Ativos")
    conn = init_db()
    users = pd.read_sql_query("SELECT email, nome, perfil FROM usuarios", conn)
    st.dataframe(users)

# ==============================================================================
# 5. CONTROLE DE FLUXO PRINCIPAL
# ==============================================================================
if 'logado' not in st.session_state:
    st.session_state['logado'] = False

if not st.session_state['logado']:
    tela_login()
else:
    if st.session_state.get('trocar_senha', False):
        tela_troca_senha()
    else:
        # Layout Principal Pós-Login
        usuario = st.session_state['usuario']
        
        with st.sidebar:
            st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/8/8c/Bras%C3%A3o_da_cidade_de_S%C3%A3o_Paulo.svg/1200px-Bras%C3%A3o_da_cidade_de_S%C3%A3o_Paulo.svg.png", width=80)
            st.write(f"Olá, **{usuario['nome']}**")
            st.write(f"Perfil: *{usuario['perfil']}*")
            st.markdown("---")
            
            opcoes = ["Dashboard", "Importar Arquivos", "Consulta"]
            if usuario['perfil'] in ['ADMIN_TI', 'ADMIN_AREA']:
                opcoes.append("Administração")
            
            opcoes.append("Sair")
            
            escolha = st.radio("Menu", opcoes)
            
            if escolha == "Sair":
                st.session_state['logado'] = False
                st.rerun()

        # Roteamento de Telas
        if escolha == "Dashboard":
            dashboard_executivo()
        elif escolha == "Importar Arquivos":
            tela_upload()
        elif escolha == "Consulta":
            tela_consulta()
        elif escolha == "Administração":
            tela_admin()
