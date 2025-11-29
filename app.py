# app.py
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timezone
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

# Função para obter data/hora no fuso horário de Brasília (São Paulo)
def agora_brasilia():
    """Retorna a data e hora atual no fuso horário de Brasília"""
    # Fuso horário de Brasília (UTC-3) - mesmo de São Paulo
    fuso_brasilia = timezone.utc.offset(datetime.now()) - timezone(timedelta(hours=-3)).utcoffset(datetime.now())
    return datetime.now(timezone.utc).astimezone(timezone(fuso_brasilia))

def data_atual_brasilia():
    """Retorna a data atual no formato dd/mm/aaaa no fuso de Brasília"""
    return agora_brasilia().strftime("%d/%m/%Y")

def data_hora_atual_brasilia():
    """Retorna a data e hora atual no formato dd/mm/aaaa às HH:MM no fuso de Brasília"""
    return agora_brasilia().strftime("%d/%m/%Y às %H:%M")

def data_hora_arquivo_brasilia():
    """Retorna a data e hora atual no formato para nome de arquivo no fuso de Brasília"""
    return agora_brasilia().strftime("%Y%m%d_%H%M")

# Sistema de autenticação simples
def autenticar():
    st.sidebar.title("Sistema POT - SMDET")
    st.sidebar.markdown("**Prefeitura de São Paulo**")
    st.sidebar.markdown("**Secretaria Municipal do Desenvolvimento Econômico e Trabalho**")
    st.sidebar.markdown("---")
    
    email = st.sidebar.text_input("Email @prefeitura.sp.gov.br")
    
    if email and not email.endswith('@prefeitura.sp.gov.br'):
        st.error("🚫 Acesso restrito aos servidores da Prefeitura de São Paulo")
        st.stop()
    
    return email

# Função auxiliar para obter coluna de conta
def obter_coluna_conta(df):
    """Identifica a coluna que contém o número da conta"""
    colunas_conta = ['Num Cartao', 'Num_Cartao', 'Conta', 'Número da Conta', 'Numero_Conta']
    for coluna in colunas_conta:
        if coluna in df.columns:
            return coluna
    return None

# Função auxiliar para formatar valores no padrão brasileiro
def formatar_brasileiro(valor, tipo='numero'):
    """Formata valores no padrão brasileiro"""
    if tipo == 'monetario':
        return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    elif tipo == 'numero':
        return f"{valor:,}".replace(',', '.')
    else:
        return str(valor)

# CORREÇÃO: Função para processar dados principais - AGORA considera ambas as planilhas
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
        'total_contas_abertas': 0,  # NOVO: Contas da planilha de abertura
        'beneficiarios_contas': 0   # NOVO: Beneficiários da planilha de abertura
    }
    
    # Combinar com análise de ausência de dados
    analise_ausencia = analisar_ausencia_dados(dados, nomes_arquivos.get('pagamentos'), nomes_arquivos.get('contas'))
    metrics.update(analise_ausencia)
    
    # CORREÇÃO: Processar planilha de PAGAMENTOS
    if not dados['pagamentos'].empty:
        df = dados['pagamentos']
        
        # Beneficiários únicos
        coluna_beneficiario = 'Beneficiario' if 'Beneficiario' in df.columns else 'Beneficiário'
        if coluna_beneficiario in df.columns:
            metrics['beneficiarios_unicos'] = df[coluna_beneficiario].nunique()
        
        # Total de pagamentos
        metrics['total_pagamentos'] = len(df)
        
        # Contas únicas (da planilha de pagamentos)
        coluna_conta = obter_coluna_conta(df)
        if coluna_conta:
            metrics['contas_unicas'] = df[coluna_conta].nunique()
            
            # Verificar duplicidades
            contas_duplicadas = df[df.duplicated([coluna_conta], keep=False)]
            if not contas_duplicadas.empty:
                metrics['pagamentos_duplicados'] = contas_duplicadas[coluna_conta].nunique()
                
                # Calcular valor total das duplicidades
                if 'Valor_Limpo' in contas_duplicadas.columns:
                    metrics['valor_total_duplicados'] = contas_duplicadas['Valor_Limpo'].sum()
        
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
    
    # CORREÇÃO: Processar planilha de ABERTURA DE CONTAS
    if not dados['contas'].empty:
        df_contas = dados['contas']
        
        # Total de contas abertas
        metrics['total_contas_abertas'] = len(df_contas)
        
        # Beneficiários únicos na planilha de contas
        coluna_nome = 'Nome' if 'Nome' in df_contas.columns else 'Beneficiario'
        if coluna_nome in df_contas.columns:
            metrics['beneficiarios_contas'] = df_contas[coluna_nome].nunique()
        
        # Se não há planilha de pagamentos, usar contas como referência
        if dados['pagamentos'].empty:
            metrics['contas_unicas'] = metrics['total_contas_abertas']
            if 'Projeto' in df_contas.columns:
                metrics['projetos_ativos'] = df_contas['Projeto'].nunique()
    
    return metrics

