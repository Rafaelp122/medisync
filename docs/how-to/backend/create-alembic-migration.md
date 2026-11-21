# Create Alembic Migration

> Como criar e validar migrações Alembic seguras no PostgreSQL 17 sob o modelo de plataforma única.

## Contexto

Após a consolidação em plataforma única ([ADR-013](../../adrs/ADR-013-Simplificacao-Plataforma-Unica-e-Remocao-RLS.md)), o esquema do MediSync Express não utiliza coluna `organizacao_id`, políticas Row-Level Security (RLS) nem papel restrito `medisync_app`.

Todas as novas tabelas e alterações incrementais operam com chaves primárias **UUIDv7** (`gen_uuidv7()` no banco e `src/core/uuid7.py:uuid7` em Python), `DateTime(timezone=True)` para timestamps UTC, `CheckConstraint` espelhando as invariantes do domínio rico e `ON DELETE RESTRICT` nas raízes clínicas.

## Conceito

Toda nova migração do Alembic segue o roteiro operacional de cinco etapas:

### 1. Declarar ou alterar o modelo SQLAlchemy 2.0

As entidades persistidas residem em `src/modules/<modulo>/domain/models/` (herdando `src.core.database.Base`) e precisam estar importadas em `src/modules/<modulo>/domain/models/__init__.py` e em `migrations/env.py` para que `alembic --autogenerate` e `alembic check` enxerguem `Base.metadata`.

### 2. Gerar ou escrever a revisão Alembic

```bash
uv run alembic revision --autogenerate -m "add_example_table"
```

Revise cuidadosamente o arquivo gerado em `migrations/versions/`:
- Use `postgresql.UUID(as_uuid=True)` com `server_default=sa.text("gen_uuidv7()")` nas PKs.
- Preserve nomes explícitos de índices e constraints (`uq_*`, `idx_*`, `chk_*`, `excl_*`).
- Caso utilize `ExcludeConstraint` temporal (ex.: agenda eMulti), dependa da extensão `btree_gist` já habilitada em `scripts/postgres/01-init-extensions.sql`.

### 3. Implementar `upgrade()` e `downgrade()` simétricos

Garanta que `downgrade()` remova índices, constraints, triggers e tabelas na ordem inversa exata da criação para que testes de ciclo completo (`upgrade` $\to$ `downgrade` $\to$ `upgrade`) passem sem artefatos residuais.

### 4. Auditar paridade entre modelos e banco

```bash
uv run alembic upgrade head
uv run alembic check
```

Saída esperada para `alembic check`: `No new upgrade operations detected.`

## Onde no código

- Migração consolidada base: `migrations/versions/0001_initial_schema.py`
- Bootstrap de extensões Postgres: `scripts/postgres/01-init-extensions.sql`
- Configuração de target metadata: `migrations/env.py`
- Suíte de validação estrutural: `tests/integration/test_migrations.py`
- Catálogo físico de tabelas: `docs/reference/database/schema.md`

## Verificação

```bash
just migrate
uv run pytest --noconftest tests/integration/test_migrations.py -v
uv run alembic check
```

## Ver também

- [Create module endpoint](create-module-endpoint.md)
- [Wire module dependencies](wire-module-dependencies.md)
- [Run tests](run-tests.md)
- [ADR-013 Simplificação para Plataforma Única](../../adrs/ADR-013-Simplificacao-Plataforma-Unica-e-Remocao-RLS.md)
- [Database Schema Reference](../../reference/database/schema.md)
