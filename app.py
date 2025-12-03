# app.py - SISTEMA POT SMDET - VERSÃO FINAL CORRIGIDA
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from fpdf import FPDF
import re
import warnings
warnings.filterwarnings('ignore')

# Configuração da página
st.set_page_config(
    page_title="Sistema POT - SMDET",
    page_icon="🏛️",
    layout="wide"
)

# ============================================
# CLASSE PDF PERSONALIZADA SIMPLIFICADA
# ============================================

class RelatorioPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=15)
    
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, 'SISTEMA POT - SMDET', 0, 1, 'C')
        self.set_font('Arial', 'I', 10)
        self.cell(0, 10, 'Relatório de Análise de Pagamentos e Contas', 0, 1, 'C')
        self.ln(5)
    
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()} - {datetime.now().strftime("%d/%m/%Y %H:%M")}', 0, 0, 'C')
    
    def add_metric(self, label, value):
        self.set_font('Arial', 'B', 10)
        self.cell(70, 8, label, 0, 0)
        self.set_font('Arial', '', 10)
        self.cell(0, 8, str(value), 0, 1)

# ============================================
# FUNÇÕES AUXILIARES
# ============================================

def formatar_brasileiro(valor, tipo='numero'):
    """Formata números no padrão brasileiro"""
    if pd.isna(valor):
        return "0"
    
    try:
        if tipo == 'monetario':
            # Formato: R$ 1.234,56
            return f"R$ {float(valor):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        elif tipo == 'numero':
            # Formato: 1.234
            return f"{int(valor):,}".replace(',', '.')
        else:
            return str(valor)
    except:
        return str(valor)

# ============================================
# DETECÇÃO AUTOMÁTICA DE COLUNAS
# ============================================

def detectar_coluna_conta(df):
    """Detecta a coluna de número da conta"""
    if df.empty:
        return None
    
    padroes = ['Num Cartao', 'NumCartao', 'Num_Cartao', 'Cartao', 'Cartão', 
               'Conta', 'Numero Conta', 'Número Conta', 'NUMCARTAO', 'CONTA']
    
    for col in df.columns:
        col_str = str(col).strip().upper()
        for padrao in padroes:
            if padrao.upper() in col_str:
                return col
    
    return None

def detectar_coluna_valor(df):
    """Detecta a coluna de valor pago"""
    if df.empty:
        return None
    
    padroes = ['Valor Pagto', 'ValorPagto', 'Valor_Pagto', 'Valor Pago', 
               'ValorPago', 'VALOR PAGTO', 'VALOR PAGO', 'Valor']
    
    for col in df.columns:
        col_str = str(col).strip().upper()
        for padrao in padroes:
            if padrao.upper() in col_str:
                return col
    
    return None

def detectar_coluna_nome(df):
    """Detecta a coluna de nome do beneficiário"""
    if df.empty:
        return None
    
    padroes = ['Nome', 'Beneficiario', 'Beneficiário', 'NOME', 'BENEFICIARIO']
    
    for col in df.columns:
        col_str = str(col).strip().upper()
        for padrao in padroes:
            if padrao.upper() in col_str:
                return col
    
    return None

# ============================================
# CONVERSÃO CORRETA DE VALORES (SEM DUPLICAR)
# ============================================

def converter_valor_simples(valor):
    """Converte valor para float de forma simples e correta"""
    if pd.isna(valor):
        return 0.0
    
    try:
        # Se já for numérico
        if isinstance(valor, (int, float, np.integer, np.floating)):
            result = float(valor)
            return abs(result) if result >= 0 else 0.0
        
        valor_str = str(valor).strip()
        
        # Remover caracteres não numéricos exceto ponto, vírgula e sinal
        valor_str = re.sub(r'[^\d,\-\.]', '', valor_str)
        
        if not valor_str or valor_str == '-':
            return 0.0
        
        # Substituir vírgula por ponto se for decimal
        if ',' in valor_str and '.' in valor_str:
            # Formato: 1.234,56 -> remover pontos de milhar, vírgula vira ponto
            if valor_str.rfind(',') > valor_str.rfind('.'):
                # Último separador é vírgula (formato brasileiro)
                valor_str = valor_str.replace('.', '').replace(',', '.')
            else:
                # Último separador é ponto (formato americano)
                valor_str = valor_str.replace(',', '')
        elif ',' in valor_str:
            # Verificar se vírgula é separador decimal (max 2 dígitos após)
            partes = valor_str.split(',')
            if len(partes) == 2 and len(partes[1]) <= 2:
                valor_str = valor_str.replace(',', '.')
            else:
                valor_str = valor_str.replace(',', '')
        
        # Converter para float
        result = float(valor_str)
        
        # Retornar valor absoluto (pagamentos são positivos)
        return abs(result) if result >= 0 else 0.0
        
    except:
        return 0.0

