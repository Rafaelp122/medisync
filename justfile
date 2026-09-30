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

# Executa suíte de testes com cobertura
test:
    uv run pytest --cov=src --cov-report=term-missing

# Executa testes em paralelo com todos os cores da CPU
test-parallel:
    uv run pytest -n auto

# Executa testes ultrarrápidos em paralelo sem medição de cobertura
test-fast:
    uv run pytest -n auto --no-cov

# Portão de qualidade completo (executado antes de commits ou PRs)
check: fmt lint typecheck tach test
