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

# --- AUMENTO DE LIMITE DE UPLOAD (CONFIGURAÇÃO AUTOMÁTICA) ---
# Cria a pasta .streamlit e o arquivo config.toml se não existirem
if not os.path.exists(".streamlit"):
    os.makedirs(".streamlit")
config_path = ".streamlit/config.toml"
if not os.path.exists(config_path):
    with open(config_path, "w") as f:
        f.write("[server]\nmaxUploadSize = 1024\n") # Define limite para 1GB

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
st.set_page_config(page_title="SMDET - Gestão POT", page_icon="💰", layout="wide")

st.markdown("""
<style>
    .header-container { text-align: center; padding-bottom: 20px; border-bottom: 2px solid #ddd; margin-bottom: 30px; }
    .metric-card { background-color: #f8f9fa; padding: 15px; border-radius: 10px; border-left: 5px solid #1E3A8A; }
    [data-testid="stDataFrame"] { width: 100%; }
    .stAlert { padding: 0.5rem; }
</style>
""", unsafe_allow_html=True)

def render_header():
    st.markdown("""
        <div class="header-container">
            <div style="color: #555;">Secretaria Municipal de Desenvolvimento Econômico e Trabalho (SMDET)</div>
            <div style="color: #1E3A8A; font-size: 1.5rem; font-weight: bold;">Programa Operação Trabalho (POT)</div>
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
            lote_pagto TEXT,
            agencia TEXT,
            arquivo_origem TEXT, 
            linha_arquivo INTEGER, 
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )'''))
        conn.execute(text('''CREATE TABLE IF NOT EXISTS bank_discrepancies (
            id SERIAL PRIMARY KEY, cartao TEXT, nome_sis TEXT, nome_bb TEXT, 
            lote TEXT, agencia TEXT, divergencia TEXT, arquivo_origem TEXT, 
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )'''))
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
# 3. TRATAMENTO INTELIGENTE (PARSERS & FUZZY)
# ===========================================

def normalize_name(name):
    """Limpa nomes, remove acentos e corrige codificação."""
    if not name or str(name).lower() in ['nan', 'none', '']: return ""
    s = str(name).upper()
    # Correção manual de codificações comuns
    replacements = {'‡ÆO': 'CAO', '‡Æo': 'CAO', 'Ã£': 'A', 'Ã§': 'C', 'Ã©': 'E', 'Ã¡': 'A'}
    for k, v in replacements.items(): s = s.replace(k, v)
    nfkd = unicodedata.normalize('NFKD', s)
    return " ".join("".join([c for c in nfkd if not unicodedata.combining(c)]).split())

def nomes_sao_similares(n1, n2, threshold=0.75):
    """Compara nomes ignorando erros comuns."""
    s1 = normalize_name(n1)
    s2 = normalize_name(n2)
    if s1 == s2: return True
    # Remove preposições
    for p in [' DE ', ' DA ', ' DO ', ' DOS ', ' DAS ', ' E ']:
        s1 = s1.replace(p, ' '); s2 = s2.replace(p, ' ')
    s1 = " ".join(s1.split()); s2 = " ".join(s2.split())
    if s1 == s2: return True
    # Similaridade
    return difflib.SequenceMatcher(None, s1, s2).ratio() > threshold

def padronizar_nome_projeto(nome):
    if pd.isna(nome): return "NÃO IDENTIFICADO"
    n = normalize_name(nome).replace('POT', '').strip()
    if any(x in n for x in ['DEFESA', 'CIVIL']): return 'DEFESA CIVIL'
    if 'ZELADOR' in n: return 'ZELADORIA'
    if 'AGRI' in n or 'HORTA' in n: return 'AGRICULTURA'
    return n

# --- PARSERS AVANÇADOS PARA OS ARQUIVOS DO BB ---

def parse_bb_resumo(file_obj):
    """
    Lê o formato 'Resumo_CREDITO' onde os dados estão em 2 linhas.
    Linha 1: Cartão | Valor | Nome
    Linha 2: Distrito | Agência | ...
    """
    content = file_obj.getvalue().decode('latin-1', errors='ignore')
    lines = content.split('\n')
    data = []
    
    current_card = None
    current_val = 0.0
    current_name = ""
    
    # Regex Linha 1: Cartão (6 digitos) + Valor (1234.56) + Nome
    reg_line1 = re.compile(r'^\s*(\d{6})\s+(\d+\.\d{2})\s+(.+)$')
    # Regex Linha 2: Agência (4 digitos) aparecendo como segundo número da linha
    # Ex: "00          2445        3"
    reg_line2 = re.compile(r'^\s+\d{2}\s+(\d{4})\s+')

    for line in lines:
        line = line.strip()
        if not line: continue
        
        # Tenta casar Linha 1 (Dados Pessoais)
        m1 = reg_line1.match(line)
        if m1:
            current_card, val_str, current_name = m1.groups()
            current_val = float(val_str)
            continue # Vai para a próxima linha buscar a agência
            
        # Tenta casar Linha 2 (Dados Bancários) se tivermos um registro aberto
        if current_card:
            m2 = reg_line2.match(line)
            if m2:
                agencia = m2.group(1)
                data.append({
                    'num_cartao': current_card,
                    'valor_pagto': current_val,
                    'nome': current_name.strip(),
                    'agencia': agencia,
                    'lote_pagto': 'N/A', # Resumo geralmente não traz lote, ou traz no cabeçalho
                    'programa': 'RESUMO BB',
                    'arquivo_origem': file_obj.name
                })
                # Reseta
                current_card = None
                
    return pd.DataFrame(data)

def parse_bb_cadastro(file_obj):
    """
    Lê o formato 'REL.CADASTRO' onde Lote e Agência estão muito à direita.
    Formato observado: ID | PROJETO | CARTÃO | NOME ... | AGENCIA | ... | LOTE
    """
    content = file_obj.getvalue().decode('latin-1', errors='ignore')
    lines = content.split('\n')
    data = []
    
    for line in lines:
        # Pula cabeçalhos ou linhas curtas
        if len(line) < 50 or "Projeto" in line or "Distrito" in line: continue
        
        # Estratégia: Quebrar a linha por múltiplos espaços para isolar colunas
        parts = re.split(r'\s{2,}', line.strip())
        
        # Esperamos pelo menos: Seq, Projeto, Cartão, Nome ...
        if len(parts) >= 4:
            # Tenta identificar o cartão (6 dígitos)
            cartao = next((p for p in parts if re.match(r'^\d{6}$', p)), None)
            
            if cartao:
                # O índice do cartão nos ajuda a achar o Nome (geralmente o próximo)
                idx_cartao = parts.index(cartao)
                if idx_cartao + 1 < len(parts):
                    nome = parts[idx_cartao + 1]
                    
                    # Agência e Lote costumam estar no final
                    # Lote é frequentemente o último número de 4 dígitos (ex: 5479)
                    # Agência é o penúltimo ou antepenúltimo (ex: 4304)
                    
                    # Vamos pegar todos os números de 4 dígitos da linha
                    numeros_4d = re.findall(r'\b\d{4}\b', line)
                    
                    lote = numeros_4d[-1] if numeros_4d else ''
                    # Se houver mais de um número, o penúltimo provavelmente é a agência
                    agencia = numeros_4d[-2] if len(numeros_4d) >= 2 else ''
                    
                    # Se só achou um número e ele parece ser lote, agência fica vazia
                    
                    data.append({
                        'num_cartao': cartao,
                        'nome': nome,
                        'lote_pagto': lote,
                        'agencia': agencia,
                        'valor_pagto': 0.0,
                        'programa': 'CADASTRO BB',
                        'arquivo_origem': file_obj.name
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
                st.plotly_chart(fig, use_container_width=True)
            else: st.warning("Sem dados válidos para exibir.")
        else: st.info("Sem dados.")

    # --- UPLOAD ---
    elif menu == "Upload":
        st.subheader("📂 Upload de Arquivos")
        st.info("Limite de Upload aumentado para 1GB.")
        files = st.file_uploader("Arquivos (CSV, Excel, TXT Banco)", accept_multiple_files=True)
        if files and st.button("Processar"):
            dfs = []
            for f in files:
                try:
                    if f.name.upper().endswith('.TXT'):
                        if "RESUMO" in f.name.upper(): d = parse_bb_resumo(f)
                        else: d = parse_bb_cadastro(f)
                    elif f.name.endswith('.csv'): d = pd.read_csv(f, sep=';', encoding='latin1', dtype=str)
                    else: d = pd.read_excel(f, dtype=str)
                    if not d.empty: dfs.append(d)
                except: st.error(f"Erro: {f.name}")
            
            if dfs:
                final = pd.concat(dfs, ignore_index=True)
                if 'programa' in final.columns: final['programa'] = final['programa'].apply(padronizar_nome_projeto)
                for c in ['lote_pagto', 'agencia']: 
                    if c not in final.columns: final[c] = ''
                final.to_sql('payments', eng, if_exists='append', index=False, method='multi', chunksize=500)
                st.success("✅ Processado com Sucesso!"); st.cache_data.clear(); st.rerun()

    # --- ANÁLISE ---
    elif menu == "Análise e Correção":
        st.subheader("🔍 Busca e Auditoria")
        c1, c2, c3, c4 = st.columns(4)
        q_nome = c1.text_input("Nome/CPF/Cartão")
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
                st.write(f"**{len(sel)} selecionados.**")
                st.download_button("📥 Baixar Seleção", sel.to_csv(index=False).encode('utf-8'), "selecao.csv")
                
                if u['role'] in ['admin_ti', 'admin_equipe']:
                    with st.expander("✏️ Editar Selecionados"):
                        ed = st.data_editor(sel, hide_index=True)
                        if st.button("Salvar"):
                            with eng.begin() as conn:
                                for i, r in ed.iterrows():
                                    conn.execute(text("UPDATE payments SET nome=:n, cpf=:c, lote_pagto=:l, agencia=:a WHERE id=:id"),
                                                 {"n":r['nome'], "c":r['cpf'], "l":r['lote_pagto'], "a":r['agencia'], "id":r['id']})
                            st.success("Salvo!"); st.rerun()

    # --- CONFERÊNCIA BB (BUSCAS ATIVADAS) ---
    elif menu == "Conferência BB":
        st.subheader("🏦 Conferência Bancária")
        t1, t2 = st.tabs(["Processar Comparação", "Histórico e Buscas"])
        
        with t1:
            st.markdown("Envie o arquivo do banco para cruzar com o sistema.")
            fbb = st.file_uploader("Arquivo TXT do Banco", type=['txt'])
            
            if fbb and st.button("Processar"):
                df_bb = parse_bb_resumo(fbb) if "Resumo" in fbb.name else parse_bb_cadastro(fbb)
                
                if not df_bb.empty and not df_raw.empty:
                    df_bb['k'] = df_bb['num_cartao'].str.strip().str.lstrip('0')
                    df_raw['k'] = df_raw['num_cartao'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True).str.lstrip('0')
                    
                    merged = pd.merge(df_raw, df_bb, on='k', suffixes=('_sis', '_bb'))
                    divs = []
                    
                    prog = st.progress(0)
                    for i, r in merged.iterrows():
                        prog.progress((i+1)/len(merged))
                        if not nomes_sao_similares(r['nome_sis'], r['nome_bb']):
                            divs.append({
                                'cartao': r['k'],
                                'nome_sis': r['nome_sis'],
                                'nome_bb': r['nome_bb'],
                                'lote': r.get('lote_pagto_bb', r.get('lote_pagto_sis', '')),
                                'agencia': r.get('agencia_bb', r.get('agencia_sis', '')),
                                'divergencia': 'NOME',
                                'arquivo_origem': r['arquivo_origem_bb']
                            })
                    prog.empty()
                    
                    if divs:
                        pd.DataFrame(divs).to_sql('bank_discrepancies', eng, if_exists='append', index=False)
                        st.error(f"{len(divs)} Divergências!")
                    else: st.success("✅ Nenhuma divergência!")

        # --- ABA DE HISTÓRICO COM OS FILTROS SOLICITADOS ---
        with t2:
            h = pd.read_sql("SELECT * FROM bank_discrepancies", eng)
            
            st.markdown("#### 🔎 Buscar nas Divergências")
            c1, c2, c3, c4 = st.columns(4)
            # Filtros requisitados
            f_nome = c1.text_input("Nome", key="fn")
            f_cpf = c2.text_input("CPF (Sistema)", key="fcpf") # CPF pode não vir no BB, busca na base sis
            f_lote = c3.text_input("Lote", key="fl")
            f_ag = c4.text_input("Agência", key="fa")
            
            if not h.empty:
                # Aplicação dos Filtros
                view = h.copy()
                if f_nome: 
                    t = f_nome.upper()
                    view = view[view['nome_sis'].str.upper().str.contains(t, na=False) | view['nome_bb'].str.upper().str.contains(t, na=False)]
                
                # Para CPF e Conta, como a tabela de divergencia salva apenas o que divergiu,
                # usamos o cartão como chave se o CPF não estiver salvo na tabela bank_discrepancies.
                # Se necessário, você pode buscar pelo cartão.
                
                if f_lote: view = view[view['lote'].astype(str).str.contains(f_lote, na=False)]
                if f_ag: view = view[view['agencia'].astype(str).str.contains(f_ag, na=False)]
                
                st.dataframe(view, use_container_width=True)
                
                if st.button("Limpar Tudo"):
                    run_db_command("DELETE FROM bank_discrepancies"); st.rerun()
            else:
                st.info("Nenhuma divergência registrada.")

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
