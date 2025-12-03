# app.py - SISTEMA POT SMDET - GESTÃO DE BENEFÍCIOS (VERSÃO CORRIGIDA)
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
import io

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
        'num_cartao': 'numero_conta',
        'numcartao': 'numero_conta',
        'n_cartao': 'numero_conta',
        'cartao': 'numero_conta',
        'numcartão': 'numero_conta',
        'n_cartão': 'numero_conta',
        'num_cartão': 'numero_conta',
        
        # Nome do beneficiário
        'nome': 'nome',
        'nome_do_beneficiário': 'nome',
        'nome_do_beneficiario': 'nome',
        'nome_do_benefici?io': 'nome',  # Corrige problema de encoding
        'beneficiario': 'nome',
        'beneficiário': 'nome',
        'nome_beneficiario': 'nome',
        
        # Valor
        'valor': 'valor',
        'valor_pagto': 'valor',
        'valorpagto': 'valor',
        'valor_total': 'valor',
        'valortotal': 'valor',
        'valor_pagamento': 'valor',
        'valor_pago': 'valor',
        'valor_pgto': 'valor',
        
        # Data
        'data_pagto': 'data_pagamento',
        'datapagto': 'data_pagamento',
        'data_pagamento': 'data_pagamento',
        'data': 'data_pagamento',
        'data_pgto': 'data_pagamento',
        
        # CPF
        'cpf': 'cpf',
        
        # Projeto
        'projeto': 'projeto',
        
        # Agência
        'agencia': 'agencia',
        'agência': 'agencia',
        'ag': 'agencia',
        
        # RG
        'rg': 'rg',
        
        # Dias
        'dias_validos': 'dias_validos',
        'dias_a_pagar': 'dias_a_pagar',
        'dias': 'dias',
        
        # Valor por dia
        'valor_dia': 'valor_dia',
        'valordia': 'valor_dia',
        
        # Ordem
        'ordem': 'ordem',
        
        # Distrito
        'distrito': 'distrito',
        
        # Desconto
        'valor_desconto': 'valor_desconto',
        'valordesconto': 'valor_desconto',
    }
    
    # Limpar o nome
    nome_limpo = nome_coluna.strip().lower()
    nome_limpo = re.sub(r'[\s\-]+', '_', nome_limpo)  # Substitui espaços e hífens por _
    nome_limpo = nome_limpo.replace('?', 'a')  # Corrige encoding
    nome_limpo = re.sub(r'[^\w_]', '', nome_limpo)  # Remove caracteres especiais
    
    # Aplicar mapeamento
    return mapeamento.get(nome_limpo, nome_limpo)

def processar_cpf(cpf):
    """Limpa e formata CPF"""
    if pd.isna(cpf):
        return None
    
    cpf_str = str(cpf).strip()
    if cpf_str in ['', 'nan', 'None', 'NaN', 'NaT', 'NULL']:
        return None
    
    # Remove tudo que não é número
    cpf_limpo = re.sub(r'\D', '', cpf_str)
    
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
    
    valor_str = str(valor).strip()
    if valor_str in ['', 'nan', 'None', 'NaN']:
        return 0.0
    
    try:
        # Remove R$, pontos e vírgulas
        valor_str = valor_str.replace('R$', '').replace('$', '').strip()
        valor_str = valor_str.replace('.', '').replace(',', '.')
        
        # Remove qualquer caractere não numérico exceto ponto
        valor_str = re.sub(r'[^\d\.\-]', '', valor_str)
        
        # Tenta converter para float
        return float(valor_str)
    except:
        try:
            # Tenta converter diretamente
            return float(valor_str)
        except:
            return 0.0

def processar_data(data_str):
    """Converte data para formato padrão"""
    if pd.isna(data_str):
        return None
    
    data_str = str(data_str).strip()
    if data_str in ['', 'nan', 'None', 'NaN']:
        return None
    
    try:
        # Tenta diferentes formatos
        formatos = [
            '%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', 
            '%d/%m/%y', '%d-%m-%y', '%Y/%m/%d',
            '%d.%m.%Y', '%d.%m.%y'
        ]
        
        for fmt in formatos:
            try:
                return datetime.strptime(data_str, fmt).date()
            except:
                continue
        
        # Se não conseguir, retorna None
        return None
    except:
        return None

