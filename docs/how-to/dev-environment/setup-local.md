# Setup local

> Suba infra + deps + schema do zero até `just check` verde. Fonte única dos comandos de ambiente.

## Contexto

Pré-reqs: Python 3.12+, `uv`, Docker com Compose v2. Sem Docker não há postgres/valkey para migrate nem testes de integração.

Infra local: postgres, valkey, livekit, minio (+ job `minio-init`). Topologia declarada fora do código Python; receitas canônicas moram no `justfile`, nunca invoque `docker compose` cru fora de `just up/down/logs/ps`.

Config: `.env.example` (37 linhas) é o contrato de variáveis; runtime lê `.env` (não commitado). Configuração normativa vive em `src/core/config.py`; schema via `alembic.ini` + `just migrate`.

## Conceito

Pipeline ordenado, cada passo depende do anterior:

1. `just up` — sobe contêineres e aguarda saúde (`--wait`).
2. `uv sync` — instala deps travadas de `pyproject.toml`.
3. `cp .env.example .env` — cria config local a partir do contrato.
4. `just migrate` — aplica schema (`alembic upgrade head`) contra postgres saudável.
5. `just check` — portão verde (fmt + lint + typecheck + tach + test).

Ordem importa: migrate sem postgres saudável falha; `just check` sem migrate quebra testes de integração. Operação diária: `just ps` (saúde), `just logs` (cauda), `just down` (parar). `clean-docker` apaga volumes — destrutivo, só para estado zero. `rollback` / `rollback-base` revertem migrações.

## Onde no código (só links)

- Topologia: `docker-compose.yml`
- Receitas: `justfile:up`, `justfile:down`, `justfile:logs`, `justfile:ps`, `justfile:migrate`, `justfile:check`, `justfile:install`, `justfile:clean-docker`
- Contrato env: `.env.example`
- Settings que consomem env: `src/core/config.py`
- Sessão DB: `src/core/database.py`
- Migrações: `alembic.ini`

Ver:

```bash
rg -n "^(up|down|logs|ps|migrate|check):" justfile
```

Expected: 6 matches (validado nesta branch).

```bash
rg -c "^[A-Z_]+=" .env.example
```

Expected: 25 (confere cobertura contra `reference/environment/variables.md` na fase 1, Task 5).

## Verificação

Run:

```bash
just up
```

Expected: 4 contêineres `healthy` (postgres, valkey, livekit, minio).

Run:

```bash
uv sync
```

Expected: ambiente sincronizado, exit 0.

Run:

```bash
cp .env.example .env
```

Expected: `.env` criado (sobrescreva valores locais se já existir).

Run:

```bash
just migrate
```

Expected: `alembic upgrade head` aplica até head sem erro.

Run:

```bash
just check
```

Expected: fmt + lint + typecheck + tach + pytest verdes, exit 0.

Run:

```bash
just ps
```

Expected: tabela com STATUS `healthy`/`running` por serviço.

Run:

```bash
just logs
```

Expected: stream de logs (`Ctrl-C` para sair; use `docker compose logs -f <serviço>` para filtrar).

Run:

```bash
just down
```

Expected: contêineres parados, volumes preservados.

## Ver também

- [Onboarding quickstart](../../tutorials/onboarding-quickstart.md)
- [Run tests](../backend/run-tests.md)
- [Backend first feature](../../tutorials/backend-first-feature.md)
