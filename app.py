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

# [TODAS AS FUNÇÕES AUXILIARES PERMANECEM IGUAIS ATÉ AQUI]
# ... (manter todas as funções: agora_brasilia, obter_coluna_conta, etc.)

# NOVA FUNÇÃO: Processar CPF para manter apenas números
def processar_cpf(cpf):
    """Processa CPF, mantendo apenas números e completando com zeros à esquerda"""
    if pd.isna(cpf) or cpf in ['', 'NaN', 'None', 'nan', 'None', 'NULL']:
        return ''  # Manter como string vazia para campos em branco
    
    cpf_str = str(cpf).strip()
    
    # Remover TODOS os caracteres não numéricos
    cpf_limpo = re.sub(r'[^\d]', '', cpf_str)
    
    # Se ficou vazio após limpeza, retornar vazio
    if cpf_limpo == '':
        return ''
    
    # Completar com zeros à esquerda se tiver menos de 11 dígitos
    if len(cpf_limpo) < 11:
        cpf_limpo = cpf_limpo.zfill(11)
    
    return cpf_limpo

# FUNÇÃO ATUALIZADA: Padronizar documentos - CPF apenas números
def padronizar_documentos(df):
    """Padroniza RGs e CPFs, CPF apenas números"""
    df_processed = df.copy()
    
    # Colunas que podem conter documentos
    colunas_documentos = ['RG', 'CPF', 'Documento', 'Numero_Documento']
    
    for coluna in colunas_documentos:
        if coluna in df_processed.columns:
            try:
                if coluna == 'CPF':
                    # Para CPF: manter apenas números
                    df_processed[coluna] = df_processed[coluna].astype(str).apply(
                        lambda x: processar_cpf(x) if pd.notna(x) and str(x).strip() != '' else ''
                    )
                elif coluna == 'RG':
                    # Para RG: manter números e letras (podem ter letras em RGs)
                    df_processed[coluna] = df_processed[coluna].astype(str).apply(
                        lambda x: re.sub(r'[^a-zA-Z0-9/]', '', x) if pd.notna(x) and str(x).strip() != '' else ''
                    )
                else:
                    # Para outros documentos: tratamento genérico
                    df_processed[coluna] = df_processed[coluna].astype(str).apply(
                        lambda x: re.sub(r'[^\w]', '', x) if pd.notna(x) and str(x).strip() != '' else ''
                    )
                
            except Exception as e:
                st.warning(f"⚠️ Não foi possível padronizar a coluna '{coluna}': {str(e)}")
    
    return df_processed

# NOVA FUNÇÃO: Identificar CPFs problemáticos
def identificar_cpfs_problematicos(df):
    """Identifica CPFs com problemas de formatação"""
    problemas_cpf = {
        'cpfs_com_caracteres_invalidos': [],
        'cpfs_com_tamanho_incorreto': [],
        'cpfs_vazios': [],
        'total_problemas_cpf': 0,
        'detalhes_cpfs_problematicos': pd.DataFrame()
    }
    
    if 'CPF' not in df.columns or df.empty:
        return problemas_cpf
    
    # Adicionar coluna com número da linha original
    df_analise = df.copy()
    df_analise['Linha_Planilha_Original'] = df_analise.index + 2
    
    # Identificar problemas
    for idx, row in df_analise.iterrows():
        cpf = str(row['CPF']) if pd.notna(row['CPF']) and str(row['CPF']).strip() != '' else ''
        problemas = []
        
        # CPF vazio
        if cpf == '':
            problemas.append('CPF vazio')
            problemas_cpf['cpfs_vazios'].append(idx)
        
        # CPF com caracteres não numéricos (após processamento não deveria ter, mas verifica)
        elif not cpf.isdigit() and cpf != '':
            problemas.append('Caracteres inválidos')
            problemas_cpf['cpfs_com_caracteres_invalidos'].append(idx)
        
        # CPF com tamanho incorreto (deve ter 11 dígitos)
        elif len(cpf) != 11 and cpf != '':
            problemas.append(f'Tamanho incorreto ({len(cpf)} dígitos)')
            problemas_cpf['cpfs_com_tamanho_incorreto'].append(idx)
        
        # Se há problemas, adicionar aos detalhes
        if problemas:
            info_problema = {
                'Linha_Planilha': row.get('Linha_Planilha_Original', idx + 2),
                'CPF_Original': row.get('CPF', ''),
                'CPF_Processado': cpf,
                'Problemas': ', '.join(problemas)
            }
            
            # Adicionar informações adicionais para identificação
            coluna_conta = obter_coluna_conta(df)
            if coluna_conta and coluna_conta in row:
                info_problema['Numero_Conta'] = row[coluna_conta]
            
            coluna_nome = obter_coluna_nome(df)
            if coluna_nome and coluna_nome in row:
                info_problema['Nome'] = row[coluna_nome]
            
            # Corrigir a concatenação do DataFrame
            if problemas_cpf['detalhes_cpfs_problematicos'].empty:
                problemas_cpf['detalhes_cpfs_problematicos'] = pd.DataFrame([info_problema])
            else:
                problemas_cpf['detalhes_cpfs_problematicos'] = pd.concat([
                    problemas_cpf['detalhes_cpfs_problematicos'],
                    pd.DataFrame([info_problema])
                ], ignore_index=True)
    
    problemas_cpf['total_problemas_cpf'] = len(problemas_cpf['cpfs_com_caracteres_invalidos']) + \
                                         len(problemas_cpf['cpfs_com_tamanho_incorreto']) + \
                                         len(problemas_cpf['cpfs_vazios'])
    
    return problemas_cpf

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