# NOVA FUNÇÃO: Processar CPF de forma inteligente
def processar_cpf(cpf):
    """Processa CPF, completando com zeros à esquerda e removendo caracteres especiais"""
    if pd.isna(cpf) or cpf in ['', 'NaN', 'None', 'nan']:
        return cpf
    
    cpf_str = str(cpf).strip()
    
    # Remover todos os caracteres não numéricos
    cpf_limpo = re.sub(r'[^\d]', '', cpf_str)
    
    # Completar com zeros à esquerda se tiver menos de 11 dígitos
    if cpf_limpo and len(cpf_limpo) < 11:
        cpf_limpo = cpf_limpo.zfill(11)
    
    return cpf_limpo

# FUNÇÃO CORRIGIDA: Padronizar documentos considerando TODAS as letras válidas em RGs
def padronizar_documentos(df):
    """Padroniza RGs e CPFs, aceitando todas as letras válidas em RGs"""
    df_processed = df.copy()
    
    # Colunas que podem conter documentos
    colunas_documentos = ['RG', 'CPF', 'Documento', 'Numero_Documento']
    
    for coluna in colunas_documentos:
        if coluna in df_processed.columns:
            try:
                if coluna == 'RG':
                    # CORREÇÃO: Para RG: manter números e TODAS as letras (A-Z) que podem aparecer em RGs
                    # Inclui X, V, W, Y, Z e outras letras que podem ser usadas em RGs
                    df_processed[coluna] = df_processed[coluna].astype(str).apply(
                        lambda x: re.sub(r'[^a-zA-Z0-9/]', '', x) if pd.notna(x) else x
                    )
                else:
                    # Para CPF: tratamento especial para diferentes formatos
                    df_processed[coluna] = df_processed[coluna].astype(str).apply(
                        lambda x: processar_cpf(x) if pd.notna(x) else x
                    )
                
            except Exception as e:
                st.warning(f"⚠️ Não foi possível padronizar a coluna '{coluna}': {str(e)}")
    
    return df_processed

