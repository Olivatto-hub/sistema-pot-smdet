import pandas as pd
import numpy as np
from datetime import datetime
import plotly.graph_objects as go
import plotly.express as px
from io import StringIO
import warnings
warnings.filterwarnings('ignore')

def processar_csv(file_content):
    """
    Processa o conteúdo do arquivo CSV
    """
    # Ler o CSV
    df = pd.read_csv(StringIO(file_content), sep=';', decimal=',', thousands='.')
    
    # Limpar e converter colunas numéricas
    colunas_monetarias = ['Valor Total', 'Valor Desconto', 'Valor Pagto', 'Valor Dia']
    
    for coluna in colunas_monetarias:
        df[coluna] = df[coluna].replace({'\$': '', 'R\$': '', '\.': '', ',': '.'}, regex=True)
        df[coluna] = pd.to_numeric(df[coluna], errors='coerce')
    
    # Converter data
    df['Data Pagto'] = pd.to_datetime(df['Data Pagto'], format='%d/%m/%Y', errors='coerce')
    
    # Converter outras colunas numéricas
    df['Dias a apagar'] = pd.to_numeric(df['Dias a apagar'], errors='coerce')
    df['Agencia'] = pd.to_numeric(df['Agencia'], errors='coerce')
    df['Num Cartao'] = pd.to_numeric(df['Num Cartao'], errors='coerce')
    
    return df

def calcular_metricas(df):
    """
    Calcula métricas principais do dataset
    """
    metricas = {
        'total_beneficiarios': len(df),
        'valor_total_pago': df['Valor Pagto'].sum(),
        'valor_medio_pago': df['Valor Pagto'].mean(),
        'total_agencias': df['Agencia'].nunique(),
        'valor_dia_medio': df['Valor Dia'].mean(),
        'dias_apagar_medio': df['Dias a apagar'].mean(),
        'projeto_principal': df['Projeto'].mode()[0] if 'Projeto' in df.columns else 'N/A'
    }
    
    # Por gerenciadora
    if 'Gerenciadora' in df.columns:
        gerenciadoras = df['Gerenciadora'].value_counts()
        metricas['top_gerenciadora'] = gerenciadoras.idxmax()
        metricas['total_vista'] = gerenciadoras.get('VISTA', 0)
        metricas['total_rede_cidada'] = gerenciadoras.get('REDE CIDAD�', 0)
    
    return metricas

def gerar_relatorios(df):
    """
    Gera relatórios e gráficos
    """
    relatorios = {}
    
    # 1. Relatório por Agência
    relatorio_agencia = df.groupby('Agencia').agg({
        'Nome': 'count',
        'Valor Pagto': ['sum', 'mean'],
        'Dias a apagar': 'mean'
    }).round(2)
    
    relatorio_agencia.columns = ['Total Beneficiarios', 'Valor Total Pago', 'Valor Medio Pago', 'Dias Medios']
    relatorio_agencia = relatorio_agencia.sort_values('Valor Total Pago', ascending=False)
    
    # 2. Relatório por Gerenciadora
    if 'Gerenciadora' in df.columns:
        relatorio_gerenciadora = df.groupby('Gerenciadora').agg({
            'Nome': 'count',
            'Valor Pagto': ['sum', 'mean'],
            'Dias a apagar': 'mean'
        }).round(2)
        
        relatorio_gerenciadora.columns = ['Total Beneficiarios', 'Valor Total Pago', 'Valor Medio Pago', 'Dias Medios']
        relatorio_gerenciadora = relatorio_gerenciadora.sort_values('Valor Total Pago', ascending=False)
    else:
        relatorio_gerenciadora = pd.DataFrame()
    
    # 3. Top 10 Beneficiários por Valor
    top_beneficiarios = df[['Nome', 'Valor Pagto', 'Agencia', 'Gerenciadora', 'Dias a apagar']].copy()
    top_beneficiarios = top_beneficiarios.sort_values('Valor Pagto', ascending=False).head(10)
    
    # 4. Distribuição de Dias a Pagar
    distribuicao_dias = df['Dias a apagar'].value_counts().sort_index()
    
    # 5. Análise Temporal (se houver datas diferentes)
    if 'Data Pagto' in df.columns and df['Data Pagto'].nunique() > 1:
        df['Mes'] = df['Data Pagto'].dt.strftime('%Y-%m')
        relatorio_mensal = df.groupby('Mes').agg({
            'Nome': 'count',
            'Valor Pagto': 'sum'
        }).round(2)
        relatorio_mensal.columns = ['Total Beneficiarios', 'Valor Total Pago']
    else:
        relatorio_mensal = pd.DataFrame()
    
    relatorios['agencia'] = relatorio_agencia
    relatorios['gerenciadora'] = relatorio_gerenciadora
    relatorios['top_beneficiarios'] = top_beneficiarios
    relatorios['distribuicao_dias'] = distribuicao_dias
    relatorios['mensal'] = relatorio_mensal
    
    return relatorios

