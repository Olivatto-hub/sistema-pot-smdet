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

# Função para obter data/hora no fuso horário de Brasília (São Paulo)
def agora_brasilia():
    """Retorna a data e hora atual no fuso horário de Brasília"""
    fuso_brasilia = timezone(timedelta(hours=-3))
    return datetime.now(timezone.utc).astimezone(fuso_brasilia)

def data_atual_brasilia():
    """Retorna a data atual no formato dd/mm/aaaa no fuso de Brasília"""
    return agora_brasilia().strftime("%d/%m/%Y")

def data_hora_atual_brasilia():
    """Retorna a data e hora atual no formato dd/mm/aaaa às HH:MM no fuso de Brasília"""
    return agora_brasilia().strftime("%d/%m/%Y às %H:%M")

def data_hora_arquivo_brasilia():
    """Retorna a data e hora atual no formato para nome de arquivo no fuso de Brasília"""
    return agora_brasilia().strftime("%Y%m%d_%H%M")

# Sistema de autenticação simples CORRIGIDO
def autenticar():
    st.sidebar.title("Sistema POT - SMDET")
    st.sidebar.markdown("**Prefeitura de São Paulo**")
    st.sidebar.markdown("**Secretaria Municipal do Desenvolvimento Econômico e Trabalho**")
    st.sidebar.markdown("---")
    
    email = st.sidebar.text_input("Email @prefeitura.sp.gov.br")
    
    # VERIFICAÇÃO CORRIGIDA - só mostra aviso mas não para execução
    if email and not email.endswith('@prefeitura.sp.gov.br'):
        st.sidebar.warning("⚠️ Use email corporativo @prefeitura.sp.gov.br")
        # Remove o st.stop() para permitir continuar
    
    return email

# Função auxiliar para obter coluna de conta
def obter_coluna_conta(df):
    """Identifica a coluna que contém o número da conta"""
    colunas_conta = ['Num Cartao', 'Num_Cartao', 'Conta', 'Número da Conta', 'Numero_Conta']
    for coluna in colunas_conta:
        if coluna in df.columns:
            return coluna
    return None

# Função auxiliar para obter coluna de nome/beneficiário
def obter_coluna_nome(df):
    """Identifica a coluna que contém o nome do beneficiário"""
    colunas_nome = ['Beneficiario', 'Beneficiário', 'Nome', 'Nome Completo']
    for coluna in colunas_nome:
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

# NOVA FUNÇÃO: Identificar e remover linha de totais
def remover_linha_totais(df):
    """Identifica e remove a linha de totais da planilha (última linha com valores somados)"""
    if df.empty:
        return df
    
    df_limpo = df.copy()
    
    # Padrões que indicam linha de totais
    padroes_totais = [
        'total', 'Total', 'TOTAL', 'soma', 'Soma', 'SOMA',
        'geral', 'Geral', 'GERAL', 'resultado', 'Resultado', 'RESULTADO'
    ]
    
    # Verificar a última linha
    ultima_linha = df_limpo.iloc[-1]
    
    # Critérios para identificar linha de totais:
    linha_eh_total = False
    
    # 1. Verificar se há texto indicando total em qualquer coluna
    for coluna in df_limpo.columns:
        if df_limpo[coluna].dtype == 'object':
            valor = str(ultima_linha[coluna]) if pd.notna(ultima_linha[coluna]) else ''
            if any(padrao in valor for padrao in padroes_totais):
                linha_eh_total = True
                break
    
    # 2. Verificar se a linha tem muitos campos vazios mas valores numéricos altos
    if not linha_eh_total:
        campos_vazios = 0
        campos_preenchidos = 0
        valor_total_linha = 0
        
        for coluna in df_limpo.columns:
            valor = ultima_linha[coluna]
            if pd.isna(valor) or str(valor).strip() in ['', 'NaN', 'None']:
                campos_vazios += 1
            else:
                campos_preenchidos += 1
                # Verificar se é valor monetário alto
                if coluna in ['Valor', 'Valor_Limpo'] and pd.notna(valor):
                    try:
                        valor_num = float(valor)
                        valor_total_linha = valor_num
                    except:
                        pass
        
        # Se tem muitos campos vazios mas um valor alto, provavelmente é linha de total
        if campos_vazios > campos_preenchidos and valor_total_linha > 1000:
            linha_eh_total = True
    
    # 3. Verificar se a linha tem número de conta vazio mas valor preenchido
    coluna_conta = obter_coluna_conta(df_limpo)
    if not linha_eh_total and coluna_conta:
        conta_vazia = pd.isna(ultima_linha[coluna_conta]) or str(ultima_linha[coluna_conta]).strip() == ''
        valor_preenchido = 'Valor' in df_limpo.columns and pd.notna(ultima_linha['Valor'])
        
        if conta_vazia and valor_preenchido:
            linha_eh_total = True
    
    # Remover a linha se for identificada como total
    if linha_eh_total:
        df_limpo = df_limpo.iloc[:-1].copy()
        st.sidebar.info(f"📝 Linha de totais identificada e removida: {len(df)} → {len(df_limpo)} registros")
    
    return df_limpo

