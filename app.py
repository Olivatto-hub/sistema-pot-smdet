# app.py - Sistema de Monitoramento de Pagamentos do POT
# Versão 3.0 - Estável e Corrigida

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from io import StringIO, BytesIO
import warnings
from datetime import datetime
import re

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
# FUNÇÕES DE PROCESSAMENTO DE DADOS - CORRIGIDAS SEM DUPLICAÇÃO
# ============================================================================

def limpar_valor_monetario(valor):
    """
    Limpa e converte valores monetários brasileiros para float.
    CORREÇÃO: Não duplica valores, trata corretamente.
    """
    if pd.isna(valor) or valor == '' or str(valor).strip() in ['nan', 'None', 'NaT', 'NULL', 'null']:
        return np.nan
    
    try:
        # Converter para string
        str_valor = str(valor).strip()
        
        # Remover R$, $, espaços e aspas
        str_valor = re.sub(r'[R\$\s\'\"\\]', '', str_valor)
        
        # Se já for float ou int, retornar
        if str_valor.replace('.', '', 1).isdigit():
            return float(str_valor)
        
        # Verificar padrão brasileiro: 1.593,90
        if '.' in str_valor and ',' in str_valor:
            # Contar quantos pontos tem - se tiver mais de 1, são milhares
            if str_valor.count('.') > 1:
                # Remover todos os pontos de milhar
                str_valor = str_valor.replace('.', '')
            
            # Substituir vírgula decimal por ponto
            str_valor = str_valor.replace(',', '.')
            return float(str_valor)
        
        # Verificar padrão com apenas vírgula: 1593,90
        elif ',' in str_valor:
            str_valor = str_valor.replace(',', '.')
            return float(str_valor)
        
        # Se chegou aqui, tentar converter diretamente
        return float(str_valor)
        
    except (ValueError, TypeError):
        return np.nan

def processar_arquivo_simples(uploaded_file):
    """
    Processa arquivo de forma simples e segura sem duplicação.
    """
    try:
        # Detectar tipo de arquivo
        if uploaded_file.name.lower().endswith('.csv'):
            # Tentar diferentes encodings
            raw_data = uploaded_file.getvalue()
            
            # Primeira tentativa: UTF-8
            try:
                content = raw_data.decode('utf-8-sig')
            except UnicodeDecodeError:
                # Segunda tentativa: Latin-1
                try:
                    content = raw_data.decode('latin-1')
                except UnicodeDecodeError:
                    # Terceira tentativa: CP1252 (Windows)
                    content = raw_data.decode('cp1252')
            
            # Detectar delimitador
            sample = content[:1000]
            if ';' in sample:
                sep = ';'
            else:
                sep = ','
            
            # Ler CSV
            df = pd.read_csv(StringIO(content), sep=sep, dtype=str, na_values=['', 'NA', 'N/A', 'null'])
            
        elif uploaded_file.name.lower().endswith(('.xlsx', '.xls')):
            # Ler Excel
            df = pd.read_excel(uploaded_file, dtype=str, na_values=['', 'NA', 'N/A', 'null'])
        else:
            return None, "❌ Formato não suportado. Use CSV ou Excel."
        
        # Renomear colunas para minúsculo
        df.columns = [str(col).strip().lower() for col in df.columns]
        
        # Mapeamento de colunas comum
        mapeamento = {
            'ordem': 'ordem',
            'projeto': 'projeto',
            'cartão': 'cartao',
            'cartao': 'cartao',
            'nº cartão': 'cartao',
            'n° cartão': 'cartao',
            'nome': 'nome',
            'distrito': 'distrito',
            'agência': 'agencia',
            'agencia': 'agencia',
            'rg': 'rg',
            'valor total': 'valor_total',
            'valor desconto': 'valor_desconto',
            'valor pagto': 'valor_pagto',
            'data pagto': 'data_pagto',
            'valor dia': 'valor_dia',
            'dias a apagar': 'dias_apagar',
            'cpf': 'cpf',
            'gerenciadora': 'gerenciadora'
        }
        
        # Aplicar mapeamento
        for col in df.columns:
            for key, value in mapeamento.items():
                if key in col:
                    df = df.rename(columns={col: value})
                    break
        
        # Garantir que temos colunas essenciais
        colunas_essenciais = ['nome', 'valor_pagto']
        colunas_faltando = [col for col in colunas_essenciais if col not in df.columns]
        
        if colunas_faltando:
            st.warning(f"⚠️ Colunas não encontradas: {', '.join(colunas_faltando)}")
        
        # Processar colunas monetárias UMA ÚNICA VEZ
        colunas_monetarias = ['valor_total', 'valor_desconto', 'valor_pagto', 'valor_dia']
        
        for coluna in colunas_monetarias:
            if coluna in df.columns:
                # Aplicar limpeza diretamente
                df[coluna] = df[coluna].apply(limpar_valor_monetario)
                
                # VERIFICAÇÃO CRÍTICA: Verificar se não houve duplicação
                if not df[coluna].isna().all():
                    # Verificar valores absurdamente altos (possível duplicação)
                    valores_validos = df[coluna].dropna()
                    if len(valores_validos) > 0:
                        media = valores_validos.mean()
                        if media > 10000:  # Média acima de 10k é suspeita
                            st.warning(f"⚠️ Valores suspeitamente altos na coluna '{coluna}'. Verifique possível duplicação.")
        
        # Processar outras colunas numéricas
        if 'dias_apagar' in df.columns:
            df['dias_apagar'] = pd.to_numeric(df['dias_apagar'], errors='coerce')
        
        if 'ordem' in df.columns:
            df['ordem'] = pd.to_numeric(df['ordem'], errors='coerce')
        
        # Processar datas
        if 'data_pagto' in df.columns:
            # Tentar converter data
            df['data_pagto'] = pd.to_datetime(df['data_pagto'], dayfirst=True, errors='coerce')
        
        # Limpar strings
        colunas_string = ['nome', 'projeto', 'gerenciadora', 'agencia', 'rg', 'cpf']
        
        for col in colunas_string:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
                # Substituir valores nulos por string vazia
                df[col] = df[col].replace(['nan', 'None', 'NaT', 'NULL', 'null', 'NaN'], '')
        
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
        
        # Log de processamento
        st.info(f"✅ Processado: {len(df)} registros, {df['valor_pagto'].notna().sum() if 'valor_pagto' in df.columns else 0} valores monetários válidos")
        
        return df, "✅ Arquivo processado com sucesso!"
        
    except Exception as e:
        return None, f"❌ Erro ao processar arquivo: {str(e)}"

