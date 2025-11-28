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

def main():
    email = autenticar()
    
    if not email:
        st.info("👆 Informe seu email institucional para acessar o sistema")
        return
    
    st.success(f"✅ Acesso permitido: {email}")
    
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
        mostrar_dashboard()
    
    with tab2:
        mostrar_importacao()
    
    with tab3:
        mostrar_consultas()
    
    with tab4:
        mostrar_relatorios()

def mostrar_dashboard():
    st.header("📊 Dashboard Executivo - POT")
    
    # Métricas
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Beneficiários Ativos", "2.847", "+12%")
    with col2:
        st.metric("Pagamentos Mensais", "R$ 4,2M", "+8%")
    with col3:
        st.metric("Projetos Ativos", "36", "+3")
    with col4:
        st.metric("Taxa de Sucesso", "97,8%", "+0,2%")
    
    # Gráficos
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Evolução de Beneficiários")
        dados_evolucao = pd.DataFrame({
            'Mês': ['Jan/24', 'Fev/24', 'Mar/24', 'Abr/24', 'Mai/24', 'Jun/24'],
            'Beneficiários': [2200, 2350, 2480, 2620, 2750, 2847],
            'Pagamentos': [1200, 1500, 1800, 2100, 2400, 2847]
        })
        
        fig = px.line(dados_evolucao, x='Mês', y='Beneficiários', 
                     markers=True, line_shape='spline')
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("Distribuição por Projeto")
        dados_projetos = pd.DataFrame({
            'Projeto': ['Operação Trabalho', 'Emprega SP', 'Jovem Aprendiz', 'Capacitação Profissional'],
            'Beneficiários': [1500, 800, 400, 147],
            'Cor': ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D']
        })
        
        fig = px.pie(dados_projetos, values='Beneficiários', names='Projeto',
                    color='Cor', color_discrete_map='identity')
        st.plotly_chart(fig, use_container_width=True)
    
    # Tabela recente
    st.subheader("Últimos Pagamentos Registrados")
    dados_recentes = pd.DataFrame({
        'Data': ['25/11/2024', '24/11/2024', '23/11/2024', '22/11/2024'],
        'Beneficiário': ['Maria Silva Santos', 'João Oliveira Costa', 'Ana Pereira Lima', 'Pedro Almeida Souza'],
        'CPF': ['123.456.789-00', '234.567.890-11', '345.678.901-22', '456.789.012-33'],
        'Projeto': ['Operação Trabalho', 'Emprega SP', 'Operação Trabalho', 'Jovem Aprendiz'],
        'Valor': ['R$ 1.200,00', 'R$ 1.200,00', 'R$ 1.200,00', 'R$ 980,00'],
        'Status': ['✅ Pago', '✅ Pago', '⏳ Pendente', '✅ Pago']
    })
    
    st.dataframe(dados_recentes, use_container_width=True)

def mostrar_importacao():
    st.header("📥 Importação de Dados")
    
    st.info("""
    **Instruções para importação:**
    - A planilha deve estar nos formatos XLSX ou XLS
    - Colunas obrigatórias: Nome, CPF, DataNasc, Data Pagto, Num Cartao, Projeto, Agência
    - Certifique-se que os dados estejam formatados corretamente
    """)
    
    uploaded_file = st.file_uploader(
        "Selecione a planilha de pagamentos", 
        type=['xlsx', 'xls'],
        help="Arraste o arquivo ou clique para procurar"
    )
    
    if uploaded_file is not None:
        try:
            # Ler a planilha
            df = pd.read_excel(uploaded_file)
            
            st.success(f"✅ Arquivo carregado com sucesso!")
            st.success(f"📊 **{len(df)} registros** encontrados no arquivo")
            
            # Mostrar pré-visualização
            st.subheader("Pré-visualização dos Dados")
            st.dataframe(df.head(), use_container_width=True)
            
            # Estatísticas rápidas
            st.subheader("📈 Estatísticas do Arquivo")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if 'CPF' in df.columns:
                    st.metric("CPFs Únicos", df['CPF'].nunique())
                else:
                    st.metric("CPFs Únicos", "Coluna não encontrada")
            
            with col2:
                if 'Projeto' in df.columns:
                    st.metric("Projetos", df['Projeto'].nunique())
                else:
                    st.metric("Projetos", "Coluna não encontrada")
            
            with col3:
                if 'Nome' in df.columns:
                    st.metric("Nomes", df['Nome'].nunique())
                else:
                    st.metric("Nomes", "Coluna não encontrada")
            
            # Botão de processamento
            if st.button("🔄 Processar e Salvar Dados", type="primary"):
                with st.spinner("Processando dados... Isso pode levar alguns segundos"):
                    # Simular processamento
                    import time
                    for i in range(100):
                        time.sleep(0.01)
                    
                    st.success("🎉 Dados processados com sucesso!")
                    st.balloons()
                        
        except Exception as e:
            st.error(f"❌ Erro ao processar arquivo: {str(e)}")
            st.info("💡 **Dica:** Verifique se o arquivo não está corrompido e se está no formato correto.")

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
                    # Simular busca
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