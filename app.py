import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import io
from fpdf import FPDF

# Configuração da página
st.set_page_config(
    page_title="Sistema POT - SMDET",
    page_icon="🏛️",
    layout="wide"
)

# Sistema de autenticação simples
def autenticar():
    st.sidebar.title("Sistema POT - SMDET")
    email = st.sidebar.text_input("Email @prefeitura.sp.gov.br")
    
    if email and not email.endswith('@prefeitura.sp.gov.br'):
        st.error("🚫 Acesso restrito aos servidores da Prefeitura de São Paulo")
        st.stop()
    
    return email

# Sistema de upload de dados
def carregar_dados():
    st.sidebar.header("📤 Carregar Dados Reais")
    
    # Upload para pagamentos
    upload_pagamentos = st.sidebar.file_uploader(
        "Planilha de Pagamentos", 
        type=['xlsx', 'csv'],
        key="pagamentos"
    )
    
    # Upload para abertura de contas
    upload_contas = st.sidebar.file_uploader(
        "Planilha de Abertura de Contas", 
        type=['xlsx', 'csv'],
        key="contas"
    )
    
    dados = {}
    
    # Carregar dados de pagamentos
    if upload_pagamentos is not None:
        try:
            if upload_pagamentos.name.endswith('.xlsx'):
                dados['pagamentos'] = pd.read_excel(upload_pagamentos)
            else:
                dados['pagamentos'] = pd.read_csv(upload_pagamentos)
            st.sidebar.success(f"✅ Pagamentos: {len(dados['pagamentos'])} registros")
        except Exception as e:
            st.sidebar.error(f"❌ Erro ao carregar pagamentos: {str(e)}")
            dados['pagamentos'] = pd.DataFrame()
    else:
        dados['pagamentos'] = pd.DataFrame()
        st.sidebar.info("📁 Aguardando planilha de pagamentos")
    
    # Carregar dados de abertura de contas
    if upload_contas is not None:
        try:
            if upload_contas.name.endswith('.xlsx'):
                dados['contas'] = pd.read_excel(upload_contas)
            else:
                dados['contas'] = pd.read_csv(upload_contas)
            st.sidebar.success(f"✅ Contas: {len(dados['contas'])} registros")
        except Exception as e:
            st.sidebar.error(f"❌ Erro ao carregar contas: {str(e)}")
            dados['contas'] = pd.DataFrame()
    else:
        dados['contas'] = pd.DataFrame()
        st.sidebar.info("📁 Aguardando planilha de abertura de contas")
    
    return dados

def processar_dados(dados):
    """Processa os dados para o dashboard"""
    metrics = {}
    
    # Métricas básicas
    if not dados['pagamentos'].empty:
        metrics['total_pagamentos'] = len(dados['pagamentos'])
        if 'Valor' in dados['pagamentos'].columns:
            # Tentar converter para numérico se for string
            try:
                if dados['pagamentos']['Valor'].dtype == 'object':
                    # Remover R$, pontos e converter vírgula para ponto
                    dados['pagamentos']['Valor_Limpo'] = (
                        dados['pagamentos']['Valor']
                        .astype(str)
                        .str.replace('R$', '')
                        .str.replace('.', '')
                        .str.replace(',', '.')
                        .str.replace(' ', '')
                        .astype(float)
                    )
                    metrics['valor_total'] = dados['pagamentos']['Valor_Limpo'].sum()
                else:
                    metrics['valor_total'] = dados['pagamentos']['Valor'].sum()
            except Exception as e:
                metrics['valor_total'] = 0
        else:
            metrics['valor_total'] = 0
        
        if 'Projeto' in dados['pagamentos'].columns:
            metrics['projetos_ativos'] = dados['pagamentos']['Projeto'].nunique()
        else:
            metrics['projetos_ativos'] = 0
            
        if 'CPF' in dados['pagamentos'].columns:
            metrics['beneficiarios_unicos'] = dados['pagamentos']['CPF'].nunique()
        else:
            metrics['beneficiarios_unicos'] = 0
    
    if not dados['contas'].empty:
        metrics['total_contas'] = len(dados['contas'])
        if 'CPF' in dados['contas'].columns:
            metrics['contas_unicas'] = dados['contas']['CPF'].nunique()
        else:
            metrics['contas_unicas'] = 0
    
    return metrics

