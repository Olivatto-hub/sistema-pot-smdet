import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, text
import hashlib
import io
import re
import unicodedata
import difflib
import os
import tempfile
from datetime import datetime

# --- CONFIGURAÇÃO DE UPLOAD ---
if not os.path.exists(".streamlit"): os.makedirs(".streamlit")
with open(".streamlit/config.toml", "w") as f: f.write("[server]\nmaxUploadSize = 1024\n")

# ===========================================
# 1. CONFIGURAÇÃO VISUAL
# ===========================================
st.set_page_config(page_title="SMDET - Gestão POT", page_icon="💰", layout="wide")

st.markdown("""
<style>
    .header-container { text-align: center; padding-bottom: 20px; border-bottom: 2px solid #ddd; margin-bottom: 30px; }
    .header-secretaria { color: #555; font-size: 1rem; font-weight: 500; }
    .header-programa { color: #1E3A8A; font-size: 1.6rem; font-weight: bold; }
    .stTextInput > div > div > input { background-color: #f0f2f6; border-radius: 5px; }
    [data-testid="stDataFrame"] { width: 100%; }
</style>
""", unsafe_allow_html=True)

def render_header():
    st.markdown("""
        <div class="header-container">
            <div class="header-secretaria">Secretaria Municipal de Desenvolvimento Econômico e Trabalho (SMDET)</div>
            <div class="header-programa">Programa Operação Trabalho (POT)</div>
            <div style="color: #2563EB; font-size: 1.2rem; font-weight: bold;">Sistema de Gestão e Monitoramento</div>
        </div>
    """, unsafe_allow_html=True)

# ===========================================
# 2. BANCO DE DADOS
# ===========================================
@st.cache_resource
def get_db_engine():
    try:
        if "DATABASE_URL" not in st.secrets: return None
        url = st.secrets["DATABASE_URL"]
        if url.startswith("postgres://"): url = url.replace("postgres://", "postgresql://", 1)
        return create_engine(url, pool_pre_ping=True)
    except: return None

def run_db_command(sql, params=None):
    eng = get_db_engine()
    if eng:
        with eng.begin() as conn: conn.execute(text(sql), params or {})

