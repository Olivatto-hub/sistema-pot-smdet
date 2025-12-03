# app.py - Sistema de Monitoramento de Pagamentos do POT
# Versão 1.0 - Corrigido e Testado

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
st.title("📊 SISTEMA DE MONITORAMENTO DE PAGAMENTOS")
st.subheader("Programa Operacional de Trabalho (POT)")
st.markdown("---")

# ============================================================================
# FUNÇÕES DE PROCESSAMENTO DE DADOS
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
                content = uploaded_file.getvalue().decode('utf-8')
            except UnicodeDecodeError:
                content = uploaded_file.getvalue().decode('latin-1')
            
            # Ler CSV
            df = pd.read_csv(
                StringIO(content), 
                sep=';', 
                decimal=',', 
                dtype=str
            )
        
        elif uploaded_file.name.lower().endswith(('.xlsx', '.xls')):
            # Processar Excel
            df = pd.read_excel(uploaded_file, dtype=str)
        
        else:
            return None, "❌ Formato não suportado. Use CSV ou Excel."
        
        # Renomear colunas para padrão
        nome_columns = {
            'Ordem': 'ordem', 'PROJETO': 'projeto', 'Nº Cartão': 'cartao',
            'Nome': 'nome', 'DISTRITO': 'distrito', 'AGÊNCIA': 'agencia',
            'RG': 'rg', 'VALOR TOTAL': 'valor_total', 'VALOR DESCONTO': 'valor_desconto',
            'VALOR PAGTO': 'valor_pagto', 'DATA PAGTO': 'data_pagto',
            'VALOR DIA': 'valor_dia', 'DIAS A APAGAR': 'dias_apagar',
            'CPF': 'cpf', 'GERENCIADORA': 'gerenciadora'
        }
        
        # Converter nomes para minúsculo e padronizar
        df.columns = [str(col).strip().lower() for col in df.columns]
        
        # Renomear colunas conhecidas
        rename_map = {}
        for col in df.columns:
            col_lower = str(col).lower()
            
            if 'ordem' in col_lower:
                rename_map[col] = 'ordem'
            elif 'projeto' in col_lower:
                rename_map[col] = 'projeto'
            elif any(x in col_lower for x in ['cartão', 'cartao', 'card']):
                rename_map[col] = 'cartao'
            elif 'nome' in col_lower:
                rename_map[col] = 'nome'
            elif 'distrito' in col_lower:
                rename_map[col] = 'distrito'
            elif 'agencia' in col_lower or 'agência' in col_lower:
                rename_map[col] = 'agencia'
            elif 'rg' in col_lower:
                rename_map[col] = 'rg'
            elif 'valor' in col_lower and 'total' in col_lower:
                rename_map[col] = 'valor_total'
            elif 'valor' in col_lower and 'desconto' in col_lower:
                rename_map[col] = 'valor_desconto'
            elif 'valor' in col_lower and 'pagto' in col_lower:
                rename_map[col] = 'valor_pagto'
            elif 'data' in col_lower and 'pagto' in col_lower:
                rename_map[col] = 'data_pagto'
            elif 'valor' in col_lower and 'dia' in col_lower:
                rename_map[col] = 'valor_dia'
            elif any(x in col_lower for x in ['dias', 'apagar']):
                rename_map[col] = 'dias_apagar'
            elif 'cpf' in col_lower:
                rename_map[col] = 'cpf'
            elif any(x in col_lower for x in ['gerenciadora', 'gestora']):
                rename_map[col] = 'gerenciadora'
        
        df = df.rename(columns=rename_map)
        
        # ====================================================================
        # CORRIGIR VALORES MONETÁRIOS (EVITAR DUPLICAÇÃO)
        # ====================================================================
        colunas_monetarias = ['valor_total', 'valor_desconto', 'valor_pagto', 'valor_dia']
        
        for coluna in colunas_monetarias:
            if coluna in df.columns:
                df[coluna] = df[coluna].astype(str)
                
                # Limpar valores
                df[coluna] = df[coluna].str.replace('R\$', '', regex=False)
                df[coluna] = df[coluna].str.replace('$', '', regex=False)
                df[coluna] = df[coluna].str.replace(' ', '', regex=False)
                df[coluna] = df[coluna].str.replace('"', '', regex=False)
                df[coluna] = df[coluna].str.replace("'", '', regex=False)
                
                # CORREÇÃO CRÍTICA: Detectar valores duplicados
                def corrigir_valor(valor):
                    if pd.isna(valor) or valor == '':
                        return valor
                    
                    str_val = str(valor).strip()
                    
                    # Detectar padrões como "1.593,901.593,90"
                    if str_val.count(',') > 1:
                        # Encontrar onde está a duplicação
                        parts = str_val.split(',')
                        if len(parts) == 3:  # Padrão de duplicação
                            # Pegar apenas a primeira parte
                            return f"{parts[0]},{parts[1]}"
                    
                    # Detectar se tem ponto no meio (indicando possível duplicação)
                    if str_val.count('.') > 1:
                        # Remover todos os pontos, depois adicionar vírgula como decimal
                        str_val = str_val.replace('.', '')
                        if len(str_val) > 6:
                            # Assume que os últimos 2 dígitos são centavos
                            return f"{str_val[:-2]},{str_val[-2:]}"
                    
                    return str_val
                
                df[coluna] = df[coluna].apply(corrigir_valor)
                
                # Converter para numérico
                df[coluna] = df[coluna].str.replace('.', '', regex=False)
                df[coluna] = df[coluna].str.replace(',', '.', regex=False)
                df[coluna] = pd.to_numeric(df[coluna], errors='coerce')
        
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
                df['data_pagto'] = pd.to_datetime(df['data_pagto'], format='%d/%m/%Y', errors='coerce')
            except:
                try:
                    df['data_pagto'] = pd.to_datetime(df['data_pagto'], errors='coerce')
                except:
                    df['data_pagto'] = pd.NaT
        
        # Limpar texto
        colunas_texto = ['nome', 'projeto', 'gerenciadora', 'agencia', 'rg', 'cpf']
        for col in colunas_texto:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
                df[col] = df[col].replace({'nan': '', 'None': '', 'NaT': ''})
        
        # Padronizar agência
        if 'agencia' in df.columns:
            df['agencia'] = df['agencia'].astype(str).str.strip().str.zfill(4)
        
        # Padronizar gerenciadora
        if 'gerenciadora' in df.columns:
            df['gerenciadora'] = df['gerenciadora'].str.upper().str.strip()
            df['gerenciadora'] = df['gerenciadora'].replace({
                'REDE CIDAD�': 'REDE CIDADÃO',
                'REDE CIDADAO': 'REDE CIDADÃO',
                'VISTA': 'VISTA'
            })
        
        return df, "✅ Arquivo processado com sucesso!"
    
    except Exception as e:
        error_msg = f"❌ Erro: {str(e)}"
        return None, error_msg

