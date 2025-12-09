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

# --- CONFIGURAÇÃO DE UPLOAD (1GB) ---
if not os.path.exists(".streamlit"): os.makedirs(".streamlit")
with open(".streamlit/config.toml", "w") as f: f.write("[server]\nmaxUploadSize = 1024\n")

# --- IMPORTAÇÕES OPCIONAIS ---
try: import matplotlib.pyplot as plt
except ImportError: plt = None
try: from fpdf import FPDF
except ImportError: FPDF = None

# ===========================================
# 1. CONFIGURAÇÃO VISUAL
# ===========================================
st.set_page_config(page_title="SMDET - Gestão POT", page_icon="💰", layout="wide")

st.markdown("""
<style>
    .header-container { text-align: center; padding-bottom: 20px; border-bottom: 2px solid #ddd; margin-bottom: 30px; }
    .header-secretaria { color: #555; font-size: 1rem; font-weight: 500; }
    .header-programa { color: #1E3A8A; font-size: 1.6rem; font-weight: bold; }
    .header-sistema { color: #2563EB; font-size: 1.2rem; font-weight: bold; }
    .metric-card { background-color: #f8f9fa; padding: 15px; border-radius: 10px; border-left: 5px solid #1E3A8A; }
    [data-testid="stDataFrame"] { width: 100%; }
</style>
""", unsafe_allow_html=True)

def render_header():
    st.markdown("""
        <div class="header-container">
            <div class="header-secretaria">Secretaria Municipal de Desenvolvimento Econômico e Trabalho (SMDET)</div>
            <div class="header-programa">Programa Operação Trabalho (POT)</div>
            <div class="header-sistema">Sistema de Gestão e Monitoramento de Pagamentos</div>
        </div>
    """, unsafe_allow_html=True)

# ===========================================
# 2. BANCO DE DADOS (POSTGRESQL)
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
        # Tabela Usuários
        conn.execute(text('''CREATE TABLE IF NOT EXISTS users (email TEXT PRIMARY KEY, password TEXT, role TEXT, name TEXT, first_login INTEGER DEFAULT 1)'''))
        
        # Tabela Pagamentos (Sistema)
        conn.execute(text('''CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY, programa TEXT, gerenciadora TEXT, num_cartao TEXT, nome TEXT, cpf TEXT, rg TEXT, 
            valor_pagto REAL, data_pagto TEXT, lote_pagto TEXT, agencia TEXT, arquivo_origem TEXT, linha_arquivo INTEGER, 
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )'''))
        
        # NOVA TABELA: Importações do Banco (Para persistência da Conferência)
        conn.execute(text('''CREATE TABLE IF NOT EXISTS bank_imports (
            id SERIAL PRIMARY KEY, num_cartao TEXT, nome_bb TEXT, valor_bb REAL, 
            agencia TEXT, lote TEXT, arquivo_origem TEXT, 
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )'''))
        
        # Tabela Divergências
        conn.execute(text('''CREATE TABLE IF NOT EXISTS bank_discrepancies (
            id SERIAL PRIMARY KEY, cartao TEXT, nome_sis TEXT, nome_bb TEXT, 
            lote TEXT, agencia TEXT, divergencia TEXT, arquivo_origem TEXT, 
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )'''))
        
        # Logs
        conn.execute(text('''CREATE TABLE IF NOT EXISTS audit_logs (id SERIAL PRIMARY KEY, user_email TEXT, action TEXT, details TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)'''))
        conn.commit()
        
        # Admin Default
        res = conn.execute(text("SELECT email FROM users WHERE email=:e"), {"e": 'admin@prefeitura.sp.gov.br'}).fetchone()
        if not res:
            h = hashlib.sha256('smdet2025'.encode()).hexdigest()
            conn.execute(text("INSERT INTO users VALUES (:e, :p, :r, :n, :f)"), 
                         {"e": 'admin@prefeitura.sp.gov.br', "p": h, "r": 'admin_ti', "n": 'Admin TI', "f": 0})
            conn.commit()

def log_action(email, action, details):
    run_db_command("INSERT INTO audit_logs (user_email, action, details) VALUES (:e, :a, :d)", {"e": email, "a": action, "d": details})

# ===========================================
# 3. FUNÇÕES DE LIMPEZA E PARSERS
# ===========================================

def normalize_name(name):
    if not name or str(name).lower() in ['nan', 'none', '']: return ""
    s = str(name).upper()
    # Correção de Encoding
    replacements = {'‡ÆO': 'CAO', '‡Æo': 'CAO', 'Ã£': 'A', 'Ã§': 'C', 'Ã©': 'E', 'Ã¡': 'A'}
    for k, v in replacements.items(): s = s.replace(k, v)
    nfkd = unicodedata.normalize('NFKD', s)
    return " ".join("".join([c for c in nfkd if not unicodedata.combining(c)]).split())

