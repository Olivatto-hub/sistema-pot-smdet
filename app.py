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
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

warnings.filterwarnings('ignore')

# Configuração da página
st.set_page_config(
    page_title="Sistema POT - Monitoramento Completo",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

class SistemaPOTComDebug:
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
        self.relatorio_executivo = {}
        self.log_processamento = []
        
    def log(self, mensagem):
        """Registra mensagem no log de processamento"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_processamento.append(f"[{timestamp}] {mensagem}")
        print(f"[LOG] {mensagem}")
    
    def detectar_encoding(self, arquivo_path):
        """Detecta o encoding do arquivo"""
        try:
            self.log(f"Detectando encoding do arquivo: {arquivo_path}")
            with open(arquivo_path, 'rb') as f:
                raw_data = f.read(10000)
            
            resultado = chardet.detect(raw_data)
            encoding = resultado['encoding']
            confianca = resultado['confidence']
            
            self.log(f"Encoding detectado: {encoding} (confiança: {confianca:.2f})")
            
            if encoding is None:
                self.log("Encoding não detectado, usando latin-1")
                return 'latin-1'
            
            encoding_map = {
                'ISO-8859-1': 'latin-1',
                'Windows-1252': 'cp1252',
                'ascii': 'utf-8',
                'UTF-8-SIG': 'utf-8',
                'UTF-8': 'utf-8'
            }
            
            encoding_final = encoding_map.get(encoding, encoding)
            self.log(f"Encoding final para uso: {encoding_final}")
            return encoding_final
            
        except Exception as e:
            self.log(f"Erro na detecção de encoding: {str(e)[:100]}")
            return 'latin-1'
    
    def tentar_encodings(self, arquivo_path):
        """Tenta diferentes encodings até encontrar um que funcione"""
        self.log(f"Tentando diferentes encodings para: {arquivo_path}")
        
        encodings_para_tentar = [
            'latin-1', 'iso-8859-1', 'cp1252', 'utf-8', 'utf-8-sig', 'cp850'
        ]
        
        for encoding in encodings_para_tentar:
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
    
    def converter_valor(self, valor_str):
        """Converte valores monetários do formato brasileiro para float"""
        if pd.isna(valor_str) or valor_str == '' or str(valor_str).strip() == '':
            return 0.0
        
        try:
            # Se já for número, retornar direto
            if isinstance(valor_str, (int, float)):
                return float(valor_str)
            
            valor_str = str(valor_str).strip()
            
            # Se já for float como string
            try:
                return float(valor_str)
            except:
                pass
            
            # Remover R$ e espaços
            valor_str = valor_str.replace('R$', '').replace(' ', '').strip()
            
            if valor_str == '':
                return 0.0
            
            # Verificar se tem vírgula como separador decimal
            if ',' in valor_str and '.' in valor_str:
                # Formato: 1.593,90
                # Remover pontos de milhar
                partes = valor_str.split(',')
                if len(partes) == 2:
                    inteiro = partes[0].replace('.', '')
                    return float(f"{inteiro}.{partes[1]}")
            
            elif ',' in valor_str:
                # Formato: 1593,90
                return float(valor_str.replace(',', '.'))
            
            # Tentar converter como está
            return float(valor_str)
                
        except Exception as e:
            self.log(f"Erro ao converter valor '{valor_str[:20]}': {str(e)}")
            return 0.0
    
    def processar_arquivo_streamlit(self, arquivo_upload):
        """Processa arquivo CSV de pagamentos do POT"""
        try:
            self.log_processamento = []  # Limpar log
            self.log(f"Iniciando processamento do arquivo: {arquivo_upload.name}")
            
            # Salvar arquivo temporariamente
            temp_path = f"temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            with open(temp_path, 'wb') as f:
                f.write(arquivo_upload.getvalue())
            
            self.log(f"Arquivo salvo temporariamente em: {temp_path}")
            
            # Detectar encoding
            encoding = self.tentar_encodings(temp_path)
            if encoding is None:
                encoding = self.detectar_encoding(temp_path) or 'latin-1'
            
            self.log(f"Encoding selecionado para leitura: {encoding}")
            
            # Ler arquivo
            try:
                self.df = pd.read_csv(
                    temp_path, 
                    delimiter=';', 
                    encoding=encoding, 
                    on_bad_lines='skip',
                    dtype=str  # Ler tudo como string inicialmente
                )
                self.log(f"✅ Arquivo lido com sucesso. Shape: {self.df.shape}")
            except Exception as e:
                self.log(f"❌ Erro ao ler arquivo: {str(e)}")
                # Tentar ler linha por linha
                try:
                    with open(temp_path, 'r', encoding=encoding, errors='replace') as f:
                        linhas = f.readlines()
                    
                    self.log(f"Arquivo lido linha por linha: {len(linhas)} linhas")
                    
                    # Tentar criar DataFrame manualmente
                    if len(linhas) > 0:
                        colunas = linhas[0].strip().split(';')
                        dados = []
                        for i, linha in enumerate(linhas[1:], 1):
                            try:
                                valores = linha.strip().split(';')
                                if len(valores) == len(colunas):
                                    dados.append(valores)
                            except:
                                self.log(f"Linha {i} ignorada: {linha[:50]}")
                        
                        self.df = pd.DataFrame(dados, columns=colunas)
                        self.log(f"DataFrame criado manualmente. Shape: {self.df.shape}")
                except Exception as e2:
                    self.log(f"❌ Erro crítico na leitura: {str(e2)}")
                    raise
            
            # Salvar cópia original para debug
            self.df_original = self.df.copy()
            
            # Limpar arquivo temporário
            if os.path.exists(temp_path):
                os.remove(temp_path)
            
            # Processar dados
            self._limpar_dados()
            self._analisar_dados_faltantes()
            self._analisar_inconsistencias()
            self._calcular_estatisticas()
            self._gerar_relatorio_executivo()
            
            self.arquivo_processado = True
            self.nome_arquivo = arquivo_upload.name
            
            self.log("✅ Processamento concluído com sucesso!")
            return True
            
        except Exception as e:
            self.log(f"❌ ERRO CRÍTICO NO PROCESSAMENTO: {str(e)}")
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
        
        # Remover linhas totalmente vazias
        df_limpo = df_limpo.dropna(how='all')
        linhas_apos_vazias = len(df_limpo)
        self.log(f"Removidas {linhas_iniciais - linhas_apos_vazias} linhas totalmente vazias")
        
        # Mostrar colunas originais
        self.log(f"Colunas originais: {list(df_limpo.columns)}")
        
        # Padronizar nomes das colunas
        mapeamento_colunas = {}
        for col in df_limpo.columns:
            if pd.isna(col):
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
        
        # IDENTIFICAR COLUNA DE VALOR DE PAGAMENTO
        possiveis_nomes_valor = [
            'valor_pagto', 'valor_pagamento', 'valor_total', 'valor', 
            'pagto', 'pagamento', 'total', 'valorpagto', 'valor_pgto'
        ]
        
        self.coluna_valor_pagto = None
        for nome in possiveis_nomes_valor:
            if nome in df_limpo.columns:
                self.coluna_valor_pagto = nome
                self.log(f"Coluna de valor identificada: {nome}")
                break
        
        if self.coluna_valor_pagto is None:
            # Procurar por padrões nas colunas
            for col in df_limpo.columns:
                col_lower = col.lower()
                if any(termo in col_lower for termo in ['val', 'pag', 'total']):
                    self.coluna_valor_pagto = col
                    self.log(f"Coluna de valor identificada por padrão: {col}")
                    break
        
        if self.coluna_valor_pagto is None:
            self.log("⚠️ Coluna de valor não identificada automaticamente")
            # Usar a primeira coluna que parece numérica
            for col in df_limpo.columns:
                try:
                    # Tentar converter amostra
                    amostra = df_limpo[col].dropna().head(10)
                    if len(amostra) > 0:
                        valores = amostra.apply(self.converter_valor)
                        if valores.sum() > 0:
                            self.coluna_valor_pagto = col
                            self.log(f"Coluna de valor inferida: {col}")
                            break
                except:
                    continue
        
        self.log(f"Coluna de valor final: {self.coluna_valor_pagto}")
        
        # Converter todas as colunas que parecem ser valores
        colunas_convertidas = []
        for coluna in df_limpo.columns:
            # Não converter colunas óbvias de texto
            if any(termo in coluna.lower() for termo in ['nome', 'distrito', 'rg', 'projeto', 'cartao']):
                continue
            
            # Tentar converter para numérico
            try:
                antes = df_limpo[coluna].head(5).tolist()
                df_limpo[coluna] = df_limpo[coluna].apply(self.converter_valor)
                depois = df_limpo[coluna].head(5).tolist()
                
                # Verificar se a conversão fez sentido
                if any(v != 0 for v in depois[:3]):
                    colunas_convertidas.append(coluna)
                    self.log(f"Coluna convertida: {coluna} (ex: {antes[:2]} -> {depois[:2]})")
            except Exception as e:
                self.log(f"Erro ao converter coluna {coluna}: {str(e)[:50]}")
        
        self.log(f"Total de colunas convertidas: {len(colunas_convertidas)}")
        
        # Remover linhas onde o valor de pagamento é zero ou negativo
        if self.coluna_valor_pagto and self.coluna_valor_pagto in df_limpo.columns:
            antes = len(df_limpo)
            df_limpo = df_limpo[df_limpo[self.coluna_valor_pagto] > 0]
            depois = len(df_limpo)
            self.log(f"Removidos {antes - depois} registros com valor ≤ 0")
        
        self.dados_limpos = df_limpo
        self.log(f"✅ Dados limpos: {len(df_limpo)} linhas, {len(df_limpo.columns)} colunas")
    
    def _analisar_dados_faltantes(self):
        """Analisa dados faltantes no dataset"""
        self.log("Analisando dados faltantes...")
        
        if self.dados_limpos is None or self.dados_limpos.empty:
            self.log("❌ Nenhum dado para análise de faltantes")
            return
        
        # Analisar valores faltantes por coluna
        faltantes_por_coluna = self.dados_limpos.isnull().sum()
        percentual_faltantes = (faltantes_por_coluna / len(self.dados_limpos)) * 100
        
        self.dados_faltantes = pd.DataFrame({
            'Coluna': faltantes_por_coluna.index,
            'Valores_Faltantes': faltantes_por_coluna.values,
            'Percentual_Faltante': percentual_faltantes.values.round(2),
            'Tipo_Dado': [str(dtype) for dtype in self.dados_limpos.dtypes.values]
        })
        
        self.log(f"Dados faltantes analisados: {len(faltantes_por_coluna)} colunas")
        
        # Identificar linhas com dados faltantes críticos
        colunas_criticas = []
        if self.coluna_valor_pagto:
            colunas_criticas.append(self.coluna_valor_pagto)
        
        for col in ['nome', 'agencia']:
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
        
        # 1. Valores negativos onde não deveriam
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
        
        # 2. Valores zerados
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
        
        # 3. Agências inválidas ou faltantes
        if 'agencia' in self.dados_limpos.columns:
            agencias_invalidas = self.dados_limpos[self.dados_limpos['agencia'].isnull()]
            if len(agencias_invalidas) > 0:
                inconsistencias.append({
                    'Tipo': 'Agências Inválidas',
                    'Coluna': 'agencia',
                    'Quantidade': len(agencias_invalidas),
                    'Exemplo': f"{len(agencias_invalidas)} registros sem agência",
                    'Descrição': 'Agência não informada'
                })
                self.log(f"Agências inválidas: {len(agencias_invalidas)}")
            
            # Agências com formato estranho
            try:
                agencias_estranhas = self.dados_limpos[
                    ~self.dados_limpos['agencia'].astype(str).str.match(r'^\d+$')
                ]
                if len(agencias_estranhas) > 0:
                    inconsistencias.append({
                        'Tipo': 'Formato de Agência Inválido',
                        'Coluna': 'agencia',
                        'Quantidade': len(agencias_estranhas),
                        'Exemplo': f"Exemplos: {agencias_estranhas['agencia'].unique()[:3]}",
                        'Descrição': 'Agência com formato não numérico'
                    })
            except:
                pass
        
        # 4. Nomes faltantes
        if 'nome' in self.dados_limpos.columns:
            nomes_faltantes = self.dados_limpos[self.dados_limpos['nome'].isnull()]
            if len(nomes_faltantes) > 0:
                inconsistencias.append({
                    'Tipo': 'Nomes Faltantes',
                    'Coluna': 'nome',
                    'Quantidade': len(nomes_faltantes),
                    'Exemplo': f"{len(nomes_faltantes)} registros sem nome",
                    'Descrição': 'Nome do beneficiário não informado'
                })
        
        # 5. Valores atípicos (outliers)
        if self.coluna_valor_pagto and self.coluna_valor_pagto in self.dados_limpos.columns:
            try:
                valores = self.dados_limpos[self.coluna_valor_pagto]
                q1 = valores.quantile(0.25)
                q3 = valores.quantile(0.75)
                iqr = q3 - q1
                limite_inferior = q1 - 1.5 * iqr
                limite_superior = q3 + 1.5 * iqr
                
                outliers = self.dados_limpos[
                    (valores < limite_inferior) | (valores > limite_superior)
                ]
                
                if len(outliers) > 0:
                    inconsistencias.append({
                        'Tipo': 'Valores Atípicos (Outliers)',
                        'Coluna': self.coluna_valor_pagto,
                        'Quantidade': len(outliers),
                        'Exemplo': f"Valores fora de [{limite_inferior:.2f}, {limite_superior:.2f}]",
                        'Descrição': 'Valores muito distantes da distribuição normal'
                    })
                    self.log(f"Outliers encontrados: {len(outliers)}")
            except Exception as e:
                self.log(f"Erro ao calcular outliers: {str(e)}")
        
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
                self.total_pagamentos = self.dados_limpos[self.coluna_valor_pagto].sum()
                self.log(f"Valor total calculado: R$ {self.total_pagamentos:,.2f}")
                
                # Verificação adicional
                soma_alternativa = np.sum(self.dados_limpos[self.coluna_valor_pagto].values)
                self.log(f"Verificação com numpy: R$ {soma_alternativa:,.2f}")
                
                if abs(self.total_pagamentos - soma_alternativa) > 0.01:
                    self.log("⚠️ Diferença detectada entre métodos de soma!")
            except Exception as e:
                self.log(f"Erro ao calcular estatísticas: {str(e)}")
                self.total_pagamentos = 0
        else:
            self.log("⚠️ Coluna de valor não disponível para cálculo")
            self.total_pagamentos = 0
    
    def _gerar_relatorio_executivo(self):
        """Gera relatório executivo consolidado"""
        self.log("Gerando relatório executivo...")
        
        self.relatorio_executivo = {
            'data_processamento': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'nome_arquivo': self.nome_arquivo,
            'total_registros': len(self.dados_limpos) if self.dados_limpos is not None else 0,
            'valor_total': self.total_pagamentos,
            'coluna_valor_principal': self.coluna_valor_pagto,
            'dados_faltantes': self.dados_faltantes.to_dict('records') if self.dados_faltantes is not None else [],
            'inconsistencias': self.inconsistencias.to_dict('records') if self.inconsistencias is not None else [],
            'colunas_disponiveis': list(self.dados_limpos.columns) if self.dados_limpos is not None else []
        }
        
        self.log("Relatório executivo gerado com sucesso")
    
    def mostrar_log_processamento(self):
        """Mostra o log de processamento"""
        if self.log_processamento:
            with st.expander("📝 Log de Processamento", expanded=False):
                for log_entry in self.log_processamento:
                    if "❌" in log_entry or "ERRO" in log_entry.upper():
                        st.error(log_entry)
                    elif "⚠️" in log_entry or "AVISO" in log_entry.upper():
                        st.warning(log_entry)
                    elif "✅" in log_entry or "SUCESSO" in log_entry.upper():
                        st.success(log_entry)
                    else:
                        st.info(log_entry)
    
    def mostrar_dados_originais(self):
        """Mostra dados originais para debug"""
        if self.df_original is not None:
            with st.expander("🔍 Dados Originais (Primeiras 10 linhas)", expanded=False):
                st.write(f"Shape: {self.df_original.shape}")
                st.dataframe(self.df_original.head(10), use_container_width=True)
                
                st.write("**Colunas originais:**")
                for i, col in enumerate(self.df_original.columns, 1):
                    st.write(f"{i}. {col}")
    
    def gerar_relatorio_excel_completo(self):
        """Gera relatório Excel completo"""
        if not self.arquivo_processado:
            return None
        
        try:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Dados Completos
                if self.dados_limpos is not None:
                    self.dados_limpos.to_excel(writer, sheet_name='Dados Completos', index=False)
                
                # Dados Faltantes
                if self.dados_faltantes is not None:
                    self.dados_faltantes.to_excel(writer, sheet_name='Dados Faltantes', index=False)
                
                # Inconsistências
                if self.inconsistencias is not None and not self.inconsistencias.empty:
                    self.inconsistencias.to_excel(writer, sheet_name='Inconsistências', index=False)
                
                # Relatório Executivo
                relatorio_data = []
                relatorio_data.append(['RELATÓRIO EXECUTIVO - SISTEMA POT', ''])
                relatorio_data.append(['Data do Relatório', self.relatorio_executivo['data_processamento']])
                relatorio_data.append(['Arquivo Processado', self.relatorio_executivo['nome_arquivo']])
                relatorio_data.append(['Total de Registros', self.relatorio_executivo['total_registros']])
                relatorio_data.append(['Valor Total', f"R$ {self.relatorio_executivo['valor_total']:,.2f}"])
                relatorio_data.append(['Coluna de Valor Principal', self.relatorio_executivo['coluna_valor_principal']])
                relatorio_data.append(['', ''])
                relatorio_data.append(['RESUMO DE QUALIDADE', ''])
                relatorio_data.append(['Dados Faltantes Detectados', len(self.relatorio_executivo['dados_faltantes'])])
                relatorio_data.append(['Inconsistências Detectadas', len(self.relatorio_executivo['inconsistencias'])])
                
                relatorio_df = pd.DataFrame(relatorio_data, columns=['Item', 'Valor'])
                relatorio_df.to_excel(writer, sheet_name='Relatório Executivo', index=False)
            
            output.seek(0)
            return output
        
        except Exception as e:
            self.log(f"Erro ao gerar Excel: {str(e)}")
            return None

# Inicializar sistema
sistema = SistemaPOTComDebug()

# ==============================================
# INTERFACE STREAMLIT COM DEBUG
# ==============================================

st.title("💰 SISTEMA DE MONITORAMENTO POT - COM DEBUG")
st.markdown("---")

# Sidebar
with st.sidebar:
    st.header("📁 Upload do Arquivo")
    
    arquivo = st.file_uploader(
        "Selecione o arquivo CSV",
        type=['csv'],
        help="Arquivo CSV com dados de pagamentos"
    )
    
    if arquivo is not None:
        st.info(f"📄 **Arquivo:** {arquivo.name}")
        st.info(f"📊 **Tamanho:** {arquivo.size / 1024:.1f} KB")
        
        modo_debug = st.checkbox("🐛 Modo Debug Detalhado", value=True)
        
        if st.button("🚀 PROCESSAR ARQUIVO", type="primary", use_container_width=True):
            with st.spinner("Processando... Isso pode levar alguns segundos"):
                sucesso = sistema.processar_arquivo_streamlit(arquivo)
                if sucesso:
                    st.session_state['arquivo_processado'] = True
                    st.session_state['modo_debug'] = modo_debug
                    st.success("✅ Processado com sucesso!")
                else:
                    st.error("❌ Falha no processamento")
    
    if 'arquivo_processado' in st.session_state and st.session_state['arquivo_processado']:
        st.markdown("---")
        if st.button("🔄 Novo Arquivo", use_container_width=True):
            st.session_state.clear()
            st.rerun()

# Área principal
if 'arquivo_processado' in st.session_state and st.session_state['arquivo_processado']:
    if sistema.arquivo_processado:
        
        # Mostrar log de processamento
        sistema.mostrar_log_processamento()
        
        # Mostrar dados originais se em modo debug
        if st.session_state.get('modo_debug', False):
            sistema.mostrar_dados_originais()
        
        # Verificar se temos dados processados
        if sistema.dados_limpos is None or len(sistema.dados_limpos) == 0:
            st.error("""
            ❌ **ERRO: Nenhum dado válido processado**
            
            **Possíveis causas:**
            1. Arquivo vazio ou corrompido
            2. Encoding não compatível
            3. Delimitador incorreto (não é ponto e vírgula)
            4. Formato de dados inválido
            
            **Soluções:**
            1. Verifique o arquivo no bloco de notas
            2. Tente salvar como UTF-8 ou Latin-1
            3. Confirme o delimitador usado
            4. Verifique se há dados válidos
            """)
            
            # Mostrar informações do arquivo original
            if sistema.df_original is not None:
                st.warning(f"Arquivo original tem {len(sistema.df_original)} linhas e {len(sistema.df_original.columns)} colunas")
                if len(sistema.df_original) > 0:
                    st.write("**Primeira linha do arquivo original:**")
                    st.write(sistema.df_original.iloc[0].to_dict())
            
            return
        
        # ============================
        # RESUMO DO PROCESSAMENTO
        # ============================
        st.header("📊 RESUMO DO PROCESSAMENTO")
        
        # Métricas principais
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_registros = len(sistema.dados_limpos)
            st.metric("📄 Registros Válidos", f"{total_registros:,}")
        
        with col2:
            if sistema.coluna_valor_pagto:
                valor_total = sistema.total_pagamentos
                st.metric("💰 Valor Total", f"R$ {valor_total:,.2f}")
            else:
                st.metric("💰 Valor Total", "N/A")
        
        with col3:
            if sistema.dados_faltantes is not None:
                total_faltantes = sistema.dados_faltantes['Valores_Faltantes'].sum()
                st.metric("⚠️ Dados Faltantes", f"{total_faltantes:,}")
            else:
                st.metric("⚠️ Dados Faltantes", "0")
        
        with col4:
            if sistema.inconsistencias is not None and not sistema.inconsistencias.empty:
                total_inconsistencias = sistema.inconsistencias['Quantidade'].sum() if 'Quantidade' in sistema.inconsistencias.columns else 0
                st.metric("🚨 Inconsistências", f"{total_inconsistencias:,}")
            else:
                st.metric("🚨 Inconsistências", "0")
        
        # Informações sobre a coluna de valor
        if sistema.coluna_valor_pagto:
            st.info(f"**Coluna de valor identificada:** `{sistema.coluna_valor_pagto}`")
            
            # Mostrar estatísticas básicas da coluna
            if sistema.coluna_valor_pagto in sistema.dados_limpos.columns:
                valores = sistema.dados_limpos[sistema.coluna_valor_pagto]
                col_stats1, col_stats2, col_stats3 = st.columns(3)
                
                with col_stats1:
                    st.metric("Média", f"R$ {valores.mean():,.2f}")
                
                with col_stats2:
                    st.metric("Mínimo", f"R$ {valores.min():,.2f}")
                
                with col_stats3:
                    st.metric("Máximo", f"R$ {valores.max():,.2f}")
        
        st.markdown("---")
        
        # ============================
        # ANÁLISE DE DADOS FALTANTES
        # ============================
        st.header("🔍 ANÁLISE DE DADOS FALTANTES")
        
        if sistema.dados_faltantes is not None and not sistema.dados_faltantes.empty:
            # Filtrar colunas com faltantes
            faltantes_com_valores = sistema.dados_faltantes[
                sistema.dados_faltantes['Valores_Faltantes'] > 0
            ]
            
            if not faltantes_com_valores.empty:
                st.subheader("📋 Dados Faltantes por Coluna")
                
                # Mostrar tabela
                st.dataframe(
                    faltantes_com_valores[['Coluna', 'Valores_Faltantes', 'Percentual_Faltante', 'Tipo_Dado']],
                    use_container_width=True,
                    height=300
                )
                
                # Gráfico de barras
                st.bar_chart(faltantes_com_valores.set_index('Coluna')['Percentual_Faltante'])
                
                # Linhas críticas
                if hasattr(sistema, 'linhas_com_faltantes_criticos') and not sistema.linhas_com_faltantes_criticos.empty:
                    st.subheader("🚨 Linhas com Faltantes Críticos")
                    st.dataframe(
                        sistema.linhas_com_faltantes_criticos,
                        use_container_width=True,
                        height=200
                    )
                    
                    st.warning(f"""
                    **Ação Necessária:** 
                    Corrigir {len(sistema.linhas_com_faltantes_criticos)} registros com dados críticos faltantes.
                    
                    **Campos críticos:** {', '.join([c for c in ['nome', 'agencia', sistema.coluna_valor_pagto] 
                                                    if c in sistema.dados_limpos.columns])}
                    """)
            else:
                st.success("✅ Nenhum dado faltante detectado!")
        else:
            st.success("✅ Nenhum dado faltante detectado!")
        
        st.markdown("---")
        
        # ============================
        # ANÁLISE DE INCONSISTÊNCIAS
        # ============================
        st.header("🚨 ANÁLISE DE INCONSISTÊNCIAS")
        
        if sistema.inconsistencias is not None and not sistema.inconsistencias.empty:
            st.subheader("📋 Tipos de Inconsistências Detectadas")
            
            # Tabela de inconsistências
            st.dataframe(
                sistema.inconsistencias,
                use_container_width=True,
                height=300
            )
            
            # Detalhamento
            st.subheader("📊 Detalhamento")
            
            for idx, row in sistema.inconsistencias.iterrows():
                with st.expander(f"{row['Tipo']} ({row['Quantidade']} ocorrências)"):
                    st.write(f"**Coluna:** {row['Coluna']}")
                    st.write(f"**Descrição:** {row.get('Descrição', 'N/A')}")
                    st.write(f"**Exemplo:** {row['Exemplo']}")
                    st.write(f"**Impacto:** {row['Quantidade']} registros afetados")
            
            # Recomendações
            st.subheader("🎯 RECOMENDAÇÕES")
            
            rec_col1, rec_col2 = st.columns(2)
            
            with rec_col1:
                st.markdown("""
                **Ações Imediatas:**
                1. Corrigir valores negativos
                2. Validar valores zerados
                3. Completar dados faltantes críticos
                """)
            
            with rec_col2:
                st.markdown("""
                **Prevenção Futura:**
                1. Validação na entrada de dados
                2. Padrões de qualidade
                3. Treinamento da equipe
                """)
        else:
            st.success("✅ Nenhuma inconsistência grave detectada!")
        
        st.markdown("---")
        
        # ============================
        # VISUALIZAÇÃO DOS DADOS
        # ============================
        st.header("👀 VISUALIZAÇÃO DOS DADOS")
        
        tab1, tab2 = st.tabs(["📋 Dados Processados", "📊 Estatísticas"])
        
        with tab1:
            col_vis1, col_vis2 = st.columns(2)
            
            with col_vis1:
                colunas_disponiveis = sistema.dados_limpos.columns.tolist()
                colunas_selecionadas = st.multiselect(
                    "Selecione colunas para visualizar:",
                    options=colunas_disponiveis,
                    default=colunas_disponiveis[:min(6, len(colunas_disponiveis))]
                )
            
            with col_vis2:
                num_linhas = st.slider("Número de linhas:", 5, 100, 20)
            
            if colunas_selecionadas:
                dados_visiveis = sistema.dados_limpos[colunas_selecionadas].head(num_linhas)
                
                # Formatar valores monetários
                if sistema.coluna_valor_pagto and sistema.coluna_valor_pagto in dados_visiveis.columns:
                    dados_visiveis = dados_visiveis.copy()
                    dados_visiveis[sistema.coluna_valor_pagto] = dados_visiveis[sistema.coluna_valor_pagto].apply(
                        lambda x: f"R$ {x:,.2f}" if pd.notna(x) else ""
                    )
                
                st.dataframe(dados_visiveis, use_container_width=True, height=400)
        
        with tab2:
            if sistema.coluna_valor_pagto:
                valores = sistema.dados_limpos[sistema.coluna_valor_pagto]
                
                col_stat1, col_stat2 = st.columns(2)
                
                with col_stat1:
                    st.markdown("**Estatísticas Descritivas:**")
                    stats = valores.describe()
                    
                    stats_df = pd.DataFrame({
                        'Estatística': ['Mínimo', '25%', 'Mediana', '75%', 'Máximo', 'Média', 'Desvio Padrão'],
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
                
                with col_stat2:
                    st.markdown("**Distribuição:**")
                    # Histograma simples
                    try:
                        hist, bins = np.histogram(valores, bins=10)
                        hist_df = pd.DataFrame({
                            'Faixa de Valor': [f"{bins[i]:.0f}-{bins[i+1]:.0f}" for i in range(len(hist))],
                            'Frequência': hist
                        })
                        st.dataframe(hist_df, use_container_width=True, height=300)
                    except:
                        st.write("Não foi possível gerar histograma")
        
        st.markdown("---")
        
        # ============================
        # EXPORTAÇÃO DE RELATÓRIOS
        # ============================
        st.header("📥 EXPORTAÇÃO DE RELATÓRIOS")
        
        col_exp1, col_exp2, col_exp3 = st.columns(3)
        
        with col_exp1:
            # Relatório Excel Completo
            excel_data = sistema.gerar_relatorio_excel_completo()
            if excel_data:
                st.download_button(
                    label="📊 Relatório Excel Completo",
                    data=excel_data,
                    file_name=f"relatorio_pot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
        
        with col_exp2:
            # Dados Processados CSV
            if sistema.dados_limpos is not None:
                csv_data = sistema.dados_limpos.to_csv(index=False, sep=';', encoding='utf-8')
                st.download_button(
                    label="📋 Dados Processados (CSV)",
                    data=csv_data,
                    file_name=f"dados_processados_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        
        with col_exp3:
            # Log de Processamento
            if sistema.log_processamento:
                log_text = "\n".join(sistema.log_processamento)
                st.download_button(
                    label="📝 Log de Processamento",
                    data=log_text,
                    file_name=f"log_processamento_{datetime.now().strftime('%Y%m%d')}.txt",
                    mime="text/plain",
                    use_container_width=True
                )
    
    else:
        st.error("❌ O processamento do arquivo falhou.")
        sistema.mostrar_log_processamento()
else:
    # Tela inicial
    st.markdown("""
    # 🚀 SISTEMA DE MONITORAMENTO POT - COM DEBUG
    
    ### 🎯 **SISTEMA COMPLETO COM:**
    
    ✅ **Processamento robusto** com múltiplos encodings
    ✅ **Análise detalhada** de dados faltantes
    ✅ **Detecção automática** de inconsistências
    ✅ **Log completo** de processamento para debug
    ✅ **Relatórios executivos** prontos para a equipe
    
    ### 🐛 **MODO DEBUG ATIVADO:**
    
    - Log detalhado de cada etapa
    - Visualização dos dados originais
    - Detecção de erros específicos
    - Informações para correção
    
    ### 📁 **COMO USAR:**
    
    1. **Faça upload** do arquivo CSV
    2. **Marque a opção** "Modo Debug Detalhado"
    3. **Clique em Processar**
    4. **Analise o log** para entender problemas
    5. **Exporte relatórios** para correção
    """)
    
    st.markdown("---")
    
    # Dicas para upload
    with st.expander("💡 DICAS PARA UPLOAD BEM-SUCEDIDO"):
        st.markdown("""
        ### **Problemas comuns e soluções:**
        
        **1. Encoding incorreto:**
        - Salve o arquivo como **UTF-8** ou **Latin-1**
        - Evite caracteres especiais problemáticos
        
        **2. Delimitador incorreto:**
        - Confirme que é **ponto e vírgula (;)**
        - Verifique se não há tabulações
        
        **3. Formato de valores:**
        - Use formato brasileiro: **R$ 1.593,90**
        - Ou formato numérico simples: **1593.90**
        
        **4. Estrutura do arquivo:**
        - Primeira linha deve ter cabeçalhos
        - Não misture tipos de dados na mesma coluna
        
        ### **Formato recomendado:**
        ```
        Nome;Agencia;Valor Pagto;Data Pagto
        João Silva;1234;R$ 1.593,90;20/10/2025
        Maria Santos;5678;R$ 2.500,00;21/10/2025
        ```
        """)

# ==============================================
# CONFIGURAÇÕES
# ==============================================
encoding_map = {
    'ISO-8859-1': 'latin-1',
    'Windows-1252': 'cp1252',
    'ascii': 'utf-8',
    'UTF-8-SIG': 'utf-8'
}

# ==============================================
# RODAPÉ
# ==============================================
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: gray; padding: 10px;'>
    <strong>Sistema POT com Debug</strong> • 
    Processamento Robusto • 
    Análise Completa • 
    Versão Debug 1.0
    </div>
    """,
    unsafe_allow_html=True
)