class PDFReport(FPDF):
    def header(self):
        # Logo ou título
        self.set_font('Arial', 'B', 16)
        self.cell(0, 10, 'RELATORIO EXECUTIVO - PROGRAMA OPERACAO TRABALHO', 0, 1, 'C')
        self.set_font('Arial', 'I', 10)
        self.cell(0, 5, f'Data de emissao: {datetime.now().strftime("%d/%m/%Y %H:%M")}', 0, 1, 'C')
        self.ln(10)
    
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Pagina {self.page_no()}', 0, 0, 'C')
    
    def chapter_title(self, title):
        self.set_font('Arial', 'B', 14)
        self.set_fill_color(200, 220, 255)
        self.cell(0, 10, title, 0, 1, 'L', 1)
        self.ln(4)
    
    def metric_card(self, label, value, width=45):
        self.set_font('Arial', 'B', 12)
        self.cell(width, 8, label, 0, 0, 'L')
        self.set_font('Arial', '', 12)
        self.cell(0, 8, str(value), 0, 1, 'R')
    
    def table_header(self, headers, col_widths):
        self.set_font('Arial', 'B', 10)
        self.set_fill_color(180, 200, 255)
        for i, header in enumerate(headers):
            self.cell(col_widths[i], 8, header, 1, 0, 'C', 1)
        self.ln()
    
    def table_row(self, data, col_widths):
        self.set_font('Arial', '', 9)
        for i, cell in enumerate(data):
            # Limpar caracteres especiais
            cell_text = str(cell).replace('•', '-').replace('´', "'").replace('`', "'")
            self.cell(col_widths[i], 8, cell_text, 1, 0, 'C')
        self.ln()
    
    def safe_text(self, text):
        """Remove caracteres problemáticos para Latin-1"""
        problematic_chars = {
            '•': '-', '´': "'", '`': "'", '“': '"', '”': '"', 
            '‘': "'", '’': "'", '–': '-', '—': '-', '…': '...'
        }
        safe_text = str(text)
        for char, replacement in problematic_chars.items():
            safe_text = safe_text.replace(char, replacement)
        return safe_text