def extrair_valor_seguro(row, coluna, default=''):
    """Extrai valor de uma coluna de forma segura"""
    try:
        if coluna in row:
            valor = row[coluna]
            if pd.isna(valor):
                return default
            return str(valor).strip()
        return default
    except:
        return default

# ========== PROCESSAMENTO DE ARQUIVOS ==========
def detectar_mes_ano_arquivo(nome_arquivo):
    """Detecta mês e ano do nome do arquivo"""
    nome_upper = nome_arquivo.upper()
    
    meses = {
        'JANEIRO': 1, 'JAN': 1,
        'FEVEREIRO': 2, 'FEV': 2,
        'MARÇO': 3, 'MARCO': 3, 'MAR': 3, 'MAR.': 3,
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
    if ano_match:
        ano = int(ano_match.group(1))
    else:
        # Tenta encontrar 2 dígitos
        ano_match = re.search(r'(\d{2})[^0-9]', nome_arquivo)
        if ano_match:
            ano = 2000 + int(ano_match.group(1))
        else:
            ano = datetime.now().year
    
    return mes, ano

def calcular_hash_arquivo(conteudo):
    """Calcula hash do arquivo para evitar duplicatas"""
    return hashlib.md5(conteudo).hexdigest()

def ler_arquivo(uploaded_file):
    """Lê arquivo de forma robusta"""
    try:
        # Salvar em arquivo temporário
        with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_path = tmp_file.name
        
        try:
            # Tentar diferentes métodos de leitura
            if uploaded_file.name.lower().endswith('.csv'):
                # Tentar diferentes encodings
                for encoding in ['latin-1', 'utf-8', 'cp1252', 'iso-8859-1']:
                    try:
                        df = pd.read_csv(tmp_path, sep=';', encoding=encoding, dtype=str)
                        if not df.empty:
                            break
                    except:
                        continue
                
                # Se não conseguiu com separador ';', tenta detectar automaticamente
                if df.empty:
                    df = pd.read_csv(tmp_path, sep=None, engine='python', dtype=str)
            
            elif uploaded_file.name.lower().endswith(('.xls', '.xlsx')):
                try:
                    df = pd.read_excel(tmp_path, dtype=str, engine='openpyxl')
                except:
                    df = pd.read_excel(tmp_path, dtype=str, engine='xlrd')
            
            else:
                return None, "Formato de arquivo não suportado"
            
            # Limpar arquivo temporário
            os.unlink(tmp_path)
            
            if df.empty:
                return None, "Arquivo vazio ou sem dados"
            
            return df, "Arquivo lido com sucesso"
            
        except Exception as e:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            return None, f"Erro ao ler arquivo: {str(e)}"
            
    except Exception as e:
        return None, f"Erro ao processar arquivo: {str(e)}"

def processar_planilha(uploaded_file, mes_manual=None, ano_manual=None):
    """Processa uma planilha de pagamentos - VERSÃO CORRIGIDA"""
    try:
        # Ler arquivo
        df, mensagem_leitura = ler_arquivo(uploaded_file)
        if df is None:
            return None, mensagem_leitura
        
        # Detectar mês e ano
        mes_detectado, ano_detectado = detectar_mes_ano_arquivo(uploaded_file.name)
        
        # Usar valores manuais se fornecidos, caso contrário usar detectados
        mes = mes_manual if mes_manual else mes_detectado
        ano = ano_manual if ano_manual else ano_detectado
        
        if not mes or not ano:
            st.warning(f"Não foi possível detectar mês/ano do arquivo. Usando mês atual.")
            mes = datetime.now().month
            ano = datetime.now().year
        
        # Normalizar cabeçalhos
        df.columns = [normalizar_nome_coluna(col) for col in df.columns]
        
        # Mostrar colunas encontradas para debug
        st.info(f"Colunas detectadas: {', '.join(df.columns)}")
        
        # Identificar coluna de valor (pode ter vários nomes)
        coluna_valor = None
        for col in df.columns:
            if 'valor' in col.lower() and 'desconto' not in col.lower():
                coluna_valor = col
                break
        
        if not coluna_valor:
            return None, "Não foi encontrada coluna de valor"
        
        # Identificar coluna de número da conta
        coluna_conta = None
        for col in df.columns:
            if any(term in col.lower() for term in ['conta', 'cartao', 'cartão', 'num']):
                coluna_conta = col
                break
        
        if not coluna_conta:
            return None, "Não foi encontrada coluna de número da conta/cartão"
        
        # Identificar coluna de nome
        coluna_nome = None
        for col in df.columns:
            if any(term in col.lower() for term in ['nome', 'beneficiario', 'beneficiário']):
                coluna_nome = col
                break
        
        if not coluna_nome:
            coluna_nome = 'nome'  # Usar padrão
            
        # Processar dados
        dados_processados = []
        
        for idx, row in df.iterrows():
            try:
                # Extrair valores de forma segura
                numero_conta = str(row.get(coluna_conta, '')).strip()
                nome = str(row.get(coluna_nome, '')).strip().title()
                valor_str = str(row.get(coluna_valor, '0')).strip()
                
                # Verificar se tem dados mínimos
                if not numero_conta or numero_conta.lower() in ['nan', 'none', '']:
                    continue
                
                if not nome or nome.lower() in ['nan', 'none', '']:
                    nome = "NÃO INFORMADO"
                
                # Processar CPF se existir
                cpf = None
                if 'cpf' in df.columns:
                    cpf = processar_cpf(row.get('cpf'))
                
                # Processar valor
                valor = processar_valor(valor_str)
                if valor <= 0:
                    continue  # Ignorar valores zero ou negativos
                
                # Processar data se existir
                data_pagamento = None
                if 'data_pagamento' in df.columns:
                    data_pagamento = processar_data(row.get('data_pagamento'))
                
                if not data_pagamento:
                    # Se não tem data, usa primeiro dia do mês de referência
                    try:
                        data_pagamento = datetime(ano, mes, 1).date()
                    except:
                        data_pagamento = datetime.now().date()
                
                # Criar registro processado
                registro = {
                    'numero_conta': numero_conta,
                    'nome': nome,
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
                registro = {k: v for k, v in registro.items() 
                          if v not in [None, '', 'nan', 'NaN', 'NÃO INFORMADO']}
                
                # Garantir campos obrigatórios
                registro['nome'] = nome
                registro['valor'] = valor
                
                dados_processados.append(registro)
                
            except Exception as e:
                # Ignorar linha com erro e continuar
                continue
        
        if not dados_processados:
            return None, "Nenhum registro válido encontrado no arquivo"
        
        return dados_processados, f"Processado: {len(dados_processados)} registros válidos"
        
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
            return False, "⚠️ Este arquivo já foi processado anteriormente"
        
        # Para cada registro, atualizar/inserir no banco
        total_valor = 0
        contas_processadas = set()
        
        for registro in dados_processados:
            try:
                # 1. Verificar/inserir beneficiário (se tiver CPF)
                if registro.get('cpf'):
                    cursor.execute('''
                        INSERT OR IGNORE INTO beneficiarios (cpf, nome, rg, projeto)
                        VALUES (?, ?, ?, ?)
                    ''', (
                        registro['cpf'], 
                        registro['nome'], 
                        registro.get('rg'), 
                        registro.get('projeto')
                    ))
                
                # 2. Verificar/inserir conta
                cursor.execute('''
                    INSERT OR IGNORE INTO contas (numero_conta, cpf_beneficiario, agencia, status)
                    VALUES (?, ?, ?, 'ATIVA')
                ''', (
                    registro['numero_conta'], 
                    registro.get('cpf'), 
                    registro.get('agencia')
                ))
                
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
                
            except Exception as e:
                # Continuar com próximo registro mesmo se um falhar
                continue
        
        # Registrar processamento do arquivo
        primeiro_registro = dados_processados[0] if dados_processados else {}
        cursor.execute('''
            INSERT INTO arquivos_processados 
            (nome_arquivo, mes_referencia, ano_referencia, tipo_arquivo, 
             total_registros, valor_total, hash_arquivo)
            VALUES (?, ?, ?, 'PAGAMENTO', ?, ?, ?)
        ''', (
            primeiro_registro.get('arquivo_origem', uploaded_file.name),
            primeiro_registro.get('mes_referencia', 0),
            primeiro_registro.get('ano_referencia', 0),
            len(dados_processados),
            total_valor,
            hash_arquivo
        ))
        
        conn.commit()
        
        # Atualizar métricas
        if dados_processados:
            atualizar_metricas_mensais(conn, dados_processados[0]['mes_referencia'], dados_processados[0]['ano_referencia'])
        
        return True, f"✅ Sucesso: {len(dados_processados)} registros salvos | R$ {total_valor:,.2f} | {len(contas_processadas)} contas"
        
    except Exception as e:
        conn.rollback()
        return False, f"❌ Erro ao salvar no banco: {str(e)}"

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
        
        # Se não houver resultados, usar zeros
        if not resultado or resultado[0] is None:
            resultado = (0, 0, 0, 0, 0)
        
        # Inserir ou atualizar métricas
        cursor.execute('''
            INSERT OR REPLACE INTO metricas_mensais 
            (mes, ano, total_beneficiarios, total_contas, total_pagamentos, 
             valor_total_pago, projetos_ativos)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (mes, ano, *resultado))
        
        conn.commit()
        
    except Exception as e:
        # Silenciar erro de métricas para não bloquear o processamento
        pass

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
            WHERE 1=1
        '''
        
        params = []
        if cpf:
            query += ' AND p.cpf_beneficiario = ?'
            params.append(cpf)
        elif numero_conta:
            query += ' AND p.numero_conta = ?'
            params.append(numero_conta)
        else:
            return pd.DataFrame()  # Retorna vazio se não houver critério
        
        query += ' ORDER BY p.ano_referencia DESC, p.mes_referencia DESC'
        
        cursor = conn.execute(query, params)
        colunas = [desc[0] for desc in cursor.description]
        dados = cursor.fetchall()
        
        return pd.DataFrame(dados, columns=colunas)
        
    except Exception as e:
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
                DATE(data_processamento) as data_processamento
            FROM arquivos_processados 
            ORDER BY data_processamento DESC
        ''')
        
        colunas = [desc[0] for desc in cursor.description]
        dados = cursor.fetchall()
        
        return pd.DataFrame(dados, columns=colunas)
        
    except Exception as e:
        return pd.DataFrame()

def obter_totais_gerais(conn):
    """Obtém totais gerais do sistema"""
    try:
        cursor = conn.cursor()
        
        # Total beneficiários
        cursor.execute("SELECT COUNT(DISTINCT cpf) FROM beneficiarios")
        total_benef = cursor.fetchone()[0] or 0
        
        # Total contas
        cursor.execute("SELECT COUNT(*) FROM contas")
        total_contas = cursor.fetchone()[0] or 0
        
        # Total pagamentos
        cursor.execute("SELECT COUNT(*) FROM pagamentos")
        total_pag = cursor.fetchone()[0] or 0
        
        # Total valor
        cursor.execute("SELECT SUM(valor_beneficio) FROM pagamentos")
        total_valor = cursor.fetchone()[0] or 0
        
        # Total arquivos
        cursor.execute("SELECT COUNT(*) FROM arquivos_processados")
        total_arquivos = cursor.fetchone()[0] or 0
        
        return {
            'beneficiarios': total_benef,
            'contas': total_contas,
            'pagamentos': total_pag,
            'valor_total': total_valor,
            'arquivos': total_arquivos
        }
        
    except Exception as e:
        return {
            'beneficiarios': 0,
            'contas': 0,
            'pagamentos': 0,
            'valor_total': 0,
            'arquivos': 0
        }

# ========== INTERFACE STREAMLIT ==========
def mostrar_dashboard(conn):
    """Mostra dashboard principal"""
    st.title("💰 Sistema POT - Gestão de Benefícios")
    st.markdown("---")
    
    # Obter totais gerais
    totais = obter_totais_gerais(conn)
    
    # Métricas gerais
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Beneficiários Cadastrados", f"{totais['beneficiarios']:,}")
    
    with col2:
        st.metric("Contas Ativas", f"{totais['contas']:,}")
    
    with col3:
        st.metric("Pagamentos Registrados", f"{totais['pagamentos']:,}")
    
    with col4:
        st.metric("Valor Total Pago", f"R$ {totais['valor_total']:,.2f}")
    
    st.markdown("---")
    
    # Resumo por mês
    st.subheader("📊 Resumo por Mês")
    df_resumo = obter_resumo_mensal(conn)
    
    if not df_resumo.empty:
        # Preparar dados para gráfico
        df_resumo['mes_ano'] = df_resumo['mes'].astype(str) + '/' + df_resumo['ano'].astype(str)
        
        # Gráfico de valores mensais
        fig = px.bar(
            df_resumo.sort_values(['ano', 'mes']), 
            x='mes_ano', 
            y='valor_total_pago',
            title="Valor Total Pago por Mês",
            labels={'mes_ano': 'Período', 'valor_total_pago': 'Valor Total (R$)'},
            color='valor_total_pago'
        )
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)
        
        # Tabela de resumo
        st.dataframe(
            df_resumo[['mes', 'ano', 'total_pagamentos', 'valor_total_pago', 'projetos_ativos']]
            .sort_values(['ano', 'mes'], ascending=[False, False]),
            use_container_width=True
        )
    else:
        st.info("📤 Nenhum dado processado ainda. Importe arquivos para começar.")

def mostrar_importacao(conn):
    """Interface de importação de arquivos"""
    st.header("📤 Importar Arquivos de Pagamento")
    
    with st.expander("ℹ️ Instruções", expanded=False):
        st.markdown("""
        ### Formatos suportados:
        - **CSV** (separado por ponto-e-vírgula `;`)
        - **Excel** (.xls, .xlsx)
        
        ### Colunas necessárias:
        - **Número da conta/cartão** (qualquer nome: 'Num Cartao', 'NumCartao', etc)
        - **Nome do beneficiário**
        - **Valor do pagamento**
        
        ### Colunas opcionais:
        - CPF, RG, Projeto, Agência, Data de pagamento
        
        ### Dica:
        O sistema detecta automaticamente o mês e ano pelo nome do arquivo.
        Exemplo: `Pgto_SETEMBRO_2024.csv` será processado como Setembro/2024
        """)
    
    uploaded_file = st.file_uploader(
        "Selecione o arquivo de pagamentos",
        type=['csv', 'xls', 'xlsx'],
        key="file_uploader"
    )
    
    if uploaded_file:
        st.info(f"📄 Arquivo selecionado: **{uploaded_file.name}**")
        
        # Detectar mês e ano
        mes_detectado, ano_detectado = detectar_mes_ano_arquivo(uploaded_file.name)
        
        # Mostrar detecção
        col1, col2 = st.columns(2)
        with col1:
            if mes_detectado:
                meses = ['', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                        'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
                st.info(f"📅 **Mês detectado:** {meses[mes_detectado]}")
            else:
                st.warning("⚠️ Não foi possível detectar o mês")
        
        with col2:
            if ano_detectado:
                st.info(f"📅 **Ano detectado:** {ano_detectado}")
            else:
                st.warning("⚠️ Não foi possível detectar o ano")
        
        # Permitir correção manual
        with st.expander("✏️ Corrigir mês/ano manualmente", expanded=False):
            col3, col4 = st.columns(2)
            with col3:
                meses_opcoes = ['', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                              'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
                mes_correcao = st.selectbox("Selecionar mês", meses_opcoes, 
                                           index=mes_detectado if mes_detectado else 0)
                mes_num = meses_opcoes.index(mes_correcao) if mes_correcao else None
            
            with col4:
                ano_atual = datetime.now().year
                anos_opcoes = [''] + list(range(ano_atual, ano_atual - 5, -1))
                ano_correcao = st.selectbox("Selecionar ano", anos_opcoes,
                                          index=0 if not ano_detectado else anos_opcoes.index(str(ano_detectado)))
                ano_num = int(ano_correcao) if ano_correcao else None
        
        # Botão para processar
        if st.button("🔄 Processar Arquivo", type="primary", use_container_width=True):
            with st.spinner("Processando arquivo..."):
                # Ler conteúdo para hash
                conteudo = uploaded_file.getvalue()
                hash_arquivo = calcular_hash_arquivo(conteudo)
                
                # Usar correção manual se fornecida
                mes_processar = mes_num if mes_num else mes_detectado
                ano_processar = ano_num if ano_num else ano_detectado
                
                if not mes_processar or not ano_processar:
                    st.error("❌ É necessário especificar mês e ano para processar o arquivo.")
                    return
                
                # Processar planilha
                dados_processados, mensagem = processar_planilha(
                    uploaded_file, 
                    mes_processar,
                    ano_processar
                )
                
                if dados_processados:
                    # Mostrar preview
                    st.subheader("📋 Pré-visualização dos Dados")
                    df_preview = pd.DataFrame(dados_processados[:20])
                    
                    # Formatar visualização
                    display_cols = ['nome', 'numero_conta', 'valor', 'projeto', 'data_pagamento']
                    display_cols = [col for col in display_cols if col in df_preview.columns]
                    
                    st.dataframe(
                        df_preview[display_cols].head(20),
                        use_container_width=True,
                        column_config={
                            'valor': st.column_config.NumberColumn(
                                'Valor (R$)',
                                format="R$ %.2f"
                            ),
                            'data_pagamento': st.column_config.DateColumn(
                                'Data Pagamento',
                                format="DD/MM/YYYY"
                            )
                        }
                    )
                    
                    # Estatísticas do processamento
                    st.subheader("📈 Estatísticas do Processamento")
                    
                    total_valor = sum(item['valor'] for item in dados_processados)
                    contas_unicas = len(set(item['numero_conta'] for item in dados_processados))
                    
                    col_stat1, col_stat2, col_stat3 = st.columns(3)
                    with col_stat1:
                        st.metric("Registros Válidos", len(dados_processados))
                    with col_stat2:
                        st.metric("Contas Únicas", contas_unicas)
                    with col_stat3:
                        st.metric("Valor Total", f"R$ {total_valor:,.2f}")
                    
                    # Confirmar importação
                    st.markdown("---")
                    st.subheader("✅ Confirmar Importação")
                    
                    if st.button("💾 SALVAR NO BANCO DE DADOS", type="primary", use_container_width=True):
                        sucesso, msg = salvar_dados_banco(conn, dados_processados, hash_arquivo)
                        
                        if sucesso:
                            st.success(msg)
                            st.balloons()
                            st.rerun()  # Atualizar a página
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
        
        col1, col2 = st.columns([2, 1])
        with col1:
            opcao = st.radio("Buscar por:", ["CPF", "Número da Conta"], horizontal=True)
        
        with col2:
            if opcao == "CPF":
                cpf_consulta = st.text_input("CPF (somente números)", placeholder="00000000000", key="cpf_input")
                numero_conta = None
            else:
                numero_conta = st.text_input("Número da Conta", placeholder="123456", key="conta_input")
                cpf_consulta = None
        
        if st.button("🔍 Buscar Histórico", use_container_width=True) and (cpf_consulta or numero_conta):
            df_historico = obter_historico_beneficiario(conn, cpf_consulta, numero_conta)
            
            if not df_historico.empty:
                # Estatísticas
                total_pago = df_historico['valor_beneficio'].sum()
                meses_ativos = df_historico['periodo'].nunique()
                
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    st.metric("Total Recebido", f"R$ {total_pago:,.2f}")
                with col_b:
                    st.metric("Meses Ativos", meses_ativos)
                with col_c:
                    st.metric("Média Mensal", f"R$ {total_pago/meses_ativos:,.2f}" if meses_ativos > 0 else "R$ 0,00")
                
                # Informações do beneficiário
                if not df_historico.empty:
                    st.info(f"👤 **{df_historico.iloc[0]['nome']}** | RG: {df_historico.iloc[0]['rg'] or 'Não informado'} | Agência: {df_historico.iloc[0]['agencia'] or 'Não informada'}")
                
                # Histórico em tabela
                st.subheader("📅 Histórico de Pagamentos")
                st.dataframe(
                    df_historico,
                    use_container_width=True,
                    column_config={
                        'valor_beneficio': st.column_config.NumberColumn(
                            'Valor (R$)',
                            format="R$ %.2f"
                        ),
                        'data_pagamento': st.column_config.DateColumn(
                            'Data',
                            format="DD/MM/YYYY"
                        )
                    }
                )
                
                # Gráfico
                st.subheader("📈 Evolução dos Pagamentos")
                df_historico_sorted = df_historico.sort_values('periodo')
                fig = px.line(
                    df_historico_sorted,
                    x='periodo',
                    y='valor_beneficio',
                    title="Histórico de Pagamentos",
                    markers=True,
                    labels={'periodo': 'Período', 'valor_beneficio': 'Valor (R$)'}
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("ℹ️ Nenhum registro encontrado")
    
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
            
            # Tabela detalhada
            st.dataframe(
                df_arquivos,
                use_container_width=True,
                column_config={
                    'valor_total': st.column_config.NumberColumn(
                        'Valor Total (R$)',
                        format="R$ %.2f"
                    )
                }
            )
            
            # Gráfico de evolução
            st.subheader("📊 Evolução das Importações")
            
            # Agrupar por mês/ano
            df_arquivos['mes_ano'] = df_arquivos['mes_referencia'].astype(str) + '/' + df_arquivos['ano_referencia'].astype(str)
            df_agrupado = df_arquivos.groupby('mes_ano').agg({
                'total_registros': 'sum',
                'valor_total': 'sum'
            }).reset_index()
            
            fig = px.bar(
                df_agrupado,
                x='mes_ano',
                y='valor_total',
                title="Valor Total Importado por Mês",
                labels={'mes_ano': 'Período', 'valor_total': 'Valor Total (R$)'},
                color='valor_total'
            )
            st.plotly_chart(fig, use_container_width=True)
            
        else:
            st.info("📭 Nenhum arquivo processado ainda")
    
    with tab3:
        st.subheader("📈 Análises Avançadas")
        
        # Top 10 beneficiários por valor
        try:
            cursor = conn.execute('''
                SELECT b.nome, SUM(p.valor_beneficio) as total_recebido, 
                       COUNT(DISTINCT p.mes_referencia || '/' || p.ano_referencia) as meses_ativos
                FROM pagamentos p
                LEFT JOIN beneficiarios b ON p.cpf_beneficiario = b.cpf
                GROUP BY p.cpf_beneficiario
                HAVING total_recebido > 0
                ORDER BY total_recebido DESC
                LIMIT 10
            ''')
            
            top_beneficiarios = cursor.fetchall()
            
            if top_beneficiarios:
                df_top = pd.DataFrame(top_beneficiarios, columns=['Nome', 'Total Recebido', 'Meses Ativos'])
                
                st.subheader("🏆 Top 10 Beneficiários por Valor Total")
                st.dataframe(
                    df_top,
                    use_container_width=True,
                    column_config={
                        'Total Recebido': st.column_config.NumberColumn(
                            'Total Recebido (R$)',
                            format="R$ %.2f"
                        )
                    }
                )
                
                # Gráfico de top beneficiários
                fig = px.bar(
                    df_top,
                    x='Nome',
                    y='Total Recebido',
                    title="Top 10 Beneficiários",
                    labels={'Nome': 'Beneficiário', 'Total Recebido': 'Valor Total (R$)'},
                    color='Total Recebido'
                )
                fig.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)
        except:
            pass
        
        # Distribuição por projeto
        try:
            cursor = conn.execute('''
                SELECT projeto, COUNT(*) as total_pagamentos, 
                       SUM(valor_beneficio) as valor_total,
                       COUNT(DISTINCT cpf_beneficiario) as beneficiarios
                FROM pagamentos 
                WHERE projeto IS NOT NULL AND projeto != ''
                GROUP BY projeto 
                ORDER BY valor_total DESC
            ''')
            
            projetos = cursor.fetchall()
            
            if projetos:
                df_projetos = pd.DataFrame(projetos, columns=['Projeto', 'Pagamentos', 'Valor Total', 'Beneficiários'])
                
                st.subheader("📋 Distribuição por Projeto")
                
                col_proj1, col_proj2 = st.columns(2)
                
                with col_proj1:
                    # Gráfico de pizza
                    fig = px.pie(
                        df_projetos.head(10),
                        values='Valor Total',
                        names='Projeto',
                        title="Top 10 Projetos por Valor"
                    )
                    st.plotly_chart(fig, use_container_width=True)
                
                with col_proj2:
                    st.dataframe(
                        df_projetos,
                        use_container_width=True,
                        column_config={
                            'Valor Total': st.column_config.NumberColumn(
                                'Valor Total (R$)',
                                format="R$ %.2f"
                            )
                        }
                    )
        except:
            pass

# ========== FUNÇÃO PRINCIPAL ==========
def main():
    # Inicializar banco
    conn = init_database()
    
    if not conn:
        st.error("❌ Não foi possível conectar ao banco de dados")
        return
    
    # Sidebar
    st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/Prefeitura_de_S%C3%A3o_Paulo_logo.png/320px-Prefeitura_de_S%C3%A3o_Paulo_logo.png", 
                    width=200)
    st.sidebar.title("💰 POT - SMDET")
    st.sidebar.markdown("**Gestão de Benefícios**")
    st.sidebar.markdown("---")
    
    # Menu
    menu = st.sidebar.radio(
        "Navegação",
        ["📊 Dashboard", "📤 Importar Arquivos", "🔍 Consultas", "⚙️ Configurações"]
    )
    
    # Exibir página selecionada
    if menu == "📊 Dashboard":
        mostrar_dashboard(conn)
    
    elif menu == "📤 Importar Arquivos":
        mostrar_importacao(conn)
    
    elif menu == "🔍 Consultas":
        mostrar_consultas(conn)
    
    elif menu == "⚙️ Configurações":
        st.header("⚙️ Configurações do Sistema")
        
        col_config1, col_config2 = st.columns(2)
        
        with col_config1:
            st.subheader("Banco de Dados")
            
            # Status do banco
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
                num_tabelas = cursor.fetchone()[0]
                st.info(f"✅ Banco conectado com {num_tabelas} tabelas")
            except:
                st.error("❌ Problema com o banco de dados")
            
            # Informações do sistema
            st.metric("Tamanho do BD", f"{os.path.getsize('pot_beneficios.db') / 1024 / 1024:.2f} MB" 
                     if os.path.exists('pot_beneficios.db') else "0 MB")
        
        with col_config2:
            st.subheader("Ações")
            
            # Botão para limpar dados
            st.warning("⚠️ Esta ação não pode ser desfeita!")
            
            if st.button("🗑️ Limpar Todos os Dados", type="secondary", use_container_width=True):
                try:
                    # Confirmar antes de apagar
                    confirmacao = st.checkbox("⚠️ CONFIRMAR: Apagar TODOS os dados permanentemente")
                    if confirmacao and st.button("✅ CONFIRMAR EXCLUSÃO", type="primary"):
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
            
            # Botão para backup
            st.markdown("---")
            if st.button("💾 Gerar Backup", use_container_width=True):
                try:
                    # Exportar dados para JSON
                    backup_data = {}
                    
                    for tabela in ['beneficiarios', 'contas', 'pagamentos', 'arquivos_processados', 'metricas_mensais']:
                        cursor = conn.execute(f"SELECT * FROM {tabela}")
                        colunas = [desc[0] for desc in cursor.description]
                        dados = cursor.fetchall()
                        backup_data[tabela] = {
                            'colunas': colunas,
                            'dados': dados
                        }
                    
                    # Criar arquivo de backup
                    backup_json = json.dumps(backup_data, ensure_ascii=False, default=str)
                    
                    st.download_button(
                        label="📥 Download Backup",
                        data=backup_json,
                        file_name=f"backup_pot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                        mime="application/json",
                        use_container_width=True
                    )
                except Exception as e:
                    st.error(f"Erro ao gerar backup: {str(e)}")
    
    # Rodapé
    st.sidebar.markdown("---")
    st.sidebar.caption(f"© {datetime.now().year} Prefeitura de São Paulo - SMDET")
    st.sidebar.caption("Sistema POT - Gestão de Benefícios")
    
    # Fechar conexão
    conn.close()

if __name__ == "__main__":
    main()
