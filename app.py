# app.py - SISTEMA POT SMDET - VERSÃO SIMPLIFICADA E FUNCIONAL
import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import os
import re
from datetime import datetime, timedelta
import plotly.express as px
import hashlib
import warnings
warnings.filterwarnings('ignore')

# ========== CONFIGURAÇÃO ==========
st.set_page_config(
    page_title="Sistema POT - Gestão de Benefícios",
    page_icon="💰",
    layout="wide"
)

# ========== BANCO DE DADOS ==========
def init_database():
    """Inicializa o banco de dados"""
    conn = sqlite3.connect('pot.db', check_same_thread=False)
    
    # Tabela principal
    conn.execute('''
        CREATE TABLE IF NOT EXISTS dados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_importacao DATETIME DEFAULT CURRENT_TIMESTAMP,
            mes INTEGER,
            ano INTEGER,
            conta TEXT,
            cpf TEXT,
            nome TEXT,
            projeto TEXT,
            valor REAL,
            arquivo TEXT,
            status TEXT DEFAULT 'ATIVO'
        )
    ''')
    
    conn.execute('CREATE INDEX IF NOT EXISTS idx_cpf ON dados(cpf)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_conta ON dados(conta)')
    
    conn.commit()
    return conn

# ========== FUNÇÕES PRINCIPAIS ==========
def normalizar_nome(nome):
    """Normaliza nome"""
    if pd.isna(nome):
        return ""
    nome = str(nome).strip().upper()
    nome = re.sub(r'\s+', ' ', nome)
    return nome

def normalizar_cpf(cpf):
    """Normaliza CPF"""
    if pd.isna(cpf):
        return ""
    cpf = str(cpf)
    cpf = re.sub(r'\D', '', cpf)
    return cpf if len(cpf) == 11 else ""

def normalizar_valor(valor):
    """Normaliza valor"""
    if pd.isna(valor):
        return 0.0
    valor = str(valor)
    valor = re.sub(r'[R\$\s]', '', valor)
    valor = valor.replace(',', '.')
    try:
        return float(valor)
    except:
        return 0.0

def detectar_mes_ano(nome_arquivo):
    """Detecta mês e ano do arquivo"""
    nome = nome_arquivo.upper()
    
    meses = {
        'JAN': 1, 'FEV': 2, 'MAR': 3, 'ABR': 4, 'MAI': 5, 'JUN': 6,
        'JUL': 7, 'AGO': 8, 'SET': 9, 'OUT': 10, 'NOV': 11, 'DEZ': 12
    }
    
    # Procurar mês
    mes = None
    for mes_nome, mes_num in meses.items():
        if mes_nome in nome:
            mes = mes_num
            break
    
    # Procurar ano
    ano_match = re.search(r'20\d{2}', nome)
    ano = int(ano_match.group()) if ano_match else datetime.now().year
    
    # Se não encontrou mês, usar atual
    if mes is None:
        mes = datetime.now().month
    
    return mes, ano

def encontrar_coluna(df, possiveis_nomes):
    """Encontra coluna no dataframe"""
    for col in df.columns:
        col_lower = str(col).lower()
        for nome in possiveis_nomes:
            if nome in col_lower:
                return col
    return None