# FUNÇÃO MELHORADA: Analisar ausência de dados considerando TODAS as letras válidas em RGs
def analisar_ausencia_dados(dados, nome_arquivo_pagamentos=None, nome_arquivo_contas=None):
    """Analisa e reporta apenas dados críticos realmente ausentes com info da planilha original"""
    analise_ausencia = {
        'registros_criticos_problematicos': [],
        'total_registros_criticos': 0,
        'colunas_com_ausencia_critica': {},
        'resumo_ausencias': pd.DataFrame(),
        'registros_problema_detalhados': pd.DataFrame(),
        'documentos_padronizados': 0,
        'tipos_problemas': {},
        'registros_validos_com_letras': 0,  # CORREÇÃO: Agora conta TODAS as letras válidas
        'cpfs_com_zeros_adicional': 0,
        'cpfs_formatos_diferentes': 0,
        'nome_arquivo_pagamentos': nome_arquivo_pagamentos,
        'nome_arquivo_contas': nome_arquivo_contas,
        'rgs_com_letras_especificas': {}  # NOVO: Detalha quais letras foram encontradas
    }
    
    if not dados['pagamentos'].empty:
        df = dados['pagamentos'].copy()
        
        # NOVO: Adicionar coluna com número da linha original (considerando que a planilha começa na linha 2 - linha 1 é cabeçalho)
        df['Linha_Planilha_Original'] = df.index + 2
        
        # Contar documentos padronizados
        colunas_docs = ['RG', 'CPF']
        for coluna in colunas_docs:
            if coluna in df.columns:
                docs_originais = len(df[df[coluna].notna()])
                analise_ausencia['documentos_padronizados'] += docs_originais
        
        # CORREÇÃO: Contar RGs válidos com QUALQUER letra (não apenas X)
        if 'RG' in df.columns:
            # Expressão regular para encontrar RGs com qualquer letra (A-Z)
            rgs_com_letras = df[df['RG'].astype(str).str.contains(r'[A-Za-z]', na=False)]
            analise_ausencia['registros_validos_com_letras'] = len(rgs_com_letras)
            
            # NOVO: Detalhar quais letras específicas foram encontradas
            letras_encontradas = {}
            for _, row in rgs_com_letras.iterrows():
                rg_str = str(row['RG'])
                # Encontrar todas as letras no RG
                letras = re.findall(r'[A-Za-z]', rg_str)
                for letra in letras:
                    letra_upper = letra.upper()
                    letras_encontradas[letra_upper] = letras_encontradas.get(letra_upper, 0) + 1
            
            analise_ausencia['rgs_com_letras_especificas'] = letras_encontradas
        
        # Contar CPFs que receberam zeros à esquerda
        if 'CPF' in df.columns:
            cpfs_com_zeros = df[
                df['CPF'].notna() & 
                (df['CPF'].astype(str).str.len() < 11) &
                (df['CPF'].astype(str).str.strip() != '') &
                (df['CPF'].astype(str).str.strip() != 'NaN') &
                (df['CPF'].astype(str).str.strip() != 'None')
            ]
            analise_ausencia['cpfs_com_zeros_adicional'] = len(cpfs_com_zeros)
            
            cpfs_com_formatos = df[
                df['CPF'].notna() & 
                (df['CPF'].astype(str).str.contains(r'[.-]', na=False))
            ]
            analise_ausencia['cpfs_formatos_diferentes'] = len(cpfs_com_formatos)
        
        # CRITÉRIO CORRIGIDO: Apenas dados realmente críticos ausentes
        registros_problematicos = []
        
        # 1. CPF COMPLETAMENTE AUSENTE
        if 'CPF' in df.columns:
            mask_cpf_ausente = (
                df['CPF'].isna() | 
                (df['CPF'].astype(str).str.strip() == '') |
                (df['CPF'].astype(str).str.strip() == 'NaN') |
                (df['CPF'].astype(str).str.strip() == 'None') |
                (df['CPF'].astype(str).str.strip() == 'nan')
            )
            
            cpfs_ausentes = df[mask_cpf_ausente]
            registros_problematicos.extend(cpfs_ausentes.index.tolist())
        
        # 2. Número da conta ausente
        coluna_conta = obter_coluna_conta(df)
        if coluna_conta:
            mask_conta_ausente = (
                df[coluna_conta].isna() | 
                (df[coluna_conta].astype(str).str.strip() == '') |
                (df[coluna_conta].astype(str).str.strip() == 'NaN') |
                (df[coluna_conta].astype(str).str.strip() == 'None')
            )
            contas_ausentes = df[mask_conta_ausente]
            for idx in contas_ausentes.index:
                if idx not in registros_problematicos:
                    registros_problematicos.append(idx)
        
        # 3. Valor ausente ou zero
        if 'Valor' in df.columns:
            mask_valor_invalido = (
                df['Valor'].isna() | 
                (df['Valor'].astype(str).str.strip() == '') |
                (df['Valor'].astype(str).str.strip() == 'NaN') |
                (df['Valor'].astype(str).str.strip() == 'None') |
                (df['Valor_Limpo'] == 0)
            )
            valores_invalidos = df[mask_valor_invalido]
            for idx in valores_invalidos.index:
                if idx not in registros_problematicos:
                    registros_problematicos.append(idx)
        
        # Atualizar análise
        analise_ausencia['registros_criticos_problematicos'] = registros_problematicos
        analise_ausencia['total_registros_criticos'] = len(registros_problematicos)
        
        if registros_problematicos:
            analise_ausencia['registros_problema_detalhados'] = df.loc[registros_problematicos].copy()
        
        # Analisar ausência por coluna crítica
        colunas_criticas = ['CPF', 'Num Cartao', 'Num_Cartao', 'Valor']
        for coluna in colunas_criticas:
            if coluna in df.columns:
                mask_ausente = (
                    df[coluna].isna() | 
                    (df[coluna].astype(str).str.strip() == '') |
                    (df[coluna].astype(str).str.strip() == 'NaN') |
                    (df[coluna].astype(str).str.strip() == 'None')
                )
                ausentes = df[mask_ausente]
                if len(ausentes) > 0:
                    analise_ausencia['colunas_com_ausencia_critica'][coluna] = len(ausentes)
                    analise_ausencia['tipos_problemas'][f'Sem {coluna}'] = len(ausentes)
        
        # Criar resumo de ausências com informações da planilha original
        if registros_problematicos:
            resumo = []
            for idx in registros_problematicos[:100]:
                registro = df.loc[idx]
                info_ausencia = {
                    'Indice_Registro': idx,
                    'Linha_Planilha': registro.get('Linha_Planilha_Original', idx + 2),
                    'Planilha_Origem': nome_arquivo_pagamentos or 'Pagamentos'
                }
                
                colunas_interesse = [
                    'CPF', 'RG', 'Projeto', 'Valor', 'Beneficiario', 'Beneficiário', 'Nome',
                    'Data', 'Data Pagto', 'Data_Pagto', 'DataPagto',
                    'Num Cartao', 'Num_Cartao', 'Conta', 'Status'
                ]
                
                for col in colunas_interesse:
                    if col in df.columns and pd.notna(registro[col]):
                        valor = str(registro[col])
                        if len(valor) > 50:
                            valor = valor[:47] + "..."
                        info_ausencia[col] = valor
                    else:
                        info_ausencia[col] = 'N/A'
                
                # Marcar campos problemáticos
                problemas = []
                if 'CPF' in df.columns and (pd.isna(registro['CPF']) or str(registro['CPF']).strip() in ['', 'NaN', 'None', 'nan']):
                    problemas.append('CPF ausente')
                
                if coluna_conta and (pd.isna(registro[coluna_conta]) or str(registro[coluna_conta]).strip() in ['', 'NaN', 'None', 'nan']):
                    problemas.append('Número da conta ausente')
                
                if 'Valor' in df.columns and (pd.isna(registro['Valor']) or registro.get('Valor_Limpo', 0) == 0):
                    problemas.append('Valor ausente ou zero')
                
                info_ausencia['Problemas_Identificados'] = ', '.join(problemas) if problemas else 'Dados OK'
                resumo.append(info_ausencia)
            
            analise_ausencia['resumo_ausencias'] = pd.DataFrame(resumo)
    
    return analise_ausencia

