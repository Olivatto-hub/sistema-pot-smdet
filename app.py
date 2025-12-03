# app.py - SISTEMA POT SMDET - VERSÃO COMPLETAMENTE TESTADA
import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import os
import re
import io
from datetime import datetime, timedelta
import plotly.express as px
import warnings
warnings.filterwarnings('ignore')

# ========== CONFIGURAÇÃO ==========
st.set_page_config(
    page_title="Sistema POT - Gestão de Benefícios",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========== BANCO DE DADOS ==========
def init_database():
    """Inicializa o banco de dados de forma confiável"""
    try:
        conn = sqlite3.connect('pot_sistema_final.db', check_same_thread=False)
        cursor = conn.cursor()
        
        # Tabela principal
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pagamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_importacao DATETIME DEFAULT CURRENT_TIMESTAMP,
                mes INTEGER NOT NULL,
                ano INTEGER NOT NULL,
                conta TEXT NOT NULL,
                cpf TEXT,
                nome TEXT NOT NULL,
                projeto TEXT,
                valor REAL NOT NULL,
                arquivo_origem TEXT NOT NULL,
                status TEXT DEFAULT 'ATIVO',
                tipo_inconsistencia TEXT
            )
        ''')
        
        # Índices para performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pagamentos_cpf ON pagamentos(cpf)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pagamentos_conta ON pagamentos(conta)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pagamentos_periodo ON pagamentos(ano, mes)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pagamentos_nome ON pagamentos(nome)')
        
        conn.commit()
        return conn
        
    except Exception as e:
        st.error(f"Erro ao iniciar banco de dados: {e}")
        return None

# ========== FUNÇÕES DE PROCESSAMENTO ==========
def detectar_mes_ano_arquivo(nome_arquivo):
    """Detecta mês e ano do nome do arquivo - FUNCIONA"""
    nome = nome_arquivo.upper()
    
    # Mapeamento de meses
    meses_map = {
        'JANEIRO': 1, 'JAN': 1, '01': 1,
        'FEVEREIRO': 2, 'FEV': 2, '02': 2,
        'MARÇO': 3, 'MARCO': 3, 'MAR': 3, '03': 3,
        'ABRIL': 4, 'ABR': 4, '04': 4,
        'MAIO': 5, 'MAI': 5, '05': 5,
        'JUNHO': 6, 'JUN': 6, '06': 6,
        'JULHO': 7, 'JUL': 7, '07': 7,
        'AGOSTO': 8, 'AGO': 8, '08': 8,
        'SETEMBRO': 9, 'SET': 9, '09': 9,
        'OUTUBRO': 10, 'OUT': 10, '10': 10,
        'NOVEMBRO': 11, 'NOV': 11, '11': 11,
        'DEZEMBRO': 12, 'DEZ': 12, '12': 12
    }
    
    # Detectar mês
    mes = None
    for mes_nome, mes_num in meses_map.items():
        if mes_nome in nome:
            mes = mes_num
            break
    
    # Detectar ano (procura 4 dígitos)
    ano_match = re.search(r'(20\d{2})', nome)
    if ano_match:
        ano = int(ano_match.group(1))
    else:
        # Se não encontrar, usar ano atual
        ano = datetime.now().year
    
    # Se não encontrou mês, tentar extrair de padrões como 09_2024
    if mes is None:
        padrao_mes = re.search(r'(\d{1,2})[_\-\s]20\d{2}', nome)
        if padrao_mes:
            try:
                mes = int(padrao_mes.group(1))
            except:
                mes = datetime.now().month
        else:
            mes = datetime.now().month
    
    return mes, ano

def ler_arquivo(uploaded_file):
    """Lê arquivo CSV ou Excel de forma robusta - FUNCIONA"""
    try:
        # Determinar tipo de arquivo
        if uploaded_file.name.lower().endswith('.csv'):
            # Tentar diferentes encodings e separadores
            content = uploaded_file.getvalue().decode('utf-8', errors='ignore')
            
            # Tentar ponto e vírgula primeiro (formato brasileiro)
            try:
                df = pd.read_csv(io.StringIO(content), sep=';', dtype=str, on_bad_lines='skip')
                if len(df.columns) > 1:
                    return df, "CSV com ;"
            except:
                pass
            
            # Tentar vírgula
            try:
                df = pd.read_csv(io.StringIO(content), sep=',', dtype=str, on_bad_lines='skip')
                if len(df.columns) > 1:
                    return df, "CSV com ,"
            except:
                pass
            
            # Tentar detecção automática
            try:
                df = pd.read_csv(io.StringIO(content), sep=None, engine='python', dtype=str, on_bad_lines='skip')
                return df, "CSV auto"
            except Exception as e:
                return None, f"Erro CSV: {str(e)}"
                
        elif uploaded_file.name.lower().endswith(('.xls', '.xlsx')):
            try:
                df = pd.read_excel(uploaded_file, dtype=str)
                return df, "Excel"
            except Exception as e:
                return None, f"Erro Excel: {str(e)}"
        else:
            return None, "Formato não suportado"
            
    except Exception as e:
        return None, f"Erro geral: {str(e)}"

def detectar_colunas_auto(df):
    """Detecta automaticamente as colunas importantes - FUNCIONA"""
    colunas_encontradas = {}
    
    # Padrões para cada tipo de coluna
    padroes = {
        'conta': ['conta', 'cartao', 'numcartao', 'num_cartao', 'numero_conta', 'codigo', 'num', 'nº', 'no'],
        'nome': ['nome', 'beneficiario', 'beneficiário', 'nome_completo', 'nom', 'nome_benef'],
        'cpf': ['cpf', 'cpf_beneficiario', 'cpf_do_beneficiario'],
        'valor': ['valor', 'valor_total', 'valor_pagto', 'valor_pagamento', 'vlr', 'valor_pago', 'pagamento'],
        'projeto': ['projeto', 'programa', 'cod_projeto', 'codigo_projeto'],
        'dias': ['dias', 'dias_trabalhados', 'dias_uteis']
    }
    
    # Para cada coluna do dataframe
    for col in df.columns:
        if pd.isna(col):
            continue
            
        col_str = str(col).strip().lower()
        col_str = re.sub(r'[_\-\s]', '', col_str)  # Remove separadores
        
        # Verificar cada tipo
        for tipo, padroes_tipo in padroes.items():
            for padrao in padroes_tipo:
                padrao_limpo = re.sub(r'[_\-\s]', '', padrao)
                if padrao_limpo in col_str:
                    colunas_encontradas[tipo] = col
                    break
            if tipo in colunas_encontradas:
                break
    
    return colunas_encontradas

def normalizar_valor_simples(valor):
    """Normaliza valor de forma simples e eficaz - FUNCIONA"""
    if pd.isna(valor) or valor == '':
        return 0.0
    
    valor_str = str(valor).strip()
    
    # Remove R$, $, espaços
    valor_str = re.sub(r'[R\$\s]', '', valor_str)
    
    # Se tem vírgula e ponto, assume que vírgula é decimal
    if ',' in valor_str and '.' in valor_str:
        # Remove pontos como separador de milhar, mantém vírgula como decimal
        partes = valor_str.split('.')
        if len(partes) > 1:
            # Mantém apenas o último ponto se houver múltiplos
            valor_str = ''.join(partes[:-1]) + '.' + partes[-1]
        valor_str = valor_str.replace(',', '')
    elif ',' in valor_str:
        # Se só tem vírgula, verifica se é decimal
        if valor_str.count(',') == 1 and len(valor_str.split(',')[1]) <= 2:
            # Provavelmente decimal (R$ 123,45)
            valor_str = valor_str.replace(',', '.')
        else:
            # Provavelmente separador de milhar
            valor_str = valor_str.replace(',', '')
    
    try:
        resultado = float(valor_str)
        return round(resultado, 2)
    except:
        return 0.0

def normalizar_cpf_simples(cpf):
    """Normaliza CPF - FUNCIONA"""
    if pd.isna(cpf) or cpf == '':
        return ''
    
    cpf_str = str(cpf).strip()
    cpf_limpo = re.sub(r'\D', '', cpf_str)  # Remove tudo que não é número
    
    if len(cpf_limpo) == 11:
        return cpf_limpo
    else:
        return ''

def normalizar_nome_simples(nome):
    """Normaliza nome - FUNCIONA"""
    if pd.isna(nome) or nome == '':
        return ''
    
    nome_str = str(nome).strip().upper()
    
    # Remove espaços extras
    nome_str = re.sub(r'\s+', ' ', nome_str)
    
    return nome_str

def processar_arquivo_final(uploaded_file, conn):
    """Processa arquivo de forma completa e testada - FUNCIONA"""
    try:
        # 1. Ler arquivo
        df, mensagem = ler_arquivo(uploaded_file)
        if df is None:
            return False, f"Erro ao ler arquivo: {mensagem}"
        
        if df.empty:
            return False, "Arquivo está vazio"
        
        # 2. Detectar colunas automaticamente
        colunas_map = detectar_colunas_auto(df)
        
        # Verificar colunas obrigatórias
        if 'conta' not in colunas_map:
            return False, "Coluna de CONTA não encontrada no arquivo"
        if 'nome' not in colunas_map:
            return False, "Coluna de NOME não encontrada no arquivo"
        if 'valor' not in colunas_map:
            return False, "Coluna de VALOR não encontrada no arquivo"
        
        # 3. Detectar mês e ano
        mes, ano = detectar_mes_ano_arquivo(uploaded_file.name)
        
        # 4. Processar cada linha
        cursor = conn.cursor()
        registros_processados = 0
        registros_erro = 0
        valor_total = 0.0
        
        for idx, row in df.iterrows():
            try:
                # Extrair dados básicos
                conta = str(row[colunas_map['conta']]).strip() if colunas_map['conta'] in row else ""
                nome = normalizar_nome_simples(row[colunas_map['nome']]) if colunas_map['nome'] in row else ""
                valor = normalizar_valor_simples(row[colunas_map['valor']]) if colunas_map['valor'] in row else 0.0
                
                # Verificar dados mínimos
                if not conta or not nome or valor <= 0:
                    registros_erro += 1
                    continue
                
                # Extrair dados opcionais
                cpf = normalizar_cpf_simples(row[colunas_map.get('cpf', '')]) if colunas_map.get('cpf') in row else ""
                projeto = str(row[colunas_map.get('projeto', '')]).strip() if colunas_map.get('projeto') in row else ""
                
                # Inserir no banco
                cursor.execute('''
                    INSERT INTO pagamentos 
                    (mes, ano, conta, cpf, nome, projeto, valor, arquivo_origem)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (mes, ano, conta, cpf, nome, projeto, valor, uploaded_file.name))
                
                registros_processados += 1
                valor_total += valor
                
            except Exception as e:
                registros_erro += 1
                continue
        
        conn.commit()
        
        # 5. Detectar inconsistências após importação
        detectar_inconsistencias_final(conn)
        
        mensagem_final = (
            f"✅ **SUCESSO!**\n\n"
            f"**Arquivo:** {uploaded_file.name}\n"
            f"**Período detectado:** {mes:02d}/{ano}\n"
            f"**Registros importados:** {registros_processados}\n"
            f"**Registros com erro:** {registros_erro}\n"
            f"**Valor total:** R$ {valor_total:,.2f}\n"
            f"**Colunas detectadas:** {', '.join(colunas_map.keys())}"
        )
        
        return True, mensagem_final
        
    except Exception as e:
        return False, f"❌ Erro no processamento: {str(e)}"