# FUNÇÃO CORRIGIDA: Filtrar apenas pagamentos válidos (com número de conta)
def filtrar_pagamentos_validos(df):
    """Filtra apenas os registros que possuem número de conta (pagamentos válidos)"""
    coluna_conta = obter_coluna_conta(df)
    
    if not coluna_conta:
        return df
    
    # Filtrar apenas registros com número de conta preenchido
    df_filtrado = df[df[coluna_conta].notna() & (df[coluna_conta].astype(str).str.strip() != '')].copy()
    
    return df_filtrado

# FUNÇÃO CORRIGIDA: Detectar pagamentos duplicados com detalhes COMPLETOS
def detectar_pagamentos_duplicados(df):
    """Detecta pagamentos duplicados por número de conta e retorna detalhes completos"""
    duplicidades = {
        'contas_duplicadas': pd.DataFrame(),
        'total_contas_duplicadas': 0,
        'total_pagamentos_duplicados': 0,
        'valor_total_duplicados': 0,
        'resumo_duplicidades': pd.DataFrame(),
        'contas_com_multiplos_pagamentos': [],
        'detalhes_completos_duplicidades': pd.DataFrame()
    }
    
    # CORREÇÃO: Filtrar apenas pagamentos válidos (com número de conta)
    df = filtrar_pagamentos_validos(df)
    
    if df.empty:
        return duplicidades
    
    coluna_conta = obter_coluna_conta(df)
    coluna_nome = obter_coluna_nome(df)
    
    if not coluna_conta:
        return duplicidades
    
    # Encontrar contas com múltiplos pagamentos
    contagem_por_conta = df[coluna_conta].value_counts()
    contas_com_multiplos = contagem_por_conta[contagem_por_conta > 1].index.tolist()
    
    duplicidades['contas_com_multiplos_pagamentos'] = contas_com_multiplos
    
    if not contas_com_multiplos:
        return duplicidades
    
    # Filtrar apenas os registros duplicados
    df_duplicados = df[df[coluna_conta].isin(contas_com_multiplos)].copy()
    
    # Ordenar por conta e data (se disponível)
    colunas_ordenacao = [coluna_conta]
    colunas_data = ['Data', 'Data Pagto', 'Data_Pagto', 'DataPagto']
    for col_data in colunas_data:
        if col_data in df_duplicados.columns:
            colunas_ordenacao.append(col_data)
            break
    
    df_duplicados = df_duplicados.sort_values(by=colunas_ordenacao)
    
    # Adicionar contador de ocorrências por conta
    df_duplicados['Ocorrencia'] = df_duplicados.groupby(coluna_conta).cumcount() + 1
    df_duplicados['Total_Ocorrencias'] = df_duplicados.groupby(coluna_conta)[coluna_conta].transform('count')
    
    # Preparar dados completos para exibição - TODOS os campos importantes
    colunas_exibicao_completas = [coluna_conta, 'Ocorrencia', 'Total_Ocorrencias']
    
    if coluna_nome:
        colunas_exibicao_completas.append(coluna_nome)
    
    if 'CPF' in df_duplicados.columns:
        colunas_exibicao_completas.append('CPF')
    
    # Adicionar colunas de data
    for col_data in colunas_data:
        if col_data in df_duplicados.columns:
            colunas_exibicao_completas.append(col_data)
            break
    
    if 'Valor' in df_duplicados.columns:
        colunas_exibicao_completas.append('Valor')
    
    if 'Valor_Limpo' in df_duplicados.columns:
        colunas_exibicao_completas.append('Valor_Limpo')
    
    if 'Projeto' in df_duplicados.columns:
        colunas_exibicao_completas.append('Projeto')
    
    if 'Status' in df_duplicados.columns:
        colunas_exibicao_completas.append('Status')
    
    # Atualizar métricas
    duplicidades['contas_duplicadas'] = df_duplicados[colunas_exibicao_completas]
    duplicidades['detalhes_completos_duplicidades'] = df_duplicados[colunas_exibicao_completas]
    duplicidades['total_contas_duplicadas'] = len(contas_com_multiplos)
    duplicidades['total_pagamentos_duplicados'] = len(df_duplicados)
    
    if 'Valor_Limpo' in df_duplicados.columns:
        duplicidades['valor_total_duplicados'] = df_duplicados['Valor_Limpo'].sum()
    
    # Criar resumo por conta
    resumo = []
    for conta in contas_com_multiplos:
        registros_conta = df_duplicados[df_duplicados[coluna_conta] == conta]
        primeiro_registro = registros_conta.iloc[0]
        
        info_conta = {
            'Conta': conta,
            'Total_Pagamentos': len(registros_conta),
            'Valor_Total': registros_conta['Valor_Limpo'].sum() if 'Valor_Limpo' in registros_conta.columns else 0,
            'Pagamentos_Extras': len(registros_conta) - 1
        }
        
        if coluna_nome:
            info_conta['Nome'] = primeiro_registro[coluna_nome]
        
        if 'CPF' in registros_conta.columns:
            info_conta['CPF'] = primeiro_registro['CPF']
        
        # Datas dos pagamentos
        datas = []
        for col_data in colunas_data:
            if col_data in registros_conta.columns:
                datas = registros_conta[col_data].dropna().unique().tolist()
                if datas:
                    info_conta['Datas_Pagamentos'] = ', '.join([str(d) for d in datas])
                    break
        
        resumo.append(info_conta)
    
    duplicidades['resumo_duplicidades'] = pd.DataFrame(resumo)
    
    return duplicidades

