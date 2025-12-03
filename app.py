# app.py - SISTEMA POT SMDET COMPLETO E CORRIGIDO (SEM CHARDET)
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timezone, timedelta
import io
from fpdf import FPDF
import numpy as np
import re
import base64
import hashlib
import sqlite3
from sqlite3 import Error
import os
import json
import warnings
warnings.filterwarnings('ignore')

# Configuração da página
st.set_page_config(
    page_title="Sistema POT - SMDET",
    page_icon="🏛️",
    layout="wide"
)

# ============================================
# FUNÇÕES AUXILIARES
# ============================================

def agora_brasilia():
    """Retorna a data e hora atual no fuso horário de Brasília"""
    fuso_brasilia = timezone(timedelta(hours=-3))
    return datetime.now(timezone.utc).astimezone(fuso_brasilia)

def data_hora_atual_brasilia():
    """Retorna a data e hora atual no formato dd/mm/aaaa às HH:MM no fuso de Brasília"""
    return agora_brasilia().strftime("%d/%m/%Y às %H:%M")

def detectar_encoding_simples(arquivo):
    """
    Detecta encoding de forma simples sem chardet.
    Tenta encodings comuns para arquivos brasileiros.
    """
    encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252', 'windows-1252']
    
    # Ler uma amostra do arquivo
    raw_data = arquivo.read(10000)  # Ler os primeiros 10KB
    arquivo.seek(0)  # Voltar ao início
    
    for encoding in encodings:
        try:
            # Tentar decodificar com o encoding
            raw_data.decode(encoding)
            arquivo.seek(0)
            return encoding
        except UnicodeDecodeError:
            continue
    
    # Se nenhum funcionar, retornar utf-8 por padrão
    arquivo.seek(0)
    return 'utf-8'

def formatar_brasileiro(valor, tipo='numero'):
    """Formata valores no padrão brasileiro"""
    if pd.isna(valor):
        valor = 0
    
    try:
        if tipo == 'monetario':
            return f"R$ {float(valor):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        elif tipo == 'numero':
            return f"{int(valor):,}".replace(',', '.')
        else:
            return str(valor)
    except:
        return str(valor)

# ============================================
# DETECÇÃO AUTOMÁTICA DE COLUNAS
# ============================================

def detectar_coluna_conta(df):
    """Detecta automaticamente a coluna de número da conta"""
    colunas_possiveis = [
        'Num Cartao', 'NumCartao', 'Num_Cartao', 'NumCartão', 'NumCart„o',
        'Num Cartão', 'Num_Cartão', 'Cartao', 'Cartão', 'Conta',
        'Numero Conta', 'Numero_Conta', 'Número Conta', 'Número_Conta',
        'NumeroCartao', 'NumeroCartão', 'Numero_Cartao', 'Numero_Cartão',
        'Nº Cartão', 'Nº Cartao', 'Nº Conta', 'Numero do Cartão',
        'NRO CARTAO', 'NRO_CARTAO', 'NR_CARTAO', 'CARTAO'
    ]
    
    for coluna in df.columns:
        coluna_limpa = str(coluna).strip().upper()
        for padrao in colunas_possiveis:
            if padrao.upper() in coluna_limpa:
                return coluna
    
    # Se não encontrou por nome, procura por colunas que contenham números de conta
    for coluna in df.columns:
        if df[coluna].dtype == 'object':
            amostra = df[coluna].dropna().head(10).astype(str)
            # Verificar se contém números de 6+ dígitos
            if any(re.search(r'^\d{6,}$', str(x).strip()) for x in amostra):
                return coluna
    
    return None

def detectar_coluna_nome(df):
    """Detecta automaticamente a coluna de nome"""
    colunas_possiveis = [
        'Nome', 'Nome do beneficiário', 'Beneficiario', 'Beneficiário',
        'Participante', 'Nome Completo', 'NomeBeneficiario', 'Nome_Beneficiario',
        'NomeBeneficiário', 'Nome_Beneficiário', 'Nome do Beneficiario',
        'NOME', 'BENEFICIARIO', 'BENEFICIÁRIO', 'PARTICIPANTE'
    ]
    
    for coluna in df.columns:
        coluna_limpa = str(coluna).strip().upper()
        for padrao in colunas_possiveis:
            if padrao.upper() in coluna_limpa:
                return coluna
    
    return None

def detectar_coluna_valor(df):
    """Detecta automaticamente a coluna de valor pago"""
    colunas_prioridade = [
        'Valor Pagto', 'ValorPagto', 'Valor_Pagto', 'Valor Pago', 'ValorPago',
        'Valor_Pago', 'Valor Pagamento', 'ValorPagamento', 'Valor_Pagamento',
        'Valor', 'Valor Total', 'ValorTotal', 'Valor_Total',
        'Valor a Pagar', 'ValoraPagar', 'Valor_a_Pagar', 'VALOR'
    ]
    
    # Primeiro busca pelas colunas de prioridade
    for coluna in df.columns:
        coluna_limpa = str(coluna).strip().upper()
        for padrao in colunas_prioridade:
            if padrao.upper() in coluna_limpa:
                return coluna
    
    # Se não encontrou, busca por qualquer coluna que possa conter valores monetários
    for coluna in df.columns:
        if df[coluna].dtype in ['float64', 'int64']:
            return coluna
        elif df[coluna].dtype == 'object':
            # Verificar se a coluna contém valores monetários
            amostra = df[coluna].dropna().head(10).astype(str)
            if any(re.search(r'[\d.,]+\s*[R$\€\£]?', str(x)) for x in amostra):
                return coluna
    
    return None

def detectar_coluna_data(df):
    """Detecta automaticamente colunas de data"""
    colunas_data = [
        'Data', 'Data Pagto', 'DataPagto', 'Data_Pagto', 'Data Pagamento',
        'DataPagamento', 'Data_Pagamento', 'Data de Pagamento', 'Data de Pagto',
        'DataNasc', 'Data de Nasc', 'Data de Nascimento', 'DataNascimento',
        'DtLote', 'Data Lote', 'Data_Lote', 'DATA', 'DT_LOTE'
    ]
    
    datas_encontradas = []
    for coluna in df.columns:
        coluna_limpa = str(coluna).strip().upper()
        for padrao in colunas_data:
            if padrao.upper() in coluna_limpa:
                datas_encontradas.append(coluna)
                break
    
    return datas_encontradas

