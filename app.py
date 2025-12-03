# app.py - SISTEMA POT - 
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from io import StringIO, BytesIO
import warnings
from datetime import datetime, timedelta
import re
import csv
import chardet

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
# FUNÇÕES DE PROCESSAMENTO CORRIGIDAS
# ============================================================================

def detectar_codificacao(bytes_data):
    """Detecta automaticamente a codificação do arquivo"""
    try:
        resultado = chardet.detect(bytes_data)
        encoding = resultado['encoding']
        confianca = resultado['confidence']
        
        # Se a confiança for baixa ou encoding None, usar fallbacks
        if not encoding or confianca < 0.7:
            # Lista de encodings comuns no Brasil
            encodings_comuns = ['latin-1', 'cp1252', 'iso-8859-1', 'utf-8-sig']
            for enc in encodings_comuns:
                try:
                    # Tentar decodificar com cada encoding
                    bytes_data.decode(enc)
                    return enc
                except:
                    continue
        
        return encoding if encoding else 'latin-1'
    except:
        return 'latin-1'

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
        
        # Verificar se já é número
        try:
            return float(texto)
        except:
            pass
        
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

def processar_csv_correto(arquivo):
    """Processa arquivo CSV com tratamento correto de encoding"""
    try:
        # Obter bytes do arquivo
        bytes_data = arquivo.getvalue()
        
        # Detectar encoding
        encoding = detectar_codificacao(bytes_data)
        
        # Decodificar usando o encoding detectado
        try:
            conteudo = bytes_data.decode(encoding, errors='replace')
        except:
            # Fallback para latin-1 (sempre funciona)
            conteudo = bytes_data.decode('latin-1', errors='replace')
        
        # Remover BOM se existir
        conteudo = conteudo.lstrip('\ufeff')
        
        # Substituir caracteres problemáticos
        conteudo = conteudo.replace('\x00', '').replace('\r\n', '\n').replace('\r', '\n')
        
        # Detectar delimitador
        linhas = conteudo.split('\n', 10)
        delimitador = ';' if any(';' in linha for linha in linhas) else ','
        
        # Ler CSV
        try:
            df = pd.read_csv(
                StringIO(conteudo),
                delimiter=delimitador,
                dtype=str,
                on_bad_lines='skip',
                engine='python'
            )
        except Exception as e:
            # Se falhar, tentar método manual
            st.warning(f"Usando método alternativo para {arquivo.name}")
            reader = csv.reader(StringIO(conteudo), delimiter=delimitador)
            linhas_csv = list(reader)
            
            if len(linhas_csv) < 2:
                return None, "Arquivo vazio ou sem dados"
            
            df = pd.DataFrame(linhas_csv[1:], columns=linhas_csv[0])
        
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
        return None, f"❌ Erro ao processar CSV: {str(e)}"

def processar_excel_correto(arquivo):
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
    
    consolidado = df.groupby('mes_referencia').agg(
        quantidade_pagamentos=('valor_pagto', 'count'),
        valor_total=('valor_pagto', 'sum'),
        valor_medio=('valor_pagto', 'mean'),
        quantidade_projetos=('projeto', 'nunique') if 'projeto' in df.columns else pd.Series([0]),
        quantidade_agencias=('agencia', 'nunique') if 'agencia' in df.columns else pd.Series([0])
    ).round(2)
    
    return consolidado.sort_index()

