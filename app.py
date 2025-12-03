# app.py - SISTEMA POT SMDET - GESTÃO AUTOMÁTICA DE BENEFÍCIOS
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
from typing import List, Dict, Tuple, Optional
warnings.filterwarnings('ignore')

# ========== CONFIGURAÇÃO ==========
st.set_page_config(
    page_title="Sistema POT - Gestão Automática de Benefícios",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========== BANCO DE DADOS ==========
def init_database():
    """Inicializa o banco de dados SQLite"""
    try:
        conn = sqlite3.connect('pot_gestao.db', check_same_thread=False)
        
        # Criar tabelas
        cursor = conn.cursor()
        
        # 1. Beneficiários
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
                cidade TEXT,
                status TEXT DEFAULT 'ATIVO',
                data_cadastro DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(cpf)
            )
        ''')
        
        # 2. Pagamentos
        cursor.execute('''
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
                valor_diario DECIMAL(10,2),
                status_pagamento TEXT DEFAULT 'PAGO',
                arquivo_origem TEXT,
                data_pagamento DATE,
                data_processamento DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 3. Arquivos processados
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
                erros_processamento TEXT,
                UNIQUE(hash_arquivo)
            )
        ''')
        
        # 4. Inconsistências
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS inconsistências (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT NOT NULL,
                severidade TEXT NOT NULL,
                descricao TEXT NOT NULL,
                cpf_envolvido TEXT,
                conta_envolvida TEXT,
                projeto_envolvido TEXT,
                valor_envolvido DECIMAL(10,2),
                data_deteccao DATETIME DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'PENDENTE',
                fonte_dados TEXT
            )
        ''')
        
        # 5. Estatísticas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS estatisticas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT NOT NULL,
                mes_referencia INTEGER NOT NULL,
                ano_referencia INTEGER NOT NULL,
                valor DECIMAL(15,2) NOT NULL,
                descricao TEXT,
                data_calculo DATETIME DEFAULT CURRENT_TIMESTAMP
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
    try:
        cursor = conn.cursor()
        
        indices = [
            "CREATE INDEX IF NOT EXISTS idx_benef_cpf ON beneficiarios(cpf)",
            "CREATE INDEX IF NOT EXISTS idx_benef_nome ON beneficiarios(nome_normalizado)",
            "CREATE INDEX IF NOT EXISTS idx_pag_cpf ON pagamentos(cpf_beneficiario)",
            "CREATE INDEX IF NOT EXISTS idx_pag_periodo ON pagamentos(ano_referencia, mes_referencia)",
            "CREATE INDEX IF NOT EXISTS idx_pag_conta ON pagamentos(numero_conta)",
            "CREATE INDEX IF NOT EXISTS idx_arq_hash ON arquivos_processados(hash_arquivo)",
            "CREATE INDEX IF NOT EXISTS idx_inc_status ON inconsistências(status)",
            "CREATE INDEX IF NOT EXISTS idx_estat_tipo ON estatisticas(tipo, ano_referencia, mes_referencia)"
        ]
        
        for idx in indices:
            cursor.execute(idx)
        
        conn.commit()
    except:
        pass

