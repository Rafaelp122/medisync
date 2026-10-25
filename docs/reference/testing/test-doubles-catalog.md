# Catálogo de Dublês de Teste (Fakes Canônicos)

> Catálogo técnico de dublês em memória e Fakes canônicos utilizados na suíte de testes unitários do MediSync Express.

## Contexto

A suíte de testes unitários do MediSync Express opera sob o princípio de feedback ultrarrápido sem dependência de containers (`just test-fast`), executando mais de 600 testes em poucos segundos.
Em alinhamento com o Clean Code para Agentes de IA (AGENTS.md) e a arquitetura Hexagonal Pragmática (ADR-001), o projeto adota **Fakes Nomeados sobre Mocks Inline Anônimos**.
Em vez de instâncias genéricas de `unittest.mock.MagicMock` ou `patch()`, o repositório emprega dublês de teste tipados que implementam fielmente as portas abstratas (`typing.Protocol`) do sistema.
Essa abordagem assegura checagem de tipos estrita (`basedpyright` em modo estrito), refatorações seguras de contratos e diagnóstico imediato de asserções via estado rastreável.
Os dublês residem principalmente em `tests/doubles.py`, com implementações em memória específicas de infraestrutura mantidas nos próprios módulos (como `src/modules/auth/infrastructure/valkey_token_revocation.py`).

## Conceito

Os dublês canônicos comportam-se como simuladores funcionais em memória com zero dependência de I/O de rede ou disco, expondo propriedades explícitas para verificação em asserções de teste.

### Catálogo de Fakes Canônicos

| Dublê Fake | Porta / Contrato Implementado | Métodos Principais | Helpers de Asserção & Estado |
|---|---|---|---|
| `FakeAsyncSession` | `sqlalchemy.ext.asyncio.AsyncSession` | `execute()`, `add()`, `add_all()`, `flush()`, `commit()`, `refresh()`, `begin_nested()` | `commits: int`, `executes: int`, `added: list[Any]`, `_results: list[Any]` (respostas FIFO de `FakeResult`). |
| `FakeResult` / `FakeAddedResult` | `sqlalchemy.engine.Result` | `scalar_one_or_none()`, `scalar_one()`, `mappings()` | Retorna valores escalares pré-programados ou simula recarga da entidade recém-adicionada na sessão. |
| `FakePDFGenerator` | `PDFGeneratorPort` (`src.modules.consultation`) | `gerar_pdf(payload)` | `calls: int`, `payloads: list[Any]` (inspeção de payloads clínicos), `content: bytes` (payload PDF configurado). |
| `FakeICPBrasilSigner` | `ICPBrasilSignerPort` (`src.modules.consultation`) | `assinar_pdf(pdf_bytes, credenciais, metadata)` | `calls: list[tuple]` (histórico de invocações com bytes e credenciais), `signed_suffix: bytes`. |
| `FakeMemoryStorage` | `StoragePort` (`src.modules.consultation`) | `salvar_documento()`, `obter_documento()`, `gerar_url_pre_assinada()` | `contains(chave) -> bool`, `clear()`, dicionário `_storage: dict[str, bytes]`. Lança erro se chave ausente. |
| `FakeArqPool` / `FakeArqJob` | `arq.connections.ArqRedis` | `enqueue_job(function_name, *args, **kwargs)` | `enqueued_jobs: list[dict]` (registros de jobs enfileirados com args e kwargs), `default_job_id: str`. |
| `FakeEligibilityProvider` | `EligibilityProviderPort` (`src.modules.billing`) | `verificar_elegibilidade(requisicao)` | `requisicoes: list[Any]` (histórico de requisições enviadas), `resultado: ResultadoElegibilidade`. |
| `FakeElegibilidadeNotifier` | `ElegibilidadeNotifierPort` (`src.modules.billing`) | `notificar_falha(evento)` | `eventos_falha: list[ElegibilidadeFalhaEvent]` (histórico ordenado de alertas de recusa/timeout emitidos). |
| `MemoryTokenRevocation` | `TokenRevocationPort` (`src.modules.auth`) | `revogar(jti, exp_segundos)`, `is_revogado(jti)` | `_revoked: set[str]` (conjunto em memória de identificadores JWT invalidados). |
| `FakeAtendimentoReader` | `AtendimentoReaderPort` (`src.modules.consultation`) | `obter_resumo()`, `concluir_atendimento()`, `atender_chamada()` | `resumo: AtendimentoResumoDTO | None`, `chamada_atendida: bool`, `atendimento_concluido: bool`. |
| `FakeValkey` / `FakePubSub` | Protocolo Valkey / Redis Pub/Sub | `publish(canal, msg)`, `pubsub()`, `subscribe()`, `listen()` | Filas thread-safe `queue.Queue` em memória para testes de WebSockets e SSE sem infraestrutura externa. |

### Detalhamento dos Dublês e Mecânica de Estado

1. **`FakeAsyncSession` (`tests/doubles.py`)**:
   - Simula o comportamento assíncrono do SQLAlchemy 2.0 sem tocar no PostgreSQL.
   - Cada chamada a `add(entity)` registra o objeto na lista `.added`.
   - Cada chamada a `commit()` incrementa o contador `.commits`.
   - O método `begin_nested()` implementa um context manager assíncrono idempotente para compatibilidade com savepoints.