def detectar_coluna_projeto(df):
    """Detecta automaticamente a coluna de projeto"""
    colunas_possiveis = ['Projeto', 'Programa', 'Projeto/Programa', 'Nome Projeto', 'PROJETO', 'PROGRAMA']
    
    for coluna in df.columns:
        coluna_limpa = str(coluna).strip().upper()
        for padrao in colunas_possiveis:
            if padrao.upper() in coluna_limpa:
                return coluna
    
    return None

def detectar_coluna_cpf(df):
    """Detecta automaticamente a coluna de CPF"""
    colunas_possiveis = ['CPF', 'Cpf', 'cpf', 'CPF/CNPJ', 'CPF_CNPJ']
    
    for coluna in df.columns:
        coluna_limpa = str(coluna).strip().upper()
        for padrao in colunas_possiveis:
            if padrao.upper() == coluna_limpa:
                return coluna
    
    return None

# ============================================
# EXTRATOR DE MÊS/ANO
# ============================================

def extrair_mes_ano_arquivo(nome_arquivo):
    """
    Extrai mês e ano do nome do arquivo.
    Prioridade: colunas de data > nome do arquivo > data atual
    """
    if not nome_arquivo:
        return None, None
    
    nome_upper = nome_arquivo.upper()
    
    # Mapeamento de meses
    meses_map = {
        'JAN': 'Janeiro', 'JANEIRO': 'Janeiro',
        'FEV': 'Fevereiro', 'FEVEREIRO': 'Fevereiro',
        'MAR': 'Março', 'MARCO': 'Março', 'MARÇO': 'Março',
        'ABR': 'Abril', 'ABRIL': 'Abril',
        'MAI': 'Maio', 'MAIO': 'Maio',
        'JUN': 'Junho', 'JUNHO': 'Junho',
        'JUL': 'Julho', 'JULHO': 'Julho',
        'AGO': 'Agosto', 'AGOSTO': 'Agosto',
        'SET': 'Setembro', 'SETEMBRO': 'Setembro',
        'OUT': 'Outubro', 'OUTUBRO': 'Outubro',
        'NOV': 'Novembro', 'NOVEMBRO': 'Novembro',
        'DEZ': 'Dezembro', 'DEZEMBRO': 'Dezembro'
    }
    
    # Procurar por padrões de data no nome do arquivo
    padroes_data = [
        r'(\d{1,2})[\.\-/](\d{1,2})[\.\-/](\d{4})',  # DD-MM-AAAA
        r'(\d{4})[\.\-/](\d{1,2})[\.\-/](\d{1,2})',  # AAAA-MM-DD
        r'(\w+)[\.\-/]?(\d{4})',  # MES-AAAA
        r'(\d{4})[\.\-/]?(\w+)',  # AAAA-MES
        r'(\d{1,2})[\.\-/](\d{4})',  # MM-AAAA
        r'(\d{4})[\.\-/](\d{1,2})',  # AAAA-MM
    ]
    
    for padrao in padroes_data:
        match = re.search(padrao, nome_upper)
        if match:
            grupos = match.groups()
            if len(grupos) == 3:
                # Formato DD-MM-AAAA ou AAAA-MM-DD
                if len(grupos[0]) == 4:  # AAAA-MM-DD
                    ano = int(grupos[0])
                    mes_num = int(grupos[1])
                else:  # DD-MM-AAAA
                    ano = int(grupos[2])
                    mes_num = int(grupos[1])
                
                meses_numeros = {
                    1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
                    5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
                    9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
                }
                return meses_numeros.get(mes_num, 'Janeiro'), ano
                
            elif len(grupos) == 2:
                # Formato MES-AAAA ou AAAA-MES
                if grupos[0].isdigit():  # AAAA-MES ou AAAA-MM
                    ano = int(grupos[0])
                    mes_info = grupos[1]
                    
                    if mes_info.isdigit():  # É número do mês
                        mes_num = int(mes_info)
                        meses_numeros = {
                            1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
                            5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
                            9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
                        }
                        return meses_numeros.get(mes_num, 'Janeiro'), ano
                    else:  # É nome do mês
                        for key, value in meses_map.items():
                            if key in mes_info.upper():
                                return value, ano
                else:  # MES-AAAA
                    mes_info = grupos[0]
                    ano = int(grupos[1])
                    
                    for key, value in meses_map.items():
                        if key in mes_info.upper():
                            return value, ano
    
    # Se não encontrou padrão específico, procurar por nomes de meses
    for key, value in meses_map.items():
        if key in nome_upper:
            # Procurar ano (4 dígitos)
            ano_match = re.search(r'(\d{4})', nome_upper)
            ano = int(ano_match.group(1)) if ano_match else datetime.now().year
            return value, ano
    
    return None, None

def extrair_mes_ano_dados(df):
    """Extrai mês e ano das colunas de data dos dados"""
    colunas_data = detectar_coluna_data(df)
    
    if not colunas_data:
        return None, None
    
    for coluna_data in colunas_data:
        try:
            # Tentar converter para datetime
            df_temp = df.copy()
            
            # Primeiro tentar converter diretamente
            df_temp[coluna_data] = pd.to_datetime(df_temp[coluna_data], errors='coerce', dayfirst=True)
            
            # Se não funcionar, tentar outros formatos
            if df_temp[coluna_data].isna().all():
                # Tentar formato brasileiro
                for fmt in ['%d/%m/%Y', '%d/%m/%y', '%d-%m-%Y', '%d.%m.%Y']:
                    try:
                        df_temp[coluna_data] = pd.to_datetime(df[coluna_data], format=fmt, errors='coerce')
                        if not df_temp[coluna_data].isna().all():
                            break
                    except:
                        continue
            
            # Filtrar datas válidas
            datas_validas = df_temp[coluna_data].dropna()
            
            if not datas_validas.empty:
                # Pegar a data mais frequente
                if len(datas_validas) > 0:
                    mes_mais_frequente = datas_validas.dt.month.mode()
                    ano_mais_frequente = datas_validas.dt.year.mode()
                    
                    if not mes_mais_frequente.empty and not ano_mais_frequente.empty:
                        meses_numeros = {
                            1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
                            5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
                            9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
                        }
                        
                        mes_num = int(mes_mais_frequente.iloc[0])
                        ano = int(ano_mais_frequente.iloc[0])
                        
                        return meses_numeros.get(mes_num, 'Janeiro'), ano
        except:
            continue
    
    return None, None

