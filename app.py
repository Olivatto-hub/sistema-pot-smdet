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

# [TODAS AS FUNÇÕES ANTERIORES PERMANECEM IGUAIS...]
# ... (autenticar, obter_coluna_conta, formatar_brasileiro, filtrar_pagamentos_validos, etc.)

# ATUALIZADA: Gerar PDF Executivo com informações CORRIGIDAS
def gerar_pdf_executivo(dados, metrics, nomes_arquivos):
    """Gera relatório PDF executivo profissional"""
    try:
        pdf = FPDF()
        pdf.add_page()
        
        # Configurações de fonte
        pdf.set_font('Arial', 'B', 16)
        
        # CABEÇALHO OFICIAL
        pdf.cell(0, 10, 'PREFEITURA DE SAO PAULO', 0, 1, 'C')
        pdf.set_font('Arial', 'B', 14)
        pdf.cell(0, 10, 'SECRETARIA MUNICIPAL DO DESENVOLVIMENTO ECONOMICO E TRABALHO', 0, 1, 'C')
        pdf.set_font('Arial', 'B', 16)
        pdf.cell(0, 10, 'PROGRAMA OPERACAO TRABALHO (POT)', 0, 1, 'C')
        pdf.cell(0, 10, 'RELATORIO DE MONITORAMENTO DE PAGAMENTOS', 0, 1, 'C')
        
        # Linha divisória
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(10)
        
        # Informações do relatório
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 8, 'INFORMACOES DO RELATORIO', 0, 1)
        pdf.set_font('Arial', '', 10)
        
        pdf.cell(0, 6, f'Data de emissao: {data_hora_atual_brasilia()}', 0, 1)
        if nomes_arquivos.get('pagamentos'):
            nome_arquivo = nomes_arquivos["pagamentos"].encode('latin-1', 'ignore').decode('latin-1')
            pdf.cell(0, 6, f'Planilha de Pagamentos: {nome_arquivo}', 0, 1)
        if nomes_arquivos.get('contas'):
            nome_arquivo = nomes_arquivos["contas"].encode('latin-1', 'ignore').decode('latin-1')
            pdf.cell(0, 6, f'Planilha de Abertura de Contas: {nome_arquivo}', 0, 1)
        
        pdf.ln(8)
        
        # MÉTRICAS PRINCIPAIS - COM DESTAQUE
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 8, 'METRICAS PRINCIPAIS', 0, 1)
        pdf.set_font('Arial', '', 10)
        
        # Criar tabela de métricas
        linha_alt = False
        metrics_data = []
        
        if metrics.get('beneficiarios_unicos', 0) > 0:
            metrics_data.append(('Beneficiarios Unicos', formatar_brasileiro(metrics["beneficiarios_unicos"], "numero")))
        
        if metrics.get('total_pagamentos', 0) > 0:
            metrics_data.append(('Total de Pagamentos', formatar_brasileiro(metrics["total_pagamentos"], "numero")))
        
        if metrics.get('contas_unicas', 0) > 0:
            metrics_data.append(('Contas Unicas', formatar_brasileiro(metrics["contas_unicas"], "numero")))
        
        if metrics.get('total_contas_abertas', 0) > 0:
            metrics_data.append(('Contas Abertas', formatar_brasileiro(metrics["total_contas_abertas"], "numero")))
        
        if metrics.get('projetos_ativos', 0) > 0:
            metrics_data.append(('Projetos Ativos', formatar_brasileiro(metrics["projetos_ativos"], "numero")))
        
        if metrics.get('valor_total', 0) > 0:
            metrics_data.append(('Valor Total dos Pagamentos', formatar_brasileiro(metrics["valor_total"], "monetario")))
        
        # NOVO: Mostrar registros inválidos
        if metrics.get('total_registros_invalidos', 0) > 0:
            metrics_data.append(('Registros sem Numero de Conta', formatar_brasileiro(metrics["total_registros_invalidos"], "numero")))
        
        # Adicionar métricas em formato de tabela
        for metric, value in metrics_data:
            if linha_alt:
                pdf.set_fill_color(240, 240, 240)
                pdf.cell(0, 6, f'{metric}: {value}', 0, 1, 'L', 1)
            else:
                pdf.cell(0, 6, f'{metric}: {value}', 0, 1)
            linha_alt = not linha_alt
        
        pdf.ln(8)
        
        # ANÁLISE DE DADOS E ALERTAS
        tem_alertas = False
        
        # ALERTA DE DUPLICIDADES DETALHADO - CORRIGIDO
        duplicidades = metrics.get('duplicidades_detalhadas', {})
        if duplicidades.get('total_contas_duplicadas', 0) > 0:
            tem_alertas = True
            pdf.set_font('Arial', 'B', 12)
            pdf.set_text_color(255, 0, 0)
            pdf.cell(0, 8, 'ALERTA CRITICO: DUPLICIDADES DETECTADAS', 0, 1)
            pdf.set_text_color(0, 0, 0)
            pdf.set_font('Arial', '', 10)
            
            total_pagamentos = metrics.get('total_pagamentos', 0)
            total_contas = metrics.get('contas_unicas', 0)
            pagamentos_em_excesso = duplicidades['total_pagamentos_duplicados'] - duplicidades['total_contas_duplicadas']
            
            pdf.cell(0, 6, f'- Total de pagamentos: {formatar_brasileiro(total_pagamentos, "numero")}', 0, 1)
            pdf.cell(0, 6, f'- Total de contas unicas: {formatar_brasileiro(total_contas, "numero")}', 0, 1)
            pdf.cell(0, 6, f'- Contas com multiplos pagamentos: {formatar_brasileiro(duplicidades["total_contas_duplicadas"], "numero")}', 0, 1)
            pdf.cell(0, 6, f'- Pagamentos em excesso: {formatar_brasileiro(pagamentos_em_excesso, "numero")}', 0, 1)
            pdf.cell(0, 6, f'- Total de pagamentos duplicados: {formatar_brasileiro(duplicidades["total_pagamentos_duplicados"], "numero")}', 0, 1)
            
            if duplicidades.get('valor_total_duplicados', 0) > 0:
                pdf.cell(0, 6, f'- Valor total em duplicidades: {formatar_brasileiro(duplicidades["valor_total_duplicados"], "monetario")}', 0, 1)
            
            pdf.ln(4)
        
        # ALERTA DE REGISTROS INVÁLIDOS
        if metrics.get('total_registros_invalidos', 0) > 0:
            tem_alertas = True
            pdf.set_font('Arial', 'B', 12)
            pdf.set_text_color(255, 165, 0)  # Laranja
            pdf.cell(0, 8, 'REGISTROS SEM NUMERO DE CONTA', 0, 1)
            pdf.set_text_color(0, 0, 0)
            pdf.set_font('Arial', '', 10)
            pdf.cell(0, 6, f'- Registros sem numero de conta: {formatar_brasileiro(metrics["total_registros_invalidos"], "numero")}', 0, 1)
            pdf.cell(0, 6, '  (Estes registros nao sao considerados como pagamentos validos)', 0, 1)
            pdf.ln(4)
        
        if metrics.get('total_registros_criticos', 0) > 0:
            tem_alertas = True
            pdf.set_font('Arial', 'B', 12)
            pdf.set_text_color(255, 0, 0)
            pdf.cell(0, 8, 'ALERTAS CRITICOS IDENTIFICADOS', 0, 1)
            pdf.set_text_color(0, 0, 0)
            pdf.set_font('Arial', '', 10)
            pdf.cell(0, 6, f'- Registros com dados criticos ausentes: {formatar_brasileiro(metrics["total_registros_criticos"], "numero")}', 0, 1)
            pdf.cell(0, 6, '  (CPF, numero da conta ou valor ausentes/zerados)', 0, 1)
            pdf.ln(4)
        
        # PAGAMENTOS PENDENTES
        pendentes = metrics.get('pagamentos_pendentes', {})
        if pendentes.get('total_contas_sem_pagamento', 0) > 0:
            tem_alertas = True
            pdf.set_font('Arial', 'B', 12)
            pdf.set_text_color(255, 165, 0)
            pdf.cell(0, 8, 'PAGAMENTOS PENDENTES IDENTIFICADOS', 0, 1)
            pdf.set_text_color(0, 0, 0)
            pdf.set_font('Arial', '', 10)
            pdf.cell(0, 6, f'- Contas abertas sem pagamento: {formatar_brasileiro(pendentes["total_contas_sem_pagamento"], "numero")}', 0, 1)
            pdf.cell(0, 6, f'- Beneficiarios aguardando pagamento: {formatar_brasileiro(pendentes["beneficiarios_sem_pagamento"], "numero")}', 0, 1)
            pdf.ln(4)
        
        # PROBLEMAS COM CPF
        problemas_cpf = metrics.get('problemas_cpf', {})
        if problemas_cpf.get('total_problemas_cpf', 0) > 0:
            tem_alertas = True
            pdf.set_font('Arial', 'B', 12)
            pdf.set_text_color(255, 165, 0)
            pdf.cell(0, 8, 'PROBLEMAS COM CPF IDENTIFICADOS', 0, 1)
            pdf.set_text_color(0, 0, 0)
            pdf.set_font('Arial', '', 10)
            pdf.cell(0, 6, f'- CPFs com problemas: {formatar_brasileiro(problemas_cpf["total_problemas_cpf"], "numero")}', 0, 1)
            pdf.cell(0, 6, f'  - CPFs vazios: {formatar_brasileiro(len(problemas_cpf.get("cpfs_vazios", [])), "numero")}', 0, 1)
            pdf.cell(0, 6, f'  - CPFs com caracteres invalidos: {formatar_brasileiro(len(problemas_cpf.get("cpfs_com_caracteres_invalidos", [])), "numero")}', 0, 1)
            pdf.cell(0, 6, f'  - CPFs com tamanho incorreto: {formatar_brasileiro(len(problemas_cpf.get("cpfs_com_tamanho_incorreto", [])), "numero")}', 0, 1)
            pdf.ln(4)
        
        if not tem_alertas:
            pdf.set_font('Arial', 'B', 12)
            pdf.set_text_color(0, 128, 0)
            pdf.cell(0, 8, 'OK - NENHUM ALERTA CRITICO IDENTIFICADO', 0, 1)
            pdf.set_text_color(0, 0, 0)
        
        pdf.ln(8)
        
        # INFORMAÇÕES DE PROCESSAMENTO
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 8, 'INFORMACOES DE PROCESSAMENTO', 0, 1)
        pdf.set_font('Arial', '', 10)
        
        if metrics.get('documentos_padronizados', 0) > 0:
            pdf.cell(0, 6, f'- Documentos processados: {formatar_brasileiro(metrics["documentos_padronizados"], "numero")}', 0, 1)
        
        if metrics.get('registros_validos_com_letras', 0) > 0:
            pdf.cell(0, 6, f'- RGs com letras validas processados: {formatar_brasileiro(metrics["registros_validos_com_letras"], "numero")}', 0, 1)
        
        if metrics.get('cpfs_com_zeros_adicional', 0) > 0:
            pdf.cell(0, 6, f'- CPFs normalizados com zeros: {formatar_brasileiro(metrics["cpfs_com_zeros_adicional"], "numero")}', 0, 1)
        
        if metrics.get('cpfs_formatos_diferentes', 0) > 0:
            pdf.cell(0, 6, f'- CPFs de outros estados processados: {formatar_brasileiro(metrics["cpfs_formatos_diferentes"], "numero")}', 0, 1)
        
        pdf.ln(10)
        
        # RODAPÉ OFICIAL
        pdf.set_font('Arial', 'I', 8)
        pdf.cell(0, 10, 'Secretaria Municipal do Desenvolvimento Economico e Trabalho - SMDET', 0, 0, 'C')
        pdf.ln(4)
        pdf.cell(0, 10, f'Relatorio gerado automaticamente pelo Sistema de Monitoramento do POT em {data_atual_brasilia()}', 0, 0, 'C')
        
        return pdf.output(dest='S').encode('latin-1')
    
    except Exception as e:
        st.error(f"Erro ao gerar PDF: {str(e)}")
        return None

