import pandas as pd
import os
import re
from datetime import datetime
import streamlit as st
import warnings
import chardet
warnings.filterwarnings('ignore')

# Configuração da página
st.set_page_config(
    page_title="Sistema POT - Monitoramento de Pagamentos",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

class SistemaPOTStreamlit:
    def __init__(self):
        self.df = None
        self.dados_limpos = None
        self.arquivo_processado = False
        self.nome_arquivo = ""
        self.total_pagamentos = 0
        
    def detectar_encoding(self, arquivo_path):
        """Detecta o encoding do arquivo"""
        try:
            # Ler primeiros bytes para detectar encoding
            with open(arquivo_path, 'rb') as f:
                raw_data = f.read(10000)
            
            resultado = chardet.detect(raw_data)
            encoding = resultado['encoding']
            confianca = resultado['confidence']
            
            st.info(f"🔍 Encoding detectado: {encoding} (confiança: {confianca:.2f})")
            
            # Mapear encoding comum para o pandas
            if encoding is None:
                return 'latin-1'
            
            encoding_map = {
                'ISO-8859-1': 'latin-1',
                'Windows-1252': 'cp1252',
                'ascii': 'utf-8',
                'UTF-8-SIG': 'utf-8'
            }
            
            return encoding_map.get(encoding, encoding)
            
        except Exception as e:
            st.warning(f"Não foi possível detectar encoding, usando latin-1: {str(e)[:50]}")
            return 'latin-1'
    
    def tentar_encodings(self, arquivo_path):
        """Tenta diferentes encodings até encontrar um que funcione"""
        encodings_para_tentar = [
            'latin-1',  # Mais comum para arquivos brasileiros
            'iso-8859-1',
            'cp1252',   # Windows
            'utf-8',
            'utf-8-sig',
            'cp850',
            'mac_roman'
        ]
        
        for encoding in encodings_para_tentar:
            try:
                st.info(f"Tentando encoding: {encoding}")
                df = pd.read_csv(arquivo_path, delimiter=';', encoding=encoding, nrows=5)
                if not df.empty and len(df.columns) > 1:
                    st.success(f"✅ Encoding funcionou: {encoding}")
                    return encoding
            except Exception as e:
                continue
        
        st.error("❌ Não foi possível ler o arquivo com nenhum encoding comum")
        return None
    
    def converter_valor(self, valor_str):
        """Converte valores monetários do formato brasileiro para float"""
        if pd.isna(valor_str) or valor_str == '':
            return 0.0
        
        try:
            # Se já for número, retornar direto
            if isinstance(valor_str, (int, float)):
                return float(valor_str)
            
            valor_str = str(valor_str).replace('R$', '').replace(' ', '').strip()
            
            # Remover pontos dos milhares e converter vírgula decimal para ponto
            if '.' in valor_str and ',' in valor_str:
                # Formato brasileiro: 1.593,90
                valor_str = valor_str.replace('.', '').replace(',', '.')
            elif ',' in valor_str:
                # Formato europeu: 1593,90
                valor_str = valor_str.replace(',', '.')
            
            return float(valor_str)
        except Exception as e:
            st.warning(f"Erro ao converter valor '{valor_str}': {str(e)[:50]}")
            return 0.0
    
    def processar_arquivo_streamlit(self, arquivo_upload):
        """Processa arquivo CSV de pagamentos do POT - Versão Streamlit"""
        try:
            with st.spinner("📥 Lendo arquivo..."):
                # Salvar arquivo temporariamente para detecção de encoding
                temp_path = f"temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                with open(temp_path, 'wb') as f:
                    f.write(arquivo_upload.getvalue())
                
                # Detectar encoding
                encoding = self.tentar_encodings(temp_path)
                
                if encoding is None:
                    # Tentar detecção automática
                    encoding = self.detectar_encoding(temp_path)
                
                # Ler arquivo com encoding detectado
                st.info(f"📖 Lendo arquivo com encoding: {encoding}")
                
                # Tentar ler linha por linha para debug
                with open(temp_path, 'r', encoding=encoding, errors='replace') as f:
                    linhas = f.readlines()
                
                st.success(f"✅ Arquivo lido: {len(linhas)} linhas detectadas")
                
                if len(linhas) < 2:
                    st.error("❌ Arquivo muito pequeno ou vazio")
                    return False
                
                # Mostrar preview do cabeçalho
                with st.expander("📋 Visualizar primeiras linhas do arquivo"):
                    st.text("Linha 1 (cabeçalho):")
                    st.code(linhas[0][:200])
                    if len(linhas) > 1:
                        st.text("Linha 2 (primeiros dados):")
                        st.code(linhas[1][:200])
                
                # Ler com pandas
                self.df = pd.read_csv(temp_path, delimiter=';', encoding=encoding, on_bad_lines='skip')
                
                # Limpar arquivo temporário
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            
            with st.spinner("🧹 Limpando dados..."):
                # Limpar dados
                self._limpar_dados()
                
            with st.spinner("📊 Calculando estatísticas..."):
                # Calcular estatísticas
                self._calcular_estatisticas()
                
            self.arquivo_processado = True
            self.nome_arquivo = arquivo_upload.name
            
            st.success(f"✅ Processamento concluído! {len(self.dados_limpos)} registros válidos")
            return True
            
        except Exception as e:
            st.error(f"❌ Erro ao processar arquivo: {str(e)[:200]}")
            return False
    
    def processar_arquivo_direto(self, arquivo_path):
        """Processa arquivo diretamente do caminho (para debug)"""
        try:
            # Detectar encoding
            encoding = self.tentar_encodings(arquivo_path)
            
            if encoding is None:
                encoding = self.detectar_encoding(arquivo_path)
            
            # Ler arquivo
            self.df = pd.read_csv(arquivo_path, delimiter=';', encoding=encoding, on_bad_lines='skip')
            
            # Limpar dados
            self._limpar_dados()
            
            # Calcular estatísticas
            self._calcular_estatisticas()
            
            self.arquivo_processado = True
            self.nome_arquivo = os.path.basename(arquivo_path)
            
            print(f"✅ Processamento concluído! {len(self.dados_limpos)} registros válidos")
            return True
            
        except Exception as e:
            print(f"❌ Erro ao processar arquivo: {str(e)}")
            return False
    
    def _limpar_dados(self):
        """Limpa e prepara os dados para análise"""
        if self.df is None or self.df.empty:
            st.error("❌ DataFrame vazio ou não carregado")
            return
        
        df_limpo = self.df.copy()
        
        # Remover linhas totalmente vazias
        linhas_iniciais = len(df_limpo)
        df_limpo = df_limpo.dropna(how='all')
        linhas_apos_vazias = len(df_limpo)
        
        st.info(f"Removidas {linhas_iniciais - linhas_apos_vazias} linhas totalmente vazias")
        
        # Verificar colunas disponíveis
        st.info(f"Colunas disponíveis: {list(df_limpo.columns)}")
        
        # Renomear colunas para padrão (remover acentos e espaços)
        mapeamento_colunas = {}
        for col in df_limpo.columns:
            col_limpa = str(col).strip().lower()
            col_limpa = col_limpa.replace(' ', '_').replace('.', '')
            # Remover acentos
            col_limpa = (col_limpa
                        .replace('á', 'a').replace('é', 'e').replace('í', 'i')
                        .replace('ó', 'o').replace('ú', 'u').replace('â', 'a')
                        .replace('ê', 'e').replace('î', 'i').replace('ô', 'o')
                        .replace('û', 'u').replace('ã', 'a').replace('õ', 'o')
                        .replace('ç', 'c'))
            mapeamento_colunas[col] = col_limpa
        
        df_limpo = df_limpo.rename(columns=mapeamento_colunas)
        st.info(f"Colunas renomeadas: {list(df_limpo.columns)}")
        
        # Identificar colunas de valor
        colunas_valor = []
        for col in df_limpo.columns:
            if any(termo in col for termo in ['valor', 'total', 'pagto', 'pagamento', 'desconto', 'dia']):
                colunas_valor.append(col)
        
        st.info(f"Colunas de valor identificadas: {colunas_valor}")
        
        # Converter colunas de valor
        for coluna in colunas_valor:
            if coluna in df_limpo.columns:
                df_limpo[coluna] = df_limpo[coluna].apply(self.converter_valor)
                st.info(f"✓ Convertida coluna: {coluna}")
        
        # Procurar coluna de dias
        coluna_dias = None
        for col in df_limpo.columns:
            if any(termo in col.lower() for termo in ['dia', 'dias', 'apagar']):
                coluna_dias = col
                break
        
        if coluna_dias and coluna_dias in df_limpo.columns:
            df_limpo[coluna_dias] = pd.to_numeric(df_limpo[coluna_dias], errors='coerce')
            st.info(f"✓ Convertida coluna de dias: {coluna_dias}")
        
        # Procurar coluna de data
        coluna_data = None
        for col in df_limpo.columns:
            if any(termo in col.lower() for termo in ['data', 'datapagto', 'dt', 'date']):
                coluna_data = col
                break
        
        if coluna_data and coluna_data in df_limpo.columns:
            # Tentar diferentes formatos de data
            try:
                df_limpo[coluna_data] = pd.to_datetime(df_limpo[coluna_data], format='%d/%m/%Y', errors='coerce')
                st.info(f"✓ Convertida coluna de data: {coluna_data} (formato DD/MM/AAAA)")
            except:
                try:
                    df_limpo[coluna_data] = pd.to_datetime(df_limpo[coluna_data], errors='coerce')
                    st.info(f"✓ Convertida coluna de data: {coluna_data} (formato automático)")
                except:
                    st.warning(f"⚠️ Não foi possível converter coluna de data: {coluna_data}")
        
        # Procurar coluna de valor de pagamento principal
        coluna_valor_pagto = None
        for col in colunas_valor:
            if 'pagto' in col or 'pagamento' in col:
                coluna_valor_pagto = col
                break
        
        if not coluna_valor_pagto and colunas_valor:
            coluna_valor_pagto = colunas_valor[0]
        
        if coluna_valor_pagto and coluna_valor_pagto in df_limpo.columns:
            # Remover linhas onde o valor é zero ou negativo
            df_limpo = df_limpo[df_limpo[coluna_valor_pagto] > 0]
            st.info(f"✓ Removidos registros com {coluna_valor_pagto} ≤ 0")
        
        self.dados_limpos = df_limpo
        
        # Verificar dados
        st.info(f"✅ Dados limpos: {len(df_limpo)} registros válidos")
        
        # Mostrar preview dos dados limpos
        with st.expander("👀 Visualizar dados processados"):
            st.dataframe(df_limpo.head(10))
    
    def _calcular_estatisticas(self):
        """Calcula estatísticas dos dados"""
        if self.dados_limpos is None or len(self.dados_limpos) == 0:
            st.error("❌ Nenhum dado para calcular estatísticas")
            return
        
        # Encontrar coluna de valor principal
        coluna_valor_principal = None
        for col in self.dados_limpos.columns:
            if any(termo in col.lower() for termo in ['valorpagto', 'valor_pagto', 'pagto', 'pagamento']):
                coluna_valor_principal = col
                break
        
        if not coluna_valor_principal:
            # Tentar encontrar qualquer coluna de valor
            for col in self.dados_limpos.select_dtypes(include=[np.number]).columns:
                if self.dados_limpos[col].sum() > 0:
                    coluna_valor_principal = col
                    break
        
        if coluna_valor_principal and coluna_valor_principal in self.dados_limpos.columns:
            self.total_pagamentos = self.dados_limpos[coluna_valor_principal].sum()
            st.info(f"💰 Valor total calculado: R$ {self.total_pagamentos:,.2f}")
        else:
            st.warning("⚠️ Não foi possível encontrar coluna de valor para cálculo do total")

# Inicializar sistema
sistema = SistemaPOTStreamlit()

# ==============================================
# INTERFACE STREAMLIT
# ==============================================

st.title("💰 SISTEMA DE MONITORAMENTO DE PAGAMENTOS - POT")
st.markdown("""
<div style='background-color: #f0f2f6; padding: 15px; border-radius: 10px; margin-bottom: 20px;'>
<strong>🚨 ATENÇÃO:</strong> Este sistema processa arquivos CSV com problemas de encoding. 
Se encontrar erros, o sistema tentará automaticamente diferentes codificações.
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# Sidebar para upload
with st.sidebar:
    st.header("📁 Upload de Arquivo")
    st.markdown("""
    **Formato esperado:**
    - CSV com delimitador **ponto e vírgula (;)**
    - Encoding comum: **Latin-1 (ISO-8859-1)**
    - Valores no formato brasileiro: **R$ 1.593,90**
    """)
    
    arquivo = st.file_uploader(
        "Selecione o arquivo CSV",
        type=['csv', 'txt'],
        help="Arquivo CSV com dados de pagamentos"
    )
    
    if arquivo is not None:
        st.info(f"📄 Arquivo selecionado: {arquivo.name}")
        st.info(f"📊 Tamanho: {arquivo.size / 1024:.1f} KB")
        
        # Opções de processamento
        st.markdown("---")
        st.header("⚙️ Opções de Processamento")
        
        encoding_manual = st.selectbox(
            "Encoding (se souber):",
            ["Auto-detect", "latin-1", "iso-8859-1", "cp1252", "utf-8", "cp850"],
            index=0
        )
        
        if st.button("🚀 Processar Arquivo", type="primary", use_container_width=True):
            if encoding_manual != "Auto-detect":
                # Salvar arquivo temporariamente e processar
                temp_path = f"temp_upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                with open(temp_path, 'wb') as f:
                    f.write(arquivo.getvalue())
                
                try:
                    with st.spinner(f"Processando com encoding {encoding_manual}..."):
                        sistema.df = pd.read_csv(temp_path, delimiter=';', encoding=encoding_manual, on_bad_lines='skip')
                        sistema._limpar_dados()
                        sistema._calcular_estatisticas()
                        sistema.arquivo_processado = True
                        sistema.nome_arquivo = arquivo.name
                    st.success("✅ Arquivo processado com sucesso!")
                    st.session_state['arquivo_processado'] = True
                except Exception as e:
                    st.error(f"❌ Erro com encoding {encoding_manual}: {str(e)[:100]}")
                    # Tentar processamento automático
                    sucesso = sistema.processar_arquivo_streamlit(arquivo)
                    if sucesso:
                        st.session_state['arquivo_processado'] = True
                finally:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
            else:
                # Processamento automático
                sucesso = sistema.processar_arquivo_streamlit(arquivo)
                if sucesso:
                    st.session_state['arquivo_processado'] = True
    
    st.markdown("---")
    st.markdown("### 🔧 Dicas para Encoding")
    
    with st.expander("Como resolver problemas de encoding"):
        st.markdown("""
        1. **Latin-1 (ISO-8859-1)**: Mais comum no Brasil
        2. **Windows-1252 (CP1252)**: Para arquivos do Excel
        3. **UTF-8**: Para arquivos modernos
        4. **CP850**: Para arquivos mais antigos
        
        **Sintomas de encoding errado:**
        - Caracteres estranhos: Ã§, Ã£, Ã©
        - Erro: "invalid continuation byte"
        - Acentuação incorreta
        """)
    
    if 'arquivo_processado' in st.session_state and st.session_state['arquivo_processado']:
        st.markdown("---")
        if st.button("🔄 Limpar e Recarregar", use_container_width=True):
            st.session_state.clear()
            st.rerun()

# Área principal
if 'arquivo_processado' in st.session_state and st.session_state['arquivo_processado']:
    if sistema.arquivo_processado and sistema.dados_limpos is not None and len(sistema.dados_limpos) > 0:
        
        # ============================
        # DASHBOARD GERAL
        # ============================
        st.header("📊 Dashboard de Análise")
        
        # Métricas principais
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                label="Total de Registros",
                value=f"{len(sistema.dados_limpos):,}",
                delta=None
            )
        
        with col2:
            st.metric(
                label="Valor Total Processado",
                value=f"R$ {sistema.total_pagamentos:,.2f}",
                delta=None
            )
        
        with col3:
            # Encontrar coluna de valor principal
            coluna_valor = None
            for col in sistema.dados_limpos.select_dtypes(include=[np.number]).columns:
                if sistema.dados_limpos[col].mean() > 0:
                    coluna_valor = col
                    break
            
            if coluna_valor:
                media = sistema.dados_limpos[coluna_valor].mean()
                st.metric(
                    label="Valor Médio",
                    value=f"R$ {media:,.2f}",
                    delta=None
                )
            else:
                st.metric(
                    label="Valor Médio",
                    value="N/A",
                    delta=None
                )
        
        with col4:
            # Contar colunas
            num_colunas = len(sistema.dados_limpos.columns)
            st.metric(
                label="Colunas Disponíveis",
                value=num_colunas,
                delta=None
            )
        
        st.markdown("---")
        
        # Informações do dataset
        st.subheader("📋 Informações do Dataset")
        
        col_info1, col_info2 = st.columns(2)
        
        with col_info1:
            st.write("**Colunas disponíveis:**")
            for col in sistema.dados_limpos.columns:
                tipo = str(sistema.dados_limpos[col].dtype)
                st.write(f"- `{col}` ({tipo})")
        
        with col_info2:
            st.write("**Estatísticas básicas:**")
            
            # Colunas numéricas
            numeric_cols = sistema.dados_limpos.select_dtypes(include=[np.number]).columns
            if len(numeric_cols) > 0:
                for col in numeric_cols[:3]:  # Mostrar até 3 colunas numéricas
                    stats = sistema.dados_limpos[col].describe()
                    st.write(f"**{col}:**")
                    st.write(f"  Média: R$ {stats['mean']:,.2f}")
                    st.write(f"  Min: R$ {stats['min']:,.2f}")
                    st.write(f"  Max: R$ {stats['max']:,.2f}")
        
        st.markdown("---")
        
        # Visualização de dados
        st.subheader("👀 Visualização dos Dados")
        
        # Filtros simples
        st.write("**Filtros rápidos:**")
        
        col_filtro1, col_filtro2 = st.columns(2)
        
        with col_filtro1:
            # Selecionar colunas para mostrar
            colunas_para_mostrar = st.multiselect(
                "Selecionar colunas:",
                options=sistema.dados_limpos.columns.tolist(),
                default=sistema.dados_limpos.columns.tolist()[:5] if len(sistema.dados_limpos.columns) > 5 else sistema.dados_limpos.columns.tolist()
            )
        
        with col_filtro2:
            # Número de linhas para mostrar
            num_linhas = st.slider(
                "Número de linhas:",
                min_value=5,
                max_value=100,
                value=20,
                step=5
            )
        
        # Mostrar dados filtrados
        if colunas_para_mostrar:
            dados_filtrados = sistema.dados_limpos[colunas_para_mostrar].head(num_linhas)
            
            # Formatar valores monetários
            for col in dados_filtrados.columns:
                if dados_filtrados[col].dtype in ['float64', 'int64']:
                    # Verificar se é coluna monetária
                    if any(termo in col.lower() for termo in ['valor', 'total', 'pagto', 'desconto']):
                        dados_filtrados[col] = dados_filtrados[col].apply(lambda x: f"R$ {x:,.2f}" if pd.notna(x) else "")
            
            st.dataframe(
                dados_filtrados,
                use_container_width=True,
                height=400
            )
        
        st.markdown("---")
        
        # Botões de ação
        st.subheader("📥 Exportação de Dados")
        
        col_exp1, col_exp2, col_exp3 = st.columns(3)
        
        with col_exp1:
            # Download CSV
            csv_data = sistema.dados_limpos.to_csv(index=False, sep=';', encoding='utf-8')
            st.download_button(
                label="📥 Download CSV",
                data=csv_data,
                file_name=f"dados_processados_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col_exp2:
            # Download Excel
            try:
                import io
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    sistema.dados_limpos.to_excel(writer, index=False, sheet_name='Dados')
                buffer.seek(0)
                
                st.download_button(
                    label="📥 Download Excel",
                    data=buffer,
                    file_name=f"dados_processados_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            except:
                st.warning("Excel não disponível")
        
        with col_exp3:
            # Copiar para clipboard
            if st.button("📋 Copiar Resumo", use_container_width=True):
                resumo = f"""
                RESUMO DO PROCESSAMENTO
                -----------------------
                Arquivo: {sistema.nome_arquivo}
                Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}
                Registros: {len(sistema.dados_limpos):,}
                Valor Total: R$ {sistema.total_pagamentos:,.2f}
                Colunas: {len(sistema.dados_limpos.columns)}
                """
                st.code(resumo)
        
        # Análise avançada
        st.markdown("---")
        st.subheader("🔍 Análise Avançada")
        
        analise_tipo = st.radio(
            "Selecione tipo de análise:",
            ["Resumo por Coluna", "Busca por Texto", "Filtros Avançados", "Estatísticas Detalhadas"],
            horizontal=True
        )
        
        if analise_tipo == "Resumo por Coluna":
            col_analise = st.selectbox(
                "Selecione coluna para análise:",
                options=sistema.dados_limpos.columns.tolist()
            )
            
            if col_analise:
                col_data = sistema.dados_limpos[col_analise]
                
                col_a1, col_a2 = st.columns(2)
                
                with col_a1:
                    st.write(f"**Resumo de '{col_analise}':**")
                    st.write(f"- Tipo: {col_data.dtype}")
                    st.write(f"- Valores únicos: {col_data.nunique()}")
                    st.write(f"- Valores nulos: {col_data.isnull().sum()}")
                
                with col_a2:
                    if pd.api.types.is_numeric_dtype(col_data):
                        st.write("**Estatísticas:**")
                        stats = col_data.describe()
                        for stat, value in stats.items():
                            st.write(f"- {stat}: {value:,.2f}")
        
        elif analise_tipo == "Busca por Texto":
            texto_busca = st.text_input("Texto para buscar:")
            if texto_busca:
                # Buscar em todas as colunas de texto
                resultados = pd.DataFrame()
                for col in sistema.dados_limpos.select_dtypes(include=['object']).columns:
                    mask = sistema.dados_limpos[col].astype(str).str.contains(texto_busca, case=False, na=False)
                    if mask.any():
                        if resultados.empty:
                            resultados = sistema.dados_limpos[mask]
                        else:
                            resultados = pd.concat([resultados, sistema.dados_limpos[mask]])
                
                if not resultados.empty:
                    st.success(f"✅ Encontrados {len(resultados)} resultados")
                    st.dataframe(resultados.head(20), use_container_width=True)
                else:
                    st.warning("⚠️ Nenhum resultado encontrado")
        
        elif analise_tipo == "Estatísticas Detalhadas":
            st.write(sistema.dados_limpos.describe(include='all'))
    
    else:
        st.error("❌ Nenhum dado válido processado. O arquivo pode estar vazio ou com formato incorreto.")
else:
    # Tela inicial
    st.header("👋 Bem-vindo ao Sistema POT")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("""
        ### 📋 Sobre o Sistema
        
        Este sistema foi desenvolvido para processar arquivos de pagamentos do POT
        que possuem problemas comuns de encoding e formatação.
        
        **Funcionalidades principais:**
        - ✅ **Detecção automática de encoding**
        - ✅ **Conversão de valores monetários brasileiros**
        - ✅ **Limpeza automática de dados**
        - ✅ **Dashboard interativo**
        - ✅ **Exportação em múltiplos formatos**
        
        **Problemas resolvidos:**
        1. Encoding incorreto (UTF-8, Latin-1, CP1252)
        2. Valores no formato R$ 1.593,90
        3. Datas no formato DD/MM/AAAA
        4. Delimitador ponto e vírgula
        """)
    
    with col2:
        st.markdown("""
        ### 🚀 Quick Start
        
        1. **Clique em 'Browse files'**
        2. **Selecione seu arquivo CSV**
        3. **Clique em 'Processar Arquivo'**
        4. **Aguarde o processamento**
        5. **Explore os dados**
        
        ### ⚠️ Solução de Problemas
        
        Se encontrar erros:
        - Tente selecionar encoding manualmente
        - Verifique o formato do arquivo
        - Confirme o delimitador (;)
        - Tente abrir no bloco de notas primeiro
        """)
    
    st.markdown("---")
    
    # Upload rápido
    st.subheader("🚀 Comece agora mesmo")
    
    arquivo_rapido = st.file_uploader(
        "Arraste e solte seu arquivo aqui",
        type=['csv'],
        label_visibility="collapsed"
    )
    
    if arquivo_rapido:
        st.info(f"📄 Pronto para processar: {arquivo_rapido.name}")
        if st.button("⚡ Processar Agora", type="primary"):
            sucesso = sistema.processar_arquivo_streamlit(arquivo_rapido)
            if sucesso:
                st.session_state['arquivo_processado'] = True
                st.rerun()

# ==============================================
# RODAPÉ
# ==============================================
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: gray; padding: 20px;'>
    <strong>Sistema de Monitoramento POT</strong> • 
    Versão 3.0 • 
    Tratamento Avançado de Encoding • 
    Desenvolvido para processar arquivos problemáticos
    </div>
    """,
    unsafe_allow_html=True
)

# Script para debug
if st.sidebar.checkbox("🐛 Modo Debug", value=False):
    st.sidebar.markdown("---")
    st.sidebar.header("Debug Information")
    
    if sistema.df is not None:
        st.sidebar.write(f"DataFrame shape: {sistema.df.shape}")
        st.sidebar.write(f"Colunas originais: {list(sistema.df.columns)}")
    
    if sistema.dados_limpos is not None:
        st.sidebar.write(f"Dados limpos shape: {sistema.dados_limpos.shape}")
        st.sidebar.write("Primeiras linhas:")
        st.sidebar.dataframe(sistema.dados_limpos.head(3))
