import streamlit as st
import pandas as pd
import io
import unicodedata
import re

# --- Configuração da Página ---
st.set_page_config(
    page_title="Processador de Folha de Pagamento", 
    page_icon="💰",
    layout="wide"
)

# --- CSS Personalizado para melhor visualização ---
st.markdown("""
    <style>
    .stMetric {
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 5px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 1. Funções Auxiliares de Limpeza ---

def remover_acentos(texto):
    """Remove acentos e caracteres especiais de uma string."""
    if not isinstance(texto, str):
        return str(texto)
    # Normaliza para NFD (decompondo caracteres) e filtra não-espaçados
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')

def limpar_string_coluna(coluna):
    """
    Padroniza o nome da coluna para comparação:
    - Minusculo
    - Sem acentos
    - Sem espaços extras
    - Sem pontuação
    """
    coluna = remover_acentos(coluna.lower().strip())
    # Remove tudo que não for letra ou número
    coluna = re.sub(r'[^a-z0-9]', '', coluna)
    return coluna

def limpar_valor_monetario(valor):
    """
    Converte strings de dinheiro (R$ 1.500,00) para float (1500.00).
    """
    if pd.isna(valor):
        return 0.0
    
    valor_str = str(valor).strip()
    
    # Remove R$ e espaços
    valor_str = valor_str.lower().replace('r$', '').strip()
    
    # Se estiver vazio após limpeza
    if not valor_str:
        return 0.0
        
    try:
        # Lógica para formato brasileiro:
        # 1. Remove ponto de milhar (1.000 -> 1000)
        # 2. Troca vírgula decimal por ponto (10,50 -> 10.50)
        valor_str = valor_str.replace('.', '').replace(',', '.')
        return float(valor_str)
    except ValueError:
        return 0.0

# --- 2. Lógica de Padronização Inteligente ---

def normalizar_cabecalhos(df):
    """
    Analisa os cabeçalhos do DataFrame e os renomeia para o padrão do sistema.
    """
    # Remove espaços em branco das colunas originais
    df.columns = df.columns.str.strip()
    
    # Dicionário de Mapeamento: Chave é o Padrão, Valor é lista de termos possíveis
    mapa_colunas = {
        'Num Cartao': ['numcartao', 'nrocartao', 'numerocartao', 'cartao', 'card', 'nrcartao'],
        'Nome': ['nome', 'beneficiario', 'favorecido', 'funcionario', 'nomedobeneficiario', 'nomefavorecido'],
        'CPF': ['cpf', 'cpfbeneficiario', 'doc', 'documento'],
        'Valor': ['valor', 'valorpagto', 'valorliquido', 'valortotal', 'total', 'liquido'],
        'Data': ['data', 'dtpagto', 'datapagto', 'datamovimento']
    }
    
    colunas_renomeadas = {}
    colunas_originais = list(df.columns)
    
    for col_atual in colunas_originais:
        # Prepara a coluna atual para comparação (limpa e sem acentos)
        col_clean = limpar_string_coluna(col_atual)
        
        match_encontrado = False
        
        for col_padrao, termos_chave in mapa_colunas.items():
            if match_encontrado: break
            
            for termo in termos_chave:
                # Verifica se o termo chave está contido na coluna limpa
                # Ex: "valortotal" contém "valor" -> Match!
                if termo in col_clean:
                    colunas_renomeadas[col_atual] = col_padrao
                    match_encontrado = True
                    break
    
    # Aplica a renomeação
    if colunas_renomeadas:
        df = df.rename(columns=colunas_renomeadas)
        
    return df, colunas_renomeadas

# --- 3. Processamento de Arquivos ---

def carregar_arquivo(uploaded_file):
    """Lê CSV ou Excel tentando várias codificações."""
    filename = uploaded_file.name.lower()
    
    try:
        if filename.endswith('.csv'):
            # Tenta ler CSV com diferentes parâmetros
            try:
                # Tentativa 1: Padrão PT-BR (Ponto e vírgula, UTF-8)
                return pd.read_csv(uploaded_file, sep=';', encoding='utf-8', dtype=str)
            except:
                uploaded_file.seek(0)
                try:
                    # Tentativa 2: Latin-1 (comum em sistemas legados/bancos)
                    return pd.read_csv(uploaded_file, sep=';', encoding='latin-1', dtype=str)
                except:
                    uploaded_file.seek(0)
                    # Tentativa 3: Separador vírgula (Padrão US)
                    return pd.read_csv(uploaded_file, sep=',', encoding='utf-8', dtype=str)
        else:
            # Excel (.xlsx, .xls)
            return pd.read_excel(uploaded_file, dtype=str)
    except Exception as e:
        raise Exception(f"Erro ao ler o arquivo: {str(e)}")

def processar_dados(uploaded_file):
    """Fluxo principal de processamento de um único arquivo."""
    
    # 1. Carregar
    df = carregar_arquivo(uploaded_file)
    
    # 2. Padronizar Colunas
    df, mudancas = normalizar_cabecalhos(df)
    
    # 3. Validação de Estrutura
    colunas_obrigatorias = ['Num Cartao', 'Nome', 'Valor']
    colunas_existentes = [c for c in colunas_obrigatorias if c in df.columns]
    colunas_faltantes = [c for c in colunas_obrigatorias if c not in df.columns]
    
    if colunas_faltantes:
        return None, f"Colunas obrigatórias não encontradas: {', '.join(colunas_faltantes)}", mudancas
    
    # 4. Limpeza e Tipagem de Dados
    
    # Limpeza do Valor
    df['Valor'] = df['Valor'].apply(limpar_valor_monetario)
    
    # Limpeza do Cartão (apenas dígitos)
    df['Num Cartao'] = df['Num Cartao'].astype(str).str.replace(r'\D', '', regex=True)
    
    # Garantir que Nome seja string limpa (opcional: title case)
    df['Nome'] = df['Nome'].astype(str).str.strip().str.title()
    
    # Adicionar metadados
    df['Arquivo Origem'] = uploaded_file.name
    
    # Selecionar e reordenar apenas colunas relevantes (mantendo CPF e Data se existirem)
    cols_finais = ['Arquivo Origem', 'Num Cartao', 'Nome', 'Valor']
    if 'CPF' in df.columns: cols_finais.append('CPF')
    if 'Data' in df.columns: cols_finais.append('Data')
    
    # Filtra apenas as colunas que realmente existem no DF final
    cols_finais = [c for c in cols_finais if c in df.columns]
    
    return df[cols_finais], None, mudancas

# --- 4. Interface do Streamlit ---

st.title("📂 Sistema de Consolidação de Pagamentos")
st.markdown("---")

with st.sidebar:
    st.header("Upload de Arquivos")
    st.info("Suporta CSV (separado por ; ou ,) e Excel (.xlsx)")
    uploaded_files = st.file_uploader(
        "Selecione as planilhas", 
        accept_multiple_files=True,
        type=['csv', 'xlsx', 'xls']
    )

if uploaded_files:
    dfs_validos = []
    
    st.subheader("🔍 Análise Individual")
    
    for arquivo in uploaded_files:
        with st.expander(f"Processando: {arquivo.name}", expanded=True):
            df_proc, erro, mudancas = processar_dados(arquivo)
            
            if erro:
                st.error(f"❌ Erro no arquivo: {erro}")
                # Debug visual para ajudar o usuário
                try:
                    arquivo.seek(0)
                    df_raw = pd.read_csv(arquivo, sep=';', nrows=3) if arquivo.name.endswith('.csv') else pd.read_excel(arquivo, nrows=3)
                    st.caption("Primeiras linhas do arquivo original para verificação:")
                    st.dataframe(df_raw)
                except:
                    pass
            else:
                col1, col2 = st.columns([3, 1])
                with col1:
                    if mudancas:
                        st.success(f"✅ Processado! Colunas detectadas: {list(mudancas.keys())} ➝ {list(mudancas.values())}")
                    else:
                        st.success("✅ Arquivo processado com colunas padrão.")
                with col2:
                    st.metric("Total do Arquivo", f"R$ {df_proc['Valor'].sum():,.2f}")
                
                st.dataframe(df_proc.head(), use_container_width=True)
                dfs_validos.append(df_proc)
    
    # --- Consolidação ---
    if dfs_validos:
        st.markdown("---")
        st.header("📊 Resultado Consolidado")
        
        df_final = pd.concat(dfs_validos, ignore_index=True)
        
        # Métricas Gerais
        m1, m2, m3 = st.columns(3)
        m1.metric("Arquivos Unificados", len(dfs_validos))
        m2.metric("Total de Beneficiários", len(df_final))
        total_geral = df_final['Valor'].sum()
        m3.metric("Valor Total da Folha", f"R$ {total_geral:,.2f}")
        
        # Exibição dos Dados
        st.dataframe(df_final, use_container_width=True)
        
        # Preparação para Download (Formato PT-BR para Excel)
        df_export = df_final.copy()
        # Formata float para string com vírgula (R$ 1000,00)
        df_export['Valor'] = df_export['Valor'].apply(lambda x: f"{x:.2f}".replace('.', ','))
        
        csv_buffer = df_export.to_csv(index=False, sep=';', encoding='utf-8-sig')
        
        col_esq, col_dir = st.columns([1, 2])
        with col_esq:
            st.download_button(
                label="⬇️ Baixar Planilha Consolidada (.csv)",
                data=csv_buffer,
                file_name="folha_pagamento_consolidada.csv",
                mime="text/csv",
                type="primary"
            )

else:
    st.info("👈 Por favor, faça o upload dos arquivos na barra lateral para começar.")
