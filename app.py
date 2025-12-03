import pandas as pd
import os
import re
from datetime import datetime
import streamlit as st
import warnings
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
        
    def converter_valor(self, valor_str):
        """Converte valores monetários do formato brasileiro para float"""
        if pd.isna(valor_str) or valor_str == '':
            return 0.0
        
        try:
            valor_str = str(valor_str).replace('R$', '').replace(' ', '').strip()
            valor_str = valor_str.replace('.', '').replace(',', '.')
            return float(valor_str)
        except:
            return 0.0
    
    def processar_arquivo(self, arquivo_upload):
        """Processa arquivo CSV de pagamentos do POT"""
        try:
            with st.spinner("Processando arquivo..."):
                # Ler o arquivo
                self.df = pd.read_csv(arquivo_upload, delimiter=';', encoding='utf-8')
                
                # Limpar dados
                self._limpar_dados()
                
                # Calcular estatísticas
                self._calcular_estatisticas()
                
                self.arquivo_processado = True
                self.nome_arquivo = arquivo_upload.name
                
            return True
            
        except Exception as e:
            st.error(f"Erro ao processar arquivo: {str(e)[:100]}")
            return False
    
    def _limpar_dados(self):
        """Limpa e prepara os dados para análise"""
        df_limpo = self.df.copy()
        
        # Remover linhas totalmente vazias
        df_limpo = df_limpo.dropna(how='all')
        
        # Converter colunas de valor
        colunas_valor = ['Valor Total', 'Valor Desconto', 'Valor Pagto', 'Valor Dia']
        
        for coluna in colunas_valor:
            if coluna in df_limpo.columns:
                df_limpo[coluna] = df_limpo[coluna].apply(self.converter_valor)
        
        # Converter 'Dias a apagar' para numérico
        if 'Dias a apagar' in df_limpo.columns:
            df_limpo['Dias a apagar'] = pd.to_numeric(df_limpo['Dias a apagar'], errors='coerce')
        
        # Converter 'Data Pagto' para datetime
        if 'Data Pagto' in df_limpo.columns:
            df_limpo['Data Pagto'] = pd.to_datetime(df_limpo['Data Pagto'], format='%d/%m/%Y', errors='coerce')
        
        # Remover linhas onde 'Valor Pagto' é zero ou negativo
        if 'Valor Pagto' in df_limpo.columns:
            df_limpo = df_limpo[df_limpo['Valor Pagto'] > 0]
        
        self.dados_limpos = df_limpo
    
    def _calcular_estatisticas(self):
        """Calcula estatísticas dos dados"""
        if self.dados_limpos is None or len(self.dados_limpos) == 0:
            return
        
        self.total_pagamentos = self.dados_limpos['Valor Pagto'].sum() if 'Valor Pagto' in self.dados_limpos.columns else 0

# Inicializar sistema
sistema = SistemaPOTStreamlit()

# ==============================================
# INTERFACE STREAMLIT
# ==============================================

st.title("💰 SISTEMA DE MONITORAMENTO DE PAGAMENTOS - POT")
st.markdown("---")

# Sidebar para upload
with st.sidebar:
    st.header("📁 Upload de Arquivo")
    st.markdown("Faça o upload do arquivo CSV com os dados de pagamentos")
    
    arquivo = st.file_uploader(
        "Selecione o arquivo CSV",
        type=['csv'],
        help="Arquivo CSV com delimitador ponto e vírgula"
    )
    
    if arquivo is not None:
        if st.button("🔄 Processar Arquivo", type="primary", use_container_width=True):
            sucesso = sistema.processar_arquivo(arquivo)
            if sucesso:
                st.success("✅ Arquivo processado com sucesso!")
                st.session_state['arquivo_processado'] = True
            else:
                st.error("❌ Erro ao processar arquivo")
    
    st.markdown("---")
    st.markdown("### 📊 Opções de Análise")
    
    if 'arquivo_processado' in st.session_state and st.session_state['arquivo_processado']:
        analise_tipo = st.radio(
            "Selecione o tipo de análise:",
            ["📈 Dashboard Geral", "🔍 Busca por Nome", "🏢 Análise por Agência", "📋 Dados Completos"]
        )
    else:
        st.info("⏳ Faça upload de um arquivo para começar")