def processar_arquivo_simples(uploaded_file, conn):
    """Processa arquivo de forma simples"""
    try:
        # Ler arquivo
        if uploaded_file.name.lower().endswith('.csv'):
            # Tentar diferentes separadores
            try:
                df = pd.read_csv(uploaded_file, sep=';', dtype=str)
            except:
                try:
                    df = pd.read_csv(uploaded_file, sep=',', dtype=str)
                except:
                    df = pd.read_csv(uploaded_file, engine='python', dtype=str)
        else:
            df = pd.read_excel(uploaded_file, dtype=str)
        
        if df.empty:
            return False, "Arquivo vazio"
        
        # Encontrar colunas
        conta_col = encontrar_coluna(df, ['conta', 'cartao', 'num', 'codigo', 'numero'])
        nome_col = encontrar_coluna(df, ['nome', 'beneficiario'])
        cpf_col = encontrar_coluna(df, ['cpf'])
        valor_col = encontrar_coluna(df, ['valor', 'vlr', 'pagamento'])
        projeto_col = encontrar_coluna(df, ['projeto', 'programa', 'cod'])
        
        if not conta_col or not nome_col or not valor_col:
            return False, "Colunas obrigatórias não encontradas"
        
        # Detectar período
        mes, ano = detectar_mes_ano(uploaded_file.name)
        
        # Processar dados
        cursor = conn.cursor()
        contador = 0
        
        for _, row in df.iterrows():
            try:
                conta = str(row[conta_col]).strip() if conta_col in row else ""
                nome = normalizar_nome(row[nome_col]) if nome_col in row else ""
                cpf = normalizar_cpf(row[cpf_col]) if cpf_col in row else ""
                valor = normalizar_valor(row[valor_col]) if valor_col in row else 0
                projeto = str(row[projeto_col]).strip() if projeto_col in row else ""
                
                if conta and nome and valor > 0:
                    cursor.execute('''
                        INSERT INTO dados (mes, ano, conta, cpf, nome, projeto, valor, arquivo)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (mes, ano, conta, cpf, nome, projeto, valor, uploaded_file.name))
                    contador += 1
            except:
                continue
        
        conn.commit()
        
        if contador > 0:
            # Detectar inconsistências após importação
            detectar_inconsistencias_simples(conn)
            return True, f"Importados {contador} registros de {uploaded_file.name}"
        else:
            return False, "Nenhum registro válido encontrado"
            
    except Exception as e:
        return False, f"Erro: {str(e)}"

def detectar_inconsistencias_simples(conn):
    """Detecta inconsistências básicas"""
    try:
        cursor = conn.cursor()
        
        # CPFs repetidos com nomes diferentes
        cursor.execute('''
            UPDATE dados 
            SET status = 'INCONSISTENTE' 
            WHERE cpf IN (
                SELECT cpf FROM dados 
                WHERE cpf != '' 
                GROUP BY cpf 
                HAVING COUNT(DISTINCT nome) > 1
            )
        ''')
        
        # CPFs repetidos com contas diferentes
        cursor.execute('''
            UPDATE dados 
            SET status = 'INCONSISTENTE' 
            WHERE cpf IN (
                SELECT cpf FROM dados 
                WHERE cpf != '' 
                GROUP BY cpf 
                HAVING COUNT(DISTINCT conta) > 1
            )
        ''')
        
        # Contas repetidas com CPFs diferentes
        cursor.execute('''
            UPDATE dados 
            SET status = 'INCONSISTENTE' 
            WHERE conta IN (
                SELECT conta FROM dados 
                WHERE conta != '' 
                GROUP BY conta 
                HAVING COUNT(DISTINCT cpf) > 1
            )
        ''')
        
        conn.commit()
    except:
        pass

# ========== FUNÇÕES DE RELATÓRIO ==========
def obter_resumo(conn):
    """Obtém resumo dos dados"""
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM dados")
    total = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(DISTINCT nome) FROM dados")
    beneficiarios = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(DISTINCT cpf) FROM dados WHERE cpf != ''")
    cpfs = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(DISTINCT conta) FROM dados")
    contas = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT SUM(valor) FROM dados")
    valor_total = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM dados WHERE status = 'INCONSISTENTE'")
    inconsist = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(DISTINCT arquivo) FROM dados")
    arquivos = cursor.fetchone()[0] or 0
    
    return {
        'total': total,
        'beneficiarios': beneficiarios,
        'cpfs': cpfs,
        'contas': contas,
        'valor': valor_total,
        'inconsistencias': inconsist,
        'arquivos': arquivos
    }

def obter_evolucao(conn):
    """Obtém evolução mensal"""
    cursor = conn.cursor()
    cursor.execute('''
        SELECT ano, mes, COUNT(*) as registros, SUM(valor) as valor, COUNT(DISTINCT nome) as beneficiarios
        FROM dados
        WHERE ano IS NOT NULL AND mes IS NOT NULL
        GROUP BY ano, mes
        ORDER BY ano, mes
        LIMIT 12
    ''')
    
    rows = cursor.fetchall()
    if rows:
        df = pd.DataFrame(rows, columns=['ano', 'mes', 'registros', 'valor', 'beneficiarios'])
        df['periodo'] = df['mes'].astype(str).str.zfill(2) + '/' + df['ano'].astype(str)
        return df
    return pd.DataFrame()

def obter_inconsistencias(conn):
    """Obtém detalhes das inconsistências"""
    cursor = conn.cursor()
    cursor.execute('''
        SELECT cpf, nome, conta, COUNT(*) as ocorrencias, GROUP_CONCAT(DISTINCT arquivo) as arquivos
        FROM dados
        WHERE status = 'INCONSISTENTE'
        GROUP BY cpf, nome, conta
        ORDER BY ocorrencias DESC
        LIMIT 50
    ''')
    
    rows = cursor.fetchall()
    if rows:
        return pd.DataFrame(rows, columns=['CPF', 'Nome', 'Conta', 'Ocorrências', 'Arquivos'])
    return pd.DataFrame()

def obter_top_beneficiarios(conn):
    """Obtém top beneficiários"""
    cursor = conn.cursor()
    cursor.execute('''
        SELECT nome, cpf, COUNT(*) as pagamentos, SUM(valor) as total, AVG(valor) as media
        FROM dados
        WHERE nome != ''
        GROUP BY nome, cpf
        ORDER BY total DESC
        LIMIT 15
    ''')
    
    rows = cursor.fetchall()
    if rows:
        return pd.DataFrame(rows, columns=['Nome', 'CPF', 'Pagamentos', 'Total', 'Média'])
    return pd.DataFrame()

# ========== INTERFACE ==========
def main():
    # Inicializar banco
    conn = init_database()
    
    # Título
    st.title("💰 SISTEMA POT - Gestão de Benefícios")
    st.markdown("---")
    
    # SEÇÃO 1: UPLOAD DE ARQUIVOS
    st.header("📤 Importar Arquivos")
    
    # Container para upload
    with st.container():
        st.info("Arraste ou selecione arquivos CSV ou Excel")
        
        # Upload múltiplo com ID único
        uploaded_files = st.file_uploader(
            " ",
            type=['csv', 'xlsx', 'xls'],
            accept_multiple_files=True,
            key="file_uploader_main"
        )
        
        if uploaded_files:
            st.success(f"{len(uploaded_files)} arquivo(s) selecionado(s)")
            
            # Processar cada arquivo
            for i, uploaded_file in enumerate(uploaded_files):
                col1, col2, col3 = st.columns([3, 1, 1])
                
                with col1:
                    st.write(f"**{uploaded_file.name}**")
                
                with col2:
                    # Botão com ID único baseado no índice
                    if st.button("📊 Prévia", key=f"preview_{i}"):
                        try:
                            if uploaded_file.name.lower().endswith('.csv'):
                                df_temp = pd.read_csv(uploaded_file, nrows=5)
                            else:
                                df_temp = pd.read_excel(uploaded_file, nrows=5)
                            
                            st.write("Prévia dos dados:")
                            st.dataframe(df_temp)
                        except:
                            st.error("Erro ao ler arquivo")
                
                with col3:
                    # Botão com ID único baseado no índice
                    if st.button("🔄 Importar", key=f"import_{i}", type="primary"):
                        with st.spinner(f"Processando {uploaded_file.name}..."):
                            sucesso, mensagem = processar_arquivo_simples(uploaded_file, conn)
                        
                        if sucesso:
                            st.success(mensagem)
                            st.rerun()
                        else:
                            st.error(mensagem)
            
            # Botão para processar todos
            if st.button("🔄 IMPORTAR TODOS", type="primary", use_container_width=True, key="import_all"):
                resultados = []
                for uploaded_file in uploaded_files:
                    with st.spinner(f"Processando {uploaded_file.name}..."):
                        sucesso, mensagem = processar_arquivo_simples(uploaded_file, conn)
                        resultados.append((uploaded_file.name, sucesso, mensagem))
                
                st.write("Resultados:")
                for nome, sucesso, msg in resultados:
                    if sucesso:
                        st.success(f"✅ {nome}: {msg}")
                    else:
                        st.error(f"❌ {nome}: {msg}")
                
                st.rerun()
    
    st.markdown("---")
    
    # SEÇÃO 2: RESUMO
    st.header("📊 Resumo dos Dados")
    
    resumo = obter_resumo(conn)
    
    # Métricas
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Registros", f"{resumo['total']:,}")
        st.caption(f"Beneficiários: {resumo['beneficiarios']:,}")
    
    with col2:
        st.metric("Valor Total", f"R$ {resumo['valor']:,.2f}")
        st.caption(f"Contas: {resumo['contas']:,}")
    
    with col3:
        st.metric("CPFs Únicos", f"{resumo['cpfs']:,}")
        st.caption(f"Arquivos: {resumo['arquivos']:,}")
    
    with col4:
        st.metric("Inconsistências", f"{resumo['inconsistencias']:,}")
        st.caption("Detectadas")
    
    st.markdown("---")
    
    # SEÇÃO 3: ANÁLISES
    st.header("📈 Análises")
    
    tab1, tab2, tab3 = st.tabs(["📅 Evolução Mensal", "⚠️ Inconsistências", "👥 Top Beneficiários"])
    
    with tab1:
        st.subheader("Evolução Mensal")
        
        df_evo = obter_evolucao(conn)
        if not df_evo.empty:
            # Gráfico
            fig = px.line(df_evo, x='periodo', y='valor', 
                         title='Valor Total por Mês', markers=True)
            st.plotly_chart(fig, use_container_width=True)
            
            # Tabela
            st.dataframe(
                df_evo[['periodo', 'registros', 'beneficiarios', 'valor']],
                column_config={
                    'valor': st.column_config.NumberColumn('Valor (R$)', format="R$ %.2f")
                }
            )
        else:
            st.info("Nenhum dado disponível")
    
    with tab2:
        st.subheader("Inconsistências Detectadas")
        
        df_inc = obter_inconsistencias(conn)
        if not df_inc.empty:
            # Tipos de inconsistências
            tipos = {}
            for _, row in df_inc.iterrows():
                cpf = row['CPF']
                if cpf:
                    # Verificar se é CPF com nomes diferentes
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(DISTINCT nome) FROM dados WHERE cpf = ?", (cpf,))
                    nomes_diff = cursor.fetchone()[0] > 1
                    
                    # Verificar se é CPF com contas diferentes
                    cursor.execute("SELECT COUNT(DISTINCT conta) FROM dados WHERE cpf = ?", (cpf,))
                    contas_diff = cursor.fetchone()[0] > 1
                    
                    if nomes_diff and contas_diff:
                        tipos[cpf] = "CPF com nomes E contas diferentes"
                    elif nomes_diff:
                        tipos[cpf] = "CPF com nomes diferentes"
                    elif contas_diff:
                        tipos[cpf] = "CPF com contas diferentes"
            
            # Mostrar tipos
            if tipos:
                st.warning("Tipos de inconsistências encontradas:")
                for cpf, tipo in list(tipos.items())[:10]:
                    st.write(f"• **{cpf}**: {tipo}")
            
            # Tabela detalhada
            st.dataframe(df_inc)
            
            # Botão para limpar
            if st.button("🗑️ Limpar Inconsistências", key="clear_incons"):
                cursor = conn.cursor()
                cursor.execute("UPDATE dados SET status = 'ATIVO' WHERE status = 'INCONSISTENTE'")
                conn.commit()
                st.success("Inconsistências limpas!")
                st.rerun()
        else:
            st.success("✅ Nenhuma inconsistência encontrada!")
    
    with tab3:
        st.subheader("Top Beneficiários")
        
        df_top = obter_top_beneficiarios(conn)
        if not df_top.empty:
            # Gráfico
            fig = px.bar(df_top.head(10), x='Nome', y='Total',
                        title='Top 10 Beneficiários por Valor',
                        color='Pagamentos')
            st.plotly_chart(fig, use_container_width=True)
            
            # Tabela
            st.dataframe(
                df_top,
                column_config={
                    'Total': st.column_config.NumberColumn('Total (R$)', format="R$ %.2f"),
                    'Média': st.column_config.NumberColumn('Média (R$)', format="R$ %.2f")
                }
            )
        else:
            st.info("Nenhum beneficiário registrado")
    
    st.markdown("---")
    
    # SEÇÃO 4: FERRAMENTAS
    st.header("🔧 Ferramentas")
    
    col_t1, col_t2 = st.columns(2)
    
    with col_t1:
        if st.button("📥 Exportar Dados", key="export_data", use_container_width=True):
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM dados")
            dados = cursor.fetchall()
            
            if dados:
                colunas = [desc[0] for desc in cursor.description]
                df_export = pd.DataFrame(dados, columns=colunas)
                
                # Converter para CSV
                csv = df_export.to_csv(index=False, sep=';')
                
                st.download_button(
                    label="💾 Baixar CSV",
                    data=csv,
                    file_name=f"dados_pot_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    key="download_csv"
                )
            else:
                st.warning("Nenhum dado para exportar")
    
    with col_t2:
        if st.button("🔄 Atualizar Análises", key="refresh_anal", use_container_width=True):
            detectar_inconsistencias_simples(conn)
            st.success("Análises atualizadas!")
            st.rerun()
    
    # Rodapé
    st.markdown("---")
    st.caption(f"💰 Sistema POT | {datetime.now().strftime('%d/%m/%Y')} | {resumo['total']} registros")
    
    conn.close()

if __name__ == "__main__":
    main()
