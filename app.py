import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import io
import base64
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

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
                    dados['pagamentos']['Valor'] = dados['pagamentos']['Valor'].str.replace('R$', '').str.replace('.', '').str.replace(',', '.').astype(float)
                metrics['valor_total'] = dados['pagamentos']['Valor'].sum()
            except:
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

def gerar_pdf(dados, tipo_relatorio):
    """Gera relatório em PDF"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []
    
    # Título
    title_style = styles['Heading1']
    title_style.alignment = 1  # Centralizado
    title = Paragraph(f"RELATÓRIO POT - {tipo_relatorio.upper()}", title_style)
    story.append(title)
    story.append(Spacer(1, 20))
    
    # Data de emissão
    data_emissao = Paragraph(f"Data de emissão: {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles['Normal'])
    story.append(data_emissao)
    story.append(Spacer(1, 20))
    
    # Métricas
    metrics = processar_dados(dados)
    story.append(Paragraph("RESUMO EXECUTIVO", styles['Heading2']))
    
    dados_metricas = [
        ['Métrica', 'Valor'],
        ['Total de Pagamentos', str(metrics.get('total_pagamentos', 0))],
        ['Beneficiários Únicos', str(metrics.get('beneficiarios_unicos', 0))],
        ['Projetos Ativos', str(metrics.get('projetos_ativos', 0))],
        ['Contas Abertas', str(metrics.get('total_contas', 0))],
        ['Contas Únicas', str(metrics.get('contas_unicas', 0))],
    ]
    
    if metrics.get('valor_total', 0) > 0:
        dados_metricas.insert(2, ['Valor Total', f"R$ {metrics['valor_total']:,.2f}"])
    
    tabela_metricas = Table(dados_metricas)
    tabela_metricas.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(tabela_metricas)
    story.append(Spacer(1, 30))
    
    # Dados de pagamentos (apenas primeiras 20 linhas)
    if not dados['pagamentos'].empty:
        story.append(Paragraph("ÚLTIMOS PAGAMENTOS", styles['Heading2']))
        
        # Selecionar colunas mais importantes
        colunas_pagamentos = [col for col in ['Data', 'Beneficiário', 'CPF', 'Projeto', 'Valor', 'Status'] 
                             if col in dados['pagamentos'].columns]
        if not colunas_pagamentos:
            colunas_pagamentos = dados['pagamentos'].columns[:5].tolist()
        
        dados_tabela = dados['pagamentos'][colunas_pagamentos].head(20)
        
        # Preparar dados para tabela
        tabela_dados = [colunas_pagamentos]  # Cabeçalho
        for _, row in dados_tabela.iterrows():
            tabela_dados.append([str(row[col]) for col in colunas_pagamentos])
        
        tabela = Table(tabela_dados, repeatRows=1)
        tabela.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
        ]))
        story.append(tabela)
        story.append(Spacer(1, 20))
    
    # Rodapé
    story.append(Spacer(1, 30))
    rodape = Paragraph(f"Relatório gerado pelo Sistema POT - SMDET - Página 1", styles['Normal'])
    story.append(rodape)
    
    # Gerar PDF
    doc.build(story)
    buffer.seek(0)
    return buffer

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
                # Implementar busca por período quando os dados estiverem disponíveis
    
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
    **Recursos disponíveis:**
    - Relatórios em Excel para análise detalhada
    - Relatórios em PDF para apresentações
    - Dados consolidados por período
    - Estatísticas e métricas do programa
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
        # Botão para gerar Excel
        if st.button("📊 Gerar Relatório Excel", type="primary", use_container_width=True):
            with st.spinner("Gerando relatório Excel..."):
                # Criar arquivo Excel em memória
                output = io.BytesIO()
                
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    # Sheet de resumo
                    metrics = processar_dados(dados)
                    resumo = pd.DataFrame({
                        'Métrica': [
                            'Total de Pagamentos',
                            'Beneficiários Únicos (Pagamentos)',
                            'Projetos Ativos',
                            'Contas Abertas',
                            'Contas Únicas'
                        ],
                        'Valor': [
                            metrics.get('total_pagamentos', 0),
                            metrics.get('beneficiarios_unicos', 0),
                            metrics.get('projetos_ativos', 0),
                            metrics.get('total_contas', 0),
                            metrics.get('contas_unicas', 0)
                        ]
                    })
                    resumo.to_excel(writer, sheet_name='Resumo', index=False)
                    
                    # Sheets com dados
                    if not dados['pagamentos'].empty:
                        dados['pagamentos'].to_excel(writer, sheet_name='Pagamentos', index=False)
                    
                    if not dados['contas'].empty:
                        dados['contas'].to_excel(writer, sheet_name='Abertura_Contas', index=False)
                
                # Botão de download Excel
                st.success("✅ Relatório Excel gerado com sucesso!")
                
                st.download_button(
                    label="📥 Baixar Relatório Excel",
                    data=output.getvalue(),
                    file_name=f"relatorio_pot_excel_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary"
                )
    
    with col2:
        # Botão para gerar PDF
        if st.button("📄 Gerar Relatório PDF", type="secondary", use_container_width=True):
            with st.spinner("Gerando relatório PDF..."):
                try:
                    pdf_buffer = gerar_pdf(dados, tipo_relatorio)
                    
                    st.success("✅ Relatório PDF gerado com sucesso!")
                    
                    st.download_button(
                        label="📥 Baixar Relatório PDF",
                        data=pdf_buffer.getvalue(),
                        file_name=f"relatorio_pot_pdf_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                        mime="application/pdf",
                        type="primary"
                    )
                except Exception as e:
                    st.error(f"❌ Erro ao gerar PDF: {str(e)}")
                    st.info("💡 **Dica:** Certifique-se de que as bibliotecas PDF estão instaladas")

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