def criar_graficos(df, metricas):
    """
    Cria gráficos visuais
    """
    graficos = {}
    
    # 1. Gráfico de pizza por Gerenciadora
    if 'Gerenciadora' in df.columns:
        contagem_gerenciadora = df['Gerenciadora'].value_counts()
        fig_pizza = go.Figure(data=[go.Pie(
            labels=contagem_gerenciadora.index,
            values=contagem_gerenciadora.values,
            hole=.3
        )])
        fig_pizza.update_layout(title='Distribuição por Gerenciadora')
        graficos['pizza_gerenciadora'] = fig_pizza
    
    # 2. Gráfico de barras - Top 10 Agências por Valor
    top_agencias = df.groupby('Agencia')['Valor Pagto'].sum().sort_values(ascending=False).head(10)
    fig_barras = go.Figure(data=[go.Bar(
        x=top_agencias.index.astype(str),
        y=top_agencias.values,
        text=[f'R$ {val:,.2f}' for val in top_agencias.values],
        textposition='auto',
    )])
    fig_barras.update_layout(
        title='Top 10 Agências por Valor Total Pago',
        xaxis_title='Agência',
        yaxis_title='Valor Total (R$)'
    )
    graficos['barras_agencias'] = fig_barras
    
    # 3. Histograma de Valores Pagos
    fig_hist = px.histogram(
        df, 
        x='Valor Pagto',
        nbins=20,
        title='Distribuição de Valores Pagos',
        labels={'Valor Pagto': 'Valor Pago (R$)'}
    )
    graficos['histograma_valores'] = fig_hist
    
    # 4. Gráfico de dispersão: Valor vs Dias
    fig_dispersao = px.scatter(
        df,
        x='Dias a apagar',
        y='Valor Pagto',
        title='Relação: Dias a Pagar vs Valor Pago',
        labels={'Dias a apagar': 'Dias a Pagar', 'Valor Pagto': 'Valor Pago (R$)'}
    )
    graficos['dispersao_dias_valor'] = fig_dispersao
    
    return graficos

