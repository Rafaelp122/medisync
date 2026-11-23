# Inter-Module Protocols

Módulos conversam por protocolos abstratos, nunca por import
direto de modelo alheio. Cada módulo declara seus ports em
`application/ports`, consome via service do próprio módulo e
recebe adaptador concreto via `composition.py`.
Regra de ouro: dependência aponta para protocolo próprio;
fiação concreta mora na borda.

## 1. Contexto

MediSync divide o sistema em módulos fechados em
`src/modules`. Comunicação síncrona entre módulos usa
portas abstratas no estilo `typing.Protocol` e objetos
imutáveis de transferência. Nenhum service importa
repositório, tabela ou modelo de outro módulo.

O padrão aparece nos ports de fila, cobrança, consulta e
triagem. Cada port tem dono único. Consumidor injeta o
protocolo no construtor e recebe a implementação na
composição ou no worker. Troca de adaptador não toca no
service.

Decisão base em
`docs/adrs/ADR-001-Hexagonal-Pragmatico-Modelos-Ricos-Protocols-e-Tach.md`
e padrão hexagonal em
`docs/explanation/concepts/hexagonal-pragmatico.md`.

## 2. Catálogo de ports por dono

Só ports que existem em disco. Dono é o módulo que
declara o arquivo. Consumidor é quem importa o símbolo,
confirmado via busca de imports no código.

| Port | Dono | Consumidor |
| --- | --- | --- |
| `src/modules/queue/application/ports/queue_engine_port.py` | queue | `src/modules/queue/application/services/fila_service.py`, `src/modules/queue/application/services/alocacao_service.py`, `src/modules/queue/application/services/controle_admissao_service.py`, `src/modules/queue/infrastructure/valkey_queue_engine.py`, `src/modules/queue/composition.py`, `src/modules/consultation/composition.py` |
| `src/modules/queue/application/ports/shift_policy_reader_port.py` | queue | `src/modules/queue/application/services/fila_service.py`, `src/modules/queue/composition.py` |
| `src/modules/queue/application/ports/queue_store_port.py` | queue | `src/modules/queue/composition.py`, `src/modules/consultation/composition.py`, `src/modules/scheduling/composition.py` |
| `src/modules/queue/application/ports/notification_port.py` | queue | `src/modules/queue/application/services/alocacao_service.py`, `src/modules/queue/composition.py` |
| `src/modules/queue/application/ports/paciente_ausente_notifier.py` | queue | `src/modules/queue/application/services/fila_service.py`, `src/worker/tasks/ring_timeout.py` |
| `src/modules/queue/application/ports/triage_port.py` | queue | `src/modules/queue/application/services/fila_service.py`, `src/modules/queue/composition.py` |
| `src/modules/auth/application/ports/doctor_presence_port.py` | auth | `src/modules/auth/application/services/auth_service.py`, `src/modules/auth/composition.py` |
| `src/modules/ambulatory/application/ports/eligibility_provider.py` | ambulatory | `src/modules/ambulatory/application/services/eligibility_service.py`, `src/modules/ambulatory/composition.py` |
| `src/modules/ambulatory/application/ports/eligibility_notifier.py` | ambulatory | `src/modules/ambulatory/application/services/eligibility_service.py`, `src/modules/ambulatory/composition.py` |
| `src/modules/consultation/application/ports/atendimento_reader_port.py` | consultation | `src/modules/consultation/application/services/pep_service.py`, `src/modules/consultation/application/services/documento_service.py`, `src/modules/consultation/application/policies/clinical_access_policy.py`, `src/modules/consultation/composition.py`, `src/modules/consultation/infrastructure/atendimento_reader_sql.py` |
| `src/modules/consultation/application/ports/producao_ambulatorial_port.py` | consultation | `src/modules/consultation/application/services/pep_service.py`, `src/modules/consultation/composition.py` |
| `src/modules/consultation/application/ports/signed_cache_port.py` | consultation | `src/modules/consultation/application/services/documento_service.py`, `src/modules/consultation/application/services/document_validation_service.py`, `src/modules/consultation/composition.py` |
| `src/modules/consultation/application/ports/pdf_generator_port.py` | consultation | `src/modules/consultation/application/services/clinical_pdf_compiler.py`, `src/modules/consultation/application/services/documento_service.py`, `src/modules/consultation/composition.py`, `src/modules/consultation/infrastructure/pdf_generator.py` |
| `src/modules/consultation/application/ports/document_directory_port.py` | consultation | `src/modules/consultation/application/services/clinical_pdf_compiler.py`, `src/modules/consultation/application/services/document_validation_service.py`, `src/modules/consultation/composition.py`, `src/modules/consultation/infrastructure/document_directory_sql.py` |
| `src/modules/consultation/application/ports/icp_brasil_signer_port.py` | consultation | `src/modules/consultation/application/services/documento_service.py`, `src/modules/consultation/composition.py`, `src/modules/consultation/infrastructure/pyhanko_signer.py`, `src/modules/consultation/presentation/routers/consultation_router.py` |
| `src/modules/consultation/application/ports/livekit_media_port.py` | consultation | `src/modules/consultation/composition.py`, `src/modules/consultation/application/services/teleconsulta_service.py` |
| `src/modules/consultation/application/ports/storage_port.py` | consultation | `src/modules/consultation/application/services/clinical_pdf_compiler.py`, `src/modules/consultation/application/services/documento_service.py`, `src/modules/consultation/application/services/document_validation_service.py`, `src/modules/consultation/composition.py`, `src/modules/consultation/infrastructure/s3_storage.py` |
| `src/modules/consultation/application/ports/validation_rate_limiter_port.py` | consultation | `src/modules/consultation/presentation/dependencies.py`, `src/modules/consultation/composition.py`, `src/modules/consultation/infrastructure/valkey_validation_rate_limiter.py` |
| `src/modules/triage/application/ports/emergency_notifier.py` | triage | `src/modules/triage/application/services/triage_service.py`, `src/modules/triage/composition.py`, `src/modules/triage/infrastructure/adapters/samu_emergency_notifier_adapter.py` |
| `src/modules/auth/application/ports/auth_rate_limiter_port.py` | auth | `src/modules/auth/application/services/auth_service.py`, `src/modules/auth/composition.py`, `src/modules/auth/infrastructure/valkey_rate_limiter.py` |
| `src/modules/auth/application/ports/password_hasher_port.py` | auth | `src/modules/auth/application/services/auth_service.py`, `src/modules/auth/composition.py`, `src/modules/auth/infrastructure/argon2_hasher.py` |
| `src/modules/auth/application/ports/token_service_port.py` | auth | `src/modules/auth/application/services/auth_service.py`, `src/modules/auth/composition.py`, `src/modules/auth/infrastructure/jwt_token_service.py` |

