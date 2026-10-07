# Onboarding quickstart

> Do zero até API respondendo + `just check` verde em ~15min.

## Contexto

Precisa de Docker + `uv`. Infra local: postgres, valkey, livekit, minio.
Receitas canônicas moram no `justfile`. Deps moram no `pyproject.toml`.

## Conceito

Setup = `just up` (infra) → `uv sync` (deps) → `just migrate` (schema) → `just check` (portão verde).
Ordem importa: sem infra saudável, migrate falha; sem migrate, testes de integração falham.

## Onde no código (só links)

- Infra: `docker-compose.yml`
- Deps: `pyproject.toml`
- Receitas: `justfile:up`, `justfile:install`, `justfile:migrate`, `justfile:check`

Ver:

```bash
rg -n "^(up|install|migrate|check):" justfile
```

## Verificação

Run:

```bash
just up && uv sync && just migrate && just check
```

Expected: `tach check` pass + `pytest` pass.

## Ver também

- [Setup local detalhado](../how-to/dev-environment/setup-local.md)
- [Run tests](../how-to/backend/run-tests.md)
