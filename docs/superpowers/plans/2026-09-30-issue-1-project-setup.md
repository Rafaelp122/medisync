# Issue #1: Project Setup and Quality Tooling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Initialize the modern Python development environment using `uv`, configuring strict linting with `ruff`, strict type-checking with `basedpyright`, modular boundary enforcement with `tach`, automated testing with `pytest` (async and parallel), command shortcuts with `justfile`, and AI guidelines with `AGENTS.md`.

**Architecture:** Modular monolith following Hexagonal Pragmático principles (ADR-001). Isolated domain modules (`identity`, `triage`, `queue`, `consultation`, `billing`) guarded by `tach.toml`, rich domain models, `typing.Protocol` contracts, and strict code quality gates.

**Tech Stack:** Python 3.12+, `uv`, `ruff`, `basedpyright`, `tach`, `pytest`, `pytest-asyncio`, `pytest-xdist`, `pytest-cov`, `just`.

---

## File Structure Map

```text
medisync/
├── pyproject.toml                 # Package definition, dependencies and tool configs (uv, ruff, basedpyright, pytest)
├── tach.toml                      # Module boundaries declaration for tach
├── justfile                       # Task automation recipes
├── AGENTS.md                      # AI agent instructions, architecture rules and skill mapping
├── src/
│   ├── __init__.py
│   ├── core/
│   │   └── __init__.py
│   └── modules/
│       ├── __init__.py
│       ├── identity/
│       │   └── __init__.py
│       ├── triage/
│       │   └── __init__.py
│       ├── queue/
│       │   └── __init__.py
│       ├── consultation/
│       │   └── __init__.py
│       └── billing/
│           └── __init__.py
└── tests/
    ├── __init__.py
    ├── conftest.py                # Common pytest fixtures
    ├── unit/
    │   ├── __init__.py
    │   └── test_smoke.py          # Initial smoke test for async/sync runner
    └── integration/
        └── __init__.py
```

---

## Tasks

### Task 1: Initialize Project Skeleton and Modular Directory Structure

**Files:**
- Create: `src/__init__.py`
- Create: `src/core/__init__.py`
- Create: `src/modules/__init__.py`
- Create: `src/modules/identity/__init__.py`
- Create: `src/modules/triage/__init__.py`
- Create: `src/modules/queue/__init__.py`
- Create: `src/modules/consultation/__init__.py`
- Create: `src/modules/billing/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/integration/__init__.py`

- [ ] **Step 1: Create all package directory markers**

Create empty `__init__.py` files across all declared modular packages so Python and static analyzers recognize the modules.

- [ ] **Step 2: Verify folder structure exists**

Run: `find src tests -name "__init__.py" | sort`
Expected output:
```text
src/__init__.py
src/core/__init__.py
src/modules/__init__.py
src/modules/billing/__init__.py
src/modules/consultation/__init__.py
src/modules/identity/__init__.py
src/modules/queue/__init__.py
src/modules/triage/__init__.py
tests/__init__.py
tests/integration/__init__.py
tests/unit/__init__.py
```

- [ ] **Step 3: Commit**

```bash
git add src tests
git commit -m "chore: scaffold modular package directory structure"
```

---

### Task 2: Configure `pyproject.toml` with `uv`, `ruff`, `basedpyright`, and `pytest`

**Files:**
- Create: `pyproject.toml`

- [ ] **Step 1: Write `pyproject.toml` with dependencies and strict configurations**

```toml
[project]
name = "medisync"
version = "0.1.0"
description = "MediSync Express — Plataforma de Pronto-Atendimento Virtual (PA Digital 24/7)"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "pydantic>=2.8.0",
    "pydantic-settings>=2.4.0",
]

[dependency-groups]
dev = [
    "basedpyright>=1.18.0",
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=5.0.0",
    "pytest-xdist>=3.6.0",
    "ruff>=0.6.0",
    "tach>=0.18.0",
]

[tool.ruff]
target-version = "py312"
line-length = 88
src = ["src", "tests"]

[tool.ruff.lint]
select = [
    "E",     # pycodestyle errors
    "W",     # pycodestyle warnings
    "F",     # Pyflakes
    "I",     # isort
    "UP",    # pyupgrade
    "B",     # flake8-bugbear
    "SIM",   # flake8-simplify
    "TCH",   # flake8-type-checking
    "ASYNC", # flake8-async
    "S",     # flake8-bandit
    "RUF",   # Ruff-specific rules
]
ignore = [
    "RUF012", # Mutable class attributes should be annotated with `typing.ClassVar`
]

[tool.ruff.lint.per-file-ignores]
"tests/**/*" = [
    "S101", # Allow assert in tests
    "S105", # Allow hardcoded passwords in test fixtures
    "S106", # Allow hardcoded credentials in test fixtures
]

[tool.basedpyright]
include = ["src", "tests"]
pythonVersion = "3.12"
typeCheckingMode = "strict"
reportMissingTypeStubs = false

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
addopts = "--strict-markers -ra"
```

