# Sistema de Gestão e Monitoramento de Pagamentos - POT (SMDET)

Sistema web desenvolvido em Python/Streamlit para a **Secretaria Municipal de Desenvolvimento Econômico e Trabalho (SMDET)**. O objetivo é centralizar, validar, monitorar e gerar relatórios das folhas de pagamento dos beneficiários do **Programa Operação Trabalho (POT)**.

## 🎯 Visão Geral

O sistema automatiza o recebimento de arquivos de diferentes fontes (CSV/Excel), padroniza os dados, aplica regras de validação ("Malha Fina") para detectar inconsistências críticas e realiza a conferência com arquivos bancários.

## 🚀 Funcionalidades Principais

### 1. Processamento de Arquivos (ETL)
- **Upload Flexível:** Suporte simultâneo a arquivos CSV e Excel (`.xlsx`).
- **Padronização Automática:** Algoritmo inteligente que reconhece diferentes nomes para a mesma coluna (ex: `NumCartão`, `Cartão`, `Código` são transformados automaticamente para `num_cartao`).
- **Limpeza de Dados:** Remoção automática de linhas de "totais" no rodapé dos arquivos para evitar duplicação de valores.
- **Detecção de Referência:** Identificação automática do Mês e Ano de competência baseada no nome do arquivo ou datas internas.

### 2. Validação e Malha Fina (Quality Assurance)
- **Inconsistências Críticas:** Identifica registros sem CPF ou sem Número de Cartão.
- **Detecção de Fraudes:** Alerta duplicidades (mesmo CPF com múltiplos cartões/nomes ou mesmo cartão em múltiplos CPFs).
- **Correção Online:** Interface para edição direta de dados incorretos no banco de dados (para perfis autorizados).

### 3. Conferência Bancária (Banco do Brasil)
- **Processamento de Retorno:** Leitura de arquivos `.txt` de retorno do banco.
- **Cruzamento de Dados:** Comparação automática entre nomes no sistema vs. nomes no banco.
- **Relatório de Divergências:** Histórico e exportação PDF das discrepâncias encontradas.

### 4. Relatórios e Exportação
- **Dashboard Executivo:** Métricas de total pago, beneficiários e gráficos interativos (Plotly).
- **Relatórios PDF:** Geração de relatórios gerenciais e logs de auditoria utilizando a biblioteca FPDF.
- **Exportação de Dados:** Planilhas consolidadas em Excel/CSV e arquivo de remessa (`.txt`) no layout padrão do Banco do Brasil.

### 5. Segurança e Auditoria
- **Login Institucional:** Restrito ao domínio `@prefeitura.sp.gov.br`.
- **Logs de Auditoria:** Rastreabilidade completa (quem fez o quê e quando).
- **Troca de Senha:** Obrigatoriedade de alteração de senha no primeiro acesso.

## 👥 Perfis de Acesso (RBAC)

**1. Analista (user)**
- Visualização de Dashboard.
- Upload de arquivos.
- Geração de relatórios e exportações.

**2. Líder/Gestor (admin_equipe)**
- Todas as funções de Analista.
- **Gestão de Equipe:** Cadastrar e remover usuários.
- **Edição de Dados:** Permissão para corrigir registros e excluir arquivos incorretos.

**3. Admin TI (admin_ti)**
- Acesso total ao sistema.
- Visualização e limpeza de Logs de Auditoria.
- Reset total do banco de dados (Limpeza de Tabelas).

## 🛠️ Tecnologias Utilizadas

- **Linguagem:** Python 3.8+
- **Frontend:** Streamlit
- **Banco de Dados:** SQLite (`pot_system.db`)
- **Bibliotecas Principais:** Pandas, Plotly, FPDF, Matplotlib, Openpyxl.

## 📋 Como Executar o Projeto

**1. Instale as dependências**

Certifique-se de ter o Python instalado e execute o comando abaixo no terminal:

```bash
pip install streamlit pandas plotly fpdf xlsxwriter openpyxl matplotlib
```
2. Execute a aplicação

No terminal, dentro da pasta do projeto:

```Bash
streamlit run app.py
```

3. Primeiro Acesso

O sistema gera automaticamente um usuário administrador na primeira execução:

E-mail: admin@prefeitura.sp.gov.br

Senha Inicial: smdet2025

Nota: O sistema solicitará a troca desta senha imediatamente após o login.

📂 Estrutura de Arquivos
app.py: Código fonte principal da aplicação.

pot_system.db: Banco de dados SQLite (criado automaticamente na execução).

README.md: Documentação do sistema.

Desenvolvido para a SMDET - Prefeitura de São Paulo por Ricardo Olivatto APDO-TI
