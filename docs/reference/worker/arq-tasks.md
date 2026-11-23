# ARQ Background Tasks

> Catálogo e ciclo de vida de jobs assíncronos sobre Valkey; orquestração vive em `src/worker/settings.py`.

## Contexto

O pronto-atendimento virtual exige operações em segundo plano desacopladas do ciclo síncrono de requisições HTTP:
- Resolução determinística de no-show via ring timeout de exatamente 45 segundos (RN02).
- Auto-cura e reconciliação periódica de inconsistências entre a fila relacional e o ZSET em memória sob lock distribuído e paginação keyset (RN03).
- Diagnóstico contínuo de conectividade com PostgreSQL 17 e Valkey 8.0 (`ping_task`).
*(Nota: sob a ADR-012 / ADR-013, a admissão SUS ingressa diretamente como `APTO_PARA_CHAMADA`, tendo sido removida a antiga task `validar_elegibilidade_task` e o acoplamento `src.worker -> ambulatory`.)*

As tarefas executam sob o framework ARQ em corrotinas nativas do `asyncio`, compartilhando pools de conexão com o banco relacional (`SQLAlchemy`) e o Valkey. No bootstrap (`startup(ctx)`), o worker inicializa `setup_logging(...)` e `setup_telemetry()` (OTel), e os helpers `get_valkey_from_ctx` (`@asynccontextmanager` que fecha clientes criados do pool via `aclose()` mantendo clientes injetados em testes) e `create_arq_redis_settings()` (`src/core/valkey.py`) padronizam o ciclo de vida sem duplicação.

## Conceito

### Catálogo de Tarefas

O worker disponibiliza três tarefas principais registradas no `WorkerSettings`:

| Tarefa / Identificador | Módulo de Origem | Gatilho / Origem | Propósito Clínico e Operacional |
|---|---|---|---|
| `resolver_ring_timeout_task` | `src.worker.tasks.ring_timeout` | Alocação médica | Resolução de abandono (no-show) após 45s de chamada sem atendimento |
| `reconciliar_fila_orphans_task` | `src.worker.tasks.sweeper` | Agendador Cron | Reconciliação em lotes (`LIMIT 200`) de atendimentos aptos ausentes no ZSET sob lock distribuído |
| `ping_task` | `src.worker.tasks.base` | Diagnóstico / Health | Teste de conectividade cruzada entre pools Valkey e PostgreSQL |

### Parâmetros, Lock Distribuído e Paginação das Tarefas

Cada tarefa recebe o contexto assíncrono `ctx` com pools compartilhados e parâmetros estruturados:

1. **`resolver_ring_timeout_task` (`src/worker/tasks/ring_timeout.py:resolver_ring_timeout_task`)**:
   - `atendimento_id: str`: UUID do atendimento cujo tempo de ring expirou.
   - `medico_id: str`: UUID do médico que efetuou a chamada.
   - `notifier: PacienteAusenteNotifierPort | None = None`: Notificador opcional (default `LoggingPacienteAusenteNotifier`).
   - Enfileirada com adiamento de 45s (ou `tempo_tolerancia_ring_segundos` de `ConfiguracaoPlantao`) via `_defer_by=timedelta(seconds=ttl_segundos)` e deduplicada com `_job_id=f"ring_timeout:{atendimento_id}"`.
   - Ação: delega a `FilaService.resolver_ring_timeout` (com `with_for_update=True`), marcando `PACIENTE_AUSENTE` e liberando locks pós-commit se ainda `CHAMANDO_PACIENTE`, ou promovendo `lock:consulta_ativa:medico:{id}` se já `EM_ATENDIMENTO`.

2. **`reconciliar_fila_orphans_task` (`src/worker/tasks/sweeper.py:reconciliar_fila_orphans_task`)**:
   - `threshold_segundos: int = 60`: Janela temporal de corte para detecção de atendimentos órfãos na fila única `fila:aptos`.
   - **Lock Distribuído Exclusivo**: Antes de consultar o banco, adquire `lock:sweeper:fila_aptos` (`SET NX EX 55` via `ValkeyQueueEngine.adquirir_lock_sweeper(ttl_segundos=55)`), liberado garantidamente no bloco `finally` (`liberar_lock_sweeper`). Se o lock já estiver retido por outra réplica, aborta imediatamente retornando `{"status": "skipped", "reason": "lock_held", ...}`.
   - **Paginação Keyset (`LIMIT 200`) e Pipeline**: `FilaService.reconciliar_fila_orfaos` varre `APTO_PARA_CHAMADA` em lotes ordenados por `(Atendimento.criado_em.asc(), Atendimento.id.asc())` com `_SWEEPER_BATCH_SIZE = 200` (prevenindo estourar `ARQ_JOB_TIMEOUT = 60s`), valida ZSET + locks (`lock:atendimento:{id}`, `lock:medico:{id}`, `lock:consulta_ativa:medico:{id}`) em 1 round-trip via `esta_bloqueado_para_reconciliacao`, revalida no banco que o `status` segue `APTO_PARA_CHAMADA` e reinsere com `ZADD NX` (`inserir_ou_atualizar_fila(..., nx=True)`).