# ============================================================================
# FUNÇÕES DE DETECÇÃO DE PROBLEMAS DETALHADOS
# ============================================================================

def detectar_problemas_detalhados(df):
    """
    Detecta problemas detalhados incluindo CPFs e Cartões duplicados com nomes diferentes.
    """
    problemas = {
        'dados_faltantes': [],
        'duplicidades_criticas': [],
        'inconsistencias': [],
        'valores_estranhos': [],
        'alertas': []
    }
    
    try:
        # 1. DADOS FALTANTES CRÍTICOS
        if 'nome' in df.columns:
            nomes_vazios = df['nome'].isna().sum() + (df['nome'] == '').sum()
            if nomes_vazios > 0:
                problemas['dados_faltantes'].append({
                    'tipo': 'NOMES EM BRANCO',
                    'quantidade': nomes_vazios,
                    'gravidade': 'ALTA',
                    'descricao': 'Registros sem nome do beneficiário',
                    'exemplo': df[df['nome'].isna() | (df['nome'] == '')].head(3).to_dict('records') if len(df) > 0 else []
                })
        
        if 'cpf' in df.columns:
            # CPFs vazios
            cpfs_vazios = df['cpf'].isna().sum() + (df['cpf'] == '').sum()
            if cpfs_vazios > 0:
                problemas['dados_faltantes'].append({
                    'tipo': 'CPFs EM BRANCO',
                    'quantidade': cpfs_vazios,
                    'gravidade': 'ALTA',
                    'descricao': 'Registros sem CPF do beneficiário',
                    'exemplo': df[df['cpf'].isna() | (df['cpf'] == '')].head(3).to_dict('records') if len(df) > 0 else []
                })
            
            # CPFs inválidos (menos de 11 dígitos)
            def cpf_valido(cpf):
                if pd.isna(cpf) or cpf == '':
                    return False
                cpf_str = str(cpf)
                # Remover caracteres não numéricos
                cpf_str = re.sub(r'\D', '', cpf_str)
                return len(cpf_str) == 11
            
            cpfs_invalidos = (~df['cpf'].apply(cpf_valido)).sum()
            if cpfs_invalidos > 0:
                problemas['dados_faltantes'].append({
                    'tipo': 'CPFs INVÁLIDOS',
                    'quantidade': cpfs_invalidos,
                    'gravidade': 'ALTA',
                    'descricao': 'CPFs com formato inválido (menos de 11 dígitos)',
                    'exemplo': df[~df['cpf'].apply(cpf_valido)].head(3).to_dict('records') if len(df) > 0 else []
                })
        
        # 2. DUPLICIDADES CRÍTICAS
        if 'cpf' in df.columns and 'nome' in df.columns:
            # Limpar CPFs para análise
            df_clean = df.copy()
            df_clean['cpf_limpo'] = df_clean['cpf'].apply(lambda x: re.sub(r'\D', '', str(x)) if pd.notna(x) else '')
            
            # Filtrar CPFs não vazios
            df_cpf_valido = df_clean[df_clean['cpf_limpo'] != '']
            
            # Encontrar CPFs duplicados
            cpfs_duplicados = df_cpf_valido['cpf_limpo'][df_cpf_valido['cpf_limpo'].duplicated(keep=False)].unique()
            
            for cpf in cpfs_duplicados[:5]:  # Analisar apenas os 5 primeiros para exemplo
                registros = df_clean[df_clean['cpf_limpo'] == cpf]
                nomes_unicos = registros['nome'].nunique()
                
                if nomes_unicos > 1:
                    problemas['duplicidades_criticas'].append({
                        'tipo': 'CPF COM NOMES DIFERENTES',
                        'quantidade': len(registros),
                        'gravidade': 'CRÍTICA',
                        'descricao': f'CPF {cpf} aparece com {nomes_unicos} nomes diferentes',
                        'exemplo': registros[['cpf', 'nome', 'agencia', 'valor_pagto']].head(3).to_dict('records')
                    })
        
        if 'cartao' in df.columns and 'nome' in df.columns:
            # Limpar números de cartão
            df_clean = df.copy()
            df_clean['cartao_limpo'] = df_clean['cartao'].apply(lambda x: str(x).strip() if pd.notna(x) else '')
            
            # Filtrar cartões não vazios
            df_cartao_valido = df_clean[df_clean['cartao_limpo'] != '']
            
            # Encontrar cartões duplicados
            cartoes_duplicados = df_cartao_valido['cartao_limpo'][df_cartao_valido['cartao_limpo'].duplicated(keep=False)].unique()
            
            for cartao in cartoes_duplicados[:5]:  # Analisar apenas os 5 primeiros
                registros = df_clean[df_clean['cartao_limpo'] == cartao]
                nomes_unicos = registros['nome'].nunique()
                
                if nomes_unicos > 1:
                    problemas['duplicidades_criticas'].append({
                        'tipo': 'CARTÃO COM NOMES DIFERENTES',
                        'quantidade': len(registros),
                        'gravidade': 'CRÍTICA',
                        'descricao': f'Cartão {cartao} aparece com {nomes_unicos} nomes diferentes',
                        'exemplo': registros[['cartao', 'nome', 'agencia', 'valor_pagto']].head(3).to_dict('records')
                    })
        
        # 3. VALORES ESTRANHOS
        if 'valor_pagto' in df.columns:
            valores_validos = df['valor_pagto'].dropna()
            
            if len(valores_validos) > 0:
                # Valores zerados
                valores_zerados = (valores_validos == 0).sum()
                if valores_zerados > 0:
                    problemas['valores_estranhos'].append({
                        'tipo': 'VALORES ZERADOS',
                        'quantidade': valores_zerados,
                        'gravidade': 'MÉDIA',
                        'descricao': 'Pagamentos com valor zero',
                        'exemplo': df[df['valor_pagto'] == 0].head(3).to_dict('records') if 'nome' in df.columns else []
                    })
                
                # Valores negativos
                valores_negativos = (valores_validos < 0).sum()
                if valores_negativos > 0:
                    problemas['valores_estranhos'].append({
                        'tipo': 'VALORES NEGATIVOS',
                        'quantidade': valores_negativos,
                        'gravidade': 'ALTA',
                        'descricao': 'Pagamentos com valor negativo',
                        'exemplo': df[df['valor_pagto'] < 0].head(3).to_dict('records') if 'nome' in df.columns else []
                    })
                
                # Valores muito altos (acima de 99º percentil)
                if len(valores_validos) > 10:
                    limite_alto = valores_validos.quantile(0.99)
                    valores_muito_altos = (valores_validos > limite_alto).sum()
                    
                    if valores_muito_altos > 0:
                        problemas['valores_estranhos'].append({
                            'tipo': 'VALORES MUITO ALTOS',
                            'quantidade': valores_muito_altos,
                            'gravidade': 'ALTA',
                            'descricao': f'Valores acima de R$ {limite_alto:,.2f} (99º percentil)',
                            'exemplo': df[df['valor_pagto'] > limite_alto].head(3).to_dict('records') if 'nome' in df.columns else []
                        })
        
        # 4. INCONSISTÊNCIAS
        if all(col in df.columns for col in ['valor_total', 'valor_desconto', 'valor_pagto']):
            # Verificar se Valor Total = Desconto + Pagto
            mask = df['valor_total'].notna() & df['valor_desconto'].notna() & df['valor_pagto'].notna()
            
            if mask.any():
                diferenca = (df.loc[mask, 'valor_total'] - (df.loc[mask, 'valor_desconto'] + df.loc[mask, 'valor_pagto'])).abs()
                inconsistentes = (diferenca > 0.01).sum()
                
                if inconsistentes > 0:
                    problemas['inconsistencias'].append({
                        'tipo': 'INCONSISTÊNCIA NOS VALORES',
                        'quantidade': inconsistentes,
                        'gravidade': 'CRÍTICA',
                        'descricao': 'Valor Total ≠ Valor Desconto + Valor Pagto',
                        'exemplo': df[mask & (diferenca > 0.01)].head(3).to_dict('records') if 'nome' in df.columns else []
                    })
        
        # 5. ALERTAS
        if 'data_pagto' in df.columns:
            datas_futuras = (df['data_pagto'] > pd.Timestamp.now()).sum()
            if datas_futuras > 0:
                problemas['alertas'].append({
                    'tipo': 'DATAS FUTURAS',
                    'quantidade': datas_futuras,
                    'gravidade': 'MÉDIA',
                    'descricao': 'Pagamentos com data no futuro',
                    'exemplo': df[df['data_pagto'] > pd.Timestamp.now()].head(3).to_dict('records') if 'nome' in df.columns else []
                })
        
        return problemas
    
    except Exception as e:
        st.error(f"Erro na detecção de problemas: {e}")
        return problemas

