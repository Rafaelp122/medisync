# Composition Root e Injeção de Dependências

> Raiz de composição por módulo e fiação sem acoplamento; vive em `src/modules/`.

## Contexto

No design com Inversão de Controle (IoC), o **Composition Root** (Mark Seemann) é o ponto centralizado onde o grafo de objetos da aplicação é montado. No Hexagonal Pragmático do MediSync Express (ADR-001, ADR-009), cada módulo vertical possui sua própria raiz de composição (ex.: `src/modules/auth/composition.py`), evitando um montador monolítico global.

A camada de composição orquestra a injeção de adaptadores de infraestrutura nas portas de aplicação, expõe dependências tipadas via `*Dep` para routers e disponibiliza fábricas síncronas para workers e testes.

As regras de fronteiras são verificadas por máquina no `tach.toml` (Stage B) e por testes AST em `tests/architecture/`.

## Conceito

### 1. Fiação Dinâmica sem Globais Mutáveis (ADR-009)

Módulos não mantêm referências globais mutáveis nem utilizam a palavra-chave `global`. A seleção entre adaptadores concretos e adaptadores em memória ocorre dinamicamente inspecionando `CommonSettings` via `get_settings()` ou parâmetros injetados:

```python
def get_rate_limiter(settings: SettingsDep) -> RateLimiterPort:
    if settings.RATE_LIMIT_BACKEND == "memory":
        return FakeAuthRateLimiter()
    return ValkeyAuthRateLimiter(get_valkey_client())
```

Essa abordagem garante determinismo, concorrência segura com `pytest-xdist` e elimina vazamento de estado entre testes.

### 2. Regra Pétrea: Serviços Não Importam Configurações

Serviços de aplicação em `src/modules/` **nunca importam `get_settings()` nem `src.core.config`**.

```python
# Correto: serviço recebe dependências e primitivos no construtor
class AuthService:
    def __init__(self, session: AsyncSession, secret_key: str): ...
```

Quem lê o ambiente é exclusivamente o `composition.py` do módulo, passando parâmetros resolvidos para o construtor do serviço. A adesão a esta regra é assegurada via teste estático AST em `tests/architecture/test_services_and_composition.py`.

### 3. Dupla de Fábricas Canônicas

Todo Composition Root expõe dois pontos de entrada para construção de serviços:

1. **Fábrica FastAPI (`get_*_service`)**: Consome `DbSessionDep` e dependências assíncronas via `Depends()`. É exportada como type alias `*Dep = Annotated[T, Depends(get_*_service)]` para injeção limpa em routers finos.
2. **Fábrica Síncrona (`build_*_service_for_session`)**: Recebe `AsyncSession` explícita e parâmetros opcionais. É consumida por workers ARQ (`src/worker/`), rotinas CLI e testes de integração sem overhead de injeção HTTP.

### 4. `composition.py` vs `presentation/dependencies.py`

Embora ambos usem primitivas do FastAPI (`Depends`), suas atribuições não se misturam:

| Critério | `composition.py` | `presentation/dependencies.py` |
| :--- | :--- | :--- |
| **Camada** | Raiz do módulo (IoC técnico) | Apresentação HTTP / WebSocket |
| **Pode importar** | `src.core`, `application`, `domain`, `infrastructure` | `src.core`, `application`, `composition` (**nunca** `infrastructure`) |
| **Erros** | Erros de domínio (`src/core/errors.py`) | Único local que lança `HTTPException(429, 401, 403)` |
| **Conhecimento** | Agnóstico a HTTP (trabalha com portas e sessões) | Conhece headers, cookies, tokens e IPs |
| **Consumidores** | Routers HTTP, Workers ARQ e Testes | Apenas Routers HTTP e Endpoints WebSocket |

### 5. Sobrescrita de Testes via `app.dependency_overrides`

Como routers consomem fábricas puras através de aliases `*Dep`, testes unitários de rotas substituem o serviço inteiro por dublês sem tocar em banco ou rede:

