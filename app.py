import pandas as pd
import os
import re
from datetime import datetime
import streamlit as st
import warnings
import chardet
import numpy as np
import io
import traceback

warnings.filterwarnings('ignore')

# Configuração da página
st.set_page_config(
    page_title="Sistema POT - Monitoramento",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

class SistemaPOT:
    def __init__(self):
        self.df = None
        self.df_original = None
        self.dados_limpos = None
        self.dados_faltantes = None
        self.inconsistencias = None
        self.arquivo_processado = False
        self.nome_arquivo = ""
        self.total_pagamentos = 0
        self.coluna_valor_pagto = None
        self.log_processamento = []
    
    def log(self, mensagem):
        """Registra mensagem no log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_processamento.append(f"[{timestamp}] {mensagem}")
    
    def detectar_encoding(self, arquivo_path):
        """Detecta o encoding do arquivo"""
        try:
            with open(arquivo_path, 'rb') as f:
                raw_data = f.read(10000)
            resultado = chardet.detect(raw_data)
            encoding = resultado['encoding']
            confianca = resultado['confidence']
            self.log(f"Encoding detectado: {encoding} (confiança: {confianca:.2f})")
            return encoding if encoding else 'latin-1'
        except Exception as e:
            self.log(f"Erro na detecção de encoding: {e}")
            return 'latin-1'
    
    def tentar_encodings(self, arquivo_path):
        """Tenta diferentes encodings até encontrar um que funcione"""
        encodings = ['latin-1', 'iso-8859-1', 'cp1252', 'utf-8', 'utf-8-sig', 'cp850']
        
        for encoding in encodings:
            try:
                self.log(f"Tentando encoding: {encoding}")
                df = pd.read_csv(arquivo_path, delimiter=';', encoding=encoding, nrows=5, on_bad_lines='skip')
                if not df.empty and len(df.columns) > 1:
                    self.log(f"✅ Encoding funcionou: {encoding}")
                    return encoding
            except Exception as e:
                self.log(f"❌ Encoding {encoding} falhou: {str(e)[:50]}")
                continue
        
        self.log("❌ Nenhum encoding comum funcionou")
        return None
    
    def eh_data(self, valor_str):
        """Verifica se uma string parece ser uma data no formato brasileiro"""
        if pd.isna(valor_str) or not isinstance(valor_str, str):
            return False
        
        valor_str = str(valor_str).strip()
        
        # Verifica padrões comuns de data
        padroes_data = [
            r'^\d{1,2}/\d{1,2}/\d{4}$',  # DD/MM/AAAA
            r'^\d{1,2}-\d{1,2}-\d{4}$',  # DD-MM-AAAA
            r'^\d{4}-\d{1,2}-\d{1,2}$',  # AAAA-MM-DD
            r'^\d{1,2}/\d{1,2}/\d{2}$',  # DD/MM/AA
            r'^\d{1,2}-\d{1,2}-\d{2}$',  # DD-MM-AA
        ]
        
        for padrao in padroes_data:
            if re.match(padrao, valor_str):
                return True
        
        # Verifica se contém palavras relacionadas a data/mês/ano
        palavras_data = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 
                        'jul', 'ago', 'set', 'out', 'nov', 'dez',
                        'january', 'february', 'march', 'april', 'may', 'june',
                        'july', 'august', 'september', 'october', 'november', 'december']
        
        valor_lower = valor_str.lower()
        for palavra in palavras_data:
            if palavra in valor_lower:
                return True
        
        return False
    
    def converter_valor_monetario(self, valor_str):
        """Converte apenas valores monetários do formato brasileiro para float"""
        if pd.isna(valor_str) or valor_str == '' or str(valor_str).strip() == '':
            return 0.0
        
        try:
            # Se for um número, retorna direto
            if isinstance(valor_str, (int, float, np.number)):
                return float(valor_str)
            
            valor_str = str(valor_str).strip()
            
            # Verifica se é uma data - NÃO CONVERTE
            if self.eh_data(valor_str):
                return valor_str  # Mantém como string
            
            # Tenta converter direto para float
            try:
                return float(valor_str)
            except:
                pass
            
            # Remove símbolo de moeda
            valor_str = valor_str.replace('R$', '').replace(' ', '').strip()
            
            if valor_str == '':
                return 0.0
            
            # Verifica se tem ponto e vírgula como separador decimal
            valor_str = valor_str.replace(';', '.')
            
            # Formato brasileiro: 1.234,56
            if '.' in valor_str and ',' in valor_str:
                # Se tem milhares separados por ponto e decimal por vírgula
                if valor_str.count('.') == 1 and len(valor_str.split('.')[-1]) <= 2:
                    # Pode ser decimal simples (ex: 123.45)
                    try:
                        return float(valor_str)
                    except:
                        pass
                
                # Remove pontos de milhar e substitui vírgula por ponto
                partes = valor_str.split(',')
                if len(partes) == 2:
                    inteiro = partes[0].replace('.', '')
                    decimal = partes[1]
                    return float(f"{inteiro}.{decimal}")
            
            # Formato com vírgula decimal: 1234,56
            elif ',' in valor_str:
                # Verifica se a vírgula separa decimal
                partes = valor_str.split(',')
                if len(partes) == 2 and len(partes[1]) <= 2:
                    return float(valor_str.replace(',', '.'))
                else:
                    # Pode ser separador de milhar
                    return float(valor_str.replace(',', ''))
            
            # Formato com ponto: pode ser separador decimal ou de milhar
            elif '.' in valor_str:
                partes = valor_str.split('.')
                if len(partes) == 2 and len(partes[1]) <= 2:
                    # Ponto como separador decimal
                    return float(valor_str)
                else:
                    # Ponto como separador de milhar
                    return float(valor_str.replace('.', ''))
            
            else:
                return float(valor_str)
                
        except Exception as e:
            self.log(f"⚠️ Não foi possível converter '{str(valor_str)[:20]}' para valor monetário: {e}")
            return 0.0
    
    def processar_arquivo_streamlit(self, arquivo_upload):
        """Processa arquivo CSV de pagamentos do POT"""
        try:
            self.log_processamento = []
            self.log(f"Iniciando processamento do arquivo: {arquivo_upload.name}")
            
            temp_path = f"temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            with open(temp_path, 'wb') as f:
                f.write(arquivo_upload.getvalue())
            
            self.log(f"Arquivo salvo temporariamente em: {temp_path}")
            
            encoding = self.tentar_encodings(temp_path)
            if encoding is None:
                encoding = self.detectar_encoding(temp_path) or 'latin-1'
            
            self.log(f"Encoding selecionado para leitura: {encoding}")
            
            try:
                with open(temp_path, 'r', encoding=encoding, errors='replace') as f:
                    linhas = f.readlines()
                
                self.log(f"Arquivo lido como texto: {len(linhas)} linhas")
                
                if len(linhas) == 0:
                    self.log("❌ Arquivo vazio")
                    return False
                
                self.log(f"Primeira linha: {linhas[0][:100]}...")
                if len(linhas) > 1:
                    self.log(f"Segunda linha: {linhas[1][:100]}...")
                
                self.df = pd.read_csv(
                    temp_path, 
                    delimiter=';', 
                    encoding=encoding, 
                    on_bad_lines='skip',
                    dtype=str,
                    quoting=3,
                    low_memory=False
                )
                
                self.log(f"✅ Arquivo lido com pandas. Shape: {self.df.shape}")
                
            except Exception as e:
                self.log(f"❌ Erro ao ler com pandas: {e}")
                try:
                    if len(linhas) > 0:
                        colunas = linhas[0].strip().split(';')
                        dados = []
                        for i, linha in enumerate(linhas[1:], 1):
                            try:
                                valores = linha.strip().split(';')
                                if len(valores) >= len(colunas) - 1:
                                    while len(valores) < len(colunas):
                                        valores.append('')
                                    dados.append(valores)
                                else:
                                    self.log(f"Linha {i} ignorada: colunas inconsistentes")
                            except Exception as e2:
                                self.log(f"Erro na linha {i}: {e2}")
                        
                        self.df = pd.DataFrame(dados, columns=colunas)
                        self.log(f"DataFrame criado manualmente. Shape: {self.df.shape}")
                    else:
                        self.log("❌ Nenhuma linha válida encontrada")
                        return False
                except Exception as e2:
                    self.log(f"❌ Erro crítico na leitura: {e2}")
                    return False
            
            self.df_original = self.df.copy()
            
            if os.path.exists(temp_path):
                os.remove(temp_path)
            
            self._limpar_dados()
            self._analisar_dados_faltantes()
            self._analisar_inconsistencias()
            self._calcular_estatisticas()
            
            self.arquivo_processado = True
            self.nome_arquivo = arquivo_upload.name
            
            self.log("✅ Processamento concluído com sucesso!")
            return True
            
        except Exception as e:
            self.log(f"❌ ERRO CRÍTICO NO PROCESSAMENTO: {e}")
            self.log(f"Traceback: {traceback.format_exc()}")
            return False
    
    def _limpar_dados(self):
        """Limpa e prepara os dados para análise"""
        self.log("Iniciando limpeza de dados...")
        
        if self.df is None or self.df.empty:
            self.log("❌ DataFrame vazio ou não carregado")
            return
        
        df_limpo = self.df.copy()
        linhas_iniciais = len(df_limpo)
        self.log(f"Dados iniciais: {linhas_iniciais} linhas, {len(df_limpo.columns)} colunas")
        
        # Remove linhas totalmente vazias
        df_limpo = df_limpo.dropna(how='all')
        linhas_apos_vazias = len(df_limpo)
        self.log(f"Removidas {linhas_iniciais - linhas_apos_vazias} linhas totalmente vazias")
        
        # Normaliza nomes das colunas
        colunas_originais = list(df_limpo.columns)
        self.log(f"Colunas originais: {colunas_originais}")
        
        mapeamento_colunas = {}
        for col in df_limpo.columns:
            if pd.isna(col) or str(col).strip() == '':
                col_novo = 'coluna_sem_nome'
            else:
                col_novo = str(col).strip().lower()
                col_novo = re.sub(r'[^a-z0-9_]', '_', col_novo)
                col_novo = (col_novo
                           .replace('á', 'a').replace('é', 'e').replace('í', 'i')
                           .replace('ó', 'o').replace('ú', 'u').replace('â', 'a')
                           .replace('ê', 'e').replace('î', 'i').replace('ô', 'o')
                           .replace('û', 'u').replace('ã', 'a').replace('õ', 'o')
                           .replace('ç', 'c'))
            
            mapeamento_colunas[col] = col_novo
        
        df_limpo = df_limpo.rename(columns=mapeamento_colunas)
        self.log(f"Colunas após renomeação: {list(df_limpo.columns)}")
        
        # Identifica coluna de valor
        possiveis_nomes_valor = [
            'valor_pagto', 'valor_pagamento', 'valor_total', 'valor', 
            'pagto', 'pagamento', 'total', 'valorpagto', 'valor_pgto',
            'valorpagamento', 'vlr_pagto', 'vlr_pagamento'
        ]
        
        self.coluna_valor_pagto = None
        for nome in possiveis_nomes_valor:
            if nome in df_limpo.columns:
                self.coluna_valor_pagto = nome
                self.log(f"✅ Coluna de valor identificada: {nome}")
                break
        
        if self.coluna_valor_pagto is None:
            for col in df_limpo.columns:
                col_lower = col.lower()
                if any(termo in col_lower for termo in ['val', 'pag', 'total', 'vlr']):
                    self.coluna_valor_pagto = col
                    self.log(f"✅ Coluna de valor identificada por padrão: {col}")
                    break
        
        if self.coluna_valor_pagto is None:
            self.log("⚠️ Coluna de valor não identificada automaticamente")
            # Tenta inferir pela análise dos dados
            for col in df_limpo.columns:
                try:
                    amostra = df_limpo[col].dropna().head(10)
                    if len(amostra) > 0:
                        # Tenta converter alguns valores
                        valores_convertidos = []
                        for val in amostra:
                            convertido = self.converter_valor_monetario(val)
                            if convertido != 0.0 and not self.eh_data(str(val)):
                                valores_convertidos.append(convertido)
                        
                        if len(valores_convertidos) > 5 and any(v > 0 for v in valores_convertidos):
                            self.coluna_valor_pagto = col
                            self.log(f"✅ Coluna de valor inferida: {col}")
                            break
                except:
                    continue
        
        self.log(f"Coluna de valor final: {self.coluna_valor_pagto}")
        
        # Analisa cada coluna e converte apenas se for valor monetário
        colunas_convertidas = []
        colunas_data = []
        colunas_texto = []
        
        for coluna in df_limpo.columns:
            # Verifica se a coluna parece conter dados textuais
            coluna_lower = coluna.lower()
            if any(termo in coluna_lower for termo in ['nome', 'distrito', 'rg', 'projeto', 'cartao', 
                                                      'agencia', 'endereco', 'cidade', 'estado', 
                                                      'cpf', 'cnpj', 'telefone', 'email', 'banco',
                                                      'conta', 'descricao', 'observacao']):
                colunas_texto.append(coluna)
                continue
            
            # Amostra para análise
            amostra = df_limpo[coluna].dropna().head(20)
            if len(amostra) == 0:
                continue
            
            # Verifica se é coluna de data
            valores_data = 0
            valores_monetarios = 0
            
            for val in amostra:
                if self.eh_data(str(val)):
                    valores_data += 1
                else:
                    # Tenta converter para monetário
                    convertido = self.converter_valor_monetario(val)
                    if convertido != 0.0 and convertido != str(val):
                        valores_monetarios += 1
            
            # Decisão baseada na análise
            if valores_data > valores_monetarios and valores_data > len(amostra) * 0.3:
                # Principalmente datas
                colunas_data.append(coluna)
                self.log(f"Coluna '{coluna}' identificada como DATA")
            elif valores_monetarios > len(amostra) * 0.3 or coluna == self.coluna_valor_pagto:
                # Principalmente valores monetários
                try:
                    valores_originais = df_limpo[coluna].head(3).tolist()
                    df_limpo[coluna] = df_limpo[coluna].apply(self.converter_valor_monetario)
                    valores_convertidos = df_limpo[coluna].head(3).tolist()
                    
                    colunas_convertidas.append(coluna)
                    self.log(f"Coluna convertida para monetário: {coluna}")
                except Exception as e:
                    self.log(f"Erro ao converter coluna {coluna} para monetário: {e}")
            else:
                # Mantém como texto
                colunas_texto.append(coluna)
        
        self.log(f"Total de colunas convertidas para monetário: {len(colunas_convertidas)}")
        self.log(f"Total de colunas identificadas como data: {len(colunas_data)}")
        self.log(f"Total de colunas mantidas como texto: {len(colunas_texto)}")
        
        # Remove registros com valor ≤ 0 na coluna de pagamento
        if self.coluna_valor_pagto and self.coluna_valor_pagto in df_limpo.columns:
            antes = len(df_limpo)
            df_limpo = df_limpo[df_limpo[self.coluna_valor_pagto] > 0]
            depois = len(df_limpo)
            removidos = antes - depois
            if removidos > 0:
                self.log(f"Removidos {removidos} registros com valor ≤ 0 na coluna {self.coluna_valor_pagto}")
        
        self.dados_limpos = df_limpo
        self.log(f"✅ Dados limpos: {len(df_limpo)} linhas, {len(df_limpo.columns)} colunas")
    
    def _analisar_dados_faltantes(self):
        """Analisa dados faltantes no dataset"""
        self.log("Analisando dados faltantes...")
        
        if self.dados_limpos is None or self.dados_limpos.empty:
            self.log("❌ Nenhum dado para análise de faltantes")
            return
        
        faltantes_por_coluna = self.dados_limpos.isnull().sum()
        percentual_faltantes = (faltantes_por_coluna / len(self.dados_limpos)) * 100
        
        self.dados_faltantes = pd.DataFrame({
            'Coluna': faltantes_por_coluna.index,
            'Valores_Faltantes': faltantes_por_coluna.values,
            'Percentual_Faltante': percentual_faltantes.values.round(2),
            'Tipo_Dado': [str(dtype) for dtype in self.dados_limpos.dtypes.values]
        })
        
        self.log(f"Dados faltantes analisados: {len(faltantes_por_coluna)} colunas")
        
        # Identifica linhas com faltantes críticos
        colunas_criticas = []
        if self.coluna_valor_pagto:
            colunas_criticas.append(self.coluna_valor_pagto)
        
        for col in ['nome', 'agencia', 'cpf', 'cnpj']:
            if col in self.dados_limpos.columns:
                colunas_criticas.append(col)
        
        if colunas_criticas:
            mask = self.dados_limpos[colunas_criticas].isnull().any(axis=1)
            self.linhas_com_faltantes_criticos = self.dados_limpos[mask].copy()
            self.log(f"Linhas com faltantes críticos: {len(self.linhas_com_faltantes_criticos)}")
        else:
            self.linhas_com_faltantes_criticos = pd.DataFrame()
            self.log("Nenhuma coluna crítica identificada")
    
    def _analisar_inconsistencias(self):
        """Analisa inconsistências nos dados"""
        self.log("Analisando inconsistências...")
        
        if self.dados_limpos is None or self.dados_limpos.empty:
            self.log("❌ Nenhum dado para análise de inconsistências")
            return
        
        inconsistencias = []
        
        # Verifica valores negativos na coluna de pagamento
        if self.coluna_valor_pagto and self.coluna_valor_pagto in self.dados_limpos.columns:
            negativos = self.dados_limpos[self.dados_limpos[self.coluna_valor_pagto] < 0]
            if len(negativos) > 0:
                inconsistencias.append({
                    'Tipo': 'Valores Negativos',
                    'Coluna': self.coluna_valor_pagto,
                    'Quantidade': len(negativos),
                    'Exemplo': f"Linhas: {list(negativos.index[:3]) if len(negativos) > 0 else 'N/A'}",
                    'Descrição': 'Valores de pagamento negativos'
                })
                self.log(f"Valores negativos encontrados: {len(negativos)}")
        
        # Verifica valores zerados na coluna de pagamento
        if self.coluna_valor_pagto and self.coluna_valor_pagto in self.dados_limpos.columns:
            zerados = self.dados_limpos[self.dados_limpos[self.coluna_valor_pagto] == 0]
            if len(zerados) > 0:
                inconsistencias.append({
                    'Tipo': 'Valores Zerados',
                    'Coluna': self.coluna_valor_pagto,
                    'Quantidade': len(zerados),
                    'Exemplo': f"Linhas: {list(zerados.index[:3]) if len(zerados) > 0 else 'N/A'}",
                    'Descrição': 'Valores de pagamento zerados'
                })
                self.log(f"Valores zerados encontrados: {len(zerados)}")
        
        # Verifica valores muito altos (possíveis erros)
        if self.coluna_valor_pagto and self.coluna_valor_pagto in self.dados_limpos.columns:
            valores = self.dados_limpos[self.coluna_valor_pagto]
            if len(valores) > 0:
                media = valores.mean()
                desvio = valores.std()
                limite_superior = media + 3 * desvio
                valores_extremos = self.dados_limpos[valores > limite_superior]
                if len(valores_extremos) > 0:
                    inconsistencias.append({
                        'Tipo': 'Valores Extremamente Altos',
                        'Coluna': self.coluna_valor_pagto,
                        'Quantidade': len(valores_extremos),
                        'Exemplo': f"Acima de R$ {limite_superior:,.2f}",
                        'Descrição': 'Valores muito acima da média (possível erro)'
                    })
                    self.log(f"Valores extremamente altos: {len(valores_extremos)}")
        
        # Verifica dados críticos faltantes
        colunas_criticas = ['nome', 'agencia', 'cpf', 'cnpj']
        for coluna in colunas_criticas:
            if coluna in self.dados_limpos.columns:
                faltantes = self.dados_limpos[self.dados_limpos[coluna].isnull()]
                if len(faltantes) > 0:
                    inconsistencias.append({
                        'Tipo': f'{coluna.upper()} Faltante',
                        'Coluna': coluna,
                        'Quantidade': len(faltantes),
                        'Exemplo': f"{len(faltantes)} registros sem {coluna}",
                        'Descrição': f'{coluna} não informado'
                    })
        
        if inconsistencias:
            self.inconsistencias = pd.DataFrame(inconsistencias)
            self.log(f"Inconsistências detectadas: {len(inconsistencias)} tipos")
        else:
            self.inconsistencias = pd.DataFrame()
            self.log("Nenhuma inconsistência detectada")
    
    def _calcular_estatisticas(self):
        """Calcula estatísticas dos dados"""
        self.log("Calculando estatísticas...")
        
        if self.dados_limpos is None or len(self.dados_limpos) == 0:
            self.log("❌ Nenhum dado para cálculo de estatísticas")
            return
        
        if self.coluna_valor_pagto and self.coluna_valor_pagto in self.dados_limpos.columns:
            try:
                valores = self.dados_limpos[self.coluna_valor_pagto]
                
                # Calcula usando pandas
                self.total_pagamentos = valores.sum()
                
                # Verifica com numpy para validação
                total_numpy = np.nansum(valores.values)
                
                self.log(f"💰 Valor total calculado (pandas): R$ {self.total_pagamentos:,.2f}")
                self.log(f"💰 Valor total calculado (numpy): R$ {total_numpy:,.2f}")
                
                # Se houver diferença significativa, usa a média
                if abs(self.total_pagamentos - total_numpy) > 0.01:
                    self.log("⚠️ Diferença detectada entre métodos de soma!")
                    self.total_pagamentos = (self.total_pagamentos + total_numpy) / 2
                    self.log(f"💰 Valor total ajustado: R$ {self.total_pagamentos:,.2f}")
                
                # Estatísticas detalhadas
                self.log(f"  - Média: R$ {valores.mean():,.2f}")
                self.log(f"  - Mínimo: R$ {valores.min():,.2f}")
                self.log(f"  - Máximo: R$ {valores.max():,.2f}")
                self.log(f"  - Mediana: R$ {valores.median():,.2f}")
                self.log(f"  - Desvio Padrão: R$ {valores.std():,.2f}")
                
            except Exception as e:
                self.log(f"Erro ao calcular estatísticas: {e}")
                self.total_pagamentos = 0
        else:
            self.log("⚠️ Coluna de valor não disponível para cálculo")
            self.total_pagamentos = 0
    
    def mostrar_log(self):
        """Mostra log de processamento"""
        if self.log_processamento:
            with st.expander("📝 LOG DE PROCESSAMENTO", expanded=True):
                for entry in self.log_processamento:
                    if "❌" in entry or "ERRO" in entry.upper():
                        st.error(entry)
                    elif "⚠️" in entry or "AVISO" in entry.upper():
                        st.warning(entry)
                    elif "✅" in entry or "SUCESSO" in entry.upper():
                        st.success(entry)
                    else:
                        st.info(entry)
    
    def mostrar_dados_originais(self):
        """Mostra dados originais para debug"""
        if self.df_original is not None and not self.df_original.empty:
            with st.expander("🔍 DADOS ORIGINAIS (DEBUG)", expanded=False):
                st.write(f"**Shape:** {self.df_original.shape}")
                st.write(f"**Colunas:** {list(self.df_original.columns)}")
                st.dataframe(self.df_original.head(5), use_container_width=True)

# ==============================================
# FUNÇÃO PRINCIPAL
# ==============================================

def main():
    """Função principal do aplicativo Streamlit"""
    
    st.title("💰 SISTEMA DE MONITORAMENTO DE PAGAMENTOS - POT")
    st.markdown("---")
    
    # Inicializar sistema
    if 'sistema' not in st.session_state:
        st.session_state['sistema'] = SistemaPOT()
    
    sistema = st.session_state['sistema']
    
    # Sidebar
    with st.sidebar:
        st.header("📁 UPLOAD DO ARQUIVO")
        
        arquivo = st.file_uploader(
            "Selecione o arquivo CSV",
            type=['csv'],
            help="Arquivo CSV com dados de pagamentos (delimitador: ponto e vírgula)"
        )
        
        if arquivo is not None:
            st.info(f"📄 **Arquivo:** {arquivo.name}")
            st.info(f"📊 **Tamanho:** {arquivo.size / 1024:.1f} KB")
            
            st.markdown("---")
            st.header("⚙️ OPÇÕES")
            mostrar_log = st.checkbox("📝 Mostrar log de processamento", value=True)
            mostrar_debug = st.checkbox("🔍 Mostrar dados originais (debug)", value=False)
            
            if st.button("🚀 PROCESSAR ARQUIVO", type="primary", use_container_width=True):
                with st.spinner("Processando arquivo... Por favor, aguarde."):
                    sucesso = sistema.processar_arquivo_streamlit(arquivo)
                    if sucesso:
                        st.session_state['arquivo_processado'] = True
                        st.session_state['mostrar_log'] = mostrar_log
                        st.session_state['mostrar_debug'] = mostrar_debug
                        st.session_state['sistema'] = sistema
                        st.success("✅ Arquivo processado com sucesso!")
                        st.rerun()
                    else:
                        st.error("❌ Erro ao processar arquivo. Verifique o log.")
            
            if 'arquivo_processado' in st.session_state and st.session_state['arquivo_processado']:
                st.markdown("---")
                if st.button("🔄 PROCESSAR OUTRO ARQUIVO", use_container_width=True):
                    st.session_state.clear()
                    st.rerun()
    
    # Área principal
    if 'arquivo_processado' in st.session_state and st.session_state['arquivo_processado']:
        sistema = st.session_state['sistema']
        
        if sistema.arquivo_processado:
            
            if st.session_state.get('mostrar_log', False):
                sistema.mostrar_log()
            
            if st.session_state.get('mostrar_debug', False):
                sistema.mostrar_dados_originais()
            
            if sistema.dados_limpos is None or len(sistema.dados_limpos) == 0:
                st.error("""
                ❌ **ERRO: NENHUM DADO VÁLIDO PROCESSADO**
                
                **Possíveis causas:**
                1. Arquivo vazio ou corrompido
                2. Encoding não compatível
                3. Delimitador incorreto (não é ponto e vírgula)
                4. Formato de dados inválido
                """)
                
                if sistema.df_original is not None:
                    st.write(f"Arquivo original tem {len(sistema.df_original)} linhas")
                    if len(sistema.df_original) > 0:
                        st.write("Primeiras linhas do arquivo original:")
                        st.dataframe(sistema.df_original.head(3))
                
                return
            
            # RESUMO EXECUTIVO
            st.header("📊 RESUMO EXECUTIVO")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("📄 TOTAL DE REGISTROS", f"{len(sistema.dados_limpos):,}")
            
            with col2:
                if sistema.coluna_valor_pagto:
                    valor_total = sistema.total_pagamentos
                    st.metric("💰 VALOR TOTAL", f"R$ {valor_total:,.2f}")
                else:
                    st.metric("💰 VALOR TOTAL", "N/A")
            
            with col3:
                if sistema.dados_faltantes is not None:
                    total_faltantes = sistema.dados_faltantes['Valores_Faltantes'].sum()
                    st.metric("⚠️ DADOS FALTANTES", f"{total_faltantes:,}")
                else:
                    st.metric("⚠️ DADOS FALTANTES", "0")
            
            with col4:
                if sistema.inconsistencias is not None and not sistema.inconsistencias.empty:
                    total_inconsistencias = sistema.inconsistencias['Quantidade'].sum()
                    st.metric("🚨 INCONSISTÊNCIAS", f"{total_inconsistencias:,}")
                else:
                    st.metric("🚨 INCONSISTÊNCIAS", "0")
            
            if sistema.coluna_valor_pagto:
                st.info(f"**Coluna de valor identificada:** `{sistema.coluna_valor_pagto}`")
                
                valores = sistema.dados_limpos[sistema.coluna_valor_pagto]
                col_stat1, col_stat2, col_stat3 = st.columns(3)
                
                with col_stat1:
                    st.metric("📊 Valor Médio", f"R$ {valores.mean():,.2f}")
                
                with col_stat2:
                    st.metric("⬇️ Valor Mínimo", f"R$ {valores.min():,.2f}")
                
                with col_stat3:
                    st.metric("⬆️ Valor Máximo", f"R$ {valores.max():,.2f}")
            
            st.markdown("---")
            
            # DADOS FALTANTES
            st.header("🔍 ANÁLISE DE DADOS FALTANTES")
            
            if sistema.dados_faltantes is not None and not sistema.dados_faltantes.empty:
                dados_faltantes_filtrados = sistema.dados_faltantes[
                    sistema.dados_faltantes['Valores_Faltantes'] > 0
                ].copy()
                
                if not dados_faltantes_filtrados.empty:
                    st.subheader("📋 DADOS FALTANTES POR COLUNA")
                    
                    dados_faltantes_filtrados['Percentual_Faltante'] = dados_faltantes_filtrados['Percentual_Faltante'].apply(
                        lambda x: f"{x}%"
                    )
                    
                    st.dataframe(
                        dados_faltantes_filtrados[['Coluna', 'Valores_Faltantes', 'Percentual_Faltante', 'Tipo_Dado']],
                        use_container_width=True,
                        height=300
                    )
                    
                    if hasattr(sistema, 'linhas_com_faltantes_criticos') and not sistema.linhas_com_faltantes_criticos.empty:
                        st.subheader("🚨 LINHAS COM FALTANTES CRÍTICOS")
                        st.dataframe(
                            sistema.linhas_com_faltantes_criticos,
                            use_container_width=True,
                            height=200
                        )
                else:
                    st.success("✅ NENHUM DADO FALTANTE DETECTADO!")
            else:
                st.success("✅ NENHUM DADO FALTANTE DETECTADO!")
            
            st.markdown("---")
            
            # INCONSISTÊNCIAS
            st.header("🚨 ANÁLISE DE INCONSISTÊNCIAS")
            
            if sistema.inconsistencias is not None and not sistema.inconsistencias.empty:
                st.subheader("📋 TIPOS DE INCONSISTÊNCIAS DETECTADAS")
                
                st.dataframe(
                    sistema.inconsistencias,
                    use_container_width=True,
                    height=300
                )
            else:
                st.success("✅ NENHUMA INCONSISTÊNCIA GRAVE DETECTADA!")
            
            st.markdown("---")
            
            # VISUALIZAÇÃO DOS DADOS
            st.header("👀 VISUALIZAÇÃO DOS DADOS PROCESSADOS")
            
            tab1, tab2 = st.tabs(["📋 TABELA DE DADOS", "📊 ESTATÍSTICAS"])
            
            with tab1:
                col_vis1, col_vis2 = st.columns(2)
                
                with col_vis1:
                    colunas_disponiveis = sistema.dados_limpos.columns.tolist()
                    colunas_selecionadas = st.multiselect(
                        "Selecione as colunas para visualizar:",
                        options=colunas_disponiveis,
                        default=colunas_disponiveis[:min(6, len(colunas_disponiveis))]
                    )
                
                with col_vis2:
                    num_linhas = st.slider(
                        "Número de linhas para mostrar:",
                        min_value=5,
                        max_value=100,
                        value=20,
                        step=5
                    )
                
                if colunas_selecionadas:
                    dados_visiveis = sistema.dados_limpos[colunas_selecionadas].head(num_linhas).copy()
                    
                    # Formata valores monetários
                    if sistema.coluna_valor_pagto and sistema.coluna_valor_pagto in dados_visiveis.columns:
                        dados_visiveis[sistema.coluna_valor_pagto] = dados_visiveis[sistema.coluna_valor_pagto].apply(
                            lambda x: f"R$ {x:,.2f}" if pd.notna(x) and isinstance(x, (int, float, np.number)) else str(x)
                        )
                    
                    st.dataframe(
                        dados_visiveis,
                        use_container_width=True,
                        height=400
                    )
            
            with tab2:
                if sistema.coluna_valor_pagto:
                    valores = sistema.dados_limpos[sistema.coluna_valor_pagto]
                    stats = valores.describe()
                    
                    col_stats1, col_stats2 = st.columns(2)
                    
                    with col_stats1:
                        st.markdown("**📈 ESTATÍSTICAS DESCRITIVAS**")
                        
                        stats_df = pd.DataFrame({
                            'Estatística': ['Mínimo', '25% (Q1)', 'Mediana', '75% (Q3)', 'Máximo', 'Média', 'Desvio Padrão'],
                            'Valor': [
                                f"R$ {stats.get('min', 0):,.2f}",
                                f"R$ {stats.get('25%', 0):,.2f}",
                                f"R$ {stats.get('50%', 0):,.2f}",
                                f"R$ {stats.get('75%', 0):,.2f}",
                                f"R$ {stats.get('max', 0):,.2f}",
                                f"R$ {stats.get('mean', 0):,.2f}",
                                f"R$ {stats.get('std', 0):,.2f}"
                            ]
                        })
                        st.dataframe(stats_df, use_container_width=True, hide_index=True)
            
            st.markdown("---")
            
            # EXPORTAÇÃO
            st.header("📥 EXPORTAÇÃO DE RELATÓRIOS")
            
            col_exp1, col_exp2, col_exp3 = st.columns(3)
            
            with col_exp1:
                if sistema.dados_limpos is not None:
                    csv_dados = sistema.dados_limpos.to_csv(index=False, sep=';', encoding='utf-8')
                    st.download_button(
                        label="📋 DADOS PROCESSADOS (CSV)",
                        data=csv_dados,
                        file_name=f"dados_processados_pot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
            
            with col_exp2:
                if sistema.inconsistencias is not None and not sistema.inconsistencias.empty:
                    csv_incon = sistema.inconsistencias.to_csv(index=False, sep=';', encoding='utf-8')
                    st.download_button(
                        label="🚨 INCONSISTÊNCIAS (CSV)",
                        data=csv_incon,
                        file_name=f"inconsistencias_pot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
            
            with col_exp3:
                if sistema.dados_faltantes is not None and not sistema.dados_faltantes.empty:
                    csv_faltantes = sistema.dados_faltantes.to_csv(index=False, sep=';', encoding='utf-8')
                    st.download_button(
                        label="⚠️ DADOS FALTANTES (CSV)",
                        data=csv_faltantes,
                        file_name=f"dados_faltantes_pot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
        
        else:
            st.error("❌ FALHA NO PROCESSAMENTO DO ARQUIVO")
            sistema.mostrar_log()
    else:
        # Tela inicial
        st.markdown("""
        # 🚀 SISTEMA DE MONITORAMENTO DE PAGAMENTOS - POT
        
        ### 📋 **FUNCIONALIDADES:**
        
        ✅ **PROCESSAMENTO ROBUSTO** com múltiplos encodings
        ✅ **ANÁLISE DE DADOS FALTANTES** com tabelas detalhadas
        ✅ **DETECÇÃO DE INCONSISTÊNCIAS** automática
        ✅ **CÁLCULO PRECISO** de valores totais
        ✅ **EXPORTAÇÃO** em formato CSV
        ✅ **DETECÇÃO INTELIGENTE** de colunas (datas, valores, textos)
        
        ### 📁 **COMO USAR:**
        
        1. **Faça upload** do arquivo CSV na barra lateral
        2. **Clique em "Processar Arquivo"**
        3. **Analise** os dados faltantes e inconsistências
        4. **Exporte** os relatórios para correção
        """)
    
    # Rodapé
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: gray; padding: 20px;'>
        <strong>💰 SISTEMA POT - MONITORAMENTO DE PAGAMENTOS</strong><br>
        Versão 2.0 • Processamento Robusto • Análise Inteligente
        </div>
        """,
        unsafe_allow_html=True
    )

# ==============================================
# EXECUÇÃO PRINCIPAL
# ==============================================

if __name__ == "__main__":
    main()
