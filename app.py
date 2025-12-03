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

# ========== BANCO DE DADOS SIMPLIFICADO ==========
def init_database():
    """Inicializa o banco de dados SQLite apenas com tabelas necessárias"""
    try:
        conn = sqlite3.connect('pot_beneficios_simplificado.db', check_same_thread=False)
        
        # 1. Tabela de beneficiários (dados mestres)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS beneficiarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cpf TEXT UNIQUE NOT NULL,
                nome TEXT NOT NULL,
                nome_normalizado TEXT,
                rg TEXT,
                data_nascimento DATE,
                telefone TEXT,
                email TEXT,
                endereco TEXT,
                bairro TEXT,
                cidade TEXT,
                cep TEXT,
                data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                fonte_cadastro TEXT,
                status TEXT DEFAULT 'ATIVO',
                observacoes TEXT
            )
        ''')
        
        # 2. Tabela de projetos/programas
        conn.execute('''
            CREATE TABLE IF NOT EXISTS projetos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT UNIQUE NOT NULL,
                nome TEXT NOT NULL,
                descricao TEXT,
                data_inicio DATE,
                data_fim DATE,
                valor_diario DECIMAL(10,2),
                valor_mensal DECIMAL(10,2),
                status TEXT DEFAULT 'ATIVO',
                orgao_responsavel TEXT,
                data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 3. Tabela de contas bancárias
        conn.execute('''
            CREATE TABLE IF NOT EXISTS contas_bancarias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                numero_conta TEXT NOT NULL,
                cpf_titular TEXT NOT NULL,
                banco TEXT NOT NULL,
                agencia TEXT NOT NULL,
                tipo_conta TEXT DEFAULT 'CORRENTE',
                data_abertura DATE,
                status TEXT DEFAULT 'ATIVA',
                fonte_dados TEXT,
                data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(numero_conta, cpf_titular)
            )
        ''')
        
        # 4. Tabela de pagamentos (principal)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS pagamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                numero_conta TEXT NOT NULL,
                cpf_beneficiario TEXT NOT NULL,
                nome_beneficiario TEXT NOT NULL,
                codigo_projeto TEXT,
                mes_referencia INTEGER NOT NULL,
                ano_referencia INTEGER NOT NULL,
                valor_bruto DECIMAL(10,2) NOT NULL,
                valor_desconto DECIMAL(10,2) DEFAULT 0,
                valor_liquido DECIMAL(10,2) NOT NULL,
                dias_trabalhados INTEGER DEFAULT 20,
                data_pagamento DATE,
                status_pagamento TEXT DEFAULT 'PAGO',
                arquivo_origem TEXT,
                lote_pagamento TEXT,
                observacoes TEXT,
                data_processamento TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(numero_conta, mes_referencia, ano_referencia)
            )
        ''')
        
        # 5. Tabela de arquivos processados
        conn.execute('''
            CREATE TABLE IF NOT EXISTS arquivos_processados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome_arquivo TEXT NOT NULL,
                tipo_arquivo TEXT NOT NULL,
                mes_referencia INTEGER,
                ano_referencia INTEGER,
                total_registros INTEGER,
                registros_processados INTEGER,
                valor_total DECIMAL(15,2),
                hash_arquivo TEXT UNIQUE NOT NULL,
                data_processamento TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                usuario_processamento TEXT,
                status_processamento TEXT DEFAULT 'SUCESSO',
                erros_processamento TEXT
            )
        ''')
        
        # 6. Tabela de inconsistências
        conn.execute('''
            CREATE TABLE IF NOT EXISTS inconsistencias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo_inconsistencia TEXT NOT NULL,
                severidade TEXT NOT NULL,
                descricao TEXT NOT NULL,
                cpf_envolvido TEXT,
                numero_conta_envolvido TEXT,
                projeto_envolvido TEXT,
                valor_envolvido DECIMAL(10,2),
                data_deteccao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'PENDENTE',
                acao_corretiva TEXT,
                usuario_responsavel TEXT,
                data_correcao TIMESTAMP,
                observacoes TEXT,
                fonte_dados TEXT
            )
        ''')
        
        conn.commit()
        
        # Criar índices
        criar_indices(conn)
        
        # Criar views para relatórios
        criar_views_relatorios(conn)
        
        return conn
        
    except Exception as e:
        st.error(f"❌ Erro ao inicializar banco de dados: {str(e)}")
        return None

def criar_indices(conn):
    """Cria índices para melhorar performance"""
    indices = [
        "CREATE INDEX IF NOT EXISTS idx_beneficiarios_cpf ON beneficiarios(cpf)",
        "CREATE INDEX IF NOT EXISTS idx_beneficiarios_nome ON beneficiarios(nome_normalizado)",
        "CREATE INDEX IF NOT EXISTS idx_contas_numero ON contas_bancarias(numero_conta)",
        "CREATE INDEX IF NOT EXISTS idx_contas_cpf ON contas_bancarias(cpf_titular)",
        "CREATE INDEX IF NOT EXISTS idx_pagamentos_periodo ON pagamentos(ano_referencia, mes_referencia)",
        "CREATE INDEX IF NOT EXISTS idx_pagamentos_conta ON pagamentos(numero_conta)",
        "CREATE INDEX IF NOT EXISTS idx_pagamentos_cpf ON pagamentos(cpf_beneficiario)",
        "CREATE INDEX IF NOT EXISTS idx_arquivos_hash ON arquivos_processados(hash_arquivo)",
        "CREATE INDEX IF NOT EXISTS idx_inconsistencias_status ON inconsistencias(status)"
    ]
    
    for idx_sql in indices:
        try:
            conn.execute(idx_sql)
        except:
            pass
    
    conn.commit()

def criar_views_relatorios(conn):
    """Cria views para facilitar consultas"""
    try:
        # View de resumo mensal
        conn.execute('''
            CREATE VIEW IF NOT EXISTS view_resumo_mensal AS
            SELECT 
                ano_referencia,
                mes_referencia,
                COUNT(DISTINCT cpf_beneficiario) as beneficiarios_pagos,
                COUNT(DISTINCT numero_conta) as contas_pagas,
                COUNT(DISTINCT codigo_projeto) as projetos_ativos,
                SUM(valor_liquido) as valor_total_pago,
                SUM(valor_desconto) as total_descontos,
                AVG(valor_liquido) as valor_medio_pagamento,
                SUM(dias_trabalhados) as total_dias_trabalhados
            FROM pagamentos
            WHERE status_pagamento = 'PAGO'
            GROUP BY ano_referencia, mes_referencia
        ''')
        
        # View de inconsistências pendentes
        conn.execute('''
            CREATE VIEW IF NOT EXISTS view_inconsistencias_pendentes AS
            SELECT 
                tipo_inconsistencia,
                severidade,
                COUNT(*) as quantidade,
                GROUP_CONCAT(DISTINCT cpf_envolvido) as cpfs_envolvidos
            FROM inconsistencias
            WHERE status = 'PENDENTE'
            GROUP BY tipo_inconsistencia, severidade
        ''')
        
        conn.commit()
    except:
        pass

# ========== NORMALIZAÇÃO DE DADOS ==========
class NormalizadorDados:
    """Classe para normalização de dados"""
    
    @staticmethod
    def normalizar_nome(nome: str) -> str:
        """Normaliza nome removendo acentos, maiúsculas e espaços extras"""
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
    
    @staticmethod
    def normalizar_cpf(cpf: Any) -> str:
        """Normaliza CPF removendo caracteres não numéricos"""
        if pd.isna(cpf):
            return ""
        
        cpf_str = str(cpf).strip()
        cpf_limpo = re.sub(r'\D', '', cpf_str)
        
        if len(cpf_limpo) == 11:
            return cpf_limpo
        elif len(cpf_limpo) > 11:
            return cpf_limpo[:11]
        else:
            # Preencher com zeros à esquerda
            return cpf_limpo.zfill(11)
    
    @staticmethod
    def normalizar_valor(valor: Any) -> float:
        """Converte valor para numérico"""
        if pd.isna(valor):
            return 0.0
        
        valor_str = str(valor).strip()
        valor_str = re.sub(r'[R\$\s]', '', valor_str)
        
        # Tratar diferentes formatos de decimal
        if ',' in valor_str and '.' in valor_str:
            valor_str = valor_str.replace('.', '').replace(',', '.')
        elif ',' in valor_str:
            if valor_str.count(',') == 1 and len(valor_str.split(',')[1]) == 2:
                valor_str = valor_str.replace(',', '.')
            else:
                valor_str = valor_str.replace(',', '')
        
        try:
            return float(valor_str)
        except:
            return 0.0
    
    @staticmethod
    def normalizar_nome_coluna(nome_coluna: str) -> str:
        """Normaliza nomes de colunas"""
        if not isinstance(nome_coluna, str):
            nome_coluna = str(nome_coluna)
        
        mapeamento = {
            'num_cartao': 'numero_conta',
            'numcartao': 'numero_conta',
            'n_cartao': 'numero_conta',
            'cartao': 'numero_conta',
            'num_conta': 'numero_conta',
            'conta': 'numero_conta',
            'n_conta': 'numero_conta',
            'codigo': 'numero_conta',
            'cod': 'numero_conta',
            
            'nome': 'nome',
            'nome_beneficiario': 'nome',
            'beneficiario': 'nome',
            'beneficiário': 'nome',
            'nome_completo': 'nome',
            'nom': 'nome',
            
            'cpf': 'cpf',
            'cpf_beneficiario': 'cpf',
            'cpf_do_beneficiario': 'cpf',
            
            'projeto': 'projeto',
            'programa': 'projeto',
            'cod_projeto': 'projeto',
            'codigo_projeto': 'projeto',
            
            'valor': 'valor',
            'valor_total': 'valor',
            'valor_pagto': 'valor',
            'valor_pagamento': 'valor',
            'valor_pago': 'valor',
            'valorpagto': 'valor',
            'vlr': 'valor',
            'valor_bruto': 'valor_bruto',
            'valor_liquido': 'valor_liquido',
            
            'data_pagto': 'data_pagamento',
            'data_pagamento': 'data_pagamento',
            'data_pgto': 'data_pagamento',
            'datapagto': 'data_pagamento',
            'data': 'data_pagamento',
            
            'dias': 'dias_trabalhados',
            'dias_trabalhados': 'dias_trabalhados',
            'dias_uteis': 'dias_trabalhados',
            
            'valor_dia': 'valor_diario',
            'valor_diario': 'valor_diario',
            'valordia': 'valor_diario',
            
            'agencia': 'agencia',
            'ag': 'agencia',
            'agência': 'agencia',
            'banco': 'banco'
        }
        
        nome_limpo = nome_coluna.strip().lower()
        nome_limpo = re.sub(r'[\s\-\.]+', '_', nome_limpo)
        nome_limpo = re.sub(r'[^\w_]', '', nome_limpo)
        
        return mapeamento.get(nome_limpo, nome_limpo)

# ========== PROCESSAMENTO DE ARQUIVOS ==========
class ProcessadorArquivos:
    """Classe para processamento de arquivos"""
    
    def __init__(self, conn):
        self.conn = conn
        self.normalizador = NormalizadorDados()
    
    def processar_arquivo(self, uploaded_file, tipo_arquivo: str, mes: int = None, ano: int = None, usuario: str = "SISTEMA"):
        """Processa arquivo de acordo com seu tipo"""
        
        # Calcular hash do arquivo
        conteudo = uploaded_file.getvalue()
        hash_arquivo = hashlib.md5(conteudo).hexdigest()
        
        # Verificar se arquivo já foi processado
        if self._arquivo_ja_processado(hash_arquivo):
            return False, "Este arquivo já foi processado anteriormente", []
        
        # Detectar mês/ano se não informados
        if not mes or not ano:
            mes, ano = self._detectar_mes_ano(uploaded_file.name)
        
        # Ler arquivo
        df, mensagem = self._ler_arquivo(uploaded_file)
        if df is None:
            return False, mensagem, []
        
        # Normalizar cabeçalhos
        df.columns = [self.normalizador.normalizar_nome_coluna(col) for col in df.columns]
        
        # Detectar inconsistências
        inconsistencias = self._detectar_inconsistencias(df, tipo_arquivo)
        
        # Processar de acordo com o tipo
        if tipo_arquivo == 'PAGAMENTOS':
            sucesso, mensagem = self._processar_pagamentos(df, mes, ano, uploaded_file.name, hash_arquivo, usuario)
        elif tipo_arquivo == 'CADASTRO_BENEFICIARIOS':
            sucesso, mensagem = self._processar_cadastro_beneficiarios(df, uploaded_file.name, hash_arquivo, usuario)
        elif tipo_arquivo == 'CONTAS_BANCARIAS':
            sucesso, mensagem = self._processar_contas_bancarias(df, uploaded_file.name, hash_arquivo, usuario)
        else:
            return False, f"Tipo de arquivo não suportado: {tipo_arquivo}", inconsistencias
        
        # Registrar processamento
        self._registrar_processamento(uploaded_file.name, tipo_arquivo, mes, ano, len(df), 
                                     hash_arquivo, usuario, sucesso, mensagem)
        
        # Registrar inconsistências
        if inconsistencias:
            self._registrar_inconsistencias(inconsistencias, tipo_arquivo, uploaded_file.name)
        
        return sucesso, mensagem, inconsistencias
    
    def _ler_arquivo(self, uploaded_file):
        """Lê arquivo de forma robusta"""
        try:
            # Salvar em arquivo temporário
            with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                tmp_path = tmp_file.name
            
            try:
                df = None
                # Verificar extensão
                if uploaded_file.name.lower().endswith('.csv'):
                    # Tentar diferentes encodings
                    for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
                        try:
                            df = pd.read_csv(tmp_path, sep=';', encoding=encoding, dtype=str, on_bad_lines='skip')
                            if df is not None and not df.empty:
                                break
                        except:
                            continue
                    
                    # Se ainda vazio, tentar com separador automático
                    if df is None or df.empty or len(df.columns) == 1:
                        try:
                            df = pd.read_csv(tmp_path, sep=None, engine='python', dtype=str, on_bad_lines='skip')
                        except:
                            df = pd.read_csv(tmp_path, sep=',', dtype=str, on_bad_lines='skip')
                
                elif uploaded_file.name.lower().endswith(('.xls', '.xlsx')):
                    try:
                        df = pd.read_excel(tmp_path, dtype=str, engine='openpyxl')
                    except:
                        try:
                            df = pd.read_excel(tmp_path, dtype=str, engine='xlrd')
                        except:
                            df = pd.read_excel(tmp_path, dtype=str)
                
                # Limpar arquivo temporário
                os.unlink(tmp_path)
                
                if df is None or df.empty:
                    return None, "Arquivo vazio ou sem dados"
                
                # Remover colunas vazias
                df = df.dropna(axis=1, how='all')
                
                return df, "Arquivo lido com sucesso"
                
            except Exception as e:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                return None, f"Erro ao ler arquivo: {str(e)}"
                
        except Exception as e:
            return None, f"Erro ao processar arquivo: {str(e)}"
    
    def _detectar_mes_ano(self, nome_arquivo: str) -> Tuple[int, int]:
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
    
    def _arquivo_ja_processado(self, hash_arquivo: str) -> bool:
        """Verifica se arquivo já foi processado"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM arquivos_processados WHERE hash_arquivo = ?", (hash_arquivo,))
        return cursor.fetchone() is not None
    
    def _detectar_inconsistencias(self, df: pd.DataFrame, tipo_arquivo: str) -> List[Dict]:
        """Detecta inconsistências nos dados"""
        inconsistencias = []
        
        # Verificar colunas obrigatórias
        if tipo_arquivo == 'PAGAMENTOS':
            obrigatorias = ['numero_conta', 'nome', 'valor']
        elif tipo_arquivo == 'CADASTRO_BENEFICIARIOS':
            obrigatorias = ['cpf', 'nome']
        elif tipo_arquivo == 'CONTAS_BANCARIAS':
            obrigatorias = ['numero_conta', 'cpf', 'agencia', 'banco']
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
            zerados = (df['valor'].apply(self.normalizador.normalizar_valor) <= 0).sum()
            if zerados > 0:
                inconsistencias.append({
                    'tipo': 'VALORES_ZERADOS',
                    'severidade': 'ALTA',
                    'descricao': f'{zerados} registros com valor zerado ou negativo'
                })
        
        return inconsistencias
    
    def _registrar_processamento(self, nome_arquivo: str, tipo_arquivo: str, mes: int, ano: int, 
                                total_registros: int, hash_arquivo: str, usuario: str, 
                                sucesso: bool, mensagem: str):
        """Registra processamento do arquivo"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO arquivos_processados 
                (nome_arquivo, tipo_arquivo, mes_referencia, ano_referencia, 
                 total_registros, hash_arquivo, usuario_processamento, 
                 status_processamento, erros_processamento)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                nome_arquivo,
                tipo_arquivo,
                mes,
                ano,
                total_registros,
                hash_arquivo,
                usuario,
                'SUCESSO' if sucesso else 'ERRO',
                None if sucesso else mensagem
            ))
            self.conn.commit()
        except Exception as e:
            st.error(f"Erro ao registrar processamento: {str(e)}")
    
    def _registrar_inconsistencias(self, inconsistencias: List[Dict], fonte_dados: str, arquivo_origem: str):
        """Registra inconsistências detectadas"""
        try:
            cursor = self.conn.cursor()
            for inc in inconsistencias:
                cursor.execute('''
                    INSERT INTO inconsistencias 
                    (tipo_inconsistencia, severidade, descricao, fonte_dados)
                    VALUES (?, ?, ?, ?)
                ''', (
                    inc['tipo'],
                    inc['severidade'],
                    inc['descricao'],
                    fonte_dados
                ))
            self.conn.commit()
        except Exception as e:
            st.error(f"Erro ao registrar inconsistências: {str(e)}")
    
    def _processar_pagamentos(self, df: pd.DataFrame, mes: int, ano: int, nome_arquivo: str, 
                             hash_arquivo: str, usuario: str) -> Tuple[bool, str]:
        """Processa arquivo de pagamentos"""
        try:
            cursor = self.conn.cursor()
            registros_processados = 0
            valor_total = 0
            
            for _, row in df.iterrows():
                try:
                    # Extrair e normalizar dados
                    numero_conta = str(row.get('numero_conta', '')).strip()
                    nome = self.normalizador.normalizar_nome(str(row.get('nome', '')))
                    cpf = self.normalizador.normalizar_cpf(row.get('cpf', ''))
                    valor_bruto = self.normalizador.normalizar_valor(row.get('valor'))
                    valor_liquido = self.normalizador.normalizar_valor(row.get('valor_liquido', valor_bruto))
                    projeto = str(row.get('projeto', '')).strip()
                    dias = int(row.get('dias_trabalhados', 20))
                    
                    # Calcular desconto se não informado
                    valor_desconto = valor_bruto - valor_liquido
                    
                    # Validar dados mínimos
                    if not numero_conta or not nome or valor_liquido <= 0:
                        continue
                    
                    # Se CPF não informado, tentar buscar do banco
                    if not cpf or len(cpf) != 11:
                        cursor.execute("SELECT cpf FROM beneficiarios WHERE nome_normalizado LIKE ? LIMIT 1", 
                                     (f"%{nome}%",))
                        resultado = cursor.fetchone()
                        if resultado:
                            cpf = resultado[0]
                    
                    # Se ainda não tem CPF, criar um placeholder
                    if not cpf or len(cpf) != 11:
                        cpf = f"SEM_CPF_{hash(nome) % 1000000:06d}"
                    
                    # Inserir/atualizar beneficiário
                    cursor.execute('''
                        INSERT OR REPLACE INTO beneficiarios 
                        (cpf, nome, nome_normalizado, fonte_cadastro, status)
                        VALUES (?, ?, ?, 'IMPORTACAO_PAGAMENTOS', 'ATIVO')
                    ''', (cpf, nome, nome))
                    
                    # Inserir pagamento
                    cursor.execute('''
                        INSERT OR REPLACE INTO pagamentos 
                        (numero_conta, cpf_beneficiario, nome_beneficiario, codigo_projeto,
                         mes_referencia, ano_referencia, valor_bruto, valor_desconto,
                         valor_liquido, dias_trabalhados, status_pagamento, arquivo_origem)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PAGO', ?)
                    ''', (
                        numero_conta, cpf, nome, projeto, mes, ano, 
                        valor_bruto, valor_desconto, valor_liquido, dias, nome_arquivo
                    ))
                    
                    registros_processados += 1
                    valor_total += valor_liquido
                    
                except Exception as e:
                    st.warning(f"Erro no registro {registros_processados}: {str(e)}")
                    continue
            
            self.conn.commit()
            
            # Atualizar cálculos consolidados
            self._atualizar_calculos_consolidados(mes, ano)
            
            return True, f"✅ Processados {registros_processados} pagamentos | Valor total: R$ {valor_total:,.2f}"
            
        except Exception as e:
            self.conn.rollback()
            return False, f"❌ Erro ao processar pagamentos: {str(e)}"
    
    def _processar_cadastro_beneficiarios(self, df: pd.DataFrame, nome_arquivo: str, 
                                        hash_arquivo: str, usuario: str) -> Tuple[bool, str]:
        """Processa arquivo de cadastro de beneficiários"""
        try:
            cursor = self.conn.cursor()
            registros_processados = 0
            
            for _, row in df.iterrows():
                try:
                    cpf = self.normalizador.normalizar_cpf(row.get('cpf'))
                    nome = self.normalizador.normalizar_nome(str(row.get('nome', '')))
                    rg = str(row.get('rg', '')).strip()
                    telefone = str(row.get('telefone', '')).strip()
                    email = str(row.get('email', '')).strip()
                    endereco = str(row.get('endereco', '')).strip()
                    bairro = str(row.get('bairro', '')).strip()
                    
                    if not cpf or not nome:
                        continue
                    
                    # Inserir/atualizar beneficiário
                    cursor.execute('''
                        INSERT OR REPLACE INTO beneficiarios 
                        (cpf, nome, nome_normalizado, rg, telefone, email, 
                         endereco, bairro, fonte_cadastro, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'CADASTRO_ARQUIVO', 'ATIVO')
                    ''', (cpf, nome, nome, rg, telefone, email, endereco, bairro))
                    
                    registros_processados += 1
                    
                except Exception as e:
                    continue
            
            self.conn.commit()
            return True, f"✅ Processados {registros_processados} cadastros de beneficiários"
            
        except Exception as e:
            self.conn.rollback()
            return False, f"❌ Erro ao processar cadastro: {str(e)}"
    
    def _processar_contas_bancarias(self, df: pd.DataFrame, nome_arquivo: str, 
                                   hash_arquivo: str, usuario: str) -> Tuple[bool, str]:
        """Processa arquivo de contas bancárias"""
        try:
            cursor = self.conn.cursor()
            registros_processados = 0
            
            for _, row in df.iterrows():
                try:
                    numero_conta = str(row.get('numero_conta', '')).strip()
                    cpf = self.normalizador.normalizar_cpf(row.get('cpf'))
                    agencia = str(row.get('agencia', '')).strip()
                    banco = str(row.get('banco', 'BANCO DO BRASIL')).strip()
                    
                    if not numero_conta or not cpf:
                        continue
                    
                    # Buscar nome do beneficiário
                    cursor.execute("SELECT nome FROM beneficiarios WHERE cpf = ?", (cpf,))
                    resultado = cursor.fetchone()
                    nome = resultado[0] if resultado else ""
                    
                    # Inserir/atualizar conta
                    cursor.execute('''
                        INSERT OR REPLACE INTO contas_bancarias 
                        (numero_conta, cpf_titular, banco, agencia, fonte_dados, status)
                        VALUES (?, ?, ?, ?, 'IMPORTACAO_ARQUIVO', 'ATIVA')
                    ''', (numero_conta, cpf, banco, agencia))
                    
                    registros_processados += 1
                    
                except Exception as e:
                    continue
            
            self.conn.commit()
            return True, f"✅ Processadas {registros_processados} contas bancárias"
            
        except Exception as e:
            self.conn.rollback()
            return False, f"❌ Erro ao processar contas bancárias: {str(e)}"
    
    def _atualizar_calculos_consolidados(self, mes: int, ano: int):
        """Atualiza cálculos consolidados após processamento"""
        try:
            cursor = self.conn.cursor()
            
            # Calcular totais do mês
            cursor.execute('''
                SELECT 
                    COUNT(DISTINCT cpf_beneficiario) as beneficiarios,
                    COUNT(DISTINCT numero_conta) as contas,
                    COUNT(*) as pagamentos,
                    SUM(valor_liquido) as valor_total,
                    SUM(valor_desconto) as total_descontos,
                    SUM(dias_trabalhados) as total_dias
                FROM pagamentos 
                WHERE mes_referencia = ? AND ano_referencia = ?
            ''', (mes, ano))
            
            resultado = cursor.fetchone()
            if resultado:
                # Atualizar arquivo processado com os cálculos
                cursor.execute('''
                    UPDATE arquivos_processados 
                    SET registros_processados = ?,
                        valor_total = ?
                    WHERE mes_referencia = ? AND ano_referencia = ?
                    ORDER BY id DESC LIMIT 1
                ''', (resultado[2], resultado[3], mes, ano))
                
                self.conn.commit()
                
        except Exception as e:
            st.error(f"Erro ao atualizar cálculos: {str(e)}")

# ========== ANÁLISE E RELATÓRIOS ==========
class AnalisadorDados:
    """Classe para análise de dados"""
    
    def __init__(self, conn):
        self.conn = conn
    
    def obter_resumo_geral(self) -> Dict:
        """Obtém resumo geral do sistema"""
        cursor = self.conn.cursor()
        resumo = {}
        
        cursor.execute("SELECT COUNT(*) FROM beneficiarios WHERE status = 'ATIVO'")
        resumo['beneficiarios_ativos'] = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM contas_bancarias WHERE status = 'ATIVA'")
        resumo['contas_ativas'] = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(DISTINCT codigo_projeto) FROM pagamentos WHERE codigo_projeto IS NOT NULL")
        resumo['projetos_ativos'] = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT SUM(valor_liquido) FROM pagamentos WHERE status_pagamento = 'PAGO'")
        resumo['valor_total_pago'] = cursor.fetchone()[0] or 0
        
        cursor.execute('''
            SELECT MAX(ano_referencia), MAX(mes_referencia)
            FROM pagamentos WHERE status_pagamento = 'PAGO'
        ''')
        ultimo_mes = cursor.fetchone()
        resumo['ultimo_mes_processado'] = f"{ultimo_mes[1]:02d}/{ultimo_mes[0]}" if ultimo_mes[0] else "Nenhum"
        
        cursor.execute("SELECT COUNT(*) FROM inconsistencias WHERE status = 'PENDENTE'")
        resumo['inconsistencias_pendentes'] = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM arquivos_processados WHERE status_processamento = 'SUCESSO'")
        resumo['arquivos_processados'] = cursor.fetchone()[0] or 0
        
        return resumo
    
    def obter_resumo_mensal(self, mes: int = None, ano: int = None) -> pd.DataFrame:
        """Obtém resumo mensal"""
        try:
            if mes and ano:
                query = '''
                    SELECT * FROM view_resumo_mensal 
                    WHERE mes_referencia = ? AND ano_referencia = ?
                '''
                params = (mes, ano)
            else:
                query = "SELECT * FROM view_resumo_mensal ORDER BY ano_referencia DESC, mes_referencia DESC LIMIT 12"
                params = ()
            
            return pd.read_sql_query(query, self.conn, params=params)
        except:
            return pd.DataFrame()
    
    def obter_inconsistencias_pendentes(self) -> pd.DataFrame:
        """Obtém inconsistências pendentes"""
        try:
            return pd.read_sql_query("SELECT * FROM view_inconsistencias_pendentes", self.conn)
        except:
            return pd.DataFrame()
    
    def obter_pagamentos_por_projeto(self, mes: int = None, ano: int = None) -> pd.DataFrame:
        """Obtém pagamentos agrupados por projeto"""
        try:
            if mes and ano:
                query = '''
                    SELECT 
                        COALESCE(codigo_projeto, 'NÃO INFORMADO') as projeto,
                        COUNT(*) as quantidade_pagamentos,
                        SUM(valor_liquido) as valor_total,
                        AVG(valor_liquido) as valor_medio,
                        COUNT(DISTINCT cpf_beneficiario) as beneficiarios_unicos,
                        SUM(dias_trabalhados) as total_dias
                    FROM pagamentos
                    WHERE mes_referencia = ? AND ano_referencia = ?
                    AND status_pagamento = 'PAGO'
                    GROUP BY codigo_projeto
                    ORDER BY valor_total DESC
                '''
                params = (mes, ano)
            else:
                query = '''
                    SELECT 
                        COALESCE(codigo_projeto, 'NÃO INFORMADO') as projeto,
                        COUNT(*) as quantidade_pagamentos,
                        SUM(valor_liquido) as valor_total,
                        AVG(valor_liquido) as valor_medio,
                        COUNT(DISTINCT cpf_beneficiario) as beneficiarios_unicos,
                        SUM(dias_trabalhados) as total_dias
                    FROM pagamentos
                    WHERE status_pagamento = 'PAGO'
                    GROUP BY codigo_projeto
                    ORDER BY valor_total DESC
                '''
                params = ()
            
            return pd.read_sql_query(query, self.conn, params=params)
        except:
            return pd.DataFrame()
    
    def obter_beneficiarios_problema(self, limite: int = 20) -> pd.DataFrame:
        """Identifica beneficiários com problemas"""
        try:
            query = '''
                SELECT 
                    b.cpf,
                    b.nome,
                    COUNT(DISTINCT c.numero_conta) as num_contas,
                    COUNT(DISTINCT p.id) as num_pagamentos,
                    SUM(p.valor_liquido) as total_recebido,
                    MAX(p.data_pagamento) as ultimo_pagamento,
                    GROUP_CONCAT(DISTINCT i.tipo_inconsistencia) as inconsistencias
                FROM beneficiarios b
                LEFT JOIN contas_bancarias c ON b.cpf = c.cpf_titular
                LEFT JOIN pagamentos p ON b.cpf = p.cpf_beneficiario
                LEFT JOIN inconsistencias i ON b.cpf = i.cpf_envolvido AND i.status = 'PENDENTE'
                WHERE b.status = 'ATIVO'
                GROUP BY b.cpf, b.nome
                HAVING num_contas > 1 OR inconsistencias IS NOT NULL
                ORDER BY num_contas DESC, total_recebido DESC
                LIMIT ?
            '''
            return pd.read_sql_query(query, self.conn, params=(limite,))
        except:
            return pd.DataFrame()

# ========== INTERFACE STREAMLIT ==========
def mostrar_dashboard(conn):
    """Mostra dashboard principal"""
    st.title("💰 Sistema POT - Gestão de Benefícios")
    st.markdown("---")
    
    analisador = AnalisadorDados(conn)
    resumo = analisador.obter_resumo_geral()
    
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
    tab1, tab2, tab3 = st.tabs(["📊 Resumo Mensal", "⚠️ Inconsistências", "👤 Beneficiários"])
    
    with tab1:
        st.subheader("Resumo Mensal de Pagamentos")
        
        df_resumo = analisador.obter_resumo_mensal()
        if not df_resumo.empty:
            # Gráfico de evolução
            df_resumo['periodo'] = df_resumo['mes_referencia'].astype(str).str.zfill(2) + '/' + df_resumo['ano_referencia'].astype(str)
            df_resumo = df_resumo.sort_values(['ano_referencia', 'mes_referencia'])
            
            fig = px.line(
                df_resumo,
                x='periodo',
                y='valor_total_pago',
                title='Evolução do Valor Total Pago',
                markers=True
            )
            fig.update_layout(xaxis_title='Período', yaxis_title='Valor (R$)')
            st.plotly_chart(fig, use_container_width=True)
            
            # Tabela detalhada
            st.dataframe(
                df_resumo[['periodo', 'beneficiarios_pagos', 'contas_pagas', 
                          'valor_total_pago', 'valor_medio_pagamento', 'total_dias_trabalhados']],
                use_container_width=True,
                column_config={
                    'valor_total_pago': st.column_config.NumberColumn('Valor Total (R$)', format="R$ %.2f"),
                    'valor_medio_pagamento': st.column_config.NumberColumn('Média (R$)', format="R$ %.2f")
                }
            )
        else:
            st.info("📭 Nenhum dado de pagamento disponível. Importe arquivos de pagamentos.")
    
    with tab2:
        st.subheader("Inconsistências Detectadas")
        
        df_inconsistencias = analisador.obter_inconsistencias_pendentes()
        if not df_inconsistencias.empty:
            # Gráfico
            fig = px.bar(
                df_inconsistencias,
                x='tipo_inconsistencia',
                y='quantidade',
                color='severidade',
                title='Inconsistências por Tipo e Severidade'
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Tabela
            st.dataframe(df_inconsistencias, use_container_width=True)
            
            # Botão para correção
            if st.button("🗑️ Marcar Todas como Resolvidas"):
                cursor = conn.cursor()
                cursor.execute("UPDATE inconsistencias SET status = 'RESOLVIDO' WHERE status = 'PENDENTE'")
                conn.commit()
                st.success("✅ Inconsistências marcadas como resolvidas!")
                st.rerun()
        else:
            st.success("✅ Nenhuma inconsistência pendente!")
    
    with tab3:
        st.subheader("Beneficiários com Potenciais Problemas")
        
        df_problemas = analisador.obter_beneficiarios_problema()
        if not df_problemas.empty:
            st.dataframe(
                df_problemas,
                use_container_width=True,
                column_config={
                    'cpf': 'CPF',
                    'nome': 'Nome',
                    'num_contas': 'Contas',
                    'num_pagamentos': 'Pagamentos',
                    'total_recebido': st.column_config.NumberColumn('Total Recebido (R$)', format="R$ %.2f"),
                    'ultimo_pagamento': 'Último Pagamento',
                    'inconsistencias': 'Inconsistências'
                }
            )
            
            # Distribuição por projeto
            st.subheader("Pagamentos por Projeto")
            df_projetos = analisador.obter_pagamentos_por_projeto()
            if not df_projetos.empty:
                fig = px.pie(
                    df_projetos.head(10),
                    values='valor_total',
                    names='projeto',
                    title='Top 10 Projetos por Valor'
                )
                st.plotly_chart(fig, use_container_width=True)
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
        - Colunas mínimas: `numero_conta`, `nome`, `valor`
        - Colunas opcionais: `cpf`, `projeto`, `dias_trabalhados`, `valor_diario`
        
        **2. CADASTRO DE BENEFICIÁRIOS** (Complementar)
        - Dados cadastrais dos beneficiários
        - Colunas mínimas: `cpf`, `nome`
        - Colunas opcionais: `rg`, `telefone`, `email`, `endereco`, `bairro`
        
        **3. CONTAS BANCÁRIAS** (Complementar)
        - Dados de contas bancárias
        - Colunas mínimas: `numero_conta`, `cpf`, `agencia`, `banco`
        
        ### Formato dos Arquivos:
        - **CSV** com separador ponto-e-vírgula (`;`) ou vírgula (`,`)
        - **Excel** (.xls, .xlsx)
        - O sistema detecta automaticamente mês/ano pelo nome do arquivo
        """)
    
    # Upload
    st.subheader("Selecionar Arquivo para Importação")
    
    col_tipo, col_mes, col_ano = st.columns(3)
    
    with col_tipo:
        tipo_arquivo = st.selectbox(
            "Tipo de Arquivo",
            ["PAGAMENTOS", "CADASTRO_BENEFICIARIOS", "CONTAS_BANCARIAS"],
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
        f"Selecione o arquivo",
        type=['csv', 'xls', 'xlsx'],
        key=f"upload_{tipo_arquivo}"
    )
    
    if uploaded_file is not None:
        st.success(f"📄 **Arquivo selecionado:** {uploaded_file.name}")
        st.info(f"📋 **Tipo:** {tipo_arquivo.replace('_', ' ').title()}")
        
        # Prévia dos dados
        if st.button("👁️ Ver Prévia dos Dados", use_container_width=True):
            processador = ProcessadorArquivos(conn)
            df_previa, mensagem = processador._ler_arquivo(uploaded_file)
            if df_previa is not None:
                df_previa.columns = [processador.normalizador.normalizar_nome_coluna(col) for col in df_previa.columns]
                st.dataframe(df_previa.head(10), use_container_width=True)
                st.info(f"📊 Total de registros: {len(df_previa)}")
                
                # Mostrar colunas detectadas
                st.info(f"📋 Colunas detectadas: {', '.join(df_previa.columns)}")
        
        # Processar arquivo
        if st.button("🔄 Processar Arquivo", type="primary", use_container_width=True):
            processador = ProcessadorArquivos(conn)
            
            with st.spinner("Processando arquivo..."):
                sucesso, mensagem, inconsistencias = processador.processar_arquivo(
                    uploaded_file, tipo_arquivo, mes_num, ano_num, "USUARIO"
                )
            
            if sucesso:
                st.success(f"✅ {mensagem}")
                
                if inconsistencias:
                    st.warning(f"⚠️ Foram detectadas {len(inconsistencias)} inconsistências:")
                    for inc in inconsistencias:
                        st.markdown(f"- **{inc['tipo']}** ({inc['severidade']}): {inc['descricao']}")
                
                st.balloons()
                st.rerun()
            else:
                st.error(f"❌ {mensagem}")

def mostrar_consulta_beneficiarios(conn):
    """Interface de consulta de beneficiários"""
    st.header("🔍 Consulta de Beneficiários")
    
    col1, col2 = st.columns(2)
    
    with col1:
        cpf_consulta = st.text_input("CPF (somente números)", placeholder="00000000000")
    
    with col2:
        nome_consulta = st.text_input("Nome (parcial)", placeholder="Digite parte do nome")
    
    buscar = st.button("🔍 Buscar", use_container_width=True)
    
    if buscar and (cpf_consulta or nome_consulta):
        cursor = conn.cursor()
        
        query = '''
            SELECT 
                b.cpf,
                b.nome,
                b.rg,
                b.status,
                b.data_cadastro,
                COUNT(DISTINCT c.numero_conta) as num_contas,
                COUNT(DISTINCT p.id) as num_pagamentos,
                SUM(p.valor_liquido) as total_recebido
            FROM beneficiarios b
            LEFT JOIN contas_bancarias c ON b.cpf = c.cpf_titular
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
            normalizador = NormalizadorDados()
            nome_normalizado = normalizador.normalizar_nome(nome_consulta)
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
                columns=['CPF', 'Nome', 'RG', 'Status', 'Data Cadastro', 
                        'Contas', 'Pagamentos', 'Total Recebido'])
            
            st.subheader(f"Resultados: {len(df_resultados)} beneficiários")
            
            # Métricas
            col_res1, col_res2 = st.columns(2)
            with col_res1:
                st.metric("Total Recebido", f"R$ {df_resultados['Total Recebido'].sum():,.2f}")
            with col_res2:
                st.metric("Média por Beneficiário", f"R$ {df_resultados['Total Recebido'].mean():,.2f}")
            
            # Tabela
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
                st.subheader(f"Histórico de Pagamentos")
                
                cursor.execute('''
                    SELECT 
                        mes_referencia || '/' || ano_referencia as periodo,
                        valor_liquido,
                        codigo_projeto,
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
            st.info("Nenhum beneficiário encontrado.")

def mostrar_relatorios(conn):
    """Interface de relatórios"""
    st.header("📊 Relatórios")
    
    analisador = AnalisadorDados(conn)
    
    tab1, tab2 = st.tabs(["📈 Análise por Período", "📋 Inconsistências"])
    
    with tab1:
        st.subheader("Análise por Período")
        
        col1, col2 = st.columns(2)
        with col1:
            meses = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
            mes_rel = st.selectbox("Mês", meses)
            mes_num = meses.index(mes_rel) if mes_rel else None
        
        with col2:
            ano_atual = datetime.now().year
            anos = [""] + list(range(ano_atual, ano_atual - 5, -1))
            ano_rel = st.selectbox("Ano", anos)
            ano_num = int(ano_rel) if ano_rel else None
        
        if st.button("Gerar Relatório", use_container_width=True) and mes_num and ano_num:
            df_resumo = analisador.obter_resumo_mensal(mes_num, ano_num)
            
            if not df_resumo.empty:
                resumo = df_resumo.iloc[0]
                
                st.success(f"📊 Relatório de {mes_rel}/{ano_num}")
                
                col_met1, col_met2, col_met3 = st.columns(3)
                with col_met1:
                    st.metric("Beneficiários", f"{resumo['beneficiarios_pagos']:,}")
                with col_met2:
                    st.metric("Valor Total", f"R$ {resumo['valor_total_pago']:,.2f}")
                with col_met3:
                    st.metric("Valor Médio", f"R$ {resumo['valor_medio_pagamento']:,.2f}")
                
                # Projetos
                df_projetos = analisador.obter_pagamentos_por_projeto(mes_num, ano_num)
                if not df_projetos.empty:
                    st.subheader("Distribuição por Projeto")
                    
                    fig = px.bar(
                        df_projetos.head(10),
                        x='projeto',
                        y='valor_total',
                        title=f'Top 10 Projetos - {mes_rel}/{ano_num}'
                    )
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning(f"Nenhum dado encontrado para {mes_rel}/{ano_num}")
    
    with tab2:
        st.subheader("Relatório de Inconsistências")
        
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                tipo_inconsistencia,
                severidade,
                descricao,
                cpf_envolvido,
                data_deteccao,
                fonte_dados
            FROM inconsistencias
            WHERE status = 'PENDENTE'
            ORDER BY data_deteccao DESC
        ''')
        
        detalhes = cursor.fetchall()
        if detalhes:
            df_detalhes = pd.DataFrame(detalhes, 
                columns=['Tipo', 'Severidade', 'Descrição', 'CPF', 'Data Detecção', 'Fonte'])
            
            st.dataframe(df_detalhes, use_container_width=True)
            
            # Exportar
            csv = df_detalhes.to_csv(index=False, sep=';', encoding='latin-1')
            st.download_button(
                label="📥 Download CSV",
                data=csv,
                file_name=f"inconsistencias_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        else:
            st.success("✅ Nenhuma inconsistência pendente!")

def mostrar_configuracoes(conn):
    """Interface de configurações"""
    st.header("⚙️ Configurações")
    
    tab1, tab2 = st.tabs(["Banco de Dados", "Manutenção"])
    
    with tab1:
        st.subheader("Status do Banco de Dados")
        
        cursor = conn.cursor()
        
        # Tamanho
        if os.path.exists('pot_beneficios_simplificado.db'):
            tamanho_mb = os.path.getsize('pot_beneficios_simplificado.db') / 1024 / 1024
            st.info(f"📊 Tamanho do banco: {tamanho_mb:.2f} MB")
        
        # Contagens
        tabelas = ['beneficiarios', 'contas_bancarias', 'pagamentos', 'inconsistencias']
        for tabela in tabelas:
            cursor.execute(f"SELECT COUNT(*) FROM {tabela}")
            count = cursor.fetchone()[0]
            st.metric(f"Registros em {tabela.replace('_', ' ').title()}", f"{count:,}")
    
    with tab2:
        st.subheader("Manutenção")
        
        if st.button("🗑️ Limpar Dados Antigos (últimos 6 meses)", use_container_width=True):
            confirmacao = st.checkbox("Confirmar limpeza")
            if confirmacao:
                try:
                    data_limite = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM pagamentos WHERE data_pagamento < ?", (data_limite,))
                    cursor.execute("DELETE FROM arquivos_processados WHERE data_processamento < ?", (data_limite,))
                    conn.commit()
                    st.success("✅ Dados antigos removidos!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Erro: {str(e)}")
        
        if st.button("⚡ Otimizar Banco de Dados", use_container_width=True):
            try:
                cursor = conn.cursor()
                cursor.execute("VACUUM")
                conn.commit()
                st.success("✅ Banco otimizado!")
            except Exception as e:
                st.error(f"❌ Erro: {str(e)}")

# ========== FUNÇÃO PRINCIPAL ==========
def main():
    # Inicializar banco
    conn = init_database()
    
    if not conn:
        st.error("❌ Erro ao inicializar banco de dados")
        return
    
    # Menu
    st.sidebar.title("💰 POT - SMDET")
    st.sidebar.markdown("**Sistema de Gestão de Benefícios**")
    st.sidebar.markdown("---")
    
    menu_opcoes = [
        "📊 Dashboard",
        "📤 Importar Arquivos",
        "🔍 Consulta Beneficiários",
        "📊 Relatórios",
        "⚙️ Configurações"
    ]
    
    menu_selecionado = st.sidebar.radio("Navegação", menu_opcoes)
    
    # Páginas
    if menu_selecionado == "📊 Dashboard":
        mostrar_dashboard(conn)
    elif menu_selecionado == "📤 Importar Arquivos":
        mostrar_importacao(conn)
    elif menu_selecionado == "🔍 Consulta Beneficiários":
        mostrar_consulta_beneficiarios(conn)
    elif menu_selecionado == "📊 Relatórios":
        mostrar_relatorios(conn)
    elif menu_selecionado == "⚙️ Configurações":
        mostrar_configuracoes(conn)
    
    # Rodapé
    st.sidebar.markdown("---")
    st.sidebar.caption(f"© {datetime.now().year} Sistema POT - SMDET")
    st.sidebar.caption("Versão 2.0 - Corrigida")
    
    conn.close()

if __name__ == "__main__":
    main()
