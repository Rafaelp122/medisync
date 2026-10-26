# ==============================================================================
# MediSync Express — Automação de Tarefas de Desenvolvimento
# ==============================================================================

# Exibe todos os comandos disponíveis organizados por categoria
default:
    @just --list

# Inicia simultaneamente o backend e o frontend em modo desenvolvimento local
dev:
    #!/usr/bin/env bash
    set -e
    trap 'kill $(jobs -p) 2>/dev/null || true' EXIT INT TERM
    echo "🚀 Iniciando MediSync Express (Backend + Frontend)..."
    just backend-dev &
    just frontend-dev &
    wait -n

# Inicializa o ambiente de desenvolvimento completo (infra Docker, deps, migrações e validação rápida)
setup-dev:
    @test -f .env || cp .env.example .env
    just up-infra
    just install
    just migrate
    just seed-dev

# Portão de qualidade completo com Fail-Fast estrito (segurança, docs, clean code, tipos, arquitetura e testes)
check: scan-secrets docs-check audit-ai-code fmt lint typecheck tach test-unit test-integration

# Validação rápida de alta velocidade (100% em memória, zero Docker, ~15 segundos)
check-fast: scan-secrets docs-check audit-ai-code fmt lint typecheck tach test-fast

# Executa auditoria estática de segredos com gitleaks (binário local ou Docker)
scan-secrets:
    @if command -v gitleaks >/dev/null 2>&1; then \
        gitleaks detect --config=.gitleaks.toml --verbose --redact; \
    else \
        docker run --rm -v {{invocation_directory()}}:/path zricethezav/gitleaks:latest detect --source="/path" --config="/path/.gitleaks.toml" --verbose --redact; \
    fi

# Valida links src/docs referenciados nos .md e proíbe cola >5 linhas
docs-check:
    uv run python scripts/docs_check.py

# Audita o código sob os princípios de Clean Code para Agentes de IA
audit-ai-code:
    uv run python scripts/audit_ai_clean_code.py

# Simula o próximo bump de versão e valida consistência (dry-run)
bump-check:
    uv run cz bump --dry-run --check-consistency

# Executa o bump semântico de versão e atualiza changelog localmente
bump:
    uv run cz bump --changelog --check-consistency

# Instala hooks locais de pre-commit no repositório git via uvx
pre-commit-install:
    uvx pre-commit install


# ==============================================================================
# INFRAESTRUTURA, BANCO DE DADOS & CONTÊINERES (INFRA)
# ==============================================================================

# Inicia serviços essenciais de infraestrutura (Postgres, Valkey, LiveKit, MinIO)
up-infra:
    docker compose up -d --wait postgres valkey livekit minio
    docker compose up -d minio-init

# Inicia toda a topologia de contêineres em background (infraestrutura + backend em contêiner)
up: up-infra
    docker compose up -d --wait backend

# Para os contêineres locais
down:
    docker compose down

# Exibe status e saúde dos contêineres
ps:
    docker compose ps

# Acompanha logs dos contêineres em tempo real
logs:
    docker compose logs -f

# Remove contêineres e apaga volumes persistentes
clean-docker:
    docker compose down -v

# Aplica migrações pendentes no banco de dados relacional
migrate:
    uv run alembic upgrade head

# Popula o banco de desenvolvimento local com tenant e pacientes de demonstração
seed-dev:
    uv run python -m scripts.seed_dev

# Reverte a última migração aplicada
rollback:
    uv run alembic downgrade -1

# Reverte todas as migrações até o estado inicial limpo
rollback-base:
    uv run alembic downgrade base

# Exibe o histórico cronológico de migrações
migration-history:
    uv run alembic history

# Compila a imagem Docker de produção
docker-build:
    docker build -t medisync:latest --target production .

# Compila a imagem Docker de desenvolvimento
docker-build-dev:
    docker build -t medisync:dev --target development .


# ==============================================================================
# BACKEND (PYTHON & FASTAPI)
# ==============================================================================

# Sincroniza ambiente e dependências com uv
install:
    uv sync

# Inicia o servidor backend localmente com hot-reload (Granian)
backend-dev:
    uv run granian src.main:app --interface asgi --host 0.0.0.0 --port 8000 --reload

# Inicia o background worker assíncrono ARQ sobre Valkey
worker:
    uv run arq src.worker.WorkerSettings

# Formata o código usando ruff
fmt:
    uv run ruff format .

# Executa lint com autofix seguro usando ruff
lint:
    uv run ruff check . --fix

# Executa checagem de tipos estrita usando basedpyright
typecheck:
    uv run basedpyright

# Executa auditoria de fronteiras modulares com tach
tach:
    uv run tach check

# Executa testes rápidos de feedback em paralelo (100% em memória, zero Docker/IO)
test-fast:
    uv run pytest tests/unit tests/architecture -n auto --no-cov

# Executa testes unitários e de arquitetura com medição de cobertura
test-unit:
    uv run pytest tests/unit tests/architecture --cov=src

# Executa testes de integração sobre serviços reais (Postgres, Valkey, MinIO, LiveKit)
test-integration:
    uv run pytest tests/integration

# Executa suíte completa com cobertura consolidada
test:
    uv run pytest tests/unit tests/architecture tests/integration --cov=src --cov-report=term-missing

# Executa todos os testes em paralelo com todos os cores da CPU
test-parallel:
    uv run pytest -n auto

# Exporta o schema OpenAPI 3.1 do backend para arquivo estático na raiz
dump-openapi:
    uv run python -c "import json; from src.main import app; print(json.dumps(app.openapi(), indent=2))" > openapi.json

# Cria esqueleto físico hexagonal para novo módulo e registra no tach.toml
scaffold-module name:
    uv run python scripts/scaffold_module.py {{name}}


# ==============================================================================
# FRONTEND (TYPESCRIPT & REACT 19 SPA/PWA)
# ==============================================================================

# Instala dependências do frontend com pnpm
frontend-install:
    @if [ -f frontend/package.json ]; then \
        pnpm --dir frontend install; \
    else \
        echo "Diretório frontend/ ainda não inicializado."; \
    fi

# Inicia servidor de desenvolvimento Vite
frontend-dev:
    @if [ -f frontend/package.json ]; then \
        pnpm --dir frontend dev; \
    else \
        echo "Diretório frontend/ ainda não inicializado." && exit 1; \
    fi

# Gera contratos tipados TypeScript via Hey API a partir do openapi.json
frontend-generate: dump-openapi
    @if [ -f frontend/package.json ]; then \
        pnpm --dir frontend generate:api; \
    else \
        echo "Diretório frontend/ ainda não inicializado."; \
    fi

# Executa checagem de tipos estrita (tsc), lint (biome) e testes do frontend
frontend-check:
    @if [ -f frontend/package.json ]; then \
        pnpm --dir frontend run check; \
    else \
        echo "Diretório frontend/ ainda não inicializado."; \
    fi

# Executa a suíte de testes de tela e unitários do frontend com Vitest
frontend-test:
    @if [ -f frontend/package.json ]; then \
        pnpm --dir frontend test; \
    else \
        echo "Diretório frontend/ ainda não inicializado."; \
    fi

# Executa testes ponta a ponta com Playwright
frontend-test-e2e:
    @if [ -f frontend/package.json ]; then \
        pnpm --dir frontend test:e2e; \
    else \
        echo "Diretório frontend/ ainda não inicializado."; \
    fi


