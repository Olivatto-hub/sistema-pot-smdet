import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, text
import hashlib
import re
import unicodedata
import difflib
import os

# ===========================================
# 1. CONFIGURAÇÃO INICIAL
# ===========================================
st.set_page_config(page_title="SMDET - Gestão POT", page_icon="💰", layout="wide")

# Garante pasta de config para upload grande
if not os.path.exists(".streamlit"): os.makedirs(".streamlit")
with open(".streamlit/config.toml", "w") as f: f.write("[server]\nmaxUploadSize = 1024\n")

st.markdown("""
<style>
    .header-div { text-align: center; padding: 20px; border-bottom: 2px solid #ddd; margin-bottom: 20px; }
    .title-text { color: #1E3A8A; font-size: 1.8rem; font-weight: bold; }
    .sub-text { color: #555; font-size: 1.1rem; }
    /* Destaque para os filtros */
    .stTextInput > div > div > input { background-color: #f0f2f6; }
</style>
""", unsafe_allow_html=True)

# ===========================================
# 2. BANCO DE DADOS (SQLite/Postgres Híbrido)
# ===========================================
@st.cache_resource
def get_engine():
    # Tenta conexão Postgres (Produção), senão usa SQLite (Local)
    if "DATABASE_URL" in st.secrets:
        url = st.secrets["DATABASE_URL"].replace("postgres://", "postgresql://")
        return create_engine(url)
    return create_engine('sqlite:///pot_system_v2.db', connect_args={'check_same_thread': False})

