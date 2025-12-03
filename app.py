# app.py - SISTEMA POT SMDET - GESTÃO DE BENEFÍCIOS
import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import os
import re
import json
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from fpdf import FPDF
import hashlib
import tempfile
import sys

# ========== CONFIGURAÇÃO ==========
st.set_page_config(
    page_title="Sistema POT - Gestão de Benefícios",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========== BANCO DE DADOS ==========
def init_database():
    """Inicializa o banco de dados SQLite"""
    try:
        conn = sqlite3.connect('pot_beneficios.db', check_same_thread=False)
        
        # Tabela de beneficiários
        conn.execute('''
            CREATE TABLE IF NOT EXISTS beneficiarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cpf TEXT UNIQUE,
                nome TEXT,
                rg TEXT,
                projeto TEXT,
                data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabela de contas/benefícios
        conn.execute('''
            CREATE TABLE IF NOT EXISTS contas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                numero_conta TEXT UNIQUE,
                cpf_beneficiario TEXT,
                banco TEXT,
                agencia TEXT,
                status TEXT DEFAULT 'ATIVA',
                data_abertura DATE,
                FOREIGN KEY (cpf_beneficiario) REFERENCES beneficiarios(cpf)
            )
        ''')
        
        # Tabela de pagamentos (histórico acumulado)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS pagamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                numero_conta TEXT,
                cpf_beneficiario TEXT,
                mes_referencia INTEGER,
                ano_referencia INTEGER,
                valor_beneficio DECIMAL(10,2),
                data_pagamento DATE,
                projeto TEXT,
                arquivo_origem TEXT,
                data_importacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (numero_conta) REFERENCES contas(numero_conta),
                FOREIGN KEY (cpf_beneficiario) REFERENCES beneficiarios(cpf)
            )
        ''')
        
        # Tabela de arquivos processados
        conn.execute('''
            CREATE TABLE IF NOT EXISTS arquivos_processados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome_arquivo TEXT,
                mes_referencia INTEGER,
                ano_referencia INTEGER,
                tipo_arquivo TEXT,
                total_registros INTEGER,
                valor_total DECIMAL(10,2),
                data_processamento TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                hash_arquivo TEXT UNIQUE
            )
        ''')
        
        # Tabela de métricas mensais
        conn.execute('''
            CREATE TABLE IF NOT EXISTS metricas_mensais (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mes INTEGER,
                ano INTEGER,
                total_beneficiarios INTEGER,
                total_contas INTEGER,
                total_pagamentos INTEGER,
                valor_total_pago DECIMAL(15,2),
                projetos_ativos INTEGER,
                data_calculo TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(mes, ano)
            )
        ''')
        
        conn.commit()
        return conn
        
    except Exception as e:
        st.error(f"Erro ao inicializar banco: {str(e)}")
        return None

# ========== NORMALIZAÇÃO DE DADOS ==========
def normalizar_nome_coluna(nome_coluna):
    """Normaliza nomes de colunas removendo inconsistências"""
    if not isinstance(nome_coluna, str):
        nome_coluna = str(nome_coluna)
    
    # Dicionário de mapeamento para nomes comuns
    mapeamento = {
        # Número da conta/cartão
        'num cartao': 'numero_conta',
        'numcartao': 'numero_conta',
        'n_cartao': 'numero_conta',
        'cartao': 'numero_conta',
        'numcartão': 'numero_conta',
        'n_cartão': 'numero_conta',
        
        # Nome do beneficiário
        'nome': 'nome',
        'nome do beneficiário': 'nome',
        'nome do beneficiario': 'nome',
        'nome do benefici?io': 'nome',  # Corrige problema de encoding
        'nome do beneficiário': 'nome',
        'beneficiario': 'nome',
        'beneficiário': 'nome',
        
        # Valor
        'valor': 'valor',
        'valor pagto': 'valor',
        'valor_pagto': 'valor',
        'valorpagto': 'valor',
        'valor total': 'valor',
        'valortotal': 'valor',
        'valor pagamento': 'valor',
        'valor_pagamento': 'valor',
        'valor pago': 'valor',
        
        # Data
        'data pagto': 'data_pagamento',
        'datapagto': 'data_pagamento',
        'data pagamento': 'data_pagamento',
        'data_pagamento': 'data_pagamento',
        'data': 'data_pagamento',
        
        # CPF
        'cpf': 'cpf',
        
        # Projeto
        'projeto': 'projeto',
        
        # Agência
        'agencia': 'agencia',
        'agência': 'agencia',
        
        # RG
        'rg': 'rg',
        
        # Dias
        'dias validos': 'dias_validos',
        'dias a pagar': 'dias_a_pagar',
        'dias': 'dias',
        
        # Valor por dia
        'valor dia': 'valor_dia',
        'valordia': 'valor_dia',
    }
    
    # Limpar o nome
    nome_limpo = nome_coluna.strip().lower()
    nome_limpo = re.sub(r'\s+', ' ', nome_limpo)  # Remove espaços múltiplos
    nome_limpo = nome_limpo.replace('?', 'a')  # Corrige encoding
    
    # Aplicar mapeamento
    return mapeamento.get(nome_limpo, nome_limpo.replace(' ', '_'))

