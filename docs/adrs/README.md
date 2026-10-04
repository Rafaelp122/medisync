# Architecture Decision Records (ADRs)

Este diretório armazena o registro formal de **Decisões de Arquitetura (ADRs)** do MediSync Express, estruturadas sob o padrão de Michael Nygard.

---

## 1. Decisões Estruturantes Consolidadas

| ADR | Título | Status | Decisão Central |
| :--- | :--- | :--- | :--- |
| **[ADR-001](ADR-001-Hexagonal-Pragmatico-Modelos-Ricos-Protocols-e-Tach.md)** | Hexagonal Pragmático com Modelos Ricos, Protocols e Tach | Aprovado | Modelos ricos no SQLAlchemy 2.0 (zero Mapper Hell), UUIDv7 nas chaves clínicas, `typing.Protocol` para adaptadores externos e DTOs inter-módulos, Event Bus e Tach. Adendos §6 (transação: service commita) e §7 (camadas Tach + composition + router fino). |
| **[ADR-002](ADR-002-Alocacao-Atomica-Valkey-Lua.md)** | Alocação Atômica via Valkey Sorted Sets e Scripts Lua | Aprovado | ZSET com pontuação de 64 bits, desempate FIFO por UUIDv7 e script Lua com códigos de retorno discriminados (`0` vs `-1`) e locks temporizados de 45s. |
| **[ADR-003](ADR-003-Multi-Tenancy-Logico-Postgres-RLS.md)** | Multi-Tenancy Lógico com Defesa em Profundidade no PostgreSQL (RLS) | Aprovado | Coluna `organizacao_id` combinada com `ContextVar` e Row-Level Security (RLS) nativo com cobertura de 100% das tabelas multi-tenant. |
| **[ADR-004](ADR-004-Worker-Assincrono-ARQ-sobre-Valkey.md)** | Adoção do Motor de Tarefas Assíncronas ARQ sobre Valkey | Aprovado | Processamento em segundo plano 100% nativo em `asyncio` com jobs diferidos (`_defer_by=45`), compartilhando instâncias do Valkey. |
| **[ADR-005](ADR-005-Desacoplamento-de-Midia-LiveKit-SFU.md)** | Desacoplamento do Servidor de Mídia WebRTC via LiveKit SFU | Aprovado | Servidor de mídia em Go desacoplado com TURNS (porta 443); backend apenas emite tokens JWT, preservando a CPU do Python. |
| **[ADR-006](ADR-006-Assinatura-Digital-ICP-Brasil-Nuvem-PSC.md)** | Assinatura Digital ICP-Brasil em Nuvem via PSCs e PAdES | Aprovado | Assinatura PAdES-LTV em nuvem com PyHanko e integração OAuth2/PSC, dispensando tokens físicos USB e validando no portal do ITI. |
| **[ADR-007](ADR-007-Auditoria-Imutavel-Append-Only.md)** | Trilha de Auditoria Imutável Append-Only via DCL e Triggers Restritivas | Aprovado | Chaves em UUIDv7 (sem sequências de banco), blindagem de `audit_events` via `REVOKE UPDATE, DELETE` e Triggers com `RAISE EXCEPTION`. |
| **[ADR-008](ADR-008-Padronizacao-de-DTOs-e-Eliminacao-de-Mapper-Hell-na-Apresentacao.md)** | Padronização de DTOs e Eliminação de Mapper Hell na Apresentação | Aprovado | Uso de Pydantic v2 imutável em entradas 1:1, `Command` apenas com enriquecimento de contexto, `from_attributes=True` e `model_validate()` em responses (zero mappers manuais). |


---

## 2. Governança Ágil para Novas Decisões (Anti-BDUF)

1. **Decisões Sob Demanda**: Novas ADRs são criadas apenas quando a equipe se deparar com encruzilhadas técnicas reais ao longo do desenvolvimento.
2. **Critérios de Relevância**: Uma ADR deve ser criada apenas quando a decisão:
   * Impactar estruturalmente múltiplos módulos;
   * Envolver trade-offs significativos de desempenho, segurança ou manutenibilidade;
   * For de difícil reversão após implementada em código.
3. **Formato Padrão**: Título, Status, Contexto, Drivers de Decisão, Opções Consideradas, Decisão Tomada e Consequências (Positivas / Riscos Mitigados).
