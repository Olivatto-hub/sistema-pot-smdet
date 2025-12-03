import pandas as pd
import streamlit as st
from io import BytesIO
import matplotlib.pyplot as plt
import seaborn as sns

# Configuração da página
st.set_page_config(page_title="Análise PGTO ABASTECE", page_icon="💰", layout="wide")

# Título da aplicação
st.title("💰 Sistema de Análise de Pagamentos - PGTO ABASTECE")

# Função para carregar e processar o arquivo
@st.cache_data
def carregar_dados(uploaded_file):
    try:
        # Ler o arquivo CSV com encoding correto e ponto-e-vírgula como separador
        df = pd.read_csv(uploaded_file, sep=';', encoding='utf-8', decimal=',', thousands='.')
        
        # Limpar nomes das colunas
        df.columns = df.columns.str.strip()
        
        # Verificar se as colunas necessárias existem
        colunas_necessarias = ['Projeto', 'Nome', 'Valor Total', 'Valor Pagto', 'Data Pagto', 'Dias a apagar']
        
        for coluna in colunas_necessarias:
            if coluna not in df.columns:
                st.error(f"Coluna '{coluna}' não encontrada no arquivo!")
                st.write("Colunas disponíveis:", df.columns.tolist())
                return None
        
        # Converter colunas de valor para numérico
        df['Valor Total'] = pd.to_numeric(df['Valor Total'].str.replace('R\$ ', '').str.replace('.', '').str.replace(',', '.'), errors='coerce')
        df['Valor Pagto'] = pd.to_numeric(df['Valor Pagto'].str.replace('R\$ ', '').str.replace('.', '').str.replace(',', '.'), errors='coerce')
        
        # Converter data
        df['Data Pagto'] = pd.to_datetime(df['Data Pagto'], format='%d/%m/%Y', errors='coerce')
        
        return df
    except Exception as e:
        st.error(f"Erro ao processar o arquivo: {str(e)}")
        return None

# Funções para métricas
def calcular_metricas(df):
    metricas = {
        'Total Pessoas': len(df),
        'Valor Total': df['Valor Total'].sum(),
        'Valor Pago': df['Valor Pagto'].sum(),
        'Média por Pessoa': df['Valor Total'].mean(),
        'Maior Valor': df['Valor Total'].max(),
        'Menor Valor': df['Valor Total'].min()
    }
    return metricas

# Interface principal
uploaded_file = st.file_uploader("Faça upload do arquivo CSV (PGTO ABASTECE)", type=['csv'])

