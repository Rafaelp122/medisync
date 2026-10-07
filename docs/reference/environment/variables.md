# Environment Variables

> Espelho comentado de `.env.example` (25 vars); valor canônico vive no arquivo, uso vive em `src/core/config.py:Settings`.

## Contexto

Config carrega de `.env` via `pydantic-settings`, `extra="ignore"`. Sem `.env`, caem defaults de dev.
Este arquivo não repete secrets; lista nome + onde é lido + default de dev quando seguro.
Mudou `.env.example`? Atualize aqui no mesmo PR.

## Conceito

Fonte única de valores: `.env.example`. Fonte única de leitura: `src/core/config.py:Settings` via `src/core/config.py:get_settings`.
Computados: `async_database_url` monta `postgresql+psycopg://` de partes ou normaliza `DATABASE_URL`; `async_valkey_url` traduz `valkey://` para `redis://`.

### 1. Aplicação core (3 vars)

| Var | Lida em | Notas |
|---|---|---|
| `ENVIRONMENT` | `src/core/config.py:Settings.ENVIRONMENT` | `development` em dev; `staging`, `production`, `test` |
| `DEBUG` | `src/core/config.py:Settings.DEBUG` | `true` em dev, nunca `true` em prod |
| `SECRET_KEY` | `src/core/config.py:Settings.SECRET_KEY` | Trocar em prod, mínimo 32 chars |

### 2. PostgreSQL 17 (6 vars)

| Var | Lida em | Notas |
|---|---|---|
| `POSTGRES_USER` | `src/core/config.py:Settings.POSTGRES_USER` | Usuário do banco + compose |
| `POSTGRES_PASSWORD` | `src/core/config.py:Settings.POSTGRES_PASSWORD` | Secret; não colar valor aqui |
| `POSTGRES_DB` | `src/core/config.py:Settings.POSTGRES_DB` | Nome do banco |
| `POSTGRES_HOST` | `src/core/config.py:Settings.POSTGRES_HOST` | `localhost` fora do compose |
| `POSTGRES_PORT` | `src/core/config.py:Settings.POSTGRES_PORT` | `5432` padrão |
| `DATABASE_URL` | `src/core/config.py:Settings.DATABASE_URL` | Opcional; quando ausente monta de partes via `async_database_url` |

### 3. Valkey 8.0 (3 vars)

| Var | Lida em | Notas |
|---|---|---|
| `VALKEY_HOST` | `src/core/config.py:Settings.VALKEY_HOST` | Cache, fila, locks |
| `VALKEY_PORT` | `src/core/config.py:Settings.VALKEY_PORT` | `6379` padrão |
| `VALKEY_URL` | `src/core/config.py:Settings.VALKEY_URL` | Normalizada por `async_valkey_url` para `redis://` |

### 4. LiveKit SFU (5 vars)

| Var | Lida em | Notas |
|---|---|---|
| `LIVEKIT_HOST` | `src/core/config.py:Settings.LIVEKIT_HOST` | Host do SFU WebRTC |
| `LIVEKIT_PORT` | `src/core/config.py:Settings.LIVEKIT_PORT` | `7880` padrão |
| `LIVEKIT_URL` | `src/core/config.py:Settings.LIVEKIT_URL` | URL base usada pelo backend |
| `LIVEKIT_API_KEY` | `src/core/config.py:Settings.LIVEKIT_API_KEY` | `devkey` em dev |
| `LIVEKIT_API_SECRET` | `src/core/config.py:Settings.LIVEKIT_API_SECRET` | Secret; não colar valor aqui |

### 5. MinIO S3-compatível (8 vars)

| Var | Lida em | Notas |
|---|---|---|
| `MINIO_ROOT_USER` | `src/core/config.py:Settings.MINIO_ROOT_USER` | Root do MinIO local |
| `MINIO_ROOT_PASSWORD` | `src/core/config.py:Settings.MINIO_ROOT_PASSWORD` | Secret; mínimo 8 chars no MinIO |
| `MINIO_HOST` | `src/core/config.py:Settings.MINIO_HOST` | `localhost` fora do compose |
| `MINIO_PORT` | `src/core/config.py:Settings.MINIO_PORT` | `9000` API S3 |
| `MINIO_CONSOLE_PORT` | `src/core/config.py:Settings.MINIO_CONSOLE_PORT` | `9001` console web |
| `MINIO_ENDPOINT` | `src/core/config.py:Settings.MINIO_ENDPOINT` | Endpoint S3 lido pelo storage |
| `MINIO_DEFAULT_BUCKET` | `src/core/config.py:Settings.MINIO_DEFAULT_BUCKET` | Bucket de documentos |
| `MINIO_USE_SSL` | `src/core/config.py:Settings.MINIO_USE_SSL` | `false` em dev local |

Cobertura: 3 + 6 + 3 + 5 + 8 = 25 vars. Confere com `rg -c "^[A-Z_]+=" .env.example` → `25`.
Extras só em `src/core/config.py` (pool `DB_*`, `VALKEY_*` tuning, `ARQ_*`, `S3_*`, `JWT_*`, `PSC_*`, `NOTIFICATION_*`) usam defaults sem precisar exportar em dev; documentar aqui só quando virarem obrigatórios.

Bootstrap:

```bash
cp .env.example .env
```

## Onde no código

- Impl: `src/core/config.py:Settings`
- Impl: `src/core/config.py:get_settings`
- Impl: `src/core/config.py:async_database_url`
- Impl: `src/core/config.py:async_valkey_url`
- Spec: `.env.example`
- Ver: `rg -c "^[A-Z_]+=" .env.example`
- Ver: `rg -n "^[A-Z_]+=" .env.example`

## Verificação

```bash
rg -c "^[A-Z_]+=" .env.example
rg -n "^(ENVIRONMENT|DATABASE_URL|VALKEY_URL|LIVEKIT_URL|MINIO_ENDPOINT)" .env.example src/core/config.py
cp .env.example .env && uv run python -c "from src.core.config import get_settings; s=get_settings(); print(s.ENVIRONMENT, s.async_database_url[:20])"
```

Esperado: `25`, 5 matches no `.env.example` batendo com campos em `config.py`, bootstrap sem erro.

## Ver também

- [Error envelope](../api/error-envelope.md)
- [Setup local](../../how-to/dev-environment/setup-local.md)
- [Onboarding quickstart](../../tutorials/onboarding-quickstart.md)
- `docs/explanation/architecture/overview.md`
- `docs/explanation/architecture/concurrency-and-queues.md`
