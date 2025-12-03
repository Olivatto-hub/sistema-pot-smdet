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
import hashlib
import tempfile
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
    """Inicializa o banco de dados SQLite"""
    try:
        conn = sqlite3.connect('pot_smdet.db', check_same_thread=False)
        
        # Criar todas as tabelas se não existirem
        criar_tabelas(conn)
        
        return conn
        
    except Exception as e:
        st.error(f"❌ Erro ao inicializar banco de dados: {str(e)}")
        return None

def criar_tabelas(conn):
    """Cria todas as tabelas necessárias"""
    try:
        cursor = conn.cursor()
        
        # Tabela de beneficiários
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS beneficiarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cpf TEXT NOT NULL,
                nome TEXT NOT NULL,
                nome_normalizado TEXT,
                rg TEXT,
                telefone TEXT,
                email TEXT,
                endereco TEXT,
                bairro TEXT,
                status TEXT DEFAULT 'ATIVO',
                data_cadastro DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabela de pagamentos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pagamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                numero_conta TEXT NOT NULL,
                cpf_beneficiario TEXT NOT NULL,
                nome_beneficiario TEXT NOT NULL,
                projeto TEXT,
                mes_referencia INTEGER,
                ano_referencia INTEGER,
                valor_bruto DECIMAL(10,2) DEFAULT 0,
                valor_liquido DECIMAL(10,2) DEFAULT 0,
                valor_desconto DECIMAL(10,2) DEFAULT 0,
                dias_trabalhados INTEGER DEFAULT 20,
                status_pagamento TEXT DEFAULT 'PAGO',
                arquivo_origem TEXT,
                data_pagamento DATE,
                data_processamento DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabela de arquivos processados
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS arquivos_processados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome_arquivo TEXT NOT NULL,
                tipo_arquivo TEXT NOT NULL,
                mes_referencia INTEGER,
                ano_referencia INTEGER,
                total_registros INTEGER DEFAULT 0,
                registros_processados INTEGER DEFAULT 0,
                valor_total DECIMAL(15,2) DEFAULT 0,
                hash_arquivo TEXT NOT NULL,
                data_processamento DATETIME DEFAULT CURRENT_TIMESTAMP,
                status_processamento TEXT DEFAULT 'SUCESSO',
                erros_processamento TEXT
            )
        ''')
        
        # Tabela de inconsistências
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS inconsistências (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT NOT NULL,
                severidade TEXT NOT NULL,
                descricao TEXT NOT NULL,
                cpf_envolvido TEXT,
                conta_envolvida TEXT,
                data_deteccao DATETIME DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'PENDENTE',
                fonte_dados TEXT
            )
        ''')
        
        conn.commit()
        criar_indices(conn)
        
    except Exception as e:
        st.error(f"Erro ao criar tabelas: {str(e)}")

def criar_indices(conn):
    """Cria índices para melhorar performance"""
    try:
        cursor = conn.cursor()
        
        # Índices para beneficiários
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_benef_cpf ON beneficiarios(cpf)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_benef_nome ON beneficiarios(nome_normalizado)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_benef_status ON beneficiarios(status)')
        
        # Índices para pagamentos
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pag_cpf ON pagamentos(cpf_beneficiario)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pag_mes_ano ON pagamentos(ano_referencia, mes_referencia)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pag_conta ON pagamentos(numero_conta)')
        
        # Índices para arquivos processados
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_arq_hash ON arquivos_processados(hash_arquivo)')
        
        # Índices para inconsistências
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_inc_status ON inconsistências(status)')
        
        conn.commit()
    except:
        pass

# ========== FUNÇÕES AUXILIARES ==========
def normalizar_nome(nome):
    """Normaliza nome"""
    if pd.isna(nome) or not isinstance(nome, str):
        return ""
    
    nome = str(nome).strip()
    nome = re.sub(r'\s+', ' ', nome)
    nome = nome.upper()
    
    substituicoes = {
        'Á': 'A', 'À': 'A', 'Â': 'A', 'Ã': 'A',
        'É': 'E', 'È': 'E', 'Ê': 'E',
        'Í': 'I', 'Ì': 'I', 'Î': 'I',
        'Ó': 'O', 'Ò': 'O', 'Ô': 'O', 'Õ': 'O',
        'Ú': 'U', 'Ù': 'U', 'Û': 'U',
        'Ç': 'C', 'Ñ': 'N'
    }
    
    for char, subst in substituicoes.items():
        nome = nome.replace(char, subst)
    
    return nome

def normalizar_cpf(cpf):
    """Normaliza CPF"""
    if pd.isna(cpf):
        return ""
    
    cpf_str = str(cpf).strip()
    cpf_limpo = re.sub(r'\D', '', cpf_str)
    
    if len(cpf_limpo) == 11:
        return cpf_limpo
    elif len(cpf_limpo) > 11:
        return cpf_limpo[:11]
    else:
        return cpf_limpo.zfill(11)

def normalizar_valor(valor):
    """Converte valor para numérico"""
    if pd.isna(valor):
        return 0.0
    
    valor_str = str(valor).strip()
    valor_str = re.sub(r'[R\$\s]', '', valor_str)
    
    # Tratar diferentes formatos
    if ',' in valor_str and '.' in valor_str:
        valor_str = valor_str.replace('.', '').replace(',', '.')
    elif ',' in valor_str:
        if ',' in valor_str and valor_str.count(',') == 1:
            partes = valor_str.split(',')
            if len(partes[1]) == 2:
                valor_str = valor_str.replace(',', '.')
            else:
                valor_str = valor_str.replace(',', '')
        else:
            valor_str = valor_str.replace(',', '')
    
    try:
        return float(valor_str)
    except:
        return 0.0