def processar_cpf(cpf):
    """Limpa e formata CPF"""
    if pd.isna(cpf) or str(cpf).strip() in ['', 'nan', 'None', 'NaN']:
        return None
    
    # Remove tudo que não é número
    cpf_limpo = re.sub(r'\D', '', str(cpf))
    
    # Verifica se tem 11 dígitos
    if len(cpf_limpo) == 11:
        return cpf_limpo
    elif len(cpf_limpo) > 11:
        return cpf_limpo[:11]
    else:
        # CPF incompleto, retorna None
        return None

def processar_valor(valor):
    """Converte valor para numérico"""
    if pd.isna(valor):
        return 0.0
    
    try:
        # Remove R$, pontos e vírgulas
        valor_str = str(valor).replace('R$', '').replace('$', '').strip()
        valor_str = valor_str.replace('.', '').replace(',', '.')
        
        # Tenta converter para float
        return float(valor_str)
    except:
        return 0.0

def processar_data(data_str):
    """Converte data para formato padrão"""
    if pd.isna(data_str) or str(data_str).strip() in ['', 'nan', 'None']:
        return None
    
    try:
        # Tenta diferentes formatos
        formatos = ['%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%d/%m/%y', '%d-%m-%y']
        
        for fmt in formatos:
            try:
                return datetime.strptime(str(data_str).strip(), fmt).date()
            except:
                continue
        
        # Se não conseguir, retorna None
        return None
    except:
        return None

# ========== PROCESSAMENTO DE ARQUIVOS ==========
def detectar_mes_ano_arquivo(nome_arquivo):
    """Detecta mês e ano do nome do arquivo"""
    nome_upper = nome_arquivo.upper()
    
    meses = {
        'JANEIRO': 1, 'JAN': 1,
        'FEVEREIRO': 2, 'FEV': 2,
        'MARÇO': 3, 'MARCO': 3, 'MAR': 3,
        'ABRIL': 4, 'ABR': 4,
        'MAIO': 5, 'MAI': 5,
        'JUNHO': 6, 'JUN': 6,
        'JULHO': 7, 'JUL': 7,
        'AGOSTO': 8, 'AGO': 8,
        'SETEMBRO': 9, 'SET': 9,
        'OUTUBRO': 10, 'OUT': 10,
        'NOVEMBRO': 11, 'NOV': 11,
        'DEZEMBRO': 12, 'DEZ': 12
    }
    
    # Procura pelo mês no nome
    mes = None
    for mes_nome, mes_num in meses.items():
        if mes_nome in nome_upper:
            mes = mes_num
            break
    
    # Procura pelo ano (4 dígitos)
    ano_match = re.search(r'(20\d{2})', nome_arquivo)
    ano = int(ano_match.group(1)) if ano_match else datetime.now().year
    
    return mes, ano

def calcular_hash_arquivo(conteudo):
    """Calcula hash do arquivo para evitar duplicatas"""
    return hashlib.md5(conteudo).hexdigest()

