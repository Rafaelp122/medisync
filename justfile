# ==============================================================================
# MediSync Express — Automação de Tarefas de Desenvolvimento
# ==============================================================================

# Exibe todos os comandos disponíveis organizados por categoria
default:
    @just --list


# ==============================================================================
# GERAL & FULL-STACK (GERAL)
# ==============================================================================

# Inicia simultaneamente o backend, worker assíncrono e frontend em modo desenvolvimento local
[group('geral')]
dev:
    #!/usr/bin/env bash
    set -e
    trap 'kill $(jobs -p) 2>/dev/null || true' EXIT INT TERM
    echo "🚀 Iniciando MediSync Express (Backend + Worker + Frontend)..."
    just backend-dev &
    just worker &
    just frontend-dev &
    wait -n

# Inicializa o ambiente de desenvolvimento completo (infra Docker, deps, migrações e validação rápida)
[group('geral')]
setup-dev:
    @test -f .env || cp .env.example .env
    just up-infra
    just install
    just migrate
    just seed-dev

# Portão de qualidade completo com Fail-Fast estrito (segurança, docs, clean code, tipos, arquitetura e testes)
[group('geral')]
check: scan-secrets docs-check audit-ai-code audit-frontend fmt lint frontend-check typecheck tach test-unit test-integration frontend-test

# Validação rápida de alta velocidade (100% em memória, zero Docker, ~16 segundos)
[group('geral')]
check-fast: scan-secrets docs-check audit-ai-code audit-frontend fmt lint frontend-check typecheck tach test-fast

# Executa auditoria estática de segredos com gitleaks (binário local ou Docker)
[group('geral')]
scan-secrets:
    @if command -v gitleaks >/dev/null 2>&1; then \
        gitleaks detect --config=.gitleaks.toml --verbose --redact; \
    else \
        docker run --rm -v {{invocation_directory()}}:/path zricethezav/gitleaks:latest detect --source="/path" --config="/path/.gitleaks.toml" --verbose --redact; \
    fi

# Valida links src/docs referenciados nos .md e proíbe cola >5 linhas
[group('geral')]
docs-check:
    uv run python scripts/docs_check.py

# Audita o código sob os princípios de Clean Code para Agentes de IA
[group('geral')]
audit-ai-code:
    uv run python scripts/audit_ai_clean_code.py

# Audita o código do frontend sob as diretrizes de Web Guidelines da Vercel e ADR-011
[group('geral')]
audit-frontend:
    uv run python scripts/audit_frontend_guidelines.py

# Simula o próximo bump de versão e valida consistência (dry-run)
[group('geral')]
bump-check:
    uv run cz bump --dry-run --check-consistency

# Executa o bump semântico de versão e atualiza changelog localmente
[group('geral')]
bump:
    uv run cz bump --changelog --check-consistency

# Instala hooks locais de pre-commit no repositório git via uvx
[group('geral')]
pre-commit-install:
    uvx pre-commit install


# ==============================================================================
# INFRAESTRUTURA, BANCO DE DADOS & CONTÊINERES (INFRA)
# ==============================================================================

# Inicia serviços essenciais de infraestrutura (Postgres, Valkey, LiveKit, MinIO)
[group('infra')]
up-infra:
    docker compose up -d --wait postgres valkey livekit minio
    docker compose up -d minio-init

# Inicia toda a topologia de contêineres em background (infraestrutura + backend em contêiner)
[group('infra')]
up: up-infra
    docker compose up -d --wait backend

# Para os contêineres locais
[group('infra')]
down:
    docker compose down

# Exibe status e saúde dos contêineres
[group('infra')]
ps:
    docker compose ps

# Acompanha logs dos contêineres em tempo real (ex.: 'just logs' ou 'just logs backend')
[group('infra')]
logs service="":
    docker compose logs -f {{service}}

# Remove contêineres e apaga volumes persistentes
[group('infra')]
clean-docker:
    docker compose down -v

# Aplica migrações pendentes no banco de dados relacional (host local)
[group('infra')]
migrate:
    uv run alembic upgrade head

# Popula o banco de desenvolvimento local com tenant e pacientes de demonstração (host local)
[group('infra')]
seed-dev:
    uv run python -m scripts.seed_dev

# Reverte a última migração aplicada
[group('infra')]
rollback:
    uv run alembic downgrade -1

# Reverte todas as migrações até o estado inicial limpo
[group('infra')]
rollback-base:
    uv run alembic downgrade base

# Exibe o histórico cronológico de migrações
[group('infra')]
migration-history:
    uv run alembic history

# Valida ausência de drift entre os modelos SQLAlchemy e as migrações do Alembic
[group('infra')]
check-migrations:
    uv run alembic check

# Compila a imagem Docker de produção
[group('infra')]
docker-build:
    docker build -t medisync:latest --target production .

# Compila a imagem Docker de desenvolvimento
[group('infra')]
docker-build-dev:
    docker build -t medisync:dev --target development .

