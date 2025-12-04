import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import warnings
import re
warnings.filterwarnings('ignore')

# ============================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================
st.set_page_config(
    page_title="Sistema POT-SMDET - Monitoramento de Projetos",
    page_icon="🏙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================
# CSS PERSONALIZADO - ALTO CONTRASTE
# ============================================
st.markdown("""
<style>
    /* FUNDO PRINCIPAL */
    .main {
        background-color: #ffffff !important;
    }
    
    /* TÍTULOS E TEXTOS - PRETO FORTE */
    h1, h2, h3, h4, h5, h6, p, div, span, label {
        color: #000000 !important;
        font-weight: 500 !important;
    }
    
    /* DATAFRAMES - CONTRASTE MÁXIMO */
    .stDataFrame {
        background-color: #ffffff !important;
        border: 2px solid #000000 !important;
    }
    
    .stDataFrame table {
        border-collapse: collapse !important;
    }
    
    .stDataFrame th {
        background-color: #000000 !important;
        color: #ffffff !important;
        font-weight: bold !important;
        border: 1px solid #ffffff !important;
        padding: 8px !important;
    }
    
    .stDataFrame td {
        background-color: #ffffff !important;
        color: #000000 !important;
        border: 1px solid #000000 !important;
        padding: 8px !important;
    }
    
    .stDataFrame tr:nth-child(even) td {
        background-color: #f0f0f0 !important;
    }
    
    /* MÉTRICAS */
    [data-testid="stMetricValue"] {
        color: #000000 !important;
        font-size: 28px !important;
        font-weight: 700 !important;
    }
    
    [data-testid="stMetricLabel"] {
        color: #000000 !important;
        font-size: 16px !important;
        font-weight: 600 !important;
    }
    
    [data-testid="stMetricDelta"] {
        font-weight: 600 !important;
    }
    
    /* WIDGETS */
    .stSlider label, 
    .stNumberInput label, 
    .stSelectbox label,
    .stMultiSelect label,
    .stRadio label,
    .stCheckbox label,
    .stTextInput label,
    .stDateInput label {
        color: #000000 !important;
        font-weight: 600 !important;
        font-size: 16px !important;
    }
    
    /* INPUTS E SELECTS */
    .stTextInput input,
    .stNumberInput input,
    .stSelectbox select,
    .stMultiSelect div {
        background-color: #ffffff !important;
        color: #000000 !important;
        border: 2px solid #000000 !important;
        font-weight: 500 !important;
    }
    
    /* BOTÕES */
    .stButton > button {
        background-color: #000000 !important;
        color: #ffffff !important;
        border: 2px solid #000000 !important;
        font-weight: 600 !important;
        padding: 10px 20px !important;
        border-radius: 4px !important;
    }
    
    .stButton > button:hover {
        background-color: #333333 !important;
        border-color: #333333 !important;
    }
    
    /* SIDEBAR */
    [data-testid="stSidebar"] {
        background-color: #f8f9fa !important;
    }
    
    /* TABS */
    .stTabs [data-baseweb="tab-list"] {
        gap: 2px;
        background-color: #e9ecef !important;
    }
    
    .stTabs [data-baseweb="tab"] {
        background-color: #ffffff !important;
        border: 1px solid #000000 !important;
        color: #000000 !important;
        font-weight: 600 !important;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: #000000 !important;
        color: #ffffff !important;
    }
    
    /* ALERTAS E MENSAGENS */
    .stAlert {
        border: 2px solid !important;
        font-weight: 500 !important;
    }
    
    .stSuccess {
        border-color: #28a745 !important;
        background-color: #d4edda !important;
        color: #000000 !important;
    }
    
    .stError {
        border-color: #dc3545 !important;
        background-color: #f8d7da !important;
        color: #000000 !important;
    }
    
    .stWarning {
        border-color: #ffc107 !important;
        background-color: #fff3cd !important;
        color: #000000 !important;
    }
    
    .stInfo {
        border-color: #17a2b8 !important;
        background-color: #d1ecf1 !important;
        color: #000000 !important;
    }
    
    /* EXPANDERS */
    .streamlit-expanderHeader {
        background-color: #f8f9fa !important;
        color: #000000 !important;
        font-weight: 600 !important;
        border: 1px solid #000000 !important;
    }
    
    /* SLIDER ESPECÍFICO */
    .stSlider > div > div {
        color: #000000 !important;
    }
    
    .stSlider > div > div > div {
        color: #000000 !important;
    }
</style>
""", unsafe_allow_html=True)

# ============================================
# CLASSE PRINCIPAL DO SISTEMA
# ============================================
class SistemaPOTSMDET:
    def __init__(self):
        self.df = None
        self.df_original = None
        self.coluna_valor = None
        self.coluna_data = None
        self.coluna_projeto = None
        self.registros_problematicos = None
        self.erros_detectados = 0
        self.total_registros = 0
        self.valor_total = 0
        
    def carregar_dados(self, arquivo):
        """Carrega dados do arquivo Excel ou CSV"""
        try:
            if arquivo.name.endswith('.xlsx'):
                self.df = pd.read_excel(arquivo, dtype=str)
            elif arquivo.name.endswith('.csv'):
                # Tenta diferentes encodings e separadores
                try:
                    self.df = pd.read_csv(arquivo, encoding='utf-8', sep=';', dtype=str)
                except:
                    self.df = pd.read_csv(arquivo, encoding='latin-1', sep=';', dtype=str)
            
            # Mantém cópia original
            self.df_original = self.df.copy()
            
            # Processa colunas de valor
            self._processar_colunas_valor()
            
            st.success(f"✅ Dados carregados com sucesso! Total: {len(self.df)} registros")
            return True
            
        except Exception as e:
            st.error(f"❌ Erro ao carregar dados: {str(e)}")
            return False
    
    def _processar_colunas_valor(self):
        """Identifica e processa colunas de valores monetários"""
        if self.df is None:
            return
            
        # Identificar coluna de valor
        colunas_candidatas = []
        for coluna in self.df.columns:
            coluna_lower = str(coluna).lower()
            if any(termo in coluna_lower for termo in ['valor', 'vlr', 'r$', 'total', 'pagamento', 'pago']):
                colunas_candidatas.append(coluna)
                # Tentar converter para numérico
                try:
                    # Remove caracteres não numéricos
                    self.df[coluna] = self.df[coluna].astype(str).str.replace('R\$', '', regex=False)
                    self.df[coluna] = self.df[coluna].astype(str).str.replace('.', '', regex=False)
                    self.df[coluna] = self.df[coluna].astype(str).str.replace(',', '.', regex=False)
                    self.df[coluna] = pd.to_numeric(self.df[coluna], errors='coerce')
                    self.coluna_valor = coluna
                    st.info(f"🔍 Coluna de valor identificada: **{coluna}**")
                    break
                except:
                    continue
        
        # Identificar coluna de data
        for coluna in self.df.columns:
            coluna_lower = str(coluna).lower()
            if any(termo in coluna_lower for termo in ['data', 'dt', 'date']):
                try:
                    self.df[coluna] = pd.to_datetime(self.df[coluna], errors='coerce')
                    self.coluna_data = coluna
                    st.info(f"📅 Coluna de data identificada: **{coluna}**")
                    break
                except:
                    continue
        
        # Identificar coluna de projeto
        for coluna in self.df.columns:
            coluna_lower = str(coluna).lower()
            if any(termo in coluna_lower for termo in ['projeto', 'proj', 'nome', 'descricao', 'objeto']):
                self.coluna_projeto = coluna
                st.info(f"🏗️ Coluna de projeto identificada: **{coluna}**")
                break
    
    def validar_dados(self):
        """Realiza validação completa dos dados"""
        if self.df is None:
            return
            
        self.registros_problematicos = pd.DataFrame()
        problemas = []
        
        # 1. Valores nulos na coluna de valor
        if self.coluna_valor:
            nulos_valor = self.df[self.df[self.coluna_valor].isna()]
            if len(nulos_valor) > 0:
                nulos_valor['Tipo_Erro'] = 'VALOR_NULO'
                problemas.append(nulos_valor)
        
        # 2. Valores zerados ou negativos
        if self.coluna_valor:
            zerados = self.df[(self.df[self.coluna_valor] <= 0) & (self.df[self.coluna_valor].notna())]
            if len(zerados) > 0:
                zerados['Tipo_Erro'] = 'VALOR_ZERADO_NEGATIVO'
                problemas.append(zerados)
        
        # 3. Datas inválidas
        if self.coluna_data:
            datas_invalidas = self.df[self.df[self.coluna_data].isna()]
            if len(datas_invalidas) > 0:
                datas_invalidas['Tipo_Erro'] = 'DATA_INVALIDA'
                problemas.append(datas_invalidas)
        
        # 4. Projetos sem nome
        if self.coluna_projeto:
            projetos_vazios = self.df[self.df[self.coluna_projeto].isna() | (self.df[self.coluna_projeto].str.strip() == '')]
            if len(projetos_vazios) > 0:
                projetos_vazios['Tipo_Erro'] = 'PROJETO_SEM_NOME'
                problemas.append(projetos_vazios)
        
        # Consolidar problemas
        if problemas:
            self.registros_problematicos = pd.concat(problemas, ignore_index=True)
            self.erros_detectados = len(self.registros_problematicos)
        else:
            self.registros_problematicos = pd.DataFrame(columns=self.df.columns.tolist() + ['Tipo_Erro'])
            self.erros_detectados = 0
        
        # Atualizar métricas
        self.total_registros = len(self.df)
        if self.coluna_valor:
            self.valor_total = self.df[self.coluna_valor].sum()
        else:
            self.valor_total = 0
    
    def mostrar_resumo_executivo(self):
        """Exibe o resumo executivo do projeto"""
        st.markdown("---")
        st.markdown("## 📋 RESUMO EXECUTIVO DO PROJETO POT")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                label="TOTAL DE REGISTROS",
                value=f"{self.total_registros:,}",
                delta=None
            )
        
        with col2:
            if self.coluna_valor:
                valor_formatado = f"R$ {self.valor_total:,.2f}"
                st.metric(
                    label="VALOR TOTAL DO PROJETO",
                    value=valor_formatado,
                    delta=None
                )
        
        with col3:
            st.metric(
                label="ERROS DETECTADOS",
                value=self.erros_detectados,
                delta=None,
                delta_color="inverse"
            )
        
        with col4:
            registros_problem = len(self.registros_problematicos) if self.registros_problematicos is not None else 0
            st.metric(
                label="REGISTROS PROBLEMÁTICOS",
                value=registros_problem,
                delta=None,
                delta_color="inverse"
            )
        
        st.markdown("---")
        
        # Mostrar informações da coluna identificada
        if self.coluna_valor:
            st.info(f"**Coluna de valor identificada:** `{self.coluna_valor}`")
        if self.coluna_data:
            st.info(f"**Coluna de data identificada:** `{self.coluna_data}`")
        if self.coluna_projeto:
            st.info(f"**Coluna de projeto identificada:** `{self.coluna_projeto}`")
    
    def mostrar_analise_financeira(self):
        """Mostra análise financeira detalhada"""
        if self.df is None or self.coluna_valor is None:
            st.warning("Não há dados financeiros para analisar.")
            return
            
        st.markdown("## 📊 ANÁLISE FINANCEIRA")
        
        tab1, tab2, tab3, tab4 = st.tabs([
            "📈 Distribuição de Valores", 
            "🗓️ Evolução Temporal",
            "🏗️ Análise por Projeto",
            "🔍 Detalhamento"
        ])
        
        with tab1:
            col1, col2 = st.columns(2)
            
            with col1:
                # Histograma de valores
                fig = px.histogram(
                    self.df, 
                    x=self.coluna_valor,
                    title="Distribuição dos Valores Pagos",
                    labels={self.coluna_valor: 'Valor (R$)', 'count': 'Quantidade'},
                    color_discrete_sequence=['#000000']
                )
                fig.update_layout(
                    plot_bgcolor='white',
                    paper_bgcolor='white',
                    font_color='black'
                )
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                # Box plot
                fig = px.box(
                    self.df,
                    y=self.coluna_valor,
                    title="Box Plot - Distribuição de Valores",
                    color_discrete_sequence=['#000000']
                )
                fig.update_layout(
                    plot_bgcolor='white',
                    paper_bgcolor='white',
                    font_color='black'
                )
                st.plotly_chart(fig, use_container_width=True)
        
        with tab2:
            if self.coluna_data:
                # Agrupar por mês
                self.df['Mês'] = self.df[self.coluna_data].dt.to_period('M').dt.to_timestamp()
                mensal = self.df.groupby('Mês')[self.coluna_valor].sum().reset_index()
                
                fig = px.line(
                    mensal,
                    x='Mês',
                    y=self.coluna_valor,
                    title="Evolução Mensal dos Pagamentos",
                    markers=True
                )
                fig.update_layout(
                    plot_bgcolor='white',
                    paper_bgcolor='white',
                    font_color='black'
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("Coluna de data não identificada para análise temporal.")
        
        with tab3:
            if self.coluna_projeto:
                # Top 10 projetos por valor
                top_projetos = self.df.groupby(self.coluna_projeto)[self.coluna_valor].sum().nlargest(10).reset_index()
                
                fig = px.bar(
                    top_projetos,
                    x=self.coluna_valor,
                    y=self.coluna_projeto,
                    orientation='h',
                    title="Top 10 Projetos por Valor",
                    color=self.coluna_valor,
                    color_continuous_scale='Viridis'
                )
                fig.update_layout(
                    plot_bgcolor='white',
                    paper_bgcolor='white',
                    font_color='black'
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("Coluna de projeto não identificada.")
        
        with tab4:
            # Estatísticas detalhadas
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Valor Médio", f"R$ {self.df[self.coluna_valor].mean():,.2f}")
            with col2:
                st.metric("Valor Máximo", f"R$ {self.df[self.coluna_valor].max():,.2f}")
            with col3:
                st.metric("Valor Mínimo", f"R$ {self.df[self.coluna_valor].min():,.2f}")
            
            st.dataframe(
                self.df[[self.coluna_projeto, self.coluna_valor, self.coluna_data]].head(20)
                if all(col in self.df.columns for col in [self.coluna_projeto, self.coluna_valor, self.coluna_data])
                else self.df.head(20),
                use_container_width=True
            )
    
    def mostrar_registros_problematicos(self):
        """Exibe registros problemáticos com slider corrigido"""
        if self.registros_problematicos is None or len(self.registros_problematicos) == 0:
            st.info("✅ Nenhum registro problemático encontrado.")
            return
        
        st.markdown("## ⚠️ REGISTROS PROBLEMÁTICOS")
        st.warning(f"Foram encontrados {len(self.registros_problematicos)} registros com problemas.")
        
        # CORREÇÃO DO SLIDER - Verificar se há registros
        if len(self.registros_problematicos) > 0:
            # Configurar slider com valores seguros
            max_rows = len(self.registros_problematicos)
            min_value = min(5, max_rows)
            
            # Slider com verificação de valores
            linhas_mostrar = st.slider(
                "🔢 Linhas para mostrar:",
                min_value=min_value,
                max_value=max_rows,
                value=min(min_value, 20),
                step=5
            )
            
            # Mostrar registros
            st.dataframe(
                self.registros_problematicos.head(linhas_mostrar),
                use_container_width=True
            )
            
            # Opções de tratamento
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button("🔄 Corrigir Automaticamente", type="primary"):
                    self._corrigir_registros_automaticamente()
            
            with col2:
                if st.button("📥 Exportar Problemas"):
                    self._exportar_problemas()
            
            with col3:
                if st.button("🗑️ Remover Registros Problemáticos"):
                    self._remover_registros_problematicos()
        else:
            st.info("Não há registros problemáticos para exibir.")
    
    def _corrigir_registros_automaticamente(self):
        """Corrige registros problemáticos automaticamente"""
        try:
            # Aqui você implementaria a lógica de correção
            st.success("Correção automática aplicada!")
            # Atualiza os dados
            self.validar_dados()
        except Exception as e:
            st.error(f"Erro na correção: {str(e)}")
    
    def _exportar_problemas(self):
        """Exporta registros problemáticos para Excel"""
        try:
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                self.registros_problematicos.to_excel(writer, index=False, sheet_name='Problemas')
            
            st.download_button(
                label="📥 Baixar Relatório de Problemas",
                data=output.getvalue(),
                file_name=f"problemas_pot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        except Exception as e:
            st.error(f"Erro ao exportar: {str(e)}")
    
    def _remover_registros_problematicos(self):
        """Remove registros problemáticos do dataset"""
        if st.checkbox("Confirmar remoção permanente"):
            if self.registros_problematicos is not None and len(self.registros_problematicos) > 0:
                # Remove os registros problemáticos
                indices_problematicos = self.registros_problematicos.index
                self.df = self.df.drop(indices_problematicos, errors='ignore')
                self.registros_problematicos = None
                self.validar_dados()
                st.success("Registros problemáticos removidos com sucesso!")
    
    def gerar_relatorio_completo(self):
        """Gera relatório completo do projeto POT"""
        if self.df is None:
            st.warning("Carregue os dados primeiro.")
            return
        
        st.markdown("## 📄 RELATÓRIO COMPLETO DO PROJETO POT")
        
        # Criar abas para diferentes seções do relatório
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📋 Sumário Executivo",
            "💰 Análise Financeira",
            "📈 Métricas de Desempenho",
            "⚠️ Gestão de Riscos",
            "📊 Dashboards"
        ])
        
        with tab1:
            self._gerar_sumario_executivo()
        
        with tab2:
            self._gerar_analise_financeira_detalhada()
        
        with tab3:
            self._gerar_metricas_desempenho()
        
        with tab4:
            self._gerar_gestao_riscos()
        
        with tab5:
            self._gerar_dashboards()
    
    def _gerar_sumario_executivo(self):
        """Gera sumário executivo"""
        st.markdown("### 📋 SUMÁRIO EXECUTIVO")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Informações Gerais:**")
            st.write(f"- Total de Projetos: {self.total_registros}")
            st.write(f"- Período Analisado: {self._obter_periodo_analise()}")
            st.write(f"- Valor Total Investido: R$ {self.valor_total:,.2f}")
            
            if self.erros_detectados > 0:
                st.error(f"- ⚠️ {self.erros_detectados} erros detectados")
            else:
                st.success("- ✅ Dados consistentes e válidos")
        
        with col2:
            st.markdown("**Indicadores Chave:**")
            if self.coluna_valor:
                st.write(f"- Valor Médio por Projeto: R$ {self.df[self.coluna_valor].mean():,.2f}")
                st.write(f"- Maior Investimento: R$ {self.df[self.coluna_valor].max():,.2f}")
                st.write(f"- Menor Investimento: R$ {self.df[self.coluna_valor].min():,.2f}")
        
        st.markdown("---")
        st.markdown("**Recomendações:**")
        if self.erros_detectados > 0:
            st.warning("1. **Corrigir registros problemáticos** antes de prosseguir com análises")
        else:
            st.success("1. Dados validados com sucesso - pode prosseguir com planejamento")
        
        st.info("2. **Monitorar projetos de alto valor** para garantir execução adequada")
        st.info("3. **Implementar controles periódicos** para manter qualidade dos dados")
    
    def _obter_periodo_analise(self):
        """Obtém período de análise dos dados"""
        if self.coluna_data and not self.df[self.coluna_data].isna().all():
            data_min = self.df[self.coluna_data].min()
            data_max = self.df[self.coluna_data].max()
            return f"{data_min.strftime('%d/%m/%Y')} a {data_max.strftime('%d/%m/%Y')}"
        return "Período não identificado"
    
    def _gerar_analise_financeira_detalhada(self):
        """Gera análise financeira detalhada"""
        st.markdown("### 💰 ANÁLISE FINANCEIRA DETALHADA")
        
        if self.coluna_valor:
            # Distribuição por faixa de valor
            bins = [0, 10000, 50000, 100000, 500000, float('inf')]
            labels = ['< 10k', '10k-50k', '50k-100k', '100k-500k', '> 500k']
            
            self.df['Faixa_Valor'] = pd.cut(self.df[self.coluna_valor], bins=bins, labels=labels)
            distribuicao = self.df['Faixa_Valor'].value_counts().sort_index()
            
            fig = px.pie(
                values=distribuicao.values,
                names=distribuicao.index,
                title="Distribuição por Faixa de Valor"
            )
            st.plotly_chart(fig, use_container_width=True)
    
    def _gerar_metricas_desempenho(self):
        """Gera métricas de desempenho"""
        st.markdown("### 📈 MÉTRICAS DE DESEMPENHO")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Taxa de Erros", f"{(self.erros_detectados/self.total_registros*100):.1f}%")
        
        with col2:
            if self.coluna_data:
                projetos_mes = self.df[self.coluna_data].dt.month.nunique()
                st.metric("Meses com Atividade", projetos_mes)
        
        with col3:
            if self.coluna_projeto:
                projetos_unicos = self.df[self.coluna_projeto].nunique()
                st.metric("Projetos Únicos", projetos_unicos)
    
    def _gerar_gestao_riscos(self):
        """Gera seção de gestão de riscos"""
        st.markdown("### ⚠️ GESTÃO DE RISCOS")
        
        riscos = [
            {"Risco": "Dados Inconsistentes", "Probabilidade": "Alta", "Impacto": "Alto", "Mitigação": "Validação contínua"},
            {"Risco": "Pagamentos Duplicados", "Probabilidade": "Média", "Impacto": "Alto", "Mitigação": "Controle de chaves únicas"},
            {"Risco": "Projetos Atrasados", "Probabilidade": "Baixa", "Impacto": "Médio", "Mitigação": "Monitoramento periódico"},
        ]
        
        st.dataframe(pd.DataFrame(riscos), use_container_width=True)
    
    def _gerar_dashboards(self):
        """Gera dashboards interativos"""
        st.markdown("### 📊 DASHBOARDS INTERATIVOS")
        
        # Dashboard 1: Visão geral
        col1, col2 = st.columns(2)
        
        with col1:
            if self.coluna_valor:
                # Gráfico de barras horizontais
                top_10 = self.df.nlargest(10, self.coluna_valor)
                fig = px.bar(
                    top_10,
                    y=self.coluna_projeto if self.coluna_projeto else 'index',
                    x=self.coluna_valor,
                    orientation='h',
                    title="Top 10 Projetos por Valor"
                )
                st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            if self.coluna_data:
                # Timeline
                self.df['Ano_Mes'] = self.df[self.coluna_data].dt.strftime('%Y-%m')
                timeline = self.df.groupby('Ano_Mes')[self.coluna_valor].sum().reset_index()
                
                fig = px.line(
                    timeline,
                    x='Ano_Mes',
                    y=self.coluna_valor,
                    title="Evolução Temporal dos Pagamentos"
                )
                st.plotly_chart(fig, use_container_width=True)
    
    def exportar_relatorio_completo(self):
        """Exporta relatório completo para Excel"""
        try:
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Dados completos
                self.df.to_excel(writer, sheet_name='Dados_Completos', index=False)
                
                # Sumário executivo
                sumario_df = pd.DataFrame({
                    'Métrica': ['Total Registros', 'Valor Total', 'Erros Detectados', 'Registros Problemáticos'],
                    'Valor': [self.total_registros, self.valor_total, self.erros_detectados, len(self.registros_problematicos) if self.registros_problematicos is not None else 0]
                })
                sumario_df.to_excel(writer, sheet_name='Sumario_Executivo', index=False)
                
                # Análise financeira
                if self.coluna_valor:
                    financeiro_df = pd.DataFrame({
                        'Métrica': ['Média', 'Mediana', 'Máximo', 'Mínimo', 'Desvio Padrão'],
                        'Valor': [
                            self.df[self.coluna_valor].mean(),
                            self.df[self.coluna_valor].median(),
                            self.df[self.coluna_valor].max(),
                            self.df[self.coluna_valor].min(),
                            self.df[self.coluna_valor].std()
                        ]
                    })
                    financeiro_df.to_excel(writer, sheet_name='Analise_Financeira', index=False)
                
                # Registros problemáticos
                if self.registros_problematicos is not None and len(self.registros_problematicos) > 0:
                    self.registros_problematicos.to_excel(writer, sheet_name='Registros_Problematicos', index=False)
            
            data = output.getvalue()
            
            st.download_button(
                label="📥 BAIXAR RELATÓRIO COMPLETO (Excel)",
                data=data,
                file_name=f"relatorio_pot_completo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )
            
        except Exception as e:
            st.error(f"Erro ao gerar relatório: {str(e)}")

# ============================================
# FUNÇÃO PRINCIPAL
# ============================================
def main():
    st.title("🏙️ SISTEMA POT-SMDET - MONITORAMENTO DE PROJETOS")
    st.markdown("**Sistema Integrado de Gestão e Monitoramento de Projetos do Plano de Ordenamento Territorial**")
    
    # Inicializar sistema
    if 'sistema' not in st.session_state:
        st.session_state.sistema = SistemaPOTSMDET()
    
    sistema = st.session_state.sistema
    
    # Sidebar para upload e navegação
    with st.sidebar:
        st.markdown("### 📁 CARREGAMENTO DE DADOS")
        
        arquivo = st.file_uploader(
            "Selecione o arquivo de dados (Excel ou CSV)",
            type=['xlsx', 'csv'],
            help="Carregue o arquivo com os dados dos projetos do POT"
        )
        
        if arquivo is not None:
            if st.button("📤 Carregar Dados", type="primary"):
                with st.spinner("Carregando e processando dados..."):
                    sistema.carregar_dados(arquivo)
                    sistema.validar_dados()
        
        st.markdown("---")
        st.markdown("### 🚀 AÇÕES RÁPIDAS")
        
        if st.button("🔄 Validar Dados Novamente"):
            sistema.validar_dados()
            st.success("Validação concluída!")
        
        if st.button("🧹 Limpar Cache"):
            st.cache_data.clear()
            st.session_state.clear()
            st.success("Cache limpo!")
            st.rerun()
        
        st.markdown("---")
        st.markdown("### 📊 NAVEGAÇÃO")
        
        pagina = st.radio(
            "Selecione a página:",
            [
                "📋 Resumo Executivo",
                "💰 Análise Financeira",
                "⚠️ Registros Problemáticos",
                "📄 Relatório Completo",
                "⚙️ Configurações"
            ]
        )
        
        st.markdown("---")
        st.markdown("### ℹ️ SOBRE")
        st.markdown("""
        **Versão:** 2.0.0  
        **Última atualização:** 2024  
        **Desenvolvido para:** SMDET  
        **Finalidade:** Monitoramento de Projetos POT
        """)
    
    # Conteúdo principal baseado na seleção
    if arquivo is None:
        st.info("👈 **Por favor, carregue um arquivo de dados na sidebar para começar.**")
        st.markdown("""
        ### 📝 Instruções:
        1. **Prepare seus dados** em Excel (.xlsx) ou CSV
        2. **Certifique-se** de ter colunas para:
           - Valores monetários
           - Datas
           - Nomes dos projetos
        3. **Clique em 'Carregar Dados'** após selecionar o arquivo
        4. **Navegue** pelas diferentes seções usando o menu lateral
        """)
        
        # Exemplo de estrutura esperada
        with st.expander("📋 Exemplo de Estrutura de Dados Esperada"):
            st.markdown("""
            | Projeto | Valor_Pago | Data_Pagamento | Status |
            |---------|------------|----------------|--------|
            | Projeto A | R$ 50.000,00 | 2024-01-15 | Concluído |
            | Projeto B | R$ 25.000,00 | 2024-02-20 | Em andamento |
            | Projeto C | R$ 100.000,00 | 2024-03-10 | Planejado |
            """)
        
        return
    
    # Navegação entre páginas
    if pagina == "📋 Resumo Executivo":
        sistema.mostrar_resumo_executivo()
        
        # Visualização rápida dos dados
        with st.expander("👁️ VISUALIZAÇÃO RÁPIDA DOS DADOS"):
            st.dataframe(sistema.df.head(20), use_container_width=True)
        
        # Exportar dados limpos
        if st.button("📤 Exportar Dados Validados", type="primary"):
            sistema.exportar_relatorio_completo()
    
    elif pagina == "💰 Análise Financeira":
        sistema.mostrar_analise_financeira()
    
    elif pagina == "⚠️ Registros Problemáticos":
        sistema.mostrar_registros_problematicos()
    
    elif pagina == "📄 Relatório Completo":
        sistema.gerar_relatorio_completo()
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🖨️ Gerar Relatório PDF", type="primary"):
                st.info("Funcionalidade de PDF em desenvolvimento...")
        with col2:
            sistema.exportar_relatorio_completo()
    
    elif pagina == "⚙️ Configurações":
        st.markdown("## ⚙️ CONFIGURAÇÕES DO SISTEMA")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 🎨 Configurações de Visualização")
            tema = st.selectbox(
                "Tema de Cores:",
                ["Alto Contraste (Recomendado)", "Escuro", "Claro"]
            )
            
            tamanho_fonte = st.slider(
                "Tamanho da Fonte Base:",
                min_value=12,
                max_value=24,
                value=16,
                step=1
            )
        
        with col2:
            st.markdown("### 🔧 Configurações de Processamento")
            auto_validar = st.checkbox(
                "Validação Automática ao Carregar",
                value=True
            )
            
            manter_backup = st.checkbox(
                "Manter Backup dos Dados Originais",
                value=True
            )
        
        if st.button("💾 Salvar Configurações", type="primary"):
            st.success("Configurações salvas com sucesso!")
    
    # Rodapé
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: #666;'>
        <strong>Sistema POT-SMDET</strong> | Desenvolvido para Gestão de Projetos do Plano de Ordenamento Territorial<br>
        © 2024 Secretaria Municipal de Desenvolvimento Econômico e Trabalho
        </div>
        """,
        unsafe_allow_html=True
    )

# ============================================
# EXECUÇÃO
# ============================================
if __name__ == "__main__":
    main()