def calcular_valores_corretos(df, coluna_valor):
    """Calcula valores total e médio CORRETAMENTE"""
    if df.empty or coluna_valor is None:
        return 0.0, 0.0, 0
    
    try:
        valores = []
        total_valido = 0
        
        for valor in df[coluna_valor]:
            valor_convertido = converter_valor_simples(valor)
            valores.append(valor_convertido)
            if valor_convertido > 0:
                total_valido += 1
        
        soma_total = sum(valores)
        
        if total_valido > 0:
            valor_medio = soma_total / total_valido
        else:
            valor_medio = 0.0
        
        return soma_total, valor_medio, total_valido
        
    except:
        return 0.0, 0.0, 0

# ============================================
# CARREGAMENTO DE PLANILHAS
# ============================================

def carregar_planilha(arquivo):
    """Carrega arquivo CSV ou Excel"""
    try:
        nome = arquivo.name.lower()
        
        if nome.endswith('.csv'):
            # Tentar diferentes delimitadores
            try:
                df = pd.read_csv(arquivo, delimiter=';', encoding='utf-8', on_bad_lines='skip')
            except:
                arquivo.seek(0)
                df = pd.read_csv(arquivo, delimiter=',', encoding='utf-8', on_bad_lines='skip')
        elif nome.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(arquivo)
        else:
            return pd.DataFrame()
        
        # Remover linhas completamente vazias
        df = df.dropna(how='all')
        
        return df
        
    except Exception as e:
        return pd.DataFrame()

# ============================================
# ANÁLISE DE PAGAMENTOS
# ============================================

def analisar_pagamentos(df):
    """Realiza análise completa dos pagamentos"""
    resultados = {
        'total_linhas': len(df) if not df.empty else 0,
        'coluna_conta': None,
        'coluna_valor': None,
        'coluna_nome': None,
        'pagamentos_validos': 0,
        'pagamentos_sem_conta': 0,
        'valor_total': 0.0,
        'valor_medio': 0.0,
        'duplicados': 0
    }
    
    if df.empty:
        return resultados
    
    # Detectar colunas
    resultados['coluna_conta'] = detectar_coluna_conta(df)
    resultados['coluna_valor'] = detectar_coluna_valor(df)
    resultados['coluna_nome'] = detectar_coluna_nome(df)
    
    # Análise de contas
    if resultados['coluna_conta']:
        df[resultados['coluna_conta']] = df[resultados['coluna_conta']].astype(str).str.strip()
        
        # Contar contas válidas
        contas_validas = ~df[resultados['coluna_conta']].isin(['', 'nan', 'NaN', 'None', 'null'])
        resultados['pagamentos_validos'] = contas_validas.sum()
        resultados['pagamentos_sem_conta'] = (~contas_validas).sum()
        
        # Verificar duplicidades
        if resultados['pagamentos_validos'] > 0:
            df_validos = df[contas_validas]
            duplicados = df_validos[df_validos.duplicated(subset=[resultados['coluna_conta']], keep=False)]
            resultados['duplicados'] = duplicados[resultados['coluna_conta']].nunique() if not duplicados.empty else 0
    
    # Calcular valores CORRETAMENTE
    if resultados['coluna_valor']:
        valor_total, valor_medio, _ = calcular_valores_corretos(df, resultados['coluna_valor'])
        resultados['valor_total'] = valor_total
        resultados['valor_medio'] = valor_medio
    
    return resultados

# ============================================
# GERAR RELATÓRIO PDF (SIMPLIFICADO)
# ============================================

