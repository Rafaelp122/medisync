# Valkey Keys Dictionary

> Dicionário canônico de namespaces, tipos de dados, TTLs e políticas de evicção do Valkey em `src/modules/`.

## Contexto

O Valkey 8.0 atua no MediSync Express como motor de altíssima vazão e baixa latência em memória, responsável pela ordenação de filas clínicas de urgência, travas de concorrência distribuída (dual-locks), limitação de taxa deslizante (sliding-window rate limiting), revogação rápida de credenciais JWT e caching volátil de telemetria operacional. Enquanto o banco relacional PostgreSQL garante a persistência ACID e a verdade clínica definitiva com Row-Level Security (RLS), o Valkey assegura o cumprimento do requisito RNF-01 (resposta e alocação em $\le 200\text{ ms}$).

Este documento estabelece o catálogo canônico de chaves, os tipos primitivos de dados utilizados, as políticas de expiração (TTLs) e as diretrizes de particionamento multi-tenant para todos os módulos do monólito modular. Engenheiros e agentes de IA devem consultar este guia antes de introduzir novos namespaces ou alterar parâmetros de retenção em memória.

Princípios pétreos de governança de chaves:
1. **Isolamento de Tenant Obrigatório (ADR-003)**: Todas as chaves associadas a dados clínicos ou operacionais contêm obrigatoriamente `{tenant_id}` ou `{organizacao_id}` no prefixo, inviabilizando qualquer contaminação cruzada entre organizações hospitalares.
2. **Prevenção de Evicção Indevida**: A configuração de servidor deve utilizar `maxmemory-policy noeviction` ou `volatile-ttl`. Filas clínicas não possuem TTL e nunca podem ser descartadas silenciosamente por saturação de memória; a reconciliação com o PostgreSQL é exercida continuamente por sweeper assíncrono.
3. **Resiliência e Fallback Seguro**: Módulos que consomem caches ou rate-limiters devem capturar exceções transitórias de conexão, garantindo degradação suave sem interrupção de fluxos críticos de admissão ou login de plantonistas.

## Conceito

### Catálogo Canônico de Namespaces