# Executa smoke test na imagem de produção compilada verificando a rota /healthz
[group('infra')]
smoke-docker: docker-build
    #!/usr/bin/env bash
    set -e
    CONTAINER_NAME="medisync-smoke-$$"
    trap 'docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true' EXIT
    docker run --detach --name "$CONTAINER_NAME" -p 8089:8080 -e PORT=8080 -e VALKEY_RETRY_ATTEMPTS=0 -e VALKEY_CONNECT_TIMEOUT=1.0 medisync:latest
    for attempt in {1..30}; do
        if curl --fail --silent http://127.0.0.1:8089/healthz >/dev/null; then
            echo "✅ Container de produção saudável em /healthz!"
            exit 0
        fi
        sleep 1
    done
    echo "❌ Timeout aguardando o healthcheck do container de produção."
    docker logs "$CONTAINER_NAME"
    exit 1

# Executa migrações do Alembic dentro do contêiner backend
[group('infra')]
docker-migrate:
    docker compose exec backend alembic upgrade head

# Popula dados de desenvolvimento dentro do contêiner backend
[group('infra')]
docker-seed:
    docker compose exec backend python -m scripts.seed_dev

# Abre um terminal interativo bash dentro do contêiner backend
[group('infra')]
docker-shell:
    docker compose exec -it backend /bin/bash

# Executa a suíte de testes unitários e de arquitetura dentro do contêiner backend
[group('infra')]
docker-test:
    docker compose exec backend pytest tests/unit tests/architecture


# ==============================================================================
# BACKEND (PYTHON & FASTAPI)
# ==============================================================================

# Sincroniza ambiente e dependências com uv
[group('backend')]
install:
    uv sync

# Inicia o servidor backend localmente com hot-reload (Granian)
[group('backend')]
backend-dev:
    uv run granian src.main:app --interface asgi --host 0.0.0.0 --port 8000 --reload

# Inicia o background worker assíncrono ARQ sobre Valkey
[group('backend')]
worker:
    uv run arq src.worker.WorkerSettings

# Formata o código usando ruff
[group('backend')]
fmt:
    uv run ruff format .

# Executa lint com autofix seguro usando ruff
[group('backend')]
lint:
    uv run ruff check . --fix

# Executa checagem de tipos estrita usando basedpyright
[group('backend')]
typecheck:
    uv run basedpyright

# Executa auditoria de fronteiras modulares com tach
[group('backend')]
tach:
    uv run tach check

# Executa testes rápidos de feedback em paralelo (100% em memória, zero Docker/IO)
[group('backend')]
test-fast:
    uv run pytest tests/unit tests/architecture -n auto --no-cov

# Executa testes unitários e de arquitetura com medição de cobertura
[group('backend')]
test-unit:
    uv run pytest tests/unit tests/architecture --cov=src

# Executa testes de integração sobre serviços reais (Postgres, Valkey, MinIO, LiveKit)
[group('backend')]
test-integration:
    uv run pytest tests/integration

# Executa suíte completa com cobertura consolidada
[group('backend')]
test:
    uv run pytest tests/unit tests/architecture tests/integration --cov=src --cov-report=term-missing

# Executa todos os testes em paralelo com todos os cores da CPU
[group('backend')]
test-parallel:
    uv run pytest -n auto

# Exporta o schema OpenAPI 3.1 do backend para arquivo estático na raiz
[group('backend')]
dump-openapi:
    uv run python -c "import json; from src.main import app; print(json.dumps(app.openapi(), indent=2))" > openapi.json

# Cria esqueleto físico hexagonal para novo módulo e registra no tach.toml
[group('backend')]
scaffold-module name:
    uv run python scripts/scaffold_module.py {{name}}


# ==============================================================================
# FRONTEND (TYPESCRIPT & REACT 19 SPA/PWA)
# ==============================================================================

# Instala dependências do frontend com pnpm
[group('frontend')]
frontend-install:
    @if [ -f frontend/package.json ]; then \
        pnpm --dir frontend install; \
    else \
        echo "Diretório frontend/ ainda não inicializado."; \
    fi

# Inicia servidor de desenvolvimento Vite
[group('frontend')]
frontend-dev:
    @if [ -f frontend/package.json ]; then \
        pnpm --dir frontend dev; \
    else \
        echo "Diretório frontend/ ainda não inicializado." && exit 1; \
    fi

# Gera contratos tipados TypeScript via Hey API a partir do openapi.json
[group('frontend')]
frontend-generate: dump-openapi
    @if [ -f frontend/package.json ]; then \
        pnpm --dir frontend generate:api; \
    else \
        echo "Diretório frontend/ ainda não inicializado."; \
    fi

# Executa checagem de tipos estrita (tsc), lint (biome) e testes do frontend
[group('frontend')]
frontend-check:
    @if [ -f frontend/package.json ]; then \
        pnpm --dir frontend run check; \
    else \
        echo "Diretório frontend/ ainda não inicializado."; \
    fi

# Executa a suíte de testes de tela e unitários do frontend com Vitest
[group('frontend')]
frontend-test:
    @if [ -f frontend/package.json ]; then \
        pnpm --dir frontend test; \
    else \
        echo "Diretório frontend/ ainda não inicializado."; \
    fi

# Executa testes ponta a ponta com Playwright
[group('frontend')]
frontend-test-e2e:
    @if [ -f frontend/package.json ]; then \
        pnpm --dir frontend test:e2e; \
    else \
        echo "Diretório frontend/ ainda não inicializado."; \
    fi
