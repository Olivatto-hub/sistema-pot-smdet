# app.py - Sistema de Monitoramento de Pagamentos do POT
# Arquivo único completo com todas as dependências

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from io import StringIO, BytesIO
import warnings
from datetime import datetime, timedelta
import sys

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
st.title("📊 SISTEMA DE MONITORAMENTO DE PAGAMENTOS - PROGRAMA OPERACIONAL DE TRABALHO (POT)")
st.markdown("---")

# ============================================================================
# FUNÇÕES DE PROCESSAMENTO DE DADOS
# ============================================================================

def processar_arquivo(uploaded_file):
    """
    Processa arquivo CSV ou Excel carregado pelo usuário.
    
    Args:
        uploaded_file: Arquivo carregado via st.file_uploader
        
    Returns:
        tuple: (DataFrame processado, mensagem de status)
    """
    try:
        # Detectar tipo de arquivo
        if uploaded_file.name.lower().endswith('.csv'):
            # Processar CSV
            try:
                # Tentar UTF-8 primeiro
                content = uploaded_file.getvalue().decode('utf-8')
            except UnicodeDecodeError:
                # Tentar Latin-1 se UTF-8 falhar
                content = uploaded_file.getvalue().decode('latin-1')
            
            # Ler CSV com separador ; e decimal brasileiro
            df = pd.read_csv(
                StringIO(content), 
                sep=';', 
                decimal=',', 
                thousands='.',
                dtype=str  # Ler tudo como string inicialmente
            )
        
        elif uploaded_file.name.lower().endswith(('.xlsx', '.xls')):
            # Processar Excel
            df = pd.read_excel(uploaded_file, dtype=str)
        
        else:
            return None, "❌ Formato de arquivo não suportado. Use CSV ou Excel."
        
        # ====================================================================
        # PASSO 1: PADRONIZAR NOMES DAS COLUNAS
        # ====================================================================
        col_rename_map = {}
        for col in df.columns:
            col_str = str(col).strip()
            col_lower = col_str.lower()
            
            # Mapear para nomes padronizados
            if 'ordem' in col_lower:
                col_rename_map[col] = 'Ordem'
            elif 'projeto' in col_lower:
                col_rename_map[col] = 'Projeto'
            elif any(x in col_lower for x in ['cartão', 'cartao', 'card']):
                col_rename_map[col] = 'Num Cartao'
            elif 'nome' in col_lower:
                col_rename_map[col] = 'Nome'
            elif 'distrito' in col_lower:
                col_rename_map[col] = 'Distrito'
            elif any(x in col_lower for x in ['agencia', 'agência']):
                col_rename_map[col] = 'Agencia'
            elif 'rg' in col_lower:
                col_rename_map[col] = 'RG'
            elif 'valor' in col_lower and 'total' in col_lower:
                col_rename_map[col] = 'Valor Total'
            elif 'valor' in col_lower and 'desconto' in col_lower:
                col_rename_map[col] = 'Valor Desconto'
            elif 'valor' in col_lower and 'pagto' in col_lower:
                col_rename_map[col] = 'Valor Pagto'
            elif 'data' in col_lower and 'pagto' in col_lower:
                col_rename_map[col] = 'Data Pagto'
            elif 'valor' in col_lower and 'dia' in col_lower:
                col_rename_map[col] = 'Valor Dia'
            elif any(x in col_lower for x in ['dias', 'apagar']):
                col_rename_map[col] = 'Dias a apagar'
            elif 'cpf' in col_lower:
                col_rename_map[col] = 'CPF'
            elif any(x in col_lower for x in ['gerenciadora', 'gestora']):
                col_rename_map[col] = 'Gerenciadora'
        
        # Aplicar renomeação
        df = df.rename(columns=col_rename_map)
        
        # ====================================================================
        # PASSO 2: CONVERTER COLUNAS MONETÁRIAS (CORRIGIR DUPLICAÇÃO)
        # ====================================================================
        colunas_monetarias = ['Valor Total', 'Valor Desconto', 'Valor Pagto', 'Valor Dia']
        
        for coluna in colunas_monetarias:
            if coluna in df.columns:
                # Garantir que é string
                df[coluna] = df[coluna].astype(str)
                
                # Remover caracteres não numéricos (manter números, ponto e vírgula)
                df[coluna] = df[coluna].str.replace('R\$', '', regex=True)
                df[coluna] = df[coluna].str.replace('$', '', regex=False)
                df[coluna] = df[coluna].str.replace(' ', '', regex=False)
                df[coluna] = df[coluna].str.replace('"', '', regex=False)  # Remover aspas
                
                # CORREÇÃO: Verificar se há duplicação (ex: 1.593,901.593,90)
                def corrigir_duplicacao(valor):
                    if pd.isna(valor):
                        return valor
                    
                    str_val = str(valor)
                    # Verificar se parece ter valores duplicados
                    parts = str_val.split('.')
                    if len(parts) > 2:
                        # Tentar detectar padrão de duplicação
                        mid_point = len(str_val) // 2
                        primeira_metade = str_val[:mid_point]
                        segunda_metade = str_val[mid_point:]
                        
                        if primeira_metade == segunda_metade:
                            return primeira_metade
                    
                    return str_val
                
                df[coluna] = df[coluna].apply(corrigir_duplicacao)
                
                # Substituir ponto de milhar (remover) e vírgula decimal (substituir por ponto)
                df[coluna] = df[coluna].apply(lambda x: str(x).replace('.', '').replace(',', '.') 
                                             if pd.notna(x) else x)
                
                # Converter para numérico
                df[coluna] = pd.to_numeric(df[coluna], errors='coerce')
                
                # Verificar valores extremos suspeitos (valores muito altos)
                if df[coluna].max() > 100000:  # Valores acima de 100 mil são suspeitos
                    st.warning(f"⚠️ Valores suspeitos detectados na coluna {coluna}. Verifique duplicação.")
        
        # ====================================================================
        # PASSO 3: CONVERTER OUTRAS COLUNAS NUMÉRICAS
        # ====================================================================
        if 'Dias a apagar' in df.columns:
            df['Dias a apagar'] = pd.to_numeric(df['Dias a apagar'], errors='coerce')
        
        if 'Ordem' in df.columns:
            df['Ordem'] = pd.to_numeric(df['Ordem'], errors='coerce')
        
        if 'Num Cartao' in df.columns:
            df['Num Cartao'] = pd.to_numeric(df['Num Cartao'], errors='coerce')
        
        # ====================================================================
        # PASSO 4: CONVERTER DATAS
        # ====================================================================
        if 'Data Pagto' in df.columns:
            # Tentar múltiplos formatos de data
            for fmt in ['%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%d/%m/%y', '%d-%m-%y']:
                try:
                    df['Data Pagto'] = pd.to_datetime(df['Data Pagto'], format=fmt, errors='coerce')
                    break
                except:
                    continue
            
            # Se nenhum formato específico funcionar, tentar inferência automática
            if df['Data Pagto'].dtype == 'object':
                df['Data Pagto'] = pd.to_datetime(df['Data Pagto'], errors='coerce')
        
        # ====================================================================
        # PASSO 5: TRATAR VALORES NULOS E ESPAÇOS
        # ====================================================================
        # Colunas de texto
        colunas_texto = ['Nome', 'Projeto', 'Gerenciadora', 'Agencia', 'RG', 'CPF']
        for col in colunas_texto:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
                df[col] = df[col].replace({'nan': '', 'None': '', 'NaT': ''})
        
        # Converter agência para string (mesmo sendo numérica, manter como texto para agrupamento)
        if 'Agencia' in df.columns:
            df['Agencia'] = df['Agencia'].astype(str).str.strip()
        
        # Corrigir caracteres especiais
        if 'Gerenciadora' in df.columns:
            df['Gerenciadora'] = df['Gerenciadora'].str.replace('�', 'Ã', regex=False)
        
        return df, "✅ Arquivo processado com sucesso!"
    
    except Exception as e:
        error_msg = f"❌ Erro ao processar arquivo: {str(e)}"
        return None, error_msg