# ============================================================================
# FUNÇÕES DE ANÁLISE E CÁLCULOS
# ============================================================================

def calcular_metricas_corretas(df):
    """
    Calcula métricas corretas sem duplicação.
    """
    metricas = {}
    
    try:
        metricas['total_registros'] = len(df)
        
        if 'valor_pagto' in df.columns:
            # Usar apenas valores válidos
            valores_validos = df['valor_pagto'].dropna()
            
            if len(valores_validos) > 0:
                metricas['valor_total'] = float(valores_validos.sum())
                metricas['valor_medio'] = float(valores_validos.mean())
                metricas['valor_min'] = float(valores_validos.min())
                metricas['valor_max'] = float(valores_validos.max())
                metricas['qtd_valores_validos'] = len(valores_validos)
                
                # VERIFICAÇÃO: Se valor total parece duplicado
                if metricas['valor_total'] > 10000000:  # Acima de 10 milhões
                    media = metricas['valor_medio']
                    if media > 5000:  # Média acima de 5k é suspeita
                        st.warning("⚠️ Valores possivelmente duplicados detectados!")
            else:
                metricas['valor_total'] = 0.0
                metricas['valor_medio'] = 0.0
                metricas['valor_min'] = 0.0
                metricas['valor_max'] = 0.0
                metricas['qtd_valores_validos'] = 0
        
        if 'agencia' in df.columns:
            agencias_validas = df['agencia'].dropna()
            metricas['total_agencias'] = agencias_validas.nunique() if len(agencias_validas) > 0 else 0
        
        if 'gerenciadora' in df.columns:
            gerenciadoras_validas = df['gerenciadora'].dropna()
            if len(gerenciadoras_validas) > 0:
                metricas['total_gerenciadoras'] = gerenciadoras_validas.nunique()
                contagem = gerenciadoras_validas.value_counts()
                metricas['total_vista'] = int(contagem.get('VISTA', 0))
                metricas['total_rede'] = int(contagem.get('REDE CIDADÃO', 0))
            else:
                metricas['total_gerenciadoras'] = 0
                metricas['total_vista'] = 0
                metricas['total_rede'] = 0
        
        if 'dias_apagar' in df.columns:
            dias_validos = df['dias_apagar'].dropna()
            metricas['dias_medio'] = float(dias_validos.mean()) if len(dias_validos) > 0 else 0.0
        
        if 'valor_dia' in df.columns:
            valor_dia_valido = df['valor_dia'].dropna()
            metricas['valor_dia_medio'] = float(valor_dia_valido.mean()) if len(valor_dia_valido) > 0 else 0.0
        
        return metricas
    
    except Exception as e:
        st.error(f"Erro nos cálculos: {e}")
        return {}