def nomes_sao_similares(n1, n2):
    s1 = normalize_name(n1); s2 = normalize_name(n2)
    if s1 == s2: return True
    # Remove preposições e espaços
    for p in [' DE ', ' DA ', ' DO ', ' DOS ', ' E ']:
        s1 = s1.replace(p, ' '); s2 = s2.replace(p, ' ')
    s1 = " ".join(s1.split()); s2 = " ".join(s2.split())
    if s1 == s2: return True
    
    # Abreviações e Typos
    parts1, parts2 = s1.split(), s2.split()
    if len(parts1) == len(parts2):
        match = True
        for p1, p2 in zip(parts1, parts2):
            # Aceita se for abreviação (M = MARIA) ou similaridade > 80%
            if p1 != p2 and not (len(p1)==1 and p2.startswith(p1)) and not (len(p2)==1 and p1.startswith(p2)):
                if difflib.SequenceMatcher(None, p1, p2).ratio() < 0.80:
                    match = False; break
        if match: return True
        
    return difflib.SequenceMatcher(None, s1, s2).ratio() > 0.75

def padronizar_nome_projeto(nome):
    if pd.isna(nome): return "NÃO IDENTIFICADO"
    n = normalize_name(nome).replace('POT', '').strip()
    if any(x in n for x in ['DEFESA', 'CIVIL']): return 'DEFESA CIVIL'
    if 'ZELADOR' in n: return 'ZELADORIA'
    if 'AGRI' in n or 'HORTA' in n: return 'AGRICULTURA'
    return n

# --- PARSERS BANCO DO BRASIL ---

def parse_bb_resumo(file_obj):
    """Lê arquivo Resumo_CREDITO (Multilinhas)"""
    content = file_obj.getvalue().decode('latin-1', errors='ignore')
    lines = content.split('\n')
    data = []
    current_card = None
    curr_val = 0.0
    curr_name = ""
    
    reg_main = re.compile(r'^\s*(\d{6})\s+(\d+\.\d{2})\s+(.+)$')
    reg_sec = re.compile(r'^\s+\d{2}\s+(\d{4})\s+') # Captura Agência

    for line in lines:
        line = line.strip()
        if not line: continue
        
        m1 = reg_main.match(line)
        if m1:
            current_card, v, n = m1.groups()
            curr_val = float(v)
            curr_name = n.strip()
            continue
            
        if current_card:
            m2 = reg_sec.match(line)
            if m2:
                agencia = m2.group(1)
                data.append({'num_cartao': current_card, 'valor_pagto': curr_val, 'nome': curr_name, 'agencia': agencia, 'lote_pagto': '', 'arquivo_origem': file_obj.name})
                current_card = None
    return pd.DataFrame(data)

def parse_bb_cadastro(file_obj):
    """Lê arquivo REL.CADASTRO (Lote no final)"""
    content = file_obj.getvalue().decode('latin-1', errors='ignore')
    lines = content.split('\n')
    data = []
    
    for line in lines:
        if len(line) < 40 or "Projeto" in line: continue
        # Cartão (6 dig)
        match = re.search(r'\s(\d{6})\s+([A-Z\s\.]+?)\s+\d', line)
        if match:
            cartao, nome = match.groups()
            # Lote e Agencia (numeros no fim da linha)
            nums = re.findall(r'\b\d{4}\b', line)
            lote = nums[-1] if nums else ''
            agencia = nums[-2] if len(nums) >= 2 else ''
            
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
    
    for c in ['programa', 'nome', 'cpf', 'num_cartao', 'valor_pagto', 'lote_pagto', 'agencia']:
        if c not in df.columns: df[c] = None
        
    df['arquivo_origem'] = filename
    if df['programa'].isnull().all(): df['programa'] = filename.split('.')[0]
    df['programa'] = df['programa'].apply(padronizar_nome_projeto)
    
    def clean_val(x):
        try: return float(str(x).replace('R$', '').replace('.', '').replace(',', '.'))
        except: return 0.0
    if 'valor_pagto' in df.columns: df['valor_pagto'] = df['valor_pagto'].apply(clean_val)
    
    for c in ['cpf', 'num_cartao']:
        if c in df.columns: df[c] = df[c].astype(str).str.replace(r'\D', '', regex=True)
        
    return df