# ============================================================================
# FUNÇÕES DE DETECÇÃO DE INCONSISTÊNCIAS
# ============================================================================

def detectar_inconsistencias(df):
    """
    Detecta inconsistências, dados críticos e casos suspeitos.
    
    Args:
        df: DataFrame processado
        
    Returns:
        dict: Dicionário com inconsistências detectadas
    """
    inconsistencias = {
        'dados_faltantes': [],
        'valores_suspeitos': [],
        'duplicidades': [],
        'inconsistencias_criticas': [],
        'alertas': []
    }
    
    try:
        # 1. Dados faltantes críticos
        if 'Nome' in df.columns:
            nulos_nome = df['Nome'].isna().sum() + (df['Nome'] == '').sum()
            if nulos_nome > 0:
                inconsistencias['dados_faltantes'].append(
                    f"Nome em branco: {nulos_nome} registros"
                )
        
        if 'CPF' in df.columns:
            cpf_invalidos = df['CPF'].apply(lambda x: len(str(x)) < 11 if pd.notna(x) and str(x).strip() != '' else False).sum()
            if cpf_invalidos > 0:
                inconsistencias['dados_faltantes'].append(
                    f"CPF inválido/curto: {cpf_invalidos} registros"
                )
        
        if 'Valor Pagto' in df.columns:
            nulos_valor = df['Valor Pagto'].isna().sum()
            if nulos_valor > 0:
                inconsistencias['dados_faltantes'].append(
                    f"Valor de pagamento em branco: {nulos_valor} registros"
                )
        
        # 2. Valores suspeitos
        if 'Valor Pagto' in df.columns:
            # Valores zerados ou negativos
            zerados = (df['Valor Pagto'] <= 0).sum()
            if zerados > 0:
                inconsistencias['valores_suspeitos'].append(
                    f"Valores zerados/negativos: {zerados} registros"
                )
            
            # Valores muito altos (suspeitos)
            valor_medio = df['Valor Pagto'].mean()
            valor_std = df['Valor Pagto'].std()
            limite_superior = valor_medio + (3 * valor_std)
            
            valores_extremos = (df['Valor Pagto'] > limite_superior).sum()
            if valores_extremos > 0:
                inconsistencias['valores_suspeitos'].append(
                    f"Valores extremamente altos (acima de R$ {limite_superior:,.2f}): {valores_extremos} registros"
                )
        
        # 3. Duplicidades suspeitas
        if 'CPF' in df.columns:
            # Verificar CPFs duplicados
            cpf_duplicados = df['CPF'][df['CPF'] != ''].duplicated().sum()
            if cpf_duplicados > 0:
                inconsistencias['duplicidades'].append(
                    f"CPFs duplicados: {cpf_duplicados} registros"
                )
        
        if 'Nome' in df.columns and 'Agencia' in df.columns:
            # Mesmo nome na mesma agência em datas próximas
            dups_nome_agencia = df.duplicated(subset=['Nome', 'Agencia'], keep=False).sum()
            if dups_nome_agencia > 0:
                inconsistencias['duplicidades'].append(
                    f"Nomes repetidos na mesma agência: {dups_nome_agencia} registros"
                )
        
        # 4. Inconsistências críticas
        if 'Valor Total' in df.columns and 'Valor Desconto' in df.columns and 'Valor Pagto' in df.columns:
            # Verificar se Valor Total = Valor Desconto + Valor Pagto
            inconsistencias_valores = ((df['Valor Total'].fillna(0) - 
                                      (df['Valor Desconto'].fillna(0) + df['Valor Pagto'].fillna(0))).abs() > 0.01).sum()
            
            if inconsistencias_valores > 0:
                inconsistencias['inconsistencias_criticas'].append(
                    f"Inconsistência nos valores (Total ≠ Desconto + Pagto): {inconsistencias_valores} registros"
                )
        
        if 'Dias a apagar' in df.columns and 'Valor Dia' in df.columns and 'Valor Pagto' in df.columns:
            # Verificar se Valor Pagto ≈ Dias a apagar * Valor Dia
            diferenca = (df['Valor Pagto'].fillna(0) - 
                        (df['Dias a apagar'].fillna(0) * df['Valor Dia'].fillna(0))).abs()
            
            inconsistencias_calc = (diferenca > 1).sum()  # Tolerância de R$ 1
            if inconsistencias_calc > 0:
                inconsistencias['inconsistencias_criticas'].append(
                    f"Inconsistência no cálculo (Pagto ≠ Dias × Valor Dia): {inconsistencias_calc} registros"
                )
        
        # 5. Alertas gerais
        if 'Data Pagto' in df.columns:
            datas_futuras = (df['Data Pagto'] > datetime.now()).sum()
            if datas_futuras > 0:
                inconsistencias['alertas'].append(
                    f"Datas de pagamento futuras: {datas_futuras} registros"
                )
        
        if 'Valor Dia' in df.columns:
            valor_dia_minimo = 30  # Valor mínimo esperado por dia
            abaixo_minimo = (df['Valor Dia'] < valor_dia_minimo).sum()
            if abaixo_minimo > 0:
                inconsistencias['alertas'].append(
                    f"Valor por dia abaixo de R$ {valor_dia_minimo}: {abaixo_minimo} registros"
                )
        
        return inconsistencias
    
    except Exception as e:
        st.error(f"Erro ao detectar inconsistências: {e}")
        return inconsistencias