| Padrão de Chave | Módulo | Tipo | TTL (s) | Política de Expiração / Evicção | Finalidade Operacional |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `fila:{tenant_id}:aptos` | `queue` | `ZSET` | Nenhum | Persistente (`noeviction`); remoção por `ZREM` | Fila ordenada de pacientes aptos para atendimento médico (RN01, ADR-002). Score: `(prioridade * 10^12) + timestamp`. |
| `lock:{tenant_id}:medico:{id}` | `queue` | `STRING` | 45 | Volátil (`EX 45`); expiração pelo ARQ ou atendimento | Trava de toque (ring) do médico durante chamada WebRTC de 45 segundos (ADR-002). Armazena `atendimento_id`. |
| `lock:{tenant_id}:atendimento:{id}` | `queue` | `STRING` | 45 | Volátil (`EX 45`); expiração pelo ARQ ou atendimento | Trava de chamada do atendimento durante toque de 45 segundos (ADR-002). Armazena `medico_id`. |
| `lock:{tenant_id}:consulta_ativa:medico:{id}` | `queue` | `STRING` | 7200 | Volátil (`EX 7200`); renovado por heartbeat | Trava de teleconsulta médica ativa em consultório virtual. Armazena `atendimento_id`. Liberado na finalização. |
| `plantao:{tenant_id}:medicos_ativos` | `queue` | `SET` | Nenhum | Gerenciado por escala (`SADD`/`SREM`) | Relação de identificadores de médicos plantonistas ativos na organização para cálculo de backpressure (RN05). |
| `medico:status:{tenant_id}:{id}` | `identity` | `STRING` | 43200 | Volátil (`EX 43200` - 12h do turno) | Estado de disponibilidade operacional do médico plantonista (online, ocupado, intervalo). |
| `auth:ratelimit:ip:{ip}` | `auth` | `ZSET` | 900 | Volátil (`EX 900`); janela deslizante | Janela deslizante de tentativas de autenticação por IP de origem (teto de 5 tentativas por 15 minutos). |
| `auth:ratelimit:acc:{tenant_id}:{user}` | `auth` | `ZSET` | 900 | Volátil (`EX 900`); janela deslizante | Janela deslizante de tentativas por credencial/usuário (teto de 5 tentativas por 15 minutos contra brute-force). |
| `validation:ratelimit:{chave}` | `consultation` | `ZSET` | 60 | Volátil (`EX 60`); janela deslizante | Janela deslizante de validação pública de receitas e atestados médicos (teto de 30 requisições por minuto). |
| `telemetry:painel:{tenant_id}` | `telemetry` | `STRING` | 60 | Volátil (`EX 60`); cache com auto-invalidação | Cache volátil de payload JSON com dados consolidados do dashboard (`PainelTelemetriaDTO`). |
| `queue:admissoes:{tenant_id}:{data}` | `queue` | `STRING` | 172800 | Volátil (`EX 172800` - 48h); contador numérico | Contador de admissões do dia (`YYYY-MM-DD`) via `INCR` para fiscalização de cota diária contratual (RN05). |
| `auth:revoked:{token_id}` | `auth` | `STRING` | Dinâmico | Volátil (`EX exp_restante`); máximo 3600 | Blacklist de revogação explícita de identificadores JWT (`jti`) persistidos até a expiração original do token. |
| `ratelimit:notif:{destination}` | `queue` | `HASH` | 3600 | Volátil (`EXPIRE`); token bucket atômico | Rate limiting anti-spam de notificações (WhatsApp/SMS) por telefone de paciente (E.164). Campos `tokens` e `last_refill`. |
| `doc:assinado:{documento_id}` | `consultation` | `STRING` | 86400 | Volátil (`EX 86400` - 24h) | Cache de status de conformidade da assinatura digital ICP-Brasil (PAdES) de documento clínico emitido. |
| `medisync:pubsub:queue:{atendimento_id}` | `core` | `PUBSUB` | N/A | Transitório de streaming em memória | Barramento de publicação e assinatura em tempo real para sinalizar mudanças de estado e toque ao paciente. |
| `medisync:pubsub:doctor:{medico_id}` | `core` | `PUBSUB` | N/A | Transitório de streaming em memória | Barramento Pub/Sub para sinalização e despacho de eventos operacionais ao painel do médico conectado. |

### Detalhamento Estrutural e Semântica por Família

#### 1. Filas Clínicas e Ordenação ZSET (`queue`)
- **Chave**: `fila:{tenant_id}:aptos`
- **Membro (Member)**: ID do atendimento (`atendimento_id` no formato canônico UUIDv7).
- **Pontuação (Score)**: Inteiro de 64 bits calculado por `(prioridade * 10^12) + timestamp_epoch`. Garante ordenação estrita por gravidade de Manchester (1 a 5) com desempate cronológico sub-milissegundo via ordenação lexicográfica de UUIDv7.
- **Complexidade**: $\mathcal{O}(\log N)$ para inclusão (`ZADD`) e remoção atômica (`ZREM`); $\mathcal{O}(1)$ para leitura da ponta da fila (`ZRANGE 0 0`).

#### 2. Travas Temporizadas e Ciclo de Vida de Chamada (`lock`)
- **Fase de Toque (Ring - 45s)**: Chaves emparelhadas `lock:{tenant_id}:medico:{id}` e `lock:{tenant_id}:atendimento:{id}` vinculam médico e paciente durante a janela de ring da videochamada LiveKit. Criadas atomicamente pelo script Lua (`alocar_chamada.lua`).
- **Fase de Atendimento Ativo**: Ao atender, o lock é promovido para `lock:{tenant_id}:consulta_ativa:medico:{id}` com TTL de 7200s (2 horas), garantindo que o médico permaneça protegido contra dupla alocação durante toda a teleconsulta.
- **Resolução de No-Show**: Caso o paciente não atenda dentro dos 45s, a tarefa diferida ARQ (`resolver_ring_timeout_task`) desfaz os locks e devolve o médico ao estado disponível.

