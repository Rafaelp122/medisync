# Backend first feature

> Guia prático passo a passo: construindo uma fatia vertical completa no padrão Hexagonal Pragmático sem mapper hell.

## Visão geral

Neste tutorial, você aprenderá a construir um novo endpoint seguindo os princípios de design do MediSync Express (ADR-001 e ADR-008): schemas Pydantic v2 diretos, regras de negócio encapsuladas no Service com transação atômica única, injeção de dependência na Composition Root e um Router fino validado por AST e Tach.

Utilizaremos como exemplo canônico o fluxo de acolhimento do paciente no módulo `src/modules/identity/`.

---

## Passo 1: Definir os schemas de entrada e saída

Em `src/modules/identity/presentation/schemas.py`, declare o schema de entrada derivado do Pydantic v2 com `frozen=True`. Se os dados vêm 100% do corpo JSON, utilize o próprio schema como entrada do caso de uso no Service, eliminando DTOs espelho:

```python
class Fase1Request(BaseModel):
    model_config = ConfigDict(frozen=True)
    nome_completo: str
    queixa_principal: str
```

Para a resposta, configure `from_attributes=True` para permitir a serialização direta de entidades do domínio ou DTOs sem conversores manuais:

```python
class Fase1Response(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    paciente_id: UUID
    token: str
```

---

## Passo 2: Implementar o caso de uso no Service

No Service de aplicação (`src/modules/identity/application/services/onboarding_service.py`), implemente a regra de negócio executando exatamente 1 transação por caso de uso. O método público que persiste é o único responsável por finalizar com `await session.commit()`:

```python
# Service commita 1x no final do caso de uso
await db.commit()
await db.refresh(paciente)
return Fase1OutputDTO(paciente_id=paciente.id, token=token)
```

Regras obrigatórias do Service:
- Helpers, policies e validadores nunca chamam `.commit()`.
- Erros de validação ou regras clínicas devem lançar exceções de domínio de `src/core/errors.py` (ex.: `ValidationError`, `TenantInvalidoError`), nunca `HTTPException`.

---

## Passo 3: Declarar a injeção na Composition Root

Em `src/modules/identity/composition.py`, centralize a montagem do serviço e suas portas. Nunca instancie o serviço diretamente no Router. Exporte um alias tipado com `Annotated` e `Depends`:

```python
def get_onboarding_service(session: DbSessionDep) -> OnboardingService:
    return OnboardingService(session=session)

OnboardingServiceDep = Annotated[OnboardingService, Depends(get_onboarding_service)]
```

Essa separação garante desacoplamento de infraestrutura (ADR-009) e permite substituição transparente de dependências em testes automatizados.

---

## Passo 4: Criar o router fino

Crie a rota HTTP em `src/modules/identity/presentation/routers/onboarding_router.py`. O router é estritamente fino: ele apenas recebe a requisição, invoca o método do Service e valida a resposta:

```python
@onboarding_router.post("/fase-1", status_code=201)
async def intake(body: Fase1Request, t: TenantDep, s: OnboardingServiceDep):
    result = await s.realizar_fase_1(t, body)
    return Fase1Response.model_validate(result)
```

Restrições pétreas para o Router (validadas por AST):
- Proibido importar `sqlalchemy`, `infrastructure` ou `domain.models`.
- Proibido chamar `.commit()`, `.refresh()`, `text()` ou `select()`.
- Proibido instanciar serviços com `*Service()`.
- Proibido levantar `HTTPException` para erros de negócio.
- Registre o router no agregador `src/modules/identity/presentation/routers/__init__.py`.

---

## Passo 5: Escrever o teste de integração e validar

Crie o teste em `tests/integration/test_onboarding_api.py` consumindo o endpoint via `httpx.AsyncClient` contra a infraestrutura real:

```bash
uv run pytest tests/integration/test_onboarding_api.py -v
```

Valide que as fronteiras modulares hexagonais não foram violadas:

```bash
just tach
```

Valide que a trava arquitetural do Router Fino (AST) foi respeitada:

```bash
uv run pytest tests/architecture/test_routers_are_thin.py --no-cov -q
```

Por fim, execute o portão completo de qualidade:

```bash
just check
```

---

## Ver também

- [Criar endpoint em módulo](../how-to/backend/create-module-endpoint.md)
- [Escrever testes](../how-to/backend/write-tests.md)
- [Estratégia de testes](../explanation/architecture/testing-strategy.md)
- [ADR-001: Hexagonal Pragmático](../adrs/ADR-001-Hexagonal-Pragmatico-Modelos-Ricos-Protocols-e-Tach.md)
- [ADR-008: DTOs sem Mapper Hell](../adrs/ADR-008-Padronizacao-de-DTOs-e-Eliminacao-de-Mapper-Hell-na-Apresentacao.md)
- [Onboarding quickstart](onboarding-quickstart.md)