# ============================================================================
# FUNÇÕES DE ANÁLISE E DETECÇÃO
# ============================================================================

def calcular_metricas(df):
    """Calcula métricas principais."""
    metricas = {}
    
    try:
        metricas['total_registros'] = len(df)
        
        if 'valor_pagto' in df.columns:
            # Verificação de valores duplicados
            valor_total = df['valor_pagto'].sum()
            valor_medio = df['valor_pagto'].mean()
            
            # Verificar se valores estão realistas
            if valor_medio > 10000:  # Média acima de 10k é suspeita
                st.warning("⚠️ Valor médio muito alto! Verifique possível duplicação.")
            
            metricas['valor_total'] = valor_total
            metricas['valor_medio'] = valor_medio
            metricas['valor_min'] = df['valor_pagto'].min()
            metricas['valor_max'] = df['valor_pagto'].max()
        
        if 'agencia' in df.columns:
            metricas['total_agencias'] = df['agencia'].nunique()
        
        if 'gerenciadora' in df.columns:
            metricas['total_gerenciadoras'] = df['gerenciadora'].nunique()
            metricas['total_vista'] = (df['gerenciadora'] == 'VISTA').sum()
            metricas['total_rede'] = (df['gerenciadora'] == 'REDE CIDADÃO').sum()
        
        if 'dias_apagar' in df.columns:
            metricas['dias_medio'] = df['dias_apagar'].mean()
        
        if 'valor_dia' in df.columns:
            metricas['valor_dia_medio'] = df['valor_dia'].mean()
        
        if 'projeto' in df.columns:
            projetos = df['projeto'].value_counts()
            if len(projetos) > 0:
                metricas['projeto_principal'] = projetos.index[0]
                metricas['total_projetos'] = len(projetos)
        
    except Exception as e:
        st.error(f"Erro nas métricas: {e}")
    
    return metricas

