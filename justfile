# MediSync Express — Automação de Tarefas de Desenvolvimento

# Exibe todos os comandos disponíveis
default:
    @just --list

# Sincroniza ambiente e dependências com uv
install:
    uv sync

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

# Portão de qualidade completo com Fail-Fast estrito (integração por último)
check: fmt lint typecheck tach test-unit test-integration

# Inicia o background worker assíncrono ARQ sobre Valkey
worker:
    uv run arq src.worker.WorkerSettings

# Inicia toda a topologia de contêineres em background e aguarda ficarem saudáveis
up:
    docker compose up -d --wait postgres valkey livekit minio
    docker compose up -d minio-init

# Para os contêineres locais
down:
    docker compose down

# Acompanha logs dos contêineres em tempo real
logs:
    docker compose logs -f

# Exibe status e saúde dos contêineres
ps:
    docker compose ps

# Remove contêineres e apaga volumes persistentes
clean-docker:
    docker compose down -v

# Aplica migrações pendentes no banco de dados
migrate:
    uv run alembic upgrade head

# Reverte a última migração aplicada
rollback:
    uv run alembic downgrade -1

# Reverte todas as migrações até o estado inicial limpo
rollback-base:
    uv run alembic downgrade base

# Exibe o histórico cronológico de migrações
migration-history:
    uv run alembic history

# Valida links src/docs referenciados nos .md e proíbe cola >5 linhas
docs-check:
    uv run python scripts/docs_check.py

# Compila a imagem Docker de produção
docker-build:
    docker build -t medisync:latest --target production .

# Compila a imagem Docker de desenvolvimento
docker-build-dev:
    docker build -t medisync:dev --target development .