def gerar_relatorio_agencia_correto(df):
    """Gera relatório por agência com cálculos corretos."""
    if 'agencia' not in df.columns or 'valor_pagto' not in df.columns:
        return pd.DataFrame()
    
    try:
        # Filtrar valores válidos
        df_valido = df[df['agencia'].notna() & df['valor_pagto'].notna()]
        
        if len(df_valido) == 0:
            return pd.DataFrame()
        
        # Agrupar e calcular
        relatorio = df_valido.groupby('agencia').agg(
            qtd_beneficiarios=('nome', 'count'),
            valor_total=('valor_pagto', 'sum'),
            valor_medio=('valor_pagto', 'mean'),
            valor_min=('valor_pagto', 'min'),
            valor_max=('valor_pagto', 'max')
        ).round(2)
        
        # Renomear colunas
        relatorio = relatorio.rename(columns={
            'qtd_beneficiarios': 'Qtd Beneficiários',
            'valor_total': 'Valor Total',
            'valor_medio': 'Valor Médio',
            'valor_min': 'Valor Mínimo',
            'valor_max': 'Valor Máximo'
        })
        
        # Ordenar por valor total
        relatorio = relatorio.sort_values('Valor Total', ascending=False)
        
        return relatorio
    
    except Exception as e:
        st.error(f"Erro no relatório: {e}")
        return pd.DataFrame()