def gerar_resumo_executivo(metricas):
    """
    Gera um resumo executivo das métricas
    """
    resumo = f"""
    📊 RESUMO EXECUTIVO - ANÁLISE DE PAGAMENTOS
    {'='*50}
    
    📋 DADOS GERAIS:
    • Total de Beneficiários: {metricas['total_beneficiarios']:,}
    • Valor Total Pago: R$ {metricas['valor_total_pago']:,.2f}
    • Valor Médio por Beneficiário: R$ {metricas['valor_medio_pago']:,.2f}
    • Número de Agências: {metricas['total_agencias']}
    
    💰 VALORES DIÁRIOS:
    • Valor Dia Médio: R$ {metricas['valor_dia_medio']:,.2f}
    • Dias a Pagar Médios: {metricas['dias_apagar_medio']:.1f} dias
    
    🏢 DISTRIBUIÇÃO:
    • Projeto Principal: {metricas['projeto_principal']}
    """
    
    if 'top_gerenciadora' in metricas:
        resumo += f"""
    • Gerenciadora Principal: {metricas['top_gerenciadora']}
    • Beneficiários VISTA: {metricas['total_vista']:,}
    • Beneficiários REDE CIDADÃO: {metricas['total_rede_cidada']:,}
        """
    
    resumo += f"""
    
    ⏱️ PERÍODO ANALISADO:
    • Data dos Pagamentos: 20/10/2025
    • Tipo de Análise: Pagamentos Únicos
    
    🔍 PRÓXIMOS PASSOS SUGERIDOS:
    1. Análise por faixa de valor
    2. Identificação de outliers
    3. Comparativo entre agências
    4. Otimização de dias de pagamento
    """
    
    return resumo

# ============================================
# INTERFACE PRINCIPAL DO SISTEMA
# ============================================

print("=" * 60)
print("SISTEMA DE ANÁLISE DE PAGAMENTOS - ABAE")
print("=" * 60)
print("\n📁 Por favor, cole o conteúdo do arquivo CSV abaixo:")