# CORREÇÃO: Nova função para processar colunas de data
def processar_colunas_data(df):
    """Converte colunas de data de formato numérico do Excel para datas legíveis"""
    df_processed = df.copy()
    
    colunas_data = ['Data', 'Data Pagto', 'Data_Pagto', 'DataPagto']
    
    for coluna in colunas_data:
        if coluna in df_processed.columns:
            try:
                if df_processed[coluna].dtype in ['int64', 'float64']:
                    df_processed[coluna] = pd.to_datetime(
                        df_processed[coluna], 
                        unit='D', 
                        origin='1899-12-30',
                        errors='coerce'
                    )
                else:
                    df_processed[coluna] = pd.to_datetime(
                        df_processed[coluna], 
                        errors='coerce'
                    )
                
                df_processed[coluna] = df_processed[coluna].dt.strftime('%d/%m/%Y')
                
            except Exception as e:
                st.warning(f"⚠️ Não foi possível processar a coluna de data '{coluna}': {str(e)}")
    
    return df_processed

# CORREÇÃO: Nova função para processar colunas de valor
def processar_colunas_valor(df):
    """Processa colunas de valor para formato brasileiro"""
    df_processed = df.copy()
    
    if 'Valor' in df_processed.columns:
        try:
            if df_processed['Valor'].dtype == 'object':
                df_processed['Valor_Limpo'] = (
                    df_processed['Valor']
                    .astype(str)
                    .str.replace('R$', '')
                    .str.replace('R$ ', '')
                    .str.replace('.', '')
                    .str.replace(',', '.')
                    .str.replace(' ', '')
                    .astype(float)
                )
            else:
                df_processed['Valor_Limpo'] = df_processed['Valor'].astype(float)
                
        except Exception as e:
            st.warning(f"⚠️ Erro ao processar valores: {str(e)}")
            df_processed['Valor_Limpo'] = 0.0
    
    return df_processed