# ============================================
# PROCESSAMENTO DE DADOS
# ============================================

def processar_valor(valor):
    """Processa valores monetários de diferentes formatos"""
    if pd.isna(valor):
        return 0.0
    
    try:
        # Se já é numérico
        if isinstance(valor, (int, float)):
            return float(valor)
        
        valor_str = str(valor).strip()
        
        if valor_str == '':
            return 0.0
        
        # Remover símbolos de moeda e espaços
        valor_str = re.sub(r'[R\$\s€£¥]', '', valor_str)
        
        # Substituir vírgula por ponto se for o formato brasileiro
        if ',' in valor_str and '.' in valor_str:
            # Formato 1.234,56 -> remover pontos de milhar, substituir vírgula por ponto
            valor_str = valor_str.replace('.', '').replace(',', '.')
        elif ',' in valor_str:
            # Formato 1234,56
            valor_str = valor_str.replace(',', '.')
        
        # Remover caracteres não numéricos exceto ponto
        valor_str = re.sub(r'[^\d\.]', '', valor_str)
        
        # Converter para float
        return float(valor_str) if valor_str else 0.0
    except:
        return 0.0

def processar_cpf(cpf):
    """Processa CPF, mantendo apenas números"""
    if pd.isna(cpf):
        return ''
    
    cpf_str = str(cpf).strip()
    
    # Remover todos os caracteres não numéricos
    cpf_limpo = re.sub(r'[^\d]', '', cpf_str)
    
    # Completar com zeros à esquerda se necessário
    if len(cpf_limpo) < 11:
        cpf_limpo = cpf_limpo.zfill(11)
    
    return cpf_limpo

def processar_data(data):
    """Processa datas de diferentes formatos"""
    if pd.isna(data):
        return None
    
    try:
        # Tentar converter diretamente
        data_dt = pd.to_datetime(data, errors='coerce', dayfirst=True)
        
        if pd.isna(data_dt):
            # Tentar outros formatos
            formatos = [
                '%d/%m/%Y', '%d/%m/%y', '%d-%m-%Y', '%d-%m-%y',
                '%d.%m.%Y', '%d.%m.%y', '%Y-%m-%d', '%Y/%m/%d'
            ]
            
            for formato in formatos:
                try:
                    if isinstance(data, str):
                        data_dt = datetime.strptime(data, formato)
                        break
                except:
                    continue
        
        return data_dt.strftime('%d/%m/%Y') if data_dt else None
    except:
        return None

def identificar_tipo_planilha(nome_arquivo, df):
    """Identifica se a planilha é de pagamentos ou abertura de contas"""
    nome_upper = nome_arquivo.upper()
    
    # Palavras-chave para pagamentos
    palavras_pagamentos = [
        'PGTO', 'PAGTO', 'PAGAMENTO', 'PENDENCIA', 'PENDÊNCIA',
        'PENDENCIAS', 'PENDÊNCIAS', 'REL.CADASTRO', 'REL_CADASTRO',
        'RELATÓRIO', 'RELATORIO', 'BOLETIM', 'PAGAMENTOS'
    ]
    
    # Palavras-chave para abertura de contas
    palavras_abertura = [
        'ABERT', 'ABERTURA', 'CADASTRO', 'INSCRICAO', 'INSCRIÇÃO',
        'CONTA', 'CONTAS', 'CADASTROS', 'INSCRIÇÕES'
    ]
    
    # Verificar pelo nome do arquivo
    for palavra in palavras_pagamentos:
        if palavra in nome_upper:
            return 'pagamentos'
    
    for palavra in palavras_abertura:
        if palavra in nome_upper:
            return 'contas'
    
    # Verificar pelas colunas do DataFrame
    colunas = [str(col).upper() for col in df.columns]
    
    # Se tem coluna de valor, provavelmente é de pagamentos
    if any('VALOR' in col for col in colunas) and any(('PAGTO' in col) or ('PAGAMENTO' in col) for col in colunas):
        return 'pagamentos'
    
    # Se tem coluna de data de nascimento ou nome da mãe, provavelmente é de abertura
    if any('DATANASC' in col for col in colunas) or any('NOMEMAE' in col for col in colunas):
        return 'contas'
    
    # Padrão como pagamentos por default
    return 'pagamentos'

def carregar_planilha(arquivo):
    """Carrega uma planilha independente do formato"""
    try:
        nome_arquivo = arquivo.name
        
        # Para arquivos CSV
        if nome_arquivo.endswith('.csv') or nome_arquivo.endswith('.txt'):
            # Detectar encoding
            encoding = detectar_encoding_simples(arquivo)
            
            # Tentar diferentes delimitadores
            delimitadores = [';', ',', '\t', '|']
            
            for delimiter in delimitadores:
                try:
                    arquivo.seek(0)
                    df = pd.read_csv(arquivo, delimiter=delimiter, encoding=encoding, 
                                    low_memory=False, on_bad_lines='skip')
                    
                    # Verificar se encontrou colunas válidas
                    if len(df.columns) > 1:
                        return df
                    
                    # Se tem apenas uma coluna, pode ser delimitador errado
                    if len(df.columns) == 1:
                        # Tentar ler como texto e analisar
                        arquivo.seek(0)
                        conteudo = arquivo.read().decode(encoding)
                        linhas = conteudo.split('\n')
                        
                        # Contar ocorrências de cada delimitador
                        contagem = {delim: 0 for delim in delimitadores}
                        for linha in linhas[:10]:
                            for delim in delimitadores:
                                contagem[delim] += linha.count(delim)
                        
                        # Usar o delimitador mais comum
                        melhor_delim = max(contagem, key=contagem.get)
                        if contagem[melhor_delim] > 0:
                            arquivo.seek(0)
                            df = pd.read_csv(arquivo, delimiter=melhor_delim, 
                                            encoding=encoding, low_memory=False)
                            return df
                except Exception as e:
                    continue
            
            # Se nada funcionou, tentar ler com engine python
            try:
                arquivo.seek(0)
                df = pd.read_csv(arquivo, sep=None, engine='python', encoding=encoding, 
                                low_memory=False, on_bad_lines='skip')
                return df
            except:
                arquivo.seek(0)
                # Último recurso: ler como texto e converter
                conteudo = arquivo.read().decode(encoding)
                linhas = [linha.split(';') for linha in conteudo.split('\n') if linha.strip()]
                if linhas:
                    df = pd.DataFrame(linhas[1:], columns=linhas[0])
                    return df
            
        # Para arquivos Excel
        elif nome_arquivo.endswith(('.xlsx', '.xls', '.xlsm')):
            try:
                return pd.read_excel(arquivo)
            except Exception as e:
                st.warning(f"Erro ao ler Excel {nome_arquivo}: {str(e)}")
                return pd.DataFrame()
            
        else:
            st.error(f"Formato de arquivo não suportado: {nome_arquivo}")
            return pd.DataFrame()
            
    except Exception as e:
        st.error(f"Erro ao carregar arquivo {arquivo.name}: {str(e)}")
        return pd.DataFrame()