#### 3. Proteção e Rate Limiting Deslizante e Token Bucket (`auth`, `consultation` e `queue`)
- **Janela Deslizante (`auth` e `consultation`)**: Sorted Sets onde cada membro possui formato `{timestamp}:{uuid7}` e score igual ao timestamp Unix da tentativa. Executado em pipeline com `ZREMRANGEBYSCORE` para expurgar registros fora da janela e `ZCARD` para comparar o total acumulado contra o limite estabelecido. Em caso de esgotamento, calcula o tempo remanescente inspecionando o elemento mais antigo via `ZRANGE 0 0 WITHSCORES`.
- **Token Bucket Atômico de Notificações (`queue`)**: Chave HASH `ratelimit:notif:{destination}` avaliada via script Lua atômico com campos `tokens` e `last_refill`, TTL renovado via `EXPIRE`. Contém rajadas e mitiga custos de envio de SMS/WhatsApp sem contenção entre pacientes distintos.

#### 4. Métricas e Caches Voláteis (`telemetry` e `consultation`)
- Payloads JSON com expiração estrita (60s a 86400s). Evitam queries analíticas repetitivas no PostgreSQL, com auto-invalidação imediata quando ocorrem mutações clínicas relevantes.

#### 5. Conexão, Pool e Limites Operacionais
- O pool assíncrono é instanciado em `src/core/valkey.py` com limite máximo configurado via variável `VALKEY_MAX_CONNECTIONS` (padrão: 50 conexões concorrentes).
- Testes de integridade de conectividade e telemetria de nó são providos via `check_valkey_health` integrado ao endpoint `/healthz`.

## Onde no código

- Impl: `src/modules/queue/application/services/alocacao_service.py:AlocacaoChamadaService`
- Impl: `src/modules/queue/application/services/fila_service.py:FilaService`
- Impl: `src/modules/queue/application/services/controle_admissao_service.py:ControleAdmissaoService`
- Impl: `src/modules/queue/infrastructure/notifications/rate_limiter.py:NotificationRateLimiter`
- Impl: `src/modules/queue/composition.py:get_notification_adapter`
- Impl: `src/modules/auth/infrastructure/valkey_rate_limiter.py:ValkeyAuthRateLimiter`
- Impl: `src/modules/telemetry/infrastructure/valkey_telemetry_cache.py:ValkeyTelemetryCache`
- Impl: `src/modules/consultation/infrastructure/valkey_signed_cache.py:ValkeySignedCache`
- Impl: `src/modules/consultation/infrastructure/valkey_validation_rate_limiter.py:ValkeyValidationRateLimiter`
- Impl: `src/core/authz/revocation.py:token_revocation_key`
- Impl: `src/core/realtime.py:queue_channel`
- Spec: `docs/adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md`
- Prova viva: `tests/integration/test_valkey_pool.py:test_valkey_client_dependency_crud`
- Prova viva: `tests/integration/test_valkey_rate_limiter.py`
- Prova viva: `tests/unit/test_valkey_config.py`
- Prova viva: `tests/unit/test_composition_wiring.py:test_queue_notification_adapter_resolution_with_rate_limiter`
- Prova viva: `tests/unit/test_notifications.py:test_in_memory_rate_limiter_burst_and_rejection`
- Ver: `rg -n "fila:" src/modules/queue/application/services/`
- Ver: `rg -n "lock:" src/modules/queue/application/services/`
- Ver: `rg -n "auth:ratelimit" src/modules/auth/infrastructure/`

## Verificação

```bash
uv run pytest tests/integration/test_lua_scripts.py tests/integration/test_valkey_pool.py
```

## Ver também

- [Lua Scripts](lua-scripts.md)
- [ADR-002: Alocação Atômica Valkey Lua](../../adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md)
- [ADR-004: Worker Assíncrono ARQ](../../adrs/ADR-004-Worker-Assincrono-ARQ-sobre-Valkey.md)
- [Concurrency and Queues](../../explanation/architecture/concurrency-and-queues.md)
- [Queue Lua ARQ](../../explanation/concepts/queue-lua-arq.md)
- [Environment Variables](../environment/variables.md)
- [Documentation Standards](../architecture-standards/documentation-standards.md)