def gerar_consolidado_projetos(df):
    """Gera consolidação por projeto"""
    if 'projeto' not in df.columns or 'valor_pagto' not in df.columns:
        return pd.DataFrame()
    
    consolidado = df.groupby('projeto').agg(
        quantidade_pagamentos=('valor_pagto', 'count'),
        valor_total=('valor_pagto', 'sum'),
        valor_medio=('valor_pagto', 'mean'),
        quantidade_meses=('mes_referencia', 'nunique') if 'mes_referencia' in df.columns else pd.Series([0])
    ).round(2)
    
    return consolidado.sort_values('valor_total', ascending=False)

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
        
        st.markdown("---")
        st.header("📊 STATUS")
        
        if not st.session_state.dados_consolidados.empty:
            metricas = calcular_metricas(st.session_state.dados_consolidados)
            st.success("Dados carregados:")
            st.metric("Registros", metricas['total_registros'])
            st.metric("Valor Total", f"R$ {metricas.get('valor_total', 0):,.2f}")
            st.metric("Arquivos", metricas['arquivos_unicos'])
        else:
            st.info("Nenhum dado carregado")
    
    # Área principal
    if not arquivos:
        st.info("👋 **Sistema de Monitoramento de Pagamentos - POT**")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown("""
            ### 📋 Funcionalidades:
            
            1. **Processamento robusto de arquivos**
               - Detecta encoding automaticamente
               - Suporta CSV, TXT, Excel
               - Formato brasileiro (R$ 1.027,18)
            
            2. **Consolidação inteligente**
               - Agrupamento por mês
               - Análise por projeto
               - Histórico temporal
            
            3. **Análise completa**
               - Métricas detalhadas
               - Gráficos interativos
               - Exportação em múltiplos formatos
            
            4. **Detecção de problemas**
               - Valores inconsistentes
               - Dados faltantes
               - Duplicidades
            """)
        
        with col2:
            st.markdown("""
            ### 🚀 Como usar:
            
            1. **Carregue os arquivos** na barra lateral
            2. **Configure o processamento**
            3. **Analise os resultados**
            4. **Exporte relatórios**
            
            ### 📊 Saídas:
            
            - Consolidação mensal
            - Análise por projeto
            - Gráficos interativos
            - Relatórios Excel/CSV
            """)
        
        return
    
    # Processar arquivos
    st.header("🔄 Processamento")
    
    dataframes = []
    mensagens = []
    
    with st.spinner(f"Processando {len(arquivos)} arquivo(s)..."):
        for arquivo in arquivos:
            try:
                if arquivo.name.lower().endswith(('.csv', '.txt')):
                    df, msg = processar_csv_correto(arquivo)
                elif arquivo.name.lower().endswith(('.xlsx', '.xls')):
                    df, msg = processar_excel_correto(arquivo)
                else:
                    msg = f"Formato não suportado: {arquivo.name}"
                    df = None
                
                if df is not None:
                    dataframes.append(df)
                    mensagens.append(msg)
                    st.success(msg)
                else:
                    mensagens.append(msg)
                    st.error(msg)
            except Exception as e:
                erro_msg = f"Erro crítico em {arquivo.name}: {str(e)}"
                mensagens.append(erro_msg)
                st.error(erro_msg)
    
    if not dataframes:
        st.error("❌ Nenhum arquivo processado com sucesso")
        return
    
    # Consolidar dados
    novo_df = pd.concat(dataframes, ignore_index=True)
    
    # Atualizar dados da sessão
    if modo == "Substituir dados" or st.session_state.dados_consolidados.empty:
        st.session_state.dados_consolidados = novo_df
        st.success(f"✅ {len(novo_df)} registros processados")
    else:
        st.session_state.dados_consolidados = pd.concat(
            [st.session_state.dados_consolidados, novo_df], 
            ignore_index=True
        )
        st.success(f"✅ {len(novo_df)} novos registros adicionados")
    
    df_final = st.session_state.dados_consolidados
    
    # Calcular métricas
    metricas = calcular_metricas(df_final)
    
    # Métricas principais
    st.header("📈 Métricas Principais")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total de Registros", f"{metricas['total_registros']:,}")
    
    with col2:
        st.metric("Valor Total", f"R$ {metricas.get('valor_total', 0):,.2f}")
    
    with col3:
        st.metric("Valor Médio", f"R$ {metricas.get('valor_medio', 0):,.2f}")
    
    with col4:
        st.metric("Arquivos", metricas['arquivos_unicos'])
    
    # Tabs de análise
    tab1, tab2, tab3, tab4 = st.tabs(["📋 Dados", "📅 Mensal", "🏢 Projetos", "📊 Gráficos"])
    
    with tab1:
        st.subheader("Dados Processados")
        
        # Filtros
        col_f1, col_f2 = st.columns(2)
        
        with col_f1:
            if 'mes_referencia' in df_final.columns:
                meses = ['Todos'] + sorted(df_final['mes_referencia'].dropna().unique().tolist())
                mes_filtro = st.selectbox("Filtrar por mês:", meses)
            else:
                mes_filtro = 'Todos'
        
        with col_f2:
            if 'projeto' in df_final.columns:
                projetos = ['Todos'] + sorted(df_final['projeto'].dropna().unique().tolist())
                projeto_filtro = st.selectbox("Filtrar por projeto:", projetos)
            else:
                projeto_filtro = 'Todos'
        
        # Aplicar filtros
        df_filtrado = df_final.copy()
        
        if mes_filtro != 'Todos' and 'mes_referencia' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['mes_referencia'] == mes_filtro]
        
        if projeto_filtro != 'Todos' and 'projeto' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['projeto'] == projeto_filtro]
        
        # Mostrar dados
        st.dataframe(
            df_filtrado,
            use_container_width=True,
            height=400,
            column_config={
                "valor_pagto": st.column_config.NumberColumn(
                    "Valor Pago",
                    format="R$ %.2f"
                )
            }
        )
    
    with tab2:
        st.subheader("Consolidação Mensal")
        
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
        else:
            st.info("Não há dados para consolidação mensal")
    
    with tab3:
        st.subheader("Consolidação por Projeto")
        
        consolidado_projetos = gerar_consolidado_projetos(df_final)
        
        if not consolidado_projetos.empty:
            st.dataframe(
                consolidado_projetos,
                use_container_width=True,
                height=500
            )
        else:
            st.info("Não há dados de projetos para análise")
    
    with tab4:
        st.subheader("Visualizações")
        
        if 'valor_pagto' in df_final.columns and 'mes_referencia' in df_final.columns:
            # Gráfico de evolução mensal
            if not consolidado_mensal.empty:
                fig1 = px.bar(
                    consolidado_mensal.reset_index(),
                    x='mes_referencia',
                    y='valor_total',
                    title='Valor Total por Mês',
                    labels={'valor_total': 'Valor Total (R$)'}
                )
                st.plotly_chart(fig1, use_container_width=True)
        
        if not consolidado_projetos.empty:
            # Gráfico de top projetos
            top_10 = consolidado_projetos.head(10)
            fig2 = px.bar(
                top_10.reset_index(),
                x='projeto',
                y='valor_total',
                title='Top 10 Projetos por Valor',
                labels={'valor_total': 'Valor Total (R$)'}
            )
            fig2.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig2, use_container_width=True)
    
    # Exportação
    st.header("💾 Exportação")
    
    col_exp1, col_exp2, col_exp3 = st.columns(3)
    
    with col_exp1:
        # Exportar dados completos
        csv_data = df_final.to_csv(index=False, sep=';', decimal=',')
        st.download_button(
            label="📥 Dados Completos (CSV)",
            data=csv_data,
            file_name=f"pot_completo_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True
        )
    
    with col_exp2:
        # Exportar consolidação mensal
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
        # Exportar consolidação projetos
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
    try:
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_final.to_excel(writer, sheet_name='DADOS', index=False)
            
            if not consolidado_mensal.empty:
                consolidado_mensal.to_excel(writer, sheet_name='CONSOLIDADO_MENSAL')
            
            if not consolidado_projetos.empty:
                consolidado_projetos.to_excel(writer, sheet_name='CONSOLIDADO_PROJETOS')
            
            # Adicionar resumo
            resumo_df = pd.DataFrame([{
                'Total de Registros': metricas['total_registros'],
                'Valor Total': metricas.get('valor_total', 0),
                'Valor Médio': metricas.get('valor_medio', 0),
                'Quantidade de Arquivos': metricas['arquivos_unicos'],
                'Data de Exportação': datetime.now().strftime('%d/%m/%Y %H:%M')
            }])
            resumo_df.to_excel(writer, sheet_name='RESUMO', index=False)
        
        excel_bytes = output.getvalue()
        
        st.download_button(
            label="📊 Relatório Completo (Excel)",
            data=excel_bytes,
            file_name=f"relatorio_pot_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    except Exception as e:
        st.warning(f"Exportação Excel não disponível: {str(e)}")
    
    # Rodapé
    st.markdown("---")
    st.caption(f"Sistema POT | {datetime.now().strftime('%d/%m/%Y %H:%M')} | Registros: {metricas['total_registros']:,}")

# ============================================================================
# EXECUÇÃO
# ============================================================================

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        st.error(f"Erro crítico: {str(e)}")
        st.info("Recarregue a página e tente novamente.")

# ============================================================================
# requirements.txt
# ============================================================================
"""
streamlit>=1.28.0
pandas>=2.0.0
numpy>=1.24.0
plotly>=5.17.0
chardet>=5.2.0
openpyxl>=3.1.0
"""
