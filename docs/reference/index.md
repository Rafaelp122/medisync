# Reference

> Biblioteca canônica de especificações técnicas, contratos, dicionários de dados e padrões de engenharia do MediSync Express.

## 1. Persistência & Isolamento de Dados
- [Database Schema & Row-Level Security (RLS)](database/schema-and-rls.md) — Catálogo físico das 12 tabelas, chaves primárias UUIDv7, índices B-Tree e políticas RLS de tenant.
- [Catálogo de Eventos de Auditoria Clínica](audit/event-catalog.md) — Taxonomia dos 11 eventos auditáveis append-only sob ADR-007, CFM nº 2.314/2022 e LGPD.

## 2. Cache, Concorrência & Atomicidade
- [Valkey Keys Dictionary](valkey/keys-dictionary.md) — Namespaces de chaves, tipos de dados (ZSET/HASH/STRING), TTLs e políticas de evicção.
- [Valkey Lua Scripts](valkey/lua-scripts.md) — Catálogo do script `alocar_chamada.lua`, parâmetros KEYS/ARGV, retornos e garantias lineares (<5ms).

## 3. APIs, Tempo Real & Background Jobs
- [API Error Envelope (RFC 7807)](api/error-envelope.md) — Catálogo exaustivo de exceções de domínio, status HTTP e envelope de erro RFC 7807.
- [WebSocket Channels & Realtime Protocol](api/websocket-channels.md) — Endpoints WS de fila/médico, autenticação pré-accept, eventos Pub/Sub e envelopes JSON.
- [ARQ Background Tasks](worker/arq-tasks.md) — Catálogo de jobs assíncronos (`validar_elegibilidade`, `ring_timeout`, `sweeper`), cron schedules e retries.

## 4. Arquitetura, Governança & Qualidade
- [Tach Boundaries Matrix](architecture-standards/tach-boundaries-matrix.md) — Matriz completa de dependências permitidas entre os 7 módulos, core e worker.
- [Documentation Standards](architecture-standards/documentation-standards.md) — Padrão atômico-denso (80–250L), 5 seções obrigatórias e regra link-sem-cola.
- [Test Doubles & Fakes Catalog](testing/test-doubles-catalog.md) — Catálogo dos Fakes tipados em memória (`tests/doubles.py`) e asserções de teste.
- [Testing Fixtures & Factories](testing/fixtures-and-factories.md) — Fixtures pytest assíncronas, factories e geradores de dados de teste.
- [Frontend Testing Patterns](testing/frontend-testing-patterns.md) — Padrões e regras de testes com Vitest, React Testing Library, MSW v2, Playwright e Axe-Core (A11y).

## 5. Ambiente & Infraestrutura de CI/CD
- [Environment Variables](environment/variables.md) — As 25 variáveis de ambiente, validações Pydantic e perfis de execução.
- [CI Pipeline & Docker Specification](ci-cd/pipeline.md) — Pipeline do GitHub Actions, multi-stage Dockerfile e servidor Granian ASGI.

## Verificação

```bash
just docs-check
```

