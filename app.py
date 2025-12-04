import pandas as pd
from io import StringIO

# Conteúdo do arquivo fornecido
file_content = """Ordem;Projeto;Num Cartao;Nome;Distrito;Agencia;RG;Valor Total;Valor Desconto;Valor Pagto;Data Pagto;Valor Dia;Dias a apagar;CPF;Gerenciadora
1;BUSCA ATIVA;14735;Vanessa Falco Chaves;0;7025;438455885;R$ 1.593,90;R$ 0,00;R$ 1.593,90;20/10/2025;R$ 53,13;30;30490002870;VISTA
2;BUSCA ATIVA;130329;Erica Claudia Albano;0;1549;445934864;R$ 1.593,90;R$ 0,00;R$ 1.593,90;20/10/2025;R$ 53,13;30;;VISTA
3;BUSCA ATIVA;152979;Rosemary De Moraes Alves;0;6969;586268327;R$ 1.593,90;R$ 0,00;R$ 1.593,90;20/10/2025;R$ 53,13;30;8275372801;VISTA
... (o restante do conteúdo)"""

# Usar StringIO para simular um arquivo a partir da string
df = pd.read_csv(StringIO(file_content), sep=';', decimal=',', thousands='.')

# Verificar as primeiras linhas
print("Primeiras 5 linhas do DataFrame:")
print(df.head())

# Verificar informações do DataFrame
print("\nInformações do DataFrame:")
print(df.info())

# Verificar as colunas
print("\nColunas do DataFrame:")
print(df.columns.tolist())

# Verificar o número de linhas
print(f"\nNúmero total de linhas: {len(df)}")

# Exibir algumas estatísticas básicas
print("\nEstatísticas básicas:")
print(df.describe(include='all'))
