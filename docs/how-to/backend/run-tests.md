# Run tests

> Qual comando de teste usar e quando. `just test` vs `test-fast` vs arquivo único.

## Contexto

Runner: pytest com config em `pyproject.toml` (`testpaths = ["tests"]`, `asyncio_mode = "auto"`). Paralelismo via pytest-xdist (`-n auto`). Suite unitária pura vive em `tests/unit/`; guardas de arquitetura em `tests/architecture/`; integração exige infra saudável (`just up`) + schema migrado (`just migrate`).

Se integração falha, primeiro garanta [Setup local](../dev-environment/setup-local.md) verde antes de culpar o código.

## Conceito

Três níveis, do mais lento/completo ao mais rápido/focado:

1. **`just test-fast`** — testes rápidos em memória, em paralelo (`pytest tests/unit tests/architecture -n auto --no-cov`). Zero Docker/IO, feedback instantâneo (~15s) no loop diário.
2. **`just test-unit`** — testes unitários e de arquitetura com cobertura (`pytest tests/unit tests/architecture --cov=src`).
3. **`just test-integration`** — testes de integração sobre infraestrutura real (`pytest tests/integration`).
4. **`just test`** — suite completa com cobertura (`pytest tests/unit tests/architecture tests/integration --cov=src --cov-report=term-missing`). Canônico pré-commit e pré-PR (roda dentro de `just check`).
5. **Arquivo único** — `pytest tests/unit/test_alocacao_service.py -v` (prova viva da fila, 6 testes, ~2s, sem infra). Iteração focada e TDD: rode o arquivo do módulo que você tocou antes da suite.

Regra: falhou? Isole no arquivo único primeiro; só suba de nível quando o foco estiver verde. Suite completa verde local antes de `just check`.

## Onde no código (só links)

- Config pytest: `pyproject.toml:testpaths`
- Prova viva fila: `tests/unit/test_alocacao_service.py`
- Suite unitária: `tests/unit/`
- Guarda routers: `tests/architecture/test_routers_are_thin.py`

Ver:

```bash
rg -n "testpaths|asyncio_mode|\[tool.pytest" pyproject.toml
```

Expected: `testpaths = ["tests"]` + `asyncio_mode = "auto"`.

```bash
rg -n "def test_" tests/unit/test_alocacao_service.py
```

Expected: 6 testes (alocação 409/rollback/sucesso + locks).

## Verificação

Run (focado, sem infra):

```bash
uv run pytest tests/unit/test_alocacao_service.py -v --no-cov
```

Expected: 6 passed em ~2s.

Run (unit completo, infra up mas sem DB):

```bash
uv run pytest tests/unit --no-cov -q
```

Expected: 404 passed em ~12s.

Run (suite completa paralela):

```bash
just test-fast
```

Expected: suite verde, exit 0.

Resultado observado com a pirâmide de testes segregada:

- Arquivo único: **6 passed in 1.62s**, exit 0.
- `tests/unit`: **418 passed em 12.17s**, exit 0.
- Guarda AST: **5 passed em 0.38s**, exit 0.
- `just test-fast`: **423 passed em ~14s**, 100% em memória, zero Docker, exit 0.
- `just test-integration`: **140 passed em ~25s**, infra real, exit 0.

## Ver também

- [Write tests](write-tests.md)
- [Testing Strategy](../../explanation/architecture/testing-strategy.md)
- [Testing Fixtures & Factories](../../reference/testing/fixtures-and-factories.md)
- [Setup local](../dev-environment/setup-local.md)
- [Onboarding quickstart](../../tutorials/onboarding-quickstart.md)
- [Create module endpoint](create-module-endpoint.md)