def init_db():
    eng = get_engine()
    with eng.connect() as conn:
        # Tabela Usuários
        conn.execute(text("CREATE TABLE IF NOT EXISTS users (email TEXT, password TEXT, role TEXT, name TEXT)"))
        
        # Tabela Pagamentos (Sistema)
        # Adicionamos colunas extras para rastreabilidade
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY, -- Para Postgres (ou INTEGER PRIMARY KEY AUTOINCREMENT para SQLite)
                programa TEXT, gerenciadora TEXT, num_cartao TEXT, nome TEXT, cpf TEXT, rg TEXT,
                valor_pagto REAL, lote_pagto TEXT, agencia TEXT, arquivo_origem TEXT
            )
        """.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT" if 'sqlite' in str(eng.url) else "SERIAL PRIMARY KEY")))
        
        # Tabela Importações Banco (Conferência)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS bank_imports (
                id INTEGER PRIMARY KEY, num_cartao TEXT, nome_bb TEXT, valor_bb REAL,
                agencia TEXT, lote TEXT, arquivo_origem TEXT
            )
        """))
        
        # Tabela Divergências
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS discrepancies (
                cartao TEXT, nome_sis TEXT, nome_bb TEXT, motivo TEXT, arquivo TEXT
            )
        """))
        
        # Cria admin se não existir
        res = conn.execute(text("SELECT email FROM users WHERE email='admin@prefeitura.sp.gov.br'")).fetchone()
        if not res:
            # Senha hash padrão para teste (smdet2025)
            h = hashlib.sha256('smdet2025'.encode()).hexdigest()
            conn.execute(text("INSERT INTO users VALUES ('admin@prefeitura.sp.gov.br', :p, 'admin_ti', 'Admin TI')"), {"p": h})
            if 'sqlite' not in str(eng.url): conn.commit()

# ===========================================
# 3. LÓGICA DE NEGÓCIO (Inteligência)
# ===========================================

def limpar_texto(texto):
    """Normaliza texto: remove acentos, caixa alta, caracteres estranhos."""
    if not texto: return ""
    s = str(texto).upper()
    # Correção de caracteres corrompidos comuns em TXT de banco
    s = s.replace('‡ÆO', 'CAO').replace('‡Æo', 'CAO').replace('Ã£', 'A').replace('Ã§', 'C')
    nfkd = unicodedata.normalize('NFKD', s)
    s = "".join([c for c in nfkd if not unicodedata.combining(c)])
    return re.sub(r'[^A-Z0-9 ]', '', s).strip()

def nomes_similares(n1, n2):
    """Compara nomes ignorando erros de digitação e abreviações."""
    s1 = limpar_texto(n1)
    s2 = limpar_texto(n2)
    if s1 == s2: return True
    
    # Remove preposições
    for p in [' DE ', ' DA ', ' DO ', ' DOS ']:
        s1 = s1.replace(p, ' '); s2 = s2.replace(p, ' ')
    
    # Verifica se um é parte do outro (ex: "JOSE SILVA" em "JOSE DA SILVA")
    parts1 = s1.split()
    parts2 = s2.split()
    
    # Se as primeiras e últimas palavras baterem, consideramos igual (ignora nome do meio abreviado)
    if len(parts1) > 1 and len(parts2) > 1:
        if parts1[0] == parts2[0] and parts1[-1] == parts2[-1]:
            return True
            
    # Similaridade geral (Levenshtein)
    return difflib.SequenceMatcher(None, s1, s2).ratio() > 0.85

def ler_txt_banco(arquivo):
    """Lê os formatos específicos do BB que você enviou."""
    conteudo = arquivo.getvalue().decode('latin-1', errors='ignore')
    linhas = conteudo.split('\n')
    dados = []
    
    cartao_atual = None
    valor_atual = 0.0
    nome_atual = ""
    
    for linha in linhas:
        # FORMATO 1: Resumo_CREDITO (Dados em linhas separadas)
        # Linha 1: Cartão (6 dig) + Valor + Nome
        match_main = re.search(r'^\s*(\d{6})\s+(\d+\.\d{2})\s+(.+)$', linha)
        if match_main:
            cartao_atual, val, nome_atual = match_main.groups()
            valor_atual = float(val)
            continue
            
        # Linha 2 (logo abaixo): Distrito + Agência
        match_ag = re.search(r'^\s+\d{2}\s+(\d{4})\s+', linha)
        if cartao_atual and match_ag:
            agencia = match_ag.group(1)
            dados.append({
                'num_cartao': cartao_atual, 'valor_pagto': valor_atual, 'nome': nome_atual.strip(),
                'agencia': agencia, 'lote_pagto': 'TXT_RESUMO', 'arquivo_origem': arquivo.name
            })
            cartao_atual = None
            continue

        # FORMATO 2: REL.CADASTRO (Lote no final da linha)
        # Ex: ... CARTAO NOME ... AGENCIA ... LOTE
        if "Projeto" in linha: continue
        # Procura sequência de 6 dígitos (Cartão)
        match_cad = re.search(r'\s(\d{6})\s+([A-Z\s\.]+?)\s+\d', linha)
        if match_cad:
            card, nome = match_cad.groups()
            # Pega números no final da linha para Lote e Agência
            nums = re.findall(r'\b\d{4}\b', linha)
            lote = nums[-1] if nums else ''
            ag = nums[-2] if len(nums) >= 2 else ''
            
            dados.append({
                'num_cartao': card, 'valor_pagto': 0.0, 'nome': nome.strip(),
                'agencia': ag, 'lote_pagto': lote, 'arquivo_origem': arquivo.name
            })
            
    return pd.DataFrame(dados)

# ===========================================
# 4. INTERFACE
# ===========================================

def main():
    if 'user' not in st.session_state: st.session_state['user'] = None

    # LOGIN SIMPLES
    if not st.session_state['user']:
        st.markdown("<h2 style='text-align: center;'>🔐 Acesso Restrito - POT</h2>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1,2,1])
        with c2:
            email = st.text_input("E-mail Institucional")
            senha = st.text_input("Senha", type="password")
            if st.button("Entrar", use_container_width=True):
                eng = get_engine()
                with eng.connect() as conn:
                    # Hash simples para exemplo (em produção use libs seguras)
                    h = hashlib.sha256(senha.encode()).hexdigest()
                    u = conn.execute(text("SELECT * FROM users WHERE email=:e"), {"e":email}).fetchone()
                    if u and u.password == h: # Ajuste conforme sua coluna de senha
                        st.session_state['user'] = {'email': u.email, 'role': u.role, 'name': u.name}
                        st.rerun()
                    else:
                        st.error("Credenciais inválidas.")
        return

    # APLICAÇÃO LOGADA
    u = st.session_state['user']
    
    # SIDEBAR
    st.sidebar.markdown(f"### 👤 {u['name']}")
    menu = st.sidebar.radio("Menu", ["Dashboard", "Upload de Pagamentos", "Análise e Correção", "Conferência BB"])
    if st.sidebar.button("Sair"):
        st.session_state['user'] = None
        st.rerun()

    # HEADER
    st.markdown("<div class='header-div'><div class='title-text'>Sistema de Gestão POT</div><div class='sub-text'>Monitoramento e Conferência Bancária</div></div>", unsafe_allow_html=True)

    eng = get_engine()

    # --- DASHBOARD ---
    if menu == "Dashboard":
        df = pd.read_sql("SELECT * FROM payments", eng)
        if not df.empty:
            # Filtro visual para ignorar zerados e nomes de projeto sujos
            df['valor_pagto'] = pd.to_numeric(df['valor_pagto'], errors='coerce').fillna(0)
            df_valid = df[(df['valor_pagto'] > 0) & (~df['programa'].str.isnumeric())].copy()
            
            # Remove "POT" do nome para o gráfico
            df_valid['programa_clean'] = df_valid['programa'].apply(lambda x: limpar_texto(x).replace("POT ", ""))
            
            c1, c2, c3 = st.columns(3)
            c1.metric("💰 Total Repassado", f"R$ {df_valid['valor_pagto'].sum():,.2f}")
            c2.metric("👥 Beneficiários Ativos", df_valid['num_cartao'].nunique())
            c3.metric("🏗️ Projetos", df_valid['programa_clean'].nunique())
            
            st.divider()
            st.subheader("Total por Projeto")
            
            # Gráfico Horizontal
            grp = df_valid.groupby('programa_clean')['valor_pagto'].sum().reset_index().sort_values('valor_pagto')
            fig = px.bar(grp, x='valor_pagto', y='programa_clean', orientation='h', text_auto='.2s')
            fig.update_layout(yaxis_title="", xaxis_title="Valor (R$)", height=600)
            st.plotly_chart(fig, use_container_width=True)
            
            st.dataframe(grp.sort_values('valor_pagto', ascending=False), use_container_width=True)
        else:
            st.info("Nenhum dado de pagamento carregado.")

    # --- UPLOAD ---
    elif menu == "Upload de Pagamentos":
        st.subheader("📂 Importar Base de Dados do Sistema")
        uploaded = st.file_uploader("Arraste CSV ou Excel aqui", accept_multiple_files=True)
        
        if uploaded and st.button("Processar Arquivos"):
            # Verifica duplicidade
            existentes = pd.read_sql("SELECT DISTINCT arquivo_origem FROM payments", eng)['arquivo_origem'].tolist()
            dfs = []
            for f in uploaded:
                if f.name in existentes:
                    st.warning(f"O arquivo {f.name} já consta no banco. Ignorado.")
                    continue
                try:
                    if f.name.endswith('.csv'): 
                        # Tenta ler com separador ; primeiro
                        temp = pd.read_csv(f, sep=';', dtype=str, encoding='latin1')
                        if len(temp.columns) < 2: # Se falhou, tenta vírgula
                            f.seek(0)
                            temp = pd.read_csv(f, sep=',', dtype=str, encoding='latin1')
                    else: 
                        temp = pd.read_excel(f, dtype=str)
                    
                    # Padronização de Colunas
                    temp.columns = [c.lower() for c in temp.columns]
                    col_map = {'projeto': 'programa', 'nome': 'nome', 'cpf': 'cpf', 'valor': 'valor_pagto', 'cartao': 'num_cartao', 'lote': 'lote_pagto', 'agencia': 'agencia'}
                    rename = {}
                    for c in temp.columns:
                        for k, v in col_map.items():
                            if k in c: rename[c] = v; break
                    
                    temp = temp.rename(columns=rename)
                    temp['arquivo_origem'] = f.name
                    
                    # Limpeza de Valor
                    if 'valor_pagto' in temp.columns:
                        temp['valor_pagto'] = temp['valor_pagto'].astype(str).str.replace('R$', '').str.replace('.', '').str.replace(',', '.').astype(float)
                    
                    dfs.append(temp)
                except Exception as e:
                    st.error(f"Erro ao ler {f.name}: {e}")
            
            if dfs:
                full_df = pd.concat(dfs, ignore_index=True)
                # Garante colunas mínimas
                for c in ['programa','nome','cpf','num_cartao','valor_pagto','lote_pagto','agencia']:
                    if c not in full_df.columns: full_df[c] = None
                
                # Salva no Banco
                full_df.to_sql('payments', eng, if_exists='append', index=False, chunksize=500)
                st.success(f"{len(full_df)} registros importados com sucesso!")
                st.rerun()

    # --- ANÁLISE E CORREÇÃO (BUSCAS FUNCIONAIS) ---
    elif menu == "Análise e Correção":
        st.subheader("🔍 Auditoria de Dados e Correções")
        
        # Filtros Globais
        c1, c2, c3, c4 = st.columns(4)
        q_nome = c1.text_input("Buscar por Nome")
        q_doc = c2.text_input("Buscar por CPF/RG")
        q_cartao = c3.text_input("Buscar por Cartão")
        q_lote = c4.text_input("Buscar por Lote/Agência")
        
        # Query Dinâmica
        query = "SELECT * FROM payments WHERE 1=1"
        params = {}
        
        if q_nome:
            query += " AND nome LIKE :nome"
            params['nome'] = f"%{q_nome}%"
        if q_doc:
            query += " AND (cpf LIKE :doc OR rg LIKE :doc)"
            params['doc'] = f"%{q_doc}%"
        if q_cartao:
            query += " AND num_cartao LIKE :cart"
            params['cart'] = f"%{q_cartao}%"
        if q_lote:
            query += " AND (lote_pagto LIKE :lote OR agencia LIKE :lote)"
            params['lote'] = f"%{q_lote}%"
            
        # Limite para não travar
        query += " LIMIT 1000"
        
        df_res = pd.read_sql(text(query), eng, params=params)
        
        st.write(f"**Resultados Encontrados:** {len(df_res)}")
        
        if not df_res.empty:
            # Edição em Grade
            edited = st.data_editor(df_res, use_container_width=True, hide_index=True, key="editor_analise")
            
            col_save, col_down = st.columns(2)
            if col_save.button("💾 Salvar Alterações"):
                with eng.begin() as conn:
                    # Atualiza linha a linha (idealmente seria batch, mas ok para volume baixo de edição manual)
                    for i, row in edited.iterrows():
                        conn.execute(text("""
                            UPDATE payments 
                            SET nome=:nome, cpf=:cpf, num_cartao=:cartao, programa=:prog, valor_pagto=:valor
                            WHERE id=:id
                        """), {
                            'nome': row['nome'], 'cpf': row['cpf'], 'cartao': row['num_cartao'], 
                            'prog': row['programa'], 'valor': row['valor_pagto'], 'id': row['id']
                        })
                st.success("Dados atualizados!")
                st.rerun()
            
            col_down.download_button("📥 Exportar Resultados (CSV)", df_res.to_csv(index=False).encode('utf-8'), "analise.csv")

    # --- CONFERÊNCIA BB (CORRIGIDA) ---
    elif menu == "Conferência BB":
        st.subheader("🏦 Confronto: Sistema x Banco")
        
        t1, t2 = st.tabs(["Processar Novos Arquivos", "Histórico e Buscas"])
        
        with t1:
            st.markdown("Suba os arquivos **TXT** do Banco do Brasil.")
            files_bb = st.file_uploader("Arquivos BB", accept_multiple_files=True)
            
            if files_bb and st.button("Processar Conferência"):
                # Carrega base do sistema para memória
                sis_df = pd.read_sql("SELECT num_cartao, nome FROM payments", eng)
                # Limpa cartões do sistema para chave de comparação (remove zeros a esquerda)
                sis_df['key'] = sis_df['num_cartao'].astype(str).str.replace(r'\.0$', '', regex=True).str.lstrip('0')
                
                divergencias = []
                
                for f in files_bb:
                    # Escolhe o parser correto
                    if "RESUMO" in f.name.upper(): 
                        df_bb = parse_bb_resumo(f)
                    else: 
                        df_bb = parse_bb_cadastro(f)
                    
                    if df_bb.empty: continue
                    
                    # Salva importação no histórico
                    df_bb.to_sql('bank_imports', eng, if_exists='append', index=False)
                    
                    # Cruza dados
                    df_bb['key'] = df_bb['num_cartao'].astype(str).str.lstrip('0')
                    
                    # Merge inner (apenas os que existem nos dois)
                    merged = pd.merge(sis_df, df_bb, on='key', suffixes=('_sis', '_bb'))
                    
                    for i, row in merged.iterrows():
                        # COMPARAÇÃO FUZZY (Resolve Maiúsculas, Acentos e Abreviações)
                        if not nomes_similares(row['nome_sis'], row['nome_bb']):
                            divergencias.append({
                                'cartao': row['key'],
                                'nome_sis': row['nome_sis'],
                                'nome_bb': row['nome_bb'],
                                'motivo': 'DIVERGÊNCIA NOMINAL',
                                'arquivo': f.name
                            })
                
                if divergencias:
                    pd.DataFrame(divergencias).to_sql('discrepancies', eng, if_exists='append', index=False)
                    st.error(f"{len(divergencias)} divergências reais encontradas e salvas.")
                else:
                    st.success("✅ Arquivos processados. Nenhuma divergência relevante encontrada (nomes compatíveis).")

        with t2:
            st.markdown("#### Histórico de Divergências")
            
            # Filtros na Conferência
            c1, c2 = st.columns(2)
            f_nome = c1.text_input("Filtrar por Nome (Sis ou Banco)")
            f_cartao = c2.text_input("Filtrar por Cartão")
            
            query_div = "SELECT * FROM discrepancies WHERE 1=1"
            p_div = {}
            if f_nome:
                query_div += " AND (nome_sis LIKE :n OR nome_bb LIKE :n)"
                p_div['n'] = f"%{f_nome}%"
            if f_cartao:
                query_div += " AND cartao LIKE :c"
                p_div['c'] = f"%{f_cartao}%"
                
            df_div = pd.read_sql(text(query_div), eng, params=p_div)
            st.dataframe(df_div, use_container_width=True)
            
            if st.button("Limpar Histórico de Divergências"):
                with eng.begin() as conn: conn.execute(text("DELETE FROM discrepancies"))
                st.rerun()

if __name__ == "__main__":
    init_db()
    app()
