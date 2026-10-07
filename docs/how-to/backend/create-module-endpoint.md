# Create module endpoint (router fino)

> Adicione endpoint a módulo existente sem vazar camadas. Checklist router-fino + onde conferir cada regra.

## Contexto

Vale para qualquer módulo em src/modules (auth, consultation, identity, queue). Arquitetura Hexagonal Pragmática (ADR-001/ADR-008): router fino, service commita, composition injeta, fronteiras validadas por `tach check` + guarda AST.

Fluxo canônico: router recebe `*Dep` da `composition.py` → chama service com schema Pydantic ou `Command` → service persiste com 1 `commit()` → resposta via `ResponseSchema.model_validate(objeto)`. Schemas moram em `presentation/schemas.py`; Commands em `application/dtos.py`.

## Conceito

Checklist obrigatório para todo endpoint novo (conferência via AST, não revisão manual):

1. **Router sem import proibido.** Nunca importe `sqlalchemy`, `infrastructure` ou `domain.models` no router. Nunca chame `.commit()`, `.refresh()`, `text()` ou `select()` no router.
2. **Router nunca instancia service.** Nada de `*Service(` no router. Receba via `*Dep` da `composition.py` (ex.: `PEPServiceDep`, `TenantDep`, `ClinicalAccessDep` como parâmetros).
3. **Service commita 1x por caso de uso.** `await session.commit()` no fim do método público que persiste. Helpers e policies nunca commitam.
4. **HTTPException só em `presentation/dependencies.py`.** Único lugar que pode levantar 429 é helper como `exigir_rate_limit` (com header `Retry-After`). Routers importam de lá. Erros de domínio via `src/core/errors.py` (`NotFoundError`, `ForbiddenError`, …).
5. **Guardas verdes.** `tests/architecture/test_routers_are_thin.py` (AST, 5 testes) e `just tach` (fronteiras) devem passar antes do commit.

Entrada: se dados vêm 100% do corpo JSON, use schema Pydantic (`frozen=True`) direto como entrada do service. Use `@dataclass(frozen=True)` com sufixo `Command` só para agregar múltiplas origens (path params, tenant, IP). Saída: `model_config = ConfigDict(from_attributes=True)` + `model_validate`. Proibido mapeamento manual campo a campo e DTOs espelho com `to_domain`/`to_orm`.

## Onde no código (só links)

- Fronteira modular: `tach.toml`
- Rate limit canônico: `src/modules/consultation/presentation/dependencies.py:exigir_rate_limit` (levanta 429 + `Retry-After`; routers importam daqui)
- Router fino exemplo: `src/modules/consultation/presentation/routers/consultation_router.py:PEPServiceDep` (recebe service via Dep; erros de `src/core/errors.py`)
- Composition exemplo: `src/modules/consultation/composition.py:get_pep_service` (único lugar que instancia services/adapters)
- Service commit exemplo: `src/modules/identity/application/services/onboarding_service.py` (1 `commit()` por caso de uso)
- Erros de domínio: `src/core/errors.py:ProblemDetail`
- Guarda AST: `tests/architecture/test_routers_are_thin.py`

Ver:

```bash
rg -n "await session.commit\(\)" src/modules/identity/application/services/ | head -5
```

Expected: commits só em services, 1 por caso de uso.

```bash
rg -n "ServiceDep" src/modules/consultation/presentation/routers/consultation_router.py | head -5
```

Expected: router consome Deps, nunca instancia `*Service(`.

```bash
rg -n "Retry-After" src/modules/consultation/presentation/dependencies.py
```

Expected: header presente no caminho 429.

## Verificação

Run:

```bash
uv run pytest tests/architecture/test_routers_are_thin.py --no-cov -q
```

Expected: 5 passed (observado 5 passed em 0.38s nesta branch).

Run:

```bash
just tach
```

Expected: `All modules validated!`, exit 0 (observado verde nesta branch).

Run:

```bash
just test-fast
```

Expected: suite verde. Nota: nesta branch o `test-fast` completo excedeu 300s sem concluir (ver detalhe em [Run tests](run-tests.md)); para validar endpoint novo prefira o nível unitário + guarda AST acima, sem corrigir suite aqui.

## Ver também

- [Backend first feature](../../tutorials/backend-first-feature.md)
- [Run tests](run-tests.md)
- [ADR-001](../../adrs/ADR-001-Hexagonal-Pragmatico-Modelos-Ricos-Protocols-e-Tach.md)
