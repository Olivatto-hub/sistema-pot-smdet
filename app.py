# app.py - SISTEMA POT - VERSÃO SEM CHARDET
# Usa apenas bibliotecas padrão do Python e Streamlit

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from io import StringIO, BytesIO
import warnings
from datetime import datetime
import re
import csv
import codecs

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
# FUNÇÕES DE PROCESSAMENTO - SEM CHARDET
# ============================================================================

def detectar_encoding_sem_chardet(bytes_data):
    """Detecta encoding usando métodos nativos do Python"""
    # Lista de encodings comuns no Brasil
    encodings = ['utf-8-sig', 'latin-1', 'cp1252', 'iso-8859-1', 'utf-8']
    
    for encoding in encodings:
        try:
            # Tentar decodificar
            bytes_data.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    
    # Se nenhum funcionar, usar latin-1 (sempre decodifica, mesmo que com erros)
    return 'latin-1'

def tentar_decodificar(bytes_data):
    """Tenta várias estratégias de decodificação"""
    try:
        # Primeira tentativa: UTF-8 com BOM
        try:
            return bytes_data.decode('utf-8-sig')
        except:
            pass
        
        # Segunda tentativa: Latin-1 (sempre funciona)
        try:
            return bytes_data.decode('latin-1')
        except:
            pass
        
        # Terceira tentativa: CP1252 (Windows)
        try:
            return bytes_data.decode('cp1252')
        except:
            pass
        
        # Último recurso: UTF-8 com tratamento de erros
        return bytes_data.decode('utf-8', errors='replace')
    except:
        # Se tudo falhar, força latin-1 ignorando erros
        return bytes_data.decode('latin-1', errors='ignore')

def limpar_valor_monetario(valor):
    """Converte valores monetários brasileiros para float"""
    if pd.isna(valor) or str(valor).strip() in ['', 'nan', 'None', 'NaT']:
        return np.nan
    
    try:
        texto = str(valor).strip()
        
        # Remover R$ e espaços
        texto = re.sub(r'[R\$\s\']', '', texto)
        
        # Remover aspas
        texto = texto.replace('"', '').replace("'", "")
        
        if texto == '':
            return np.nan
        
        # Formato brasileiro: 1.027,18 ou 272.486,06
        if ',' in texto:
            if '.' in texto:
                # Formato com separador de milhar e decimal
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

def processar_csv_robusto(arquivo):
    """Processa arquivo CSV de forma robusta"""
    try:
        # Obter bytes do arquivo
        bytes_data = arquivo.getvalue()
        
        # Decodificar usando método robusto
        conteudo = tentar_decodificar(bytes_data)
        
        # Remover BOM se existir
        conteudo = conteudo.lstrip('\ufeff')
        
        # Substituir caracteres problemáticos
        conteudo = conteudo.replace('\x00', '').replace('\r\n', '\n').replace('\r', '\n')
        
        # Remover linhas que são apenas totais (muitos ;;;)
        linhas = conteudo.split('\n')
        linhas_validas = []
        
        for linha in linhas:
            linha = linha.strip()
            if linha:
                # Pular linhas que são apenas totais ou resumos
                if linha.count(';') > 8 and any(x in linha for x in ['R$', ';;;', ';;;;']):
                    continue
                linhas_validas.append(linha)
        
        if len(linhas_validas) < 2:
            return None, "Arquivo vazio ou sem dados válidos"
        
        # Detectar delimitador
        primeira_linha = linhas_validas[0]
        if ';' in primeira_linha:
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
                engine='python'
            )
        except Exception as e:
            # Método manual
            st.warning(f"Usando método manual para {arquivo.name}")
            dados = []
            for linha in linhas_validas:
                dados.append(linha.split(sep))
            
            if len(dados) < 2:
                return None, "Não foi possível ler o CSV"
            
            df = pd.DataFrame(dados[1:], columns=dados[0])
        
        # Padronizar nomes das colunas
        df.columns = [str(col).strip().lower() for col in df.columns]
        
        # Mapeamento de colunas
        mapeamento = {
            'ordem': 'ordem',
            'projeto': 'projeto',
            'num cartao': 'cartao',
            'cartão': 'cartao',
            'nome': 'nome',
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
            'gerenciadora': 'gerenciadora',
            'mes referencia': 'mes_referencia',
            'mes': 'mes_referencia'
        }
        
        # Aplicar mapeamento
        for col_antiga, col_nova in mapeamento.items():
            if col_antiga in df.columns:
                df.rename(columns={col_antiga: col_nova}, inplace=True)
        
        # Processar colunas monetárias
        colunas_monetarias = ['valor_total', 'valor_desconto', 'valor_pagto', 'valor_dia']
        for col in colunas_monetarias:
            if col in df.columns:
                df[col] = df[col].apply(limpar_valor_monetario)
        
        # Processar colunas numéricas
        if 'dias_apagar' in df.columns:
            df['dias_apagar'] = pd.to_numeric(df['dias_apagar'], errors='coerce')
        
        # Processar datas
        if 'data_pagto' in df.columns:
            df['data_pagto'] = pd.to_datetime(df['data_pagto'], dayfirst=True, errors='coerce')
        
        # Processar gerenciadora
        if 'gerenciadora' in df.columns:
            df['gerenciadora'] = df['gerenciadora'].astype(str).str.upper().str.strip()
        
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
        
        # Remover linhas completamente vazias
        df.replace('', np.nan, inplace=True)
        df.dropna(how='all', inplace=True)
        
        return df, f"✅ Processado: {len(df)} registros ({mes_referencia})"
    
    except Exception as e:
        return None, f"❌ Erro ao processar: {str(e)[:100]}"

