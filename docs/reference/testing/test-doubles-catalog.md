# Catálogo de Dublês de Teste (Fakes Canônicos)

> Catálogo técnico de dublês em memória e Fakes canônicos utilizados na suíte de testes unitários do MediSync Express.

## Contexto

A suíte de testes unitários do MediSync Express opera sob o princípio de feedback ultrarrápido sem dependência de containers (`just test-fast`), executando mais de 600 testes em poucos segundos.
Em alinhamento com o Clean Code para Agentes de IA (AGENTS.md) e a arquitetura Hexagonal Pragmática (ADR-001), o projeto adota **Fakes Nomeados sobre Mocks Inline Anônimos**.
Em vez de instâncias genéricas de `unittest.mock.MagicMock` ou `patch()`, o repositório emprega dublês de teste tipados que implementam fielmente as portas abstratas (`typing.Protocol`) do sistema.
Essa abordagem assegura checagem de tipos estrita (`basedpyright` em modo estrito), refatorações seguras de contratos e diagnóstico imediato de asserções via estado rastreável.
Os dublês residem principalmente em `tests/doubles.py`, com implementações em memória específicas de infraestrutura mantidas nos próprios módulos ou no núcleo de autorização (como `src/core/authz/revocation.py`).

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
| `FakeEligibilityProvider` | `EligibilityProviderPort` (`src.modules.ambulatory`) | `verificar_elegibilidade(requisicao)` | `requisicoes: list[Any]` (histórico de requisições enviadas), `resultado: ResultadoElegibilidade`. |
| `FakeElegibilidadeNotifier` | `ElegibilidadeNotifierPort` (`src.modules.ambulatory`) | `notificar_falha(evento)` | `eventos_falha: list[ElegibilidadeFalhaEvent]` (histórico ordenado de alertas de recusa/timeout emitidos). |

| `MemoryTokenRevocation` | `TokenRevocationPort` (`src.core.authz`) | `revogar(jti, exp_segundos)`, `marcar_revogado_se_nao_revogado(jti)`, `is_revogado(jti)` | `_revoked: set[str]` (conjunto em memória de identificadores JWT invalidados com `SET NX` lógico). |
| `MemoryChallengeStore` | `ChallengeStorePort` (`src.modules.auth`) | `store_one_time()`, `consume_one_time()`, `verify_and_increment_otp()` | `entries: dict[str, tuple[str, float]]` com expiração monotônica, `consume_calls: list[str]` e `clear()`. |
| `FakeIdentityReader` | `IdentityReaderPort` (`src.modules.identity`) | `obter_dados_diretorio()`, `buscar_paciente_cadsus()`, `buscar_passkey_por_credencial()` | Somente leitura CQRS (`lookups`, `passkeys`); bloqueia consultas CADSUS sem CPF/CNS ou ambíguas. |
| `FakeIdentityWriter` | `IdentityWriterPort` (`src.modules.identity`) | `criar_paciente()`, `registrar_passkey_paciente()`, `atualizar_sign_count_passkey()` | Persiste pacientes e mutações de passkeys no `FakeIdentityReader` compartilhado sem commit. |
| `FakeSmsSenderAdapter` | `SmsSenderPort` (`src.modules.auth`) | `enviar_otp(telefone, codigo)`, `clear()` | `sent_otps: list[dict]` residente em `src/modules/auth/infrastructure/fake_sms_adapter.py` (removido de `identity`). |
| `FakeAtendimentoReader` | `AtendimentoReaderPort` (`src.modules.consultation`) | `obter_resumo()`, `concluir_atendimento(..., auto_commit=True)`, `liberar_consulta_ativa_medico()`, `atender_chamada()` | `resumo`, `chamada_atendida`, `atendimento_concluido`, `last_auto_commit: bool \| None`, `liberados_consulta: list[UUID]`. |
| `FakeEmergencyNotifier` | `EmergencyNotifierPort` (`src.modules.triage`) | `notificar_emergencia_samu(alert)`, `clear()` | `sent_alerts: list[EmergencyAlertDTO]`, `error: Exception \| None` (extraído da classe de produção `SamuEmergencyNotifierAdapter`). |
| `FakeTriagePort` | `TriagePort` (`src.modules.queue`) | `avaliar_risco()`, `registrar_triagem()`, `obter_queixas_por_atendimentos()` | `avaliacoes: list[dict]`, `triagens_registradas: list[dict]`, `queixas: dict[UUID, str \| None]`, `error_avaliar`, `error_registrar`. |
| `FakeShiftPolicyReader` | `ShiftPolicyReaderPort` (`src.modules.queue`) | `obter_politica_atual()` | `policy: ShiftPolicyDTO` configurável com `alpha_backpressure`, `cota_diaria_maxima`, `tma_padrao_segundos`, `tempo_tolerancia_ring_segundos`. |
| `FakeQueueEngine` | `QueueEnginePort` (`src.modules.queue`) | `alocar_proximo()`, `alocar_atendimento()`, `promover_para_consulta()`, `liberar_ring()`, `liberar_consulta()`, `devolver_para_fila()`, `consumir_cota_ou_bloquear()`, `estornar_cota_diaria()`, `adquirir_lock_sweeper()`, `esta_bloqueado_para_reconciliacao()`, `publicar_evento_*()` | Estado completo em memória: `fila_scores`, `locks_medico`, `locks_atendimento`, `locks_consulta_ativa`, `medicos_ativos`, `cota_diaria_usada`, `sweeper_lock_held`, `published_fila`, `published_medico`, `alocar_*_calls`, `sweeper_checks`. |
| `FakeValkey` / `FakePubSub` | Protocolo Valkey / Redis Pub/Sub | `publish(canal, msg)`, `pubsub()`, `subscribe()`, `listen()`, `zadd()`, `zrange()`, `incr()`, `decr()`, `sadd()` | Filas `queue.Queue`, `_zsets`, `_kv`, `_sets` e `FakePipeline` em memória sem infraestrutura externa. |

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