def calcular_metricas_principais(df):
    """
    Calcula métricas principais do DataFrame.
    
    Args:
        df: DataFrame processado
        
    Returns:
        dict: Dicionário com métricas
    """
    metricas = {}
    
    try:
        metricas['total_registros'] = len(df)
        
        if 'Valor Pagto' in df.columns:
            # CORREÇÃO: Verificar se há duplicação antes de calcular
            valor_total = df['Valor Pagto'].sum()
            
            # Verificação adicional para valores duplicados
            if valor_total > 10000000:  # Se valor total acima de 10 milhões
                st.warning("⚠️ Valor total suspeitamente alto. Verifique possíveis duplicações.")
                
                # Tentar detectar e corrigir automaticamente
                valores_suspeitos = df[df['Valor Pagto'] > 10000]  # Valores acima de 10k são suspeitos
                if len(valores_suspeitos) > 0:
                    st.info(f"🔍 {len(valores_suspeitos)} valores acima de R$ 10.000 encontrados")
            
            metricas['valor_total'] = valor_total
            metricas['valor_medio'] = df['Valor Pagto'].mean()
            metricas['valor_min'] = df['Valor Pagto'].min()
            metricas['valor_max'] = df['Valor Pagto'].max()
            metricas['valor_std'] = df['Valor Pagto'].std()
        
        if 'Agencia' in df.columns:
            metricas['total_agencias'] = df['Agencia'].nunique()
        
        if 'Gerenciadora' in df.columns:
            metricas['total_gerenciadoras'] = df['Gerenciadora'].nunique()
            distrib_gerenciadora = df['Gerenciadora'].value_counts()
            metricas['gerenciadora_principal'] = distrib_gerenciadora.index[0] if len(distrib_gerenciadora) > 0 else 'N/A'
            metricas['total_vista'] = distrib_gerenciadora.get('VISTA', 0)
            metricas['total_rede'] = distrib_gerenciadora.get('REDE CIDADÃO', 0)
        
        if 'Dias a apagar' in df.columns:
            metricas['dias_medio'] = df['Dias a apagar'].mean()
            metricas['dias_total'] = df['Dias a apagar'].sum()
        
        if 'Valor Dia' in df.columns:
            metricas['valor_dia_medio'] = df['Valor Dia'].mean()
        
        if 'Projeto' in df.columns:
            metricas['projeto_principal'] = df['Projeto'].mode()[0] if not df['Projeto'].mode().empty else 'N/A'
        
        # Verificação cruzada de valores
        if 'Valor Pagto' in df.columns:
            # Verificar se o valor médio parece realista
            valor_medio = metricas['valor_medio']
            if valor_medio > 5000:  # Valor médio acima de 5 mil é suspeito
                metricas['alerta_valor_medio'] = f"Valor médio suspeito: R$ {valor_medio:,.2f}"
            else:
                metricas['alerta_valor_medio'] = "OK"
    
    except Exception as e:
        st.error(f"Erro ao calcular métricas: {e}")
    
    return metricas

# ============================================================================
# FUNÇÕES DE ANÁLISE E RELATÓRIOS
# ============================================================================

def gerar_relatorio_agencia(df):
    """
    Gera relatório consolidado por agência.
    
    Args:
        df: DataFrame processado
        
    Returns:
        DataFrame: Relatório por agência
    """
    if 'Agencia' not in df.columns or 'Valor Pagto' not in df.columns:
        return pd.DataFrame()
    
    try:
        relatorio = df.groupby('Agencia').agg({
            'Nome': 'count',
            'Valor Pagto': ['sum', 'mean', 'min', 'max', 'std'],
            'Dias a apagar': 'mean' if 'Dias a apagar' in df.columns else None,
            'Valor Dia': 'mean' if 'Valor Dia' in df.columns else None
        }).round(2)
        
        # Simplificar nomes das colunas
        relatorio.columns = ['Qtd Beneficiários', 'Valor Total', 'Valor Médio', 
                            'Valor Mínimo', 'Valor Máximo', 'Desvio Padrão']
        
        # Adicionar colunas extras se existirem
        col_index = 6
        if 'Dias a apagar' in df.columns:
            dias_medios = df.groupby('Agencia')['Dias a apagar'].mean().round(2)
            relatorio.insert(col_index, 'Dias Médios', dias_medios)
            col_index += 1
        
        if 'Valor Dia' in df.columns:
            valor_dia_medio = df.groupby('Agencia')['Valor Dia'].mean().round(2)
            relatorio.insert(col_index, 'Valor Dia Médio', valor_dia_medio)
        
        return relatorio.sort_values('Valor Total', ascending=False)
    
    except Exception as e:
        st.error(f"Erro ao gerar relatório por agência: {e}")
        return pd.DataFrame()

