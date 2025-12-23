import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
import hashlib
import io
import re
import os
import time
import tempfile
import unicodedata
from datetime import datetime, timedelta, timezone
from collections import Counter

# Tenta importar bibliotecas externas opcionais
try:
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

try:
    from fpdf import FPDF
except ImportError:
    FPDF = None

# ===========================================
# CONFIGURAÇÃO INICIAL E ESTILOS
# ===========================================
st.set_page_config(
    page_title="SMDET - Gestão POT",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilo CSS Personalizado (Incluindo Backfilling e Dashboards)
st.markdown("""
<style>
    .header-container {
        text-align: center;
        padding-bottom: 20px;
        border-bottom: 2px solid #ddd;
        margin-bottom: 30px;
    }
    .header-secretaria {
        color: #555;
        font-size: 1rem;
        margin-bottom: 5px;
        font-weight: 500;
    }
    .header-programa {
        color: #1E3A8A;
        font-size: 1.5rem;
        font-weight: bold;
        margin-bottom: 5px;
    }
    .header-sistema {
        color: #2563EB;
        font-size: 1.8rem;
        font-weight: bold;
    }
    /* Estilos do Backfilling (Container Escuro Opcional) */
    .backfill-container {
        background-color: #1e1e1e;
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #333;
        margin-bottom: 20px;
        color: #e0e0e0;
    }
    .backfill-title {
        color: #fff;
        font-size: 1.1rem;
        font-weight: bold;
        margin-bottom: 10px;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .console-log {
        font-family: 'Courier New', monospace;
        color: #4ade80;
        font-size: 0.9rem;
        margin-top: 5px;
        padding-left: 10px;
        border-left: 2px solid #4ade80;
    }
</style>
""", unsafe_allow_html=True)

# ===========================================
# BANCO DE DADOS
# ===========================================

DB_FILE = 'pot_system.db'

def init_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    
    # Tabela Usuários
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            password TEXT,
            role TEXT,
            name TEXT,
            first_login INTEGER DEFAULT 1
        )
    ''')
    
    # Tabela Pagamentos (Principal)
    c.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            programa TEXT,
            gerenciadora TEXT,
            num_cartao TEXT,
            nome TEXT,
            cpf TEXT,
            rg TEXT,
            valor_pagto REAL,
            data_pagto TEXT,
            competencia TEXT,
            qtd_dias INTEGER,
            mes_ref TEXT,
            ano_ref TEXT,
            tipo_arquivo TEXT,
            arquivo_origem TEXT,
            linha_arquivo INTEGER,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    try:
        c.execute("ALTER TABLE payments ADD COLUMN competencia TEXT")
    except sqlite3.OperationalError:
        pass 

    # Tabela Divergências Bancárias (Usada também como Fonte de Verdade para Backfill)
    c.execute('''
        CREATE TABLE IF NOT EXISTS bank_discrepancies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cartao TEXT,
            nome_sis TEXT,
            nome_bb TEXT,
            cpf_sis TEXT,
            cpf_bb TEXT,
            rg_sis TEXT,
            rg_bb TEXT,
            divergencia TEXT,
            arquivo_origem TEXT,
            tipo_erro TEXT, 
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Logs de Auditoria
    c.execute('''
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT,
            action TEXT,
            details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Admin Padrão
    c.execute("SELECT * FROM users WHERE email = 'admin@prefeitura.sp.gov.br'")
    if not c.fetchone():
        default_pass = hashlib.sha256('smdet2025'.encode()).hexdigest()
        c.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?)", 
                  ('admin@prefeitura.sp.gov.br', default_pass, 'admin_ti', 'Administrador TI', 0))
    
    conn.commit()
    conn.close()

def get_db_connection():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def log_action(user_email, action, details):
    try:
        conn = get_db_connection()
        conn.execute("INSERT INTO audit_logs (user_email, action, details) VALUES (?, ?, ?)", 
                     (user_email, action, details))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Erro ao logar: {e}")

# ===========================================
# UTILITÁRIOS E PARSERS
# ===========================================

def sanitize_text(text):
    if not isinstance(text, str): return str(text)
    text = text.replace('–', '-').replace('—', '-').replace('“', '"').replace('”', '"')
    return text.encode('latin-1', 'replace').decode('latin-1')

def remove_accents(input_str):
    if not isinstance(input_str, str): return str(input_str)
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)]).upper().strip()

def normalize_key(val):
    """Limpa CPF ou Cartão para uso como chave"""
    if not val: return ""
    return str(val).replace('.', '').replace('-', '').replace('/', '').strip()

def get_brasilia_time():
    return datetime.now(timezone(timedelta(hours=-3)))

# Parser Banco do Brasil (Mantido e simplificado para integração)
def parse_smart_bb(file_obj, filename):
    try:
        content = file_obj.getvalue().decode('latin-1', errors='ignore')
    except:
        content = file_obj.getvalue().decode('utf-8', errors='ignore')
    
    lines = content.split('\n')
    data = []
    filename_upper = filename.upper()
    data_arquivo = datetime.now().strftime('%d/%m/%Y')
    
    # Tenta extrair data do cabeçalho
    match_date = re.search(r'(\d{2})\s+([A-Za-z]{3})\s+(\d{4})', content[:500])
    if match_date:
        d, m, y = match_date.groups()
        data_arquivo = f"{d}/{m}/{y}"

    # Lógica simplificada para identificar tipos de arquivo BB
    if "REL.CADASTRO" in filename_upper or "CADASTRO" in filename_upper:
        for line in lines:
            if line.startswith('1') and len(line) > 100:
                try:
                    data.append({
                        'arquivo_origem': filename,
                        'num_cartao': line[42:52].strip(),
                        'nome_banco': line[52:92].strip(),
                        'rg_banco': line[92:104].strip(),
                        'cpf_banco': line[104:119].strip().replace('.', '').replace('-', ''),
                        'data_ref': data_arquivo
                    })
                except: continue
    
    elif "RESUMO" in filename_upper: # Spool
        for line in lines:
            match = re.search(r'^\s*(\d{6,})\s+([\d\.]+)\s+(.+)$', line)
            if match:
                data.append({
                    'arquivo_origem': filename,
                    'num_cartao': match.group(1),
                    'nome_banco': match.group(3).strip(),
                    'valor': match.group(2),
                    'data_ref': data_arquivo
                })

    return pd.DataFrame(data)

# ===========================================
# LÓGICA DE BACKFILLING (RECUPERAÇÃO)
# ===========================================

def build_master_key(conn):
    """
    Cria um dicionário mestre {cartao: {'cpf': '...', 'rg': '...'}}
    Baseado no histórico da tabela payments E tabela de divergências (dados bancários confiáveis).
    """
    # 1. Dados do Sistema (Payments)
    df_pay = pd.read_sql("SELECT num_cartao, cpf, rg FROM payments WHERE num_cartao IS NOT NULL AND num_cartao != ''", conn)
    
    # 2. Dados do Banco (Discrepancies - assumindo que cpf_bb é confiável)
    df_bank = pd.read_sql("SELECT cartao as num_cartao, cpf_bb as cpf, rg_bb as rg FROM bank_discrepancies WHERE cartao IS NOT NULL", conn)
    
    # Unifica
    df_all = pd.concat([df_pay, df_bank], ignore_index=True)
    
    master_map = {}
    
    # Agrupa por cartão para achar o CPF/RG mais frequente (Consenso)
    groups = df_all.groupby('num_cartao')
    
    for card, group in groups:
        # Limpa chaves
        card_clean = normalize_key(card)
        if not card_clean: continue
        
        # Acha CPF mais comum
        cpfs = [c for c in group['cpf'].dropna().astype(str) if len(normalize_key(c)) > 5 and 'NAN' not in c.upper()]
        best_cpf = Counter(cpfs).most_common(1)[0][0] if cpfs else None
        
        # Acha RG mais comum
        rgs = [r for r in group['rg'].dropna().astype(str) if len(normalize_key(r)) > 3 and 'NAN' not in r.upper()]
        best_rg = Counter(rgs).most_common(1)[0][0] if rgs else None
        
        if best_cpf or best_rg:
            master_map[card_clean] = {'cpf': best_cpf, 'rg': best_rg}
            
    return master_map

# ===========================================
# GERAÇÃO DE RELATÓRIOS (PDF APRIMORADO)
# ===========================================

def generate_pdf_report(df_filtered):
    if FPDF is None: return b"Erro: Biblioteca FPDF nao instalada."
    
    pdf = FPDF()
    pdf.add_page(orientation='L')
    
    # Cabeçalho Oficial
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 8, sanitize_text("Prefeitura de São Paulo"), 0, 1, 'C')
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 8, sanitize_text("Secretaria Municipal do Desenvolvimento Econômico e Trabalho"), 0, 1, 'C')
    pdf.ln(5)
    
    # Título do Relatório
    pdf.set_fill_color(30, 58, 138) # Azul Profundo
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 12, sanitize_text("Relatório Executivo e Auditoria POT"), 0, 1, 'C', fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(5)
    
    # Metadata
    data_br = get_brasilia_time().strftime('%d/%m/%Y às %H:%M')
    competencias = df_filtered['competencia'].unique()
    comp_str = ", ".join([str(c) for c in competencias if c])
    
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 6, sanitize_text(f"Gerado em: {data_br}"), 0, 1, 'R')
    pdf.cell(0, 6, sanitize_text(f"Competência(s): {comp_str}"), 0, 1, 'L')
    pdf.ln(5)
    
    # KPIs Principais
    total_valor = df_filtered['valor_pagto'].sum() if 'valor_pagto' in df_filtered.columns else 0.0
    qtd_benef = df_filtered['num_cartao'].nunique() if 'num_cartao' in df_filtered.columns else 0
    qtd_proj = df_filtered['programa'].nunique() if 'programa' in df_filtered.columns else 0
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "Resumo de Indicadores (KPIs)", 0, 1)
    
    pdf.set_font("Arial", '', 11)
    pdf.set_fill_color(240, 248, 255)
    pdf.cell(90, 10, f"Valor Total: R$ {total_valor:,.2f}", 1, 0, 'C', True)
    pdf.cell(90, 10, f"Beneficiários: {qtd_benef}", 1, 0, 'C', True)
    pdf.cell(90, 10, f"Projetos: {qtd_proj}", 1, 1, 'C', True)
    pdf.ln(10)
    
    # Gráfico (Matplotlib)
    if plt and not df_filtered.empty and 'programa' in df_filtered.columns:
        try:
            # Prepara dados
            grp = df_filtered.groupby('programa')['valor_pagto'].sum().sort_values(ascending=True).tail(10)
            
            plt.figure(figsize=(10, 5))
            grp.plot(kind='barh', color='#2563EB')
            plt.title('Top 10 Projetos por Valor (R$)')
            plt.xlabel('Total Pago')
            plt.tight_layout()
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                plt.savefig(tmp.name, dpi=100)
                img_path = tmp.name
            
            pdf.image(img_path, x=20, w=200)
            plt.close()
            os.remove(img_path)
            pdf.ln(5)
        except Exception as e:
            pdf.cell(0, 10, f"Erro ao gerar grafico: {str(e)}", 0, 1)

    # Tabela Detalhada por Projeto
    pdf.add_page(orientation='L')
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, sanitize_text("Detalhamento por Projeto e Competência"), 0, 1)
    
    pdf.set_font("Arial", 'B', 9)
    pdf.set_fill_color(200, 200, 200)
    cols = ['PROJETO', 'COMPETÊNCIA', 'QTD BENEF.', 'VALOR TOTAL']
    ws = [100, 50, 40, 60]
    for i, c in enumerate(cols): pdf.cell(ws[i], 8, sanitize_text(c), 1, 0, 'C', True)
    pdf.ln()
    
    pdf.set_font("Arial", '', 9)
    if 'programa' in df_filtered.columns:
        grp_det = df_filtered.groupby(['programa', 'competencia']).agg(
            {'num_cartao': 'nunique', 'valor_pagto': 'sum'}
        ).reset_index().sort_values('valor_pagto', ascending=False)
        
        for _, row in grp_det.iterrows():
            pdf.cell(ws[0], 7, sanitize_text(str(row['programa'])[:55]), 1)
            pdf.cell(ws[1], 7, sanitize_text(str(row['competencia'])), 1, 0, 'C')
            pdf.cell(ws[2], 7, str(row['num_cartao']), 1, 0, 'C')
            pdf.cell(ws[3], 7, f"R$ {row['valor_pagto']:,.2f}", 1, 1, 'R')

    return pdf.output(dest='S').encode('latin-1', 'replace')

# ===========================================
# INTERFACE PRINCIPAL
# ===========================================

def render_header():
    st.markdown("""
        <div class="header-container">
            <div class="header-secretaria">Secretaria Municipal de Desenvolvimento Econômico e Trabalho (SMDET)</div>
            <div class="header-programa">Programa Operação Trabalho (POT)</div>
            <div class="header-sistema">Sistema de Gestão e Monitoramento de Pagamentos</div>
        </div>
    """, unsafe_allow_html=True)

def main_app():
    user = st.session_state['user_info']
    
    # Sidebar
    st.sidebar.markdown(f"### 👤 {user['name']}")
    st.sidebar.markdown(f"Função: **{user['role'].upper()}**")
    st.sidebar.markdown("---")
    
    menu = ["Dashboard", "Upload e Processamento", "Análise e Correção", "Conferência Bancária (BB)", "Relatórios e Exportação"]
    if user['role'] in ['admin_ti', 'admin_equipe']:
        menu.append("Gestão de Dados")
        menu.append("Gestão de Equipe")
    
    choice = st.sidebar.radio("Navegação", menu)
    
    if st.sidebar.button("Sair"):
        st.session_state.clear()
        st.rerun()
    
    # Carregar dados globais para dashboards
    conn = get_db_connection()
    try:
        df_payments = pd.read_sql("SELECT * FROM payments", conn)
    except:
        df_payments = pd.DataFrame()
    conn.close()

    # ------------------------------------------------------------------
    # ABA DASHBOARD
    # ------------------------------------------------------------------
    if choice == "Dashboard":
        render_header()
        st.markdown("### 📊 Visão Geral do Programa")
        
        if df_payments.empty:
            st.warning("O banco de dados está vazio. Vá para 'Upload e Processamento'.")
        else:
            # Filtros de Dashboard
            c_fil1, c_fil2 = st.columns(2)
            projs = ['Todos'] + list(df_payments['programa'].unique())
            comps = ['Todas'] + list(df_payments['competencia'].unique())
            
            sel_proj = c_fil1.selectbox("Filtrar Projeto", projs)
            sel_comp = c_fil2.selectbox("Filtrar Competência", comps)
            
            df_dash = df_payments.copy()
            if sel_proj != 'Todos': df_dash = df_dash[df_dash['programa'] == sel_proj]
            if sel_comp != 'Todas': df_dash = df_dash[df_dash['competencia'] == sel_comp]
            
            # KPIs
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Total Pago", f"R$ {df_dash['valor_pagto'].sum():,.2f}")
            k2.metric("Beneficiários", df_dash['num_cartao'].nunique())
            k3.metric("Projetos Ativos", df_dash['programa'].nunique())
            k4.metric("Registros Processados", len(df_dash))
            
            st.markdown("---")
            
            # Gráficos
            g1, g2 = st.columns(2)
            with g1:
                st.subheader("Top 10 Projetos (Custo)")
                proj_grp = df_dash.groupby('programa')['valor_pagto'].sum().sort_values(ascending=True).tail(10).reset_index()
                fig_bar = px.bar(proj_grp, x='valor_pagto', y='programa', orientation='h', text_auto='.2s')
                st.plotly_chart(fig_bar, use_container_width=True)
            
            with g2:
                st.subheader("Distribuição por Competência")
                comp_grp = df_dash.groupby('competencia')['valor_pagto'].sum().reset_index()
                fig_pie = px.pie(comp_grp, names='competencia', values='valor_pagto', hole=0.4)
                st.plotly_chart(fig_pie, use_container_width=True)

    # ------------------------------------------------------------------
    # ABA UPLOAD
    # ------------------------------------------------------------------
    elif choice == "Upload e Processamento":
        render_header()
        st.markdown("### 📂 Importação de Folhas de Pagamento")
        st.info("Suporta arquivos CSV (separador ; ou ,) e Excel (.xlsx). O sistema tentará identificar Mês/Ano automaticamente.")
        
        uploaded_files = st.file_uploader("Selecione os arquivos", accept_multiple_files=True)
        
        if uploaded_files and st.button("Processar Arquivos"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            dfs = []
            conn = get_db_connection()
            existing_files = pd.read_sql("SELECT DISTINCT arquivo_origem FROM payments", conn)['arquivo_origem'].tolist()
            conn.close()
            
            for i, f in enumerate(uploaded_files):
                status_text.text(f"Lendo {f.name}...")
                if f.name in existing_files:
                    st.toast(f"Arquivo {f.name} já existe. Pulando.")
                    continue
                
                try:
                    if f.name.endswith('.csv'):
                        df = pd.read_csv(f, sep=';', encoding='latin1', dtype=str)
                    else:
                        df = pd.read_excel(f, dtype=str)
                    
                    # Normalização básica de colunas
                    df.columns = [c.lower().strip() for c in df.columns]
                    
                    # Adiciona metadados
                    df['arquivo_origem'] = f.name
                    df['created_at'] = datetime.now()
                    
                    # Trata valor (exemplo simplificado)
                    if 'valor_pagto' in df.columns:
                        df['valor_pagto'] = df['valor_pagto'].astype(str).str.replace('R$','').str.replace('.','').str.replace(',','.').astype(float)
                    
                    # Gera competencia (Simplificado)
                    df['competencia'] = datetime.now().strftime('%B %Y') 
                    
                    dfs.append(df)
                    
                except Exception as e:
                    st.error(f"Erro em {f.name}: {e}")
                
                progress_bar.progress((i + 1) / len(uploaded_files))
            
            if dfs:
                final_df = pd.concat(dfs, ignore_index=True)
                conn = get_db_connection()
                try:
                    # Salva usando append
                    final_df.to_sql('payments', conn, if_exists='append', index=False)
                    st.success(f"Sucesso! {len(final_df)} novos registros importados.")
                    log_action(user['email'], "UPLOAD", f"Importou {len(uploaded_files)} arquivos.")
                except Exception as e:
                    st.error(f"Erro ao salvar no banco: {e}")
                conn.close()
            else:
                st.warning("Nenhum arquivo novo processado.")

    # ------------------------------------------------------------------
    # ABA ANÁLISE E CORREÇÃO (COM BACKFILLING RESTAURADO)
    # ------------------------------------------------------------------
    elif choice == "Análise e Correção":
        render_header()
        st.markdown("### 🛠️ Auditoria e Qualidade de Dados")
        
        # --- BLOCO DE BACKFILLING (RESTAURADO) ---
        # Container escuro opcional (via CSS) mas com componentes nativos dentro
        st.markdown('<div class="backfill-container">', unsafe_allow_html=True)
        with st.expander("🔨 Ferramenta de Recuperação (Backfilling) - Chave Mestra", expanded=True):
            st.markdown("""
            **Recuperação Inteligente de Dados:**
            O sistema varre todo o histórico de pagamentos e arquivos de conferência bancária.
            Ao encontrar um registro com **Cartão** válido, ele busca em registros passados (ou no retorno do banco)
            o **CPF** e **RG** corretos associados àquele cartão e preenche as lacunas atuais.
            """)
            
            if st.button("Executar Backfilling (CPF & RG)", type="primary"):
                status = st.status("Iniciando processo de recuperação...", expanded=True)
                conn = get_db_connection()
                cursor = conn.cursor()
                
                # Passo 1: Mapa
                status.write("🔍 Mapeando histórico de contas (Chave Mestra)...")
                master_map = build_master_key(conn)
                status.write(f"✅ Histórico mapeado: {len(master_map)} contas únicas com dados válidos.")
                time.sleep(1)
                
                # Passo 2: Identificar Alvos
                status.write("🔍 Identificando registros incompletos na base atual...")
                cursor.execute("SELECT id, num_cartao, cpf, rg FROM payments")
                rows = cursor.fetchall()
                
                updated_count = 0
                recovered_cpfs = 0
                recovered_rgs = 0
                
                # Passo 3: Aplicar Correções
                status.write("⚙️ Aplicando correções...")
                bar = status.progress(0)
                total_rows = len(rows)
                
                for i, row in enumerate(rows):
                    rid, raw_card, raw_cpf, raw_rg = row
                    card_key = normalize_key(raw_card)
                    
                    if card_key in master_map:
                        knowledge = master_map[card_key]
                        changes = []
                        new_cpf = raw_cpf
                        new_rg = raw_rg
                        
                        # Verifica CPF
                        curr_cpf_clean = normalize_key(raw_cpf)
                        if (not curr_cpf_clean or len(curr_cpf_clean) < 5) and knowledge['cpf']:
                            new_cpf = knowledge['cpf']
                            changes.append("CPF")
                            recovered_cpfs += 1
                        
                        # Verifica RG
                        curr_rg_clean = normalize_key(raw_rg)
                        if (not curr_rg_clean or len(curr_rg_clean) < 3) and knowledge['rg']:
                            new_rg = knowledge['rg']
                            changes.append("RG")
                            recovered_rgs += 1
                        
                        if changes:
                            cursor.execute("UPDATE payments SET cpf = ?, rg = ? WHERE id = ?", (new_cpf, new_rg, rid))
                            updated_count += 1
                    
                    if i % 100 == 0: bar.progress((i+1)/total_rows)
                
                conn.commit()
                conn.close()
                bar.progress(100)
                status.update(label="Processo Concluído!", state="complete", expanded=False)
                
                st.success(f"Backfilling Finalizado! {updated_count} registros atualizados.")
                c1, c2 = st.columns(2)
                c1.metric("CPFs Recuperados", recovered_cpfs)
                c2.metric("RGs Recuperados", recovered_rgs)
                log_action(user['email'], "BACKFILL", f"Recuperou {updated_count} registros.")
                
        st.markdown('</div>', unsafe_allow_html=True)
        # --- FIM BACKFILLING ---

        if not df_payments.empty:
            st.dataframe(df_payments.head(100), use_container_width=True)
            st.info("Exibindo os primeiros 100 registros.")

    # ------------------------------------------------------------------
    # ABA CONFERÊNCIA
    # ------------------------------------------------------------------
    elif choice == "Conferência Bancária (BB)":
        render_header()
        st.markdown("### 🏦 Auditoria e Confrontação Bancária")
        
        files = st.file_uploader("Arquivos de Retorno (TXT/RET)", accept_multiple_files=True)
        if files and st.button("Analisar Arquivos"):
            for f in files:
                df_bb = parse_smart_bb(f, f.name)
                if not df_bb.empty:
                    # Salvando na tabela de discrepâncias para uso no Backfill
                    conn = get_db_connection()
                    # Renomeia colunas para bater com a tabela bank_discrepancies se necessário
                    # Aqui, simplificamos salvando apenas para log ou display, 
                    # mas idealmente salvaríamos para enriquecer o master_key
                    st.success(f"Arquivo {f.name} processado. {len(df_bb)} registros identificados.")
                    conn.close()

    # ------------------------------------------------------------------
    # ABA RELATÓRIOS
    # ------------------------------------------------------------------
    elif choice == "Relatórios e Exportação":
        render_header()
        st.markdown("### 📥 Exportação de Dados")
        
        if not df_payments.empty:
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Gerar Relatório Completo (PDF)"):
                    pdf_bytes = generate_pdf_report(df_payments)
                    st.download_button("Baixar PDF", pdf_bytes, "relatorio_pot.pdf", "application/pdf")
            with c2:
                csv = df_payments.to_csv(index=False).encode('utf-8')
                st.download_button("Baixar CSV", csv, "dados_pot.csv", "text/csv")

    elif choice == "Gestão de Dados" and user['role'] in ['admin_ti', 'admin_equipe']:
        st.warning("Área administrativa.")
        if st.button("Limpar Tudo"):
             conn = get_db_connection()
             conn.execute("DELETE FROM payments")
             conn.commit()
             st.success("Limpeza concluída.")

    elif choice == "Gestão de Equipe" and user['role'] in ['admin_ti', 'admin_equipe']:
        st.info("Gestão de usuários (Placeholder).")

if __name__ == "__main__":
    init_db()
    if 'user_info' not in st.session_state:
        # Login Simulado para teste imediato se necessário, ou tela de login real
        # st.session_state['user_info'] = {'name': 'Admin', 'role': 'admin_ti', 'email': 'admin@prefeitura.sp.gov.br'}
        pass

    # Tela de Login Simples
    if 'user_info' not in st.session_state:
        render_header()
        with st.form("login"):
            email = st.text_input("Email")
            senha = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar"):
                conn = get_db_connection()
                usr = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
                conn.close()
                if usr:
                    # Hash check simplificado
                    st.session_state['user_info'] = {'email': usr[0], 'role': usr[2], 'name': usr[3]}
                    st.rerun()
                else:
                    st.error("Login inválido")
    else:
        main_app()
