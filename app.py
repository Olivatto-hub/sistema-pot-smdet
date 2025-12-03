# app.py - SISTEMA POT - VERSÃO COM DETECÇÃO AVANÇADA DE DADOS
# Corrige problema de "Arquivo vazio ou sem dados válidos"

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
# FUNÇÕES DE PROCESSAMENTO AVANÇADAS
# ============================================================================

def decodificar_arquivo_com_fallback(bytes_data):
    """Decodifica arquivo com múltiplas tentativas"""
    # Lista de encodings em ordem de prioridade
    encodings = ['utf-8-sig', 'latin-1', 'cp1252', 'iso-8859-1', 'utf-8']
    
    for encoding in encodings:
        try:
            return bytes_data.decode(encoding, errors='replace')
        except:
            continue
    
    # Último recurso: latin-1 ignorando erros
    return bytes_data.decode('latin-1', errors='ignore')

def detectar_separador(conteudo):
    """Detecta o separador do CSV analisando o conteúdo"""
    # Amostra das primeiras linhas
    linhas = conteudo.split('\n', 20)
    
    contagem_ponto_virgula = 0
    contagem_virgula = 0
    contagem_tab = 0
    
    for linha in linhas[:10]:  # Analisar apenas as primeiras 10 linhas
        if linha.strip():
            contagem_ponto_virgula += linha.count(';')
            contagem_virgula += linha.count(',')
            contagem_tab += linha.count('\t')
    
    # Determinar separador baseado na contagem
    if contagem_ponto_virgula > contagem_virgula and contagem_ponto_virgula > contagem_tab:
        return ';'
    elif contagem_virgula > contagem_ponto_virgula and contagem_virgula > contagem_tab:
        return ','
    elif contagem_tab > 0:
        return '\t'
    else:
        # Se não detectar claramente, verificar padrão brasileiro
        for linha in linhas[:5]:
            if ';' in linha and any(c.isdigit() for c in linha):
                return ';'
        return ','  # Padrão como fallback

def limpar_valor_monetario_avancado(valor):
    """Converte valores monetários de forma avançada"""
    if pd.isna(valor) or str(valor).strip() in ['', 'nan', 'None', 'NaT', 'NULL']:
        return np.nan
    
    try:
        texto = str(valor).strip()
        
        # Remover caracteres não numéricos exceto pontos, vírgulas e hífens
        texto = re.sub(r'[^\d,\-.]', '', texto)
        
        if texto == '':
            return np.nan
        
        # Se já é número simples
        if texto.replace('.', '', 1).replace('-', '', 1).isdigit():
            return float(texto)
        
        # Formato brasileiro: 1.027,18 ou 272.486,06
        if ',' in texto:
            # Verificar se há pontos de milhar
            if '.' in texto:
                # Contar dígitos após a vírgula
                partes = texto.split(',')
                if len(partes) == 2 and len(partes[1]) <= 2:
                    # Formato com separador decimal
                    # Remover pontos de milhar
                    texto_sem_milhar = texto.replace('.', '')
                    # Substituir vírgula por ponto
                    texto_final = texto_sem_milhar.replace(',', '.')
                    return float(texto_final)
            
            # Apenas vírgula como separador decimal
            texto = texto.replace(',', '.')
        
        # Verificar se é número negativo
        if texto.startswith('-'):
            try:
                return float(texto)
            except:
                pass
        
        # Tentar converter
        return float(texto)
    except:
        return np.nan

