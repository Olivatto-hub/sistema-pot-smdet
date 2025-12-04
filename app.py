import pandas as pd
import os
import re
from datetime import datetime
import streamlit as st
import warnings
import chardet
import numpy as np
import io
import traceback
from typing import Dict, List, Any

warnings.filterwarnings('ignore')

# Configuração da página
st.set_page_config(
    page_title="Sistema POT - Monitoramento de Pagamentos",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS personalizados
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1E3A8A;
        text-align: center;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.5rem;
        color: #2563EB;
        margin-top: 1rem;
        margin-bottom: 1rem;
        border-bottom: 2px solid #E5E7EB;
        padding-bottom: 0.5rem;
    }
    .metric-card {
        background-color: #F8FAFC;
        border-radius: 10px;
        padding: 1rem;
        border: 1px solid #E2E8F0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    .alert-card {
        background-color: #FEF2F2;
        border: 1px solid #FCA5A5;
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 1rem;
    }
    .success-card {
        background-color: #F0FDF4;
        border: 1px solid #86EFAC;
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 1rem;
    }
    .info-card {
        background-color: #EFF6FF;
        border: 1px solid #93C5FD;
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 1rem;
    }
    .critical-row {
        background-color: #FEE2E2 !important;
    }
    .warning-row {
        background-color: #FEF3C7 !important;
    }
    .data-table {
        font-size: 0.9rem;
    }
