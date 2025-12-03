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
        conn = sqlite3.connect('pot_beneficios.db', check_same_thread=False)
        
        # 1. Tabela de beneficiários
        conn.execute('''
            CREATE TABLE IF NOT EXISTS beneficiarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cpf TEXT UNIQUE NOT NULL,
                nome TEXT NOT NULL,
                nome_normalizado TEXT,
                rg TEXT,
                telefone TEXT,
                email TEXT,
                endereco TEXT,
                bairro TEXT,
                status TEXT DEFAULT 'ATIVO',
                data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 2. Tabela de pagamentos
        conn.execute('''
            CREATE TABLE IF NOT EXISTS pagamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                numero_conta TEXT NOT NULL,
                cpf_beneficiario TEXT NOT NULL,
                nome_beneficiario TEXT NOT NULL,
                projeto TEXT,
                mes_referencia INTEGER NOT NULL,
                ano_referencia INTEGER NOT NULL,
                valor_bruto DECIMAL(10,2) NOT NULL,
                valor_liquido DECIMAL(10,2) NOT NULL,
                valor_desconto DECIMAL(10,2) DEFAULT 0,
                dias_trabalhados INTEGER DEFAULT 20,
                status_pagamento TEXT DEFAULT 'PAGO',
                arquivo_origem TEXT,
                data_processamento TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(numero_conta, mes_referencia, ano_referencia)
            )
        ''')
        
        # 3. Tabela de arquivos processados
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
                status_processamento TEXT DEFAULT 'SUCESSO',
                erros_processamento TEXT
            )
        ''')
        
        # 4. Tabela de inconsistências
        conn.execute('''
            CREATE TABLE IF NOT EXISTS inconsistencias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT NOT NULL,
                severidade TEXT NOT NULL,
                descricao TEXT NOT NULL,
                cpf_envolvido TEXT,
                conta_envolvida TEXT,
                data_deteccao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'PENDENTE',
                fonte_dados TEXT
            )
        ''')
        
        conn.commit()
        
        # Criar índices
        criar_indices(conn)
        
        return conn
        
    except Exception as e:
        st.error(f"❌ Erro ao inicializar banco de dados: {str(e)}")
        return None

def criar_indices(conn):
    """Cria índices para performance"""
    indices = [
        "CREATE INDEX IF NOT EXISTS idx_beneficiarios_cpf ON beneficiarios(cpf)",
        "CREATE INDEX IF NOT EXISTS idx_pagamentos_periodo ON pagamentos(ano_referencia, mes_referencia)",
        "CREATE INDEX IF NOT EXISTS idx_pagamentos_cpf ON pagamentos(cpf_beneficiario)",
        "CREATE INDEX IF NOT EXISTS idx_arquivos_hash ON arquivos_processados(hash_arquivo)",
        "CREATE INDEX IF NOT EXISTS idx_inconsistencias_status ON inconsistencias(status)"
    ]
    
    for idx in indices:
        try:
            conn.execute(idx)
        except:
            pass
    
    conn.commit()

