import pandas as pd
import os
import re
from datetime import datetime
import streamlit as st
import warnings
import chardet
import numpy as np  # IMPORTANTE: Adicionado numpy

warnings.filterwarnings('ignore')

# Configuração da página
st.set_page_config(
    page_title="Sistema POT - Monitoramento de Pagamentos",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

class SistemaPOTStreamlit:
    def __init__(self):
        self.df = None
        self.dados_limpos = None
        self.arquivo_processado = False
        self.nome_arquivo = ""
        self.total_pagamentos = 0
        self.coluna_valor_pagto = None  # Armazenar nome da coluna de valor de pagamento
        
    def detectar_encoding(self, arquivo_path):
        """Detecta o encoding do arquivo"""
        try:
            with open(arquivo_path, 'rb') as f:
                raw_data = f.read(10000)
            
            resultado = chardet.detect(raw_data)
            encoding = resultado['encoding']
            confianca = resultado['confidence']
            
            return encoding_map.get(encoding, encoding) if encoding else 'latin-1'
            
        except:
            return 'latin-1'
    
    def tentar_encodings(self, arquivo_path):
        """Tenta diferentes encodings até encontrar um que funcione"""
        encodings_para_tentar = [
            'latin-1', 'iso-8859-1', 'cp1252', 'utf-8', 'utf-8-sig', 'cp850'
        ]
        
        for encoding in encodings_para_tentar:
            try:
                df = pd.read_csv(arquivo_path, delimiter=';', encoding=encoding, nrows=5)
                if not df.empty and len(df.columns) > 1:
                    return encoding
            except:
                continue
        
        return None
    
    def converter_valor(self, valor_str):
        """Converte valores monetários do formato brasileiro para float"""
        if pd.isna(valor_str) or valor_str == '' or str(valor_str).strip() == '':
            return 0.0
        
        try:
            if isinstance(valor_str, (int, float)):
                return float(valor_str)
            
            valor_str = str(valor_str)
            
            # Se já começar com número, provavelmente já é numérico
            if re.match(r'^\d', valor_str.strip()):
                try:
                    return float(valor_str.replace(',', '.'))
                except:
                    pass
            
            # Remover R$ e espaços
            valor_str = valor_str.replace('R$', '').replace(' ', '').strip()
            
            # Verificar se tem vírgula como separador decimal
            if ',' in valor_str and '.' in valor_str:
                # Formato: 1.593,90 - remover pontos de milhar, substituir vírgula decimal
                partes = valor_str.split(',')
                if len(partes) == 2:
                    inteiro = partes[0].replace('.', '')
                    return float(f"{inteiro}.{partes[1]}")
            
            elif ',' in valor_str:
                # Formato: 1593,90
                return float(valor_str.replace(',', '.'))
            
            else:
                # Formato: 1593.90 ou 1593
                return float(valor_str)
                
        except Exception as e:
            return 0.0
    
    def processar_arquivo_streamlit(self, arquivo_upload):
        """Processa arquivo CSV de pagamentos do POT"""
        try:
            with st.spinner("📥 Lendo arquivo..."):
                # Salvar arquivo temporariamente
                temp_path = f"temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                with open(temp_path, 'wb') as f:
                    f.write(arquivo_upload.getvalue())
                
                # Detectar encoding
                encoding = self.tentar_encodings(temp_path) or self.detectar_encoding(temp_path) or 'latin-1'
                
                # Ler arquivo
                self.df = pd.read_csv(temp_path, delimiter=';', encoding=encoding, on_bad_lines='skip')
                
                # Limpar arquivo temporário
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            
            with st.spinner("🧹 Limpando dados..."):
                self._limpar_dados()
                
            with st.spinner("📊 Calculando estatísticas..."):
                self._calcular_estatisticas()
                
            self.arquivo_processado = True
            self.nome_arquivo = arquivo_upload.name
            
            return True
            
        except Exception as e:
            st.error(f"❌ Erro ao processar: {str(e)[:100]}")
            return False
    
    def _limpar_dados(self):
        """Limpa e prepara os dados para análise"""
        if self.df is None or self.df.empty:
            return
        
        df_limpo = self.df.copy()
        
        # Remover linhas totalmente vazias
        df_limpo = df_limpo.dropna(how='all')
        
        # Padronizar nomes das colunas (remover acentos, espaços, minúsculas)
        mapeamento_colunas = {}
        for col in df_limpo.columns:
            col_limpa = str(col).strip().lower()
            col_limpa = re.sub(r'[^a-z0-9_]', '_', col_limpa)
            col_limpa = (col_limpa
                        .replace('á', 'a').replace('é', 'e').replace('í', 'i')
                        .replace('ó', 'o').replace('ú', 'u').replace('â', 'a')
                        .replace('ê', 'e').replace('î', 'i').replace('ô', 'o')
                        .replace('û', 'u').replace('ã', 'a').replace('õ', 'o')
                        .replace('ç', 'c'))
            mapeamento_colunas[col] = col_limpa
        
        df_limpo = df_limpo.rename(columns=mapeamento_colunas)
        
        # IDENTIFICAR COLUNA DE VALOR DE PAGAMENTO
        # Lista de possíveis nomes (em ordem de prioridade)
        possiveis_nomes_valor = [
            'valor_pagto', 'valor_pagamento', 'valor_total', 'valor', 
            'pagto', 'pagamento', 'total', 'valorpagto'
        ]
        
        self.coluna_valor_pagto = None
        for nome in possiveis_nomes_valor:
            if nome in df_limpo.columns:
                self.coluna_valor_pagto = nome
                break
        
        # Se não encontrou, procurar por colunas que contenham essas palavras
        if self.coluna_valor_pagto is None:
            for col in df_limpo.columns:
                col_lower = col.lower()
                if any(termo in col_lower for termo in ['pagto', 'pagamento', 'valor']):
                    self.coluna_valor_pagto = col
                    break
        
        st.info(f"🔍 Coluna de valor identificada: {self.coluna_valor_pagto}")
        
        # Converter todas as colunas que parecem ser valores monetários
        colunas_valor = []
        for col in df_limpo.columns:
            col_lower = col.lower()
            if any(termo in col_lower for termo in ['valor', 'total', 'pagto', 'pagamento', 'desconto', 'dia']):
                colunas_valor.append(col)
        
        for coluna in colunas_valor:
            df_limpo[coluna] = df_limpo[coluna].apply(self.converter_valor)
        
        # Converter outras colunas numéricas
        for col in df_limpo.columns:
            # Tentar converter para numérico se não for texto óbvio
            if col not in ['nome', 'distrito', 'agencia', 'rg']:
                try:
                    df_limpo[col] = pd.to_numeric(df_limpo[col], errors='ignore')
                except:
                    pass
        
        # Procurar coluna de dias
        for col in df_limpo.columns:
            if 'dia' in col.lower() or 'dias' in col.lower():
                try:
                    df_limpo[col] = pd.to_numeric(df_limpo[col], errors='coerce')
                except:
                    pass
        
        # Procurar coluna de data
        for col in df_limpo.columns:
            if 'data' in col.lower():
                try:
                    df_limpo[col] = pd.to_datetime(df_limpo[col], format='%d/%m/%Y', errors='coerce')
                except:
                    try:
                        df_limpo[col] = pd.to_datetime(df_limpo[col], errors='coerce')
                    except:
                        pass
        
        # Remover linhas onde o valor de pagamento é zero ou negativo
        if self.coluna_valor_pagto and self.coluna_valor_pagto in df_limpo.columns:
            antes = len(df_limpo)
            df_limpo = df_limpo[df_limpo[self.coluna_valor_pagto] > 0]
            depois = len(df_limpo)
            st.info(f"📊 Removidos {antes - depois} registros com valor ≤ 0")
        
        self.dados_limpos = df_limpo
    
    def _calcular_estatisticas(self):
        """Calcula estatísticas dos dados - CORRIGIDO"""
        if self.dados_limpos is None or len(self.dados_limpos) == 0:
            st.error("❌ Nenhum dado para calcular estatísticas")
            return
        
        # USAR A COLUNA IDENTIFICADA DE VALOR DE PAGAMENTO
        if self.coluna_valor_pagto and self.coluna_valor_pagto in self.dados_limpos.columns:
            # Calcular soma TOTAL e precisa
            self.total_pagamentos = self.dados_limpos[self.coluna_valor_pagto].sum()
            
            # Verificação extra: calcular também usando numpy para garantir
            total_numpy = np.sum(self.dados_limpos[self.coluna_valor_pagto].values)
            
            st.success(f"💰 Valor total calculado: R$ {self.total_pagamentos:,.2f}")
            st.info(f"✅ Verificação com numpy: R$ {total_numpy:,.2f}")
            
            # Mostrar alguns valores para debug
            with st.expander("🔍 Ver primeiros valores da coluna"):
                st.write(f"Coluna: {self.coluna_valor_pagto}")
                st.write(f"Primeiros 5 valores: {self.dados_limpos[self.coluna_valor_pagto].head(5).tolist()}")
                st.write(f"Média: R$ {self.dados_limpos[self.coluna_valor_pagto].mean():,.2f}")
                st.write(f"Contagem: {len(self.dados_limpos)} registros")
        else:
            st.error(f"❌ Coluna de valor não encontrada: {self.coluna_valor_pagto}")
            # Tentar encontrar qualquer coluna numérica
            colunas_numericas = self.dados_limpos.select_dtypes(include=[np.number]).columns
            if len(colunas_numericas) > 0:
                st.warning(f"Colunas numéricas disponíveis: {list(colunas_numericas)}")
                # Usar a primeira coluna numérica como fallback
                col_fallback = colunas_numericas[0]
                self.total_pagamentos = self.dados_limpos[col_fallback].sum()
                st.warning(f"⚠️ Usando coluna alternativa '{col_fallback}': R$ {self.total_pagamentos:,.2f}")

# Inicializar sistema
sistema = SistemaPOTStreamlit()

# ==============================================
# INTERFACE STREAMLIT - SIMPLIFICADA E FUNCIONAL
# ==============================================

st.title("💰 SISTEMA DE MONITORAMENTO DE PAGAMENTOS - POT")
st.markdown("---")

# Sidebar simplificada
with st.sidebar:
    st.header("📁 Upload do Arquivo")
    
    arquivo = st.file_uploader(
        "Selecione o arquivo CSV",
        type=['csv'],
        help="Arquivo CSV com delimitador ponto e vírgula"
    )
    
    if arquivo is not None:
        st.info(f"📄 **Arquivo:** {arquivo.name}")
        st.info(f"📊 **Tamanho:** {arquivo.size / 1024:.1f} KB")
        
        if st.button("🚀 PROCESSAR ARQUIVO", type="primary", use_container_width=True):
            with st.spinner("Processando..."):
                sucesso = sistema.processar_arquivo_streamlit(arquivo)
                if sucesso:
                    st.session_state['arquivo_processado'] = True
                    st.success("✅ Processado com sucesso!")
                else:
                    st.error("❌ Falha no processamento")
    
    if 'arquivo_processado' in st.session_state and st.session_state['arquivo_processado']:
        st.markdown("---")
        if st.button("🔄 Novo Arquivo", use_container_width=True):
            st.session_state.clear()
            st.rerun()

# Área principal
if 'arquivo_processado' in st.session_state and st.session_state['arquivo_processado']:
    if sistema.arquivo_processado and sistema.dados_limpos is not None and len(sistema.dados_limpos) > 0:
        
        # ============================
        # DASHBOARD PRINCIPAL
        # ============================
        st.header("📊 RESUMO DO PROCESSAMENTO")
        
        # Métricas principais em destaque
        st.markdown("### 📈 MÉTRICAS PRINCIPAIS")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                label="📄 Total de Registros",
                value=f"{len(sistema.dados_limpos):,}",
                help="Número total de pagamentos processados"
            )
        
        with col2:
            # VALOR TOTAL CORRETO
            if sistema.coluna_valor_pagto and sistema.coluna_valor_pagto in sistema.dados_limpos.columns:
                valor_total = sistema.dados_limpos[sistema.coluna_valor_pagto].sum()
                st.metric(
                    label="💰 Valor Total",
                    value=f"R$ {valor_total:,.2f}",
                    help=f"Soma da coluna '{sistema.coluna_valor_pagto}'"
                )
            else:
                st.metric(
                    label="💰 Valor Total",
                    value="N/A",
                    help="Coluna de valor não identificada"
                )
        
        with col3:
            if sistema.coluna_valor_pagto and sistema.coluna_valor_pagto in sistema.dados_limpos.columns:
                media = sistema.dados_limpos[sistema.coluna_valor_pagto].mean()
                st.metric(
                    label="📊 Valor Médio",
                    value=f"R$ {media:,.2f}",
                    help="Média por pagamento"
                )
            else:
                st.metric(
                    label="📊 Valor Médio",
                    value="N/A"
                )
        
        with col4:
            # Contar agências se existir coluna
            if 'agencia' in sistema.dados_limpos.columns:
                num_agencias = sistema.dados_limpos['agencia'].nunique()
                st.metric(
                    label="🏢 Agências",
                    value=num_agencias,
                    help="Número de agências distintas"
                )
            else:
                st.metric(
                    label="🏢 Agências",
                    value="N/A"
                )
        
        st.markdown("---")
        
        # ============================
        # VERIFICAÇÃO DO VALOR TOTAL
        # ============================
        st.subheader("✅ VERIFICAÇÃO DO CÁLCULO")
        
        if sistema.coluna_valor_pagto and sistema.coluna_valor_pagto in sistema.dados_limpos.columns:
            # Calcular de 3 formas diferentes para verificar
            col_a, col_b, col_c = st.columns(3)
            
            with col_a:
                st.markdown("**Método 1: Pandas Sum**")
                soma_pandas = sistema.dados_limpos[sistema.coluna_valor_pagto].sum()
                st.code(f"R$ {soma_pandas:,.2f}")
            
            with col_b:
                st.markdown("**Método 2: Numpy Sum**")
                soma_numpy = np.sum(sistema.dados_limpos[sistema.coluna_valor_pagto].values)
                st.code(f"R$ {soma_numpy:,.2f}")
            
            with col_c:
                st.markdown("**Método 3: Loop Manual**")
                soma_manual = 0
                for valor in sistema.dados_limpos[sistema.coluna_valor_pagto]:
                    try:
                        soma_manual += float(valor)
                    except:
                        pass
                st.code(f"R$ {soma_manual:,.2f}")
            
            # Verificar consistência
            if abs(soma_pandas - soma_numpy) < 0.01 and abs(soma_pandas - soma_manual) < 0.01:
                st.success("✅ Cálculos consistentes! O valor total está correto.")
            else:
                st.warning("⚠️ Pequena diferença nos cálculos (arredondamento).")
        
        st.markdown("---")
        
        # ============================
        # VISUALIZAÇÃO DOS DADOS
        # ============================
        st.subheader("👀 VISUALIZAÇÃO DOS DADOS")
        
        # Selecionar colunas para visualizar
        todas_colunas = sistema.dados_limpos.columns.tolist()
        colunas_selecionadas = st.multiselect(
            "Selecione as colunas para visualizar:",
            options=todas_colunas,
            default=todas_colunas[:min(6, len(todas_colunas))]
        )
        
        # Número de linhas
        num_linhas = st.slider("Número de linhas para mostrar:", 5, 100, 20)
        
        if colunas_selecionadas:
            dados_visiveis = sistema.dados_limpos[colunas_selecionadas].head(num_linhas).copy()
            
            # Formatar valores monetários
            for col in dados_visiveis.columns:
                if col == sistema.coluna_valor_pagto or 'valor' in col.lower():
                    dados_visiveis[col] = dados_visiveis[col].apply(lambda x: f"R$ {x:,.2f}" if pd.notna(x) else "")
            
            st.dataframe(dados_visiveis, use_container_width=True, height=400)
        
        st.markdown("---")
        
        # ============================
        # ANÁLISE POR AGÊNCIA
        # ============================
        if 'agencia' in sistema.dados_limpos.columns and sistema.coluna_valor_pagto:
            st.subheader("🏢 ANÁLISE POR AGÊNCIA")
            
            # Top 10 agências por valor
            analise_agencia = sistema.dados_limpos.groupby('agencia').agg({
                sistema.coluna_valor_pagto: ['sum', 'count', 'mean']
            }).round(2)
            
            analise_agencia.columns = ['Valor Total', 'Quantidade', 'Média']
            analise_agencia = analise_agencia.sort_values('Valor Total', ascending=False)
            
            col_ag1, col_ag2 = st.columns(2)
            
            with col_ag1:
                st.markdown("**Top 5 Agências por Valor Total:**")
                top5 = analise_agencia.head(5).copy()
                top5['Valor Total'] = top5['Valor Total'].apply(lambda x: f"R$ {x:,.2f}")
                top5['Média'] = top5['Média'].apply(lambda x: f"R$ {x:,.2f}")
                st.dataframe(top5, use_container_width=True)
            
            with col_ag2:
                st.markdown("**Distribuição por Agência:**")
                st.write(f"Total de agências: {len(analise_agencia)}")
                st.write(f"Agência com maior valor: {analise_agencia.index[0]}")
                st.write(f"Valor da maior agência: R$ {analise_agencia.iloc[0]['Valor Total']:,.2f}")
        
        st.markdown("---")
        
        # ============================
        # ESTATÍSTICAS DETALHADAS
        # ============================
        if sistema.coluna_valor_pagto:
            st.subheader("📈 ESTATÍSTICAS DETALHADAS")
            
            col_stats1, col_stats2 = st.columns(2)
            
            with col_stats1:
                st.markdown(f"**Estatísticas de '{sistema.coluna_valor_pagto}':**")
                stats = sistema.dados_limpos[sistema.coluna_valor_pagto].describe()
                
                stats_df = pd.DataFrame({
                    'Estatística': ['Mínimo', '25% (Q1)', 'Mediana', '75% (Q3)', 'Máximo', 'Média', 'Desvio Padrão'],
                    'Valor': [
                        f"R$ {stats.get('min', 0):,.2f}",
                        f"R$ {stats.get('25%', 0):,.2f}",
                        f"R$ {stats.get('50%', 0):,.2f}",
                        f"R$ {stats.get('75%', 0):,.2f}",
                        f"R$ {stats.get('max', 0):,.2f}",
                        f"R$ {stats.get('mean', 0):,.2f}",
                        f"R$ {stats.get('std', 0):,.2f}"
                    ]
                })
                st.dataframe(stats_df, use_container_width=True, hide_index=True)
            
            with col_stats2:
                # Histograma simples usando HTML
                st.markdown("**Distribuição de Valores:**")
                
                # Classificar valores em faixas
                if sistema.coluna_valor_pagto in sistema.dados_limpos.columns:
                    valores = sistema.dados_limpos[sistema.coluna_valor_pagto]
                    min_val = valores.min()
                    max_val = valores.max()
                    
                    # Criar faixas
                    faixas = pd.cut(valores, bins=5)
                    contagem = faixas.value_counts().sort_index()
                    
                    for intervalo, count in contagem.items():
                        percent = (count / len(valores)) * 100
                        st.write(f"{intervalo}: {count} pagamentos ({percent:.1f}%)")
        
        st.markdown("---")
        
        # ============================
        # DOWNLOAD DE DADOS
        # ============================
        st.subheader("📥 EXPORTAR DADOS")
        
        col_dl1, col_dl2, col_dl3 = st.columns(3)
        
        with col_dl1:
            # Download CSV
            csv = sistema.dados_limpos.to_csv(index=False, sep=';', encoding='utf-8')
            st.download_button(
                label="📥 Download CSV",
                data=csv,
                file_name=f"dados_processados_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col_dl2:
            # Download Excel
            try:
                output = sistema.dados_limpos.to_excel(index=False)
                st.download_button(
                    label="📥 Download Excel",
                    data=output,
                    file_name=f"dados_processados_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            except:
                st.button("📥 Download Excel (não disponível)", disabled=True, use_container_width=True)
        
        with col_dl3:
            # Copiar resumo
            if st.button("📋 Copiar Resumo", use_container_width=True):
                resumo = f"""
                RESUMO POT - {datetime.now().strftime('%d/%m/%Y %H:%M')}
                Arquivo: {sistema.nome_arquivo}
                Registros: {len(sistema.dados_limpos):,}
                Valor Total: R$ {sistema.total_pagamentos:,.2f}
                """
                st.code(resumo)
    
    else:
        st.error("❌ Erro: Dados não processados corretamente.")
else:
    # Tela inicial
    st.markdown("""
    # 🚀 SISTEMA DE MONITORAMENTO POT
    
    ### 📋 **Funcionalidades:**
    
    1. **Processamento automático** de arquivos CSV com encoding variável
    2. **Cálculo preciso** de valores totais de pagamentos
    3. **Identificação automática** da coluna de valor de pagamento
    4. **Dashboard interativo** com métricas principais
    5. **Exportação** em CSV e Excel
    
    ### 📁 **Como usar:**
    
    1. **Faça upload** do arquivo CSV na barra lateral
    2. **Clique em "Processar Arquivo"**
    3. **Verifique** as métricas calculadas
    4. **Explore** os dados com as ferramentas disponíveis
    
    ### ⚠️ **Formato esperado:**
    
    - Arquivo CSV com **delimitador ponto e vírgula (;)**
    - Coluna de **Valor Pagto** com valores no formato brasileiro (R$ 1.593,90)
    - **Encoding comum:** Latin-1 (ISO-8859-1) ou UTF-8
    """)
    
    st.markdown("---")
    
    # Exemplo de formato esperado
    with st.expander("📋 Exemplo do formato de arquivo esperado"):
        st.code("""
        Ordem;Projeto;Num Cartao;Nome;Distrito;Agencia;RG;Valor Total;Valor Desconto;Valor Pagto;Data Pagto;Valor Dia;Dias a apagar
        1;ABASTECE;364363;PRISCILA REGINA DE OLIVEIRA;0;1530;;R$ 1.593,90;R$ 0,00;R$ 1.593,90;20/10/2025;R$ 53,13;30
        2;ABASTECE;364629;NADIA SOUSA DA COSTA;0;3107;;R$ 1.593,90;R$ 0,00;R$ 1.593,90;20/10/2025;R$ 53,13;30
        """)

# ==============================================
# RODAPÉ
# ==============================================
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: gray; padding: 10px;'>
    <strong>Sistema POT - Monitoramento de Pagamentos</strong> • 
    Cálculo Correto de Valores • 
    Versão 4.0 • 
    Desenvolvido para precisão
    </div>
    """,
    unsafe_allow_html=True
)

# Configurações auxiliares
encoding_map = {
    'ISO-8859-1': 'latin-1',
    'Windows-1252': 'cp1252',
    'ascii': 'utf-8',
    'UTF-8-SIG': 'utf-8'
}