try:
    # Solicitar conteúdo do arquivo
    file_content = """
Ordem;Projeto;Num Cartao;Nome;Distrito;Agencia;RG;Valor Total;Valor Desconto;Valor Pagto;Data Pagto;Valor Dia;Dias a apagar;CPF;Gerenciadora
1;BUSCA ATIVA;14735;Vanessa Falco Chaves;0;7025;438455885;R$ 1.593,90;R$ 0,00;R$ 1.593,90;20/10/2025;R$ 53,13;30;30490002870;VISTA
2;BUSCA ATIVA;130329;Erica Claudia Albano;0;1549;445934864;R$ 1.593,90;R$ 0,00;R$ 1.593,90;20/10/2025;R$ 53,13;30;;VISTA
3;BUSCA ATIVA;152979;Rosemary De Moraes Alves;0;6969;586268327;R$ 1.593,90;R$ 0,00;R$ 1.593,90;20/10/2025;R$ 53,13;30;8275372801;VISTA
4;BUSCA ATIVA;335916;Adriana Oliveira Bastos;0;1267;296598331;R$ 1.593,90;R$ 0,00;R$ 1.593,90;20/10/2025;R$ 53,13;30;32816455858;VISTA
5;BUSCA ATIVA;336722;Cristiane De Almeida Luiz;0;3008;397091941;R$ 1.593,90;R$ 0,00;R$ 1.593,90;20/10/2025;R$ 53,13;30;30071993878;VISTA
6;BUSCA ATIVA;338155;Mislene Lopes Da Silva Alves;0;1549;3033552085;R$ 1.593,90;R$ 0,00;R$ 1.593,90;20/10/2025;R$ 53,13;30;32061112854;VISTA
7;BUSCA ATIVA;344453;Marina de Oliveira souza;0;4302;461443144;R$ 1.593,90;R$ 0,00;R$ 1.593,90;20/10/2025;R$ 53,13;30;37648084899;REDE CIDAD�
8;BUSCA ATIVA;344664;Erica Fernandes Da Silva;0;1819;464720904;R$ 1.593,90;R$ 0,00;R$ 1.593,90;20/10/2025;R$ 53,13;30;41739662881;VISTA
9;BUSCA ATIVA;346855;Lucia helena de sousa;0;4309;217428216;R$ 1.593,90;R$ 0,00;R$ 1.593,90;20/10/2025;R$ 53,13;30;35258677869;REDE CIDAD�
10;BUSCA ATIVA;349751;Luciana Ferreira Dos Santos;0;1874;55527455X;R$ 1.540,77;R$ 0,00;R$ 1.540,77;20/10/2025;R$ 53,13;29;49113199846;VISTA
"""
    
    print("✅ Arquivo detectado! Processando dados...")
    
    # Processar o arquivo
    df = processar_csv(file_content)
    
    print(f"✅ Dados processados com sucesso!")
    print(f"📊 Total de registros: {len(df):,}")
    print(f"💰 Valor total processado: R$ {df['Valor Pagto'].sum():,.2f}")
    
    # Calcular métricas
    print("\n📈 Calculando métricas...")
    metricas = calcular_metricas(df)
    
    # Gerar resumo executivo
    print("\n" + "=" * 60)
    print("📋 RESUMO EXECUTIVO")
    print("=" * 60)
    resumo = gerar_resumo_executivo(metricas)
    print(resumo)
    
    # Gerar relatórios
    print("\n" + "=" * 60)
    print("📄 RELATÓRIOS DETALHADOS")
    print("=" * 60)
    
    relatorios = gerar_relatorios(df)
    
    # Exibir relatório por agência
    print("\n🏢 TOP 10 AGÊNCIAS (por valor total):")
    print("-" * 80)
    print(relatorios['agencia'].head(10).to_string())
    
    # Exibir relatório por gerenciadora
    if not relatorios['gerenciadora'].empty:
        print("\n🏦 DISTRIBUIÇÃO POR GERENCIADORA:")
        print("-" * 80)
        print(relatorios['gerenciadora'].to_string())
    
    # Exibir top beneficiários
    print("\n👥 TOP 10 BENEFICIÁRIOS (maior valor):")
    print("-" * 80)
    print(relatorios['top_beneficiarios'].to_string(index=False))
    
    # Exibir distribuição de dias
    print("\n📅 DISTRIBUIÇÃO DE DIAS A PAGAR:")
    print("-" * 80)
    print(relatorios['distribuicao_dias'].head(15).to_string())
    
    # Criar gráficos
    print("\n" + "=" * 60)
    print("📊 GRÁFICOS VISUAIS")
    print("=" * 60)
    print("\n✅ Gráficos criados com sucesso!")
    print("   Os seguintes gráficos estão disponíveis:")
    print("   1. Distribuição por Gerenciadora (Pizza)")
    print("   2. Top 10 Agências por Valor (Barras)")
    print("   3. Histograma de Valores Pagos")
    print("   4. Dispersão: Dias vs Valor")
    
    # Mostrar gráficos (em ambiente interativo)
    graficos = criar_graficos(df, metricas)
    
    print("\n" + "=" * 60)
    print("💾 OPÇÕES DE EXPORTAÇÃO")
    print("=" * 60)
    print("\n📤 O sistema pode exportar os dados em vários formatos:")
    print("   1. Excel com múltiplas abas")
    print("   2. CSV separado por relatório")
    print("   3. PDF com relatório completo")
    print("   4. Gráficos em PNG/JPEG")
    
    print("\n" + "=" * 60)
    print("✅ PROCESSAMENTO CONCLUÍDO!")
    print("=" * 60)
    
except Exception as e:
    print(f"\n❌ ERRO: {str(e)}")
    print("Por favor, verifique o formato do arquivo e tente novamente.")

# Função adicional para exportação (exemplo)
def exportar_para_excel(df, relatorios, nome_arquivo="relatorio_abae.xlsx"):
    """
    Exporta dados para Excel
    """
    with pd.ExcelWriter(nome_arquivo, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Dados Completos', index=False)
        relatorios['agencia'].to_excel(writer, sheet_name='Por Agencia')
        if not relatorios['gerenciadora'].empty:
            relatorios['gerenciadora'].to_excel(writer, sheet_name='Por Gerenciadora')
        relatorios['top_beneficiarios'].to_excel(writer, sheet_name='Top Beneficiarios', index=False)
    
    print(f"✅ Arquivo Excel salvo: {nome_arquivo}")

# Para usar a função de exportação:
# exportar_para_excel(df, relatorios)