def gerar_relatorio_pdf(mes, ano, analise_pagamentos, df_pagamentos):
    """Gera relatório PDF simplificado e funcional"""
    try:
        pdf = RelatorioPDF()
        pdf.add_page()
        
        # Título
        pdf.set_font('Arial', 'B', 16)
        pdf.cell(0, 10, 'RELATÓRIO DE ANÁLISE - SMDET', 0, 1, 'C')
        pdf.set_font('Arial', '', 12)
        pdf.cell(0, 10, f'Período: {mes} de {ano}', 0, 1, 'C')
        pdf.cell(0, 10, f'Gerado em: {datetime.now().strftime("%d/%m/%Y %H:%M")}', 0, 1, 'C')
        pdf.ln(10)
        
        # Métricas
        pdf.set_font('Arial', 'B', 14)
        pdf.cell(0, 10, 'MÉTRICAS PRINCIPAIS', 0, 1)
        pdf.ln(5)
        
        pdf.add_metric('Total de Linhas:', formatar_brasileiro(analise_pagamentos['total_linhas']))
        pdf.add_metric('Pagamentos Válidos:', formatar_brasileiro(analise_pagamentos['pagamentos_validos']))
        pdf.add_metric('Pagamentos sem Conta:', formatar_brasileiro(analise_pagamentos['pagamentos_sem_conta']))
        pdf.add_metric('Valor Total Pago:', formatar_brasileiro(analise_pagamentos['valor_total'], 'monetario'))
        pdf.add_metric('Valor Médio:', formatar_brasileiro(analise_pagamentos['valor_medio'], 'monetario'))
        pdf.add_metric('Contas Duplicadas:', formatar_brasileiro(analise_pagamentos['duplicados']))
        
        pdf.ln(10)
        
        # Detecção de colunas
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 10, 'COLUNAS DETECTADAS:', 0, 1)
        pdf.set_font('Arial', '', 11)
        
        if analise_pagamentos['coluna_conta']:
            pdf.cell(0, 8, f'• Conta: {analise_pagamentos["coluna_conta"]}', 0, 1)
        
        if analise_pagamentos['coluna_valor']:
            pdf.cell(0, 8, f'• Valor: {analise_pagamentos["coluna_valor"]}', 0, 1)
        
        if analise_pagamentos['coluna_nome']:
            pdf.cell(0, 8, f'• Nome: {analise_pagamentos["coluna_nome"]}', 0, 1)
        
        # Gerar bytes do PDF
        pdf_bytes = pdf.output(dest='S').encode('latin-1')
        return pdf_bytes
        
    except Exception as e:
        # Fallback: criar PDF mínimo
        try:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font('Arial', 'B', 16)
            pdf.cell(0, 10, 'Relatório SMDET', 0, 1, 'C')
            pdf.set_font('Arial', '', 12)
            pdf.cell(0, 10, f'Erro ao gerar relatório completo: {str(e)[:50]}', 0, 1)
            return pdf.output(dest='S').encode('latin-1')
        except:
            return None

# ============================================
# INTERFACE PRINCIPAL
# ============================================