# ATUALIZAR a função processar_dados para incluir análise de CPFs
def processar_dados(dados, nomes_arquivos=None):
    """Processa os dados para gerar métricas e análises"""
    metrics = {
        'beneficiarios_unicos': 0,
        'total_pagamentos': 0,
        'contas_unicas': 0,
        'projetos_ativos': 0,
        'valor_total': 0,
        'pagamentos_duplicados': 0,
        'valor_total_duplicados': 0,
        'total_cpfs_duplicados': 0,
        'total_contas_abertas': 0,
        'beneficiarios_contas': 0,
        'duplicidades_detalhadas': {},
        'pagamentos_pendentes': {},
        'total_registros_invalidos': 0,
        'problemas_cpf': {}  # NOVO: Análise de problemas com CPF
    }
    
    # Combinar com análise de ausência de dados
    analise_ausencia = analisar_ausencia_dados(dados, nomes_arquivos.get('pagamentos'), nomes_arquivos.get('contas'))
    metrics.update(analise_ausencia)
    
    # Processar planilha de PAGAMENTOS - apenas válidos
    if 'pagamentos' in dados and not dados['pagamentos'].empty:
        df_original = dados['pagamentos']
        
        # Filtrar apenas pagamentos válidos (com número de conta)
        df = filtrar_pagamentos_validos(df_original)
        
        # NOVO: Analisar problemas com CPF
        metrics['problemas_cpf'] = identificar_cpfs_problematicos(df)
        
        # Resto do processamento permanece igual...
        if df.empty:
            return metrics
        
        # Beneficiários únicos
        coluna_beneficiario = obter_coluna_nome(df)
        if coluna_beneficiario:
            metrics['beneficiarios_unicos'] = df[coluna_beneficiario].nunique()
        
        # Total de pagamentos VÁLIDOS
        metrics['total_pagamentos'] = len(df)
        
        # Contas únicas (da planilha de pagamentos VÁLIDOS)
        coluna_conta = obter_coluna_conta(df)
        if coluna_conta:
            metrics['contas_unicas'] = df[coluna_conta].nunique()
            
            # Detectar duplicidades detalhadas
            duplicidades = detectar_pagamentos_duplicados(df)
            metrics['duplicidades_detalhadas'] = duplicidades
            metrics['pagamentos_duplicados'] = duplicidades['total_contas_duplicadas']
            metrics['valor_total_duplicados'] = duplicidades['valor_total_duplicados']
        
        # Projetos ativos
        if 'Projeto' in df.columns:
            metrics['projetos_ativos'] = df['Projeto'].nunique()
        
        # Valor total
        if 'Valor_Limpo' in df.columns:
            metrics['valor_total'] = df['Valor_Limpo'].sum()
        
        # CPFs duplicados
        if 'CPF' in df.columns:
            cpfs_duplicados = df[df.duplicated(['CPF'], keep=False)]
            metrics['total_cpfs_duplicados'] = cpfs_duplicados['CPF'].nunique()
    
    # Processar planilha de ABERTURA DE CONTAS
    if 'contas' in dados and not dados['contas'].empty:
        df_contas = dados['contas']
        
        # Total de contas abertas
        metrics['total_contas_abertas'] = len(df_contas)
        
        # Beneficiários únicos na planilha de contas
        coluna_nome = obter_coluna_nome(df_contas)
        if coluna_nome:
            metrics['beneficiarios_contas'] = df_contas[coluna_nome].nunique()
        
        # Se não há planilha de pagamentos, usar contas como referência
        if 'pagamentos' not in dados or dados['pagamentos'].empty:
            metrics['contas_unicas'] = metrics['total_contas_abertas']
            if 'Projeto' in df_contas.columns:
                metrics['projetos_ativos'] = df_contas['Projeto'].nunique()
    
    # Detectar pagamentos pendentes
    pendentes = detectar_pagamentos_pendentes(dados)
    metrics['pagamentos_pendentes'] = pendentes
    
    return metrics

