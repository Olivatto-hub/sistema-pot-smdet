import pandas as pd
import os
import re
from datetime import datetime
import matplotlib.pyplot as plt
import numpy as np
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
import warnings
warnings.filterwarnings('ignore')

class SistemaPOTCompleto:
    def __init__(self):
        self.df = None
        self.dados_limpos = None
        self.arquivo_processado = False
        self.nome_arquivo = ""
        self.total_pagamentos = 0
        self.resumo = {}
        
    def converter_valor(self, valor_str):
        """Converte valores monetários do formato brasileiro para float"""
        if pd.isna(valor_str) or valor_str == '':
            return 0.0
        
        # Remover R$, pontos e converter vírgula para ponto
        try:
            valor_str = str(valor_str).replace('R$', '').replace(' ', '').strip()
            valor_str = valor_str.replace('.', '').replace(',', '.')
            return float(valor_str)
        except:
            return 0.0
    
    def processar_arquivo(self, caminho_arquivo):
        """Processa arquivo CSV de pagamentos do POT"""
        try:
            print(f"🔍 INICIANDO PROCESSAMENTO DO ARQUIVO")
            print(f"📂 Arquivo: {os.path.basename(caminho_arquivo)}")
            
            # Verificar se arquivo existe
            if not os.path.exists(caminho_arquivo):
                print("❌ ERRO: Arquivo não encontrado!")
                return False
            
            # Tentar diferentes encodings
            encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
            
            for encoding in encodings:
                try:
                    # Ler o arquivo linha por linha primeiro para debug
                    with open(caminho_arquivo, 'r', encoding=encoding) as f:
                        linhas = f.readlines()
                    
                    print(f"✓ Encoding detectado: {encoding}")
                    print(f"✓ Total de linhas no arquivo: {len(linhas)}")
                    
                    # Verificar se o arquivo tem conteúdo
                    if len(linhas) < 2:
                        print("❌ ERRO: Arquivo muito pequeno ou vazio!")
                        return False
                    
                    # Mostrar cabeçalho
                    print(f"📋 Cabeçalho: {linhas[0][:100]}...")
                    
                    # Processar com pandas
                    self.df = pd.read_csv(caminho_arquivo, delimiter=';', encoding=encoding)
                    break
                    
                except UnicodeDecodeError:
                    continue
                except Exception as e:
                    print(f"❌ Erro ao ler com encoding {encoding}: {str(e)[:50]}")
            
            if self.df is None:
                print("❌ ERRO: Não foi possível ler o arquivo com nenhum encoding!")
                return False
            
            print(f"✅ ARQUIVO LIDO COM SUCESSO!")
            print(f"📊 Shape do DataFrame: {self.df.shape}")
            print(f"📝 Colunas: {list(self.df.columns)}")
            
            # Limpar dados
            self._limpar_dados()
            
            # Calcular totais e estatísticas
            self._calcular_estatisticas()
            
            self.arquivo_processado = True
            self.nome_arquivo = os.path.basename(caminho_arquivo)
            
            print(f"\n🎉 PROCESSAMENTO CONCLUÍDO COM SUCESSO!")
            print(f"📈 Total de registros válidos: {len(self.dados_limpos)}")
            print(f"💰 Valor total processado: R$ {self.total_pagamentos:,.2f}")
            
            return True
            
        except Exception as e:
            print(f"❌ ERRO CRÍTICO NO PROCESSAMENTO: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def _limpar_dados(self):
        """Limpa e prepara os dados para análise"""
        print(f"\n🧹 LIMPANDO DADOS...")
        
        # Criar cópia para manipulação
        df_limpo = self.df.copy()
        
        # Remover linhas totalmente vazias
        df_limpo = df_limpo.dropna(how='all')
        
        # Converter colunas de valor
        colunas_valor = ['Valor Total', 'Valor Desconto', 'Valor Pagto', 'Valor Dia']
        
        for coluna in colunas_valor:
            if coluna in df_limpo.columns:
                df_limpo[coluna] = df_limpo[coluna].apply(self.converter_valor)
                print(f"✓ Convertida coluna: {coluna}")
        
        # Converter 'Dias a apagar' para numérico
        if 'Dias a apagar' in df_limpo.columns:
            df_limpo['Dias a apagar'] = pd.to_numeric(df_limpo['Dias a apagar'], errors='coerce')
        
        # Converter 'Data Pagto' para datetime
        if 'Data Pagto' in df_limpo.columns:
            df_limpo['Data Pagto'] = pd.to_datetime(df_limpo['Data Pagto'], format='%d/%m/%Y', errors='coerce')
        
        # Remover linhas onde 'Valor Pagto' é zero ou negativo
        if 'Valor Pagto' in df_limpo.columns:
            df_limpo = df_limpo[df_limpo['Valor Pagto'] > 0]
        
        self.dados_limpos = df_limpo
        print(f"✅ Dados limpos: {len(df_limpo)} registros válidos")
    
    def _calcular_estatisticas(self):
        """Calcula estatísticas dos dados"""
        print(f"\n📊 CALCULANDO ESTATÍSTICAS...")
        
        if self.dados_limpos is None or len(self.dados_limpos) == 0:
            print("⚠️  Nenhum dado para calcular estatísticas")
            return
        
        df = self.dados_limpos
        
        # Totais
        self.total_pagamentos = df['Valor Pagto'].sum() if 'Valor Pagto' in df.columns else 0
        
        # Resumo por agência
        if 'Agencia' in df.columns:
            resumo_agencia = df.groupby('Agencia').agg({
                'Valor Pagto': ['sum', 'count'],
                'Nome': 'first'
            }).round(2)
            print(f"✓ Resumo por agência calculado")
        
        # Média de valores
        media_pagto = df['Valor Pagto'].mean() if 'Valor Pagto' in df.columns else 0
        media_dia = df['Valor Dia'].mean() if 'Valor Dia' in df.columns else 0
        
        # Distribuição de dias
        if 'Dias a apagar' in df.columns:
            distribuicao_dias = df['Dias a apagar'].value_counts().sort_index()
        
        # Agências com mais pagamentos
        if 'Agencia' in df.columns:
            top_agencias = df['Agencia'].value_counts().head(10)
        
        print(f"✅ Estatísticas calculadas")
        print(f"   • Total pagamentos: R$ {self.total_pagamentos:,.2f}")
        print(f"   • Média por pagamento: R$ {media_pagto:,.2f}")
    
    def gerar_relatorio(self, caminho_saida=None):
        """Gera relatório completo em Excel"""
        if not self.arquivo_processado:
            print("❌ Nenhum arquivo processado. Use processar_arquivo() primeiro.")
            return False
        
        try:
            if caminho_saida is None:
                caminho_saida = f"relatorio_pot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            
            print(f"\n📄 GERANDO RELATÓRIO EXCEL...")
            
            with pd.ExcelWriter(caminho_saida, engine='openpyxl') as writer:
                # 1. Dados completos
                self.dados_limpos.to_excel(writer, sheet_name='Dados Completos', index=False)
                
                # 2. Resumo por Agência
                if 'Agencia' in self.dados_limpos.columns:
                    resumo_agencia = self.dados_limpos.groupby('Agencia').agg({
                        'Valor Pagto': ['sum', 'count', 'mean', 'std'],
                        'Nome': 'first'
                    }).round(2)
                    resumo_agencia.to_excel(writer, sheet_name='Por Agência')
                
                # 3. Top 20 maiores pagamentos
                top_pagamentos = self.dados_limpos.nlargest(20, 'Valor Pagto')[['Nome', 'Agencia', 'Valor Pagto', 'Data Pagto']]
                top_pagamentos.to_excel(writer, sheet_name='Top Pagamentos', index=False)
                
                # 4. Estatísticas gerais
                stats_df = pd.DataFrame({
                    'Métrica': ['Total de Pagamentos', 'Valor Total', 'Média por Pagamento', 
                              'Maior Pagamento', 'Menor Pagamento', 'Número de Agências'],
                    'Valor': [
                        len(self.dados_limpos),
                        f"R$ {self.total_pagamentos:,.2f}",
                        f"R$ {self.dados_limpos['Valor Pagto'].mean():,.2f}",
                        f"R$ {self.dados_limpos['Valor Pagto'].max():,.2f}",
                        f"R$ {self.dados_limpos['Valor Pagto'].min():,.2f}",
                        self.dados_limpos['Agencia'].nunique() if 'Agencia' in self.dados_limpos.columns else 0
                    ]
                })
                stats_df.to_excel(writer, sheet_name='Estatísticas', index=False)
            
            print(f"✅ RELATÓRIO GERADO COM SUCESSO!")
            print(f"📁 Salvo em: {caminho_saida}")
            
            return True
            
        except Exception as e:
            print(f"❌ ERRO AO GERAR RELATÓRIO: {str(e)}")
            return False
    
    def mostrar_dashboard(self):
        """Mostra dashboard com principais métricas"""
        if not self.arquivo_processado:
            print("❌ Nenhum arquivo processado.")
            return
        
        print("\n" + "="*60)
        print("📊 DASHBOARD DE MONITORAMENTO DE PAGAMENTOS POT")
        print("="*60)
        
        df = self.dados_limpos
        
        # Métricas principais
        print(f"\n📈 MÉTRICAS PRINCIPAIS:")
        print(f"   • Total de Pagamentos: {len(df):,}")
        print(f"   • Valor Total: R$ {self.total_pagamentos:,.2f}")
        print(f"   • Média por Pagamento: R$ {df['Valor Pagto'].mean():,.2f}")
        print(f"   • Data do Processamento: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        
        # Top 5 agências
        if 'Agencia' in df.columns:
            print(f"\n🏢 TOP 5 AGÊNCIAS (por valor):")
            top_agencias = df.groupby('Agencia')['Valor Pagto'].sum().nlargest(5)
            for agencia, valor in top_agencias.items():
                print(f"   • Agência {agencia}: R$ {valor:,.2f}")
        
        # Distribuição de valores
        print(f"\n💰 DISTRIBUIÇÃO DE VALORES:")
        print(f"   • Maior Pagamento: R$ {df['Valor Pagto'].max():,.2f}")
        print(f"   • Menor Pagamento: R$ {df['Valor Pagto'].min():,.2f}")
        print(f"   • Mediana: R$ {df['Valor Pagto'].median():,.2f}")
        
        # Distribuição por dias
        if 'Dias a apagar' in df.columns:
            print(f"\n📅 DIAS A PAGAR:")
            dias_stats = df['Dias a apagar'].describe()
            print(f"   • Média: {dias_stats['mean']:.1f} dias")
            print(f"   • Máximo: {dias_stats['max']:.0f} dias")
            print(f"   • Mínimo: {dias_stats['min']:.0f} dias")
        
        print("\n" + "="*60)
    
    def buscar_por_nome(self, nome):
        """Busca pagamentos por nome"""
        if not self.arquivo_processado:
            print("❌ Nenhum arquivo processado.")
            return None
        
        resultados = self.dados_limpos[self.dados_limpos['Nome'].str.contains(nome, case=False, na=False)]
        
        if len(resultados) == 0:
            print(f"⚠️  Nenhum resultado encontrado para '{nome}'")
            return None
        
        print(f"\n🔍 RESULTADOS PARA '{nome}':")
        print(f"   • Encontrados: {len(resultados)} registros")
        print(f"   • Valor Total: R$ {resultados['Valor Pagto'].sum():,.2f}")
        
        # Mostrar primeiros resultados
        for idx, row in resultados.head(5).iterrows():
            print(f"\n   [{idx+1}] {row['Nome']}")
            print(f"      Agência: {row.get('Agencia', 'N/A')}")
            print(f"      Valor: R$ {row['Valor Pagto']:,.2f}")
            print(f"      Data: {row.get('Data Pagto', 'N/A')}")
        
        return resultados
    
    def analisar_por_agencia(self, agencia=None):
        """Analisa pagamentos por agência"""
        if not self.arquivo_processado:
            print("❌ Nenhum arquivo processado.")
            return None
        
        df = self.dados_limpos
        
        if 'Agencia' not in df.columns:
            print("⚠️  Coluna 'Agencia' não encontrada nos dados.")
            return None
        
        if agencia:
            resultados = df[df['Agencia'] == agencia]
            if len(resultados) == 0:
                print(f"⚠️  Nenhum resultado para agência {agencia}")
                return None
            
            print(f"\n🏢 ANÁLISE DA AGÊNCIA {agencia}:")
            print(f"   • Total de Pagamentos: {len(resultados)}")
            print(f"   • Valor Total: R$ {resultados['Valor Pagto'].sum():,.2f}")
            print(f"   • Média por Pagamento: R$ {resultados['Valor Pagto'].mean():,.2f}")
            
            return resultados
        else:
            # Análise de todas as agências
            analise = df.groupby('Agencia').agg({
                'Valor Pagto': ['sum', 'count', 'mean'],
                'Nome': 'first'
            }).round(2)
            
            analise.columns = ['Valor Total', 'Quantidade', 'Média', 'Exemplo Nome']
            analise = analise.sort_values('Valor Total', ascending=False)
            
            print(f"\n🏢 ANÁLISE DE TODAS AS AGÊNCIAS:")
            print(f"   • Total de Agências: {len(analise)}")
            print(f"   • Agência com mais pagamentos: {analise.iloc[0].name}")
            print(f"   • Valor total desta agência: R$ {analise.iloc[0]['Valor Total']:,.2f}")
            
            return analise
    
    def exportar_para_csv(self, caminho_saida):
        """Exporta dados limpos para CSV"""
        if not self.arquivo_processado:
            print("❌ Nenhum arquivo processado.")
            return False
        
        try:
            self.dados_limpos.to_csv(caminho_saida, index=False, sep=';', encoding='utf-8')
            print(f"✅ Dados exportados para: {caminho_saida}")
            return True
        except Exception as e:
            print(f"❌ Erro ao exportar: {str(e)}")
            return False
    
    def gerar_grafico_distribuicao(self):
        """Gera gráfico de distribuição de valores"""
        if not self.arquivo_processado:
            print("❌ Nenhum arquivo processado.")
            return
        
        try:
            import matplotlib.pyplot as plt
            
            valores = self.dados_limpos['Valor Pagto']
            
            plt.figure(figsize=(10, 6))
            plt.hist(valores, bins=50, alpha=0.7, color='blue', edgecolor='black')
            plt.title('Distribuição dos Valores de Pagamento', fontsize=14)
            plt.xlabel('Valor (R$)', fontsize=12)
            plt.ylabel('Frequência', fontsize=12)
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            
            # Salvar gráfico
            caminho_grafico = f"grafico_distribuicao_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            plt.savefig(caminho_grafico, dpi=300)
            plt.show()
            
            print(f"✅ Gráfico salvo em: {caminho_grafico}")
            
        except Exception as e:
            print(f"⚠️  Não foi possível gerar gráfico: {str(e)}")

# ==============================================
# FUNÇÃO PRINCIPAL DE EXECUÇÃO
# ==============================================

def main():
    """Função principal para executar o sistema"""
    print("="*60)
    print("SISTEMA COMPLETO DE MONITORAMENTO DE PAGAMENTOS - POT")
    print("="*60)
    
    sistema = SistemaPOTCompleto()
    
    # Solicitar arquivo ao usuário
    while True:
        caminho_arquivo = input("\n📁 Digite o caminho completo do arquivo CSV: ").strip()
        
        if caminho_arquivo.lower() == 'sair':
            print("👋 Encerrando sistema...")
            return
        
        # Tentar processar o arquivo
        sucesso = sistema.processar_arquivo(caminho_arquivo)
        
        if sucesso:
            break
        else:
            print("\n⚠️  Deseja tentar outro arquivo? (s/n) ou 'sair' para encerrar")
            resposta = input("> ").lower()
            if resposta != 's':
                print("👋 Encerrando sistema...")
                return
    
    # Mostrar dashboard
    sistema.mostrar_dashboard()
    
    # Menu interativo
    while True:
        print("\n" + "="*60)
        print("MENU PRINCIPAL")
        print("="*60)
        print("1. 🔍 Buscar por nome")
        print("2. 🏢 Analisar por agência")
        print("3. 📄 Gerar relatório completo (Excel)")
        print("4. 📊 Gerar gráfico de distribuição")
        print("5. 💾 Exportar dados limpos (CSV)")
        print("6. 📋 Mostrar dashboard")
        print("7. 🔄 Processar outro arquivo")
        print("8. 🚪 Sair")
        print("="*60)
        
        opcao = input("\n🎯 Selecione uma opção (1-8): ").strip()
        
        if opcao == '1':
            nome = input("🔍 Digite o nome para buscar: ").strip()
            sistema.buscar_por_nome(nome)
        
        elif opcao == '2':
            print("\n🏢 Análise por Agência:")
            print("   a) Analisar agência específica")
            print("   b) Análise de todas as agências")
            sub_opcao = input("   Selecione (a/b): ").strip().lower()
            
            if sub_opcao == 'a':
                agencia = input("   Digite o número da agência: ").strip()
                sistema.analisar_por_agencia(agencia)
            elif sub_opcao == 'b':
                sistema.analisar_por_agencia()
        
        elif opcao == '3':
            caminho = input("📄 Digite o caminho para salvar (ou Enter para padrão): ").strip()
            if caminho == '':
                sistema.gerar_relatorio()
            else:
                sistema.gerar_relatorio(caminho)
        
        elif opcao == '4':
            sistema.gerar_grafico_distribuicao()
        
        elif opcao == '5':
            caminho = input("💾 Digite o caminho para salvar o CSV: ").strip()
            if caminho:
                sistema.exportar_para_csv(caminho)
        
        elif opcao == '6':
            sistema.mostrar_dashboard()
        
        elif opcao == '7':
            main()  # Reiniciar processo
            break
        
        elif opcao == '8':
            print("\n👋 Encerrando sistema...")
            break
        
        else:
            print("❌ Opção inválida! Tente novamente.")
        
        input("\n⏎ Pressione Enter para continuar...")

# ==============================================
# EXEMPLO DE USO RÁPIDO (TESTE DIRETO)
# ==============================================

def teste_rapido(caminho_arquivo):
    """Função para teste rápido do sistema"""
    print("🧪 INICIANDO TESTE RÁPIDO DO SISTEMA...")
    
    sistema = SistemaPOTCompleto()
    
    # Processar arquivo
    if sistema.processar_arquivo(caminho_arquivo):
        # Mostrar dashboard
        sistema.mostrar_dashboard()
        
        # Gerar relatório
        sistema.gerar_relatorio()
        
        # Exportar CSV
        sistema.exportar_para_csv("dados_limpos_pot.csv")
        
        print("\n✅ TESTE CONCLUÍDO COM SUCESSO!")
        return True
    else:
        print("\n❌ FALHA NO TESTE!")
        return False

# ==============================================
# EXECUTAR SISTEMA
# ==============================================

if __name__ == "__main__":
    # Para usar de forma interativa:
    main()
    
    # Para teste rápido com arquivo específico:
    # teste_rapido("PGTO ABASTECE SETEMBRO.csv")