# NOVA FUNÇÃO: Gerar PDF Executivo CORRIGIDA
def gerar_pdf_executivo(dados, metrics, nomes_arquivos):
    """Gera relatório PDF executivo profissional"""
    try:
        pdf = FPDF()
        pdf.add_page()
        
        # Configurações de fonte
        pdf.set_font('Arial', 'B', 16)
        
        # CABEÇALHO OFICIAL
        # Logo/Texto da Prefeitura
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
            # Remover caracteres especiais do nome do arquivo
            nome_arquivo = nomes_arquivos["pagamentos"].encode('latin-1', 'ignore').decode('latin-1')
            pdf.cell(0, 6, f'Planilha de Pagamentos: {nome_arquivo}', 0, 1)
        if nomes_arquivos.get('contas'):
            # Remover caracteres especiais do nome do arquivo
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
        
        if metrics.get('total_registros_criticos', 0) > 0:
            tem_alertas = True
            pdf.set_font('Arial', 'B', 12)
            pdf.set_text_color(255, 0, 0)  # Vermelho para alertas
            pdf.cell(0, 8, 'ALERTAS CRITICOS IDENTIFICADOS', 0, 1)
            pdf.set_text_color(0, 0, 0)  # Voltar para preto
            pdf.set_font('Arial', '', 10)
            pdf.cell(0, 6, f'- Registros com dados criticos ausentes: {formatar_brasileiro(metrics["total_registros_criticos"], "numero")}', 0, 1)
            pdf.cell(0, 6, '  (CPF, numero da conta ou valor ausentes/zerados)', 0, 1)
            pdf.ln(4)
        
        if metrics.get('pagamentos_duplicados', 0) > 0:
            tem_alertas = True
            pdf.set_font('Arial', 'B', 12)
            pdf.set_text_color(255, 0, 0)
            pdf.cell(0, 8, 'DUPLICIDADES IDENTIFICADAS', 0, 1)
            pdf.set_text_color(0, 0, 0)
            pdf.set_font('Arial', '', 10)
            pdf.cell(0, 6, f'- Contas com pagamentos duplicados: {formatar_brasileiro(metrics["pagamentos_duplicados"], "numero")}', 0, 1)
            if metrics.get('valor_total_duplicados', 0) > 0:
                pdf.cell(0, 6, f'- Valor total em duplicidades: {formatar_brasileiro(metrics["valor_total_duplicados"], "monetario")}', 0, 1)
            pdf.ln(4)
        
        if not tem_alertas:
            pdf.set_font('Arial', 'B', 12)
            pdf.set_text_color(0, 128, 0)  # Verde para OK
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

