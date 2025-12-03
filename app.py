import pandas as pd
import streamlit as st
from io import BytesIO

# Configuração da página
st.set_page_config(page_title="Sistema de Análise de Pagamentos", page_icon="💰", layout="wide")

# Título da aplicação
st.title("💰 Sistema de Análise de Pagamentos")

# Função para carregar e processar o arquivo
@st.cache_data
def carregar_dados(uploaded_file):
    try:
        # Tentar diferentes encodings
        encodings = ['latin-1', 'iso-8859-1', 'cp1252', 'utf-8']
        
        for encoding in encodings:
            try:
                # Ler o arquivo CSV com encoding correto
                uploaded_file.seek(0)  # Resetar o ponteiro do arquivo
                df = pd.read_csv(uploaded_file, sep=';', encoding=encoding, decimal=',', thousands='.')
                
                # Limpar nomes das colunas
                df.columns = [col.strip() for col in df.columns]
                
                # Verificar se as colunas necessárias existem
                colunas_necessarias = ['Projeto', 'Nome', 'Valor Total', 'Valor Pagto', 'Data Pagto']
                
                for coluna in colunas_necessarias:
                    if coluna not in df.columns:
                        # Tentar versões alternativas
                        if coluna == 'Nome' and 'Nome' not in df.columns:
                            # Procurar coluna que contenha 'nome'
                            nome_cols = [col for col in df.columns if 'nome' in col.lower()]
                            if nome_cols:
                                df = df.rename(columns={nome_cols[0]: 'Nome'})
                        
                        if coluna == 'Projeto' and 'Projeto' not in df.columns:
                            # Procurar coluna que contenha 'projeto'
                            proj_cols = [col for col in df.columns if 'projeto' in col.lower()]
                            if proj_cols:
                                df = df.rename(columns={proj_cols[0]: 'Projeto'})
                        
                        if coluna == 'Valor Total' and 'Valor Total' not in df.columns:
                            # Procurar coluna que contenha 'valor total'
                            vt_cols = [col for col in df.columns if 'valor' in col.lower() and 'total' in col.lower()]
                            if vt_cols:
                                df = df.rename(columns={vt_cols[0]: 'Valor Total'})
                
                # Verificar novamente
                for coluna in colunas_necessarias:
                    if coluna not in df.columns:
                        continue  # Continuar para tentar processar mesmo sem todas as colunas
                
                # Converter colunas de valor para numérico
                if 'Valor Total' in df.columns:
                    # Remover R$, pontos e converter vírgula para ponto
                    df['Valor Total'] = df['Valor Total'].astype(str).str.replace('R\$', '', regex=False)
                    df['Valor Total'] = df['Valor Total'].str.replace('.', '', regex=False)
                    df['Valor Total'] = df['Valor Total'].str.replace(',', '.', regex=False)
                    df['Valor Total'] = pd.to_numeric(df['Valor Total'], errors='coerce')
                
                if 'Valor Pagto' in df.columns:
                    df['Valor Pagto'] = df['Valor Pagto'].astype(str).str.replace('R\$', '', regex=False)
                    df['Valor Pagto'] = df['Valor Pagto'].str.replace('.', '', regex=False)
                    df['Valor Pagto'] = df['Valor Pagto'].str.replace(',', '.', regex=False)
                    df['Valor Pagto'] = pd.to_numeric(df['Valor Pagto'], errors='coerce')
                
                # Converter data
                if 'Data Pagto' in df.columns:
                    # Tentar diferentes formatos de data
                    for fmt in ['%d/%m/%Y', '%d/%m/%y', '%Y-%m-%d', '%d-%m-%Y']:
                        try:
                            df['Data Pagto'] = pd.to_datetime(df['Data Pagto'], format=fmt, errors='raise')
                            break
                        except:
                            continue
                    else:
                        # Se nenhum formato funcionar, tentar inferir
                        df['Data Pagto'] = pd.to_datetime(df['Data Pagto'], errors='coerce')
                
                st.success(f"✅ Arquivo carregado com encoding: {encoding}")
                return df
                
            except UnicodeDecodeError:
                continue
            except Exception as e:
                st.warning(f"Tentativa com encoding {encoding} falhou: {str(e)}")
                continue
        
        # Se nenhum encoding funcionou, tentar com erro
        uploaded_file.seek(0)
        df = pd.read_csv(uploaded_file, sep=';', encoding='latin-1', errors='replace', decimal=',', thousands='.')
        st.warning("⚠️ Arquivo carregado com substituição de caracteres inválidos")
        return df
        
    except Exception as e:
        st.error(f"Erro crítico ao processar o arquivo: {str(e)}")
        st.write("Dica: O arquivo deve estar no formato CSV com separador ';'")
        return None