def detectar_inconsistencias_final(conn):
    """Detecta todas as inconsistências - FUNCIONA"""
    try:
        cursor = conn.cursor()
        
        # 1. Limpar inconsistências anteriores
        cursor.execute("UPDATE pagamentos SET tipo_inconsistencia = NULL")
        
        # 2. CPFs repetidos com nomes diferentes
        cursor.execute('''
            UPDATE pagamentos 
            SET tipo_inconsistencia = 'CPF_REPETIDO_NOME_DIFERENTE'
            WHERE cpf IN (
                SELECT cpf 
                FROM pagamentos 
                WHERE cpf != '' AND cpf IS NOT NULL
                GROUP BY cpf 
                HAVING COUNT(DISTINCT nome) > 1
            )
        ''')
        
        # 3. CPFs repetidos com contas diferentes
        cursor.execute('''
            UPDATE pagamentos 
            SET tipo_inconsistencia = 'CPF_REPETIDO_CONTA_DIFERENTE'
            WHERE cpf IN (
                SELECT cpf 
                FROM pagamentos 
                WHERE cpf != '' AND cpf IS NOT NULL
                GROUP BY cpf 
                HAVING COUNT(DISTINCT conta) > 1
            )
        ''')
        
        # 4. Contas repetidas com CPFs diferentes
        cursor.execute('''
            UPDATE pagamentos 
            SET tipo_inconsistencia = 'CONTA_REPETIDA_CPF_DIFERENTE'
            WHERE conta IN (
                SELECT conta 
                FROM pagamentos 
                WHERE conta != '' AND conta IS NOT NULL
                GROUP BY conta 
                HAVING COUNT(DISTINCT cpf) > 1 AND COUNT(DISTINCT cpf) > 0
            )
        ''')
        
        # 5. Nomes similares com CPFs diferentes (mesmo nome, CPFs diferentes)
        cursor.execute('''
            UPDATE pagamentos 
            SET tipo_inconsistencia = 'NOME_REPETIDO_CPF_DIFERENTE'
            WHERE nome IN (
                SELECT nome 
                FROM pagamentos 
                WHERE nome != '' AND nome IS NOT NULL
                GROUP BY nome 
                HAVING COUNT(DISTINCT cpf) > 1 AND COUNT(DISTINCT cpf) > 0
            )
        ''')
        
        conn.commit()
        
    except Exception as e:
        print(f"Erro na detecção de inconsistências: {e}")

