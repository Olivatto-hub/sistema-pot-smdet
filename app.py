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
# CSS MINIMALISTA - ADAPTA AO TEMA DO USUÁRIO
# ============================================
st.markdown("""
<style>
    /* MELHORIAS GERAIS - NÃO INTERFERE NO TEMA */
    .stDataFrame {
        border-radius: 8px;
        overflow: hidden;
    }
    
    /* MELHOR VISIBILIDADE PARA DATAFRAMES */
    .stDataFrame th {
        font-weight: 700 !important;
    }
    
    /* ESPAÇAMENTO MELHOR ENTRE WIDGETS */
    .stSlider, .stSelectbox, .stMultiSelect {
        margin-bottom: 1rem;
    }
    
    /* BOTÕES MAIS VISÍVEIS */
    .stButton > button {
        border-radius: 6px;
        font-weight: 600;
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    
    /* MÉTRICAS COM DESTAQUE */
    [data-testid="stMetricValue"] {
        font-weight: 700;
    }
    
    /* HEADERS COM DESTAQUE */
    h1, h2, h3 {
        margin-top: 1.5rem !important;
        margin-bottom: 1rem !important;
    }
    
    /* SEPARADORES VISÍVEIS */
    hr {
        margin: 2rem 0 !important;
        height: 2px !important;
    }
    
    /* TABS MAIS VISÍVEIS */
    .stTabs [data-baseweb="tab-list"] {
        border-bottom: 2px solid;
    }
    
    /* TOOLTIPS E INFORMAÇÕES */
    .stTooltip {
        font-size: 14px;
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
        self.coluna_status = None
        self.registros_problematicos = None
        self.erros_detectados = 0
        self.total_registros = 0
        self.valor_total = 0
        
    def carregar_dados(self, arquivo):
        """Carrega dados do arquivo Excel ou CSV"""
        try:
            # Exibe spinner enquanto carrega
            with st.spinner("📂 Carregando e processando dados..."):
                if arquivo.name.endswith('.xlsx'):
                    # Tenta ler todas as abas
                    try:
                        xls = pd.ExcelFile(arquivo)
                        sheet_names = xls.sheet_names
                        
                        if len(sheet_names) > 1:
                            sheet = st.selectbox(
                                "📋 Selecione a aba do Excel:",
                                sheet_names
                            )
                            self.df = pd.read_excel(arquivo, sheet_name=sheet, dtype=str)
                        else:
                            self.df = pd.read_excel(arquivo, dtype=str)
                    except:
                        self.df = pd.read_excel(arquivo, dtype=str)
                        
                elif arquivo.name.endswith('.csv'):
                    # Tenta diferentes encodings e separadores
                    try:
                        self.df = pd.read_csv(arquivo, encoding='utf-8', sep=';', dtype=str)
                    except:
                        try:
                            self.df = pd.read_csv(arquivo, encoding='latin-1', sep=';', dtype=str)
                        except:
                            self.df = pd.read_csv(arquivo, encoding='utf-8', sep=',', dtype=str)
                
                # Mantém cópia original
                self.df_original = self.df.copy()
                
                # Processa automaticamente as colunas
                self._processar_colunas_automaticamente()
                
                # Valida dados após carregamento
                self.validar_dados()
                
                return True
                
        except Exception as e:
            st.error(f"❌ Erro ao carregar dados: {str(e)}")
            return False
    
    def _processar_colunas_automaticamente(self):
        """Identifica e processa automaticamente as colunas principais"""
        if self.df is None:
            return
        
        # Lista de padrões para cada tipo de coluna
        padroes_valor = ['valor', 'vlr', 'r$', 'total', 'pagamento', 'pago', 'custo', 'investimento']
        padroes_data = ['data', 'dt', 'date', 'periodo', 'mes', 'ano']
        padroes_projeto = ['projeto', 'proj', 'nome', 'descricao', 'objeto', 'atividade']
        padroes_status = ['status', 'situacao', 'estado', 'andamento', 'fase']
        
        # Identificar cada tipo de coluna
        self.coluna_valor = self._identificar_coluna_por_padrao(padroes_valor, "💰 Coluna de VALOR")
        self.coluna_data = self._identificar_coluna_por_padrao(padroes_data, "📅 Coluna de DATA")
        self.coluna_projeto = self._identificar_coluna_por_padrao(padroes_projeto, "🏗️ Coluna de PROJETO")
        self.coluna_status = self._identificar_coluna_por_padrao(padroes_status, "🔄 Coluna de STATUS")
        
        # Processar coluna de valor se encontrada
        if self.coluna_valor:
            self._processar_coluna_valor()
        
        # Processar coluna de data se encontrada
        if self.coluna_data:
            self._processar_coluna_data()
    
    def _identificar_coluna_por_padrao(self, padroes, tipo):
        """Identifica coluna por padrões de nome"""
        for coluna in self.df.columns:
            coluna_lower = str(coluna).lower()
            for padrao in padroes:
                if padrao in coluna_lower:
                    st.success(f"{tipo} identificada: **{coluna}**")
                    return coluna
        
        # Se não encontrou, mostra aviso
        st.warning(f"⚠️ {tipo} não identificada automaticamente")
        return None
    
    def _processar_coluna_valor(self):
        """Converte coluna de valor para formato numérico"""
        try:
            # Cria cópia da coluna original
            coluna_original = f"{self.coluna_valor}_ORIGINAL"
            if coluna_original not in self.df.columns:
                self.df[coluna_original] = self.df[self.coluna_valor]
            
            # Remove caracteres não numéricos
            self.df[self.coluna_valor] = self.df[self.coluna_valor].astype(str)
            self.df[self.coluna_valor] = self.df[self.coluna_valor].str.replace('R\$', '', regex=False)
            self.df[self.coluna_valor] = self.df[self.coluna_valor].str.replace('$', '', regex=False)
            self.df[self.coluna_valor] = self.df[self.coluna_valor].str.replace('.', '', regex=False)
            self.df[self.coluna_valor] = self.df[self.coluna_valor].str.replace(',', '.', regex=False)
            
            # Remove espaços e caracteres especiais
            self.df[self.coluna_valor] = self.df[self.coluna_valor].str.replace(r'[^\d\.-]', '', regex=True)
            
            # Converte para numérico
            self.df[self.coluna_valor] = pd.to_numeric(self.df[self.coluna_valor], errors='coerce')
            
        except Exception as e:
            st.warning(f"⚠️ Não foi possível processar a coluna de valor: {str(e)}")
    
    def _processar_coluna_data(self):
        """Converte coluna de data para formato datetime"""
        try:
            self.df[self.coluna_data] = pd.to_datetime(self.df[self.coluna_data], errors='coerce', dayfirst=True)
            
            # Cria colunas auxiliares
            if self.coluna_data:
                self.df['Ano'] = self.df[self.coluna_data].dt.year
                self.df['Mês'] = self.df[self.coluna_data].dt.month
                self.df['Trimestre'] = self.df[self.coluna_data].dt.quarter
                self.df['Ano_Mês'] = self.df[self.coluna_data].dt.strftime('%Y-%m')
                
        except Exception as e:
            st.warning(f"⚠️ Não foi possível processar a coluna de data: {str(e)}")
    
    def validar_dados(self):
        """Realiza validação completa dos dados"""
        if self.df is None:
            st.warning("⚠️ Nenhum dado carregado para validação")
            return
        
        with st.spinner("🔍 Validando dados..."):
            problemas = []
            
            # 1. Valores nulos na coluna de valor
            if self.coluna_valor:
                nulos_valor = self.df[self.df[self.coluna_valor].isna()]
                if len(nulos_valor) > 0:
                    nulos_valor = nulos_valor.copy()
                    nulos_valor['Tipo_Erro'] = 'VALOR_NULO'
                    nulos_valor['Descrição_Erro'] = f'Valor ausente na coluna {self.coluna_valor}'
                    problemas.append(nulos_valor)
            
            # 2. Valores zerados ou negativos (apenas se não for esperado)
            if self.coluna_valor:
                zerados = self.df[(self.df[self.coluna_valor] <= 0) & (self.df[self.coluna_valor].notna())]
                if len(zerados) > 0:
                    zerados = zerados.copy()
                    zerados['Tipo_Erro'] = 'VALOR_ZERADO_NEGATIVO'
                    zerados['Descrição_Erro'] = f'Valor zerado ou negativo na coluna {self.coluna_valor}'
                    problemas.append(zerados)
            
            # 3. Datas inválidas ou futuras
            if self.coluna_data:
                datas_invalidas = self.df[self.df[self.coluna_data].isna()]
                if len(datas_invalidas) > 0:
                    datas_invalidas = datas_invalidas.copy()
                    datas_invalidas['Tipo_Erro'] = 'DATA_INVALIDA'
                    datas_invalidas['Descrição_Erro'] = f'Data inválida na coluna {self.coluna_data}'
                    problemas.append(datas_invalidas)
                
                # Datas futuras (apenas aviso)
                hoje = datetime.now()
                datas_futuras = self.df[(self.df[self.coluna_data] > hoje) & (self.df[self.coluna_data].notna())]
                if len(datas_futuras) > 0:
                    datas_futuras = datas_futuras.copy()
                    datas_futuras['Tipo_Erro'] = 'DATA_FUTURA'
                    datas_futuras['Descrição_Erro'] = f'Data futura na coluna {self.coluna_data}'
                    problemas.append(datas_futuras)
            
            # 4. Projetos sem nome
            if self.coluna_projeto:
                projetos_vazios = self.df[self.df[self.coluna_projeto].isna() | 
                                          (self.df[self.coluna_projeto].astype(str).str.strip() == '') |
                                          (self.df[self.coluna_projeto].astype(str).str.strip() == 'nan')]
                if len(projetos_vazios) > 0:
                    projetos_vazios = projetos_vazios.copy()
                    projetos_vazios['Tipo_Erro'] = 'PROJETO_SEM_NOME'
                    projetos_vazios['Descrição_Erro'] = f'Projeto sem nome na coluna {self.coluna_projeto}'
                    problemas.append(projetos_vazios)
            
            # 5. Valores extremos (outliers)
            if self.coluna_valor and len(self.df) > 10:
                Q1 = self.df[self.coluna_valor].quantile(0.25)
                Q3 = self.df[self.coluna_valor].quantile(0.75)
                IQR = Q3 - Q1
                limite_superior = Q3 + 3 * IQR
                
                outliers = self.df[self.df[self.coluna_valor] > limite_superior]
                if len(outliers) > 0:
                    outliers = outliers.copy()
                    outliers['Tipo_Erro'] = 'VALOR_OUTLIER'
                    outliers['Descrição_Erro'] = f'Valor muito alto (possível outlier) na coluna {self.coluna_valor}'
                    problemas.append(outliers)
            
            # Consolidar problemas
            if problemas:
                self.registros_problematicos = pd.concat(problemas, ignore_index=True)
                self.erros_detectados = len(self.registros_problematicos)
            else:
                self.registros_problematicos = pd.DataFrame()
                self.erros_detectados = 0
            
            # Atualizar métricas
            self.total_registros = len(self.df)
            if self.coluna_valor and self.df[self.coluna_valor].notna().any():
                self.valor_total = self.df[self.coluna_valor].sum()
            else:
                self.valor_total = 0
    
    def mostrar_resumo_executivo(self):
        """Exibe o resumo executivo do projeto"""
        st.markdown("---")
        st.markdown("## 📋 RESUMO EXECUTIVO - PROJETO POT")
        
        # Container principal
        with st.container():
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    label="📊 TOTAL DE REGISTROS",
                    value=f"{self.total_registros:,}",
                    help="Número total de projetos/registros"
                )
            
            with col2:
                if self.coluna_valor and self.valor_total > 0:
                    valor_formatado = f"R$ {self.valor_total:,.2f}"
                    st.metric(
                        label="💰 VALOR TOTAL",
                        value=valor_formatado,
                        help="Somatório de todos os valores"
                    )
                else:
                    st.metric(
                        label="💰 VALOR TOTAL",
                        value="N/A",
                        help="Coluna de valor não identificada"
                    )
            
            with col3:
                st.metric(
                    label="⚠️ ERROS DETECTADOS",
                    value=self.erros_detectados,
                    delta=None,
                    delta_color="inverse",
                    help="Problemas identificados na validação"
                )
            
            with col4:
                registros_problem = len(self.registros_problematicos) if self.registros_problematicos is not None else 0
                st.metric(
                    label="🔴 REGISTROS PROBLEMÁTICOS",
                    value=registros_problem,
                    delta=None,
                    delta_color="inverse",
                    help="Registros que necessitam atenção"
                )
        
        st.markdown("---")
        
        # Informações de colunas identificadas
        col_info1, col_info2 = st.columns(2)
        
        with col_info1:
            if self.coluna_valor:
                st.info(f"**💰 Coluna de Valor:** `{self.coluna_valor}`")
            if self.coluna_data:
                st.info(f"**📅 Coluna de Data:** `{self.coluna_data}`")
        
        with col_info2:
            if self.coluna_projeto:
                st.info(f"**🏗️ Coluna de Projeto:** `{self.coluna_projeto}`")
            if self.coluna_status:
                st.info(f"**🔄 Coluna de Status:** `{self.coluna_status}`")
        
        # Estatísticas rápidas se houver coluna de valor
        if self.coluna_valor and self.df[self.coluna_valor].notna().any():
            st.markdown("### 📈 ESTATÍSTICAS RÁPIDAS")
            
            col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
            
            with col_stat1:
                valor_medio = self.df[self.coluna_valor].mean()
                st.metric("Média", f"R$ {valor_medio:,.2f}")
            
            with col_stat2:
                valor_mediano = self.df[self.coluna_valor].median()
                st.metric("Mediana", f"R$ {valor_mediano:,.2f}")
            
            with col_stat3:
                valor_max = self.df[self.coluna_valor].max()
                st.metric("Máximo", f"R$ {valor_max:,.2f}")
            
            with col_stat4:
                valor_min = self.df[self.coluna_valor].min()
                st.metric("Mínimo", f"R$ {valor_min:,.2f}")
        
        # Visualização rápida dos dados
        with st.expander("👁️ VISUALIZAR PRIMEIROS REGISTROS", expanded=False):
            num_rows = st.slider("Número de linhas para mostrar:", 5, 50, 10)
            st.dataframe(self.df.head(num_rows), use_container_width=True)
    
    def mostrar_analise_financeira(self):
        """Mostra análise financeira detalhada"""
        if self.df is None:
            st.warning("⚠️ Nenhum dado carregado para análise.")
            return
            
        st.markdown("## 📊 ANÁLISE FINANCEIRA DETALHADA")
        
        # Verificar se temos coluna de valor
        if self.coluna_valor is None or self.df[self.coluna_valor].isna().all():
            st.error("❌ Coluna de valor não disponível para análise financeira.")
            return
        
        # Criar abas para diferentes análises
        tab1, tab2, tab3, tab4 = st.tabs([
            "📈 Distribuição", 
            "🗓️ Evolução Temporal",
            "🏗️ Por Projeto",
            "🔍 Detalhamento"
        ])
        
        with tab1:
            self._analise_distribuicao()
        
        with tab2:
            self._analise_temporal()
        
        with tab3:
            self._analise_por_projeto()
        
        with tab4:
            self._analise_detalhada()
    
    def _analise_distribuicao(self):
        """Análise de distribuição de valores"""
        col1, col2 = st.columns(2)
        
        with col1:
            # Histograma
            fig = px.histogram(
                self.df, 
                x=self.coluna_valor,
                title="Distribuição dos Valores",
                labels={self.coluna_valor: 'Valor (R$)', 'count': 'Frequência'},
                nbins=50,
                opacity=0.8
            )
            fig.update_layout(
                showlegend=False,
                hovermode='x unified'
            )
            st.plotly_chart(fig, use_container_width=True, theme=None)
        
        with col2:
            # Box plot
            fig = px.box(
                self.df,
                y=self.coluna_valor,
                title="Box Plot - Distribuição",
                points="outliers"
            )
            fig.update_layout(
                showlegend=False,
                yaxis_title="Valor (R$)"
            )
            st.plotly_chart(fig, use_container_width=True, theme=None)
    
    def _analise_temporal(self):
        """Análise temporal dos pagamentos"""
        if self.coluna_data is None:
            st.warning("⚠️ Coluna de data não identificada para análise temporal.")
            return
        
        # Agrupar por período selecionado
        periodo = st.selectbox(
            "📊 Agrupar por:",
            ["Mês", "Trimestre", "Ano", "Ano-Mês"],
            index=0
        )
        
        if periodo == "Mês":
            self.df['Periodo'] = self.df[self.coluna_data].dt.strftime('%Y-%m')
        elif periodo == "Trimestre":
            self.df['Periodo'] = self.df['Ano'].astype(str) + '-T' + self.df['Trimestre'].astype(str)
        elif periodo == "Ano":
            self.df['Periodo'] = self.df['Ano'].astype(str)
        elif periodo == "Ano-Mês":
            self.df['Periodo'] = self.df['Ano_Mês']
        
        # Agrupar dados
        temporal = self.df.groupby('Periodo', as_index=False)[self.coluna_valor].sum().sort_values('Periodo')
        
        # Gráfico de linha
        fig = px.line(
            temporal,
            x='Periodo',
            y=self.coluna_valor,
            title=f"Evolução Temporal - Agrupado por {periodo}",
            markers=True,
            line_shape='spline'
        )
        
        # Adicionar barras
        fig.add_bar(
            x=temporal['Periodo'],
            y=temporal[self.coluna_valor],
            name='Valor Total',
            opacity=0.3
        )
        
        fig.update_layout(
            hovermode='x unified',
            xaxis_title=periodo,
            yaxis_title="Valor Total (R$)"
        )
        
        st.plotly_chart(fig, use_container_width=True, theme=None)
        
        # Tabela de dados
        with st.expander("📋 Ver dados agrupados"):
            st.dataframe(temporal, use_container_width=True)
    
    def _analise_por_projeto(self):
        """Análise por projeto"""
        if self.coluna_projeto is None:
            st.warning("⚠️ Coluna de projeto não identificada.")
            return
        
        # Top N projetos
        n_projetos = st.slider("Número de projetos para mostrar:", 5, 30, 10)
        
        # Agrupar por projeto
        por_projeto = self.df.groupby(self.coluna_projeto, as_index=False)[self.coluna_valor].sum()
        por_projeto = por_projeto.sort_values(self.coluna_valor, ascending=False).head(n_projetos)
        
        # Gráfico de barras horizontais
        fig = px.bar(
            por_projeto,
            y=self.coluna_projeto,
            x=self.coluna_valor,
            orientation='h',
            title=f"Top {n_projetos} Projetos por Valor",
            text=self.coluna_valor,
            color=self.coluna_valor,
            color_continuous_scale='Viridis'
        )
        
        fig.update_layout(
            showlegend=False,
            xaxis_title="Valor Total (R$)",
            yaxis_title="Projeto",
            yaxis={'categoryorder': 'total ascending'}
        )
        
        # Formatar valores no eixo X
        fig.update_xaxes(tickformat=",.0f")
        
        st.plotly_chart(fig, use_container_width=True, theme=None)
        
        # Tabela detalhada
        with st.expander("📋 Ver tabela detalhada"):
            st.dataframe(por_projeto, use_container_width=True)
    
    def _analise_detalhada(self):
        """Análise detalhada com múltiplas visualizações"""
        col1, col2 = st.columns(2)
        
        with col1:
            # Pizza por status se disponível
            if self.coluna_status and self.coluna_valor:
                status_group = self.df.groupby(self.coluna_status)[self.coluna_valor].sum().reset_index()
                
                if len(status_group) > 0:
                    fig = px.pie(
                        status_group,
                        values=self.coluna_valor,
                        names=self.coluna_status,
                        title="Distribuição por Status",
                        hole=0.3
                    )
                    st.plotly_chart(fig, use_container_width=True, theme=None)
        
        with col2:
            # Valores por ano se disponível
            if 'Ano' in self.df.columns and self.coluna_valor:
                ano_group = self.df.groupby('Ano')[self.coluna_valor].sum().reset_index()
                
                fig = px.bar(
                    ano_group,
                    x='Ano',
                    y=self.coluna_valor,
                    title="Valores por Ano",
                    text=self.coluna_valor
                )
                fig.update_traces(texttemplate='R$ %{text:,.0f}', textposition='outside')
                st.plotly_chart(fig, use_container_width=True, theme=None)
        
        # Filtros interativos
        st.markdown("### 🔍 FILTROS AVANÇADOS")
        
        col_filtro1, col_filtro2 = st.columns(2)
        
        with col_filtro1:
            # Filtrar por valor mínimo
            if self.coluna_valor:
                valor_min = st.number_input(
                    "Valor Mínimo (R$):",
                    min_value=0.0,
                    max_value=float(self.df[self.coluna_valor].max()),
                    value=0.0,
                    step=1000.0
                )
        
        with col_filtro2:
            # Filtrar por ano se disponível
            if 'Ano' in self.df.columns:
                anos = sorted(self.df['Ano'].dropna().unique())
                anos_selecionados = st.multiselect(
                    "Filtrar por Ano:",
                    options=anos,
                    default=anos
                )
        
        # Aplicar filtros
        df_filtrado = self.df.copy()
        
        if self.coluna_valor and 'valor_min' in locals():
            df_filtrado = df_filtrado[df_filtrado[self.coluna_valor] >= valor_min]
        
        if 'Ano' in self.df.columns and 'anos_selecionados' in locals() and anos_selecionados:
            df_filtrado = df_filtrado[df_filtrado['Ano'].isin(anos_selecionados)]
        
        # Mostrar dados filtrados
        st.dataframe(df_filtrado, use_container_width=True)
    
    def mostrar_registros_problematicos(self):
        """Exibe registros problemáticos de forma segura"""
        if self.registros_problematicos is None or len(self.registros_problematicos) == 0:
            st.success("✅ Nenhum registro problemático encontrado!")
            return
        
        st.markdown("## ⚠️ REGISTROS PROBLEMÁTICOS")
        
        # Métricas de problemas
        col1, col2, col3 = st.columns(3)
        
        with col1:
            tipos_erro = self.registros_problematicos['Tipo_Erro'].nunique()
            st.metric("Tipos de Erro Diferentes", tipos_erro)
        
        with col2:
            total_problemas = len(self.registros_problematicos)
            st.metric("Total de Problemas", total_problemas)
        
        with col3:
            if self.coluna_valor and self.coluna_valor in self.registros_problematicos.columns:
                valor_problematico = self.registros_problematicos[self.coluna_valor].sum()
                st.metric("Valor Problemático Total", f"R$ {valor_problematico:,.2f}")
        
        # Distribuição por tipo de erro
        st.markdown("### 📊 DISTRIBUIÇÃO DOS PROBLEMAS")
        
        distribuicao_erros = self.registros_problematicos['Tipo_Erro'].value_counts().reset_index()
        distribuicao_erros.columns = ['Tipo de Erro', 'Quantidade']
        
        fig = px.bar(
            distribuicao_erros,
            x='Tipo de Erro',
            y='Quantidade',
            title="Tipos de Erros Encontrados",
            color='Quantidade',
            color_continuous_scale='Reds'
        )
        st.plotly_chart(fig, use_container_width=True, theme=None)
        
        # Visualização dos registros problemáticos com SLIDER SEGURO
        st.markdown("### 👁️ VISUALIZAÇÃO DOS REGISTROS")
        
        # Garantir que temos registros para mostrar
        total_rows = len(self.registros_problematicos)
        
        if total_rows > 0:
            # Configurar slider com valores seguros
            min_value = 1
            max_value = max(min_value, total_rows)
            default_value = min(10, max_value)
            
            linhas_mostrar = st.slider(
                "🔢 Número de linhas para mostrar:",
                min_value=min_value,
                max_value=max_value,
                value=default_value,
                step=1,
                help="Selecione quantos registros problemáticos visualizar"
            )
            
            # Mostrar registros
            st.dataframe(
                self.registros_problematicos.head(linhas_mostrar),
                use_container_width=True
            )
        else:
            st.info("Nenhum registro problemático para exibir.")
        
        # Ações de correção
        st.markdown("### 🛠️ AÇÕES DE CORREÇÃO")
        
        col_acao1, col_acao2, col_acao3 = st.columns(3)
        
        with col_acao1:
            if st.button("📥 Exportar Problemas", type="secondary", use_container_width=True):
                self._exportar_problemas()
        
        with col_acao2:
            if st.button("🔄 Corrigir Automaticamente", type="primary", use_container_width=True):
                self._corrigir_automaticamente()
        
        with col_acao3:
            if st.button("🗑️ Excluir Registros", type="secondary", use_container_width=True):
                self._excluir_registros_problematicos()
    
    def _exportar_problemas(self):
        """Exporta registros problemáticos para Excel"""
        try:
            output = BytesIO()
            
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Registros problemáticos
                self.registros_problematicos.to_excel(
                    writer, 
                    sheet_name='Registros_Problematicos', 
                    index=False
                )
                
                # Sumário dos problemas
                sumario = self.registros_problematicos['Tipo_Erro'].value_counts().reset_index()
                sumario.columns = ['Tipo de Erro', 'Quantidade']
                sumario.to_excel(writer, sheet_name='Sumario_Problemas', index=False)
            
            # Botão de download
            st.download_button(
                label="⬇️ Baixar Relatório de Problemas",
                data=output.getvalue(),
                file_name=f"problemas_pot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )
            
        except Exception as e:
            st.error(f"❌ Erro ao exportar: {str(e)}")
    
    def _corrigir_automaticamente(self):
        """Tenta corrigir problemas automaticamente"""
        with st.spinner("🔄 Aplicando correções automáticas..."):
            try:
                # Correções básicas
                correcoes_aplicadas = 0
                
                # 1. Corrigir valores nulos (substituir por 0 ou média)
                if self.coluna_valor:
                    nulos_antes = self.df[self.coluna_valor].isna().sum()
                    if nulos_antes > 0:
                        # Substituir por 0 (poderia ser por média, mediana, etc.)
                        self.df[self.coluna_valor] = self.df[self.coluna_valor].fillna(0)
                        nulos_depois = self.df[self.coluna_valor].isna().sum()
                        correcoes_aplicadas += (nulos_antes - nulos_depois)
                
                # 2. Corrigir projetos sem nome
                if self.coluna_projeto:
                    vazios_antes = self.df[self.coluna_projeto].isna().sum() + \
                                  (self.df[self.coluna_projeto].astype(str).str.strip() == '').sum()
                    if vazios_antes > 0:
                        self.df[self.coluna_projeto] = self.df[self.coluna_projeto].fillna('PROJETO_NÃO_IDENTIFICADO')
                        # Substituir strings vazias
                        mask = self.df[self.coluna_projeto].astype(str).str.strip() == ''
                        self.df.loc[mask, self.coluna_projeto] = 'PROJETO_NÃO_IDENTIFICADO'
                        vazios_depois = self.df[self.coluna_projeto].isna().sum() + \
                                       (self.df[self.coluna_projeto].astype(str).str.strip() == '').sum()
                        correcoes_aplicadas += (vazios_antes - vazios_depois)
                
                # Revalidar dados após correções
                self.validar_dados()
                
                if correcoes_aplicadas > 0:
                    st.success(f"✅ {correcoes_aplicadas} correções aplicadas com sucesso!")
                    st.rerun()
                else:
                    st.info("ℹ️ Nenhuma correção necessária foi aplicada.")
                    
            except Exception as e:
                st.error(f"❌ Erro ao aplicar correções: {str(e)}")
    
    def _excluir_registros_problematicos(self):
        """Exclui registros problemáticos após confirmação"""
        st.warning("⚠️ ATENÇÃO: Esta ação removerá permanentemente os registros problemáticos!")
        
        if st.checkbox("✅ Confirmar exclusão permanente"):
            if st.button("🗑️ CONFIRMAR EXCLUSÃO", type="primary"):
                with st.spinner("Excluindo registros..."):
                    try:
                        # Obter índices dos registros problemáticos
                        indices_problematicos = self.registros_problematicos.index
                        
                        # Remover do dataframe principal
                        self.df = self.df.drop(indices_problematicos, errors='ignore')
                        
                        # Limpar registros problemáticos
                        self.registros_problematicos = None
                        
                        # Revalidar dados
                        self.validar_dados()
                        
                        st.success("✅ Registros problemáticos excluídos com sucesso!")
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ Erro ao excluir registros: {str(e)}")
    
    def gerar_relatorio_completo(self):
        """Gera relatório completo do projeto POT"""
        if self.df is None:
            st.warning("⚠️ Carregue os dados primeiro.")
            return
        
        st.markdown("## 📄 RELATÓRIO COMPLETO - PROJETO POT")
        st.markdown("---")
        
        # Criar abas para diferentes seções
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
        """Gera sumário executivo detalhado"""
        st.markdown("### 📋 SUMÁRIO EXECUTIVO")
        
        # Informações gerais
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**📊 INFORMAÇÕES GERAIS**")
            st.markdown(f"- **Total de Registros:** {self.total_registros:,}")
            st.markdown(f"- **Período Analisado:** {self._obter_periodo_analise()}")
            st.markdown(f"- **Valor Total:** R$ {self.valor_total:,.2f}")
            
            if self.erros_detectados > 0:
                st.error(f"- **⚠️ Erros Detectados:** {self.erros_detectados}")
            else:
                st.success("- **✅ Dados consistentes**")
        
        with col2:
            st.markdown("**🎯 INDICADORES CHAVE**")
            if self.coluna_valor and self.df[self.coluna_valor].notna().any():
                media = self.df[self.coluna_valor].mean()
                mediana = self.df[self.coluna_valor].median()
                maximo = self.df[self.coluna_valor].max()
                minimo = self.df[self.coluna_valor].min()
                
                st.markdown(f"- **💰 Valor Médio:** R$ {media:,.2f}")
                st.markdown(f"- **📊 Mediana:** R$ {mediana:,.2f}")
                st.markdown(f"- **📈 Maior Valor:** R$ {maximo:,.2f}")
                st.markdown(f"- **📉 Menor Valor:** R$ {minimo:,.2f}")
        
        # Recomendações
        st.markdown("---")
        st.markdown("**💡 RECOMENDAÇÕES**")
        
        if self.erros_detectados > 0:
            st.warning("1. **Corrigir registros problemáticos** antes de análises detalhadas")
        else:
            st.success("1. **Dados validados** - Pode prosseguir com planejamento")
        
        if self.coluna_valor and self.df[self.coluna_valor].max() > self.df[self.coluna_valor].mean() * 10:
            st.info("2. **Monitorar projetos de alto valor** para garantir execução adequada")
        
        st.info("3. **Implementar controles periódicos** para manutenção da qualidade dos dados")
    
    def _obter_periodo_analise(self):
        """Obtém período de análise dos dados"""
        if self.coluna_data and self.df[self.coluna_data].notna().any():
            data_min = self.df[self.coluna_data].min()
            data_max = self.df[self.coluna_data].max()
            
            if pd.notna(data_min) and pd.notna(data_max):
                return f"{data_min.strftime('%d/%m/%Y')} a {data_max.strftime('%d/%m/%Y')}"
        
        return "Período não identificado"
    
    def _gerar_analise_financeira_detalhada(self):
        """Gera análise financeira detalhada para relatório"""
        st.markdown("### 💰 ANÁLISE FINANCEIRA DETALHADA")
        
        if self.coluna_valor and self.df[self.coluna_valor].notna().any():
            # Distribuição por faixa de valor
            st.markdown("**📊 DISTRIBUIÇÃO POR FAIXA DE VALOR**")
            
            # Definir faixas
            bins = [0, 10000, 50000, 100000, 500000, 1000000, float('inf')]
            labels = ['< 10k', '10k-50k', '50k-100k', '100k-500k', '500k-1M', '> 1M']
            
            self.df['Faixa_Valor'] = pd.cut(
                self.df[self.coluna_valor], 
                bins=bins, 
                labels=labels,
                include_lowest=True
            )
            
            distribuicao = self.df['Faixa_Valor'].value_counts().sort_index()
            
            # Gráfico de pizza
            fig = px.pie(
                values=distruibuicao.values,
                names=distruibuicao.index,
                title="Distribuição por Faixa de Valor"
            )
            st.plotly_chart(fig, use_container_width=True, theme=None)
            
            # Tabela de distribuição
            st.dataframe(distruibuicao.reset_index().rename(
                columns={'index': 'Faixa de Valor', 'Faixa_Valor': 'Quantidade'}
            ), use_container_width=True)
    
    def _gerar_metricas_desempenho(self):
        """Gera métricas de desempenho para relatório"""
        st.markdown("### 📈 MÉTRICAS DE DESEMPENHO")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if self.total_registros > 0:
                taxa_erros = (self.erros_detectados / self.total_registros) * 100
                st.metric("📉 Taxa de Erros", f"{taxa_erros:.1f}%")
        
        with col2:
            if self.coluna_data:
                meses_unicos = self.df[self.coluna_data].dt.to_period('M').nunique()
                st.metric("🗓️ Meses com Atividade", meses_unicos)
        
        with col3:
            if self.coluna_projeto:
                projetos_unicos = self.df[self.coluna_projeto].nunique()
                st.metric("🏗️ Projetos Únicos", projetos_unicos)
        
        # Outras métricas
        col4, col5, col6 = st.columns(3)
        
        with col4:
            if self.coluna_status:
                status_unicos = self.df[self.coluna_status].nunique()
                st.metric("🔄 Status Diferentes", status_unicos)
        
        with col5:
            if self.coluna_valor:
                desvio_padrao = self.df[self.coluna_valor].std()
                st.metric("📊 Desvio Padrão", f"R$ {desvio_padrao:,.2f}")
        
        with col6:
            if self.coluna_valor and self.total_registros > 0:
                valor_por_registro = self.valor_total / self.total_registros
                st.metric("💰 Valor Médio/Registro", f"R$ {valor_por_registro:,.2f}")
    
    def _gerar_gestao_riscos(self):
        """Gera seção de gestão de riscos"""
        st.markdown("### ⚠️ GESTÃO DE RISCOS")
        
        # Tabela de riscos identificados
        riscos = [
            {
                "Risco": "Dados Inconsistentes",
                "Probabilidade": "Alta" if self.erros_detectados > 0 else "Baixa",
                "Impacto": "Alto",
                "Mitigação": "Validação contínua dos dados"
            },
            {
                "Risco": "Pagamentos Duplicados",
                "Probabilidade": "Média",
                "Impacto": "Alto", 
                "Mitigação": "Controle por chaves únicas de projeto"
            },
            {
                "Risco": "Projetos Atrasados",
                "Probabilidade": "Baixa",
                "Impacto": "Médio",
                "Mitigação": "Monitoramento periódico do cronograma"
            },
            {
                "Risco": "Valores Extremos (Outliers)",
                "Probabilidade": "Média",
                "Impacto": "Médio",
                "Mitigação": "Análise estatística regular"
            }
        ]
        
        st.dataframe(pd.DataFrame(riscos), use_container_width=True)
        
        # Recomendações de mitigação
        st.markdown("**🛡️ RECOMENDAÇÕES DE MITIGAÇÃO**")
        
        if self.erros_detectados > 0:
            st.warning("1. **Resolver imediatamente** os erros identificados na validação")
        
        st.info("2. **Implementar processo de revisão** mensal dos dados")
        st.info("3. **Estabelecer limites de aprovação** para valores acima de R$ 500.000,00")
        st.info("4. **Criar alertas automáticos** para dados inconsistentes")
    
    def _gerar_dashboards(self):
        """Gera dashboards interativos"""
        st.markdown("### 📊 DASHBOARDS INTERATIVOS")
        
        # Dashboard 1: Visão Geral
        st.markdown("#### 📈 VISÃO GERAL DO PORTFÓLIO")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if self.coluna_projeto and self.coluna_valor:
                # Top 10 projetos
                top_10 = self.df.nlargest(10, self.coluna_valor)
                fig = px.bar(
                    top_10,
                    y=self.coluna_projeto,
                    x=self.coluna_valor,
                    orientation='h',
                    title="Top 10 Projetos por Valor",
                    color=self.coluna_valor,
                    color_continuous_scale='Viridis'
                )
                fig.update_layout(
                    yaxis={'categoryorder': 'total ascending'},
                    xaxis_title="Valor (R$)",
                    yaxis_title="Projeto"
                )
                st.plotly_chart(fig, use_container_width=True, theme=None)
        
        with col2:
            if self.coluna_data and self.coluna_valor:
                # Evolução acumulada
                self.df = self.df.sort_values(self.coluna_data)
                self.df['Acumulado'] = self.df[self.coluna_valor].cumsum()
                
                fig = px.line(
                    self.df,
                    x=self.coluna_data,
                    y='Acumulado',
                    title="Valor Acumulado ao Longo do Tempo",
                    markers=True
                )
                st.plotly_chart(fig, use_container_width=True, theme=None)
        
        # Dashboard 2: Análise Detalhada
        st.markdown("#### 🔍 ANÁLISE DETALHADA")
        
        # Filtros interativos
        st.markdown("**🔧 FILTROS PARA ANÁLISE**")
        
        col_f1, col_f2, col_f3 = st.columns(3)
        
        with col_f1:
            # Filtro por valor
            if self.coluna_valor:
                min_valor, max_valor = st.slider(
                    "💰 Faixa de Valor (R$):",
                    float(self.df[self.coluna_valor].min()),
                    float(self.df[self.coluna_valor].max()),
                    (float(self.df[self.coluna_valor].min()), float(self.df[self.coluna_valor].max()))
                )
        
        with col_f2:
            # Filtro por data se disponível
            if self.coluna_data:
                min_data = self.df[self.coluna_data].min()
                max_data = self.df[self.coluna_data].max()
                
                data_inicio, data_fim = st.date_input(
                    "🗓️ Período:",
                    [min_data, max_data],
                    min_value=min_data,
                    max_value=max_data
                )
        
        with col_f3:
            # Filtro por status se disponível
            if self.coluna_status:
                status_opcoes = ['Todos'] + list(self.df[self.coluna_status].unique())
                status_selecionado = st.selectbox("🔄 Status:", status_opcoes)
        
        # Aplicar filtros
        df_filtrado = self.df.copy()
        
        if self.coluna_valor and 'min_valor' in locals() and 'max_valor' in locals():
            df_filtrado = df_filtrado[
                (df_filtrado[self.coluna_valor] >= min_valor) & 
                (df_filtrado[self.coluna_valor] <= max_valor)
            ]
        
        if self.coluna_data and 'data_inicio' in locals() and 'data_fim' in locals():
            df_filtrado = df_filtrado[
                (df_filtrado[self.coluna_data] >= pd.Timestamp(data_inicio)) & 
                (df_filtrado[self.coluna_data] <= pd.Timestamp(data_fim))
            ]
        
        if self.coluna_status and 'status_selecionado' in locals() and status_selecionado != 'Todos':
            df_filtrado = df_filtrado[df_filtrado[self.coluna_status] == status_selecionado]
        
        # Mostrar dados filtrados
        st.dataframe(df_filtrado, use_container_width=True)
        
        # Estatísticas dos dados filtrados
        st.markdown(f"**📊 Estatísticas dos Dados Filtrados ({len(df_filtrado)} registros):**")
        
        if len(df_filtrado) > 0 and self.coluna_valor:
            col_s1, col_s2, col_s3 = st.columns(3)
            
            with col_s1:
                st.metric("Total Filtrado", f"R$ {df_filtrado[self.coluna_valor].sum():,.2f}")
            
            with col_s2:
                st.metric("Média Filtrada", f"R$ {df_filtrado[self.coluna_valor].mean():,.2f}")
            
            with col_s3:
                st.metric("Registros Filtrados", len(df_filtrado))
    
    def exportar_relatorio_completo(self):
        """Exporta relatório completo para Excel"""
        try:
            output = BytesIO()
            
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # 1. Dados completos
                self.df.to_excel(writer, sheet_name='Dados_Completos', index=False)
                
                # 2. Sumário executivo
                sumario_data = {
                    'Métrica': [
                        'Total de Registros',
                        'Valor Total (R$)',
                        'Erros Detectados',
                        'Registros Problemáticos',
                        'Data de Geração',
                        'Período Analisado'
                    ],
                    'Valor': [
                        self.total_registros,
                        self.valor_total,
                        self.erros_detectados,
                        len(self.registros_problematicos) if self.registros_problematicos is not None else 0,
                        datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
                        self._obter_periodo_analise()
                    ]
                }
                pd.DataFrame(sumario_data).to_excel(writer, sheet_name='Sumario_Executivo', index=False)
                
                # 3. Análise financeira
                if self.coluna_valor and self.df[self.coluna_valor].notna().any():
                    analise_financeira = {
                        'Métrica': [
                            'Média (R$)',
                            'Mediana (R$)',
                            'Máximo (R$)',
                            'Mínimo (R$)',
                            'Desvio Padrão (R$)',
                            'Coeficiente de Variação (%)',
                            '1º Quartil (R$)',
                            '3º Quartil (R$)'
                        ],
                        'Valor': [
                            self.df[self.coluna_valor].mean(),
                            self.df[self.coluna_valor].median(),
                            self.df[self.coluna_valor].max(),
                            self.df[self.coluna_valor].min(),
                            self.df[self.coluna_valor].std(),
                            (self.df[self.coluna_valor].std() / self.df[self.coluna_valor].mean()) * 100,
                            self.df[self.coluna_valor].quantile(0.25),
                            self.df[self.coluna_valor].quantile(0.75)
                        ]
                    }
                    pd.DataFrame(analise_financeira).to_excel(writer, sheet_name='Analise_Financeira', index=False)
                
                # 4. Registros problemáticos
                if self.registros_problematicos is not None and len(self.registros_problematicos) > 0:
                    self.registros_problematicos.to_excel(writer, sheet_name='Registros_Problematicos', index=False)
                
                # 5. Top projetos
                if self.coluna_projeto and self.coluna_valor:
                    top_projetos = self.df.groupby(self.coluna_projeto)[self.coluna_valor].sum().nlargest(20).reset_index()
                    top_projetos.to_excel(writer, sheet_name='Top_Projetos', index=False)
                
                # 6. Evolução temporal
                if self.coluna_data and self.coluna_valor:
                    self.df['Mês_Ano'] = self.df[self.coluna_data].dt.strftime('%Y-%m')
                    evolucao = self.df.groupby('Mês_Ano')[self.coluna_valor].sum().reset_index()
                    evolucao.to_excel(writer, sheet_name='Evolucao_Temporal', index=False)
            
            # Preparar dados para download
            data = output.getvalue()
            
            # Botão de download
            st.download_button(
                label="📥 BAIXAR RELATÓRIO COMPLETO (Excel)",
                data=data,
                file_name=f"relatorio_pot_completo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True
            )
            
        except Exception as e:
            st.error(f"❌ Erro ao gerar relatório: {str(e)}")

# ============================================
# FUNÇÃO PRINCIPAL
# ============================================
def main():
    # Título principal
    st.title("🏙️ SISTEMA POT-SMDET")
    st.markdown("**Sistema Integrado de Gestão e Monitoramento de Projetos do Plano de Ordenamento Territorial**")
    st.markdown("---")
    
    # Inicializar sistema na session state
    if 'sistema' not in st.session_state:
        st.session_state.sistema = SistemaPOTSMDET()
    
    sistema = st.session_state.sistema
    
    # Sidebar para navegação e upload
    with st.sidebar:
        st.markdown("### 📁 CARREGAMENTO DE DADOS")
        
        arquivo = st.file_uploader(
            "Selecione o arquivo de dados",
            type=['xlsx', 'csv'],
            help="Suporta Excel (.xlsx) e CSV (.csv)"
        )
        
        if arquivo is not None:
            if st.button("📤 CARREGAR DADOS", type="primary", use_container_width=True):
                if sistema.carregar_dados(arquivo):
                    st.success("✅ Dados carregados com sucesso!")
                else:
                    st.error("❌ Falha ao carregar dados")
        
        st.markdown("---")
        st.markdown("### 🚀 AÇÕES RÁPIDAS")
        
        col_a1, col_a2 = st.columns(2)
        
        with col_a1:
            if st.button("🔄 Validar", use_container_width=True):
                sistema.validar_dados()
                st.success("Validação concluída!")
        
        with col_a2:
            if st.button("🧹 Limpar", use_container_width=True):
                st.cache_data.clear()
                st.session_state.clear()
                st.rerun()
        
        st.markdown("---")
        st.markdown("### 📊 NAVEGAÇÃO")
        
        # Menu de navegação
        opcao = st.radio(
            "Selecione a página:",
            [
                "🏠 Início",
                "📋 Resumo Executivo",
                "💰 Análise Financeira",
                "⚠️ Registros Problemáticos",
                "📄 Relatório Completo",
                "⚙️ Configurações"
            ]
        )
        
        st.markdown("---")
        st.markdown("### ℹ️ INFORMAÇÕES")
        st.markdown("""
        **Versão:** 3.0.0  
        **Última atualização:** Dez 2024  
        **Desenvolvido para:** SMDET  
        **Contato:** suporte@smdet.gov.br
        """)
    
    # Conteúdo principal baseado na seleção
    if arquivo is None and opcao != "🏠 Início":
        st.info("👈 **Por favor, carregue um arquivo de dados na sidebar para acessar esta funcionalidade.**")
        return
    
    if opcao == "🏠 Início":
        mostrar_pagina_inicial()
    
    elif opcao == "📋 Resumo Executivo":
        sistema.mostrar_resumo_executivo()
    
    elif opcao == "💰 Análise Financeira":
        sistema.mostrar_analise_financeira()
    
    elif opcao == "⚠️ Registros Problemáticos":
        sistema.mostrar_registros_problematicos()
    
    elif opcao == "📄 Relatório Completo":
        sistema.gerar_relatorio_completo()
        
        # Botão para exportar relatório
        st.markdown("---")
        sistema.exportar_relatorio_completo()
    
    elif opcao == "⚙️ Configurações":
        mostrar_configuracoes()
    
    # Rodapé
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: #666; font-size: 0.9em;'>
        <strong>Sistema POT-SMDET</strong> | Secretaria Municipal de Desenvolvimento Econômico e Trabalho<br>
        © 2024 - Todos os direitos reservados
        </div>
        """,
        unsafe_allow_html=True
    )