3. **`ping_task` (`src/worker/tasks/base.py:ping_task`)**:
   - `message: str = "pong"`: Executa `valkey.ping()` e `SELECT 1` via `get_valkey_from_ctx` e `get_db_session_from_ctx`.

### Cron Schedules e Parâmetros de Execução

As configurações operacionais derivam de `src.core.config.Settings`:

| Configuração | Variável / Padrão | Descrição |
|---|---|---|
| Fila ARQ | `ARQ_QUEUE_NAME = "arq:queue"` | Chave principal de enfileiramento no Valkey |
| Concorrência Máxima | `ARQ_MAX_JOBS = 20` | Teto de corrotinas simultâneas por processo worker |
| Timeout Máximo | `ARQ_JOB_TIMEOUT = 60` | Tempo limite de execução por job em segundos |
| Retenção de Resultados | `ARQ_KEEP_RESULT = 3600` | Persistência do resultado do job no Valkey (1 hora) |
| Graceful Shutdown | `ARQ_JOB_COMPLETION_WAIT = 10` | Janela de espera para encerramento gracioso (SIGINT/SIGTERM) |
| Cron de Reconciliação | `cron(second=0)` | Execução a cada minuto (segundo 0) da varredura de órfãos |
| Heartbeat do Worker | `ARQ_HEALTH_CHECK_INTERVAL = 10` | Atualização da telemetria na chave `medisync:worker:health` |

### Retries, Backoff e Telemetria de Falhas

O decorador `@monitored_task` encapsula todas as tarefas e direciona falhas não tratadas para `on_job_failure`:
- Captura exceções e serializa metadados: `job_id`, `job_try`, `enqueue_time`, `score`, `error_type` e `error_message`.
- O ARQ registra tentativas através de `job_try`; tarefas que excedem o limite de tentativas são marcadas como falhas permanentes no Valkey.
- Deduplicação por `_job_id` impede enfileiramento duplicado durante rajadas de reconexão ou reprocessamento concorrente.

### Envelope JSON do Resultado

Contrato mínimo retornado na conclusão do job (spec, 5 linhas):

```json
{"status": "resolved", "action": "no_show_recorded", "atendimento_id": "uuid"}
```

## Onde no código

- Impl: `src/worker/settings.py:WorkerSettings`
- Impl: `src/worker/settings.py:startup`
- Impl: `src/worker/context.py:get_valkey_from_ctx`
- Impl: `src/core/valkey.py:create_arq_redis_settings`
- Impl: `src/worker/tasks/ring_timeout.py:resolver_ring_timeout_task`
- Impl: `src/worker/tasks/sweeper.py:reconciliar_fila_orphans_task`
- Impl: `src/worker/tasks/base.py:monitored_task`
- Impl: `src/worker/tasks/base.py:on_job_failure`
- Impl: `src/worker/tasks/base.py:ping_task`
- Impl: `src/worker/health.py:check_worker_heartbeat`
- Spec: `docs/adrs/ADR-004-Worker-Assincrono-ARQ-sobre-Valkey.md`
- Prova viva: `tests/unit/test_sweeper_task.py`
- Prova viva: `tests/unit/test_ring_timeout_task.py`
- Prova viva: `tests/unit/test_worker_settings.py`
- Prova viva: `tests/integration/test_arq_worker.py:test_arq_worker_executes_ping_task_with_shared_pools`
- Prova viva: `tests/integration/test_arq_worker.py:test_arq_worker_publishes_heartbeat_key`
- Prova viva: `tests/integration/test_arq_worker.py:test_arq_worker_unhandled_failure_logging`
- Prova viva: `tests/integration/test_arq_worker.py:test_worker_graceful_shutdown_timeout_configured`
- Ver: `rg -n "resolver_ring_timeout_task" src/worker/tasks/`
- Ver: `rg -n "reconciliar_fila_orphans_task" src/worker/tasks/`

## Verificação

```bash
uv run pytest tests/integration/test_websocket_endpoints.py tests/integration/test_arq_worker.py
```

## Ver também

- [WebSocket channels](../api/websocket-channels.md)
- [Environment variables](../environment/variables.md)
- [Documentation standards](../architecture-standards/documentation-standards.md)
- [ADR-004: Worker Assíncrono ARQ sobre Valkey](../../adrs/ADR-004-Worker-Assincrono-ARQ-sobre-Valkey.md)
- [Concurrency and queues](../../explanation/architecture/concurrency-and-queues.md)
- [Queue domain](../../explanation/domains/queue-domain.md)