def processar_dataframe(df, tipo_planilha):
    """Processa um DataFrame para padronização"""
    if df.empty:
        return df
    
    df_processado = df.copy()
    
    # Remover linhas completamente vazias
    df_processado = df_processado.dropna(how='all')
    
    # Remover linhas que são totais
    for idx in df_processado.index[-10:]:  # Verificar as últimas 10 linhas
        linha = df_processado.loc[idx]
        
        # Converter valores da linha para string e verificar se contém "TOTAL"
        linha_str = ' '.join([str(val).upper() for val in linha.dropna()])
        if any(palavra in linha_str for palavra in ['TOTAL', 'SOMA', 'SUM', 'TOTAL GERAL']):
            df_processado = df_processado.drop(idx)
    
    # Padronizar nomes de colunas
    df_processado.columns = [str(col).strip() for col in df_processado.columns]
    
    # Processar colunas de data
    colunas_data = detectar_coluna_data(df_processado)
    for coluna in colunas_data:
        try:
            df_processado[f'{coluna}_Processada'] = df_processado[coluna].apply(processar_data)
        except:
            pass
    
    # Processar coluna de valor se for planilha de pagamentos
    if tipo_planilha == 'pagamentos':
        coluna_valor = detectar_coluna_valor(df_processado)
        if coluna_valor:
            try:
                df_processado['Valor_Processado'] = df_processado[coluna_valor].apply(processar_valor)
            except:
                # Tentar converter diretamente
                try:
                    df_processado['Valor_Processado'] = pd.to_numeric(df_processado[coluna_valor], errors='coerce').fillna(0)
                except:
                    df_processado['Valor_Processado'] = 0
    
    # Processar CPF
    coluna_cpf = detectar_coluna_cpf(df_processado)
    if coluna_cpf:
        try:
            df_processado['CPF_Processado'] = df_processado[coluna_cpf].apply(processar_cpf)
        except:
            pass
    
    return df_processado

# ============================================
# ANÁLISE E MÉTRICAS
# ============================================

def analisar_pagamentos(df_pagamentos):
    """Analisa dados de pagamentos e gera métricas"""
    if df_pagamentos.empty:
        return {}
    
    metrics = {
        'total_registros': len(df_pagamentos),
        'registros_validos': 0,
        'registros_sem_conta': 0,
        'valor_total': 0.0,
        'pagamentos_duplicados': 0,
        'valor_duplicados': 0.0,
        'projetos_ativos': 0,
        'beneficiarios_unicos': 0
    }
    
    # Detectar colunas
    coluna_conta = detectar_coluna_conta(df_pagamentos)
    coluna_nome = detectar_coluna_nome(df_pagamentos)
    coluna_valor = 'Valor_Processado' if 'Valor_Processado' in df_pagamentos.columns else detectar_coluna_valor(df_pagamentos)
    coluna_projeto = detectar_coluna_projeto(df_pagamentos)
    
    # Contar registros válidos (com número de conta)
    if coluna_conta and coluna_conta in df_pagamentos.columns:
        try:
            registros_validos = df_pagamentos[coluna_conta].notna() & (df_pagamentos[coluna_conta].astype(str).str.strip() != '')
            metrics['registros_validos'] = int(registros_validos.sum())
            metrics['registros_sem_conta'] = len(df_pagamentos) - metrics['registros_validos']
        except:
            metrics['registros_validos'] = len(df_pagamentos)
            metrics['registros_sem_conta'] = 0
        
        # Beneficiários únicos
        if coluna_nome and coluna_nome in df_pagamentos.columns:
            try:
                df_validos = df_pagamentos[registros_validos] if 'registros_validos' in locals() else df_pagamentos
                metrics['beneficiarios_unicos'] = df_validos[coluna_nome].nunique()
            except:
                pass
    
    # Valor total
    if coluna_valor and coluna_valor in df_pagamentos.columns:
        try:
            metrics['valor_total'] = float(df_pagamentos[coluna_valor].sum())
        except:
            metrics['valor_total'] = 0.0
    
    # Projetos ativos
    if coluna_projeto and coluna_projeto in df_pagamentos.columns:
        try:
            metrics['projetos_ativos'] = df_pagamentos[coluna_projeto].nunique()
        except:
            metrics['projetos_ativos'] = 0
    
    # Detectar duplicidades por número de conta
    if coluna_conta and coluna_conta in df_pagamentos.columns:
        try:
            contas_duplicadas = df_pagamentos[df_pagamentos.duplicated(subset=[coluna_conta], keep=False)]
            metrics['pagamentos_duplicados'] = contas_duplicadas[coluna_conta].nunique()
            
            if coluna_valor and coluna_valor in contas_duplicadas.columns:
                metrics['valor_duplicados'] = float(contas_duplicadas[coluna_valor].sum())
        except:
            metrics['pagamentos_duplicados'] = 0
            metrics['valor_duplicados'] = 0.0
    
    return metrics