# [MANTER TODAS AS OUTRAS FUNÇÕES EXISTENTES]
# ... (manter: filtrar_pagamentos_validos, detectar_pagamentos_duplicados, etc.)

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
    
    # Verificar se há dados para processar de forma segura
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
    
    # [MANTER O RESTO DAS ABAS EXISTENTES - tab3, tab4, tab5]
    with tab3:
        st.header("Análise de Duplicidades")
        
        if duplicidades.get('total_contas_duplicadas', 0) > 0:
            # ... (manter conteúdo existente da tab3)
            pass
        else:
            st.success("✅ Nenhuma duplicidade detectada nos pagamentos válidos")
    
    with tab4:
        st.header("Pagamentos Pendentes")
        
        if pendentes.get('total_contas_sem_pagamento', 0) > 0:
            # ... (manter conteúdo existente da tab4)
            pass
        else:
            st.success("✅ Todos as contas abertas possuem pagamentos registrados")
    
    with tab5:
        st.header("Registros sem Número de Conta")
        
        if metrics.get('total_registros_invalidos', 0) > 0:
            # ... (manter conteúdo existente da tab5)
            pass
        else:
            st.success("✅ Todos os registros possuem número de conta e são considerados pagamentos válidos")
    
    with tab6:
        st.header("Relatórios e Exportações")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.subheader("Relatório Executivo (PDF)")
            if st.button("📄 Gerar Relatório PDF", type="primary", key="pdf_button"):
                with st.spinner("Gerando relatório PDF..."):
                    pdf_bytes = gerar_pdf_executivo(dados, metrics, nomes_arquivos)
                    if pdf_bytes:
                        st.success("✅ Relatório PDF gerado com sucesso!")
                        b64 = base64.b64encode(pdf_bytes).decode()
                        href = f'<a href="data:application/pdf;base64,{b64}" download="relatorio_pot_{data_hora_arquivo_brasilia()}.pdf">📥 Baixar Relatório PDF</a>'
                        st.markdown(href, unsafe_allow_html=True)
        
        with col2:
            st.subheader("Dados Completos (Excel)")
            if st.button("📊 Gerar Excel Completo", key="excel_button"):
                with st.spinner("Gerando arquivo Excel..."):
                    excel_bytes = gerar_excel_completo(dados, metrics)
                    if excel_bytes:
                        st.success("✅ Arquivo Excel gerado com sucesso!")
                        b64 = base64.b64encode(excel_bytes).decode()
                        href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="dados_pot_{data_hora_arquivo_brasilia()}.xlsx">📥 Baixar Excel Completo</a>'
                        st.markdown(href, unsafe_allow_html=True)
        
        # NOVA COLUNA: Planilha de Ajustes
        with col3:
            st.subheader("🛠️ Planilha de Ajustes")
            st.info("Gera planilha com todos os ajustes realizados nos dados")
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

if __name__ == "__main__":
    main()