# ========== NORMALIZAÇÃO DE DADOS ==========
class NormalizadorDados:
    """Classe para normalização de dados"""
    
    @staticmethod
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
    
    @staticmethod
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
    
    @staticmethod
    def normalizar_valor(valor):
        """Converte valor para numérico"""
        if pd.isna(valor):
            return 0.0
        
        valor_str = str(valor).strip()
        valor_str = re.sub(r'[R\$\s]', '', valor_str)
        
        # Tratar formato brasileiro
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
            'valor_diario': 'valor_diario'
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
    
    def processar_arquivo(self, uploaded_file, tipo_arquivo, mes=None, ano=None):
        """Processa arquivo"""
        
        # Calcular hash
        conteudo = uploaded_file.getvalue()
        hash_arquivo = hashlib.md5(conteudo).hexdigest()
        
        # Verificar se já processado
        if self._arquivo_ja_processado(hash_arquivo):
            return False, "Arquivo já processado", []
        
        # Detectar mês/ano
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
        
        # Processar
        if tipo_arquivo == 'PAGAMENTOS':
            sucesso, mensagem = self._processar_pagamentos(df, mes, ano, uploaded_file.name, hash_arquivo)
        elif tipo_arquivo == 'CADASTRO':
            sucesso, mensagem = self._processar_cadastro(df, uploaded_file.name, hash_arquivo)
        else:
            return False, f"Tipo não suportado: {tipo_arquivo}", inconsistencias
        
        # Registrar processamento
        self._registrar_processamento(uploaded_file.name, tipo_arquivo, mes, ano, 
                                     len(df), hash_arquivo, sucesso, mensagem)
        
        # Registrar inconsistências
        if inconsistencias:
            self._registrar_inconsistencias(inconsistencias, tipo_arquivo, uploaded_file.name)
        
        return sucesso, mensagem, inconsistencias
    
    def _ler_arquivo(self, uploaded_file):
        """Lê arquivo"""
        try:
            # Salvar temporariamente
            with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                tmp_path = tmp_file.name
            
            try:
                # Verificar extensão
                if uploaded_file.name.lower().endswith('.csv'):
                    # Tentar diferentes encodings
                    for encoding in ['utf-8', 'latin-1', 'cp1252']:
                        try:
                            df = pd.read_csv(tmp_path, sep=';', encoding=encoding, dtype=str, on_bad_lines='skip')
                            if not df.empty:
                                break
                        except:
                            continue
                    
                    # Tentar com separador automático
                    if df.empty or len(df.columns) == 1:
                        try:
                            df = pd.read_csv(tmp_path, sep=None, engine='python', dtype=str, on_bad_lines='skip')
                        except:
                            df = pd.read_csv(tmp_path, sep=',', dtype=str, on_bad_lines='skip')
                
                elif uploaded_file.name.lower().endswith(('.xls', '.xlsx')):
                    try:
                        df = pd.read_excel(tmp_path, dtype=str)
                    except:
                        df = pd.read_excel(tmp_path, dtype=str, engine='openpyxl')
                
                # Limpar
                os.unlink(tmp_path)
                
                if df.empty:
                    return None, "Arquivo vazio"
                
                # Remover colunas vazias
                df = df.dropna(axis=1, how='all')
                
                return df, "Arquivo lido"
                
            except Exception as e:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                return None, f"Erro ao ler: {str(e)}"
                
        except Exception as e:
            return None, f"Erro: {str(e)}"
    
    def _detectar_mes_ano(self, nome_arquivo):
        """Detecta mês e ano do arquivo"""
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
        
        # Padrão se não detectou
        if mes is None:
            mes = datetime.now().month
        
        return mes, ano
    
    def _arquivo_ja_processado(self, hash_arquivo):
        """Verifica se arquivo já foi processado"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM arquivos_processados WHERE hash_arquivo = ?", (hash_arquivo,))
        return cursor.fetchone() is not None
    
    def _detectar_inconsistencias(self, df, tipo_arquivo):
        """Detecta inconsistências"""
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
                'descricao': f'Faltam colunas: {", ".join(colunas_faltantes)}'
            })
        
        # Verificar valores nulos
        for col in obrigatorias:
            if col in df.columns:
                nulos = df[col].isna().sum()
                if nulos > 0:
                    inconsistencias.append({
                        'tipo': f'VALORES_NULOS_{col}',
                        'severidade': 'MEDIA',
                        'descricao': f'{nulos} registros sem {col}'
                    })
        
        # Verificar valores zerados em pagamentos
        if tipo_arquivo == 'PAGAMENTOS' and 'valor' in df.columns:
            zerados = (df['valor'].apply(self.normalizador.normalizar_valor) <= 0).sum()
            if zerados > 0:
                inconsistencias.append({
                    'tipo': 'VALORES_ZERADOS',
                    'severidade': 'ALTA',
                    'descricao': f'{zerados} valores zerados/negativos'
                })
        
        return inconsistencias
    
    def _registrar_processamento(self, nome_arquivo, tipo_arquivo, mes, ano, 
                                total_registros, hash_arquivo, sucesso, mensagem):
        """Registra processamento"""
        try:
            cursor = self.conn.cursor()
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
            self.conn.commit()
        except Exception as e:
            st.error(f"Erro registro: {str(e)}")
    
    def _registrar_inconsistencias(self, inconsistencias, fonte_dados, arquivo_origem):
        """Registra inconsistências"""
        try:
            cursor = self.conn.cursor()
            for inc in inconsistencias:
                cursor.execute('''
                    INSERT INTO inconsistencias 
                    (tipo, severidade, descricao, fonte_dados)
                    VALUES (?, ?, ?, ?)
                ''', (
                    inc['tipo'],
                    inc['severidade'],
                    inc['descricao'],
                    fonte_dados
                ))
            self.conn.commit()
        except Exception as e:
            st.error(f"Erro inconsistências: {str(e)}")
    
    def _processar_pagamentos(self, df, mes, ano, nome_arquivo, hash_arquivo):
        """Processa pagamentos"""
        try:
            cursor = self.conn.cursor()
            registros_processados = 0
            valor_total = 0
            
            for _, row in df.iterrows():
                try:
                    # Extrair dados
                    numero_conta = str(row.get('numero_conta', '')).strip()
                    nome = self.normalizador.normalizar_nome(str(row.get('nome', '')))
                    cpf = self.normalizador.normalizar_cpf(row.get('cpf', ''))
                    valor_bruto = self.normalizador.normalizar_valor(row.get('valor'))
                    valor_liquido = self.normalizador.normalizar_valor(row.get('valor_liquido', valor_bruto))
                    projeto = str(row.get('projeto', '')).strip()
                    dias = int(row.get('dias_trabalhados', 20))
                    
                    # Validar
                    if not numero_conta or not nome or valor_liquido <= 0:
                        continue
                    
                    # Se não tem CPF, buscar ou criar
                    if not cpf or len(cpf) != 11:
                        cursor.execute("SELECT cpf FROM beneficiarios WHERE nome_normalizado LIKE ? LIMIT 1", 
                                     (f"%{nome}%",))
                        resultado = cursor.fetchone()
                        if resultado:
                            cpf = resultado[0]
                        else:
                            cpf = f"SEM_CPF_{hash(nome) % 1000000:06d}"
                    
                    # Inserir beneficiário se não existir
                    cursor.execute('''
                        INSERT OR IGNORE INTO beneficiarios 
                        (cpf, nome, nome_normalizado, status)
                        VALUES (?, ?, ?, 'ATIVO')
                    ''', (cpf, nome, nome))
                    
                    # Calcular desconto
                    valor_desconto = valor_bruto - valor_liquido
                    
                    # Inserir pagamento
                    cursor.execute('''
                        INSERT OR REPLACE INTO pagamentos 
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
                    continue
            
            self.conn.commit()
            
            # Atualizar arquivo processado com valor total
            cursor.execute('''
                UPDATE arquivos_processados 
                SET registros_processados = ?,
                    valor_total = ?
                WHERE hash_arquivo = ?
            ''', (registros_processados, valor_total, hash_arquivo))
            self.conn.commit()
            
            return True, f"✅ {registros_processados} pagamentos | R$ {valor_total:,.2f}"
            
        except Exception as e:
            self.conn.rollback()
            return False, f"❌ Erro: {str(e)}"
    
    def _processar_cadastro(self, df, nome_arquivo, hash_arquivo):
        """Processa cadastro"""
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
                    
                    # Inserir ou atualizar
                    cursor.execute('''
                        INSERT OR REPLACE INTO beneficiarios 
                        (cpf, nome, nome_normalizado, rg, telefone, email, endereco, bairro, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ATIVO')
                    ''', (cpf, nome, nome, rg, telefone, email, endereco, bairro))
                    
                    registros_processados += 1
                    
                except Exception as e:
                    continue
            
            self.conn.commit()
            
            # Atualizar arquivo processado
            cursor.execute('''
                UPDATE arquivos_processados 
                SET registros_processados = ?
                WHERE hash_arquivo = ?
            ''', (registros_processados, hash_arquivo))
            self.conn.commit()
            
            return True, f"✅ {registros_processados} cadastros processados"
            
        except Exception as e:
            self.conn.rollback()
            return False, f"❌ Erro: {str(e)}"

# ========== ANÁLISE ==========
class AnalisadorDados:
    """Classe para análise"""
    
    def __init__(self, conn):
        self.conn = conn
    
    def obter_resumo_geral(self):
        """Obtém resumo geral"""
        cursor = self.conn.cursor()
        resumo = {}
        
        cursor.execute("SELECT COUNT(*) FROM beneficiarios WHERE status = 'ATIVO'")
        resumo['beneficiarios'] = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(DISTINCT cpf_beneficiario) FROM pagamentos")
        resumo['beneficiarios_pagos'] = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT SUM(valor_liquido) FROM pagamentos")
        resumo['valor_total'] = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM pagamentos")
        resumo['total_pagamentos'] = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM inconsistencias WHERE status = 'PENDENTE'")
        resumo['inconsistencias'] = cursor.fetchone()[0] or 0
        
        cursor.execute('''
            SELECT MAX(ano_referencia), MAX(mes_referencia)
            FROM pagamentos
        ''')
        ultimo = cursor.fetchone()
        if ultimo[0]:
            resumo['ultimo_mes'] = f"{ultimo[1]:02d}/{ultimo[0]}"
        else:
            resumo['ultimo_mes'] = "Nenhum"
        
        cursor.execute("SELECT COUNT(*) FROM arquivos_processados WHERE status_processamento = 'SUCESSO'")
        resumo['arquivos'] = cursor.fetchone()[0] or 0
        
        return resumo
    
    def obter_resumo_mensal(self, mes=None, ano=None):
        """Obtém resumo mensal"""
        try:
            cursor = self.conn.cursor()
            
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
    
    def obter_inconsistencias(self):
        """Obtém inconsistências"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT 
                    tipo,
                    severidade,
                    COUNT(*) as quantidade,
                    GROUP_CONCAT(DISTINCT cpf_envolvido) as cpfs
                FROM inconsistencias
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
    
    def obter_pagamentos_por_projeto(self, mes=None, ano=None):
        """Obtém pagamentos por projeto"""
        try:
            cursor = self.conn.cursor()
            
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