def gerar_pdf_executivo(dados, tipo_relatorio):
    """Gera PDF executivo profissional"""
    pdf = PDFReport()
    pdf.add_page()
    
    metrics = processar_dados(dados)
    
    # Capa
    pdf.set_font('Arial', 'B', 20)
    pdf.cell(0, 40, '', 0, 1, 'C')
    pdf.cell(0, 15, 'RELATORIO EXECUTIVO', 0, 1, 'C')
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 10, 'PROGRAMA OPERACAO TRABALHO', 0, 1, 'C')
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 10, f'Tipo: {tipo_relatorio}', 0, 1, 'C')
    pdf.cell(0, 10, f'Data: {datetime.now().strftime("%d/%m/%Y")}', 0, 1, 'C')
    pdf.cell(0, 10, 'Secretaria Municipal de Desenvolvimento Economico, Trabalho e Turismo', 0, 1, 'C')
    
    pdf.add_page()
    
    # Resumo Executivo
    pdf.chapter_title('RESUMO EXECUTIVO')
    
    # Métricas principais
    col_width = 60
    pdf.metric_card('Total de Pagamentos:', f"{metrics.get('total_pagamentos', 0):,}")
    pdf.metric_card('Beneficiarios Unicos:', f"{metrics.get('beneficiarios_unicos', 0):,}")
    pdf.metric_card('Projetos Ativos:', f"{metrics.get('projetos_ativos', 0):,}")
    pdf.metric_card('Contas Abertas:', f"{metrics.get('total_contas', 0):,}")
    
    if metrics.get('valor_total', 0) > 0:
        pdf.metric_card('Valor Total Investido:', f"R$ {metrics.get('valor_total', 0):,.2f}")
    
    pdf.ln(10)
    
    # Análise de Projetos
    if not dados['pagamentos'].empty and 'Projeto' in dados['pagamentos'].columns:
        pdf.chapter_title('DISTRIBUICAO POR PROJETO')
        
        projetos_count = dados['pagamentos']['Projeto'].value_counts().head(10)
        
        # Cabeçalho da tabela
        headers = ['Projeto', 'Quantidade', '% do Total']
        col_widths = [80, 40, 40]
        pdf.table_header(headers, col_widths)
        
        # Dados da tabela
        total = projetos_count.sum()
        for projeto, quantidade in projetos_count.items():
            percentual = (quantidade / total) * 100
            pdf.table_row([projeto, f"{quantidade:,}", f"{percentual:.1f}%"], col_widths)
    
    # Últimos Pagamentos
    if not dados['pagamentos'].empty:
        pdf.add_page()
        pdf.chapter_title('ULTIMOS PAGAMENTOS REGISTRADOS')
        
        # Selecionar colunas relevantes
        colunas_relevantes = [col for col in ['Data', 'Beneficiario', 'Projeto', 'Valor', 'Status'] 
                             if col in dados['pagamentos'].columns]
        
        if not colunas_relevantes:
            colunas_relevantes = dados['pagamentos'].columns[:4].tolist()
        
        dados_exibir = dados['pagamentos'][colunas_relevantes].head(15)
        
        # Ajustar larguras das colunas
        num_cols = len(colunas_relevantes)
        col_width = 180 // num_cols
        col_widths = [col_width] * num_cols
        
        # Cabeçalho
        pdf.table_header(colunas_relevantes, col_widths)
        
        # Dados
        for _, row in dados_exibir.iterrows():
            row_data = []
            for col in colunas_relevantes:
                cell_value = str(row[col]) if pd.notna(row[col]) else ""
                # Limpar caracteres especiais
                cell_value = pdf.safe_text(cell_value)
                row_data.append(cell_value)
            pdf.table_row(row_data, col_widths)
    
    # Análise Temporal
    if not dados['pagamentos'].empty and 'Data' in dados['pagamentos'].columns:
        try:
            pdf.add_page()
            pdf.chapter_title('ANALISE TEMPORAL')
            
            dados_pagamentos = dados['pagamentos'].copy()
            dados_pagamentos['Data'] = pd.to_datetime(dados_pagamentos['Data'])
            dados_pagamentos['Mes/Ano'] = dados_pagamentos['Data'].dt.strftime('%m/%Y')
            
            evolucao = dados_pagamentos.groupby('Mes/Ano').size().tail(6)
            
            headers = ['Mes/Ano', 'Pagamentos']
            col_widths = [60, 60]
            pdf.table_header(headers, col_widths)
            
            for mes_ano, quantidade in evolucao.items():
                pdf.table_row([mes_ano, f"{quantidade:,}"], col_widths)
                
        except Exception as e:
            # Ignora erro na análise temporal
            pass
    
    # Conclusão
    pdf.add_page()
    pdf.chapter_title('CONCLUSOES E RECOMENDACOES')
    
    pdf.set_font('Arial', '', 12)
    conclusoes = [
        f"- O programa atendeu {metrics.get('beneficiarios_unicos', 0):,} beneficiarios unicos",
        f"- Foram realizados {metrics.get('total_pagamentos', 0):,} pagamentos",
        f"- {metrics.get('projetos_ativos', 0)} projetos em operacao",
        f"- {metrics.get('total_contas', 0):,} contas bancarias abertas"
    ]
    
    if metrics.get('valor_total', 0) > 0:
        conclusoes.append(f"- Investimento total de R$ {metrics.get('valor_total', 0):,.2f}")
    
    for conclusao in conclusoes:
        pdf.cell(0, 8, pdf.safe_text(conclusao), 0, 1)
    
    pdf.ln(10)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 8, 'Recomendacoes:', 0, 1)
    pdf.set_font('Arial', '', 11)
    recomendacoes = [
        "- Manter monitoramento continuo dos projetos",
        "- Expandir para novas regioes da cidade",
        "- Avaliar impacto social do programa",
        "- Otimizar processos de pagamento"
    ]
    
    for recomendacao in recomendacoes:
        pdf.cell(0, 7, pdf.safe_text(recomendacao), 0, 1)
    
    # Salvar PDF em buffer
    pdf_output = io.BytesIO()
    pdf_bytes = pdf.output(dest='S').encode('latin1', 'replace')
    pdf_output.write(pdf_bytes)
    pdf_output.seek(0)
    
    return pdf_output