def normalizar_nome_coluna(nome_coluna):
    """Normaliza nomes de colunas"""
    if not isinstance(nome_coluna, str):
        nome_coluna = str(nome_coluna)
    
    mapeamento = {
        'num_cartao': 'numero_conta',
        'numcartao': 'numero_conta',
        'cartao': 'numero_conta',
        'num_conta': 'numero_conta',
        'conta': 'numero_conta',
        'codigo': 'numero_conta',
        
        'nome': 'nome',
        'nome_beneficiario': 'nome',
        'beneficiario': 'nome',
        'nome_completo': 'nome',
        
        'cpf': 'cpf',
        'cpf_beneficiario': 'cpf',
        
        'projeto': 'projeto',
        'programa': 'projeto',
        'cod_projeto': 'projeto',
        
        'valor': 'valor',
        'valor_total': 'valor',
        'valor_pagto': 'valor',
        'valor_pagamento': 'valor',
        'valor_liquido': 'valor_liquido',
        
        'dias': 'dias_trabalhados',
        'dias_trabalhados': 'dias_trabalhados',
        
        'valor_dia': 'valor_diario',
        'valor_diario': 'valor_diario',
        
        'data_pagto': 'data_pagamento',
        'data_pagamento': 'data_pagamento',
        'data': 'data_pagamento'
    }
    
    nome_limpo = nome_coluna.strip().lower()
    nome_limpo = re.sub(r'[\s\-\.]+', '_', nome_limpo)
    nome_limpo = re.sub(r'[^\w_]', '', nome_limpo)
    
    return mapeamento.get(nome_limpo, nome_limpo)

# ========== PROCESSAMENTO DE ARQUIVOS ==========
def processar_arquivo(uploaded_file, tipo_arquivo, conn, mes=None, ano=None):
    """Processa arquivo enviado"""
    try:
        # Calcular hash do arquivo
        conteudo = uploaded_file.getvalue()
        hash_arquivo = hashlib.md5(conteudo).hexdigest()
        
        # Verificar se já foi processado
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM arquivos_processados WHERE hash_arquivo = ?", (hash_arquivo,))
        if cursor.fetchone():
            return False, "Arquivo já processado anteriormente", []
        
        # Detectar mês e ano se não informados
        if not mes or not ano:
            mes, ano = detectar_mes_ano(uploaded_file.name)
        
        # Ler arquivo
        df, mensagem = ler_arquivo(uploaded_file)
        if df is None:
            return False, mensagem, []
        
        # Normalizar cabeçalhos
        df.columns = [normalizar_nome_coluna(col) for col in df.columns]
        
        # Detectar inconsistências
        inconsistencias = detectar_inconsistencias(df, tipo_arquivo)
        
        # Processar de acordo com o tipo
        if tipo_arquivo == 'PAGAMENTOS':
            sucesso, mensagem = processar_pagamentos(df, mes, ano, uploaded_file.name, hash_arquivo, conn)
        elif tipo_arquivo == 'CADASTRO':
            sucesso, mensagem = processar_cadastro(df, uploaded_file.name, hash_arquivo, conn)
        else:
            return False, f"Tipo de arquivo não suportado: {tipo_arquivo}", inconsistencias
        
        # Registrar processamento
        registrar_processamento(uploaded_file.name, tipo_arquivo, mes, ano, 
                              len(df), hash_arquivo, sucesso, mensagem, conn)
        
        # Registrar inconsistências
        if inconsistencias:
            registrar_inconsistencias(inconsistencias, tipo_arquivo, uploaded_file.name, conn)
        
        return sucesso, mensagem, inconsistencias
        
    except Exception as e:
        return False, f"Erro ao processar arquivo: {str(e)}", []

def ler_arquivo(uploaded_file):
    """Lê arquivo CSV ou Excel"""
    try:
        # Salvar em arquivo temporário
        with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_path = tmp_file.name
        
        try:
            # Determinar tipo de arquivo
            if uploaded_file.name.lower().endswith('.csv'):
                # Tentar diferentes encodings e separadores
                for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
                    try:
                        df = pd.read_csv(tmp_path, sep=';', encoding=encoding, dtype=str)
                        if not df.empty:
                            break
                    except:
                        continue
                
                # Se ainda vazio, tentar com separador automático
                if df.empty or len(df.columns) == 1:
                    try:
                        df = pd.read_csv(tmp_path, sep=None, engine='python', dtype=str)
                    except:
                        df = pd.read_csv(tmp_path, sep=',', dtype=str)
            
            elif uploaded_file.name.lower().endswith(('.xls', '.xlsx')):
                try:
                    df = pd.read_excel(tmp_path, dtype=str)
                except:
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
            
            # Remover colunas completamente vazias
            df = df.dropna(axis=1, how='all')
            
            return df, "Arquivo lido com sucesso"
            
        except Exception as e:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            return None, f"Erro ao ler arquivo: {str(e)}"
            
    except Exception as e:
        return None, f"Erro ao processar arquivo: {str(e)}"