- [ ] **Step 2: Sync dependencies using `uv sync`**

Run: `uv sync`
Expected output: Installs core packages and dev dependency groups into `.venv` with exit code 0.

- [ ] **Step 3: Verify ruff passes on initial skeleton**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: 0 errors detected.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(setup): configure pyproject.toml with uv, ruff, basedpyright and pytest"
```

---

### Task 3: Configure Modular Boundaries with `tach.toml`

**Files:**
- Create: `tach.toml`

- [ ] **Step 1: Write `tach.toml` declaring closed boundaries for core and domain modules**

```toml
interfaces = []
exact = false
forbid_circular_dependencies = true
source_roots = ["src"]

[[modules]]
path = "core"
depends_on = []
layer = "shared"

[[modules]]
path = "modules.identity"
depends_on = ["core"]
layer = "domain"

[[modules]]
path = "modules.triage"
depends_on = ["core"]
layer = "domain"

[[modules]]
path = "modules.queue"
depends_on = ["core"]
layer = "domain"

[[modules]]
path = "modules.consultation"
depends_on = ["core"]
layer = "domain"

[[modules]]
path = "modules.billing"
depends_on = ["core"]
layer = "domain"
```

- [ ] **Step 2: Verify `tach check` passes**

Run: `uv run tach check`
Expected output: All modules audited successfully with 0 boundary violations.

- [ ] **Step 3: Commit**

```bash
git add tach.toml
git commit -m "chore(tach): configure module boundary rules in tach.toml"
```

---

### Task 4: Configure Smoke Tests with Async and Parallel Execution

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/unit/test_smoke.py`

- [ ] **Step 1: Create `tests/conftest.py` with basic async test fixture**

```python
"""Global pytest fixtures and configurations."""

import asyncio
from collections.abc import AsyncGenerator
import pytest


@pytest.fixture
async def sample_async_resource() -> AsyncGenerator[str, None]:
    """Sample asynchronous resource fixture to validate pytest-asyncio loop scope."""
    await asyncio.sleep(0.001)
    yield "ready"
```

- [ ] **Step 2: Create `tests/unit/test_smoke.py` verifying sync, async, and type-safety**

```python
"""Smoke test suite to validate test execution environment."""

from src import __file__ as src_init_file


def test_sync_environment() -> None:
    """Validate synchronous test runner and package discovery."""
    assert src_init_file is not None


async def test_async_environment(sample_async_resource: str) -> None:
    """Validate asynchronous test execution with pytest-asyncio."""
    assert sample_async_resource == "ready"
```

- [ ] **Step 3: Run pytest sequentially and verify passing**

Run: `uv run pytest -v`
Expected output: 2 passed in test suite with exit code 0.

- [ ] **Step 4: Run pytest in parallel with `pytest-xdist`**

Run: `uv run pytest -n auto -v`
Expected output: 2 workers spawned, 2 passed with exit code 0.

- [ ] **Step 5: Run basedpyright to ensure tests and fixtures pass strict typing**

Run: `uv run basedpyright`
Expected output: 0 errors, 0 warnings.

- [ ] **Step 6: Commit**

```bash
git add tests/conftest.py tests/unit/test_smoke.py
git commit -m "test(setup): add smoke tests validating async and parallel pytest execution"
```

---

### Task 5: Configure Development Automation with `justfile`

**Files:**
- Create: `justfile`

- [ ] **Step 1: Write `justfile` with standard commands**

```just
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
```

- [ ] **Step 2: Verify `just --list` works**

Run: `just --list`
Expected output: Displays list of recipes (`check`, `default`, `fmt`, `install`, `lint`, `tach`, `test`, `test-fast`, `test-parallel`, `typecheck`).

- [ ] **Step 3: Run `just check` to execute the full quality gate**

Run: `just check`
Expected output: Formats, lints, typechecks, audits tach boundaries, and runs pytest with 100% coverage on `src`. Exit code 0.

- [ ] **Step 4: Commit**