def gerar_relatorio_excel(dados, tipo_relatorio):
    """Gera relatório em Excel"""
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Sheet de resumo
        metrics = processar_dados(dados)
        resumo = pd.DataFrame({
            'Metrica': [
                'Total de Pagamentos',
                'Beneficiarios Unicos (Pagamentos)',
                'Projetos Ativos',
                'Contas Abertas',
                'Contas Unicas',
                'Valor Total Investido',
                'Data de Emissao'
            ],
            'Valor': [
                metrics.get('total_pagamentos', 0),
                metrics.get('beneficiarios_unicos', 0),
                metrics.get('projetos_ativos', 0),
                metrics.get('total_contas', 0),
                metrics.get('contas_unicas', 0),
                f"R$ {metrics.get('valor_total', 0):,.2f}" if metrics.get('valor_total', 0) > 0 else "N/A",
                datetime.now().strftime('%d/%m/%Y %H:%M')
            ]
        })
        resumo.to_excel(writer, sheet_name='Resumo Executivo', index=False)
        
        # Sheets com dados completos
        if not dados['pagamentos'].empty:
            dados['pagamentos'].to_excel(writer, sheet_name='Pagamentos_Completo', index=False)
        
        if not dados['contas'].empty:
            dados['contas'].to_excel(writer, sheet_name='Abertura_Contas_Completo', index=False)
        
        # Sheet de estatísticas detalhadas
        estatisticas = pd.DataFrame({
            'Estatistica': [
                'Tipo de Relatorio',
                'Total de Registros Processados',
                'Valor Total dos Pagamentos',
                'Media por Beneficiario',
                'Data de Geracao',
                'Status do Relatorio'
            ],
            'Valor': [
                tipo_relatorio,
                metrics.get('total_pagamentos', 0) + metrics.get('total_contas', 0),
                f"R$ {metrics.get('valor_total', 0):,.2f}" if metrics.get('valor_total', 0) > 0 else "N/A",
                f"R$ {metrics.get('valor_total', 0)/metrics.get('beneficiarios_unicos', 1):,.2f}" if metrics.get('valor_total', 0) > 0 else "N/A",
                datetime.now().strftime('%d/%m/%Y %H:%M'),
                'CONCLUIDO'
            ]
        })
        estatisticas.to_excel(writer, sheet_name='Estatisticas_Detalhadas', index=False)
    
    output.seek(0)
    return output

def main():
    email = autenticar()
    
    if not email:
        st.info("👆 Informe seu email institucional para acessar o sistema")
        return
    
    st.success(f"✅ Acesso permitido: {email}")
    
    # Carregar dados
    dados = carregar_dados()
    
    # Menu principal
    st.title("🏛️ Sistema POT - Programa Operação Trabalho")
    st.markdown("Desenvolvido para Secretaria Municipal de Desenvolvimento Econômico, Trabalho e Turismo")
    st.markdown("---")
    
    # Abas
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Dashboard", 
        "📥 Importar Dados", 
        "🔍 Consultas", 
        "📋 Relatórios"
    ])
    
    with tab1:
        mostrar_dashboard(dados)
    
    with tab2:
        mostrar_importacao()
    
    with tab3:
        mostrar_consultas(dados)
    
    with tab4:
        mostrar_relatorios(dados)