# ATUALIZADA: Gerar Excel Completo com abas CORRIGIDAS
def gerar_excel_completo(dados, metrics):
    """Gera arquivo Excel completo com os dados"""
    try:
        output = io.BytesIO()
        
        # Criar um arquivo Excel simples usando pandas
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Aba de Pagamentos (apenas válidos)
            if 'pagamentos' in dados and not dados['pagamentos'].empty:
                # CORREÇÃO: Mostrar apenas pagamentos válidos
                df_pagamentos_validos = filtrar_pagamentos_validos(dados['pagamentos'])
                if not df_pagamentos_validos.empty:
                    df_pagamentos_validos.to_excel(writer, sheet_name='Pagamentos_Validos', index=False)
                
                # NOVO: Mostrar também registros inválidos
                coluna_conta = obter_coluna_conta(dados['pagamentos'])
                if coluna_conta:
                    df_pagamentos_invalidos = dados['pagamentos'][
                        dados['pagamentos'][coluna_conta].isna() | 
                        (dados['pagamentos'][coluna_conta].astype(str).str.strip() == '')
                    ]
                    if not df_pagamentos_invalidos.empty:
                        df_pagamentos_invalidos.to_excel(writer, sheet_name='Registros_Sem_Conta', index=False)
            
            # Aba de Contas
            if 'contas' in dados and not dados['contas'].empty:
                dados['contas'].to_excel(writer, sheet_name='Contas', index=False)
            
            # Aba de Métricas
            metricas_df = pd.DataFrame([
                {'Métrica': 'Beneficiários Únicos', 'Valor': metrics.get('beneficiarios_unicos', 0)},
                {'Métrica': 'Total de Pagamentos Válidos', 'Valor': metrics.get('total_pagamentos', 0)},
                {'Métrica': 'Contas Únicas', 'Valor': metrics.get('contas_unicas', 0)},
                {'Métrica': 'Contas Abertas', 'Valor': metrics.get('total_contas_abertas', 0)},
                {'Métrica': 'Projetos Ativos', 'Valor': metrics.get('projetos_ativos', 0)},
                {'Métrica': 'Valor Total', 'Valor': metrics.get('valor_total', 0)},
                {'Métrica': 'Registros Críticos', 'Valor': metrics.get('total_registros_criticos', 0)},
                {'Métrica': 'Contas com Duplicidades', 'Valor': metrics.get('pagamentos_duplicados', 0)},
                {'Métrica': 'Pagamentos Duplicados', 'Valor': metrics.get('duplicidades_detalhadas', {}).get('total_pagamentos_duplicados', 0)},
                {'Métrica': 'Contas sem Pagamento', 'Valor': metrics.get('pagamentos_pendentes', {}).get('total_contas_sem_pagamento', 0)},
                {'Métrica': 'Registros sem Número de Conta', 'Valor': metrics.get('total_registros_invalidos', 0)},
                {'Métrica': 'CPFs com Problemas', 'Valor': metrics.get('problemas_cpf', {}).get('total_problemas_cpf', 0)}
            ])
            metricas_df.to_excel(writer, sheet_name='Métricas', index=False)
            
            # ABA: Duplicidades Detalhadas
            duplicidades = metrics.get('duplicidades_detalhadas', {})
            if not duplicidades.get('detalhes_completos_duplicidades', pd.DataFrame()).empty:
                duplicidades['detalhes_completos_duplicidades'].to_excel(writer, sheet_name='Duplicidades_Detalhadas', index=False)
            
            if not duplicidades.get('resumo_duplicidades', pd.DataFrame()).empty:
                duplicidades['resumo_duplicidades'].to_excel(writer, sheet_name='Resumo_Duplicidades', index=False)
            
            # ABA: Pagamentos Pendentes
            pendentes = metrics.get('pagamentos_pendentes', {})
            if not pendentes.get('contas_sem_pagamento', pd.DataFrame()).empty:
                pendentes['contas_sem_pagamento'].to_excel(writer, sheet_name='Pagamentos_Pendentes', index=False)
            
            # Aba de Problemas (se houver)
            if not metrics.get('resumo_ausencias', pd.DataFrame()).empty:
                metrics['resumo_ausencias'].to_excel(writer, sheet_name='Problemas_Identificados', index=False)
            
            # NOVA ABA: CPFs Problemáticos
            problemas_cpf = metrics.get('problemas_cpf', {})
            if not problemas_cpf.get('detalhes_cpfs_problematicos', pd.DataFrame()).empty:
                problemas_cpf['detalhes_cpfs_problematicos'].to_excel(writer, sheet_name='CPFs_Problematicos', index=False)
        
        output.seek(0)
        return output.getvalue()
    
    except Exception as e:
        st.error(f"Erro ao gerar Excel: {str(e)}")
        return None