```bash
git add justfile
git commit -m "chore(dx): add justfile recipes for linting, typechecking, tach and testing"
```

---

### Task 6: Configure Agent Guidelines (`AGENTS.md`)

**Files:**
- Create: `AGENTS.md`

- [ ] **Step 1: Write `AGENTS.md` detailing architecture, tooling, and skills**

```markdown
# MediSync Express — Guia do Desenvolvedor de IA (AGENTS.md)

Este documento contém as instruções mandatórias para qualquer agente de IA ou desenvolvedor atuando neste repositório.

---

## 1. Comandos e Tooling

* **Gerenciador de Pacotes:** `uv`. Nunca use `pip install` global.
* **Automação:** Sempre utilize os comandos do `justfile`:
  * `just check` — Executa o portão de qualidade completo (fmt, lint, typecheck, tach, test).
  * `just fmt` — Formata o código com `ruff`.
  * `just lint` — Executa lint com autofix seguro (`ruff check . --fix`).
  * `just typecheck` — Executa checagem estrita de tipos com `basedpyright`.
  * `just tach` — Valida as fronteiras modulares com `tach check`.
  * `just test` — Executa testes com medição de cobertura (`pytest`).
  * `just test-fast` — Executa testes rápidos em paralelo (`pytest -n auto --no-cov`).

---

## 2. Princípios Arquiteturais Pétreos (ADR-001)

1. **Hexagonal Pragmático sem Mapper Hell:**
   * Entidades persistidas com SQLAlchemy 2.0 (`Mapped[...]`) são **modelos ricos** e residem no domínio do próprio módulo.
   * Encapsulam regras clínicas, validações e transições de estado.
   * **Proibido:** Criar DTOs espelho duplicados com conversores manuais (`to_domain`/`to_orm`).
2. **Comunicação Inter-Módulos:**
   * Os módulos em `src/modules/*` são independentes e fechados.
   * Comunicação síncrona ocorre exclusivamente via portas abstratas (`typing.Protocol` do PEP 544) e DTOs imutáveis (`@dataclass(frozen=True)` ou Pydantic v2).
   * **Proibido:** Importar modelos internos, tabelas ou repositórios de outro módulo.
   * Toda violação modular é bloqueada pelo `tach check`.
3. **Tipagem Estrita:**
   * O código deve passar em `basedpyright` com `typeCheckingMode = "strict"`.
   * Evite `Any`. Use tipos genéricos, `Union`, `Literal` ou `Protocol`.

---

## 3. Catálogo de Skills do Projeto

Consulte e utilize as skills especializadas localizadas em `.agents/skills/`:
* [`.agents/skills/fastapi`](.agents/skills/fastapi/SKILL.md): Boas práticas com FastAPI, injeção de dependências, routers e Pydantic v2.
* [`.agents/skills/sqlalchemy-alembic-expert-best-practices-code-review`](.agents/skills/sqlalchemy-alembic-expert-best-practices-code-review/SKILL.md): Padrões de queries assíncronas no SQLAlchemy 2.0, migrations idempotentes e modelagem relacional.
* [`.agents/skills/valkey`](.agents/skills/valkey/SKILL.md): Comandos atômicos, Sorted Sets (ZSET), scripts Lua e caching de alta performance.

---

## 4. Definição de Pronto (DoD)

Antes de finalizar qualquer tarefa ou abrir PR:
- [ ] O código adere aos padrões do Hexagonal Pragmático.
- [ ] Novos testes foram adicionados (unitários ou integração).
- [ ] `just check` foi executado e passou com código de retorno 0.
```

- [ ] **Step 2: Commit**

```bash
git add AGENTS.md
git commit -m "docs(agents): add AGENTS.md with architecture principles, commands and skill directory"
```

---

### Task 7: Full Quality Verification & GitHub Issue Close Check

**Files:**
- None (verification phase)

- [ ] **Step 1: Execute `just check` to ensure clean environment**

Run: `just check`
Expected output: All 5 steps pass cleanly (Ruff format, Ruff lint, Basedpyright, Tach, Pytest with coverage).

- [ ] **Step 2: Verify git status is clean**

Run: `git status`
Expected output: Working tree clean, nothing to commit.

- [ ] **Step 3: Document closing of GitHub Issue #1**

Check issue status and close Issue #1 with resolution comment referencing the commits:
Run: `gh issue close 1 --comment "Concluído via setup do uv, ruff, basedpyright, tach, pytest, justfile e AGENTS.md"`
Expected output: Issue #1 closed.