# FUNÇÃO: Detectar pagamentos pendentes
def detectar_pagamentos_pendentes(dados):
    """Detecta possíveis pagamentos pendentes comparando contas abertas com pagamentos realizados"""
    pendentes = {
        'contas_sem_pagamento': pd.DataFrame(),
        'total_contas_sem_pagamento': 0,
        'beneficiarios_sem_pagamento': 0
    }
    
    # Só funciona se tivermos ambas as planilhas
    if 'contas' not in dados or dados['contas'].empty or 'pagamentos' not in dados or dados['pagamentos'].empty:
        return pendentes
    
    df_contas = dados['contas']
    df_pagamentos = dados['pagamentos']
    
    coluna_conta_contas = obter_coluna_conta(df_contas)
    coluna_conta_pagamentos = obter_coluna_conta(df_pagamentos)
    coluna_nome_contas = obter_coluna_nome(df_contas)
    
    if not coluna_conta_contas or not coluna_conta_pagamentos:
        return pendentes
    
    # CORREÇÃO: Filtrar apenas pagamentos válidos (com número de conta)
    df_pagamentos_validos = filtrar_pagamentos_validos(df_pagamentos)
    
    # Encontrar contas que estão na planilha de contas mas não na de pagamentos
    contas_com_pagamento = df_pagamentos_validos[coluna_conta_pagamentos].dropna().unique()
    contas_abertas = df_contas[coluna_conta_contas].dropna().unique()
    
    contas_sem_pagamento = [conta for conta in contas_abertas if conta not in contas_com_pagamento]
    
    if not contas_sem_pagamento:
        return pendentes
    
    # Filtrar contas sem pagamento
    df_contas_sem_pagamento = df_contas[df_contas[coluna_conta_contas].isin(contas_sem_pagamento)].copy()
    
    # Preparar colunas para exibição
    colunas_exibicao = [coluna_conta_contas]
    
    if coluna_nome_contas:
        colunas_exibicao.append(coluna_nome_contas)
    
    if 'CPF' in df_contas_sem_pagamento.columns:
        colunas_exibicao.append('CPF')
    
    if 'Projeto' in df_contas_sem_pagamento.columns:
        colunas_exibicao.append('Projeto')
    
    if 'Data_Abertura' in df_contas_sem_pagamento.columns:
        colunas_exibicao.append('Data_Abertura')
    elif 'Data' in df_contas_sem_pagamento.columns:
        colunas_exibicao.append('Data')
    
    # Adicionar status
    df_contas_sem_pagamento['Status'] = 'Aguardando Pagamento'
    
    pendentes['contas_sem_pagamento'] = df_contas_sem_pagamento[colunas_exibicao + ['Status']]
    pendentes['total_contas_sem_pagamento'] = len(contas_sem_pagamento)
    pendentes['beneficiarios_sem_pagamento'] = df_contas_sem_pagamento[coluna_nome_contas].nunique() if coluna_nome_contas else 0
    
    return pendentes

