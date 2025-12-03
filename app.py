import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from io import StringIO
import io
import warnings
from datetime import datetime

warnings.filterwarnings('ignore')

# Configuração da página
st.set_page_config(
    page_title="Sistema ABAE - Análise de Pagamentos",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personalizado para melhorar a aparência
st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        color: #1E3A8A;
        text-align: center;
        margin-bottom: 2rem;
    }
    .sub-header {
        font-size: 1.5rem;
        color: #2563EB;
        margin-top: 2rem;
        margin-bottom: 1rem;
    }
    .metric-card {
        background-color: #F8FAFC;
        padding: 1.5rem;
        border-radius: 10px;
        border-left: 5px solid #3B82F6;
        margin-bottom: 1rem;
    }
    .success-box {
        background-color: #D1FAE5;
        padding: 1rem;
        border-radius: 8px;
        border: 1px solid #10B981;
        margin: 1rem 0;
    }
    .info-box {
        background-color: #DBEAFE;
        padding: 1rem;
        border-radius: 8px;
        border: 1px solid #3B82F6;
        margin: 1rem 0;
    }
    </style>
""", unsafe_allow_html=True)

# Título principal
st.markdown('<h1 class="main-header">📊 SISTEMA ABAE - ANÁLISE DE PAGAMENTOS</h1>', unsafe_allow_html=True)
st.markdown("---")

# Funções de processamento
def processar_csv(uploaded_file):
    """Processa o arquivo CSV carregado"""
    try:
        # Ler o arquivo
        if uploaded_file.name.endswith('.csv'):
            # Para CSV
            content = uploaded_file.getvalue().decode('utf-8')
            df = pd.read_csv(StringIO(content), sep=';', decimal=',', thousands='.')
        else:
            # Para Excel
            df = pd.read_excel(uploaded_file)
        
        # Limpar nomes das colunas
        df.columns = [col.strip() for col in df.columns]
        
        # Converter colunas monetárias
        colunas_monetarias = ['Valor Total', 'Valor Desconto', 'Valor Pagto', 'Valor Dia']
        
        for coluna in colunas_monetarias:
            if coluna in df.columns:
                # Remover R$, pontos e substituir vírgula por ponto
                df[coluna] = df[coluna].astype(str).str.replace('R\$', '', regex=True)
                df[coluna] = df[coluna].str.replace('.', '', regex=False)
                df[coluna] = df[coluna].str.replace(',', '.', regex=False)
                df[coluna] = pd.to_numeric(df[coluna], errors='coerce')
        
        # Converter outras colunas numéricas
        if 'Dias a apagar' in df.columns:
            df['Dias a apagar'] = pd.to_numeric(df['Dias a apagar'], errors='coerce')
        
        if 'Agencia' in df.columns:
            df['Agencia'] = df['Agencia'].astype(str).str.strip()
        
        if 'Data Pagto' in df.columns:
            df['Data Pagto'] = pd.to_datetime(df['Data Pagto'], format='%d/%m/%Y', errors='coerce')
        
        return df, "✅ Arquivo processado com sucesso!"
    
    except Exception as e:
        return None, f"❌ Erro ao processar arquivo: {str(e)}"

def calcular_metricas(df):
    """Calcula métricas principais"""
    metricas = {}
    
    if df is not None and not df.empty:
        metricas['total_registros'] = len(df)
        metricas['valor_total_pago'] = df['Valor Pagto'].sum() if 'Valor Pagto' in df.columns else 0
        metricas['valor_medio_pago'] = df['Valor Pagto'].mean() if 'Valor Pagto' in df.columns else 0
        metricas['total_agencias'] = df['Agencia'].nunique() if 'Agencia' in df.columns else 0
        
        if 'Gerenciadora' in df.columns:
            gerenciadoras = df['Gerenciadora'].value_counts()
            metricas['gerenciadoras'] = gerenciadoras.to_dict()
        
        if 'Projeto' in df.columns:
            metricas['projeto_principal'] = df['Projeto'].mode()[0] if not df['Projeto'].mode().empty else 'N/A'
    
    return metricas

# Sidebar - Upload e Controles
with st.sidebar:
    st.markdown("## 📁 Upload de Arquivo")
    
    uploaded_file = st.file_uploader(
        "Carregue seu arquivo CSV ou Excel",
        type=['csv', 'xlsx', 'xls'],
        help="Arquivos devem conter as colunas: Ordem, Projeto, Num Cartao, Nome, Agencia, Valor Pagto, etc."
    )
    
    st.markdown("---")
    st.markdown("## ⚙️ Configurações")
    
    show_raw_data = st.checkbox("Mostrar dados brutos", value=False)
    show_analytics = st.checkbox("Mostrar análises detalhadas", value=True)
    show_charts = st.checkbox("Mostrar gráficos", value=True)
    
    st.markdown("---")
    st.markdown("## 📊 Filtros")
    
    # Filtros dinâmicos
    if uploaded_file:
        try:
            df, _ = processar_csv(uploaded_file)
            
            if df is not None:
                # Filtro por Agência
                if 'Agencia' in df.columns:
                    agencias = sorted(df['Agencia'].dropna().unique())
                    selected_agencias = st.multiselect(
                        "Filtrar por Agência:",
                        options=agencias,
                        default=agencias[:5] if len(agencias) > 5 else agencias
                    )
                
                # Filtro por Gerenciadora
                if 'Gerenciadora' in df.columns:
                    gerenciadoras = sorted(df['Gerenciadora'].dropna().unique())
                    selected_gerenciadoras = st.multiselect(
                        "Filtrar por Gerenciadora:",
                        options=gerenciadoras,
                        default=gerenciadoras
                    )
                
                # Filtro por valor mínimo
                if 'Valor Pagto' in df.columns:
                    min_valor = float(df['Valor Pagto'].min())
                    max_valor = float(df['Valor Pagto'].max())
                    valor_range = st.slider(
                        "Faixa de Valor Pago:",
                        min_value=min_valor,
                        max_value=max_valor,
                        value=(min_valor, max_valor)
                    )
        except:
            pass

# Área principal do aplicativo
if uploaded_file is None:
    st.markdown("""
    <div class="info-box">
    <h3>👋 Bem-vindo ao Sistema ABAE!</h3>
    <p>Este sistema foi desenvolvido para análise de pagamentos do projeto ABAE.</p>
    <p><strong>Para começar:</strong></p>
    <ol>
        <li>Use a barra lateral à esquerda para carregar seu arquivo</li>
        <li>O sistema aceita arquivos CSV ou Excel</li>
        <li>Após o upload, as análises serão geradas automaticamente</li>
    </ol>
    <p><strong>Estrutura esperada do arquivo:</strong></p>
    <ul>
        <li>Ordem</li>
        <li>Projeto</li>
        <li>Num Cartao</li>
        <li>Nome</li>
        <li>Agencia</li>
        <li>Valor Total</li>
        <li>Valor Pagto</li>
        <li>Valor Dia</li>
        <li>Dias a apagar</li>
        <li>Gerenciadora</li>
    </ul>
    </div>
    """, unsafe_allow_html=True)
    
    # Exemplo de como os dados devem estar formatados
    st.markdown("### 📋 Exemplo de Formato dos Dados")
    exemplo_data = {
        'Ordem': [1, 2, 3],
        'Projeto': ['BUSCA ATIVA', 'BUSCA ATIVA', 'BUSCA ATIVA'],
        'Num Cartao': [14735, 130329, 152979],
        'Nome': ['Vanessa Falco Chaves', 'Erica Claudia Albano', 'Rosemary De Moraes Alves'],
        'Agencia': ['7025', '1549', '6969'],
        'Valor Total': ['R$ 1.593,90', 'R$ 1.593,90', 'R$ 1.593,90'],
        'Valor Pagto': ['R$ 1.593,90', 'R$ 1.593,90', 'R$ 1.593,90'],
        'Valor Dia': ['R$ 53,13', 'R$ 53,13', 'R$ 53,13'],
        'Dias a apagar': [30, 30, 30],
        'Gerenciadora': ['VISTA', 'VISTA', 'VISTA']
    }
    st.dataframe(pd.DataFrame(exemplo_data), use_container_width=True)

else:
    # Processar arquivo
    with st.spinner('Processando arquivo...'):
        df, message = processar_csv(uploaded_file)
    
    if df is not None:
        st.markdown(f'<div class="success-box">{message}</div>', unsafe_allow_html=True)
        
        # Métricas principais
        st.markdown('<h2 class="sub-header">📈 Métricas Principais</h2>', unsafe_allow_html=True)
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                label="Total de Registros",
                value=f"{len(df):,}",
                help="Número total de beneficiários"
            )
        
        with col2:
            valor_total = df['Valor Pagto'].sum() if 'Valor Pagto' in df.columns else 0
            st.metric(
                label="Valor Total Pago",
                value=f"R$ {valor_total:,.2f}",
                help="Soma de todos os pagamentos"
            )
        
        with col3:
            valor_medio = df['Valor Pagto'].mean() if 'Valor Pagto' in df.columns else 0
            st.metric(
                label="Valor Médio",
                value=f"R$ {valor_medio:,.2f}",
                help="Valor médio por beneficiário"
            )
        
        with col4:
            total_agencias = df['Agencia'].nunique() if 'Agencia' in df.columns else 0
            st.metric(
                label="Agências Únicas",
                value=f"{total_agencias}",
                help="Número de agências diferentes"
            )
        
        # Abas para diferentes análises
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📋 Dados Brutos", 
            "🏢 Análise por Agência", 
            "🏦 Por Gerenciadora", 
            "👥 Beneficiários", 
            "📊 Gráficos"
        ])
        
        with tab1:
            if show_raw_data:
                st.markdown("### Dados Completos")
                st.dataframe(df, use_container_width=True)
                
                # Estatísticas descritivas
                st.markdown("### Estatísticas Descritivas")
                if 'Valor Pagto' in df.columns:
                    st.dataframe(df['Valor Pagto'].describe(), use_container_width=True)
            
        with tab2:
            if 'Agencia' in df.columns:
                st.markdown("### Análise por Agência")
                
                # Agrupar por agência
                agencia_stats = df.groupby('Agencia').agg({
                    'Nome': 'count',
                    'Valor Pagto': ['sum', 'mean', 'min', 'max'],
                    'Dias a apagar': 'mean' if 'Dias a apagar' in df.columns else None
                }).round(2)
                
                # Renomear colunas
                agencia_stats.columns = ['Total Beneficiários', 'Valor Total', 'Valor Médio', 'Valor Mínimo', 'Valor Máximo']
                if 'Dias a apagar' in df.columns:
                    agencia_stats['Dias Médios'] = df.groupby('Agencia')['Dias a apagar'].mean().round(2)
                
                st.dataframe(agencia_stats.sort_values('Valor Total', ascending=False), use_container_width=True)
                
                # Top 10 agências
                st.markdown("#### Top 10 Agências por Valor Total")
                top_10 = agencia_stats.nlargest(10, 'Valor Total')
                st.dataframe(top_10, use_container_width=True)
        
        with tab3:
            if 'Gerenciadora' in df.columns:
                st.markdown("### Análise por Gerenciadora")
                
                # Agrupar por gerenciadora
                gerenciadora_stats = df.groupby('Gerenciadora').agg({
                    'Nome': 'count',
                    'Valor Pagto': ['sum', 'mean'],
                    'Dias a apagar': 'mean' if 'Dias a apagar' in df.columns else None
                }).round(2)
                
                gerenciadora_stats.columns = ['Total Beneficiários', 'Valor Total', 'Valor Médio']
                if 'Dias a apagar' in df.columns:
                    gerenciadora_stats['Dias Médios'] = df.groupby('Gerenciadora')['Dias a apagar'].mean().round(2)
                
                st.dataframe(gerenciadora_stats, use_container_width=True)
                
                # Gráfico de pizza
                if show_charts:
                    fig = px.pie(
                        values=gerenciadora_stats['Total Beneficiários'],
                        names=gerenciadora_stats.index,
                        title='Distribuição por Gerenciadora',
                        hole=0.3
                    )
                    st.plotly_chart(fig, use_container_width=True)
        
        with tab4:
            st.markdown("### Análise de Beneficiários")
            
            # Top beneficiários por valor
            if 'Valor Pagto' in df.columns and 'Nome' in df.columns:
                top_beneficiarios = df.nlargest(10, 'Valor Pagto')[['Nome', 'Valor Pagto', 'Agencia', 'Gerenciadora']]
                st.markdown("#### Top 10 Beneficiários (Maior Valor)")
                st.dataframe(top_beneficiarios, use_container_width=True)
            
            # Distribuição de valores
            if 'Valor Pagto' in df.columns:
                st.markdown("#### Distribuição de Valores Pagos")
                col1, col2 = st.columns(2)
                
                with col1:
                    fig1 = px.histogram(
                        df, 
                        x='Valor Pagto',
                        nbins=20,
                        title='Histograma de Valores',
                        labels={'Valor Pagto': 'Valor Pago (R$)'}
                    )
                    st.plotly_chart(fig1, use_container_width=True)
                
                with col2:
                    fig2 = px.box(
                        df,
                        y='Valor Pagto',
                        title='Box Plot - Valores Pagos',
                        labels={'Valor Pagto': 'Valor Pago (R$)'}
                    )
                    st.plotly_chart(fig2, use_container_width=True)
        
        with tab5:
            if show_charts:
                st.markdown("### Visualizações Gráficas")
                
                # Gráfico 1: Top agências
                if 'Agencia' in df.columns and 'Valor Pagto' in df.columns:
                    top_agencias_chart = df.groupby('Agencia')['Valor Pagto'].sum().nlargest(10)
                    fig1 = px.bar(
                        x=top_agencias_chart.index.astype(str),
                        y=top_agencias_chart.values,
                        title='Top 10 Agências por Valor Total',
                        labels={'x': 'Agência', 'y': 'Valor Total (R$)'}
                    )
                    fig1.update_traces(
                        text=[f'R$ {val:,.2f}' for val in top_agencias_chart.values],
                        textposition='auto'
                    )
                    st.plotly_chart(fig1, use_container_width=True)
                
                # Gráfico 2: Dispersão
                if 'Valor Pagto' in df.columns and 'Dias a apagar' in df.columns:
                    fig2 = px.scatter(
                        df,
                        x='Dias a apagar',
                        y='Valor Pagto',
                        title='Relação: Dias vs Valor',
                        labels={'Dias a apagar': 'Dias a Pagar', 'Valor Pagto': 'Valor Pago (R$)'},
                        color='Gerenciadora' if 'Gerenciadora' in df.columns else None
                    )
                    st.plotly_chart(fig2, use_container_width=True)
                
                # Gráfico 3: Heatmap de correlação
                numeric_cols = df.select_dtypes(include=[np.number]).columns
                if len(numeric_cols) > 1:
                    corr_matrix = df[numeric_cols].corr()
                    fig3 = px.imshow(
                        corr_matrix,
                        title='Matriz de Correlação',
                        text_auto=True,
                        aspect="auto"
                    )
                    st.plotly_chart(fig3, use_container_width=True)
        
        # Seção de exportação
        st.markdown("---")
        st.markdown('<h2 class="sub-header">💾 Exportação de Dados</h2>', unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # Exportar para CSV
            csv = df.to_csv(index=False, sep=';', decimal=',')
            st.download_button(
                label="📥 Baixar CSV Processado",
                data=csv,
                file_name="dados_abae_processados.csv",
                mime="text/csv"
            )
        
        with col2:
            # Exportar resumo por agência
            if 'Agencia' in df.columns:
                agencia_summary = df.groupby('Agencia')['Valor Pagto'].agg(['count', 'sum', 'mean']).round(2)
                agencia_summary_csv = agencia_summary.to_csv(sep=';', decimal=',')
                st.download_button(
                    label="📥 Resumo por Agência",
                    data=agencia_summary_csv,
                    file_name="resumo_agencias.csv",
                    mime="text/csv"
                )
        
        with col3:
            # Exportar para Excel
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Dados Completos', index=False)
                
                if 'Agencia' in df.columns:
                    agencia_stats.to_excel(writer, sheet_name='Por Agencia')
                
                if 'Gerenciadora' in df.columns:
                    gerenciadora_stats.to_excel(writer, sheet_name='Por Gerenciadora')
            
            excel_data = output.getvalue()
            st.download_button(
                label="📥 Baixar Excel Completo",
                data=excel_data,
                file_name="relatorio_completo_abae.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        
        # Informações do processamento
        st.markdown("---")
        with st.expander("ℹ️ Informações do Processamento"):
            st.write(f"**Arquivo:** {uploaded_file.name}")
            st.write(f"**Tamanho:** {uploaded_file.size:,} bytes")
            st.write(f"**Colunas no dataset:** {', '.join(df.columns)}")
            st.write(f"**Registros processados:** {len(df):,}")
            st.write(f"**Data do processamento:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    
    else:
        st.error(f"Erro ao processar o arquivo: {message}")

# Rodapé
st.markdown("---")
st.markdown(
    """
    <div style="text-align: center; color: #666; font-size: 0.9rem; margin-top: 2rem;">
    <p>Sistema ABAE - Análise de Pagamentos | Desenvolvido para processamento de dados do projeto</p>
    <p>📧 Suporte: sistema.abae@analise.com | 📞 (11) 99999-9999</p>
    </div>
    """,
    unsafe_allow_html=True
)