def detectar_problemas(df):
    """Detecta problemas e inconsistências nos dados."""
    problemas = {
        'dados_faltantes': [],
        'valores_estranhos': [],
        'duplicidades': [],
        'inconsistencias': [],
        'alertas': []
    }
    
    # Dados faltantes
    if 'nome' in df.columns:
        nomes_vazios = df['nome'].isna().sum() + (df['nome'] == '').sum()
        if nomes_vazios > 0:
            problemas['dados_faltantes'].append(f"Nomes em branco: {nomes_vazios}")
    
    if 'cpf' in df.columns:
        cpfs_invalidos = df['cpf'].apply(lambda x: len(str(x)) < 11 if pd.notna(x) and str(x).strip() != '' else False).sum()
        if cpfs_invalidos > 0:
            problemas['dados_faltantes'].append(f"CPFs inválidos: {cpfs_invalidos}")
    
    # Valores estranhos
    if 'valor_pagto' in df.columns:
        valores_zerados = (df['valor_pagto'] == 0).sum()
        if valores_zerados > 0:
            problemas['valores_estranhos'].append(f"Valores zerados: {valores_zerados}")
        
        # Verificar valores muito altos
        q3 = df['valor_pagto'].quantile(0.75)
        iqr = df['valor_pagto'].quantile(0.75) - df['valor_pagto'].quantile(0.25)
        limite = q3 + (1.5 * iqr)
        valores_altos = (df['valor_pagto'] > limite).sum()
        
        if valores_altos > 0:
            problemas['valores_estranhos'].append(f"Valores muito altos (> R$ {limite:,.2f}): {valores_altos}")
    
    # Duplicidades
    if 'cpf' in df.columns:
        cpf_duplicados = df[df['cpf'] != '']['cpf'].duplicated().sum()
        if cpf_duplicados > 0:
            problemas['duplicidades'].append(f"CPFs duplicados: {cpf_duplicados}")
    
    # Inconsistências
    if all(col in df.columns for col in ['valor_total', 'valor_desconto', 'valor_pagto']):
        diferenca = (df['valor_total'].fillna(0) - (df['valor_desconto'].fillna(0) + df['valor_pagto'].fillna(0))).abs()
        inconsistentes = (diferenca > 0.01).sum()
        
        if inconsistentes > 0:
            problemas['inconsistencias'].append(f"Inconsistência nos valores: {inconsistentes}")
    
    # Alertas
    if 'data_pagto' in df.columns:
        datas_futuras = (df['data_pagto'] > pd.Timestamp.now()).sum()
        if datas_futuras > 0:
            problemas['alertas'].append(f"Datas futuras: {datas_futuras}")
    
    return problemas

def gerar_relatorio_agencia(df):
    """Gera relatório por agência."""
    if 'agencia' not in df.columns or 'valor_pagto' not in df.columns:
        return pd.DataFrame()
    
    try:
        relatorio = df.groupby('agencia').agg({
            'nome': 'count',
            'valor_pagto': ['sum', 'mean', 'min', 'max']
        }).round(2)
        
        # Renomear colunas
        relatorio.columns = ['Qtd Beneficiários', 'Valor Total', 'Valor Médio', 'Valor Mínimo', 'Valor Máximo']
        
        # Adicionar dias médios se disponível
        if 'dias_apagar' in df.columns:
            dias_medio = df.groupby('agencia')['dias_apagar'].mean().round(2)
            relatorio['Dias Médios'] = dias_medio
        
        return relatorio.sort_values('Valor Total', ascending=False)
    
    except Exception as e:
        st.error(f"Erro no relatório: {e}")
        return pd.DataFrame()

def gerar_relatorio_gerenciadora(df):
    """Gera relatório por gerenciadora."""
    if 'gerenciadora' not in df.columns or 'valor_pagto' not in df.columns:
        return pd.DataFrame()
    
    try:
        relatorio = df.groupby('gerenciadora').agg({
            'nome': 'count',
            'valor_pagto': ['sum', 'mean'],
            'agencia': 'nunique'
        }).round(2)
        
        relatorio.columns = ['Qtd Beneficiários', 'Valor Total', 'Valor Médio', 'Qtd Agências']
        
        if 'dias_apagar' in df.columns:
            dias_medio = df.groupby('gerenciadora')['dias_apagar'].mean().round(2)
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
        agencias_topo = df.groupby('agencia')['valor_pagto'].sum().nlargest(top_n)
        
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
        st.error(f"Erro no gráfico: {e}")
        return None

