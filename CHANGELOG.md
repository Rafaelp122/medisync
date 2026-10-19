## v0.4.1 (2026-10-19)

### Refactor

- **core**: mover nomes de canais realtime para os módulos donos

## v0.4.0 (2026-10-18)

### Feat

- **queue**: conectar rate limiter de notificações na composition

### Refactor

- **core**: mover notificações do core para o módulo queue

## v0.3.0 (2026-10-18)

### Feat

- **tooling/skills**: adicionar gerador de módulos hexagonal e triunvirato de skills de governança

### Refactor

- **core/modules**: incorporar 5 princípios de clean code para agentes de ia e fakes tipados

## v0.2.1 (2026-10-17)

### Fix

- **queue/identity/telemetry**: correções operacionais de atendimento, onboarding OTP e TTL de telemetria

## v0.2.0 (2026-10-17)

### Feat

- **routers**: agregar rotas HTTP e WS no __init__ de cada modulo
- **queue**: expor hook on_startup para preload de scripts Lua na composition
- **core**: extrair /healthz para health_router com versao configuravel
- **observability**: integrar OpenTelemetry nativo no FastAPI com correlação de traces em logs JSON
- **telemetry**: implementar módulo desacoplado de telemetria operacional e read model (RF-10 / RF-09)
- **queue**: criar routers REST alocacao_router e fila_router em conformidade com ADR-001
- **queue**: implementar logica de aplicacao para posicao, cancelamento e piora clinica
- **identity**: suportar nome_social nos schemas, DTOs, onboarding e reader
- **identity**: adicionar campo nome_social no modelo Paciente e migration CFM 1.821/2007
- **identity**: implementar autenticação passwordless com OTP e token com papel PACIENTE
- **security**: proteger emissão de token LiveKit e handshakes de WebSocket
- **auth**: migrar revogação de tokens para Valkey e inferência automática de tenant (#41)
- **ci**: configurar pipeline do github actions e dockerfile multi-stage com python 3.14
- **auth**: implementar revogacao distribuida de tokens via Valkey
- **queue**: unificar acolhimento clinico e persistencia atomica de triagem
- **consultation**: add AtendimentoReaderPort sql reader
- **consultation**: add DocumentoService with canonical keys and signed cache
- **consultation**: add SignedCachePort valkey and memory adapters
- **queue**: add domain scoring single source
- **auth**: implement OWASP authentication service, Argon2id verification, rate limiting and JWT session management (#35)
- **storage**: implement StoragePort S3/MinIO adapter and secure validation portal (#27)
- **documents**: implement ICPBrasilSignerPort and PyHanko cloud PAdES signer (#26)
- **documents**: implement ReportLab PDF/A generator with ITI verification QR Code (#25)
- **consultation**: implement PEP SOAP clinical workflow and Portaria 344/98 prescription safeguards (#24)
- **webrtc**: implement LiveKit SFU adapter and room JWT token generation (#23)
- **realtime**: implement WebSockets signaling with Valkey Pub/Sub (#22)
- **messaging**: implement decoupled NotificationPort and rate limiting with Valkey (#21)
- **billing**: implement async eligibility worker (SUS no-op & private 15s timeout) (#20)
- **worker**: implement 60s periodic self-healing sweeper for dual-write reconciliation (#19)
- **worker**: implement deterministic 45s ring timeout task (_defer_by=45) with UUIDv7 (#18)
- **worker**: setup ARQ worker runtime and asyncpg/valkey connection sharing (#17)
- **queue**: implement stochastic admission control and backpressure (alpha factor) (#16)
- **queue**: implement queue ingestion with 64-bit score and UUIDv7 sub-millisecond FIFO (#15)
- **queue**: implement atomic call allocation service with retry and 45s locks (#14)
- **valkey**: configure async client pool and Lua script loader (#13)
- **identity**: implement progressive 2-phase onboarding API and dependent management (#12)
- **security**: implement PostgreSQL Row-Level Security (RLS) on all 9 tables and immutable audit trigger (#11)
- **db**: configure async Alembic migrations with psycopg3 and initial UUIDv7 schema (#10)
- **audit**: implement AuditEvent append-only model with UUIDv7 and polymorphic actor (#9)
- **consultation**: implement EvolucaoClinica, DocumentoClinico and DocumentoItem models with UUIDv7 (#8)
- **triage**: implement Triagem clinical model with UUIDv7 and SAMU 192 emergency detection (#7)
- **queue**: implement Atendimento rich model and state machine (RN03) (#6)
- **identity**: implement Organizacao, Profissional, Paciente and Dependente models with UUIDv7 (#5)
- **core**: implement middleware pipeline and RFC 7807 problem details handler (#4)
- **core**: implement application settings, async database engine with psycopg3, contextvars and granian (#3)
- **infra**: setup docker-compose with postgres 17, valkey 8.0, livekit, minio and dependabot (#2)

### Fix

- **ci**: ativar pipeline de release semantico automatizado e commitizen
- **queue**: integrar leitura e incremento da cota diaria no Valkey (NC-QUE-01 / RN05)
- **queue**: sanear acoplamento com triagem, conectar worker de elegibilidade e ativar salvaguarda SAMU 192 (closes #52)
- **identity**: implementar prova de posse via intake token no onboarding Fase 2 e dependentes (#40)
- **security**: blindar mutações clínicas do PEP e refinar política de acesso (#39)
- **test**: segregar suítes fail-fast e padronizar testes com Padrão Ouro
- **consultation**: status from signed cache not key prefix

### Refactor

- **app**: transformar main.py em composition root enxuto
- **config**: configurações polimórficas por perfil, composition roots desacoplados e ADR-009
- harden composition roots, standardize FastAPI deps and adopt httpx2
- **architecture**: eliminar wrappers legados e purificar ports inter-modulos
- **consultation**: aprofundar PEPService e eliminar injecao dupla no router
- **auth**: centralizar autenticacao de paciente no modulo auth
- **queue**: unificar admissao e governanca da fila no FilaService
- **triage**: consolidar avaliacao de risco e simplificar interface de triagem
- **http**: auditoria, seguranca e padronizacao completa da camada FastAPI
- **consultation**: eliminar queries SQL cruas e adicionar finalizado_em no PEP
- **queue**: colapsar dual-write de fila e workers no QueueStorePort
- **identity**: implementar IdentityReaderPort com ORM e refatorar routers finos
- remove compat shims
- **consultation**: extract EvolucaoService
- **queue**: tighten allocation port typing
- **queue**: typed allocation port hiding lua codes
- **queue**: delegate score to domain single source
- **routers**: routers finos, DI via composition e Tach strict (#46)
- **identity**: remove password field from Profissional domain model
- **identity**: modularize domain models and decouple password hashing (#34)

## v0.1.0 (2026-09-13)
