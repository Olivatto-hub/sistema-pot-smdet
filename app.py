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
        self.relatorio_executivo = {}
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
            return 'latin-1' if encoding is None else encoding
        except:
            return 'latin-1'
    
    def tentar_encodings(self, arquivo_path):
        """Tenta diferentes encodings"""
        encodings = ['latin-1', 'iso-8859-1', 'cp1252', 'utf-8', 'utf-8-sig', 'cp850']
        for encoding in encodings:
            try:
                df = pd.read_csv(arquivo_path, delimiter=';', encoding=encoding, nrows=5, on_bad_lines='skip')
                if not df.empty and len(df.columns) > 1:
                    return encoding
            except:
                continue
        return None
    
    def converter_valor(self, valor_str):
        """Converte valores monetários para float"""
        if pd.isna(valor_str) or valor_str == '' or str(valor_str).strip() == '':
            return 0.0
        
        try:
            if isinstance(valor_str, (int, float)):
                return float(valor_str)
            
            valor_str = str(valor_str).strip()
            
            # Tentar converter diretamente
            try:
                return float(valor_str)
            except:
                pass
            
            # Remover R$ e espaços
            valor_str = valor_str.replace('R$', '').replace(' ', '').strip()
            
            if valor_str == '':
                return 0.0
            
            # Formato brasileiro: 1.593,90
            if '.' in valor_str and ',' in valor_str:
                partes = valor_str.split(',')
                if len(partes) == 2:
                    inteiro = partes[0].replace('.', '')
                    return float(f"{inteiro}.{partes[1]}")
            
            # Formato europeu: 1593,90
            elif ',' in valor_str:
                return float(valor_str.replace(',', '.'))
            
            # Tentar como está
            return float(valor_str)
        except:
            return 0.0
    
    def processar_arquivo_streamlit(self, arquivo_upload):
        """Processa arquivo CSV"""
        try:
            self.log_processamento = []
            self.log(f"Iniciando processamento: {arquivo_upload.name}")
            
            # Salvar arquivo temporariamente
            temp_path = f"temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            with open(temp_path, 'wb') as f:
                f.write(arquivo_upload.getvalue())
            
            # Detectar encoding
            encoding = self.tentar_encodings(temp_path)
            if encoding is None:
                encoding = self.detectar_encoding(temp_path) or 'latin-1'
            
            self.log(f"Encoding usado: {encoding}")
            
            # Ler arquivo
            try:
                self.df = pd.read_csv(
                    temp_path, 
                    delimiter=';', 
                    encoding=encoding, 
                    on_bad_lines='skip',
                    dtype=str
                )
                self.log(f"Arquivo lido: {self.df.shape[0]} linhas, {self.df.shape[1]} colunas")
            except Exception as e:
                self.log(f"Erro ao ler com pandas: {str(e)}")
                # Tentar ler manualmente
                with open(temp_path, 'r', encoding=encoding, errors='replace') as f:
                    linhas = f.readlines()
                
                if len(linhas) > 0:
                    colunas = linhas[0].strip().split(';')
                    dados = []
                    for linha in linhas[1:]:
                        valores = linha.strip().split(';')
                        if len(valores) == len(colunas):
                            dados.append(valores)
                    
                    self.df = pd.DataFrame(dados, columns=colunas)
                    self.log(f"DataFrame criado manualmente: {self.df.shape}")
            
            # Salvar cópia original
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
            self.log("Processamento concluído com sucesso!")
            return True
            
        except Exception as e:
            self.log(f"ERRO CRÍTICO: {str(e)}")
            return False
    
    def _limpar_dados(self):
        """Limpa e prepara os dados"""
        if self.df is None or self.df.empty:
            self.log("DataFrame vazio")
            return
        
        df_limpo = self.df.copy()
        
        # Remover linhas totalmente vazias
        df_limpo = df_limpo.dropna(how='all')
        self.log(f"Após remover vazias: {len(df_limpo)} linhas")
        
        # Padronizar nomes das colunas
        mapeamento = {}
        for col in df_limpo.columns:
            if pd.isna(col):
                col_novo = 'coluna_sem_nome'
            else:
                col_novo = str(col).strip().lower()
                col_novo = re.sub(r'[^a-z0-9_]', '_', col_novo)
                col_novo = col_novo.replace('á', 'a').replace('é', 'e').replace('í', 'i')
                col_novo = col_novo.replace('ó', 'o').replace('ú', 'u').replace('ç', 'c')
            mapeamento[col] = col_novo
        
        df_limpo = df_limpo.rename(columns=mapeamento)
        self.log(f"Colunas renomeadas: {list(df_limpo.columns)}")
        
        # Identificar coluna de valor
        possiveis_nomes = ['valor_pagto', 'valor_pagamento', 'valor_total', 'valor', 'pagto', 'valorpagto']
        self.coluna_valor_pagto = None
        
        for nome in possiveis_nomes:
            if nome in df_limpo.columns:
                self.coluna_valor_pagto = nome
                break
        
        if self.coluna_valor_pagto is None:
            for col in df_limpo.columns:
                if 'valor' in col.lower() or 'pagto' in col.lower():
                    self.coluna_valor_pagto = col
                    break
        
        self.log(f"Coluna de valor: {self.coluna_valor_pagto}")
        
        # Converter colunas que parecem valores
        for coluna in df_limpo.columns:
            # Pular colunas óbvias de texto
            if any(termo in coluna.lower() for termo in ['nome', 'distrito', 'rg', 'projeto']):
                continue
            
            try:
                df_limpo[coluna] = df_limpo[coluna].apply(self.converter_valor)
            except:
                pass
        
        # Remover valores zero ou negativos
        if self.coluna_valor_pagto and self.coluna_valor_pagto in df_limpo.columns:
            antes = len(df_limpo)
            df_limpo = df_limpo[df_limpo[self.coluna_valor_pagto] > 0]
            depois = len(df_limpo)
            self.log(f"Removidos {antes - depois} registros com valor ≤ 0")
        
        self.dados_limpos = df_limpo
        self.log(f"Dados limpos: {len(df_limpo)} linhas")
    
    def _analisar_dados_faltantes(self):
        """Analisa dados faltantes"""
        if self.dados_limpos is None or self.dados_limpos.empty:
            return
        
        faltantes = self.dados_limpos.isnull().sum()
        percentual = (faltantes / len(self.dados_limpos)) * 100
        
        self.dados_faltantes = pd.DataFrame({
            'Coluna': faltantes.index,
            'Valores_Faltantes': faltantes.values,
            'Percentual_Faltante': percentual.values.round(2),
            'Tipo_Dado': [str(dtype) for dtype in self.dados_limpos.dtypes.values]
        })
        
        # Linhas com faltantes críticos
        colunas_criticas = []
        if self.coluna_valor_pagto:
            colunas_criticas.append(self.coluna_valor_pagto)
        if 'nome' in self.dados_limpos.columns:
            colunas_criticas.append('nome')
        if 'agencia' in self.dados_limpos.columns:
            colunas_criticas.append('agencia')
        
        if colunas_criticas:
            mask = self.dados_limpos[colunas_criticas].isnull().any(axis=1)
            self.linhas_com_faltantes_criticos = self.dados_limpos[mask].copy()
        else:
            self.linhas_com_faltantes_criticos = pd.DataFrame()
    
    def _analisar_inconsistencias(self):
        """Analisa inconsistências"""
        if self.dados_limpos is None or self.dados_limpos.empty:
            return
        
        inconsistencias = []
        
        # Valores negativos
        if self.coluna_valor_pagto and self.coluna_valor_pagto in self.dados_limpos.columns:
            negativos = self.dados_limpos[self.dados_limpos[self.coluna_valor_pagto] < 0]
            if len(negativos) > 0:
                inconsistencias.append({
                    'Tipo': 'Valores Negativos',
                    'Coluna': self.coluna_valor_pagto,
                    'Quantidade': len(negativos),
                    'Exemplo': f"{len(negativos)} registros"
                })
        
        # Valores zerados
        if self.coluna_valor_pagto and self.coluna_valor_pagto in self.dados_limpos.columns:
            zerados = self.dados_limpos[self.dados_limpos[self.coluna_valor_pagto] == 0]
            if len(zerados) > 0:
                inconsistencias.append({
                    'Tipo': 'Valores Zerados',
                    'Coluna': self.coluna_valor_pagto,
                    'Quantidade': len(zerados),
                    'Exemplo': f"{len(zerados)} registros"
                })
        
        # Agências inválidas
        if 'agencia' in self.dados_limpos.columns:
            agencias_invalidas = self.dados_limpos[self.dados_limpos['agencia'].isnull()]
            if len(agencias_invalidas) > 0:
                inconsistencias.append({
                    'Tipo': 'Agências Inválidas',
                    'Coluna': 'agencia',
                    'Quantidade': len(agencias_invalidas),
                    'Exemplo': f"{len(agencias_invalidas)} registros"
                })
        
        # Nomes faltantes
        if 'nome' in self.dados_limpos.columns:
            nomes_faltantes = self.dados_limpos[self.dados_limpos['nome'].isnull()]
            if len(nomes_faltantes) > 0:
                inconsistencias.append({
                    'Tipo': 'Nomes Faltantes',
                    'Coluna': 'nome',
                    'Quantidade': len(nomes_faltantes),
                    'Exemplo': f"{len(nomes_faltantes)} registros"
                })
        
        if inconsistencias:
            self.inconsistencias = pd.DataFrame(inconsistencias)
        else:
            self.inconsistencias = pd.DataFrame()
    
    def _calcular_estatisticas(self):
        """Calcula estatísticas"""
        if self.dados_limpos is None or len(self.dados_limpos) == 0:
            return
        
        if self.coluna_valor_pagto and self.coluna_valor_pagto in self.dados_limpos.columns:
            self.total_pagamentos = self.dados_limpos[self.coluna_valor_pagto].sum()
    
    def _gerar_relatorio_executivo(self):
        """Gera relatório executivo"""
        self.relatorio_executivo = {
            'data_processamento': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'nome_arquivo': self.nome_arquivo,
            'total_registros': len(self.dados_limpos) if self.dados_limpos is not None else 0,
            'valor_total': self.total_pagamentos,
            'coluna_valor_principal': self.coluna_valor_pagto,
            'dados_faltantes': self.dados_faltantes.to_dict('records') if self.dados_faltantes is not None else [],
            'inconsistencias': self.inconsistencias.to_dict('records') if self.inconsistencias is not None else []
        }
    
    def mostrar_log(self):
        """Mostra log de processamento"""
        if self.log_processamento:
            with st.expander("📝 Log de Processamento", expanded=False):
                for entry in self.log_processamento:
                    if "ERRO" in entry.upper() or "❌" in entry:
                        st.error(entry)
                    elif "AVISO" in entry.upper() or "⚠️" in entry:
                        st.warning(entry)
                    elif "SUCESSO" in entry.upper() or "✅" in entry:
                        st.success(entry)
                    else:
                        st.info(entry)
    
    def mostrar_dados_originais(self):
        """Mostra dados originais"""
        if self.df_original is not None and not self.df_original.empty:
            with st.expander("🔍 Dados Originais (Primeiras 5 linhas)", expanded=False):
                st.write(f"Shape: {self.df_original.shape}")
                st.dataframe(self.df_original.head(5))
                st.write("Colunas originais:")
                for i, col in enumerate(self.df_original.columns, 1):
                    st.write(f"{i}. {col}")

