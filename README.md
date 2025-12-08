Sistema de Gestão e Monitoramento de Pagamentos - POT (SMDET)

Sistema web corporativo desenvolvido para a Secretaria Municipal de Desenvolvimento Econômico e Trabalho (SMDET) da Prefeitura de São Paulo. A plataforma centraliza, valida e audita o processamento das folhas de pagamento do Programa Operação Trabalho (POT), garantindo conformidade e segurança dos dados.

🎯 Visão Geral

O sistema automatiza o fluxo de recebimento de arquivos (ETL), aplica regras rigorosas de validação ("Malha Fina") para detectar fraudes e duplicidades, realiza o cruzamento com arquivos bancários e fornece um ambiente seguro com controle de acesso baseado em perfis (RBAC) e auditoria completa de ações.

🚀 Funcionalidades Principais

1. Processamento Inteligente (ETL)

Upload Universal: Suporte a arquivos Excel (.xlsx) e CSV simultâneos.

Padronização Automática: Algoritmo que identifica e normaliza colunas (ex: NumCartão, Cartão, Código -> num_cartao).

Sanitização: Remoção automática de linhas de "totais" e caracteres especiais que quebram integrações bancárias.

2. Malha Fina e Segurança (Anti-Fraude)

Detecção de Conflitos Cadastrais: Identifica CPFs que aparecem com Nomes ou Cartões diferentes em registros distintos.

Prevenção de Fraudes: Alerta imediato se um único Cartão Bancário estiver associado a múltiplos CPFs diferentes.

Validação Cruzada: Diferencia pagamentos recorrentes legítimos de duplicidades indevidas.

3. Conferência Bancária

Conciliação Automática: Processamento de arquivos de retorno do Banco do Brasil (REL.CADASTRO.OT).

Relatório de Divergências: Aponta inconsistências entre o banco de dados da Prefeitura e o cadastro do Banco (ex: Nome divergente).

4. Gestão e Auditoria

Controle de Acesso (RBAC):

Analista: Operação básica.

Líder/Gestor: Correção de dados e gestão de equipe.

Admin TI: Controle total, limpeza de dados e acesso aos logs.

Logs de Auditoria: Registro imutável de todas as ações críticas (quem fez, o que fez e quando).

Manuais Integrados: Documentação específica por perfil disponível dentro da plataforma.

🛠️ Tecnologias Utilizadas

Frontend/Backend: Python + Streamlit

Banco de Dados: SQLite (com suporte nativo para migração PostgreSQL)

Análise de Dados: Pandas, NumPy

Visualização: Plotly Express

Relatórios: FPDF (Geração de PDFs dinâmicos)

📋 Como Executar o Projeto

Pré-requisitos

Certifique-se de ter o Python 3.9+ instalado.

Clone o repositório:

git clone [https://github.com/seu-usuario/sistema-pot-smdet.git](https://github.com/seu-usuario/sistema-pot-smdet.git)
cd sistema-pot-smdet


Instale as dependências:

pip install -r requirements.txt


Execute a aplicação:

streamlit run app.py


🔐 Primeiro Acesso (Admin Padrão)

O sistema cria automaticamente um superusuário na primeira execução:

E-mail: admin@prefeitura.sp.gov.br

Senha Inicial: smdet2025

Nota: O sistema exigirá a troca desta senha imediatamente após o login.

📂 Estrutura de Arquivos

app.py: Código fonte principal (Monolito).

pot_system.db: Banco de dados local (criado automaticamente).

requirements.txt: Lista de bibliotecas necessárias.

README.md: Documentação do projeto.

Desenvolvido para a Prefeitura de São Paulo - SMDET.