def analisar_contas(df_contas):
    """Analisa dados de abertura de contas"""
    if df_contas.empty:
        return {}
    
    metrics = {
        'total_contas': len(df_contas),
        'beneficiarios_unicos': 0,
        'projetos_ativos': 0,
        'contas_unicas': 0
    }
    
    # Detectar colunas
    coluna_nome = detectar_coluna_nome(df_contas)
    coluna_projeto = detectar_coluna_projeto(df_contas)
    coluna_conta = detectar_coluna_conta(df_contas)
    
    # Beneficiários únicos
    if coluna_nome and coluna_nome in df_contas.columns:
        try:
            metrics['beneficiarios_unicos'] = df_contas[coluna_nome].nunique()
        except:
            pass
    
    # Projetos ativos
    if coluna_projeto and coluna_projeto in df_contas.columns:
        try:
            metrics['projetos_ativos'] = df_contas[coluna_projeto].nunique()
        except:
            pass
    
    # Contas únicas
    if coluna_conta and coluna_conta in df_contas.columns:
        try:
            metrics['contas_unicas'] = df_contas[coluna_conta].nunique()
        except:
            pass
    
    return metrics

def comparar_pagamentos_contas(df_pagamentos, df_contas):
    """Compara pagamentos com abertura de contas para identificar pendências"""
    if df_pagamentos.empty or df_contas.empty:
        return {}
    
    coluna_conta_pag = detectar_coluna_conta(df_pagamentos)
    coluna_conta_cont = detectar_coluna_conta(df_contas)
    
    if not coluna_conta_pag or not coluna_conta_cont:
        return {}
    
    try:
        # Extrair listas de contas
        contas_com_pagamento = df_pagamentos[coluna_conta_pag].dropna().unique()
        contas_abertas = df_contas[coluna_conta_cont].dropna().unique()
        
        # Converter para strings para comparação
        contas_com_pagamento = [str(c).strip() for c in contas_com_pagamento]
        contas_abertas = [str(c).strip() for c in contas_abertas]
        
        # Encontrar contas sem pagamento
        contas_sem_pagamento = [conta for conta in contas_abertas if conta not in contas_com_pagamento]
        
        return {
            'total_contas_abertas': len(contas_abertas),
            'total_contas_com_pagamento': len(set(contas_com_pagamento)),
            'total_contas_sem_pagamento': len(contas_sem_pagamento),
            'contas_sem_pagamento': contas_sem_pagamento
        }
    except:
        return {}

# ============================================
# INTERFACE STREAMLIT
# ============================================