# ===========================================
# 4. APLICAÇÃO
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
    
    # MENU ATUALIZADO
    menu = st.sidebar.radio("Navegação", [
        "Dashboard", 
        "Upload de Pagamentos e Abertura de Contas", 
        "Análise e Correção", 
        "Conferência BB", 
        "Relatórios"
    ])
    
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
            k1.metric("Total Pago", f"R$ {df_clean['valor_pagto'].sum():,.2f}")
            k2.metric("Beneficiários", df_clean['nome'].nunique())
            k3.metric("Projetos", df_clean['programa'].nunique())
            st.markdown("---")
            if not df_clean.empty:
                grp = df_clean.groupby('programa')['valor_pagto'].sum().reset_index().sort_values('valor_pagto', ascending=True)
                fig = px.bar(grp, x='valor_pagto', y='programa', orientation='h', text_auto='.2s', title="Totais por Projeto")
                fig.update_layout(height=max(400, len(grp)*45))
                st.plotly_chart(fig, use_container_width=True)
                st.dataframe(grp.sort_values('valor_pagto', ascending=False).style.format({'valor_pagto': 'R$ {:,.2f}'}), use_container_width=True)
            else: st.warning("Sem dados válidos.")
        else: st.info("Sem dados.")

    # --- UPLOAD RENOMEADO E COM AVISOS ---
    elif menu == "Upload de Pagamentos e Abertura de Contas":
        st.subheader("📂 Upload de Pagamentos e Abertura de Contas")
        files = st.file_uploader("Arquivos (CSV/Excel/TXT)", accept_multiple_files=True)
        if files and st.button("Processar Arquivos"):
            dfs = []
            # Verifica existentes no banco
            try: existing_files = pd.read_sql("SELECT DISTINCT arquivo_origem FROM payments", eng)['arquivo_origem'].tolist()
            except: existing_files = []
            
            for f in files:
                if f.name in existing_files:
                    st.warning(f"⚠️ O arquivo '{f.name}' já foi enviado anteriormente. Ignorado.")
                    continue
                try:
                    if f.name.endswith('.csv'): d = pd.read_csv(f, sep=';', encoding='latin1', dtype=str)
                    elif f.name.endswith('.xlsx'): d = pd.read_excel(f, dtype=str)
                    else: d = pd.DataFrame() # Ignora TXT aqui se for de banco
                    
                    if not d.empty: 
                        d = standardize_dataframe(d, f.name)
                        dfs.append(d)
                except: st.error(f"Erro: {f.name}")
            
            if dfs:
                final = pd.concat(dfs, ignore_index=True)
                final.to_sql('payments', eng, if_exists='append', index=False, method='multi', chunksize=500)
                st.success("✅ Arquivos processados!"); st.rerun()

    # --- ANÁLISE (BUSCA COMPLETA) ---
    elif menu == "Análise e Correção":
        st.subheader("🔍 Auditoria e Correção")
        c1, c2, c3, c4 = st.columns(4)
        q_geral = c1.text_input("Nome/CPF/Cartão/RG")
        q_lote = c2.text_input("Filtrar Lote")
        q_ag = c3.text_input("Filtrar Agência")
        
        if not df_raw.empty:
            df_view = df_raw.copy()
            if q_geral:
                t = q_geral.upper()
                df_view = df_view[df_view['nome'].str.upper().str.contains(t, na=False) | df_view['cpf'].str.contains(t, na=False) | df_view['num_cartao'].str.contains(t, na=False)]
            if q_lote: df_view = df_view[df_view['lote_pagto'].astype(str).str.contains(q_lote, na=False)]
            if q_ag: df_view = df_view[df_view['agencia'].astype(str).str.contains(q_ag, na=False)]
            
            st.info(f"{len(df_view)} registros encontrados.")
            event = st.dataframe(df_view, use_container_width=True, hide_index=True, selection_mode="multi-row", on_select="rerun")
            
            if event.selection.rows:
                sel = df_view.iloc[event.selection.rows]
                st.download_button("📥 CSV Seleção", sel.to_csv(index=False).encode('utf-8'), "selecao.csv")
                if u['role'] in ['admin_ti', 'admin_equipe']:
                    with st.expander("✏️ Editar Selecionados"):
                        ed = st.data_editor(sel, hide_index=True)
                        if st.button("Salvar"):
                            with eng.begin() as conn:
                                for i, r in ed.iterrows():
                                    conn.execute(text("UPDATE payments SET nome=:n, cpf=:c, lote_pagto=:l WHERE id=:id"), 
                                                 {"n":r['nome'], "c":r['cpf'], "l":r['lote_pagto'], "id":r['id']})
                            st.success("Salvo!"); st.rerun()

    # --- CONFERÊNCIA BB (CORRIGIDA E PERSISTENTE) ---
    elif menu == "Conferência BB":
        st.subheader("🏦 Conferência Bancária (Histórico e Novos)")
        
        t1, t2 = st.tabs(["Nova Conferência (Upload)", "Histórico de Arquivos e Divergências"])
        
        with t1:
            f_bb = st.file_uploader("Arquivo TXT do Banco", type=['txt'])
            if f_bb and st.button("Processar e Salvar"):
                # 1. Verifica Duplicidade no banco de IMPORTAÇÕES
                try: exist_bb = pd.read_sql("SELECT DISTINCT arquivo_origem FROM bank_imports", eng)['arquivo_origem'].tolist()
                except: exist_bb = []
                
                if f_bb.name in exist_bb:
                    st.error(f"❌ O arquivo '{f_bb.name}' JÁ FOI PROCESSADO anteriormente.")
                else:
                    # 2. Parseia e Salva
                    df_bb = parse_bb_resumo(f_bb) if "Resumo" in f_bb.name else parse_bb_cadastro(f_bb)
                    
                    if not df_bb.empty:
                        # Normaliza colunas para salvar na tabela bank_imports
                        db_save = df_bb.rename(columns={'nome': 'nome_bb', 'valor_pagto': 'valor_bb', 'lote_pagto': 'lote'})
                        # Garante colunas
                        for c in ['num_cartao', 'nome_bb', 'valor_bb', 'agencia', 'lote', 'arquivo_origem']:
                            if c not in db_save.columns: db_save[c] = None
                        
                        # SALVA O HISTÓRICO DO ARQUIVO
                        db_save.to_sql('bank_imports', eng, if_exists='append', index=False, method='multi', chunksize=500)
                        
                        # 3. Roda a Comparação
                        if not df_raw.empty:
                            df_bb['k'] = df_bb['num_cartao'].str.strip().str.lstrip('0')
                            df_raw['k'] = df_raw['num_cartao'].astype(str).str.strip().str.replace(r'\.0$','').str.lstrip('0')
                            
                            merged = pd.merge(df_raw, df_bb, on='k', suffixes=('_sis', '_bb'))
                            divs = []
                            
                            prog = st.progress(0)
                            for i, r in merged.iterrows():
                                prog.progress((i+1)/len(merged))
                                if not nomes_sao_similares(r['nome_sis'], r.get('nome', r.get('nome_bb'))):
                                    divs.append({
                                        'cartao': r['k'], 'nome_sis': r['nome_sis'], 'nome_bb': r.get('nome', r.get('nome_bb')),
                                        'lote': r.get('lote_pagto_bb', ''), 'agencia': r.get('agencia_bb', ''),
                                        'divergencia': 'NOME', 'arquivo_origem': f_bb.name
                                    })
                            prog.empty()
                            
                            if divs:
                                pd.DataFrame(divs).to_sql('bank_discrepancies', eng, if_exists='append', index=False)
                                st.error(f"{len(divs)} Divergências encontradas e salvas.")
                            else:
                                st.success("✅ Arquivo Salvo! Nenhuma divergência encontrada.")
                        else:
                            st.warning("Arquivo salvo, mas base do sistema está vazia para comparação.")
                            
        with t2:
            st.markdown("#### 🔎 Pesquisar no Histórico do Banco")
            
            # Busca nas Importações (O que o banco mandou)
            c1, c2, c3 = st.columns(3)
            q_nome_bb = c1.text_input("Nome no Banco")
            q_lote_bb = c2.text_input("Lote Banco")
            q_ag_bb = c3.text_input("Agência Banco")
            
            if q_nome_bb or q_lote_bb or q_ag_bb:
                query = "SELECT * FROM bank_imports WHERE 1=1"
                params = {}
                if q_nome_bb: 
                    query += " AND nome_bb ILIKE :n"
                    params['n'] = f"%{q_nome_bb}%"
                if q_lote_bb: 
                    query += " AND lote ILIKE :l"
                    params['l'] = f"%{q_lote_bb}%"
                if q_ag_bb:
                    query += " AND agencia ILIKE :a"
                    params['a'] = f"%{q_ag_bb}%"
                
                res_bb = pd.read_sql(text(query), eng, params=params)
                st.dataframe(res_bb, use_container_width=True)
            
            st.markdown("---")
            st.markdown("#### 🚨 Histórico de Divergências")
            try: h = pd.read_sql("SELECT * FROM bank_discrepancies", eng)
            except: h = pd.DataFrame()
            
            if not h.empty:
                st.dataframe(h, use_container_width=True)
                if st.button("Limpar Divergências"):
                    run_db_command("DELETE FROM bank_discrepancies"); st.rerun()

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
