# Como Escrever Testes (Write Tests)

> Receitas práticas para escrever testes unitários e de integração seguindo o Padrão Ouro do MediSync.

---

## 1. Como Escrever um Teste Unitário (Camada U)

Testes unitários residem em `tests/unit/`, rodam 100% em memória, não usam Docker e devem executar em milissegundos.

### Exemplo: Testando Regras de Domínio ou Modelos Ricos

Para validar entidades e cálculos de domínio sem acoplamento a banco de dados, utilize as fábricas em memória de `tests/factories/` e teste métodos ricos diretamente no modelo.

- Impl: `src/modules/queue/domain/models/atendimento.py:Atendimento`
- Spec: `docs/explanation/domains/queue-domain.md`
- Prova viva: `tests/unit/test_atendimento_model.py:test_ciclo_vida_completo_happy_path`
- Ver:

```bash
rg -n "def test_ciclo_vida|def test_transicoes" tests/unit/test_atendimento_model.py
```

Rode para verificar:

```bash
uv run pytest tests/unit/test_atendimento_model.py -v --no-cov
```

### Exemplo: Testando Services com Mocks de Sessão

Para testar métodos de aplicação e regras de serviço que recebem uma `AsyncSession`, utilize a fixture compartilhada `mock_db_session` ou helpers de construção com mocks:

- Impl: `src/modules/consultation/application/services/pep_service.py:PEPService`
- Spec: `src/modules/consultation/domain/exceptions.py:ConsultaFinalizadaError`
- Prova viva: `tests/unit/test_pep_soap_service.py:test_finalized_consultation_immutability`
- Ver:

```bash
rg -n "def test_.*finaliz|make_pep_service" tests/unit/test_pep_soap_service.py
```

Rode para verificar:

```bash
uv run pytest tests/unit/test_pep_soap_service.py -v --no-cov
```

---

## 2. Como Escrever um Teste de Integração (Camada I)

Testes de integração residem em `tests/integration/` e utilizam o PostgreSQL 17 e Valkey 8.0 reais provisionados localmente.

### Exemplo: Testando um Endpoint HTTP Autenticado

Utilize a fixture global `async_client`, o helper `auth_headers` (com papéis definidos em `src/core/authz/roles.py:Role`) e a persistência atômica de cenários com `seed_clinical_scenario`:

- Impl: `src/modules/consultation/presentation/routers/consultation_router.py`
- Spec: `tests/factories/scenarios.py:seed_clinical_scenario`
- Prova viva: `tests/integration/test_consultation_endpoints.py:test_consultation_soap_full_lifecycle_and_safeguards`
- Ver:

```bash
rg -n "test_consultation_soap|seed_clinical_scenario" tests/integration/test_consultation_endpoints.py
```

Rode para verificar:

```bash
uv run pytest tests/integration/test_consultation_endpoints.py -k test_consultation_soap_full_lifecycle_and_safeguards
```

---

## 3. Como Limpar Estado em Testes de Integração

- **Automático:** A fixture global `clean_db_and_valkey` (ou `clean_db`) em `tests/conftest.py` é executada automaticamente antes e depois de cada teste de integração, garantindo isolamento total entre execuções.
- **Sob demanda:** Caso seu teste realize operações concorrentes que exijam limpeza intermediária de tabelas ou chaves:
  - Impl: `tests/helpers.py:clean_database_tables`
  - Spec: `tests/conftest.py:clean_db`
  - Prova viva: `tests/conftest.py:clean_db_and_valkey`
  - Ver:

```bash
rg -n "clean_database_tables|clean_valkey_keys" tests/helpers.py
```

---

## 4. O que NUNCA fazer em testes

1. **Nunca use `DROP SCHEMA public CASCADE;`:** Isso destrói a infraestrutura de outros testes concorrentes e remove grants da role `medisync_app`.
2. **Nunca use `Base.metadata.create_all` em testes:** O schema deve ser provisionado canonicamente via migrações do Alembic (`just migrate`).
3. **Nunca copie blocos de 30 linhas de `session.add(...)`:** Use `seed_clinical_scenario(session)` ou as fábricas de persistência de `tests/factories/scenarios.py`.
4. **Nunca instancie `ASGITransport(app=app)` manualmente:** Use a fixture `async_client` ou `authed_client_factory` de `tests/conftest.py`.
5. **Nunca deixe testes sem tipagem estrita:** O `just typecheck` (`basedpyright`) roda em modo estrito tanto para `src/` quanto para `tests/`.