def detectar_mes_ano(nome_arquivo):
    """Detecta mês e ano do nome do arquivo"""
    nome_upper = nome_arquivo.upper()
    
    meses = {
        'JANEIRO': 1, 'JAN': 1,
        'FEVEREIRO': 2, 'FEV': 2,
        'MARCO': 3, 'MAR': 3,
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
    
    # Detectar mês
    mes = None
    for mes_nome, mes_num in meses.items():
        if mes_nome in nome_upper:
            mes = mes_num
            break
    
    # Detectar ano
    ano = datetime.now().year
    ano_match = re.search(r'(20\d{2})', nome_upper)
    if ano_match:
        ano = int(ano_match.group(1))
    
    # Se não detectou mês, usar mês atual
    if mes is None:
        mes = datetime.now().month
    
    return mes, ano

def detectar_inconsistencias(df, tipo_arquivo):
    """Detecta inconsistências nos dados"""
    inconsistencias = []
    
    # Verificar colunas obrigatórias
    if tipo_arquivo == 'PAGAMENTOS':
        obrigatorias = ['numero_conta', 'nome', 'valor']
    elif tipo_arquivo == 'CADASTRO':
        obrigatorias = ['cpf', 'nome']
    else:
        obrigatorias = []
    
    colunas_faltantes = [col for col in obrigatorias if col not in df.columns]
    if colunas_faltantes:
        inconsistencias.append({
            'tipo': 'COLUNAS_FALTANTES',
            'severidade': 'ALTA',
            'descricao': f'Colunas obrigatórias faltantes: {", ".join(colunas_faltantes)}'
        })
    
    # Verificar valores nulos nas colunas obrigatórias
    for col in obrigatorias:
        if col in df.columns:
            nulos = df[col].isna().sum()
            if nulos > 0:
                inconsistencias.append({
                    'tipo': f'VALORES_NULOS_{col.upper()}',
                    'severidade': 'MEDIA',
                    'descricao': f'{nulos} registros sem valor na coluna {col}'
                })
    
    # Verificar valores zerados para pagamentos
    if tipo_arquivo == 'PAGAMENTOS' and 'valor' in df.columns:
        zerados = (df['valor'].apply(normalizar_valor) <= 0).sum()
        if zerados > 0:
            inconsistencias.append({
                'tipo': 'VALORES_ZERADOS',
                'severidade': 'ALTA',
                'descricao': f'{zerados} registros com valor zerado ou negativo'
            })
    
    return inconsistencias

def registrar_processamento(nome_arquivo, tipo_arquivo, mes, ano, total_registros, 
                           hash_arquivo, sucesso, mensagem, conn):
    """Registra processamento do arquivo"""
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO arquivos_processados 
            (nome_arquivo, tipo_arquivo, mes_referencia, ano_referencia, 
             total_registros, hash_arquivo, status_processamento, erros_processamento)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            nome_arquivo,
            tipo_arquivo,
            mes,
            ano,
            total_registros,
            hash_arquivo,
            'SUCESSO' if sucesso else 'ERRO',
            None if sucesso else mensagem
        ))
        conn.commit()
    except Exception as e:
        print(f"Erro ao registrar processamento: {str(e)}")

def registrar_inconsistencias(inconsistencias, fonte_dados, arquivo_origem, conn):
    """Registra inconsistências detectadas"""
    try:
        cursor = conn.cursor()
        for inc in inconsistencias:
            cursor.execute('''
                INSERT INTO inconsistências 
                (tipo, severidade, descricao, fonte_dados)
                VALUES (?, ?, ?, ?)
            ''', (
                inc['tipo'],
                inc['severidade'],
                inc['descricao'],
                fonte_dados
            ))
        conn.commit()
    except Exception as e:
        print(f"Erro ao registrar inconsistências: {str(e)}")