def processar_planilha(uploaded_file, mes_manual=None, ano_manual=None):
    """Processa uma planilha de pagamentos"""
    try:
        # Detectar mês e ano
        mes, ano = detectar_mes_ano_arquivo(uploaded_file.name)
        
        # Usar valores manuais se fornecidos
        if mes_manual:
            mes = mes_manual
        if ano_manual:
            ano = ano_manual
        
        if not mes or not ano:
            return None, "Não foi possível detectar mês/ano do arquivo"
        
        # Ler arquivo
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file, sep=';', encoding='latin-1', dtype=str)
        elif uploaded_file.name.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(uploaded_file, dtype=str)
        else:
            return None, "Formato de arquivo não suportado"
        
        if df.empty:
            return None, "Arquivo vazio"
        
        # Normalizar cabeçalhos
        df.columns = [normalizar_nome_coluna(col) for col in df.columns]
        
        # Verificar colunas mínimas necessárias
        colunas_necessarias = ['numero_conta', 'nome', 'valor']
        colunas_faltantes = [col for col in colunas_necessarias if col not in df.columns]
        
        if colunas_faltantes:
            return None, f"Colunas faltantes: {', '.join(colunas_faltantes)}"
        
        # Processar dados
        dados_processados = []
        
        for _, row in df.iterrows():
            # Processar CPF se existir
            cpf = processar_cpf(row.get('cpf', ''))
            
            # Processar valor
            valor = processar_valor(row.get('valor', 0))
            
            # Processar data se existir
            data_pagamento = processar_data(row.get('data_pagamento', ''))
            if not data_pagamento:
                # Se não tem data, usa primeiro dia do mês de referência
                data_pagamento = datetime(ano, mes, 1).date()
            
            # Criar registro processado
            registro = {
                'numero_conta': str(row.get('numero_conta', '')).strip(),
                'nome': str(row.get('nome', '')).strip().title(),
                'cpf': cpf,
                'valor': valor,
                'data_pagamento': data_pagamento,
                'projeto': str(row.get('projeto', '')).strip(),
                'agencia': str(row.get('agencia', '')).strip(),
                'rg': str(row.get('rg', '')).strip(),
                'mes_referencia': mes,
                'ano_referencia': ano,
                'arquivo_origem': uploaded_file.name
            }
            
            # Remover campos vazios
            registro = {k: v for k, v in registro.items() if v not in [None, '', 'nan', 'NaN']}
            
            if registro['numero_conta'] and registro['valor'] > 0:
                dados_processados.append(registro)
        
        return dados_processados, f"Processado: {len(dados_processados)} registros"
        
    except Exception as e:
        return None, f"Erro ao processar arquivo: {str(e)}"

# ========== GESTÃO DO BANCO DE DADOS ==========
def salvar_dados_banco(conn, dados_processados, hash_arquivo):
    """Salva dados processados no banco"""
    try:
        cursor = conn.cursor()
        
        # Verificar se arquivo já foi processado
        cursor.execute("SELECT id FROM arquivos_processados WHERE hash_arquivo = ?", (hash_arquivo,))
        if cursor.fetchone():
            return False, "Este arquivo já foi processado anteriormente"
        
        # Para cada registro, atualizar/inserir no banco
        total_valor = 0
        contas_processadas = set()
        
        for registro in dados_processados:
            # 1. Verificar/inserir beneficiário
            if registro.get('cpf'):
                cursor.execute('''
                    INSERT OR IGNORE INTO beneficiarios (cpf, nome, rg, projeto)
                    VALUES (?, ?, ?, ?)
                ''', (registro['cpf'], registro['nome'], registro.get('rg'), registro.get('projeto')))
            
            # 2. Verificar/inserir conta
            cursor.execute('''
                INSERT OR IGNORE INTO contas (numero_conta, cpf_beneficiario, agencia, status)
                VALUES (?, ?, ?, 'ATIVA')
            ''', (registro['numero_conta'], registro.get('cpf'), registro.get('agencia')))
            
            # 3. Inserir pagamento
            cursor.execute('''
                INSERT INTO pagamentos 
                (numero_conta, cpf_beneficiario, mes_referencia, ano_referencia, 
                 valor_beneficio, data_pagamento, projeto, arquivo_origem)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                registro['numero_conta'],
                registro.get('cpf'),
                registro['mes_referencia'],
                registro['ano_referencia'],
                registro['valor'],
                registro['data_pagamento'],
                registro.get('projeto'),
                registro['arquivo_origem']
            ))
            
            total_valor += registro['valor']
            contas_processadas.add(registro['numero_conta'])
        
        # Registrar processamento do arquivo
        cursor.execute('''
            INSERT INTO arquivos_processados 
            (nome_arquivo, mes_referencia, ano_referencia, tipo_arquivo, 
             total_registros, valor_total, hash_arquivo)
            VALUES (?, ?, ?, 'PAGAMENTO', ?, ?, ?)
        ''', (
            dados_processados[0]['arquivo_origem'] if dados_processados else '',
            dados_processados[0]['mes_referencia'] if dados_processados else 0,
            dados_processados[0]['ano_referencia'] if dados_processados else 0,
            len(dados_processados),
            total_valor,
            hash_arquivo
        ))
        
        conn.commit()
        
        # Atualizar métricas
        atualizar_metricas_mensais(conn, dados_processados[0]['mes_referencia'], dados_processados[0]['ano_referencia'])
        
        return True, f"Salvo: {len(dados_processados)} registros, R$ {total_valor:,.2f}"
        
    except Exception as e:
        conn.rollback()
        return False, f"Erro ao salvar no banco: {str(e)}"

def atualizar_metricas_mensais(conn, mes, ano):
    """Atualiza métricas mensais"""
    try:
        cursor = conn.cursor()
        
        # Calcular totais do mês
        cursor.execute('''
            SELECT 
                COUNT(DISTINCT cpf_beneficiario) as total_beneficiarios,
                COUNT(DISTINCT numero_conta) as total_contas,
                COUNT(*) as total_pagamentos,
                SUM(valor_beneficio) as valor_total_pago,
                COUNT(DISTINCT projeto) as projetos_ativos
            FROM pagamentos 
            WHERE mes_referencia = ? AND ano_referencia = ?
        ''', (mes, ano))
        
        resultado = cursor.fetchone()
        
        # Inserir ou atualizar métricas
        cursor.execute('''
            INSERT OR REPLACE INTO metricas_mensais 
            (mes, ano, total_beneficiarios, total_contas, total_pagamentos, 
             valor_total_pago, projetos_ativos)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (mes, ano, *resultado))
        
        conn.commit()
        
    except Exception as e:
        st.error(f"Erro ao atualizar métricas: {str(e)}")

