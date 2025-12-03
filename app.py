# app.py - SISTEMA POT SMDET - VERSÃO PRÁTICA E FUNCIONAL
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
import hashlib
import tempfile
import warnings
from io import BytesIO
warnings.filterwarnings('ignore')

# ========== CONFIGURAÇÃO ==========
st.set_page_config(
    page_title="Sistema POT - Gestão Prática de Benefícios",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========== BANCO DE DADOS SIMPLIFICADO ==========
def init_database():
    """Inicializa o banco de dados de forma robusta"""
    try:
        conn = sqlite3.connect('pot_funcional.db', check_same_thread=False, timeout=10)
        
        # TABELA ÚNICA DE BENEFICIÁRIOS E PAGAMENTOS
        conn.execute('''
            CREATE TABLE IF NOT EXISTS dados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_importacao DATETIME DEFAULT CURRENT_TIMESTAMP,
                mes_referencia INTEGER,
                ano_referencia INTEGER,
                numero_conta TEXT,
                cpf TEXT,
                nome TEXT,
                nome_normalizado TEXT,
                projeto TEXT,
                valor_bruto REAL,
                valor_liquido REAL,
                valor_desconto REAL DEFAULT 0,
                dias_trabalhados INTEGER DEFAULT 20,
                valor_diario REAL,
                arquivo_origem TEXT,
                tipo_arquivo TEXT,
                status TEXT DEFAULT 'ATIVO',
                
                -- Para controle de inconsistências
                cpf_repetido BOOLEAN DEFAULT 0,
                nome_diferente BOOLEAN DEFAULT 0,
                conta_diferente BOOLEAN DEFAULT 0,
                inconsistencia TEXT
            )
        ''')
        
        # Índices para performance
        conn.execute('CREATE INDEX IF NOT EXISTS idx_cpf ON dados(cpf)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_conta ON dados(numero_conta)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_periodo ON dados(ano_referencia, mes_referencia)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_nome ON dados(nome_normalizado)')
        
        conn.commit()
        return conn
        
    except Exception as e:
        st.error(f"❌ Erro no banco de dados: {str(e)}")
        return None

# ========== FUNÇÕES DE PROCESSAMENTO ==========
def normalizar_nome(nome):
    """Normaliza nome para comparação"""
    if pd.isna(nome) or nome == '':
        return ''
    
    nome = str(nome).strip().upper()
    
    # Remove acentos
    substituicoes = {
        'Á': 'A', 'À': 'A', 'Â': 'A', 'Ã': 'A',
        'É': 'E', 'È': 'E', 'Ê': 'E', 'Ë': 'E',
        'Í': 'I', 'Ì': 'I', 'Î': 'I', 'Ï': 'I',
        'Ó': 'O', 'Ò': 'O', 'Ô': 'O', 'Õ': 'O', 'Ö': 'O',
        'Ú': 'U', 'Ù': 'U', 'Û': 'U', 'Ü': 'U',
        'Ç': 'C', 'Ñ': 'N'
    }
    
    for char, subst in substituicoes.items():
        nome = nome.replace(char, subst)
    
    # Remove espaços extras
    nome = re.sub(r'\s+', ' ', nome)
    
    return nome

def normalizar_cpf(cpf):
    """Normaliza CPF (só números)"""
    if pd.isna(cpf) or cpf == '':
        return ''
    
    cpf_str = str(cpf)
    # Remove tudo que não é número
    cpf_limpo = re.sub(r'\D', '', cpf_str)
    
    # Se não tem 11 dígitos, retorna vazio
    if len(cpf_limpo) != 11:
        return ''
    
    return cpf_limpo

def normalizar_valor(valor):
    """Converte qualquer formato para float"""
    if pd.isna(valor) or valor == '':
        return 0.0
    
    valor_str = str(valor).strip()
    
    # Remove R$, $ e espaços
    valor_str = re.sub(r'[R\$\s]', '', valor_str)
    
    # Substitui vírgula por ponto para decimal
    valor_str = valor_str.replace(',', '.')
    
    # Remove múltiplos pontos (mantém apenas o último como decimal)
    if valor_str.count('.') > 1:
        partes = valor_str.split('.')
        valor_str = ''.join(partes[:-1]) + '.' + partes[-1]
    
    try:
        return float(valor_str)
    except:
        return 0.0

def detectar_mes_ano(nome_arquivo, df=None):
    """Detecta mês e ano do arquivo"""
    nome = nome_arquivo.upper()
    
    # Mapeamento de meses
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
    
    # 1. Tentar pelo nome do arquivo
    mes = None
    for mes_nome, mes_num in meses.items():
        if mes_nome in nome:
            mes = mes_num
            break
    
    # 2. Tentar extrair ano do nome (4 dígitos começando com 20)
    ano_match = re.search(r'(20\d{2})', nome)
    ano = int(ano_match.group(1)) if ano_match else datetime.now().year
    
    # 3. Se não encontrou mês, usar atual
    if mes is None:
        mes = datetime.now().month
    
    return mes, ano

def detectar_colunas(df):
    """Detecta automaticamente as colunas importantes"""
    colunas = {}
    
    # Padrões para cada tipo de coluna
    padroes = {
        'numero_conta': ['num_cartao', 'numcartao', 'cartao', 'num_conta', 'conta', 'codigo'],
        'cpf': ['cpf', 'cpf_beneficiario'],
        'nome': ['nome', 'nome_beneficiario', 'beneficiario'],
        'valor': ['valor', 'valor_total', 'valor_pagto', 'valor_pagamento'],
        'projeto': ['projeto', 'programa', 'cod_projeto'],
        'dias': ['dias', 'dias_trabalhados']
    }
    
    # Para cada coluna do dataframe
    for col in df.columns:
        col_lower = str(col).lower().strip()
        
        # Verificar cada padrão
        for tipo, padroes_tipo in padroes.items():
            for padrao in padroes_tipo:
                if padrao in col_lower:
                    colunas[tipo] = col
                    break
    
    return colunas

def processar_arquivo(uploaded_file, conn):
    """Processa um arquivo de forma simples e direta"""
    try:
        # Verificar se é CSV ou Excel
        if uploaded_file.name.lower().endswith('.csv'):
            # Tentar diferentes separadores
            try:
                df = pd.read_csv(uploaded_file, sep=';', dtype=str)
            except:
                try:
                    df = pd.read_csv(uploaded_file, sep=',', dtype=str)
                except:
                    df = pd.read_csv(uploaded_file, sep=None, engine='python', dtype=str)
        
        elif uploaded_file.name.lower().endswith(('.xls', '.xlsx')):
            df = pd.read_excel(uploaded_file, dtype=str)
        else:
            return False, "Formato não suportado"
        
        # Remover linhas completamente vazias
        df = df.dropna(how='all')
        
        if len(df) == 0:
            return False, "Arquivo vazio"
        
        # Detectar colunas automaticamente
        colunas_map = detectar_colunas(df)
        
        # Verificar colunas mínimas
        if 'numero_conta' not in colunas_map or 'nome' not in colunas_map:
            return False, "Colunas obrigatórias não encontradas (número da conta e nome)"
        
        # Detectar mês e ano
        mes, ano = detectar_mes_ano(uploaded_file.name, df)
        
        # Processar cada linha
        cursor = conn.cursor()
        registros_importados = 0
        
        for _, row in df.iterrows():
            try:
                # Extrair dados com base no mapeamento
                numero_conta = str(row[colunas_map.get('numero_conta')]).strip() if colunas_map.get('numero_conta') else ''
                nome = str(row[colunas_map.get('nome')]).strip() if colunas_map.get('nome') else ''
                cpf = normalizar_cpf(row[colunas_map.get('cpf')]) if colunas_map.get('cpf') else ''
                
                # Valores
                if colunas_map.get('valor'):
                    valor_bruto = normalizar_valor(row[colunas_map.get('valor')])
                    valor_liquido = valor_bruto  # Assume que é o mesmo se não houver desconto
                else:
                    valor_bruto = 0
                    valor_liquido = 0
                
                # Projeto
                projeto = str(row[colunas_map.get('projeto')]).strip() if colunas_map.get('projeto') else ''
                
                # Dias trabalhados
                if colunas_map.get('dias'):
                    try:
                        dias = int(float(row[colunas_map.get('dias')]))
                    except:
                        dias = 20
                else:
                    dias = 20
                
                # Calcular valor diário
                valor_diario = valor_liquido / dias if dias > 0 else 0
                
                # Normalizar nome para comparação
                nome_normalizado = normalizar_nome(nome)
                
                # Inserir no banco
                cursor.execute('''
                    INSERT INTO dados 
                    (mes_referencia, ano_referencia, numero_conta, cpf, nome, nome_normalizado,
                     projeto, valor_bruto, valor_liquido, valor_desconto, dias_trabalhados,
                     valor_diario, arquivo_origem, tipo_arquivo)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    mes, ano, numero_conta, cpf, nome, nome_normalizado,
                    projeto, valor_bruto, valor_liquido, 0, dias,
                    valor_diario, uploaded_file.name, 'PAGAMENTO'
                ))
                
                registros_importados += 1
                
            except Exception as e:
                # Continua com próximo registro mesmo se um falhar
                continue
        
        conn.commit()
        
        # Após importar, detectar inconsistências
        detectar_inconsistencias(conn)
        
        return True, f"✅ {registros_importados} registros importados do arquivo {uploaded_file.name} | Período: {mes:02d}/{ano}"
        
    except Exception as e:
        return False, f"❌ Erro ao processar arquivo: {str(e)}"

def detectar_inconsistencias(conn):
    """Detecta CPFs repetidos com nomes ou contas diferentes"""
    try:
        cursor = conn.cursor()
        
        # 1. CPFs repetidos com nomes diferentes
        cursor.execute('''
            UPDATE dados 
            SET cpf_repetido = 1,
                nome_diferente = 1,
                inconsistencia = 'CPF_REPETIDO_NOME_DIFERENTE'
            WHERE cpf IN (
                SELECT cpf 
                FROM dados 
                WHERE cpf != '' 
                GROUP BY cpf 
                HAVING COUNT(DISTINCT nome_normalizado) > 1
            )
        ''')
        
        # 2. CPFs repetidos com contas diferentes
        cursor.execute('''
            UPDATE dados 
            SET cpf_repetido = 1,
                conta_diferente = 1,
                inconsistencia = 'CPF_REPETIDO_CONTA_DIFERENTE'
            WHERE cpf IN (
                SELECT cpf 
                FROM dados 
                WHERE cpf != '' 
                GROUP BY cpf 
                HAVING COUNT(DISTINCT numero_conta) > 1
            )
        ''')
        
        # 3. Contas repetidas com CPFs diferentes
        cursor.execute('''
            UPDATE dados 
            SET inconsistencia = 'CONTA_REPETIDA_CPF_DIFERENTE'
            WHERE numero_conta IN (
                SELECT numero_conta 
                FROM dados 
                WHERE numero_conta != '' 
                GROUP BY numero_conta 
                HAVING COUNT(DISTINCT cpf) > 1
            )
        ''')
        
        # 4. Nomes similares com CPFs diferentes
        cursor.execute('''
            UPDATE dados 
            SET inconsistencia = 'NOME_SIMILAR_CPF_DIFERENTE'
            WHERE nome_normalizado IN (
                SELECT nome_normalizado 
                FROM dados 
                WHERE nome_normalizado != '' 
                GROUP BY nome_normalizado 
                HAVING COUNT(DISTINCT cpf) > 1
            )
        ''')
        
        conn.commit()
        
        # Contar inconsistências
        cursor.execute("SELECT COUNT(*) FROM dados WHERE inconsistencia IS NOT NULL")
        total = cursor.fetchone()[0]
        
        return total
        
    except Exception as e:
        print(f"Erro detectando inconsistências: {str(e)}")
        return 0

# ========== FUNÇÕES DE ANÁLISE ==========
def calcular_resumo(conn):
    """Calcula resumo geral dos dados"""
    try:
        cursor = conn.cursor()
        
        # Total de registros
        cursor.execute("SELECT COUNT(*) FROM dados")
        total_registros = cursor.fetchone()[0] or 0
        
        # Total de beneficiários únicos
        cursor.execute("SELECT COUNT(DISTINCT nome_normalizado) FROM dados WHERE nome_normalizado != ''")
        beneficiarios_unicos = cursor.fetchone()[0] or 0
        
        # Total de CPFs únicos
        cursor.execute("SELECT COUNT(DISTINCT cpf) FROM dados WHERE cpf != ''")
        cpfs_unicos = cursor.fetchone()[0] or 0
        
        # Total de contas únicas
        cursor.execute("SELECT COUNT(DISTINCT numero_conta) FROM dados WHERE numero_conta != ''")
        contas_unicas = cursor.fetchone()[0] or 0
        
        # Valor total pago
        cursor.execute("SELECT SUM(valor_liquido) FROM dados")
        valor_total = cursor.fetchone()[0] or 0
        
        # Inconsistências
        cursor.execute("SELECT COUNT(*) FROM dados WHERE inconsistencia IS NOT NULL")
        total_inconsistencias = cursor.fetchone()[0] or 0
        
        # Último período
        cursor.execute('''
            SELECT MAX(ano_referencia), MAX(mes_referencia) 
            FROM dados 
            WHERE ano_referencia IS NOT NULL AND mes_referencia IS NOT NULL
        ''')
        ultimo = cursor.fetchone()
        if ultimo[0] and ultimo[1]:
            ultimo_periodo = f"{ultimo[1]:02d}/{ultimo[0]}"
        else:
            ultimo_periodo = "Nenhum"
        
        # Total de arquivos
        cursor.execute("SELECT COUNT(DISTINCT arquivo_origem) FROM dados")
        arquivos_processados = cursor.fetchone()[0] or 0
        
        return {
            'total_registros': total_registros,
            'beneficiarios_unicos': beneficiarios_unicos,
            'cpfs_unicos': cpfs_unicos,
            'contas_unicas': contas_unicas,
            'valor_total': valor_total,
            'inconsistencias': total_inconsistencias,
            'ultimo_periodo': ultimo_periodo,
            'arquivos_processados': arquivos_processados
        }
        
    except:
        return {
            'total_registros': 0,
            'beneficiarios_unicos': 0,
            'cpfs_unicos': 0,
            'contas_unicas': 0,
            'valor_total': 0,
            'inconsistencias': 0,
            'ultimo_periodo': 'Nenhum',
            'arquivos_processados': 0
        }

def obter_evolucao_mensal(conn):
    """Obtém evolução mensal dos pagamentos"""
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                ano_referencia,
                mes_referencia,
                COUNT(*) as registros,
                COUNT(DISTINCT nome_normalizado) as beneficiarios,
                SUM(valor_liquido) as valor_total,
                AVG(valor_liquido) as valor_medio
            FROM dados
            WHERE ano_referencia IS NOT NULL AND mes_referencia IS NOT NULL
            GROUP BY ano_referencia, mes_referencia
            ORDER BY ano_referencia DESC, mes_referencia DESC
            LIMIT 12
        ''')
        
        resultados = cursor.fetchall()
        if resultados:
            df = pd.DataFrame(resultados, 
                columns=['ano', 'mes', 'registros', 'beneficiarios', 'valor_total', 'valor_medio'])
            df['periodo'] = df['mes'].astype(str).str.zfill(2) + '/' + df['ano'].astype(str)
            df = df.sort_values(['ano', 'mes'])
            return df
        else:
            return pd.DataFrame()
    except:
        return pd.DataFrame()

def obter_inconsistencias_detalhadas(conn):
    """Obtém detalhes das inconsistências"""
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                cpf,
                nome,
                nome_normalizado,
                numero_conta,
                inconsistencia,
                COUNT(*) as ocorrencias,
                GROUP_CONCAT(DISTINCT arquivo_origem) as arquivos
            FROM dados
            WHERE inconsistencia IS NOT NULL
            GROUP BY cpf, nome, nome_normalizado, numero_conta, inconsistencia
            ORDER BY ocorrencias DESC
            LIMIT 50
        ''')
        
        resultados = cursor.fetchall()
        if resultados:
            return pd.DataFrame(resultados, 
                columns=['CPF', 'Nome', 'Nome Normalizado', 'Conta', 'Tipo', 'Ocorrências', 'Arquivos'])
        else:
            return pd.DataFrame()
    except:
        return pd.DataFrame()

def obter_top_beneficiarios(conn, limite=10):
    """Obtém top beneficiários por valor recebido"""
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                nome,
                cpf,
                COUNT(DISTINCT numero_conta) as contas,
                COUNT(*) as pagamentos,
                SUM(valor_liquido) as total_recebido,
                AVG(valor_liquido) as media_pagamento,
                MAX(ano_referencia || '-' || mes_referencia) as ultimo_periodo
            FROM dados
            WHERE nome != ''
            GROUP BY nome, cpf
            ORDER BY total_recebido DESC
            LIMIT ?
        ''', (limite,))
        
        resultados = cursor.fetchall()
        if resultados:
            return pd.DataFrame(resultados, 
                columns=['Nome', 'CPF', 'Contas', 'Pagamentos', 'Total', 'Média', 'Último'])
        else:
            return pd.DataFrame()
    except:
        return pd.DataFrame()