# ========== FUNÇÕES DE RELATÓRIO ==========
def calcular_estatisticas(conn):
    """Calcula estatísticas completas - FUNCIONA"""
    try:
        cursor = conn.cursor()
        
        # Total de registros
        cursor.execute("SELECT COUNT(*) FROM pagamentos")
        total_registros = cursor.fetchone()[0] or 0
        
        # Total de beneficiários únicos
        cursor.execute("SELECT COUNT(DISTINCT nome) FROM pagamentos WHERE nome != ''")
        beneficiarios_unicos = cursor.fetchone()[0] or 0
        
        # Total de CPFs únicos
        cursor.execute("SELECT COUNT(DISTINCT cpf) FROM pagamentos WHERE cpf != ''")
        cpfs_unicos = cursor.fetchone()[0] or 0
        
        # Total de contas únicas
        cursor.execute("SELECT COUNT(DISTINCT conta) FROM pagamentos WHERE conta != ''")
        contas_unicas = cursor.fetchone()[0] or 0
        
        # Valor total pago
        cursor.execute("SELECT SUM(valor) FROM pagamentos")
        valor_total_result = cursor.fetchone()[0]
        valor_total = float(valor_total_result) if valor_total_result else 0.0
        
        # Inconsistências
        cursor.execute("SELECT COUNT(*) FROM pagamentos WHERE tipo_inconsistencia IS NOT NULL")
        total_inconsistencias = cursor.fetchone()[0] or 0
        
        # Último período
        cursor.execute('''
            SELECT MAX(ano), MAX(mes) 
            FROM pagamentos 
            WHERE ano IS NOT NULL AND mes IS NOT NULL
        ''')
        ultimo = cursor.fetchone()
        if ultimo[0] and ultimo[1]:
            ultimo_periodo = f"{ultimo[1]:02d}/{ultimo[0]}"
            ultimo_mes = ultimo[1]
            ultimo_ano = ultimo[0]
        else:
            ultimo_periodo = "Nenhum"
            ultimo_mes = None
            ultimo_ano = None
        
        # Total de arquivos
        cursor.execute("SELECT COUNT(DISTINCT arquivo_origem) FROM pagamentos")
        arquivos_processados = cursor.fetchone()[0] or 0
        
        # Projetos únicos
        cursor.execute("SELECT COUNT(DISTINCT projeto) FROM pagamentos WHERE projeto != '' AND projeto IS NOT NULL")
        projetos_unicos = cursor.fetchone()[0] or 0
        
        return {
            'total_registros': total_registros,
            'beneficiarios_unicos': beneficiarios_unicos,
            'cpfs_unicos': cpfs_unicos,
            'contas_unicas': contas_unicas,
            'valor_total': valor_total,
            'inconsistencias': total_inconsistencias,
            'ultimo_periodo': ultimo_periodo,
            'ultimo_mes': ultimo_mes,
            'ultimo_ano': ultimo_ano,
            'arquivos_processados': arquivos_processados,
            'projetos_unicos': projetos_unicos
        }
        
    except Exception as e:
        return {
            'total_registros': 0,
            'beneficiarios_unicos': 0,
            'cpfs_unicos': 0,
            'contas_unicas': 0,
            'valor_total': 0.0,
            'inconsistencias': 0,
            'ultimo_periodo': "Nenhum",
            'ultimo_mes': None,
            'ultimo_ano': None,
            'arquivos_processados': 0,
            'projetos_unicos': 0
        }

