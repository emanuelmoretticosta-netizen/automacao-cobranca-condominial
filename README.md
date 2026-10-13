# Automação de Cobrança Condominial 🏢

Script em Python que automatiza a rotina de verificação de cotas em atraso
num sistema de gestão condominial baseado na web. Faz login sozinho,
percorre os condomínios do dia, identifica unidades inadimplentes, aplica
regras de negócio específicas e gera relatórios organizados em texto.

Esse processo, que antes era feito manualmente conferindo unidade por
unidade na tela, passou a levar poucos minutos rodando o script.

## Contexto

Em administradoras de condomínios, o setor de cobrança precisa, todos os
dias, verificar quais unidades estão com parcelas em atraso em cada
condomínio sob sua responsabilidade. Esse processo manual é repetitivo,
sujeito a erro e consome bastante tempo. Este projeto automatiza
integralmente esse fluxo.

## Funcionalidades

- **Login automático** no sistema, com relogin automático caso a sessão
  caia no meio da execução (navegador fechado ou sessão expirada)
- **Agenda por dia da semana**: cada condomínio é processado apenas nos
  dias configurados, simulando a rotina real do setor de cobrança
- **Navegação automatizada**: troca de condomínio, acessa a tela de
  cotas em atraso e rola a página para carregar a lista completa de
  unidades (a interface carrega os dados aos poucos, como um feed)
- **Leitura de dados**: para cada unidade inadimplente, entra no detalhe
  e lê todas as parcelas em atraso (vencimento, valor, multa, correção,
  juros e honorários)
- **Aplicação de regras de negócio próprias**, não contempladas pelo
  cálculo padrão do sistema, como:
  - Só considerar uma parcela em cobrança após um prazo mínimo de
    carência contado do vencimento
  - Ajustar o percentual de honorários aplicado sobre o valor total
  - Sinalizar unidades com grande volume de parcelas em aberto para
    tratamento separado (indício de processo judicial em andamento)
  - Marcar unidades de valor muito alto para conferência manual, em
    condomínios de grande porte, acelerando o processamento
- **Leitura de acordos em andamento**, com o detalhamento de parcelas e
  das cotas originais que compõem cada acordo
- **Geração de relatórios em texto** (`.txt`), um por condomínio, prontos
  para uso no dia a dia da cobrança
- **Resiliência a falhas**: nova tentativa automática (até 6 vezes por
  condomínio) em caso de instabilidade da sessão, sem travar o restante
  da execução

## Tecnologias utilizadas

- **Python**
- **Selenium** (automação de navegador)
- **python-dotenv** (variáveis de ambiente)

## Como rodar o projeto localmente

### Pré-requisitos
- Python 3.10 ou superior instalado
- Google Chrome instalado
- Acesso válido ao sistema a ser automatizado (usuário e senha)

### Passo a passo

1. Clone o repositório:
```bash
   git clone https://github.com/emanuelmoretticosta-netizen/automacao-cobranca-condominial.git
   cd automacao-cobranca-condominial
```

2. Crie um ambiente virtual e ative:
```bash
   python -m venv venv

   # Windows
   venv\Scripts\activate

   # Mac/Linux
   source venv/bin/activate
```

3. Instale as dependências:
```bash
   pip install selenium python-dotenv
```

4. Crie o arquivo `.env` a partir do exemplo e preencha com suas
   credenciais:
```bash
   # Windows
   copy .env.example .env

   # Mac/Linux
   cp .env.example .env
```
LELLO_USUARIO=seu_usuario_aqui
LELLO_SENHA=sua_senha_aqui


5. Crie o arquivo de configuração dos condomínios a partir do exemplo:
```bash
   # Windows
   copy config_condominios.example.py config_condominios.py

   # Mac/Linux
   cp config_condominios.example.py config_condominios.py
```
   Edite `config_condominios.py` com os condomínios e códigos reais,
   organizados por dia da semana.

6. Rode o script:
```bash
   python relatorio_diario.py
```

Os relatórios (`relatorio_NOMECONDOMINIO.txt` e `acordos_NOMECONDOMINIO.txt`)
são gerados na mesma pasta, um por condomínio processado no dia.

## Estrutura do projeto

automacao-cobranca-condominial/
├── relatorio_diario.py # Script principal: login, navegação, coleta e geração de relatórios
├── config_condominios.example.py # Modelo da lista de condomínios por dia da semana
├── .env.example # Modelo das variáveis de ambiente necessárias
└── .gitignore # Arquivos e pastas ignorados pelo Git


Os arquivos `.env` e `config_condominios.py` (com dados reais) **nunca são
versionados** e precisam ser criados localmente a partir dos exemplos
acima.

## Decisões técnicas relevantes

- A interface do sistema automatizado é uma SPA (Single Page Application),
  então a navegação é feita simulando cliques em vez de acessar URLs
  diretamente
- Parte do conteúdo carrega dentro de um `iframe`, exigindo troca de
  contexto no Selenium antes de localizar os elementos
- A lista de unidades carrega progressivamente conforme a rolagem da
  página, então o script rola em pequenos passos até a lista parar de
  crescer
- O layout da tabela de detalhe varia entre condomínios (algumas têm uma
  coluna a mais ou a menos); por isso, em vez de posições fixas, o script
  localiza as colunas dinamicamente (ex: identificando qual célula contém
  uma data válida)

## Possíveis melhorias futuras

- [ ] Envio automático das cobranças (WhatsApp ou e-mail)
- [ ] Geração de relatório consolidado único, além dos arquivos por
      condomínio
- [ ] Testes automatizados para as funções de parsing

## Aviso

Este projeto foi desenvolvido para uso pessoal, automatizando uma rotina
de trabalho real. Os relatórios gerados contêm dados sensíveis de
terceiros e nunca devem ser compartilhados publicamente. O nome e os
dados do sistema automatizado foram mantidos genéricos neste repositório
por questões de privacidade.