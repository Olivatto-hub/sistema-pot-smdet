import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import io
import base64
from fpdf import FPDF
import tempfile
import os

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
        self.cell(0, 10, 'RELATÓRIO EXECUTIVO - PROGRAMA OPERAÇÃO TRABALHO', 0, 1, 'C')
        self.set_font('Arial', 'I', 10)
        self.cell(0, 5, f'Data de emissão: {datetime.now().strftime("%d/%m/%Y %H:%M")}', 0, 1, 'C')
        self.ln(10)
    
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')
    
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
            self.cell(col_widths[i], 8, str(cell), 1, 0, 'C')
        self.ln()

def gerar_pdf_executivo(dados, tipo_relatorio):
    """Gera PDF executivo profissional"""
    pdf = PDFReport()
    pdf.add_page()
    
    metrics = processar_dados(dados)
    
    # Capa
    pdf.set_font('Arial', 'B', 20)
    pdf.cell(0, 40, '', 0, 1, 'C')
    pdf.cell(0, 15, 'RELATÓRIO EXECUTIVO', 0, 1, 'C')
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 10, 'PROGRAMA OPERAÇÃO TRABALHO', 0, 1, 'C')
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 10, f'Tipo: {tipo_relatorio}', 0, 1, 'C')
    pdf.cell(0, 10, f'Data: {datetime.now().strftime("%d/%m/%Y")}', 0, 1, 'C')
    pdf.cell(0, 10, 'Secretaria Municipal de Desenvolvimento Econômico, Trabalho e Turismo', 0, 1, 'C')
    
    pdf.add_page()
    
    # Resumo Executivo
    pdf.chapter_title('RESUMO EXECUTIVO')
    
    # Métricas principais
    col_width = 60
    pdf.metric_card('Total de Pagamentos:', f"{metrics.get('total_pagamentos', 0):,}")
    pdf.metric_card('Beneficiários Únicos:', f"{metrics.get('beneficiarios_unicos', 0):,}")
    pdf.metric_card('Projetos Ativos:', f"{metrics.get('projetos_ativos', 0):,}")
    pdf.metric_card('Contas Abertas:', f"{metrics.get('total_contas', 0):,}")
    
    if metrics.get('valor_total', 0) > 0:
        pdf.metric_card('Valor Total Investido:', f"R$ {metrics.get('valor_total', 0):,.2f}")
    
    pdf.ln(10)
    
    # Análise de Projetos
    if not dados['pagamentos'].empty and 'Projeto' in dados['pagamentos'].columns:
        pdf.chapter_title('DISTRIBUIÇÃO POR PROJETO')
        
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
        pdf.chapter_title('ÚLTIMOS PAGAMENTOS REGISTRADOS')
        
        # Selecionar colunas relevantes
        colunas_relevantes = [col for col in ['Data', 'Beneficiário', 'Projeto', 'Valor', 'Status'] 
                             if col in dados['pagamentos'].columns]
        
        if colunas_relevantes:
            dados_exibir = dados['pagamentos'][colunas_relevantes].head(15)
            
            # Ajustar larguras das colunas
            num_cols = len(colunas_relevantes)
            col_widths = [180 // num_cols] * num_cols
            
            # Cabeçalho
            pdf.table_header(colunas_relevantes, col_widths)
            
            # Dados
            for _, row in dados_exibir.iterrows():
                pdf.table_row([str(row[col]) for col in colunas_relevantes], col_widths)
    
    # Análise Temporal
    if not dados['pagamentos'].empty and 'Data' in dados['pagamentos'].columns:
        try:
            pdf.add_page()
            pdf.chapter_title('ANÁLISE TEMPORAL')
            
            dados_pagamentos = dados['pagamentos'].copy()
            dados_pagamentos['Data'] = pd.to_datetime(dados_pagamentos['Data'])
            dados_pagamentos['Mês/Ano'] = dados_pagamentos['Data'].dt.strftime('%m/%Y')
            
            evolucao = dados_pagamentos.groupby('Mês/Ano').size().tail(6)
            
            headers = ['Mês/Ano', 'Pagamentos']
            col_widths = [60, 60]
            pdf.table_header(headers, col_widths)
            
            for mes_ano, quantidade in evolucao.items():
                pdf.table_row([mes_ano, f"{quantidade:,}"], col_widths)
                
        except:
            pass
    
    # Conclusão
    pdf.add_page()
    pdf.chapter_title('CONCLUSÕES E RECOMENDAÇÕES')
    
    pdf.set_font('Arial', '', 12)
    conclusoes = [
        f"• O programa atendeu {metrics.get('beneficiarios_unicos', 0):,} beneficiários únicos",
        f"• Foram realizados {metrics.get('total_pagamentos', 0):,} pagamentos",
        f"• {metrics.get('projetos_ativos', 0)} projetos em operação",
        f"• {metrics.get('total_contas', 0):,} contas bancárias abertas"
    ]
    
    if metrics.get('valor_total', 0) > 0:
        conclusoes.append(f"• Investimento total de R$ {metrics.get('valor_total', 0):,.2f}")
    
    for conclusao in conclusoes:
        pdf.cell(0, 8, conclusao, 0, 1)
    
    pdf.ln(10)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 8, 'Recomendações:', 0, 1)
    pdf.set_font('Arial', '', 11)
    recomendacoes = [
        "• Manter monitoramento contínuo dos projetos",
        "• Expandir para novas regiões da cidade",
        "• Avaliar impacto social do programa",
        "• Otimizar processos de pagamento"
    ]
    
    for recomendacao in recomendacoes:
        pdf.cell(0, 7, recomendacao, 0, 1)
    
    # Salvar PDF em buffer
    pdf_output = io.BytesIO()
    pdf_output.write(pdf.output(dest='S').encode('latin1'))
    pdf_output.seek(0)
    
    return pdf_output

def gerar_relatorio_excel(dados, tipo_relatorio):
    """Gera relatório em Excel"""
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
                'Contas Únicas',
                'Valor Total Investido',
                'Data de Emissão'
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
            'Estatística': [
                'Tipo de Relatório',
                'Total de Registros Processados',
                'Valor Total dos Pagamentos',
                'Média por Beneficiário',
                'Data de Geração',
                'Status do Relatório'
            ],
            'Valor': [
                tipo_relatorio,
                metrics.get('total_pagamentos', 0) + metrics.get('total_contas', 0),
                f"R$ {metrics.get('valor_total', 0):,.2f}" if metrics.get('valor_total', 0) > 0 else "N/A",
                f"R$ {metrics.get('valor_total', 0)/metrics.get('beneficiarios_unicos', 1):,.2f}" if metrics.get('valor_total', 0) > 0 else "N/A",
                datetime.now().strftime('%d/%m/%Y %H:%M'),
                'CONCLUÍDO'
            ]
        })
        estatisticas.to_excel(writer, sheet_name='Estatísticas_Detalhadas', index=False)
    
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
    # ... (mantenha o mesmo código do dashboard que já funciona)
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
    
    # ... (restante do dashboard mantido igual)

def mostrar_importacao():
    # ... (código mantido igual)

def mostrar_consultas(dados):
    # ... (código mantido igual)

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