```python
# Em testes: substituição pontual sem infraestrutura
app.dependency_overrides[get_fila_service] = lambda: mock_service
```

Combinado com perfis `ENVIRONMENT="test"`, os testes alcançam execução instantânea em memória (`just test-fast`).

### 6. Composition Root da Aplicação (`src/main.py`) e Hooks de Ciclo de Vida

No nível global, `src/main.py` é o **Composition Root enxuto** da aplicação:

1. **Montagem de Rotas**: `src/main.py` não conhece sub-roteadores internos. Cada módulo exporta `http_router` (e `ws_router`) via `presentation/routers/__init__.py`. O `main.py` monta cada módulo com um único `api_v1.include_router(...)`.
2. **Isolamento de Infraestrutura**: `main.py` **nunca importa nada de `src.modules.*.infrastructure`** (assegurado por `tests/architecture/test_main_composition_root.py`).
3. **Hooks de Ciclo de Vida (`on_startup`)**: Quando um módulo precisa executar inicializações na inicialização do servidor (como o pré-carregamento de scripts Lua no Valkey), a lógica fica encapsulada no `composition.py` do módulo (ex.: `src/modules/queue/composition.py:on_startup`). O `lifespan` em `main.py` apenas despacha o hook assíncrono.
4. **Diagnóstico do Sistema**: O endpoint `/healthz` é isolado em `src/core/health_router.py` sob o guard de routers finos, consumindo `APP_VERSION` do `Settings`.

## Onde no código

- Impl auth composition: `src/modules/auth/composition.py:get_auth_service`
- Impl triage composition: `src/modules/triage/composition.py:get_triage_service`
- Impl consultation composition: `src/modules/consultation/composition.py:get_pep_service`
- Impl identity composition: `src/modules/identity/composition.py:get_onboarding_service`
- Impl queue composition: `src/modules/queue/composition.py:get_fila_service`
- Impl queue notification adapter: `src/modules/queue/composition.py:get_notification_adapter`
- Impl queue startup hook: `src/modules/queue/composition.py:on_startup`
- Impl telemetry composition: `src/modules/telemetry/composition.py:get_telemetry_service`
- Impl global composition root: `src/main.py:create_app`
- Impl health router: `src/core/health_router.py:health_router`
- Spec de fronteiras: `tach.toml`
- Prova viva AST serviços: `tests/architecture/test_services_and_composition.py:test_services_do_not_import_config_or_get_settings`
- Prova viva AST routers: `tests/architecture/test_routers_are_thin.py:test_routers_do_not_instantiate_services`
- Prova viva AST main composition root: `tests/architecture/test_main_composition_root.py:test_main_does_not_import_infrastructure`
- Prova viva wiring: `tests/unit/test_composition_wiring.py:test_auth_rate_limiter_resolution`
- Prova viva queue wiring: `tests/unit/test_composition_wiring.py:test_queue_notification_adapter_resolution_with_rate_limiter`
- Ver: `rg -n "build_.*_for_session|get_.*_service" src/modules/*/composition.py`

## Verificação

```bash
uv run pytest tests/architecture/ -v --no-cov
uv run pytest tests/unit/test_composition_wiring.py -v --no-cov
just tach
```

Esperado: todos os testes AST aprovados, fiação dinâmica validada e fronteiras do Tach intactas (`All modules validated!`).

## Ver também

- [Wire module dependencies](../../how-to/backend/wire-module-dependencies.md)
- [Create module endpoint](../../how-to/backend/create-module-endpoint.md)
- [Hexagonal Pragmático](hexagonal-pragmatico.md)
- [Environment Variables](../../reference/environment/variables.md)
- [ADR-001](../../adrs/ADR-001-Hexagonal-Pragmatico-Modelos-Ricos-Protocols-e-Tach.md)
- [ADR-009](../../adrs/ADR-009-Configuracoes-Polimorficas-por-Perfil-e-Desacoplamento-nos-Composition-Roots.md)