# ========== CONSULTAS E RELATÓRIOS ==========
def obter_resumo_mensal(conn, mes=None, ano=None):
    """Obtém resumo mensal"""
    try:
        if mes and ano:
            cursor = conn.execute('''
                SELECT * FROM metricas_mensais 
                WHERE mes = ? AND ano = ?
            ''', (mes, ano))
        else:
            cursor = conn.execute('''
                SELECT * FROM metricas_mensais 
                ORDER BY ano DESC, mes DESC
            ''')
        
        colunas = [desc[0] for desc in cursor.description]
        dados = cursor.fetchall()
        
        return pd.DataFrame(dados, columns=colunas)
        
    except Exception as e:
        st.error(f"Erro ao obter resumo: {str(e)}")
        return pd.DataFrame()

def obter_historico_beneficiario(conn, cpf=None, numero_conta=None):
    """Obtém histórico de um beneficiário"""
    try:
        query = '''
            SELECT 
                p.mes_referencia || '/' || p.ano_referencia as periodo,
                p.valor_beneficio,
                p.data_pagamento,
                p.projeto,
                p.arquivo_origem,
                b.nome,
                b.rg,
                c.agencia
            FROM pagamentos p
            LEFT JOIN beneficiarios b ON p.cpf_beneficiario = b.cpf
            LEFT JOIN contas c ON p.numero_conta = c.numero_conta
        '''
        
        params = []
        if cpf:
            query += ' WHERE p.cpf_beneficiario = ?'
            params.append(cpf)
        elif numero_conta:
            query += ' WHERE p.numero_conta = ?'
            params.append(numero_conta)
        
        query += ' ORDER BY p.ano_referencia DESC, p.mes_referencia DESC'
        
        cursor = conn.execute(query, params)
        colunas = [desc[0] for desc in cursor.description]
        dados = cursor.fetchall()
        
        return pd.DataFrame(dados, columns=colunas)
        
    except Exception as e:
        st.error(f"Erro ao obter histórico: {str(e)}")
        return pd.DataFrame()

def obter_arquivos_processados(conn):
    """Lista arquivos já processados"""
    try:
        cursor = conn.execute('''
            SELECT 
                nome_arquivo,
                mes_referencia,
                ano_referencia,
                total_registros,
                valor_total,
                data_processamento
            FROM arquivos_processados 
            ORDER BY data_processamento DESC
        ''')
        
        colunas = [desc[0] for desc in cursor.description]
        dados = cursor.fetchall()
        
        return pd.DataFrame(dados, columns=colunas)
        
    except Exception as e:
        st.error(f"Erro ao obter arquivos: {str(e)}")
        return pd.DataFrame()

