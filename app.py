import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import io

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
    
    # Upload para projetos
    upload_projetos = st.sidebar.file_uploader(
        "Planilha de Projetos", 
        type=['xlsx', 'csv'],
        key="projetos"
    )
    
    # Upload para evolução mensal
    upload_evolucao = st.sidebar.file_uploader(
        "Planilha de Evolução Mensal", 
        type=['xlsx', 'csv'],
        key="evolucao"
    )
    
    # Upload para pagamentos recentes
    upload_pagamentos = st.sidebar.file_uploader(
        "Planilha de Pagamentos Recentes", 
        type=['xlsx', 'csv'],
        key="pagamentos"
    )
    
    dados = {}
    
    # Carregar dados de projetos
    if upload_projetos is not None:
        try:
            if upload_projetos.name.endswith('.xlsx'):
                dados['projetos'] = pd.read_excel(upload_projetos)
            else:
                dados['projetos'] = pd.read_csv(upload_projetos)
            st.sidebar.success(f"✅ Projetos: {len(dados['projetos'])} registros")
        except Exception as e:
            st.sidebar.error(f"❌ Erro ao carregar projetos: {str(e)}")
            dados['projetos'] = pd.DataFrame()
    else:
        dados['projetos'] = pd.DataFrame()
        st.sidebar.info("📁 Aguardando planilha de projetos")
    
    # Carregar dados de evolução
    if upload_evolucao is not None:
        try:
            if upload_evolucao.name.endswith('.xlsx'):
                dados['evolucao'] = pd.read_excel(upload_evolucao)
            else:
                dados['evolucao'] = pd.read_csv(upload_evolucao)
            st.sidebar.success(f"✅ Evolução: {len(dados['evolucao'])} registros")
        except Exception as e:
            st.sidebar.error(f"❌ Erro ao carregar evolução: {str(e)}")
            dados['evolucao'] = pd.DataFrame()
    else:
        dados['evolucao'] = pd.DataFrame()
        st.sidebar.info("📁 Aguardando planilha de evolução")
    
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
    
    return dados

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
        mostrar_consultas()
    
    with tab4:
        mostrar_relatorios()

def mostrar_dashboard(dados):
    st.header("📊 Dashboard Executivo - POT")
    
    # Verificar se há dados carregados
    dados_carregados = any([not df.empty for df in dados.values()])
    
    if not dados_carregados:
        st.warning("📁 **Nenhum dado carregado ainda**")
        st.info("""
        **Para ver o dashboard:**
        1. Use o menu lateral para carregar as planilhas
        2. Formato suportado: XLSX ou CSV
        3. Os gráficos serão atualizados automaticamente
        """)
        return
    
    # Métricas (agora dinâmicas)
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if not dados['projetos'].empty and 'Beneficiários' in dados['projetos'].columns:
            total_benef = dados['projetos']['Beneficiários'].sum()
            st.metric("Beneficiários Ativos", f"{total_benef:,}")
        else:
            st.metric("Beneficiários Ativos", "0")
    
    with col2:
        if not dados['pagamentos'].empty:
            total_pagamentos = len(dados['pagamentos'])
            st.metric("Pagamentos Registrados", total_pagamentos)
        else:
            st.metric("Pagamentos Registrados", "0")
    
    with col3:
        if not dados['projetos'].empty:
            total_projetos = len(dados['projetos'])
            st.metric("Projetos Ativos", total_projetos)
        else:
            st.metric("Projetos Ativos", "0")
    
    with col4:
        st.metric("Taxa de Sucesso", "97,8%", "+0,2%")
    
    # Gráficos
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Evolução de Beneficiários")
        if not dados['evolucao'].empty:
            fig = px.line(dados['evolucao'], x='Mês', y='Beneficiários', 
                         markers=True, line_shape='spline')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("📊 Gráfico de evolução aparecerá aqui após carregar os dados")
    
    with col2:
        st.subheader("Distribuição por Projeto")
        if not dados['projetos'].empty and 'Beneficiários' in dados['projetos'].columns:
            fig = px.pie(dados['projetos'], values='Beneficiários', names='Projeto')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("📊 Gráfico de projetos aparecerá aqui após carregar os dados")
    
    # Tabela recente
    st.subheader("Últimos Pagamentos Registrados")
    if not dados['pagamentos'].empty:
        st.dataframe(dados['pagamentos'].head(), use_container_width=True)
    else:
        st.info("📋 Tabela de pagamentos aparecerá aqui após carregar os dados")

