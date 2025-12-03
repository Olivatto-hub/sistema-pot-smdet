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
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file, sep=';', encoding=encoding, decimal=',', thousands='.')
                break
            except UnicodeDecodeError:
                continue
            except Exception:
                continue
        else:
            # Última tentativa com error handling
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file, sep=';', encoding='latin-1', errors='replace', decimal=',', thousands='.')
        
        # Limpar nomes das colunas
        df.columns = [str(col).strip() for col in df.columns]
        
        # Corrigir nomes das colunas
        col_mapping = {}
        for col in df.columns:
            col_lower = str(col).lower()
            if 'nome' in col_lower:
                col_mapping[col] = 'Nome'
            elif 'projeto' in col_lower:
                col_mapping[col] = 'Projeto'
            elif 'valor total' in col_lower:
                col_mapping[col] = 'Valor Total'
            elif 'valor pagto' in col_lower or 'valor pago' in col_lower:
                col_mapping[col] = 'Valor Pagto'
            elif 'data pagto' in col_lower or 'data pago' in col_lower:
                col_mapping[col] = 'Data Pagto'
        
        df = df.rename(columns=col_mapping)
        
        # Processar colunas de valor
        if 'Valor Total' in df.columns:
            df['Valor Total'] = pd.to_numeric(
                df['Valor Total'].astype(str)
                .str.replace('R\$', '', regex=False)
                .str.replace(' ', '', regex=False)
                .str.replace('.', '', regex=False)
                .str.replace(',', '.', regex=False),
                errors='coerce'
            )
        
        if 'Valor Pagto' in df.columns:
            df['Valor Pagto'] = pd.to_numeric(
                df['Valor Pagto'].astype(str)
                .str.replace('R\$', '', regex=False)
                .str.replace(' ', '', regex=False)
                .str.replace('.', '', regex=False)
                .str.replace(',', '.', regex=False),
                errors='coerce'
            )
        
        # Processar data
        if 'Data Pagto' in df.columns:
            df['Data Pagto'] = pd.to_datetime(df['Data Pagto'], dayfirst=True, errors='coerce')
        
        return df
        
    except Exception as e:
        st.error(f"Erro ao processar o arquivo: {str(e)}")
        return None

# Interface principal
st.header("📤 Upload do Arquivo")
uploaded_file = st.file_uploader("Carregue o arquivo CSV", type=['csv'])