def processar_csv_avancado(arquivo):
    """Processa CSV com detecção avançada de dados"""
    try:
        # Obter bytes do arquivo
        bytes_data = arquivo.getvalue()
        
        # Decodificar
        conteudo = decodificar_arquivo_com_fallback(bytes_data)
        
        # Remover BOM e caracteres problemáticos
        conteudo = conteudo.lstrip('\ufeff')
        conteudo = conteudo.replace('\x00', '').replace('\r\n', '\n').replace('\r', '\n')
        
        # Verificar se há conteúdo
        if not conteudo.strip():
            return None, "Arquivo completamente vazio"
        
        # Separar linhas
        linhas = conteudo.split('\n')
        
        # Remover linhas completamente vazias
        linhas = [linha.strip() for linha in linhas if linha.strip()]
        
        if len(linhas) < 2:
            return None, "Arquivo com menos de 2 linhas não vazias"
        
        # Detectar separador
        separador = detectar_separador(conteudo)
        
        # DEBUG: Mostrar primeiras linhas para diagnóstico
        debug_info = []
        debug_info.append(f"Total de linhas: {len(linhas)}")
        debug_info.append(f"Separador detectado: '{separador}'")
        debug_info.append(f"Primeira linha: {linhas[0][:100]}...")
        if len(linhas) > 1:
            debug_info.append(f"Segunda linha: {linhas[1][:100]}...")
        
        # Tentar diferentes métodos de leitura
        df = None
        metodo_utilizado = "Desconhecido"
        
        # MÉTODO 1: pandas read_csv normal
        try:
            df = pd.read_csv(
                StringIO(conteudo),
                sep=separador,
                dtype=str,
                on_bad_lines='skip',
                engine='python',
                quoting=csv.QUOTE_MINIMAL
            )
            metodo_utilizado = "Pandas normal"
        except Exception as e:
            debug_info.append(f"Falha método 1: {str(e)[:100]}")
        
        # MÉTODO 2: pandas com configuração diferente
        if df is None or len(df) == 0:
            try:
                # Tentar sem cabeçalho primeiro
                df = pd.read_csv(
                    StringIO(conteudo),
                    sep=separador,
                    header=None,
                    dtype=str,
                    on_bad_lines='skip',
                    engine='python'
                )
                metodo_utilizado = "Pandas sem cabeçalho"
            except Exception as e:
                debug_info.append(f"Falha método 2: {str(e)[:100]}")
        
        # MÉTODO 3: Leitura manual
        if df is None or len(df) == 0:
            try:
                dados = []
                for linha in linhas:
                    if separador in linha:
                        partes = linha.split(separador)
                        dados.append(partes)
                
                if len(dados) >= 1:
                    # Se tiver poucas colunas, pode não ter cabeçalho
                    if len(dados[0]) <= 3:
                        df = pd.DataFrame(dados, columns=[f'col{i}' for i in range(len(dados[0]))])
                    else:
                        # Assumir primeira linha como cabeçalho
                        df = pd.DataFrame(dados[1:], columns=dados[0])
                    metodo_utilizado = "Leitura manual"
            except Exception as e:
                debug_info.append(f"Falha método 3: {str(e)[:100]}")
        
        # MÉTODO 4: Tentar detectar padrão específico do POT
        if df is None or len(df) == 0:
            # Procurar por padrões conhecidos
            for i, linha in enumerate(linhas[:10]):
                if 'projeto' in linha.lower() or 'valor' in linha.lower() or 'pagto' in linha.lower():
                    # Esta linha parece ser cabeçalho
                    if i + 1 < len(linhas):
                        dados = []
                        for j in range(i, min(i + 20, len(linhas))):  # Pegar até 20 linhas
                            if separador in linhas[j]:
                                partes = linhas[j].split(separador)
                                dados.append(partes)
                        
                        if len(dados) >= 2:
                            df = pd.DataFrame(dados[1:], columns=dados[0])
                            metodo_utilizado = f"Detecção padrão POT (linha {i})"
                            break
        
        if df is None or len(df) == 0:
            return None, f"Não foi possível extrair dados. Métodos tentados: {debug_info}"
        
        # DEBUG: Informações sobre o DataFrame
        debug_info.append(f"Método utilizado: {metodo_utilizado}")
        debug_info.append(f"Colunas encontradas: {list(df.columns)}")
        debug_info.append(f"Linhas no DataFrame: {len(df)}")
        
        # Padronizar nomes das colunas
        df.columns = [str(col).strip().lower().replace(' ', '_') for col in df.columns]
        
        # Mapeamento extenso de colunas
        mapeamento_colunas = {
            # Projeto
            'projeto': 'projeto', 'programa': 'projeto', 'cod_projeto': 'projeto',
            'codigo_projeto': 'projeto', 'proj': 'projeto',
            
            # Nome
            'nome': 'nome', 'beneficiario': 'nome', 'beneficiário': 'nome',
            'nome_beneficiario': 'nome', 'nome_beneficiário': 'nome',
            
            # Valor
            'valor_pagto': 'valor_pagto', 'valor_pagamento': 'valor_pagto',
            'valor': 'valor_pagto', 'valor_pago': 'valor_pagto',
            'vlr_pagto': 'valor_pagto', 'vl_pagto': 'valor_pagto',
            'pagamento': 'valor_pagto', 'valor_total': 'valor_pagto',
            
            # Data
            'data_pagto': 'data_pagto', 'data_pagamento': 'data_pagto',
            'data': 'data_pagto', 'dt_pagto': 'data_pagto',
            'datapagto': 'data_pagto',
            
            # Agência
            'agencia': 'agencia', 'agência': 'agencia',
            'cod_agencia': 'agencia', 'ag': 'agencia',
            
            # Gerenciadora
            'gerenciadora': 'gerenciadora', 'gerenciador': 'gerenciadora',
            'sistema': 'gerenciadora', 'rede': 'gerenciadora',
            
            # Outros
            'ordem': 'ordem', 'num': 'ordem', 'nº': 'ordem',
            'cartao': 'cartao', 'cartão': 'cartao',
            'cpf': 'cpf', 'rg': 'rg',
            'dias': 'dias_apagar', 'dias_apagar': 'dias_apagar',
            'valor_dia': 'valor_dia', 'vl_dia': 'valor_dia'
        }
        
        # Aplicar mapeamento
        colunas_mapeadas = []
        for col in df.columns:
            col_lower = col.lower()
            mapeada = False
            for padrao, novo_nome in mapeamento_colunas.items():
                if padrao in col_lower:
                    df = df.rename(columns={col: novo_nome})
                    colunas_mapeadas.append(novo_nome)
                    mapeada = True
                    break
            
            if not mapeada:
                colunas_mapeadas.append(col)
        
        # Garantir colunas essenciais
        colunas_essenciais = ['projeto', 'valor_pagto']
        for col_essencial in colunas_essenciais:
            if col_essencial not in df.columns:
                # Tentar encontrar coluna similar
                col_similar = None
                for col in df.columns:
                    if col_essencial in col or any(palavra in col for palavra in ['proj', 'val', 'pag']):
                        col_similar = col
                        break
                
                if col_similar:
                    df = df.rename(columns={col_similar: col_essencial})
                else:
                    # Criar coluna vazia
                    df[col_essencial] = ''
        
        # Processar valores monetários
        if 'valor_pagto' in df.columns:
            df['valor_pagto'] = df['valor_pagto'].apply(limpar_valor_monetario_avancado)
            
            # Remover linhas com valor NaN ou zero (se muitos registros)
            valores_validos = df['valor_pagto'].notna().sum()
            if valores_validos > 0:
                # Manter apenas linhas com valores válidos
                df = df[df['valor_pagto'].notna()]
        
        # Processar outras colunas numéricas
        if 'dias_apagar' in df.columns:
            df['dias_apagar'] = pd.to_numeric(df['dias_apagar'], errors='coerce')
        
        # Processar datas
        if 'data_pagto' in df.columns:
            # Tentar diferentes formatos de data
            try:
                df['data_pagto'] = pd.to_datetime(df['data_pagto'], dayfirst=True, errors='coerce')
            except:
                try:
                    df['data_pagto'] = pd.to_datetime(df['data_pagto'], errors='coerce')
                except:
                    df['data_pagto'] = pd.NaT
        
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
        
        # Limpeza final
        df = df.replace(['', 'nan', 'NaN', 'None', 'NaT', 'null', 'NULL'], np.nan)
        
        # Remover linhas completamente vazias
        df = df.dropna(how='all')
        
        # Se ainda estiver vazio após processamento
        if len(df) == 0:
            return None, f"Arquivo processado mas sem dados válidos após limpeza. Debug: {' | '.join(debug_info[:3])}"
        
        return df, f"✅ Processado: {len(df)} registros ({mes_referencia}) - {metodo_utilizado}"
    
    except Exception as e:
        return None, f"❌ Erro ao processar: {str(e)}"

