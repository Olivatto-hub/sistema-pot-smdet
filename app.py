# app.py - SISTEMA POT SMDET - GESTÃO COMPLETA DE BENEFÍCIOS
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
from typing import Dict, List, Tuple, Optional, Any
import warnings
warnings.filterwarnings('ignore')

# ========== CONFIGURAÇÃO ==========
st.set_page_config(
    page_title="Sistema POT - Gestão de Benefícios",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========== BANCO DE DADOS COMPLETO ==========
def init_database():
    """Inicializa o banco de dados SQLite com todas as tabelas necessárias"""
    try:
        conn = sqlite3.connect('pot_beneficios_completo.db', check_same_thread=False)
        
        # ===== TABELAS PRINCIPAIS =====
        
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
                observacoes TEXT,
                INDEX idx_beneficiarios_cpf (cpf),
                INDEX idx_beneficiarios_nome (nome_normalizado)
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
                numero_conta TEXT UNIQUE NOT NULL,
                cpf_titular TEXT NOT NULL,
                banco TEXT NOT NULL,
                agencia TEXT NOT NULL,
                tipo_conta TEXT DEFAULT 'CORRENTE',
                data_abertura DATE,
                data_encerramento DATE,
                status TEXT DEFAULT 'ATIVA',
                motivo_encerramento TEXT,
                fonte_dados TEXT,
                data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cpf_titular) REFERENCES beneficiarios(cpf),
                INDEX idx_contas_numero (numero_conta),
                INDEX idx_contas_cpf (cpf_titular)
            )
        ''')
        
        # 4. Tabela de vínculos beneficiário-projeto
        conn.execute('''
            CREATE TABLE IF NOT EXISTS vinculos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cpf_beneficiario TEXT NOT NULL,
                codigo_projeto TEXT NOT NULL,
                numero_conta TEXT NOT NULL,
                data_inicio DATE NOT NULL,
                data_fim DATE,
                valor_diario DECIMAL(10,2),
                dias_semana INTEGER DEFAULT 5,
                status TEXT DEFAULT 'ATIVO',
                motivo_desligamento TEXT,
                data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cpf_beneficiario) REFERENCES beneficiarios(cpf),
                FOREIGN KEY (codigo_projeto) REFERENCES projetos(codigo),
                FOREIGN KEY (numero_conta) REFERENCES contas_bancarias(numero_conta),
                INDEX idx_vinculos_cpf (cpf_beneficiario),
                INDEX idx_vinculos_projeto (codigo_projeto)
            )
        ''')
        
        # ===== TABELAS DE PAGAMENTOS =====
        
        # 5. Tabela de pagamentos (histórico completo)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS pagamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                numero_conta TEXT NOT NULL,
                cpf_beneficiario TEXT NOT NULL,
                codigo_projeto TEXT NOT NULL,
                mes_referencia INTEGER NOT NULL,
                ano_referencia INTEGER NOT NULL,
                valor_bruto DECIMAL(10,2) NOT NULL,
                valor_desconto DECIMAL(10,2) DEFAULT 0,
                valor_liquido DECIMAL(10,2) NOT NULL,
                dias_trabalhados INTEGER,
                data_pagamento DATE,
                data_credito DATE,
                status_pagamento TEXT DEFAULT 'PAGO',
                arquivo_origem TEXT,
                lote_pagamento TEXT,
                observacoes TEXT,
                data_processamento TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (numero_conta) REFERENCES contas_bancarias(numero_conta),
                FOREIGN KEY (cpf_beneficiario) REFERENCES beneficiarios(cpf),
                FOREIGN KEY (codigo_projeto) REFERENCES projetos(codigo),
                INDEX idx_pagamentos_periodo (ano_referencia, mes_referencia),
                INDEX idx_pagamentos_conta (numero_conta),
                INDEX idx_pagamentos_cpf (cpf_beneficiario),
                UNIQUE(numero_conta, mes_referencia, ano_referencia, codigo_projeto)
            )
        ''')
        
        # 6. Tabela de lançamentos bancários (BB)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS lancamentos_bb (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                numero_conta TEXT,
                cpf_beneficiario TEXT,
                data_movimentacao DATE NOT NULL,
                descricao TEXT,
                valor DECIMAL(10,2) NOT NULL,
                tipo_movimentacao TEXT,
                codigo_banco TEXT,
                arquivo_origem TEXT,
                data_importacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status_conciliacao TEXT DEFAULT 'NAO_CONCILIADO',
                id_pagamento_conciliado INTEGER,
                FOREIGN KEY (numero_conta) REFERENCES contas_bancarias(numero_conta),
                FOREIGN KEY (cpf_beneficiario) REFERENCES beneficiarios(cpf),
                FOREIGN KEY (id_pagamento_conciliado) REFERENCES pagamentos(id),
                INDEX idx_lancamentos_data (data_movimentacao),
                INDEX idx_lancamentos_conta (numero_conta)
            )
        ''')
        
        # ===== TABELAS DE CONTROLE =====
        
        # 7. Tabela de arquivos processados
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
                erros_processamento TEXT,
                INDEX idx_arquivos_tipo (tipo_arquivo),
                INDEX idx_arquivos_periodo (ano_referencia, mes_referencia)
            )
        ''')
        
        # 8. Tabela de inconsistências detectadas
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
                fonte_dados TEXT,
                FOREIGN KEY (cpf_envolvido) REFERENCES beneficiarios(cpf),
                FOREIGN KEY (numero_conta_envolvido) REFERENCES contas_bancarias(numero_conta),
                INDEX idx_inconsistencias_tipo (tipo_inconsistencia),
                INDEX idx_inconsistencias_status (status),
                INDEX idx_inconsistencias_cpf (cpf_envolvido)
            )
        ''')
        
        # 9. Tabela de métricas e indicadores
        conn.execute('''
            CREATE TABLE IF NOT EXISTS metricas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo_metrica TEXT NOT NULL,
                mes_referencia INTEGER NOT NULL,
                ano_referencia INTEGER NOT NULL,
                valor DECIMAL(15,2) NOT NULL,
                descricao TEXT,
                data_calculo TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(tipo_metrica, mes_referencia, ano_referencia)
            )
        ''')
        
        # 10. Tabela de logs de atividades
        conn.execute('''
            CREATE TABLE IF NOT EXISTS logs_atividades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT,
                acao TEXT NOT NULL,
                modulo TEXT,
                descricao TEXT,
                ip_origem TEXT
            )
        ''')
        
        # ===== ÍNDICES ADICIONAIS =====
        
        conn.execute('CREATE INDEX IF NOT EXISTS idx_pagamentos_status ON pagamentos(status_pagamento)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_vinculos_status ON vinculos(status)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_contas_status ON contas_bancarias(status)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_beneficiarios_status ON beneficiarios(status)')
        
        conn.commit()
        
        # Criar views para relatórios
        criar_views_relatorios(conn)
        
        return conn
        
    except Exception as e:
        st.error(f"❌ Erro ao inicializar banco de dados: {str(e)}")
        return None

def criar_views_relatorios(conn):
    """Cria views para facilitar consultas de relatórios"""
    views = {
        'view_resumo_mensal': '''
            CREATE VIEW IF NOT EXISTS view_resumo_mensal AS
            SELECT 
                ano_referencia,
                mes_referencia,
                COUNT(DISTINCT cpf_beneficiario) as beneficiarios_ativos,
                COUNT(DISTINCT numero_conta) as contas_ativas,
                COUNT(DISTINCT codigo_projeto) as projetos_ativos,
                SUM(valor_liquido) as valor_total_pago,
                SUM(valor_desconto) as total_descontos,
                AVG(valor_liquido) as valor_medio_pagamento
            FROM pagamentos
            WHERE status_pagamento = 'PAGO'
            GROUP BY ano_referencia, mes_referencia
            ORDER BY ano_referencia DESC, mes_referencia DESC
        ''',
        
        'view_inconsistencias_pendentes': '''
            CREATE VIEW IF NOT EXISTS view_inconsistencias_pendentes AS
            SELECT 
                tipo_inconsistencia,
                severidade,
                COUNT(*) as quantidade,
                GROUP_CONCAT(DISTINCT cpf_envolvido) as cpfs_envolvidos
            FROM inconsistencias
            WHERE status = 'PENDENTE'
            GROUP BY tipo_inconsistencia, severidade
            ORDER BY 
                CASE severidade 
                    WHEN 'CRITICA' THEN 1
                    WHEN 'ALTA' THEN 2
                    WHEN 'MEDIA' THEN 3
                    WHEN 'BAIXA' THEN 4
                    ELSE 5
                END
        ''',
        
        'view_conciliacao_pagamentos': '''
            CREATE VIEW IF NOT EXISTS view_conciliacao_pagamentos AS
            SELECT 
                p.mes_referencia,
                p.ano_referencia,
                COUNT(p.id) as total_pagamentos,
                SUM(p.valor_liquido) as valor_total_pagamentos,
                COUNT(l.id) as lancamentos_conciliados,
                SUM(l.valor) as valor_conciliado,
                COUNT(p.id) - COUNT(l.id) as discrepancia_quantidade,
                SUM(p.valor_liquido) - SUM(COALESCE(l.valor, 0)) as discrepancia_valor
            FROM pagamentos p
            LEFT JOIN lancamentos_bb l ON p.id = l.id_pagamento_conciliado
            GROUP BY p.mes_referencia, p.ano_referencia
        '''
    }
    
    for view_name, view_sql in views.items():
        try:
            conn.execute(f'DROP VIEW IF EXISTS {view_name}')
            conn.execute(view_sql)
        except:
            pass
    
    conn.commit()

# ========== NORMALIZAÇÃO E PADRONIZAÇÃO ==========
class NormalizadorDados:
    """Classe para normalização e padronização de dados"""
    
    @staticmethod
    def normalizar_nome(nome: str) -> str:
        """Normaliza nome removendo acentos, maiúsculas e espaços extras"""
        if pd.isna(nome) or not isinstance(nome, str):
            return ""
        
        # Converter para string e remover espaços
        nome = str(nome).strip()
        
        # Remover múltiplos espaços
        nome = re.sub(r'\s+', ' ', nome)
        
        # Converter para maiúsculas e remover acentos
        nome = nome.upper()
        substituicoes = {
            'Á': 'A', 'À': 'A', 'Â': 'A', 'Ã': 'A', 'Ä': 'A',
            'É': 'E', 'È': 'E', 'Ê': 'E', 'Ë': 'E',
            'Í': 'I', 'Ì': 'I', 'Î': 'I', 'Ï': 'I',
            'Ó': 'O', 'Ò': 'O', 'Ô': 'O', 'Õ': 'O', 'Ö': 'O',
            'Ú': 'U', 'Ù': 'U', 'Û': 'U', 'Ü': 'U',
            'Ç': 'C', 'Ñ': 'N'
        }
        
        for char, subst in substituicoes.items():
            nome = nome.replace(char, subst)
        
        return nome
    
    @staticmethod
    def normalizar_cpf(cpf: Any) -> Optional[str]:
        """Normaliza CPF removendo caracteres não numéricos"""
        if pd.isna(cpf):
            return None
        
        cpf_str = str(cpf).strip()
        
        # Remover tudo que não é número
        cpf_limpo = re.sub(r'\D', '', cpf_str)
        
        # Verificar se tem 11 dígitos
        if len(cpf_limpo) == 11:
            return cpf_limpo
        elif len(cpf_limpo) > 11:
            return cpf_limpo[:11]
        else:
            return None
    
    @staticmethod
    def normalizar_valor(valor: Any) -> float:
        """Converte valor para numérico"""
        if pd.isna(valor):
            return 0.0
        
        valor_str = str(valor).strip()
        
        # Remover símbolos de moeda e espaços
        valor_str = re.sub(r'[R\$\s]', '', valor_str)
        
        # Substituir vírgula por ponto se necessário
        if ',' in valor_str and '.' in valor_str:
            # Se tem ambos, vírgula é decimal
            valor_str = valor_str.replace('.', '').replace(',', '.')
        elif ',' in valor_str:
            # Se só tem vírgula, pode ser decimal ou milhar
            if valor_str.count(',') == 1 and len(valor_str.split(',')[1]) == 2:
                # Provavelmente decimal
                valor_str = valor_str.replace(',', '.')
            else:
                # Provavelmente milhar
                valor_str = valor_str.replace(',', '')
        
        try:
            return float(valor_str)
        except:
            return 0.0
    
    @staticmethod
    def normalizar_data(data_str: Any) -> Optional[datetime.date]:
        """Converte data para objeto date"""
        if pd.isna(data_str):
            return None
        
        data_str = str(data_str).strip()
        if data_str in ['', 'nan', 'None', 'NaN', 'NaT']:
            return None
        
        formatos = [
            '%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d',
            '%d/%m/%y', '%d-%m-%y', '%Y/%m/%d',
            '%d.%m.%Y', '%d.%m.%y', '%Y%m%d'
        ]
        
        for fmt in formatos:
            try:
                return datetime.strptime(data_str, fmt).date()
            except:
                continue
        
        return None
    
    @staticmethod
    def normalizar_nome_coluna(nome_coluna: str) -> str:
        """Normaliza nomes de colunas para padrão do sistema"""
        if not isinstance(nome_coluna, str):
            nome_coluna = str(nome_coluna)
        
        mapeamento = {
            # Identificadores
            'num_cartao': 'numero_conta',
            'numcartao': 'numero_conta',
            'n_cartao': 'numero_conta',
            'cartao': 'numero_conta',
            'num_conta': 'numero_conta',
            'conta': 'numero_conta',
            'n_conta': 'numero_conta',
            'codigo': 'numero_conta',
            'cod': 'numero_conta',
            
            # Pessoa
            'nome': 'nome',
            'nome_beneficiario': 'nome',
            'beneficiario': 'nome',
            'beneficiário': 'nome',
            'nome_completo': 'nome',
            'nom': 'nome',
            
            # CPF/RG
            'cpf': 'cpf',
            'cpf_beneficiario': 'cpf',
            'cpf_do_beneficiario': 'cpf',
            'rg': 'rg',
            'registro_geral': 'rg',
            'identidade': 'rg',
            
            # Projeto
            'projeto': 'projeto',
            'programa': 'projeto',
            'cod_projeto': 'projeto',
            'codigo_projeto': 'projeto',
            
            # Valores
            'valor': 'valor',
            'valor_total': 'valor',
            'valor_pagto': 'valor',
            'valor_pagamento': 'valor',
            'valor_pago': 'valor',
            'valorpagto': 'valor',
            'vlr': 'valor',
            'valor_bruto': 'valor_bruto',
            'valor_liquido': 'valor_liquido',
            'valor_desconto': 'valor_desconto',
            
            # Datas
            'data_pagto': 'data_pagamento',
            'data_pagamento': 'data_pagamento',
            'data_pgto': 'data_pagamento',
            'datapagto': 'data_pagamento',
            'data': 'data_pagamento',
            'data_pag': 'data_pagamento',
            'dt_pagamento': 'data_pagamento',
            'data_credito': 'data_credito',
            
            # Bancário
            'agencia': 'agencia',
            'ag': 'agencia',
            'agência': 'agencia',
            'banco': 'banco',
            'instituicao': 'banco',
            
            # Dias
            'dias': 'dias',
            'dias_validos': 'dias',
            'dias_trabalhados': 'dias',
            'dias_a_pagar': 'dias',
            'dias_uteis': 'dias',
            
            # Valor por dia
            'valor_dia': 'valor_dia',
            'valordia': 'valor_dia',
            'valor_diario': 'valor_dia',
            
            # Outros
            'distrito': 'distrito',
            'bairro': 'bairro',
            'ordem': 'ordem',
            'sequencia': 'ordem',
            'status': 'status',
            'situacao': 'status',
            'observacao': 'observacao',
            'obs': 'observacao'
        }
        
        # Limpar nome da coluna
        nome_limpo = nome_coluna.strip().lower()
        nome_limpo = re.sub(r'[\s\-\.]+', '_', nome_limpo)
        nome_limpo = nome_limpo.replace('?', 'a')  # Corrige encoding
        nome_limpo = re.sub(r'[^\w_]', '', nome_limpo)
        
        # Aplicar mapeamento
        return mapeamento.get(nome_limpo, nome_limpo)

# ========== DETECÇÃO DE INCONSISTÊNCIAS ==========
class DetectorInconsistencias:
    """Classe para detectar inconsistências nos dados"""
    
    def __init__(self, conn):
        self.conn = conn
    
    def detectar_inconsistencias_planilha(self, df: pd.DataFrame, tipo_arquivo: str) -> List[Dict]:
        """Detecta inconsistências em uma planilha"""
        inconsistencias = []
        
        # Verificar colunas obrigatórias
        colunas_obrigatorias = self._obter_colunas_obrigatorias(tipo_arquivo)
        colunas_faltantes = [col for col in colunas_obrigatorias if col not in df.columns]
        
        if colunas_faltantes:
            inconsistencias.append({
                'tipo': 'COLUNAS_FALTANTES',
                'severidade': 'ALTA',
                'descricao': f'Colunas obrigatórias faltantes: {", ".join(colunas_faltantes)}',
                'quantidade': len(colunas_faltantes)
            })
        
        # Verificar registros duplicados
        if 'numero_conta' in df.columns:
            duplicados = df[df.duplicated(['numero_conta'], keep=False)]
            if not duplicados.empty:
                inconsistencias.append({
                    'tipo': 'REGISTROS_DUPLICADOS',
                    'severidade': 'ALTA',
                    'descricao': f'{len(duplicados["numero_conta"].unique())} números de conta duplicados',
                    'quantidade': len(duplicados)
                })
        
        # Verificar CPFs inválidos
        if 'cpf' in df.columns:
            cpfs_invalidos = df[df['cpf'].apply(lambda x: not self._validar_cpf(x))]
            if not cpfs_invalidos.empty:
                inconsistencias.append({
                    'tipo': 'CPFS_INVALIDOS',
                    'severidade': 'MEDIA',
                    'descricao': f'{len(cpfs_invalidos)} CPFs com formato inválido',
                    'quantidade': len(cpfs_invalidos)
                })
        
        # Verificar valores zerados ou negativos
        if 'valor' in df.columns:
            valores_invalidos = df[df['valor'] <= 0]
            if not valores_invalidos.empty:
                inconsistencias.append({
                    'tipo': 'VALORES_INVALIDOS',
                    'severidade': 'ALTA',
                    'descricao': f'{len(valores_invalidos)} registros com valor zerado ou negativo',
                    'quantidade': len(valores_invalidos)
                })
        
        # Verificar contas vazias
        if 'numero_conta' in df.columns:
            contas_vazias = df[df['numero_conta'].isna() | (df['numero_conta'].astype(str).str.strip() == '')]
            if not contas_vazias.empty:
                inconsistencias.append({
                    'tipo': 'CONTAS_VAZIAS',
                    'severidade': 'CRITICA',
                    'descricao': f'{len(contas_vazias)} registros sem número de conta',
                    'quantidade': len(contas_vazias)
                })
        
        # Verificar nomes vazios
        if 'nome' in df.columns:
            nomes_vazios = df[df['nome'].isna() | (df['nome'].astype(str).str.strip() == '')]
            if not nomes_vazios.empty:
                inconsistencias.append({
                    'tipo': 'NOMES_VAZIOS',
                    'severidade': 'ALTA',
                    'descricao': f'{len(nomes_vazios)} registros sem nome do beneficiário',
                    'quantidade': len(nomes_vazios)
                })
        
        return inconsistencias
    
    def _obter_colunas_obrigatorias(self, tipo_arquivo: str) -> List[str]:
        """Retorna colunas obrigatórias por tipo de arquivo"""
        obrigatorias = {
            'PAGAMENTOS': ['numero_conta', 'nome', 'valor'],
            'ABERTURA_CONTAS': ['numero_conta', 'cpf', 'nome', 'agencia', 'banco'],
            'GESTAO_DOCUMENTOS': ['cpf', 'nome', 'rg'],
            'LANCAMENTOS_BB': ['numero_conta', 'data_movimentacao', 'valor', 'descricao']
        }
        return obrigatorias.get(tipo_arquivo, [])
    
    def _validar_cpf(self, cpf: Any) -> bool:
        """Valida formato do CPF"""
        if pd.isna(cpf):
            return False
        
        cpf_str = str(cpf).strip()
        cpf_limpo = re.sub(r'\D', '', cpf_str)
        
        return len(cpf_limpo) == 11

# ========== PROCESSAMENTO DE ARQUIVOS ==========
class ProcessadorArquivos:
    """Classe para processamento de diferentes tipos de arquivos"""
    
    def __init__(self, conn):
        self.conn = conn
        self.normalizador = NormalizadorDados()
        self.detector = DetectorInconsistencias(conn)
    
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
        inconsistencias = self.detector.detectar_inconsistencias_planilha(df, tipo_arquivo)
        
        # Processar de acordo com o tipo
        if tipo_arquivo == 'PAGAMENTOS':
            sucesso, mensagem = self._processar_pagamentos(df, mes, ano, uploaded_file.name, hash_arquivo, usuario)
        elif tipo_arquivo == 'ABERTURA_CONTAS':
            sucesso, mensagem = self._processar_abertura_contas(df, uploaded_file.name, hash_arquivo, usuario)
        elif tipo_arquivo == 'GESTAO_DOCUMENTOS':
            sucesso, mensagem = self._processar_gestao_documentos(df, uploaded_file.name, hash_arquivo, usuario)
        elif tipo_arquivo == 'LANCAMENTOS_BB':
            sucesso, mensagem = self._processar_lancamentos_bb(df, uploaded_file.name, hash_arquivo, usuario)
        else:
            return False, f"Tipo de arquivo não suportado: {tipo_arquivo}", inconsistencias
        
        # Registrar processamento
        self._registrar_processamento(uploaded_file.name, tipo_arquivo, mes, ano, len(df), hash_arquivo, usuario, sucesso, mensagem)
        
        # Registrar inconsistências no banco
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
                # Determinar tipo de arquivo
                if uploaded_file.name.lower().endswith('.csv'):
                    # Tentar diferentes encodings
                    for encoding in ['latin-1', 'utf-8', 'cp1252', 'iso-8859-1']:
                        try:
                            df = pd.read_csv(tmp_path, sep=';', encoding=encoding, dtype=str, on_bad_lines='skip')
                            if not df.empty:
                                break
                        except:
                            continue
                    
                    # Se ainda vazio, tentar com separador automático
                    if df.empty or len(df.columns) == 1:
                        df = pd.read_csv(tmp_path, sep=None, engine='python', dtype=str, on_bad_lines='skip')
                
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
        
        # Detectar ano (procura por 4 dígitos)
        ano_match = re.search(r'(20\d{2})', nome_upper)
        ano = int(ano_match.group(1)) if ano_match else datetime.now().year
        
        return mes or datetime.now().month, ano
    
    def _arquivo_ja_processado(self, hash_arquivo: str) -> bool:
        """Verifica se arquivo já foi processado"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM arquivos_processados WHERE hash_arquivo = ?", (hash_arquivo,))
        return cursor.fetchone() is not None
    
    def _registrar_processamento(self, nome_arquivo: str, tipo_arquivo: str, mes: int, ano: int, 
                                total_registros: int, hash_arquivo: str, usuario: str, 
                                sucesso: bool, mensagem: str):
        """Registra processamento do arquivo"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO arquivos_processados 
                (nome_arquivo, tipo_arquivo, mes_referencia, ano_referencia, 
                 total_registros, hash_arquivo, usuario_processamento, status_processamento, erros_processamento)
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
                mensagem if not sucesso else None
            ))
            self.conn.commit()
        except Exception as e:
            print(f"Erro ao registrar processamento: {str(e)}")
    
    def _registrar_inconsistencias(self, inconsistencias: List[Dict], fonte_dados: str, arquivo_origem: str):
        """Registra inconsistências detectadas no banco"""
        try:
            cursor = self.conn.cursor()
            for inc in inconsistencias:
                cursor.execute('''
                    INSERT INTO inconsistencias 
                    (tipo_inconsistencia, severidade, descricao, quantidade, 
                     fonte_dados, data_deteccao, status)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 'PENDENTE')
                ''', (
                    inc['tipo'],
                    inc['severidade'],
                    inc['descricao'],
                    inc.get('quantidade', 1),
                    fonte_dados
                ))
            self.conn.commit()
        except Exception as e:
            print(f"Erro ao registrar inconsistências: {str(e)}")
    
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
                    cpf = self.normalizador.normalizar_cpf(row.get('cpf'))
                    valor = self.normalizador.normalizar_valor(row.get('valor'))
                    projeto = str(row.get('projeto', '')).strip()
                    data_pagamento = self.normalizador.normalizar_data(row.get('data_pagamento'))
                    
                    # Validar dados mínimos
                    if not numero_conta or valor <= 0:
                        continue
                    
                    # Buscar beneficiário pelo CPF ou criar se não existir
                    if cpf:
                        cursor.execute("SELECT id FROM beneficiarios WHERE cpf = ?", (cpf,))
                        if not cursor.fetchone():
                            cursor.execute('''
                                INSERT INTO beneficiarios (cpf, nome, nome_normalizado, fonte_cadastro)
                                VALUES (?, ?, ?, ?)
                            ''', (cpf, nome, nome, 'IMPORTACAO_PAGAMENTOS'))
                    
                    # Buscar conta ou criar se não existir
                    cursor.execute("SELECT id FROM contas_bancarias WHERE numero_conta = ?", (numero_conta,))
                    if not cursor.fetchone():
                        cursor.execute('''
                            INSERT INTO contas_bancarias (numero_conta, cpf_titular, banco, agencia, fonte_dados)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (
                            numero_conta,
                            cpf,
                            str(row.get('banco', '')).strip(),
                            str(row.get('agencia', '')).strip(),
                            'IMPORTACAO_PAGAMENTOS'
                        ))
                    
                    # Inserir pagamento
                    cursor.execute('''
                        INSERT OR REPLACE INTO pagamentos 
                        (numero_conta, cpf_beneficiario, codigo_projeto, mes_referencia, ano_referencia,
                         valor_bruto, valor_liquido, data_pagamento, arquivo_origem)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        numero_conta,
                        cpf,
                        projeto,
                        mes,
                        ano,
                        valor,
                        valor,
                        data_pagamento,
                        nome_arquivo
                    ))
                    
                    registros_processados += 1
                    valor_total += valor
                    
                except Exception as e:
                    # Continuar com próximo registro mesmo se um falhar
                    continue
            
            self.conn.commit()
            
            # Atualizar métricas
            self._atualizar_metricas_pagamentos(mes, ano)
            
            return True, f"Processados {registros_processados} pagamentos | Valor total: R$ {valor_total:,.2f}"
            
        except Exception as e:
            self.conn.rollback()
            return False, f"Erro ao processar pagamentos: {str(e)}"
    
    def _processar_abertura_contas(self, df: pd.DataFrame, nome_arquivo: str, 
                                  hash_arquivo: str, usuario: str) -> Tuple[bool, str]:
        """Processa arquivo de abertura de contas"""
        try:
            cursor = self.conn.cursor()
            registros_processados = 0
            
            for _, row in df.iterrows():
                try:
                    # Extrair e normalizar dados
                    numero_conta = str(row.get('numero_conta', '')).strip()
                    cpf = self.normalizador.normalizar_cpf(row.get('cpf'))
                    nome = self.normalizador.normalizar_nome(str(row.get('nome', '')))
                    agencia = str(row.get('agencia', '')).strip()
                    banco = str(row.get('banco', '')).strip()
                    
                    # Validar dados mínimos
                    if not numero_conta or not cpf:
                        continue
                    
                    # Inserir/atualizar beneficiário
                    cursor.execute('''
                        INSERT OR REPLACE INTO beneficiarios 
                        (cpf, nome, nome_normalizado, fonte_cadastro, status)
                        VALUES (?, ?, ?, ?, 'ATIVO')
                    ''', (cpf, nome, nome, 'ABERTURA_CONTAS'))
                    
                    # Inserir/atualizar conta
                    cursor.execute('''
                        INSERT OR REPLACE INTO contas_bancarias 
                        (numero_conta, cpf_titular, banco, agencia, status, fonte_dados)
                        VALUES (?, ?, ?, ?, 'ATIVA', ?)
                    ''', (numero_conta, cpf, banco, agencia, 'ABERTURA_CONTAS'))
                    
                    registros_processados += 1
                    
                except Exception as e:
                    continue
            
            self.conn.commit()
            return True, f"Processadas {registros_processados} aberturas de conta"
            
        except Exception as e:
            self.conn.rollback()
            return False, f"Erro ao processar abertura de contas: {str(e)}"
    
    def _processar_gestao_documentos(self, df: pd.DataFrame, nome_arquivo: str, 
                                    hash_arquivo: str, usuario: str) -> Tuple[bool, str]:
        """Processa arquivo de gestão de documentos"""
        try:
            cursor = self.conn.cursor()
            registros_processados = 0
            
            for _, row in df.iterrows():
                try:
                    cpf = self.normalizador.normalizar_cpf(row.get('cpf'))
                    nome = self.normalizador.normalizar_nome(str(row.get('nome', '')))
                    rg = str(row.get('rg', '')).strip()
                    
                    if not cpf:
                        continue
                    
                    # Atualizar beneficiário com dados da gestão de documentos
                    cursor.execute('''
                        UPDATE beneficiarios 
                        SET rg = COALESCE(rg, ?),
                            nome = COALESCE(nome, ?),
                            nome_normalizado = COALESCE(nome_normalizado, ?),
                            fonte_cadastro = COALESCE(fonte_cadastro, 'GESTAO_DOCUMENTOS')
                        WHERE cpf = ?
                    ''', (rg, nome, nome, cpf))
                    
                    # Se não existir, inserir
                    if cursor.rowcount == 0:
                        cursor.execute('''
                            INSERT INTO beneficiarios 
                            (cpf, nome, nome_normalizado, rg, fonte_cadastro, status)
                            VALUES (?, ?, ?, ?, 'GESTAO_DOCUMENTOS', 'ATIVO')
                        ''', (cpf, nome, nome, rg))
                    
                    registros_processados += 1
                    
                except Exception as e:
                    continue
            
            self.conn.commit()
            return True, f"Processados {registros_processados} documentos"
            
        except Exception as e:
            self.conn.rollback()
            return False, f"Erro ao processar gestão de documentos: {str(e)}"
    
    def _processar_lancamentos_bb(self, df: pd.DataFrame, nome_arquivo: str, 
                                 hash_arquivo: str, usuario: str) -> Tuple[bool, str]:
        """Processa arquivo de lançamentos do Banco do Brasil"""
        try:
            cursor = self.conn.cursor()
            registros_processados = 0
            
            for _, row in df.iterrows():
                try:
                    numero_conta = str(row.get('numero_conta', '')).strip()
                    data_mov = self.normalizador.normalizar_data(row.get('data_movimentacao'))
                    valor = self.normalizador.normalizar_valor(row.get('valor'))
                    descricao = str(row.get('descricao', '')).strip()
                    
                    if not numero_conta or not data_mov or valor == 0:
                        continue
                    
                    # Buscar CPF associado à conta
                    cursor.execute("SELECT cpf_titular FROM contas_bancarias WHERE numero_conta = ?", (numero_conta,))
                    resultado = cursor.fetchone()
                    cpf = resultado[0] if resultado else None
                    
                    # Inserir lançamento
                    cursor.execute('''
                        INSERT INTO lancamentos_bb 
                        (numero_conta, cpf_beneficiario, data_movimentacao, 
                         valor, descricao, arquivo_origem)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (numero_conta, cpf, data_mov, valor, descricao, nome_arquivo))
                    
                    registros_processados += 1
                    
                except Exception as e:
                    continue
            
            self.conn.commit()
            
            # Tentar conciliar automaticamente
            self._conciliar_lancamentos_automaticamente()
            
            return True, f"Processados {registros_processados} lançamentos bancários"
            
        except Exception as e:
            self.conn.rollback()
            return False, f"Erro ao processar lançamentos BB: {str(e)}"
    
    def _atualizar_metricas_pagamentos(self, mes: int, ano: int):
        """Atualiza métricas de pagamentos"""
        try:
            cursor = self.conn.cursor()
            
            # Calcular totais
            cursor.execute('''
                SELECT 
                    COUNT(DISTINCT cpf_beneficiario) as beneficiarios,
                    COUNT(DISTINCT numero_conta) as contas,
                    COUNT(*) as pagamentos,
                    SUM(valor_liquido) as valor_total,
                    COUNT(DISTINCT codigo_projeto) as projetos
                FROM pagamentos 
                WHERE mes_referencia = ? AND ano_referencia = ? 
                AND status_pagamento = 'PAGO'
            ''', (mes, ano))
            
            resultado = cursor.fetchone()
            if resultado and resultado[0]:
                # Inserir métricas
                metricas = [
                    ('BENEFICIARIOS_ATIVOS', mes, ano, resultado[0]),
                    ('CONTAS_ATIVAS', mes, ano, resultado[1]),
                    ('TOTAL_PAGAMENTOS', mes, ano, resultado[2]),
                    ('VALOR_TOTAL_PAGO', mes, ano, resultado[3]),
                    ('PROJETOS_ATIVOS', mes, ano, resultado[4])
                ]
                
                for tipo, m, a, valor in metricas:
                    cursor.execute('''
                        INSERT OR REPLACE INTO metricas 
                        (tipo_metrica, mes_referencia, ano_referencia, valor)
                        VALUES (?, ?, ?, ?)
                    ''', (tipo, m, a, valor))
                
                self.conn.commit()
                
        except Exception as e:
            print(f"Erro ao atualizar métricas: {str(e)}")
    
    def _conciliar_lancamentos_automaticamente(self):
        """Tenta conciliar automaticamente lançamentos com pagamentos"""
        try:
            cursor = self.conn.cursor()
            
            # Buscar lançamentos não conciliados
            cursor.execute('''
                SELECT l.id, l.numero_conta, l.valor, l.data_movimentacao
                FROM lancamentos_bb l
                WHERE l.status_conciliacao = 'NAO_CONCILIADO'
                AND l.data_movimentacao >= DATE('now', '-90 days')
            ''')
            
            lancamentos = cursor.fetchall()
            
            for lancamento in lancamentos:
                lanc_id, conta, valor, data_mov = lancamento
                
                # Buscar pagamento correspondente
                cursor.execute('''
                    SELECT p.id, p.valor_liquido, p.data_pagamento
                    FROM pagamentos p
                    WHERE p.numero_conta = ?
                    AND p.status_pagamento = 'PAGO'
                    AND ABS(p.valor_liquido - ?) < 0.01  # Tolerância de 1 centavo
                    AND p.data_pagamento <= DATE(?, '+7 days')
                    AND p.data_pagamento >= DATE(?, '-7 days')
                    AND NOT EXISTS (
                        SELECT 1 FROM lancamentos_bb 
                        WHERE id_pagamento_conciliado = p.id
                    )
                    LIMIT 1
                ''', (conta, valor, data_mov, data_mov))
                
                pagamento = cursor.fetchone()
                
                if pagamento:
                    pag_id, pag_valor, pag_data = pagamento
                    
                    # Conciliar
                    cursor.execute('''
                        UPDATE lancamentos_bb 
                        SET status_conciliacao = 'CONCILIADO',
                            id_pagamento_conciliado = ?
                        WHERE id = ?
                    ''', (pag_id, lanc_id))
                    
                    # Marcar pagamento como conciliado
                    cursor.execute('''
                        UPDATE pagamentos 
                        SET status_pagamento = 'CONCILIADO'
                        WHERE id = ?
                    ''', (pag_id,))
            
            self.conn.commit()
            
        except Exception as e:
            print(f"Erro na conciliação automática: {str(e)}")