if uploaded_file is not None:
    # Carregar dados
    with st.spinner("Processando arquivo..."):
        df = carregar_dados(uploaded_file)
    
    if df is not None:
        st.success(f"✅ Arquivo processado! {len(df)} registros carregados.")
        
        # Mostrar prévia
        with st.expander("📋 Visualizar dados (primeiras 20 linhas)"):
            st.dataframe(df.head(20))
        
        # Filtros na sidebar
        st.sidebar.header("🔍 Filtros")
        
        # Filtro por Projeto
        if 'Projeto' in df.columns:
            projetos = ['Todos'] + sorted([p for p in df['Projeto'].dropna().unique() if isinstance(p, str)])
            projeto_selecionado = st.sidebar.selectbox("Projeto:", projetos)
        else:
            projeto_selecionado = 'Todos'
        
        # Filtro por Valor
        if 'Valor Total' in df.columns:
            valor_min = float(df['Valor Total'].min())
            valor_max = float(df['Valor Total'].max())
            if valor_min < valor_max:
                intervalo = st.sidebar.slider("Valor Total:", valor_min, valor_max, (valor_min, valor_max))
            else:
                intervalo = (valor_min, valor_max)
                st.sidebar.write(f"Valor: R$ {valor_min:,.2f}")
        else:
            intervalo = (0, 0)
        
        # Filtro por Nome
        nome_filtro = st.sidebar.text_input("Nome (parcial):")
        
        # Aplicar filtros
        df_filtrado = df.copy()
        
        if projeto_selecionado != 'Todos' and 'Projeto' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['Projeto'] == projeto_selecionado]
        
        if 'Valor Total' in df_filtrado.columns and intervalo[0] != intervalo[1]:
            df_filtrado = df_filtrado[
                (df_filtrado['Valor Total'] >= intervalo[0]) & 
                (df_filtrado['Valor Total'] <= intervalo[1])
            ]
        
        if nome_filtro and 'Nome' in df_filtrado.columns:
            df_filtrado = df_filtrado[
                df_filtrado['Nome'].astype(str).str.contains(nome_filtro, case=False, na=False)
            ]
        
        # Métricas
        st.header("📊 Métricas")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total de Registros", len(df_filtrado))
            if 'Valor Total' in df_filtrado.columns:
                st.metric("Maior Valor", f"R$ {df_filtrado['Valor Total'].max():,.2f}")
        
        with col2:
            if 'Valor Total' in df_filtrado.columns:
                st.metric("Valor Total", f"R$ {df_filtrado['Valor Total'].sum():,.2f}")
                st.metric("Menor Valor", f"R$ {df_filtrado['Valor Total'].min():,.2f}")
        
        with col3:
            if 'Valor Pagto' in df_filtrado.columns:
                st.metric("Valor Pago", f"R$ {df_filtrado['Valor Pagto'].sum():,.2f}")
        
        with col4:
            if 'Valor Total' in df_filtrado.columns:
                st.metric("Média por Pessoa", f"R$ {df_filtrado['Valor Total'].mean():,.2f}")
        
        # Análise por Projeto
        if 'Projeto' in df_filtrado.columns:
            st.header("📈 Análise por Projeto")
            
            # Estatísticas por projeto
            projeto_stats = df_filtrado.groupby('Projeto').agg({
                'Nome': 'count',
                'Valor Total': ['sum', 'mean', 'min', 'max']
            }).round(2)
            
            # Formatar para exibição
            projeto_display = pd.DataFrame({
                'Quantidade': projeto_stats[('Nome', 'count')],
                'Valor Total': projeto_stats[('Valor Total', 'sum')].apply(lambda x: f"R$ {x:,.2f}"),
                'Média': projeto_stats[('Valor Total', 'mean')].apply(lambda x: f"R$ {x:,.2f}"),
                'Mínimo': projeto_stats[('Valor Total', 'min')].apply(lambda x: f"R$ {x:,.2f}"),
                'Máximo': projeto_stats[('Valor Total', 'max')].apply(lambda x: f"R$ {x:,.2f}")
            })
            
            st.dataframe(projeto_display)
            
            # Gráficos SIMPLIFICADOS - sem histograma problemático
            col_chart1, col_chart2 = st.columns(2)
            
            with col_chart1:
                st.subheader("Quantidade por Projeto")
                contagem = df_filtrado['Projeto'].value_counts()
                st.bar_chart(contagem)
            
            with col_chart2:
                st.subheader("Valor Total por Projeto")
                valor_total = df_filtrado.groupby('Projeto')['Valor Total'].sum()
                st.bar_chart(valor_total)
        
        # Tabela de dados
        st.header("📋 Dados Detalhados")
        
        # Formatar para exibição
        df_display = df_filtrado.copy()
        
        # Formatar colunas
        format_cols = []
        if 'Valor Total' in df_display.columns:
            format_cols.append('Valor Total')
        if 'Valor Pagto' in df_display.columns:
            format_cols.append('Valor Pagto')
        
        for col in format_cols:
            df_display[col] = df_display[col].apply(lambda x: f"R$ {x:,.2f}" if pd.notnull(x) else "")
        
        if 'Data Pagto' in df_display.columns:
            df_display['Data Pagto'] = df_display['Data Pagto'].dt.strftime('%d/%m/%Y')
        
        # Selecionar colunas para exibir
        cols_to_show = []
        for col in ['Nome', 'Projeto', 'Valor Total', 'Valor Pagto', 'Data Pagto']:
            if col in df_display.columns:
                cols_to_show.append(col)
        
        st.dataframe(df_display[cols_to_show])
        
        # Pesquisa específica
        st.header("🔍 Pesquisa Específica")
        
        search_col, search_btn = st.columns([4, 1])
        with search_col:
            search_term = st.text_input("Digite o nome para pesquisa:")
        
        if search_term and 'Nome' in df_filtrado.columns:
            resultados = df_filtrado[
                df_filtrado['Nome'].astype(str).str.contains(search_term, case=False, na=False)
            ]
            
            if len(resultados) > 0:
                st.success(f"Encontrados {len(resultados)} resultados")
                
                # Formatar resultados
                resultados_display = resultados.copy()
                if 'Valor Total' in resultados_display.columns:
                    resultados_display['Valor Total'] = resultados_display['Valor Total'].apply(
                        lambda x: f"R$ {x:,.2f}" if pd.notnull(x) else ""
                    )
                if 'Data Pagto' in resultados_display.columns:
                    resultados_display['Data Pagto'] = resultados_display['Data Pagto'].dt.strftime('%d/%m/%Y')
                
                st.dataframe(resultados_display[cols_to_show])
            else:
                st.warning("Nenhum resultado encontrado")
        
        # Exportação
        st.header("📥 Exportar Dados")
        
        col_csv, col_excel = st.columns(2)
        
        with col_csv:
            csv = df_filtrado.to_csv(index=False, sep=';', decimal=',')
            st.download_button(
                label="📄 Baixar CSV",
                data=csv,
                file_name="dados_filtrados.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col_excel:
            try:
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_filtrado.to_excel(writer, sheet_name='Dados', index=False)
                output.seek(0)
                
                st.download_button(
                    label="📊 Baixar Excel",
                    data=output,
                    file_name="dados_filtrados.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            except:
                st.info("Para exportar em Excel, instale: pip install openpyxl")
        
        # Informações
        with st.expander("📊 Informações do Dataset"):
            st.write(f"**Total de registros:** {len(df)}")
            st.write(f"**Registros após filtros:** {len(df_filtrado)}")
            st.write(f"**Colunas disponíveis:** {', '.join(df.columns.tolist())}")
            
            if 'Data Pagto' in df.columns:
                st.write(f"**Período:** {df['Data Pagto'].min().strftime('%d/%m/%Y')} a {df['Data Pagto'].max().strftime('%d/%m/%Y')}")

else:
    st.info("👆 Faça upload de um arquivo CSV para começar")
    
    st.markdown("""
    ### 📋 Formato esperado:
    - Arquivo CSV com separador ponto-e-vírgula (;)
    - Colunas esperadas: Projeto, Nome, Valor Total, Valor Pagto, Data Pagto
    - Formato de valores: R$ 1.593,90
    - Formato de data: DD/MM/YYYY
    
    ### 🚀 Funcionalidades:
    - Filtros por projeto, valor e nome
    - Métricas em tempo real
    - Análise por projeto
    - Pesquisa de dados
    - Exportação em CSV
    """)

# Rodapé
st.divider()
st.caption("Sistema de Análise de Pagamentos © 2024")