def mostrar_dashboard(dados):
    st.header("📊 Dashboard Executivo - POT")
    
    # Processar dados
    metrics = processar_dados(dados)
    
    # Verificar se há dados carregados
    dados_carregados = any([not df.empty for df in dados.values()])
    
    if not dados_carregados:
        st.warning("📁 **Nenhum dado carregado ainda**")
        st.info("""
        **Para ver o dashboard:**
        1. Use o menu lateral para carregar as planilhas de Pagamentos e Abertura de Contas
        2. Formato suportado: XLSX ou CSV
        3. Os gráficos serão atualizados automaticamente
        """)
        return
    
    # Métricas
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Beneficiários Únicos", metrics.get('beneficiarios_unicos', 0))
    
    with col2:
        st.metric("Total de Pagamentos", metrics.get('total_pagamentos', 0))
    
    with col3:
        st.metric("Contas Abertas", metrics.get('total_contas', 0))
    
    with col4:
        st.metric("Projetos Ativos", metrics.get('projetos_ativos', 0))
    
    # Valor total se disponível
    if metrics.get('valor_total', 0) > 0:
        st.metric("Valor Total dos Pagamentos", f"R$ {metrics['valor_total']:,.2f}")
    
    # Gráficos
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Distribuição por Projeto (Pagamentos)")
        if not dados['pagamentos'].empty and 'Projeto' in dados['pagamentos'].columns:
            projetos_count = dados['pagamentos']['Projeto'].value_counts().reset_index()
            projetos_count.columns = ['Projeto', 'Quantidade']
            
            fig = px.pie(projetos_count, values='Quantidade', names='Projeto',
                        title="Pagamentos por Projeto")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("📊 Gráfico de projetos aparecerá aqui após carregar os dados de pagamentos")
    
    with col2:
        st.subheader("Evolução Mensal de Pagamentos")
        if not dados['pagamentos'].empty and 'Data' in dados['pagamentos'].columns:
            try:
                # Tentar converter para data
                dados_pagamentos = dados['pagamentos'].copy()
                dados_pagamentos['Data'] = pd.to_datetime(dados_pagamentos['Data'])
                dados_pagamentos['Mês'] = dados_pagamentos['Data'].dt.to_period('M').astype(str)
                
                evolucao = dados_pagamentos.groupby('Mês').size().reset_index()
                evolucao.columns = ['Mês', 'Pagamentos']
                
                fig = px.line(evolucao, x='Mês', y='Pagamentos', 
                             markers=True, line_shape='spline',
                             title="Evolução de Pagamentos por Mês")
                st.plotly_chart(fig, use_container_width=True)
            except:
                st.info("📊 Formato de data não reconhecido. Ajuste a coluna 'Data'")
        else:
            st.info("📊 Gráfico de evolução aparecerá aqui após carregar os dados")
    
    # Tabelas recentes
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Últimos Pagamentos")
        if not dados['pagamentos'].empty:
            # Mostrar colunas mais relevantes
            colunas_pagamentos = [col for col in ['Data', 'Beneficiário', 'CPF', 'Projeto', 'Valor', 'Status'] 
                                if col in dados['pagamentos'].columns]
            if colunas_pagamentos:
                st.dataframe(dados['pagamentos'][colunas_pagamentos].head(10), use_container_width=True)
            else:
                st.dataframe(dados['pagamentos'].head(10), use_container_width=True)
        else:
            st.info("📋 Tabela de pagamentos aparecerá aqui")
    
    with col2:
        st.subheader("Últimas Contas Abertas")
        if not dados['contas'].empty:
            # Mostrar colunas mais relevantes
            colunas_contas = [col for col in ['Data', 'Nome', 'CPF', 'Projeto', 'Agência'] 
                            if col in dados['contas'].columns]
            if colunas_contas:
                st.dataframe(dados['contas'][colunas_contas].head(10), use_container_width=True)
            else:
                st.dataframe(dados['contas'].head(10), use_container_width=True)
        else:
            st.info("📋 Tabela de contas aparecerá aqui")

