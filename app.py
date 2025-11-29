# app.py
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timezone, timedelta
import io
from fpdf import FPDF
import numpy as np
import re
import base64

# Configuração da página
st.set_page_config(
    page_title="Sistema POT - SMDET",
    page_icon="🏛️",
    layout="wide"
)

# [TODAS AS FUNÇÕES ANTERIORES PERMANECEM AQUI...]
# ... (autenticar, obter_coluna_conta, formatar_brasileiro, filtrar_pagamentos_validos, etc.)

# Interface principal do sistema - CORRIGIDA
def main():
    # Autenticação
    email = autenticar()
    
    if not email:
        st.info("👆 Por favor, insira seu email @prefeitura.sp.gov.br para acessar o sistema")
        return
    
    st.sidebar.success(f"✅ Acesso autorizado: {email}")
    st.sidebar.markdown("---")
    
    # Carregar dados
    dados, nomes_arquivos = carregar_dados()
    
    # CORREÇÃO: Verificar se há dados para processar de forma segura
    tem_dados_pagamentos = 'pagamentos' in dados and not dados['pagamentos'].empty
    tem_dados_contas = 'contas' in dados and not dados['contas'].empty
    
    if not tem_dados_pagamentos and not tem_dados_contas:
        st.info("📊 Faça o upload das planilhas de pagamentos e/ou abertura de contas para iniciar a análise")
        return
    
    # Processar dados
    with st.spinner("🔄 Processando dados..."):
        metrics = processar_dados(dados, nomes_arquivos)
    
    # Interface principal
    st.title("🏛️ Sistema POT - SMDET")
    st.subheader("Monitoramento de Pagamentos e Abertura de Contas")
    
    # Métricas principais
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if metrics.get('beneficiarios_unicos', 0) > 0:
            st.metric("Beneficiários Únicos", formatar_brasileiro(metrics["beneficiarios_unicos"], "numero"))
        elif metrics.get('beneficiarios_contas', 0) > 0:
            st.metric("Beneficiários (Contas)", formatar_brasileiro(metrics["beneficiarios_contas"], "numero"))
    
    with col2:
        if metrics.get('total_pagamentos', 0) > 0:
            st.metric("Pagamentos Válidos", formatar_brasileiro(metrics["total_pagamentos"], "numero"))
        if metrics.get('total_contas_abertas', 0) > 0:
            st.metric("Contas Abertas", formatar_brasileiro(metrics["total_contas_abertas"], "numero"))
    
    with col3:
        if metrics.get('contas_unicas', 0) > 0:
            st.metric("Contas Únicas", formatar_brasileiro(metrics["contas_unicas"], "numero"))
    
    with col4:
        if metrics.get('projetos_ativos', 0) > 0:
            st.metric("Projetos Ativos", formatar_brasileiro(metrics["projetos_ativos"], "numero"))
        if metrics.get('valor_total', 0) > 0:
            st.metric("Valor Total", formatar_brasileiro(metrics["valor_total"], "monetario"))
    
    # Alertas
    duplicidades = metrics.get('duplicidades_detalhadas', {})
    if duplicidades.get('total_contas_duplicadas', 0) > 0:
        total_pagamentos = metrics.get('total_pagamentos', 0)
        total_contas = metrics.get('contas_unicas', 0)
        total_contas_duplicadas = duplicidades['total_contas_duplicadas']
        total_pagamentos_duplicados = duplicidades['total_pagamentos_duplicados']
        pagamentos_em_excesso = total_pagamentos_duplicados - total_contas_duplicadas
        
        st.error(f"""
        🚨 **ALERTA CRÍTICO: DUPLICIDADE DETECTADA**
        
        **{formatar_brasileiro(total_pagamentos, 'numero')} pagamentos válidos** para **{formatar_brasileiro(total_contas, 'numero')} contas**
        
        ⚠️ **{formatar_brasileiro(total_contas_duplicadas, 'numero')} contas** receberam múltiplos pagamentos
        📋 **{formatar_brasileiro(pagamentos_em_excesso, 'numero')} pagamentos em excesso** (acima do esperado)
        💰 **Valor total em duplicidades:** {formatar_brasileiro(duplicidades.get('valor_total_duplicados', 0), 'monetario')}
        
        *Análise: {formatar_brasileiro(total_contas_duplicadas, 'numero')} contas receberam mais de 1 pagamento cada*
        """)
    
    # ALERTA DE REGISTROS INVÁLIDOS
    if metrics.get('total_registros_invalidos', 0) > 0:
        st.warning(f"⚠️ REGISTROS SEM CONTA: {formatar_brasileiro(metrics['total_registros_invalidos'], 'numero')} registros não possuem número de conta e não são considerados pagamentos válidos")
    
    # Alertas críticos
    if metrics.get('total_registros_criticos', 0) > 0:
        st.error(f"🚨 ALERTA: {formatar_brasileiro(metrics['total_registros_criticos'], 'numero')} registros com dados críticos ausentes (CPF, conta ou valor)")
    
    # Pagamentos pendentes
    pendentes = metrics.get('pagamentos_pendentes', {})
    if pendentes.get('total_contas_sem_pagamento', 0) > 0:
        st.warning(f"⚠️ PAGAMENTOS PENDENTES: {formatar_brasileiro(pendentes['total_contas_sem_pagamento'], 'numero')} contas abertas sem pagamento")
    
    # PROBLEMAS COM CPF - NOVO ALERTA
    problemas_cpf = metrics.get('problemas_cpf', {})
    if problemas_cpf.get('total_problemas_cpf', 0) > 0:
        st.warning(f"⚠️ PROBLEMAS COM CPF: {formatar_brasileiro(problemas_cpf['total_problemas_cpf'], 'numero')} CPFs com problemas de formatação identificados")
    
    # CORREÇÃO: DEFINIR AS ABAS APÓS PROCESSAR OS DADOS
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📈 Visão Geral", "🔍 Dados Detalhados", "🔄 Duplicidades", "⏳ Pagamentos Pendentes", "🚫 Registros Inválidos", "📋 Relatórios"])
    
    with tab1:
        st.header("Visão Geral dos Dados")
        
        # Visualização de dados
        if tem_dados_pagamentos:
            st.subheader("Dados de Pagamentos Válidos")
            df_pagamentos_validos = filtrar_pagamentos_validos(dados['pagamentos'])
            if not df_pagamentos_validos.empty:
                st.dataframe(df_pagamentos_validos.head(100), use_container_width=True)
            else:
                st.info("ℹ️ Nenhum pagamento válido encontrado (todos os registros estão sem número de conta)")
        
        if tem_dados_contas:
            st.subheader("Dados de Abertura de Contas")
            st.dataframe(dados['contas'].head(100), use_container_width=True)
    
    with tab2:
        st.header("Análise Detalhada")
        
        # NOVA SEÇÃO: Problemas com CPF
        problemas_cpf = metrics.get('problemas_cpf', {})
        if problemas_cpf.get('total_problemas_cpf', 0) > 0:
            st.subheader("🔍 Problemas com CPF Identificados")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("CPFs Vazios", len(problemas_cpf.get('cpfs_vazios', [])))
            
            with col2:
                st.metric("CPFs com Caracteres Inválidos", len(problemas_cpf.get('cpfs_com_caracteres_invalidos', [])))
            
            with col3:
                st.metric("CPFs com Tamanho Incorreto", len(problemas_cpf.get('cpfs_com_tamanho_incorreto', [])))
            
            if not problemas_cpf.get('detalhes_cpfs_problematicos', pd.DataFrame()).empty:
                st.subheader("📋 Detalhes dos CPFs Problemáticos")
                st.dataframe(problemas_cpf['detalhes_cpfs_problematicos'], use_container_width=True)
        else:
            st.success("✅ Nenhum problema com CPF identificado")
        
        if not metrics.get('resumo_ausencias', pd.DataFrame()).empty:
            st.subheader("Registros com Problemas Críticos")
            st.dataframe(metrics['resumo_ausencias'], use_container_width=True)
        
        # Estatísticas de processamento
        if metrics.get('documentos_padronizados', 0) > 0:
            st.subheader("Estatísticas de Processamento")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Documentos Processados", formatar_brasileiro(metrics['documentos_padronizados'], 'numero'))
            
            with col2:
                st.metric("RGs com Letras", formatar_brasileiro(metrics['registros_validos_com_letras'], 'numero'))
            
            with col3:
                st.metric("CPFs Normalizados", formatar_brasileiro(metrics['cpfs_com_zeros_adicional'], 'numero'))
            
            with col4:
                st.metric("Registros sem Conta", formatar_brasileiro(metrics.get('total_registros_invalidos', 0), 'numero'))
    
    with tab3:
        st.header("Análise de Duplicidades")
        
        if duplicidades.get('total_contas_duplicadas', 0) > 0:
            total_pagamentos = metrics.get('total_pagamentos', 0)
            total_contas = metrics.get('contas_unicas', 0)
            pagamentos_em_excesso = duplicidades['total_pagamentos_duplicados'] - duplicidades['total_contas_duplicadas']
            
            st.subheader(f"📊 Análise das Duplicidades")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total de Pagamentos", formatar_brasileiro(total_pagamentos, 'numero'))
            
            with col2:
                st.metric("Contas Únicas", formatar_brasileiro(total_contas, 'numero'))
            
            with col3:
                st.metric("Contas com Múltiplos Pagamentos", 
                         formatar_brasileiro(duplicidades['total_contas_duplicadas'], 'numero'),
                         delta=f"+{formatar_brasileiro(pagamentos_em_excesso, 'numero')} pagamentos extras")
            
            with col4:
                st.metric("Valor em Duplicidades", 
                         formatar_brasileiro(duplicidades.get('valor_total_duplicados', 0), 'monetario'))
            
            st.info(f"""
            **📈 Análise Detalhada:**
            - **{formatar_brasileiro(total_pagamentos, 'numero')} pagamentos válidos** realizados
            - **{formatar_brasileiro(total_contas, 'numero')} contas únicas** identificadas  
            - **{formatar_brasileiro(duplicidades['total_contas_duplicadas'], 'numero')} contas** receberam múltiplos pagamentos
            - **{formatar_brasileiro(pagamentos_em_excesso, 'numero')} pagamentos em excesso** detectados
            """)
            
            st.subheader("📋 Contas com Múltiplos Pagamentos")
            if not duplicidades.get('resumo_duplicidades', pd.DataFrame()).empty:
                df_resumo = duplicidades['resumo_duplicidades'].sort_values('Total_Pagamentos', ascending=False)
                st.dataframe(df_resumo, use_container_width=True)
            
            st.subheader("📄 DETALHES COMPLETOS DOS PAGAMENTOS DUPLICADOS")
            st.write("**Abaixo estão todos os registros de pagamentos duplicados com dados completos:**")
            
            if not duplicidades.get('detalhes_completos_duplicidades', pd.DataFrame()).empty:
                df_detalhes = duplicidades['detalhes_completos_duplicidades']
                
                colunas_importantes = []
                if 'Num Cartao' in df_detalhes.columns or 'Num_Cartao' in df_detalhes.columns or 'Conta' in df_detalhes.columns:
                    colunas_importantes.extend(['Num Cartao', 'Num_Cartao', 'Conta'])
                if 'Beneficiario' in df_detalhes.columns or 'Beneficiário' in df_detalhes.columns or 'Nome' in df_detalhes.columns:
                    colunas_importantes.extend(['Beneficiario', 'Beneficiário', 'Nome'])
                if 'CPF' in df_detalhes.columns:
                    colunas_importantes.append('CPF')
                if 'Data' in df_detalhes.columns or 'Data Pagto' in df_detalhes.columns or 'Data_Pagto' in df_detalhes.columns or 'DataPagto' in df_detalhes.columns:
                    colunas_importantes.extend(['Data', 'Data Pagto', 'Data_Pagto', 'DataPagto'])
                if 'Valor' in df_detalhes.columns:
                    colunas_importantes.append('Valor')
                if 'Valor_Limpo' in df_detalhes.columns:
                    colunas_importantes.append('Valor_Limpo')
                if 'Ocorrencia' in df_detalhes.columns:
                    colunas_importantes.append('Ocorrencia')
                if 'Total_Ocorrencias' in df_detalhes.columns:
                    colunas_importantes.append('Total_Ocorrencias')
                
                colunas_existentes = [col for col in colunas_importantes if col in df_detalhes.columns]
                df_exibicao = df_detalhes[colunas_existentes]
                
                st.dataframe(df_exibicao, use_container_width=True)
                
                if st.button("📥 Exportar Duplicidades para Excel", key="export_duplicidades"):
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        duplicidades['resumo_duplicidades'].to_excel(writer, sheet_name='Resumo_Duplicidades', index=False)
                        duplicidades['detalhes_completos_duplicidades'].to_excel(writer, sheet_name='Detalhes_Completos_Duplicidades', index=False)
                    
                    output.seek(0)
                    b64 = base64.b64encode(output.getvalue()).decode()
                    href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="duplicidades_pot_{data_hora_arquivo_brasilia()}.xlsx">📥 Baixar Duplicidades</a>'
                    st.markdown(href, unsafe_allow_html=True)
        else:
            st.success("✅ Nenhuma duplicidade detectada nos pagamentos válidos")
    
    with tab4:
        st.header("Pagamentos Pendentes")
        
        if pendentes.get('total_contas_sem_pagamento', 0) > 0:
            st.subheader(f"⏳ Contas Aguardando Pagamento")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric("Contas sem Pagamento", formatar_brasileiro(pendentes['total_contas_sem_pagamento'], 'numero'))
            
            with col2:
                st.metric("Beneficiários Afetados", formatar_brasileiro(pendentes['beneficiarios_sem_pagamento'], 'numero'))
            
            st.subheader("📋 Lista de Contas sem Pagamento")
            if not pendentes.get('contas_sem_pagamento', pd.DataFrame()).empty:
                st.dataframe(pendentes['contas_sem_pagamento'], use_container_width=True)
        else:
            st.success("✅ Todos as contas abertas possuem pagamentos registrados")
    
    with tab5:
        st.header("Registros sem Número de Conta")
        
        if metrics.get('total_registros_invalidos', 0) > 0:
            st.subheader(f"🚫 Registros Não Considerados como Pagamentos")
            st.info("""
            **Estes registros não possuem número de conta e NÃO são considerados pagamentos válidos:**
            - Não entram na contagem total de pagamentos
            - Não são considerados nas análises de duplicidade
            - Não são incluídos nos cálculos de valor total
            """)
            
            coluna_conta = obter_coluna_conta(dados['pagamentos'])
            if coluna_conta:
                df_pagamentos_invalidos = dados['pagamentos'][
                    dados['pagamentos'][coluna_conta].isna() | 
                    (dados['pagamentos'][coluna_conta].astype(str).str.strip() == '')
                ]
                
                if not df_pagamentos_invalidos.empty:
                    st.dataframe(df_pagamentos_invalidos, use_container_width=True)
                    
                    st.warning(f"⚠️ Total de registros sem número de conta: {formatar_brasileiro(len(df_pagamentos_invalidos), 'numero')}")
        else:
            st.success("✅ Todos os registros possuem número de conta e são considerados pagamentos válidos")
    
    with tab6:
        st.header("Relatórios e Exportações")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.subheader("📄 Relatório Executivo (PDF)")
            st.info("Relatório formal em PDF com análise completa")
            if st.button("📄 Gerar Relatório PDF", type="primary", key="pdf_button"):
                with st.spinner("Gerando relatório PDF..."):
                    pdf_bytes = gerar_pdf_executivo(dados, metrics, nomes_arquivos)
                    if pdf_bytes:
                        st.success("✅ Relatório PDF gerado com sucesso!")
                        b64 = base64.b64encode(pdf_bytes).decode()
                        href = f'<a href="data:application/pdf;base64,{b64}" download="relatorio_pot_{data_hora_arquivo_brasilia()}.pdf">📥 Baixar Relatório PDF</a>'
                        st.markdown(href, unsafe_allow_html=True)
                    else:
                        st.error("❌ Erro ao gerar relatório PDF")
        
        with col2:
            st.subheader("📊 Dados Completos (Excel)")
            st.info("Planilha completa com todos os dados processados")
            if st.button("📊 Gerar Excel Completo", key="excel_button"):
                with st.spinner("Gerando arquivo Excel..."):
                    excel_bytes = gerar_excel_completo(dados, metrics)
                    if excel_bytes:
                        st.success("✅ Arquivo Excel gerado com sucesso!")
                        b64 = base64.b64encode(excel_bytes).decode()
                        href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="dados_pot_{data_hora_arquivo_brasilia()}.xlsx">📥 Baixar Excel Completo</a>'
                        st.markdown(href, unsafe_allow_html=True)
                    else:
                        st.error("❌ Erro ao gerar arquivo Excel")
        
        with col3:
            st.subheader("🛠️ Planilha de Ajustes")
            st.info("Planilha com comparação dos ajustes realizados")
            if st.button("📋 Gerar Planilha de Ajustes", key="ajustes_button"):
                with st.spinner("Gerando planilha de ajustes..."):
                    # Carregar dados originais novamente para comparação
                    dados_originais = {}
                    if 'pagamentos' in dados:
                        # Recarregar os dados originais sem processamento
                        upload_pagamentos = st.session_state.get("pagamentos")
                        if upload_pagamentos is not None:
                            try:
                                if upload_pagamentos.name.endswith('.xlsx'):
                                    df_original = pd.read_excel(upload_pagamentos)
                                else:
                                    df_original = pd.read_csv(upload_pagamentos, encoding='utf-8', sep=';')
                                dados_originais['pagamentos'] = df_original
                            except Exception as e:
                                st.error(f"Erro ao carregar dados originais: {str(e)}")
                    
                    ajustes_bytes = gerar_planilha_ajustes(dados_originais, dados, metrics)
                    if ajustes_bytes:
                        st.success("✅ Planilha de ajustes gerada com sucesso!")
                        b64 = base64.b64encode(ajustes_bytes).decode()
                        href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="ajustes_pot_{data_hora_arquivo_brasilia()}.xlsx">📥 Baixar Planilha de Ajustes</a>'
                        st.markdown(href, unsafe_allow_html=True)
                    else:
                        st.error("❌ Erro ao gerar planilha de ajustes")
        
        # SEÇÃO DE ESTATÍSTICAS DOS RELATÓRIOS
        st.markdown("---")
        st.subheader("📈 Estatísticas para Exportação")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Pagamentos Válidos", metrics.get('total_pagamentos', 0))
        
        with col2:
            st.metric("Contas Únicas", metrics.get('contas_unicas', 0))
        
        with col3:
            st.metric("Duplicidades", metrics.get('pagamentos_duplicados', 0))
        
        with col4:
            st.metric("Problemas CPF", metrics.get('problemas_cpf', {}).get('total_problemas_cpf', 0))

if __name__ == "__main__":
    main()