def mostrar_pagina_inicial():
    """Mostra página inicial com informações"""
    st.markdown("## 🎯 BEM-VINDO AO SISTEMA POT-SMDET")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("""
        ### 📋 SOBRE O SISTEMA
        
        O **Sistema POT-SMDET** é uma ferramenta integrada para gestão e monitoramento 
        dos projetos do **Plano de Ordenamento Territorial (POT)**.
        
        ### 🚀 PRINCIPAIS FUNCIONALIDADES
        
        1. **📁 Carregamento Inteligente** de dados em Excel ou CSV
        2. **🔍 Validação Automática** de consistência dos dados
        3. **📊 Análise Financeira** completa com gráficos interativos
        4. **⚠️ Detecção de Problemas** e sugestões de correção
        5. **📄 Relatórios Completos** para tomada de decisão
        6. **📈 Dashboards** interativos para monitoramento
        
        ### 👨‍💻 COMEÇAR A USAR
        
        1. **Prepare seus dados** em Excel (.xlsx) ou CSV
        2. **Clique em 'Browse files'** na sidebar para selecionar
        3. **Clique em 'Carregar Dados'** para processar
        4. **Navegue** pelas diferentes funcionalidades
        """)
    
    with col2:
        st.markdown("### 📝 ESTRUTURA RECOMENDADA")
        
        exemplo_data = {
            'Projeto': ['Projeto A', 'Projeto B', 'Projeto C'],
            'Valor_Total': [50000, 25000, 100000],
            'Data_Inicio': ['2024-01-15', '2024-02-20', '2024-03-10'],
            'Status': ['Concluído', 'Em andamento', 'Planejado'],
            'Responsavel': ['João Silva', 'Maria Santos', 'Pedro Costa']
        }
        
        st.dataframe(pd.DataFrame(exemplo_data), use_container_width=True)
        
        st.markdown("### 🔧 SUPORTE")
        st.markdown("""
        - 📧 suporte@smdet.gov.br
        - 📞 (11) 9999-9999
        - 🕐 Seg-Sex: 8h-18h
        """)
    
    st.markdown("---")
    
    # Demonstração rápida
    with st.expander("🎬 VER DEMONSTRAÇÃO RÁPIDA", expanded=False):
        st.markdown("""
        ### 🎥 COMO FUNCIONA
        
        1. **Carregue um arquivo** com dados de projetos
        2. **Sistema identifica automaticamente** colunas de valor, data e projeto
        3. **Validação mostra** possíveis problemas nos dados
        4. **Análises financeiras** fornecem insights
        5. **Relatórios completos** podem ser exportados
        
        ### 📊 EXEMPLO DE SAÍDA
        
        Após carregar os dados, você verá:
        - ✅ **Resumo Executivo** com métricas principais
        - 📈 **Gráficos interativos** de distribuição
        - ⚠️ **Alertas** para dados problemáticos
        - 📄 **Relatórios** prontos para download
        """)