2. **`FakePDFGenerator` (`tests/doubles.py`)**:
   - Implementa a interface síncrona `PDFGeneratorPort`.
   - Registra cada invocação incrementando `.calls` e anexando o `DocumentoPDFPayload` em `.payloads`.
   - Permite asserções profundas sobre os dados formatados do paciente, médico e itens de prescrição sem parsing binário.

3. **`FakeICPBrasilSigner` (`tests/doubles.py`)**:
   - Implementa `ICPBrasilSignerPort` simulando assinatura digital PAdES com certificado ICP-Brasil em nuvem (PSC).
   - Registra tuplas `(pdf_bytes, credenciais, metadata)` em `.calls` e apõe `.signed_suffix` ao binário final.

4. **`FakeMemoryStorage` (`tests/doubles.py`)**:
   - Implementa `StoragePort` com dicionário chave-valor interno `_storage`.
   - Emula links assinados via `https://mock-storage.local/{chave}?expires={segundos}`.
   - Lança `DocumentoNaoEncontradoNoStorageError` para chaves inexistentes.

5. **`FakeArqPool` e `FakeArqJob` (`tests/doubles.py`)**:
   - Emula a fila assíncrona ARQ sobre Valkey.
   - Cada chamada a `enqueue_job()` armazena o nome da função e parâmetros em `.enqueued_jobs` e retorna um `FakeArqJob` com `job_id`.

6. **`FakeEligibilityProvider` e `FakeElegibilidadeNotifier` (`tests/doubles.py`)**:
   - Dublam a verificação de convênios SUS/Privado e a mensageria de alertas na sala de espera.
   - Capturam o tráfego de requisições e falhas para validação de regras de tolerância a falhas (RF-02, RF-05, RT-01).

7. **`MemoryTokenRevocation` (`src/modules/auth/infrastructure/valkey_token_revocation.py`)**:
   - Implementa `TokenRevocationPort` com `set[str]` para controle de tokens revogados (logout / blacklisting).

## Onde no código

- Impl: `tests/doubles.py:FakeAsyncSession`
- Impl: `tests/doubles.py:FakePDFGenerator`
- Impl: `tests/doubles.py:FakeICPBrasilSigner`
- Impl: `tests/doubles.py:FakeMemoryStorage`
- Impl: `tests/doubles.py:FakeArqPool`
- Impl: `tests/doubles.py:FakeEligibilityProvider`
- Impl: `tests/doubles.py:FakeElegibilidadeNotifier`
- Impl: `tests/doubles.py:FakeAtendimentoReader`
- Impl: `src/modules/auth/infrastructure/valkey_token_revocation.py:MemoryTokenRevocation`
- Spec: `src/modules/consultation/application/ports/pdf_generator_port.py:PDFGeneratorPort`
- Spec: `src/modules/consultation/application/ports/icp_brasil_signer_port.py:ICPBrasilSignerPort`
- Spec: `src/modules/consultation/application/ports/storage_port.py:StoragePort`
- Spec: `src/modules/consultation/application/ports/atendimento_reader_port.py:AtendimentoReaderPort`
- Spec: `src/modules/billing/application/ports/eligibility_provider.py:EligibilityProviderPort`
- Spec: `src/modules/billing/application/ports/eligibility_notifier.py:ElegibilidadeNotifierPort`
- Spec: `src/modules/auth/application/ports/token_revocation_port.py:TokenRevocationPort`
- Prova viva: `tests/unit/test_factories.py:test_seed_clinical_scenario_with_fake_session`
- Prova viva: `tests/unit/test_pyhanko_signer.py:test_fake_icp_brasil_signer_success`
- Prova viva: `tests/unit/test_billing_eligibility.py:test_elegibilidade_service_emits_failure_event_on_rejection`
- Prova viva: `tests/unit/test_token_revocation.py:test_memory_token_revocation`
- Prova viva: `tests/unit/test_documento_service.py:test_emitir_gera_chave_canonica_sem_legado`
- Prova viva: `tests/unit/test_livekit_dependencies.py:test_validar_acesso_livekit_paciente_ausente_retorna_conflict_error`
- Ver: `uv run pytest tests/unit/ -k "fake" --no-cov`
- Ver: `rg -n "class Fake" tests/doubles.py`

## Verificação

```bash
uv run pytest tests/unit/ -k "fake" --no-cov
uv run pytest tests/unit/test_token_revocation.py -v
rg -n "class Fake" tests/doubles.py
```

Saída esperada: 14 testes selecionados executados com sucesso em menos de 3 segundos, comprovando isolamento total em memória.

## Ver também

- [Fixtures, fábricas e dublês](fixtures-and-factories.md)
- [Matriz de fronteiras modulares Tach](../architecture-standards/tach-boundaries-matrix.md)
- [Documentation standards](../architecture-standards/documentation-standards.md)
- [Run tests](../../how-to/backend/run-tests.md)
- [Write tests](../../how-to/backend/write-tests.md)
- [Testing strategy](../../explanation/architecture/testing-strategy.md)