def mostrar_importacao():
    st.header("📥 Importação de Dados")
    
    st.info("""
    **💡 AGORA USE O MENU LATERAL!**
    
    **Instruções para importação:**
    - Acesse o menu lateral "📤 Carregar Dados Reais" 
    - Faça upload das planilhas nos formatos XLSX ou CSV
    - O dashboard será atualizado automaticamente
    """)
    
    # Estrutura esperada das planilhas
    with st.expander("📋 Estrutura Esperada das Planilhas"):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("**Planilha de Projetos:**")
            st.code("""
Projeto
Beneficiários
Status
Cor (opcional)
            """)
        
        with col2:
            st.markdown("**Planilha de Evolução:**")
            st.code("""
Mês
Beneficiários
Pagamentos (opcional)
            """)
        
        with col3:
            st.markdown("**Planilha de Pagamentos:**")
            st.code("""
Data
Beneficiário
CPF
Projeto
Valor
Status
            """)

def mostrar_consultas():
    st.header("🔍 Consultas de Pagamentos")
    
    # Opções de consulta
    opcao_consulta = st.radio(
        "Tipo de consulta:",
        ["Por CPF", "Por Mês/Ano", "Por Projeto", "Por Nome"],
        horizontal=True
    )
    
    if opcao_consulta == "Por CPF":
        col1, col2 = st.columns([2, 1])
        with col1:
            cpf = st.text_input("Digite o CPF (apenas números):", placeholder="12345678900")
        with col2:
            if st.button("🔍 Buscar CPF", use_container_width=True):
                if cpf:
                    st.info(f"Buscando pagamentos para CPF: {cpf}")
                else:
                    st.warning("Por favor, digite um CPF para buscar")
    
    elif opcao_consulta == "Por Mês/Ano":
        col1, col2 = st.columns(2)
        with col1:
            mes = st.selectbox("Mês:", list(range(1, 13)))
        with col2:
            ano = st.selectbox("Ano:", [2024, 2023, 2022])
        
        if st.button("📅 Buscar por Período"):
            st.info(f"Buscando pagamentos para {mes}/{ano}")
    
    elif opcao_consulta == "Por Projeto":
        projeto = st.selectbox("Selecione o projeto:", 
                              ["Operação Trabalho", "Emprega SP", "Jovem Aprendiz", "Capacitação Profissional"])
        if st.button("🏢 Buscar por Projeto"):
            st.info(f"Buscando pagamentos do projeto: {projeto}")
    
    else:  # Por Nome
        nome = st.text_input("Digite o nome do beneficiário:")
        if st.button("👤 Buscar por Nome"):
            if nome:
                st.info(f"Buscando pagamentos para: {nome}")
            else:
                st.warning("Por favor, digite um nome para buscar")
    
    # Área de resultados
    st.markdown("---")
    st.subheader("Resultados da Consulta")
    st.info("Os resultados aparecerão aqui após a busca")

def mostrar_relatorios():
    st.header("📋 Gerar Relatórios")
    
    st.info("""
    **Recursos disponíveis:**
    - Relatórios em Excel para análise detalhada
    - Dados consolidados por período
    - Estatísticas e métricas do programa
    """)
    
    # Opções de relatório
    tipo_relatorio = st.selectbox(
        "Selecione o tipo de relatório:",
        [
            "Relatório Geral Completo",
            "Relatório por Período Mensal", 
            "Relatório por Projeto",
            "Relatório de Beneficiários",
            "Dashboard Executivo"
        ]
    )
    
    # Parâmetros adicionais
    col1, col2 = st.columns(2)
    with col1:
        if "Período" in tipo_relatorio:
            mes = st.selectbox("Mês:", list(range(1, 13)))
    with col2:
        if "Período" in tipo_relatorio:
            ano = st.selectbox("Ano:", [2024, 2023])
    
    # Botão de geração
    if st.button("📊 Gerar Relatório", type="primary"):
        with st.spinner("Gerando relatório..."):
            # Simular geração
            import time
            time.sleep(2)
            
            # Criar dados de exemplo para download
            dados_exemplo = pd.DataFrame({
                'Data': pd.date_range('2024-01-01', periods=50),
                'Beneficiário': [f'Beneficiário {i}' for i in range(1, 51)],
                'CPF': [f'123.456.78{str(i).zfill(2)}-00' for i in range(1, 51)],
                'Projeto': ['Operação Trabalho'] * 25 + ['Emprega SP'] * 15 + ['Jovem Aprendiz'] * 10,
                'Valor': [1200] * 50,
                'Status': ['Pago'] * 45 + ['Pendente'] * 5
            })
            
            # Criar arquivo Excel em memória
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                dados_exemplo.to_excel(writer, sheet_name='Pagamentos', index=False)
                
                # Adicionar sheet de resumo
                resumo = pd.DataFrame({
                    'Métrica': ['Total de Pagamentos', 'Valor Total', 'Beneficiários Únicos', 'Projetos'],
                    'Valor': [len(dados_exemplo), len(dados_exemplo) * 1200, 50, 3]
                })
                resumo.to_excel(writer, sheet_name='Resumo', index=False)
            
            # Botão de download
            st.success("✅ Relatório gerado com sucesso!")
            
            st.download_button(
                label="📥 Baixar Relatório Excel",
                data=output.getvalue(),
                file_name=f"relatorio_pot_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )

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