# Funções para métricas
def calcular_metricas(df):
    metricas = {}
    
    if 'Nome' in df.columns:
        metricas['Total Pessoas'] = len(df)
    
    if 'Valor Total' in df.columns:
        metricas['Valor Total'] = df['Valor Total'].sum()
        metricas['Média por Pessoa'] = df['Valor Total'].mean()
        metricas['Maior Valor'] = df['Valor Total'].max()
        metricas['Menor Valor'] = df['Valor Total'].min()
    
    if 'Valor Pagto' in df.columns:
        metricas['Valor Pago'] = df['Valor Pagto'].sum()
    
    return metricas

# Função para formatar valores monetários
def formatar_moeda(valor):
    try:
        return f"R$ {float(valor):,.2f}"
    except:
        return f"R$ {valor}"

# Interface principal
st.header("📤 Upload do Arquivo")
uploaded_file = st.file_uploader("Carregue o arquivo CSV (PGTO ABASTECE)", type=['csv'])

if uploaded_file is not None:
    # Carregar dados
    with st.spinner("Processando arquivo..."):
        df = carregar_dados(uploaded_file)
    
    if df is not None:
        # Mostrar informações do arquivo
        st.success(f"✅ Arquivo processado com sucesso!")
        
        # Mostrar prévia dos dados
        with st.expander("📋 Visualizar dados carregados", expanded=True):
            st.write(f"**Total de registros:** {len(df)}")
            st.write(f"**Colunas disponíveis:** {', '.join(df.columns.tolist())}")
            st.dataframe(df.head(10))
        
        # Sidebar com filtros
        st.sidebar.header("🔍 Filtros")
        
        # Filtro por Projeto (se existir)
        if 'Projeto' in df.columns:
            projetos = sorted(df['Projeto'].dropna().unique())
            projeto_selecionado = st.sidebar.selectbox("Selecione o Projeto:", ['Todos'] + list(projetos))
        else:
            projeto_selecionado = 'Todos'
            st.sidebar.warning("Coluna 'Projeto' não encontrada")
        
        # Filtro por valor (se existir)
        if 'Valor Total' in df.columns:
            min_valor = float(df['Valor Total'].min())
            max_valor = float(df['Valor Total'].max())
            
            min_valor, max_valor = st.sidebar.slider(
                "Filtrar por Valor Total:",
                min_valor,
                max_valor,
                (min_valor, max_valor)
            )
        else:
            min_valor, max_valor = 0, 0
            st.sidebar.warning("Coluna 'Valor Total' não encontrada")
        
        # Filtro por nome (se existir)
        if 'Nome' in df.columns:
            nome_filtro = st.sidebar.text_input("Filtrar por nome:")
        else:
            nome_filtro = ""
            st.sidebar.warning("Coluna 'Nome' não encontrada")
        
        # Aplicar filtros
        df_filtrado = df.copy()
        
        # Filtrar por projeto
        if projeto_selecionado != 'Todos' and 'Projeto' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['Projeto'] == projeto_selecionado]
        
        # Filtrar por valor
        if 'Valor Total' in df_filtrado.columns:
            df_filtrado = df_filtrado[
                (df_filtrado['Valor Total'] >= min_valor) & 
                (df_filtrado['Valor Total'] <= max_valor)
            ]
        
        # Filtrar por nome
        if nome_filtro and 'Nome' in df_filtrado.columns:
            df_filtrado = df_filtrado[
                df_filtrado['Nome'].astype(str).str.contains(nome_filtro, case=False, na=False)
            ]
        
        # Métricas principais
        st.header("📊 Métricas Gerais")
        metricas = calcular_metricas(df_filtrado)
        
        # Layout de métricas
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if 'Total Pessoas' in metricas:
                st.metric("👥 Total de Pessoas", f"{metricas['Total Pessoas']:,}")
            if 'Maior Valor' in metricas:
                st.metric("📈 Maior Valor", formatar_moeda(metricas['Maior Valor']))
        
        with col2:
            if 'Valor Total' in metricas:
                st.metric("💰 Valor Total", formatar_moeda(metricas['Valor Total']))
            if 'Menor Valor' in metricas:
                st.metric("📉 Menor Valor", formatar_moeda(metricas['Menor Valor']))
        
        with col3:
            if 'Valor Pago' in metricas:
                st.metric("💵 Valor Pago", formatar_moeda(metricas['Valor Pago']))
        
        with col4:
            if 'Média por Pessoa' in metricas:
                st.metric("📊 Média por Pessoa", formatar_moeda(metricas['Média por Pessoa']))
        
        # Análise por Projeto
        if 'Projeto' in df_filtrado.columns:
            st.header("📈 Análise por Projeto")
            
            # Estatísticas por projeto
            projeto_stats = df_filtrado.groupby('Projeto').agg({
                'Nome': 'count',
                'Valor Total': ['sum', 'mean', 'min', 'max'],
                'Valor Pagto': 'sum'
            }).round(2)
            
            # Renomear colunas
            projeto_stats.columns = ['Quantidade', 'Valor Total', 'Média', 'Mínimo', 'Máximo', 'Valor Pago']
            
            # Formatar para exibição
            projeto_display = projeto_stats.copy()
            for col in ['Valor Total', 'Média', 'Mínimo', 'Máximo', 'Valor Pago']:
                projeto_display[col] = projeto_display[col].apply(lambda x: f"R$ {x:,.2f}" if pd.notnull(x) else "-")
            
            st.dataframe(projeto_display)
            
            # Gráficos por projeto
            col_chart1, col_chart2 = st.columns(2)
            
            with col_chart1:
                st.subheader("Quantidade por Projeto")
                contagem_projetos = df_filtrado['Projeto'].value_counts()
                st.bar_chart(contagem_projetos)
            
            with col_chart2:
                st.subheader("Valor Total por Projeto")
                valor_por_projeto = df_filtrado.groupby('Projeto')['Valor Total'].sum().sort_values()
                st.bar_chart(valor_por_projeto)
        
        # Histograma de valores
        if 'Valor Total' in df_filtrado.columns:
            st.header("📊 Distribuição de Valores")
            
            # Criar bins para histograma
            bins = st.slider("Número de intervalos:", 5, 50, 20)
            
            # Criar histograma com pandas
            hist_series = pd.cut(df_filtrado['Valor Total'], bins=bins).value_counts().sort_index()
            st.bar_chart(hist_series)
        
        # Tabelas detalhadas
        st.header("📋 Dados Detalhados")
        
        tab1, tab2, tab3 = st.tabs(["📊 Todos os Dados", "🏆 Top Valores", "🔍 Pesquisa"])
        
        with tab1:
            st.subheader("Dados Filtrados")
            st.write(f"Mostrando {len(df_filtrado)} registros")
            
            # Formatar colunas para exibição
            df_display = df_filtrado.copy()
            
            if 'Valor Total' in df_display.columns:
                df_display['Valor Total'] = df_display['Valor Total'].apply(lambda x: f"R$ {x:,.2f}" if pd.notnull(x) else "-")
            
            if 'Valor Pagto' in df_display.columns:
                df_display['Valor Pagto'] = df_display['Valor Pagto'].apply(lambda x: f"R$ {x:,.2f}" if pd.notnull(x) else "-")
            
            if 'Data Pagto' in df_display.columns:
                df_display['Data Pagto'] = df_display['Data Pagto'].dt.strftime('%d/%m/%Y')
            
            st.dataframe(df_display)
        
        with tab2:
            st.subheader("Top 10 Maiores Valores")
            if 'Valor Total' in df_filtrado.columns:
                top_10 = df_filtrado.nlargest(10, 'Valor Total')[['Nome', 'Projeto', 'Valor Total', 'Data Pagto']].copy()
                top_10['Valor Total'] = top_10['Valor Total'].apply(lambda x: f"R$ {x:,.2f}")
                if 'Data Pagto' in top_10.columns:
                    top_10['Data Pagto'] = top_10['Data Pagto'].dt.strftime('%d/%m/%Y')
                st.dataframe(top_10)
            
            st.subheader("Top 10 Menores Valores")
            if 'Valor Total' in df_filtrado.columns:
                bottom_10 = df_filtrado.nsmallest(10, 'Valor Total')[['Nome', 'Projeto', 'Valor Total', 'Data Pagto']].copy()
                bottom_10['Valor Total'] = bottom_10['Valor Total'].apply(lambda x: f"R$ {x:,.2f}")
                if 'Data Pagto' in bottom_10.columns:
                    bottom_10['Data Pagto'] = bottom_10['Data Pagto'].dt.strftime('%d/%m/%Y')
                st.dataframe(bottom_10)
        
        with tab3:
            st.subheader("Pesquisa Avançada")
            
            col_search1, col_search2 = st.columns(2)
            
            with col_search1:
                search_nome = st.text_input("Digite o nome completo ou parcial:")
            
            with col_search2:
                if 'Projeto' in df_filtrado.columns:
                    search_projeto = st.selectbox("Projeto:", ['Todos'] + list(df_filtrado['Projeto'].unique()))
                else:
                    search_projeto = 'Todos'
            
            if st.button("🔍 Pesquisar"):
                resultados = df_filtrado.copy()
                
                if search_nome and 'Nome' in resultados.columns:
                    resultados = resultados[
                        resultados['Nome'].astype(str).str.contains(search_nome, case=False, na=False)
                    ]
                
                if search_projeto != 'Todos' and 'Projeto' in resultados.columns:
                    resultados = resultados[resultados['Projeto'] == search_projeto]
                
                if len(resultados) > 0:
                    st.success(f"Encontrados {len(resultados)} resultado(s)")
                    
                    # Formatar para exibição
                    resultados_display = resultados.copy()
                    
                    if 'Valor Total' in resultados_display.columns:
                        resultados_display['Valor Total'] = resultados_display['Valor Total'].apply(
                            lambda x: f"R$ {x:,.2f}" if pd.notnull(x) else "-"
                        )
                    
                    if 'Valor Pagto' in resultados_display.columns:
                        resultados_display['Valor Pagto'] = resultados_display['Valor Pagto'].apply(
                            lambda x: f"R$ {x:,.2f}" if pd.notnull(x) else "-"
                        )
                    
                    if 'Data Pagto' in resultados_display.columns:
                        resultados_display['Data Pagto'] = resultados_display['Data Pagto'].dt.strftime('%d/%m/%Y')
                    
                    st.dataframe(resultados_display)
                else:
                    st.warning("Nenhum resultado encontrado")
        
        # Exportação de dados
        st.header("📥 Exportar Dados")
        
        col_export1, col_export2 = st.columns(2)
        
        with col_export1:
            # CSV
            csv_data = df_filtrado.to_csv(index=False, sep=';', decimal=',')
            st.download_button(
                label="⬇️ Baixar CSV",
                data=csv_data,
                file_name="dados_filtrados.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col_export2:
            # Excel
            try:
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_filtrado.to_excel(writer, sheet_name='Dados', index=False)
                    if 'Projeto' in df_filtrado.columns:
                        projeto_stats.to_excel(writer, sheet_name='Resumo por Projeto')
                output.seek(0)
                
                st.download_button(
                    label="⬇️ Baixar Excel",
                    data=output,
                    file_name="dados_filtrados.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            except:
                st.warning("Funcionalidade Excel não disponível")

else:
    st.info("👆 Faça upload de um arquivo CSV para começar a análise")
    
    st.markdown("""
    ### 📋 Instruções:
    1. O arquivo deve ser um CSV com separador ponto-e-vírgula (;)
    2. Formatos suportados:
       - Valores: R$ 1.593,90 ou 1593,90
       - Data: DD/MM/YYYY
    3. Colunas esperadas:
       - Projeto
       - Nome
       - Valor Total
       - Valor Pagto
       - Data Pagto
    
    ### 🚀 Funcionalidades:
    - Filtros por projeto, valor e nome
    - Métricas e estatísticas
    - Análise por projeto
    - Gráficos interativos
    - Pesquisa avançada
    - Exportação em CSV/Excel
    """)

# Rodapé
st.divider()
st.caption("Sistema de Análise de Pagamentos v1.0")