*(Nota: os antigos seams hipotéticos `LuaScriptPort`, `QueueOverflowNotifierPort`, `DoctorCallNotifierPort` e `TriageQueixaReaderPort` foram removidos e consolidados respectivamente em `QueueEnginePort` e `TriagePort`; `src/modules/queue/application/ports/allocation_port.py` define apenas o enum tipado `AlocacaoCodigo`.)*

## 3. Services consomem ports do próprio módulo

Busca em services mostra o padrão sem exceção: cada
service importa ports do próprio módulo, nunca de outro.
Comando de prova:

`rg -n "ports\." src/modules/queue/application/services/alocacao_service.py`

Retorna import de `queue_engine_port`, `allocation_port` (`AlocacaoCodigo`) e `notification_port`
dentro da fila. Mesmo vale para consulta, triagem e auth:

- `src/modules/queue/application/services/alocacao_service.py` consome `queue_engine_port` e `notification_port`.
- `src/modules/queue/application/services/fila_service.py` consome `queue_engine_port`, `shift_policy_reader_port`, `paciente_ausente_notifier` e `triage_port` (seam único de risco, persistência 1:1 e leitura de queixas).
- `src/modules/queue/application/services/controle_admissao_service.py` consome `queue_engine_port`.
- `src/modules/consultation/application/services/pep_service.py` consome `atendimento_reader_port` e `producao_ambulatorial_port`.
- `src/modules/consultation/application/services/clinical_pdf_compiler.py` consome `document_directory_port`, `pdf_generator_port` e `storage_port`.
- `src/modules/consultation/application/services/documento_service.py` consome `atendimento_reader_port`, `document_directory_port`, `icp_brasil_signer_port`, `pdf_generator_port`, `signed_cache_port` e `storage_port`.
- `src/modules/consultation/application/services/document_validation_service.py` consome `document_directory_port`, `signed_cache_port` e `storage_port`.
- `src/modules/ambulatory/application/services/eligibility_service.py` consome `eligibility_provider` e `eligibility_notifier` do próprio ambulatory.
- `src/modules/triage/application/services/triage_service.py` consome `emergency_notifier` do próprio triage.
- `src/modules/auth/application/services/auth_service.py` consome `auth_rate_limiter_port`, `doctor_presence_port`, `password_hasher_port` e `token_service_port`.

## 4. Regra de ouro

Nunca importar modelos, tabelas ou repositórios de outro
módulo. Erros de domínio viajam em tipos de
`src/core/errors.py`, nunca como exceção http dentro do
service. Fronteira entre módulos é protocolo mais objeto
imutável, nunca classe concreta alheia.

Na prática isso significa três proibições:

- service de fila não importa modelo de cobrança.
- service de consulta não importa modelo de fila; lê
  atendimento via `atendimento_reader_port`.
- worker cruza módulos por ports e domínio explícito,
  nunca por import escondido de service alheio.

Quem precisa de dado de outro contexto declara um reader
ou notifier no próprio módulo e deixa o adaptador
resolver fora do domínio.

## 5. Composition como wiring

Só a raiz de composição pode importar adaptadores de
infraestrutura. Routers e tasks pedem deps prontas, nunca
instanciam service com construtor direto. Cada módulo expõe seu `composition.py`:

- `src/modules/queue/composition.py` fia `ValkeyQueueEngine`, `ShiftPolicyReaderPort` (`TelemetryShiftPolicyReaderAdapter`), `TriagePort`, notificador e `build_doctor_presence_engine`.
- `src/modules/consultation/composition.py` fia documento, pep, validação, leitor de atendimento, mídia LiveKit, armazenamento e `DoctorPresenceDep`.
- `src/modules/auth/composition.py` fia hash, token, rate limit, presença médica (`DoctorPresencePort` $\to$ `build_doctor_presence_engine`) e lookup de atendimento ativo.
- `src/modules/identity/composition.py` expõe readers/writers de onboarding, pacientes e dependentes.
- `src/modules/triage/composition.py` fia triagem e notificador de emergência SAMU.
- `src/modules/telemetry/composition.py` fia telemetria, políticas de plantão e `ler_politica_plantao_snapshot`.
- `src/modules/ambulatory/composition.py` fia produção ambulatorial SUS (`ProducaoAmbulatorialService`) e qualificação cadastral.
- `src/modules/scheduling/composition.py` fia agenda eMulti e `AttendanceLookupPort` sobre `QueueStorePort`.

## 6. Grafo confirmado por busca

Grafo abaixo contém só arestas service para port do
próprio módulo, exatamente as retornadas pela busca em
services. Sem aresta inventada entre módulos.

```mermaid
flowchart LR
    alocacao_service --> queue_engine_port
    alocacao_service --> notification_port
    fila_service --> queue_engine_port
    fila_service --> shift_policy_reader_port
    fila_service --> triage_port
    fila_service --> paciente_ausente_notifier
    controle_admissao_service --> queue_engine_port
    documento_service --> icp_brasil_signer_port
    clinical_pdf_compiler --> document_directory_port
    clinical_pdf_compiler --> pdf_generator_port
    clinical_pdf_compiler --> storage_port
    documento_service --> atendimento_reader_port
    documento_service --> icp_brasil_signer_port
    documento_service --> signed_cache_port
    documento_service --> storage_port
    document_validation_service --> document_directory_port
    document_validation_service --> signed_cache_port
    document_validation_service --> storage_port
    pep_service --> atendimento_reader_port
    pep_service --> producao_ambulatorial_port
    eligibility_service --> eligibility_provider
    eligibility_service --> eligibility_notifier
    auth_service --> auth_rate_limiter_port
    auth_service --> doctor_presence_port
    auth_service --> password_hasher_port
    auth_service --> token_service_port
    triage_service --> emergency_notifier
```

Cruzamento entre módulos acontece fora de services, em
pontos permitidos: `composition.py` conecta adaptadores externos e
`src/worker/tasks/ring_timeout.py` / `src/worker/tasks/sweeper.py`
consomem fábricas de `queue.composition` e ports de `queue`. Isso mantém
o grafo de application acíclico e auditável pelo guarda de fronteiras.

## 7. Limites verificados por máquina

Fronteira não é acordo verbal. Dois guardas travam
regressão e um comando prova o grafo:

- `tach.toml` declara que cada `application` depende só
  de `core` mais domínio próprio; `worker` puxa `core`,
  `queue` e `identity` (sem dependência de `ambulatory`).
  Comando `just tach` valida o grafo.

  Definição do comando em `justfile`.
- `tests/architecture/test_routers_are_thin.py` varre
  routers e falha em import proibido ou instanciação
  direta de service.
- Prova de consumo via busca tipada, por exemplo buscar
  `EmergencyNotifierPort` em
  `src/modules/triage/application/services/triage_service.py`
  ou `QueueEnginePort` em
  `src/modules/queue/application/services/alocacao_service.py`.

## 8. Referências

- Decisão hexagonal:
  `docs/adrs/ADR-001-Hexagonal-Pragmatico-Modelos-Ricos-Protocols-e-Tach.md`
- Conceito base:
  `docs/explanation/concepts/hexagonal-pragmatico.md`
- Fronteiras: `tach.toml` mais `justfile`
- Guarda de routers:
  `tests/architecture/test_routers_are_thin.py`
- Erros de domínio: `src/core/errors.py`
- Fiação queue: `src/modules/queue/composition.py`
- Fiação consultation: `src/modules/consultation/composition.py`
- Fiação auth: `src/modules/auth/composition.py`
- Fiação identity: `src/modules/identity/composition.py`
- Fiação triage: `src/modules/triage/composition.py`
- Fiação telemetry: `src/modules/telemetry/composition.py`
- Consumo em worker:
  `src/worker/tasks/sweeper.py` e
  `src/worker/tasks/ring_timeout.py`
- Infra de leitura, fila e mídia:
  `src/modules/queue/infrastructure/valkey_queue_engine.py`,
  `src/modules/consultation/infrastructure/atendimento_reader_sql.py`,
  `src/modules/consultation/infrastructure/s3_storage.py`,
  `src/modules/consultation/infrastructure/livekit_adapter.py` e
  `src/modules/queue/infrastructure/lua_loader.py`