# Inicializar sistema
sistema = SistemaPOT()

# ==============================================
# INTERFACE STREAMLIT
# ==============================================

st.title("💰 SISTEMA DE MONITORAMENTO DE PAGAMENTOS - POT")
st.markdown("---")

# Sidebar
with st.sidebar:
    st.header("📁 Upload do Arquivo")
    
    arquivo = st.file_uploader(
        "Selecione o arquivo CSV",
        type=['csv'],
        help="Arquivo CSV com delimitador ponto e vírgula"
    )
    
    if arquivo is not None:
        st.info(f"📄 Arquivo: {arquivo.name}")
        st.info(f"📊 Tamanho: {arquivo.size / 1024:.1f} KB")
        
        modo_debug = st.checkbox("🔍 Modo Debug", value=True)
        
        if st.button("🚀 PROCESSAR ARQUIVO", type="primary", use_container_width=True):
            with st.spinner("Processando arquivo..."):
                sucesso = sistema.processar_arquivo_streamlit(arquivo)
                if sucesso:
                    st.session_state['arquivo_processado'] = True
                    st.session_state['modo_debug'] = modo_debug
                    st.success("✅ Processado!")
                else:
                    st.error("❌ Erro no processamento")
    
    if 'arquivo_processado' in st.session_state and st.session_state['arquivo_processado']:
        st.markdown("---")
        if st.button("🔄 Novo Arquivo", use_container_width=True):
            st.session_state.clear()
            st.rerun()

