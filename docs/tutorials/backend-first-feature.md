# Backend first feature

> Vertical slice completo: router fino → `*Dep` composition → service com `commit()` 1x → teste verde.

## Contexto

Primeiro endpoint toca 4 camadas sem vazar SQL no router nem instanciar service na mão.
Padrão vale para qualquer módulo em `src/modules/`. Exemplo canônico abaixo usa identity onboarding; fila usa mesmo esqueleto com Valkey + Lua.

## Conceito

### Router fino

Router só declara rota, recebe `body + TenantDep + DbSessionDep + *Dep`, chama 1 método do service, retorna `Response.model_validate(result)`.
Proibido no router: importar `sqlalchemy`, `infrastructure`, `domain.models`; chamar `.commit()`, `.refresh()`, `text()`, `select()`; instanciar `*Service(`; levantar `HTTPException` direto.

### Composition `*Dep`

Service é stateless e vem de `src/modules/identity/composition.py` via `Annotated[..., Depends(...)]`.
Router nunca faz `OnboardingService()`. Troca de impl (mock em teste, outra infra) acontece na composition, não no router.

### Service commita 1x, helpers nunca

Método público que persiste termina com 1 `await session.commit()` ( + `refresh` se precisa retornar entidade).
Helpers, policies e validators nunca commitam. Regra permite 1 transação por caso de uso, rollback simples, teste determinístico.
Queue segue mesma regra com `self._db_session.commit()` após transição de estado + compensação Valkey em `except`.

### `HTTPException` só em `presentation/dependencies.py`

Rate limit, path parsing, guardas HTTP vivem em dependencies. Exemplo: `exigir_rate_limit` → 429 com header `Retry-After`.
Routers importam o guard de lá. Erro de negócio nunca é `HTTPException`; é exceção de domínio.

### Erros de domínio via `src/core/errors.py`

Service levanta `NotFoundError`, `ForbiddenError`, `ValidationError`, `TenantInvalidoError`, etc.
Handler global converte para RFC 7807 (`title/status/detail/code`). Router não faz try/except de negócio.
Códigos estáveis: `TENANT_INVALIDO`, `NOT_FOUND`, `VALIDATION_ERROR`, `CONFLICT`, `FORBIDDEN`.

### Fronteira `tach.toml`

`presentation` depende de `application + composition + core`. Nunca de `infrastructure` ou `domain` alheio.
Comunicação inter-módulos só via `Protocol` + DTO imutável. `tach check` quebra build se inverter.
Teste AST `tests/architecture/test_routers_are_thin.py` trava router fino no CI.

## Onde no código (só links)

- Router fino HTTP: `src/modules/identity/presentation/routers/onboarding_router.py:intake_fase_1`
- Router fino HTTP (segundo verbo): `src/modules/identity/presentation/routers/onboarding_router.py:enrichment_fase_2`
- Router WS fino: `src/modules/queue/presentation/routers/queue_ws_router.py:ws_queue_patient`
- Composition DI: `src/modules/identity/composition.py:OnboardingServiceDep`
- Service com commit 1x: `src/modules/identity/application/services/onboarding_service.py:realizar_fase_1`
- Service com commit 1x (fase 2): `src/modules/identity/application/services/onboarding_service.py:realizar_fase_2`
- Service fila com commit + compensação: `src/modules/queue/application/services/alocacao_service.py:alocar_chamada`
- Guard HTTP único: `src/modules/consultation/presentation/dependencies.py:exigir_rate_limit`
- Erros domínio: `src/core/errors.py:DomainError`
- Erros domínio (códigos): `src/core/errors.py:TenantInvalidoError`
- Fronteira modular: `tach.toml`
- Schemas resposta: `src/modules/identity/presentation/schemas.py:Fase1Response`
- Prova viva HTTP: `tests/integration/test_onboarding_api.py`
- Trava arquitetural: `tests/architecture/test_routers_are_thin.py`

Ver:

```bash
rg -n "await session.commit\(\)" src/modules/identity/application/services/onboarding_service.py
rg -n "_db_session.commit" src/modules/queue/application/services/alocacao_service.py
ls src/modules/queue/presentation/routers/ src/modules/identity/presentation/routers/
rg -n "HTTPException" src/modules/consultation/presentation/dependencies.py
```

## Verificação

Run:

```bash
just tach
```

Expected: `tach check` pass, zero violação de fronteira.

Run:

```bash
uv run pytest tests/integration/test_onboarding_api.py -v
```

Expected: onboarding fase-1 + fase-2 passam.

Run:

```bash
just check
```

Expected: fmt + lint + typecheck + tach + test verdes.

## Ver também

- [Create module endpoint](../how-to/backend/create-module-endpoint.md)
- [Write tests](../how-to/backend/write-tests.md)
- [Testing Strategy](../explanation/architecture/testing-strategy.md)
- [ADR-001 Hexagonal pragmático](../adrs/ADR-001-Hexagonal-Pragmatico-Modelos-Ricos-Protocols-e-Tach.md)
- [ADR-008 DTOs sem mapper hell](../adrs/ADR-008-Padronizacao-de-DTOs-e-Eliminacao-de-Mapper-Hell-na-Apresentacao.md)
- [Onboarding quickstart](onboarding-quickstart.md)