def criar_grafico_distribuicao(df):
    """Cria histograma da distribuição de valores."""
    if 'valor_pagto' not in df.columns:
        return None
    
    try:
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
    
    except Exception as e:
        st.error(f"Erro no gráfico: {e}")
        return None

def criar_grafico_pizza_gerenciadora(df):
    """Cria gráfico de pizza por gerenciadora."""
    if 'gerenciadora' not in df.columns:
        return None
    
    try:
        contagem = df['gerenciadora'].value_counts()
        
        fig = go.Figure(data=[
            go.Pie(
                labels=contagem.index,
                values=contagem.values,
                hole=0.4,
                textinfo='percent+label',
                marker_colors=['#F18F01', '#2E86AB', '#A23B72', '#73AB84']
            )
        ])
        
        fig.update_layout(title='Distribuição por Gerenciadora')
        
        return fig
    
    except Exception as e:
        st.error(f"Erro no gráfico: {e}")
        return None

# ============================================================================
# FUNÇÕES DE EXPORTAÇÃO
# ============================================================================

def exportar_excel(df, rel_agencia, rel_gerenciadora, problemas):
    """Exporta para Excel com múltiplas abas."""
    output = BytesIO()
    
    try:
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Dados completos
            df.to_excel(writer, sheet_name='Dados Completos', index=False)
            
            # Relatórios
            if not rel_agencia.empty:
                rel_agencia.to_excel(writer, sheet_name='Por Agência')
            
            if not rel_gerenciadora.empty:
                rel_gerenciadora.to_excel(writer, sheet_name='Por Gerenciadora')
            
            # Problemas detectados
            problemas_df = pd.DataFrame([
                ['Dados Faltantes', len(problemas['dados_faltantes']), '; '.join(problemas['dados_faltantes'])],
                ['Valores Estranhos', len(problemas['valores_estranhos']), '; '.join(problemas['valores_estranhos'])],
                ['Duplicidades', len(problemas['duplicidades']), '; '.join(problemas['duplicidades'])],
                ['Inconsistências', len(problemas['inconsistencias']), '; '.join(problemas['inconsistencias'])],
                ['Alertas', len(problemas['alertas']), '; '.join(problemas['alertas'])]
            ], columns=['Categoria', 'Quantidade', 'Detalhes'])
            
            problemas_df.to_excel(writer, sheet_name='Problemas Detectados', index=False)
            
            # Top beneficiários
            if 'nome' in df.columns and 'valor_pagto' in df.columns:
                top_benef = df.nlargest(20, 'valor_pagto')[['nome', 'valor_pagto', 'agencia', 'gerenciadora']]
                top_benef.to_excel(writer, sheet_name='Top Beneficiários', index=False)
        
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
        mostrar_graficos = st.checkbox("Mostrar gráficos", True)
        top_n = st.slider("Top N agências", 5, 20, 10)
        
        st.markdown("---")
        
        st.header("ℹ️ INFORMAÇÕES")
        st.info(
            "**Sistema de Monitoramento**\n"
            "Programa Operacional de Trabalho (POT)\n\n"
            "Versão: 1.0\n"
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
               - CSV (separado por ;)
               - Excel (.xlsx, .xls)
            
            3. **Colunas esperadas:**
               - Ordem, Projeto, Nome
               - Agência, Valor Total
               - Valor Pagto, Data Pagto
               - Dias a apagar, CPF
               - Gerenciadora
            
            4. **Correção automática:**
               - Detecta valores duplicados
               - Identifica inconsistências
               - Gera alertas críticos
            """)
        
        with col2:
            st.markdown("""
            ### 🚀 Funcionalidades:
            
            ✅ **Processamento inteligente**
            ✅ **Detecção de problemas**
            ✅ **Análise por agência**
            ✅ **Análise por gerenciadora**
            ✅ **Gráficos interativos**
            ✅ **Exportação completa**
            ✅ **Validação de dados**
            ✅ **Relatórios detalhados**
            """)
        
        # Exemplo de dados
        with st.expander("📝 Exemplo de formato de dados"):
            exemplo = pd.DataFrame({
                'Ordem': [1, 2, 3],
                'Projeto': ['ABAE', 'ABAE', 'OUTRO PROJETO'],
                'Nome': ['MARIA SILVA', 'JOSÉ SANTOS', 'ANA OLIVEIRA'],
                'AGÊNCIA': ['0012', '0345', '0789'],
                'VALOR PAGTO': ['R$ 1.593,90', 'R$ 1.200,00', 'R$ 890,50'],
                'DATA PAGTO': ['15/10/2024', '16/10/2024', '17/10/2024'],
                'GERENCIADORA': ['VISTA', 'REDE CIDADÃO', 'VISTA']
            })
            st.dataframe(exemplo, use_container_width=True)
        
        return
    
    # ========================================================================
    # PROCESSAR ARQUIVO
    # ========================================================================
    with st.spinner('Processando...'):
        df, mensagem = processar_arquivo(uploaded_file)
    
    if df is None:
        st.error(mensagem)
        return
    
    st.success(f"✅ {mensagem}")
    st.markdown(f"**Arquivo:** `{uploaded_file.name}` | **Registros:** {len(df):,} | **Colunas:** {len(df.columns)}")
    st.markdown("---")
    
    # ========================================================================
    # DETECTAR PROBLEMAS
    # ========================================================================
    st.header("🔍 DETECÇÃO DE PROBLEMAS E INCONSISTÊNCIAS")
    
    problemas = detectar_problemas(df)
    
    # Mostrar problemas em colunas
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_faltantes = len(problemas['dados_faltantes'])
        st.metric("Dados Faltantes", total_faltantes)
        if total_faltantes > 0:
            with st.expander("Ver detalhes"):
                for item in problemas['dados_faltantes']:
                    st.error(f"❌ {item}")
    
    with col2:
        total_estranhos = len(problemas['valores_estranhos'])
        st.metric("Valores Estranhos", total_estranhos)
        if total_estranhos > 0:
            with st.expander("Ver detalhes"):
                for item in problemas['valores_estranhos']:
                    st.warning(f"⚠️ {item}")
    
    with col3:
        total_duplicados = len(problemas['duplicidades'])
        st.metric("Duplicidades", total_duplicados)
        if total_duplicados > 0:
            with st.expander("Ver detalhes"):
                for item in problemas['duplicidades']:
                    st.info(f"🔍 {item}")
    
    with col4:
        total_inconsistentes = len(problemas['inconsistencias'])
        st.metric("Inconsistências", total_inconsistentes)
        if total_inconsistentes > 0:
            with st.expander("Ver detalhes"):
                for item in problemas['inconsistencias']:
                    st.error(f"❌ {item}")
    
    # Alertas gerais
    if problemas['alertas']:
        st.warning("### ⚠️ Alertas Gerais")
        for alerta in problemas['alertas']:
            st.warning(f"• {alerta}")
    
    st.markdown("---")
    
    # ========================================================================
    # MÉTRICAS PRINCIPAIS
    # ========================================================================
    st.header("📈 MÉTRICAS PRINCIPAIS")
    
    metricas = calcular_metricas(df)
    
    # Primeira linha
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total de Registros", f"{metricas.get('total_registros', 0):,}")
    
    with col2:
        valor_total = metricas.get('valor_total', 0)
        st.metric("Valor Total Pago", f"R$ {valor_total:,.2f}")
        
        # Verificação de valor total
        if valor_total > 10000000:
            st.caption("⚠️ Verifique possível duplicação")
    
    with col3:
        valor_medio = metricas.get('valor_medio', 0)
        st.metric("Valor Médio", f"R$ {valor_medio:,.2f}")
    
    with col4:
        st.metric("Agências Únicas", metricas.get('total_agencias', 0))
    
    # Segunda linha
    col5, col6, col7, col8 = st.columns(4)
    
    with col5:
        st.metric("Dias Médios", f"{metricas.get('dias_medio', 0):.1f}")
    
    with col6:
        st.metric("Valor/Dia Médio", f"R$ {metricas.get('valor_dia_medio', 0):.2f}")
    
    with col7:
        st.metric("VISTA", f"{metricas.get('total_vista', 0):,}")
    
    with col8:
        st.metric("REDE CIDADÃO", f"{metricas.get('total_rede', 0):,}")
    
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
        st.subheader("📊 Estatísticas")
        
        col_stat1, col_stat2 = st.columns(2)
        
        with col_stat1:
            if 'valor_pagto' in df.columns:
                st.write("**Valores Pagos**")
                stats = df['valor_pagto'].describe().to_frame().round(2)
                st.dataframe(stats, use_container_width=True)
        
        with col_stat2:
            if 'dias_apagar' in df.columns:
                st.write("**Dias a Pagar**")
                dias_stats = df['dias_apagar'].describe().to_frame().round(2)
                st.dataframe(dias_stats, use_container_width=True)
    
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
            st.warning("Não foi possível gerar análise por agência.")
    
    with tab3:
        st.subheader("🏦 Análise por Gerenciadora")
        
        rel_gerenciadora = gerar_relatorio_gerenciadora(df)
        
        if not rel_gerenciadora.empty:
            st.dataframe(rel_gerenciadora, use_container_width=True)
            
            # Comparativo
            if 'VISTA' in rel_gerenciadora.index or 'REDE CIDADÃO' in rel_gerenciadora.index:
                st.subheader("📊 Comparativo")
                
                comparativo = []
                if 'VISTA' in rel_gerenciadora.index:
                    vista = rel_gerenciadora.loc['VISTA']
                    comparativo.append({
                        'Gerenciadora': 'VISTA',
                        'Beneficiários': vista['Qtd Beneficiários'],
                        'Valor Total': vista['Valor Total'],
                        'Valor Médio': vista['Valor Médio']
                    })
                
                if 'REDE CIDADÃO' in rel_gerenciadora.index:
                    rede = rel_gerenciadora.loc['REDE CIDADÃO']
                    comparativo.append({
                        'Gerenciadora': 'REDE CIDADÃO',
                        'Beneficiários': rede['Qtd Beneficiários'],
                        'Valor Total': rede['Valor Total'],
                        'Valor Médio': rede['Valor Médio']
                    })
                
                if comparativo:
                    st.dataframe(pd.DataFrame(comparativo), use_container_width=True)
            
            # Gráficos
            if mostrar_graficos:
                col_g1, col_g2 = st.columns(2)
                
                with col_g1:
                    fig1 = criar_grafico_pizza_gerenciadora(df)
                    if fig1:
                        st.plotly_chart(fig1, use_container_width=True)
                
                with col_g2:
                    fig2 = criar_grafico_distribuicao(df)
                    if fig2:
                        st.plotly_chart(fig2, use_container_width=True)
        else:
            st.warning("Não foi possível gerar análise por gerenciadora.")
    
    with tab4:
        st.subheader("💾 Exportação de Dados")
        
        col_exp1, col_exp2, col_exp3 = st.columns(3)
        
        with col_exp1:
            # CSV
            csv = df.to_csv(index=False, sep=';', decimal=',')
            st.download_button(
                label="📥 Baixar CSV",
                data=csv,
                file_name="dados_pot.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col_exp2:
            # Excel completo
            excel_data = exportar_excel(df, rel_agencia, rel_gerenciadora, problemas)
            if excel_data:
                st.download_button(
                    label="📥 Baixar Excel Completo",
                    data=excel_data,
                    file_name="relatorio_pot.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
        
        with col_exp3:
            # JSON
            json = df.to_json(orient='records', indent=2)
            st.download_button(
                label="📥 Baixar JSON",
                data=json,
                file_name="dados_pot.json",
                mime="application/json",
                use_container_width=True
            )
        
        # Relatórios individuais
        st.markdown("---")
        st.subheader("📊 Relatórios Individuais")
        
        col_rel1, col_rel2 = st.columns(2)
        
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
    
    # ========================================================================
    # RODAPÉ
    # ========================================================================
    st.markdown("---")
    st.markdown(
        f"""
        <div style='text-align: center; color: gray;'>
        Sistema de Monitoramento de Pagamentos - POT | 
        Processado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}
        </div>
        """,
        unsafe_allow_html=True
    )

# ============================================================================
# EXECUTAR APLICAÇÃO
# ============================================================================
if __name__ == "__main__":
    main()