# ========== PROCESSAMENTO AUTOMÁTICO ==========
class ProcessadorAutomatico:
    """Classe para processamento automático de dados"""
    
    def __init__(self, conn):
        self.conn = conn
    
    def processar_arquivo(self, uploaded_file, tipo_arquivo):
        """Processa arquivo de forma automática"""
        try:
            # Calcular hash para evitar duplicidade
            hash_arquivo = hashlib.md5(uploaded_file.getvalue()).hexdigest()
            
            # Verificar se já foi processado
            if self._arquivo_ja_processado(hash_arquivo):
                return False, "Arquivo já processado anteriormente", []
            
            # Ler arquivo
            df, mensagem = self._ler_arquivo(uploaded_file)
            if df is None:
                return False, mensagem, []
            
            # Normalizar colunas
            df.columns = self._normalizar_colunas(df.columns)
            
            # Detectar mês e ano automaticamente
            mes, ano = self._detectar_periodo(df, uploaded_file.name)
            
            # Detectar inconsistências
            inconsistencias = self._detectar_inconsistencias(df, tipo_arquivo, mes, ano)
            
            # Processar de acordo com o tipo
            if tipo_arquivo == 'PAGAMENTOS':
                sucesso, mensagem = self._processar_pagamentos_auto(df, mes, ano, uploaded_file.name, hash_arquivo)
            elif tipo_arquivo == 'CADASTRO':
                sucesso, mensagem = self._processar_cadastro_auto(df, uploaded_file.name, hash_arquivo)
            else:
                return False, f"Tipo não suportado: {tipo_arquivo}", inconsistencias
            
            # Registrar processamento
            self._registrar_processamento(uploaded_file.name, tipo_arquivo, mes, ano, 
                                        len(df), hash_arquivo, sucesso, mensagem)
            
            # Registrar inconsistências
            if inconsistencias:
                self._registrar_inconsistencias(inconsistencias, tipo_arquivo, uploaded_file.name)
            
            # Atualizar estatísticas automáticas
            if sucesso and tipo_arquivo == 'PAGAMENTOS':
                self._atualizar_estatisticas(mes, ano)
            
            return sucesso, mensagem, inconsistencias
            
        except Exception as e:
            return False, f"Erro no processamento: {str(e)}", []
    
    def _ler_arquivo(self, uploaded_file):
        """Lê arquivo CSV ou Excel automaticamente"""
        try:
            # Salvar temporariamente
            with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as tmp:
                tmp.write(uploaded_file.getvalue())
                tmp_path = tmp.name
            
            try:
                # Detectar tipo
                if uploaded_file.name.lower().endswith('.csv'):
                    # Tentar diferentes combinações
                    for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
                        for sep in [';', ',', '\t']:
                            try:
                                df = pd.read_csv(tmp_path, sep=sep, encoding=encoding, 
                                                dtype=str, on_bad_lines='skip')
                                if len(df.columns) > 1 and not df.empty:
                                    break
                            except:
                                continue
                        if 'df' in locals() and not df.empty:
                            break
                    
                    # Se falhou, tentar auto-detecção
                    if 'df' not in locals() or df.empty:
                        try:
                            df = pd.read_csv(tmp_path, sep=None, engine='python', 
                                           dtype=str, on_bad_lines='skip')
                        except:
                            return None, "Não foi possível ler o arquivo CSV"
                
                elif uploaded_file.name.lower().endswith(('.xls', '.xlsx')):
                    try:
                        df = pd.read_excel(tmp_path, dtype=str)
                    except:
                        try:
                            df = pd.read_excel(tmp_path, dtype=str, engine='openpyxl')
                        except:
                            df = pd.read_excel(tmp_path, dtype=str, engine='xlrd')
                else:
                    return None, "Formato não suportado"
                
                # Limpar
                os.unlink(tmp_path)
                
                if df.empty:
                    return None, "Arquivo vazio"
                
                # Remover colunas completamente vazias
                df = df.dropna(axis=1, how='all')
                
                return df, "Arquivo lido com sucesso"
                
            except Exception as e:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                return None, f"Erro na leitura: {str(e)}"
                
        except Exception as e:
            return None, f"Erro ao processar: {str(e)}"
    
    def _normalizar_colunas(self, colunas):
        """Normaliza nomes de colunas automaticamente"""
        mapeamento = {
            'num_cartao': 'numero_conta', 'numcartao': 'numero_conta', 'cartao': 'numero_conta',
            'num_conta': 'numero_conta', 'conta': 'numero_conta', 'codigo': 'numero_conta',
            'nome': 'nome', 'nome_beneficiario': 'nome', 'beneficiario': 'nome',
            'nome_completo': 'nome', 'nom': 'nome', 'beneficiário': 'nome',
            'cpf': 'cpf', 'cpf_beneficiario': 'cpf', 'cpf_do_beneficiario': 'cpf',
            'projeto': 'projeto', 'programa': 'projeto', 'cod_projeto': 'projeto',
            'valor': 'valor', 'valor_total': 'valor', 'valor_pagto': 'valor',
            'valor_pagamento': 'valor', 'valor_pago': 'valor', 'vlr': 'valor',
            'valor_bruto': 'valor_bruto', 'valor_liquido': 'valor_liquido',
            'valor_desconto': 'valor_desconto', 'desconto': 'valor_desconto',
            'dias': 'dias_trabalhados', 'dias_trabalhados': 'dias_trabalhados',
            'dias_uteis': 'dias_trabalhados', 'dias_a_pagar': 'dias_trabalhados',
            'valor_dia': 'valor_diario', 'valor_diario': 'valor_diario', 'valordia': 'valor_diario',
            'data_pagto': 'data_pagamento', 'data_pagamento': 'data_pagamento',
            'data_pgto': 'data_pagamento', 'datapagto': 'data_pagamento',
            'data': 'data_pagamento', 'dt_pagamento': 'data_pagamento',
            'agencia': 'agencia', 'ag': 'agencia', 'agência': 'agencia',
            'banco': 'banco', 'instituicao': 'banco',
            'rg': 'rg', 'registro_geral': 'rg', 'identidade': 'rg',
            'telefone': 'telefone', 'tel': 'telefone', 'fone': 'telefone',
            'celular': 'telefone', 'cel': 'telefone',
            'email': 'email', 'e_mail': 'email', 'e-mail': 'email',
            'endereco': 'endereco', 'endereço': 'endereco', 'logradouro': 'endereco',
            'bairro': 'bairro', 'distrito': 'bairro', 'zona': 'bairro',
            'cidade': 'cidade', 'municipio': 'cidade', 'município': 'cidade'
        }
        
        colunas_normalizadas = []
        for col in colunas:
            if not isinstance(col, str):
                col = str(col)
            
            col_limpa = col.strip().lower()
            col_limpa = re.sub(r'[\s\-\.]+', '_', col_limpa)
            col_limpa = re.sub(r'[^\w_]', '', col_limpa)
            
            colunas_normalizadas.append(mapeamento.get(col_limpa, col_limpa))
        
        return colunas_normalizadas
    
    def _detectar_periodo(self, df, nome_arquivo):
        """Detecta mês e ano automaticamente"""
        # 1. Tentar pelo nome do arquivo
        mes, ano = self._detectar_periodo_nome(nome_arquivo)
        
        # 2. Tentar pelas colunas de data
        if mes is None or ano is None:
            mes, ano = self._detectar_periodo_colunas(df)
        
        # 3. Usar data atual como fallback
        if mes is None:
            mes = datetime.now().month
        if ano is None:
            ano = datetime.now().year
        
        return mes, ano
    
    def _detectar_periodo_nome(self, nome_arquivo):
        """Detecta período pelo nome do arquivo"""
        nome_upper = nome_arquivo.upper()
        
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
        
        # Detectar mês
        mes = None
        for mes_nome, mes_num in meses.items():
            if mes_nome in nome_upper:
                mes = mes_num
                break
        
        # Detectar ano (procura por 4 dígitos começando com 20)
        ano = None
        ano_match = re.search(r'(20\d{2})', nome_upper)
        if ano_match:
            ano = int(ano_match.group(1))
        
        return mes, ano
    
    def _detectar_periodo_colunas(self, df):
        """Detecta período pelas colunas de data"""
        mes = None
        ano = None
        
        # Procurar por colunas que contenham data
        for col in df.columns:
            col_lower = col.lower()
            if 'data' in col_lower or 'dt' in col_lower or 'periodo' in col_lower:
                # Tentar extrair datas da coluna
                try:
                    # Converter para datetime
                    df[col] = pd.to_datetime(df[col], errors='coerce', dayfirst=True)
                    
                    # Extrair mês e ano das datas válidas
                    meses_validos = df[col].dt.month.dropna().unique()
                    anos_validos = df[col].dt.year.dropna().unique()
                    
                    if len(meses_validos) > 0:
                        mes = int(meses_validos[0])
                    if len(anos_validos) > 0:
                        ano = int(anos_validos[0])
                    
                    if mes and ano:
                        break
                except:
                    continue
        
        return mes, ano
    
    def _detectar_inconsistencias(self, df, tipo_arquivo, mes, ano):
        """Detecta inconsistências automaticamente"""
        inconsistencias = []
        
        # Verificar colunas mínimas
        if tipo_arquivo == 'PAGAMENTOS':
            colunas_minimas = ['numero_conta', 'nome', 'valor']
            tipo_desc = 'pagamentos'
        elif tipo_arquivo == 'CADASTRO':
            colunas_minimas = ['cpf', 'nome']
            tipo_desc = 'cadastro'
        else:
            colunas_minimas = []
            tipo_desc = 'desconhecido'
        
        # Verificar colunas faltantes
        colunas_faltantes = [col for col in colunas_minimas if col not in df.columns]
        if colunas_faltantes:
            inconsistencias.append({
                'tipo': 'COLUNAS_FALTANTES',
                'severidade': 'ALTA',
                'descricao': f'Arquivo de {tipo_desc}: faltam colunas: {", ".join(colunas_faltantes)}'
            })
        
        # Verificar dados vazios nas colunas críticas
        for col in colunas_minimas:
            if col in df.columns:
                vazios = df[col].isna().sum() + (df[col].astype(str).str.strip() == '').sum()
                if vazios > 0:
                    severidade = 'CRITICA' if col in ['numero_conta', 'cpf'] else 'ALTA'
                    inconsistencias.append({
                        'tipo': f'DADOS_VAZIOS_{col.upper()}',
                        'severidade': severidade,
                        'descricao': f'{vazios} registros sem {col}'
                    })
        
        # Verificar valores inválidos para pagamentos
        if tipo_arquivo == 'PAGAMENTOS' and 'valor' in df.columns:
            # Converter valores
            valores = df['valor'].apply(self._converter_valor)
            invalidos = (valores <= 0).sum()
            if invalidos > 0:
                inconsistencias.append({
                    'tipo': 'VALORES_INVALIDOS',
                    'severidade': 'ALTA',
                    'descricao': f'{invalidos} valores zerados ou negativos'
                })
            
            # Verificar valores muito altos ou baixos
            if len(valores) > 0:
                media = valores.mean()
                extremos = ((valores > media * 10) | (valores < 1)).sum()
                if extremos > 0:
                    inconsistencias.append({
                        'tipo': 'VALORES_EXTREMOS',
                        'severidade': 'MEDIA',
                        'descricao': f'{extremos} valores fora do padrão esperado'
                    })
        
        # Verificar CPFs inválidos
        if 'cpf' in df.columns:
            cpfs_invalidos = df['cpf'].apply(self._validar_cpf).sum()
            if cpfs_invalidos > 0:
                inconsistencias.append({
                    'tipo': 'CPFS_INVALIDOS',
                    'severidade': 'ALTA',
                    'descricao': f'{cpfs_invalidos} CPFs com formato inválido'
                })
        
        return inconsistencias
    
    def _converter_valor(self, valor):
        """Converte valor para numérico"""
        if pd.isna(valor):
            return 0.0
        
        valor_str = str(valor).strip()
        
        # Remover símbolos
        valor_str = re.sub(r'[R\$\s]', '', valor_str)
        
        # Tratar formato brasileiro
        if ',' in valor_str and '.' in valor_str:
            # Ex: 1.234,56 -> 1234.56
            valor_str = valor_str.replace('.', '').replace(',', '.')
        elif ',' in valor_str:
            # Verificar se vírgula é decimal
            partes = valor_str.split(',')
            if len(partes) == 2 and len(partes[1]) == 2:
                # Provavelmente decimal (R$ 123,45)
                valor_str = valor_str.replace(',', '.')
            else:
                # Provavelmente separador de milhar
                valor_str = valor_str.replace(',', '')
        
        try:
            return float(valor_str)
        except:
            return 0.0
    
    def _validar_cpf(self, cpf):
        """Valida formato básico do CPF"""
        if pd.isna(cpf):
            return True  # Considera válido para não contar como erro
        
        cpf_str = str(cpf).strip()
        cpf_limpo = re.sub(r'\D', '', cpf_str)
        
        return len(cpf_limpo) != 11
    
    def _arquivo_ja_processado(self, hash_arquivo):
        """Verifica se arquivo já foi processado"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM arquivos_processados WHERE hash_arquivo = ?", (hash_arquivo,))
        return cursor.fetchone() is not None
    
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
            print(f"Erro ao registrar: {str(e)}")
    
    def _registrar_inconsistencias(self, inconsistencias, fonte_dados, arquivo_origem):
        """Registra inconsistências"""
        try:
            cursor = self.conn.cursor()
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
            self.conn.commit()
        except Exception as e:
            print(f"Erro inconsistências: {str(e)}")
    
    def _processar_pagamentos_auto(self, df, mes, ano, nome_arquivo, hash_arquivo):
        """Processa pagamentos automaticamente"""
        try:
            cursor = self.conn.cursor()
            registros_processados = 0
            valor_total = 0
            valor_bruto_total = 0
            descontos_total = 0
            
            for idx, row in df.iterrows():
                try:
                    # Extrair dados básicos
                    numero_conta = str(row.get('numero_conta', '')).strip()
                    nome = self._normalizar_nome(str(row.get('nome', '')))
                    
                    # Validar dados mínimos
                    if not numero_conta or not nome:
                        continue
                    
                    # Extrair valores
                    valor_bruto = self._converter_valor(row.get('valor'))
                    valor_liquido = self._converter_valor(row.get('valor_liquido', valor_bruto))
                    
                    # Se valor líquido não informado, usar valor bruto
                    if valor_liquido == 0:
                        valor_liquido = valor_bruto
                    
                    valor_desconto = valor_bruto - valor_liquido
                    
                    # Calcular valor diário se tiver dias trabalhados
                    dias = self._extrair_dias(row)
                    valor_diario = valor_liquido / dias if dias > 0 else 0
                    
                    # Extrair outros dados
                    cpf = self._normalizar_cpf(row.get('cpf', ''))
                    projeto = str(row.get('projeto', '')).strip()
                    
                    # Se não tem CPF válido, tentar buscar ou criar
                    if not cpf or len(cpf) != 11:
                        cpf = self._obter_ou_criar_cpf(nome, cursor)
                    
                    # Garantir beneficiário no cadastro
                    self._atualizar_beneficiario(cpf, nome, cursor)
                    
                    # Inserir pagamento
                    cursor.execute('''
                        INSERT INTO pagamentos 
                        (numero_conta, cpf_beneficiario, nome_beneficiario, projeto,
                         mes_referencia, ano_referencia, valor_bruto, valor_liquido,
                         valor_desconto, dias_trabalhados, valor_diario, arquivo_origem)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        numero_conta, cpf, nome, projeto, mes, ano,
                        valor_bruto, valor_liquido, valor_desconto, dias, valor_diario, nome_arquivo
                    ))
                    
                    registros_processados += 1
                    valor_total += valor_liquido
                    valor_bruto_total += valor_bruto
                    descontos_total += valor_desconto
                    
                except Exception as e:
                    # Continuar com próximo registro
                    continue
            
            self.conn.commit()
            
            # Atualizar arquivo processado com totais
            cursor.execute('''
                UPDATE arquivos_processados 
                SET registros_processados = ?,
                    valor_total = ?
                WHERE hash_arquivo = ?
            ''', (registros_processados, valor_total, hash_arquivo))
            self.conn.commit()
            
            return True, f"✅ {registros_processados} pagamentos processados | Mês/Ano: {mes:02d}/{ano} | Total: R$ {valor_total:,.2f}"
            
        except Exception as e:
            self.conn.rollback()
            return False, f"❌ Erro: {str(e)}"
    
    def _processar_cadastro_auto(self, df, nome_arquivo, hash_arquivo):
        """Processa cadastro automaticamente"""
        try:
            cursor = self.conn.cursor()
            registros_processados = 0
            
            for idx, row in df.iterrows():
                try:
                    cpf = self._normalizar_cpf(row.get('cpf', ''))
                    nome = self._normalizar_nome(str(row.get('nome', '')))
                    
                    if not cpf or not nome or len(cpf) != 11:
                        continue
                    
                    # Extrair outros dados
                    rg = str(row.get('rg', '')).strip()
                    telefone = str(row.get('telefone', '')).strip()
                    email = str(row.get('email', '')).strip()
                    endereco = str(row.get('endereco', '')).strip()
                    bairro = str(row.get('bairro', '')).strip()
                    cidade = str(row.get('cidade', '')).strip()
                    
                    # Inserir ou atualizar
                    cursor.execute('''
                        INSERT OR REPLACE INTO beneficiarios 
                        (cpf, nome, nome_normalizado, rg, telefone, email, 
                         endereco, bairro, cidade, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ATIVO')
                    ''', (cpf, nome, nome, rg, telefone, email, endereco, bairro, cidade))
                    
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
    
    def _normalizar_nome(self, nome):
        """Normaliza nome"""
        if pd.isna(nome) or not isinstance(nome, str):
            return ""
        
        nome = str(nome).strip()
        nome = re.sub(r'\s+', ' ', nome)
        nome = nome.upper()
        
        # Remover acentos
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
    
    def _normalizar_cpf(self, cpf):
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
    
    def _extrair_dias(self, row):
        """Extrai número de dias trabalhados"""
        # Tentar diferentes campos
        campos_dias = ['dias_trabalhados', 'dias', 'dias_uteis']
        
        for campo in campos_dias:
            if campo in row and not pd.isna(row[campo]):
                try:
                    return int(float(row[campo]))
                except:
                    continue
        
        # Valor padrão
        return 20
    
    def _obter_ou_criar_cpf(self, nome, cursor):
        """Obtém ou cria CPF para beneficiário"""
        # Tentar buscar por nome
        cursor.execute("SELECT cpf FROM beneficiarios WHERE nome_normalizado LIKE ? LIMIT 1", 
                     (f"%{nome}%",))
        resultado = cursor.fetchone()
        
        if resultado:
            return resultado[0]
        else:
            # Criar CPF temporário baseado no hash do nome
            return f"TEMP{hash(nome) % 1000000:06d}"
    
    def _atualizar_beneficiario(self, cpf, nome, cursor):
        """Atualiza ou cria beneficiário"""
        cursor.execute('''
            INSERT OR IGNORE INTO beneficiarios 
            (cpf, nome, nome_normalizado, status)
            VALUES (?, ?, ?, 'ATIVO')
        ''', (cpf, nome, nome))
    
    def _atualizar_estatisticas(self, mes, ano):
        """Atualiza estatísticas automaticamente"""
        try:
            cursor = self.conn.cursor()
            
            # Calcular estatísticas do período
            cursor.execute('''
                SELECT 
                    COUNT(DISTINCT cpf_beneficiario) as beneficiarios,
                    COUNT(*) as pagamentos,
                    SUM(valor_liquido) as valor_total,
                    SUM(valor_desconto) as descontos_total,
                    AVG(valor_liquido) as valor_medio,
                    AVG(valor_diario) as diario_medio,
                    SUM(dias_trabalhados) as total_dias
                FROM pagamentos
                WHERE mes_referencia = ? AND ano_referencia = ?
            ''', (mes, ano))
            
            resultado = cursor.fetchone()
            
            if resultado:
                # Inserir estatísticas
                estatisticas = [
                    ('BENEFICIARIOS', mes, ano, resultado[0], f'Beneficiários pagos em {mes:02d}/{ano}'),
                    ('TOTAL_PAGAMENTOS', mes, ano, resultado[1], f'Total de pagamentos em {mes:02d}/{ano}'),
                    ('VALOR_TOTAL', mes, ano, resultado[2], f'Valor total pago em {mes:02d}/{ano}'),
                    ('DESCONTOS_TOTAL', mes, ano, resultado[3], f'Total de descontos em {mes:02d}/{ano}'),
                    ('VALOR_MEDIO', mes, ano, resultado[4], f'Valor médio por pagamento em {mes:02d}/{ano}'),
                    ('DIARIO_MEDIO', mes, ano, resultado[5], f'Valor diário médio em {mes:02d}/{ano}'),
                    ('TOTAL_DIAS', mes, ano, resultado[6], f'Total de dias trabalhados em {mes:02d}/{ano}')
                ]
                
                for tipo, m, a, valor, desc in estatisticas:
                    cursor.execute('''
                        INSERT OR REPLACE INTO estatisticas 
                        (tipo, mes_referencia, ano_referencia, valor, descricao)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (tipo, m, a, valor, desc))
                
                self.conn.commit()
                
        except Exception as e:
            print(f"Erro estatísticas: {str(e)}")

# ========== ANÁLISE AUTOMÁTICA ==========
class AnaliseAutomatica:
    """Classe para análise automática de dados"""
    
    def __init__(self, conn):
        self.conn = conn
    
    def obter_resumo_geral(self):
        """Obtém resumo geral automático"""
        try:
            cursor = self.conn.cursor()
            resumo = {}
            
            # Totais gerais
            cursor.execute("SELECT COUNT(*) FROM beneficiarios WHERE status = 'ATIVO'")
            resumo['beneficiarios_ativos'] = cursor.fetchone()[0] or 0
            
            cursor.execute("SELECT COUNT(DISTINCT cpf_beneficiario) FROM pagamentos")
            resumo['beneficiarios_pagos'] = cursor.fetchone()[0] or 0
            
            cursor.execute("SELECT SUM(valor_liquido) FROM pagamentos")
            resultado = cursor.fetchone()[0]
            resumo['valor_total_pago'] = float(resultado) if resultado else 0
            
            cursor.execute("SELECT COUNT(*) FROM pagamentos")
            resumo['total_pagamentos'] = cursor.fetchone()[0] or 0
            
            # Último período
            cursor.execute('''
                SELECT MAX(ano_referencia), MAX(mes_referencia)
                FROM pagamentos
            ''')
            ultimo = cursor.fetchone()
            if ultimo[0]:
                resumo['ultimo_periodo'] = f"{ultimo[1]:02d}/{ultimo[0]}"
                resumo['ultimo_mes'] = ultimo[1]
                resumo['ultimo_ano'] = ultimo[0]
            else:
                resumo['ultimo_periodo'] = "Nenhum"
                resumo['ultimo_mes'] = None
                resumo['ultimo_ano'] = None
            
            # Inconsistências
            cursor.execute("SELECT COUNT(*) FROM inconsistências WHERE status = 'PENDENTE'")
            resumo['inconsistencias_pendentes'] = cursor.fetchone()[0] or 0
            
            # Arquivos processados
            cursor.execute("SELECT COUNT(*) FROM arquivos_processados WHERE status_processamento = 'SUCESSO'")
            resumo['arquivos_processados'] = cursor.fetchone()[0] or 0
            
            # Projetos ativos
            cursor.execute("SELECT COUNT(DISTINCT projeto) FROM pagamentos WHERE projeto IS NOT NULL AND projeto != ''")
            resumo['projetos_ativos'] = cursor.fetchone()[0] or 0
            
            return resumo
            
        except:
            return self._resumo_padrao()
    
    def _resumo_padrao(self):
        """Resumo padrão em caso de erro"""
        return {
            'beneficiarios_ativos': 0,
            'beneficiarios_pagos': 0,
            'valor_total_pago': 0,
            'total_pagamentos': 0,
            'ultimo_periodo': 'Nenhum',
            'ultimo_mes': None,
            'ultimo_ano': None,
            'inconsistencias_pendentes': 0,
            'arquivos_processados': 0,
            'projetos_ativos': 0
        }
    
    def obter_evolucao_mensal(self, limite=12):
        """Obtém evolução mensal automática"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT 
                    ano_referencia,
                    mes_referencia,
                    COUNT(DISTINCT cpf_beneficiario) as beneficiarios,
                    COUNT(*) as pagamentos,
                    SUM(valor_liquido) as valor_total,
                    AVG(valor_liquido) as valor_medio,
                    SUM(valor_desconto) as descontos,
                    SUM(dias_trabalhados) as total_dias
                FROM pagamentos
                GROUP BY ano_referencia, mes_referencia
                ORDER BY ano_referencia DESC, mes_referencia DESC
                LIMIT ?
            ''', (limite,))
            
            resultados = cursor.fetchall()
            if resultados:
                df = pd.DataFrame(resultados, 
                    columns=['ano', 'mes', 'beneficiarios', 'pagamentos', 'valor_total', 
                            'valor_medio', 'descontos', 'dias'])
                df['periodo'] = df['mes'].astype(str).str.zfill(2) + '/' + df['ano'].astype(str)
                df = df.sort_values(['ano', 'mes'])
                return df
            else:
                return pd.DataFrame()
        except:
            return pd.DataFrame()
    
    def obter_distribuicao_projetos(self):
        """Obtém distribuição por projeto automática"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT 
                    COALESCE(projeto, 'NÃO INFORMADO') as projeto,
                    COUNT(*) as pagamentos,
                    SUM(valor_liquido) as valor_total,
                    AVG(valor_liquido) as valor_medio,
                    COUNT(DISTINCT cpf_beneficiario) as beneficiarios,
                    SUM(dias_trabalhados) as total_dias
                FROM pagamentos
                GROUP BY projeto
                ORDER BY valor_total DESC
                LIMIT 15
            ''')
            
            resultados = cursor.fetchall()
            if resultados:
                return pd.DataFrame(resultados, 
                    columns=['projeto', 'pagamentos', 'valor_total', 'valor_medio', 
                            'beneficiarios', 'dias'])
            else:
                return pd.DataFrame()
        except:
            return pd.DataFrame()
    
    def obter_inconsistencias_ativas(self):
        """Obtém inconsistências ativas"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT 
                    tipo,
                    severidade,
                    descricao,
                    COUNT(*) as quantidade
                FROM inconsistências
                WHERE status = 'PENDENTE'
                GROUP BY tipo, severidade, descricao
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
                return pd.DataFrame(resultados, 
                    columns=['tipo', 'severidade', 'descricao', 'quantidade'])
            else:
                return pd.DataFrame()
        except:
            return pd.DataFrame()
    
    def obter_arquivos_recentes(self, limite=10):
        """Obtém arquivos processados recentemente"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT 
                    nome_arquivo,
                    tipo_arquivo,
                    mes_referencia,
                    ano_referencia,
                    registros_processados,
                    valor_total,
                    data_processamento,
                    status_processamento
                FROM arquivos_processados
                ORDER BY data_processamento DESC
                LIMIT ?
            ''', (limite,))
            
            resultados = cursor.fetchall()
            if resultados:
                df = pd.DataFrame(resultados, 
                    columns=['arquivo', 'tipo', 'mes', 'ano', 'registros', 
                            'valor', 'data_processamento', 'status'])
                df['periodo'] = df['mes'].fillna(0).astype(int).astype(str).str.zfill(2) + '/' + df['ano'].fillna(0).astype(int).astype(str)
                return df
            else:
                return pd.DataFrame()
        except:
            return pd.DataFrame()

# ========== INTERFACE STREAMLIT ==========
def mostrar_dashboard_automatico(conn):
    """Dashboard automático"""
    st.title("💰 Sistema POT - Gestão Automática de Benefícios")
    st.markdown("---")
    
    analise = AnaliseAutomatica(conn)
    resumo = analise.obter_resumo_geral()
    
    # Métricas principais
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Beneficiários Ativos", f"{resumo['beneficiarios_ativos']:,}")
        st.caption(f"Com pagamentos: {resumo['beneficiarios_pagos']:,}")
    
    with col2:
        st.metric("Valor Total Pago", f"R$ {resumo['valor_total_pago']:,.2f}")
        st.caption(f"Projetos: {resumo['projetos_ativos']:,}")
    
    with col3:
        st.metric("Último Período", resumo['ultimo_periodo'])
        st.caption(f"Pagamentos: {resumo['total_pagamentos']:,}")
    
    with col4:
        cor = "inverse" if resumo['inconsistencias_pendentes'] > 0 else "normal"
        st.metric("Inconsistências", f"{resumo['inconsistencias_pendentes']:,}")
        st.caption(f"Arquivos: {resumo['arquivos_processados']:,}")
    
    st.markdown("---")
    
    # Abas automáticas
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Evolução Mensal", "📋 Projetos", "⚠️ Alertas", "📁 Processamentos"])
    
    with tab1:
        st.subheader("Evolução Automática dos Pagamentos")
        
        df_evolucao = analise.obter_evolucao_mensal()
        if not df_evolucao.empty:
            # Gráfico de evolução
            fig = px.line(
                df_evolucao,
                x='periodo',
                y='valor_total',
                title='Valor Total Pago por Período (Detecção Automática)',
                markers=True
            )
            fig.update_layout(xaxis_title='Período (Detectado Automaticamente)', 
                            yaxis_title='Valor Total (R$)')
            st.plotly_chart(fig, use_container_width=True)
            
            # Gráfico de barras para beneficiários
            fig2 = px.bar(
                df_evolucao,
                x='periodo',
                y='beneficiarios',
                title='Beneficiários por Período',
                color='valor_total',
                color_continuous_scale='Blues'
            )
            st.plotly_chart(fig2, use_container_width=True)
            
            # Tabela de dados
            st.dataframe(
                df_evolucao[['periodo', 'beneficiarios', 'pagamentos', 'valor_total', 'valor_medio', 'descontos']],
                use_container_width=True,
                column_config={
                    'valor_total': st.column_config.NumberColumn('Valor Total (R$)', format="R$ %.2f"),
                    'valor_medio': st.column_config.NumberColumn('Média (R$)', format="R$ %.2f"),
                    'descontos': st.column_config.NumberColumn('Descontos (R$)', format="R$ %.2f")
                }
            )
        else:
            st.info("📭 Nenhum pagamento processado ainda. Importe arquivos para visualizar dados.")
    
    with tab2:
        st.subheader("Distribuição Automática por Projeto")
        
        df_projetos = analise.obter_distribuicao_projetos()
        if not df_projetos.empty:
            # Gráfico de pizza
            fig = px.pie(
                df_projetos.head(10),
                values='valor_total',
                names='projeto',
                title='Distribuição por Projeto (Top 10)'
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Gráfico de barras
            fig2 = px.bar(
                df_projetos.head(10),
                x='projeto',
                y='valor_total',
                title='Valor Total por Projeto',
                color='beneficiarios',
                color_continuous_scale='Viridis'
            )
            st.plotly_chart(fig2, use_container_width=True)
            
            # Tabela detalhada
            st.dataframe(
                df_projetos,
                use_container_width=True,
                column_config={
                    'valor_total': st.column_config.NumberColumn('Valor Total (R$)', format="R$ %.2f"),
                    'valor_medio': st.column_config.NumberColumn('Média (R$)', format="R$ %.2f"),
                    'dias': st.column_config.NumberColumn('Dias', format="%.0f")
                }
            )
        else:
            st.info("📭 Nenhum projeto registrado ainda.")
    
    with tab3:
        st.subheader("Alertas e Inconsistências Detectadas")
        
        df_inconsistencias = analise.obter_inconsistencias_ativas()
        if not df_inconsistencias.empty:
            # Gráfico de severidade
            fig = px.bar(
                df_inconsistencias,
                x='tipo',
                y='quantidade',
                color='severidade',
                title='Inconsistências por Tipo e Severidade',
                color_discrete_map={
                    'CRITICA': 'red',
                    'ALTA': 'orange',
                    'MEDIA': 'yellow',
                    'BAIXA': 'green'
                }
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Lista detalhada
            for _, row in df_inconsistencias.iterrows():
                emoji = "🔴" if row['severidade'] == 'CRITICA' else "🟠" if row['severidade'] == 'ALTA' else "🟡"
                st.warning(f"{emoji} **{row['tipo']}** ({row['quantidade']}x): {row['descricao']}")
            
            # Botão para resolver
            if st.button("✅ Marcar Todas como Resolvidas", key="resolver_todas"):
                cursor = conn.cursor()
                cursor.execute("UPDATE inconsistências SET status = 'RESOLVIDO' WHERE status = 'PENDENTE'")
                conn.commit()
                st.success("Todas as inconsistências foram marcadas como resolvidas!")
                st.rerun()
        else:
            st.success("🎉 Nenhuma inconsistência pendente!")
    
    with tab4:
        st.subheader("Últimos Processamentos Automáticos")
        
        df_processamentos = analise.obter_arquivos_recentes()
        if not df_processamentos.empty:
            # Timeline visual
            for _, row in df_processamentos.iterrows():
                status_emoji = "✅" if row['status'] == 'SUCESSO' else "❌"
                tipo_emoji = "💰" if row['tipo'] == 'PAGAMENTOS' else "👤"
                
                with st.container():
                    cols = st.columns([1, 4, 2, 2])
                    with cols[0]:
                        st.markdown(f"**{tipo_emoji}**")
                    with cols[1]:
                        st.markdown(f"**{row['arquivo']}**")
                    with cols[2]:
                        if pd.notna(row['periodo']) and row['periodo'] != '00/0':
                            st.markdown(f"📅 {row['periodo']}")
                    with cols[3]:
                        st.markdown(f"{status_emoji} {row['registros']} reg")
            
            # Tabela detalhada
            st.dataframe(
                df_processamentos[['arquivo', 'tipo', 'periodo', 'registros', 'valor', 'data_processamento', 'status']],
                use_container_width=True,
                column_config={
                    'valor': st.column_config.NumberColumn('Valor (R$)', format="R$ %.2f"),
                    'data_processamento': st.column_config.DatetimeColumn('Processamento'),
                    'registros': st.column_config.NumberColumn('Registros', format="%.0f")
                },
                hide_index=True
            )
        else:
            st.info("📭 Nenhum arquivo processado ainda.")

def mostrar_importacao_automatica(conn):
    """Importação automática"""
    st.header("📤 Importação Automática de Arquivos")
    
    # Explicação
    with st.expander("🔍 Como funciona a importação automática", expanded=True):
        st.markdown("""
        ### 📋 **Funcionamento Automático:**
        
        1. **Detecção Automática de Período:**
           - Analisa o nome do arquivo (ex: `pagamentos_janeiro_2024.csv`)
           - Extrai dados das colunas de data
           - Define mês/ano automaticamente
        
        2. **Processamento Inteligente:**
           - Detecta automaticamente o tipo de arquivo
           - Normaliza colunas (aceita vários nomes)
           - Calcula valores automaticamente
        
        3. **Validação Automática:**
           - Verifica inconsistências
           - Calcula estatísticas
           - Atualiza relatórios
        """)
    
    # Seção de upload
    st.subheader("📁 Envie seus arquivos")
    
    # Upload múltiplo
    uploaded_files = st.file_uploader(
        "Arraste ou selecione arquivos (CSV ou Excel)",
        type=['csv', 'xls', 'xlsx'],
        accept_multiple_files=True,
        key="upload_multiplo"
    )
    
    if uploaded_files:
        st.success(f"✅ {len(uploaded_files)} arquivo(s) selecionado(s)")
        
        # Processar cada arquivo
        processador = ProcessadorAutomatico(conn)
        
        for uploaded_file in uploaded_files:
            with st.expander(f"📄 {uploaded_file.name}", expanded=False):
                # Detectar tipo automaticamente
                tipo_auto = "PAGAMENTOS" if any(palavra in uploaded_file.name.upper() for palavra in 
                                              ['PAG', 'PAGAMENTO', 'PAGTO', 'VALOR', 'CONTA']) else "CADASTRO"
                
                st.info(f"📋 **Tipo detectado:** {tipo_auto}")
                
                # Prévia automática
                if st.button(f"👁️ Ver prévia - {uploaded_file.name}", key=f"previa_{uploaded_file.name}"):
                    df_previa, mensagem = processador._ler_arquivo(uploaded_file)
                    if df_previa is not None:
                        df_previa.columns = processador._normalizar_colunas(df_previa.columns)
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.dataframe(df_previa.head(5), use_container_width=True)
                        with col2:
                            st.metric("Registros", len(df_previa))
                            st.metric("Colunas", len(df_previa.columns))
                        
                        # Detectar período
                        mes, ano = processador._detectar_periodo(df_previa, uploaded_file.name)
                        st.info(f"📅 **Período detectado:** {mes:02d}/{ano}")
                
                # Processar
                if st.button(f"🔄 Processar - {uploaded_file.name}", key=f"processar_{uploaded_file.name}", type="primary"):
                    with st.spinner(f"Processando {uploaded_file.name}..."):
                        sucesso, mensagem, inconsistencias = processador.processar_arquivo(
                            uploaded_file, tipo_auto
                        )
                    
                    if sucesso:
                        st.success(mensagem)
                        
                        if inconsistencias:
                            st.warning(f"⚠️ {len(inconsistencias)} inconsistência(s) detectada(s)")
                            for inc in inconsistencias:
                                st.markdown(f"- **{inc['tipo']}**: {inc['descricao']}")
                        
                        st.balloons()
                    else:
                        st.error(mensagem)
        
        # Processar todos
        if len(uploaded_files) > 1 and st.button("🔄 PROCESSAR TODOS OS ARQUIVOS", type="primary", use_container_width=True):
            resultados = []
            
            with st.status("Processando todos os arquivos...", expanded=True) as status:
                for uploaded_file in uploaded_files:
                    tipo_auto = "PAGAMENTOS" if any(palavra in uploaded_file.name.upper() for palavra in 
                                                  ['PAG', 'PAGAMENTO', 'PAGTO', 'VALOR', 'CONTA']) else "CADASTRO"
                    
                    status.update(label=f"Processando: {uploaded_file.name}", state="running")
                    
                    sucesso, mensagem, inconsistencias = processador.processar_arquivo(
                        uploaded_file, tipo_auto
                    )
                    
                    resultados.append({
                        'arquivo': uploaded_file.name,
                        'sucesso': sucesso,
                        'mensagem': mensagem,
                        'inconsistencias': len(inconsistencias)
                    })
            
            # Resumo
            st.subheader("📋 Resumo do Processamento em Lote")
            
            sucessos = sum(1 for r in resultados if r['sucesso'])
            total_inc = sum(r['inconsistencias'] for r in resultados)
            
            col_res1, col_res2, col_res3 = st.columns(3)
            with col_res1:
                st.metric("Arquivos", len(resultados))
            with col_res2:
                st.metric("Processados", sucessos)
            with col_res3:
                st.metric("Inconsistências", total_inc)
            
            # Tabela de resultados
            df_resultados = pd.DataFrame(resultados)
            st.dataframe(df_resultados, use_container_width=True)
            
            if sucessos == len(resultados):
                st.balloons()
                st.success("✅ Todos os arquivos foram processados com sucesso!")
            else:
                st.warning(f"⚠️ {len(resultados) - sucessos} arquivo(s) com problemas")
            
            st.rerun()

def mostrar_consultas_automaticas(conn):
    """Consultas automáticas"""
    st.header("🔍 Consultas Automáticas")
    
    tab1, tab2, tab3 = st.tabs(["👤 Beneficiários", "💰 Pagamentos", "📊 Estatísticas"])
    
    with tab1:
        st.subheader("Consulta de Beneficiários")
        
        col1, col2 = st.columns(2)
        
        with col1:
            termo = st.text_input("Buscar por nome ou CPF", placeholder="Digite nome ou CPF")
        
        with col2:
            limite = st.slider("Máximo de resultados", 10, 100, 50)
        
        if termo:
            try:
                cursor = conn.cursor()
                
                # Buscar por nome ou CPF
                termo_limpo = re.sub(r'\D', '', termo)
                
                if len(termo_limpo) >= 11:  # Provavelmente CPF
                    query = '''
                        SELECT 
                            b.cpf,
                            b.nome,
                            b.rg,
                            b.status,
                            COUNT(p.id) as total_pagamentos,
                            SUM(p.valor_liquido) as valor_total,
                            MAX(p.data_processamento) as ultimo_pagamento
                        FROM beneficiarios b
                        LEFT JOIN pagamentos p ON b.cpf = p.cpf_beneficiario
                        WHERE b.cpf LIKE ?
                        GROUP BY b.cpf, b.nome, b.rg, b.status
                        ORDER BY b.nome
                        LIMIT ?
                    '''
                    params = (f'%{termo_limpo}%', limite)
                else:
                    # Buscar por nome
                    nome_normalizado = termo.upper()
                    nome_normalizado = re.sub(r'[ÁÀÂÃ]', 'A', nome_normalizado)
                    nome_normalizado = re.sub(r'[ÉÈÊ]', 'E', nome_normalizado)
                    nome_normalizado = re.sub(r'[ÍÌÎ]', 'I', nome_normalizado)
                    nome_normalizado = re.sub(r'[ÓÒÔÕ]', 'O', nome_normalizado)
                    nome_normalizado = re.sub(r'[ÚÙÛ]', 'U', nome_normalizado)
                    nome_normalizado = re.sub(r'Ç', 'C', nome_normalizado)
                    
                    query = '''
                        SELECT 
                            b.cpf,
                            b.nome,
                            b.rg,
                            b.status,
                            COUNT(p.id) as total_pagamentos,
                            SUM(p.valor_liquido) as valor_total,
                            MAX(p.data_processamento) as ultimo_pagamento
                        FROM beneficiarios b
                        LEFT JOIN pagamentos p ON b.cpf = p.cpf_beneficiario
                        WHERE b.nome_normalizado LIKE ?
                        GROUP BY b.cpf, b.nome, b.rg, b.status
                        ORDER BY b.nome
                        LIMIT ?
                    '''
                    params = (f'%{nome_normalizado}%', limite)
                
                cursor.execute(query, params)
                resultados = cursor.fetchall()
                
                if resultados:
                    df = pd.DataFrame(resultados, 
                        columns=['CPF', 'Nome', 'RG', 'Status', 'Pagamentos', 'Total', 'Último'])
                    
                    st.success(f"✅ {len(df)} resultado(s) encontrado(s)")
                    
                    # Métricas
                    col_met1, col_met2 = st.columns(2)
                    with col_met1:
                        st.metric("Valor Total", f"R$ {df['Total'].sum():,.2f}")
                    with col_met2:
                        st.metric("Média por Benef.", f"R$ {df['Total'].mean():,.2f}")
                    
                    # Tabela
                    st.dataframe(
                        df,
                        use_container_width=True,
                        column_config={
                            'Total': st.column_config.NumberColumn('Total (R$)', format="R$ %.2f")
                        }
                    )
                else:
                    st.info("Nenhum resultado encontrado")
                    
            except Exception as e:
                st.error(f"Erro na consulta: {str(e)}")
    
    with tab2:
        st.subheader("Consulta de Pagamentos")
        
        # Últimos pagamentos automaticamente
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                p.nome_beneficiario,
                p.cpf_beneficiario,
                p.projeto,
                p.mes_referencia || '/' || p.ano_referencia as periodo,
                p.valor_liquido,
                p.dias_trabalhados,
                p.valor_diario,
                p.data_processamento
            FROM pagamentos p
            ORDER BY p.data_processamento DESC
            LIMIT 50
        ''')
        
        resultados = cursor.fetchall()
        if resultados:
            df = pd.DataFrame(resultados, 
                columns=['Nome', 'CPF', 'Projeto', 'Período', 'Valor', 'Dias', 'Diário', 'Processamento'])
            
            st.dataframe(
                df,
                use_container_width=True,
                column_config={
                    'Valor': st.column_config.NumberColumn('Valor (R$)', format="R$ %.2f"),
                    'Diário': st.column_config.NumberColumn('Diário (R$)', format="R$ %.2f")
                }
            )
        else:
            st.info("Nenhum pagamento registrado")
    
    with tab3:
        st.subheader("Estatísticas Automáticas")
        
        analise = AnaliseAutomatica(conn)
        resumo = analise.obter_resumo_geral()
        
        # Cards de estatísticas
        col_est1, col_est2, col_est3 = st.columns(3)
        
        with col_est1:
            st.metric("Benef. com Pagamento", f"{resumo['beneficiarios_pagos']:,}")
            st.caption(f"Ativos: {resumo['beneficiarios_ativos']:,}")
        
        with col_est2:
            st.metric("Valor Médio/Pag.", 
                     f"R$ {resumo['valor_total_pago']/resumo['total_pagamentos']:,.2f}" 
                     if resumo['total_pagamentos'] > 0 else "R$ 0,00")
            st.caption(f"Total: R$ {resumo['valor_total_pago']:,.2f}")
        
        with col_est3:
            st.metric("Projetos Ativos", f"{resumo['projetos_ativos']:,}")
            st.caption(f"Arquivos: {resumo['arquivos_processados']:,}")