# NOVA FUNÇÃO: Gerar planilha com ajustes realizados
def gerar_planilha_ajustes(dados_originais, dados_processados, metrics):
    """Gera planilha com os ajustes realizados nos dados"""
    try:
        output = io.BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Aba 1: Dados Originais vs Processados
            if 'pagamentos' in dados_originais and not dados_originais['pagamentos'].empty and 'pagamentos' in dados_processados:
                df_original = dados_originais['pagamentos'].copy()
                df_processado = dados_processados['pagamentos'].copy()
                
                # Criar comparação para CPF
                if 'CPF' in df_original.columns:
                    df_comparacao = df_original[['CPF']].copy()
                    df_comparacao['CPF_Original'] = df_original['CPF'].fillna('')
                    df_comparacao['CPF_Processado'] = df_processado['CPF'].fillna('')
                    df_comparacao['Alteracao_CPF'] = df_comparacao['CPF_Original'] != df_comparacao['CPF_Processado']
                    
                    # Adicionar outras colunas importantes para contexto
                    coluna_conta = obter_coluna_conta(df_original)
                    if coluna_conta:
                        df_comparacao['Numero_Conta'] = df_original[coluna_conta]
                    
                    coluna_nome = obter_coluna_nome(df_original)
                    if coluna_nome:
                        df_comparacao['Nome'] = df_original[coluna_nome]
                    
                    df_comparacao.to_excel(writer, sheet_name='Ajustes_CPF', index=False)
            
            # Aba 2: Resumo de Ajustes
            resumo_ajustes = []
            
            # Contar ajustes de CPF
            if 'pagamentos' in dados_originais and 'CPF' in dados_originais['pagamentos'].columns:
                df_original = dados_originais['pagamentos']
                df_processado = dados_processados.get('pagamentos', pd.DataFrame())
                if not df_processado.empty and 'CPF' in df_processado.columns:
                    cpfs_alterados = sum(df_original['CPF'].fillna('') != df_processado['CPF'].fillna(''))
                    resumo_ajustes.append({'Tipo_Ajuste': 'CPFs Formatados', 'Quantidade': cpfs_alterados})
            
            # Adicionar outros tipos de ajustes
            if metrics.get('documentos_padronizados', 0) > 0:
                resumo_ajustes.append({'Tipo_Ajuste': 'Documentos Processados', 'Quantidade': metrics['documentos_padronizados']})
            
            if metrics.get('cpfs_com_zeros_adicional', 0) > 0:
                resumo_ajustes.append({'Tipo_Ajuste': 'CPFs com Zeros Adicionados', 'Quantidade': metrics['cpfs_com_zeros_adicional']})
            
            if metrics.get('registros_validos_com_letras', 0) > 0:
                resumo_ajustes.append({'Tipo_Ajuste': 'RGs com Letras Preservadas', 'Quantidade': metrics['registros_validos_com_letras']})
            
            df_resumo = pd.DataFrame(resumo_ajustes)
            if not df_resumo.empty:
                df_resumo.to_excel(writer, sheet_name='Resumo_Ajustes', index=False)
            
            # Aba 3: Problemas Identificados
            if not metrics.get('resumo_ausencias', pd.DataFrame()).empty:
                metrics['resumo_ausencias'].to_excel(writer, sheet_name='Problemas_Identificados', index=False)
            
            # Aba 4: CPFs Problemáticos
            problemas_cpf = identificar_cpfs_problematicos(dados_processados.get('pagamentos', pd.DataFrame()))
            if not problemas_cpf['detalhes_cpfs_problematicos'].empty:
                problemas_cpf['detalhes_cpfs_problematicos'].to_excel(writer, sheet_name='CPFs_Problematicos', index=False)
        
        output.seek(0)
        return output.getvalue()
    
    except Exception as e:
        st.error(f"Erro ao gerar planilha de ajustes: {str(e)}")
        return None

# ATUALIZAR a interface principal para incluir os relatórios na tab6
def main():
    # [TODO O CÓDIGO ANTERIOR DA MAIN PERMANECE IGUAL ATÉ A DEFINIÇÃO DAS ABAS...]
    
    # CORREÇÃO: DEFINIR AS ABAS ANTES DE USAR
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
    
    # [AS OUTRAS ABAS tab3, tab4, tab5 PERMANECEM COM SEU CONTEÚDO ORIGINAL...]
    
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
