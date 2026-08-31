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