def init_db():
    eng = get_db_engine()
    if not eng: return
    with eng.connect() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS users (email TEXT PRIMARY KEY, password TEXT, role TEXT, name TEXT, first_login INTEGER DEFAULT 1)"))
        
        # Tabela Principal
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY, programa TEXT, gerenciadora TEXT, num_cartao TEXT, nome TEXT, cpf TEXT, rg TEXT, 
                valor_pagto REAL, data_pagto TEXT, lote_pagto TEXT, agencia TEXT, arquivo_origem TEXT, linha_arquivo INTEGER, 
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # Tabela de Importação Bruta do Banco (Para histórico)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS bank_imports (
                id SERIAL PRIMARY KEY, num_cartao TEXT, nome_bb TEXT, valor_bb REAL, 
                agencia TEXT, lote TEXT, arquivo_origem TEXT, 
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # Tabela de Divergências Encontradas
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS bank_discrepancies (
                id SERIAL PRIMARY KEY, cartao TEXT, nome_sis TEXT, nome_bb TEXT, 
                lote TEXT, agencia TEXT, divergencia TEXT, arquivo_origem TEXT, 
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        conn.execute(text("CREATE TABLE IF NOT EXISTS audit_logs (id SERIAL PRIMARY KEY, user_email TEXT, action TEXT, details TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"))
        conn.commit()
        
        # Admin
        res = conn.execute(text("SELECT email FROM users WHERE email=:e"), {"e": 'admin@prefeitura.sp.gov.br'}).fetchone()
        if not res:
            h = hashlib.sha256('smdet2025'.encode()).hexdigest()
            conn.execute(text("INSERT INTO users VALUES (:e, :p, :r, :n, :f)"), 
                         {"e": 'admin@prefeitura.sp.gov.br', "p": h, "r": 'admin_ti', "n": 'Admin TI', "f": 0})
            conn.commit()

def log_action(email, action, details):
    run_db_command("INSERT INTO audit_logs (user_email, action, details) VALUES (:e, :a, :d)", {"e": email, "a": action, "d": details})

# ===========================================
# 3. INTELIGÊNCIA DE DADOS (PARSERS E FUZZY)
# ===========================================

def normalize_name(name):
    if not name or str(name).lower() in ['nan', 'none', '']: return ""
    s = str(name).upper()
    # Correção de caracteres estranhos do BB
    replacements = {'‡ÆO': 'CAO', '‡Æo': 'CAO', 'Ã£': 'A', 'Ã§': 'C', 'Ã©': 'E', 'Ã¡': 'A'}
    for k, v in replacements.items(): s = s.replace(k, v)
    nfkd = unicodedata.normalize('NFKD', s)
    return " ".join("".join([c for c in nfkd if not unicodedata.combining(c)]).split())

def nomes_sao_similares(n1, n2):
    s1 = normalize_name(n1); s2 = normalize_name(n2)
    if s1 == s2: return True
    # Remove preposições
    for p in [' DE ', ' DA ', ' DO ', ' DOS ', ' E ']:
        s1 = s1.replace(p, ' '); s2 = s2.replace(p, ' ')
    s1 = " ".join(s1.split()); s2 = " ".join(s2.split())
    if s1 == s2: return True
    
    # Verifica abreviações (M = MAURICIO)
    p1, p2 = s1.split(), s2.split()
    if len(p1) == len(p2):
        match = True
        for a, b in zip(p1, p2):
            if a != b and not (len(a)==1 and b.startswith(a)) and not (len(b)==1 and a.startswith(b)):
                # Aceita typos leves
                if difflib.SequenceMatcher(None, a, b).ratio() < 0.85:
                    match = False; break
        if match: return True
        
    return difflib.SequenceMatcher(None, s1, s2).ratio() > 0.80

def padronizar_nome_projeto(nome):
    if pd.isna(nome): return "NÃO IDENTIFICADO"
    n = normalize_name(nome).replace('POT', '').strip()
    if any(x in n for x in ['DEFESA', 'CIVIL']): return 'DEFESA CIVIL'
    if 'ZELADOR' in n: return 'ZELADORIA'
    if 'AGRI' in n or 'HORTA' in n: return 'AGRICULTURA'
    return n

# --- PARSERS REVISADOS PARA OS ARQUIVOS ENVIADOS ---

def parse_bb_resumo(file_obj):
    """Para arquivos como Resumo_CREDITO_OT_4475.txt"""
    content = file_obj.getvalue().decode('latin-1', errors='ignore')
    lines = content.split('\n')
    data = []
    curr_card = None; curr_val = 0.0; curr_name = ""
    
    # Regex Linha 1: Cartão + Valor + Nome
    reg1 = re.compile(r'^\s*(\d{6})\s+(\d+\.\d{2})\s+(.+)$')
    # Regex Linha 2: Agencia (segundo número da linha)
    reg2 = re.compile(r'^\s+\d{2}\s+(\d{4})\s+')

    for line in lines:
        if not line.strip(): continue
        m1 = reg1.match(line)
        if m1:
            curr_card, v, n = m1.groups()
            curr_val = float(v)
            curr_name = n.strip()
            continue
        if curr_card:
            m2 = reg2.match(line)
            if m2:
                ag = m2.group(1)
                data.append({'num_cartao': curr_card, 'valor_pagto': curr_val, 'nome': curr_name, 'agencia': ag, 'lote_pagto': 'RESUMO', 'arquivo_origem': file_obj.name})
                curr_card = None
    return pd.DataFrame(data)

def parse_bb_cadastro(file_obj):
    """Para arquivos como REL.CADASTRO.OT.V5478.TXT"""
    content = file_obj.getvalue().decode('latin-1', errors='ignore')
    lines = content.split('\n')
    data = []
    
    for line in lines:
        if len(line) < 40 or "Projeto" in line: continue
        # Cartão (6 digitos) no meio da linha
        match = re.search(r'\s(\d{6})\s+([A-Z\s\.]+?)\s+\d', line)
        if match:
            cartao, nome = match.groups()
            # Lote costuma ser o último token numérico da linha (ex: 5478)
            tokens = line.strip().split()
            lote = tokens[-1] if tokens[-1].isdigit() and len(tokens[-1]) == 4 else ''
            # Agencia costuma estar antes do nome da agencia. Tentativa heurística:
            # Procura padrao de 4 digitos que não seja o lote
            agencia = ''
            nums_4d = re.findall(r'\b\d{4}\b', line)
            for n in nums_4d:
                if n != lote: agencia = n
            
            data.append({
                'num_cartao': cartao, 'nome': nome.strip(), 'lote_pagto': lote, 'agencia': agencia,
                'valor_pagto': 0.0, 'arquivo_origem': file_obj.name
            })
    return pd.DataFrame(data)

def standardize_dataframe(df, filename):
    df.columns = [str(c).strip().lower() for c in df.columns]
    mapa = {'projeto': 'programa', 'nome': 'nome', 'cpf': 'cpf', 'cartao': 'num_cartao', 'valor': 'valor_pagto', 'lote': 'lote_pagto', 'agencia': 'agencia'}
    new_cols = {}
    for c in df.columns:
        for k, v in mapa.items():
            if k in c: new_cols[c] = v; break
    df = df.rename(columns=new_cols)
    
    for c in ['programa','nome','cpf','num_cartao','valor_pagto','lote_pagto','agencia']:
        if c not in df.columns: df[c] = None
        
    df['arquivo_origem'] = filename
    if df['programa'].isnull().all(): df['programa'] = filename.split('.')[0]
    df['programa'] = df['programa'].apply(padronizar_nome_projeto)
    
    # Clean Values
    def clean_val(x):
        try: return float(str(x).replace('R$', '').replace('.', '').replace(',', '.'))
        except: return 0.0
    if 'valor_pagto' in df.columns: df['valor_pagto'] = df['valor_pagto'].apply(clean_val)
    
    # Clean IDs
    for c in ['cpf', 'num_cartao']:
        if c in df.columns: df[c] = df[c].astype(str).str.replace(r'\D', '', regex=True)
    return df

# ===========================================
# 4. APP PRINCIPAL
# ===========================================

def login_screen():
    render_header()
    c1,c2,c3 = st.columns([1,2,1])
    with c2:
        with st.form("login"):
            e = st.text_input("Email"); p = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar"):
                eng = get_db_engine()
                if not eng: st.error("Erro BD"); return
                with eng.connect() as conn:
                    res = conn.execute(text("SELECT * FROM users WHERE email=:e"), {"e": e}).fetchone()
                    if res and res.password == hashlib.sha256(p.encode()).hexdigest():
                        st.session_state['logged_in'] = True
                        st.session_state['u'] = {'email':res.email, 'role':res.role, 'name':res.name}
                        st.rerun()
                    else: st.error("Inválido")

def app():
    u = st.session_state['u']
    st.sidebar.markdown(f"**Usuário:** {u['name']}")
    menu = st.sidebar.radio("Menu", ["Dashboard", "Upload e Abertura", "Análise e Correção", "Conferência BB", "Relatórios"])
    
    eng = get_db_engine()
    df_raw = pd.DataFrame()
    if eng:
        try: df_raw = pd.read_sql("SELECT * FROM payments", eng)
        except: pass

    render_header()

    # --- DASHBOARD ---
    if menu == "Dashboard":
        st.subheader("📊 Visão Geral")
        if not df_raw.empty:
            df_raw['valor_pagto'] = pd.to_numeric(df_raw['valor_pagto'], errors='coerce').fillna(0.0)
            mask_valid = (df_raw['valor_pagto'] > 0.01) & (~df_raw['programa'].astype(str).str.isnumeric())
            df_clean = df_raw[mask_valid].copy()
            
            k1,k2,k3 = st.columns(3)
            k1.metric("Total Repasses", f"R$ {df_clean['valor_pagto'].sum():,.2f}")
            k2.metric("Beneficiários", df_clean['nome'].nunique())
            k3.metric("Projetos", df_clean['programa'].nunique())
            st.markdown("---")
            
            if not df_clean.empty:
                grp = df_clean.groupby('programa')['valor_pagto'].sum().reset_index().sort_values('valor_pagto', ascending=True)
                fig = px.bar(grp, x='valor_pagto', y='programa', orientation='h', text_auto='.2s', title="Totais por Projeto")
                st.plotly_chart(fig, use_container_width=True)
                st.dataframe(grp.sort_values('valor_pagto', ascending=False).style.format({'valor_pagto': 'R$ {:,.2f}'}), use_container_width=True)
            else: st.warning("Sem dados válidos (Valores > 0).")
        else: st.info("Sem dados.")

    # --- UPLOAD ---
    elif menu == "Upload e Abertura":
        st.subheader("📂 Upload de Pagamentos e Abertura de Contas")
        files = st.file_uploader("Arquivos (CSV/Excel/TXT)", accept_multiple_files=True)
        if files and st.button("Processar"):
            dfs = []
            try: existing = pd.read_sql("SELECT DISTINCT arquivo_origem FROM payments", eng)['arquivo_origem'].tolist()
            except: existing = []
            
            for f in files:
                if f.name in existing:
                    st.warning(f"⚠️ {f.name} já foi enviado antes. Ignorado."); continue
                try:
                    if f.name.upper().endswith('.TXT'):
                        d = parse_bb_resumo(f) if "RESUMO" in f.name.upper() else parse_bb_cadastro(f)
                    elif f.name.endswith('.csv'): d = pd.read_csv(f, sep=';', encoding='latin1', dtype=str)
                    else: d = pd.read_excel(f, dtype=str)
                    
                    if not d.empty: 
                        d = standardize_dataframe(d, f.name)
                        dfs.append(d)
                except Exception as e: st.error(f"Erro {f.name}: {e}")
            
            if dfs:
                final = pd.concat(dfs, ignore_index=True)
                final.to_sql('payments', eng, if_exists='append', index=False, method='multi', chunksize=500)
                st.success("✅ Arquivos Salvos!"); st.rerun()

    # --- ANÁLISE ---
    elif menu == "Análise e Correção":
        st.subheader("🔍 Auditoria e Correção")
        c1, c2, c3, c4 = st.columns(4)
        q_nome = c1.text_input("Nome/CPF/Cartão/RG")
        q_lote = c2.text_input("Lote")
        q_ag = c3.text_input("Agência")
        
        if not df_raw.empty:
            df_view = df_raw.copy()
            if q_nome:
                t = q_nome.upper()
                df_view = df_view[df_view['nome'].str.upper().str.contains(t, na=False) | df_view['cpf'].str.contains(t, na=False) | df_view['num_cartao'].str.contains(t, na=False)]
            if q_lote: df_view = df_view[df_view['lote_pagto'].astype(str).str.contains(q_lote, na=False)]
            if q_ag: df_view = df_view[df_view['agencia'].astype(str).str.contains(q_ag, na=False)]
            
            st.info(f"{len(df_view)} resultados.")
            event = st.dataframe(df_view, use_container_width=True, hide_index=True, selection_mode="multi-row", on_select="rerun")
            
            if event.selection.rows:
                sel = df_view.iloc[event.selection.rows]
                st.download_button("📥 Baixar Seleção", sel.to_csv(index=False).encode('utf-8'), "selecao.csv")
                
                if u['role'] in ['admin_ti', 'admin_equipe']:
                    with st.expander("✏️ Editar Selecionados"):
                        ed = st.data_editor(sel, hide_index=True)
                        if st.button("Salvar Edições"):
                            with eng.begin() as conn:
                                for i, r in ed.iterrows():
                                    conn.execute(text("UPDATE payments SET nome=:n, cpf=:c, lote_pagto=:l, agencia=:a WHERE id=:id"),
                                                 {"n":r['nome'], "c":r['cpf'], "l":r['lote_pagto'], "a":r['agencia'], "id":r['id']})
                            st.success("Salvo!"); st.rerun()

    # --- CONFERÊNCIA BB (FILTROS NOVOS) ---
    elif menu == "Conferência BB":
        st.subheader("🏦 Conferência Bancária")
        
        t1, t2 = st.tabs(["Nova Conferência", "Histórico e Buscas"])
        
        with t1:
            st.markdown("Envie o arquivo do banco. Ele será salvo no histórico para consultas futuras.")
            fbb = st.file_uploader("Arquivo TXT Banco", type=['txt'])
            
            if fbb and st.button("Processar e Salvar"):
                # Verifica Duplicidade
                try: exists = pd.read_sql(text("SELECT COUNT(*) FROM bank_imports WHERE arquivo_origem = :f"), eng, params={"f":fbb.name}).scalar()
                except: exists = 0
                
                if exists > 0:
                    st.warning(f"O arquivo {fbb.name} já foi processado antes.")
                
                # Parse
                df_bb = parse_bb_resumo(fbb) if "Resumo" in fbb.name else parse_bb_cadastro(fbb)
                
                if not df_bb.empty:
                    # Salva TUDO na tabela de importações (para permitir busca futura)
                    df_save = df_bb.rename(columns={'nome': 'nome_bb', 'valor_pagto': 'valor_bb', 'lote_pagto': 'lote'})
                    # Ensure cols
                    for c in ['num_cartao','nome_bb','valor_bb','agencia','lote','arquivo_origem']: 
                        if c not in df_save.columns: df_save[c] = None
                    df_save.to_sql('bank_imports', eng, if_exists='append', index=False, chunksize=500)
                    
                    # Comparação
                    if not df_raw.empty:
                        # Normaliza chaves
                        df_bb['k'] = df_bb['num_cartao'].str.strip().str.lstrip('0')
                        df_raw['k'] = df_raw['num_cartao'].astype(str).str.strip().str.replace(r'\.0$','').str.lstrip('0')
                        merged = pd.merge(df_raw, df_bb, on='k', suffixes=('_sis', '_bb'))
                        divs = []
                        prog = st.progress(0)
                        for i, r in merged.iterrows():
                            prog.progress((i+1)/len(merged))
                            if not nomes_sao_similares(r['nome_sis'], r['nome_bb']):
                                divs.append({
                                    'cartao': r['k'], 'nome_sis': r['nome_sis'], 'nome_bb': r['nome_bb'],
                                    'lote': r.get('lote_pagto_bb', ''), 'agencia': r.get('agencia_bb', ''),
                                    'divergencia': 'NOME', 'arquivo_origem': fbb.name
                                })
                        prog.empty()
                        
                        if divs:
                            pd.DataFrame(divs).to_sql('bank_discrepancies', eng, if_exists='append', index=False)
                            st.error(f"{len(divs)} Divergências encontradas e salvas.")
                        else: st.success("✅ Nenhuma divergência encontrada! (Nomes compatíveis)")
                    else: st.warning("Base do sistema vazia. Arquivo salvo apenas no histórico.")

        with t2:
            st.markdown("#### 🔎 Buscar nas Divergências")
            
            # FILTROS REQUISITADOS
            c1, c2, c3, c4, c5 = st.columns(5)
            f_nome = c1.text_input("Nome", key="fn")
            f_cartao = c2.text_input("Cartão", key="fc")
            f_ag = c3.text_input("Agência", key="fa")
            f_lote = c4.text_input("Lote", key="fl")
            
            query = "SELECT * FROM bank_discrepancies WHERE 1=1"
            params = {}
            if f_nome: 
                query += " AND (nome_sis ILIKE :n OR nome_bb ILIKE :n)"
                params['n'] = f"%{f_nome}%"
            if f_cartao:
                query += " AND cartao LIKE :c"
                params['c'] = f"%{f_cartao}%"
            if f_ag:
                query += " AND agencia LIKE :a"
                params['a'] = f"%{f_ag}%"
            if f_lote:
                query += " AND lote LIKE :l"
                params['l'] = f"%{f_lote}%"
                
            try: h = pd.read_sql(text(query), eng, params=params)
            except: h = pd.DataFrame()
            
            if not h.empty:
                st.dataframe(h, use_container_width=True)
                if st.button("Limpar Histórico de Divergências"):
                    run_db_command("DELETE FROM bank_discrepancies"); st.rerun()
            else: st.info("Nenhuma divergência encontrada com estes filtros.")

    # --- RELATÓRIOS ---
    elif menu == "Relatórios":
        st.subheader("📥 Exportação")
        if not df_raw.empty:
            proj = st.multiselect("Projeto", df_raw['programa'].unique())
            dff = df_raw[df_raw['programa'].isin(proj)] if proj else df_raw
            st.download_button("Baixar CSV", dff.to_csv(index=False).encode('utf-8'), "dados.csv")

if __name__ == "__main__":
    init_db()
    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
    if st.session_state['logged_in']: app()
    else: login_screen()