7. **`MemoryTokenRevocation` (`src/core/authz/revocation.py`)**:
   - Implementa `TokenRevocationPort` com `set[str]` para controle atômico de tokens revogados (`marcar_revogado_se_nao_revogado`, `revogar`, `is_revogado`) sem dependência de Valkey sob `TestSettings`.

8. **`MemoryChallengeStore`, `FakeIdentityReader` & `FakeIdentityWriter` (`tests/doubles.py`) e `FakeSmsSenderAdapter` (`src/modules/auth/infrastructure/fake_sms_adapter.py`)**:
   - `MemoryChallengeStore` substitui dicts ad-hoc `_memory_*` e stubs locais em testes unitários de OTP e WebAuthn (`consume_one_time` atômico e `verify_and_increment_otp`).
   - `FakeIdentityReader` (leitura CQRS) e `FakeIdentityWriter` (escrita de pacientes e passkeys) espelham a segregação `IdentityReaderPort`/`IdentityWriterPort`, enquanto `SmsSenderPort`/`FakeSmsSenderAdapter` pertencem exclusivamente ao módulo `auth`.

9. **`FakeEmergencyNotifier`, `FakeTriagePort`, `FakeShiftPolicyReader` & `FakeQueueEngine` (`tests/doubles.py`)**:
   - `FakeEmergencyNotifier` mantém o buffer em memória `sent_alerts` exclusivamente na suíte de testes após remoção de estado de teste da classe de produção `SamuEmergencyNotifierAdapter`.
   - `FakeTriagePort` implementa o seam único `TriagePort` (incluindo `obter_queixas_por_atendimentos`), eliminando o antigo `TriageQueixaReaderPort`.
   - `FakeShiftPolicyReader` fornece snapshots `ShiftPolicyDTO` para testar backpressure e estimativa de espera sem banco relacional.
   - `FakeQueueEngine` simula integralmente o contrato `QueueEnginePort` (ZSET ordenado, locks 4-Keys com `locks_consulta_ativa`, presença médica, cota atômica, lock do sweeper e Pub/Sub), substituindo mocks inline de `Redis` e dos antigos seams removidos.