def processar_excel_robusto(arquivo):
    """Processa arquivo Excel"""
    try:
        # Ler Excel
        df = pd.read_excel(arquivo, dtype=str)
        
        # Padronizar colunas
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
                df.rename(columns={col_antiga: col_nova}, inplace=True)
        
        # Processar valores
        if 'valor_pagto' in df.columns:
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

def calcular_metricas(df):
    """Calcula métricas dos dados"""
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
        else:
            metricas['valor_total'] = 0.0
            metricas['valor_medio'] = 0.0
    
    if 'projeto' in df.columns:
        metricas['projetos_unicos'] = df['projeto'].nunique()
    
    if 'mes_referencia' in df.columns:
        metricas['meses_unicos'] = df['mes_referencia'].nunique()
    
    if 'agencia' in df.columns:
        metricas['agencias_unicas'] = df['agencia'].nunique()
    
    return metricas

def gerar_consolidado_mensal(df):
    """Gera consolidação mensal"""
    if 'mes_referencia' not in df.columns or 'valor_pagto' not in df.columns:
        return pd.DataFrame()
    
    try:
        consolidado = df.groupby('mes_referencia').agg(
            quantidade_pagamentos=('valor_pagto', 'count'),
            valor_total=('valor_pagto', 'sum'),
            valor_medio=('valor_pagto', 'mean'),
            quantidade_projetos=('projeto', 'nunique') if 'projeto' in df.columns else pd.Series([0]),
            quantidade_agencias=('agencia', 'nunique') if 'agencia' in df.columns else pd.Series([0])
        ).round(2)
        
        return consolidado
    except:
        return pd.DataFrame()