# NOVA FUNÇÃO: Processar CPF para manter apenas números
def processar_cpf(cpf):
    """Processa CPF, mantendo apenas números e completando com zeros à esquerda"""
    if pd.isna(cpf) or cpf in ['', 'NaN', 'None', 'nan', 'None', 'NULL']:
        return ''  # Manver como string vazia para campos em branco
    
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

# FUNÇÃO MELHORADA: Analisar ausência de dados considerando apenas pagamentos válidos
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
        'registros_validos_com_letras': 0,
        'cpfs_com_zeros_adicional': 0,
        'cpfs_formatos_diferentes': 0,
        'nome_arquivo_pagamentos': nome_arquivo_pagamentos,
        'nome_arquivo_contas': nome_arquivo_contas,
        'rgs_com_letras_especificas': {}
    }
    
    if 'pagamentos' in dados and not dados['pagamentos'].empty:
        # CORREÇÃO: Usar dados originais para análise de ausência
        df = dados['pagamentos'].copy()
        
        # NOVO: Adicionar coluna com número da linha original
        df['Linha_Planilha_Original'] = df.index + 2
        
        # Contar documentos padronizados
        colunas_docs = ['RG', 'CPF']
        for coluna in colunas_docs:
            if coluna in df.columns:
                docs_originais = len(df[df[coluna].notna()])
                analise_ausencia['documentos_padronizados'] += docs_originais
        
        # CORREÇÃO: Contar RGs válidos com QUALQUER letra
        if 'RG' in df.columns:
            rgs_com_letras = df[df['RG'].astype(str).str.contains(r'[A-Za-z]', na=False)]
            analise_ausencia['registros_validos_com_letras'] = len(rgs_com_letras)
            
            # Detalhar quais letras específicas foram encontradas
            letras_encontradas = {}
            for _, row in rgs_com_letras.iterrows():
                rg_str = str(row['RG'])
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
                (df['CPF'].astype(str).str.strip() != '')
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
                (df['CPF'].astype(str).str.strip() == '')
            )
            
            cpfs_ausentes = df[mask_cpf_ausente]
            registros_problematicos.extend(cpfs_ausentes.index.tolist())
        
        # 2. Número da conta ausente
        coluna_conta = obter_coluna_conta(df)
        if coluna_conta:
            mask_conta_ausente = (
                df[coluna_conta].isna() | 
                (df[coluna_conta].astype(str).str.strip() == '')
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
                    (df[coluna].astype(str).str.strip() == '')
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
                    elif col in df.columns:
                        info_ausencia[col] = ''
                    else:
                        info_ausencia[col] = ''
                
                # Marcar campos problemáticos
                problemas = []
                if 'CPF' in df.columns and (pd.isna(registro['CPF']) or str(registro['CPF']).strip() == ''):
                    problemas.append('CPF ausente')
                
                if coluna_conta and (pd.isna(registro[coluna_conta]) or str(registro[coluna_conta]).strip() == ''):
                    problemas.append('Número da conta ausente')
                
                if 'Valor' in df.columns and (pd.isna(registro['Valor']) or registro.get('Valor_Limpo', 0) == 0):
                    problemas.append('Valor ausente ou zero')
                
                info_ausencia['Problemas_Identificados'] = ', '.join(problemas) if problemas else 'Dados OK'
                resumo.append(info_ausencia)
            
            analise_ausencia['resumo_ausencias'] = pd.DataFrame(resumo)
    
    return analise_ausencia

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

# CORREÇÃO: Função para processar dados principais - Considera apenas pagamentos válidos
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
        'problemas_cpf': {},  # NOVO: Análise de problemas com CPF
        'linha_totais_removida': False  # NOVO: Indicador se linha de totais foi removida
    }
    
    # Combinar com análise de ausência de dados
    analise_ausencia = analisar_ausencia_dados(dados, nomes_arquivos.get('pagamentos'), nomes_arquivos.get('contas'))
    metrics.update(analise_ausencia)
    
    # CORREÇÃO: Processar planilha de PAGAMENTOS - apenas válidos
    if 'pagamentos' in dados and not dados['pagamentos'].empty:
        df_original = dados['pagamentos']
        
        # NOVO: Remover linha de totais antes de qualquer processamento
        df_sem_totais = remover_linha_totais(df_original)
        if len(df_sem_totais) < len(df_original):
            metrics['linha_totais_removida'] = True
        
        # CORREÇÃO: Filtrar apenas pagamentos válidos (com número de conta)
        df = filtrar_pagamentos_validos(df_sem_totais)
        
        # NOVO: Contar registros inválidos (sem número de conta)
        coluna_conta = obter_coluna_conta(df_sem_totais)
        if coluna_conta:
            registros_invalidos = df_sem_totais[
                df_sem_totais[coluna_conta].isna() | 
                (df_sem_totais[coluna_conta].astype(str).str.strip() == '')
            ]
            metrics['total_registros_invalidos'] = len(registros_invalidos)
        
        # Se não há pagamentos válidos após filtrar, retornar métricas vazias
        if df.empty:
            return metrics
        
        # NOVO: Analisar problemas com CPF
        metrics['problemas_cpf'] = identificar_cpfs_problematicos(df)
        
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
    
    # CORREÇÃO: Processar planilha de ABERTURA DE CONTAS
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