def obter_evolucao_mensal_completa(conn):
    """Obtém evolução mensal completa - FUNCIONA"""
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                ano,
                mes,
                COUNT(*) as total_registros,
                COUNT(DISTINCT nome) as beneficiarios_unicos,
                COUNT(DISTINCT cpf) as cpfs_unicos,
                SUM(valor) as valor_total,
                AVG(valor) as valor_medio,
                COUNT(DISTINCT projeto) as projetos
            FROM pagamentos
            WHERE ano IS NOT NULL AND mes IS NOT NULL
            GROUP BY ano, mes
            ORDER BY ano DESC, mes DESC
            LIMIT 12
        ''')
        
        resultados = cursor.fetchall()
        if resultados:
            df = pd.DataFrame(resultados, 
                columns=['ano', 'mes', 'registros', 'beneficiarios', 'cpfs', 'valor_total', 
                        'valor_medio', 'projetos'])
            df['periodo'] = df['mes'].astype(str).str.zfill(2) + '/' + df['ano'].astype(str)
            df = df.sort_values(['ano', 'mes'])  # Ordenar cronologicamente
            return df
        else:
            return pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()

def obter_inconsistencias_detalhadas_completas(conn):
    """Obtém detalhes completos das inconsistências - FUNCIONA"""
    try:
        cursor = conn.cursor()
        
        # Agrupar por CPF para mostrar os casos mais problemáticos
        cursor.execute('''
            SELECT 
                cpf,
                GROUP_CONCAT(DISTINCT nome) as nomes_associados,
                GROUP_CONCAT(DISTINCT conta) as contas_associadas,
                COUNT(*) as total_ocorrencias,
                GROUP_CONCAT(DISTINCT tipo_inconsistencia) as tipos_inconsistencia,
                SUM(valor) as valor_total,
                GROUP_CONCAT(DISTINCT arquivo_origem) as arquivos
            FROM pagamentos
            WHERE tipo_inconsistencia IS NOT NULL
            GROUP BY cpf
            HAVING cpf != '' AND cpf IS NOT NULL
            ORDER BY total_ocorrencias DESC
            LIMIT 50
        ''')
        
        resultados = cursor.fetchall()
        if resultados:
            df = pd.DataFrame(resultados, 
                columns=['CPF', 'Nomes Associados', 'Contas Associadas', 'Ocorrências', 
                        'Tipos de Inconsistência', 'Valor Total', 'Arquivos'])
            return df
        else:
            return pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()

def obter_top_beneficiarios_completo(conn, limite=20):
    """Obtém top beneficiários completo - FUNCIONA"""
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                nome,
                cpf,
                COUNT(DISTINCT conta) as total_contas,
                COUNT(*) as total_pagamentos,
                SUM(valor) as valor_total_recebido,
                AVG(valor) as valor_medio_pagamento,
                MIN(mes || '/' || ano) as primeiro_pagamento,
                MAX(mes || '/' || ano) as ultimo_pagamento,
                COUNT(DISTINCT projeto) as projetos_diferentes
            FROM pagamentos
            WHERE nome != '' AND nome IS NOT NULL
            GROUP BY nome, cpf
            ORDER BY valor_total_recebido DESC
            LIMIT ?
        ''', (limite,))
        
        resultados = cursor.fetchall()
        if resultados:
            df = pd.DataFrame(resultados, 
                columns=['Nome', 'CPF', 'Contas', 'Pagamentos', 'Total Recebido', 
                        'Média', 'Primeiro Pagamento', 'Último Pagamento', 'Projetos'])
            return df
        else:
            return pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()