def gerar_consolidado_projetos(df):
    """Gera consolidação por projeto"""
    if 'projeto' not in df.columns or 'valor_pagto' not in df.columns:
        return pd.DataFrame()
    
    try:
        consolidado = df.groupby('projeto').agg(
            quantidade_pagamentos=('valor_pagto', 'count'),
            valor_total=('valor_pagto', 'sum'),
            valor_medio=('valor_pagto', 'mean'),
            quantidade_meses=('mes_referencia', 'nunique') if 'mes_referencia' in df.columns else pd.Series([0])
        ).round(2)
        
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
    
    # Sidebar
    with st.sidebar:
        st.header("📁 CARREGAR ARQUIVOS")
        
        arquivos = st.file_uploader(
            "Selecione os arquivos",
            type=['csv', 'txt', 'xlsx', 'xls'],
            accept_multiple_files=True,
            help="Formatos suportados: CSV, TXT, Excel"
        )
        
        st.markdown("---")
        st.header("⚙️ CONFIGURAÇÕES")
        
        modo = st.radio(
            "Modo de processamento:",
            ["Substituir dados", "Acumular dados"]
        )
        
        mostrar_graficos = st.checkbox("Mostrar gráficos", value=True)
        
        st.markdown("---")
        st.header("📊 STATUS")
        
        if not st.session_state.dados_consolidados.empty:
            metricas = calcular_metricas(st.session_state.dados_consolidados)
            st.success("Dados carregados:")
            st.metric("Registros", f"{metricas['total_registros']:,}")
            st.metric("Valor Total", f"R$ {metricas.get('valor_total', 0):,.2f}")
        else:
            st.info("⏳ Aguardando arquivos...")
        
        if st.button("🧹 Limpar Dados", use_container_width=True):
            st.session_state.dados_consolidados = pd.DataFrame()
            st.rerun()
    
    # Área principal
    if not arquivos:
        st.info("👋 **Sistema de Monitoramento de Pagamentos - POT**")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown("""
            ### 🚀 **VERSÃO ROBUSTA - SEM DEPENDÊNCIAS EXTERNAS**
            
            **✅ CARACTERÍSTICAS:**
            
            1. **Processamento Ultra Robusto**
               - Qualquer encoding (UTF-8, Latin-1, CP1252)
               - Ignora linhas corrompidas
               - Remove automaticamente totais
            
            2. **Análise Completa**
               - Consolidação por mês
               - Análise por projeto
               - Métricas detalhadas
            
            3. **Exportação Total**
               - CSV formatado
               - Excel com múltiplas abas
               - Relatórios completos
            
            4. **Interface Amigável**
               - Filtros interativos
               - Gráficos Plotly
               - Armazenamento em sessão
            
            **🔧 TECNOLOGIAS:**
            - Python puro (sem chardet)
            - Pandas para processamento
            - Plotly para visualização
            - Streamlit para interface
            """)
        
        with col2:
            st.markdown("""
            ### 📋 **COMO USAR:**
            
            1. **Arraste os arquivos** para a barra lateral
               - CSV, TXT ou Excel
               - Múltiplos arquivos de uma vez
            
            2. **Configure as opções**
               - Substituir ou acumular dados
               - Ativar/desativar gráficos
            
            3. **Analise os resultados**
               - Métricas principais
               - Consolidação mensal
               - Análise por projeto
            
            4. **Exporte relatórios**
               - Dados completos
               - Consolidações
               - Relatório Excel
            
            ### ⚠️ **PROBLEMAS COMUNS:**
            
            **Arquivo não processa?**
            - O sistema ignora encoding errado
            - Remove linhas problemáticas
            - Processa o máximo possível
            
            **Valores incorretos?**
            - Converte R$ 1.027,18 para 1027.18
            - Detecta formato brasileiro
            - Ignora erros de conversão
            """)
        
        return
    
    # Processar arquivos
    st.header("🔄 PROCESSAMENTO DE ARQUIVOS")
    
    dataframes = []
    mensagens = []
    
    with st.spinner(f"Processando {len(arquivos)} arquivo(s)..."):
        progress_bar = st.progress(0)
        
        for i, arquivo in enumerate(arquivos):
            progresso = (i + 1) / len(arquivos)
            progress_bar.progress(progresso)
            
            try:
                if arquivo.name.lower().endswith(('.csv', '.txt')):
                    df, msg = processar_csv_robusto(arquivo)
                elif arquivo.name.lower().endswith(('.xlsx', '.xls')):
                    df, msg = processar_excel_robusto(arquivo)
                else:
                    msg = f"❌ Formato não suportado: {arquivo.name}"
                    df = None
                
                if df is not None:
                    dataframes.append(df)
                    st.success(f"✅ {arquivo.name}: {msg}")
                else:
                    st.error(f"❌ {arquivo.name}: {msg}")
                
                mensagens.append(msg)
            except Exception as e:
                erro = f"❌ Erro crítico em {arquivo.name}: {str(e)[:100]}"
                st.error(erro)
                mensagens.append(erro)
        
        progress_bar.empty()
    
    if not dataframes:
        st.error("❌ Nenhum arquivo foi processado com sucesso")
        return
    
    # Consolidar dados
    novo_df = pd.concat(dataframes, ignore_index=True, sort=False)
    
    # Atualizar dados da sessão
    if modo == "Substituir dados" or st.session_state.dados_consolidados.empty:
        st.session_state.dados_consolidados = novo_df
        st.success(f"✅ {len(novo_df)} registros processados")
    else:
        st.session_state.dados_consolidados = pd.concat(
            [st.session_state.dados_consolidados, novo_df], 
            ignore_index=True,
            sort=False
        )
        st.success(f"✅ {len(novo_df)} novos registros adicionados. Total: {len(st.session_state.dados_consolidados)}")
    
    df_final = st.session_state.dados_consolidados
    
    # Calcular métricas
    metricas = calcular_metricas(df_final)
    
    # Métricas principais
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
            valores_validos = df_final['valor_pagto'].dropna().count()
            st.metric("Valores Válidos", f"{valores_validos:,}")
    
    # Tabs de análise
    tab1, tab2, tab3, tab4 = st.tabs(["📋 Dados", "📅 Mensal", "🏢 Projetos", "💾 Exportar"])
    
    with tab1:
        st.subheader("📋 Dados Processados")
        
        # Filtros
        col_f1, col_f2, col_f3 = st.columns(3)
        
        with col_f1:
            if 'mes_referencia' in df_final.columns:
                meses = ['Todos'] + sorted(df_final['mes_referencia'].dropna().unique().tolist())
                mes_filtro = st.selectbox("Filtrar por mês:", meses)
            else:
                mes_filtro = 'Todos'
        
        with col_f2:
            if 'projeto' in df_final.columns:
                projetos = ['Todos'] + sorted(df_final['projeto'].dropna().unique().tolist()[:50])
                projeto_filtro = st.selectbox("Filtrar por projeto:", projetos)
            else:
                projeto_filtro = 'Todos'
        
        with col_f3:
            if 'gerenciadora' in df_final.columns:
                gerenciadoras = ['Todas'] + sorted(df_final['gerenciadora'].dropna().unique().tolist())
                gerenciadora_filtro = st.selectbox("Filtrar por gerenciadora:", gerenciadoras)
            else:
                gerenciadora_filtro = 'Todas'
        
        # Aplicar filtros
        df_filtrado = df_final.copy()
        
        if mes_filtro != 'Todos' and 'mes_referencia' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['mes_referencia'] == mes_filtro]
        
        if projeto_filtro != 'Todos' and 'projeto' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['projeto'] == projeto_filtro]
        
        if gerenciadora_filtro != 'Todas' and 'gerenciadora' in df_filtrado.columns:
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
            st.info(f"**Filtro aplicado:** {len(df_filtrado):,} registros | Valor total: R$ {valor_filtrado:,.2f}")
    
    with tab2:
        st.subheader("📅 Consolidação Mensal")
        
        consolidado_mensal = gerar_consolidado_mensal(df_final)
        
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
        
        consolidado_projetos = gerar_consolidado_projetos(df_final)
        
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
            # Dados completos CSV
            csv_completo = df_final.to_csv(index=False, sep=';', decimal=',')
            st.download_button(
                label="📄 Dados Completos (CSV)",
                data=csv_completo,
                file_name=f"pot_completo_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col_exp2:
            # Consolidação mensal CSV
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
            # Consolidação projetos CSV
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
                    'Métrica': [
                        'Total de Registros',
                        'Valor Total (R$)',
                        'Valor Médio (R$)',
                        'Quantidade de Arquivos',
                        'Quantidade de Projetos',
                        'Quantidade de Meses',
                        'Quantidade de Agências',
                        'Data de Exportação'
                    ],
                    'Valor': [
                        metricas['total_registros'],
                        f"R$ {metricas.get('valor_total', 0):,.2f}",
                        f"R$ {metricas.get('valor_medio', 0):,.2f}",
                        metricas['arquivos_unicos'],
                        metricas.get('projetos_unicos', 0),
                        metricas.get('meses_unicos', 0),
                        metricas.get('agencias_unicas', 0),
                        datetime.now().strftime('%d/%m/%Y %H:%M')
                    ]
                }
                resumo_df = pd.DataFrame(resumo_data)
                resumo_df.to_excel(writer, sheet_name='RESUMO_EXECUTIVO', index=False)
            
            excel_bytes = output.getvalue()
            
            st.download_button(
                label="📊 BAIXAR RELATÓRIO COMPLETO (Excel)",
                data=excel_bytes,
                file_name=f"relatorio_pot_completo_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        except Exception as e:
            st.warning(f"Exportação Excel não disponível: {str(e)}")
            st.info("Use os botões CSV acima para exportar os dados")
    
    # Rodapé
    st.markdown("---")
    st.caption(f"⚙️ Sistema POT - Versão Robusta | {datetime.now().strftime('%d/%m/%Y %H:%M')} | Registros: {metricas['total_registros']:,}")

# ============================================================================
# EXECUÇÃO
# ============================================================================

if __name__ == "__main__":
    main()