# ========== ANÁLISE E RELATÓRIOS ==========
class AnalisadorDados:
    """Classe para análise de dados e geração de relatórios"""
    
    def __init__(self, conn):
        self.conn = conn
    
    def obter_resumo_geral(self) -> Dict:
        """Obtém resumo geral do sistema"""
        cursor = self.conn.cursor()
        
        resumo = {}
        
        # Totais gerais
        cursor.execute("SELECT COUNT(*) FROM beneficiarios WHERE status = 'ATIVO'")
        resumo['beneficiarios_ativos'] = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM contas_bancarias WHERE status = 'ATIVA'")
        resumo['contas_ativas'] = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM projetos WHERE status = 'ATIVO'")
        resumo['projetos_ativos'] = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT SUM(valor_liquido) FROM pagamentos WHERE status_pagamento = 'PAGO'")
        resumo['valor_total_pago'] = cursor.fetchone()[0] or 0
        
        # Último mês processado
        cursor.execute('''
            SELECT MAX(ano_referencia), MAX(mes_referencia)
            FROM pagamentos 
            WHERE status_pagamento = 'PAGO'
        ''')
        ultimo_mes = cursor.fetchone()
        if ultimo_mes and ultimo_mes[0]:
            resumo['ultimo_mes_processado'] = f"{ultimo_mes[1]:02d}/{ultimo_mes[0]}"
        else:
            resumo['ultimo_mes_processado'] = "Nenhum"
        
        # Inconsistências pendentes
        cursor.execute("SELECT COUNT(*) FROM inconsistencias WHERE status = 'PENDENTE'")
        resumo['inconsistencias_pendentes'] = cursor.fetchone()[0] or 0
        
        # Arquivos processados
        cursor.execute("SELECT COUNT(*) FROM arquivos_processados WHERE status_processamento = 'SUCESSO'")
        resumo['arquivos_processados'] = cursor.fetchone()[0] or 0
        
        # Conciliados vs não conciliados
        cursor.execute("SELECT COUNT(*) FROM lancamentos_bb WHERE status_conciliacao = 'CONCILIADO'")
        resumo['lancamentos_conciliados'] = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM lancamentos_bb WHERE status_conciliacao = 'NAO_CONCILIADO'")
        resumo['lancamentos_nao_conciliados'] = cursor.fetchone()[0] or 0
        
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
                query = 'SELECT * FROM view_resumo_mensal ORDER BY ano_referencia DESC, mes_referencia DESC LIMIT 12'
                params = ()
            
            return pd.read_sql_query(query, self.conn, params=params)
        except:
            return pd.DataFrame()
    
    def obter_inconsistencias_pendentes(self) -> pd.DataFrame:
        """Obtém inconsistências pendentes"""
        try:
            return pd.read_sql_query('SELECT * FROM view_inconsistencias_pendentes', self.conn)
        except:
            return pd.DataFrame()
    
    def obter_conciliacao_pagamentos(self) -> pd.DataFrame:
        """Obtém status da conciliação de pagamentos"""
        try:
            return pd.read_sql_query('SELECT * FROM view_conciliacao_pagamentos', self.conn)
        except:
            return pd.DataFrame()
    
    def obter_beneficiarios_problema(self, limite: int = 50) -> pd.DataFrame:
        """Identifica beneficiários com problemas"""
        try:
            query = '''
                SELECT 
                    b.cpf,
                    b.nome,
                    COUNT(DISTINCT c.numero_conta) as num_contas,
                    COUNT(DISTINCT p.id) as num_pagamentos,
                    COUNT(DISTINCT CASE WHEN i.status = 'PENDENTE' THEN i.id END) as num_inconsistencias,
                    MAX(p.data_pagamento) as ultimo_pagamento
                FROM beneficiarios b
                LEFT JOIN contas_bancarias c ON b.cpf = c.cpf_titular
                LEFT JOIN pagamentos p ON b.cpf = p.cpf_beneficiario
                LEFT JOIN inconsistencias i ON b.cpf = i.cpf_envolvido
                WHERE b.status = 'ATIVO'
                GROUP BY b.cpf, b.nome
                HAVING num_inconsistencias > 0 OR num_contas > 1
                ORDER BY num_inconsistencias DESC, num_contas DESC
                LIMIT ?
            '''
            return pd.read_sql_query(query, self.conn, params=(limite,))
        except:
            return pd.DataFrame()
    
    def obter_pagamentos_por_projeto(self, mes: int = None, ano: int = None) -> pd.DataFrame:
        """Obtém pagamentos agrupados por projeto"""
        try:
            if mes and ano:
                query = '''
                    SELECT 
                        codigo_projeto as projeto,
                        COUNT(*) as quantidade_pagamentos,
                        SUM(valor_liquido) as valor_total,
                        AVG(valor_liquido) as valor_medio,
                        COUNT(DISTINCT cpf_beneficiario) as beneficiarios_unicos
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
                        codigo_projeto as projeto,
                        COUNT(*) as quantidade_pagamentos,
                        SUM(valor_liquido) as valor_total,
                        AVG(valor_liquido) as valor_medio,
                        COUNT(DISTINCT cpf_beneficiario) as beneficiarios_unicos
                    FROM pagamentos
                    WHERE status_pagamento = 'PAGO'
                    GROUP BY codigo_projeto
                    ORDER BY valor_total DESC
                '''
                params = ()
            
            return pd.read_sql_query(query, self.conn, params=params)
        except:
            return pd.DataFrame()