def main():
    st.title("🏛️ Sistema POT - SMDET")
    st.markdown("### Sistema de Análise de Pagamentos e Contas")
    st.markdown("---")
    
    # Sidebar para upload
    st.sidebar.header("📤 Carregar Planilhas")
    
    uploaded_pagamentos = st.sidebar.file_uploader(
        "Planilhas de Pagamentos",
        type=['csv', 'xlsx', 'xls', 'txt'],
        accept_multiple_files=True,
        help="Carregue uma ou mais planilhas de pagamentos (CSV, Excel, TXT)"
    )
    
    uploaded_contas = st.sidebar.file_uploader(
        "Planilhas de Abertura de Contas",
        type=['csv', 'xlsx', 'xls', 'txt'],
        accept_multiple_files=True,
        help="Carregue uma ou mais planilhas de abertura de contas"
    )
    
    # Processar uploads
    dados_pagamentos = []
    dados_contas = []
    
    if uploaded_pagamentos:
        with st.spinner("Processando planilhas de pagamentos..."):
            for arquivo in uploaded_pagamentos:
                df = carregar_planilha(arquivo)
                if not df.empty and len(df) > 0:
                    df_processado = processar_dataframe(df, 'pagamentos')
                    dados_pagamentos.append({
                        'nome': arquivo.name,
                        'dataframe': df_processado,
                        'tipo': 'pagamentos'
                    })
                    st.sidebar.success(f"✓ {arquivo.name} ({len(df)} registros)")
    
    if uploaded_contas:
        with st.spinner("Processando planilhas de abertura de contas..."):
            for arquivo in uploaded_contas:
                df = carregar_planilha(arquivo)
                if not df.empty and len(df) > 0:
                    df_processado = processar_dataframe(df, 'contas')
                    dados_contas.append({
                        'nome': arquivo.name,
                        'dataframe': df_processado,
                        'tipo': 'contas'
                    })
                    st.sidebar.success(f"✓ {arquivo.name} ({len(df)} registros)")
    
    # Verificar se há dados para análise
    if not dados_pagamentos and not dados_contas:
        st.info("📊 Faça o upload das planilhas para iniciar a análise")
        
        # Mostrar exemplo de formato esperado
        with st.expander("ℹ️ Formato esperado das planilhas"):
            st.write("""
            **Para planilhas de pagamentos:**
            - Deve conter coluna com número da conta (ex: "Num Cartao", "Conta", "Número Conta")
            - Deve conter coluna de valor (ex: "Valor Pagto", "Valor", "Valor Pago")
            - Pode conter colunas adicionais: Nome, Projeto, Data, CPF
            
            **Para planilhas de abertura de contas:**
            - Deve conter coluna com número da conta
            - Deve conter coluna de nome do beneficiário
            - Pode conter colunas adicionais: Projeto, Data Nascimento, CPF
            
            **Formatos suportados:** CSV, Excel (XLSX, XLS), TXT
            **Encoding suportados:** UTF-8, Latin-1, Windows-1252
            """)
        
        return
    
    # Combinar dados se houver múltiplos arquivos
    df_pagamentos_combinado = pd.DataFrame()
    if dados_pagamentos:
        dfs_pag = [d['dataframe'] for d in dados_pagamentos]
        df_pagamentos_combinado = pd.concat(dfs_pag, ignore_index=True)
    
    df_contas_combinado = pd.DataFrame()
    if dados_contas:
        dfs_cont = [d['dataframe'] for d in dados_contas]
        df_contas_combinado = pd.concat(dfs_cont, ignore_index=True)
    
    # Extrair mês/ano de referência
    mes_ref, ano_ref = None, None
    
    # Tentar extrair dos nomes dos arquivos primeiro
    if dados_pagamentos:
        for dado in dados_pagamentos:
            mes_arquivo, ano_arquivo = extrair_mes_ano_arquivo(dado['nome'])
            if mes_arquivo and ano_arquivo:
                mes_ref, ano_ref = mes_arquivo, ano_arquivo
                break
    
    if not mes_ref and dados_contas:
        for dado in dados_contas:
            mes_arquivo, ano_arquivo = extrair_mes_ano_arquivo(dado['nome'])
            if mes_arquivo and ano_arquivo:
                mes_ref, ano_ref = mes_arquivo, ano_arquivo
                break
    
    # Se não encontrou no nome do arquivo, tentar extrair dos dados
    if not mes_ref and not df_pagamentos_combinado.empty:
        mes_dados, ano_dados = extrair_mes_ano_dados(df_pagamentos_combinado)
        if mes_dados and ano_dados:
            mes_ref, ano_ref = mes_dados, ano_dados
    
    if not mes_ref:
        mes_ref, ano_ref = 'Outubro', datetime.now().year
    
    # Seleção manual de mês/ano na sidebar
    st.sidebar.markdown("---")
    st.sidebar.subheader("📅 Período de Referência")
    
    col1, col2 = st.sidebar.columns(2)
    with col1:
        meses = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
        mes_selecionado = st.selectbox("Mês", meses, 
                                      index=meses.index(mes_ref) if mes_ref in meses else 9)
    with col2:
        ano_atual = datetime.now().year
        anos = list(range(ano_atual, ano_atual - 5, -1))
        ano_selecionado = st.selectbox("Ano", anos, 
                                      index=0 if ano_ref in anos else 0)
    
    st.sidebar.markdown("---")
    
    # Botão para análise
    if st.sidebar.button("🔍 Realizar Análise", type="primary", use_container_width=True):
        # Realizar análises
        with st.spinner("Realizando análises..."):
            # Análise de pagamentos
            if not df_pagamentos_combinado.empty:
                metrics_pagamentos = analisar_pagamentos(df_pagamentos_combinado)
            else:
                metrics_pagamentos = {}
            
            # Análise de contas
            if not df_contas_combinado.empty:
                metrics_contas = analisar_contas(df_contas_combinado)
            else:
                metrics_contas = {}
            
            # Comparação entre pagamentos e contas
            if not df_pagamentos_combinado.empty and not df_contas_combinado.empty:
                comparacao = comparar_pagamentos_contas(df_pagamentos_combinado, df_contas_combinado)
            else:
                comparacao = {}
            
            # Exibir resultados
            st.success("✅ Análise concluída!")
            
            # Exibir período de referência
            st.subheader(f"📅 Período Analisado: {mes_selecionado} de {ano_selecionado}")
            
            # Métricas principais
            st.subheader("📊 Métricas Principais")
            
            # Criar colunas para métricas
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                if 'total_registros' in metrics_pagamentos:
                    st.metric("Total de Pagamentos", 
                             formatar_brasileiro(metrics_pagamentos['total_registros']))
                else:
                    st.metric("Total de Pagamentos", "0")
            
            with col2:
                if 'registros_validos' in metrics_pagamentos:
                    st.metric("Pagamentos Válidos", 
                             formatar_brasileiro(metrics_pagamentos['registros_validos']))
                else:
                    st.metric("Pagamentos Válidos", "0")
            
            with col3:
                if 'valor_total' in metrics_pagamentos:
                    st.metric("Valor Total", 
                             formatar_brasileiro(metrics_pagamentos['valor_total'], 'monetario'))
                else:
                    st.metric("Valor Total", "R$ 0,00")
            
            with col4:
                projetos = metrics_pagamentos.get('projetos_ativos', 
                                                 metrics_contas.get('projetos_ativos', 0))
                st.metric("Projetos Ativos", 
                         formatar_brasileiro(projetos))
            
            # Segunda linha de métricas
            col5, col6, col7, col8 = st.columns(4)
            
            with col5:
                if 'pagamentos_duplicados' in metrics_pagamentos:
                    duplicados = metrics_pagamentos['pagamentos_duplicados']
                    valor_dup = metrics_pagamentos.get('valor_duplicados', 0)
                    st.metric("Pagamentos Duplicados", 
                             formatar_brasileiro(duplicados),
                             delta=f"-{formatar_brasileiro(valor_dup, 'monetario')}" if valor_dup > 0 else "0",
                             delta_color="inverse")
                else:
                    st.metric("Pagamentos Duplicados", "0")
            
            with col6:
                beneficiarios = metrics_pagamentos.get('beneficiarios_unicos', 
                                                      metrics_contas.get('beneficiarios_unicos', 0))
                st.metric("Beneficiários Únicos", 
                         formatar_brasileiro(beneficiarios))
            
            with col7:
                if 'total_contas' in metrics_contas:
                    st.metric("Contas Abertas", 
                             formatar_brasileiro(metrics_contas['total_contas']))
                else:
                    st.metric("Contas Abertas", "0")
            
            with col8:
                if 'total_contas_sem_pagamento' in comparacao:
                    st.metric("Contas sem Pagamento", 
                             formatar_brasileiro(comparacao['total_contas_sem_pagamento']),
                             delta_color="inverse")
                else:
                    st.metric("Contas sem Pagamento", "0")
            
            st.markdown("---")
            
            # Abas para análises detalhadas
            tab1, tab2, tab3, tab4 = st.tabs([
                "📋 Resumo dos Dados", 
                "⚠️ Duplicidades", 
                "⏳ Pendências", 
                "📊 Estatísticas"
            ])
            
            with tab1:
                st.subheader("Resumo dos Dados Processados")
                
                if not df_pagamentos_combinado.empty:
                    st.write("**Planilhas de Pagamentos Carregadas:**")
                    for dado in dados_pagamentos:
                        st.write(f"- {dado['nome']} ({len(dado['dataframe'])} registros)")
                    
                    st.write(f"**Total de registros de pagamentos:** {len(df_pagamentos_combinado)}")
                    
                    # Mostrar colunas detectadas
                    st.write("**Colunas detectadas automaticamente:**")
                    colunas_info = []
                    
                    coluna_conta = detectar_coluna_conta(df_pagamentos_combinado)
                    if coluna_conta:
                        colunas_info.append(f"📎 Conta: {coluna_conta}")
                    
                    coluna_nome = detectar_coluna_nome(df_pagamentos_combinado)
                    if coluna_nome:
                        colunas_info.append(f"👤 Nome: {coluna_nome}")
                    
                    coluna_valor = detectar_coluna_valor(df_pagamentos_combinado)
                    if coluna_valor:
                        colunas_info.append(f"💰 Valor: {coluna_valor}")
                    
                    coluna_projeto = detectar_coluna_projeto(df_pagamentos_combinado)
                    if coluna_projeto:
                        colunas_info.append(f"🏢 Projeto: {coluna_projeto}")
                    
                    if colunas_info:
                        for info in colunas_info:
                            st.write(info)
                    else:
                        st.write("Não foi possível detectar colunas automaticamente.")
                    
                    # Mostrar preview dos dados
                    with st.expander("👁️ Visualizar Primeiras Linhas dos Dados"):
                        st.dataframe(df_pagamentos_combinado.head(10))
                
                if not df_contas_combinado.empty:
                    st.write("---")
                    st.write("**Planilhas de Contas Carregadas:**")
                    for dado in dados_contas:
                        st.write(f"- {dado['nome']} ({len(dado['dataframe'])} registros)")
                    
                    st.write(f"**Total de registros de contas:** {len(df_contas_combinado)}")
            
            with tab2:
                if not df_pagamentos_combinado.empty:
                    st.subheader("Análise de Duplicidades")
                    
                    coluna_conta = detectar_coluna_conta(df_pagamentos_combinado)
                    
                    if coluna_conta and coluna_conta in df_pagamentos_combinado.columns:
                        try:
                            # Encontrar duplicidades
                            duplicidades = df_pagamentos_combinado[
                                df_pagamentos_combinado.duplicated(subset=[coluna_conta], keep=False)
                            ].sort_values(by=coluna_conta)
                            
                            if not duplicidades.empty:
                                contas_duplicadas = duplicidades[coluna_conta].nunique()
                                st.warning(f"🚨 Foram encontradas {contas_duplicadas} contas com pagamentos duplicados")
                                
                                # Resumo por conta
                                resumo_cols = [coluna_conta]
                                value_col = 'Valor_Processado' if 'Valor_Processado' in duplicidades.columns else detectar_coluna_valor(duplicidades)
                                
                                if value_col and value_col in duplicidades.columns:
                                    resumo = duplicidades.groupby(coluna_conta).agg({
                                        value_col: ['count', 'sum']
                                    }).reset_index()
                                    resumo.columns = [coluna_conta, 'Quantidade', 'Valor Total']
                                    
                                    st.write("**Resumo das Duplicidades (Top 20):**")
                                    st.dataframe(resumo.head(20))
                                    
                                    # Detalhes completos
                                    with st.expander("Ver detalhes completos"):
                                        colunas_mostrar = [coluna_conta]
                                        
                                        coluna_nome = detectar_coluna_nome(duplicidades)
                                        if coluna_nome and coluna_nome in duplicidades.columns:
                                            colunas_mostrar.append(coluna_nome)
                                        
                                        if value_col:
                                            colunas_mostrar.append(value_col)
                                        
                                        coluna_projeto = detectar_coluna_projeto(duplicidades)
                                        if coluna_projeto and coluna_projeto in duplicidades.columns:
                                            colunas_mostrar.append(coluna_projeto)
                                        
                                        colunas_data = detectar_coluna_data(duplicidades)
                                        if colunas_data and colunas_data[0] in duplicidades.columns:
                                            colunas_mostrar.append(colunas_data[0])
                                        
                                        st.dataframe(duplicidades[colunas_mostrar].head(50))
                                else:
                                    st.write("**Contas com registros duplicados:**")
                                    contas_dup = duplicidades[coluna_conta].value_counts().head(20)
                                    st.dataframe(pd.DataFrame({'Conta': contas_dup.index, 'Ocorrências': contas_dup.values}))
                            else:
                                st.success("✅ Nenhum pagamento duplicado encontrado")
                        except Exception as e:
                            st.error(f"Erro ao analisar duplicidades: {str(e)}")
                    else:
                        st.info("ℹ️ Não foi possível identificar coluna de conta para análise de duplicidades")
            
            with tab3:
                st.subheader("Análise de Pendências")
                
                if 'total_contas_sem_pagamento' in comparacao and comparacao['total_contas_sem_pagamento'] > 0:
                    st.warning(f"⚠️ {comparacao['total_contas_sem_pagamento']} contas abertas não possuem pagamento registrado")
                    
                    # Mostrar contas sem pagamento
                    if not df_contas_combinado.empty:
                        coluna_conta_cont = detectar_coluna_conta(df_contas_combinado)
                        coluna_nome_cont = detectar_coluna_nome(df_contas_combinado)
                        
                        if coluna_conta_cont and coluna_conta_cont in df_contas_combinado.columns:
                            try:
                                contas_sem_pagamento = df_contas_combinado[
                                    df_contas_combinado[coluna_conta_cont].astype(str).isin(
                                        [str(c) for c in comparacao['contas_sem_pagamento']]
                                    )
                                ]
                                
                                colunas_mostrar = [coluna_conta_cont]
                                if coluna_nome_cont and coluna_nome_cont in contas_sem_pagamento.columns:
                                    colunas_mostrar.append(coluna_nome_cont)
                                
                                coluna_projeto = detectar_coluna_projeto(contas_sem_pagamento)
                                if coluna_projeto and coluna_projeto in contas_sem_pagamento.columns:
                                    colunas_mostrar.append(coluna_projeto)
                                
                                st.write("**Contas sem pagamento (Primeiras 50):**")
                                st.dataframe(contas_sem_pagamento[colunas_mostrar].head(50))
                            except:
                                st.write("Não foi possível filtrar as contas sem pagamento.")
                else:
                    if not df_contas_combinado.empty and not df_pagamentos_combinado.empty:
                        st.success("✅ Todas as contas abertas possuem pagamento registrado")
                    else:
                        st.info("ℹ️ Carregue ambas as planilhas (pagamentos e contas) para análise de pendências")
            
            with tab4:
                st.subheader("Estatísticas Detalhadas")
                
                # Estatísticas por projeto
                if not df_pagamentos_combinado.empty:
                    coluna_projeto = detectar_coluna_projeto(df_pagamentos_combinado)
                    coluna_valor = 'Valor_Processado' if 'Valor_Processado' in df_pagamentos_combinado.columns else detectar_coluna_valor(df_pagamentos_combinado)
                    
                    if coluna_projeto and coluna_projeto in df_pagamentos_combinado.columns and coluna_valor and coluna_valor in df_pagamentos_combinado.columns:
                        try:
                            # Top projetos por valor
                            projetos_valor = df_pagamentos_combinado.groupby(coluna_projeto)[coluna_valor].sum().sort_values(ascending=False).head(10)
                            
                            if not projetos_valor.empty and len(projetos_valor) > 0:
                                st.write("**Top 10 Projetos por Valor Total:**")
                                fig = px.bar(
                                    x=projetos_valor.values,
                                    y=projetos_valor.index,
                                    orientation='h',
                                    labels={'x': 'Valor Total (R$)', 'y': 'Projeto'},
                                    title='Top 10 Projetos por Valor'
                                )
                                st.plotly_chart(fig, use_container_width=True)
                        except:
                            pass
                        
                        try:
                            # Distribuição de valores
                            st.write("**Distribuição de Valores:**")
                            valores_validos = df_pagamentos_combinado[coluna_valor].dropna()
                            if len(valores_validos) > 0:
                                fig2 = px.histogram(
                                    valores_validos,
                                    nbins=20,
                                    labels={'value': 'Valor (R$)', 'count': 'Quantidade'},
                                    title='Distribuição dos Valores dos Pagamentos'
                                )
                                st.plotly_chart(fig2, use_container_width=True)
                        except:
                            pass
                
                # Estatísticas descritivas
                if 'valor_total' in metrics_pagamentos and metrics_pagamentos['valor_total'] > 0:
                    st.write("**Estatísticas Descritivas:**")
                    
                    if coluna_valor and coluna_valor in df_pagamentos_combinado.columns:
                        try:
                            estatisticas = df_pagamentos_combinado[coluna_valor].describe()
                            estat_df = pd.DataFrame({
                                'Estatística': estatisticas.index,
                                'Valor': estatisticas.values
                            })
                            st.dataframe(estat_df)
                        except:
                            pass
            
            # Botões para exportação
            st.markdown("---")
            st.subheader("📥 Exportar Resultados")
            
            col_exp1, col_exp2, col_exp3 = st.columns(3)
            
            with col_exp1:
                # Exportar relatório resumido
                relatorio_resumo = {
                    'Mês de Referência': mes_selecionado,
                    'Ano de Referência': ano_selecionado,
                    'Data da Análise': data_hora_atual_brasilia(),
                    'Total Pagamentos': metrics_pagamentos.get('total_registros', 0),
                    'Pagamentos Válidos': metrics_pagamentos.get('registros_validos', 0),
                    'Valor Total': metrics_pagamentos.get('valor_total', 0),
                    'Pagamentos Duplicados': metrics_pagamentos.get('pagamentos_duplicados', 0),
                    'Valor Duplicado': metrics_pagamentos.get('valor_duplicados', 0),
                    'Contas Abertas': metrics_contas.get('total_contas', 0),
                    'Contas sem Pagamento': comparacao.get('total_contas_sem_pagamento', 0)
                }
                
                df_relatorio = pd.DataFrame([relatorio_resumo])
                csv = df_relatorio.to_csv(index=False, sep=';')
                
                st.download_button(
                    label="📄 Relatório Resumido (CSV)",
                    data=csv,
                    file_name=f"relatorio_pot_{mes_selecionado}_{ano_selecionado}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            
            with col_exp2:
                # Exportar dados de pagamentos
                if not df_pagamentos_combinado.empty:
                    csv_pagamentos = df_pagamentos_combinado.to_csv(index=False, sep=';', encoding='utf-8')
                    
                    st.download_button(
                        label="📊 Dados de Pagamentos (CSV)",
                        data=csv_pagamentos,
                        file_name=f"dados_pagamentos_{mes_selecionado}_{ano_selecionado}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
            
            with col_exp3:
                # Exportar dados de contas
                if not df_contas_combinado.empty:
                    csv_contas = df_contas_combinado.to_csv(index=False, sep=';', encoding='utf-8')
                    
                    st.download_button(
                        label="📋 Dados de Contas (CSV)",
                        data=csv_contas,
                        file_name=f"dados_contas_{mes_selecionado}_{ano_selecionado}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
    
    else:
        # Mostrar preview dos dados carregados
        if dados_pagamentos or dados_contas:
            st.info("👈 Clique no botão 'Realizar Análise' para processar os dados")
            
            # Mostrar resumo do que foi carregado
            col_load1, col_load2 = st.columns(2)
            
            with col_load1:
                if dados_pagamentos:
                    st.subheader("📊 Planilhas de Pagamentos")
                    total_reg = sum(len(d['dataframe']) for d in dados_pagamentos)
                    st.write(f"**Total de arquivos:** {len(dados_pagamentos)}")
                    st.write(f"**Total de registros:** {total_reg}")
                    
                    with st.expander("Ver arquivos carregados"):
                        for dado in dados_pagamentos:
                            st.write(f"- {dado['nome']} ({len(dado['dataframe'])} registros)")
            
            with col_load2:
                if dados_contas:
                    st.subheader("📋 Planilhas de Contas")
                    total_reg = sum(len(d['dataframe']) for d in dados_contas)
                    st.write(f"**Total de arquivos:** {len(dados_contas)}")
                    st.write(f"**Total de registros:** {total_reg}")
                    
                    with st.expander("Ver arquivos carregados"):
                        for dado in dados_contas:
                            st.write(f"- {dado['nome']} ({len(dado['dataframe'])} registros)")

if __name__ == "__main__":
    main()