def obter_arquivos_processados(conn):
    """Obtém lista de arquivos processados"""
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                arquivo_origem,
                tipo_arquivo,
                mes_referencia,
                ano_referencia,
                COUNT(*) as registros,
                SUM(valor_liquido) as valor_total,
                MAX(data_importacao) as data_importacao
            FROM dados
            WHERE arquivo_origem IS NOT NULL
            GROUP BY arquivo_origem, tipo_arquivo, mes_referencia, ano_referencia
            ORDER BY data_importacao DESC
            LIMIT 20
        ''')
        
        resultados = cursor.fetchall()
        if resultados:
            df = pd.DataFrame(resultados, 
                columns=['Arquivo', 'Tipo', 'Mês', 'Ano', 'Registros', 'Valor Total', 'Data'])
            df['Período'] = df['Mês'].fillna(0).astype(int).astype(str).str.zfill(2) + '/' + df['Ano'].fillna(0).astype(int).astype(str)
            return df
        else:
            return pd.DataFrame()
    except:
        return pd.DataFrame()

# ========== INTERFACE PRINCIPAL ==========
def main():
    # Inicializar banco
    conn = init_database()
    if not conn:
        st.error("Erro ao conectar com o banco de dados")
        return
    
    # Título principal
    st.title("💰 SISTEMA POT - Gestão Prática de Benefícios")
    st.markdown("---")
    
    # ========== SEÇÃO 1: UPLOAD DE ARQUIVOS ==========
    st.header("📤 Importar Arquivos")
    
    with st.expander("📋 Instruções Rápidas", expanded=False):
        st.markdown("""
        ### Como usar:
        1. **Arraste ou selecione** arquivos CSV ou Excel
        2. **O sistema detecta automaticamente** as colunas
        3. **Clique em Processar** para importar
        4. **Os dados aparecem automaticamente** nos relatórios abaixo
        
        ### Colunas que o sistema detecta:
        - **Número da conta**: `num_cartao`, `cartao`, `num_conta`, `conta`
        - **Nome**: `nome`, `beneficiario`, `nome_beneficiario`
        - **CPF**: `cpf`, `cpf_beneficiario`
        - **Valor**: `valor`, `valor_total`, `valor_pagamento`
        - **Projeto**: `projeto`, `programa`
        - **Dias**: `dias`, `dias_trabalhados`
        """)
    
    # Upload de arquivos
    uploaded_files = st.file_uploader(
        "Arraste ou selecione arquivos (CSV ou Excel)",
        type=['csv', 'xls', 'xlsx'],
        accept_multiple_files=True,
        key="uploader_principal"
    )
    
    if uploaded_files:
        st.success(f"📁 {len(uploaded_files)} arquivo(s) selecionado(s)")
        
        # Processar cada arquivo
        for uploaded_file in uploaded_files:
            col1, col2, col3 = st.columns([3, 1, 1])
            
            with col1:
                st.write(f"**{uploaded_file.name}**")
            
            with col2:
                if st.button(f"📊 Ver prévia", key=f"previa_{uploaded_file.name}"):
                    try:
                        if uploaded_file.name.lower().endswith('.csv'):
                            df = pd.read_csv(uploaded_file, nrows=10)
                        else:
                            df = pd.read_excel(uploaded_file, nrows=10)
                        
                        st.write(f"Prévia de {uploaded_file.name}:")
                        st.dataframe(df.head(5))
                    except:
                        st.error("Erro ao ler prévia")
            
            with col3:
                if st.button(f"🔄 Processar", key=f"processar_{uploaded_file.name}", type="primary"):
                    with st.spinner(f"Processando {uploaded_file.name}..."):
                        sucesso, mensagem = processar_arquivo(uploaded_file, conn)
                    
                    if sucesso:
                        st.success(mensagem)
                        st.balloons()
                    else:
                        st.error(mensagem)
        
        # Botão para processar todos
        if len(uploaded_files) > 1:
            if st.button("🔄 PROCESSAR TODOS OS ARQUIVOS", type="primary", use_container_width=True):
                with st.spinner("Processando todos os arquivos..."):
                    resultados = []
                    for uploaded_file in uploaded_files:
                        sucesso, mensagem = processar_arquivo(uploaded_file, conn)
                        resultados.append((uploaded_file.name, sucesso, mensagem))
                
                # Mostrar resultados
                st.subheader("Resultado do processamento:")
                for nome, sucesso, msg in resultados:
                    if sucesso:
                        st.success(f"✅ {nome}: {msg}")
                    else:
                        st.error(f"❌ {nome}: {msg}")
                
                st.rerun()
    
    st.markdown("---")
    
    # ========== SEÇÃO 2: RESUMO GERAL ==========
    st.header("📊 Resumo Geral")
    
    # Calcular resumo
    resumo = calcular_resumo(conn)
    
    # Métricas
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total de Registros", f"{resumo['total_registros']:,}")
        st.caption(f"Beneficiários: {resumo['beneficiarios_unicos']:,}")
    
    with col2:
        st.metric("Valor Total Pago", f"R$ {resumo['valor_total']:,.2f}")
        st.caption(f"Contas: {resumo['contas_unicas']:,}")
    
    with col3:
        st.metric("Último Período", resumo['ultimo_periodo'])
        st.caption(f"CPFs: {resumo['cpfs_unicos']:,}")
    
    with col4:
        cor = "red" if resumo['inconsistencias'] > 0 else "green"
        st.metric("Inconsistências", f"{resumo['inconsistencias']:,}")
        st.caption(f"Arquivos: {resumo['arquivos_processados']:,}")
    
    st.markdown("---")
    
    # ========== SEÇÃO 3: ANÁLISES E RELATÓRIOS ==========
    st.header("📈 Análises e Relatórios")
    
    # Criar abas para diferentes análises
    tab1, tab2, tab3, tab4 = st.tabs(["📅 Evolução Mensal", "⚠️ Inconsistências", "👥 Top Beneficiários", "📁 Arquivos"])
    
    with tab1:
        st.subheader("Evolução Mensal dos Pagamentos")
        
        df_evolucao = obter_evolucao_mensal(conn)
        if not df_evolucao.empty:
            # Gráfico de linha para valor total
            fig1 = px.line(
                df_evolucao,
                x='periodo',
                y='valor_total',
                title='Valor Total Pago por Mês',
                markers=True,
                line_shape='spline'
            )
            fig1.update_layout(xaxis_title='Período', yaxis_title='Valor Total (R$)')
            st.plotly_chart(fig1, use_container_width=True)
            
            # Gráfico de barras para beneficiários
            fig2 = px.bar(
                df_evolucao,
                x='periodo',
                y='beneficiarios',
                title='Número de Beneficiários por Mês',
                color='valor_total',
                color_continuous_scale='Blues'
            )
            st.plotly_chart(fig2, use_container_width=True)
            
            # Tabela de dados
            st.dataframe(
                df_evolucao[['periodo', 'registros', 'beneficiarios', 'valor_total', 'valor_medio']],
                use_container_width=True,
                column_config={
                    'valor_total': st.column_config.NumberColumn('Valor Total (R$)', format="R$ %.2f"),
                    'valor_medio': st.column_config.NumberColumn('Valor Médio (R$)', format="R$ %.2f")
                }
            )
        else:
            st.info("📭 Nenhum dado disponível. Importe arquivos para visualizar a evolução mensal.")
    
    with tab2:
        st.subheader("Inconsistências Detectadas")
        
        df_inconsistencias = obter_inconsistencias_detalhadas(conn)
        if not df_inconsistencias.empty:
            # Resumo por tipo de inconsistência
            st.write("### 📋 Tipos de Inconsistências")
            
            tipo_counts = df_inconsistencias['Tipo'].value_counts()
            fig_tipos = px.pie(
                values=tipo_counts.values,
                names=tipo_counts.index,
                title='Distribuição por Tipo de Inconsistência'
            )
            st.plotly_chart(fig_tipos, use_container_width=True)
            
            # Detalhamento
            st.write("### 🔍 Detalhamento das Inconsistências")
            
            # Agrupar por CPF para mostrar os casos mais problemáticos
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    cpf,
                    GROUP_CONCAT(DISTINCT nome) as nomes,
                    GROUP_CONCAT(DISTINCT numero_conta) as contas,
                    COUNT(*) as ocorrencias,
                    GROUP_CONCAT(DISTINCT inconsistencia) as tipos
                FROM dados
                WHERE inconsistencia IS NOT NULL AND cpf != ''
                GROUP BY cpf
                HAVING COUNT(DISTINCT nome) > 1 OR COUNT(DISTINCT numero_conta) > 1
                ORDER BY ocorrencias DESC
            ''')
            
            cpfs_problematicos = cursor.fetchall()
            
            if cpfs_problematicos:
                st.warning("### 🚨 CPFs com Múltiplos Nomes ou Contas")
                for cpf, nomes, contas, ocorrencias, tipos in cpfs_problematicos[:10]:
                    with st.expander(f"CPF: {cpf} ({ocorrencias} ocorrências)"):
                        st.write(f"**Nomes associados:** {nomes}")
                        st.write(f"**Contas associadas:** {contas}")
                        st.write(f"**Tipos de inconsistência:** {tipos}")
            
            # Tabela completa
            st.write("### 📊 Todas as Inconsistências")
            st.dataframe(
                df_inconsistencias,
                use_container_width=True,
                column_config={
                    'CPF': st.column_config.TextColumn('CPF'),
                    'Nome': st.column_config.TextColumn('Nome'),
                    'Conta': st.column_config.TextColumn('Conta'),
                    'Ocorrências': st.column_config.NumberColumn('Ocorrências', format="%.0f")
                }
            )
            
            # Botão para limpar inconsistências
            if st.button("🗑️ Marcar Inconsistências como Verificadas", use_container_width=True):
                cursor.execute("UPDATE dados SET inconsistencia = NULL")
                conn.commit()
                st.success("Inconsistências marcadas como verificadas!")
                st.rerun()
        else:
            st.success("🎉 Nenhuma inconsistência detectada!")
    
    with tab3:
        st.subheader("Top Beneficiários")
        
        df_top = obter_top_beneficiarios(conn, 15)
        if not df_top.empty:
            # Gráfico de barras
            fig = px.bar(
                df_top.head(10),
                x='Nome',
                y='Total',
                title='Top 10 Beneficiários por Valor Total Recebido',
                color='Pagamentos',
                color_continuous_scale='Viridis',
                hover_data=['CPF', 'Contas', 'Média']
            )
            fig.update_layout(xaxis_title='Beneficiário', yaxis_title='Valor Total Recebido (R$)')
            st.plotly_chart(fig, use_container_width=True)
            
            # Tabela detalhada
            st.dataframe(
                df_top,
                use_container_width=True,
                column_config={
                    'Total': st.column_config.NumberColumn('Total Recebido (R$)', format="R$ %.2f"),
                    'Média': st.column_config.NumberColumn('Média por Pagamento (R$)', format="R$ %.2f"),
                    'Pagamentos': st.column_config.NumberColumn('Nº de Pagamentos', format="%.0f"),
                    'Contas': st.column_config.NumberColumn('Nº de Contas', format="%.0f")
                }
            )
        else:
            st.info("📭 Nenhum beneficiário registrado.")
    
    with tab4:
        st.subheader("Arquivos Processados")
        
        df_arquivos = obter_arquivos_processados(conn)
        if not df_arquivos.empty:
            # Timeline visual
            st.write("### 📅 Linha do Tempo de Processamento")
            
            for _, row in df_arquivos.iterrows():
                with st.container():
                    cols = st.columns([1, 3, 2, 2])
                    with cols[0]:
                        st.write("📄")
                    with cols[1]:
                        st.write(f"**{row['Arquivo']}**")
                    with cols[2]:
                        if row['Período'] != '00/0':
                            st.write(f"📅 {row['Período']}")
                    with cols[3]:
                        st.write(f"📊 {row['Registros']} reg | R$ {row['Valor Total']:,.2f}")
            
            # Tabela detalhada
            st.write("### 📊 Detalhes dos Arquivos")
            st.dataframe(
                df_arquivos[['Arquivo', 'Período', 'Registros', 'Valor Total', 'Data']],
                use_container_width=True,
                column_config={
                    'Valor Total': st.column_config.NumberColumn('Valor Total (R$)', format="R$ %.2f"),
                    'Registros': st.column_config.NumberColumn('Registros', format="%.0f")
                }
            )
        else:
            st.info("📭 Nenhum arquivo processado ainda.")
    
    st.markdown("---")
    
    # ========== SEÇÃO 4: FERRAMENTAS ADICIONAIS ==========
    st.header("🔧 Ferramentas")
    
    col_tool1, col_tool2, col_tool3 = st.columns(3)
    
    with col_tool1:
        if st.button("🔄 Atualizar Análises", use_container_width=True):
            detectar_inconsistencias(conn)
            st.success("Análises atualizadas!")
            st.rerun()
    
    with col_tool2:
        if st.button("📥 Exportar Dados", use_container_width=True):
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM dados")
                dados = cursor.fetchall()
                colunas = [desc[0] for desc in cursor.description]
                
                df_export = pd.DataFrame(dados, columns=colunas)
                
                # Converter para CSV
                csv = df_export.to_csv(index=False, sep=';', encoding='latin-1')
                
                st.download_button(
                    label="💾 Download CSV Completo",
                    data=csv,
                    file_name=f"dados_pot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            except Exception as e:
                st.error(f"Erro ao exportar: {str(e)}")
    
    with col_tool3:
        if st.button("🧹 Limpar Dados Antigos", use_container_width=True):
            with st.expander("Confirmar limpeza", expanded=True):
                st.warning("⚠️ Esta ação removerá dados antigos (anteriores a 6 meses)")
                if st.button("✅ Confirmar Limpeza"):
                    try:
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM dados WHERE data_importacao < datetime('now', '-6 months')")
                        conn.commit()
                        st.success("Dados antigos removidos!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {str(e)}")
    
    # Rodapé
    st.markdown("---")
    st.caption(f"💰 Sistema POT - SMDET | {datetime.now().strftime('%d/%m/%Y %H:%M')} | Dados: {resumo['total_registros']:,} registros")
    
    # Fechar conexão
    conn.close()

if __name__ == "__main__":
    main()