# ========== INTERFACE STREAMLIT ==========
def mostrar_dashboard(conn):
    """Mostra dashboard principal"""
    st.title("💰 Sistema POT - Gestão de Benefícios")
    st.markdown("---")
    
    # Métricas gerais
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        cursor = conn.execute("SELECT COUNT(DISTINCT cpf) FROM beneficiarios")
        total_benef = cursor.fetchone()[0] or 0
        st.metric("Beneficiários Cadastrados", f"{total_benef:,}")
    
    with col2:
        cursor = conn.execute("SELECT COUNT(*) FROM contas")
        total_contas = cursor.fetchone()[0] or 0
        st.metric("Contas Ativas", f"{total_contas:,}")
    
    with col3:
        cursor = conn.execute("SELECT COUNT(*) FROM pagamentos")
        total_pag = cursor.fetchone()[0] or 0
        st.metric("Pagamentos Registrados", f"{total_pag:,}")
    
    with col4:
        cursor = conn.execute("SELECT SUM(valor_beneficio) FROM pagamentos")
        total_valor = cursor.fetchone()[0] or 0
        st.metric("Valor Total Pago", f"R$ {total_valor:,.2f}")
    
    st.markdown("---")
    
    # Resumo por mês
    st.subheader("📊 Resumo por Mês")
    df_resumo = obter_resumo_mensal(conn)
    
    if not df_resumo.empty:
        # Gráfico de valores mensais
        fig = px.bar(
            df_resumo, 
            x='mes', 
            y='valor_total_pago',
            color='ano',
            title="Valor Total Pago por Mês",
            labels={'mes': 'Mês', 'valor_total_pago': 'Valor Total (R$)'}
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Tabela de resumo
        st.dataframe(
            df_resumo.sort_values(['ano', 'mes'], ascending=[False, False]),
            use_container_width=True
        )
    else:
        st.info("Nenhum dado processado ainda. Importe arquivos para começar.")

def mostrar_importacao(conn):
    """Interface de importação de arquivos"""
    st.header("📤 Importar Arquivos de Pagamento")
    
    with st.form("import_form"):
        # Upload de arquivo
        uploaded_file = st.file_uploader(
            "Selecione o arquivo (CSV ou Excel)",
            type=['csv', 'xls', 'xlsx']
        )
        
        # Seleção manual de mês/ano (opcional)
        col1, col2 = st.columns(2)
        with col1:
            meses = ['', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
            mes_selecionado = st.selectbox("Mês (se não detectado)", meses)
            mes_num = meses.index(mes_selecionado) if mes_selecionado else None
        
        with col2:
            ano_atual = datetime.now().year
            anos = list(range(ano_atual, ano_atual - 5, -1))
            ano_selecionado = st.selectbox("Ano (se não detectado)", [""] + anos)
        
        submit = st.form_submit_button("Processar Arquivo")
        
        if submit and uploaded_file:
            with st.spinner("Processando arquivo..."):
                # Ler conteúdo para hash
                conteudo = uploaded_file.getvalue()
                hash_arquivo = calcular_hash_arquivo(conteudo)
                
                # Processar planilha
                dados_processados, mensagem = processar_planilha(
                    uploaded_file, 
                    mes_num if mes_num else None,
                    int(ano_selecionado) if ano_selecionado else None
                )
                
                if dados_processados:
                    # Mostrar preview
                    st.subheader("📋 Pré-visualização dos Dados")
                    df_preview = pd.DataFrame(dados_processados[:10])
                    st.dataframe(df_preview, use_container_width=True)
                    
                    # Confirmar importação
                    if st.button("✅ Confirmar Importação", type="primary"):
                        sucesso, msg = salvar_dados_banco(conn, dados_processados, hash_arquivo)
                        
                        if sucesso:
                            st.success(msg)
                            st.balloons()
                        else:
                            st.error(msg)
                else:
                    st.error(f"❌ {mensagem}")

def mostrar_consultas(conn):
    """Interface de consultas"""
    st.header("🔍 Consultas e Relatórios")
    
    tab1, tab2, tab3 = st.tabs(["📋 Beneficiários", "📁 Arquivos Processados", "📈 Análises"])
    
    with tab1:
        st.subheader("Consulta por Beneficiário")
        
        col1, col2 = st.columns(2)
        with col1:
            cpf_consulta = st.text_input("CPF (somente números)", placeholder="00000000000")
        with col2:
            conta_consulta = st.text_input("Número da Conta")
        
        if st.button("Buscar Histórico") and (cpf_consulta or conta_consulta):
            df_historico = obter_historico_beneficiario(conn, cpf_consulta, conta_consulta)
            
            if not df_historico.empty:
                # Estatísticas
                total_pago = df_historico['valor_beneficio'].sum()
                meses_ativos = df_historico['periodo'].nunique()
                
                col_a, col_b = st.columns(2)
                with col_a:
                    st.metric("Total Recebido", f"R$ {total_pago:,.2f}")
                with col_b:
                    st.metric("Meses Ativos", meses_ativos)
                
                # Histórico
                st.dataframe(df_historico, use_container_width=True)
                
                # Gráfico
                fig = px.line(
                    df_historico.sort_values('periodo'),
                    x='periodo',
                    y='valor_beneficio',
                    title="Histórico de Pagamentos",
                    markers=True
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Nenhum registro encontrado")
    
    with tab2:
        st.subheader("Arquivos Processados")
        df_arquivos = obter_arquivos_processados(conn)
        
        if not df_arquivos.empty:
            # Estatísticas
            total_arquivos = len(df_arquivos)
            total_registros = df_arquivos['total_registros'].sum()
            total_valor = df_arquivos['valor_total'].sum()
            
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                st.metric("Arquivos Processados", total_arquivos)
            with col_b:
                st.metric("Registros Totais", f"{total_registros:,}")
            with col_c:
                st.metric("Valor Total", f"R$ {total_valor:,.2f}")
            
            # Tabela
            st.dataframe(df_arquivos, use_container_width=True)
        else:
            st.info("Nenhum arquivo processado ainda")
    
    with tab3:
        st.subheader("Análises Avançadas")
        
        # Projetos mais ativos
        cursor = conn.execute('''
            SELECT projeto, COUNT(*) as total_pagamentos, 
                   SUM(valor_beneficio) as valor_total
            FROM pagamentos 
            WHERE projeto IS NOT NULL AND projeto != ''
            GROUP BY projeto 
            ORDER BY total_pagamentos DESC
            LIMIT 10
        ''')
        
        projetos = cursor.fetchall()
        
        if projetos:
            df_projetos = pd.DataFrame(projetos, columns=['Projeto', 'Pagamentos', 'Valor Total'])
            
            # Gráfico de projetos
            fig = px.pie(
                df_projetos,
                values='Valor Total',
                names='Projeto',
                title="Distribuição por Projeto (Top 10)"
            )
            st.plotly_chart(fig, use_container_width=True)
            
            st.dataframe(df_projetos, use_container_width=True)

# ========== FUNÇÃO PRINCIPAL ==========
def main():
    # Inicializar banco
    conn = init_database()
    
    if not conn:
        st.error("Não foi possível conectar ao banco de dados")
        return
    
    # Sidebar
    st.sidebar.title("💰 POT - SMDET")
    st.sidebar.markdown("**Gestão de Benefícios**")
    st.sidebar.markdown("---")
    
    # Menu
    menu = st.sidebar.radio(
        "Navegação",
        ["📊 Dashboard", "📤 Importar Arquivos", "🔍 Consultas", "⚙️ Configurações"]
    )
    
    # Navegação
    if menu == "📊 Dashboard":
        mostrar_dashboard(conn)
    
    elif menu == "📤 Importar Arquivos":
        mostrar_importacao(conn)
    
    elif menu == "🔍 Consultas":
        mostrar_consultas(conn)
    
    elif menu == "⚙️ Configurações":
        st.header("⚙️ Configurações do Sistema")
        
        st.subheader("Limpar Dados")
        st.warning("⚠️ Esta ação não pode ser desfeita!")
        
        if st.button("🔄 Limpar Todos os Dados", type="secondary"):
            try:
                conn.execute("DELETE FROM pagamentos")
                conn.execute("DELETE FROM beneficiarios")
                conn.execute("DELETE FROM contas")
                conn.execute("DELETE FROM arquivos_processados")
                conn.execute("DELETE FROM metricas_mensais")
                conn.commit()
                st.success("✅ Todos os dados foram limpos!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {str(e)}")
        
        st.subheader("Backup do Banco")
        if st.button("💾 Gerar Backup"):
            try:
                backup_data = conn.execute("SELECT * FROM sqlite_master").fetchall()
                st.download_button(
                    label="📥 Download Backup",
                    data=str(backup_data),
                    file_name=f"backup_pot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json"
                )
            except Exception as e:
                st.error(f"Erro ao gerar backup: {str(e)}")
    
    # Fechar conexão
    conn.close()

if __name__ == "__main__":
    main()