</style>
""", unsafe_allow_html=True)

class SistemaPOT:
    def __init__(self):
        self.df = None
        self.df_original = None
        self.dados_limpos = None
        self.dados_faltantes = None
        self.inconsistencias = None
        self.registros_problematicos = None
        self.arquivo_processado = False
        self.nome_arquivo = ""
        self.total_pagamentos = 0
        self.coluna_valor_pagto = None
        self.log_processamento = []
        self.erros_detalhados = []
        self.linha_original_offset = 0  # Offset para mapear linha original
    
    def log(self, mensagem):
        """Registra mensagem no log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_processamento.append(f"[{timestamp}] {mensagem}")
    
    def registrar_erro(self, tipo_erro, coluna, valor, linha_original, descricao):
        """Registra erro detalhado com linha original"""
        self.erros_detalhados.append({
            'Tipo_Erro': tipo_erro,
            'Coluna': coluna,
            'Valor_Problema': str(valor)[:50],
            'Linha_Original': linha_original,
            'Descricao': descricao,
            'Timestamp': datetime.now().strftime("%H:%M:%S")
        })
    
    def detectar_encoding(self, arquivo_path):
        """Detecta o encoding do arquivo"""
        try:
            with open(arquivo_path, 'rb') as f:
                raw_data = f.read(10000)
            resultado = chardet.detect(raw_data)
            encoding = resultado['encoding']
            confianca = resultado['confidence']
            self.log(f"Encoding detectado: {encoding} (confiança: {confianca:.2f})")
            return encoding if encoding else 'latin-1'
        except Exception as e:
            self.log(f"Erro na detecção de encoding: {e}")
            return 'latin-1'
    
    def tentar_encodings(self, arquivo_path):
        """Tenta diferentes encodings até encontrar um que funcione"""
        encodings = ['latin-1', 'iso-8859-1', 'cp1252', 'utf-8', 'utf-8-sig', 'cp850']
        
        for encoding in encodings:
            try:
                self.log(f"Tentando encoding: {encoding}")
                df = pd.read_csv(arquivo_path, delimiter=';', encoding=encoding, nrows=5, on_bad_lines='skip')
                if not df.empty and len(df.columns) > 1:
                    self.log(f"✅ Encoding funcionou: {encoding}")
                    return encoding
            except Exception as e:
                self.log(f"❌ Encoding {encoding} falhou: {str(e)[:50]}")
                continue
        
        self.log("❌ Nenhum encoding comum funcionou")
        return None
    
    def eh_data(self, valor_str):
        """Verifica se uma string parece ser uma data"""
        if pd.isna(valor_str) or not isinstance(valor_str, str):
            return False
        
        valor_str = str(valor_str).strip()
        
        # Padrões de data
        padroes_data = [
            r'^\d{1,2}/\d{1,2}/\d{4}$',      # DD/MM/AAAA
            r'^\d{1,2}-\d{1,2}-\d{4}$',      # DD-MM-AAAA
            r'^\d{4}-\d{1,2}-\d{1,2}$',      # AAAA-MM-DD
            r'^\d{1,2}/\d{1,2}/\d{2}$',      # DD/MM/AA
            r'^\d{1,2}-\d{1,2}-\d{2}$',      # DD-MM-AA
            r'^\d{1,2}\.\d{1,2}\.\d{4}$',    # DD.MM.AAAA
            r'^\d{8}$',                       # AAAAMMDD
        ]
        
        for padrao in padroes_data:
            if re.match(padrao, valor_str):
                return True
        
        return False
    
    def converter_valor_monetario(self, valor_str, linha_original, coluna):
        """Converte valores monetários do formato brasileiro para float"""
        if pd.isna(valor_str) or valor_str == '' or str(valor_str).strip() == '':
            return 0.0
        
        valor_original = str(valor_str).strip()
        
        try:
            # Se for um número, retorna direto
            if isinstance(valor_str, (int, float, np.number)):
                return float(valor_str)
            
            # Verifica se é uma data - NÃO CONVERTE
            if self.eh_data(valor_original):
                return valor_original  # Mantém como string
            
            # Tenta converter direto para float
            try:
                return float(valor_original)
            except:
                pass
            
            # Remove símbolos de moeda
            valor_limpo = valor_original.replace('R$', '').replace('US$', '').replace(' ', '').strip()
            
            if valor_limpo == '':
                return 0.0
            
            # Substitui ponto e vírgula por ponto
            valor_limpo = valor_limpo.replace(';', '.')
            
            # Formato brasileiro: 1.234,56
            if '.' in valor_limpo and ',' in valor_limpo:
                # Remove pontos de milhar
                if valor_limpo.count('.') > 1:
                    partes = valor_limpo.split(',')
                    if len(partes) == 2:
                        inteiro = partes[0].replace('.', '')
                        decimal = partes[1]
                        return float(f"{inteiro}.{decimal}")
            
            # Formato com vírgula decimal
            elif ',' in valor_limpo:
                partes = valor_limpo.split(',')
                if len(partes) == 2 and len(partes[1]) <= 3:
                    return float(valor_limpo.replace(',', '.'))
                else:
                    return float(valor_limpo.replace(',', ''))
            
            # Formato com ponto
            elif '.' in valor_limpo:
                partes = valor_limpo.split('.')
                if len(partes) == 2 and len(partes[1]) <= 3:
                    return float(valor_limpo)
                else:
                    return float(valor_limpo.replace('.', ''))
            
            else:
                return float(valor_limpo)
                
        except Exception as e:
            # Registra erro de conversão
            self.registrar_erro(
                "Erro de Conversão",
                coluna,
                valor_original,
                linha_original,
                f"Não foi possível converter para valor monetário: {str(e)[:100]}"
            )
            return 0.0
    
    def processar_arquivo_streamlit(self, arquivo_upload):
        """Processa arquivo CSV de pagamentos do POT"""
        try:
            self.log_processamento = []
            self.erros_detalhados = []
            self.log(f"Iniciando processamento do arquivo: {arquivo_upload.name}")
            
            # Salva arquivo temporariamente
            temp_path = f"temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            with open(temp_path, 'wb') as f:
                f.write(arquivo_upload.getvalue())
            
            self.log(f"Arquivo salvo temporariamente em: {temp_path}")
            
            # Detecta encoding
            encoding = self.tentar_encodings(temp_path)
            if encoding is None:
                encoding = self.detectar_encoding(temp_path) or 'latin-1'
            
            self.log(f"Encoding selecionado: {encoding}")
            
            # Lê o arquivo mantendo o índice original
            try:
                self.df = pd.read_csv(
                    temp_path, 
                    delimiter=';', 
                    encoding=encoding, 
                    on_bad_lines='skip',
                    dtype=str,
                    quoting=3,
                    low_memory=False
                )
                
                # Adiciona coluna com linha original (considerando header)
                self.df['__linha_original'] = range(2, len(self.df) + 2)
                self.log(f"✅ Arquivo lido. Total de linhas: {len(self.df)}")
                
            except Exception as e:
                self.log(f"❌ Erro ao ler com pandas: {e}")
                # Tenta leitura manual
                with open(temp_path, 'r', encoding=encoding, errors='replace') as f:
                    linhas = f.readlines()
                
                if len(linhas) > 1:
                    colunas = linhas[0].strip().split(';')
                    dados = []
                    for i, linha in enumerate(linhas[1:], 2):  # i começa em 2 (após header)
                        try:
                            valores = linha.strip().split(';')
                            if len(valores) >= len(colunas) - 1:
                                while len(valores) < len(colunas):
                                    valores.append('')
                                valores.append(str(i))  # Adiciona linha original
                                dados.append(valores)
                        except:
                            continue
                    
                    colunas.append('__linha_original')
                    self.df = pd.DataFrame(dados, columns=colunas)
                    self.log(f"DataFrame criado manualmente. Linhas: {len(self.df)}")
                else:
                    self.log("❌ Nenhuma linha válida encontrada")
                    return False
            
            self.df_original = self.df.copy()
            
            # Remove arquivo temporário
            if os.path.exists(temp_path):
                os.remove(temp_path)
            
            # Processa os dados
            self._limpar_dados()
            self._analisar_dados_faltantes()
            self._analisar_inconsistencias()
            self._identificar_registros_problematicos()
            self._calcular_estatisticas()
            
            self.arquivo_processado = True
            self.nome_arquivo = arquivo_upload.name
            
            self.log("✅ Processamento concluído com sucesso!")
            return True
            
        except Exception as e:
            self.log(f"❌ ERRO CRÍTICO NO PROCESSAMENTO: {e}")
            self.log(f"Traceback: {traceback.format_exc()}")
            return False
    
    def _limpar_dados(self):
        """Limpa e prepara os dados para análise"""
        self.log("Iniciando limpeza de dados...")
        
        if self.df is None or self.df.empty:
            self.log("❌ DataFrame vazio")
            return
        
        df_limpo = self.df.copy()
        
        # Remove linhas totalmente vazias
        linhas_iniciais = len(df_limpo)
        colunas_sem_linha_original = [c for c in df_limpo.columns if c != '__linha_original']
        df_limpo = df_limpo.dropna(subset=colunas_sem_linha_original, how='all')
        linhas_apos_vazias = len(df_limpo)
        removidas = linhas_iniciais - linhas_apos_vazias
        if removidas > 0:
            self.log(f"Removidas {removidas} linhas totalmente vazias")
        
        # Normaliza nomes das colunas
        mapeamento_colunas = {}
        for col in df_limpo.columns:
            if pd.isna(col) or str(col).strip() == '':
                col_novo = 'coluna_sem_nome'
            else:
                col_novo = str(col).strip().lower()
                col_novo = re.sub(r'[^a-z0-9_]', '_', col_novo)
                col_novo = (col_novo
                           .replace('á', 'a').replace('é', 'e').replace('í', 'i')
                           .replace('ó', 'o').replace('ú', 'u').replace('â', 'a')
                           .replace('ê', 'e').replace('î', 'i').replace('ô', 'o')
                           .replace('û', 'u').replace('ã', 'a').replace('õ', 'o')
                           .replace('ç', 'c'))
            
            mapeamento_colunas[col] = col_novo
        
        df_limpo = df_limpo.rename(columns=mapeamento_colunas)
        
        # Identifica coluna de valor
        possiveis_nomes_valor = [
            'valor_pagto', 'valor_pagamento', 'valor_total', 'valor', 
            'pagto', 'pagamento', 'total', 'valorpagto', 'valor_pgto',
            'valorpagamento', 'vlr_pagto', 'vlr_pagamento', 'vlr_total',
            'valor_do_pagamento', 'val_pagto'
        ]
        
        self.coluna_valor_pagto = None
        for nome in possiveis_nomes_valor:
            if nome in df_limpo.columns:
                self.coluna_valor_pagto = nome
                self.log(f"✅ Coluna de valor identificada: {nome}")
                break
        
        # Converte valores monetários
        if self.coluna_valor_pagto and self.coluna_valor_pagto in df_limpo.columns:
            self.log(f"Convertendo valores da coluna: {self.coluna_valor_pagto}")
            
            for idx, row in df_limpo.iterrows():
                linha_original = row.get('__linha_original', idx + 2)
                valor_original = row[self.coluna_valor_pagto]
                
                if pd.notna(valor_original):
                    valor_convertido = self.converter_valor_monetario(
                        valor_original, 
                        linha_original, 
                        self.coluna_valor_pagto
                    )
                    df_limpo.at[idx, self.coluna_valor_pagto] = valor_convertido
        
        self.dados_limpos = df_limpo
        self.log(f"✅ Dados limpos: {len(df_limpo)} linhas, {len(df_limpo.columns)} colunas")
    
    def _analisar_dados_faltantes(self):
        """Analisa dados faltantes no dataset"""
        self.log("Analisando dados faltantes...")
        
        if self.dados_limpos is None or self.dados_limpos.empty:
            self.log("❌ Nenhum dado para análise de faltantes")
            return
        
        # Ignora coluna de linha original na análise
        colunas_analise = [c for c in self.dados_limpos.columns if c != '__linha_original']
        
        faltantes_por_coluna = self.dados_limpos[colunas_analise].isnull().sum()
        percentual_faltantes = (faltantes_por_coluna / len(self.dados_limpos)) * 100
        
        self.dados_faltantes = pd.DataFrame({
            'Coluna': faltantes_por_coluna.index,
            'Valores_Faltantes': faltantes_por_coluna.values,
            'Percentual_Faltante': percentual_faltantes.values.round(2),
            'Tipo_Dado': [str(self.dados_limpos[col].dtype) for col in colunas_analise]
        })
        
        self.log(f"Dados faltantes analisados: {len(faltantes_por_coluna)} colunas")
    
    def _analisar_inconsistencias(self):
        """Analisa inconsistências nos dados"""
        self.log("Analisando inconsistências...")
        
        if self.dados_limpos is None or self.dados_limpos.empty:
            self.log("❌ Nenhum dado para análise de inconsistências")
            return
        
        inconsistencias = []
        
        # 1. Valores negativos
        if self.coluna_valor_pagto and self.coluna_valor_pagto in self.dados_limpos.columns:
            negativos = self.dados_limpos[self.dados_limpos[self.coluna_valor_pagto] < 0]
            if len(negativos) > 0:
                for idx, row in negativos.iterrows():
                    linha_original = row.get('__linha_original', idx + 2)
                    self.registrar_erro(
                        "Valor Negativo",
                        self.coluna_valor_pagto,
                        row[self.coluna_valor_pagto],
                        linha_original,
                        "Valor de pagamento negativo"
                    )
                
                inconsistencias.append({
                    'Tipo': 'Valores Negativos',
                    'Coluna': self.coluna_valor_pagto,
                    'Quantidade': len(negativos),
                    'Descrição': 'Valores de pagamento negativos'
                })
        
        # 2. Valores zerados
        if self.coluna_valor_pagto and self.coluna_valor_pagto in self.dados_limpos.columns:
            zerados = self.dados_limpos[self.dados_limpos[self.coluna_valor_pagto] == 0]
            if len(zerados) > 0:
                for idx, row in zerados.iterrows():
                    linha_original = row.get('__linha_original', idx + 2)
                    self.registrar_erro(
                        "Valor Zerado",
                        self.coluna_valor_pagto,
                        row[self.coluna_valor_pagto],
                        linha_original,
                        "Valor de pagamento zerado"
                    )
                
                inconsistencias.append({
                    'Tipo': 'Valores Zerados',
                    'Coluna': self.coluna_valor_pagto,
                    'Quantidade': len(zerados),
                    'Descrição': 'Valores de pagamento zerados'
                })
        
        # 3. Dados críticos faltantes
        colunas_criticas = ['nome', 'cpf', 'cnpj', 'agencia', 'conta', 'banco']
        for coluna in colunas_criticas:
            if coluna in self.dados_limpos.columns:
                faltantes = self.dados_limpos[self.dados_limpos[coluna].isnull()]
                if len(faltantes) > 0:
                    for idx, row in faltantes.iterrows():
                        linha_original = row.get('__linha_original', idx + 2)
                        self.registrar_erro(
                            "Dado Crítico Faltante",
                            coluna,
                            "",
                            linha_original,
                            f"{coluna.upper()} não informado"
                        )
                    
                    inconsistencias.append({
                        'Tipo': f'{coluna.upper()} Faltante',
                        'Coluna': coluna,
                        'Quantidade': len(faltantes),
                        'Descrição': f'{coluna} não informado'
                    })
        
        if inconsistencias:
            self.inconsistencias = pd.DataFrame(inconsistencias)
            self.log(f"Inconsistências detectadas: {len(inconsistencias)} tipos")
        else:
            self.inconsistencias = pd.DataFrame()
            self.log("Nenhuma inconsistência detectada")
    
    def _identificar_registros_problematicos(self):
        """Identifica registros problemáticos com todos os detalhes"""
        self.log("Identificando registros problemáticos...")
        
        if self.dados_limpos is None or len(self.dados_limpos) == 0:
            return
        
        registros_problematicos = []
        
        # Verifica cada linha
        for idx, row in self.dados_limpos.iterrows():
            linha_original = row.get('__linha_original', idx + 2)
            problemas = []
            nivel_severidade = "BAIXA"
            
            # Verifica valores negativos
            if self.coluna_valor_pagto and self.coluna_valor_pagto in row:
                valor = row[self.coluna_valor_pagto]
                if isinstance(valor, (int, float)):
                    if valor < 0:
                        problemas.append("VALOR NEGATIVO")
                        nivel_severidade = "CRÍTICA"
                    elif valor == 0:
                        problemas.append("VALOR ZERADO")
                        nivel_severidade = "ALTA"
            
            # Verifica dados críticos faltantes
            for coluna in ['nome', 'cpf', 'cnpj']:
                if coluna in row and pd.isna(row[coluna]):
                    problemas.append(f"{coluna.upper()} FALTANTE")
                    nivel_severidade = "ALTA"
            
            if problemas:
                registro = {
                    'Linha_Original': int(linha_original),
                    'Problemas': ', '.join(problemas),
                    'Severidade': nivel_severidade
                }
                
                # Adiciona informações do registro
                for col in self.dados_limpos.columns:
                    if col not in ['__linha_original']:
                        valor = row[col]
                        if pd.isna(valor):
                            registro[col] = ''
                        elif isinstance(valor, (int, float)):
                            if col == self.coluna_valor_pagto:
                                registro[col] = f"R$ {valor:,.2f}"
                            else:
                                registro[col] = f"{valor:,.2f}"
                        else:
                            registro[col] = str(valor)[:50]
                
                registros_problematicos.append(registro)
        
        if registros_problematicos:
            self.registros_problematicos = pd.DataFrame(registros_problematicos)
            self.log(f"Registros problemáticos identificados: {len(registros_problematicos)}")
        else:
            self.registros_problematicos = pd.DataFrame()
            self.log("Nenhum registro problemático identificado")
    
    def _calcular_estatisticas(self):
        """Calcula estatísticas dos dados"""
        self.log("Calculando estatísticas...")
        
        if self.dados_limpos is None or len(self.dados_limpos) == 0:
            self.log("❌ Nenhum dado para cálculo de estatísticas")
            return
        
        if self.coluna_valor_pagto and self.coluna_valor_pagto in self.dados_limpos.columns:
            try:
                valores = self.dados_limpos[self.coluna_valor_pagto]
                valores_numericos = pd.to_numeric(valores, errors='coerce').dropna()
                
                if len(valores_numericos) > 0:
                    self.total_pagamentos = valores_numericos.sum()
                    
                    self.log(f"💰 Valor total: R$ {self.total_pagamentos:,.2f}")
                    self.log(f"  - Média: R$ {valores_numericos.mean():,.2f}")
                    self.log(f"  - Mínimo: R$ {valores_numericos.min():,.2f}")
                    self.log(f"  - Máximo: R$ {valores_numericos.max():,.2f}")
                    self.log(f"  - Mediana: R$ {valores_numericos.median():,.2f}")
                else:
                    self.log("⚠️ Nenhum valor numérico encontrado na coluna de pagamento")
                    self.total_pagamentos = 0
                    
            except Exception as e:
                self.log(f"Erro ao calcular estatísticas: {e}")
                self.total_pagamentos = 0
        else:
            self.log("⚠️ Coluna de valor não disponível para cálculo")
            self.total_pagamentos = 0
    
    def mostrar_log(self):
        """Mostra log de processamento"""
        if self.log_processamento:
            with st.expander("📝 LOG DE PROCESSAMENTO", expanded=False):
                for entry in self.log_processamento:
                    if "❌" in entry or "ERRO" in entry.upper():
                        st.error(entry)
                    elif "⚠️" in entry or "AVISO" in entry.upper():
                        st.warning(entry)
                    elif "✅" in entry or "SUCESSO" in entry.upper():
                        st.success(entry)
                    else:
                        st.info(entry)
    
    def mostrar_resumo_executivo(self):
        """Mostra resumo executivo dos dados"""
        if not self.arquivo_processado or self.dados_limpos is None:
            return
        
        st.markdown('<div class="sub-header">📊 RESUMO EXECUTIVO</div>', unsafe_allow_html=True)
        
        # Métricas principais
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.metric("📄 TOTAL DE REGISTROS", f"{len(self.dados_limpos):,}")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with col2:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            if self.coluna_valor_pagto and self.total_pagamentos > 0:
                st.metric("💰 VALOR TOTAL", f"R$ {self.total_pagamentos:,.2f}")
            else:
                st.metric("💰 VALOR TOTAL", "N/A")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with col3:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            total_erros = len(self.erros_detalhados)
            st.metric("🚨 ERROS DETECTADOS", f"{total_erros:,}")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with col4:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            if self.registros_problematicos is not None and not self.registros_problematicos.empty:
                total_problematicos = len(self.registros_problematicos)
                st.metric("⚠️ REGISTROS PROBLEMÁTICOS", f"{total_problematicos:,}")
            else:
                st.metric("⚠️ REGISTROS PROBLEMÁTICOS", "0")
            st.markdown('</div>', unsafe_allow_html=True)
        
        # Informações adicionais
        if self.coluna_valor_pagto and self.coluna_valor_pagto in self.dados_limpos.columns:
            col_info1, col_info2, col_info3 = st.columns(3)
            
            with col_info1:
                st.markdown('<div class="info-card">', unsafe_allow_html=True)
                st.write(f"**Coluna de Valor:** `{self.coluna_valor_pagto}`")
                st.markdown('</div>', unsafe_allow_html=True)
            
            with col_info2:
                st.markdown('<div class="info-card">', unsafe_allow_html=True)
                st.write(f"**Total de Colunas:** {len(self.dados_limpos.columns) - 1}")
                st.markdown('</div>', unsafe_allow_html=True)
            
            with col_info3:
                st.markdown('<div class="info-card">', unsafe_allow_html=True)
                st.write(f"**Arquivo:** {self.nome_arquivo}")
                st.markdown('</div>', unsafe_allow_html=True)
    
    def mostrar_erros_detalhados(self):
        """Mostra erros detalhados com linha original"""
        if not self.erros_detalhados:
            st.markdown('<div class="success-card">✅ NENHUM ERRO DE CONVERSÃO DETECTADO</div>', unsafe_allow_html=True)
            return
        
        st.markdown('<div class="sub-header">🚨 ERROS DE CONVERSÃO DETALHADOS</div>', unsafe_allow_html=True)
        
        df_erros = pd.DataFrame(self.erros_detalhados)
        
        # Agrupa por tipo de erro para melhor visualização
        with st.expander("📋 VISÃO GERAL DOS ERROS", expanded=True):
            col1, col2 = st.columns(2)
            
            with col1:
                erro_por_tipo = df_erros['Tipo_Erro'].value_counts()
                st.bar_chart(erro_por_tipo)
            
            with col2:
                st.dataframe(
                    erro_por_tipo.reset_index().rename(columns={'index': 'Tipo de Erro', 'Tipo_Erro': 'Quantidade'}),
                    use_container_width=True,
                    hide_index=True
                )
        
        # Mostra todos os erros detalhados
        with st.expander("🔍 DETALHES COMPLETOS DOS ERROS", expanded=False):
            st.dataframe(
                df_erros[['Linha_Original', 'Tipo_Erro', 'Coluna', 'Valor_Problema', 'Descricao', 'Timestamp']],
                use_container_width=True,
                height=400
            )
    
    def mostrar_registros_problematicos(self):
        """Mostra registros problemáticos com linha original"""
        if self.registros_problematicos is None or self.registros_problematicos.empty:
            st.markdown('<div class="success-card">✅ NENHUM REGISTRO PROBLEMÁTICO IDENTIFICADO</div>', unsafe_allow_html=True)
            return
        
        st.markdown('<div class="sub-header">⚠️ REGISTROS PROBLEMÁTICOS</div>', unsafe_allow_html=True)
        
        # Filtros
        col_filtro1, col_filtro2 = st.columns(2)
        
        with col_filtro1:
            severidades = self.registros_problematicos['Severidade'].unique()
            severidade_selecionada = st.multiselect(
                "Filtrar por Severidade:",
                options=severidades,
                default=severidades
            )
        
        with col_filtro2:
            linhas_mostrar = st.slider(
                "Linhas para mostrar:",
                min_value=5,
                max_value=min(100, len(self.registros_problematicos)),
                value=min(20, len(self.registros_problematicos)),
                step=5
            )
        
        # Aplica filtros
        df_filtrado = self.registros_problematicos[
            self.registros_problematicos['Severidade'].isin(severidade_selecionada)
        ]
        
        if df_filtrado.empty:
            st.info("Nenhum registro encontrado com os filtros selecionados.")
            return
        
        # Mostra tabela com formatação condicional
        st.dataframe(
            df_filtrado.head(linhas_mostrar),
            use_container_width=True,
            height=500
        )
        
        # Botão para exportar
        if st.button("📥 EXPORTAR REGISTROS PROBLEMÁTICOS", use_container_width=True):
            csv_data = df_filtrado.to_csv(index=False, sep=';', encoding='utf-8')
            st.download_button(
                label="Baixar CSV",
                data=csv_data,
                file_name=f"registros_problematicos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
    
    def mostrar_estatisticas_valores(self):
        """Mostra estatísticas detalhadas dos valores"""
        if not self.coluna_valor_pagto or self.coluna_valor_pagto not in self.dados_limpos.columns:
            return
        
        st.markdown('<div class="sub-header">📈 ESTATÍSTICAS DE VALORES</div>', unsafe_allow_html=True)
        
        valores = pd.to_numeric(self.dados_limpos[self.coluna_valor_pagto], errors='coerce').dropna()
        
        if len(valores) == 0:
            st.warning("Nenhum valor numérico encontrado para análise.")
            return
        
        col_stat1, col_stat2, col_stat3 = st.columns(3)
        
        with col_stat1:
            st.metric("📊 Valor Médio", f"R$ {valores.mean():,.2f}")
        
        with col_stat2:
            st.metric("⬇️ Valor Mínimo", f"R$ {valores.min():,.2f}")
        
        with col_stat3:
            st.metric("⬆️ Valor Máximo", f"R$ {valores.max():,.2f}")
        
        # Distribuição de valores
        with st.expander("📊 DISTRIBUIÇÃO DE VALORES", expanded=True):
            fig_col1, fig_col2 = st.columns(2)
            
            with fig_col1:
                st.bar_chart(
                    pd.cut(valores, bins=10).value_counts().sort_index(),
                    use_container_width=True
                )
            
            with fig_col2:
                # Tabela de estatísticas
                stats = valores.describe()
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

# ==============================================
# FUNÇÃO PRINCIPAL
# ==============================================

def main():
    """Função principal do aplicativo Streamlit"""
    
    # Cabeçalho principal
    st.markdown('<h1 class="main-header">💰 SISTEMA DE MONITORAMENTO DE PAGAMENTOS - POT</h1>', unsafe_allow_html=True)
    
    # Inicializar sistema no session_state
    if 'sistema' not in st.session_state:
        st.session_state['sistema'] = SistemaPOT()
    
    sistema = st.session_state['sistema']
    
    # Sidebar
    with st.sidebar:
        st.markdown("---")
        st.markdown("### 📁 UPLOAD DO ARQUIVO")
        
        arquivo = st.file_uploader(
            "Selecione o arquivo CSV",
            type=['csv'],
            help="Arquivo CSV com dados de pagamentos (delimitador: ponto e vírgula)",
            key="file_uploader"
        )
        
        if arquivo is not None:
            st.markdown('<div class="info-card">', unsafe_allow_html=True)
            st.write(f"**Arquivo:** {arquivo.name}")
            st.write(f"**Tamanho:** {arquivo.size / 1024:.1f} KB")
            st.markdown('</div>', unsafe_allow_html=True)
            
            st.markdown("---")
            st.markdown("### ⚙️ OPÇÕES")
            
            mostrar_log = st.checkbox("📝 Mostrar log de processamento", value=False)
            
            col_op1, col_op2 = st.columns(2)
            with col_op1:
                mostrar_detalhes = st.checkbox("🔍 Detalhes dos erros", value=True)
            with col_op2:
                mostrar_dados = st.checkbox("📋 Dados completos", value=False)
            
            st.markdown("---")
            
            if st.button("🚀 PROCESSAR ARQUIVO", type="primary", use_container_width=True):
                with st.spinner("Processando arquivo... Por favor, aguarde."):
                    sucesso = sistema.processar_arquivo_streamlit(arquivo)
                    if sucesso:
                        st.session_state['arquivo_processado'] = True
                        st.session_state['mostrar_log'] = mostrar_log
                        st.session_state['mostrar_detalhes'] = mostrar_detalhes
                        st.session_state['mostrar_dados'] = mostrar_dados
                        st.session_state['sistema'] = sistema
                        st.success("✅ Arquivo processado com sucesso!")
                        st.rerun()
                    else:
                        st.error("❌ Erro ao processar arquivo.")
            
            if st.session_state.get('arquivo_processado', False):
                st.markdown("---")
                if st.button("🔄 PROCESSAR OUTRO ARQUIVO", use_container_width=True):
                    st.session_state.clear()
                    st.rerun()
    
    # Área principal
    if st.session_state.get('arquivo_processado', False):
        sistema = st.session_state['sistema']
        
        if sistema.arquivo_processado:
            # Resumo Executivo
            sistema.mostrar_resumo_executivo()
            st.markdown("---")
            
            # Erros Detalhados
            if st.session_state.get('mostrar_detalhes', True):
                sistema.mostrar_erros_detalhados()
                st.markdown("---")
            
            # Registros Problemáticos
            sistema.mostrar_registros_problematicos()
            st.markdown("---")
            
            # Estatísticas
            sistema.mostrar_estatisticas_valores()
            st.markdown("---")
            
            # Dados Completos (opcional)
            if st.session_state.get('mostrar_dados', False):
                st.markdown('<div class="sub-header">📋 DADOS COMPLETOS PROCESSADOS</div>', unsafe_allow_html=True)
                
                colunas_disponiveis = [c for c in sistema.dados_limpos.columns if c != '__linha_original']
                colunas_selecionadas = st.multiselect(
                    "Selecione colunas para visualizar:",
                    options=colunas_disponiveis,
                    default=colunas_disponiveis[:min(8, len(colunas_disponiveis))]
                )
                
                if colunas_selecionadas:
                    dados_visiveis = sistema.dados_limpos[colunas_selecionadas + ['__linha_original']]
                    st.dataframe(
                        dados_visiveis.head(50),
                        use_container_width=True,
                        height=400
                    )
                
                st.markdown("---")
            
            # Log de Processamento (opcional)
            if st.session_state.get('mostrar_log', False):
                sistema.mostrar_log()
            
            # Exportação
            st.markdown('<div class="sub-header">📥 EXPORTAÇÃO DE RELATÓRIOS</div>', unsafe_allow_html=True)
            
            col_exp1, col_exp2, col_exp3 = st.columns(3)
            
            with col_exp1:
                if sistema.dados_limpos is not None:
                    csv_dados = sistema.dados_limpos.to_csv(index=False, sep=';', encoding='utf-8')
                    st.download_button(
                        label="📋 DADOS PROCESSADOS",
                        data=csv_dados,
                        file_name=f"dados_processados_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
            
            with col_exp2:
                if sistema.registros_problematicos is not None and not sistema.registros_problematicos.empty:
                    csv_problematicos = sistema.registros_problematicos.to_csv(index=False, sep=';', encoding='utf-8')
                    st.download_button(
                        label="⚠️ REGISTROS PROBLEMÁTICOS",
                        data=csv_problematicos,
                        file_name=f"problemas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
            
            with col_exp3:
                if sistema.erros_detalhados:
                    csv_erros = pd.DataFrame(sistema.erros_detalhados).to_csv(index=False, sep=';', encoding='utf-8')
                    st.download_button(
                        label="🚨 ERROS DETALHADOS",
                        data=csv_erros,
                        file_name=f"erros_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
        
        else:
            st.error("❌ FALHA NO PROCESSAMENTO DO ARQUIVO")
            sistema.mostrar_log()
    else:
        # Tela inicial
        st.markdown("""
        <div class="info-card">
        <h3>🚀 BEM-VINDO AO SISTEMA POT</h3>
        <p>Sistema de monitoramento e análise de pagamentos com foco na identificação de inconsistências e dados problemáticos.</p>
        </div>
        """, unsafe_allow_html=True)
        
        col_feat1, col_feat2, col_feat3 = st.columns(3)
        
        with col_feat1:
            st.markdown("""
            <div class="metric-card">
            <h4>🔍 DETECÇÃO PRECISA</h4>
            <p>• Identifica a linha exata de cada problema</p>
            <p>• Classifica por severidade</p>
            <p>• Mantém referência à planilha original</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col_feat2:
            st.markdown("""
            <div class="metric-card">
            <h4>📊 ANÁLISE COMPLETA</h4>
            <p>• Estatísticas detalhadas</p>
            <p>• Valores monetários convertidos</p>
            <p>• Relatórios exportáveis</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col_feat3:
            st.markdown("""
            <div class="metric-card">
            <h4>⚠️ CONTROLE DE QUALIDADE</h4>
            <p>• Valores negativos/zerados</p>
            <p>• Dados críticos faltantes</p>
            <p>• Erros de conversão</p>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("""
        <div class="info-card">
        <h4>📋 COMO USAR:</h4>
        <ol>
            <li><strong>Faça upload</strong> do arquivo CSV na barra lateral</li>
            <li><strong>Configure as opções</strong> desejadas</li>
            <li><strong>Clique em "Processar Arquivo"</strong></li>
            <li><strong>Analise os resultados</strong> com foco nos registros problemáticos</li>
            <li><strong>Exporte os relatórios</strong> para correção</li>
        </ol>
        </div>
        """, unsafe_allow_html=True)
    
    # Rodapé
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: #6B7280; padding: 20px; font-size: 0.9rem;'>
        <strong>💰 SISTEMA POT - MONITORAMENTO DE PAGAMENTOS</strong><br>
        Versão 3.0 • Foco em Problemas • Linha Original • Layout Otimizado
        </div>
        """,
        unsafe_allow_html=True
    )

# ==============================================
# EXECUÇÃO PRINCIPAL
# ==============================================

if __name__ == "__main__":
    main()
