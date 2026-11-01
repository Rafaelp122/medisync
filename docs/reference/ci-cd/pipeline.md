# CI Pipeline & Docker Specification

> Especificação técnica factual dos jobs de integração contínua no GitHub Actions e contratos do contêiner Docker.

## Contexto

Consulte este documento para obter a referência exata dos comandos, gatilhos, variáveis de ambiente e estágios do pipeline de CI/CD do MediSync Express localizado em `.github/workflows/ci.yml`.

Para instruções passo a passo de como rodar o contêiner, consulte `docs/how-to/dev-environment/run-docker.md`. Para a motivação das escolhas arquiteturais, consulte `docs/explanation/architecture/ci-cd-and-containers.md`.

## Conceito

### Matriz de Jobs do CI (`.github/workflows/ci.yml`)

O pipeline é acionado nos eventos `push` e `pull_request` direcionados à branch `main`. A concorrência é configurada com `cancel-in-progress: true` no escopo do PR para otimizar consumo de runners.

| Job | Escopo / Responsabilidade | Comandos Executados | Dependências Externas |
| :--- | :--- | :--- | :--- |
| `detect-changes` | Filtragem de caminhos alterados via `dorny/paths-filter` | Mapeamento de diff em `backend`, `frontend` e `docs` | Nenhuma |
| `code-quality` | Formatação, tipos, fronteiras, links e auditorias de clean code | `scripts/docs_check.py`<br>`scripts/audit_ai_clean_code.py`<br>`scripts/audit_frontend_guidelines.py`<br>`uv run ruff check .`<br>`uv run basedpyright`<br>`uv run tach check` | Python 3.14 + uv (em memória) |
| `database-migrations` | Aplicação de DDL e detecção de drift entre models e schema | `uv run alembic upgrade head`<br>`uv run alembic check` | Postgres 17 (Service Container) |
| `unit-tests` | Regras clínicas, modelos ricos e AST routers | `uv run pytest tests/unit tests/architecture -n auto --cov=src` | Python 3.14 + uv (em memória) |
| `frontend-quality` | Tipos, linting e paridade de contratos OpenAPI | `uv run python -c "..." > openapi.json`<br>`pnpm --dir frontend generate:api`<br>`pnpm --dir frontend run check` | Node.js 24 + pnpm 10 + Python 3.14 |
| `frontend-tests` | Testes de integração de tela e unitários | `pnpm --dir frontend test` | Vitest + MSW v2 (condicional a `frontend`) |
| `frontend-e2e` | Testes ponta a ponta com Playwright e upload de relatório em falha | `pnpm --dir frontend test:e2e`<br>`actions/upload-artifact@v4` (`playwright-report`) | Chromium + Node.js 24 (condicional a `frontend`) |
| `docker-build` | Empacotamento OCI multi-stage e Smoke Test HTTP | `docker buildx build`<br>`docker run --detach ... medisync:ci`<br>Polling curl em `/healthz` | Docker Buildx + Daemon |

### Workflows Complementares de Segurança (DevSecOps)

Além do pipeline principal de CI, o repositório conta com dois workflows dedicados à segurança no GitHub Actions:

| Workflow | Arquivo | Gatilhos | Objetivo e Ferramental |
| :--- | :--- | :--- | :--- |
| **Secret Scanning** | `.github/workflows/secret-scanning.yml` | `push` e `pull_request` (branch `main`) | Detecção preventiva de segredos, credenciais e chaves via `gitleaks-action@v2` e `.gitleaks.toml`. |
| **Deep SAST** | `.github/workflows/codeql.yml` | `push` (branch `main`), `schedule` (semanal) e `pull_request` (código em src/) | Análise estática profunda de vulnerabilidades e fluxo de dados (*taint tracking*) em Python 3.12 via GitHub CodeQL. |

### Governança de Dependências (`.github/dependabot.yml`)

O repositório adota política de atualização automatizada com escalonamento diário para evitar sobrecarga de PRs:

| Ecossistema | Diretório | Agendamento | Limite de PRs | Grupo |
| :--- | :--- | :--- | :--- | :--- |
| **uv** | `/` | Semanal (Segundas) | 3 | `python-dependencies` |
| **npm** | `/frontend` | Semanal (Terças) | 3 | `frontend-dependencies` |
| **docker** | `/` | Semanal (Quartas) | 3 | `docker-images` |
| **github-actions** | `/` | Semanal (Quintas) | 3 | `github-actions` |

### Composite Actions Reutilizáveis (`.github/actions/`)

A infraestrutura adota duas composite actions locais para padronizar versões de runtimes e políticas de cache:
1. **`.github/actions/setup-python-uv`**: Encapsula `astral-sh/setup-uv@v5` (cache com hash de `uv.lock`) e `actions/setup-python@v5` (Python 3.14).
2. **`.github/actions/setup-node-pnpm`**: Encapsula `pnpm/action-setup@v4` (pnpm 10) e `actions/setup-node@v4` (Node.js 24 com cache de `frontend/pnpm-lock.yaml`).

### Concorrência e Cancelamento Preventivo

O workflow define a política de cancelamento automático:
* Grupo: `${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}`.
* `cancel-in-progress: true`: Quando novos commits são enviados para um Pull Request aberto, execuções anteriores em andamento são canceladas imediatamente.

## Onde no código

- Impl: `.github/workflows/ci.yml:jobs`
- Impl: `Dockerfile:production`
- Spec: `pyproject.toml:project.dependencies`
- Prova viva: `.github/workflows/ci.yml:docker-build`
- Ver: `rg -n "runs-on:" .github/workflows/ci.yml`
- Ver: `rg -n "GRANIAN_WORKERS" Dockerfile`

## Verificação

```bash
uv run ruff format --check .
uv run ruff check .
uv run basedpyright
uv run tach check
just scan-secrets
just check-migrations
just smoke-docker
```

Esperado: todas as checagens estáticas, varredura de segredos, paridade de migrações e smoke test do contêiner retornam código 0; build Docker conclui e responde HTTP 200 em `/healthz`.

## Ver também

- [ADR-010: Estratégia de DevSecOps](../../adrs/ADR-010-Estrategia-DevSecOps-Defesa-em-Profundidade-de-Segredos-e-SAST.md)
- [Run Docker Container](../../how-to/dev-environment/run-docker.md)
- [Testing Strategy](../../explanation/architecture/testing-strategy.md)
- [CI/CD Strategy & Container Architecture](../../explanation/architecture/ci-cd-and-containers.md)
- [Environment Variables](../environment/variables.md)

