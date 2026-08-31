# Histórico

## 2026-08-31T14:00:25Z

- Criado o projeto independente de dados legislativos, com pipeline canônico,
  releases reprodutíveis, API REST, MCP somente leitura e publicação por
  GitHub Releases.
- A publicação de dados reais permanece condicionada ao cadastro da licença e
  do status de redistribuição de cada fonte.
- Validada uma prévia real com 26.816 proposições únicas, 3.256 duplicatas
  reconciliadas, 18 casas legislativas, 121 assets e 65,6 MB. Todas as 18
  fontes continuam marcadas como `pending`, e o guard de publicação bloqueou a
  promoção como esperado.
- Validada a reconstrução do índice em PostgreSQL 17 com pgvector, incluindo
  migrações, carga, busca, paginação de texto, fontes e resolução de releases.

## 2026-08-31T14:15:22Z

- Preparado o ambiente isolado de staging no Railway, com serviço de API,
  PostgreSQL e domínio público próprios, sem alterar o Assessoraí existente.
- O container agora normaliza URLs PostgreSQL do Railway para o driver
  Psycopg 3 e aplica migrações pela rede privada antes de iniciar a API.
- Migrada a configuração de deploy para Railway Config as Code e validado o
  novo entrypoint com lint, testes e build local do container.
- O primeiro smoke test de staging detectou que o CLI instalado resolvia um
  diretório de migrações vazio. O entrypoint passou a usar o caminho absoluto
  do container, e a ausência de SQLs agora interrompe o deploy explicitamente.
- Carregada no índice isolado de staging a prévia validada com 26.816
  proposições. REST e MCP recusam links de download para releases ainda não
  publicáveis, evitando anunciar assets inexistentes ou sem licença aprovada.
- Após os smoke tests, a carga temporária foi removida do PostgreSQL público de
  staging porque todas as fontes continuam com redistribuição pendente. Os
  assets validados permanecem locais e permitem reconstruir o índice.