def mostrar_manutencao_automatica(conn):
    """Manutenção automática"""
    st.header("⚙️ Manutenção Automática")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📊 Status do Sistema")
        
        cursor = conn.cursor()
        
        # Tamanho do banco
        if os.path.exists('pot_gestao.db'):
            tamanho = os.path.getsize('pot_gestao.db') / 1024 / 1024
            st.info(f"**Tamanho do banco:** {tamanho:.2f} MB")
        
        # Contagens
        tabelas = ['beneficiarios', 'pagamentos', 'arquivos_processados', 'inconsistências']
        for tabela in tabelas:
            cursor.execute(f"SELECT COUNT(*) FROM {tabela}")
            count = cursor.fetchone()[0]
            st.metric(tabela.title().replace('_', ' '), f"{count:,}")
    
    with col2:
        st.subheader("🔧 Ferramentas")
        
        # Backup automático
        if st.button("💾 Criar Backup Automático", use_container_width=True):
            try:
                data_backup = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_file = f"backup_pot_{data_backup}.db"
                
                # Criar cópia do banco
                conn.backup(sqlite3.connect(backup_file))
                
                st.success(f"Backup criado: {backup_file}")
                
                # Oferecer download
                with open(backup_file, 'rb') as f:
                    st.download_button(
                        label="📥 Download Backup",
                        data=f,
                        file_name=backup_file,
                        mime="application/octet-stream",
                        use_container_width=True
                    )
                
                # Limpar arquivo temporário
                os.remove(backup_file)
                
            except Exception as e:
                st.error(f"Erro no backup: {str(e)}")
        
        # Limpeza automática
        if st.button("🧹 Limpeza Automática", use_container_width=True):
            try:
                cursor = conn.cursor()
                
                # Contar antes
                cursor.execute("SELECT COUNT(*) FROM pagamentos")
                antes = cursor.fetchone()[0]
                
                # Manter apenas últimos 12 meses
                limite = datetime.now() - timedelta(days=365)
                data_limite = limite.strftime('%Y-%m-%d')
                
                cursor.execute("DELETE FROM pagamentos WHERE data_processamento < ?", (data_limite,))
                cursor.execute("DELETE FROM arquivos_processados WHERE data_processamento < ?", (data_limite,))
                
                conn.commit()
                
                cursor.execute("SELECT COUNT(*) FROM pagamentos")
                depois = cursor.fetchone()[0]
                
                st.success(f"Limpeza concluída! {antes - depois} registros antigos removidos.")
                st.rerun()
                
            except Exception as e:
                st.error(f"Erro na limpeza: {str(e)}")
        
        # Otimização
        if st.button("⚡ Otimizar Banco", use_container_width=True):
            try:
                cursor = conn.cursor()
                cursor.execute("VACUUM")
                cursor.execute("ANALYZE")
                conn.commit()
                st.success("Banco otimizado com sucesso!")
            except Exception as e:
                st.error(f"Erro na otimização: {str(e)}")