# Área principal
if 'arquivo_processado' in st.session_state and st.session_state['arquivo_processado']:
    if sistema.arquivo_processado:
        
        # Mostrar log se modo debug
        if st.session_state.get('modo_debug', False):
            sistema.mostrar_log()
            sistema.mostrar_dados_originais()
        
        # Verificar se temos dados
        if sistema.dados_limpos is None or len(sistema.dados_limpos) == 0:
            st.error("""
            ❌ **Nenhum dado válido processado**
            
            **Possíveis causas:**
            1. Arquivo vazio
            2. Encoding incompatível
            3. Delimitador incorreto
            4. Formato inválido
            
            **Tente:**
            1. Abrir no bloco de notas
            2. Salvar como UTF-8
            3. Verificar ponto e vírgula
            """)
            return
        
        # ============================
        # RESUMO
        # ============================
        st.header("📊 RESUMO DO PROCESSAMENTO")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("📄 Registros", f"{len(sistema.dados_limpos):,}")
        
        with col2:
            if sistema.coluna_valor_pagto:
                valor = sistema.total_pagamentos
                st.metric("💰 Valor Total", f"R$ {valor:,.2f}")
            else:
                st.metric("💰 Valor Total", "N/A")
        
        with col3:
            if sistema.dados_faltantes is not None:
                total = sistema.dados_faltantes['Valores_Faltantes'].sum()
                st.metric("⚠️ Faltantes", f"{total:,}")
            else:
                st.metric("⚠️ Faltantes", "0")
        
        with col4:
            if sistema.inconsistencias is not None and not sistema.inconsistencias.empty:
                total = sistema.inconsistencias['Quantidade'].sum()
                st.metric("🚨 Inconsistências", f"{total:,}")
            else:
                st.metric("🚨 Inconsistências", "0")
        
        st.markdown("---")
        
        # ============================
        # DADOS FALTANTES
        # ============================
        st.header("🔍 DADOS FALTANTES")
        
        if sistema.dados_faltantes is not None and not sistema.dados_faltantes.empty:
            faltantes_filtrados = sistema.dados_faltantes[
                sistema.dados_faltantes['Valores_Faltantes'] > 0
            ]
            
            if not faltantes_filtrados.empty:
                st.dataframe(
                    faltantes_filtrados[['Coluna', 'Valores_Faltantes', 'Percentual_Faltante']],
                    use_container_width=True
                )
                
                if hasattr(sistema, 'linhas_com_faltantes_criticos') and not sistema.linhas_com_faltantes_criticos.empty:
                    st.subheader("🚨 Linhas Críticas")
                    st.dataframe(sistema.linhas_com_faltantes_criticos, use_container_width=True)
            else:
                st.success("✅ Nenhum dado faltante")
        else:
            st.success("✅ Nenhum dado faltante")
        
        st.markdown("---")
        
        # ============================
        # INCONSISTÊNCIAS
        # ============================
        st.header("🚨 INCONSISTÊNCIAS")
        
        if sistema.inconsistencias is not None and not sistema.inconsistencias.empty:
            st.dataframe(sistema.inconsistencias, use_container_width=True)
        else:
            st.success("✅ Nenhuma inconsistência")
        
        st.markdown("---")
        
        # ============================
        # DADOS PROCESSADOS
        # ============================
        st.header("👀 DADOS PROCESSADOS")
        
        tab1, tab2 = st.tabs(["📋 Tabela", "📊 Estatísticas"])
        
        with tab1:
            colunas = sistema.dados_limpos.columns.tolist()
            selecionadas = st.multiselect(
                "Colunas:",
                options=colunas,
                default=colunas[:min(6, len(colunas))]
            )
            
            linhas = st.slider("Linhas:", 5, 100, 20)
            
            if selecionadas:
                dados = sistema.dados_limpos[selecionadas].head(linhas)
                if sistema.coluna_valor_pagto and sistema.coluna_valor_pagto in dados.columns:
                    dados = dados.copy()
                    dados[sistema.coluna_valor_pagto] = dados[sistema.coluna_valor_pagto].apply(
                        lambda x: f"R$ {x:,.2f}" if pd.notna(x) else ""
                    )
                st.dataframe(dados, use_container_width=True, height=400)
        
        with tab2:
            if sistema.coluna_valor_pagto:
                valores = sistema.dados_limpos[sistema.coluna_valor_pagto]
                stats = valores.describe()
                
                col_a, col_b = st.columns(2)
                
                with col_a:
                    st.write("**Estatísticas:**")
                    for stat, val in stats.items():
                        st.write(f"**{stat}:** R$ {val:,.2f}")
                
                with col_b:
                    st.write("**Distribuição:**")
                    try:
                        hist, bins = np.histogram(valores, bins=10)
                        for i in range(len(hist)):
                            st.write(f"{bins[i]:.0f}-{bins[i+1]:.0f}: {hist[i]}")
                    except:
                        st.write("Não disponível")
        
        st.markdown("---")
        
        # ============================
        # EXPORTAÇÃO
        # ============================
        st.header("📥 EXPORTAÇÃO")
        
        col_exp1, col_exp2 = st.columns(2)
        
        with col_exp1:
            # CSV dos dados processados
            csv_data = sistema.dados_limpos.to_csv(index=False, sep=';', encoding='utf-8')
            st.download_button(
                label="📋 CSV Dados Processados",
                data=csv_data,
                file_name=f"dados_pot_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col_exp2:
            # CSV de inconsistências
            if sistema.inconsistencias is not None and not sistema.inconsistencias.empty:
                csv_incon = sistema.inconsistencias.to_csv(index=False, sep=';', encoding='utf-8')
                st.download_button(
                    label="🚨 CSV Inconsistências",
                    data=csv_incon,
                    file_name=f"inconsistencias_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
    
    else:
        st.error("❌ Falha no processamento")
        sistema.mostrar_log()
else:
    # Tela inicial
    st.markdown("""
    # 🚀 SISTEMA DE MONITORAMENTO POT
    
    ### 📋 **Funcionalidades:**
    
    ✅ **Processamento automático** de arquivos CSV
    ✅ **Análise de dados faltantes** com tabelas
    ✅ **Detecção de inconsistências**
    ✅ **Cálculo preciso** de valores totais
    ✅ **Exportação** em formato CSV
    
    ### 📁 **Como usar:**
    
    1. **Faça upload** do arquivo CSV na barra lateral
    2. **Clique em "Processar Arquivo"**
    3. **Analise** os dados faltantes e inconsistências
    4. **Exporte** os relatórios para correção
    
    ### ⚠️ **Formato esperado:**
    
    - CSV com **ponto e vírgula (;)**
    - **Valores:** R$ 1.593,90 ou 1593.90
    - **Encoding:** UTF-8 ou Latin-1
    """)
    
    st.markdown("---")
    
    with st.expander("📋 Exemplo do formato"):
        st.code("""
        Nome;Agencia;Valor Pagto;Data Pagto
        João Silva;1234;R$ 1.593,90;20/10/2025
        Maria Santos;5678;1593.90;21/10/2025
        """)

# Rodapé
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: gray;'>
    Sistema POT • Versão Simplificada • Processamento Confiável
    </div>
    """,
    unsafe_allow_html=True
)
