# app.py - Sistema de Monitoramento de Pagamentos do POT
# VERSÃO 6.0 - SIMPLIFICADA E ESTÁVEL
# Mínimo de dependências, máximo de estabilidade

import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import re
from datetime import datetime

# Configuração da página Streamlit
st.set_page_config(
    page_title="Sistema POT - Monitoramento",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Título principal
st.title("📊 SISTEMA DE MONITORAMENTO DE PAGAMENTOS - POT")
st.markdown("---")

# ============================================================================
# FUNÇÕES BÁSICAS E ROBUSTAS
# ============================================================================

def limpar_valor_simples(valor):
    """Converte valores brasileiros para float de forma simples e segura"""
    if pd.isna(valor) or valor == '':
        return np.nan
    
    try:
        # Converter para string
        texto = str(valor).strip()
        
        # Remover R$ e espaços
        texto = texto.replace('R$', '').replace('$', '').strip()
        
        # Remover pontos de milhar
        if '.' in texto and ',' in texto:
            # Formato: 1.027,18 ou 272.486,06
            # Remover todos os pontos
            texto = texto.replace('.', '')
            # Substituir vírgula por ponto
            texto = texto.replace(',', '.')
        elif ',' in texto:
            # Formato: 1027,18
            texto = texto.replace(',', '.')
        
        # Converter para float
        return float(texto)
    
    except:
        return np.nan

def processar_arquivo_csv_robusto(arquivo):
    """Processa CSV de forma robusta e simples"""
    try:
        # Ler conteúdo
        conteudo = arquivo.getvalue().decode('utf-8-sig')
        
        # Substituir encoding problemático
        conteudo = conteudo.encode('utf-8', errors='ignore').decode('utf-8')
        
        # Remover linhas problemáticas
        linhas = conteudo.split('\n')
        linhas_validas = []
        
        for linha in linhas:
            linha = linha.strip()
            if linha:
                # Pular linhas que são apenas totais ou sumários
                if ';;;;' in linha and 'R$' in linha:
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
        
        # Criar DataFrame
        try:
            df = pd.read_csv(
                StringIO('\n'.join(linhas_validas)), 
                sep=sep, 
                dtype=str,
                on_bad_lines='skip'
            )
        except:
            # Tentar método manual para CSV problemático
            dados = []
            for linha in linhas_validas:
                dados.append(linha.split(sep))
            
            if len(dados) > 1:
                df = pd.DataFrame(dados[1:], columns=dados[0])
            else:
                return None, "Não foi possível ler o CSV"
        
        # Padronizar nomes das colunas
        df.columns = [str(col).strip().lower().replace(' ', '_') for col in df.columns]
        
        # Renomear colunas importantes
        mapeamento = {
            'projeto': 'projeto',
            'nome': 'nome',
            'valor_pagto': 'valor_pago',
            'valor_pagamento': 'valor_pago',
            'valorpagto': 'valor_pago',
            'data_pagto': 'data',
            'datapagto': 'data',
            'agencia': 'agencia',
            'agência': 'agencia'
        }
        
        for velho, novo in mapeamento.items():
            if velho in df.columns:
                df.rename(columns={velho: novo}, inplace=True)
        
        # Garantir coluna de valor
        if 'valor_pago' not in df.columns:
            # Procurar coluna que tenha 'valor' no nome
            colunas_valor = [col for col in df.columns if 'valor' in col.lower()]
            if colunas_valor:
                df['valor_pago'] = df[colunas_valor[0]]
            else:
                df['valor_pago'] = 0
        
        # Processar valores monetários
        if 'valor_pago' in df.columns:
            df['valor_pago'] = df['valor_pago'].apply(limpar_valor_simples)
        
        # Adicionar mês de referência do nome do arquivo
        nome_arquivo = arquivo.name.upper()
        meses = {
            'JAN': 'Janeiro', 'FEV': 'Fevereiro', 'MAR': 'Março',
            'ABR': 'Abril', 'MAI': 'Maio', 'JUN': 'Junho',
            'JUL': 'Julho', 'AGO': 'Agosto', 'SET': 'Setembro',
            'OUT': 'Outubro', 'NOV': 'Novembro', 'DEZ': 'Dezembro'
        }
        
        mes_referencia = 'Não identificado'
        for sigla, mes in meses.items():
            if sigla in nome_arquivo:
                mes_referencia = mes
                break
        
        df['mes_referencia'] = mes_referencia
        df['arquivo_origem'] = arquivo.name
        
        return df, f"✅ Processado: {len(df)} registros ({mes_referencia})"
    
    except Exception as e:
        return None, f"❌ Erro: {str(e)}"

def processar_arquivo_excel_robusto(arquivo):
    """Processa Excel de forma simples"""
    try:
        # Ler Excel
        df = pd.read_excel(arquivo, dtype=str)
        
        # Padronizar colunas
        df.columns = [str(col).strip().lower().replace(' ', '_') for col in df.columns]
        
        # Renomear colunas importantes
        mapeamento = {
            'projeto': 'projeto',
            'nome': 'nome',
            'valor_pagto': 'valor_pago',
            'data_pagto': 'data',
            'agencia': 'agencia'
        }
        
        for velho, novo in mapeamento.items():
            if velho in df.columns:
                df.rename(columns={velho: novo}, inplace=True)
        
        # Processar valores
        if 'valor_pago' in df.columns:
            df['valor_pago'] = df['valor_pago'].apply(limpar_valor_simples)
        
        # Adicionar informações
        df['mes_referencia'] = 'Excel'
        df['arquivo_origem'] = arquivo.name
        
        return df, f"✅ Excel processado: {len(df)} registros"
    
    except Exception as e:
        return None, f"❌ Erro no Excel: {str(e)}"

# ============================================================================
# FUNÇÕES DE ANÁLISE
# ============================================================================

def calcular_resumo(df):
    """Calcula resumo básico dos dados"""
    resumo = {
        'total_registros': len(df),
        'arquivos_unicos': df['arquivo_origem'].nunique() if 'arquivo_origem' in df.columns else 1,
        'meses_unicos': df['mes_referencia'].nunique() if 'mes_referencia' in df.columns else 1
    }
    
    if 'valor_pago' in df.columns:
        valores = df['valor_pago'].dropna()
        if len(valores) > 0:
            resumo['valor_total'] = float(valores.sum())
            resumo['valor_medio'] = float(valores.mean())
            resumo['valor_min'] = float(valores.min())
            resumo['valor_max'] = float(valores.max())
        else:
            resumo['valor_total'] = 0.0
            resumo['valor_medio'] = 0.0
    
    if 'projeto' in df.columns:
        resumo['projetos_unicos'] = df['projeto'].nunique()
    
    return resumo

def gerar_relatorio_mensal(df):
    """Gera relatório consolidado por mês"""
    if 'mes_referencia' not in df.columns or 'valor_pago' not in df.columns:
        return pd.DataFrame()
    
    try:
        relatorio = df.groupby('mes_referencia').agg(
            registros=('valor_pago', 'count'),
            valor_total=('valor_pago', 'sum'),
            valor_medio=('valor_pago', 'mean'),
            projetos=('projeto', 'nunique') if 'projeto' in df.columns else pd.Series([0])
        ).round(2)
        
        return relatorio.sort_values('valor_total', ascending=False)
    
    except:
        return pd.DataFrame()

def gerar_relatorio_projetos(df):
    """Gera relatório consolidado por projeto"""
    if 'projeto' not in df.columns or 'valor_pago' not in df.columns:
        return pd.DataFrame()
    
    try:
        relatorio = df.groupby('projeto').agg(
            registros=('valor_pago', 'count'),
            valor_total=('valor_pago', 'sum'),
            valor_medio=('valor_pago', 'mean'),
            meses=('mes_referencia', 'nunique') if 'mes_referencia' in df.columns else pd.Series([0])
        ).round(2)
        
        return relatorio.sort_values('valor_total', ascending=False)
    
    except:
        return pd.DataFrame()

# ============================================================================
# INTERFACE PRINCIPAL
# ============================================================================

def main():
    # Inicializar dados na sessão
    if 'dados' not in st.session_state:
        st.session_state.dados = pd.DataFrame()
    
    # Sidebar
    with st.sidebar:
        st.header("📁 CARREGAR ARQUIVOS")
        
        arquivos = st.file_uploader(
            "Selecione os arquivos",
            type=['csv', 'txt', 'xlsx', 'xls'],
            accept_multiple_files=True,
            help="Arquivos CSV, TXT ou Excel"
        )
        
        st.markdown("---")
        st.header("⚙️ OPÇÕES")
        
        modo = st.radio(
            "Modo de processamento:",
            ["Novo processamento", "Acumular dados"]
        )
        
        st.markdown("---")
        
        if not st.session_state.dados.empty:
            st.info(f"""
            **Dados atuais:**
            - Registros: {len(st.session_state.dados):,}
            - Valor total: R$ {st.session_state.dados['valor_pago'].sum():,.2f}
            - Arquivos: {st.session_state.dados['arquivo_origem'].nunique()}
            """)
            
            if st.button("🧹 Limpar Dados", use_container_width=True):
                st.session_state.dados = pd.DataFrame()
                st.rerun()
    
    # Área principal
    if not arquivos:
        # Tela inicial
        st.info("👋 **Bem-vindo ao Sistema POT - Versão Estável**")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown("""
            ### 📋 Como usar:
            
            1. **Carregue os arquivos** na barra lateral
               - CSV, TXT, Excel
               - Formato brasileiro (R$ 1.027,18)
            
            2. **Escolha o modo:**
               - Novo processamento (substitui)
               - Acumular dados (adiciona)
            
            3. **Analise os resultados:**
               - Totais gerais
               - Consolidação por mês
               - Consolidação por projeto
            
            4. **Exporte relatórios**
            
            ### 🛡️ Sistema Estável:
            
            ✅ **Mínimo de dependências**  
            ✅ **Processamento robusto**  
            ✅ **Tratamento de erros**  
            ✅ **Interface simples**  
            """)
        
        with col2:
            st.markdown("""
            ### 📊 Dados esperados:
            
            **Colunas importantes:**
            - Projeto
            - Nome
            - Valor Pago
            - Data
            - Agência
            
            **Formatos aceitos:**
            - R$ 1.027,18
            - 1027,18
            - 1027.18
            """)
        
        return
    
    # Processar arquivos
    st.subheader("🔄 Processando Arquivos")
    
    dados_processados = []
    mensagens = []
    
    for arquivo in arquivos:
        with st.spinner(f"Processando {arquivo.name}..."):
            if arquivo.name.lower().endswith(('.csv', '.txt')):
                df, msg = processar_arquivo_csv_robusto(arquivo)
            elif arquivo.name.lower().endswith(('.xlsx', '.xls')):
                df, msg = processar_arquivo_excel_robusto(arquivo)
            else:
                msg = f"❌ Formato não suportado: {arquivo.name}"
                df = None
            
            if df is not None:
                dados_processados.append(df)
                mensagens.append(f"✅ {msg}")
            else:
                mensagens.append(f"❌ {msg}")
    
    # Mostrar resultados
    for msg in mensagens:
        if "✅" in msg:
            st.success(msg)
        else:
            st.error(msg)
    
    if not dados_processados:
        st.error("Nenhum arquivo foi processado com sucesso.")
        return
    
    # Consolidar dados
    novo_df = pd.concat(dados_processados, ignore_index=True) if dados_processados else pd.DataFrame()
    
    # Atualizar dados da sessão
    if modo == "Novo processamento" or st.session_state.dados.empty:
        st.session_state.dados = novo_df
        st.success(f"✅ {len(novo_df)} registros processados")
    else:
        st.session_state.dados = pd.concat([st.session_state.dados, novo_df], ignore_index=True)
        st.success(f"✅ {len(novo_df)} novos registros adicionados. Total: {len(st.session_state.dados)}")
    
    df_final = st.session_state.dados
    
    # Calcular resumo
    st.subheader("📈 Resumo Geral")
    
    resumo = calcular_resumo(df_final)
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total de Registros", f"{resumo['total_registros']:,}")
    
    with col2:
        valor_total = resumo.get('valor_total', 0)
        st.metric("Valor Total", f"R$ {valor_total:,.2f}")
    
    with col3:
        valor_medio = resumo.get('valor_medio', 0)
        st.metric("Valor Médio", f"R$ {valor_medio:,.2f}")
    
    with col4:
        arquivos = resumo.get('arquivos_unicos', 0)
        st.metric("Arquivos", f"{arquivos}")
    
    # Tabs para análise
    tab1, tab2, tab3, tab4 = st.tabs(["📋 Dados", "📅 Por Mês", "🏢 Por Projeto", "💾 Exportar"])
    
    with tab1:
        st.subheader("Dados Processados")
        
        # Filtros simples
        if 'mes_referencia' in df_final.columns:
            meses = ['Todos'] + sorted(df_final['mes_referencia'].unique().tolist())
            mes_selecionado = st.selectbox("Filtrar por mês:", meses)
            
            if mes_selecionado != 'Todos':
                df_exibir = df_final[df_final['mes_referencia'] == mes_selecionado]
            else:
                df_exibir = df_final
        else:
            df_exibir = df_final
        
        # Mostrar dados
        st.dataframe(
            df_exibir,
            use_container_width=True,
            height=300,
            column_config={
                "valor_pago": st.column_config.NumberColumn(
                    "Valor Pago",
                    format="R$ %.2f"
                )
            }
        )
        
        st.info(f"Mostrando {len(df_exibir)} de {len(df_final)} registros")
    
    with tab2:
        st.subheader("Consolidação por Mês")
        
        relatorio_mensal = gerar_relatorio_mensal(df_final)
        
        if not relatorio_mensal.empty:
            st.dataframe(
                relatorio_mensal,
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
            
            # Gráfico simples
            try:
                import plotly.express as px
                
                fig = px.bar(
                    relatorio_mensal,
                    x=relatorio_mensal.index,
                    y='valor_total',
                    title='Valor Total por Mês',
                    labels={'valor_total': 'Valor Total (R$)'},
                    text=[f'R$ {x:,.0f}' for x in relatorio_mensal['valor_total']]
                )
                fig.update_traces(textposition='outside')
                st.plotly_chart(fig, use_container_width=True)
            except:
                st.info("Gráfico não disponível no momento")
        else:
            st.info("Não há dados suficientes para consolidação mensal")
    
    with tab3:
        st.subheader("Consolidação por Projeto")
        
        relatorio_projetos = gerar_relatorio_projetos(df_final)
        
        if not relatorio_projetos.empty:
            st.dataframe(
                relatorio_projetos.head(20),  # Limitar a 20 projetos
                use_container_width=True,
                height=400,
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
            
            # Gráfico simples
            try:
                import plotly.express as px
                
                top_10 = relatorio_projetos.head(10)
                fig = px.bar(
                    top_10,
                    x=top_10.index,
                    y='valor_total',
                    title='Top 10 Projetos',
                    labels={'valor_total': 'Valor Total (R$)'},
                    text=[f'R$ {x:,.0f}' for x in top_10['valor_total']]
                )
                fig.update_traces(textposition='outside')
                fig.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)
            except:
                st.info("Gráfico não disponível no momento")
        else:
            st.info("Não há dados de projetos para análise")
    
    with tab4:
        st.subheader("Exportação de Dados")
        
        col_exp1, col_exp2, col_exp3 = st.columns(3)
        
        with col_exp1:
            # Exportar dados brutos CSV
            csv_data = df_final.to_csv(index=False, sep=';', decimal=',')
            st.download_button(
                label="📥 Dados Completos (CSV)",
                data=csv_data,
                file_name=f"pot_dados_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col_exp2:
            # Exportar relatório mensal
            if not relatorio_mensal.empty:
                csv_mensal = relatorio_mensal.to_csv(sep=';', decimal=',')
                st.download_button(
                    label="📅 Relatório Mensal (CSV)",
                    data=csv_mensal,
                    file_name=f"pot_mensal_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        
        with col_exp3:
            # Exportar relatório de projetos
            if not relatorio_projetos.empty:
                csv_projetos = relatorio_projetos.to_csv(sep=';', decimal=',')
                st.download_button(
                    label="🏢 Relatório Projetos (CSV)",
                    data=csv_projetos,
                    file_name=f"pot_projetos_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        
        # Exportar tudo em Excel (se possível)
        try:
            from io import BytesIO
            import openpyxl
            
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_final.to_excel(writer, sheet_name='DADOS', index=False)
                if not relatorio_mensal.empty:
                    relatorio_mensal.to_excel(writer, sheet_name='MENSAL')
                if not relatorio_projetos.empty:
                    relatorio_projetos.to_excel(writer, sheet_name='PROJETOS')
            
            excel_bytes = output.getvalue()
            
            st.download_button(
                label="📊 Relatório Completo (Excel)",
                data=excel_bytes,
                file_name=f"pot_completo_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        except:
            st.info("Exportação em Excel não disponível")
    
    # Rodapé
    st.markdown("---")
    st.caption(f"""
    ⚙️ Sistema POT - Versão Estável 6.0 | 
    Data: {datetime.now().strftime('%d/%m/%Y %H:%M')} | 
    Registros: {len(df_final):,}
    """)

# ============================================================================
# EXECUTAR APLICAÇÃO
# ============================================================================
if __name__ == "__main__":
    # Importação condicional para evitar erros
    try:
        from io import StringIO
    except:
        st.error("Erro de importação. Recarregue a página.")
    
    main()# app.py - Sistema de Monitoramento de Pagamentos do POT
# VERSÃO 5.0 - COMPLETA COM MULTIPLOS ARQUIVOS E CONSOLIDAÇÃO
# Funcionalidades:
# 1. Processamento de múltiplos arquivos (CSV, TXT, Excel)
# 2. Consolidação mensal dos pagamentos
# 3. Análise por projeto
# 4. Armazenamento em sessão para análise temporal
# 5. Relatórios consolidados

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
import os
from pathlib import Path
import tempfile
import zipfile

# Configurar warnings
warnings.filterwarnings('ignore')

# Configuração da página Streamlit
st.set_page_config(
    page_title="Sistema POT - Monitoramento Consolidado",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Título principal
st.title("📊 SISTEMA DE MONITORAMENTO DE PAGAMENTOS - POT")
st.subheader("Consolidação Mensal e Análise por Projeto")
st.markdown("---")

# ============================================================================
# INICIALIZAÇÃO DE SESSÃO
# ============================================================================

def inicializar_sessao():
    """Inicializa variáveis de sessão se não existirem"""
    if 'dados_consolidados' not in st.session_state:
        st.session_state.dados_consolidados = pd.DataFrame()
    
    if 'arquivos_processados' not in st.session_state:
        st.session_state.arquivos_processados = []
    
    if 'historico_mensal' not in st.session_state:
        st.session_state.historico_mensal = pd.DataFrame()
    
    if 'projetos_consolidados' not in st.session_state:
        st.session_state.projetos_consolidados = pd.DataFrame()

# ============================================================================
# FUNÇÕES DE PROCESSAMENTO DE DADOS
# ============================================================================

def limpar_valor_monetario(valor):
    """
    Converte valores no formato brasileiro para float
    Suporta: R$ 1.027,18 | 1.027,18 | 1027,18 | 1027.18
    """
    if pd.isna(valor) or valor == '' or str(valor).strip() in ['nan', 'None', 'NaT', 'NULL', 'null', 'NaN', 'N/A']:
        return np.nan
    
    try:
        str_valor = str(valor).strip()
        
        # Remover R$, espaços e aspas
        str_valor = re.sub(r'^R\$\s*', '', str_valor)
        str_valor = re.sub(r'[R\$\s\'\"]', '', str_valor)
        
        if str_valor == '':
            return np.nan
        
        # Se já é número (float ou int)
        if isinstance(valor, (int, float)):
            return float(valor)
        
        # Formato brasileiro: 1.027,18 ou 272.486,06
        if ',' in str_valor:
            if '.' in str_valor:
                # Formato com separadores de milhar e decimal
                # Contar dígitos após vírgula
                partes = str_valor.split(',')
                if len(partes) == 2 and len(partes[1]) <= 2:
                    # Remover pontos de milhar, manter vírgula decimal
                    valor_sem_milhar = str_valor.replace('.', '')
                    valor_final = valor_sem_milhar.replace(',', '.')
                    return float(valor_final)
            else:
                # Apenas vírgula decimal, sem pontos de milhar
                valor_final = str_valor.replace(',', '.')
                return float(valor_final)
        
        # Formato internacional ou apenas números
        if '.' in str_valor:
            # Se tem múltiplos pontos, pode ser milhar.internacional
            if str_valor.count('.') > 1:
                # Verificar se último ponto tem 2-3 dígitos após
                ultimo_ponto = str_valor.rfind('.')
                digitos_apos = len(str_valor) - ultimo_ponto - 1
                if digitos_apos in [2, 3]:
                    # Provavelmente formato internacional com decimal
                    parte_inteira = str_valor[:ultimo_ponto].replace('.', '')
                    parte_decimal = str_valor[ultimo_ponto+1:]
                    valor_final = parte_inteira + '.' + parte_decimal
                    return float(valor_final)
            return float(str_valor)
        
        # Apenas números inteiros
        if str_valor.replace('.', '', 1).isdigit():
            return float(str_valor)
        
        # Tentar extrair números
        numeros = re.findall(r'[\d,\.]+', str_valor)
        if numeros:
            primeiro_num = numeros[0]
            if ',' in primeiro_num:
                primeiro_num = primeiro_num.replace('.', '').replace(',', '.')
            return float(primeiro_num)
        
        return np.nan
        
    except Exception:
        return np.nan

def extrair_mes_referencia(nome_arquivo, df):
    """
    Extrai o mês de referência do arquivo
    Ordem de prioridade:
    1. Coluna 'mes_referencia' no DataFrame
    2. Coluna 'data_pagto' no DataFrame
    3. Nome do arquivo (ex: SETEMBRO, OUTUBRO, etc.)
    4. Data de modificação do arquivo
    """
    meses_ptbr = {
        'JANEIRO': 1, 'FEVEREIRO': 2, 'MARÇO': 3, 'MARCO': 3,
        'ABRIL': 4, 'MAIO': 5, 'JUNHO': 6, 'JULHO': 7,
        'AGOSTO': 8, 'SETEMBRO': 9, 'OUTUBRO': 10,
        'NOVEMBRO': 11, 'DEZEMBRO': 12
    }
    
    # 1. Verificar coluna 'mes_referencia' no DataFrame
    if 'mes_referencia' in df.columns:
        primeiro_valor = df['mes_referencia'].dropna().iloc[0] if len(df['mes_referencia'].dropna()) > 0 else None
        if primeiro_valor:
            try:
                if isinstance(primeiro_valor, str):
                    for mes_nome, mes_num in meses_ptbr.items():
                        if mes_nome in primeiro_valor.upper():
                            return mes_num, mes_nome.capitalize()
                
                # Tentar converter data
                data_ref = pd.to_datetime(primeiro_valor, errors='coerce')
                if pd.notna(data_ref):
                    return data_ref.month, data_ref.strftime('%B').upper()
            except:
                pass
    
    # 2. Verificar coluna 'data_pagto'
    if 'data_pagto' in df.columns:
        datas_validas = df['data_pagto'].dropna()
        if len(datas_validas) > 0:
            try:
                # Converter para datetime
                datas_dt = pd.to_datetime(datas_validas, errors='coerce', dayfirst=True)
                datas_dt = datas_dt.dropna()
                if len(datas_dt) > 0:
                    mes_comum = datas_dt.iloc[0].month
                    mes_nome = datas_dt.iloc[0].strftime('%B').upper()
                    return mes_comum, mes_nome
            except:
                pass
    
    # 3. Extrair do nome do arquivo
    nome_upper = nome_arquivo.upper()
    for mes_nome, mes_num in meses_ptbr.items():
        if mes_nome in nome_upper:
            return mes_num, mes_nome.capitalize()
    
    # 4. Data atual como fallback
    mes_atual = datetime.now().month
    mes_nome_atual = datetime.now().strftime('%B').upper()
    return mes_atual, mes_nome_atual

def processar_arquivo_csv(uploaded_file):
    """Processa arquivo CSV específico do POT"""
    try:
        # Ler conteúdo
        raw_data = uploaded_file.getvalue()
        
        # Tentar diferentes encodings
        encodings = ['utf-8-sig', 'latin-1', 'cp1252', 'utf-8', 'iso-8859-1']
        content = None
        
        for encoding in encodings:
            try:
                content = raw_data.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        
        if content is None:
            return None, "❌ Não foi possível decodificar o arquivo"
        
        # Remover BOM se existir
        content = content.lstrip('\ufeff')
        
        # Detectar delimitador
        first_lines = content.split('\n', 10)
        for line in first_lines:
            if ';' in line and line.count(';') > line.count(','):
                delimiter = ';'
                break
            elif ',' in line:
                delimiter = ','
                break
        else:
            delimiter = ';'  # Padrão
        
        # Ler CSV manualmente para controle
        reader = csv.reader(StringIO(content), delimiter=delimiter)
        rows = list(reader)
        
        if len(rows) < 2:
            return None, "❌ Arquivo vazio ou sem dados válidos"
        
        # Remover linhas que são totais (muitos campos vazios no início)
        rows_validos = []
        for row in rows:
            if len(row) > 5:
                # Contar campos não vazios nos primeiros 5
                campos_preenchidos = sum(1 for campo in row[:5] if str(campo).strip() not in ['', 'nan', 'NaN', 'None'])
                if campos_preenchidos >= 3:  # Pelo menos 3 campos preenchidos
                    # Verificar se não é linha de total
                    if not any('R$' in str(campo) and ';' * 10 in str(campo) for campo in row):
                        rows_validos.append(row)
        
        if len(rows_validos) < 2:
            return None, "❌ Não há dados suficientes após limpeza"
        
        # Criar DataFrame
        headers = [str(h).strip().lower() for h in rows_validos[0]]
        data_rows = rows_validos[1:]
        
        # Garantir que todas as linhas tenham o mesmo número de colunas
        max_cols = len(headers)
        data_rows_padded = []
        for row in data_rows:
            if len(row) < max_cols:
                row = row + [''] * (max_cols - len(row))
            elif len(row) > max_cols:
                row = row[:max_cols]
            data_rows_padded.append(row)
        
        df = pd.DataFrame(data_rows_padded, columns=headers)
        
        # Padronizar nomes de colunas
        mapeamento = {
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
            'data pagto': 'data_pagto',
            'valor dia': 'valor_dia',
            'dias validos': 'dias_apagar',
            'dias a pagar': 'dias_apagar',
            'dias': 'dias_apagar',
            'gerenciadora': 'gerenciadora',
            'mes referencia': 'mes_referencia',
            'mes': 'mes_referencia',
            'referencia': 'mes_referencia'
        }
        
        for old_name, new_name in mapeamento.items():
            if old_name in df.columns:
                df = df.rename(columns={old_name: new_name})
        
        # Processar colunas monetárias
        colunas_monetarias = ['valor_total', 'valor_desconto', 'valor_pagto', 'valor_dia']
        for col in colunas_monetarias:
            if col in df.columns:
                df[col] = df[col].apply(limpar_valor_monetario)
        
        # Processar colunas numéricas
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
            df['gerenciadora'] = df['gerenciadora'].replace({
                'REDE CIDAD�': 'REDE CIDADÃO',
                'REDE CIDADAO': 'REDE CIDADÃO',
                'REDE': 'REDE CIDADÃO',
                'VISTA': 'VISTA',
                '': 'NÃO INFORMADO',
                'NAN': 'NÃO INFORMADO',
                'NONE': 'NÃO INFORMADO'
            })
        
        # Limpar strings
        colunas_texto = ['nome', 'projeto', 'agencia', 'rg', 'cartao', 'cpf']
        for col in colunas_texto:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
                df[col] = df[col].replace(['nan', 'None', 'NaT', 'NULL', 'null', 'NaN'], '')
        
        # Adicionar coluna com nome do arquivo original
        df['arquivo_origem'] = uploaded_file.name
        
        # Extrair mês de referência
        mes_num, mes_nome = extrair_mes_referencia(uploaded_file.name, df)
        df['mes_numero'] = mes_num
        df['mes_nome'] = mes_nome
        df['ano'] = datetime.now().year
        
        return df, f"✅ Arquivo processado: {len(df)} registros (Mês: {mes_nome})"
    
    except Exception as e:
        return None, f"❌ Erro ao processar CSV: {str(e)}"

def processar_arquivo_excel(uploaded_file):
    """Processa arquivo Excel"""
    try:
        # Ler todas as abas
        xls = pd.ExcelFile(uploaded_file)
        
        # Procurar aba com dados
        sheet_names = xls.sheet_names
        df_final = None
        
        for sheet in sheet_names:
            try:
                df = pd.read_excel(xls, sheet_name=sheet, dtype=str)
                
                # Verificar se tem dados mínimos
                if len(df) > 0 and len(df.columns) >= 5:
                    df_final = df
                    break
            except:
                continue
        
        if df_final is None:
            return None, "❌ Nenhuma aba com dados válidos encontrada"
        
        # Processar colunas (similar ao CSV)
        df_final.columns = [str(col).strip().lower() for col in df_final.columns]
        
        # Padronizar nomes de colunas
        mapeamento = {
            'ordem': 'ordem',
            'projeto': 'projeto',
            'num cartao': 'cartao',
            'cartão': 'cartao',
            'nome': 'nome',
            'agencia': 'agencia',
            'valor total': 'valor_total',
            'valor pagto': 'valor_pagto',
            'data pagto': 'data_pagto',
            'gerenciadora': 'gerenciadora'
        }
        
        for old_name, new_name in mapeamento.items():
            if old_name in df_final.columns:
                df_final = df_final.rename(columns={old_name: new_name})
        
        # Processar colunas monetárias
        colunas_monetarias = ['valor_total', 'valor_pagto']
        for col in colunas_monetarias:
            if col in df_final.columns:
                df_final[col] = df_final[col].apply(limpar_valor_monetario)
        
        # Adicionar coluna com nome do arquivo
        df_final['arquivo_origem'] = uploaded_file.name
        
        # Extrair mês de referência
        mes_num, mes_nome = extrair_mes_referencia(uploaded_file.name, df_final)
        df_final['mes_numero'] = mes_num
        df_final['mes_nome'] = mes_nome
        df_final['ano'] = datetime.now().year
        
        return df_final, f"✅ Excel processado: {len(df_final)} registros (Mês: {mes_nome})"
    
    except Exception as e:
        return None, f"❌ Erro ao processar Excel: {str(e)}"

def processar_multiplos_arquivos(uploaded_files):
    """Processa múltiplos arquivos e consolida os dados"""
    todos_dados = []
    resultados = []
    
    for uploaded_file in uploaded_files:
        try:
            nome_arquivo = uploaded_file.name.lower()
            
            if nome_arquivo.endswith(('.csv', '.txt')):
                df, mensagem = processar_arquivo_csv(uploaded_file)
            elif nome_arquivo.endswith(('.xlsx', '.xls')):
                df, mensagem = processar_arquivo_excel(uploaded_file)
            else:
                resultados.append(f"❌ Formato não suportado: {uploaded_file.name}")
                continue
            
            if df is not None:
                todos_dados.append(df)
                resultados.append(mensagem)
            else:
                resultados.append(f"❌ Falha: {uploaded_file.name} - {mensagem}")
        
        except Exception as e:
            resultados.append(f"❌ Erro em {uploaded_file.name}: {str(e)}")
    
    if todos_dados:
        # Consolidar todos os DataFrames
        dados_consolidados = pd.concat(todos_dados, ignore_index=True)
        
        # Garantir colunas essenciais
        colunas_essenciais = ['projeto', 'valor_pagto', 'mes_nome', 'mes_numero', 'ano', 'arquivo_origem']
        for col in colunas_essenciais:
            if col not in dados_consolidados.columns:
                if col == 'projeto':
                    dados_consolidados['projeto'] = 'NÃO INFORMADO'
                elif col == 'valor_pagto':
                    dados_consolidados['valor_pagto'] = 0.0
        
        return dados_consolidados, resultados
    else:
        return pd.DataFrame(), resultados

# ============================================================================
# FUNÇÕES DE ANÁLISE E CONSOLIDAÇÃO
# ============================================================================

def calcular_consolidado_mensal(df):
    """Calcula consolidação mensal dos pagamentos"""
    if df.empty:
        return pd.DataFrame()
    
    try:
        # Agrupar por mês e ano
        if 'mes_nome' in df.columns and 'ano' in df.columns:
            # Criar coluna de período
            df['periodo'] = df['mes_nome'] + '/' + df['ano'].astype(str)
            
            # Agrupar por período
            consolidado = df.groupby('periodo').agg(
                quantidade_pagamentos=('valor_pagto', 'count'),
                valor_total=('valor_pagto', 'sum'),
                valor_medio=('valor_pagto', 'mean'),
                quantidade_projetos=('projeto', lambda x: x.nunique()),
                quantidade_agencias=('agencia', lambda x: x.nunique() if 'agencia' in df.columns else 0),
                arquivos=('arquivo_origem', lambda x: ', '.join(x.unique()[:3]))
            ).round(2)
            
            # Ordenar por período
            consolidado = consolidado.sort_index()
            
            return consolidado
        
        else:
            # Se não tem mês/ano, agrupar por arquivo
            consolidado = df.groupby('arquivo_origem').agg(
                quantidade_pagamentos=('valor_pagto', 'count'),
                valor_total=('valor_pagto', 'sum'),
                valor_medio=('valor_pagto', 'mean')
            ).round(2)
            
            return consolidado
    
    except Exception as e:
        st.error(f"Erro no cálculo mensal: {e}")
        return pd.DataFrame()

def calcular_consolidado_projetos(df):
    """Calcula consolidação por projeto"""
    if df.empty:
        return pd.DataFrame()
    
    try:
        if 'projeto' in df.columns:
            # Agrupar por projeto
            por_projeto = df.groupby('projeto').agg(
                quantidade_pagamentos=('valor_pagto', 'count'),
                valor_total=('valor_pagto', 'sum'),
                valor_medio=('valor_pagto', 'mean'),
                quantidade_meses=('mes_nome', lambda x: x.nunique() if 'mes_nome' in df.columns else 1),
                quantidade_beneficiarios=('nome', lambda x: x.nunique() if 'nome' in df.columns else 0),
                primeira_data=('data_pagto', 'min') if 'data_pagto' in df.columns else None,
                ultima_data=('data_pagto', 'max') if 'data_pagto' in df.columns else None
            ).round(2)
            
            # Remover agregações que deram None
            por_projeto = por_projeto.dropna(axis=1, how='all')
            
            # Ordenar por valor total
            por_projeto = por_projeto.sort_values('valor_total', ascending=False)
            
            return por_projeto
        else:
            return pd.DataFrame()
    
    except Exception as e:
        st.error(f"Erro no cálculo por projeto: {e}")
        return pd.DataFrame()

def calcular_estatisticas_detalhadas(df):
    """Calcula estatísticas detalhadas dos dados consolidados"""
    estatisticas = {}
    
    if df.empty:
        return estatisticas
    
    try:
        # Estatísticas gerais
        estatisticas['total_registros'] = len(df)
        estatisticas['total_arquivos'] = df['arquivo_origem'].nunique() if 'arquivo_origem' in df.columns else 1
        
        if 'valor_pagto' in df.columns:
            valores = df['valor_pagto'].dropna()
            if len(valores) > 0:
                estatisticas['valor_total'] = float(valores.sum())
                estatisticas['valor_medio'] = float(valores.mean())
                estatisticas['valor_min'] = float(valores.min())
                estatisticas['valor_max'] = float(valores.max())
                estatisticas['desvio_padrao'] = float(valores.std())
                estatisticas['quantidade_valores_validos'] = len(valores)
        
        # Estatísticas por mês
        if 'mes_nome' in df.columns and 'ano' in df.columns:
            meses_unicos = df[['mes_nome', 'ano']].drop_duplicates()
            estatisticas['quantidade_meses'] = len(meses_unicos)
            estatisticas['meses'] = [f"{row['mes_nome']}/{row['ano']}" for _, row in meses_unicos.iterrows()]
        
        # Estatísticas por projeto
        if 'projeto' in df.columns:
            projetos_unicos = df['projeto'].nunique()
            estatisticas['quantidade_projetos'] = projetos_unicos
        
        # Estatísticas por agência
        if 'agencia' in df.columns:
            agencias_unicas = df['agencia'].nunique()
            estatisticas['quantidade_agencias'] = agencias_unicas
        
        # Estatísticas por gerenciadora
        if 'gerenciadora' in df.columns:
            gerenciadoras = df['gerenciadora'].value_counts().to_dict()
            estatisticas['gerenciadoras'] = gerenciadoras
        
        return estatisticas
    
    except Exception as e:
        st.error(f"Erro nas estatísticas: {e}")
        return estatisticas

# ============================================================================
# FUNÇÕES DE VISUALIZAÇÃO
# ============================================================================

def criar_grafico_evolucao_mensal(consolidado_mensal):
    """Cria gráfico de evolução mensal dos pagamentos"""
    if consolidado_mensal.empty:
        return None
    
    try:
        fig = go.Figure()
        
        # Adicionar barras para valor total
        fig.add_trace(go.Bar(
            x=consolidado_mensal.index,
            y=consolidado_mensal['valor_total'],
            name='Valor Total',
            marker_color='#2E86AB',
            text=[f'R$ {x:,.0f}' for x in consolidado_mensal['valor_total']],
            textposition='auto'
        ))
        
        # Adicionar linha para quantidade de pagamentos (eixo secundário)
        fig.add_trace(go.Scatter(
            x=consolidado_mensal.index,
            y=consolidado_mensal['quantidade_pagamentos'],
            name='Quantidade',
            yaxis='y2',
            mode='lines+markers',
            line=dict(color='#FF6B6B', width=3),
            marker=dict(size=8)
        ))
        
        fig.update_layout(
            title='Evolução Mensal dos Pagamentos',
            xaxis_title='Período',
            yaxis_title='Valor Total (R$)',
            yaxis2=dict(
                title='Quantidade de Pagamentos',
                overlaying='y',
                side='right'
            ),
            hovermode='x unified',
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )
        
        return fig
    
    except Exception as e:
        st.error(f"Erro no gráfico de evolução: {e}")
        return None

def criar_grafico_projetos(consolidado_projetos):
    """Cria gráfico de barras dos projetos"""
    if consolidado_projetos.empty:
        return None
    
    try:
        # Pegar top 10 projetos por valor total
        top_projetos = consolidado_projetos.head(10)
        
        fig = px.bar(
            top_projetos,
            x=top_projetos.index,
            y='valor_total',
            title='Top 10 Projetos por Valor Total',
            labels={'valor_total': 'Valor Total (R$)', 'index': 'Projeto'},
            text=[f'R$ {x:,.0f}' for x in top_projetos['valor_total']],
            color='valor_total',
            color_continuous_scale='Viridis'
        )
        
        fig.update_layout(
            xaxis_tickangle=-45,
            showlegend=False,
            coloraxis_showscale=False
        )
        
        fig.update_traces(texttemplate='%{text}', textposition='outside')
        
        return fig
    
    except Exception as e:
        st.error(f"Erro no gráfico de projetos: {e}")
        return None

def criar_grafico_distribuicao_mensal(df):
    """Cria gráfico de distribuição por mês"""
    if df.empty or 'mes_nome' not in df.columns:
        return None
    
    try:
        # Agrupar por mês para distribuição
        por_mes = df.groupby('mes_nome').agg(
            quantidade=('valor_pagto', 'count'),
            valor_total=('valor_pagto', 'sum')
        ).round(2)
        
        # Ordenar por mês
        ordem_meses = ['JANEIRO', 'FEVEREIRO', 'MARÇO', 'ABRIL', 'MAIO', 'JUNHO',
                      'JULHO', 'AGOSTO', 'SETEMBRO', 'OUTUBRO', 'NOVEMBRO', 'DEZEMBRO']
        
        por_mes = por_mes.reindex([m for m in ordem_meses if m in por_mes.index])
        
        fig = go.Figure()
        
        fig.add_trace(go.Bar(
            x=por_mes.index,
            y=por_mes['quantidade'],
            name='Quantidade',
            marker_color='#4ECDC4',
            yaxis='y'
        ))
        
        fig.add_trace(go.Scatter(
            x=por_mes.index,
            y=por_mes['valor_total'],
            name='Valor Total',
            yaxis='y2',
            mode='lines+markers',
            line=dict(color='#FF6B6B', width=3),
            marker=dict(size=8)
        ))
        
        fig.update_layout(
            title='Distribuição por Mês',
            xaxis_title='Mês',
            yaxis=dict(title='Quantidade'),
            yaxis2=dict(
                title='Valor Total (R$)',
                overlaying='y',
                side='right'
            ),
            hovermode='x unified'
        )
        
        return fig
    
    except Exception as e:
        st.error(f"Erro no gráfico de distribuição: {e}")
        return None

# ============================================================================
# FUNÇÕES DE EXPORTAÇÃO
# ============================================================================

def exportar_dados_completos(df, consolidado_mensal, consolidado_projetos):
    """Exporta todos os dados para Excel"""
    try:
        output = BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Dados brutos consolidados
            df.to_excel(writer, sheet_name='DADOS_CONSOLIDADOS', index=False)
            
            # Consolidação mensal
            if not consolidado_mensal.empty:
                consolidado_mensal.to_excel(writer, sheet_name='CONSOLIDADO_MENSAL')
            
            # Consolidação por projeto
            if not consolidado_projetos.empty:
                consolidado_projetos.to_excel(writer, sheet_name='CONSOLIDADO_PROJETOS')
            
            # Estatísticas
            estatisticas = calcular_estatisticas_detalhadas(df)
            if estatisticas:
                df_estat = pd.DataFrame(list(estatisticas.items()), columns=['Metrica', 'Valor'])
                df_estat.to_excel(writer, sheet_name='ESTATISTICAS', index=False)
            
            # Resumo executivo
            resumo_data = {
                'Total de Registros': [estatisticas.get('total_registros', 0)],
                'Valor Total': [f"R$ {estatisticas.get('valor_total', 0):,.2f}"],
                'Quantidade de Meses': [estatisticas.get('quantidade_meses', 0)],
                'Quantidade de Projetos': [estatisticas.get('quantidade_projetos', 0)],
                'Quantidade de Arquivos': [estatisticas.get('total_arquivos', 0)],
                'Data de Geração': [datetime.now().strftime('%d/%m/%Y %H:%M')]
            }
            df_resumo = pd.DataFrame(resumo_data)
            df_resumo.to_excel(writer, sheet_name='RESUMO_EXECUTIVO', index=False)
        
        excel_bytes = output.getvalue()
        
        return excel_bytes
    
    except Exception as e:
        st.error(f"Erro na exportação: {e}")
        return None

# ============================================================================
# INTERFACE PRINCIPAL
# ============================================================================

def main():
    # Inicializar sessão
    inicializar_sessao()
    
    # ========================================================================
    # SIDEBAR
    # ========================================================================
    with st.sidebar:
        st.image("https://cdn-icons-png.flaticon.com/512/3067/3067256.png", width=100)
        st.header("📁 CARREGAMENTO DE DADOS")
        
        uploaded_files = st.file_uploader(
            "Selecione os arquivos para processar",
            type=['csv', 'txt', 'xlsx', 'xls'],
            accept_multiple_files=True,
            help="Você pode selecionar múltiplos arquivos de uma vez"
        )
        
        st.markdown("---")
        
        st.header("⚙️ CONFIGURAÇÕES")
        
        modo_processamento = st.radio(
            "Modo de processamento:",
            ["Adicionar aos dados existentes", "Substituir dados existentes"]
        )
        
        st.markdown("---")
        
        st.header("📊 VISUALIZAÇÕES")
        
        mostrar_graficos = st.checkbox("Mostrar gráficos", True)
        mostrar_detalhes = st.checkbox("Mostrar detalhes dos dados", False)
        
        st.markdown("---")
        
        st.header("📈 STATUS ATUAL")
        
        if not st.session_state.dados_consolidados.empty:
            st.success(f"✅ Dados carregados:")
            st.info(f"""
            - Registros: {len(st.session_state.dados_consolidados):,}
            - Arquivos: {len(st.session_state.arquivos_processados)}
            - Valor total: R$ {st.session_state.dados_consolidados['valor_pagto'].sum():,.2f}
            """)
        else:
            st.warning("⚠️ Nenhum dado carregado ainda")
    
    # ========================================================================
    # ÁREA PRINCIPAL
    # ========================================================================
    
    if not uploaded_files:
        # Tela inicial
        st.info("👋 **Bem-vindo ao Sistema de Consolidação de Pagamentos - POT**")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown("""
            ### 📋 Funcionalidades Principais:
            
            1. **Processamento de múltiplos arquivos**
               - CSV, TXT, Excel
               - Formatos brasileiros (R$ 1.027,18)
               - Detecção automática de mês de referência
            
            2. **Consolidação Inteligente**
               - Agrupamento por mês
               - Análise por projeto
               - Histórico temporal
            
            3. **Análise Avançada**
               - Estatísticas detalhadas
               - Gráficos interativos
               - Detecção de inconsistências
            
            4. **Exportação Completa**
               - Relatórios em Excel
               - Dados consolidados
               - Gráficos e métricas
            
            ### 🎯 Instruções:
            
            1. **Carregue os arquivos** na barra lateral
            2. **Configure o modo** de processamento
            3. **Analise os resultados** consolidados
            4. **Exporte relatórios** conforme necessário
            """)
        
        with col2:
            st.markdown("""
            ### 📁 Formatos Suportados:
            
            **CSV/TXT:**
            - Separador: ; ou ,
            - Encoding: UTF-8, Latin-1
            - Formato: R$ 1.027,18
            
            **Excel:**
            - .xlsx, .xls
            - Múltiplas abas
            
            ### 🔧 Processamento:
            
            ✅ **Validação automática**
            ✅ **Consolidação por mês**
            ✅ **Análise por projeto**
            ✅ **Armazenamento em sessão**
            ✅ **Exportação completa**
            """)
        
        # Exibir histórico se existir
        if not st.session_state.historico_mensal.empty:
            st.markdown("---")
            st.subheader("📊 Histórico Carregado")
            st.dataframe(st.session_state.historico_mensal, use_container_width=True)
        
        return
    
    # ========================================================================
    # PROCESSAMENTO DOS ARQUIVOS
    # ========================================================================
    st.subheader("🔄 Processamento dos Arquivos")
    
    with st.spinner(f'Processando {len(uploaded_files)} arquivo(s)...'):
        dados_consolidados, resultados = processar_multiplos_arquivos(uploaded_files)
    
    # Mostrar resultados do processamento
    for resultado in resultados:
        if resultado.startswith("✅"):
            st.success(resultado)
        elif resultado.startswith("❌"):
            st.error(resultado)
        else:
            st.info(resultado)
    
    if dados_consolidados.empty:
        st.error("❌ Nenhum dado válido foi processado")
        return
    
    # ========================================================================
    # CONSOLIDAÇÃO COM DADOS EXISTENTES
    # ========================================================================
    if modo_processamento == "Adicionar aos dados existentes" and not st.session_state.dados_consolidados.empty:
        # Combinar com dados existentes
        dados_finais = pd.concat([st.session_state.dados_consolidados, dados_consolidados], ignore_index=True)
        
        # Remover duplicatas (baseado em combinação de campos únicos)
        campos_unicos = ['nome', 'valor_pagto', 'data_pagto', 'projeto', 'arquivo_origem']
        campos_disponiveis = [campo for campo in campos_unicos if campo in dados_finais.columns]
        
        if len(campos_disponiveis) >= 2:
            dados_finais = dados_finais.drop_duplicates(subset=campos_disponiveis[:2])
        
        st.success(f"✅ Dados adicionados. Total: {len(dados_finais):,} registros")
    else:
        dados_finais = dados_consolidados
        st.success(f"✅ {len(dados_finais):,} registros processados")
    
    # Atualizar sessão
    st.session_state.dados_consolidados = dados_finais
    
    # Adicionar aos arquivos processados
    novos_arquivos = [f.name for f in uploaded_files]
    st.session_state.arquivos_processados.extend(novos_arquivos)
    st.session_state.arquivos_processados = list(set(st.session_state.arquivos_processados))
    
    # ========================================================================
    # CÁLCULOS CONSOLIDADOS
    # ========================================================================
    st.subheader("📈 Análise Consolidada")
    
    # Calcular consolidações
    consolidado_mensal = calcular_consolidado_mensal(dados_finais)
    consolidado_projetos = calcular_consolidado_projetos(dados_finais)
    estatisticas = calcular_estatisticas_detalhadas(dados_finais)
    
    # Atualizar histórico
    st.session_state.historico_mensal = consolidado_mensal
    st.session_state.projetos_consolidados = consolidado_projetos
    
    # ========================================================================
    # MÉTRICAS PRINCIPAIS
    # ========================================================================
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_registros = estatisticas.get('total_registros', 0)
        st.metric("📊 Total de Registros", f"{total_registros:,}")
    
    with col2:
        valor_total = estatisticas.get('valor_total', 0)
        st.metric("💰 Valor Total", f"R$ {valor_total:,.2f}")
    
    with col3:
        qtd_meses = estatisticas.get('quantidade_meses', 0)
        st.metric("📅 Meses", f"{qtd_meses}")
    
    with col4:
        qtd_projetos = estatisticas.get('quantidade_projetos', 0)
        st.metric("🏢 Projetos", f"{qtd_projetos}")
    
    # ========================================================================
    # VISUALIZAÇÃO DOS DADOS
    # ========================================================================
    tab1, tab2, tab3, tab4 = st.tabs(["📋 Dados", "📅 Mensal", "🏢 Projetos", "📊 Gráficos"])
    
    with tab1:
        st.subheader("Dados Consolidados")
        
        # Filtros
        col_filtro1, col_filtro2, col_filtro3 = st.columns(3)
        
        with col_filtro1:
            if 'projeto' in dados_finais.columns:
                projetos = ['Todos'] + sorted(dados_finais['projeto'].dropna().unique().tolist())
                projeto_selecionado = st.selectbox("Filtrar por projeto:", projetos)
            else:
                projeto_selecionado = 'Todos'
        
        with col_filtro2:
            if 'mes_nome' in dados_finais.columns:
                meses = ['Todos'] + sorted(dados_finais['mes_nome'].dropna().unique().tolist())
                mes_selecionado = st.selectbox("Filtrar por mês:", meses)
            else:
                mes_selecionado = 'Todos'
        
        with col_filtro3:
            if 'gerenciadora' in dados_finais.columns:
                gerenciadoras = ['Todas'] + sorted(dados_finais['gerenciadora'].dropna().unique().tolist())
                gerenciadora_selecionada = st.selectbox("Filtrar por gerenciadora:", gerenciadoras)
            else:
                gerenciadora_selecionada = 'Todas'
        
        # Aplicar filtros
        dados_filtrados = dados_finais.copy()
        
        if projeto_selecionado != 'Todos':
            dados_filtrados = dados_filtrados[dados_filtrados['projeto'] == projeto_selecionado]
        
        if mes_selecionado != 'Todos':
            dados_filtrados = dados_filtrados[dados_filtrados['mes_nome'] == mes_selecionado]
        
        if gerenciadora_selecionada != 'Todas':
            dados_filtrados = dados_filtrados[dados_filtrados['gerenciadora'] == gerenciadora_selecionada]
        
        # Mostrar dados
        st.dataframe(
            dados_filtrados,
            use_container_width=True,
            height=400,
            column_config={
                "valor_pagto": st.column_config.NumberColumn(
                    "Valor Pago",
                    format="R$ %.2f"
                )
            }
        )
        
        # Estatísticas dos filtrados
        if len(dados_filtrados) > 0:
            st.info(f"""
            **Filtro aplicado:** {len(dados_filtrados):,} registros | 
            Valor total: R$ {dados_filtrados['valor_pagto'].sum():,.2f} | 
            Média: R$ {dados_filtrados['valor_pagto'].mean():,.2f}
            """)
    
    with tab2:
        st.subheader("Consolidação Mensal")
        
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
            
            # Gráfico de evolução mensal
            if mostrar_graficos:
                fig_evolucao = criar_grafico_evolucao_mensal(consolidado_mensal)
                if fig_evolucao:
                    st.plotly_chart(fig_evolucao, use_container_width=True)
        else:
            st.info("Não há dados suficientes para consolidação mensal")
    
    with tab3:
        st.subheader("Consolidação por Projeto")
        
        if not consolidado_projetos.empty:
            st.dataframe(
                consolidado_projetos,
                use_container_width=True,
                height=400,
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
            
            # Gráfico de projetos
            if mostrar_graficos:
                fig_projetos = criar_grafico_projetos(consolidado_projetos)
                if fig_projetos:
                    st.plotly_chart(fig_projetos, use_container_width=True)
        else:
            st.info("Não há dados de projetos para análise")
    
    with tab4:
        st.subheader("Visualizações Gráficas")
        
        if mostrar_graficos and not dados_finais.empty:
            col_graf1, col_graf2 = st.columns(2)
            
            with col_graf1:
                # Gráfico de distribuição mensal
                fig_dist_mensal = criar_grafico_distribuicao_mensal(dados_finais)
                if fig_dist_mensal:
                    st.plotly_chart(fig_dist_mensal, use_container_width=True)
            
            with col_graf2:
                # Gráfico de pizza por gerenciadora (se disponível)
                if 'gerenciadora' in dados_finais.columns:
                    gerenciadoras_contagem = dados_finais['gerenciadora'].value_counts()
                    
                    if len(gerenciadoras_contagem) > 0:
                        fig_pizza = px.pie(
                            values=gerenciadoras_contagem.values,
                            names=gerenciadoras_contagem.index,
                            title='Distribuição por Gerenciadora',
                            hole=0.3
                        )
                        st.plotly_chart(fig_pizza, use_container_width=True)
            
            # Gráfico de distribuição de valores
            if 'valor_pagto' in dados_finais.columns:
                fig_hist = px.histogram(
                    dados_finais,
                    x='valor_pagto',
                    nbins=30,
                    title='Distribuição dos Valores Pagos',
                    labels={'valor_pagto': 'Valor Pago (R$)'}
                )
                st.plotly_chart(fig_hist, use_container_width=True)
    
    # ========================================================================
    # EXPORTAÇÃO
    # ========================================================================
    st.markdown("---")
    st.subheader("💾 Exportação de Dados")
    
    col_exp1, col_exp2, col_exp3, col_exp4 = st.columns(4)
    
    with col_exp1:
        # Exportar dados consolidados CSV
        csv_data = dados_finais.to_csv(index=False, sep=';', decimal=',')
        st.download_button(
            label="📥 Dados Consolidados (CSV)",
            data=csv_data,
            file_name=f"pot_consolidado_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True
        )
    
    with col_exp2:
        # Exportar relatório completo Excel
        excel_bytes = exportar_dados_completos(dados_finais, consolidado_mensal, consolidado_projetos)
        
        if excel_bytes:
            st.download_button(
                label="📊 Relatório Completo (Excel)",
                data=excel_bytes,
                file_name=f"relatorio_pot_completo_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
    
    with col_exp3:
        # Exportar consolidação mensal
        if not consolidado_mensal.empty:
            csv_mensal = consolidado_mensal.to_csv(sep=';', decimal=',')
            st.download_button(
                label="📅 Consolidação Mensal (CSV)",
                data=csv_mensal,
                file_name=f"consolidacao_mensal_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )
    
    with col_exp4:
        # Exportar consolidação por projeto
        if not consolidado_projetos.empty:
            csv_projetos = consolidado_projetos.to_csv(sep=';', decimal=',')
            st.download_button(
                label="🏢 Consolidação por Projeto (CSV)",
                data=csv_projetos,
                file_name=f"consolidacao_projetos_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )
    
    # Botão para limpar dados
    st.markdown("---")
    col_limpar, _, _ = st.columns([1, 2, 1])
    
    with col_limpar:
        if st.button("🗑️ Limpar Todos os Dados", use_container_width=True):
            st.session_state.dados_consolidados = pd.DataFrame()
            st.session_state.arquivos_processados = []
            st.session_state.historico_mensal = pd.DataFrame()
            st.session_state.projetos_consolidados = pd.DataFrame()
            st.success("✅ Dados limpos com sucesso!")
            st.rerun()
    
    # ========================================================================
    # RODAPÉ
    # ========================================================================
    st.markdown("---")
    st.caption(f"""
    ⚙️ Sistema de Consolidação de Pagamentos - POT v5.0 | 
    Processado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} | 
    Total de registros: {len(dados_finais):,} | 
    Arquivos processados: {len(st.session_state.arquivos_processados)}
    """)

# ============================================================================
# EXECUTAR APLICAÇÃO
# ============================================================================
if __name__ == "__main__":
    main()
