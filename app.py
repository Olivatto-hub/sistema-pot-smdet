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
        # Tabela com campos de Lote e Agência para busca
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
            lote_pagto TEXT,
            agencia TEXT,
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
# 3. TRATAMENTO INTELIGENTE DE DADOS (FUZZY)
# ===========================================

def normalize_name(name):
    if not name or str(name).lower() in ['nan', 'none', '']: return ""
    s = str(name)
    # Correção manual de codificações comuns em arquivos de banco
    s = s.replace('‡Æo', 'CAO').replace('‡ÆO', 'CAO').replace('Ã£', 'A').replace('Ã§', 'C')
    try: s = s.encode('cp1252').decode('utf-8') 
    except: pass
    
    nfkd = unicodedata.normalize('NFKD', s)
    ascii_only = "".join([c for c in nfkd if not unicodedata.combining(c)])
    return " ".join(ascii_only.upper().split())

def is_abbreviation(part1, part2):
    # Verifica se uma parte é abreviação da outra (ex: M vs MAURICIO)
    if len(part1) == 1 and part2.startswith(part1): return True
    if len(part2) == 1 and part1.startswith(part2): return True
    return False

def nomes_sao_similares(n1, n2, threshold=0.80):
    """
    Compara nomes ignorando erros comuns, abreviações e preposições.
    Retorna True se forem a mesma pessoa.
    """
    s1 = normalize_name(n1)
    s2 = normalize_name(n2)
    
    if s1 == s2: return True
    
    # Remove preposições
    stops = [' DE ', ' DA ', ' DO ', ' DOS ', ' DAS ', ' E ']
    for stop in stops:
        s1 = s1.replace(stop, ' ')
        s2 = s2.replace(stop, ' ')
    
    # Remove espaços duplicados
    s1 = " ".join(s1.split())
    s2 = " ".join(s2.split())
    
    if s1 == s2: return True
    
    # Comparação palavra por palavra (para pegar abreviações e typos)
    parts1 = s1.split()
    parts2 = s2.split()
    
    if len(parts1) == len(parts2):
        match = True
        for p1, p2 in zip(parts1, parts2):
            # Se não for igual, não for abreviação e a similaridade for baixa -> Diferente
            if p1 != p2 and not is_abbreviation(p1, p2):
                if difflib.SequenceMatcher(None, p1, p2).ratio() < 0.85:
                    match = False
                    break
        if match: return True

    # Comparação Fuzzy Geral (para nomes colados ou com muitas diferenças pequenas)
    return difflib.SequenceMatcher(None, s1, s2).ratio() > threshold

def padronizar_nome_projeto(nome_original):
    if pd.isna(nome_original): return "NÃO IDENTIFICADO"
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

# --- PARSERS DE ARQUIVOS ---

