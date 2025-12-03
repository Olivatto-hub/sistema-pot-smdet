import pandas as pd
import os
import re
from datetime import datetime
import streamlit as st
import warnings
import chardet
import numpy as np
import io
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

warnings.filterwarnings('ignore')

# Configuração da página
st.set_page_config(
    page_title="Sistema POT - Monitoramento Completo",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

class SistemaPOTCompleto:
    def __init__(self):
        self.df = None
        self.dados_limpos = None
        self.dados_faltantes = None
        self.inconsistencias = None
        self.arquivo_processado = False
        self.nome_arquivo = ""
        self.total_pagamentos = 0
        self.coluna_valor_pagto = None
        self.relatorio_executivo = {}
        
    def detectar_encoding(self, arquivo_path):
        """Detecta o encoding do arquivo"""
        try:
            with open(arquivo_path, 'rb') as f:
                raw_data = f.read(10000)
            
            resultado = chardet.detect(raw_data)
            encoding = resultado['encoding']
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
            
            # Remover R$ e espaços
            valor_str = valor_str.replace('R$', '').replace(' ', '').strip()
            
            # Se já for número com ponto
            if re.match(r'^\d+\.?\d*$', valor_str):
                return float(valor_str)
            
            # Formato brasileiro: 1.593,90
            if '.' in valor_str and ',' in valor_str:
                # Remover pontos de milhar
                partes = valor_str.split(',')
                if len(partes) == 2:
                    inteiro = partes[0].replace('.', '')
                    return float(f"{inteiro}.{partes[1]}")
            
            # Formato europeu: 1593,90
            elif ',' in valor_str:
                return float(valor_str.replace(',', '.'))
            
            return float(valor_str)
                
        except:
            return 0.0
    
    def processar_arquivo_streamlit(self, arquivo_upload):
        """Processa arquivo CSV de pagamentos do POT"""
        try:
            with st.spinner("📥 Lendo e processando arquivo..."):
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
            
            with st.spinner("🧹 Limpando e analisando dados..."):
                self._limpar_dados()
                self._analisar_dados_faltantes()
                self._analisar_inconsistencias()
                
            with st.spinner("📊 Calculando estatísticas e gerando relatórios..."):
                self._calcular_estatisticas()
                self._gerar_relatorio_executivo()
                
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
        
        # Padronizar nomes das colunas
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
        possiveis_nomes_valor = [
            'valor_pagto', 'valor_pagamento', 'valor_total', 'valor', 
            'pagto', 'pagamento', 'total', 'valorpagto'
        ]
        
        self.coluna_valor_pagto = None
        for nome in possiveis_nomes_valor:
            if nome in df_limpo.columns:
                self.coluna_valor_pagto = nome
                break
        
        # Converter colunas de valor
        colunas_valor = []
        for col in df_limpo.columns:
            col_lower = col.lower()
            if any(termo in col_lower for termo in ['valor', 'total', 'pagto', 'pagamento', 'desconto', 'dia']):
                colunas_valor.append(col)
        
        for coluna in colunas_valor:
            df_limpo[coluna] = df_limpo[coluna].apply(self.converter_valor)
        
        # Converter outras colunas
        for col in df_limpo.columns:
            if 'dia' in col.lower() or 'dias' in col.lower():
                try:
                    df_limpo[col] = pd.to_numeric(df_limpo[col], errors='coerce')
                except:
                    pass
            
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
            df_limpo = df_limpo[df_limpo[self.coluna_valor_pagto] > 0]
        
        self.dados_limpos = df_limpo
    
    def _analisar_dados_faltantes(self):
        """Analisa dados faltantes no dataset"""
        if self.dados_limpos is None or self.dados_limpos.empty:
            return
        
        # Analisar valores faltantes por coluna
        faltantes_por_coluna = self.dados_limpos.isnull().sum()
        percentual_faltantes = (faltantes_por_coluna / len(self.dados_limpos)) * 100
        
        self.dados_faltantes = pd.DataFrame({
            'Coluna': faltantes_por_coluna.index,
            'Valores_Faltantes': faltantes_por_coluna.values,
            'Percentual_Faltante': percentual_faltantes.values.round(2),
            'Tipo_Dado': self.dados_limpos.dtypes.values
        })
        
        # Identificar linhas com dados faltantes críticos
        colunas_criticas = []
        for col in self.dados_limpos.columns:
            if col in ['nome', 'agencia', self.coluna_valor_pagto]:
                colunas_criticas.append(col)
        
        if colunas_criticas:
            mask = self.dados_limpos[colunas_criticas].isnull().any(axis=1)
            self.linhas_com_faltantes_criticos = self.dados_limpos[mask].copy()
        else:
            self.linhas_com_faltantes_criticos = pd.DataFrame()
    
    def _analisar_inconsistencias(self):
        """Analisa inconsistências nos dados"""
        if self.dados_limpos is None or self.dados_limpos.empty:
            return
        
        inconsistencias = []
        
        # 1. Valores negativos onde não deveriam
        if self.coluna_valor_pagto and self.coluna_valor_pagto in self.dados_limpos.columns:
            negativos = self.dados_limpos[self.dados_limpos[self.coluna_valor_pagto] < 0]
            if len(negativos) > 0:
                inconsistencias.append({
                    'Tipo': 'Valores Negativos',
                    'Coluna': self.coluna_valor_pagto,
                    'Quantidade': len(negativos),
                    'Exemplo': f"Linhas: {list(negativos.index[:3])}"
                })
        
        # 2. Valores zerados
        if self.coluna_valor_pagto and self.coluna_valor_pagto in self.dados_limpos.columns:
            zerados = self.dados_limpos[self.dados_limpos[self.coluna_valor_pagto] == 0]
            if len(zerados) > 0:
                inconsistencias.append({
                    'Tipo': 'Valores Zerados',
                    'Coluna': self.coluna_valor_pagto,
                    'Quantidade': len(zerados),
                    'Exemplo': f"Linhas: {list(zerados.index[:3])}"
                })
        
        # 3. Datas inválidas
        colunas_data = [col for col in self.dados_limpos.columns if 'data' in col.lower()]
        for col in colunas_data:
            if pd.api.types.is_datetime64_any_dtype(self.dados_limpos[col]):
                datas_invalidas = self.dados_limpos[self.dados_limpos[col].isnull()]
                if len(datas_invalidas) > 0:
                    inconsistencias.append({
                        'Tipo': 'Datas Inválidas',
                        'Coluna': col,
                        'Quantidade': len(datas_invalidas),
                        'Exemplo': f"{len(datas_invalidas)} registros sem data válida"
                    })
        
        # 4. Valores fora do padrão esperado
        if self.coluna_valor_pagto and self.coluna_valor_pagto in self.dados_limpos.columns:
            valores = self.dados_limpos[self.coluna_valor_pagto]
            q1 = valores.quantile(0.25)
            q3 = valores.quantile(0.75)
            iqr = q3 - q1
            limite_inferior = q1 - 1.5 * iqr
            limite_superior = q3 + 1.5 * iqr
            
            outliers = self.dados_limpos[
                (valores < limite_inferior) | (valores > limite_superior)
            ]
            
            if len(outliers) > 0:
                inconsistencias.append({
                    'Tipo': 'Valores Atípicos (Outliers)',
                    'Coluna': self.coluna_valor_pagto,
                    'Quantidade': len(outliers),
                    'Exemplo': f"Valores fora de [{limite_inferior:.2f}, {limite_superior:.2f}]"
                })
        
        # 5. Agências inválidas
        if 'agencia' in self.dados_limpos.columns:
            agencias_invalidas = self.dados_limpos[self.dados_limpos['agencia'].isnull()]
            if len(agencias_invalidas) > 0:
                inconsistencias.append({
                    'Tipo': 'Agências Inválidas',
                    'Coluna': 'agencia',
                    'Quantidade': len(agencias_invalidas),
                    'Exemplo': f"{len(agencias_invalidas)} registros sem agência"
                })
        
        self.inconsistencias = pd.DataFrame(inconsistencias) if inconsistencias else pd.DataFrame()
    
    def _calcular_estatisticas(self):
        """Calcula estatísticas dos dados"""
        if self.dados_limpos is None or len(self.dados_limpos) == 0:
            return
        
        if self.coluna_valor_pagto and self.coluna_valor_pagto in self.dados_limpos.columns:
            self.total_pagamentos = self.dados_limpos[self.coluna_valor_pagto].sum()
    
    def _gerar_relatorio_executivo(self):
        """Gera relatório executivo consolidado"""
        self.relatorio_executivo = {
            'data_processamento': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'nome_arquivo': self.nome_arquivo,
            'total_registros': len(self.dados_limpos) if self.dados_limpos is not None else 0,
            'valor_total': self.total_pagamentos,
            'coluna_valor_principal': self.coluna_valor_pagto,
            'dados_faltantes': self.dados_faltantes.to_dict('records') if self.dados_faltantes is not None else [],
            'inconsistencias': self.inconsistencias.to_dict('records') if self.inconsistencias is not None else [],
            'colunas_disponiveis': list(self.dados_limpos.columns) if self.dados_limpos is not None else []
        }
    
    def gerar_relatorio_excel_completo(self):
        """Gera relatório Excel completo com análises"""
        if not self.arquivo_processado:
            return None
        
        try:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # 1. Dados Completos
                self.dados_limpos.to_excel(writer, sheet_name='Dados Completos', index=False)
                
                # 2. Análise de Dados Faltantes
                if self.dados_faltantes is not None and not self.dados_faltantes.empty:
                    self.dados_faltantes.to_excel(writer, sheet_name='Dados Faltantes', index=False)
                    
                    # Linhas com faltantes críticos
                    if hasattr(self, 'linhas_com_faltantes_criticos') and not self.linhas_com_faltantes_criticos.empty:
                        self.linhas_com_faltantes_criticos.to_excel(
                            writer, sheet_name='Faltantes Críticos', index=False
                        )
                
                # 3. Análise de Inconsistências
                if self.inconsistencias is not None and not self.inconsistencias.empty:
                    self.inconsistencias.to_excel(writer, sheet_name='Inconsistências', index=False)
                
                # 4. Estatísticas Detalhadas
                if self.coluna_valor_pagto and self.coluna_valor_pagto in self.dados_limpos.columns:
                    stats = self.dados_limpos[self.coluna_valor_pagto].describe()
                    stats_df = pd.DataFrame({
                        'Estatística': stats.index,
                        'Valor': stats.values
                    })
                    stats_df.to_excel(writer, sheet_name='Estatísticas', index=False)
                
                # 5. Relatório Executivo
                relatorio_df = pd.DataFrame([
                    ['Data Processamento', self.relatorio_executivo['data_processamento']],
                    ['Arquivo', self.relatorio_executivo['nome_arquivo']],
                    ['Total de Registros', self.relatorio_executivo['total_registros']],
                    ['Valor Total', f"R$ {self.relatorio_executivo['valor_total']:,.2f}"],
                    ['Coluna Valor Principal', self.relatorio_executivo['coluna_valor_principal']],
                    ['Colunas Disponíveis', ', '.join(self.relatorio_executivo['colunas_disponiveis'])],
                    ['Dados Faltantes Detectados', len(self.relatorio_executivo['dados_faltantes'])],
                    ['Inconsistências Detectadas', len(self.relatorio_executivo['inconsistencias'])]
                ], columns=['Item', 'Valor'])
                
                relatorio_df.to_excel(writer, sheet_name='Relatório Executivo', index=False)
                
                # 6. Top 10 Agências (se existir)
                if 'agencia' in self.dados_limpos.columns and self.coluna_valor_pagto:
                    analise_agencia = self.dados_limpos.groupby('agencia').agg({
                        self.coluna_valor_pagto: ['sum', 'count', 'mean']
                    }).round(2)
                    
                    analise_agencia.columns = ['Valor Total', 'Quantidade', 'Média']
                    analise_agencia = analise_agencia.sort_values('Valor Total', ascending=False)
                    analise_agencia.to_excel(writer, sheet_name='Análise por Agência')
            
            output.seek(0)
            return output
        
        except Exception as e:
            st.error(f"Erro ao gerar relatório Excel: {str(e)}")
            return None
    
    def gerar_relatorio_consolidado_html(self):
        """Gera relatório consolidado em formato HTML"""
        if not self.arquivo_processado:
            return ""
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                .header {{ background-color: #f0f0f0; padding: 20px; border-radius: 10px; }}
                .section {{ margin: 30px 0; padding: 20px; border: 1px solid #ddd; border-radius: 5px; }}
                .metric {{ display: inline-block; margin: 10px; padding: 15px; background: #007bff; color: white; border-radius: 5px; }}
                .alert {{ background: #ffcccc; padding: 10px; border-radius: 5px; margin: 10px 0; }}
                .success {{ background: #ccffcc; padding: 10px; border-radius: 5px; margin: 10px 0; }}
                table {{ width: 100%; border-collapse: collapse; }}
                th, td {{ padding: 8px; text-align: left; border-bottom: 1px solid #ddd; }}
                th {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📊 RELATÓRIO EXECUTIVO - SISTEMA POT</h1>
                <p><strong>Data:</strong> {self.relatorio_executivo['data_processamento']}</p>
                <p><strong>Arquivo:</strong> {self.relatorio_executivo['nome_arquivo']}</p>
            </div>
            
            <div class="section">
                <h2>📈 MÉTRICAS PRINCIPAIS</h2>
                <div class="metric">Total Registros: {self.relatorio_executivo['total_registros']:,}</div>
                <div class="metric">Valor Total: R$ {self.relatorio_executivo['valor_total']:,.2f}</div>
                <div class="metric">Colunas: {len(self.relatorio_executivo['colunas_disponiveis'])}</div>
            </div>
        """
        
        # Dados Faltantes
        if self.dados_faltantes is not None and not self.dados_faltantes.empty:
            html += """
            <div class="section">
                <h2>⚠️ DADOS FALTANTES</h2>
                <table>
                    <tr>
                        <th>Coluna</th>
                        <th>Valores Faltantes</th>
                        <th>Percentual</th>
                        <th>Tipo de Dado</th>
                    </tr>
            """
            
            for _, row in self.dados_faltantes.iterrows():
                if row['Valores_Faltantes'] > 0:
                    html += f"""
                    <tr>
                        <td>{row['Coluna']}</td>
                        <td>{row['Valores_Faltantes']:,}</td>
                        <td>{row['Percentual_Faltante']}%</td>
                        <td>{row['Tipo_Dado']}</td>
                    </tr>
                    """
            
            html += "</table></div>"
        
        # Inconsistências
        if self.inconsistencias is not None and not self.inconsistencias.empty:
            html += """
            <div class="section">
                <h2>🚨 INCONSISTÊNCIAS DETECTADAS</h2>
                <table>
                    <tr>
                        <th>Tipo</th>
                        <th>Coluna</th>
                        <th>Quantidade</th>
                        <th>Exemplo/Descrição</th>
                    </tr>
            """
            
            for _, row in self.inconsistencias.iterrows():
                html += f"""
                <tr>
                    <td>{row['Tipo']}</td>
                    <td>{row['Coluna']}</td>
                    <td>{row['Quantidade']:,}</td>
                    <td>{row['Exemplo']}</td>
                </tr>
                """
            
            html += "</table></div>"
        
        html += """
            <div class="section">
                <h2>📋 RECOMENDAÇÕES</h2>
                <div class="success">
                    <strong>✓ Ações Recomendadas:</strong><br>
                    1. Corrigir dados faltantes críticos<br>
                    2. Validar inconsistências detectadas<br>
                    3. Revisar valores atípicos<br>
                    4. Atualizar informações incompletas
                </div>
            </div>
        </body>
        </html>
        """
        
        return html

# Inicializar sistema
sistema = SistemaPOTCompleto()

# ==============================================
# INTERFACE STREAMLIT COMPLETA
# ==============================================

st.title("💰 SISTEMA COMPLETO DE MONITORAMENTO DE PAGAMENTOS - POT")
st.markdown("---")

# Sidebar
with st.sidebar:
    st.header("📁 Upload do Arquivo")
    
    arquivo = st.file_uploader(
        "Selecione o arquivo CSV",
        type=['csv'],
        help="Arquivo CSV com dados de pagamentos"
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
        st.header("📊 RESUMO EXECUTIVO")
        
        # Métricas principais
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                label="📄 Total de Registros",
                value=f"{len(sistema.dados_limpos):,}"
            )
        
        with col2:
            valor_total = sistema.dados_limpos[sistema.coluna_valor_pagto].sum() if sistema.coluna_valor_pagto else 0
            st.metric(
                label="💰 Valor Total",
                value=f"R$ {valor_total:,.2f}"
            )
        
        with col3:
            if sistema.dados_faltantes is not None:
                total_faltantes = sistema.dados_faltantes['Valores_Faltantes'].sum()
                st.metric(
                    label="⚠️ Dados Faltantes",
                    value=f"{total_faltantes:,}"
                )
            else:
                st.metric(label="⚠️ Dados Faltantes", value="0")
        
        with col4:
            if sistema.inconsistencias is not None:
                total_inconsistencias = sistema.inconsistencias['Quantidade'].sum() if 'Quantidade' in sistema.inconsistencias.columns else 0
                st.metric(
                    label="🚨 Inconsistências",
                    value=f"{total_inconsistencias:,}"
                )
            else:
                st.metric(label="🚨 Inconsistências", value="0")
        
        st.markdown("---")
        
        # ============================
        # ANÁLISE DE DADOS FALTANTES
        # ============================
        st.header("🔍 ANÁLISE DE DADOS FALTANTES")
        
        if sistema.dados_faltantes is not None and not sistema.dados_faltantes.empty:
            # Filtrar apenas colunas com dados faltantes
            dados_faltantes_filtrados = sistema.dados_faltantes[
                sistema.dados_faltantes['Valores_Faltantes'] > 0
            ]
            
            if not dados_faltantes_filtrados.empty:
                st.subheader("📋 Dados Faltantes por Coluna")
                
                col_f1, col_f2 = st.columns(2)
                
                with col_f1:
                    st.dataframe(
                        dados_faltantes_filtrados[['Coluna', 'Valores_Faltantes', 'Percentual_Faltante']],
                        use_container_width=True,
                        height=300
                    )
                
                with col_f2:
                    # Gráfico de barras simples
                    chart_data = dados_faltantes_filtrados.set_index('Coluna')['Percentual_Faltante']
                    st.bar_chart(chart_data)
                
                # Mostrar linhas com faltantes críticos
                if hasattr(sistema, 'linhas_com_faltantes_criticos') and not sistema.linhas_com_faltantes_criticos.empty:
                    st.subheader("🚨 Linhas com Faltantes Críticos")
                    st.dataframe(
                        sistema.linhas_com_faltantes_criticos,
                        use_container_width=True,
                        height=200
                    )
                    st.info(f"**Ação necessária:** Corrigir {len(sistema.linhas_com_faltantes_criticos)} registros com dados críticos faltantes.")
            else:
                st.success("✅ Nenhum dado faltante detectado!")
        else:
            st.success("✅ Nenhum dado faltante detectado!")
        
        st.markdown("---")
        
        # ============================
        # ANÁLISE DE INCONSISTÊNCIAS
        # ============================
        st.header("🚨 ANÁLISE DE INCONSISTÊNCIAS")
        
        if sistema.inconsistencias is not None and not sistema.inconsistencias.empty:
            st.subheader("📋 Inconsistências Detectadas")
            
            # Tabela de inconsistências
            st.dataframe(
                sistema.inconsistencias,
                use_container_width=True,
                height=300
            )
            
            # Detalhamento por tipo de inconsistência
            st.subheader("📊 Detalhamento por Tipo")
            
            for _, row in sistema.inconsistencias.iterrows():
                with st.expander(f"{row['Tipo']} - {row['Quantidade']} ocorrências"):
                    st.write(f"**Coluna:** {row['Coluna']}")
                    st.write(f"**Descrição:** {row['Exemplo']}")
                    st.write(f"**Impacto:** {row['Quantidade']} registros afetados")
                    
                    # Botão para ver exemplos
                    if st.button(f"Ver exemplos de {row['Tipo']}", key=f"btn_{row['Tipo']}"):
                        # Aqui você pode mostrar exemplos específicos
                        st.write("Exemplos serão mostrados aqui...")
            
            # Recomendações
            st.subheader("🎯 RECOMENDAÇÕES DE CORREÇÃO")
            
            rec_col1, rec_col2 = st.columns(2)
            
            with rec_col1:
                st.markdown("""
                **Ações Imediatas:**
                1. Corrigir valores negativos
                2. Validar valores zerados
                3. Completar dados faltantes críticos
                4. Revisar datas inválidas
                """)
            
            with rec_col2:
                st.markdown("""
                **Ações Preventivas:**
                1. Implementar validação na entrada
                2. Criar relatórios de qualidade
                3. Treinar equipe de inserção
                4. Estabelecer padrões de qualidade
                """)
        else:
            st.success("✅ Nenhuma inconsistência grave detectada!")
        
        st.markdown("---")
        
        # ============================
        # VISUALIZAÇÃO DOS DADOS
        # ============================
        st.header("👀 VISUALIZAÇÃO DOS DADOS PROCESSADOS")
        
        tab1, tab2, tab3 = st.tabs(["📋 Dados Completos", "📊 Estatísticas", "🏢 Análise por Agência"])
        
        with tab1:
            # Filtros para visualização
            col_vis1, col_vis2 = st.columns(2)
            
            with col_vis1:
                colunas_selecionadas = st.multiselect(
                    "Selecione colunas:",
                    options=sistema.dados_limpos.columns.tolist(),
                    default=sistema.dados_limpos.columns.tolist()[:min(6, len(sistema.dados_limpos.columns))]
                )
            
            with col_vis2:
                num_linhas = st.slider("Linhas para mostrar:", 5, 100, 20)
            
            if colunas_selecionadas:
                dados_visiveis = sistema.dados_limpos[colunas_selecionadas].head(num_linhas)
                st.dataframe(dados_visiveis, use_container_width=True, height=400)
        
        with tab2:
            if sistema.coluna_valor_pagto:
                stats = sistema.dados_limpos[sistema.coluna_valor_pagto].describe()
                
                col_stat1, col_stat2 = st.columns(2)
                
                with col_stat1:
                    st.markdown("**Estatísticas Descritivas:**")
                    for stat, value in stats.items():
                        st.write(f"**{stat}:** R$ {value:,.2f}")
                
                with col_stat2:
                    st.markdown("**Distribuição:**")
                    # Histograma simples
                    hist_values = np.histogram(sistema.dados_limpos[sistema.coluna_valor_pagto], bins=20)
                    hist_df = pd.DataFrame({
                        'Faixa': [f"{hist_values[1][i]:.0f}-{hist_values[1][i+1]:.0f}" 
                                 for i in range(len(hist_values[0]))],
                        'Frequência': hist_values[0]
                    })
                    st.dataframe(hist_df, use_container_width=True, height=300)
        
        with tab3:
            if 'agencia' in sistema.dados_limpos.columns and sistema.coluna_valor_pagto:
                analise_agencia = sistema.dados_limpos.groupby('agencia').agg({
                    sistema.coluna_valor_pagto: ['sum', 'count', 'mean']
                }).round(2)
                
                analise_agencia.columns = ['Valor Total', 'Quantidade', 'Média']
                analise_agencia = analise_agencia.sort_values('Valor Total', ascending=False)
                
                st.dataframe(
                    analise_agencia.head(20),
                    use_container_width=True,
                    height=400
                )
        
        st.markdown("---")
        
        # ============================
        # RELATÓRIOS E EXPORTAÇÃO
        # ============================
        st.header("📥 RELATÓRIOS E EXPORTAÇÃO")
        
        col_rel1, col_rel2, col_rel3 = st.columns(3)
        
        with col_rel1:
            # Relatório Excel Completo
            excel_data = sistema.gerar_relatorio_excel_completo()
            if excel_data:
                st.download_button(
                    label="📥 Relatório Excel Completo",
                    data=excel_data,
                    file_name=f"relatorio_completo_pot_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            else:
                st.button("📥 Relatório Excel", disabled=True, use_container_width=True)
        
        with col_rel2:
            # CSV dos dados processados
            csv_data = sistema.dados_limpos.to_csv(index=False, sep=';', encoding='utf-8')
            st.download_button(
                label="📥 Dados Processados (CSV)",
                data=csv_data,
                file_name=f"dados_processados_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col_rel3:
            # Relatório HTML
            html_relatorio = sistema.gerar_relatorio_consolidado_html()
            if html_relatorio:
                st.download_button(
                    label="📥 Relatório Executivo (HTML)",
                    data=html_relatorio,
                    file_name=f"relatorio_executivo_{datetime.now().strftime('%Y%m%d')}.html",
                    mime="text/html",
                    use_container_width=True
                )
        
        # Relatório de Inconsistências específico
        st.subheader("📋 RELATÓRIOS ESPECÍFICOS")
        
        col_rep1, col_rep2 = st.columns(2)
        
        with col_rep1:
            if sistema.inconsistencias is not None and not sistema.inconsistencias.empty:
                csv_inconsistencias = sistema.inconsistencias.to_csv(index=False, sep=';', encoding='utf-8')
                st.download_button(
                    label="📥 Relatório de Inconsistências",
                    data=csv_inconsistencias,
                    file_name=f"inconsistencias_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        
        with col_rep2:
            if sistema.dados_faltantes is not None and not sistema.dados_faltantes.empty:
                csv_faltantes = sistema.dados_faltantes.to_csv(index=False, sep=';', encoding='utf-8')
                st.download_button(
                    label="📥 Relatório de Dados Faltantes",
                    data=csv_faltantes,
                    file_name=f"dados_faltantes_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
    
    else:
        st.error("❌ Erro no processamento dos dados.")
else:
    # Tela inicial
    st.markdown("""
    # 🚀 SISTEMA COMPLETO DE MONITORAMENTO POT
    
    ### 📋 **FUNCIONALIDADES INCLUÍDAS:**
    
    ✅ **Processamento Completo** de arquivos CSV
    ✅ **Análise de Dados Faltantes** com tabelas detalhadas
    ✅ **Detecção de Inconsistências** com recomendações
    ✅ **Relatórios Executivos** em múltiplos formatos
    ✅ **Dashboard Interativo** com métricas em tempo real
    ✅ **Exportação Completa** (Excel, CSV, HTML)
    
    ### 🎯 **PARA A EQUIPE DE QUALIDADE:**
    
    1. **Localize erros rapidamente** com tabelas específicas
    2. **Identifique padrões de problemas** com análises detalhadas
    3. **Gere relatórios executivos** para gestão
    4. **Monitore a qualidade dos dados** continuamente
    
    ### 📁 **COMO USAR:**
    
    1. **Faça upload** do arquivo CSV
    2. **Analise** os dados faltantes e inconsistências
    3. **Exporte** relatórios para a equipe
    4. **Corrija** os problemas identificados
    """)
    
    st.markdown("---")
    
    # Demonstração das funcionalidades
    with st.expander("🎬 DEMONSTRAÇÃO DAS ANÁLISES"):
        st.markdown("""
        ### 📊 **ANÁLISE DE DADOS FALTANTES:**
        - Tabela por coluna com quantitativos
        - Percentual de completude
        - Linhas críticas destacadas
        
        ### 🚨 **DETECÇÃO DE INCONSISTÊNCIAS:**
        - Valores negativos/zerados
        - Datas inválidas
        - Valores atípicos (outliers)
        - Agências inválidas
        
        ### 📥 **RELATÓRIOS EXECUTIVOS:**
        - Excel com múltiplas abas
        - HTML para visualização web
        - CSV para análise adicional
        """)

# ==============================================
# CONFIGURAÇÕES
# ==============================================
encoding_map = {
    'ISO-8859-1': 'latin-1',
    'Windows-1252': 'cp1252',
    'ascii': 'utf-8',
    'UTF-8-SIG': 'utf-8'
}

# ==============================================
# RODAPÉ
# ==============================================
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: gray; padding: 10px;'>
    <strong>Sistema POT Completo</strong> • 
    Análise de Dados Faltantes • 
    Detecção de Inconsistências • 
    Relatórios Executivos • 
    Versão 5.0
    </div>
    """,
    unsafe_allow_html=True
)