# Área principal
if 'arquivo_processado' in st.session_state and st.session_state['arquivo_processado']:
    if sistema.arquivo_processado and sistema.dados_limpos is not None:
        
        # ============================
        # DASHBOARD GERAL
        # ============================
        if analise_tipo == "📈 Dashboard Geral":
            st.header("📊 Dashboard de Análise")
            
            # Métricas principais
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    label="Total de Pagamentos",
                    value=f"{len(sistema.dados_limpos):,}",
                    delta=None
                )
            
            with col2:
                st.metric(
                    label="Valor Total",
                    value=f"R$ {sistema.total_pagamentos:,.2f}",
                    delta=None
                )
            
            with col3:
                media = sistema.dados_limpos['Valor Pagto'].mean() if 'Valor Pagto' in sistema.dados_limpos.columns else 0
                st.metric(
                    label="Média por Pagamento",
                    value=f"R$ {media:,.2f}",
                    delta=None
                )
            
            with col4:
                if 'Agencia' in sistema.dados_limpos.columns:
                    num_agencias = sistema.dados_limpos['Agencia'].nunique()
                    st.metric(
                        label="Número de Agências",
                        value=num_agencias,
                        delta=None
                    )
            
            st.markdown("---")
            
            # Análise por agência (TOP 10)
            if 'Agencia' in sistema.dados_limpos.columns:
                st.subheader("🏢 Top 10 Agências por Valor Total")
                
                agencias_top = sistema.dados_limpos.groupby('Agencia').agg({
                    'Valor Pagto': ['sum', 'count']
                }).round(2)
                
                agencias_top.columns = ['Valor Total', 'Quantidade']
                agencias_top = agencias_top.sort_values('Valor Total', ascending=False).head(10)
                
                # Formatar para exibição
                agencias_display = agencias_top.copy()
                agencias_display['Valor Total'] = agencias_display['Valor Total'].apply(lambda x: f"R$ {x:,.2f}")
                
                st.dataframe(
                    agencias_display,
                    use_container_width=True,
                    height=400
                )
            
            # Distribuição de valores
            st.subheader("💰 Distribuição de Valores")
            
            col_left, col_right = st.columns(2)
            
            with col_left:
                st.write("**Estatísticas Descritivas:**")
                stats = sistema.dados_limpos['Valor Pagto'].describe() if 'Valor Pagto' in sistema.dados_limpos.columns else pd.Series()
                stats_display = pd.DataFrame({
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
                st.dataframe(stats_display, use_container_width=True, hide_index=True)
            
            with col_right:
                if 'Dias a apagar' in sistema.dados_limpos.columns:
                    st.write("**Distribuição de Dias a Pagar:**")
                    dias_stats = sistema.dados_limpos['Dias a apagar'].describe()
                    dias_display = pd.DataFrame({
                        'Estatística': ['Média', 'Mínimo', '25%', 'Mediana', '75%', 'Máximo'],
                        'Dias': [
                            f"{dias_stats.get('mean', 0):.1f}",
                            f"{dias_stats.get('min', 0):.0f}",
                            f"{dias_stats.get('25%', 0):.0f}",
                            f"{dias_stats.get('50%', 0):.0f}",
                            f"{dias_stats.get('75%', 0):.0f}",
                            f"{dias_stats.get('max', 0):.0f}"
                        ]
                    })
                    st.dataframe(dias_display, use_container_width=True, hide_index=True)
            
            # Top 10 maiores pagamentos
            st.subheader("🏆 Top 10 Maiores Pagamentos")
            
            top_pagamentos = sistema.dados_limpos.nlargest(10, 'Valor Pagto')
            if 'Nome' in top_pagamentos.columns and 'Valor Pagto' in top_pagamentos.columns:
                top_display = top_pagamentos[['Nome', 'Valor Pagto']].copy()
                top_display['Valor Pagto'] = top_display['Valor Pagto'].apply(lambda x: f"R$ {x:,.2f}")
                
                st.dataframe(
                    top_display,
                    use_container_width=True,
                    hide_index=True
                )
        
        # ============================
        # BUSCA POR NOME
        # ============================
        elif analise_tipo == "🔍 Busca por Nome":
            st.header("🔍 Busca por Nome")
            
            nome_busca = st.text_input(
                "Digite o nome para buscar:",
                placeholder="Ex: João Silva",
                help="Busca parcial no campo Nome"
            )
            
            if nome_busca:
                resultados = sistema.dados_limpos[
                    sistema.dados_limpos['Nome'].str.contains(nome_busca, case=False, na=False)
                ]
                
                if len(resultados) > 0:
                    st.success(f"✅ Encontrados {len(resultados)} resultados")
                    
                    # Métricas da busca
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.metric(
                            "Total de Registros",
                            len(resultados)
                        )
                    
                    with col2:
                        valor_total = resultados['Valor Pagto'].sum() if 'Valor Pagto' in resultados.columns else 0
                        st.metric(
                            "Valor Total",
                            f"R$ {valor_total:,.2f}"
                        )
                    
                    # Mostrar resultados
                    st.subheader("📋 Resultados da Busca")
                    
                    # Formatar colunas para exibição
                    resultados_display = resultados.copy()
                    
                    # Formatar valores monetários
                    for col in ['Valor Total', 'Valor Pagto', 'Valor Dia']:
                        if col in resultados_display.columns:
                            resultados_display[col] = resultados_display[col].apply(lambda x: f"R$ {x:,.2f}" if pd.notna(x) else "")
                    
                    # Formatar data
                    if 'Data Pagto' in resultados_display.columns:
                        resultados_display['Data Pagto'] = resultados_display['Data Pagto'].dt.strftime('%d/%m/%Y')
                    
                    st.dataframe(
                        resultados_display,
                        use_container_width=True,
                        height=400
                    )
                    
                    # Opção para download
                    csv = resultados.to_csv(index=False, sep=';', encoding='utf-8')
                    st.download_button(
                        label="📥 Download dos Resultados (CSV)",
                        data=csv,
                        file_name=f"busca_{nome_busca}_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )
                else:
                    st.warning(f"⚠️ Nenhum resultado encontrado para '{nome_busca}'")
        
        # ============================
        # ANÁLISE POR AGÊNCIA
        # ============================
        elif analise_tipo == "🏢 Análise por Agência":
            st.header("🏢 Análise por Agência")
            
            if 'Agencia' in sistema.dados_limpos.columns:
                # Selecionar agência
                agencias = sorted(sistema.dados_limpos['Agencia'].dropna().unique())
                
                agencia_selecionada = st.selectbox(
                    "Selecione uma agência para análise detalhada:",
                    options=agencias,
                    format_func=lambda x: f"Agência {x}"
                )
                
                if agencia_selecionada:
                    dados_agencia = sistema.dados_limpos[sistema.dados_limpos['Agencia'] == agencia_selecionada]
                    
                    st.subheader(f"📊 Análise da Agência {agencia_selecionada}")
                    
                    # Métricas da agência
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.metric(
                            "Total de Pagamentos",
                            len(dados_agencia)
                        )
                    
                    with col2:
                        valor_total = dados_agencia['Valor Pagto'].sum()
                        st.metric(
                            "Valor Total",
                            f"R$ {valor_total:,.2f}"
                        )
                    
                    with col3:
                        media = dados_agencia['Valor Pagto'].mean()
                        st.metric(
                            "Média por Pagamento",
                            f"R$ {media:,.2f}"
                        )
                    
                    # Dados da agência
                    st.subheader("📋 Pagamentos da Agência")
                    
                    dados_display = dados_agencia.copy()
                    
                    # Formatar colunas
                    for col in ['Valor Total', 'Valor Pagto', 'Valor Dia']:
                        if col in dados_display.columns:
                            dados_display[col] = dados_display[col].apply(lambda x: f"R$ {x:,.2f}" if pd.notna(x) else "")
                    
                    if 'Data Pagto' in dados_display.columns:
                        dados_display['Data Pagto'] = dados_display['Data Pagto'].dt.strftime('%d/%m/%Y')
                    
                    st.dataframe(
                        dados_display,
                        use_container_width=True,
                        height=400
                    )
                    
                    # Resumo estatístico
                    st.subheader("📈 Estatísticas Detalhadas")
                    
                    stats_agencia = dados_agencia['Valor Pagto'].describe()
                    
                    col_stats1, col_stats2 = st.columns(2)
                    
                    with col_stats1:
                        st.write("**Distribuição de Valores:**")
                        stats_df = pd.DataFrame({
                            'Estatística': ['Mínimo', '25%', 'Mediana', '75%', 'Máximo'],
                            'Valor': [
                                f"R$ {stats_agencia.get('min', 0):,.2f}",
                                f"R$ {stats_agencia.get('25%', 0):,.2f}",
                                f"R$ {stats_agencia.get('50%', 0):,.2f}",
                                f"R$ {stats_agencia.get('75%', 0):,.2f}",
                                f"R$ {stats_agencia.get('max', 0):,.2f}"
                            ]
                        })
                        st.dataframe(stats_df, use_container_width=True, hide_index=True)
                    
                    with col_stats2:
                        if 'Dias a apagar' in dados_agencia.columns:
                            st.write("**Dias a Pagar:**")
                            dias_agencia = dados_agencia['Dias a apagar'].describe()
                            dias_df = pd.DataFrame({
                                'Estatística': ['Média', 'Mínimo', 'Máximo'],
                                'Dias': [
                                    f"{dias_agencia.get('mean', 0):.1f}",
                                    f"{dias_agencia.get('min', 0):.0f}",
                                    f"{dias_agencia.get('max', 0):.0f}"
                                ]
                            })
                            st.dataframe(dias_df, use_container_width=True, hide_index=True)
            else:
                st.warning("⚠️ Coluna 'Agencia' não encontrada nos dados")
        
        # ============================
        # DADOS COMPLETOS
        # ============================
        elif analise_tipo == "📋 Dados Completos":
            st.header("📋 Dados Completos Processados")
            
            # Filtros
            st.subheader("🔍 Filtros")
            
            col_filtro1, col_filtro2 = st.columns(2)
            
            with col_filtro1:
                if 'Agencia' in sistema.dados_limpos.columns:
                    agencias_filtro = st.multiselect(
                        "Filtrar por Agência:",
                        options=sorted(sistema.dados_limpos['Agencia'].dropna().unique()),
                        default=[]
                    )
            
            with col_filtro2:
                # Filtro por valor
                min_valor = float(sistema.dados_limpos['Valor Pagto'].min()) if 'Valor Pagto' in sistema.dados_limpos.columns else 0
                max_valor = float(sistema.dados_limpos['Valor Pagto'].max()) if 'Valor Pagto' in sistema.dados_limpos.columns else 10000
                
                valor_range = st.slider(
                    "Filtrar por Valor:",
                    min_value=min_valor,
                    max_value=max_valor,
                    value=(min_valor, max_valor),
                    step=100.0,
                    format="R$ %.2f"
                )
            
            # Aplicar filtros
            dados_filtrados = sistema.dados_limpos.copy()
            
            if 'agencia' in locals() and agencias_filtro:
                dados_filtrados = dados_filtrados[dados_filtrados['Agencia'].isin(agencias_filtro)]
            
            if 'Valor Pagto' in dados_filtrados.columns:
                dados_filtrados = dados_filtrados[
                    (dados_filtrados['Valor Pagto'] >= valor_range[0]) & 
                    (dados_filtrados['Valor Pagto'] <= valor_range[1])
                ]
            
            st.metric(
                "Registros Filtrados",
                f"{len(dados_filtrados):,} de {len(sistema.dados_limpos):,}"
            )
            
            # Formatar dados para exibição
            dados_display = dados_filtrados.copy()
            
            # Formatar valores monetários
            for col in ['Valor Total', 'Valor Desconto', 'Valor Pagto', 'Valor Dia']:
                if col in dados_display.columns:
                    dados_display[col] = dados_display[col].apply(lambda x: f"R$ {x:,.2f}" if pd.notna(x) else "")
            
            # Formatar datas
            date_cols = ['Data Pagto']
            for col in date_cols:
                if col in dados_display.columns:
                    dados_display[col] = dados_display[col].dt.strftime('%d/%m/%Y')
            
            # Mostrar tabela
            st.subheader("📊 Tabela de Dados")
            
            # Paginação
            page_size = st.selectbox("Registros por página:", [10, 25, 50, 100], index=1)
            
            # Calcular número de páginas
            total_pages = max(1, len(dados_display) // page_size + (1 if len(dados_display) % page_size > 0 else 0))
            
            # Seletor de página
            if total_pages > 1:
                page_number = st.number_input("Página:", min_value=1, max_value=total_pages, value=1, step=1)
                start_idx = (page_number - 1) * page_size
                end_idx = start_idx + page_size
                
                st.write(f"Mostrando registros {start_idx + 1} a {min(end_idx, len(dados_display))} de {len(dados_display)}")
                
                dados_pagina = dados_display.iloc[start_idx:end_idx]
            else:
                dados_pagina = dados_display
            
            # Exibir tabela
            st.dataframe(
                dados_pagina,
                use_container_width=True,
                height=500
            )
            
            # Botões de download
            st.subheader("📥 Download")
            
            col_dl1, col_dl2 = st.columns(2)
            
            with col_dl1:
                csv_filtrado = dados_filtrados.to_csv(index=False, sep=';', encoding='utf-8')
                st.download_button(
                    label="📥 Download Dados Filtrados (CSV)",
                    data=csv_filtrado,
                    file_name=f"dados_filtrados_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            
            with col_dl2:
                csv_completo = sistema.dados_limpos.to_csv(index=False, sep=';', encoding='utf-8')
                st.download_button(
                    label="📥 Download Todos os Dados (CSV)",
                    data=csv_completo,
                    file_name=f"dados_completos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        
        # ============================
        # BOTÃO DE RESET
        # ============================
        st.markdown("---")
        if st.button("🔄 Processar Outro Arquivo", use_container_width=True):
            st.session_state.clear()
            st.rerun()
    
    else:
        st.warning("⚠️ Nenhum dado processado. Faça upload de um arquivo válido.")
else:
    # Tela inicial
    st.info("👋 Bem-vindo ao Sistema de Monitoramento de Pagamentos POT")
    
    col_intro1, col_intro2 = st.columns(2)
    
    with col_intro1:
        st.markdown("""
        ### 📋 Funcionalidades:
        
        - **📊 Dashboard Geral**: Métricas e análises completas
        - **🔍 Busca por Nome**: Encontre pagamentos específicos
        - **🏢 Análise por Agência**: Detalhes por agência
        - **📋 Dados Completos**: Visualização e filtros avançados
        - **📥 Exportação**: Download em formato CSV
        
        ### 📁 Formato do Arquivo:
        
        O arquivo deve ser CSV com delimitador **ponto e vírgula (;)**
        
        Colunas esperadas:
        - Nome
        - Agencia
        - Valor Pagto
        - Data Pagto
        - Dias a apagar
        """)
    
    with col_intro2:
        st.markdown("""
        ### 🚀 Como Usar:
        
        1. **Faça upload** do arquivo CSV na barra lateral
        2. **Clique em Processar Arquivo**
        3. **Selecione o tipo de análise**
        4. **Explore os dados** com as ferramentas disponíveis
        
        ### ⚠️ Requisitos:
        
        - Arquivo CSV válido
        - Formato brasileiro para valores (R$ 1.593,90)
        - Datas no formato DD/MM/AAAA
        
        ### 📞 Suporte:
        
        Em caso de problemas, verifique:
        - Formato do arquivo
        - Encoding (UTF-8 recomendado)
        - Presença das colunas necessárias
        """)
    
    st.markdown("---")
    st.warning("⏳ Aguardando upload do arquivo...")

# ==============================================
# RODAPÉ
# ==============================================
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: gray;'>
    Sistema de Monitoramento de Pagamentos POT • Desenvolvido para análise de dados financeiros • Versão 2.0
    </div>
    """,
    unsafe_allow_html=True
)