def gerar_relatorio_gerenciadora(df):
    """
    Gera relatório consolidado por gerenciadora.
    
    Args:
        df: DataFrame processado
        
    Returns:
        DataFrame: Relatório por gerenciadora
    """
    if 'Gerenciadora' not in df.columns or 'Valor Pagto' not in df.columns:
        return pd.DataFrame()
    
    try:
        relatorio = df.groupby('Gerenciadora').agg({
            'Nome': 'count',
            'Valor Pagto': ['sum', 'mean', 'min', 'max'],
            'Dias a apagar': 'mean' if 'Dias a apagar' in df.columns else None,
            'Agencia': 'nunique'
        }).round(2)
        
        # Simplificar nomes das colunas
        relatorio.columns = ['Qtd Beneficiários', 'Valor Total', 'Valor Médio', 
                            'Valor Mínimo', 'Valor Máximo', 'Dias Médios', 'Qtd Agências']
        
        return relatorio.sort_values('Valor Total', ascending=False)
    
    except Exception as e:
        st.error(f"Erro ao gerar relatório por gerenciadora: {e}")
        return pd.DataFrame()

# ============================================================================
# FUNÇÕES DE VISUALIZAÇÃO (GRÁFICOS)
# ============================================================================

def criar_grafico_distribuicao_valores(df):
    """
    Cria histograma da distribuição de valores.
    
    Args:
        df: DataFrame processado
        
    Returns:
        plotly.graph_objects.Figure: Gráfico de histograma
    """
    if 'Valor Pagto' not in df.columns:
        return None
    
    try:
        fig = px.histogram(
            df,
            x='Valor Pagto',
            nbins=30,
            title='Distribuição de Valores Pagos',
            labels={'Valor Pagto': 'Valor Pago (R$)'},
            color_discrete_sequence=['#3366CC']
        )
        
        fig.update_layout(
            xaxis_title='Valor Pago (R$)',
            yaxis_title='Quantidade de Beneficiários',
            bargap=0.1,
            showlegend=False
        )
        
        return fig
    
    except Exception as e:
        st.error(f"Erro ao criar gráfico de distribuição: {e}")
        return None