# NOVA FUNÇÃO: Gerar Excel Completo (sem xlsxwriter)
def gerar_excel_completo(dados, metrics):
    """Gera arquivo Excel completo com os dados"""
    try:
        output = io.BytesIO()
        
        # Criar um arquivo Excel simples usando pandas
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Aba de Pagamentos
            if not dados['pagamentos'].empty:
                dados['pagamentos'].to_excel(writer, sheet_name='Pagamentos', index=False)
            
            # Aba de Contas
            if not dados['contas'].empty:
                dados['contas'].to_excel(writer, sheet_name='Contas', index=False)
            
            # Aba de Métricas
            metricas_df = pd.DataFrame([
                {'Métrica': 'Beneficiários Únicos', 'Valor': metrics.get('beneficiarios_unicos', 0)},
                {'Métrica': 'Total de Pagamentos', 'Valor': metrics.get('total_pagamentos', 0)},
                {'Métrica': 'Contas Únicas', 'Valor': metrics.get('contas_unicas', 0)},
                {'Métrica': 'Contas Abertas', 'Valor': metrics.get('total_contas_abertas', 0)},
                {'Métrica': 'Projetos Ativos', 'Valor': metrics.get('projetos_ativos', 0)},
                {'Métrica': 'Valor Total', 'Valor': metrics.get('valor_total', 0)},
                {'Métrica': 'Registros Críticos', 'Valor': metrics.get('total_registros_criticos', 0)},
                {'Métrica': 'Pagamentos Duplicados', 'Valor': metrics.get('pagamentos_duplicados', 0)}
            ])
            metricas_df.to_excel(writer, sheet_name='Métricas', index=False)
            
            # Aba de Problemas (se houver)
            if not metrics.get('resumo_ausencias', pd.DataFrame()).empty:
                metrics['resumo_ausencias'].to_excel(writer, sheet_name='Problemas_Identificados', index=False)
        
        output.seek(0)
        return output.getvalue()
    
    except Exception as e:
        st.error(f"Erro ao gerar Excel: {str(e)}")
        return None

# Sistema de upload de dados MELHORADO: capturar nomes dos arquivos
def carregar_dados():
    st.sidebar.header("📤 Carregar Dados Reais")
    
    # CORREÇÃO: File uploaders em português
    upload_pagamentos = st.sidebar.file_uploader(
        "Planilha de Pagamentos", 
        type=['xlsx', 'csv'],
        key="pagamentos",
        help="Arraste e solte o arquivo aqui ou clique para procurar"
    )
    
    upload_contas = st.sidebar.file_uploader(
        "Planilha de Abertura de Contas", 
        type=['xlsx', 'csv'],
        key="contas",
        help="Arraste e solte o arquivo aqui ou clique para procurar"
    )
    
    dados = {}
    nomes_arquivos = {}
    
    # Carregar dados de pagamentos
    if upload_pagamentos is not None:
        try:
            if upload_pagamentos.name.endswith('.xlsx'):
                df_pagamentos = pd.read_excel(upload_pagamentos)
            else:
                df_pagamentos = pd.read_csv(upload_pagamentos, encoding='utf-8', sep=';')
            
            nomes_arquivos['pagamentos'] = upload_pagamentos.name
            
            df_pagamentos = processar_colunas_data(df_pagamentos)
            df_pagamentos = processar_colunas_valor(df_pagamentos)
            df_pagamentos = padronizar_documentos(df_pagamentos)
            
            dados['pagamentos'] = df_pagamentos
            st.sidebar.success(f"✅ Pagamentos: {len(dados['pagamentos'])} registros - {upload_pagamentos.name}")
        except Exception as e:
            st.sidebar.error(f"❌ Erro ao carregar pag
