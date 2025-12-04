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
    
    def converter_valor(self, valor_str):
        """Converte valores monetários do formato brasileiro para float"""
        if pd.isna(valor_str) or valor_str == '' or str(valor_str).strip() == '':
            return 0.0
        
        try:
            # Se já for número, retornar direto
            if isinstance(valor_str, (int, float)):
                return float(valor_str)
            
            valor_str = str(valor_str).strip()
            
            # Tentar converter diretamente (para números sem formatação)
            try:
                return float(valor_str)
            except:
                pass
            
            # Remover R$ e espaços
            valor_str = valor_str.replace('R$', '').replace(' ', '').strip()
            
            if valor_str == '':
                return 0.0
            
            # Formato brasileiro: 1.593,90
            # Tem ponto de milhar e vírgula decimal
            if '.' in valor_str and ',' in valor_str:
                # Remover pontos de milhar e substituir vírgula por ponto
                partes = valor_str.split(',')
                if len(partes) == 2:
                    inteiro = partes[0].replace('.', '')  # Remove pontos de milhar
                    decimal = partes[1]
                    return float(f"{inteiro}.{decimal}")
            
            # Formato europeu: 1593,90 (apenas vírgula decimal)
            elif ',' in valor_str:
                return float(valor_str.replace(',', '.'))
            
            # Formato americano: 1593.90 (apenas ponto decimal)
            elif '.' in valor_str:
                # Pode ser número com ponto decimal ou ponto de milhar
                if valor_str.count('.') == 1 and len(valor_str.split('.')[-1]) <= 2:
                    # Provavelmente ponto decimal
                    return float(valor_str)
                else:
                    # Pode ter ponto de milhar, remover todos
                    return float(valor_str.replace('.', ''))
            
            # Número inteiro
            else:
                return float(valor_str)
                
        except Exception as e:
            self.log(f"Erro ao converter valor '{str(valor_str)[:20]}': {e}")
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
            
            # Tentar ler arquivo
            try:
                # Primeiro, tentar ler como texto para análise
                with open(temp_path, 'r', encoding=encoding, errors='replace') as f:
                    linhas = f.readlines()
                
                self.log(f"Arquivo lido como texto: {len(linhas)} linhas")
                
                if len(linhas) == 0:
                    self.log("❌ Arquivo vazio")
                    return False
                
                # Mostrar preview
                self.log(f"Primeira linha: {linhas[0][:100]}...")
                if len(linhas) > 1:
                    self.log(f"Segunda linha: {linhas[1][:100]}...")
                
                # Agora ler com pandas
                self.df = pd.read_csv(
                    temp_path, 
                    delimiter=';', 
                    encoding=encoding, 
                    on_bad_lines='skip',
                    dtype=str,
                    quoting=3  # Ignorar aspas
                )
                
                self.log(f"✅ Arquivo lido com pandas. Shape: {self.df.shape}")
                
            except Exception as e:
                self.log(f"❌ Erro ao ler com pandas: {e}")
                # Tentar criar DataFrame manualmente
                try:
                    if len(linhas) > 0:
                        colunas = linhas[0].strip().split(';')
                        dados = []
                        for i, linha in enumerate(linhas[1:], 1):
                            try:
                                valores = linha.strip().split(';')
                                if len(valores) >= len(colunas) - 1:  # Permitir colunas faltantes
                                    # Preencher valores faltantes
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
        
        # Remover linhas totalmente vazias
        df_limpo = df_limpo.dropna(how='all')
        linhas_apos_vazias = len(df_limpo)
        self.log(f"Removidas {linhas_iniciais - linhas_apos_vazias} linhas totalmente vazias")
        
        # Mostrar colunas originais
        colunas_originais = list(df_limpo.columns)
        self.log(f"Colunas originais: {colunas_originais}")
        
        # Padronizar nomes das colunas (remover acentos, espaços, minúsculas)
        mapeamento_colunas = {}
        for col in df_limpo.columns:
            if pd.isna(col) or str(col).strip() == '':
                col_novo = 'coluna_sem_nome'
            else:
                col_novo = str(col).strip().lower()
                # Substituir caracteres especiais
                col_novo = re.sub(r'[^a-z0-9_]', '_', col_novo)
                # Remover acentos
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
        # Lista de possíveis nomes (em ordem de prioridade)
        possiveis_nomes_valor = [
            'valor_pagto', 'valor_pagamento', 'valor_total', 'valor', 
            'pagto', 'pagamento', 'total', 'valorpagto', 'valor_pgto',
            'valorpagamento'
        ]
        
        self.coluna_valor_pagto = None
        for nome in possiveis_nomes_valor:
            if nome in df_limpo.columns:
                self.coluna_valor_pagto = nome
                self.log(f"✅ Coluna de valor identificada: {nome}")
                break
        
        # Se não encontrou, procurar por padrões nas colunas
        if self.coluna_valor_pagto is None:
            for col in df_limpo.columns:
                col_lower = col.lower()
                if any(termo in col_lower for termo in ['val', 'pag', 'total']):
                    self.coluna_valor_pagto = col
                    self.log(f"✅ Coluna de valor identificada por padrão: {col}")
                    break
        
        if self.coluna_valor_pagto is None:
            self.log("⚠️ Coluna de valor não identificada automaticamente")
            # Tentar inferir pela primeira coluna numérica
            for col in df_limpo.columns:
                try:
                    # Tentar converter amostra
                    amostra = df_limpo[col].dropna().head(10)
                    if len(amostra) > 0:
                        valores = amostra.apply(self.converter_valor)
                        if valores.sum() > 0:
                            self.coluna_valor_pagto = col
                            self.log(f"✅ Coluna de valor inferida: {col}")
                            break
                except:
                    continue
        
        self.log(f"Coluna de valor final: {self.coluna_valor_pagto}")
        
        # Converter todas as colunas que parecem ser valores monetários
        colunas_convertidas = []
        for coluna in df_limpo.columns:
            # Pular colunas óbvias de texto
            if any(termo in coluna.lower() for termo in ['nome', 'distrito', 'rg', 'projeto', 'cartao']):
                continue
            
            try:
                # Tentar converter
                valores_originais = df_limpo[coluna].head(3).tolist()
                df_limpo[coluna] = df_limpo[coluna].apply(self.converter_valor)
                valores_convertidos = df_limpo[coluna].head(3).tolist()
                
                # Verificar se a conversão fez sentido (não são todos zeros)
                if any(v != 0 for v in valores_convertidos):
                    colunas_convertidas.append(coluna)
                    self.log(f"Coluna convertida: {coluna} (ex: {valores_originais} -> {valores_convertidos})")
            except Exception as e:
                self.log(f"Erro ao converter coluna {coluna}: {e}")
        
        self.log(f"Total de colunas convertidas: {len(colunas_convertidas)}")
        
        # Remover linhas onde o valor de pagamento é zero ou negativo
        if self.coluna_valor_pagto and self.coluna_valor_pagto in df_limpo.columns:
            antes = len(df_limpo)
            df_limpo = df_limpo[df_limpo[self.coluna_valor_pagto] > 0]
            depois = len(df_limpo)
            removidos = antes - depois
            if removidos > 0:
                self.log(f"Removidos {removidos} registros com valor ≤ 0")
        
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
            self.log("❌ Nenhum dato para análise de inconsistências")
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
                # Calcular soma TOTAL e precisa
                self.total_pagamentos = self.dados_limpos[self.coluna_valor_pagto].sum()
                
                # Verificação extra: calcular também usando numpy para garantir
                total_numpy = np.sum(self.dados_limpos[self.coluna_valor_pagto].values)
                
                self.log(f"💰 Valor total calculado (pandas): R$ {self.total_pagamentos:,.2f}")
                self.log(f"💰 Valor total calculado (numpy): R$ {total_numpy:,.2f}")
                
                # Pequena diferença de arredondamento é aceitável
                if abs(self.total_pagamentos - total_numpy) > 0.01:
                    self.log("⚠️ Diferença detectada entre métodos de soma!")
                    # Usar a média dos dois para minimizar erros
                    self.total_pagamentos = (self.total_pagamentos + total_numpy) / 2
                    self.log(f"💰 Valor total ajustado: R$ {self.total_pagamentos:,.2f}")
                
                # Mostrar estatísticas básicas
                valores = self.dados_limpos[self.coluna_valor_pagto]
                self.log(f"  - Média: R$ {valores.mean():,.2f}")
                self.log(f"  - Mínimo: R$ {valores.min():,.2f}")
                self.log(f"  - Máximo: R$ {valores.max():,.2f}")
                self.log(f"  - Mediana: R$ {valores.median():,.2f}")
                
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
                
                # Mostrar primeiras 5 linhas
                st.dataframe(self.df_original.head(5), use_container_width=True)
                
                # Mostrar tipos de dados
                st.write("**Tipos de dados:**")
                for col in self.df_original.columns:
                    st.write(f"- {col}: {str(self.df_original[col].dtype)}")
                
                # Mostrar exemplo de valores da primeira linha
                if len(self.df_original) > 0:
                    st.write("**Primeira linha (exemplo):**")
                    primeira_linha = self.df_original.iloc[0]
                    for col, valor in primeira_linha.items():
                        st.write(f"  - {col}: `{valor}`")

