import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, text
import hashlib
import io
import re
import unicodedata
import difflib
import tempfile
import os
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
st.set_page_config(page_title="SMDET - Gestão POT", page_icon="💰", layout="wide")

st.markdown("""
<style>
    .header-container { text-align: center; padding-bottom: 20px; border-bottom: 2px solid #ddd; margin-bottom: 30px; }
    .header-programa { color: #1E3A8A; font-size: 1.5rem; font-weight: bold; }
    .metric-card { background-color: #f8f9fa; padding: 15px; border-radius: 10px; border-left: 5px solid #1E3A8A; }
    /* Força a tabela a ocupar largura total */
    [data-testid="stDataFrame"] { width: 100%; }
</style>
""", unsafe_allow_html=True)

def render_header():
    st.markdown("""
        <div class="header-container">
            <div style="color: #555;">Secretaria Municipal de Desenvolvimento Econômico e Trabalho (SMDET)</div>
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
        with eng.begin() as conn:
            conn.execute(text(sql), params or {})

def init_db():
    eng = get_db_engine()
    if not eng: return
    with eng.connect() as conn:
        conn.execute(text('''CREATE TABLE IF NOT EXISTS users (email TEXT PRIMARY KEY, password TEXT, role TEXT, name TEXT, first_login INTEGER DEFAULT 1)'''))
        # Tabela principal expandida para conter Lote e Agência se disponíveis
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
        conn.execute(text('''CREATE TABLE IF NOT EXISTS audit_logs (id SERIAL PRIMARY KEY, user_email TEXT, action TEXT, details TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)'''))
        conn.execute(text('''CREATE TABLE IF NOT EXISTS bank_discrepancies (
            id SERIAL PRIMARY KEY, cartao TEXT, nome_sis TEXT, nome_bb TEXT, 
            divergencia TEXT, arquivo_origem TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )'''))
        conn.commit()
        # Admin padrão
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
# 3. PARSERS ESPECÍFICOS DO BB (TEXTO/LARGURA FIXA)
# ===========================================

def normalize_name(name):
    if not name or str(name).lower() in ['nan', 'none', '']: return ""
    s = str(name)
    try: s = s.encode('cp1252').decode('utf-8') # Tenta corrigir encoding comum
    except: pass
    nfkd = unicodedata.normalize('NFKD', s)
    return " ".join("".join([c for c in nfkd if not unicodedata.combining(c)]).upper().split())

def nomes_sao_similares(n1, n2):
    """Compara nomes ignorando case, preposições e pequenas diferenças."""
    s1 = normalize_name(n1)
    s2 = normalize_name(n2)
    if s1 == s2: return True
    
    # Remove preposições comuns
    for p in [' DE ', ' DA ', ' DO ', ' DOS ', ' E ']:
        s1 = s1.replace(p, ' ')
        s2 = s2.replace(p, ' ')
        
    # Similaridade (0.85 = 85% igual)
    return difflib.SequenceMatcher(None, s1, s2).ratio() > 0.85

def parse_bb_resumo(file_obj):
    """Lê o arquivo Resumo_CREDITO... que tem dados em multiplas linhas."""
    content = file_obj.getvalue().decode('latin-1', errors='ignore')
    lines = content.split('\n')
    
    data = []
    current_record = {}
    
    # Regex para capturar a linha principal: Cartão (6 digitos) + Valor + Nome
    # Ex: 377120     1386.00       ABDUL MANAN SHARIFI
    regex_main = re.compile(r'^(\d{6})\s+(\d+\.\d{2})\s+(.+)$')
    
    # Regex para capturar a linha secundária: Distrito + Agencia
    # Ex:           00          2445        3                24
    regex_sec = re.compile(r'^\s+(\d{2})\s+(\d{4})\s+')

    for line in lines:
        line = line.strip()
        if not line: continue
        
        # Tenta casar linha principal
        match_main = regex_main.match(line)
        if match_main:
            # Se já tinha um record aberto, salva (embora nesse layout o record feche na prox linha)
            if current_record: 
                data.append(current_record)
            
            cartao, valor, nome = match_main.groups()
            current_record = {
                'num_cartao': cartao,
                'valor_pagto': float(valor),
                'nome': nome.strip(),
                'agencia': '', # Será preenchido na proxima linha
                'lote_pagto': '',
                'programa': 'PAGAMENTO BB',
                'arquivo_origem': file_obj.name
            }
            continue
            
        # Tenta casar linha secundária (Agência)
        if current_record:
            match_sec = regex_sec.match(line)
            if match_sec:
                distrito, agencia = match_sec.groups()
                current_record['agencia'] = agencia
                data.append(current_record)
                current_record = {} # Reseta
                
    # Adiciona o último se sobrar
    if current_record: data.append(current_record)
    
    return pd.DataFrame(data)

def parse_bb_cadastro(file_obj):
    """Lê o arquivo REL.CADASTRO... que tem Lote e Agência."""
    content = file_obj.getvalue().decode('latin-1', errors='ignore')
    lines = content.split('\n')
    
    data = []
    # Padrão: ID + PROJETO + CARTÃO + NOME ... e na mesma linha ou quebra: LOTE
    # Observando os dados:
    # 1 AGRICULTURA 381001 GABRIEL... (dados) ... 2996 (ag) ... 5480 (lote)
    
    for line in lines:
        if len(line) < 50 or "Projeto" in line: continue
        
        # Tenta extrair via Regex flexível para o formato observado
        # Procura: Seq (digitos) + Espaços + Projeto (texto) + Espaços + Cartão (6 dig)
        match = re.search(r'^\s*\d+\s+([A-Z\s]+?)\s+(\d{6})\s+([A-Z\s\.]+?)\s+\d+', line)
        
        if match:
            proj, cartao, nome = match.groups()
            
            # Tenta achar o lote e agencia no final da linha
            # O lote costuma ser o último número de 4 digitos, a agência o antepenúltimo
            parts = line.split()
            lote = parts[-1] if len(parts[-1]) == 4 else ''
            # A data costuma ser antes do lote
            # A agência costuma vir antes do nome da agência. É arriscado pegar por posição fixa sem split.
            
            # Busca agencia (4 digitos) próximo ao fim
            agencia = ''
            matches_nums = re.findall(r'\s(\d{4})\s', line)
            if matches_nums:
                agencia = matches_nums[-1] # Assume que é o último número de 4 dígitos isolado antes do lote

            data.append({
                'programa': proj.strip(),
                'num_cartao': cartao,
                'nome': nome.strip(),
                'lote_pagto': lote,
                'agencia': agencia,
                'valor_pagto': 0.0, # Cadastro não tem valor de pagamento geralmente
                'arquivo_origem': file_obj.name
            })
            
    return pd.DataFrame(data)

# ===========================================
# 4. PADRONIZAÇÃO E ANÁLISE
# ===========================================

def padronizar_nome_projeto(nome_original):
    if pd.isna(nome_original): return "NÃO IDENTIFICADO"
    nome = normalize_name(nome_original)
    nome = re.sub(r'^POT\s?', '', nome).strip() # Remove POT do começo
    
    # Regras de Unificação
    if 'DEFESA' in nome or 'CIVIL' in nome: return 'DEFESA CIVIL'
    if 'ZELADOR' in nome: return 'ZELADORIA'
    if 'AGRI' in nome or 'HORTA' in nome: return 'AGRICULTURA'
    if 'ADM' in nome: return 'ADM'
    if 'PARQUE' in nome: return 'PARQUES'
    return nome

def processar_upload(dfs):
    if not dfs: return None
    final = pd.concat(dfs, ignore_index=True)
    
    # Padronizações Finais
    if 'programa' in final.columns:
        final['programa'] = final['programa'].apply(padronizar_nome_projeto)
    
    # Garante colunas
    cols_check = ['lote_pagto', 'agencia', 'cpf', 'rg']
    for c in cols_check:
        if c not in final.columns: final[c] = ''
        
    return final

# ===========================================
# 5. APP PRINCIPAL
# ===========================================

def login_screen():
    render_header()
    c1,c2,c3 = st.columns([1,2,1])
    with c2:
        with st.form("login"):
            email = st.text_input("Email"); p = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar"):
                eng = get_db_engine()
                if not eng: st.error("Erro BD"); return
                with eng.connect() as conn:
                    res = conn.execute(text("SELECT * FROM users WHERE email=:e"), {"e": e}).fetchone()
                    if res and res.password == hashlib.sha256(p.encode()).hexdigest():
                        st.session_state['logged_in'] = True
                        st.session_state['u'] = {'email':res.email, 'role':res.role, 'name':res.name}
                        st.rerun()
                    else: st.error("Acesso Negado")

def app():
    u = st.session_state['u']
    st.sidebar.markdown(f"**Usuário:** {u['name']}")
    
    # Botão para limpar cache se houver problemas de atualização
    if st.sidebar.button("🧹 Limpar Cache do Sistema"):
        st.cache_data.clear()
        st.rerun()

    menu = st.sidebar.radio("Navegação", ["Dashboard", "Upload", "Análise e Correção", "Conferência BB", "Relatórios"])
    
    eng = get_db_engine()
    
    # Carrega dados para memória (Cacheado)
    df_raw = pd.DataFrame()
    if eng:
        try: df_raw = pd.read_sql("SELECT * FROM payments", eng)
        except: pass

    render_header()

    # --- DASHBOARD ---
    if menu == "Dashboard":
        st.subheader("📊 Visão Geral (Dados Válidos)")
        if not df_raw.empty:
            df_raw['valor_pagto'] = pd.to_numeric(df_raw['valor_pagto'], errors='coerce').fillna(0.0)
            
            # Filtro de Higiene: Remove zerados e nomes de projeto inválidos (só números)
            mask_valid = (df_raw['valor_pagto'] > 0.01) & (~df_raw['programa'].astype(str).str.isnumeric())
            df_clean = df_raw[mask_valid].copy()
            
            k1,k2,k3 = st.columns(3)
            k1.metric("Total Pago", f"R$ {df_clean['valor_pagto'].sum():,.2f}")
            k2.metric("Beneficiários", df_clean['nome'].nunique())
            k3.metric("Projetos", df_clean['programa'].nunique())
            
            st.markdown("---")
            
            if not df_clean.empty:
                # Gráfico Horizontal
                grp = df_clean.groupby('programa')['valor_pagto'].sum().reset_index().sort_values('valor_pagto', ascending=True)
                fig = px.bar(grp, x='valor_pagto', y='programa', orientation='h', text_auto='.2s', title="Totais por Projeto")
                fig.update_traces(texttemplate='R$ %{x:,.2f}', textposition='outside')
                fig.update_layout(height=max(400, len(grp)*40)) # Altura dinâmica
                st.plotly_chart(fig, use_container_width=True)
                
                # Tabela Detalhada
                st.dataframe(grp.sort_values('valor_pagto', ascending=False).style.format({'valor_pagto': 'R$ {:,.2f}'}), use_container_width=True)
            else:
                st.warning("Sem dados válidos para exibir (Valores > 0).")
        else:
            st.info("Base de dados vazia.")

    # --- UPLOAD INTELIGENTE ---
    elif menu == "Upload":
        st.subheader("📂 Upload de Arquivos (BB / Excel / CSV)")
        files = st.file_uploader("Arraste seus arquivos aqui", accept_multiple_files=True)
        
        if files and st.button("Processar Arquivos"):
            dfs = []
            for f in files:
                try:
                    # Identifica tipo de arquivo pelo nome ou extensão
                    if f.name.startswith("Resumo_CREDITO"):
                        st.info(f"Processando arquivo de Crédito BB: {f.name}")
                        d = parse_bb_resumo(f)
                    elif f.name.startswith("REL.CADASTRO"):
                        st.info(f"Processando arquivo de Cadastro BB: {f.name}")
                        d = parse_bb_cadastro(f)
                    elif f.name.endswith(".csv"):
                        d = pd.read_csv(f, sep=';', encoding='latin1', dtype=str)
                    else:
                        d = pd.read_excel(f, dtype=str)
                    
                    if not d.empty: dfs.append(d)
                    
                except Exception as e:
                    st.error(f"Erro ao ler {f.name}: {e}")
            
            if dfs:
                final = processar_upload(dfs)
                # Salva no Banco
                final.to_sql('payments', eng, if_exists='append', index=False, method='multi', chunksize=500)
                st.success("✅ Arquivos processados e salvos com sucesso!")
                st.cache_data.clear() # Força atualização
                st.rerun()

    # --- ANÁLISE (BUSCA AVANÇADA) ---
    elif menu == "Análise e Correção":
        st.subheader("🔍 Busca Avançada e Auditoria")
        
        # Filtros
        c1, c2, c3 = st.columns(3)
        q_geral = c1.text_input("🔎 Busca Geral (Nome/CPF/Cartão/RG)")
        q_lote = c2.text_input("📦 Filtrar por Lote")
        q_agencia = c3.text_input("🏦 Filtrar por Agência")
        
        if not df_raw.empty:
            df_view = df_raw.copy()
            
            # Aplica Filtros
            if q_geral:
                t = q_geral.upper()
                df_view = df_view[
                    df_view['nome'].str.upper().str.contains(t, na=False) | 
                    df_view['cpf'].str.contains(t, na=False) |
                    df_view['num_cartao'].str.contains(t, na=False) |
                    df_view['rg'].str.contains(t, na=False)
                ]
            if q_lote:
                df_view = df_view[df_view['lote_pagto'].astype(str).str.contains(q_lote, na=False)]
            if q_agencia:
                df_view = df_view[df_view['agencia'].astype(str).str.contains(q_agencia, na=False)]
            
            st.write(f"**Resultados:** {len(df_view)} registros encontrados.")
            
            # Tabela Interativa
            event = st.dataframe(
                df_view,
                use_container_width=True,
                hide_index=True,
                selection_mode="multi-row",
                on_select="rerun"
            )
            
            # Ações em Lote
            sel_rows = event.selection.rows
            if sel_rows:
                df_sel = df_view.iloc[sel_rows]
                st.success(f"{len(df_sel)} itens selecionados.")
                
                col_btn1, col_btn2 = st.columns(2)
                col_btn1.download_button("📥 Baixar CSV dos Selecionados", df_sel.to_csv(index=False), "selecao.csv")
                
                with st.expander("✏️ Editar Selecionados (Admin)"):
                    if u['role'] == 'admin_ti':
                        edit_df = st.data_editor(df_sel, hide_index=True)
                        if st.button("Salvar Edições"):
                            with eng.begin() as conn:
                                for i, r in edit_df.iterrows():
                                    conn.execute(text("""
                                        UPDATE payments SET nome=:n, cpf=:c, num_cartao=:nc, lote_pagto=:l, agencia=:a 
                                        WHERE id=:id
                                    """), {"n":r['nome'], "c":r['cpf'], "nc":r['num_cartao'], "l":r['lote_pagto'], "a":r['agencia'], "id":r['id']})
                            st.success("Salvo!")
                            st.rerun()
                    else:
                        st.error("Apenas Admin pode editar.")

    # --- CONFERÊNCIA BB (CORRIGIDA) ---
    elif menu == "Conferência BB":
        st.subheader("🏦 Conferência Bancária (Inteligente)")
        
        f_bb = st.file_uploader("Suba o arquivo TXT do Banco", type=['txt'])
        
        if f_bb:
            # Tenta processar o arquivo usando os parsers
            df_bb = pd.DataFrame()
            if "Resumo" in f_bb.name:
                df_bb = parse_bb_resumo(f_bb)
            elif "REL" in f_bb.name:
                df_bb = parse_bb_cadastro(f_bb)
            else:
                st.warning("Formato desconhecido. Tentando parser genérico.")
                df_bb = parse_bb_resumo(f_bb) # Tenta o resumo por padrão
            
            if not df_bb.empty and not df_raw.empty:
                st.info(f"Analisando {len(df_bb)} registros do Banco contra {len(df_raw)} do Sistema...")
                
                # Normaliza para comparação
                df_bb['key'] = df_bb['num_cartao'].str.strip().str.lstrip('0')
                df_raw['key'] = df_raw['num_cartao'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True).str.lstrip('0')
                
                # Cruza os dados
                merged = pd.merge(df_raw, df_bb, on='key', suffixes=('_sis', '_bb'), how='inner')
                
                divergencias = []
                
                # Barra de progresso para a comparação fuzzy (pode ser lenta)
                prog_bar = st.progress(0)
                total = len(merged)
                
                for idx, row in merged.iterrows():
                    prog_bar.progress((idx + 1) / total)
                    
                    # COMPARAÇÃO INTELIGENTE
                    nome_sis = row['nome_sis']
                    nome_bb = row['nome_bb']
                    
                    if not nomes_sao_similares(nome_sis, nome_bb):
                        divergencias.append({
                            'Cartão': row['key'],
                            'Nome Sistema': nome_sis,
                            'Nome Banco': nome_bb,
                            'Status': 'DIVERGENTE'
                        })
                
                prog_bar.empty()
                
                if divergencias:
                    df_div = pd.DataFrame(divergencias)
                    st.error(f"{len(df_div)} Divergências Reais Encontradas!")
                    st.dataframe(df_div, use_container_width=True)
                else:
                    st.success("✅ Nenhuma divergência encontrada! (Ignorando diferenças de caixa alta e abreviações)")

if __name__ == "__main__":
    init_db()
    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
    if st.session_state['logged_in']: app()
    else: login_screen()