# ========== INTERFACE ==========
def mostrar_dashboard(conn):
    """Mostra dashboard"""
    st.title("💰 Sistema POT - Gestão de Benefícios")
    st.markdown("---")
    
    analisador = AnalisadorDados(conn)
    resumo = analisador.obter_resumo_geral()
    
    # Métricas
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Beneficiários", f"{resumo['beneficiarios']:,}")
        st.caption(f"Pagamentos: {resumo['beneficiarios_pagos']:,}")
    
    with col2:
        st.metric("Valor Total", f"R$ {resumo['valor_total']:,.2f}")
        st.caption(f"Pagamentos: {resumo['total_pagamentos']:,}")
    
    with col3:
        st.metric("Último Mês", resumo['ultimo_mes'])
        st.caption(f"Arquivos: {resumo['arquivos']:,}")
    
    with col4:
        st.metric("Inconsistências", f"{resumo['inconsistencias']:,}")
        st.caption("Pendentes")
    
    st.markdown("---")
    
    # Abas
    tab1, tab2, tab3 = st.tabs(["📊 Resumo Mensal", "⚠️ Inconsistências", "📋 Projetos"])
    
    with tab1:
        st.subheader("Resumo Mensal")
        
        df_resumo = analisador.obter_resumo_mensal()
        if not df_resumo.empty:
            # Gráfico
            fig = px.line(
                df_resumo,
                x='periodo',
                y='valor_total',
                title='Evolução do Valor Total Pago',
                markers=True
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Tabela
            st.dataframe(
                df_resumo[['periodo', 'beneficiarios', 'pagamentos', 'valor_total', 'valor_medio', 'dias']],
                use_container_width=True,
                column_config={
                    'valor_total': st.column_config.NumberColumn('Valor Total (R$)', format="R$ %.2f"),
                    'valor_medio': st.column_config.NumberColumn('Média (R$)', format="R$ %.2f")
                }
            )
        else:
            st.info("📭 Nenhum pagamento processado. Importe arquivos de pagamentos.")
    
    with tab2:
        st.subheader("Inconsistências Detectadas")
        
        df_inconsistencias = analisador.obter_inconsistencias()
        if not df_inconsistencias.empty:
            # Gráfico
            fig = px.bar(
                df_inconsistencias,
                x='tipo',
                y='quantidade',
                color='severidade',
                title='Inconsistências por Tipo'
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Tabela
            st.dataframe(df_inconsistencias, use_container_width=True)
            
            # Botão correção
            if st.button("🗑️ Marcar como Resolvidas"):
                cursor = conn.cursor()
                cursor.execute("UPDATE inconsistencias SET status = 'RESOLVIDO' WHERE status = 'PENDENTE'")
                conn.commit()
                st.success("✅ Marcadas como resolvidas!")
                st.rerun()
        else:
            st.success("✅ Nenhuma inconsistência!")
    
    with tab3:
        st.subheader("Pagamentos por Projeto")
        
        df_projetos = analisador.obter_pagamentos_por_projeto()
        if not df_projetos.empty:
            # Gráfico
            fig = px.pie(
                df_projetos.head(10),
                values='valor_total',
                names='projeto',
                title='Top 10 Projetos'
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Tabela
            st.dataframe(
                df_projetos,
                use_container_width=True,
                column_config={
                    'valor_total': st.column_config.NumberColumn('Valor Total (R$)', format="R$ %.2f"),
                    'valor_medio': st.column_config.NumberColumn('Média (R$)', format="R$ %.2f")
                }
            )
        else:
            st.info("📭 Nenhum projeto registrado.")

def mostrar_importacao(conn):
    """Interface de importação"""
    st.header("📤 Importar Arquivos")
    
    # Instruções
    with st.expander("ℹ️ Instruções"):
        st.markdown("""
        ### Tipos de Arquivos:
        
        **1. PAGAMENTOS** (Principal)
        - Arquivos de pagamento
        - Colunas necessárias: `numero_conta`, `nome`, `valor`
        - Colunas opcionais: `cpf`, `projeto`, `dias_trabalhados`
        
        **2. CADASTRO** (Complementar)
        - Dados cadastrais
        - Colunas necessárias: `cpf`, `nome`
        - Colunas opcionais: `rg`, `telefone`, `email`, `endereco`
        
        ### Formatos:
        - CSV (separador ; ou ,)
        - Excel (.xls, .xlsx)
        - Mês/ano detectado automaticamente
        """)
    
    # Upload
    st.subheader("Selecionar Arquivo")
    
    col_tipo, col_mes, col_ano = st.columns(3)
    
    with col_tipo:
        tipo_arquivo = st.selectbox(
            "Tipo",
            ["PAGAMENTOS", "CADASTRO"],
            index=0
        )
    
    with col_mes:
        meses = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
        mes_selecionado = st.selectbox("Mês (pagamentos)", meses)
        mes_num = meses.index(mes_selecionado) if mes_selecionado else None
    
    with col_ano:
        ano_atual = datetime.now().year
        anos = [""] + list(range(ano_atual, ano_atual - 5, -1))
        ano_selecionado = st.selectbox("Ano (pagamentos)", anos)
        ano_num = int(ano_selecionado) if ano_selecionado else None
    
    # Upload
    uploaded_file = st.file_uploader(
        "Arquivo",
        type=['csv', 'xls', 'xlsx'],
        key="upload_file"
    )
    
    if uploaded_file is not None:
        st.success(f"📄 Arquivo: {uploaded_file.name}")
        st.info(f"📋 Tipo: {tipo_arquivo}")
        
        # Prévia
        if st.button("👁️ Ver Prévia"):
            processador = ProcessadorArquivos(conn)
            df_previa, mensagem = processador._ler_arquivo(uploaded_file)
            if df_previa is not None:
                df_previa.columns = [processador.normalizador.normalizar_nome_coluna(col) for col in df_previa.columns]
                st.dataframe(df_previa.head(10), use_container_width=True)
                st.info(f"📊 Registros: {len(df_previa)}")
                st.info(f"📋 Colunas: {', '.join(df_previa.columns)}")
        
        # Processar
        if st.button("🔄 Processar", type="primary"):
            processador = ProcessadorArquivos(conn)
            
            with st.spinner("Processando..."):
                sucesso, mensagem, inconsistencias = processador.processar_arquivo(
                    uploaded_file, tipo_arquivo, mes_num, ano_num
                )
            
            if sucesso:
                st.success(f"✅ {mensagem}")
                
                if inconsistencias:
                    st.warning(f"⚠️ {len(inconsistencias)} inconsistências:")
                    for inc in inconsistencias:
                        st.markdown(f"- **{inc['tipo']}**: {inc['descricao']}")
                
                st.balloons()
                st.rerun()
            else:
                st.error(f"❌ {mensagem}")

def mostrar_consulta(conn):
    """Consulta de beneficiários"""
    st.header("🔍 Consulta de Beneficiários")
    
    col1, col2 = st.columns(2)
    
    with col1:
        cpf_consulta = st.text_input("CPF", placeholder="Somente números")
    
    with col2:
        nome_consulta = st.text_input("Nome", placeholder="Parcial")
    
    if st.button("🔍 Buscar"):
        cursor = conn.cursor()
        
        query = '''
            SELECT 
                b.cpf,
                b.nome,
                b.rg,
                b.status,
                COUNT(DISTINCT p.id) as pagamentos,
                SUM(p.valor_liquido) as total
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
            normalizador = NormalizadorDados()
            nome_normalizado = normalizador.normalizar_nome(nome_consulta)
            query += ' AND b.nome_normalizado LIKE ?'
            params.append(f'%{nome_normalizado}%')
        
        query += '''
            GROUP BY b.cpf, b.nome, b.rg, b.status
            ORDER BY b.nome
            LIMIT 100
        '''
        
        cursor.execute(query, params)
        resultados = cursor.fetchall()
        
        if resultados:
            df = pd.DataFrame(resultados, 
                columns=['CPF', 'Nome', 'RG', 'Status', 'Pagamentos', 'Total'])
            
            st.subheader(f"Resultados: {len(df)} beneficiários")
            
            # Métricas
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total Recebido", f"R$ {df['Total'].sum():,.2f}")
            with col2:
                st.metric("Média", f"R$ {df['Total'].mean():,.2f}")
            
            # Tabela
            st.dataframe(
                df,
                use_container_width=True,
                column_config={
                    'Total': st.column_config.NumberColumn('Total (R$)', format="R$ %.2f")
                }
            )
        else:
            st.info("Nenhum resultado")

def mostrar_relatorios(conn):
    """Relatórios"""
    st.header("📊 Relatórios")
    
    analisador = AnalisadorDados(conn)
    
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
    
    if st.button("📈 Gerar Relatório") and mes_num and ano_num:
        df_resumo = analisador.obter_resumo_mensal(mes_num, ano_num)
        
        if not df_resumo.empty:
            resumo = df_resumo.iloc[0]
            
            st.success(f"📊 Relatório: {mes_rel}/{ano_num}")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Beneficiários", f"{resumo['beneficiarios']:,}")
            with col2:
                st.metric("Valor Total", f"R$ {resumo['valor_total']:,.2f}")
            with col3:
                st.metric("Valor Médio", f"R$ {resumo['valor_medio']:,.2f}")
            
            # Projetos
            df_projetos = analisador.obter_pagamentos_por_projeto(mes_num, ano_num)
            if not df_projetos.empty:
                st.subheader("Projetos")
                st.dataframe(
                    df_projetos,
                    use_container_width=True,
                    column_config={
                        'valor_total': st.column_config.NumberColumn('Valor (R$)', format="R$ %.2f")
                    }
                )
        else:
            st.warning(f"Nenhum dado para {mes_rel}/{ano_num}")

def mostrar_configuracoes(conn):
    """Configurações"""
    st.header("⚙️ Configurações")
    
    tab1, tab2 = st.tabs(["Banco", "Manutenção"])
    
    with tab1:
        st.subheader("Banco de Dados")
        
        cursor = conn.cursor()
        
        if os.path.exists('pot_beneficios.db'):
            tamanho = os.path.getsize('pot_beneficios.db') / 1024 / 1024
            st.info(f"📊 Tamanho: {tamanho:.2f} MB")
        
        tabelas = ['beneficiarios', 'pagamentos', 'arquivos_processados', 'inconsistencias']
        for tabela in tabelas:
            cursor.execute(f"SELECT COUNT(*) FROM {tabela}")
            count = cursor.fetchone()[0]
            st.metric(tabela.title(), f"{count:,}")
    
    with tab2:
        st.subheader("Manutenção")
        
        if st.button("🗑️ Limpar Dados Antigos"):
            confirmacao = st.checkbox("Confirmar")
            if confirmacao:
                try:
                    data_limite = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM pagamentos WHERE data_processamento < ?", (data_limite,))
                    cursor.execute("DELETE FROM arquivos_processados WHERE data_processamento < ?", (data_limite,))
                    conn.commit()
                    st.success("✅ Limpeza concluída!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Erro: {str(e)}")
        
        if st.button("⚡ Otimizar Banco"):
            try:
                cursor = conn.cursor()
                cursor.execute("VACUUM")
                conn.commit()
                st.success("✅ Otimizado!")
            except Exception as e:
                st.error(f"❌ Erro: {str(e)}")

# ========== MAIN ==========
def main():
    # Inicializar
    conn = init_database()
    
    if not conn:
        st.error("❌ Erro no banco")
        return
    
    # Menu
    st.sidebar.title("💰 POT - SMDET")
    st.sidebar.markdown("Gestão de Benefícios")
    st.sidebar.markdown("---")
    
    opcoes = [
        "📊 Dashboard",
        "📤 Importar",
        "🔍 Consulta",
        "📊 Relatórios",
        "⚙️ Configurações"
    ]
    
    selecionado = st.sidebar.radio("Menu", opcoes)
    
    # Páginas
    if selecionado == "📊 Dashboard":
        mostrar_dashboard(conn)
    elif selecionado == "📤 Importar":
        mostrar_importacao(conn)
    elif selecionado == "🔍 Consulta":
        mostrar_consulta(conn)
    elif selecionado == "📊 Relatórios":
        mostrar_relatorios(conn)
    elif selecionado == "⚙️ Configurações":
        mostrar_configuracoes(conn)
    
    # Rodapé
    st.sidebar.markdown("---")
    st.sidebar.caption(f"© {datetime.now().year} SMDET")
    
    conn.close()

if __name__ == "__main__":
    main()