# ========== MAIN ==========
def main():
    # Inicializar banco
    conn = init_database()
    
    if not conn:
        st.error("❌ Não foi possível inicializar o sistema.")
        return
    
    # Menu lateral
    st.sidebar.title("🤖 POT - Sistema Automático")
    st.sidebar.markdown("**Gestão Inteligente de Benefícios**")
    st.sidebar.markdown("---")
    
    # Opções
    menu = st.sidebar.radio(
        "Navegação",
        ["📊 Dashboard Automático", "📤 Importação Automática", "🔍 Consultas", "⚙️ Manutenção"],
        key="menu_auto"
    )
    
    # Páginas
    if menu == "📊 Dashboard Automático":
        mostrar_dashboard_automatico(conn)
    
    elif menu == "📤 Importação Automática":
        mostrar_importacao_automatica(conn)
    
    elif menu == "🔍 Consultas":
        mostrar_consultas_automaticas(conn)
    
    elif menu == "⚙️ Manutenção":
        mostrar_manutencao_automatica(conn)
    
    # Rodapé
    st.sidebar.markdown("---")
    st.sidebar.caption(f"🤖 Sistema Automático | {datetime.now().year}")
    st.sidebar.caption("✨ Detecção automática de períodos")
    st.sidebar.caption("💰 Cálculos automáticos")
    st.sidebar.caption("📊 Relatórios automáticos")
    
    conn.close()

if __name__ == "__main__":
    main()