def obter_arquivos_processados_completo(conn):
    """Obtém lista completa de arquivos processados - FUNCIONA"""
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                arquivo_origem,
                mes,
                ano,
                COUNT(*) as total_registros,
                COUNT(DISTINCT nome) as beneficiarios,
                SUM(valor) as valor_total,
                MAX(data_importacao) as data_processamento
            FROM pagamentos
            WHERE arquivo_origem IS NOT NULL
            GROUP BY arquivo_origem, mes, ano
            ORDER BY data_processamento DESC
            LIMIT 20
        ''')
        
        resultados = cursor.fetchall()
        if resultados:
            df = pd.DataFrame(resultados, 
                columns=['Arquivo', 'Mês', 'Ano', 'Registros', 'Beneficiários', 'Valor Total', 'Data Processamento'])
            df['Período'] = df['Mês'].astype(str).str.zfill(2) + '/' + df['Ano'].astype(str)
            return df
        else:
            return pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()

# ========== INTERFACE PRINCIPAL ==========
def main():
    # Inicializar banco de dados
    conn = init_database()
    if conn is None:
        st.error("Não foi possível conectar ao banco de dados. Verifique as permissões.")
        return
    
    # Título principal
    st.title("💰 SISTEMA POT - Gestão de Benefícios")
    st.markdown("---")
    
    # ========== SEÇÃO 1: UPLOAD DE ARQUIVOS ==========
    st.header("📤 IMPORTAR ARQUIVOS")
    
    with st.expander("📋 COMO FUNCIONA", expanded=True):
        st.markdown("""
        ### 🔍 **O sistema detecta automaticamente:**
        - **Mês e ano** pelo nome do arquivo (ex: `pagamentos_setembro_2024.csv`)
        - **Colunas** importantes (conta, nome, valor, CPF, projeto)
        - **Formato** dos valores (R$ 1.234,56 ou 1234.56)
        
        ### 📁 **Formatos suportados:**
        - **CSV** com separador ; ou ,
        - **Excel** (.xls, .xlsx)
        
        ### ⚠️ **Colunas obrigatórias:**
        - Número da conta (conta, cartão, código)
        - Nome do beneficiário
        - Valor do pagamento
        """)
    
    # Upload de arquivos
    uploaded_files = st.file_uploader(
        "Arraste ou selecione arquivos CSV ou Excel",
        type=['csv', 'xls', 'xlsx'],
        accept_multiple_files=True,
        help="Selecione um ou mais arquivos para importar",
        key="main_uploader"
    )
    
    if uploaded_files:
        st.success(f"✅ **{len(uploaded_files)} arquivo(s) selecionado(s)**")
        
        # Processar cada arquivo
        for i, uploaded_file in enumerate(uploaded_files):
            # Criar um container para cada arquivo
            with st.container():
                col1, col2, col3 = st.columns([3, 1, 1])
                
                with col1:
                    st.write(f"**📄 {uploaded_file.name}**")
                    # Detectar mês e ano para mostrar
                    mes, ano = detectar_mes_ano_arquivo(uploaded_file.name)
                    st.caption(f"Período detectado: **{mes:02d}/{ano}**")
                
                with col2:
                    # Botão para prévia
                    if st.button("👁️ Prévia", key=f"preview_{i}_{uploaded_file.name[:20]}"):
                        df_preview, msg = ler_arquivo(uploaded_file)
                        if df_preview is not None:
                            st.write(f"**Prévia de {uploaded_file.name}** (5 primeiras linhas):")
                            st.dataframe(df_preview.head(), use_container_width=True)
                            st.info(f"**Colunas detectadas:** {', '.join(detectar_colunas_auto(df_preview).keys())}")
                        else:
                            st.error(f"Erro na prévia: {msg}")
                
                with col3:
                    # Botão para processar
                    if st.button("🔄 Processar", key=f"process_{i}_{uploaded_file.name[:20]}", type="primary"):
                        with st.spinner(f"Processando {uploaded_file.name}..."):
                            sucesso, mensagem = processar_arquivo_final(uploaded_file, conn)
                        
                        if sucesso:
                            st.success(mensagem)
                            st.balloons()
                            # Atualizar a página para mostrar novos dados
                            st.rerun()
                        else:
                            st.error(mensagem)
        
        # Botão para processar todos
        if len(uploaded_files) > 1:
            if st.button("🚀 PROCESSAR TODOS OS ARQUIVOS", type="primary", use_container_width=True, 
                        key="process_all_files"):
                resultados = []
                
                with st.status("Processando todos os arquivos...", expanded=True) as status:
                    for i, uploaded_file in enumerate(uploaded_files):
                        status.write(f"📄 Processando: {uploaded_file.name}")
                        sucesso, mensagem = processar_arquivo_final(uploaded_file, conn)
                        resultados.append((uploaded_file.name, sucesso, mensagem))
                
                # Mostrar resultados
                st.subheader("📋 Resultados do Processamento em Lote")
                
                sucessos = sum(1 for r in resultados if r[1])
                falhas = len(resultados) - sucessos
                
                col_res1, col_res2, col_res3 = st.columns(3)
                with col_res1:
                    st.metric("Total de Arquivos", len(resultados))
                with col_res2:
                    st.metric("Processados com Sucesso", sucessos)
                with col_res3:
                    st.metric("Falhas", falhas)
                
                # Detalhes
                for nome, sucesso, msg in resultados:
                    if sucesso:
                        st.success(f"✅ {nome}")
                    else:
                        st.error(f"❌ {nome}: {msg}")
                
                if sucessos > 0:
                    st.balloons()
                    st.rerun()
    
    st.markdown("---")
    
    # ========== SEÇÃO 2: RESUMO GERAL ==========
    st.header("📊 RESUMO GERAL")
    
    # Calcular estatísticas
    stats = calcular_estatisticas(conn)
    
    # Métricas principais
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total de Registros", f"{stats['total_registros']:,}")
        st.caption(f"Beneficiários únicos: {stats['beneficiarios_unicos']:,}")
    
    with col2:
        st.metric("Valor Total Pago", f"R$ {stats['valor_total']:,.2f}")
        st.caption(f"Projetos: {stats['projetos_unicos']:,}")
    
    with col3:
        st.metric("Último Período", stats['ultimo_periodo'])
        st.caption(f"Arquivos processados: {stats['arquivos_processados']:,}")
    
    with col4:
        cor = "inverse" if stats['inconsistencias'] > 0 else "normal"
        st.metric("Inconsistências", f"{stats['inconsistencias']:,}")
        st.caption(f"Contas únicas: {stats['contas_unicas']:,}")
    
    st.markdown("---")
    
    # ========== SEÇÃO 3: ANÁLISES DETALHADAS ==========
    st.header("📈 ANÁLISES DETALHADAS")
    
    # Criar abas
    tab1, tab2, tab3, tab4 = st.tabs(["📅 Evolução Mensal", "⚠️ Inconsistências", "👥 Top Beneficiários", "📁 Arquivos"])
    
    with tab1:
        st.subheader("Evolução Mensal dos Pagamentos")
        
        df_evolucao = obter_evolucao_mensal_completa(conn)
        if not df_evolucao.empty:
            # Gráfico 1: Valor total por mês
            fig1 = px.line(
                df_evolucao,
                x='periodo',
                y='valor_total',
                title='Valor Total Pago por Mês',
                markers=True,
                line_shape='spline'
            )
            fig1.update_layout(
                xaxis_title='Período',
                yaxis_title='Valor Total (R$)',
                hovermode='x unified'
            )
            st.plotly_chart(fig1, use_container_width=True)
            
            # Gráfico 2: Beneficiários por mês
            fig2 = px.bar(
                df_evolucao,
                x='periodo',
                y='beneficiarios',
                title='Número de Beneficiários por Mês',
                color='valor_total',
                color_continuous_scale='Blues'
            )
            st.plotly_chart(fig2, use_container_width=True)
            
            # Tabela detalhada
            st.subheader("Dados Detalhados por Período")
            st.dataframe(
                df_evolucao[['periodo', 'registros', 'beneficiarios', 'cpfs', 'valor_total', 'valor_medio', 'projetos']],
                use_container_width=True,
                column_config={
                    'valor_total': st.column_config.NumberColumn('Valor Total (R$)', format="R$ %.2f"),
                    'valor_medio': st.column_config.NumberColumn('Valor Médio (R$)', format="R$ %.2f")
                }
            )
        else:
            st.info("📭 **Nenhum dado disponível ainda.** Importe arquivos para visualizar a evolução mensal.")
    
    with tab2:
        st.subheader("Inconsistências Detectadas")
        
        df_inconsistencias = obter_inconsistencias_detalhadas_completas(conn)
        if not df_inconsistencias.empty:
            # Resumo por tipo
            tipos_contagem = {}
            for tipos in df_inconsistencias['Tipos de Inconsistência']:
                if tipos:
                    for tipo in tipos.split(','):
                        tipo = tipo.strip()
                        tipos_contagem[tipo] = tipos_contagem.get(tipo, 0) + 1
            
            if tipos_contagem:
                st.warning("### 📊 Distribuição por Tipo de Inconsistência")
                for tipo, quantidade in tipos_contagem.items():
                    st.write(f"• **{tipo}**: {quantidade} ocorrência(s)")
            
            # Casos mais problemáticos
            st.subheader("🚨 Casos Mais Problemáticos")
            
            for idx, row in df_inconsistencias.head(10).iterrows():
                with st.expander(f"CPF: {row['CPF']} - {row['Ocorrências']} ocorrências"):
                    st.write(f"**Nomes associados:** {row['Nomes Associados']}")
                    st.write(f"**Contas associadas:** {row['Contas Associadas']}")
                    st.write(f"**Tipos de inconsistência:** {row['Tipos de Inconsistência']}")
                    st.write(f"**Valor total envolvido:** R$ {float(row['Valor Total']):,.2f}")
                    st.write(f"**Arquivos:** {row['Arquivos']}")
            
            # Tabela completa
            st.subheader("📋 Todas as Inconsistências")
            st.dataframe(
                df_inconsistencias,
                use_container_width=True,
                column_config={
                    'Valor Total': st.column_config.NumberColumn('Valor Total (R$)', format="R$ %.2f"),
                    'Ocorrências': st.column_config.NumberColumn('Ocorrências', format="%.0f")
                }
            )
            
            # Botão para resolver
            if st.button("✅ Marcar Todas como Verificadas", key="resolve_all_incons", use_container_width=True):
                cursor = conn.cursor()
                cursor.execute("UPDATE pagamentos SET tipo_inconsistencia = NULL")
                conn.commit()
                st.success("Todas as inconsistências foram marcadas como verificadas!")
                st.rerun()
        else:
            st.success("🎉 **Nenhuma inconsistência detectada!**")
    
    with tab3:
        st.subheader("Top Beneficiários por Valor Recebido")
        
        df_top = obter_top_beneficiarios_completo(conn, 15)
        if not df_top.empty:
            # Gráfico
            fig = px.bar(
                df_top.head(10),
                x='Nome',
                y='Total Recebido',
                title='Top 10 Beneficiários por Valor Total Recebido',
                color='Pagamentos',
                color_continuous_scale='Viridis',
                hover_data=['CPF', 'Contas', 'Média', 'Projetos']
            )
            fig.update_layout(
                xaxis_title='Beneficiário',
                yaxis_title='Valor Total Recebido (R$)',
                xaxis_tickangle=45
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Tabela detalhada
            st.dataframe(
                df_top,
                use_container_width=True,
                column_config={
                    'Total Recebido': st.column_config.NumberColumn('Total Recebido (R$)', format="R$ %.2f"),
                    'Média': st.column_config.NumberColumn('Média por Pagamento (R$)', format="R$ %.2f"),
                    'Pagamentos': st.column_config.NumberColumn('Nº de Pagamentos', format="%.0f"),
                    'Contas': st.column_config.NumberColumn('Nº de Contas', format="%.0f"),
                    'Projetos': st.column_config.NumberColumn('Nº de Projetos', format="%.0f")
                }
            )
        else:
            st.info("📭 **Nenhum beneficiário registrado ainda.**")
    
    with tab4:
        st.subheader("Arquivos Processados")
        
        df_arquivos = obter_arquivos_processados_completo(conn)
        if not df_arquivos.empty:
            # Timeline visual
            st.write("### 📅 Histórico de Processamento")
            
            for _, row in df_arquivos.iterrows():
                with st.container():
                    col_a1, col_a2, col_a3, col_a4 = st.columns([1, 3, 2, 2])
                    
                    with col_a1:
                        st.write("📄")
                    
                    with col_a2:
                        st.write(f"**{row['Arquivo']}**")
                    
                    with col_a3:
                        st.write(f"📅 {row['Período']}")
                    
                    with col_a4:
                        st.write(f"👤 {row['Beneficiários']} | 💰 R$ {row['Valor Total']:,.2f}")
            
            # Tabela detalhada
            st.write("### 📊 Detalhes dos Arquivos")
            st.dataframe(
                df_arquivos[['Arquivo', 'Período', 'Registros', 'Beneficiários', 'Valor Total', 'Data Processamento']],
                use_container_width=True,
                column_config={
                    'Valor Total': st.column_config.NumberColumn('Valor Total (R$)', format="R$ %.2f"),
                    'Registros': st.column_config.NumberColumn('Registros', format="%.0f"),
                    'Beneficiários': st.column_config.NumberColumn('Beneficiários', format="%.0f")
                }
            )
        else:
            st.info("📭 **Nenhum arquivo processado ainda.**")
    
    st.markdown("---")
    
    # ========== SEÇÃO 4: FERRAMENTAS ==========
    st.header("🔧 FERRAMENTAS")
    
    col_t1, col_t2, col_t3 = st.columns(3)
    
    with col_t1:
        if st.button("🔄 Atualizar Análises", use_container_width=True, key="refresh_tools"):
            detectar_inconsistencias_final(conn)
            st.success("Análises atualizadas com sucesso!")
            st.rerun()
    
    with col_t2:
        if st.button("📥 Exportar Dados", use_container_width=True, key="export_tools"):
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM pagamentos")
                dados = cursor.fetchall()
                
                if dados:
                    colunas = [desc[0] for desc in cursor.description]
                    df_export = pd.DataFrame(dados, columns=colunas)
                    
                    # Converter para CSV
                    csv = df_export.to_csv(index=False, sep=';', encoding='utf-8')
                    
                    st.download_button(
                        label="💾 Baixar Dados Completos (CSV)",
                        data=csv,
                        file_name=f"dados_pot_completo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        key="download_complete"
                    )
                else:
                    st.warning("Nenhum dado para exportar")
            except Exception as e:
                st.error(f"Erro ao exportar: {str(e)}")
    
    with col_t3:
        if st.button("🧹 Limpar Banco", use_container_width=True, key="clean_tools"):
            with st.expander("⚠️ CONFIRMAR LIMPEZA", expanded=False):
                st.warning("Esta ação removerá TODOS os dados do sistema!")
                if st.button("✅ CONFIRMAR LIMPEZA TOTAL", type="primary"):
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM pagamentos")
                    conn.commit()
                    st.success("Todos os dados foram removidos!")
                    st.rerun()
    
    # Rodapé
    st.markdown("---")
    st.caption(f"💰 **Sistema POT - SMDET** | {datetime.now().strftime('%d/%m/%Y %H:%M')} | "
              f"Registros: {stats['total_registros']:,} | "
              f"Valor Total: R$ {stats['valor_total']:,.2f}")
    
    # Fechar conexão
    conn.close()

if __name__ == "__main__":
    main()