def main():
    st.title("🏛️ Sistema POT - SMDET")
    st.markdown("### Sistema de Análise de Pagamentos e Contas")
    st.markdown("---")
    
    # Sidebar
    st.sidebar.header("📤 Upload de Arquivos")
    
    uploaded_files = st.sidebar.file_uploader(
        "Selecione os arquivos",
        type=['csv', 'xlsx', 'xls'],
        accept_multiple_files=True
    )
    
    # Processar arquivos
    df_pagamentos = pd.DataFrame()
    
    if uploaded_files:
        for arquivo in uploaded_files:
            df = carregar_planilha(arquivo)
            if not df.empty:
                st.sidebar.success(f"✓ {arquivo.name} ({len(df)} linhas)")
                if df_pagamentos.empty:
                    df_pagamentos = df
                else:
                    df_pagamentos = pd.concat([df_pagamentos, df], ignore_index=True)
    
    # Período
    st.sidebar.markdown("---")
    st.sidebar.header("📅 Período")
    
    meses = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
             'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
    
    col1, col2 = st.sidebar.columns(2)
    with col1:
        mes = st.selectbox("Mês", meses, index=8)
    with col2:
        ano_atual = datetime.now().year
        ano = st.selectbox("Ano", list(range(ano_atual, ano_atual - 3, -1)))
    
    # Botão de análise
    if st.sidebar.button("🔍 Realizar Análise", type="primary", use_container_width=True):
        if not df_pagamentos.empty:
            with st.spinner("Analisando dados..."):
                # Análise
                analise = analisar_pagamentos(df_pagamentos)
                
                st.success("✅ Análise concluída!")
                
                # Exibir métricas
                st.subheader("📊 Resultados da Análise")
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric(
                        "Total de Linhas",
                        formatar_brasileiro(analise['total_linhas'])
                    )
                    st.metric(
                        "Pagamentos Válidos",
                        formatar_brasileiro(analise['pagamentos_validos'])
                    )
                    st.metric(
                        "Pagamentos sem Conta",
                        formatar_brasileiro(analise['pagamentos_sem_conta']),
                        delta_color="inverse"
                    )
                
                with col2:
                    st.metric(
                        "Valor Total Pago",
                        formatar_brasileiro(analise['valor_total'], 'monetario')
                    )
                    st.metric(
                        "Valor Médio",
                        formatar_brasileiro(analise['valor_medio'], 'monetario')
                    )
                    st.metric(
                        "Contas Duplicadas",
                        formatar_brasileiro(analise['duplicados']),
                        delta_color="inverse"
                    )
                
                with col3:
                    # Informações de detecção
                    st.info("**Colunas Detectadas:**")
                    if analise['coluna_conta']:
                        st.write(f"✓ Conta: `{analise['coluna_conta']}`")
                    else:
                        st.write("✗ Conta: Não detectada")
                    
                    if analise['coluna_valor']:
                        st.write(f"✓ Valor: `{analise['coluna_valor']}`")
                    else:
                        st.write("✗ Valor: Não detectada")
                    
                    if analise['coluna_nome']:
                        st.write(f"✓ Nome: `{analise['coluna_nome']}`")
                    else:
                        st.write("✗ Nome: Não detectada")
                
                # Visualização dos dados
                with st.expander("📋 Visualizar Dados (Primeiras 50 linhas)"):
                    st.dataframe(df_pagamentos.head(50))
                
                # Exportação
                st.subheader("📤 Exportar Resultados")
                
                col_exp1, col_exp2 = st.columns(2)
                
                with col_exp1:
                    # Exportar dados em CSV
                    if not df_pagamentos.empty:
                        csv_data = df_pagamentos.to_csv(index=False, sep=';', encoding='utf-8')
                        st.download_button(
                            label="📊 Baixar Dados (CSV)",
                            data=csv_data,
                            file_name=f"dados_pagamentos_{mes}_{ano}.csv",
                            mime="text/csv",
                            use_container_width=True
                        )
                
                with col_exp2:
                    # Gerar e baixar PDF
                    try:
                        pdf_bytes = gerar_relatorio_pdf(mes, ano, analise, df_pagamentos)
                        
                        if pdf_bytes:
                            st.download_button(
                                label="📄 Baixar Relatório (PDF)",
                                data=pdf_bytes,
                                file_name=f"relatorio_smdet_{mes}_{ano}.pdf",
                                mime="application/pdf",
                                use_container_width=True
                            )
                            st.success("✅ Relatório PDF disponível para download!")
                        else:
                            st.error("❌ Não foi possível gerar o PDF")
                    except Exception as e:
                        st.error(f"❌ Erro ao gerar PDF: {str(e)}")
                
                # Verificação dos valores
                st.markdown("---")
                st.subheader("✅ Verificação de Valores")
                
                if analise['coluna_valor']:
                    # Mostrar alguns valores convertidos para verificação
                    st.write("**Amostra de valores convertidos:**")
                    
                    valores_amostra = []
                    for i, valor in enumerate(df_pagamentos[analise['coluna_valor']].head(10)):
                        valor_convertido = converter_valor_simples(valor)
                        valores_amostra.append({
                            'Original': str(valor),
                            'Convertido': formatar_brasileiro(valor_convertido, 'monetario')
                        })
                    
                    df_amostra = pd.DataFrame(valores_amostra)
                    st.dataframe(df_amostra)
                    
                    st.info(f"**Valor total calculado:** {formatar_brasileiro(analise['valor_total'], 'monetario')}")
                    if analise['pagamentos_validos'] > 0:
                        st.info(f"**Valor médio:** {formatar_brasileiro(analise['valor_medio'], 'monetario')}")
        
        else:
            st.warning("⚠️ Nenhum arquivo válido carregado. Por favor, carregue arquivos CSV ou Excel.")
    
    else:
        # Tela inicial
        st.info("👈 **Para começar:**")
        st.markdown("""
        1. **Carregue os arquivos** no menu à esquerda
        2. **Selecione o período** de análise
        3. **Clique em "Realizar Análise"**
        
        **Formatos suportados:** CSV, Excel (.xlsx, .xls)
        
        **Funcionalidades:**
        - ✅ Análise automática de pagamentos
        - ✅ Cálculo CORRETO de valores totais e médios
        - ✅ Detecção automática de colunas
        - ✅ Exportação para CSV e PDF
        - ✅ Visualização dos dados
        """)

if __name__ == "__main__":
    main()