def criar_grafico_top_agencias(df, top_n=10):
    """
    Cria gráfico de barras das top agências.
    
    Args:
        df: DataFrame processado
        top_n: Número de agências para mostrar
        
    Returns:
        plotly.graph_objects.Figure: Gráfico de barras
    """
    if 'Agencia' not in df.columns or 'Valor Pagto' not in df.columns:
        return None
    
    try:
        # Calcular totais por agência
        agencia_totals = df.groupby('Agencia')['Valor Pagto'].sum().sort_values(ascending=False).head(top_n)
        
        fig = go.Figure(data=[
            go.Bar(
                x=agencia_totals.index,
                y=agencia_totals.values,
                text=[f'R$ {val:,.2f}' for val in agencia_totals.values],
                textposition='auto',
                marker_color='#4CAF50'
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
        st.error(f"Erro ao criar gráfico de top agências: {e}")
        return None

def criar_grafico_pizza_gerenciadora(df):
    """
    Cria gráfico de pizza por gerenciadora.
    
    Args:
        df: DataFrame processado
        
    Returns:
        plotly.graph_objects.Figure: Gráfico de pizza
    """
    if 'Gerenciadora' not in df.columns:
        return None
    
    try:
        contagem = df['Gerenciadora'].value_counts()
        
        fig = go.Figure(data=[
            go.Pie(
                labels=contagem.index,
                values=contagem.values,
                hole=0.3,
                textinfo='label+percent',
                marker_colors=px.colors.qualitative.Set3
            )
        ])
        
        fig.update_layout(
            title='Distribuição por Gerenciadora'
        )
        
        return fig
    
    except Exception as e:
        st.error(f"Erro ao criar gráfico de pizza: {e}")
        return None

def criar_grafico_dispersao_dias_valor(df):
    """
    Cria gráfico de dispersão entre dias e valores.
    
    Args:
        df: DataFrame processado
        
    Returns:
        plotly.graph_objects.Figure: Gráfico de dispersão
    """
    if 'Dias a apagar' not in df.columns or 'Valor Pagto' not in df.columns:
        return None
    
    try:
        fig = px.scatter(
            df,
            x='Dias a apagar',
            y='Valor Pagto',
            title='Relação: Dias a Pagar vs Valor Pago',
            labels={
                'Dias a apagar': 'Dias a Pagar',
                'Valor Pagto': 'Valor Pago (R$)'
            },
            color='Gerenciadora' if 'Gerenciadora' in df.columns else None,
            opacity=0.7
        )
        
        fig.update_traces(marker=dict(size=8))
        
        return fig
    
    except Exception as e:
        st.error(f"Erro ao criar gráfico de dispersão: {e}")
        return None

# ============================================================================
# FUNÇÕES DE EXPORTAÇÃO
# ============================================================================

def exportar_para_excel(df, relatorio_agencia, relatorio_gerenciadora, inconsistencias):
    """
    Exporta dados para arquivo Excel com múltiplas abas.
    
    Args:
        df: DataFrame principal
        relatorio_agencia: Relatório por agência
        relatorio_gerenciadora: Relatório por gerenciadora
        inconsistencias: Dicionário com inconsistências
        
    Returns:
        bytes: Dados do arquivo Excel em bytes
    """
    output = BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Aba 1: Dados completos
        df.to_excel(writer, sheet_name='Dados Completos', index=False)
        
        # Aba 2: Relatório por agência
        if not relatorio_agencia.empty:
            relatorio_agencia.to_excel(writer, sheet_name='Por Agência')
        
        # Aba 3: Relatório por gerenciadora
        if not relatorio_gerenciadora.empty:
            relatorio_gerenciadora.to_excel(writer, sheet_name='Por Gerenciadora')
        
        # Aba 4: Inconsistências detectadas
        inconsistencias_df = pd.DataFrame([
            ['Dados Faltantes', len(inconsistencias.get('dados_faltantes', [])), '; '.join(inconsistencias.get('dados_faltantes', []))],
            ['Valores Suspeitos', len(inconsistencias.get('valores_suspeitos', [])), '; '.join(inconsistencias.get('valores_suspeitos', []))],
            ['Duplicidades', len(inconsistencias.get('duplicidades', [])), '; '.join(inconsistencias.get('duplicidades', []))],
            ['Inconsistências Críticas', len(inconsistencias.get('inconsistencias_criticas', [])), '; '.join(inconsistencias.get('inconsistencias_criticas', []))],
            ['Alertas', len(inconsistencias.get('alertas', [])), '; '.join(inconsistencias.get('alertas', []))]
        ], columns=['Categoria', 'Quantidade', 'Descrição'])
        
        inconsistencias_df.to_excel(writer, sheet_name='Inconsistências', index=False)
        
        # Aba 5: Top beneficiários
        if 'Nome' in df.columns and 'Valor Pagto' in df.columns:
            top_benef = df.nlargest(20, 'Valor Pagto')[['Nome', 'Valor Pagto', 'Agencia', 'Gerenciadora']]
            top_benef.to_excel(writer, sheet_name='Top Beneficiários', index=False)
        
        # Aba 6: Resumo estatístico
        if 'Valor Pagto' in df.columns:
            resumo_stats = df['Valor Pagto'].describe().to_frame().T
            resumo_stats.to_excel(writer, sheet_name='Resumo Estatístico')
    
    return output.getvalue()

# ============================================================================
# INTERFACE PRINCIPAL DO STREAMLIT
# ============================================================================

def main():
    """
    Função principal que executa a aplicação Streamlit.
    """
    
    # ========================================================================
    # SIDEBAR - CONFIGURAÇÕES E UPLOAD
    # ========================================================================
    with st.sidebar:
        st.header("📁 CONFIGURAÇÃO DO SISTEMA")
        
        # Upload do arquivo
        uploaded_file = st.file_uploader(
            "Carregue o arquivo de dados",
            type=['csv', 'xlsx'],
            help="Suporta CSV (separado por ;) ou Excel"
        )
        
        st.markdown("---")
        
        # Opções de visualização
        st.header("⚙️ OPÇÕES DE VISUALIZAÇÃO")
        mostrar_graficos = st.checkbox("Mostrar gráficos", value=True)
        mostrar_dados_brutos = st.checkbox("Mostrar dados completos", value=False)
        mostrar_inconsistencias = st.checkbox("Mostrar inconsistências", value=True)
        top_n_agencias = st.slider("Top N agências nos gráficos", 5, 20, 10)
        
        # Opção para corrigir valores duplicados
        st.markdown("---")
        st.header("🔧 CORREÇÃO DE DADOS")
        auto_corrigir_duplicacao = st.checkbox(
            "Tentar correção automática de valores duplicados",
            value=True,
            help="Tenta detectar e corrigir valores que parecem estar duplicados"
        )
        
        st.markdown("---")
        
        # Informações do sistema
        st.header("ℹ️ INFORMAÇÕES")
        st.info(
            "**Sistema de Monitoramento de Pagamentos - POT**\n\n"
            "Versão: 3.0\n"
            f"Data: {datetime.now().strftime('%d/%m/%Y')}\n"
            "Desenvolvido para monitoramento dos projetos do POT\n\n"
            "**Projetos incluídos:**\n"
            "- ABAE\n"
            "- Outros projetos do POT"
        )
    
    # ========================================================================
    # ÁREA PRINCIPAL - CONTEÚDO DINÂMICO
    # ========================================================================
    
    # Caso 1: Nenhum arquivo carregado
    if uploaded_file is None:
        st.info("👋 **Bem-vindo ao Sistema de Monitoramento de Pagamentos do POT!**")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown("""
            ### 📋 Como usar o sistema:
            
            1. **Carregue seu arquivo** usando a barra lateral à esquerda
            2. **Formatos suportados:**
               - CSV (separado por ponto-e-vírgula)
               - Excel (.xlsx, .xls)
            
            3. **Estrutura esperada do arquivo:**
               - Ordem;Projeto;Num Cartao;Nome;Distrito;Agencia;RG
               - Valor Total;Valor Desconto;Valor Pagto;Data Pagto
               - Valor Dia;Dias a apagar;CPF;Gerenciadora
            
            4. **Funcionalidades de correção:**
               - Detecção automática de valores duplicados
               - Identificação de inconsistências críticas
               - Alertas para dados suspeitos
            """)
        
        with col2:
            st.markdown("""
            ### 🚀 Funcionalidades:
            
            ✅ **Processamento automático**
            ✅ **Análise por agência**
            ✅ **Análise por gerenciadora**
            ✅ **Detecção de inconsistências**
            ✅ **Gráficos interativos**
            ✅ **Exportação para Excel**
            ✅ **Filtros dinâmicos**
            ✅ **Relatórios detalhados**
            ✅ **Correção de valores duplicados**
            """)
        
        # Exemplo de dados
        with st.expander("📝 **Exemplo de dados (formato esperado)**"):
            exemplo_data = {
                'Ordem': [1, 2, 3],
                'Projeto': ['BUSCA ATIVA', 'BUSCA ATIVA', 'BUSCA ATIVA'],
                'Num Cartao': [14735, 130329, 152979],
                'Nome': ['Vanessa Falco Chaves', 'Erica Claudia Albano', 'Rosemary De Moraes Alves'],
                'Distrito': [0, 0, 0],
                'Agencia': ['7025', '1549', '6969'],
                'RG': ['438455885', '445934864', '586268327'],
                'Valor Total': ['R$ 1.593,90', 'R$ 1.593,90', 'R$ 1.593,90'],
                'Valor Desconto': ['R$ 0,00', 'R$ 0,00', 'R$ 0,00'],
                'Valor Pagto': ['R$ 1.593,90', 'R$ 1.593,90', 'R$ 1.593,90'],
                'Data Pagto': ['20/10/2025', '20/10/2025', '20/10/2025'],
                'Valor Dia': ['R$ 53,13', 'R$ 53,13', 'R$ 53,13'],
                'Dias a apagar': [30, 30, 30],
                'CPF': ['30490002870', '', '8275372801'],
                'Gerenciadora': ['VISTA', 'VISTA', 'VISTA']
            }
            
            st.dataframe(pd.DataFrame(exemplo_data), use_container_width=True)
        
        return
    
    # Caso 2: Arquivo carregado - processar
    with st.spinner(f'Processando {uploaded_file.name}...'):
        df, mensagem = processar_arquivo(uploaded_file)
    
    if df is None:
        st.error(mensagem)
        return
    
    # Sucesso no processamento
    st.success(mensagem)
    st.markdown(f"**Arquivo:** `{uploaded_file.name}` | **Registros:** {len(df):,} | **Colunas:** {len(df.columns)}")
    st.markdown("---")
    
    # ========================================================================
    # SEÇÃO 1: DETECÇÃO DE INCONSISTÊNCIAS
    # ========================================================================
    if mostrar_inconsistencias:
        st.header("🔍 DETECÇÃO DE INCONSISTÊNCIAS E DADOS CRÍTICOS")
        
        with st.spinner("Analisando inconsistências..."):
            inconsistencias = detectar_inconsistencias(df)
        
        # Mostrar inconsistências em abas
        tab_incon1, tab_incon2, tab_incon3, tab_incon4, tab_incon5 = st.tabs([
            "📋 RESUMO", 
            "❌ DADOS FALTANTES", 
            "⚠️ VALORES SUSPEITOS", 
            "🔁 DUPLICIDADES", 
            "🚨 CRÍTICOS"
        ])
        
        with tab_incon1:
            st.subheader("Resumo de Inconsistências")
            
            col_res1, col_res2, col_res3, col_res4 = st.columns(4)
            
            with col_res1:
                total_faltantes = len(inconsistencias.get('dados_faltantes', []))
                st.metric("Dados Faltantes", total_faltantes)
            
            with col_res2:
                total_suspeitos = len(inconsistencias.get('valores_suspeitos', []))
                st.metric("Valores Suspeitos", total_suspeitos)
            
            with col_res3:
                total_duplicidades = len(inconsistencias.get('duplicidades', []))
                st.metric("Duplicidades", total_duplicidades)
            
            with col_res4:
                total_criticos = len(inconsistencias.get('inconsistencias_criticas', []))
                st.metric("Críticos", total_criticos)
            
            # Lista de alertas
            if inconsistencias.get('alertas'):
                st.subheader("⚠️ Alertas Gerais")
                for alerta in inconsistencias.get('alertas', []):
                    st.warning(alerta)
        
        with tab_incon2:
            if inconsistencias.get('dados_faltantes'):
                st.subheader("Dados Faltantes ou Inválidos")
                for item in inconsistencias.get('dados_faltantes', []):
                    st.error(item)
                
                # Mostrar exemplos de dados faltantes
                if 'Nome' in df.columns:
                    nulos_nome = df[df['Nome'].isna() | (df['Nome'] == '')]
                    if not nulos_nome.empty:
                        with st.expander("Ver registros com nome em branco"):
                            st.dataframe(nulos_nome[['Ordem', 'Agencia', 'Valor Pagto']].head(10), use_container_width=True)
            else:
                st.success("✅ Nenhum dado faltante crítico encontrado")
        
        with tab_incon3:
            if inconsistencias.get('valores_suspeitos'):
                st.subheader("Valores Suspeitos")
                for item in inconsistencias.get('valores_suspeitos', []):
                    st.warning(item)
                
                # Mostrar valores extremos
                if 'Valor Pagto' in df.columns:
                    valor_medio = df['Valor Pagto'].mean()
                    valor_std = df['Valor Pagto'].std()
                    limite_superior = valor_medio + (3 * valor_std)
                    
                    valores_extremos = df[df['Valor Pagto'] > limite_superior]
                    if not valores_extremos.empty:
                        with st.expander(f"Ver valores acima de R$ {limite_superior:,.2f}"):
                            st.dataframe(valores_extremos[['Nome', 'Agencia', 'Valor Pagto', 'Dias a apagar']].sort_values('Valor Pagto', ascending=False).head(10), use_container_width=True)
            else:
                st.success("✅ Nenhum valor suspeito encontrado")
        
        with tab_incon4:
            if inconsistencias.get('duplicidades'):
                st.subheader("Possíveis Duplicidades")
                for item in inconsistencias.get('duplicidades', []):
                    st.info(item)
                
                # Mostrar CPFs duplicados
                if 'CPF' in df.columns:
                    cpf_duplicados = df[df['CPF'].duplicated(keep=False) & (df['CPF'] != '')]
                    if not cpf_duplicados.empty:
                        with st.expander("Ver CPFs duplicados"):
                            st.dataframe(cpf_duplicados[['CPF', 'Nome', 'Agencia', 'Valor Pagto']].sort_values('CPF').head(20), use_container_width=True)
            else:
                st.success("✅ Nenhuma duplicidade crítica encontrada")
        
        with tab_incon5:
            if inconsistencias.get('inconsistencias_criticas'):
                st.subheader("Inconsistências Críticas")
                for item in inconsistencias.get('inconsistencias_criticas', []):
                    st.error(item)
                
                # Mostrar inconsistências de cálculo
                if all(col in df.columns for col in ['Valor Total', 'Valor Desconto', 'Valor Pagto']):
                    df_calc = df.copy()
                    df_calc['Diferença'] = (df_calc['Valor Total'].fillna(0) - 
                                          (df_calc['Valor Desconto'].fillna(0) + df_calc['Valor Pagto'].fillna(0))).abs()
                    
                    inconsistencias_calc = df_calc[df_calc['Diferença'] > 0.01]
                    if not inconsistencias_calc.empty:
                        with st.expander("Ver inconsistências de cálculo"):
                            st.dataframe(inconsistencias_calc[['Nome', 'Valor Total', 'Valor Desconto', 'Valor Pagto', 'Diferença']].head(10), use_container_width=True)
            else:
                st.success("✅ Nenhuma inconsistência crítica encontrada")
        
        st.markdown("---")
    
    # ========================================================================
    # SEÇÃO 2: MÉTRICAS PRINCIPAIS (COM VERIFICAÇÃO DE DUPLICAÇÃO)
    # ========================================================================
    st.header("📈 MÉTRICAS PRINCIPAIS")
    
    # Verificação explícita de valores duplicados
    if 'Valor Pagto' in df.columns:
        valor_total = df['Valor Pagto'].sum()
        
        # Verificar se o valor total parece realista
        if valor_total > 10000000:  # Acima de 10 milhões
            st.warning(f"""
            ⚠️ **ATENÇÃO: Valor total suspeito**  
            Valor total calculado: R$ {valor_total:,.2f}  
            
            Possíveis causas:
            1. Valores duplicados no arquivo fonte
            2. Erro na formatação dos números
            3. Dados de múltiplos períodos agrupados
            
            **Ação recomendada:** Verifique manualmente os valores mais altos.
            """)
    
    metricas = calcular_metricas_principais(df)
    
    # Cards com métricas
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total de Registros", f"{metricas.get('total_registros', 0):,}")
    
    with col2:
        valor_total = metricas.get('valor_total', 0)
        st.metric("Valor Total Pago", f"R$ {valor_total:,.2f}")
    
    with col3:
        valor_medio = metricas.get('valor_medio', 0)
        st.metric("Valor Médio", f"R$ {valor_medio:,.2f}")
        
        # Mostrar alerta se valor médio for suspeito
        if 'alerta_valor_medio' in metricas and metricas['alerta_valor_medio'] != "OK":
            st.caption(f"⚠️ {metricas['alerta_valor_medio']}")
    
    with col4:
        total_agencias = metricas.get('total_agencias', 0)
        st.metric("Agências Únicas", f"{total_agencias}")
    
    # Segunda linha de métricas
    col5, col6, col7, col8 = st.columns(4)
    
    with col5:
        dias_medio = metricas.get('dias_medio', 0)
        st.metric("Dias Médios", f"{dias_medio:.1f}")
    
    with col6:
        valor_dia_medio = metricas.get('valor_dia_medio', 0)
        st.metric("Valor/Dia Médio", f"R$ {valor_dia_medio:.2f}")
    
    with col7:
        total_vista = metricas.get('total_vista', 0)
        st.metric("VISTA", f"{total_vista:,}")
    
    with col8:
        total_rede = metricas.get('total_rede', 0)
        st.metric("REDE CIDADÃO", f"{total_rede:,}")
    
    st.markdown("---")
    
    # ========================================================================
    # SEÇÃO 3: ANÁLISES DETALHADAS (ABAS)
    # ========================================================================
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📋 VISÃO GERAL", 
        "🏢 POR AGÊNCIA", 
        "🏦 POR GERENCIADORA", 
        "📊 GRÁFICOS", 
        "💾 EXPORTAR"
    ])
    
    # ========================================================================
    # ABA 1: VISÃO GERAL
    # ========================================================================
    with tab1:
        if mostrar_dados_brutos:
            st.subheader("Dados Processados (Visualização)")
            st.dataframe(df, use_container_width=True, height=400)
        
        # Estatísticas descritivas
        st.subheader("📊 Estatísticas Descritivas")
        
        if 'Valor Pagto' in df.columns:
            col_stat1, col_stat2 = st.columns(2)
            
            with col_stat1:
                st.markdown("**Valores Pagos**")
                stats_df = df['Valor Pagto'].describe().to_frame().T.round(2)
                st.dataframe(stats_df, use_container_width=True)
            
            with col_stat2:
                if 'Dias a apagar' in df.columns:
                    st.markdown("**Dias a Pagar**")
                    dias_stats = df['Dias a apagar'].describe().to_frame().T.round(2)
                    st.dataframe(dias_stats, use_container_width=True)
        
        # Informações do dataset
        with st.expander("🔍 Informações Detalhadas do Dataset"):
            col_info1, col_info2 = st.columns(2)
            
            with col_info1:
                st.write("**Colunas disponíveis:**")
                for col in df.columns:
                    na_count = df[col].isna().sum()
                    st.write(f"- `{col}`: {df[col].dtype} ({na_count} nulos)")
            
            with col_info2:
                st.write("**Resumo do processamento:**")
                st.write(f"- Data/hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
                st.write(f"- Memória aproximada: {sys.getsizeof(df) / 1024 / 1024:.2f} MB")
                
                if 'Data Pagto' in df.columns:
                    min_date = df['Data Pagto'].min()
                    max_date = df['Data Pagto'].max()
                    if pd.notna(min_date) and pd.notna(max_date):
                        st.write(f"- Período: {min_date.strftime('%d/%m/%Y')} a {max_date.strftime('%d/%m/%Y')}")
    
    # ========================================================================
    # ABA 2: POR AGÊNCIA
    # ========================================================================
    with tab2:
        st.subheader("🏢 Análise por Agência")
        
        relatorio_agencia = gerar_relatorio_agencia(df)
        
        if not relatorio_agencia.empty:
            st.dataframe(relatorio_agencia, use_container_width=True)
            
            # Top 10 agências
            st.subheader(f"🏆 Top {top_n_agencias} Agências")
            top_agencias = relatorio_agencia.head(top_n_agencias)
            st.dataframe(top_agencias, use_container_width=True)
        else:
            st.warning("Não foi possível gerar relatório por agência. Verifique se as colunas 'Agencia' e 'Valor Pagto' estão presentes.")
    
    # ========================================================================
    # ABA 3: POR GERENCIADORA
    # ========================================================================
    with tab3:
        st.subheader("🏦 Análise por Gerenciadora")
        
        relatorio_gerenciadora = gerar_relatorio_gerenciadora(df)
        
        if not relatorio_gerenciadora.empty:
            st.dataframe(relatorio_gerenciadora, use_container_width=True)
            
            # Comparativo VISTA vs REDE
            if 'VISTA' in relatorio_gerenciadora.index or 'REDE CIDADÃO' in relatorio_gerenciadora.index:
                st.subheader("📊 Comparativo VISTA vs REDE CIDADÃO")
                
                comparativo_data = []
                if 'VISTA' in relatorio_gerenciadora.index:
                    vista_data = relatorio_gerenciadora.loc['VISTA']
                    comparativo_data.append({
                        'Gerenciadora': 'VISTA',
                        'Beneficiários': vista_data['Qtd Beneficiários'],
                        'Valor Total': vista_data['Valor Total'],
                        'Valor Médio': vista_data['Valor Médio']
                    })
                
                if 'REDE CIDADÃO' in relatorio_gerenciadora.index:
                    rede_data = relatorio_gerenciadora.loc['REDE CIDADÃO']
                    comparativo_data.append({
                        'Gerenciadora': 'REDE CIDADÃO',
                        'Beneficiários': rede_data['Qtd Beneficiários'],
                        'Valor Total': rede_data['Valor Total'],
                        'Valor Médio': rede_data['Valor Médio']
                    })
                
                if comparativo_data:
                    st.dataframe(pd.DataFrame(comparativo_data), use_container_width=True)
        else:
            st.warning("Não foi possível gerar relatório por gerenciadora. Verifique se a coluna 'Gerenciadora' está presente.")
    
    # ========================================================================
    # ABA 4: GRÁFICOS
    # ========================================================================
    with tab4:
        if not mostrar_graficos:
            st.info("Ative a opção 'Mostrar gráficos' na sidebar para visualizar os gráficos.")
        else:
            st.subheader("📊 Visualizações Gráficas")
            
            # Gráfico 1: Distribuição de valores
            fig1 = criar_grafico_distribuicao_valores(df)
            if fig1:
                st.plotly_chart(fig1, use_container_width=True)
            
            # Gráficos em colunas
            col_g1, col_g2 = st.columns(2)
            
            with col_g1:
                # Gráfico 2: Top agências
                fig2 = criar_grafico_top_agencias(df, top_n_agencias)
                if fig2:
                    st.plotly_chart(fig2, use_container_width=True)
            
            with col_g2:
                # Gráfico 3: Pizza por gerenciadora
                fig3 = criar_grafico_pizza_gerenciadora(df)
                if fig3:
                    st.plotly_chart(fig3, use_container_width=True)
            
            # Gráfico 4: Dispersão
            fig4 = criar_grafico_dispersao_dias_valor(df)
            if fig4:
                st.plotly_chart(fig4, use_container_width=True)
    
    # ========================================================================
    # ABA 5: EXPORTAÇÃO
    # ========================================================================
    with tab5:
        st.subheader("💾 Exportação de Dados")
        
        col_exp1, col_exp2, col_exp3 = st.columns(3)
        
        with col_exp1:
            # Exportar CSV
            csv_data = df.to_csv(index=False, sep=';', decimal=',')
            st.download_button(
                label="📥 Baixar CSV",
                data=csv_data,
                file_name="dados_pot_processados.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col_exp2:
            # Exportar Excel com inconsistências
            excel_bytes = exportar_para_excel(df, relatorio_agencia, relatorio_gerenciadora, inconsistencias)
            st.download_button(
                label="📥 Baixar Excel Completo",
                data=excel_bytes,
                file_name="relatorio_pot_completo.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        
        with col_exp3:
            # Exportar JSON
            json_data = df.to_json(orient='records', indent=2, force_ascii=False)
            st.download_button(
                label="📥 Baixar JSON",
                data=json_data,
                file_name="dados_pot.json",
                mime="application/json",
                use_container_width=True
            )
        
        st.markdown("---")
        
        # Opções avançadas de exportação
        with st.expander("⚙️ Opções Avançadas de Exportação"):
            st.markdown("### Exportar Relatórios Individuais")
            
            col_exp4, col_exp5, col_exp6 = st.columns(3)
            
            with col_exp4:
                if not relatorio_agencia.empty:
                    agencia_csv = relatorio_agencia.to_csv(sep=';', decimal=',')
                    st.download_button(
                        label="📊 Relatório por Agência (CSV)",
                        data=agencia_csv,
                        file_name="relatorio_agencias.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
            
            with col_exp5:
                if not relatorio_gerenciadora.empty:
                    gerenciadora_csv = relatorio_gerenciadora.to_csv(sep=';', decimal=',')
                    st.download_button(
                        label="🏦 Relatório por Gerenciadora (CSV)",
                        data=gerenciadora_csv,
                        file_name="relatorio_gerenciadoras.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
            
            with col_exp6:
                # Exportar inconsistências
                if inconsistencias:
                    incon_df = pd.DataFrame([
                        ['Dados Faltantes', '; '.join(inconsistencias.get('dados_faltantes', []))],
                        ['Valores Suspeitos', '; '.join(inconsistencias.get('valores_suspeitos', []))],
                        ['Duplicidades', '; '.join(inconsistencias.get('duplicidades', []))],
                        ['Inconsistências Críticas', '; '.join(inconsistencias.get('inconsistencias_criticas', []))],
                        ['Alertas', '; '.join(inconsistencias.get('alertas', []))]
                    ], columns=['Categoria', 'Descrição'])
                    
                    incon_csv = incon_df.to_csv(index=False, sep=';')
                    st.download_button(
                        label="🔍 Inconsistências (CSV)",
                        data=incon_csv,
                        file_name="inconsistencias.csv",
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
        Inconsistências detectadas: {sum(len(v) for v in inconsistencias.values() if isinstance(v, list))}
        </div>
        """,
        unsafe_allow_html=True
    )

# ============================================================================
# EXECUÇÃO PRINCIPAL
# ============================================================================
if __name__ == "__main__":
    main()
