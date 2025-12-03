# app.py - Sistema ABAE Análise de Pagamentos
# Arquivo único completo com todas as dependências

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from io import StringIO, BytesIO
import warnings
from datetime import datetime
import sys

# Configurar warnings
warnings.filterwarnings('ignore')

# Configuração da página Streamlit
st.set_page_config(
    page_title="Sistema ABAE - Análise de Pagamentos",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Título principal
st.title("📊 SISTEMA ABAE - ANÁLISE DE PAGAMENTOS")
st.markdown("---")

# ============================================================================
# FUNÇÕES DE PROCESSAMENTO DE DADOS
# ============================================================================

def processar_arquivo(uploaded_file):
    """
    Processa arquivo CSV ou Excel carregado pelo usuário.
    
    Args:
        uploaded_file: Arquivo carregado via st.file_uploader
        
    Returns:
        tuple: (DataFrame processado, mensagem de status)
    """
    try:
        # Detectar tipo de arquivo
        if uploaded_file.name.lower().endswith('.csv'):
            # Processar CSV
            try:
                # Tentar UTF-8 primeiro
                content = uploaded_file.getvalue().decode('utf-8')
            except UnicodeDecodeError:
                # Tentar Latin-1 se UTF-8 falhar
                content = uploaded_file.getvalue().decode('latin-1')
            
            # Ler CSV com separador ; e decimal brasileiro
            df = pd.read_csv(
                StringIO(content), 
                sep=';', 
                decimal=',', 
                thousands='.',
                dtype=str  # Ler tudo como string inicialmente
            )
        
        elif uploaded_file.name.lower().endswith(('.xlsx', '.xls')):
            # Processar Excel
            df = pd.read_excel(uploaded_file, dtype=str)
        
        else:
            return None, "❌ Formato de arquivo não suportado. Use CSV ou Excel."
        
        # ====================================================================
        # PASSO 1: PADRONIZAR NOMES DAS COLUNAS
        # ====================================================================
        col_rename_map = {}
        for col in df.columns:
            col_str = str(col).strip()
            col_lower = col_str.lower()
            
            # Mapear para nomes padronizados
            if 'ordem' in col_lower:
                col_rename_map[col] = 'Ordem'
            elif 'projeto' in col_lower:
                col_rename_map[col] = 'Projeto'
            elif any(x in col_lower for x in ['cartão', 'cartao', 'card']):
                col_rename_map[col] = 'Num Cartao'
            elif 'nome' in col_lower:
                col_rename_map[col] = 'Nome'
            elif 'distrito' in col_lower:
                col_rename_map[col] = 'Distrito'
            elif any(x in col_lower for x in ['agencia', 'agência']):
                col_rename_map[col] = 'Agencia'
            elif 'rg' in col_lower:
                col_rename_map[col] = 'RG'
            elif 'valor' in col_lower and 'total' in col_lower:
                col_rename_map[col] = 'Valor Total'
            elif 'valor' in col_lower and 'desconto' in col_lower:
                col_rename_map[col] = 'Valor Desconto'
            elif 'valor' in col_lower and 'pagto' in col_lower:
                col_rename_map[col] = 'Valor Pagto'
            elif 'data' in col_lower and 'pagto' in col_lower:
                col_rename_map[col] = 'Data Pagto'
            elif 'valor' in col_lower and 'dia' in col_lower:
                col_rename_map[col] = 'Valor Dia'
            elif any(x in col_lower for x in ['dias', 'apagar']):
                col_rename_map[col] = 'Dias a apagar'
            elif 'cpf' in col_lower:
                col_rename_map[col] = 'CPF'
            elif any(x in col_lower for x in ['gerenciadora', 'gestora']):
                col_rename_map[col] = 'Gerenciadora'
        
        # Aplicar renomeação
        df = df.rename(columns=col_rename_map)
        
        # ====================================================================
        # PASSO 2: CONVERTER COLUNAS MONETÁRIAS
        # ====================================================================
        colunas_monetarias = ['Valor Total', 'Valor Desconto', 'Valor Pagto', 'Valor Dia']
        
        for coluna in colunas_monetarias:
            if coluna in df.columns:
                # Garantir que é string
                df[coluna] = df[coluna].astype(str)
                
                # Remover caracteres não numéricos (manter números, ponto e vírgula)
                df[coluna] = df[coluna].str.replace('R\$', '', regex=True)
                df[coluna] = df[coluna].str.replace('$', '', regex=False)
                df[coluna] = df[coluna].str.replace(' ', '', regex=False)
                
                # Substituir ponto de milhar (remover) e vírgula decimal (substituir por ponto)
                df[coluna] = df[coluna].apply(lambda x: str(x).replace('.', '').replace(',', '.') 
                                             if pd.notna(x) else x)
                
                # Converter para numérico
                df[coluna] = pd.to_numeric(df[coluna], errors='coerce')
        
        # ====================================================================
        # PASSO 3: CONVERTER OUTRAS COLUNAS NUMÉRICAS
        # ====================================================================
        if 'Dias a apagar' in df.columns:
            df['Dias a apagar'] = pd.to_numeric(df['Dias a apagar'], errors='coerce')
        
        if 'Ordem' in df.columns:
            df['Ordem'] = pd.to_numeric(df['Ordem'], errors='coerce')
        
        if 'Num Cartao' in df.columns:
            df['Num Cartao'] = pd.to_numeric(df['Num Cartao'], errors='coerce')
        
        # ====================================================================
        # PASSO 4: CONVERTER DATAS
        # ====================================================================
        if 'Data Pagto' in df.columns:
            # Tentar múltiplos formatos de data
            for fmt in ['%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%d/%m/%y', '%d-%m-%y']:
                try:
                    df['Data Pagto'] = pd.to_datetime(df['Data Pagto'], format=fmt, errors='coerce')
                    break
                except:
                    continue
            
            # Se nenhum formato específico funcionar, tentar inferência automática
            if df['Data Pagto'].dtype == 'object':
                df['Data Pagto'] = pd.to_datetime(df['Data Pagto'], errors='coerce')
        
        # ====================================================================
        # PASSO 5: TRATAR VALORES NULOS E ESPAÇOS
        # ====================================================================
        # Colunas de texto
        colunas_texto = ['Nome', 'Projeto', 'Gerenciadora', 'Agencia', 'RG', 'CPF']
        for col in colunas_texto:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
                df[col] = df[col].replace({'nan': '', 'None': '', 'NaT': ''})
        
        # Converter agência para string (mesmo sendo numérica, manter como texto para agrupamento)
        if 'Agencia' in df.columns:
            df['Agencia'] = df['Agencia'].astype(str).str.strip()
        
        return df, "✅ Arquivo processado com sucesso!"
    
    except Exception as e:
        error_msg = f"❌ Erro ao processar arquivo: {str(e)}"
        return None, error_msg

# ============================================================================
# FUNÇÕES DE ANÁLISE E RELATÓRIOS
# ============================================================================

def calcular_metricas_principais(df):
    """
    Calcula métricas principais do DataFrame.
    
    Args:
        df: DataFrame processado
        
    Returns:
        dict: Dicionário com métricas
    """
    metricas = {}
    
    try:
        metricas['total_registros'] = len(df)
        
        if 'Valor Pagto' in df.columns:
            metricas['valor_total'] = df['Valor Pagto'].sum()
            metricas['valor_medio'] = df['Valor Pagto'].mean()
            metricas['valor_min'] = df['Valor Pagto'].min()
            metricas['valor_max'] = df['Valor Pagto'].max()
            metricas['valor_std'] = df['Valor Pagto'].std()
        
        if 'Agencia' in df.columns:
            metricas['total_agencias'] = df['Agencia'].nunique()
        
        if 'Gerenciadora' in df.columns:
            metricas['total_gerenciadoras'] = df['Gerenciadora'].nunique()
            distrib_gerenciadora = df['Gerenciadora'].value_counts()
            metricas['gerenciadora_principal'] = distrib_gerenciadora.index[0] if len(distrib_gerenciadora) > 0 else 'N/A'
            metricas['total_vista'] = distrib_gerenciadora.get('VISTA', 0)
            metricas['total_rede'] = distrib_gerenciadora.get('REDE CIDAD�', 0)
        
        if 'Dias a apagar' in df.columns:
            metricas['dias_medio'] = df['Dias a apagar'].mean()
            metricas['dias_total'] = df['Dias a apagar'].sum()
        
        if 'Valor Dia' in df.columns:
            metricas['valor_dia_medio'] = df['Valor Dia'].mean()
        
        if 'Projeto' in df.columns:
            metricas['projeto_principal'] = df['Projeto'].mode()[0] if not df['Projeto'].mode().empty else 'N/A'
    
    except Exception as e:
        st.error(f"Erro ao calcular métricas: {e}")
    
    return metricas

def gerar_relatorio_agencia(df):
    """
    Gera relatório consolidado por agência.
    
    Args:
        df: DataFrame processado
        
    Returns:
        DataFrame: Relatório por agência
    """
    if 'Agencia' not in df.columns or 'Valor Pagto' not in df.columns:
        return pd.DataFrame()
    
    try:
        relatorio = df.groupby('Agencia').agg({
            'Nome': 'count',
            'Valor Pagto': ['sum', 'mean', 'min', 'max', 'std'],
            'Dias a apagar': 'mean' if 'Dias a apagar' in df.columns else None,
            'Valor Dia': 'mean' if 'Valor Dia' in df.columns else None
        }).round(2)
        
        # Simplificar nomes das colunas
        relatorio.columns = ['Qtd Beneficiários', 'Valor Total', 'Valor Médio', 
                            'Valor Mínimo', 'Valor Máximo', 'Desvio Padrão']
        
        # Adicionar colunas extras se existirem
        col_index = 6
        if 'Dias a apagar' in df.columns:
            relatorio.insert(col_index, 'Dias Médios', df.groupby('Agencia')['Dias a apagar'].mean().round(2))
            col_index += 1
        
        if 'Valor Dia' in df.columns:
            relatorio.insert(col_index, 'Valor Dia Médio', df.groupby('Agencia')['Valor Dia'].mean().round(2))
        
        return relatorio.sort_values('Valor Total', ascending=False)
    
    except Exception as e:
        st.error(f"Erro ao gerar relatório por agência: {e}")
        return pd.DataFrame()

def gerar_relatorio_gerenciadora(df):
    """
    Gera relatório consolidado por gerenciadora.
    
    Args:
        df: DataFrame processado
        
    Returns:
        DataFrame: Relatório por gerenciadora
    """
    if 'Gerenciadora' not in df.columns or 'Valor Pagto' not in df.columns:
        return pd.DataFrame()
    
    try:
        relatorio = df.groupby('Gerenciadora').agg({
            'Nome': 'count',
            'Valor Pagto': ['sum', 'mean', 'min', 'max'],
            'Dias a apagar': 'mean' if 'Dias a apagar' in df.columns else None,
            'Agencia': 'nunique'
        }).round(2)
        
        # Simplificar nomes das colunas
        relatorio.columns = ['Qtd Beneficiários', 'Valor Total', 'Valor Médio', 
                            'Valor Mínimo', 'Valor Máximo', 'Dias Médios', 'Qtd Agências']
        
        return relatorio.sort_values('Valor Total', ascending=False)
    
    except Exception as e:
        st.error(f"Erro ao gerar relatório por gerenciadora: {e}")
        return pd.DataFrame()

# ============================================================================
# FUNÇÕES DE VISUALIZAÇÃO (GRÁFICOS)
# ============================================================================

def criar_grafico_distribuicao_valores(df):
    """
    Cria histograma da distribuição de valores.
    
    Args:
        df: DataFrame processado
        
    Returns:
        plotly.graph_objects.Figure: Gráfico de histograma
    """
    if 'Valor Pagto' not in df.columns:
        return None
    
    try:
        fig = px.histogram(
            df,
            x='Valor Pagto',
            nbins=30,
            title='Distribuição de Valores Pagos',
            labels={'Valor Pagto': 'Valor Pago (R$)'},
            color_discrete_sequence=['#3366CC']
        )
        
        fig.update_layout(
            xaxis_title='Valor Pago (R$)',
            yaxis_title='Quantidade de Beneficiários',
            bargap=0.1,
            showlegend=False
        )
        
        return fig
    
    except Exception as e:
        st.error(f"Erro ao criar gráfico de distribuição: {e}")
        return None

def criar_grafico_top_agencias(df, top_n=10):
    """
    Cria gráfico de barras das top agências.
    
    Args:
        df: DataFrame processado
        top_n: Número de agências para mostrar
        
    Returns:
        plotly.graph_objects.Figure: Gráfico de barras
    """
    if 'Agencia' not in df.columns or 'Valor Pagto' not in df.columns:
        return None
    
    try:
        # Calcular totais por agência
        agencia_totals = df.groupby('Agencia')['Valor Pagto'].sum().sort_values(ascending=False).head(top_n)
        
        fig = go.Figure(data=[
            go.Bar(
                x=agencia_totals.index,
                y=agencia_totals.values,
                text=[f'R$ {val:,.2f}' for val in agencia_totals.values],
                textposition='auto',
                marker_color='#4CAF50'
            )
        ])
        
        fig.update_layout(
            title=f'Top {top_n} Agências por Valor Total',
            xaxis_title='Agência',
            yaxis_title='Valor Total (R$)',
            xaxis_tickangle=-45
        )
        
        return fig
    
    except Exception as e:
        st.error(f"Erro ao criar gráfico de top agências: {e}")
        return None

def criar_grafico_pizza_gerenciadora(df):
    """
    Cria gráfico de pizza por gerenciadora.
    
    Args:
        df: DataFrame processado
        
    Returns:
        plotly.graph_objects.Figure: Gráfico de pizza
    """
    if 'Gerenciadora' not in df.columns:
        return None
    
    try:
        contagem = df['Gerenciadora'].value_counts()
        
        fig = go.Figure(data=[
            go.Pie(
                labels=contagem.index,
                values=contagem.values,
                hole=0.3,
                textinfo='label+percent',
                marker_colors=px.colors.qualitative.Set3
            )
        ])
        
        fig.update_layout(
            title='Distribuição por Gerenciadora'
        )
        
        return fig
    
    except Exception as e:
        st.error(f"Erro ao criar gráfico de pizza: {e}")
        return None

def criar_grafico_dispersao_dias_valor(df):
    """
    Cria gráfico de dispersão entre dias e valores.
    
    Args:
        df: DataFrame processado
        
    Returns:
        plotly.graph_objects.Figure: Gráfico de dispersão
    """
    if 'Dias a apagar' not in df.columns or 'Valor Pagto' not in df.columns:
        return None
    
    try:
        fig = px.scatter(
            df,
            x='Dias a apagar',
            y='Valor Pagto',
            title='Relação: Dias a Pagar vs Valor Pago',
            labels={
                'Dias a apagar': 'Dias a Pagar',
                'Valor Pagto': 'Valor Pago (R$)'
            },
            color='Gerenciadora' if 'Gerenciadora' in df.columns else None,
            opacity=0.7
        )
        
        fig.update_traces(marker=dict(size=8))
        
        return fig
    
    except Exception as e:
        st.error(f"Erro ao criar gráfico de dispersão: {e}")
        return None

# ============================================================================
# FUNÇÕES DE EXPORTAÇÃO
# ============================================================================

def exportar_para_excel(df, relatorio_agencia, relatorio_gerenciadora):
    """
    Exporta dados para arquivo Excel com múltiplas abas.
    
    Args:
        df: DataFrame principal
        relatorio_agencia: Relatório por agência
        relatorio_gerenciadora: Relatório por gerenciadora
        
    Returns:
        bytes: Dados do arquivo Excel em bytes
    """
    output = BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Aba 1: Dados completos
        df.to_excel(writer, sheet_name='Dados Completos', index=False)
        
        # Aba 2: Relatório por agência
        if not relatorio_agencia.empty:
            relatorio_agencia.to_excel(writer, sheet_name='Por Agência')
        
        # Aba 3: Relatório por gerenciadora
        if not relatorio_gerenciadora.empty:
            relatorio_gerenciadora.to_excel(writer, sheet_name='Por Gerenciadora')
        
        # Aba 4: Resumo estatístico
        if 'Valor Pagto' in df.columns:
            resumo_stats = df['Valor Pagto'].describe().to_frame().T
            resumo_stats.to_excel(writer, sheet_name='Resumo Estatístico')
        
        # Aba 5: Top beneficiários
        if 'Nome' in df.columns and 'Valor Pagto' in df.columns:
            top_benef = df.nlargest(20, 'Valor Pagto')[['Nome', 'Valor Pagto', 'Agencia', 'Gerenciadora']]
            top_benef.to_excel(writer, sheet_name='Top Beneficiários', index=False)
    
    return output.getvalue()

# ============================================================================
# INTERFACE PRINCIPAL DO STREAMLIT
# ============================================================================

def main():
    """
    Função principal que executa a aplicação Streamlit.
    """
    
    # ========================================================================
    # SIDEBAR - CONFIGURAÇÕES E UPLOAD
    # ========================================================================
    with st.sidebar:
        st.header("📁 CONFIGURAÇÃO DO SISTEMA")
        
        # Upload do arquivo
        uploaded_file = st.file_uploader(
            "Carregue o arquivo de dados",
            type=['csv', 'xlsx'],
            help="Suporta CSV (separado por ;) ou Excel"
        )
        
        st.markdown("---")
        
        # Opções de visualização
        st.header("⚙️ OPÇÕES DE VISUALIZAÇÃO")
        mostrar_graficos = st.checkbox("Mostrar gráficos", value=True)
        mostrar_dados_brutos = st.checkbox("Mostrar dados completos", value=False)
        top_n_agencias = st.slider("Top N agências nos gráficos", 5, 20, 10)
        
        st.markdown("---")
        
        # Informações do sistema
        st.header("ℹ️ INFORMAÇÕES")
        st.info(
            "**Sistema ABAE - Análise de Pagamentos**\n\n"
            "Versão: 2.0\n"
            f"Data: {datetime.now().strftime('%d/%m/%Y')}\n"
            "Desenvolvido para análise de dados do projeto ABAE"
        )
    
    # ========================================================================
    # ÁREA PRINCIPAL - CONTEÚDO DINÂMICO
    # ========================================================================
    
    # Caso 1: Nenhum arquivo carregado
    if uploaded_file is None:
        st.info("👋 **Bem-vindo ao Sistema ABAE!**")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown("""
            ### 📋 Como usar o sistema:
            
            1. **Carregue seu arquivo** usando a barra lateral à esquerda
            2. **Formatos suportados:**
               - CSV (separado por ponto-e-vírgula)
               - Excel (.xlsx, .xls)
            
            3. **Estrutura esperada do arquivo:**
               - Ordem;Projeto;Num Cartao;Nome;Distrito;Agencia;RG
               - Valor Total;Valor Desconto;Valor Pagto;Data Pagto
               - Valor Dia;Dias a apagar;CPF;Gerenciadora
            
            4. **Formato dos valores monetários:**
               - R$ 1.593,90 (vírgula como decimal)
               - Sistema converte automaticamente
            """)
        
        with col2:
            st.markdown("""
            ### 🚀 Funcionalidades:
            
            ✅ **Processamento automático**
            ✅ **Análise por agência**
            ✅ **Análise por gerenciadora**
            ✅ **Gráficos interativos**
            ✅ **Exportação para Excel**
            ✅ **Filtros dinâmicos**
            ✅ **Relatórios detalhados**
            """)
        
        # Exemplo de dados
        with st.expander("📝 **Exemplo de dados (formato esperado)**"):
            exemplo_data = {
                'Ordem': [1, 2, 3],
                'Projeto': ['BUSCA ATIVA', 'BUSCA ATIVA', 'BUSCA ATIVA'],
                'Num Cartao': [14735, 130329, 152979],
                'Nome': ['Vanessa Falco Chaves', 'Erica Claudia Albano', 'Rosemary De Moraes Alves'],
                'Distrito': [0, 0, 0],
                'Agencia': ['7025', '1549', '6969'],
                'RG': ['438455885', '445934864', '586268327'],
                'Valor Total': ['R$ 1.593,90', 'R$ 1.593,90', 'R$ 1.593,90'],
                'Valor Desconto': ['R$ 0,00', 'R$ 0,00', 'R$ 0,00'],
                'Valor Pagto': ['R$ 1.593,90', 'R$ 1.593,90', 'R$ 1.593,90'],
                'Data Pagto': ['20/10/2025', '20/10/2025', '20/10/2025'],
                'Valor Dia': ['R$ 53,13', 'R$ 53,13', 'R$ 53,13'],
                'Dias a apagar': [30, 30, 30],
                'CPF': ['30490002870', '', '8275372801'],
                'Gerenciadora': ['VISTA', 'VISTA', 'VISTA']
            }
            
            st.dataframe(pd.DataFrame(exemplo_data), use_container_width=True)
        
        return
    
    # Caso 2: Arquivo carregado - processar
    with st.spinner(f'Processando {uploaded_file.name}...'):
        df, mensagem = processar_arquivo(uploaded_file)
    
    if df is None:
        st.error(mensagem)
        return
    
    # Sucesso no processamento
    st.success(mensagem)
    st.markdown(f"**Arquivo:** `{uploaded_file.name}` | **Registros:** {len(df):,} | **Colunas:** {len(df.columns)}")
    st.markdown("---")
    
    # ========================================================================
    # SEÇÃO 1: MÉTRICAS PRINCIPAIS
    # ========================================================================
    st.header("📈 MÉTRICAS PRINCIPAIS")
    
    metricas = calcular_metricas_principais(df)
    
    # Cards com métricas
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total de Registros", f"{metricas.get('total_registros', 0):,}")
    
    with col2:
        valor_total = metricas.get('valor_total', 0)
        st.metric("Valor Total Pago", f"R$ {valor_total:,.2f}")
    
    with col3:
        valor_medio = metricas.get('valor_medio', 0)
        st.metric("Valor Médio", f"R$ {valor_medio:,.2f}")
    
    with col4:
        total_agencias = metricas.get('total_agencias', 0)
        st.metric("Agências Únicas", f"{total_agencias}")
    
    # Segunda linha de métricas
    col5, col6, col7, col8 = st.columns(4)
    
    with col5:
        dias_medio = metricas.get('dias_medio', 0)
        st.metric("Dias Médios", f"{dias_medio:.1f}")
    
    with col6:
        valor_dia_medio = metricas.get('valor_dia_medio', 0)
        st.metric("Valor/Dia Médio", f"R$ {valor_dia_medio:.2f}")
    
    with col7:
        total_vista = metricas.get('total_vista', 0)
        st.metric("VISTA", f"{total_vista:,}")
    
    with col8:
        total_rede = metricas.get('total_rede', 0)
        st.metric("REDE CIDADÃO", f"{total_rede:,}")
    
    st.markdown("---")
    
    # ========================================================================
    # SEÇÃO 2: ANÁLISES DETALHADAS (ABAS)
    # ========================================================================
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📋 VISÃO GERAL", 
        "🏢 POR AGÊNCIA", 
        "🏦 POR GERENCIADORA", 
        "📊 GRÁFICOS", 
        "💾 EXPORTAR"
    ])
    
    # ========================================================================
    # ABA 1: VISÃO GERAL
    # ========================================================================
    with tab1:
        if mostrar_dados_brutos:
            st.subheader("Dados Processados (Visualização)")
            st.dataframe(df, use_container_width=True, height=400)
        
        # Estatísticas descritivas
        st.subheader("📊 Estatísticas Descritivas")
        
        if 'Valor Pagto' in df.columns:
            col_stat1, col_stat2 = st.columns(2)
            
            with col_stat1:
                st.markdown("**Valores Pagos**")
                stats_df = df['Valor Pagto'].describe().to_frame().T.round(2)
                st.dataframe(stats_df, use_container_width=True)
            
            with col_stat2:
                if 'Dias a apagar' in df.columns:
                    st.markdown("**Dias a Pagar**")
                    dias_stats = df['Dias a apagar'].describe().to_frame().T.round(2)
                    st.dataframe(dias_stats, use_container_width=True)
        
        # Informações do dataset
        with st.expander("🔍 Informações Detalhadas do Dataset"):
            col_info1, col_info2 = st.columns(2)
            
            with col_info1:
                st.write("**Colunas disponíveis:**")
                for col in df.columns:
                    na_count = df[col].isna().sum()
                    st.write(f"- `{col}`: {df[col].dtype} ({na_count} nulos)")
            
            with col_info2:
                st.write("**Resumo do processamento:**")
                st.write(f"- Data/hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
                st.write(f"- Memória aproximada: {sys.getsizeof(df) / 1024 / 1024:.2f} MB")
                
                if 'Data Pagto' in df.columns:
                    st.write(f"- Período: {df['Data Pagto'].min().strftime('%d/%m/%Y')} a {df['Data Pagto'].max().strftime('%d/%m/%Y')}")
    
    # ========================================================================
    # ABA 2: POR AGÊNCIA
    # ========================================================================
    with tab2:
        st.subheader("🏢 Análise por Agência")
        
        relatorio_agencia = gerar_relatorio_agencia(df)
        
        if not relatorio_agencia.empty:
            st.dataframe(relatorio_agencia, use_container_width=True)
            
            # Top 10 agências
            st.subheader(f"🏆 Top {top_n_agencias} Agências")
            top_agencias = relatorio_agencia.head(top_n_agencias)
            st.dataframe(top_agencias, use_container_width=True)
        else:
            st.warning("Não foi possível gerar relatório por agência. Verifique se as colunas 'Agencia' e 'Valor Pagto' estão presentes.")
    
    # ========================================================================
    # ABA 3: POR GERENCIADORA
    # ========================================================================
    with tab3:
        st.subheader("🏦 Análise por Gerenciadora")
        
        relatorio_gerenciadora = gerar_relatorio_gerenciadora(df)
        
        if not relatorio_gerenciadora.empty:
            st.dataframe(relatorio_gerenciadora, use_container_width=True)
            
            # Comparativo VISTA vs REDE
            if 'VISTA' in relatorio_gerenciadora.index or 'REDE CIDAD�' in relatorio_gerenciadora.index:
                st.subheader("📊 Comparativo VISTA vs REDE CIDADÃO")
                
                comparativo_data = []
                if 'VISTA' in relatorio_gerenciadora.index:
                    vista_data = relatorio_gerenciadora.loc['VISTA']
                    comparativo_data.append({
                        'Gerenciadora': 'VISTA',
                        'Beneficiários': vista_data['Qtd Beneficiários'],
                        'Valor Total': vista_data['Valor Total'],
                        'Valor Médio': vista_data['Valor Médio']
                    })
                
                if 'REDE CIDAD�' in relatorio_gerenciadora.index:
                    rede_data = relatorio_gerenciadora.loc['REDE CIDAD�']
                    comparativo_data.append({
                        'Gerenciadora': 'REDE CIDADÃO',
                        'Beneficiários': rede_data['Qtd Beneficiários'],
                        'Valor Total': rede_data['Valor Total'],
                        'Valor Médio': rede_data['Valor Médio']
                    })
                
                if comparativo_data:
                    st.dataframe(pd.DataFrame(comparativo_data), use_container_width=True)
        else:
            st.warning("Não foi possível gerar relatório por gerenciadora. Verifique se a coluna 'Gerenciadora' está presente.")
    
    # ========================================================================
    # ABA 4: GRÁFICOS
    # ========================================================================
    with tab4:
        if not mostrar_graficos:
            st.info("Ative a opção 'Mostrar gráficos' na sidebar para visualizar os gráficos.")
        else:
            st.subheader("📊 Visualizações Gráficas")
            
            # Gráfico 1: Distribuição de valores
            fig1 = criar_grafico_distribuicao_valores(df)
            if fig1:
                st.plotly_chart(fig1, use_container_width=True)
            
            # Gráficos em colunas
            col_g1, col_g2 = st.columns(2)
            
            with col_g1:
                # Gráfico 2: Top agências
                fig2 = criar_grafico_top_agencias(df, top_n_agencias)
                if fig2:
                    st.plotly_chart(fig2, use_container_width=True)
            
            with col_g2:
                # Gráfico 3: Pizza por gerenciadora
                fig3 = criar_grafico_pizza_gerenciadora(df)
                if fig3:
                    st.plotly_chart(fig3, use_container_width=True)
            
            # Gráfico 4: Dispersão
            fig4 = criar_grafico_dispersao_dias_valor(df)
            if fig4:
                st.plotly_chart(fig4, use_container_width=True)
    
    # ========================================================================
    # ABA 5: EXPORTAÇÃO
    # ========================================================================
    with tab5:
        st.subheader("💾 Exportação de Dados")
        
        col_exp1, col_exp2, col_exp3 = st.columns(3)
        
        with col_exp1:
            # Exportar CSV
            csv_data = df.to_csv(index=False, sep=';', decimal=',')
            st.download_button(
                label="📥 Baixar CSV",
                data=csv_data,
                file_name="dados_abae_processados.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col_exp2:
            # Exportar Excel
            excel_bytes = exportar_para_excel(df, relatorio_agencia, relatorio_gerenciadora)
            st.download_button(
                label="📥 Baixar Excel Completo",
                data=excel_bytes,
                file_name="relatorio_abae_completo.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        
        with col_exp3:
            # Exportar JSON
            json_data = df.to_json(orient='records', indent=2, force_ascii=False)
            st.download_button(
                label="📥 Baixar JSON",
                data=json_data,
                file_name="dados_abae.json",
                mime="application/json",
                use_container_width=True
            )
        
        st.markdown("---")
        
        # Opções avançadas de exportação
        with st.expander("⚙️ Opções Avançadas de Exportação"):
            st.markdown("### Exportar Relatórios Individuais")
            
            col_exp4, col_exp5 = st.columns(2)
            
            with col_exp4:
                if not relatorio_agencia.empty:
                    agencia_csv = relatorio_agencia.to_csv(sep=';', decimal=',')
                    st.download_button(
                        label="📊 Relatório por Agência (CSV)",
                        data=agencia_csv,
                        file_name="relatorio_agencias.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
            
            with col_exp5:
                if not relatorio_gerenciadora.empty:
                    gerenciadora_csv = relatorio_gerenciadora.to_csv(sep=';', decimal=',')
                    st.download_button(
                        label="🏦 Relatório por Gerenciadora (CSV)",
                        data=gerenciadora_csv,
                        file_name="relatorio_gerenciadoras.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
    
    # ========================================================================
    # RODAPÉ
    # ========================================================================
    st.markdown("---")
    st.markdown(
        f"""
        <div style='text-align: center; color: gray; font-size: 0.9em;'>
        Sistema ABAE - Análise de Pagamentos | 
        Processado em: {datetime.now().strftime('%d/%m/%Y %H:%M')} | 
        Desenvolvido para o projeto ABAE
        </div>
        """,
        unsafe_allow_html=True
    )

# ============================================================================
# EXECUÇÃO PRINCIPAL
# ============================================================================
if __name__ == "__main__":
    main()