def standardize_dataframe(df, filename):
    df.columns = [str(c).strip() for c in df.columns]
    mapa = {
        'projeto': 'programa', 'programa': 'programa', 'eixo': 'programa', 'acao': 'programa',
        'valor': 'valor_pagto', 'liquido': 'valor_pagto', 'pagto': 'valor_pagto',
        'nome': 'nome', 'beneficiario': 'nome',
        'cpf': 'cpf', 'rg': 'rg',
        'cartao': 'num_cartao', 'codigo': 'num_cartao',
        'gerenciadora': 'gerenciadora', 'lote': 'lote_pagto', 'agencia': 'agencia'
    }
    cols_new = {}
    for col in df.columns:
        c_low = col.lower()
        match = mapa.get(c_low) or next((v for k, v in mapa.items() if k in c_low), None)
        if match: cols_new[col] = match
    
    df = df.rename(columns=cols_new)
    
    # Garante colunas
    for c in ['programa', 'num_cartao', 'nome', 'cpf', 'rg', 'valor_pagto', 'lote_pagto', 'agencia']:
        if c not in df.columns: df[c] = None

    if df['programa'].isnull().all(): df['programa'] = filename.split('.')[0]
    df['programa'] = df['programa'].apply(padronizar_nome_projeto)
    df['arquivo_origem'] = filename
    df['linha_arquivo'] = df.index + 2
    
    # Limpeza
    def clean_money(x):
        try: return float(str(x).replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.'))
        except: return 0.0
    
    if 'valor_pagto' in df.columns: df['valor_pagto'] = df['valor_pagto'].apply(clean_money)
    for c in ['cpf', 'num_cartao']:
        if c in df.columns: df[c] = df[c].astype(str).str.replace(r'\D', '', regex=True)

    return df

def parse_bb_resumo(file_obj):
    """Lê arquivo Resumo_CREDITO que tem quebra de linha."""
    content = file_obj.getvalue().decode('latin-1', errors='ignore')
    lines = content.split('\n')
    data = []
    curr = {}
    
    # Regex: Cartão (6d) + Valor + Nome
    reg_main = re.compile(r'^(\d{6})\s+(\d+\.\d{2})\s+(.+)$')
    # Regex: Agencia (4d) na linha seguinte
    reg_sec = re.compile(r'^\s+(\d{2})\s+(\d{4})\s+')

    for line in lines:
        line = line.strip()
        m1 = reg_main.match(line)
        if m1:
            if curr: data.append(curr)
            c, v, n = m1.groups()
            curr = {'num_cartao': c, 'valor_pagto': float(v), 'nome': n.strip(), 'arquivo_origem': file_obj.name, 'programa': 'BB RESUMO'}
            continue
        m2 = reg_sec.match(line)
        if m2 and curr:
            _, ag = m2.groups()
            curr['agencia'] = ag
            data.append(curr)
            curr = {}
            
    if curr: data.append(curr)
    return pd.DataFrame(data)

def parse_bb_cadastro(file_obj):
    """Lê arquivo REL.CADASTRO com posições variadas."""
    content = file_obj.getvalue().decode('latin-1', errors='ignore')
    lines = content.split('\n')
    data = []
    
    for line in lines:
        if len(line) < 40 or "Projeto" in line: continue
        # Tenta extrair cartao (6 digitos) e nome
        # Procura sequencia de 6 digitos seguida de texto
        match = re.search(r'\s(\d{6})\s+([A-Z\s\.]+?)\s+\d', line)
        if match:
            cartao, nome = match.groups()
            # Tenta pegar Lote (4 digitos no fim) e Agencia (4 digitos antes)
            parts = line.split()
            lote = parts[-1] if len(parts[-1]) == 4 and parts[-1].isdigit() else ''
            
            # Encontrar agencia: procura numero de 4 digitos na linha
            nums = re.findall(r'\s(\d{4})\s', line)
            agencia = nums[-1] if nums else ''
            
            data.append({
                'num_cartao': cartao, 'nome': nome.strip(), 
                'lote_pagto': lote, 'agencia': agencia,
                'arquivo_origem': file_obj.name, 'programa': 'BB CADASTRO'
            })
            
    return pd.DataFrame(data)

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
    menu = st.sidebar.radio("Menu", ["Dashboard", "Upload", "Análise e Correção", "Conferência BB", "Relatórios"])
    
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
            
            # Filtro de Higiene Visual (Valores > 0 e Projetos Válidos)
            mask = (df_raw['valor_pagto'] > 0.01) & (~df_raw['programa'].astype(str).str.isnumeric())
            df_clean = df_raw[mask].copy()
            
            k1,k2,k3 = st.columns(3)
            k1.metric("Total Pago", f"R$ {df_clean['valor_pagto'].sum():,.2f}")
            k2.metric("Beneficiários", df_clean['nome'].nunique())
            k3.metric("Projetos", df_clean['programa'].nunique())
            
            st.markdown("---")
            if not df_clean.empty:
                grp = df_clean.groupby('programa')['valor_pagto'].sum().reset_index().sort_values('valor_pagto', ascending=True)
                fig = px.bar(grp, x='valor_pagto', y='programa', orientation='h', text_auto='.2s', title="Totais por Projeto")
                fig.update_layout(height=max(400, len(grp)*40))
                st.plotly_chart(fig, use_container_width=True)
            else: st.warning("Sem dados válidos para exibir.")
        else: st.info("Sem dados.")

    # --- UPLOAD ---
    elif menu == "Upload":
        st.subheader("📂 Upload de Arquivos")
        files = st.file_uploader("CSV, Excel ou TXT do Banco", accept_multiple_files=True)
        if files and st.button("Processar"):
            dfs = []
            for f in files:
                try:
                    if f.name.upper().endswith('.TXT'):
                        if "RESUMO" in f.name.upper(): d = parse_bb_resumo(f)
                        else: d = parse_bb_cadastro(f)
                    elif f.name.endswith('.csv'): d = pd.read_csv(f, sep=';', encoding='latin1', dtype=str)
                    else: d = pd.read_excel(f, dtype=str)
                    
                    if not d.empty: 
                        d = standardize_dataframe(d, f.name)
                        dfs.append(d)
                except Exception as e: st.error(f"Erro {f.name}: {e}")
            
            if dfs:
                final = pd.concat(dfs, ignore_index=True)
                final.to_sql('payments', eng, if_exists='append', index=False, method='multi', chunksize=500)
                st.success("✅ Arquivos processados!")
                st.rerun()

    # --- ANÁLISE (BUSCA AVANÇADA IMPLEMENTADA) ---
    elif menu == "Análise e Correção":
        st.subheader("🔍 Busca e Auditoria")
        
        # Filtros de Busca Solicitados
        c1, c2, c3, c4, c5 = st.columns(5)
        q_nome = c1.text_input("Nome")
        q_cpf = c2.text_input("CPF")
        q_cartao = c3.text_input("Cartão")
        q_ag = c4.text_input("Agência")
        q_lote = c5.text_input("Lote")
        
        if not df_raw.empty:
            df_view = df_raw.copy()
            if q_nome: df_view = df_view[df_view['nome'].str.contains(q_nome, case=False, na=False)]
            if q_cpf: df_view = df_view[df_view['cpf'].str.contains(q_cpf, na=False)]
            if q_cartao: df_view = df_view[df_view['num_cartao'].str.contains(q_cartao, na=False)]
            if q_ag: df_view = df_view[df_view['agencia'].astype(str).str.contains(q_ag, na=False)]
            if q_lote: df_view = df_view[df_view['lote_pagto'].astype(str).str.contains(q_lote, na=False)]
            
            st.write(f"Encontrados: {len(df_view)}")
            
            # Tabela Editável para Correções em Lote
            if not df_view.empty:
                event = st.dataframe(df_view, use_container_width=True, hide_index=True, selection_mode="multi-row", on_select="rerun")
                
                if event.selection.rows:
                    sel = df_view.iloc[event.selection.rows]
                    st.info(f"{len(sel)} selecionados para ação.")
                    
                    if u['role'] in ['admin_ti', 'admin_equipe']:
                        with st.expander("✏️ Editar Selecionados"):
                            ed = st.data_editor(sel, hide_index=True)
                            if st.button("Salvar Alterações"):
                                with eng.begin() as conn:
                                    for i, r in ed.iterrows():
                                        conn.execute(text("UPDATE payments SET nome=:n, cpf=:c, num_cartao=:nc, agencia=:a, lote_pagto=:l WHERE id=:id"),
                                                     {"n":r['nome'], "c":r['cpf'], "nc":r['num_cartao'], "a":r['agencia'], "l":r['lote_pagto'], "id":r['id']})
                                st.success("Salvo!"); st.rerun()
                    
                    # Botão para Exportar a Seleção
                    st.download_button("📥 Baixar CSV da Seleção", sel.to_csv(index=False).encode('utf-8'), "selecao.csv")

    # --- CONFERÊNCIA BB (CORRIGIDA) ---
    elif menu == "Conferência BB":
        st.subheader("🏦 Conferência Bancária (Inteligente)")
        f_bb = st.file_uploader("Arquivo TXT do Banco", type=['txt'])
        
        if f_bb:
            # Processa usando os novos parsers
            df_bb = parse_bb_resumo(f_bb) if "Resumo" in f_bb.name else parse_bb_cadastro(f_bb)
            
            if not df_bb.empty and not df_raw.empty:
                # Normaliza chaves
                df_bb['k'] = df_bb['num_cartao'].str.strip().str.lstrip('0')
                df_raw['k'] = df_raw['num_cartao'].astype(str).str.strip().str.replace(r'\.0$','').str.lstrip('0')
                
                merged = pd.merge(df_raw, df_bb, on='k', suffixes=('_sis', '_bb'))
                divs = []
                
                prog = st.progress(0)
                for i, r in merged.iterrows():
                    prog.progress((i+1)/len(merged))
                    # COMPARAÇÃO INTELIGENTE (Fuzzy)
                    if not nomes_sao_similares(r['nome_sis'], r['nome_bb']):
                        divs.append({'Cartão':r['k'], 'Nome Sistema':r['nome_sis'], 'Nome Banco':r['nome_bb'], 'Status':'DIVERGENTE'})
                prog.empty()
                
                if divs:
                    st.error(f"{len(divs)} Divergências Reais Encontradas")
                    st.dataframe(pd.DataFrame(divs), use_container_width=True)
                else:
                    st.success("✅ Nenhuma divergência encontrada (considerando similaridade de nomes).")

if __name__ == "__main__":
    init_db()
    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
    if st.session_state['logged_in']: app()
    else: login_screen()
