# How-to

> Guias operacionais orientados a problema.

## Guias

- [Setup local](dev-environment/setup-local.md) — deps, `.env`, serviços.
- [Run Docker Container](dev-environment/run-docker.md) — compilação e execução de contêineres OCI.
- [Release e Versionamento Semântico](dev-environment/release-and-versioning.md) — Conventional Commits, Commitizen e pipeline de release.
- [Create Module Endpoint](backend/create-module-endpoint.md) — receitas API/workers/filas.
- [Wire Module Dependencies](backend/wire-module-dependencies.md) — como plugar adaptadores, compor dependências e auditar conformidade.
- [Create Alembic Migration with RLS](backend/create-alembic-migration-with-rls.md) — migração segura de tabelas multi-tenant com isolamento Postgres RLS e papel NOBYPASSRLS.
- [Debug Background Task ARQ](backend/debug-background-task-arq.md) — execução pontual, inspeção de filas Valkey, modo burst e diagnóstico de tarefas assíncronas.
- [Emit Realtime Domain Event](backend/emit-realtime-domain-event.md) — publicação de eventos clínicos via Valkey Pub/Sub e streaming WebSockets de baixa latência.
- [Write Tests](backend/write-tests.md) — como escrever testes unitários e de integração no Padrão Ouro.
- [Run Tests](backend/run-tests.md) — comandos, pirâmide e diagnóstico.

## Verificação

```bash
just check
```
