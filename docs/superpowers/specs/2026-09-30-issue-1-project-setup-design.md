# Design Document: Issue #1 — Setup do Projeto, Ferramental Python e Governança

**Data:** 2026-09-30  
**Status:** Proposto  
**Issue de Referência:** [#1 - chore(setup): configure pyproject.toml, uv, ruff, basedpyright, tach and testing tooling](https://github.com/Rafaelp122/medisync/issues/1)  
**Autor:** Antigravity & Rafael

---

## 1. Visão Geral & Contexto

O objetivo desta etapa é estabelecer as fundações de engenharia de software do **MediSync Express**, preparando o ambiente para todo o desenvolvimento dos módulos de negócio e infraestrutura.

O projeto adotará:
* **`uv`** como gerenciador de dependências e ambientes virtuais ultrarrápido para Python 3.12+.
* **`ruff`** para formatação e linting estrito com regras modernas de qualidade, segurança e tipagem.
* **`basedpyright`** em modo estrito (`strict`) para garantia de segurança de tipos em tempo de compilação/estático.
* **`tach`** para governança arquitetural de fronteiras modulares (garantindo que `identity`, `triage`, `queue`, `consultation` e `billing` não violem o isolamento do monólito modular conforme [ADR-001](../../adrs/ADR-001-Hexagonal-Pragmatico-Modelos-Ricos-Protocols-e-Tach.md)).
* **`pytest`** com suporte a testes assíncronos (`pytest-asyncio`), paralelismo (`pytest-xdist`) e cobertura (`pytest-cov` com meta de 85%+).
* **`just`** (`justfile`) para padronizar comandos de desenvolvimento e qualidade em atalhos concisos.
* **`AGENTS.md`** na raiz do projeto para orientar agentes de IA em relação aos padrões arquiteturais, comandos de teste/lint e uso das skills do repositório.

---

## 2. Estrutura de Diretórios Inicial

A estrutura do projeto seguirá o padrão modular definido no [Overview de Arquitetura](../../03-architecture/overview.md):

```text
medisync/
├── .agents/
│   └── skills/
│       ├── fastapi/
│       ├── sqlalchemy-alembic-expert-best-practices-code-review/
│       └── valkey/
├── docs/
│   ├── 01-business/
│   ├── 02-product/
│   ├── 03-architecture/
│   ├── adrs/
│   └── superpowers/specs/
├── src/
│   ├── __init__.py
│   ├── core/                      # Componentes transversais
│   │   └── __init__.py
│   └── modules/                   # Módulos do domínio
│       ├── __init__.py
│       ├── billing/
│       │   └── __init__.py
│       ├── consultation/
│       │   └── __init__.py
│       ├── identity/
│       │   └── __init__.py
│       ├── queue/
│       │   └── __init__.py
│       └── triage/
│           └── __init__.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── unit/
│   │   ├── __init__.py
│   │   └── test_smoke.py          # Teste inicial para validar setup do pytest
│   └── integration/
│       └── __init__.py
├── AGENTS.md                      # Diretrizes de IA e arquitetura
├── justfile                       # Automação de tarefas de desenvolvimento
├── pyproject.toml                 # Definição do projeto e dependências (uv)
├── tach.toml                      # Declaração das fronteiras modulares
└── README.md
```

---

## 3. Especificação Técnica dos Componentes

### 3.1 `pyproject.toml`
* **Python Target:** `>=3.12`
* **Dependências de Produção (Core para inicialização):**
  * `fastapi>=0.115.0`
  * `pydantic>=2.8.0`
  * `pydantic-settings>=2.4.0`
* **Dependências de Desenvolvimento (`[dependency-groups.dev]`):**
  * `ruff>=0.6.0`
  * `basedpyright>=1.18.0`
  * `tach>=0.18.0`
  * `pytest>=8.3.0`
  * `pytest-asyncio>=0.24.0`
  * `pytest-cov>=5.0.0`
  * `pytest-xdist>=3.6.0`

#### Configuração do Ruff
* Regras ativadas: `["E", "W", "F", "I", "UP", "B", "SIM", "TCH", "ASYNC", "S", "RUF"]`
* `line-length = 88`
* `target-version = "py312"`
* Ignore sensato para testes (ex.: ignorar `S101` assert em `tests/*`).

#### Configuração do Basedpyright
* `typeCheckingMode = "strict"`
* `pythonVersion = "3.12"`
* `include = ["src", "tests"]`

#### Configuração do Pytest
* `testpaths = ["tests"]`
* **Assincronismo Nativamente Ativo (`pytest-asyncio`)**:
  * `asyncio_mode = "auto"`: Permite que funções de teste assíncronas (`async def test_*`) e fixtures assíncronas sejam executadas diretamente sem necessidade de decorar com `@pytest.mark.asyncio`.
  * `asyncio_default_fixture_loop_scope = "function"`: Garante isolamento estrito de event loop por teste, em conformidade com o `pytest-asyncio>=0.24`.
* **Paralelismo (`pytest-xdist`)**:
  * Disponível via flag `-n auto` (ou `-n <workers>`).
  * Integrado com receitas dedicadas no `justfile` para permitir execução paralela em suítes unitárias, mantendo a suíte de integração com estado de banco protegida contra colisões de workers.
* `addopts = "--strict-markers -ra --cov=src --cov-report=term-missing --cov-fail-under=85"`

---

### 3.2 Governança Modular com `tach.toml`

Conforme a [ADR-001](../../adrs/ADR-001-Hexagonal-Pragmatico-Modelos-Ricos-Protocols-e-Tach.md) e [Architecture Overview](../../03-architecture/overview.md#L309-L322), cada módulo em `src/modules/*` é considerado fechado por padrão:
* `src/core`: Módulo compartilhado permitido para dependências utilitárias de infraestrutura/configuração.
* Módulos: `src/modules/identity`, `src/modules/triage`, `src/modules/queue`, `src/modules/consultation`, `src/modules/billing`.
* Dependências cruzadas entre módulos devem ser explicitadas ou bloqueadas. Nenhuma dependência cruzada direta entre módulos privados é permitida; a comunicação ocorre via contratos públicos de portas (`typing.Protocol`) e DTOs imutáveis.

---

### 3.3 Automação de Comandos com `justfile`

O arquivo `justfile` disponibilizará comandos diretos:

```just
# Exibe ajuda com todos os comandos disponíveis
default:
    @just --list

# Instala todas as dependências com uv
install:
    uv sync

# Formata código com ruff
fmt:
    uv run ruff format .

# Executa lint com autofix seguro
lint:
    uv run ruff check . --fix

# Executa checagem de tipos estrita
typecheck:
    uv run basedpyright

# Executa auditoria de fronteiras modulares com tach
tach:
    uv run tach check

# Executa testes unitários e de integração com cobertura
test:
    uv run pytest

# Executa testes em paralelo com todos os cores da CPU (pytest-xdist)
test-parallel:
    uv run pytest -n auto

# Executa testes rápidos em paralelo sem medição de cobertura (para fluxo TDD ágil)
test-fast:
    uv run pytest -n auto --no-cov

# Portão de qualidade completo (executado antes de commits/PRs)
check: fmt lint typecheck tach test
```

---

### 3.4 Diretrizes de IA em `AGENTS.md`

O documento `AGENTS.md` definirá:
1. **Regra de Execução de Comandos**: Sempre usar `just <comando>` ou comandos prefixados por `uv run`. Nunca usar `pip install` global.
2. **Arquitetura (ADR-001)**:
   * **Hexagonal Pragmático**: Entidades ricas do SQLAlchemy 2.0 (`Mapped[...]`) são permitidas no domínio do próprio módulo. Jamais criar classes DTO idênticas com mappers manuais redundantes (`to_domain`/`to_orm`).
   * **Comunicação Inter-Módulos**: Apenas via contratos estruturais (`typing.Protocol` do PEP 544) e DTOs imutáveis (`@dataclass(frozen=True)` ou Pydantic v2).
   * **Bloqueio Modular**: Nunca importar arquivos internos de outro módulo. O `tach check` é autoridade final.
3. **Catálogo de Skills Disponíveis**:
   * `.agents/skills/fastapi`: Convenções de rotas, dependências, injeção e Pydantic v2.
   * `.agents/skills/sqlalchemy-alembic-expert-best-practices-code-review`: Padrões do SQLAlchemy 2.0 assíncrono, migrations idempotentes no Alembic e consultas otimizadas.
   * `.agents/skills/valkey`: Operações atômicas no Valkey, Sorted Sets, scripts Lua e cache.
4. **Padrão de Qualidade**: Antes de considerar qualquer tarefa finalizada, `just check` deve passar com código de saída 0.

---

## 4. Plano de Verificação

### Critérios de Aceite (Definition of Done da Issue #1)
- [ ] `uv sync` sincroniza todas as dependências core e dev sem conflitos.
- [ ] `uv run ruff check .` e `uv run ruff format --check .` passam sem erros.
- [ ] `uv run basedpyright` executa e passa em modo estrito.
- [ ] `uv run tach check` executa e valida as fronteiras modulares sem violações.
- [ ] `uv run pytest` executa e descobre os testes com sucesso.
- [ ] Todos os atalhos do `just` funcionam conforme especificado.