def processar_excel_avancado(arquivo):
    """Processa Excel com tentativas múltiplas"""
    try:
        # Tentar ler todas as abas
        try:
            xls = pd.ExcelFile(arquivo)
            sheet_names = xls.sheet_names
        except:
            return None, "Não foi possível abrir o arquivo Excel"
        
        dfs = []
        
        for sheet in sheet_names:
            try:
                df_sheet = pd.read_excel(xls, sheet_name=sheet, dtype=str)
                
                # Verificar se tem dados
                if len(df_sheet) > 0 and len(df_sheet.columns) > 0:
                    dfs.append(df_sheet)
            except:
                continue
        
        if not dfs:
            return None, "Nenhuma aba com dados encontrada"
        
        # Combinar todas as abas
        if len(dfs) == 1:
            df = dfs[0]
        else:
            df = pd.concat(dfs, ignore_index=True)
        
        # Padronizar colunas
        df.columns = [str(col).strip().lower().replace(' ', '_') for col in df.columns]
        
        # Mapeamento
        mapeamento = {
            'projeto': 'projeto',
            'nome': 'nome',
            'valor_pagto': 'valor_pagto',
            'valor_pagamento': 'valor_pagto',
            'valor': 'valor_pagto',
            'data_pagto': 'data_pagto',
            'data': 'data_pagto',
            'agencia': 'agencia',
            'gerenciadora': 'gerenciadora'
        }
        
        for col_antiga, col_nova in mapeamento.items():
            if col_antiga in df.columns:
                df = df.rename(columns={col_antiga: col_nova})
        
        # Processar valores
        if 'valor_pagto' in df.columns:
            df['valor_pagto'] = df['valor_pagto'].apply(limpar_valor_monetario_avancado)
        
        # Adicionar metadados
        df['arquivo_origem'] = arquivo.name
        df['mes_referencia'] = 'Excel'
        df['ano'] = datetime.now().year
        
        return df, f"✅ Excel processado: {len(df)} registros de {len(sheet_names)} aba(s)"
    
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
            metricas['qtd_valores_validos'] = len(valores)
        else:
            metricas['valor_total'] = 0.0
            metricas['valor_medio'] = 0.0
    
    if 'projeto' in df.columns:
        metricas['projetos_unicos'] = df['projeto'].nunique()
    
    if 'mes_referencia' in df.columns:
        metricas['meses_unicos'] = df['mes_referencia'].nunique()
    
    return metricas