# Sistema de upload de dados MELHORADO: capturar nomes dos arquivos
def carregar_dados():
    st.sidebar.header("📤 Carregar Dados Reais")
    
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
            
            # NOVO: Remover linha de totais antes do processamento
            df_pagamentos = remover_linha_totais(df_pagamentos)
            
            df_pagamentos = processar_colunas_data(df_pagamentos)
            df_pagamentos = processar_colunas_valor(df_pagamentos)
            df_pagamentos = padronizar_documentos(df_pagamentos)
            
            dados['pagamentos'] = df_pagamentos
            
            # CORREÇÃO: Mostrar estatísticas de pagamentos válidos vs inválidos
            df_pagamentos_validos = filtrar_pagamentos_validos(df_pagamentos)
            total_validos = len(df_pagamentos_validos)
            total_invalidos = len(df_pagamentos) - total_validos
            
            st.sidebar.success(f"✅ Pagamentos: {total_validos} válidos + {total_invalidos} sem conta - {upload_pagamentos.name}")
            
        except Exception as e:
            st.sidebar.error(f"❌ Erro ao carregar pagamentos: {str(e)}")
    
    # Carregar dados de abertura de contas
    if upload_contas is not None:
        try:
            if upload_contas.name.endswith('.xlsx'):
                df_contas = pd.read_excel(upload_contas)
            else:
                df_contas = pd.read_csv(upload_contas, encoding='utf-8', sep=';')
            
            nomes_arquivos['contas'] = upload_contas.name
            
            df_contas = processar_colunas_data(df_contas)
            df_contas = padronizar_documentos(df_contas)
            
            dados['contas'] = df_contas
            st.sidebar.success(f"✅ Contas: {len(dados['contas'])} registros - {upload_contas.name}")
        except Exception as e:
            st.sidebar.error(f"❌ Erro ao carregar contas: {str(e)}")
    
    return dados, nomes_arquivos

