# Fixtures, Factories e Dublês (Testing Reference)

> Catálogo técnico de fixtures em `tests/conftest.py`, fábricas em `tests/factories/` e dublês em `tests/doubles.py`.

---

## 1. Fixtures Globais (`tests/conftest.py`)

| Fixture | Escopo | Tipo de Retorno | Descrição |
| :--- | :--- | :--- | :--- |
| `async_client` | Function | `AsyncGenerator[AsyncClient, None]` | Cliente HTTP assíncrono conectado ao app FastAPI via `ASGITransport(app=app)`. |
| `authed_client_factory` | Function | `Callable[[str, int, UUID \| None], AsyncClient]` | Função geradora de `AsyncClient` com headers `Authorization: Bearer <token>` e `X-Tenant-ID` pré-configurados. |
| `db_session` | Function | `AsyncGenerator[AsyncSession, None]` | Sessão assíncrona do SQLAlchemy 2.0 conectada ao PostgreSQL real com rollback/fechamento automático. |
| `mock_db_session` | Function | `AsyncMock` | Dublê mock de `AsyncSession` com mocks preparados para `add`, `flush`, `commit`, `refresh` e `execute`. |
| `clean_db` | Function (Autouse opcional) | `AsyncGenerator[None, None]` | Trunca todas as tabelas de domínio via `clean_database_tables()` antes e depois do teste. |
| `clean_db_and_valkey` | Function | `AsyncGenerator[None, None]` | Trunca tabelas de domínio e remove chaves de namespaces de teste do Valkey. |
| `cleanup_valkey_pool_fixture` | Function (Autouse) | `AsyncGenerator[None, None]` | Fecha graciosamente os pools de conexão com Valkey após cada teste. |

---

## 2. Catálogo de Fábricas de Modelos (`tests/factories/`)

Todas as fábricas retornam instâncias tipadas com valores padrão válidos, aceitando sobrescritas explícitas:

### Módulo Identidade (`tests/factories/identity.py`)
* `make_organizacao(*, cnpj, razao_social, modo_publico_sus, ...) -> Organizacao`
* `make_profissional(organizacao_id, *, cpf, papel, crm, ...) -> Profissional`
* `make_paciente(organizacao_id, *, cpf, data_nascimento, ...) -> Paciente`
* `make_dependente(organizacao_id, titular_id, dependente_id, ...) -> Dependente`

### Módulo Fila (`tests/factories/queue.py`)
* `make_atendimento(organizacao_id, paciente_id, *, status, prioridade_clinica, ...) -> Atendimento`

### Módulo Triagem (`tests/factories/triage.py`)
* `make_triagem(organizacao_id, atendimento_id, *, queixa_principal, prioridade_calculada, ...) -> Triagem`

### Módulo Consulta & PEP (`tests/factories/consultation.py`)
* `make_evolucao_clinica(organizacao_id, atendimento_id, *, cid10_principal, ...) -> EvolucaoClinica`
* `make_documento_clinico(organizacao_id, atendimento_id, *, tipo_documento, ...) -> DocumentoClinico`
* `make_documento_item(organizacao_id, documento_id, *, medicamento, posologia, ...) -> DocumentoItem`

### Módulo Auditoria (`tests/factories/audit.py`)
* `make_audit_event(organizacao_id, atendimento_id, *, tipo_evento, ator_tipo, ...) -> AuditEvent`

### Módulo Autenticação (`tests/factories/auth.py`)
* `make_usuario_credencial(organizacao_id, usuario_id, *, identificador, senha_hash, ...) -> UsuarioCredencial`
* `make_cadastrar_credencial_command(organizacao_id, usuario_id, *, identificador, senha_pura, ...) -> CadastrarCredencialCommand`

### Cenários Compostos Persistentes (`tests/factories/scenarios.py`)
* `seed_clinical_scenario(session, *, org_kwargs, paciente_kwargs, medico_kwargs, atendimento_kwargs) -> ClinicalScenario`
  * Cria e persiste atomicamente no banco: `Organizacao` + `Paciente` + `Profissional` (Médico) + `Atendimento`.
* `seed_multi_tenant_orgs(session) -> tuple[Organizacao, Organizacao]`
  * Cria e persiste duas organizações distintas para testes de isolamento multi-tenant e RLS.

---

## 3. Catálogo de Dublês Canônicos (`tests/doubles.py`)

Dublês em memória para acelerar testes unitários sem acoplamento com serviços externos:

* **`FakeAsyncSession`:** Dublê assíncrono de sessão SQLAlchemy com suporte a resultados pré-programados em `execute()`, rastreamento de entidades em `add()` e transações aninhadas em `begin_nested()`.
* **`FakeResult` / `FakeAddedResult`:** Dublês para respostas escalares (`scalar_one_or_none`, `scalar_one`).
* **`FakeValkey`:** Dublê em memória de cliente Valkey suportando operações de publicação e pubsub assíncrono.
* **`FakePubSub`:** Dublê in-memory thread-safe de canal Pub/Sub para testes de WebSockets e SSE.

---

## 4. Helpers Canônicos de Teste (`tests/helpers.py`)

* `clean_database_tables() -> None`: Executa `TRUNCATE TABLE ... CASCADE` nas tabelas de domínio do Postgres.
* `clean_valkey_keys(*patterns: str) -> None`: Limpa chaves do Valkey por padrão glob ou padrões padrão (`DEFAULT_VALKEY_TEST_PATTERNS`).
* `clean_database_and_valkey(*valkey_patterns: str) -> None`: Executa limpeza coordenada de Postgres e Valkey.
* `auth_headers(papel: str, org_id: int, usuario_id: UUID) -> dict[str, str]`: Emite cabeçalho HTTP `{"Authorization": "Bearer <jwt>"}` com token real assinado.
* `make_auth_service(session, **overrides) -> AuthService`: Fábrica do serviço de autenticação com fakes padrão.
* `make_pep_service(session, **overrides) -> PEPService`: Fábrica do serviço de prontuário eletrônico com fakes padrão.
* `make_alocacao(valkey, db_session, **overrides) -> AlocacaoChamadaService`: Fábrica do serviço de alocação de chamadas com fakes padrão.
* `make_fila_service(valkey, db_session, **overrides) -> FilaService`: Fábrica do serviço de filas com fakes padrão.