def processar_pagamentos(df, mes, ano, nome_arquivo, hash_arquivo, conn):
    """Processa arquivo de pagamentos"""
    try:
        cursor = conn.cursor()
        registros_processados = 0
        valor_total = 0
        
        for _, row in df.iterrows():
            try:
                # Extrair dados básicos
                numero_conta = str(row.get('numero_conta', '')).strip()
                nome = normalizar_nome(str(row.get('nome', '')))
                cpf = normalizar_cpf(row.get('cpf', ''))
                valor_bruto = normalizar_valor(row.get('valor'))
                projeto = str(row.get('projeto', '')).strip()
                dias = int(row.get('dias_trabalhados', 20))
                
                # Validar dados mínimos
                if not numero_conta or not nome or valor_bruto <= 0:
                    continue
                
                # Usar valor bruto como líquido se não informado
                valor_liquido = normalizar_valor(row.get('valor_liquido', valor_bruto))
                valor_desconto = valor_bruto - valor_liquido
                
                # Se não tem CPF, buscar do banco ou criar placeholder
                if not cpf or len(cpf) != 11:
                    cursor.execute("SELECT cpf FROM beneficiarios WHERE nome_normalizado LIKE ? LIMIT 1", 
                                 (f"%{nome}%",))
                    resultado = cursor.fetchone()
                    if resultado:
                        cpf = resultado[0]
                    else:
                        cpf = f"SEMCPF{registros_processados:06d}"
                
                # Inserir beneficiário se não existir
                cursor.execute('''
                    INSERT OR IGNORE INTO beneficiarios 
                    (cpf, nome, nome_normalizado, status)
                    VALUES (?, ?, ?, 'ATIVO')
                ''', (cpf, nome, nome))
                
                # Inserir pagamento
                cursor.execute('''
                    INSERT INTO pagamentos 
                    (numero_conta, cpf_beneficiario, nome_beneficiario, projeto,
                     mes_referencia, ano_referencia, valor_bruto, valor_desconto,
                     valor_liquido, dias_trabalhados, arquivo_origem)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    numero_conta, cpf, nome, projeto, mes, ano, 
                    valor_bruto, valor_desconto, valor_liquido, dias, nome_arquivo
                ))
                
                registros_processados += 1
                valor_total += valor_liquido
                
            except Exception as e:
                # Continuar com próximo registro
                continue
        
        conn.commit()
        
        # Atualizar arquivo processado com valores
        cursor.execute('''
            UPDATE arquivos_processados 
            SET registros_processados = ?,
                valor_total = ?
            WHERE hash_arquivo = ?
        ''', (registros_processados, valor_total, hash_arquivo))
        conn.commit()
        
        return True, f"Processados {registros_processados} pagamentos | Valor total: R$ {valor_total:,.2f}"
        
    except Exception as e:
        conn.rollback()
        return False, f"Erro ao processar pagamentos: {str(e)}"

def processar_cadastro(df, nome_arquivo, hash_arquivo, conn):
    """Processa arquivo de cadastro"""
    try:
        cursor = conn.cursor()
        registros_processados = 0
        
        for _, row in df.iterrows():
            try:
                cpf = normalizar_cpf(row.get('cpf'))
                nome = normalizar_nome(str(row.get('nome', '')))
                rg = str(row.get('rg', '')).strip()
                telefone = str(row.get('telefone', '')).strip()
                email = str(row.get('email', '')).strip()
                endereco = str(row.get('endereco', '')).strip()
                bairro = str(row.get('bairro', '')).strip()
                
                # Validar dados mínimos
                if not cpf or not nome:
                    continue
                
                # Inserir ou atualizar beneficiário
                cursor.execute('''
                    INSERT OR REPLACE INTO beneficiarios 
                    (cpf, nome, nome_normalizado, rg, telefone, email, endereco, bairro, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ATIVO')
                ''', (cpf, nome, nome, rg, telefone, email, endereco, bairro))
                
                registros_processados += 1
                
            except Exception as e:
                continue
        
        conn.commit()
        
        # Atualizar arquivo processado
        cursor.execute('''
            UPDATE arquivos_processados 
            SET registros_processados = ?
            WHERE hash_arquivo = ?
        ''', (registros_processados, hash_arquivo))
        conn.commit()
        
        return True, f"Processados {registros_processados} cadastros de beneficiários"
        
    except Exception as e:
        conn.rollback()
        return False, f"Erro ao processar cadastro: {str(e)}"

# ========== FUNÇÕES DE ANÁLISE ==========
def obter_resumo_geral(conn):
    """Obtém resumo geral do sistema"""
    try:
        cursor = conn.cursor()
        resumo = {}
        
        # Total de beneficiários ativos
        cursor.execute("SELECT COUNT(*) FROM beneficiarios WHERE status = 'ATIVO'")
        resumo['beneficiarios_ativos'] = cursor.fetchone()[0] or 0
        
        # Total de beneficiários com pagamentos
        cursor.execute("SELECT COUNT(DISTINCT cpf_beneficiario) FROM pagamentos")
        resumo['beneficiarios_pagos'] = cursor.fetchone()[0] or 0
        
        # Valor total pago
        cursor.execute("SELECT SUM(valor_liquido) FROM pagamentos")
        resultado = cursor.fetchone()[0]
        resumo['valor_total_pago'] = float(resultado) if resultado else 0
        
        # Total de pagamentos
        cursor.execute("SELECT COUNT(*) FROM pagamentos")
        resumo['total_pagamentos'] = cursor.fetchone()[0] or 0
        
        # Inconsistências pendentes
        cursor.execute("SELECT COUNT(*) FROM inconsistências WHERE status = 'PENDENTE'")
        resumo['inconsistencias_pendentes'] = cursor.fetchone()[0] or 0
        
        # Último mês processado
        cursor.execute('''
            SELECT MAX(ano_referencia), MAX(mes_referencia)
            FROM pagamentos
        ''')
        resultado = cursor.fetchone()
        if resultado and resultado[0]:
            resumo['ultimo_mes_processado'] = f"{resultado[1]:02d}/{resultado[0]}"
        else:
            resumo['ultimo_mes_processado'] = "Nenhum"
        
        # Arquivos processados
        cursor.execute("SELECT COUNT(*) FROM arquivos_processados WHERE status_processamento = 'SUCESSO'")
        resumo['arquivos_processados'] = cursor.fetchone()[0] or 0
        
        return resumo
        
    except Exception as e:
        print(f"Erro ao obter resumo: {str(e)}")
        return {
            'beneficiarios_ativos': 0,
            'beneficiarios_pagos': 0,
            'valor_total_pago': 0,
            'total_pagamentos': 0,
            'inconsistencias_pendentes': 0,
            'ultimo_mes_processado': 'Nenhum',
            'arquivos_processados': 0
        }

def obter_resumo_mensal(conn, mes=None, ano=None):
    """Obtém resumo mensal"""
    try:
        cursor = conn.cursor()
        
        if mes and ano:
            cursor.execute('''
                SELECT 
                    mes_referencia,
                    ano_referencia,
                    COUNT(DISTINCT cpf_beneficiario) as beneficiarios,
                    COUNT(*) as pagamentos,
                    SUM(valor_liquido) as valor_total,
                    AVG(valor_liquido) as valor_medio,
                    SUM(dias_trabalhados) as total_dias
                FROM pagamentos
                WHERE mes_referencia = ? AND ano_referencia = ?
                GROUP BY mes_referencia, ano_referencia
            ''', (mes, ano))
        else:
            cursor.execute('''
                SELECT 
                    mes_referencia,
                    ano_referencia,
                    COUNT(DISTINCT cpf_beneficiario) as beneficiarios,
                    COUNT(*) as pagamentos,
                    SUM(valor_liquido) as valor_total,
                    AVG(valor_liquido) as valor_medio,
                    SUM(dias_trabalhados) as total_dias
                FROM pagamentos
                GROUP BY ano_referencia, mes_referencia
                ORDER BY ano_referencia DESC, mes_referencia DESC
                LIMIT 12
            ''')
        
        resultados = cursor.fetchall()
        if resultados:
            df = pd.DataFrame(resultados, 
                columns=['mes', 'ano', 'beneficiarios', 'pagamentos', 'valor_total', 'valor_medio', 'dias'])
            df['periodo'] = df['mes'].astype(str).str.zfill(2) + '/' + df['ano'].astype(str)
            return df
        else:
            return pd.DataFrame()
    except:
        return pd.DataFrame()

def obter_inconsistencias(conn):
    """Obtém inconsistências pendentes"""
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                tipo,
                severidade,
                COUNT(*) as quantidade,
                GROUP_CONCAT(DISTINCT cpf_envolvido) as cpfs
            FROM inconsistências
            WHERE status = 'PENDENTE'
            GROUP BY tipo, severidade
            ORDER BY 
                CASE severidade 
                    WHEN 'CRITICA' THEN 1
                    WHEN 'ALTA' THEN 2
                    WHEN 'MEDIA' THEN 3
                    WHEN 'BAIXA' THEN 4
                    ELSE 5
                END
        ''')
        
        resultados = cursor.fetchall()
        if resultados:
            return pd.DataFrame(resultados, columns=['tipo', 'severidade', 'quantidade', 'cpfs'])
        else:
            return pd.DataFrame()
    except:
        return pd.DataFrame()

def obter_pagamentos_por_projeto(conn, mes=None, ano=None):
    """Obtém pagamentos agrupados por projeto"""
    try:
        cursor = conn.cursor()
        
        if mes and ano:
            cursor.execute('''
                SELECT 
                    COALESCE(projeto, 'NÃO INFORMADO') as projeto,
                    COUNT(*) as pagamentos,
                    SUM(valor_liquido) as valor_total,
                    AVG(valor_liquido) as valor_medio,
                    COUNT(DISTINCT cpf_beneficiario) as beneficiarios,
                    SUM(dias_trabalhados) as dias
                FROM pagamentos
                WHERE mes_referencia = ? AND ano_referencia = ?
                GROUP BY projeto
                ORDER BY valor_total DESC
            ''', (mes, ano))
        else:
            cursor.execute('''
                SELECT 
                    COALESCE(projeto, 'NÃO INFORMADO') as projeto,
                    COUNT(*) as pagamentos,
                    SUM(valor_liquido) as valor_total,
                    AVG(valor_liquido) as valor_medio,
                    COUNT(DISTINCT cpf_beneficiario) as beneficiarios,
                    SUM(dias_trabalhados) as dias
                FROM pagamentos
                GROUP BY projeto
                ORDER BY valor_total DESC
            ''')
        
        resultados = cursor.fetchall()
        if resultados:
            return pd.DataFrame(resultados, 
                columns=['projeto', 'pagamentos', 'valor_total', 'valor_medio', 'beneficiarios', 'dias'])
        else:
            return pd.DataFrame()
    except:
        return pd.DataFrame()

def obter_beneficiarios_problema(conn, limite=20):
    """Identifica beneficiários com problemas"""
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                b.cpf,
                b.nome,
                COUNT(DISTINCT p.id) as pagamentos,
                SUM(p.valor_liquido) as total,
                COUNT(DISTINCT i.id) as inconsistências
            FROM beneficiarios b
            LEFT JOIN pagamentos p ON b.cpf = p.cpf_beneficiario
            LEFT JOIN inconsistências i ON b.cpf = i.cpf_envolvido AND i.status = 'PENDENTE'
            WHERE b.status = 'ATIVO'
            GROUP BY b.cpf, b.nome
            HAVING inconsistências > 0
            ORDER BY inconsistências DESC
            LIMIT ?
        ''', (limite,))
        
        resultados = cursor.fetchall()
        if resultados:
            return pd.DataFrame(resultados, 
                columns=['cpf', 'nome', 'pagamentos', 'total', 'inconsistencias'])
        else:
            return pd.DataFrame()
    except:
        return pd.DataFrame()

# ========== INTERFACE STREAMLIT ==========
def mostrar_dashboard(conn):
    """Mostra dashboard principal"""
    st.title("💰 Sistema POT - Gestão de Benefícios")
    st.markdown("---")
    
    # Obter resumo
    resumo = obter_resumo_geral(conn)
    
    # Métricas principais
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Beneficiários Ativos", f"{resumo['beneficiarios_ativos']:,}")
        st.caption("Cadastrados no sistema")
    
    with col2:
        st.metric("Valor Total Pago", f"R$ {resumo['valor_total_pago']:,.2f}")
        st.caption("Histórico completo")
    
    with col3:
        st.metric("Último Mês", resumo['ultimo_mes_processado'])
        st.caption("Processamento")
    
    with col4:
        st.metric("Inconsistências", f"{resumo['inconsistencias_pendentes']:,}")
        st.caption("Pendentes de correção")
    
    st.markdown("---")
    
    # Abas de análise
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Resumo Mensal", "⚠️ Inconsistências", "📋 Projetos", "👤 Problemas"])
    
    with tab1:
        st.subheader("Resumo Mensal de Pagamentos")
        
        df_resumo = obter_resumo_mensal(conn)
        if not df_resumo.empty:
            # Gráfico de evolução
            fig = px.line(
                df_resumo,
                x='periodo',
                y='valor_total',
                title='Evolução do Valor Total Pago',
                markers=True
            )
            fig.update_layout(xaxis_title='Período', yaxis_title='Valor (R$)')
            st.plotly_chart(fig, use_container_width=True)
            
            # Tabela detalhada
            st.dataframe(
                df_resumo[['periodo', 'beneficiarios', 'pagamentos', 'valor_total', 'valor_medio', 'dias']],
                use_container_width=True,
                column_config={
                    'valor_total': st.column_config.NumberColumn('Valor Total (R$)', format="R$ %.2f"),
                    'valor_medio': st.column_config.NumberColumn('Valor Médio (R$)', format="R$ %.2f")
                }
            )
        else:
            st.info("📭 Nenhum dado de pagamento disponível. Importe arquivos de pagamentos.")
    
    with tab2:
        st.subheader("Inconsistências Detectadas")
        
        df_inconsistencias = obter_inconsistencias(conn)
        if not df_inconsistencias.empty:
            # Gráfico
            fig = px.bar(
                df_inconsistencias,
                x='tipo',
                y='quantidade',
                color='severidade',
                title='Inconsistências por Tipo e Severidade'
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Tabela
            st.dataframe(df_inconsistencias, use_container_width=True)
            
            # Botão para correção
            if st.button("🗑️ Marcar Todas como Resolvidas", key="resolver_inc"):
                cursor = conn.cursor()
                cursor.execute("UPDATE inconsistências SET status = 'RESOLVIDO' WHERE status = 'PENDENTE'")
                conn.commit()
                st.success("✅ Inconsistências marcadas como resolvidas!")
                st.rerun()
        else:
            st.success("✅ Nenhuma inconsistência pendente!")
    
    with tab3:
        st.subheader("Pagamentos por Projeto")
        
        df_projetos = obter_pagamentos_por_projeto(conn)
        if not df_projetos.empty:
            # Gráfico
            fig = px.pie(
                df_projetos.head(10),
                values='valor_total',
                names='projeto',
                title='Top 10 Projetos por Valor'
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Tabela
            st.dataframe(
                df_projetos,
                use_container_width=True,
                column_config={
                    'valor_total': st.column_config.NumberColumn('Valor Total (R$)', format="R$ %.2f"),
                    'valor_medio': st.column_config.NumberColumn('Valor Médio (R$)', format="R$ %.2f")
                }
            )
        else:
            st.info("📭 Nenhum projeto registrado.")
    
    with tab4:
        st.subheader("Beneficiários com Problemas")
        
        df_problemas = obter_beneficiarios_problema(conn)
        if not df_problemas.empty:
            st.dataframe(
                df_problemas,
                use_container_width=True,
                column_config={
                    'cpf': 'CPF',
                    'nome': 'Nome',
                    'pagamentos': 'Pagamentos',
                    'total': st.column_config.NumberColumn('Total Recebido (R$)', format="R$ %.2f"),
                    'inconsistencias': 'Inconsistências'
                }
            )
        else:
            st.success("✅ Nenhum beneficiário com problemas identificados!")

def mostrar_importacao(conn):
    """Interface de importação de arquivos"""
    st.header("📤 Importar Arquivos")
    
    # Instruções
    with st.expander("ℹ️ Instruções de Importação", expanded=False):
        st.markdown("""
        ### Tipos de Arquivos Suportados:
        
        **1. PAGAMENTOS** (Principal)
        - Arquivos de pagamento realizados
        - Colunas necessárias: `numero_conta`, `nome`, `valor`
        - Colunas opcionais: `cpf`, `projeto`, `dias_trabalhados`
        
        **2. CADASTRO** (Complementar)
        - Dados cadastrais dos beneficiários
        - Colunas necessárias: `cpf`, `nome`
        - Colunas opcionais: `rg`, `telefone`, `email`, `endereco`, `bairro`
        
        ### Formatos:
        - **CSV** (separador ponto-e-vírgula ou vírgula)
        - **Excel** (.xls, .xlsx)
        - Mês/ano detectado automaticamente do nome do arquivo
        """)
    
    # Upload
    st.subheader("Selecionar Arquivo para Importação")
    
    col_tipo, col_mes, col_ano = st.columns(3)
    
    with col_tipo:
        tipo_arquivo = st.selectbox(
            "Tipo de Arquivo",
            ["PAGAMENTOS", "CADASTRO"],
            index=0
        )
    
    with col_mes:
        meses = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
        mes_selecionado = st.selectbox("Mês de Referência (pagamentos)", meses)
        mes_num = meses.index(mes_selecionado) if mes_selecionado else None
    
    with col_ano:
        ano_atual = datetime.now().year
        anos = [""] + list(range(ano_atual, ano_atual - 5, -1))
        ano_selecionado = st.selectbox("Ano de Referência (pagamentos)", anos)
        ano_num = int(ano_selecionado) if ano_selecionado else None
    
    # Upload do arquivo
    uploaded_file = st.file_uploader(
        "Selecione o arquivo",
        type=['csv', 'xls', 'xlsx'],
        key="upload_file"
    )
    
    if uploaded_file is not None:
        st.success(f"📄 **Arquivo selecionado:** {uploaded_file.name}")
        st.info(f"📋 **Tipo:** {tipo_arquivo}")
        
        # Prévia dos dados
        if st.button("👁️ Ver Prévia dos Dados", key="previa"):
            df_previa, mensagem = ler_arquivo(uploaded_file)
            if df_previa is not None:
                df_previa.columns = [normalizar_nome_coluna(col) for col in df_previa.columns]
                st.dataframe(df_previa.head(10), use_container_width=True)
                st.info(f"📊 **Total de registros:** {len(df_previa)}")
                st.info(f"📋 **Colunas detectadas:** {', '.join(df_previa.columns)}")
            else:
                st.error(f"❌ {mensagem}")
        
        # Processar arquivo
        if st.button("🔄 Processar Arquivo", type="primary", key="processar"):
            with st.spinner("Processando arquivo..."):
                sucesso, mensagem, inconsistencias = processar_arquivo(
                    uploaded_file, tipo_arquivo, conn, mes_num, ano_num
                )
            
            if sucesso:
                st.success(f"✅ {mensagem}")
                
                if inconsistencias:
                    st.warning(f"⚠️ Foram detectadas {len(inconsistencias)} inconsistências:")
                    for inc in inconsistencias:
                        emoji = "🔴" if inc['severidade'] == 'CRITICA' else "🟡" if inc['severidade'] == 'ALTA' else "🔵"
                        st.markdown(f"{emoji} **{inc['tipo']}**: {inc['descricao']}")
                
                st.balloons()
                st.rerun()
            else:
                st.error(f"❌ {mensagem}")

def mostrar_consulta(conn):
    """Interface de consulta de beneficiários"""
    st.header("🔍 Consulta de Beneficiários")
    
    col1, col2 = st.columns(2)
    
    with col1:
        cpf_consulta = st.text_input("CPF (somente números)", placeholder="00000000000", key="cpf_consulta")
    
    with col2:
        nome_consulta = st.text_input("Nome (parcial)", placeholder="Digite parte do nome", key="nome_consulta")
    
    if st.button("🔍 Buscar Beneficiários", key="buscar_benef"):
        try:
            cursor = conn.cursor()
            
            query = '''
                SELECT 
                    b.cpf,
                    b.nome,
                    b.rg,
                    b.status,
                    b.data_cadastro,
                    COUNT(p.id) as pagamentos,
                    SUM(p.valor_liquido) as total_recebido
                FROM beneficiarios b
                LEFT JOIN pagamentos p ON b.cpf = p.cpf_beneficiario
                WHERE 1=1
            '''
            
            params = []
            
            if cpf_consulta:
                cpf_limpo = re.sub(r'\D', '', cpf_consulta)
                if cpf_limpo:
                    query += ' AND b.cpf LIKE ?'
                    params.append(f'%{cpf_limpo}%')
            
            if nome_consulta:
                nome_normalizado = normalizar_nome(nome_consulta)
                query += ' AND b.nome_normalizado LIKE ?'
                params.append(f'%{nome_normalizado}%')
            
            query += '''
                GROUP BY b.cpf, b.nome, b.rg, b.status, b.data_cadastro
                ORDER BY b.nome
                LIMIT 100
            '''
            
            cursor.execute(query, params)
            resultados = cursor.fetchall()
            
            if resultados:
                df_resultados = pd.DataFrame(resultados, 
                    columns=['CPF', 'Nome', 'RG', 'Status', 'Data Cadastro', 'Pagamentos', 'Total Recebido'])
                
                st.subheader(f"📋 Resultados: {len(df_resultados)} beneficiários encontrados")
                
                # Métricas
                col_res1, col_res2 = st.columns(2)
                with col_res1:
                    st.metric("Total Recebido", f"R$ {df_resultados['Total Recebido'].sum():,.2f}")
                with col_res2:
                    st.metric("Média por Beneficiário", f"R$ {df_resultados['Total Recebido'].mean():,.2f}")
                
                # Tabela de resultados
                st.dataframe(
                    df_resultados,
                    use_container_width=True,
                    column_config={
                        'Total Recebido': st.column_config.NumberColumn('Total Recebido (R$)', format="R$ %.2f"),
                        'Data Cadastro': st.column_config.DateColumn('Data Cadastro')
                    }
                )
                
                # Detalhes se apenas um resultado
                if len(df_resultados) == 1:
                    cpf_detalhe = df_resultados.iloc[0]['CPF']
                    st.subheader(f"📅 Histórico de Pagamentos")
                    
                    cursor.execute('''
                        SELECT 
                            mes_referencia || '/' || ano_referencia as periodo,
                            valor_liquido,
                            projeto,
                            dias_trabalhados,
                            arquivo_origem
                        FROM pagamentos
                        WHERE cpf_beneficiario = ?
                        ORDER BY ano_referencia DESC, mes_referencia DESC
                    ''', (cpf_detalhe,))
                    
                    historico = cursor.fetchall()
                    if historico:
                        df_historico = pd.DataFrame(historico, 
                            columns=['Período', 'Valor', 'Projeto', 'Dias', 'Origem'])
                        
                        st.dataframe(
                            df_historico,
                            use_container_width=True,
                            column_config={
                                'Valor': st.column_config.NumberColumn('Valor (R$)', format="R$ %.2f")
                            }
                        )
            else:
                st.info("📭 Nenhum beneficiário encontrado com os critérios informados.")
                
        except Exception as e:
            st.error(f"❌ Erro na consulta: {str(e)}")

def mostrar_relatorios(conn):
    """Interface de relatórios"""
    st.header("📊 Relatórios e Análises")
    
    col1, col2 = st.columns(2)
    
    with col1:
        meses = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
        mes_rel = st.selectbox("Mês", meses, key="mes_rel")
        mes_num = meses.index(mes_rel) if mes_rel else None
    
    with col2:
        ano_atual = datetime.now().year
        anos = [""] + list(range(ano_atual, ano_atual - 5, -1))
        ano_rel = st.selectbox("Ano", anos, key="ano_rel")
        ano_num = int(ano_rel) if ano_rel else None
    
    if st.button("📈 Gerar Relatório do Período", key="gerar_rel"):
        if mes_num and ano_num:
            df_resumo = obter_resumo_mensal(conn, mes_num, ano_num)
            
            if not df_resumo.empty:
                resumo = df_resumo.iloc[0]
                
                st.success(f"📊 Relatório de {mes_rel}/{ano_num}")
                
                # Métricas
                col_met1, col_met2, col_met3 = st.columns(3)
                with col_met1:
                    st.metric("Beneficiários Pagos", f"{resumo['beneficiarios']:,}")
                with col_met2:
                    st.metric("Valor Total", f"R$ {resumo['valor_total']:,.2f}")
                with col_met3:
                    st.metric("Valor Médio", f"R$ {resumo['valor_medio']:,.2f}")
                
                # Projetos
                df_projetos = obter_pagamentos_por_projeto(conn, mes_num, ano_num)
                if not df_projetos.empty:
                    st.subheader("📋 Distribuição por Projeto")
                    
                    # Gráfico
                    fig = px.bar(
                        df_projetos.head(10),
                        x='projeto',
                        y='valor_total',
                        title=f'Top 10 Projetos - {mes_rel}/{ano_num}'
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # Tabela
                    st.dataframe(
                        df_projetos,
                        use_container_width=True,
                        column_config={
                            'valor_total': st.column_config.NumberColumn('Valor Total (R$)', format="R$ %.2f"),
                            'valor_medio': st.column_config.NumberColumn('Valor Médio (R$)', format="R$ %.2f")
                        }
                    )
            else:
                st.warning(f"⚠️ Nenhum dado encontrado para {mes_rel}/{ano_num}")
        else:
            st.warning("⚠️ Selecione mês e ano para gerar o relatório")

def mostrar_configuracoes(conn):
    """Interface de configurações"""
    st.header("⚙️ Configurações do Sistema")
    
    tab1, tab2 = st.tabs(["📊 Banco de Dados", "🔧 Manutenção"])
    
    with tab1:
        st.subheader("Status do Banco de Dados")
        
        cursor = conn.cursor()
        
        # Tamanho do banco
        if os.path.exists('pot_smdet.db'):
            tamanho_mb = os.path.getsize('pot_smdet.db') / 1024 / 1024
            st.info(f"📊 **Tamanho do banco:** {tamanho_mb:.2f} MB")
        
        # Contagem de registros
        st.write("### 📈 Estatísticas")
        
        col_db1, col_db2, col_db3 = st.columns(3)
        
        with col_db1:
            cursor.execute("SELECT COUNT(*) FROM beneficiarios")
            count = cursor.fetchone()[0]
            st.metric("Beneficiários", f"{count:,}")
        
        with col_db2:
            cursor.execute("SELECT COUNT(*) FROM pagamentos")
            count = cursor.fetchone()[0]
            st.metric("Pagamentos", f"{count:,}")
        
        with col_db3:
            cursor.execute("SELECT COUNT(*) FROM arquivos_processados")
            count = cursor.fetchone()[0]
            st.metric("Arquivos", f"{count:,}")
    
    with tab2:
        st.subheader("Manutenção do Sistema")
        
        st.warning("⚠️ **Ações Irreversíveis**")
        
        # Limpeza de dados antigos
        if st.button("🗑️ Limpar Dados Antigos (últimos 6 meses)", key="limpar_dados"):
            confirmacao = st.checkbox("Confirmar limpeza de dados antigos")
            if confirmacao:
                try:
                    cursor = conn.cursor()
                    
                    # Calcular data limite (6 meses atrás)
                    data_limite = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
                    
                    # Contar antes
                    cursor.execute("SELECT COUNT(*) FROM pagamentos WHERE data_processamento < ?", (data_limite,))
                    count_antes = cursor.fetchone()[0]
                    
                    # Executar limpeza
                    cursor.execute("DELETE FROM pagamentos WHERE data_processamento < ?", (data_limite,))
                    cursor.execute("DELETE FROM arquivos_processados WHERE data_processamento < ?", (data_limite,))
                    
                    conn.commit()
                    
                    st.success(f"✅ Limpeza concluída! {count_antes} registros antigos removidos.")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ Erro na limpeza: {str(e)}")
        
        # Otimização do banco
        if st.button("⚡ Otimizar Banco de Dados", key="otimizar"):
            try:
                cursor = conn.cursor()
                cursor.execute("VACUUM")
                conn.commit()
                st.success("✅ Banco de dados otimizado com sucesso!")
            except Exception as e:
                st.error(f"❌ Erro na otimização: {str(e)}")
        
        # Exportar dados
        if st.button("📤 Exportar Dados", key="exportar"):
            try:
                cursor = conn.cursor()
                
                # Exportar beneficiários
                cursor.execute("SELECT * FROM beneficiarios")
                beneficiarios = cursor.fetchall()
                colunas = [desc[0] for desc in cursor.description]
                
                df_benef = pd.DataFrame(beneficiarios, columns=colunas)
                csv_benef = df_benef.to_csv(index=False, sep=';', encoding='latin-1')
                
                st.download_button(
                    label="📥 Download Beneficiários (CSV)",
                    data=csv_benef,
                    file_name=f"beneficiarios_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )
                
            except Exception as e:
                st.error(f"❌ Erro na exportação: {str(e)}")

# ========== FUNÇÃO PRINCIPAL ==========
def main():
    # Inicializar banco de dados
    conn = init_database()
    
    if not conn:
        st.error("❌ Não foi possível inicializar o banco de dados.")
        return
    
    # Menu lateral
    st.sidebar.title("💰 POT - SMDET")
    st.sidebar.markdown("**Sistema de Gestão de Benefícios**")
    st.sidebar.markdown("---")
    
    # Opções do menu
    menu_opcoes = [
        "📊 Dashboard",
        "📤 Importar Arquivos",
        "🔍 Consulta Beneficiários",
        "📊 Relatórios",
        "⚙️ Configurações"
    ]
    
    menu_selecionado = st.sidebar.radio("Navegação", menu_opcoes, key="menu")
    
    # Exibir página selecionada
    if menu_selecionado == "📊 Dashboard":
        mostrar_dashboard(conn)
    
    elif menu_selecionado == "📤 Importar Arquivos":
        mostrar_importacao(conn)
    
    elif menu_selecionado == "🔍 Consulta Beneficiários":
        mostrar_consulta(conn)
    
    elif menu_selecionado == "📊 Relatórios":
        mostrar_relatorios(conn)
    
    elif menu_selecionado == "⚙️ Configurações":
        mostrar_configuracoes(conn)
    
    # Rodapé
    st.sidebar.markdown("---")
    st.sidebar.caption(f"© {datetime.now().year} Prefeitura de São Paulo - SMDET")
    st.sidebar.caption("Versão 3.0 - Sistema POT")
    
    # Fechar conexão
    conn.close()

if __name__ == "__main__":
    main()
