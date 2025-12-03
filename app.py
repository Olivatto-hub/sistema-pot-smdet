# app.py - SISTEMA POT 
# SEM chardet - USANDO APENAS BIBLIOTECAS NATIVAS

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from io import StringIO, BytesIO
import warnings
from datetime import datetime
import re
import csv

# Desativar warnings
warnings.filterwarnings('ignore')

# Configuração da página
st.set_page_config(
    page_title="Sistema POT - Monitoramento",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Título
st.title("📊 SISTEMA DE MONITORAMENTO DE PAGAMENTOS - POT")
st.markdown("---")

# ============================================================================
# FUNÇÕES DE PROCESSAMENTO - SEM DEPENDÊNCIAS EXTERNAS
# ============================================================================

def detectar_encoding_simples(bytes_data):
    """
    Detecta encoding usando métodos simples sem chardet
    Tenta os encodings mais comuns no Brasil
    """
    # Lista de encodings em ordem de tentativa
    encodings = ['utf-8-sig', 'latin-1', 'cp1252', 'iso-8859-1', 'utf-8']
    
    for encoding in encodings:
        try:
            # Tentar decodificar
            bytes_data.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    
    # Se nenhum funcionar, usar latin-1 com tratamento de erros
    return 'latin-1'

def decodificar_arquivo(bytes_data):
    """
    Decodifica arquivo com tratamento robusto de erros
    """
    # Primeiro, tentar UTF-8 com BOM (comum em arquivos brasileiros exportados)
    try:
        return bytes_data.decode('utf-8-sig')
    except UnicodeDecodeError:
        pass
    
    # Tentar Latin-1 (sempre funciona, mas pode ter caracteres errados)
    try:
        return bytes_data.decode('latin-1')
    except UnicodeDecodeError:
        pass
    
    # Tentar CP1252 (Windows)
    try:
        return bytes_data.decode('cp1252')
    except UnicodeDecodeError:
        pass
    
    # Último recurso: usar latin-1 ignorando erros
    return bytes_data.decode('latin-1', errors='ignore')

def limpar_valor_monetario(valor):
    """Converte valores monetários brasileiros para float"""
    if pd.isna(valor) or str(valor).strip() in ['', 'nan', 'None', 'NaT', 'NULL']:
        return np.nan
    
    try:
        texto = str(valor).strip()
        
        # Remover R$, espaços e caracteres especiais
        texto = re.sub(r'[R\$\s\'\"]', '', texto)
        
        if texto == '':
            return np.nan
        
        # Se já é número, retornar
        try:
            return float(texto)
        except:
            pass
        
        # Formato brasileiro: 1.027,18 ou 272.486,06
        if ',' in texto:
            if '.' in texto:
                # Formato com separador de milhar (.) e decimal (,)
                # Exemplo: 1.027,18 ou 272.486,06
                # Remover pontos de milhar
                texto = texto.replace('.', '')
                # Substituir vírgula decimal por ponto
                texto = texto.replace(',', '.')
            else:
                # Apenas vírgula decimal
                texto = texto.replace(',', '.')
        
        # Tentar converter
        return float(texto)
    except:
        return np.nan

def processar_csv_pot(arquivo):
    """Processa arquivo CSV do POT de forma robusta"""
    try:
        # Obter bytes do arquivo
        bytes_data = arquivo.getvalue()
        
        # Decodificar usando método robusto
        conteudo = decodificar_arquivo(bytes_data)
        
        # Limpar conteúdo
        conteudo = conteudo.lstrip('\ufeff')  # Remover BOM
        conteudo = conteudo.replace('\r\n', '\n').replace('\r', '\n')
        conteudo = conteudo.replace('\x00', '')  # Remover null bytes
        
        # Separar linhas
        linhas = conteudo.split('\n')
        
        # Remover linhas vazias e linhas que são apenas totais
        linhas_validas = []
        for linha in linhas:
            linha = linha.strip()
            if linha:
                # Pular linhas que são apenas totais (muitos ;;;)
                if linha.count(';') > 8 and 'R$' in linha:
                    continue
                linhas_validas.append(linha)
        
        if len(linhas_validas) < 2:
            return None, "Arquivo vazio ou sem dados válidos"
        
        # Detectar delimitador
        primeira_linha = linhas_validas[0]
        if ';' in primeira_linha and primeira_linha.count(';') > primeira_linha.count(','):
            sep = ';'
        else:
            sep = ','
        
        # Ler CSV
        try:
            df = pd.read_csv(
                StringIO('\n'.join(linhas_validas)),
                sep=sep,
                dtype=str,
                on_bad_lines='skip',
                engine='python',
                quoting=csv.QUOTE_MINIMAL
            )
        except Exception as e:
            # Método manual como fallback
            st.warning(f"Usando método manual para {arquivo.name}")
            dados = []
            for linha in linhas_validas:
                if sep == ';':
                    # Tratar caso especial onde ; está dentro de valores entre aspas
                    partes = []
                    dentro_aspas = False
                    parte_atual = ''
                    
                    for char in linha:
                        if char == '"':
                            dentro_aspas = not dentro_aspas
                        elif char == sep and not dentro_aspas:
                            partes.append(parte_atual.strip('"'))
                            parte_atual = ''
                        else:
                            parte_atual += char
                    
                    if parte_atual:
                        partes.append(parte_atual.strip('"'))
                    
                    dados.append(partes)
                else:
                    dados.append(linha.split(sep))
            
            if len(dados) < 2:
                return None, "Não foi possível ler o CSV"
            
            # Garantir que todas as linhas tenham o mesmo número de colunas
            max_cols = max(len(linha) for linha in dados)
            dados_padronizados = []
            for linha in dados:
                if len(linha) < max_cols:
                    linha = linha + [''] * (max_cols - len(linha))
                elif len(linha) > max_cols:
                    linha = linha[:max_cols]
                dados_padronizados.append(linha)
            
            df = pd.DataFrame(dados_padronizados[1:], columns=dados_padronizados[0])
        
        # Limpar nomes das colunas
        df.columns = [str(col).strip().lower() for col in df.columns]
        
        # Mapeamento de colunas
        mapeamento_colunas = {
            'ordem': 'ordem',
            'projeto': 'projeto',
            'num cartao': 'cartao',
            'cartão': 'cartao',
            'nº cartão': 'cartao',
            'n° cartão': 'cartao',
            'nome': 'nome',
            'distrito': 'distrito',
            'agencia': 'agencia',
            'agência': 'agencia',
            'rg': 'rg',
            'cpf': 'cpf',
            'valor total': 'valor_total',
            'valor desconto': 'valor_desconto',
            'valor pagto': 'valor_pagto',
            'valor pagamento': 'valor_pagto',
            'data pagto': 'data_pagto',
            'data': 'data_pagto',
            'valor dia': 'valor_dia',
            'dias validos': 'dias_apagar',
            'dias a pagar': 'dias_apagar',
            'dias': 'dias_apagar',
            'gerenciadora': 'gerenciadora',
            'mes referencia': 'mes_referencia',
            'mes': 'mes_referencia'
        }
        
        # Aplicar mapeamento
        for col_antiga, col_nova in mapeamento_colunas.items():
            if col_antiga in df.columns:
                df = df.rename(columns={col_antiga: col_nova})
        
        # Garantir colunas essenciais
        if 'projeto' not in df.columns:
            df['projeto'] = 'NÃO INFORMADO'
        
        if 'valor_pagto' not in df.columns:
            # Procurar coluna que tenha 'valor' no nome
            colunas_valor = [col for col in df.columns if 'valor' in col.lower()]
            if colunas_valor:
                df['valor_pagto'] = df[colunas_valor[0]]
            else:
                df['valor_pagto'] = 0
        
        # Processar colunas monetárias
        colunas_monetarias = ['valor_total', 'valor_desconto', 'valor_pagto', 'valor_dia']
        for col in colunas_monetarias:
            if col in df.columns:
                df[col] = df[col].apply(limpar_valor_monetario)
        
        # Processar outras colunas numéricas
        if 'dias_apagar' in df.columns:
            df['dias_apagar'] = pd.to_numeric(df['dias_apagar'], errors='coerce')
        
        if 'ordem' in df.columns:
            df['ordem'] = pd.to_numeric(df['ordem'], errors='coerce')
        
        # Processar datas
        if 'data_pagto' in df.columns:
            df['data_pagto'] = pd.to_datetime(df['data_pagto'], dayfirst=True, errors='coerce')
        
        # Processar gerenciadora
        if 'gerenciadora' in df.columns:
            df['gerenciadora'] = df['gerenciadora'].astype(str).str.strip().str.upper()
        
        # Adicionar metadados
        df['arquivo_origem'] = arquivo.name
        
        # Extrair mês do nome do arquivo
        nome_upper = arquivo.name.upper()
        meses = {
            'JANEIRO': 'Janeiro', 'JAN': 'Janeiro',
            'FEVEREIRO': 'Fevereiro', 'FEV': 'Fevereiro',
            'MARÇO': 'Março', 'MARCO': 'Março', 'MAR': 'Março',
            'ABRIL': 'Abril', 'ABR': 'Abril',
            'MAIO': 'Maio', 'MAI': 'Maio',
            'JUNHO': 'Junho', 'JUN': 'Junho',
            'JULHO': 'Julho', 'JUL': 'Julho',
            'AGOSTO': 'Agosto', 'AGO': 'Agosto',
            'SETEMBRO': 'Setembro', 'SET': 'Setembro',
            'OUTUBRO': 'Outubro', 'OUT': 'Outubro',
            'NOVEMBRO': 'Novembro', 'NOV': 'Novembro',
            'DEZEMBRO': 'Dezembro', 'DEZ': 'Dezembro'
        }
        
        mes_referencia = 'Não identificado'
        for chave, valor in meses.items():
            if chave in nome_upper:
                mes_referencia = valor
                break
        
        df['mes_referencia'] = mes_referencia
        df['ano'] = datetime.now().year
        
        # Limpar dados
        df = df.replace(['', 'nan', 'NaN', 'None', 'NaT'], np.nan)
        df = df.dropna(subset=['valor_pagto'], how='all')
        
        # Remover duplicatas completas
        df = df.drop_duplicates()
        
        return df, f"✅ Processado: {len(df)} registros ({mes_referencia})"
    
    except Exception as e:
        return None, f"❌ Erro ao processar: {str(e)}"

def processar_excel_pot(arquivo):
    """Processa arquivo Excel"""
    try:
        # Ler Excel
        df = pd.read_excel(arquivo, dtype=str)
        
        # Limpar nomes das colunas
        df.columns = [str(col).strip().lower() for col in df.columns]
        
        # Mapeamento
        mapeamento = {
            'projeto': 'projeto',
            'nome': 'nome',
            'valor pagto': 'valor_pagto',
            'valor pagamento': 'valor_pagto',
            'data pagto': 'data_pagto',
            'agencia': 'agencia',
            'gerenciadora': 'gerenciadora'
        }
        
        for col_antiga, col_nova in mapeamento.items():
            if col_antiga in df.columns:
                df = df.rename(columns={col_antiga: col_nova})
        
        # Garantir colunas essenciais
        if 'projeto' not in df.columns:
            df['projeto'] = 'NÃO INFORMADO'
        
        if 'valor_pagto' not in df.columns:
            df['valor_pagto'] = 0
        
        # Processar valores
        df['valor_pagto'] = df['valor_pagto'].apply(limpar_valor_monetario)
        
        # Adicionar metadados
        df['arquivo_origem'] = arquivo.name
        df['mes_referencia'] = 'Excel'
        df['ano'] = datetime.now().year
        
        return df, f"✅ Excel processado: {len(df)} registros"
    
    except Exception as e:
        return None, f"❌ Erro no Excel: {str(e)}"

# ============================================================================
# FUNÇÕES DE ANÁLISE
# ============================================================================

def calcular_metricas_detalhadas(df):
    """Calcula métricas detalhadas"""
    metricas = {
        'total_registros': len(df),
        'arquivos_unicos': df['arquivo_origem'].nunique() if 'arquivo_origem' in df.columns else 0
    }
    
    if 'valor_pagto' in df.columns:
        valores = df['valor_pagto'].dropna()
        if len(valores) > 0:
            metricas['valor_total'] = float(valores.sum())
            metricas['valor_medio'] = float(valores.mean())
            metricas['valor_min'] = float(valores.min())
            metricas['valor_max'] = float(valores.max())
            metricas['desvio_padrao'] = float(valores.std())
            metricas['qtd_valores_validos'] = len(valores)
        else:
            metricas['valor_total'] = 0.0
            metricas['valor_medio'] = 0.0
    
    if 'projeto' in df.columns:
        metricas['projetos_unicos'] = df['projeto'].nunique()
    
    if 'mes_referencia' in df.columns:
        metricas['meses_unicos'] = df['mes_referencia'].nunique()
        metricas['meses'] = sorted(df['mes_referencia'].unique().tolist())
    
    if 'agencia' in df.columns:
        metricas['agencias_unicas'] = df['agencia'].nunique()
    
    if 'gerenciadora' in df.columns:
        gerenciadoras = df['gerenciadora'].value_counts().to_dict()
        metricas['gerenciadoras'] = gerenciadoras
    
    return metricas

def gerar_consolidacao_mensal(df):
    """Gera consolidação por mês"""
    if 'mes_referencia' not in df.columns or 'valor_pagto' not in df.columns:
        return pd.DataFrame()
    
    try:
        consolidado = df.groupby('mes_referencia').agg(
            qtd_pagamentos=('valor_pagto', 'count'),
            valor_total=('valor_pagto', 'sum'),
            valor_medio=('valor_pagto', 'mean'),
            qtd_projetos=('projeto', 'nunique') if 'projeto' in df.columns else pd.Series([0]),
            qtd_agencias=('agencia', 'nunique') if 'agencia' in df.columns else pd.Series([0]),
            arquivos=('arquivo_origem', 'nunique')
        ).round(2)
        
        # Ordenar por mês lógico
        ordem_meses = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                      'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
        
        # Reindexar se possível
        meses_presentes = [m for m in ordem_meses if m in consolidado.index]
        if meses_presentes:
            consolidado = consolidado.reindex(meses_presentes)
        
        return consolidado
    except:
        return pd.DataFrame()

def gerar_consolidacao_projetos(df):
    """Gera consolidação por projeto"""
    if 'projeto' not in df.columns or 'valor_pagto' not in df.columns:
        return pd.DataFrame()
    
    try:
        consolidado = df.groupby('projeto').agg(
            qtd_pagamentos=('valor_pagto', 'count'),
            valor_total=('valor_pagto', 'sum'),
            valor_medio=('valor_pagto', 'mean'),
            qtd_meses=('mes_referencia', 'nunique') if 'mes_referencia' in df.columns else pd.Series([0]),
            qtd_agencias=('agencia', 'nunique') if 'agencia' in df.columns else pd.Series([0]),
            primeiro_pagamento=('data_pagto', 'min') if 'data_pagto' in df.columns else None,
            ultimo_pagamento=('data_pagto', 'max') if 'data_pagto' in df.columns else None
        ).round(2)
        
        # Remover colunas None
        consolidado = consolidado.dropna(axis=1, how='all')
        
        return consolidado.sort_values('valor_total', ascending=False)
    except:
        return pd.DataFrame()

# ============================================================================
# INTERFACE PRINCIPAL
# ============================================================================

def main():
    # Inicializar sessão
    if 'dados_consolidados' not in st.session_state:
        st.session_state.dados_consolidados = pd.DataFrame()
    
    if 'historico_processamento' not in st.session_state:
        st.session_state.historico_processamento = []
    
    # Sidebar
    with st.sidebar:
        st.header("📁 CARREGAMENTO")
        
        arquivos = st.file_uploader(
            "Selecione os arquivos",
            type=['csv', 'txt', 'xlsx', 'xls'],
            accept_multiple_files=True,
            help="Arraste e solte múltiplos arquivos"
        )
        
        st.markdown("---")
        st.header("⚙️ CONFIGURAÇÕES")
        
        modo = st.radio(
            "Modo de processamento:",
            ["Substituir dados existentes", "Acumular aos dados existentes"],
            index=0
        )
        
        mostrar_graficos = st.checkbox("Mostrar gráficos", value=True)
        
        st.markdown("---")
        st.header("📊 STATUS")
        
        if not st.session_state.dados_consolidados.empty:
            metricas = calcular_metricas_detalhadas(st.session_state.dados_consolidados)
            
            st.success("✅ Dados carregados")
            st.metric("Registros", f"{metricas['total_registros']:,}")
            st.metric("Valor Total", f"R$ {metricas.get('valor_total', 0):,.2f}")
            st.metric("Arquivos", metricas['arquivos_unicos'])
            
            if st.button("🧹 Limpar Todos os Dados", type="secondary", use_container_width=True):
                st.session_state.dados_consolidados = pd.DataFrame()
                st.session_state.historico_processamento = []
                st.rerun()
        else:
            st.info("⏳ Aguardando arquivos...")
        
        st.markdown("---")
        st.caption(f"🕒 {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    
    # Área principal
    if not arquivos:
        # Tela inicial
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.header("🎯 SISTEMA POT - VERSÃO DEFINITIVA")
            st.markdown("""
            ### ✨ **CARACTERÍSTICAS PRINCIPAIS:**
            
            **✅ PROCESSAMENTO ROBUSTO:**
            - Qualquer encoding (UTF-8, Latin-1, CP1252)
            - Ignora linhas corrompidas
            - Remove totais automaticamente
            - Converte valores brasileiros (R$ 1.027,18)
            
            **✅ ANÁLISE COMPLETA:**
            - Consolidação por mês
            - Análise por projeto
            - Métricas detalhadas
            - Evolução temporal
            
            **✅ EXPORTAÇÃO:**
            - Dados completos em CSV
            - Relatórios Excel
            - Consolidações separadas
            
            **✅ INTERFACE:**
            - Filtros interativos
            - Gráficos Plotly
            - Armazenamento em sessão
            - Multi-arquivos
            """)
        
        with col2:
            st.header("📋 **COMO USAR:**")
            st.markdown("""
            1. **Carregue os arquivos** na barra lateral
            2. **Escolha o modo** de processamento
            3. **Analise os resultados**
            4. **Exporte relatórios**
            
            ### 📁 **ARQUIVOS ACEITOS:**
            
            **CSV/TXT:**
            - Separador ; ou ,
            - Encoding qualquer
            - Formato brasileiro
            
            **Excel:**
            - .xlsx, .xls
            - Múltiplas abas
            
            ### 🔧 **TECNOLOGIAS:**
            
            - Python 3.9+
            - Pandas (processamento)
            - Plotly (gráficos)
            - Streamlit (interface)
            
            **✅ SEM DEPENDÊNCIAS EXTERNAS**
            """)
            
            st.info("""
            **💡 DICA:** 
            O sistema detecta automaticamente
            o mês pelo nome do arquivo!
            Ex: SETEMBRO.csv → Setembro
            """)
        
        # Mostrar histórico se existir
        if st.session_state.historico_processamento:
            st.markdown("---")
            st.subheader("📜 Histórico de Processamento")
            for item in st.session_state.historico_processamento[-3:]:
                st.info(item)
        
        return
    
    # Processar arquivos
    st.header("🔄 PROCESSANDO ARQUIVOS")
    
    dataframes = []
    mensagens_processamento = []
    
    with st.spinner(f"Processando {len(arquivos)} arquivo(s)..."):
        progress_bar = st.progress(0)
        
        for i, arquivo in enumerate(arquivos):
            progresso = (i + 1) / len(arquivos)
            progress_bar.progress(progresso)
            
            try:
                if arquivo.name.lower().endswith(('.csv', '.txt')):
                    df, msg = processar_csv_pot(arquivo)
                elif arquivo.name.lower().endswith(('.xlsx', '.xls')):
                    df, msg = processar_excel_pot(arquivo)
                else:
                    msg = f"Formato não suportado: {arquivo.name}"
                    df = None
                
                if df is not None:
                    dataframes.append(df)
                    mensagens_processamento.append(msg)
                    
                    with st.expander(f"📄 {arquivo.name}", expanded=False):
                        st.success(msg)
                        if len(df) > 0:
                            st.dataframe(df.head(3), use_container_width=True)
                else:
                    mensagens_processamento.append(f"❌ {msg}")
                    st.error(f"{arquivo.name}: {msg}")
            
            except Exception as e:
                erro_msg = f"❌ Erro crítico em {arquivo.name}: {str(e)[:200]}"
                mensagens_processamento.append(erro_msg)
                st.error(erro_msg)
        
        progress_bar.empty()
    
    if not dataframes:
        st.error("❌ Nenhum arquivo foi processado com sucesso.")
        return
    
    # Consolidar dados
    novo_df = pd.concat(dataframes, ignore_index=True, sort=False)
    
    # Atualizar dados da sessão
    if modo == "Substituir dados existentes" or st.session_state.dados_consolidados.empty:
        st.session_state.dados_consolidados = novo_df
        st.success(f"✅ {len(novo_df)} registros processados")
    else:
        st.session_state.dados_consolidados = pd.concat(
            [st.session_state.dados_consolidados, novo_df], 
            ignore_index=True,
            sort=False
        )
        st.success(f"✅ {len(novo_df)} novos registros adicionados. Total: {len(st.session_state.dados_consolidados):,}")
    
    # Atualizar histórico
    st.session_state.historico_processamento.extend(mensagens_processamento)
    
    df_final = st.session_state.dados_consolidados
    
    # Calcular métricas
    metricas = calcular_metricas_detalhadas(df_final)
    
    # Mostrar métricas principais
    st.header("📈 MÉTRICAS PRINCIPAIS")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total de Registros", f"{metricas['total_registros']:,}")
    
    with col2:
        st.metric("Valor Total", f"R$ {metricas.get('valor_total', 0):,.2f}")
    
    with col3:
        st.metric("Valor Médio", f"R$ {metricas.get('valor_medio', 0):,.2f}")
    
    with col4:
        st.metric("Arquivos", metricas['arquivos_unicos'])
    
    # Segunda linha de métricas
    col5, col6, col7, col8 = st.columns(4)
    
    with col5:
        st.metric("Projetos", metricas.get('projetos_unicos', 0))
    
    with col6:
        st.metric("Meses", metricas.get('meses_unicos', 0))
    
    with col7:
        st.metric("Agências", metricas.get('agencias_unicas', 0))
    
    with col8:
        if 'valor_pagto' in df_final.columns:
            valores_validos = df_final['valor_pagto'].notna().sum()
            st.metric("Valores Válidos", f"{valores_validos:,}")
    
    # Tabs de análise
    tab1, tab2, tab3, tab4 = st.tabs(["📋 Dados", "📅 Por Mês", "🏢 Por Projeto", "💾 Exportar"])
    
    with tab1:
        st.subheader("📋 Dados Processados")
        
        # Filtros avançados
        col_filtro1, col_filtro2, col_filtro3 = st.columns(3)
        
        with col_filtro1:
            if 'mes_referencia' in df_final.columns:
                meses = ['Todos'] + sorted(df_final['mes_referencia'].dropna().unique().tolist())
                mes_filtro = st.selectbox("Mês:", meses)
            else:
                mes_filtro = 'Todos'
        
        with col_filtro2:
            if 'projeto' in df_final.columns:
                projetos = ['Todos'] + sorted(df_final['projeto'].dropna().unique().tolist())
                projeto_filtro = st.selectbox("Projeto:", projetos)
            else:
                projeto_filtro = 'Todos'
        
        with col_filtro3:
            if 'gerenciadora' in df_final.columns:
                gerenciadoras = ['Todas'] + sorted(df_final['gerenciadora'].dropna().unique().tolist())
                gerenciadora_filtro = st.selectbox("Gerenciadora:", gerenciadoras)
            else:
                gerenciadora_filtro = 'Todas'
        
        # Aplicar filtros
        df_filtrado = df_final.copy()
        
        if mes_filtro != 'Todos':
            df_filtrado = df_filtrado[df_filtrado['mes_referencia'] == mes_filtro]
        
        if projeto_filtro != 'Todos':
            df_filtrado = df_filtrado[df_filtrado['projeto'] == projeto_filtro]
        
        if gerenciadora_filtro != 'Todas':
            df_filtrado = df_filtrado[df_filtrado['gerenciadora'] == gerenciadora_filtro]
        
        # Mostrar dados
        st.dataframe(
            df_filtrado,
            use_container_width=True,
            height=400,
            column_config={
                "valor_pagto": st.column_config.NumberColumn(
                    "Valor Pago",
                    format="R$ %.2f"
                ),
                "valor_total": st.column_config.NumberColumn(
                    "Valor Total",
                    format="R$ %.2f"
                )
            }
        )
        
        # Estatísticas do filtro
        if len(df_filtrado) > 0:
            valor_filtrado = df_filtrado['valor_pagto'].sum() if 'valor_pagto' in df_filtrado.columns else 0
            st.info(f"**Filtro:** {len(df_filtrado):,} registros | Valor: R$ {valor_filtrado:,.2f} | Média: R$ {df_filtrado['valor_pagto'].mean():,.2f}")
    
    with tab2:
        st.subheader("📅 Consolidação por Mês")
        
        consolidado_mensal = gerar_consolidacao_mensal(df_final)
        
        if not consolidado_mensal.empty:
            st.dataframe(
                consolidado_mensal,
                use_container_width=True,
                column_config={
                    "valor_total": st.column_config.NumberColumn(
                        "Valor Total",
                        format="R$ %.2f"
                    ),
                    "valor_medio": st.column_config.NumberColumn(
                        "Valor Médio",
                        format="R$ %.2f"
                    )
                }
            )
            
            # Gráfico
            if mostrar_graficos:
                fig = px.bar(
                    consolidado_mensal.reset_index(),
                    x='mes_referencia',
                    y='valor_total',
                    title='Valor Total por Mês',
                    labels={'valor_total': 'Valor Total (R$)'},
                    text=[f'R$ {x:,.0f}' for x in consolidado_mensal['valor_total']]
                )
                fig.update_traces(textposition='outside')
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Não há dados para consolidação mensal")
    
    with tab3:
        st.subheader("🏢 Consolidação por Projeto")
        
        consolidado_projetos = gerar_consolidacao_projetos(df_final)
        
        if not consolidado_projetos.empty:
            st.dataframe(
                consolidado_projetos.head(50),
                use_container_width=True,
                height=500,
                column_config={
                    "valor_total": st.column_config.NumberColumn(
                        "Valor Total",
                        format="R$ %.2f"
                    ),
                    "valor_medio": st.column_config.NumberColumn(
                        "Valor Médio",
                        format="R$ %.2f"
                    )
                }
            )
            
            # Gráfico top 10
            if mostrar_graficos and len(consolidado_projetos) > 0:
                top_10 = consolidado_projetos.head(10)
                fig = px.bar(
                    top_10.reset_index(),
                    x='projeto',
                    y='valor_total',
                    title='Top 10 Projetos por Valor',
                    labels={'valor_total': 'Valor Total (R$)'},
                    text=[f'R$ {x:,.0f}' for x in top_10['valor_total']]
                )
                fig.update_layout(xaxis_tickangle=-45)
                fig.update_traces(textposition='outside')
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Não há dados de projetos para análise")
    
    with tab4:
        st.subheader("💾 Exportação de Dados")
        
        st.markdown("### 📥 Baixar Relatórios")
        
        col_exp1, col_exp2, col_exp3 = st.columns(3)
        
        with col_exp1:
            # Dados completos
            csv_completo = df_final.to_csv(index=False, sep=';', decimal=',')
            st.download_button(
                label="📄 Dados Completos (CSV)",
                data=csv_completo,
                file_name=f"pot_completo_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col_exp2:
            # Consolidação mensal
            if not consolidado_mensal.empty:
                csv_mensal = consolidado_mensal.to_csv(sep=';', decimal=',')
                st.download_button(
                    label="📅 Consolidação Mensal (CSV)",
                    data=csv_mensal,
                    file_name=f"pot_mensal_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        
        with col_exp3:
            # Consolidação projetos
            if not consolidado_projetos.empty:
                csv_projetos = consolidado_projetos.to_csv(sep=';', decimal=',')
                st.download_button(
                    label="🏢 Consolidação Projetos (CSV)",
                    data=csv_projetos,
                    file_name=f"pot_projetos_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        
        # Exportação Excel
        st.markdown("---")
        st.markdown("### 📊 Relatório Completo em Excel")
        
        try:
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Dados completos
                df_final.to_excel(writer, sheet_name='DADOS_COMPLETOS', index=False)
                
                # Consolidações
                if not consolidado_mensal.empty:
                    consolidado_mensal.to_excel(writer, sheet_name='CONSOLIDADO_MENSAL')
                
                if not consolidado_projetos.empty:
                    consolidado_projetos.to_excel(writer, sheet_name='CONSOLIDADO_PROJETOS')
                
                # Resumo executivo
                resumo_data = {
                    'Total de Registros': [metricas['total_registros']],
                    'Valor Total (R$)': [f"R$ {metricas.get('valor_total', 0):,.2f}"],
                    'Valor Médio (R$)': [f"R$ {metricas.get('valor_medio', 0):,.2f}"],
                    'Quantidade de Arquivos': [metricas['arquivos_unicos']],
                    'Quantidade de Projetos': [metricas.get('projetos_unicos', 0)],
                    'Quantidade de Meses': [metricas.get('meses_unicos', 0)],
                    'Quantidade de Agências': [metricas.get('agencias_unicas', 0)],
                    'Data de Exportação': [datetime.now().strftime('%d/%m/%Y %H:%M')]
                }
                resumo_df = pd.DataFrame(resumo_data)
                resumo_df.to_excel(writer, sheet_name='RESUMO_EXECUTIVO', index=False)
            
            excel_bytes = output.getvalue()
            
            st.download_button(
                label="📊 RELATÓRIO COMPLETO (Excel)",
                data=excel_bytes,
                file_name=f"relatorio_pot_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        except Exception as e:
            st.warning(f"Exportação Excel não disponível")
    
    # Rodapé
    st.markdown("---")
    st.caption(f"⚙️ Sistema POT - Versão Final | {datetime.now().strftime('%d/%m/%Y %H:%M')} | {metricas['total_registros']:,} registros")

# ============================================================================
# EXECUÇÃO
# ============================================================================

if __name__ == "__main__":
    main()