# Interface principal do sistema CORRIGIDA
def main():
    # Autenticação
    email = autenticar()
    
    if email:
        st.sidebar.success(f"✅ Acesso autorizado: {email}")
    else:
        st.sidebar.info("👆 Insira seu email para continuar")
    
    st.sidebar.markdown("---")
    
    # Carregar dados
    dados, nomes_arquivos = carregar_dados()
    
    # Verificar se há dados para processar
    tem_dados_pagamentos = 'pagamentos' in dados and not dados['pagamentos'].empty
    tem_dados_contas = 'contas' in dados and not dados['contas'].empty
    
    if not tem_dados_pagamentos and not tem_dados_contas:
        st.info("📊 Faça o upload das planilhas de pagamentos e/ou abertura de contas para iniciar a análise")
        
        # Mostrar exemplo de interface mesmo sem dados
        st.title("🏛️ Sistema POT - SMDET")
        st.markdown("### Análise de Pagamentos e Contas")
        st.markdown("---")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total de Pagamentos", "0")
        with col2:
            st.metric("Beneficiários Únicos", "0")
        with col3:
            st.metric("Valor Total", "R$ 0,00")
        
        return
    
    # Processar dados
    with st.spinner("🔄 Processando dados..."):
        metrics = processar_dados(dados, nomes_arquivos)
    
    # Interface principal
    st.title("🏛️ Sistema POT - SMDET")
    st.markdown("### Análise de Pagamentos e Contas")
    st.markdown(f"**Data da análise:** {data_hora_atual_brasilia()}")
    
    # NOVO: Mostrar informação sobre linha de totais removida
    if metrics.get('linha_totais_removida', False):
        st.info("📝 **Nota:** Linha de totais da planilha foi identificada e excluída da análise")
    
    st.markdown("---")
    
    # Métricas principais
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Total de Pagamentos", 
            formatar_brasileiro(metrics['total_pagamentos']),
            help="Pagamentos válidos com número de conta"
        )
    
    with col2:
        st.metric(
            "Beneficiários Únicos", 
            formatar_brasileiro(metrics['beneficiarios_unicos'])
        )
    
    with col3:
        st.metric(
            "Contas Únicas", 
            formatar_brasileiro(metrics['contas_unicas'])
        )
    
    with col4:
        st.metric(
            "Valor Total", 
            formatar_brasileiro(metrics['valor_total'], 'monetario')
        )
    
    # Segunda linha de métricas
    col5, col6, col7, col8 = st.columns(4)
    
    with col5:
        st.metric(
            "Pagamentos Duplicados", 
            formatar_brasileiro(metrics['pagamentos_duplicados']),
            delta=f"-{formatar_brasileiro(metrics['valor_total_duplicados'], 'monetario')}",
            delta_color="inverse",
            help="Contas com múltiplos pagamentos"
        )
    
    with col6:
        st.metric(
            "Contas Abertas", 
            formatar_brasileiro(metrics['total_contas_abertas'])
        )
    
    with col7:
        st.metric(
            "Projetos Ativos", 
            formatar_brasileiro(metrics['projetos_ativos'])
        )
    
    with col8:
        st.metric(
            "Registros com Problemas", 
            formatar_brasileiro(metrics['total_registros_criticos']),
            delta_color="inverse" if metrics['total_registros_criticos'] > 0 else "off"
        )
    
    st.markdown("---")
    
    # Abas para análises detalhadas
    tab1, tab2, tab3, tab4 = st.tabs([
        "📋 Visão Geral", 
        "⚠️ Duplicidades", 
        "⏳ Pagamentos Pendentes", 
        "🔍 Análise de Dados"
    ])
    
    with tab1:
        st.subheader("Resumo dos Dados")
        
        if tem_dados_pagamentos:
            st.write(f"**Planilha de Pagamentos:** {nomes_arquivos.get('pagamentos', 'N/A')}")
            st.write(f"**Total de registros:** {len(dados['pagamentos'])}")
            st.write(f"**Pagamentos válidos:** {metrics['total_pagamentos']}")
            st.write(f"**Registros sem conta:** {metrics['total_registros_invalidos']}")
            
            # NOVO: Informação sobre linha de totais
            if metrics.get('linha_totais_removida', False):
                st.write("🔍 **Linha de totais:** Identificada e removida da análise")
        
        if tem_dados_contas:
            st.write(f"**Planilha de Contas:** {nomes_arquivos.get('contas', 'N/A')}")
            st.write(f"**Total de contas:** {metrics['total_contas_abertas']}")
            st.write(f"**Beneficiários únicos:** {metrics['beneficiarios_contas']}")
    
    with tab2:
        st.subheader("Pagamentos Duplicados")
        
        if metrics['duplicidades_detalhadas']['total_contas_duplicadas'] > 0:
            st.warning(f"🚨 Foram encontradas {metrics['duplicidades_detalhadas']['total_contas_duplicadas']} contas com pagamentos duplicados")
            
            # Mostrar resumo das duplicidades
            if not metrics['duplicidades_detalhadas']['resumo_duplicidades'].empty:
                st.write("**Resumo das Duplicidades:**")
                st.dataframe(metrics['duplicidades_detalhadas']['resumo_duplicidades'])
            
            # Mostrar detalhes completos
            if not metrics['duplicidades_detalhadas']['detalhes_completos_duplicidades'].empty:
                st.write("**Detalhes Completos dos Pagamentos Duplicados:**")
                st.dataframe(metrics['duplicidades_detalhadas']['detalhes_completos_duplicidades'])
        else:
            st.success("✅ Nenhum pagamento duplicado encontrado")
    
    with tab3:
        st.subheader("Pagamentos Pendentes")
        
        if metrics['pagamentos_pendentes']['total_contas_sem_pagamento'] > 0:
            st.info(f"ℹ️ {metrics['pagamentos_pendentes']['total_contas_sem_pagamento']} contas aguardando pagamento")
            
            if not metrics['pagamentos_pendentes']['contas_sem_pagamento'].empty:
                st.write("**Contas sem Pagamento:**")
                st.dataframe(metrics['pagamentos_pendentes']['contas_sem_pagamento'])
        else:
            st.success("✅ Todas as contas abertas possuem pagamentos registrados")
    
    with tab4:
        st.subheader("Análise de Qualidade dos Dados")
        
        if metrics['total_registros_criticos'] > 0:
            st.error(f"❌ {metrics['total_registros_criticos']} registros com problemas críticos")
            
            if not metrics['resumo_ausencias'].empty:
                st.write("**Registros com Problemas:**")
                st.dataframe(metrics['resumo_ausencias'])
        else:
            st.success("✅ Todos os registros possuem dados essenciais preenchidos")
        
        # Mostrar problemas com CPF se houver
        if metrics['problemas_cpf']['total_problemas_cpf'] > 0:
            st.warning(f"⚠️ {metrics['problemas_cpf']['total_problemas_cpf']} CPFs com problemas de formatação")
            
            if not metrics['problemas_cpf']['detalhes_cpfs_problematicos'].empty:
                st.write("**Detalhes dos CPFs Problemáticos:**")
                st.dataframe(metrics['problemas_cpf']['detalhes_cpfs_problematicos'])

if __name__ == "__main__":
    main()