## Onde no código

- Impl: `tests/doubles.py:FakeAsyncSession`
- Impl: `tests/doubles.py:FakePDFGenerator`
- Impl: `tests/doubles.py:FakeICPBrasilSigner`
- Impl: `tests/doubles.py:FakeMemoryStorage`
- Impl: `tests/doubles.py:FakeArqPool`
- Impl: `tests/doubles.py:FakeEligibilityProvider`
- Impl: `tests/doubles.py:FakeElegibilidadeNotifier`
- Impl: `tests/doubles.py:FakeAtendimentoReader`
- Impl: `tests/doubles.py:FakeEmergencyNotifier`
- Impl: `tests/doubles.py:FakeTriagePort`
- Impl: `tests/doubles.py:FakeShiftPolicyReader`
- Impl: `tests/doubles.py:FakeQueueEngine`
- Impl: `tests/doubles.py:MemoryChallengeStore`
- Impl: `tests/doubles.py:FakeIdentityReader`
- Impl: `tests/doubles.py:FakeIdentityWriter`
- Impl: `src/core/authz/revocation.py:MemoryTokenRevocation`
- Impl: `src/modules/auth/infrastructure/fake_sms_adapter.py:FakeSmsSenderAdapter`
- Spec: `src/modules/auth/application/ports/challenge_store_port.py:ChallengeStorePort`
- Spec: `src/modules/auth/application/ports/sms_sender_port.py:SmsSenderPort`
- Spec: `src/modules/identity/application/ports/identity_reader_port.py:IdentityReaderPort`
- Spec: `src/modules/identity/application/ports/identity_writer_port.py:IdentityWriterPort`
- Spec: `src/modules/queue/application/ports/queue_engine_port.py:QueueEnginePort`
- Spec: `src/modules/queue/application/ports/shift_policy_reader_port.py:ShiftPolicyReaderPort`
- Spec: `src/modules/queue/application/ports/triage_port.py:TriagePort`
- Spec: `src/modules/triage/application/ports/emergency_notifier.py:EmergencyNotifierPort`
- Spec: `src/modules/consultation/application/ports/pdf_generator_port.py:PDFGeneratorPort`
- Spec: `src/modules/consultation/application/ports/icp_brasil_signer_port.py:ICPBrasilSignerPort`
- Spec: `src/modules/consultation/application/ports/storage_port.py:StoragePort`
- Spec: `src/modules/consultation/application/ports/atendimento_reader_port.py:AtendimentoReaderPort`
- Spec: `src/modules/ambulatory/application/ports/eligibility_provider.py:EligibilityProviderPort`
- Spec: `src/modules/ambulatory/application/ports/eligibility_notifier.py:ElegibilidadeNotifierPort`
- Spec: `src/core/authz/revocation.py:TokenRevocationPort`
- Prova viva: `tests/unit/test_factories.py:test_seed_clinical_scenario_with_fake_session`
- Prova viva: `tests/unit/test_pyhanko_signer.py:test_fake_icp_brasil_signer_success`
- Prova viva: `tests/unit/test_ambulatory_production.py:test_elegibilidade_service_emits_failure_event_on_rejection`
- Prova viva: `tests/unit/test_triage_model.py:test_samu_notifier_adapter_raise_for_status_e_log_erro`
- Prova viva: `tests/unit/test_pep_service.py:test_pep_finalizar_consulta_transacao_unica_e_libera_lock_pos_commit`
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

Saída esperada: 18 testes selecionados (`-k "fake"`) executados com sucesso em memória, além dos testes dedicados em `test_token_revocation.py`, comprovando isolamento total sem I/O externo.

## Ver também

- [Fixtures, fábricas e dublês](fixtures-and-factories.md)
- [Matriz de fronteiras modulares Tach](../architecture-standards/tach-boundaries-matrix.md)
- [Documentation standards](../architecture-standards/documentation-standards.md)
- [Run tests](../../how-to/backend/run-tests.md)
- [Write tests](../../how-to/backend/write-tests.md)
- [Testing strategy](../../explanation/architecture/testing-strategy.md)