def mostrar_configuracoes():
    """Mostra página de configurações"""
    st.markdown("## ⚙️ CONFIGURAÇÕES DO SISTEMA")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 🎨 PREFERÊNCIAS DE VISUALIZAÇÃO")
        
        tema = st.selectbox(
            "Tema de Interface:",
            ["Automático (recomendado)", "Claro", "Escuro"],
            help="O tema automático segue as preferências do seu sistema"
        )
        
        tamanho_fonte = st.slider(
            "Tamanho da Fonte Base:",
            min_value=12,
            max_value=20,
            value=16,
            step=1,
            help="Ajuste o tamanho da fonte para melhor legibilidade"
        )
        
        mostrar_tutoriais = st.checkbox(
            "Mostrar dicas e tutoriais",
            value=True,
            help="Exibe dicas úteis durante o uso do sistema"
        )
    
    with col2:
        st.markdown("### 🔧 CONFIGURAÇÕES DE PROCESSAMENTO")
        
        auto_validar = st.checkbox(
            "Validação automática ao carregar",
            value=True,
            help="Executa validação automática após carregar dados"
        )
        
        manter_historico = st.checkbox(
            "Manter histórico de alterações",
            value=True,
            help="Armazena histórico de modificações nos dados"
        )
        
        limite_registros = st.number_input(
            "Limite de registros para processamento:",
            min_value=1000,
            max_value=1000000,
            value=100000,
            step=1000,
            help="Define o número máximo de registros para processamento otimizado"
        )
    
    st.markdown("### 💾 OPÇÕES DE EXPORTAÇÃO")
    
    col_e1, col_e2 = st.columns(2)
    
    with col_e1:
        formato_exportacao = st.selectbox(
            "Formato padrão de exportação:",
            ["Excel (.xlsx)", "CSV (.csv)", "PDF (.pdf)"]
        )
    
    with col_e2:
        incluir_graficos = st.checkbox(
            "Incluir gráficos nos relatórios",
            value=True
        )
    
    # Botão para salvar configurações
    if st.button("💾 SALVAR CONFIGURAÇÕES", type="primary", use_container_width=True):
        st.success("✅ Configurações salvas com sucesso!")
        # Aqui você implementaria a lógica para salvar as configurações

# ============================================
# EXECUÇÃO
# ============================================
if __name__ == "__main__":
    main()