def mostrar_importacao():
    st.header("📥 Estrutura das Planilhas")
    
    st.info("""
    **💡 USE O MENU LATERAL PARA CARREGAR AS PLANILHAS!**
    """)
    
    # Estrutura esperada das planilhas
    with st.expander("📋 Estrutura das Planilhas Necessárias"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**📋 Planilha de Pagamentos:**")
            st.code("""
Data (dd/mm/aaaa)
Beneficiário (texto)
CPF (número)
Projeto (texto)
Valor (número)
Status (texto)
*Outras colunas opcionais*
            """)
        
        with col2:
            st.markdown("**🏦 Planilha de Abertura de Contas:**")
            st.code("""
Data (dd/mm/aaaa)
Nome (texto)
CPF (número)
Projeto (texto)
Agência (texto/número)
*Outras colunas opcionais*
            """)

def mostrar_consultas(dados):
    st.header("🔍 Consultas de Dados")
    
    # Opções de consulta
    opcao_consulta = st.radio(
        "Tipo de consulta:",
        ["Por CPF", "Por Projeto", "Por Período"],
        horizontal=True
    )
    
    if opcao_consulta == "Por CPF":
        col1, col2 = st.columns([2, 1])
        with col1:
            cpf = st.text_input("Digite o CPF (apenas números):", placeholder="12345678900")
        with col2:
            if st.button("🔍 Buscar CPF", use_container_width=True):
                if cpf:
                    resultados = {}
                    if not dados['pagamentos'].empty and 'CPF' in dados['pagamentos'].columns:
                        resultados['pagamentos'] = dados['pagamentos'][dados['pagamentos']['CPF'].astype(str).str.contains(cpf)]
                    if not dados['contas'].empty and 'CPF' in dados['contas'].columns:
                        resultados['contas'] = dados['contas'][dados['contas']['CPF'].astype(str).str.contains(cpf)]
                    
                    st.session_state.resultados_consulta = resultados
                else:
                    st.warning("Por favor, digite um CPF para buscar")
    
    elif opcao_consulta == "Por Projeto":
        projeto = st.text_input("Digite o nome do projeto:")
        if st.button("🏢 Buscar por Projeto"):
            if projeto:
                resultados = {}
                if not dados['pagamentos'].empty and 'Projeto' in dados['pagamentos'].columns:
                    resultados['pagamentos'] = dados['pagamentos'][dados['pagamentos']['Projeto'].str.contains(projeto, case=False, na=False)]
                if not dados['contas'].empty and 'Projeto' in dados['contas'].columns:
                    resultados['contas'] = dados['contas'][dados['contas']['Projeto'].str.contains(projeto, case=False, na=False)]
                
                st.session_state.resultados_consulta = resultados
            else:
                st.warning("Por favor, digite um projeto para buscar")
    
    else:  # Por Período
        col1, col2 = st.columns(2)
        with col1:
            data_inicio = st.date_input("Data início:")
        with col2:
            data_fim = st.date_input("Data fim:")
        
        if st.button("📅 Buscar por Período"):
            if data_inicio and data_fim:
                st.info(f"Buscando dados de {data_inicio} a {data_fim}")
    
    # Área de resultados
    st.markdown("---")
    st.subheader("Resultados da Consulta")
    
    if 'resultados_consulta' in st.session_state:
        resultados = st.session_state.resultados_consulta
        
        if resultados.get('pagamentos') is not None and not resultados['pagamentos'].empty:
            st.markdown("**📋 Pagamentos Encontrados:**")
            st.dataframe(resultados['pagamentos'], use_container_width=True)
        
        if resultados.get('contas') is not None and not resultados['contas'].empty:
            st.markdown("**🏦 Contas Encontradas:**")
            st.dataframe(resultados['contas'], use_container_width=True)
        
        if not any([not df.empty if df is not None else False for df in resultados.values()]):
            st.info("Nenhum resultado encontrado para a consulta.")
    else:
        st.info("Os resultados aparecerão aqui após a busca")

def mostrar_relatorios(dados):
    st.header("📋 Gerar Relatórios")
    
    st.info("""
    **Escolha o formato do relatório:**
    - **📄 PDF Executivo**: Relatório visual e profissional para apresentações
    - **📊 Excel Completo**: Dados detalhados para análise técnica
    """)
    
    # Opções de relatório
    tipo_relatorio = st.selectbox(
        "Selecione o tipo de relatório:",
        [
            "Relatório Geral Completo",
            "Relatório de Pagamentos", 
            "Relatório de Abertura de Contas",
            "Relatório por Projeto",
            "Dashboard Executivo"
        ]
    )
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Botão para gerar PDF Executivo
        if st.button("📄 Gerar PDF Executivo", type="primary", use_container_width=True):
            with st.spinner("Gerando relatório PDF executivo..."):
                try:
                    pdf_buffer = gerar_pdf_executivo(dados, tipo_relatorio)
                    
                    st.success("✅ PDF Executivo gerado com sucesso!")
                    st.info("💡 **Ideal para:** Apresentações, reuniões e análise executiva")
                    
                    st.download_button(
                        label="📥 Baixar PDF Executivo",
                        data=pdf_buffer.getvalue(),
                        file_name=f"relatorio_executivo_pot_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                        mime="application/pdf",
                        type="primary"
                    )
                except Exception as e:
                    st.error(f"❌ Erro ao gerar PDF: {str(e)}")
    
    with col2:
        # Botão para gerar Excel
        if st.button("📊 Gerar Excel Completo", type="secondary", use_container_width=True):
            with st.spinner("Gerando relatório Excel completo..."):
                try:
                    excel_buffer = gerar_relatorio_excel(dados, tipo_relatorio)
                    
                    st.success("✅ Excel Completo gerado com sucesso!")
                    st.info("💡 **Ideal para:** Análise detalhada e processamento de dados")
                    
                    st.download_button(
                        label="📥 Baixar Excel Completo",
                        data=excel_buffer.getvalue(),
                        file_name=f"relatorio_completo_pot_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary"
                    )
                except Exception as e:
                    st.error(f"❌ Erro ao gerar Excel: {str(e)}")

# Rodapé
def mostrar_rodape():
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**SMDET**")
        st.markdown("Secretaria Municipal de Desenvolvimento Econômico, Trabalho e Turismo")
    
    with col2:
        st.markdown("**Suporte Técnico**")
        st.markdown("rolivatto@prefeitura.sp.gov.br")
    
    with col3:
        st.markdown("**Versão**")
        st.markdown("1.0 - Novembro 2024")

if __name__ == "__main__":
    main()
    mostrar_rodape()
