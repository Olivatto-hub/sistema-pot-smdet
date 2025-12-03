import pandas as pd
import streamlit as st
from io import BytesIO

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
        'Menor Valor': df['Valor Total'].min(),
        'Valor Médio Pago': df['Valor Pagto'].mean()
    }
    return metricas

# Função para formatar valores monetários
def formatar_moeda(valor):
    return f"R$ {valor:,.2f}"

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
        projetos = sorted(df['Projeto'].unique())
        projeto_selecionado = st.sidebar.selectbox("Selecione o Projeto:", ['Todos'] + list(projetos))
        
        # Filtro por valor
        min_valor, max_valor = st.sidebar.slider(
            "Filtrar por Valor Total:",
            float(df['Valor Total'].min()),
            float(df['Valor Total'].max()),
            (float(df['Valor Total'].min()), float(df['Valor Total'].max()))
        )
        
        # Filtro por nome
        nome_filtro = st.sidebar.text_input("Filtrar por nome (parcial):")
        
        # Aplicar filtros
        df_filtrado = df.copy()
        
        if projeto_selecionado != 'Todos':
            df_filtrado = df_filtrado[df_filtrado['Projeto'] == projeto_selecionado]
        
        df_filtrado = df_filtrado[(df_filtrado['Valor Total'] >= min_valor) & (df_filtrado['Valor Total'] <= max_valor)]
        
        if nome_filtro:
            df_filtrado = df_filtrado[df_filtrado['Nome'].str.contains(nome_filtro, case=False, na=False)]
        
        # Métricas principais
        st.header("📊 Métricas Gerais")
        metricas = calcular_metricas(df_filtrado)
        
        # Layout de métricas em colunas
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("👥 Total de Pessoas", f"{metricas['Total Pessoas']:,}")
            st.metric("📈 Maior Valor", formatar_moeda(metricas['Maior Valor']))
        
        with col2:
            st.metric("💰 Valor Total", formatar_moeda(metricas['Valor Total']))
            st.metric("📉 Menor Valor", formatar_moeda(metricas['Menor Valor']))
        
        with col3:
            st.metric("💵 Valor Pago", formatar_moeda(metricas['Valor Pago']))
            st.metric("📊 Média por Pessoa", formatar_moeda(metricas['Média por Pessoa']))
        
        # Análise por Projeto
        st.header("📈 Análise por Projeto")
        
        # Estatísticas por projeto usando pandas
        projeto_stats = df_filtrado.groupby('Projeto').agg({
            'Nome': 'count',
            'Valor Total': ['sum', 'mean', 'min', 'max'],
            'Valor Pagto': 'sum'
        }).round(2)
        
        # Renomear colunas
        projeto_stats.columns = ['Quantidade', 'Valor Total', 'Média', 'Mínimo', 'Máximo', 'Valor Pago']
        
        # Formatar valores
        projeto_stats_formatado = projeto_stats.copy()
        for col in ['Valor Total', 'Média', 'Mínimo', 'Máximo', 'Valor Pago']:
            projeto_stats_formatado[col] = projeto_stats_formatado[col].apply(lambda x: f"R$ {x:,.2f}")
        
        st.dataframe(projeto_stats_formatado)
        
        # Visualizações com gráficos nativos do Streamlit
        st.header("📊 Visualizações Gráficas")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Distribuição por Projeto (Quantidade)")
            contagem_projetos = df_filtrado['Projeto'].value_counts()
            st.bar_chart(contagem_projetos)
        
        with col2:
            st.subheader("Valor Total por Projeto")
            valor_por_projeto = df_filtrado.groupby('Projeto')['Valor Total'].sum().sort_values()
            st.bar_chart(valor_por_projeto)
        
        # Histograma de valores
        st.subheader("Distribuição de Valores Individuais")
        
        # Criar bins para o histograma
        bins = st.slider("Número de intervalos (bins):", 5, 50, 20)
        
        # Usar o gráfico de barras do Streamlit para histograma
        hist_data = df_filtrado['Valor Total']
        hist_values, hist_bins = pd.cut(hist_data, bins=bins, retbins=True)
        hist_counts = hist_values.value_counts().sort_index()
        
        st.bar_chart(hist_counts)
        
        # Tabelas detalhadas
        st.header("📋 Dados Detalhados")
        
        # Top 10 maiores valores
        with st.expander("🏆 Top 10 Maiores Valores"):
            top_10 = df_filtrado.nlargest(10, 'Valor Total')[['Nome', 'Projeto', 'Valor Total', 'Data Pagto']].copy()
            top_10['Valor Total'] = top_10['Valor Total'].apply(formatar_moeda)
            top_10['Data Pagto'] = top_10['Data Pagto'].dt.strftime('%d/%m/%Y')
            st.dataframe(top_10)
        
        # Top 10 menores valores
        with st.expander("📉 Top 10 Menores Valores"):
            bottom_10 = df_filtrado.nsmallest(10, 'Valor Total')[['Nome', 'Projeto', 'Valor Total', 'Data Pagto']].copy()
            bottom_10['Valor Total'] = bottom_10['Valor Total'].apply(formatar_moeda)
            bottom_10['Data Pagto'] = bottom_10['Data Pagto'].dt.strftime('%d/%m/%Y')
            st.dataframe(bottom_10)
        
        # Pesquisa avançada
        st.header("🔎 Pesquisa Avançada")
        
        col_search1, col_search2 = st.columns(2)
        
        with col_search1:
            pesquisa_nome = st.text_input("Digite o nome para pesquisa exata:")
        
        with col_search2:
            pesquisa_projeto = st.selectbox("Filtrar por projeto:", ['Todos'] + list(df_filtrado['Projeto'].unique()))
        
        if pesquisa_nome:
            resultados = df_filtrado[df_filtrado['Nome'].str.contains(pesquisa_nome, case=False, na=False)]
            
            if pesquisa_projeto != 'Todos':
                resultados = resultados[resultados['Projeto'] == pesquisa_projeto]
            
            if len(resultados) > 0:
                st.write(f"🔍 {len(resultados)} resultado(s) encontrado(s):")
                
                resultados_formatados = resultados.copy()
                resultados_formatados['Valor Total'] = resultados_formatados['Valor Total'].apply(formatar_moeda)
                resultados_formatados['Valor Pagto'] = resultados_formatados['Valor Pagto'].apply(formatar_moeda)
                resultados_formatados['Data Pagto'] = resultados_formatados['Data Pagto'].dt.strftime('%d/%m/%Y')
                
                st.dataframe(resultados_formatados[['Nome', 'Projeto', 'Valor Total', 'Valor Pagto', 'Data Pagto']])
            else:
                st.warning("Nenhum resultado encontrado com os critérios especificados.")
        
        # Resumo estatístico
        st.header("📈 Resumo Estatístico Completo")
        
        col_stat1, col_stat2 = st.columns(2)
        
        with col_stat1:
            st.subheader("Estatísticas Descritivas")
            estatisticas = df_filtrado['Valor Total'].describe()
            
            for stat, value in estatisticas.items():
                if stat in ['count']:
                    st.write(f"**{stat.capitalize()}:** {int(value):,}")
                else:
                    st.write(f"**{stat.capitalize()}:** R$ {value:,.2f}")
        
        with col_stat2:
            st.subheader("Distribuição por Faixa de Valor")
            
            # Criar faixas de valor
            faixas = pd.cut(df_filtrado['Valor Total'], bins=5)
            distribuicao_faixas = faixas.value_counts().sort_index()
            
            for faixa, quantidade in distribuicao_faixas.items():
                st.write(f"**{faixa}:** {quantidade:,} pessoas ({quantidade/len(df_filtrado)*100:.1f}%)")
        
        # Download dos dados filtrados
        st.header("📥 Exportar Dados")
        
        col_dl1, col_dl2 = st.columns(2)
        
        with col_dl1:
            if st.button("💾 Baixar Dados Filtrados (CSV)", use_container_width=True):
                csv = df_filtrado.to_csv(index=False, sep=';', decimal=',')
                st.download_button(
                    label="Clique para baixar CSV",
                    data=csv,
                    file_name="dados_filtrados_pgto_abastece.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        
        with col_dl2:
            if st.button("📄 Baixar Resumo (Excel)", use_container_width=True):
                # Criar um resumo em Excel
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_filtrado.to_excel(writer, sheet_name='Dados Completos', index=False)
                    projeto_stats.to_excel(writer, sheet_name='Resumo por Projeto')
                    
                    # Adicionar estatísticas
                    estatisticas_df = pd.DataFrame([metricas])
                    estatisticas_df.to_excel(writer, sheet_name='Métricas', index=False)
                
                output.seek(0)
                st.download_button(
                    label="Clique para baixar Excel",
                    data=output,
                    file_name="resumo_analise_pgto.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
        
        # Informações sobre os dados
        with st.expander("ℹ️ Informações sobre os dados"):
            st.write(f"**Total de registros no arquivo original:** {len(df):,}")
            st.write(f"**Total de registros após filtros:** {len(df_filtrado):,}")
            st.write(f"**Período dos dados:** {df['Data Pagto'].min().strftime('%d/%m/%Y')} a {df['Data Pagto'].max().strftime('%d/%m/%Y')}")
            st.write(f"**Projetos encontrados:** {', '.join(projetos)}")
            st.write(f"**Intervalo de valores:** {formatar_moeda(df['Valor Total'].min())} a {formatar_moeda(df['Valor Total'].max())}")

else:
    st.info("👆 Faça upload de um arquivo CSV para começar a análise.")
    st.markdown("""
    ### 📋 Formato esperado do arquivo:
    - Colunas obrigatórias: `Projeto`, `Nome`, `Valor Total`, `Valor Pagto`, `Data Pagto`
    - Separador: ponto-e-vírgula (;)
    - Formato de data: DD/MM/YYYY
    - Formato de valores: R$ 1.593,90
    
    ### 🚀 Funcionalidades disponíveis:
    1. **Filtros avançados** por projeto, valor e nome
    2. **Métricas em tempo real** com KPIs importantes
    3. **Análise por projeto** com estatísticas detalhadas
    4. **Gráficos interativos** usando bibliotecas nativas
    5. **Pesquisa avançada** de pessoas
    6. **Exportação de dados** em CSV e Excel
    7. **Resumo estatístico** completo
    """)