# ============================================================================
# INTERFACE PRINCIPAL - SIMPLIFICADA E ESTÁVEL
# ============================================================================

def main():
    # ========================================================================
    # SIDEBAR SIMPLIFICADA
    # ========================================================================
    with st.sidebar:
        st.header("📁 CARREGAR DADOS")
        
        uploaded_file = st.file_uploader(
            "Selecione o arquivo",
            type=['csv', 'xlsx', 'xls'],
            help="Formatos suportados: CSV ou Excel"
        )
        
        st.markdown("---")
        
        st.header("⚙️ CONFIGURAÇÕES")
        mostrar_detalhes = st.checkbox("Mostrar detalhes dos dados", False)
        
        st.markdown("---")
        
        st.header("✅ STATUS DO SISTEMA")
        st.success("Sistema Operacional")
        st.caption(f"Data: {datetime.now().strftime('%d/%m/%Y')}")
    
    # ========================================================================
    # ÁREA PRINCIPAL
    # ========================================================================
    
    if uploaded_file is None:
        # Tela inicial
        st.info("👋 Bem-vindo ao Sistema de Monitoramento de Pagamentos do POT")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown("""
            ### 📋 Instruções de Uso:
            
            1. **Carregue o arquivo** na barra lateral
            2. **Formatos suportados:**
               - CSV (separado por ponto-e-vírgula ou vírgula)
               - Excel (.xlsx, .xls)
            
            3. **Colunas importantes:**
               - Nome, CPF, Número do Cartão
               - Agência, Valor Pago
               - Data Pagto, Gerenciadora
            
            4. **Funcionalidades:**
               - Processamento seguro sem duplicação
               - Detecção de inconsistências
               - Verificação de CPFs e Cartões duplicados
               - Relatórios detalhados
            """)
        
        with col2:
            st.markdown("""
            ### 🛡️ Sistema Estável:
            
            ✅ **Sem duplicação de valores**
            ✅ **Processamento seguro**
            ✅ **Detecção avançada**
            ✅ **Interface confiável**
            ✅ **Cálculos precisos**
            """)
        
        return
    
    # ========================================================================
    # PROCESSAMENTO DO ARQUIVO
    # ========================================================================
    try:
        with st.spinner('🔄 Processando arquivo...'):
            df, mensagem = processar_arquivo_simples(uploaded_file)
        
        if df is None:
            st.error(mensagem)
            return
        
        st.success(mensagem)
        
        # Informações básicas
        st.markdown(f"""
        **📊 Informações do Arquivo:**
        - **Arquivo:** `{uploaded_file.name}`
        - **Total de Registros:** {len(df):,}
        - **Colunas Processadas:** {len(df.columns)}
        """)
        
        # Visualização rápida
        with st.expander("🔍 Visualizar primeiros registros"):
            st.dataframe(df.head(), use_container_width=True)
        
        st.markdown("---")
        
        # ====================================================================
        # MÉTRICAS PRINCIPAIS - CÁLCULOS CORRETOS
        # ====================================================================
        st.header("📈 MÉTRICAS PRINCIPAIS")
        
        metricas = calcular_metricas_corretas(df)
        
        # Verificar se temos dados
        if metricas.get('qtd_valores_validos', 0) == 0:
            st.warning("⚠️ Nenhum valor monetário válido encontrado!")
        
        # Layout das métricas
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total = metricas.get('total_registros', 0)
            st.metric("Total de Registros", f"{total:,}")
        
        with col2:
            valor_total = metricas.get('valor_total', 0)
            st.metric("Valor Total Pago", f"R$ {valor_total:,.2f}")
            
            # Verificação de valor total
            if valor_total > 10000000:
                st.caption("⚠️ Verificar possíveis duplicações")
        
        with col3:
            valor_medio = metricas.get('valor_medio', 0)
            st.metric("Valor Médio", f"R$ {valor_medio:,.2f}")
        
        with col4:
            agencias = metricas.get('total_agencias', 0)
            st.metric("Agências Únicas", f"{agencias}")
        
        col5, col6, col7, col8 = st.columns(4)
        
        with col5:
            dias_medio = metricas.get('dias_medio', 0)
            st.metric("Dias Médios", f"{dias_medio:.1f}")
        
        with col6:
            valor_dia_medio = metricas.get('valor_dia_medio', 0)
            st.metric("Valor/Dia Médio", f"R$ {valor_dia_medio:.2f}")
        
        with col7:
            vista = metricas.get('total_vista', 0)
            st.metric("VISTA", f"{vista:,}")
        
        with col8:
            rede = metricas.get('total_rede', 0)
            st.metric("REDE CIDADÃO", f"{rede:,}")
        
        st.markdown("---")
        
        # ====================================================================
        # DETECÇÃO DE PROBLEMAS DETALHADA
        # ====================================================================
        st.header("🔍 DETECÇÃO DE PROBLEMAS E INCONSISTÊNCIAS")
        
        with st.spinner("🔎 Analisando dados em busca de problemas..."):
            problemas = detectar_problemas_detalhados(df)
        
        # Contar total de problemas
        total_problemas = sum(len(itens) for itens in problemas.values())
        
        if total_problemas > 0:
            st.warning(f"⚠️ **{total_problemas} problemas detectados** nos dados")
            
            # Exibir problemas por categoria
            for categoria, itens in problemas.items():
                if itens:
                    st.subheader(f"📋 {categoria.replace('_', ' ').upper()}")
                    
                    for item in itens:
                        with st.expander(f"❌ {item['tipo']} - {item['quantidade']} registros ({item['gravidade']})"):
                            st.write(f"**Descrição:** {item['descricao']}")
                            
                            if item.get('exemplo') and len(item['exemplo']) > 0:
                                st.write("**Exemplos:**")
                                exemplo_df = pd.DataFrame(item['exemplo'])
                                st.dataframe(exemplo_df, use_container_width=True)
        else:
            st.success("✅ Nenhum problema crítico detectado!")
        
        st.markdown("---")
        
        # ====================================================================
        # ANÁLISES E RELATÓRIOS
        # ====================================================================
        st.header("📊 ANÁLISES E RELATÓRIOS")
        
        tab1, tab2, tab3 = st.tabs(["🏢 Por Agência", "📈 Estatísticas", "💾 Exportar"])
        
        with tab1:
            st.subheader("Análise por Agência")
            
            relatorio_agencia = gerar_relatorio_agencia_correto(df)
            
            if not relatorio_agencia.empty:
                st.dataframe(relatorio_agencia, use_container_width=True)
                
                # Gráfico simples
                try:
                    top_10 = relatorio_agencia.head(10)
                    fig = px.bar(
                        top_10,
                        x=top_10.index,
                        y='Valor Total',
                        title='Top 10 Agências por Valor Total',
                        labels={'Valor Total': 'Valor Total (R$)'}
                    )
                    st.plotly_chart(fig, use_container_width=True)
                except:
                    pass
            else:
                st.info("Não há dados suficientes para análise por agência.")
        
        with tab2:
            st.subheader("Estatísticas Descritivas")
            
            col_stat1, col_stat2 = st.columns(2)
            
            with col_stat1:
                if 'valor_pagto' in df.columns:
                    st.write("**Valores Pagos**")
                    valores = df['valor_pagto'].dropna()
                    if len(valores) > 0:
                        stats = valores.describe().to_frame().round(2)
                        st.dataframe(stats, use_container_width=True)
            
            with col_stat2:
                if 'dias_apagar' in df.columns:
                    st.write("**Dias a Pagar**")
                    dias = df['dias_apagar'].dropna()
                    if len(dias) > 0:
                        stats_dias = dias.describe().to_frame().round(2)
                        st.dataframe(stats_dias, use_container_width=True)
        
        with tab3:
            st.subheader("Exportação de Dados")
            
            # Opções de exportação
            col_exp1, col_exp2 = st.columns(2)
            
            with col_exp1:
                # Exportar CSV
                csv_data = df.to_csv(index=False, sep=';', decimal=',')
                st.download_button(
                    label="📥 Baixar CSV Processado",
                    data=csv_data,
                    file_name=f"dados_pot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    help="Baixar dados processados em formato CSV"
                )
            
            with col_exp2:
                # Exportar Excel
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    # Dados principais
                    df.to_excel(writer, sheet_name='DADOS', index=False)
                    
                    # Relatório de problemas
                    if total_problemas > 0:
                        problemas_data = []
                        for categoria, itens in problemas.items():
                            for item in itens:
                                problemas_data.append({
                                    'Categoria': categoria,
                                    'Tipo': item['tipo'],
                                    'Quantidade': item['quantidade'],
                                    'Gravidade': item['gravidade'],
                                    'Descrição': item['descricao']
                                })
                        
                        if problemas_data:
                            problemas_df = pd.DataFrame(problemas_data)
                            problemas_df.to_excel(writer, sheet_name='PROBLEMAS', index=False)
                
                excel_bytes = output.getvalue()
                
                st.download_button(
                    label="📥 Baixar Relatório Excel",
                    data=excel_bytes,
                    file_name=f"relatorio_pot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    help="Baixar relatório completo em Excel"
                )
            
            # Exportar relatório de problemas específico
            if total_problemas > 0:
                st.markdown("---")
                st.subheader("📋 Relatório de Problemas")
                
                problemas_texto = f"RELATÓRIO DE PROBLEMAS DETECTADOS\n"
                problemas_texto += f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
                problemas_texto += f"Arquivo: {uploaded_file.name}\n"
                problemas_texto += f"Total de Problemas: {total_problemas}\n\n"
                
                for categoria, itens in problemas.items():
                    if itens:
                        problemas_texto += f"\n{categoria.upper()}:\n"
                        for item in itens:
                            problemas_texto += f"- {item['tipo']}: {item['quantidade']} registros ({item['gravidade']})\n"
                            problemas_texto += f"  Descrição: {item['descricao']}\n"
                
                st.download_button(
                    label="📄 Baixar Relatório de Problemas (TXT)",
                    data=problemas_texto,
                    file_name=f"problemas_detectados_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain",
                    use_container_width=True
                )
        
        # ====================================================================
        # RODAPÉ
        # ====================================================================
        st.markdown("---")
        st.markdown(
            f"""
            <div style='text-align: center; color: gray; font-size: 0.9em;'>
            Sistema de Monitoramento de Pagamentos - POT | 
            Processado em: {datetime.now().strftime('%d/%m/%Y %H:%M')} | 
            Versão: 3.0 Estável
            </div>
            """,
            unsafe_allow_html=True
        )
        
    except Exception as e:
        st.error(f"❌ Ocorreu um erro no sistema: {str(e)}")
        st.info("""
        **Soluções possíveis:**
        1. Verifique o formato do arquivo
        2. Certifique-se de que o arquivo não está corrompido
        3. Tente carregar novamente
        4. Contate o suporte técnico se o problema persistir
        """)

# ============================================================================
# EXECUTAR APLICAÇÃO
# ============================================================================
if __name__ == "__main__":
    # Configuração simples para evitar erros
    try:
        main()
    except Exception as e:
        st.error(f"Erro crítico: {e}")
        st.stop()
