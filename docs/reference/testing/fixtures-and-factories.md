# Fixtures, Fábricas e Dublês

> Catálogo técnico de fixtures em `tests/conftest.py`, fábricas em `tests/factories/` e dublês em `tests/doubles.py`.

## Contexto

A suíte de testes do MediSync Express opera sob o princípio de feedback ultrarrápido sem dependência de containers para testes unitários (`just test-fast`).
Fixtures globais orquestram o ciclo de vida do cliente HTTP, sessões assíncronas de banco de dados e pools de cache.
Fábricas modulares instanciam modelos ricos com atributos padrão consistentes, permitindo sobrescritas explícitas sem acoplamento a arquivos estáticos em JSON ou SQL.
Para testes de integração, seeders compostos persistem grafos clínicos completos garantindo integridade relacional e multi-tenancy.

## Conceito

A infraestrutura de teste é organizada em quatro grupos: fixtures globais, fábricas de modelos, dublês canônicos e helpers de suporte.

### Fixtures Globais (`tests/conftest.py`)

| Fixture | Escopo | Retorno | Descrição |
|---|---|---|---|
| `sample_async_resource` | Function | `AsyncGenerator[str, None]` | Recurso assíncrono para validação do escopo do event loop `pytest-asyncio`. |
| `async_client` | Function | `AsyncGenerator[AsyncClient, None]` | Cliente HTTP assíncrono conectado ao ASGI FastAPI via `ASGITransport`. |
| `authed_client_factory` | Function | `Callable[[str, int, UUID \| None], AsyncClient]` | Gerador de cliente HTTP com cabeçalhos `Authorization` e `X-Tenant-ID`. |
| `db_session` | Function | `AsyncGenerator[AsyncSession, None]` | Sessão assíncrona SQLAlchemy conectada ao Postgres real com rollback automático. |
| `mock_db_session` | Function | `AsyncMock` | Dublê mock de `AsyncSession` com métodos preparados (`add`, `commit`, etc.). |
| `clean_db` | Function | `AsyncGenerator[None, None]` | Trunca tabelas de domínio via `clean_database_tables()` antes e após o teste. |
| `clean_db_and_valkey` | Function | `AsyncGenerator[None, None]` | Limpeza coordenada de tabelas Postgres e chaves de teste no Valkey. |
| `cleanup_valkey_pool_fixture` | Function (Autouse) | `AsyncGenerator[None, None]` | Fecha graciosamente os pools de conexão Valkey ao final de cada teste. |

### Fábricas de Modelos de Domínio (`tests/factories/`)

- **Identidade** (`tests/factories/identity.py`):
  - `make_organizacao(*, cnpj, razao_social, nome_fantasia, id, ...) -> Organizacao`
  - `make_profissional(organizacao_id, *, cpf, papel, crm, ...) -> Profissional`
  - `make_paciente(organizacao_id, *, cpf, data_nascimento, ...) -> Paciente`
  - `make_dependente(organizacao_id, titular_id, dependente_id, ...) -> Dependente`
- **Fila** (`tests/factories/queue.py`):
  - `make_atendimento(organizacao_id, paciente_id, *, status, prioridade_clinica, ...) -> Atendimento`
- **Triagem** (`tests/factories/triage.py`):
  - `make_triagem(organizacao_id, atendimento_id, *, queixa_principal, prioridade_calculada, ...) -> Triagem`
- **Consulta & PEP** (`tests/factories/consultation.py`):
  - `make_evolucao_clinica(organizacao_id, atendimento_id, *, cid10_principal, ...) -> EvolucaoClinica`
  - `make_documento_clinico(organizacao_id, atendimento_id, *, tipo_documento, ...) -> DocumentoClinico`
  - `make_documento_item(organizacao_id, documento_id, *, medicamento, posologia, ...) -> DocumentoItem`
- **Auditoria** (`tests/factories/audit.py`):
  - `make_audit_event(organizacao_id, atendimento_id, *, tipo_evento, ator_tipo, ...) -> AuditEvent`
- **Autenticação** (`tests/factories/auth.py`):
  - `make_usuario_credencial(organizacao_id, usuario_id, *, identificador, senha_hash, ...) -> UsuarioCredencial`
  - `make_cadastrar_credencial_command(organizacao_id, usuario_id, *, identificador, senha_pura, ...) -> CadastrarCredencialCommand`
  - `persist_credencial(session, organizacao_id, usuario_id, *, identificador, senha_pura, papel, hasher) -> UsuarioCredencial`
- **Cenários Compostos** (`tests/factories/scenarios.py`):
  - `seed_clinical_scenario(session, *, org_id, org_cnpj, org_razao_social, org_nome_fantasia, paciente_nome, paciente_cpf, medico_nome, medico_cpf, medico_email, medico_papel, medico_crm, medico_crm_uf, status_atendimento, prioridade_clinica, tcle_hash) -> ClinicalScenario`
  - `seed_multi_tenant_orgs(session) -> tuple[Organizacao, Organizacao]`

### Dublês Canônicos (`tests/doubles.py`)

- `FakeAsyncSession`: Dublê assíncrono de sessão SQLAlchemy para testes sem I/O real.
- `FakeResult` / `FakeAddedResult`: Dublês de retorno escalar para queries simuladas.
- `FakeValkey`: Dublê em memória de cliente Valkey com comandos de chave/valor e Pub/Sub.
- `FakePubSub`: Dublê in-memory thread-safe para canais de notificação WebSocket e SSE.

### Helpers de Teste (`tests/helpers.py`)

- `clean_database_tables()`: Executa `TRUNCATE TABLE ... CASCADE` nas tabelas de domínio.
- `clean_valkey_keys(*patterns)`: Limpa chaves do Valkey por padrão glob.
- `clean_database_and_valkey(*valkey_patterns)`: Limpeza coordenada de Postgres e Valkey.
- `auth_headers(papel, org_id, usuario_id)`: Gera cabeçalhos HTTP com JWT assinado real.
- `make_auth_service(session, **overrides)`: Monta `AuthService` com dependências dubladas.
- `make_pep_service(session, **overrides)`: Monta `PEPService` com dependências dubladas.
- `make_alocacao(valkey, db_session, **overrides)`: Monta `AlocacaoChamadaService`.
- `make_fila_service(valkey, db_session, **overrides)`: Monta `FilaService`.

## Onde no código

- Impl: `tests/conftest.py:sample_async_resource`
- Impl: `tests/conftest.py:async_client`
- Impl: `tests/factories/identity.py:make_organizacao`
- Impl: `tests/factories/queue.py:make_atendimento`
- Impl: `tests/factories/triage.py:make_triagem`
- Impl: `tests/factories/consultation.py:make_evolucao_clinica`
- Impl: `tests/factories/audit.py:make_audit_event`
- Impl: `tests/factories/auth.py:persist_credencial`
- Impl: `tests/factories/scenarios.py:seed_clinical_scenario`
- Impl: `tests/doubles.py:FakeAsyncSession`
- Impl: `tests/helpers.py:clean_database_and_valkey`

## Verificação

```bash
pytest tests/unit/test_smoke.py
rg -n "def persist_credencial" tests/factories/auth.py
rg -n "def seed_clinical_scenario" tests/factories/scenarios.py
rg -n "def sample_async_resource" tests/conftest.py
```

## Ver também

- [Documentation standards](../architecture-standards/documentation-standards.md)
- [Setup local](../../how-to/dev-environment/setup-local.md)
- [Create module endpoint](../../how-to/backend/create-module-endpoint.md)
- `docs/explanation/architecture/overview.md`
