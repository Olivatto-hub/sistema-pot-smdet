# app.py - Sistema de Monitoramento de Pagamentos do POT
# Versão 2.0 - 

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from io import StringIO, BytesIO
import warnings
from datetime import datetime
import sys
import json

# Configurar warnings
warnings.filterwarnings('ignore')

# Configuração da página Streamlit
st.set_page_config(
    page_title="Sistema POT - Monitoramento de Pagamentos",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Título principal
st.title("📊 SISTEMA DE MONITORAMENTO DE PAGAMENTOS")
st.subheader("Programa Operacional de Trabalho (POT)")
st.markdown("---")

# ============================================================================
# FUNÇÕES DE PROCESSAMENTO DE DADOS - CORRIGIDAS
# ============================================================================

def processar_arquivo(uploaded_file):
    """
    Processa arquivo CSV ou Excel carregado pelo usuário.
    """
    try:
        # Detectar tipo de arquivo
        if uploaded_file.name.lower().endswith('.csv'):
            # Tentar diferentes encodings
            try:
                content = uploaded_file.getvalue().decode('utf-8-sig')
            except UnicodeDecodeError:
                try:
                    content = uploaded_file.getvalue().decode('latin-1')
                except:
                    content = uploaded_file.getvalue().decode('cp1252')
            
            # Ler CSV com diferentes delimitadores
            try:
                df = pd.read_csv(StringIO(content), sep=';', decimal=',', thousands='.', dtype=str)
            except:
                df = pd.read_csv(StringIO(content), sep=',', decimal='.', dtype=str)
        
        elif uploaded_file.name.lower().endswith(('.xlsx', '.xls')):
            # Processar Excel
            df = pd.read_excel(uploaded_file, dtype=str)
        else:
            return None, "❌ Formato não suportado. Use CSV ou Excel."
        
        # Renomear colunas para minúsculo e remover espaços
        df.columns = [str(col).strip().lower().replace(' ', '_').replace('.', '') for col in df.columns]
        
        # Mapeamento de colunas
        mapeamento_colunas = {
            'ordem': 'ordem',
            'projeto': 'projeto',
            'n°_cartão': 'cartao',
            'nº_cartão': 'cartao',
            'cartão': 'cartao',
            'cartao': 'cartao',
            'nome': 'nome',
            'distrito': 'distrito',
            'agência': 'agencia',
            'agencia': 'agencia',
            'rg': 'rg',
            'valor_total': 'valor_total',
            'valor_desconto': 'valor_desconto',
            'valor_pagto': 'valor_pagto',
            'data_pagto': 'data_pagto',
            'valor_dia': 'valor_dia',
            'dias_a_apagar': 'dias_apagar',
            'dias_apagar': 'dias_apagar',
            'cpf': 'cpf',
            'gerenciadora': 'gerenciadora'
        }
        
        # Renomear colunas
        rename_dict = {}
        for col in df.columns:
            for key, value in mapeamento_colunas.items():
                if key in col:
                    rename_dict[col] = value
                    break
            if col not in rename_dict:
                rename_dict[col] = col
        
        df = df.rename(columns=rename_dict)
        
        # ====================================================================
        # CORREÇÃO CRÍTICA: PROCESSAMENTO DE VALORES MONETÁRIOS
        # ====================================================================
        
        colunas_monetarias = ['valor_total', 'valor_desconto', 'valor_pagto', 'valor_dia']
        
        for coluna in colunas_monetarias:
            if coluna in df.columns:
                # Garantir que é string
                df[coluna] = df[coluna].astype(str)
                
                # Remover caracteres especiais
                df[coluna] = df[coluna].str.replace('R\$', '', regex=True)
                df[coluna] = df[coluna].str.replace('$', '', regex=False)
                df[coluna] = df[coluna].str.replace(' ', '', regex=False)
                df[coluna] = df[coluna].str.replace('"', '', regex=False)
                df[coluna] = df[coluna].str.replace("'", '', regex=False)
                df[coluna] = df[coluna].str.replace('USD', '', regex=False)
                df[coluna] = df[coluna].str.replace('US\$', '', regex=True)
                
                # Função para corrigir valores
                def corrigir_valor_monetario(valor):
                    if pd.isna(valor) or valor == '' or valor == 'nan':
                        return np.nan
                    
                    str_val = str(valor).strip()
                    
                    # Se já for número com ponto decimal, converter
                    if str_val.replace('.', '', 1).isdigit() and str_val.count('.') == 1:
                        return float(str_val)
                    
                    # Remover pontos de milhar
                    if '.' in str_val and ',' in str_val:
                        # Formato brasileiro: 1.593,90
                        str_val = str_val.replace('.', '')
                        str_val = str_val.replace(',', '.')
                        return float(str_val) if str_val.replace('.', '', 1).isdigit() else np.nan
                    
                    # Formato americano: 1593.90
                    if ',' in str_val and '.' not in str_val:
                        str_val = str_val.replace(',', '.')
                        return float(str_val) if str_val.replace('.', '', 1).isdigit() else np.nan
                    
                    # Tentar converter diretamente
                    try:
                        return float(str_val)
                    except:
                        return np.nan
                
                # Aplicar correção
                df[coluna] = df[coluna].apply(corrigir_valor_monetario)
                
                # Verificar se há valores
                if df[coluna].isna().all():
                    st.warning(f"⚠️ Coluna '{coluna}' está vazia ou com valores inválidos")
        
        # Converter outras colunas numéricas
        if 'dias_apagar' in df.columns:
            df['dias_apagar'] = pd.to_numeric(df['dias_apagar'], errors='coerce')
        
        if 'ordem' in df.columns:
            df['ordem'] = pd.to_numeric(df['ordem'], errors='coerce')
        
        if 'cartao' in df.columns:
            df['cartao'] = pd.to_numeric(df['cartao'], errors='coerce')
        
        # Converter datas
        if 'data_pagto' in df.columns:
            try:
                df['data_pagto'] = pd.to_datetime(df['data_pagto'], dayfirst=True, errors='coerce')
            except:
                try:
                    df['data_pagto'] = pd.to_datetime(df['data_pagto'], errors='coerce')
                except:
                    df['data_pagto'] = pd.NaT
        
        # Limpar e padronizar texto
        colunas_texto = ['nome', 'projeto', 'gerenciadora', 'agencia', 'rg', 'cpf']
        for col in colunas_texto:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
                df[col] = df[col].replace({
                    'nan': '', 
                    'None': '', 
                    'NaT': '',
                    'NULL': '',
                    'null': ''
                })
        
        # Padronizar agência
        if 'agencia' in df.columns:
            df['agencia'] = df['agencia'].astype(str).str.strip()
            # Remover zeros à esquerda se for numérico
            def formatar_agencia(x):
                try:
                    return str(int(float(x)))
                except:
                    return str(x).strip()
            df['agencia'] = df['agencia'].apply(formatar_agencia)
        
        # Padronizar gerenciadora
        if 'gerenciadora' in df.columns:
            df['gerenciadora'] = df['gerenciadora'].str.upper().str.strip()
            df['gerenciadora'] = df['gerenciadora'].replace({
                'REDE CIDAD�': 'REDE CIDADÃO',
                'REDE CIDADAO': 'REDE CIDADÃO',
                'REDE': 'REDE CIDADÃO',
                'VISTA': 'VISTA',
                '': 'NÃO INFORMADO'
            })
        
        # Verificar se temos dados monetários
        if 'valor_pagto' in df.columns:
            valores_validos = df['valor_pagto'].notna().sum()
            if valores_validos == 0:
                st.error("❌ Nenhum valor monetário válido encontrado na coluna 'valor_pagto'")
        
        return df, "✅ Arquivo processado com sucesso!"
    
    except Exception as e:
        error_msg = f"❌ Erro ao processar: {str(e)}"
        return None, error_msg

# ============================================================================
# FUNÇÕES DE ANÁLISE E DETECÇÃO - CORRIGIDAS
# ============================================================================

def calcular_metricas(df):
    """Calcula métricas principais com tratamento de NaN."""
    metricas = {}
    
    try:
        metricas['total_registros'] = len(df)
        
        if 'valor_pagto' in df.columns:
            # Remover NaN antes de calcular
            valores_validos = df['valor_pagto'].dropna()
            if len(valores_validos) > 0:
                metricas['valor_total'] = valores_validos.sum()
                metricas['valor_medio'] = valores_validos.mean()
                metricas['valor_min'] = valores_validos.min()
                metricas['valor_max'] = valores_validos.max()
                metricas['valor_std'] = valores_validos.std()
                metricas['total_valido'] = len(valores_validos)
            else:
                metricas['valor_total'] = 0
                metricas['valor_medio'] = 0
                metricas['valor_min'] = 0
                metricas['valor_max'] = 0
                metricas['valor_std'] = 0
                metricas['total_valido'] = 0
        
        if 'agencia' in df.columns:
            agencias_validas = df['agencia'].dropna()
            if len(agencias_validas) > 0:
                metricas['total_agencias'] = agencias_validas.nunique()
            else:
                metricas['total_agencias'] = 0
        
        if 'gerenciadora' in df.columns:
            gerenciadoras_validas = df['gerenciadora'].dropna()
            if len(gerenciadoras_validas) > 0:
                metricas['total_gerenciadoras'] = gerenciadoras_validas.nunique()
                distrib = gerenciadoras_validas.value_counts()
                metricas['total_vista'] = distrib.get('VISTA', 0)
                metricas['total_rede'] = distrib.get('REDE CIDADÃO', 0)
            else:
                metricas['total_gerenciadoras'] = 0
                metricas['total_vista'] = 0
                metricas['total_rede'] = 0
        
        if 'dias_apagar' in df.columns:
            dias_validos = df['dias_apagar'].dropna()
            if len(dias_validos) > 0:
                metricas['dias_medio'] = dias_validos.mean()
                metricas['dias_total'] = dias_validos.sum()
            else:
                metricas['dias_medio'] = 0
                metricas['dias_total'] = 0
        
        if 'valor_dia' in df.columns:
            valor_dia_valido = df['valor_dia'].dropna()
            if len(valor_dia_valido) > 0:
                metricas['valor_dia_medio'] = valor_dia_valido.mean()
            else:
                metricas['valor_dia_medio'] = 0
        
        if 'projeto' in df.columns:
            projetos_validos = df['projeto'].dropna()
            if len(projetos_validos) > 0:
                mode_result = projetos_validos.mode()
                if not mode_result.empty:
                    metricas['projeto_principal'] = mode_result.iloc[0]
                else:
                    metricas['projeto_principal'] = 'N/A'
            else:
                metricas['projeto_principal'] = 'N/A'
        
        return metricas
    
    except Exception as e:
        st.error(f"Erro nas métricas: {e}")
        return {}

def detectar_problemas_completos(df):
    """Detecta problemas e inconsistências com relatório detalhado."""
    problemas = {
        'dados_faltantes': [],
        'valores_estranhos': [],
        'duplicidades': [],
        'inconsistencias_criticas': [],
        'alertas_gerais': []
    }
    
    try:
        # 1. DADOS FALTANTES CRÍTICOS
        if 'nome' in df.columns:
            nomes_vazios = df['nome'].isna().sum() + ((df['nome'] == '') | (df['nome'] == 'nan')).sum()
            if nomes_vazios > 0:
                problemas['dados_faltantes'].append({
                    'tipo': 'Nome em branco',
                    'quantidade': nomes_vazios,
                    'gravidade': 'Alta',
                    'exemplos': df[df['nome'].isna() | (df['nome'] == '')].head(3)[['ordem', 'agencia']].to_dict('records') if 'ordem' in df.columns else []
                })
        
        if 'cpf' in df.columns:
            cpfs_invalidos = df['cpf'].apply(lambda x: len(str(x)) < 11 if pd.notna(x) and str(x).strip() not in ['', 'nan'] else pd.isna(x)).sum()
            if cpfs_invalidos > 0:
                problemas['dados_faltantes'].append({
                    'tipo': 'CPF inválido/faltante',
                    'quantidade': cpfs_invalidos,
                    'gravidade': 'Alta',
                    'exemplos': df[df['cpf'].isna() | (df['cpf'] == '') | (df['cpf'].astype(str).str.len() < 11)].head(3)[['nome', 'ordem']].to_dict('records') if 'nome' in df.columns else []
                })
        
        if 'valor_pagto' in df.columns:
            valores_nulos = df['valor_pagto'].isna().sum()
            if valores_nulos > 0:
                problemas['dados_faltantes'].append({
                    'tipo': 'Valor de pagamento nulo',
                    'quantidade': valores_nulos,
                    'gravidade': 'Crítica',
                    'exemplos': df[df['valor_pagto'].isna()].head(3)[['nome', 'ordem']].to_dict('records') if 'nome' in df.columns else []
                })
        
        # 2. VALORES ESTRANHOS/SUSPEITOS
        if 'valor_pagto' in df.columns:
            valores_validos = df['valor_pagto'].dropna()
            if len(valores_validos) > 0:
                # Valores zerados ou negativos
                valores_zerados = (valores_validos <= 0).sum()
                if valores_zerados > 0:
                    problemas['valores_estranhos'].append({
                        'tipo': 'Valores zerados ou negativos',
                        'quantidade': valores_zerados,
                        'gravidade': 'Média',
                        'exemplos': df[df['valor_pagto'] <= 0].head(3)[['nome', 'valor_pagto']].to_dict('records') if 'nome' in df.columns else []
                    })
                
                # Valores extremamente altos
                if len(valores_validos) > 10:
                    q1 = valores_validos.quantile(0.25)
                    q3 = valores_validos.quantile(0.75)
                    iqr = q3 - q1
                    limite_superior = q3 + (3 * iqr)
                    
                    valores_extremos = (valores_validos > limite_superior).sum()
                    if valores_extremos > 0:
                        problemas['valores_estranhos'].append({
                            'tipo': f'Valores extremamente altos (> R$ {limite_superior:,.2f})',
                            'quantidade': valores_extremos,
                            'gravidade': 'Alta',
                            'exemplos': df[df['valor_pagto'] > limite_superior].head(3)[['nome', 'valor_pagto']].to_dict('records') if 'nome' in df.columns else []
                        })
        
        # 3. DUPLICIDADES
        if 'cpf' in df.columns:
            cpf_nao_vazio = df[df['cpf'].notna() & (df['cpf'] != '')]
            if len(cpf_nao_vazio) > 0:
                cpf_duplicados = cpf_nao_vazio['cpf'].duplicated().sum()
                if cpf_duplicados > 0:
                    problemas['duplicidades'].append({
                        'tipo': 'CPFs duplicados',
                        'quantidade': cpf_duplicados,
                        'gravidade': 'Alta',
                        'exemplos': df[df['cpf'].duplicated(keep=False) & df['cpf'].notna()].head(3)[['cpf', 'nome']].to_dict('records') if 'nome' in df.columns else []
                    })
        
        # 4. INCONSISTÊNCIAS CRÍTICAS
        if all(col in df.columns for col in ['valor_total', 'valor_desconto', 'valor_pagto']):
            # Verificar se Valor Total = Desconto + Pagto
            mask = df['valor_total'].notna() & df['valor_desconto'].notna() & df['valor_pagto'].notna()
            if mask.any():
                diferenca = (df.loc[mask, 'valor_total'] - (df.loc[mask, 'valor_desconto'] + df.loc[mask, 'valor_pagto'])).abs()
                inconsistentes = (diferenca > 1).sum()  # Tolerância de R$ 1
                
                if inconsistentes > 0:
                    problemas['inconsistencias_criticas'].append({
                        'tipo': 'Inconsistência nos valores (Total ≠ Desconto + Pagto)',
                        'quantidade': inconsistentes,
                        'gravidade': 'Crítica',
                        'exemplos': df[mask & (diferenca > 1)].head(3)[['nome', 'valor_total', 'valor_desconto', 'valor_pagto']].to_dict('records') if 'nome' in df.columns else []
                    })
        
        if all(col in df.columns for col in ['valor_pagto', 'dias_apagar', 'valor_dia']):
            # Verificar se Valor Pagto ≈ Dias × Valor Dia
            mask = df['valor_pagto'].notna() & df['dias_apagar'].notna() & df['valor_dia'].notna()
            if mask.any():
                calc_esperado = df.loc[mask, 'dias_apagar'] * df.loc[mask, 'valor_dia']
                diferenca = (df.loc[mask, 'valor_pagto'] - calc_esperado).abs()
                inconsistentes = (diferenca > 10).sum()  # Tolerância de R$ 10
                
                if inconsistentes > 0:
                    problemas['inconsistencias_criticas'].append({
                        'tipo': 'Inconsistência no cálculo (Pagto ≠ Dias × Valor Dia)',
                        'quantidade': inconsistentes,
                        'gravidade': 'Crítica',
                        'exemplos': df[mask & (diferenca > 10)].head(3)[['nome', 'valor_pagto', 'dias_apagar', 'valor_dia']].to_dict('records') if 'nome' in df.columns else []
                    })
        
        # 5. ALERTAS GERAIS
        if 'data_pagto' in df.columns:
            datas_futuras = (df['data_pagto'] > pd.Timestamp.now()).sum()
            if datas_futuras > 0:
                problemas['alertas_gerais'].append({
                    'tipo': 'Datas de pagamento futuras',
                    'quantidade': datas_futuras,
                    'gravidade': 'Média',
                    'exemplos': df[df['data_pagto'] > pd.Timestamp.now()].head(3)[['nome', 'data_pagto']].to_dict('records') if 'nome' in df.columns else []
                })
        
        if 'valor_dia' in df.columns:
            valor_dia_valido = df['valor_dia'].dropna()
            if len(valor_dia_valido) > 0:
                abaixo_minimo = (valor_dia_valido < 30).sum()  # Mínimo R$ 30 por dia
                if abaixo_minimo > 0:
                    problemas['alertas_gerais'].append({
                        'tipo': 'Valor por dia abaixo de R$ 30,00',
                        'quantidade': abaixo_minimo,
                        'gravidade': 'Baixa',
                        'exemplos': df[df['valor_dia'] < 30].head(3)[['nome', 'valor_dia']].to_dict('records') if 'nome' in df.columns else []
                    })
        
        return problemas
    
    except Exception as e:
        st.error(f"Erro na detecção de problemas: {e}")
        return problemas

def gerar_tabela_problemas(problemas):
    """Converte problemas em DataFrame para exibição."""
    dados = []
    
    for categoria, itens in problemas.items():
        for item in itens:
            dados.append({
                'Categoria': categoria.replace('_', ' ').title(),
                'Tipo de Problema': item['tipo'],
                'Quantidade': item['quantidade'],
                'Gravidade': item['gravidade']
            })
    
    if dados:
        return pd.DataFrame(dados)
    else:
        return pd.DataFrame(columns=['Categoria', 'Tipo de Problema', 'Quantidade', 'Gravidade'])

# ============================================================================
# FUNÇÕES DE RELATÓRIOS
# ============================================================================

def gerar_relatorio_agencia(df):
    """Gera relatório por agência."""
    if 'agencia' not in df.columns or 'valor_pagto' not in df.columns:
        return pd.DataFrame()
    
    try:
        # Filtrar apenas valores válidos
        df_valido = df[df['valor_pagto'].notna() & df['agencia'].notna()]
        
        if len(df_valido) == 0:
            return pd.DataFrame()
        
        relatorio = df_valido.groupby('agencia').agg({
            'nome': 'count',
            'valor_pagto': ['sum', 'mean', 'min', 'max']
        }).round(2)
        
        # Renomear colunas
        relatorio.columns = ['Qtd Beneficiários', 'Valor Total', 'Valor Médio', 'Valor Mínimo', 'Valor Máximo']
        
        # Adicionar colunas extras se disponíveis
        if 'dias_apagar' in df.columns:
            dias_medio = df_valido.groupby('agencia')['dias_apagar'].mean().round(2)
            relatorio['Dias Médios'] = dias_medio
        
        if 'valor_dia' in df.columns:
            valor_dia_medio = df_valido.groupby('agencia')['valor_dia'].mean().round(2)
            relatorio['Valor Dia Médio'] = valor_dia_medio
        
        return relatorio.sort_values('Valor Total', ascending=False)
    
    except Exception as e:
        st.error(f"Erro no relatório: {e}")
        return pd.DataFrame()

def gerar_relatorio_gerenciadora(df):
    """Gera relatório por gerenciadora."""
    if 'gerenciadora' not in df.columns or 'valor_pagto' not in df.columns:
        return pd.DataFrame()
    
    try:
        # Filtrar apenas valores válidos
        df_valido = df[df['valor_pagto'].notna() & df['gerenciadora'].notna()]
        
        if len(df_valido) == 0:
            return pd.DataFrame()
        
        relatorio = df_valido.groupby('gerenciadora').agg({
            'nome': 'count',
            'valor_pagto': ['sum', 'mean'],
            'agencia': 'nunique'
        }).round(2)
        
        relatorio.columns = ['Qtd Beneficiários', 'Valor Total', 'Valor Médio', 'Qtd Agências']
        
        if 'dias_apagar' in df.columns:
            dias_medio = df_valido.groupby('gerenciadora')['dias_apagar'].mean().round(2)
            relatorio['Dias Médios'] = dias_medio
        
        return relatorio.sort_values('Valor Total', ascending=False)
    
    except Exception as e:
        st.error(f"Erro no relatório: {e}")
        return pd.DataFrame()

# ============================================================================
# FUNÇÕES DE VISUALIZAÇÃO
# ============================================================================

def criar_grafico_barras_agencia(df, top_n=10):
    """Cria gráfico de barras para top agências."""
    if 'agencia' not in df.columns or 'valor_pagto' not in df.columns:
        return None
    
    try:
        df_valido = df[df['valor_pagto'].notna() & df['agencia'].notna()]
        if len(df_valido) == 0:
            return None
        
        agencias_topo = df_valido.groupby('agencia')['valor_pagto'].sum().nlargest(top_n)
        
        fig = go.Figure(data=[
            go.Bar(
                x=agencias_topo.index,
                y=agencias_topo.values,
                text=[f'R$ {v:,.0f}' for v in agencias_topo.values],
                textposition='auto',
                marker_color='#2E86AB'
            )
        ])
        
        fig.update_layout(
            title=f'Top {top_n} Agências por Valor Total',
            xaxis_title='Agência',
            yaxis_title='Valor Total (R$)',
            xaxis_tickangle=-45
        )
        
        return fig
    
    except Exception as e:
        return None

def criar_grafico_distribuicao(df):
    """Cria histograma da distribuição de valores."""
    if 'valor_pagto' not in df.columns:
        return None
    
    try:
        valores_validos = df['valor_pagto'].dropna()
        if len(valores_validos) == 0:
            return None
        
        fig = px.histogram(
            df, 
            x='valor_pagto',
            nbins=30,
            title='Distribuição dos Valores Pagos',
            labels={'valor_pagto': 'Valor Pago (R$)'},
            color_discrete_sequence=['#A23B72']
        )
        
        fig.update_layout(
            xaxis_title='Valor Pago (R$)',
            yaxis_title='Quantidade',
            bargap=0.1
        )
        
        return fig
    
    except Exception:
        return None

# ============================================================================
# FUNÇÕES DE EXPORTAÇÃO
# ============================================================================

def exportar_excel_completo(df, rel_agencia, rel_gerenciadora, problemas, metricas):
    """Exporta para Excel com múltiplas abas."""
    output = BytesIO()
    
    try:
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Aba 1: Dados completos
            df.to_excel(writer, sheet_name='DADOS COMPLETOS', index=False)
            
            # Aba 2: Relatório por agência
            if not rel_agencia.empty:
                rel_agencia.to_excel(writer, sheet_name='POR AGÊNCIA')
            
            # Aba 3: Relatório por gerenciadora
            if not rel_gerenciadora.empty:
                rel_gerenciadora.to_excel(writer, sheet_name='POR GERENCIADORA')
            
            # Aba 4: Problemas detectados
            problemas_df = gerar_tabela_problemas(problemas)
            if not problemas_df.empty:
                problemas_df.to_excel(writer, sheet_name='PROBLEMAS DETECTADOS', index=False)
                
                # Detalhes dos problemas
                detalhes_data = []
                for categoria, itens in problemas.items():
                    for item in itens:
                        detalhes_data.append({
                            'Categoria': categoria.replace('_', ' ').title(),
                            'Tipo': item['tipo'],
                            'Quantidade': item['quantidade'],
                            'Gravidade': item['gravidade'],
                            'Exemplos': str(item.get('exemplos', []))[:500]  # Limitar tamanho
                        })
                
                if detalhes_data:
                    detalhes_df = pd.DataFrame(detalhes_data)
                    detalhes_df.to_excel(writer, sheet_name='DETALHES PROBLEMAS', index=False)
            
            # Aba 5: Métricas principais
            metricas_df = pd.DataFrame([metricas])
            metricas_df.to_excel(writer, sheet_name='MÉTRICAS', index=False)
            
            # Aba 6: Top beneficiários
            if 'nome' in df.columns and 'valor_pagto' in df.columns:
                top_benef = df[df['valor_pagto'].notna()].nlargest(20, 'valor_pagto')
                if not top_benef.empty:
                    top_benef[['nome', 'valor_pagto', 'agencia', 'gerenciadora']].to_excel(
                        writer, sheet_name='TOP BENEFICIÁRIOS', index=False
                    )
            
            # Aba 7: Estatísticas
            if 'valor_pagto' in df.columns:
                stats = df['valor_pagto'].describe().to_frame().T
                stats.to_excel(writer, sheet_name='ESTATÍSTICAS', index=False)
        
        return output.getvalue()
    
    except Exception as e:
        st.error(f"Erro na exportação: {e}")
        return None

# ============================================================================
# INTERFACE PRINCIPAL
# ============================================================================

def main():
    # ========================================================================
    # SIDEBAR
    # ========================================================================
    with st.sidebar:
        st.header("📁 CARREGAR DADOS")
        
        uploaded_file = st.file_uploader(
            "Escolha o arquivo",
            type=['csv', 'xlsx', 'xls'],
            help="Suporta CSV (;) ou Excel"
        )
        
        st.markdown("---")
        
        st.header("⚙️ CONFIGURAÇÕES")
        mostrar_dados = st.checkbox("Mostrar dados brutos", False)
        mostrar_problemas = st.checkbox("Mostrar problemas detalhados", True)
        mostrar_graficos = st.checkbox("Mostrar gráficos", True)
        top_n = st.slider("Top N agências", 5, 20, 10)
        
        st.markdown("---")
        
        st.header("ℹ️ INFORMAÇÕES")
        st.info(
            "**Sistema de Monitoramento**\n"
            "Programa Operacional de Trabalho (POT)\n\n"
            "Versão: 2.0 Corrigida\n"
            f"Data: {datetime.now().strftime('%d/%m/%Y')}"
        )
    
    # ========================================================================
    # ÁREA PRINCIPAL
    # ========================================================================
    
    # Se não tem arquivo carregado
    if uploaded_file is None:
        st.info("👋 Bem-vindo ao Sistema de Monitoramento de Pagamentos do POT")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("""
            ### 📋 Como usar:
            
            1. **Carregue o arquivo** na barra lateral
            2. **Formatos suportados:**
               - CSV (separado por ; ou ,)
               - Excel (.xlsx, .xls)
            
            3. **Colunas esperadas:**
               - Ordem, Projeto, Nome
               - Agência, Valor Total
               - Valor Pagto, Data Pagto
               - Dias a apagar, CPF
               - Gerenciadora
            
            4. **Funcionalidades:**
               - Detecção automática de problemas
               - Correção de valores monetários
               - Relatórios detalhados
               - Exportação completa
            """)
        
        with col2:
            st.markdown("""
            ### 🚀 Novidades desta versão:
            
            ✅ **Correção de valores monetários**
            ✅ **Tratamento de dados faltantes**
            ✅ **Detecção de inconsistências**
            ✅ **Métricas corretas (sem NaN)**
            ✅ **Tabelas de problemas detalhadas**
            ✅ **Relatórios completos em Excel**
            """)
        
        return
    
    # ========================================================================
    # PROCESSAR ARQUIVO
    # ========================================================================
    with st.spinner('Processando arquivo...'):
        df, mensagem = processar_arquivo(uploaded_file)
    
    if df is None:
        st.error(mensagem)
        return
    
    st.success(f"✅ {mensagem}")
    st.markdown(f"**Arquivo:** `{uploaded_file.name}` | **Registros:** {len(df):,} | **Colunas:** {len(df.columns)}")
    
    # Mostrar preview dos dados
    with st.expander("🔍 Visualizar primeiros registros"):
        st.dataframe(df.head(10), use_container_width=True)
    
    st.markdown("---")
    
    # ========================================================================
    # MÉTRICAS PRINCIPAIS - CORRIGIDAS
    # ========================================================================
    st.header("📈 MÉTRICAS PRINCIPAIS")
    
    metricas = calcular_metricas(df)
    
    # Verificar se temos dados válidos
    if metricas.get('total_valido', 0) == 0 and 'valor_pagto' in df.columns:
        st.warning("⚠️ Nenhum valor monetário válido encontrado. Verifique o formato dos dados.")
    
    # Primeira linha de métricas
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total = metricas.get('total_registros', 0)
        st.metric("Total de Registros", f"{total:,}")
    
    with col2:
        valor_total = metricas.get('valor_total', 0)
        # Formatar corretamente, evitando NaN
        if pd.isna(valor_total) or valor_total == 0:
            display_valor = "R$ 0,00"
        else:
            display_valor = f"R$ {valor_total:,.2f}"
        st.metric("Valor Total Pago", display_valor)
    
    with col3:
        valor_medio = metricas.get('valor_medio', 0)
        if pd.isna(valor_medio) or valor_medio == 0:
            display_medio = "R$ 0,00"
        else:
            display_medio = f"R$ {valor_medio:,.2f}"
        st.metric("Valor Médio", display_medio)
    
    with col4:
        agencias = metricas.get('total_agencias', 0)
        st.metric("Agências Únicas", f"{agencias}")
    
    # Segunda linha de métricas
    col5, col6, col7, col8 = st.columns(4)
    
    with col5:
        dias_medio = metricas.get('dias_medio', 0)
        if pd.isna(dias_medio):
            display_dias = "0,0"
        else:
            display_dias = f"{dias_medio:.1f}"
        st.metric("Dias Médios", display_dias)
    
    with col6:
        valor_dia_medio = metricas.get('valor_dia_medio', 0)
        if pd.isna(valor_dia_medio) or valor_dia_medio == 0:
            display_dia = "R$ 0,00"
        else:
            display_dia = f"R$ {valor_dia_medio:.2f}"
        st.metric("Valor/Dia Médio", display_dia)
    
    with col7:
        vista = metricas.get('total_vista', 0)
        st.metric("VISTA", f"{vista:,}")
    
    with col8:
        rede = metricas.get('total_rede', 0)
        st.metric("REDE CIDADÃO", f"{rede:,}")
    
    st.markdown("---")
    
    # ========================================================================
    # DETECÇÃO DE PROBLEMAS - COM TABELAS DETALHADAS
    # ========================================================================
    st.header("🔍 DETECÇÃO DE PROBLEMAS E INCONSISTÊNCIAS")
    
    with st.spinner("Analisando dados em busca de problemas..."):
        problemas = detectar_problemas_completos(df)
    
    # Resumo em cards
    total_problemas = sum(len(itens) for itens in problemas.values())
    
    if total_problemas > 0:
        st.warning(f"⚠️ Foram detectados {total_problemas} tipos de problemas nos dados")
        
        # Tabela resumo dos problemas
        st.subheader("📋 Resumo dos Problemas Detectados")
        problemas_df = gerar_tabela_problemas(problemas)
        
        if not problemas_df.empty:
            # Colorir por gravidade
            def color_gravidade(val):
                if val == 'Crítica':
                    return 'background-color: #ff4444; color: white'
                elif val == 'Alta':
                    return 'background-color: #ff9444; color: white'
                elif val == 'Média':
                    return 'background-color: #ffd544; color: black'
                else:
                    return 'background-color: #44ff44; color: black'
            
            styled_df = problemas_df.style.applymap(color_gravidade, subset=['Gravidade'])
            st.dataframe(styled_df, use_container_width=True)
            
            # Detalhes por categoria
            if mostrar_problemas:
                st.subheader("📊 Detalhamento por Categoria")
                
                tabs = st.tabs([cat.replace('_', ' ').title() for cat in problemas.keys() if problemas[cat]])
                
                tab_index = 0
                for categoria, itens in problemas.items():
                    if itens:
                        with tabs[tab_index]:
                            for item in itens:
                                with st.expander(f"❌ {item['tipo']} ({item['quantidade']} registros)"):
                                    col_det1, col_det2 = st.columns([1, 2])
                                    
                                    with col_det1:
                                        st.metric("Quantidade", item['quantidade'])
                                        st.metric("Gravidade", item['gravidade'])
                                    
                                    with col_det2:
                                        if item.get('exemplos'):
                                            st.write("**Exemplos:**")
                                            for exemplo in item['exemplos']:
                                                st.write(f"- {exemplo}")
                                        else:
                                            st.write("Sem exemplos específicos.")
                        tab_index += 1
    else:
        st.success("✅ Nenhum problema crítico detectado nos dados!")
    
    st.markdown("---")
    
    # ========================================================================
    # ABAS DE ANÁLISE
    # ========================================================================
    tab1, tab2, tab3, tab4 = st.tabs([
        "📋 VISÃO GERAL", 
        "🏢 POR AGÊNCIA", 
        "🏦 POR GERENCIADORA", 
        "💾 EXPORTAR"
    ])
    
    with tab1:
        if mostrar_dados:
            st.subheader("Dados Processados")
            st.dataframe(df, use_container_width=True, height=400)
        
        # Estatísticas
        st.subheader("📊 Estatísticas Descritivas")
        
        col_stat1, col_stat2 = st.columns(2)
        
        with col_stat1:
            if 'valor_pagto' in df.columns:
                st.write("**Valores Pagos**")
                valores_validos = df['valor_pagto'].dropna()
                if len(valores_validos) > 0:
                    stats = valores_validos.describe().to_frame().round(2)
                    st.dataframe(stats, use_container_width=True)
                else:
                    st.write("Nenhum valor válido encontrado.")
        
        with col_stat2:
            if 'dias_apagar' in df.columns:
                st.write("**Dias a Pagar**")
                dias_validos = df['dias_apagar'].dropna()
                if len(dias_validos) > 0:
                    dias_stats = dias_validos.describe().to_frame().round(2)
                    st.dataframe(dias_stats, use_container_width=True)
                else:
                    st.write("Nenhum dado válido encontrado.")
        
        # Informações do dataset
        with st.expander("🔍 Informações do Dataset"):
            st.write(f"**Total de registros:** {len(df)}")
            st.write(f"**Total de colunas:** {len(df.columns)}")
            st.write(f"**Memória aproximada:** {sys.getsizeof(df) / 1024 / 1024:.2f} MB")
            
            if 'data_pagto' in df.columns:
                datas_validas = df['data_pagto'].dropna()
                if len(datas_validas) > 0:
                    st.write(f"**Período:** {datas_validas.min().strftime('%d/%m/%Y')} a {datas_validas.max().strftime('%d/%m/%Y')}")
    
    with tab2:
        st.subheader("🏢 Análise por Agência")
        
        rel_agencia = gerar_relatorio_agencia(df)
        
        if not rel_agencia.empty:
            st.dataframe(rel_agencia, use_container_width=True)
            
            # Top agências
            st.subheader(f"🏆 Top {top_n} Agências")
            top_df = rel_agencia.head(top_n)
            st.dataframe(top_df, use_container_width=True)
            
            # Gráfico
            if mostrar_graficos:
                fig = criar_grafico_barras_agencia(df, top_n)
                if fig:
                    st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Não foi possível gerar análise por agência. Verifique se há dados válidos.")
    
    with tab3:
        st.subheader("🏦 Análise por Gerenciadora")
        
        rel_gerenciadora = gerar_relatorio_gerenciadora(df)
        
        if not rel_gerenciadora.empty:
            st.dataframe(rel_gerenciadora, use_container_width=True)
            
            # Gráfico de distribuição
            if mostrar_graficos:
                fig = criar_grafico_distribuicao(df)
                if fig:
                    st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Não foi possível gerar análise por gerenciadora. Verifique se há dados válidos.")
    
    with tab4:
        st.subheader("💾 Exportação de Dados")
        
        # Gerar relatórios
        rel_agencia = gerar_relatorio_agencia(df)
        rel_gerenciadora = gerar_relatorio_gerenciadora(df)
        
        col_exp1, col_exp2, col_exp3 = st.columns(3)
        
        with col_exp1:
            # CSV dos dados processados
            csv_data = df.to_csv(index=False, sep=';', decimal=',')
            st.download_button(
                label="📥 Baixar CSV",
                data=csv_data,
                file_name="dados_pot_processados.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col_exp2:
            # Excel completo
            excel_data = exportar_excel_completo(df, rel_agencia, rel_gerenciadora, problemas, metricas)
            if excel_data:
                st.download_button(
                    label="📥 Baixar Excel Completo",
                    data=excel_data,
                    file_name="relatorio_pot_completo.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
        
        with col_exp3:
            # JSON para integração
            json_data = df.to_json(orient='records', indent=2, force_ascii=False)
            st.download_button(
                label="📥 Baixar JSON",
                data=json_data,
                file_name="dados_pot.json",
                mime="application/json",
                use_container_width=True
            )
        
        # Relatórios individuais
        st.markdown("---")
        st.subheader("📊 Relatórios Individuais")
        
        col_rel1, col_rel2, col_rel3 = st.columns(3)
        
        with col_rel1:
            if not rel_agencia.empty:
                csv_agencia = rel_agencia.to_csv(sep=';', decimal=',')
                st.download_button(
                    label="🏢 Relatório por Agência",
                    data=csv_agencia,
                    file_name="relatorio_agencias.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        
        with col_rel2:
            if not rel_gerenciadora.empty:
                csv_gerenciadora = rel_gerenciadora.to_csv(sep=';', decimal=',')
                st.download_button(
                    label="🏦 Relatório por Gerenciadora",
                    data=csv_gerenciadora,
                    file_name="relatorio_gerenciadoras.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        
        with col_rel3:
            # Relatório de problemas
            if total_problemas > 0:
                problemas_csv = problemas_df.to_csv(index=False, sep=';')
                st.download_button(
                    label="🔍 Relatório de Problemas",
                    data=problemas_csv,
                    file_name="problemas_detectados.csv",
                    mime="text/csv",
                    use_container_width=True
                )
    
    # ========================================================================
    # RODAPÉ
    # ========================================================================
    st.markdown("---")
    st.markdown(
        f"""
        <div style='text-align: center; color: gray; font-size: 0.9em;'>
        Sistema de Monitoramento de Pagamentos - Programa Operacional de Trabalho (POT) | 
        Processado em: {datetime.now().strftime('%d/%m/%Y %H:%M')} | 
        Problemas detectados: {total_problemas}
        </div>
        """,
        unsafe_allow_html=True
    )

# ============================================================================
# EXECUTAR APLICAÇÃO
# ============================================================================
if __name__ == "__main__":
    main()
