import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, text
import hashlib
import io
import re
import unicodedata
import os
import tempfile
from datetime import datetime
import difflib  # Biblioteca nativa para comparar similaridade de texto

# --- IMPORTAÇÕES OPCIONAIS ---
try:
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

try:
    from fpdf import FPDF
except ImportError:
    FPDF = None

# ===========================================
# 1. CONFIGURAÇÃO E ESTILOS
# ===========================================
st.set_page_config(
    page_title="SMDET - Gestão POT",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .header-container { text-align: center; padding-bottom: 20px; border-bottom: 2px solid #ddd; margin-bottom: 30px; }
    .header-secretaria { color: #555; font-size: 1rem; margin-bottom: 5px; font-weight: 500; }
    .header-programa { color: #1E3A8A; font-size: 1.5rem; font-weight: bold; margin-bottom: 5px; }
    .header-sistema { color: #2563EB; font-size: 1.8rem; font-weight: bold; }
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
        with eng.begin() as conn:
            conn.execute(text(sql), params or {})

def init_db():
    eng = get_db_engine()
    if not eng: return
    with eng.connect() as conn:
        conn.execute(text('''CREATE TABLE IF NOT EXISTS users (email TEXT PRIMARY KEY, password TEXT, role TEXT, name TEXT, first_login INTEGER DEFAULT 1)'''))
        conn.execute(text('''CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY, 
            programa TEXT, 
            gerenciadora TEXT, 
            num_cartao TEXT, 
            nome TEXT, 
            cpf TEXT, 
            rg TEXT, 
            valor_pagto REAL, 
            data_pagto TEXT, 
            qtd_dias INTEGER, 
            mes_ref TEXT, 
            ano_ref TEXT, 
            arquivo_origem TEXT, 
            linha_arquivo INTEGER, 
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )'''))
        conn.execute(text('''CREATE TABLE IF NOT EXISTS bank_discrepancies (id SERIAL PRIMARY KEY, cartao TEXT, nome_sis TEXT, nome_bb TEXT, cpf_sis TEXT, cpf_bb TEXT, divergencia TEXT, arquivo_origem TEXT, tipo_erro TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)'''))
        conn.execute(text('''CREATE TABLE IF NOT EXISTS audit_logs (id SERIAL PRIMARY KEY, user_email TEXT, action TEXT, details TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)'''))
        conn.commit()
        
        res = conn.execute(text("SELECT email FROM users WHERE email=:e"), {"e": 'admin@prefeitura.sp.gov.br'}).fetchone()
        if not res:
            h = hashlib.sha256('smdet2025'.encode()).hexdigest()
            conn.execute(text("INSERT INTO users VALUES (:e, :p, :r, :n, :f)"), 
                         {"e": 'admin@prefeitura.sp.gov.br', "p": h, "r": 'admin_ti', "n": 'Admin TI', "f": 0})
            conn.commit()

def log_action(email, action, details):
    run_db_command("INSERT INTO audit_logs (user_email, action, details) VALUES (:e, :a, :d)", 
                   {"e": email, "a": action, "d": details})

# ===========================================
# 3. TRATAMENTO INTELIGENTE DE DADOS
# ===========================================

def sanitize_text(text):
    if not isinstance(text, str): return str(text)
    return text.encode('latin-1', 'replace').decode('latin-1')

def normalize_name(name):
    """Remove acentos, espaços extras e converte para maiúsculo."""
    if not name or str(name).lower() in ['nan', 'none', '']: return ""
    s = str(name)
    # Tenta corrigir encoding comum de arquivos de banco (cp850/latin1 misturado)
    try:
        s = s.encode('cp1252').decode('utf-8') 
    except: pass
    
    nfkd = unicodedata.normalize('NFKD', s)
    ascii_only = "".join([c for c in nfkd if not unicodedata.combining(c)])
    return " ".join(ascii_only.upper().split())

def nomes_sao_similares(nome1, nome2, limite=0.75):
    """
    Compara dois nomes ignorando preposições e tolerando pequenas diferenças.
    Retorna True se forem considerados a mesma pessoa.
    """
    n1 = normalize_name(nome1)
    n2 = normalize_name(nome2)
    
    # 1. Igualdade exata após normalização
    if n1 == n2: return True
    
    # 2. Remover preposições (DE, DA, DOS, E...)
    stops = [' DE ', ' DA ', ' DO ', ' DOS ', ' DAS ', ' E ']
    for s in stops:
        n1 = n1.replace(s, ' ')
        n2 = n2.replace(s, ' ')
    
    # 3. Comparação por Similaridade (SequenceMatcher)
    # Isso resolve "ADRIANA" vs "ADRIANS" (Typo)
    ratio = difflib.SequenceMatcher(None, n1, n2).ratio()
    if ratio > limite:
        return True
        
    # 4. Verificação de Abreviações (Mauricio -> M)
    # Se todas as palavras de um nome curto estiverem contidas no nome longo (iniciais)
    parts1 = n1.split()
    parts2 = n2.split()
    
    if len(parts1) == len(parts2):
        match_count = 0
        for p1, p2 in zip(parts1, parts2):
            # Se for igual ou se um for abreviação do outro (M == MAURICIO)
            if p1 == p2 or (len(p1) == 1 and p2.startswith(p1)) or (len(p2) == 1 and p1.startswith(p2)):
                match_count += 1
        
        if match_count == len(parts1):
            return True

    return False

def padronizar_nome_projeto(nome_original):
    if pd.isna(nome_original) or str(nome_original).strip() == '': return "NÃO IDENTIFICADO"
    nome = normalize_name(nome_original)
    nome = re.sub(r'^POT\s?', '', nome).strip()
    
    if any(x in nome for x in ['DEFESA', 'CIVIL', 'CICIL']): return 'DEFESA CIVIL'
    elif any(x in nome for x in ['ZELADOR', 'ZELADORIA']): return 'ZELADORIA'
    elif any(x in nome for x in ['AGRI', 'HORTA']): return 'AGRICULTURA'
    elif any(x in nome for x in ['ADM', 'ADMINISTRATIVO']): return 'ADM'
    elif any(x in nome for x in ['PARQUE']): return 'PARQUES'
    elif any(x in nome for x in ['REDENCAO', 'REDENÇÃO']): return 'REDENÇÃO'
    elif any(x in nome for x in ['VIVARURAL', 'VIVA']): return 'VIVA RURAL'
    return nome

def standardize_dataframe(df, filename):
    df.columns = [str(c).strip() for c in df.columns]
    mapa = {
        'projeto': 'programa', 'programa': 'programa', 'eixo': 'programa', 'acao': 'programa',
        'valor': 'valor_pagto', 'liquido': 'valor_pagto', 'pagto': 'valor_pagto',
        'nome': 'nome', 'beneficiario': 'nome',
        'cpf': 'cpf', 'rg': 'rg',
        'cartao': 'num_cartao', 'codigo': 'num_cartao',
        'gerenciadora': 'gerenciadora', 'parceiro': 'gerenciadora', 'entidade': 'gerenciadora'
    }
    cols_new = {}
    for col in df.columns:
        c_low = col.lower()
        match = mapa.get(c_low) or next((v for k, v in mapa.items() if k in c_low), None)
        if match: cols_new[col] = match
    
    df = df.rename(columns=cols_new)
    essential = ['programa', 'gerenciadora', 'num_cartao', 'nome', 'cpf', 'rg', 'valor_pagto', 'arquivo_origem', 'linha_arquivo']
    for c in essential: 
        if c not in df.columns: df[c] = None

    if df['programa'].isnull().all(): df['programa'] = filename.split('.')[0]
    df['programa'] = df['programa'].apply(padronizar_nome_projeto)
    df['arquivo_origem'] = filename
    df['linha_arquivo'] = df.index + 2
    
    def clean_money(x):
        if isinstance(x, str):
            x = x.replace('R$', '').replace(' ', '')
            if ',' in x and '.' in x: x = x.replace('.', '').replace(',', '.') 
            elif ',' in x: x = x.replace(',', '.') 
        try: return float(x)
        except: return 0.0
    
    if 'valor_pagto' in df.columns: df['valor_pagto'] = df['valor_pagto'].apply(clean_money)
    if 'cpf' in df.columns: df['cpf'] = df['cpf'].astype(str).str.replace(r'\D', '', regex=True)
    if 'num_cartao' in df.columns: df['num_cartao'] = df['num_cartao'].astype(str).str.replace(r'\.0$', '', regex=True)
    return df[essential]

def detect_inconsistencies(df):
    if df is None or df.empty: return pd.DataFrame()
    errs = []
    df['cpf_c'] = df['cpf'].fillna('').astype(str).str.replace(r'\D', '', regex=True)
    for i, r in df.iterrows():
        if len(r['cpf_c']) < 5: 
            errs.append({'ID': r.get('id'), 'NOME': r.get('nome'), 'ERRO': 'CPF AUSENTE/INVÁLIDO', 'ARQUIVO': r.get('arquivo_origem')})
    return pd.DataFrame(errs)

def parse_bb_txt(file):
    try:
        # Layout estimado BB. Se tiver Lote/Agencia em posições fixas, ajustar aqui.
        # Adicionei campos genéricos para Lote/Agencia caso estejam no header ou em colunas extras
        # Nota: Sem o manual exato, estamos lendo colunas chave. 
        colspecs = [(0, 11), (11, 42), (42, 52), (52, 92), (92, 104), (104, 119)]
        names = ['tipo','projeto','cartao','nome','rg','cpf']
        
        df = pd.read_fwf(file, colspecs=colspecs, names=names, dtype=str, encoding='latin1')
        
        # Filtra apenas linhas de dados (Tipo 1)
        df = df[df['tipo'] == '1'].copy()
        
        # Cria colunas vazias para busca futura se o layout mudar
        df['lote'] = 'N/A'
        df['agencia'] = 'N/A'
        
        return df
    except: return pd.DataFrame()

# ===========================================
# 4. PDF
# ===========================================
def generate_pdf_report(df_filt, titulo="Relatório"):
    if FPDF is None: return None
    pdf = FPDF(); pdf.add_page(orientation='L'); pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, sanitize_text("SMDET - Sistema POT"), 0, 1, 'C')
    pdf.set_font("Arial", 'B', 12); pdf.cell(0, 10, sanitize_text(titulo), 0, 1, 'C')
    
    total = df_filt['valor_pagto'].sum() if 'valor_pagto' in df_filt.columns else 0
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 10, f"Registros: {len(df_filt)} | Total: R$ {total:,.2f}", 0, 1)
    
    pdf.set_font("Arial", 'B', 8); pdf.set_fill_color(240,240,240)
    w = [90, 35, 35, 30, 80]
    h = ["NOME", "CPF", "CARTAO", "VALOR", "PROJETO"]
    for i, head in enumerate(h): pdf.cell(w[i], 8, sanitize_text(head), 1, 0, 'C', True)
    pdf.ln()
    
    pdf.set_font("Arial", '', 8)
    for _, r in df_filt.head(500).iterrows():
        d = [str(r.get('nome',''))[:40], str(r.get('cpf','')), str(r.get('num_cartao','')), f"{float(r.get('valor_pagto',0)):.2f}", str(r.get('programa',''))[:40]]
        for i, val in enumerate(d): pdf.cell(w[i], 8, sanitize_text(val), 1, 0, 'L')
        pdf.ln()
    return pdf.output(dest='S').encode('latin-1', 'replace')

# ===========================================
# 5. APP
# ===========================================

def login_screen():
    render_header()
    c1,c2,c3 = st.columns([1,2,1])
    with c2:
        st.markdown("### Acesso Restrito")
        with st.form("login"):
            e = st.text_input("Email"); p = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar"):
                eng = get_db_engine()
                if not eng: st.error("Erro Conexão"); return
                with eng.connect() as conn:
                    res = conn.execute(text("SELECT * FROM users WHERE email=:e"), {"e": e}).fetchone()
                    if res and res.password == hashlib.sha256(p.encode()).hexdigest():
                        st.session_state['logged_in'] = True
                        st.session_state['u'] = {'email':res.email, 'role':res.role, 'name':res.name}
                        st.rerun()
                    else: st.error("Acesso Negado")

def app():
    u = st.session_state['u']
    st.sidebar.markdown(f"### Olá, {u['name']}")
    menu_options = ["Dashboard", "Upload", "Análise e Correção", "Conferência BB", "Relatórios", "Gestão de Dados", "Manuais"]
    if u['role'] in ['admin_ti', 'admin_equipe']: menu_options.insert(6, "Gestão de Equipe")
    if u['role'] == 'admin_ti': menu_options.append("Admin TI (Logs)")
    op = st.sidebar.radio("Menu", menu_options)
    if st.sidebar.button("Sair"): st.session_state.clear(); st.rerun()
    
    eng = get_db_engine()
    df_raw = pd.DataFrame()
    if eng:
        try: df_raw = pd.read_sql("SELECT * FROM payments", eng)
        except: pass
    render_header()

    # --- DASHBOARD ---
    if op == "Dashboard":
        st.markdown("### 📊 Visão Geral")
        if not df_raw.empty:
            df_raw['valor_pagto'] = pd.to_numeric(df_raw['valor_pagto'], errors='coerce').fillna(0.0)
            mask_valid = ((df_raw['valor_pagto'] > 0.01) & (df_raw['programa'].notna()) & (df_raw['programa'] != '') & (~df_raw['programa'].astype(str).str.isnumeric()))
            df_clean = df_raw[mask_valid].copy()
            
            k1,k2,k3,k4 = st.columns(4)
            k1.metric("Total Pago (Válido)", f"R$ {df_clean['valor_pagto'].sum():,.2f}")
            k2.metric("Beneficiários", df_clean['cpf'].nunique())
            k3.metric("Projetos", df_clean['programa'].nunique())
            k4.metric("Registros", len(df_clean))
            st.markdown("---")
            
            st.subheader("Total de Repasses por Projeto")
            if not df_clean.empty:
                df_clean['programa'] = df_clean['programa'].apply(padronizar_nome_projeto)
                grp = df_clean.groupby('programa')['valor_pagto'].sum().reset_index().sort_values('valor_pagto', ascending=True)
                fig = px.bar(grp, x='valor_pagto', y='programa', orientation='h', text_auto='.2s', title="Valores Pagos por Projeto")
                fig.update_traces(texttemplate='R$ %{x:,.2f}', textposition='outside')
                fig.update_layout(xaxis_title="Valor (R$)", yaxis_title="Projeto", height=max(400, len(grp)*50), margin=dict(l=150))
                st.plotly_chart(fig, use_container_width=True)
                
                st.markdown("### 📋 Detalhamento")
                st.dataframe(grp.sort_values('valor_pagto', ascending=False).style.format({'valor_pagto': 'R$ {:,.2f}'}), use_container_width=True)
                st.markdown("---")
                g2 = df_clean.groupby('gerenciadora')['valor_pagto'].sum().reset_index()
                st.plotly_chart(px.pie(g2, values='valor_pagto', names='gerenciadora', title="Por Gerenciadora"), use_container_width=True)
            else: st.warning("Sem dados válidos.")
        else: st.info("Sem dados.")

    # --- UPLOAD ---
    elif op == "Upload":
        st.markdown("### 📂 Upload")
        files = st.file_uploader("CSV/Excel", accept_multiple_files=True)
        if files and st.button("Processar"):
            dfs = []
            exist = df_raw['arquivo_origem'].unique().tolist() if not df_raw.empty else []
            for f in files:
                if f.name in exist: st.warning(f"{f.name} já existe."); continue
                try:
                    d = pd.read_csv(f, sep=';', dtype=str, encoding='latin1') if f.name.endswith('.csv') else pd.read_excel(f, dtype=str)
                    d = standardize_dataframe(d, f.name)
                    dfs.append(d)
                except Exception as e: st.error(f"Erro {f.name}: {e}")
            if dfs:
                final = pd.concat(dfs)
                final.to_sql('payments', eng, if_exists='append', index=False, method='multi', chunksize=500)
                st.success("Sucesso!"); log_action(u['email'], "UPLOAD", f"{len(final)} regs"); st.rerun()

    # --- ANÁLISE ---
    elif op == "Análise e Correção":
        st.markdown("### 🔍 Busca e Auditoria")
        q = st.text_input("🔎 Buscar Beneficiário (Nome, CPF, Cartão, RG):")
        if not df_raw.empty:
            df_disp = df_raw.copy()
            if q:
                mask = df_disp.apply(lambda x: x.astype(str).str.contains(q, case=False, na=False)).any(axis=1)
                df_disp = df_disp[mask]
            
            event = st.dataframe(df_disp, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="multi-row")
            if event.selection.rows:
                sel = df_disp.iloc[event.selection.rows]
                st.success(f"{len(sel)} selecionados.")
                c1,c2 = st.columns(2)
                pdf = generate_pdf_report(sel, "Auditoria")
                if pdf: c1.download_button("📄 PDF", pdf, "audit.pdf")
                c2.download_button("📊 CSV", sel.to_csv(index=False).encode('utf-8'), "audit.csv")
                
                if u['role'] in ['admin_ti', 'admin_equipe']:
                    with st.expander("✏️ Editar Selecionados"):
                        ed = st.data_editor(sel, hide_index=True)
                        if st.button("Salvar Edição"):
                            with eng.begin() as conn:
                                for i, r in ed.iterrows():
                                    p_corr = padronizar_nome_projeto(r['programa'])
                                    conn.execute(text("UPDATE payments SET nome=:n, cpf=:c, num_cartao=:nc, valor_pagto=:v, programa=:p WHERE id=:id"),
                                                 {"n":r['nome'], "c":r['cpf'], "nc":r['num_cartao'], "v":r['valor_pagto'], "p":p_corr, "id":r['id']})
                            st.success("Salvo!"); st.rerun()

    # --- CONFERÊNCIA BB (MELHORADA) ---
    elif op == "Conferência BB":
        st.markdown("### 🏦 Conferência Bancária Inteligente")
        t1, t2 = st.tabs(["Processar Retorno", "Histórico Divergências"])
        
        with t1:
            st.info("O sistema agora ignora diferenças de caixa alta, abreviações (M vs MAURICIO) e preposições (DE, DA).")
            fbb = st.file_uploader("Arquivo TXT Banco", accept_multiple_files=True)
            if fbb and st.button("Processar Comparação"):
                dfs = []
                for f in fbb:
                    d = parse_bb_txt(f); d['arquivo_origem'] = f.name; dfs.append(d)
                
                if dfs:
                    bb = pd.concat(dfs)
                    sis = df_raw[['num_cartao','nome','cpf']].copy()
                    sis['k'] = sis['num_cartao'].astype(str).str.replace(r'\.0$','', regex=True)
                    bb['k'] = bb['cartao'].astype(str).str.replace(r'^0+','', regex=True)
                    
                    merged = pd.merge(sis, bb, on='k', suffixes=('_sis', '_bb'))
                    divs = []
                    
                    with st.spinner("Analisando similaridade de nomes..."):
                        for i, r in merged.iterrows():
                            # USA A NOVA FUNÇÃO DE SIMILARIDADE
                            if not nomes_sao_similares(r['nome_sis'], r['nome_bb']):
                                divs.append({
                                    'cartao':r['k'], 
                                    'nome_sis':r['nome_sis'], 
                                    'nome_bb':r['nome_bb'], 
                                    'divergencia':'NOME', 
                                    'arquivo_origem':r['arquivo_origem']
                                })
                    
                    if divs:
                        pd.DataFrame(divs).to_sql('bank_discrepancies', eng, if_exists='append', index=False)
                        st.error(f"🚨 {len(divs)} divergências reais encontradas!")
                    else: st.success("✅ Nenhuma divergência encontrada (considerando similaridades).")
        
        with t2:
            h = pd.read_sql("SELECT * FROM bank_discrepancies", eng)
            
            # --- BUSCA NO HISTÓRICO ---
            c_busca = st.columns([2, 1, 1, 1])
            q_nome = c_busca[0].text_input("Buscar Nome")
            q_cpf = c_busca[1].text_input("CPF")
            q_lote = c_busca[2].text_input("Lote") # Placeholder
            q_ag = c_busca[3].text_input("Agência") # Placeholder
            
            if not h.empty:
                if q_nome: h = h[h['nome_sis'].str.contains(q_nome, case=False) | h['nome_bb'].str.contains(q_nome, case=False)]
                if q_cpf: h = h[h['cpf_sis'].astype(str).str.contains(q_cpf) | h['cpf_bb'].astype(str).str.contains(q_cpf)]
                # Filtros de Lote/Agencia funcionariam se as colunas existissem preenchidas no DB
                
                st.dataframe(h, use_container_width=True)
                if st.button("Limpar Histórico"):
                    run_db_command("DELETE FROM bank_discrepancies"); st.rerun()
            else: st.info("Histórico vazio.")

    # --- GESTÃO DE DADOS ---
    elif op == "Gestão de Dados":
        st.markdown("### 🗄️ Gestão de Arquivos")
        if not df_raw.empty:
            resumo = df_raw.groupby('arquivo_origem').size().reset_index(name='qtd')
            st.dataframe(resumo)
            fdel = st.selectbox("Excluir:", resumo['arquivo_origem'].unique())
            if st.button("🗑️ Excluir"):
                run_db_command("DELETE FROM payments WHERE arquivo_origem = :f", {"f": fdel})
                log_action(u['email'], "DEL_FILE", f"Excluiu {fdel}"); st.rerun()

    # --- GESTÃO DE EQUIPE ---
    elif op == "Gestão de Equipe":
        st.markdown("### 👥 Usuários")
        with st.form("nu"):
            ne = st.text_input("Email"); nn = st.text_input("Nome"); nr = st.selectbox("Perfil", ["user", "admin_equipe"])
            if st.form_submit_button("Criar"):
                try:
                    hp = hashlib.sha256('123456'.encode()).hexdigest()
                    run_db_command("INSERT INTO users VALUES (:e, :p, :r, :n, 1)", {"e":ne, "p":hp, "r":nr, "n":nn})
                    st.success("Criado!")
                except: st.error("Erro")
        st.dataframe(pd.read_sql("SELECT email, name, role FROM users", eng))

    # --- RELATÓRIOS ---
    elif op == "Relatórios":
        st.markdown("### 📥 Exportação")
        if not df_raw.empty:
            proj = st.multiselect("Filtrar Projeto", df_raw['programa'].unique())
            dff = df_raw[df_raw['programa'].isin(proj)] if proj else df_raw
            c1, c2 = st.columns(2)
            c1.download_button("CSV", dff.to_csv(index=False).encode('utf-8'), "dados.csv")
            pdf = generate_pdf_report(dff)
            if pdf: c2.download_button("PDF", pdf, "relatorio.pdf")

    # --- MANUAIS ---
    elif op == "Manuais":
        st.markdown("### 📚 Manuais")
        t1, t2 = st.tabs(["Usuário", "Admin"])
        t1.markdown("""**Conferência Bancária:** O sistema agora aceita abreviações e pequenas diferenças (ex: 'De Souza' = 'D Souza').""")
        t2.markdown("### Admin\nGestão completa do sistema.")

    # --- LOGS ---
    elif op == "Admin TI (Logs)":
        st.markdown("### 🛡️ Logs")
        st.dataframe(pd.read_sql("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT 200", eng))

if __name__ == "__main__":
    init_db()
    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
    if st.session_state['logged_in']: app()
    else: login_screen()