# ========== INTERFACE STREAMLIT ==========
def mostrar_dashboard(conn):
    """Mostra dashboard principal"""
    st.title("💰 Sistema POT - Gestão Completa de Benefícios")
    st.markdown("---")
    
    analisador = AnalisadorDados(conn)
    resumo = analisador.obter_resumo_geral()
    
    # Métricas principais
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Beneficiários Ativos", f"{resumo['beneficiarios_ativos']:,}")
        st.caption(f"Contas Ativas: {resumo['contas_ativas']:,}")
    
    with col2:
        st.metric("Valor Total Pago", f"R$ {resumo['valor_total_pago']:,.2f}")
        st.caption(f"Projetos Ativos: {resumo['projetos_ativos']:,}")
    
    with col3:
        st.metric("Último Mês", resumo['ultimo_mes_processado'])
        st.caption(f"Arquivos: {resumo['arquivos_processados']:,}")
    
    with col4:
        cor = "red" if resumo['inconsistencias_pendentes'] > 0 else "green"
        st.metric("Inconsistências Pendentes", f"{resumo['inconsistencias_pendentes']:,}", delta_color="off")
        st.caption(f"Conciliados: {resumo['lancamentos_conciliados']:,}")
    
    st.markdown("---")
    
    # Abas de análise
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Resumo Mensal", "⚠️ Inconsistências", "🔍 Conciliação", "👤 Beneficiários"])
    
    with tab1:
        st.subheader("Resumo Mensal de Pagamentos")
        
        df_resumo = analisador.obter_resumo_mensal()
        if not df_resumo.empty:
            # Gráfico de evolução
            df_resumo['periodo'] = df_resumo['mes_referencia'].astype(str) + '/' + df_resumo['ano_referencia'].astype(str)
            
            fig = px.line(
                df_resumo.sort_values(['ano_referencia', 'mes_referencia']),
                x='periodo',
                y='valor_total_pago',
                title='Evolução do Valor Total Pago',
                markers=True
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Tabela detalhada
            st.dataframe(
                df_resumo[['mes_referencia', 'ano_referencia', 'beneficiarios_ativos', 
                          'contas_ativas', 'valor_total_pago', 'valor_medio_pagamento']],
                use_container_width=True,
                column_config={
                    'valor_total_pago': st.column_config.NumberColumn(
                        'Valor Total (R$)',
                        format="R$ %.2f"
                    ),
                    'valor_medio_pagamento': st.column_config.NumberColumn(
                        'Média (R$)',
                        format="R$ %.2f"
                    )
                }
            )
        else:
            st.info("Nenhum dado de pagamento disponível.")
    
    with tab2:
        st.subheader("Inconsistências Detectadas")
        
        df_inconsistencias = analisador.obter_inconsistencias_pendentes()
        if not df_inconsistencias.empty:
            # Gráfico por severidade
            fig = px.bar(
                df_inconsistencias,
                x='tipo_inconsistencia',
                y='quantidade',
                color='severidade',
                title='Inconsistências por Tipo e Severidade'
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Tabela detalhada
            st.dataframe(df_inconsistencias, use_container_width=True)
            
            # Ações para correção
            st.subheader("Ações Recomendadas")
            
            for _, row in df_inconsistencias.iterrows():
                acoes = {
                    'COLUNAS_FALTANTES': 'Verificar layout do arquivo e importar novamente',
                    'REGISTROS_DUPLICADOS': 'Verificar duplicidade nos registros',
                    'CPFS_INVALIDOS': 'Corrigir formatação dos CPFs',
                    'VALORES_INVALIDOS': 'Verificar valores zerados ou negativos',
                    'CONTAS_VAZIAS': 'Completar número das contas',
                    'NOMES_VAZIOS': 'Completar nomes dos beneficiários'
                }
                
                acao = acoes.get(row['tipo_inconsistencia'], 'Verificar manualmente')
                st.warning(f"**{row['tipo_inconsistencia']}** ({row['quantidade']} ocorrências): {acao}")
        else:
            st.success("✅ Nenhuma inconsistência pendente!")
    
    with tab3:
        st.subheader("Conciliação Bancária")
        
        df_conciliacao = analisador.obter_conciliacao_pagamentos()
        if not df_conciliacao.empty:
            # Status da conciliação
            col_conc1, col_conc2, col_conc3 = st.columns(3)
            
            with col_conc1:
                total_pag = df_conciliacao['total_pagamentos'].sum()
                st.metric("Total Pagamentos", f"{total_pag:,}")
            
            with col_conc2:
                conciliados = df_conciliacao['lancamentos_conciliados'].sum()
                st.metric("Conciliados", f"{conciliados:,}")
            
            with col_conc3:
                discrepancia = df_conciliacao['discrepancia_quantidade'].sum()
                cor = "green" if discrepancia == 0 else "red"
                st.metric("Discrepância", f"{discrepancia:,}", delta_color="off")
            
            # Tabela de conciliação
            st.dataframe(
                df_conciliacao,
                use_container_width=True,
                column_config={
                    'valor_total_pagamentos': st.column_config.NumberColumn(
                        'Valor Pagamentos (R$)',
                        format="R$ %.2f"
                    ),
                    'valor_conciliado': st.column_config.NumberColumn(
                        'Valor Conciliado (R$)',
                        format="R$ %.2f"
                    ),
                    'discrepancia_valor': st.column_config.NumberColumn(
                        'Diferença (R$)',
                        format="R$ %.2f"
                    )
                }
            )
        else:
            st.info("Nenhuma informação de conciliação disponível.")
    
    with tab4:
        st.subheader("Beneficiários com Potenciais Problemas")
        
        df_problemas = analisador.obter_beneficiarios_problema(20)
        if not df_problemas.empty:
            st.dataframe(
                df_problemas,
                use_container_width=True,
                column_config={
                    'cpf': 'CPF',
                    'nome': 'Nome',
                    'num_contas': 'Contas',
                    'num_pagamentos': 'Pagamentos',
                    'num_inconsistencias': 'Inconsistências',
                    'ultimo_pagamento': st.column_config.DateColumn('Último Pagamento')
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
            st.info("Nenhum beneficiário com problemas identificados.")

def mostrar_importacao(conn):
    """Interface de importação de arquivos"""
    st.header("📤 Importar Arquivos")
    
    # Seção de instruções
    with st.expander("ℹ️ Instruções de Importação", expanded=False):
        st.markdown("""
        ### Tipos de Arquivos Suportados:
        
        **1. PAGAMENTOS** (obrigatório)
        - Arquivos de pagamento realizados
        - Colunas mínimas: `numero_conta`, `nome`, `valor`
        - Colunas opcionais: `cpf`, `projeto`, `data_pagamento`, `agencia`
        
        **2. ABERTURA DE CONTAS** (recomendado)
        - Cadastro de novas contas bancárias
        - Colunas mínimas: `numero_conta`, `cpf`, `nome`, `agencia`, `banco`
        - Usado para cruzamento com pagamentos
        
        **3. GESTÃO DE DOCUMENTOS** (recomendado)
        - Dados complementares dos beneficiários
        - Colunas mínimas: `cpf`, `nome`, `rg`
        - Usado para completar cadastros
        
        **4. LANÇAMENTOS BB** (opcional)
        - Extratos bancários do Banco do Brasil
        - Colunas mínimas: `numero_conta`, `data_movimentacao`, `valor`, `descricao`
        - Usado para conciliação bancária
        
        ### Formato dos Arquivos:
        - **CSV** com separador ponto-e-vírgula (`;`)
        - **Excel** (.xls, .xlsx)
        - O sistema detecta automaticamente o mês/ano pelo nome do arquivo
        """)
    
    # Seção de upload
    st.subheader("Selecionar Arquivo para Importação")
    
    col_tipo, col_mes, col_ano = st.columns(3)
    
    with col_tipo:
        tipo_arquivo = st.selectbox(
            "Tipo de Arquivo",
            ["PAGAMENTOS", "ABERTURA_CONTAS", "GESTAO_DOCUMENTOS", "LANCAMENTOS_BB"],
            index=0
        )
    
    with col_mes:
        meses = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
        mes_selecionado = st.selectbox("Mês de Referência", meses)
        mes_num = meses.index(mes_selecionado) if mes_selecionado else None
    
    with col_ano:
        ano_atual = datetime.now().year
        anos = [""] + list(range(ano_atual, ano_atual - 5, -1))
        ano_selecionado = st.selectbox("Ano de Referência", anos)
        ano_num = int(ano_selecionado) if ano_selecionado else None
    
    # Upload do arquivo
    uploaded_file = st.file_uploader(
        f"Selecione o arquivo de {tipo_arquivo.replace('_', ' ').lower()}",
        type=['csv', 'xls', 'xlsx'],
        key=f"upload_{tipo_arquivo}"
    )
    
    if uploaded_file:
        st.info(f"📄 **Arquivo selecionado:** {uploaded_file.name}")
        st.info(f"📋 **Tipo:** {tipo_arquivo.replace('_', ' ').title()}")
        
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
                        emoji = "🔴" if inc['severidade'] == 'CRITICA' else "🟡" if inc['severidade'] == 'ALTA' else "🔵"
                        st.markdown(f"{emoji} **{inc['tipo']}** ({inc['severidade']}): {inc['descricao']}")
                
                # Mostrar prévia dos cálculos atualizados
                analisador = AnalisadorDados(conn)
                resumo = analisador.obter_resumo_geral()
                
                st.balloons()
                st.rerun()
            else:
                st.error(f"❌ {mensagem}")

def mostrar_consulta_beneficiarios(conn):
    """Interface de consulta detalhada de beneficiários"""
    st.header("🔍 Consulta Detalhada de Beneficiários")
    
    col_filtro1, col_filtro2 = st.columns(2)
    
    with col_filtro1:
        cpf_consulta = st.text_input("CPF (somente números)", placeholder="00000000000")
    
    with col_filtro2:
        nome_consulta = st.text_input("Nome (parcial)", placeholder="Digite parte do nome")
    
    # Botões de ação
    col_btn1, col_btn2, col_btn3 = st.columns(3)
    
    with col_btn1:
        buscar = st.button("🔍 Buscar", use_container_width=True)
    
    with col_btn2:
        limpar = st.button("🔄 Limpar Filtros", use_container_width=True)
    
    with col_btn3:
        exportar = st.button("📥 Exportar Resultados", use_container_width=True)
    
    if limpar:
        st.rerun()
    
    if buscar and (cpf_consulta or nome_consulta):
        cursor = conn.cursor()
        
        # Construir query dinâmica
        query = '''
            SELECT 
                b.cpf,
                b.nome,
                b.rg,
                b.status,
                b.data_cadastro,
                COUNT(DISTINCT c.numero_conta) as num_contas,
                COUNT(DISTINCT p.id) as num_pagamentos,
                SUM(p.valor_liquido) as total_recebido,
                MAX(p.data_pagamento) as ultimo_pagamento
            FROM beneficiarios b
            LEFT JOIN contas_bancarias c ON b.cpf = c.cpf_titular
            LEFT JOIN pagamentos p ON b.cpf = p.cpf_beneficiario
            WHERE 1=1
        '''
        
        params = []
        
        if cpf_consulta:
            query += ' AND b.cpf LIKE ?'
            params.append(f'%{cpf_consulta}%')
        
        if nome_consulta:
            query += ' AND b.nome_normalizado LIKE ?'
            params.append(f'%{NormalizadorDados.normalizar_nome(nome_consulta)}%')
        
        query += '''
            GROUP BY b.cpf, b.nome, b.rg, b.status, b.data_cadastro
            ORDER BY b.nome
            LIMIT 100
        '''
        
        cursor.execute(query, params)
        resultados = cursor.fetchall()
        
        if resultados:
            colunas = ['CPF', 'Nome', 'RG', 'Status', 'Data Cadastro', 
                      'Contas', 'Pagamentos', 'Total Recebido', 'Último Pagamento']
            
            df_resultados = pd.DataFrame(resultados, columns=colunas)
            
            # Mostrar resultados
            st.subheader(f"Resultados: {len(df_resultados)} beneficiários encontrados")
            
            # Métricas do resultado
            col_res1, col_res2, col_res3 = st.columns(3)
            with col_res1:
                st.metric("Total Recebido", f"R$ {df_resultados['Total Recebido'].sum():,.2f}")
            with col_res2:
                st.metric("Média por Beneficiário", f"R$ {df_resultados['Total Recebido'].mean():,.2f}")
            with col_res3:
                st.metric("Pagamentos Totais", f"{df_resultados['Pagamentos'].sum():,}")
            
            # Tabela de resultados
            st.dataframe(
                df_resultados,
                use_container_width=True,
                column_config={
                    'Total Recebido': st.column_config.NumberColumn(
                        'Total Recebido (R$)',
                        format="R$ %.2f"
                    ),
                    'Data Cadastro': st.column_config.DateColumn('Data Cadastro'),
                    'Último Pagamento': st.column_config.DateColumn('Último Pagamento')
                }
            )
            
            # Detalhes de um beneficiário específico
            if len(df_resultados) == 1:
                cpf_detalhe = df_resultados.iloc[0]['CPF']
                st.subheader(f"Detalhes do Beneficiário: {df_resultados.iloc[0]['Nome']}")
                
                # Histórico de pagamentos
                cursor.execute('''
                    SELECT 
                        mes_referencia || '/' || ano_referencia as periodo,
                        valor_liquido,
                        data_pagamento,
                        codigo_projeto,
                        status_pagamento
                    FROM pagamentos
                    WHERE cpf_beneficiario = ?
                    ORDER BY ano_referencia DESC, mes_referencia DESC
                ''', (cpf_detalhe,))
                
                historico = cursor.fetchall()
                if historico:
                    df_historico = pd.DataFrame(historico, 
                                               columns=['Período', 'Valor', 'Data Pagamento', 'Projeto', 'Status'])
                    
                    st.dataframe(
                        df_historico,
                        use_container_width=True,
                        column_config={
                            'Valor': st.column_config.NumberColumn(
                                'Valor (R$)',
                                format="R$ %.2f"
                            ),
                            'Data Pagamento': st.column_config.DateColumn('Data Pagamento')
                        }
                    )
                    
                    # Gráfico do histórico
                    fig = px.line(
                        df_historico.sort_values('Período'),
                        x='Período',
                        y='Valor',
                        title='Histórico de Pagamentos',
                        markers=True
                    )
                    st.plotly_chart(fig, use_container_width=True)
                
                # Contas associadas
                cursor.execute('''
                    SELECT numero_conta, banco, agencia, status, data_abertura
                    FROM contas_bancarias
                    WHERE cpf_titular = ?
                    ORDER BY data_abertura DESC
                ''', (cpf_detalhe,))
                
                contas = cursor.fetchall()
                if contas:
                    df_contas = pd.DataFrame(contas, 
                                            columns=['Conta', 'Banco', 'Agência', 'Status', 'Data Abertura'])
                    st.dataframe(df_contas, use_container_width=True)
        else:
            st.info("Nenhum beneficiário encontrado com os critérios informados.")

def mostrar_relatorios(conn):
    """Interface de geração de relatórios"""
    st.header("📊 Relatórios e Análises")
    
    analisador = AnalisadorDados(conn)
    
    tab_rel1, tab_rel2, tab_rel3 = st.tabs(["📈 Análise por Período", "📋 Inconsistências", "💰 Conciliação"])
    
    with tab_rel1:
        st.subheader("Análise por Período")
        
        col_per1, col_per2 = st.columns(2)
        with col_per1:
            meses_opcoes = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                           "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
            mes_rel = st.selectbox("Mês", meses_opcoes)
            mes_num = meses_opcoes.index(mes_rel) if mes_rel else None
        
        with col_per2:
            ano_atual = datetime.now().year
            anos_opcoes = [""] + list(range(ano_atual, ano_atual - 5, -1))
            ano_rel = st.selectbox("Ano", anos_opcoes)
            ano_num = int(ano_rel) if ano_rel else None
        
        if st.button("Gerar Relatório do Período", use_container_width=True) and mes_num and ano_num:
            # Resumo do período
            df_resumo = analisador.obter_resumo_mensal(mes_num, ano_num)
            
            if not df_resumo.empty:
                st.success(f"📊 Relatório de {mes_rel}/{ano_num}")
                
                # Métricas
                resumo_periodo = df_resumo.iloc[0]
                col_met1, col_met2, col_met3, col_met4 = st.columns(4)
                
                with col_met1:
                    st.metric("Beneficiários", f"{resumo_periodo['beneficiarios_ativos']:,}")
                with col_met2:
                    st.metric("Contas Ativas", f"{resumo_periodo['contas_ativas']:,}")
                with col_met3:
                    st.metric("Valor Total", f"R$ {resumo_periodo['valor_total_pago']:,.2f}")
                with col_met4:
                    st.metric("Valor Médio", f"R$ {resumo_periodo['valor_medio_pagamento']:,.2f}")
                
                # Pagamentos por projeto
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
                    
                    st.dataframe(
                        df_projetos,
                        use_container_width=True,
                        column_config={
                            'valor_total': st.column_config.NumberColumn(
                                'Valor Total (R$)',
                                format="R$ %.2f"
                            ),
                            'valor_medio': st.column_config.NumberColumn(
                                'Valor Médio (R$)',
                                format="R$ %.2f"
                            )
                        }
                    )
            else:
                st.warning(f"Nenhum dado encontrado para {mes_rel}/{ano_num}")
    
    with tab_rel2:
        st.subheader("Relatório de Inconsistências")
        
        df_inconsistencias = analisador.obter_inconsistencias_pendentes()
        
        if not df_inconsistencias.empty:
            # Resumo por tipo
            st.dataframe(df_inconsistencias, use_container_width=True)
            
            # Botão para exportar
            if st.button("Exportar Lista Completa", use_container_width=True):
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT 
                        tipo_inconsistencia,
                        severidade,
                        descricao,
                        cpf_envolvido,
                        numero_conta_envolvido,
                        data_deteccao,
                        status
                    FROM inconsistencias
                    WHERE status = 'PENDENTE'
                    ORDER BY 
                        CASE severidade 
                            WHEN 'CRITICA' THEN 1
                            WHEN 'ALTA' THEN 2
                            WHEN 'MEDIA' THEN 3
                            WHEN 'BAIXA' THEN 4
                            ELSE 5
                        END,
                        data_deteccao DESC
                ''')
                
                detalhes = cursor.fetchall()
                df_detalhes = pd.DataFrame(detalhes, 
                                          columns=['Tipo', 'Severidade', 'Descrição', 'CPF', 
                                                  'Conta', 'Data Detecção', 'Status'])
                
                # Converter para CSV
                csv = df_detalhes.to_csv(index=False, sep=';', encoding='latin-1')
                
                st.download_button(
                    label="📥 Download CSV",
                    data=csv,
                    file_name=f"inconsistencias_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        else:
            st.success("✅ Nenhuma inconsistência pendente para relatar!")
    
    with tab_rel3:
        st.subheader("Relatório de Conciliação")
        
        df_conciliacao = analisador.obter_conciliacao_pagamentos()
        
        if not df_conciliacao.empty:
            # Status geral
            total_discrepancia = df_conciliacao['discrepancia_valor'].sum()
            
            if total_discrepancia == 0:
                st.success("✅ Conciliação perfeita! Todos os valores estão conciliados.")
            else:
                st.error(f"⚠️ Existe uma discrepância total de R$ {total_discrepancia:,.2f}")
            
            # Tabela detalhada
            st.dataframe(
                df_conciliacao,
                use_container_width=True,
                column_config={
                    'valor_total_pagamentos': st.column_config.NumberColumn(
                        'Pagamentos (R$)',
                        format="R$ %.2f"
                    ),
                    'valor_conciliado': st.column_config.NumberColumn(
                        'Conciliado (R$)',
                        format="R$ %.2f"
                    ),
                    'discrepancia_valor': st.column_config.NumberColumn(
                        'Diferença (R$)',
                        format="R$ %.2f"
                    )
                }
            )
            
            # Detalhes dos não conciliados
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    l.numero_conta,
                    l.data_movimentacao,
                    l.valor,
                    l.descricao,
                    l.data_importacao
                FROM lancamentos_bb l
                WHERE l.status_conciliacao = 'NAO_CONCILIADO'
                ORDER BY l.data_movimentacao DESC
                LIMIT 50
            ''')
            
            nao_conciliados = cursor.fetchall()
            if nao_conciliados:
                st.subheader("Lançamentos Não Conciliados (Últimos 50)")
                
                df_nao_conc = pd.DataFrame(nao_conciliados, 
                                          columns=['Conta', 'Data', 'Valor', 'Descrição', 'Importação'])
                
                st.dataframe(
                    df_nao_conc,
                    use_container_width=True,
                    column_config={
                        'Valor': st.column_config.NumberColumn(
                            'Valor (R$)',
                            format="R$ %.2f"
                        ),
                        'Data': st.column_config.DateColumn('Data Movimentação'),
                        'Importação': st.column_config.DateColumn('Data Importação')
                    }
                )

def mostrar_configuracoes(conn):
    """Interface de configurações do sistema"""
    st.header("⚙️ Configurações do Sistema")
    
    tab_conf1, tab_conf2, tab_conf3 = st.tabs(["Banco de Dados", "Manutenção", "Backup"])
    
    with tab_conf1:
        st.subheader("Status do Banco de Dados")
        
        cursor = conn.cursor()
        
        # Tamanho do banco
        if os.path.exists('pot_beneficios_completo.db'):
            tamanho_mb = os.path.getsize('pot_beneficios_completo.db') / 1024 / 1024
            st.info(f"📊 Tamanho do banco: {tamanho_mb:.2f} MB")
        
        # Contagem de registros
        tabelas = ['beneficiarios', 'contas_bancarias', 'pagamentos', 'inconsistencias', 'arquivos_processados']
        
        for tabela in tabelas:
            cursor.execute(f"SELECT COUNT(*) FROM {tabela}")
            count = cursor.fetchone()[0]
            st.metric(f"Registros em {tabela.replace('_', ' ').title()}", f"{count:,}")
    
    with tab_conf2:
        st.subheader("Manutenção do Sistema")
        
        col_man1, col_man2 = st.columns(2)
        
        with col_man1:
            st.warning("⚠️ Ações Irreversíveis")
            
            if st.button("🗑️ Limpar Dados de Teste", use_container_width=True):
                confirmacao = st.checkbox("Confirmar limpeza de dados de teste")
                if confirmacao:
                    try:
                        # Manter apenas dados dos últimos 6 meses
                        data_limite = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
                        
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM pagamentos WHERE data_pagamento < ?", (data_limite,))
                        cursor.execute("DELETE FROM lancamentos_bb WHERE data_movimentacao < ?", (data_limite,))
                        cursor.execute("DELETE FROM arquivos_processados WHERE data_processamento < ?", (data_limite,))
                        
                        conn.commit()
                        st.success("✅ Dados antigos removidos com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erro: {str(e)}")
        
        with col_man2:
            st.info("🔄 Otimização")
            
            if st.button("⚡ Otimizar Banco de Dados", use_container_width=True):
                try:
                    cursor = conn.cursor()
                    cursor.execute("VACUUM")
                    cursor.execute("ANALYZE")
                    conn.commit()
                    st.success("✅ Banco de dados otimizado com sucesso!")
                except Exception as e:
                    st.error(f"❌ Erro: {str(e)}")
    
    with tab_conf3:
        st.subheader("Backup e Restauração")
        
        # Backup
        if st.button("💾 Criar Backup Completo", use_container_width=True):
            try:
                # Exportar tudo para JSON
                backup_data = {}
                cursor = conn.cursor()
                
                for tabela in ['beneficiarios', 'contas_bancarias', 'pagamentos', 
                              'lancamentos_bb', 'inconsistencias', 'arquivos_processados']:
                    cursor.execute(f"SELECT * FROM {tabela}")
                    colunas = [desc[0] for desc in cursor.description]
                    dados = cursor.fetchall()
                    
                    backup_data[tabela] = {
                        'colunas': colunas,
                        'dados': dados,
                        'total': len(dados)
                    }
                
                # Adicionar metadados
                backup_data['metadata'] = {
                    'data_backup': datetime.now().isoformat(),
                    'sistema': 'POT SMDET',
                    'versao': '2.0'
                }
                
                # Converter para JSON
                backup_json = json.dumps(backup_data, ensure_ascii=False, indent=2, default=str)
                
                st.download_button(
                    label="📥 Download Backup",
                    data=backup_json,
                    file_name=f"backup_pot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json",
                    use_container_width=True
                )
                
            except Exception as e:
                st.error(f"❌ Erro ao criar backup: {str(e)}")

# ========== FUNÇÃO PRINCIPAL ==========
def main():
    # Inicializar banco de dados
    conn = init_database()
    
    if not conn:
        st.error("❌ Não foi possível inicializar o banco de dados. Verifique as permissões.")
        return
    
    # Sidebar com menu
    st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/Prefeitura_de_S%C3%A3o_Paulo_logo.png/320px-Prefeitura_de_S%C3%A3o_Paulo_logo.png", 
                    width=200)
    st.sidebar.title("💰 POT - SMDET")
    st.sidebar.markdown("**Sistema de Gestão de Benefícios**")
    st.sidebar.markdown("---")
    
    # Menu de navegação
    menu_opcoes = [
        "📊 Dashboard",
        "📤 Importar Arquivos",
        "🔍 Consulta Beneficiários",
        "📊 Relatórios",
        "⚙️ Configurações"
    ]
    
    menu_selecionado = st.sidebar.radio("Navegação", menu_opcoes)
    
    # Exibir página selecionada
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
    st.sidebar.caption(f"© {datetime.now().year} Prefeitura de São Paulo - SMDET")
    st.sidebar.caption("Versão 2.0 - Sistema POT")
    
    # Fechar conexão
    conn.close()

if __name__ == "__main__":
    main()