def gerar_consolidado_mensal(df):
    """Gera consolidação mensal"""
    if 'mes_referencia' not in df.columns or 'valor_pagto' not in df.columns:
        return pd.DataFrame()
    
    try:
        consolidado = df.groupby('mes_referencia').agg(
            qtd_pagamentos=('valor_pagto', 'count'),
            valor_total=('valor_pagto', 'sum'),
            valor_medio=('valor_pagto', 'mean'),
            qtd_projetos=('projeto', 'nunique') if 'projeto' in df.columns else pd.Series([0])
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
            qtd_pagamentos=('valor_pagto', 'count'),
            valor_total=('valor_pagto', 'sum'),
            valor_medio=('valor_pagto', 'mean'),
            qtd_meses=('mes_referencia', 'nunique') if 'mes_referencia' in df.columns else pd.Series([0])
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
            "Selecione os arquivos do POT",
            type=['csv', 'txt', 'xlsx', 'xls'],
            accept_multiple_files=True,
            help="Arraste arquivos como PGTO ABASTECE SETEMBRO.csv"
        )
        
        st.markdown("---")
        st.header("⚙️ CONFIGURAÇÕES")
        
        modo = st.radio(
            "Modo:",
            ["Processar novos", "Acumular aos existentes"]
        )
        
        mostrar_detalhes = st.checkbox("Mostrar detalhes do processamento", value=False)
        
        st.markdown("---")
        st.header("📊 STATUS")
        
        if not st.session_state.dados_consolidados.empty:
            metricas = calcular_metricas(st.session_state.dados_consolidados)
            st.success("Dados carregados")
            st.metric("Registros", f"{metricas['total_registros']:,}")
            st.metric("Valor Total", f"R$ {metricas.get('valor_total', 0):,.2f}")
        else:
            st.info("Aguardando arquivos...")
    
    # Área principal
    if not arquivos:
        st.info("👋 **Sistema POT - Detecção Avançada de Dados**")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown("""
            ### 🚨 **PROBLEMA RESOLVIDO:**
            
            **Arquivo mostra "vazio" mas tem dados?**
            
            O sistema agora tem **4 métodos diferentes** para detectar dados:
            
            1. **Pandas normal** - Para CSVs bem formatados
            2. **Pandas sem cabeçalho** - Para arquivos sem linha de cabeçalho
            3. **Leitura manual** - Para arquivos com problemas de formatação
            4. **Detecção padrão POT** - Para arquivos do sistema POT
            
            ### 🎯 **PARA ARQUIVOS PROBLEMÁTICOS:**
            
            Se seus arquivos como `PGTO ABASTECE SETEMBRO.csv` estão dando erro:
            
            1. O sistema vai **analisar o conteúdo** automaticamente
            2. **Detectar o separador** correto (; ou ,)
            3. **Identificar cabeçalhos** mesmo que não estejam na primeira linha
            4. **Extrair dados** mesmo de arquivos mal formatados
            
            ### 🔧 **FUNCIONALIDADES:**
            
            - ✅ Detecção automática de encoding
            - ✅ Múltiplos métodos de leitura
            - ✅ Consolidação por mês e projeto
            - ✅ Exportação completa
            """)
        
        with col2:
            st.markdown("""
            ### 📋 **COMO TESTAR:**
            
            1. **Carregue os arquivos problemáticos**
            2. **Marque "Mostrar detalhes do processamento"**
            3. **Veja qual método foi usado**
            4. **Analise os dados extraídos**
            
            ### ⚠️ **ARQUIVOS COM PROBLEMAS:**
            
            **Formato brasileiro comum:**
            ```
            Projeto;Nome;Valor Pagto
            ABATECE;João Silva;R$ 1.027,18
            ADS;Maria Santos;R$ 2.500,00
            ```
            
            **O sistema detecta:**
            - Separador: `;`
            - Valores: `R$ 1.027,18` → `1027.18`
            - Mês: Do nome do arquivo
            """)
            
            st.error("""
            **Problema anterior:**
            "Arquivo vazio ou sem dados válidos"
            
            **Solução aplicada:**
            Múltiplos métodos de detecção
            """)
        
        return
    
    # Processar arquivos
    st.header("🔄 PROCESSAMENTO AVANÇADO")
    
    dataframes = []
    resultados = []
    
    for arquivo in arquivos:
        st.subheader(f"📄 {arquivo.name}")
        
        col_info, col_status = st.columns([3, 1])
        
        with col_info:
            st.text(f"Tamanho: {len(arquivo.getvalue()):,} bytes")
        
        # Processar arquivo
        if arquivo.name.lower().endswith(('.csv', '.txt')):
            df, mensagem = processar_csv_avancado(arquivo)
        elif arquivo.name.lower().endswith(('.xlsx', '.xls')):
            df, mensagem = processar_excel_avancado(arquivo)
        else:
            mensagem = f"Formato não suportado: {arquivo.name}"
            df = None
        
        with col_status:
            if df is not None:
                st.success("✅")
            else:
                st.error("❌")
        
        if df is not None:
            dataframes.append(df)
            resultados.append(f"✅ {arquivo.name}: {mensagem}")
            
            if mostrar_detalhes:
                with st.expander("Detalhes do processamento", expanded=False):
                    st.write(f"**Mensagem:** {mensagem}")
                    st.write(f"**Colunas:** {list(df.columns)}")
                    st.write(f"**Amostra de dados:**")
                    st.dataframe(df.head(5), use_container_width=True)
        else:
            resultados.append(f"❌ {arquivo.name}: {mensagem}")
            
            if mostrar_detalhes:
                with st.expander("Detalhes do erro", expanded=True):
                    st.error(mensagem)
                    
                    # Mostrar conteúdo do arquivo para diagnóstico
                    try:
                        conteudo = arquivo.getvalue().decode('latin-1', errors='ignore')[:1000]
                        st.text("Primeiros 1000 caracteres do arquivo:")
                        st.code(conteudo)
                    except:
                        st.warning("Não foi possível exibir o conteúdo do arquivo")
    
    if not dataframes:
        st.error("❌ Nenhum arquivo foi processado com sucesso")
        
        # Sugestões para problemas comuns
        st.markdown("---")
        st.header("🔧 SOLUÇÃO DE PROBLEMAS")
        
        col_prob1, col_prob2 = st.columns(2)
        
        with col_prob1:
            st.markdown("""
            ### 📁 **PROBLEMA: Separador errado**
            
            **Sintoma:**
            - Arquivo tem dados mas sistema não detecta
            
            **Solução:**
            1. Abra o arquivo em um editor de texto
            2. Verifique se usa `;` ou `,` como separador
            3. O sistema detecta automaticamente
            
            **Exemplo correto:**
            ```
            Projeto;Nome;Valor
            ABATECE;João;R$ 1.000,00
            ```
            """)
        
        with col_prob2:
            st.markdown("""
            ### 💾 **PROBLEMA: Encoding**
            
            **Sintoma:**
            - Caracteres estranhos como `�`
            
            **Solução:**
            1. Abra no Bloco de Notas
            2. Salve como "UTF-8 com BOM"
            3. Tente novamente
            
            **Formato correto:**
            - UTF-8 com BOM (recomendado)
            - Latin-1 (funciona)
            - CP1252 (Windows)
            """)
        
        return
    
    # Consolidar dados
    novo_df = pd.concat(dataframes, ignore_index=True)
    
    # Atualizar dados da sessão
    if modo == "Processar novos" or st.session_state.dados_consolidados.empty:
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
    
    # Mostrar métricas
    st.header("📈 RESULTADOS")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Registros", f"{metricas['total_registros']:,}")
    
    with col2:
        st.metric("Valor Total", f"R$ {metricas.get('valor_total', 0):,.2f}")
    
    with col3:
        st.metric("Valor Médio", f"R$ {metricas.get('valor_medio', 0):,.2f}")
    
    with col4:
        st.metric("Arquivos", len(arquivos))
    
    # Análise
    tab1, tab2, tab3 = st.tabs(["📋 Dados", "📅 Consolidação", "💾 Exportar"])
    
    with tab1:
        st.subheader("Dados Processados")
        
        if 'mes_referencia' in df_final.columns:
            meses = ['Todos'] + sorted(df_final['mes_referencia'].unique().tolist())
            mes_filtro = st.selectbox("Filtrar por mês:", meses)
            
            if mes_filtro != 'Todos':
                df_exibir = df_final[df_final['mes_referencia'] == mes_filtro]
            else:
                df_exibir = df_final
        else:
            df_exibir = df_final
        
        st.dataframe(
            df_exibir,
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
        col_cons1, col_cons2 = st.columns(2)
        
        with col_cons1:
            st.subheader("Por Mês")
            consolidado_mensal = gerar_consolidado_mensal(df_final)
            if not consolidado_mensal.empty:
                st.dataframe(consolidado_mensal, use_container_width=True)
        
        with col_cons2:
            st.subheader("Por Projeto")
            consolidado_projetos = gerar_consolidado_projetos(df_final)
            if not consolidado_projetos.empty:
                st.dataframe(consolidado_projetos.head(20), use_container_width=True)
    
    with tab3:
        st.subheader("Exportação")
        
        col_exp1, col_exp2 = st.columns(2)
        
        with col_exp1:
            csv_data = df_final.to_csv(index=False, sep=';', decimal=',')
            st.download_button(
                label="📥 Baixar CSV",
                data=csv_data,
                file_name=f"pot_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col_exp2:
            try:
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_final.to_excel(writer, sheet_name='DADOS', index=False)
                excel_bytes = output.getvalue()
                
                st.download_button(
                    label="📊 Baixar Excel",
                    data=excel_bytes,
                    file_name=f"pot_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            except:
                st.warning("Exportação Excel não disponível")
    
    # Rodapé
    st.markdown("---")
    st.caption(f"Sistema POT | {datetime.now().strftime('%d/%m/%Y %H:%M')}")

# ============================================================================
# EXECUÇÃO
# ============================================================================

if __name__ == "__main__":
    main()