# Inicializar sistema
sistema = SistemaPOT()

# ==============================================
# INTERFACE STREAMLIT - SIMPLIFICADA
# ==============================================

st.title("💰 SISTEMA DE MONITORAMENTO DE PAGAMENTOS - POT")
st.markdown("---")

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
        
        # Opções
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
                    st.success("✅ Arquivo processado com sucesso!")
                else:
                    st.error("❌ Erro ao processar arquivo. Verifique o log.")
        
        if 'arquivo_processado' in st.session_state and st.session_state['arquivo_processado']:
            st.markdown("---")
            if st.button("🔄 PROCESSAR OUTRO ARQUIVO", use_container_width=True):
                st.session_state.clear()
                st.rerun()

# Área principal
if 'arquivo_processado' in st.session_state and st.session_state['arquivo_processado']:
    if sistema.arquivo_processado:
        
        # Mostrar log se solicitado
        if st.session_state.get('mostrar_log', False):
            sistema.mostrar_log()
        
        # Mostrar dados originais se solicitado
        if st.session_state.get('mostrar_debug', False):
            sistema.mostrar_dados_originais()
        
        # Verificar se temos dados processados
        if sistema.dados_limpos is None or len(sistema.dados_limpos) == 0:
            st.error("""
            ❌ **ERRO: NENHUM DADO VÁLIDO PROCESSADO**
            
            **Possíveis causas:**
            1. Arquivo vazio ou corrompido
            2. Encoding não compatível
            3. Delimitador incorreto (não é ponto e vírgula)
            4. Formato de dados inválido
            
            **Soluções:**
            1. Abra o arquivo no bloco de notas e verifique
            2. Salve como UTF-8 ou Latin-1 (ISO-8859-1)
            3. Confirme que o delimitador é ponto e vírgula (;)
            4. Verifique se há dados válidos nas colunas
            """)
            return
        
        # ============================
        # RESUMO EXECUTIVO
        # ============================
        st.header("📊 RESUMO EXECUTIVO")
        
        # Métricas principais
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                label="📄 TOTAL DE REGISTROS",
                value=f"{len(sistema.dados_limpos):,}",
                help="Número total de pagamentos processados"
            )
        
        with col2:
            if sistema.coluna_valor_pagto:
                valor_total = sistema.total_pagamentos
                st.metric(
                    label="💰 VALOR TOTAL",
                    value=f"R$ {valor_total:,.2f}",
                    help=f"Soma da coluna '{sistema.coluna_valor_pagto}'"
                )
            else:
                st.metric(
                    label="💰 VALOR TOTAL",
                    value="N/A",
                    help="Coluna de valor não identificada"
                )
        
        with col3:
            if sistema.dados_faltantes is not None:
                total_faltantes = sistema.dados_faltantes['Valores_Faltantes'].sum()
                st.metric(
                    label="⚠️ DADOS FALTANTES",
                    value=f"{total_faltantes:,}",
                    help="Total de valores faltantes em todas as colunas"
                )
            else:
                st.metric(label="⚠️ DADOS FALTANTES", value="0")
        
        with col4:
            if sistema.inconsistencias is not None and not sistema.inconsistencias.empty:
                total_inconsistencias = sistema.inconsistencias['Quantidade'].sum()
                st.metric(
                    label="🚨 INCONSISTÊNCIAS",
                    value=f"{total_inconsistencias:,}",
                    help="Total de inconsistências detectadas"
                )
            else:
                st.metric(label="🚨 INCONSISTÊNCIAS", value="0")
        
        # Informações adicionais
        if sistema.coluna_valor_pagto:
            st.info(f"**Coluna de valor identificada:** `{sistema.coluna_valor_pagto}`")
            
            # Estatísticas básicas
            valores = sistema.dados_limpos[sistema.coluna_valor_pagto]
            col_stat1, col_stat2, col_stat3 = st.columns(3)
            
            with col_stat1:
                st.metric("📊 Valor Médio", f"R$ {valores.mean():,.2f}")
            
            with col_stat2:
                st.metric("⬇️ Valor Mínimo", f"R$ {valores.min():,.2f}")
            
            with col_stat3:
                st.metric("⬆️ Valor Máximo", f"R$ {valores.max():,.2f}")
        
        st.markdown("---")
        
        # ============================
        # ANÁLISE DE DADOS FALTANTES
        # ============================
        st.header("🔍 ANÁLISE DE DADOS FALTANTES")
        
        if sistema.dados_faltantes is not None and not sistema.dados_faltantes.empty:
            # Filtrar apenas colunas com dados faltantes
            dados_faltantes_filtrados = sistema.dados_faltantes[
                sistema.dados_faltantes['Valores_Faltantes'] > 0
            ].copy()
            
            if not dados_faltantes_filtrados.empty:
                st.subheader("📋 DADOS FALTANTES POR COLUNA")
                
                # Formatar para exibição
                dados_faltantes_filtrados['Percentual_Faltante'] = dados_faltantes_filtrados['Percentual_Faltante'].apply(
                    lambda x: f"{x}%"
                )
                
                st.dataframe(
                    dados_faltantes_filtrados[['Coluna', 'Valores_Faltantes', 'Percentual_Faltante', 'Tipo_Dado']],
                    use_container_width=True,
                    height=300
                )
                
                # Gráfico de barras
                try:
                    chart_data = dados_faltantes_filtrados.set_index('Coluna')['Valores_Faltantes']
                    st.bar_chart(chart_data)
                except:
                    pass
                
                # Linhas com faltantes críticos
                if hasattr(sistema, 'linhas_com_faltantes_criticos') and not sistema.linhas_com_faltantes_criticos.empty:
                    st.subheader("🚨 LINHAS COM FALTANTES CRÍTICOS")
                    st.dataframe(
                        sistema.linhas_com_faltantes_criticos,
                        use_container_width=True,
                        height=200
                    )
                    
                    st.warning(f"""
                    **AÇÃO NECESSÁRIA:** 
                    Corrigir **{len(sistema.linhas_com_faltantes_criticos)}** registros com dados críticos faltantes.
                    
                    **Campos críticos:** {', '.join([c for c in ['nome', 'agencia', sistema.coluna_valor_pagto] 
                                                    if c in sistema.dados_limpos.columns])}
                    """)
            else:
                st.success("✅ NENHUM DADO FALTANTE DETECTADO!")
        else:
            st.success("✅ NENHUM DADO FALTANTE DETECTADO!")
        
        st.markdown("---")
        
        # ============================
        # ANÁLISE DE INCONSISTÊNCIAS
        # ============================
        st.header("🚨 ANÁLISE DE INCONSISTÊNCIAS")
        
        if sistema.inconsistencias is not None and not sistema.inconsistencias.empty:
            st.subheader("📋 TIPOS DE INCONSISTÊNCIAS DETECTADAS")
            
            # Tabela de inconsistências
            st.dataframe(
                sistema.inconsistencias,
                use_container_width=True,
                height=300
            )
            
            # Detalhamento por tipo
            st.subheader("📊 DETALHAMENTO")
            
            for idx, row in sistema.inconsistencias.iterrows():
                with st.expander(f"{row['Tipo']} ({row['Quantidade']} ocorrências)"):
                    st.write(f"**Coluna:** {row['Coluna']}")
                    st.write(f"**Descrição:** {row.get('Descrição', 'N/A')}")
                    st.write(f"**Exemplo:** {row['Exemplo']}")
                    st.write(f"**Impacto:** {row['Quantidade']} registros afetados")
            
            # Recomendações
            st.subheader("🎯 RECOMENDAÇÕES DE CORREÇÃO")
            
            rec_col1, rec_col2 = st.columns(2)
            
            with rec_col1:
                st.markdown("""
                **AÇÕES IMEDIATAS:**
                1. Corrigir valores negativos
                2. Validar valores zerados
                3. Completar dados faltantes críticos
                4. Revisar agências inválidas
                """)
            
            with rec_col2:
                st.markdown("""
                **PREVENÇÃO FUTURA:**
                1. Implementar validação na entrada
                2. Criar padrões de qualidade
                3. Treinar equipe de inserção
                4. Monitorar qualidade continuamente
                """)
        else:
            st.success("✅ NENHUMA INCONSISTÊNCIA GRAVE DETECTADA!")
        
        st.markdown("---")
        
        # ============================
        # VISUALIZAÇÃO DOS DADOS
        # ============================
        st.header("👀 VISUALIZAÇÃO DOS DADOS PROCESSADOS")
        
        tab1, tab2 = st.tabs(["📋 TABELA DE DADOS", "📊 ESTATÍSTICAS"])
        
        with tab1:
            col_vis1, col_vis2 = st.columns(2)
            
            with col_vis1:
                # Selecionar colunas
                colunas_disponiveis = sistema.dados_limpos.columns.tolist()
                colunas_selecionadas = st.multiselect(
                    "Selecione as colunas para visualizar:",
                    options=colunas_disponiveis,
                    default=colunas_disponiveis[:min(6, len(colunas_disponiveis))]
                )
            
            with col_vis2:
                # Número de linhas
                num_linhas = st.slider(
                    "Número de linhas para mostrar:",
                    min_value=5,
                    max_value=100,
                    value=20,
                    step=5
                )
            
            if colunas_selecionadas:
                dados_visiveis = sistema.dados_limpos[colunas_selecionadas].head(num_linhas).copy()
                
                # Formatar valores monetários
                if sistema.coluna_valor_pagto and sistema.coluna_valor_pagto in dados_visiveis.columns:
                    dados_visiveis[sistema.coluna_valor_pagto] = dados_visiveis[sistema.coluna_valor_pagto].apply(
                        lambda x: f"R$ {x:,.2f}" if pd.notna(x) else ""
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
                
                with col_stats2:
                    st.markdown("**📊 DISTRIBUIÇÃO**")
                    
                    try:
                        # Criar faixas de valores
                        faixas = pd.cut(valores, bins=10)
                        contagem = faixas.value_counts().sort_index()
                        
                        dist_df = pd.DataFrame({
                            'Faixa de Valor': [str(intervalo) for intervalo in contagem.index],
                            'Quantidade': contagem.values,
                            'Percentual': (contagem.values / len(valores) * 100).round(1)
                        })
                        
                        st.dataframe(dist_df, use_container_width=True, height=300)
                    except:
                        st.write("Não foi possível gerar distribuição")
        
        st.markdown("---")
        
        # ============================
        # EXPORTAÇÃO DE RELATÓRIOS
        # ============================
        st.header("📥 EXPORTAÇÃO DE RELATÓRIOS")
        
        col_exp1, col_exp2, col_exp3 = st.columns(3)
        
        with col_exp1:
            # Dados Processados (CSV)
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
            # Inconsistências (CSV)
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
            # Dados Faltantes (CSV)
            if sistema.dados_faltantes is not None and not sistema.dados_faltantes.empty:
                csv_faltantes = sistema.dados_faltantes.to_csv(index=False, sep=';', encoding='utf-8')
                st.download_button(
                    label="⚠️ DADOS FALTANTES (CSV)",
                    data=csv_faltantes,
                    file_name=f"dados_faltantes_pot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        
        # Log de Processamento
        if sistema.log_processamento:
            st.markdown("---")
            st.subheader("📝 LOG DE PROCESSAMENTO")
            
            log_text = "\n".join(sistema.log_processamento)
            st.download_button(
                label="📥 BAIXAR LOG COMPLETO",
                data=log_text,
                file_name=f"log_processamento_pot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain",
                use_container_width=True
            )
    
    else:
        st.error("❌ FALHA NO PROCESSAMENTO DO ARQUIVO")
        sistema.mostrar_log()
else:
    # Tela inicial
    st.markdown("""
    # 🚀 SISTEMA DE MONITORAMENTO DE PAGAMENTOS - POT
    
    ### 📋 **FUNCIONALIDADES COMPLETAS:**
    
    ✅ **PROCESSAMENTO ROBUSTO** com múltiplos encodings
    ✅ **ANÁLISE DE DADOS FALTANTES** com tabelas detalhadas
    ✅ **DETECÇÃO DE INCONSISTÊNCIAS** automática
    ✅ **CÁLCULO PRECISO** de valores totais
    ✅ **RELATÓRIOS EXECUTIVOS** prontos para exportação
    ✅ **LOGS COMPLETOS** para debug e auditoria
    
    ### 🎯 **PARA A EQUIPE DE QUALIDADE:**
    
    1. **IDENTIFIQUE** dados faltantes rapidamente
    2. **LOCALIZE** inconsistências específicas
    3. **EXPORTE** relatórios para correção
    4. **MONITORE** a qualidade dos dados
    
    ### 📁 **COMO USAR:**
    
    1. **Faça upload** do arquivo CSV na barra lateral
    2. **Clique em "Processar Arquivo"**
    3. **Analise** os dados faltantes e inconsistências
    4. **Exporte** os relatórios para a equipe
    5. **Corrija** os problemas identificados
    """)
    
    st.markdown("---")
    
    # Dicas
    with st.expander("💡 DICAS PARA UM PROCESSAMENTO BEM-SUCEDIDO"):
        st.markdown("""
        ### **FORMATO RECOMENDADO:**
        
        ```csv
        Nome;Agencia;Valor Pagto;Data Pagto
        João Silva;1234;R$ 1.593,90;20/10/2025
        Maria Santos;5678;1593.90;21/10/2025
        ```
        
        ### **ENCODING RECOMENDADO:**
        - **UTF-8** (para arquivos modernos)
        - **Latin-1 / ISO-8859-1** (para arquivos brasileiros)
        
        ### **DELIMITADOR:**
        - **Ponto e vírgula (;)** - obrigatório
        
        ### **FORMATO DE VALORES:**
        - **Brasileiro:** R$ 1.593,90
        - **Internacional:** 1593.90
        - **Evitar:** 1,593.90 (formato americano)
        
        ### **SE ENCONTRAR ERROS:**
        1. Ative as opções de debug
        2. Analise o log de processamento
        3. Verifique os dados originais
        4. Corrija o arquivo fonte
        """)

# ==============================================
# RODAPÉ
# ==============================================
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: gray; padding: 20px;'>
    <strong>💰 SISTEMA POT - MONITORAMENTO DE PAGAMENTOS</strong><br>
    Versão Definitiva • Processamento Robusto • Análise Completa • Cálculo Preciso
    </div>
    """,
    unsafe_allow_html=True
)