if uploaded_file is not None:
    # Carregar dados
    df = carregar_dados(uploaded_file)
    
    if df is not None:
        st.success(f"✅ Arquivo carregado com sucesso! {len(df)} registros encontrados.")
        
        # Mostrar prévia dos dados
        with st.expander("📋 Visualizar dados (primeiras 10 linhas)"):
            st.dataframe(df.head(10))
        
        # Sidebar com filtros
        st.sidebar.header("🔍 Filtros")
        
        # Filtro por Projeto
        projetos = df['Projeto'].unique()
        projeto_selecionado = st.sidebar.selectbox("Selecione o Projeto:", ['Todos'] + list(projetos))
        
        # Filtro por valor
        min_valor, max_valor = st.sidebar.slider(
            "Filtrar por Valor Total:",
            float(df['Valor Total'].min()),
            float(df['Valor Total'].max()),
            (float(df['Valor Total'].min()), float(df['Valor Total'].max()))
        )
        
        # Aplicar filtros
        df_filtrado = df.copy()
        
        if projeto_selecionado != 'Todos':
            df_filtrado = df_filtrado[df_filtrado['Projeto'] == projeto_selecionado]
        
        df_filtrado = df_filtrado[(df_filtrado['Valor Total'] >= min_valor) & (df_filtrado['Valor Total'] <= max_valor)]
        
        # Métricas principais
        st.header("📊 Métricas Gerais")
        metricas = calcular_metricas(df_filtrado)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("👥 Total de Pessoas", f"{metricas['Total Pessoas']:,}")
            st.metric("📈 Maior Valor", f"R$ {metricas['Maior Valor']:,.2f}")
        
        with col2:
            st.metric("💰 Valor Total", f"R$ {metricas['Valor Total']:,.2f}")
            st.metric("📉 Menor Valor", f"R$ {metricas['Menor Valor']:,.2f}")
        
        with col3:
            st.metric("💵 Valor Pago", f"R$ {metricas['Valor Pago']:,.2f}")
            st.metric("📊 Média por Pessoa", f"R$ {metricas['Média por Pessoa']:,.2f}")
        
        # Análise por Projeto
        st.header("📈 Análise por Projeto")
        projeto_stats = df_filtrado.groupby('Projeto').agg({
            'Nome': 'count',
            'Valor Total': ['sum', 'mean', 'min', 'max']
        }).round(2)
        
        projeto_stats.columns = ['Quantidade', 'Valor Total', 'Média', 'Mínimo', 'Máximo']
        projeto_stats['Valor Total'] = projeto_stats['Valor Total'].map(lambda x: f'R$ {x:,.2f}')
        projeto_stats['Média'] = projeto_stats['Média'].map(lambda x: f'R$ {x:,.2f}')
        projeto_stats['Mínimo'] = projeto_stats['Mínimo'].map(lambda x: f'R$ {x:,.2f}')
        projeto_stats['Máximo'] = projeto_stats['Máximo'].map(lambda x: f'R$ {x:,.2f}')
        
        st.dataframe(projeto_stats)
        
        # Gráficos
        st.header("📊 Visualizações Gráficas")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Distribuição por Projeto (Quantidade)")
            fig, ax = plt.subplots(figsize=(10, 6))
            df_filtrado['Projeto'].value_counts().plot(kind='bar', ax=ax, color='skyblue')
            ax.set_ylabel('Quantidade de Pessoas')
            ax.set_xlabel('Projeto')
            plt.xticks(rotation=45)
            st.pyplot(fig)
        
        with col2:
            st.subheader("Distribuição por Projeto (Valor Total)")
            fig, ax = plt.subplots(figsize=(10, 6))
            df_filtrado.groupby('Projeto')['Valor Total'].sum().sort_values().plot(
                kind='barh', ax=ax, color='lightgreen'
            )
            ax.set_xlabel('Valor Total (R$)')
            ax.set_ylabel('Projeto')
            st.pyplot(fig)
        
        # Distribuição de Valores
        st.subheader("Distribuição de Valores Individuais")
        fig, ax = plt.subplots(figsize=(12, 6))
        df_filtrado['Valor Total'].hist(bins=30, ax=ax, edgecolor='black')
        ax.set_xlabel('Valor (R$)')
        ax.set_ylabel('Frequência')
        ax.set_title('Histograma de Valores')
        st.pyplot(fig)
        
        # Top 10 maiores valores
        st.header("🏆 Top 10 Maiores Valores")
        top_10 = df_filtrado.nlargest(10, 'Valor Total')[['Nome', 'Projeto', 'Valor Total']]
        top_10['Valor Total'] = top_10['Valor Total'].map(lambda x: f'R$ {x:,.2f}')
        st.dataframe(top_10)
        
        # Pesquisa de pessoas
        st.header("🔎 Pesquisar Pessoa")
        nome_pesquisa = st.text_input("Digite o nome para pesquisa:")
        
        if nome_pesquisa:
            resultados = df_filtrado[df_filtrado['Nome'].str.contains(nome_pesquisa, case=False, na=False)]
            st.write(f"🔍 {len(resultados)} resultado(s) encontrado(s):")
            
            if len(resultados) > 0:
                for _, row in resultados.iterrows():
                    with st.container():
                        st.markdown(f"**{row['Nome']}**")
                        st.write(f"Projeto: {row['Projeto']}")
                        st.write(f"Valor Total: R$ {row['Valor Total']:,.2f}")
                        st.write(f"Data Pagto: {row['Data Pagto'].strftime('%d/%m/%Y')}")
                        st.divider()
        
        # Download dos dados filtrados
        st.header("📥 Exportar Dados")
        
        if st.button("💾 Baixar Dados Filtrados (CSV)"):
            csv = df_filtrado.to_csv(index=False, sep=';', decimal=',')
            st.download_button(
                label="Clique para baixar",
                data=csv,
                file_name="dados_filtrados_pgto_abastece.csv",
                mime="text/csv"
            )
        
        # Informações sobre os dados
        with st.expander("ℹ️ Informações sobre os dados"):
            st.write(f"**Total de registros no arquivo original:** {len(df)}")
            st.write(f"**Total de registros após filtros:** {len(df_filtrado)}")
            st.write(f"**Período dos dados:** {df['Data Pagto'].min().strftime('%d/%m/%Y')} a {df['Data Pagto'].max().strftime('%d/%m/%Y')}")
            st.write(f"**Projetos encontrados:** {', '.join(projetos)}")

else:
    st.info("👆 Faça upload de um arquivo CSV para começar a análise.")
    st.markdown("""
    ### 📋 Formato esperado do arquivo:
    - Colunas obrigatórias: `Projeto`, `Nome`, `Valor Total`, `Valor Pagto`, `Data Pagto`
    - Separador: ponto-e-vírgula (;)
    - Formato de data: DD/MM/YYYY
    - Formato de valores: R$ 1.593,90
    """)
