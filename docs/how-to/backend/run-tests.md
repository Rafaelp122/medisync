# Run tests

> Qual comando de teste usar e quando. `just test` vs `test-fast` vs arquivo único.

## Contexto

Runner: pytest com config em `pyproject.toml` (`testpaths = ["tests"]`, `asyncio_mode = "auto"`). Paralelismo via pytest-xdist (`-n auto`). Suite unitária pura vive em `tests/unit/`; guardas de arquitetura em `tests/architecture/`; integração exige infra saudável (`just up`) + schema migrado (`just migrate`).

Se integração falha, primeiro garanta [Setup local](../dev-environment/setup-local.md) verde antes de culpar o código.

## Conceito

Três níveis, do mais lento/completo ao mais rápido/focado:

1. **`just test`** — suite completa com cobertura (`pytest --cov=src --cov-report=term-missing`). Canônico pré-commit e pré-PR (roda dentro de `just check`). Lento, completo, gera relatório de linhas não cobertas.
2. **`just test-fast`** — mesma suite sem cobertura, em paralelo (`pytest -n auto --no-cov`). Loop diário durante desenvolvimento. Rápido quando infra está saudável.
3. **Arquivo único** — `pytest tests/unit/test_alocacao_service.py -v` (prova viva da fila, 6 testes, ~2s, sem infra). Iteração focada e TDD: rode o arquivo do módulo que você tocou antes da suite.

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

Resultado observado em 2026-10-05 nesta branch (infra up, 4 contêineres healthy, sem correção de código — fora de escopo desta task):

- Arquivo único: **6 passed in 1.62s**, exit 0.
- `tests/unit`: **404 passed em 12.17s**, exit 0 (2 `DeprecationWarning` de `pyhanko_certvalidator`, pré-existentes).
- Guarda AST: **5 passed em 0.38s**, exit 0.
- `just test-fast` completo: **timeout após 300s sem concluir** (nenhum output em `tail -5`; processo ainda coletando/executando quando interrompido). Causa não investigada aqui; usar níveis focado/unitário acima para validar mudanças. Falha registrada, código não tocado.

## Ver também

- [Setup local](../dev-environment/setup-local.md)
- [Onboarding quickstart](../../tutorials/onboarding-quickstart.md)
- [Create module endpoint](create-module-endpoint.md)
