# ARQ Background Tasks

> Catálogo e ciclo de vida de jobs assíncronos sobre Valkey; orquestração vive em `src/worker/settings.py`.

## Contexto

O pronto-atendimento virtual exige operações em segundo plano desacopladas do ciclo síncrono de requisições HTTP:
- Validação assíncrona de convênio e elegibilidade SUS sem travar o endpoint de admissão (RF-02, RN03).
- Resolução determinística de no-show via ring timeout de exatamente 45 segundos (RN02).
- Auto-cura e reconciliação periódica de inconsistências entre a fila relacional e o cache em memória (RN03).
As tarefas executam sob o framework ARQ em corrotinas nativas do `asyncio`, compartilhando pools de conexão com o banco relacional (`SQLAlchemy`) e o Valkey.

## Conceito

### Catálogo de Tarefas

O worker disponibiliza quatro tarefas principais registradas no `WorkerSettings`:

| Tarefa / Identificador | Módulo de Origem | Gatilho / Origem | Propósito Clínico e Operacional |
|---|---|---|---|
| `validar_elegibilidade_task` | `src.worker.tasks.eligibility` | Admissão na fila | Validação de elegibilidade (SUS/Convênio) e promoção atômica para `APTO_PARA_CHAMADA` |
| `ring_timeout_task` | `src.worker.tasks.ring_timeout` | Alocação médica | Resolução de abandono (no-show) após 45s de chamada sem atendimento |
| `sweeper_reconciliation_task` | `src.worker.tasks.sweeper` | Agendador Cron | Reconciliação de atendimentos aptos do PostgreSQL ausentes no ZSET do Valkey |
| `ping_task` | `src.worker.tasks.base` | Diagnóstico / Health | Teste de conectividade cruzada entre pools Valkey e PostgreSQL |

### Parâmetros e Assinatura das Tarefas

Cada tarefa recebe o contexto assíncrono `ctx` com pools compartilhados e parâmetros estruturados:

1. **`validar_elegibilidade_task` (`src/worker/tasks/eligibility.py:validar_elegibilidade_task`)**:
   - `organizacao_id: int`: Tenant do atendimento.
   - `atendimento_id: str`: UUID do atendimento a validar e promover.
   - `paciente_id: str`: UUID do paciente para cruzamento cadastral.
   - `cpf: str | None`, `cns: str | None`: Identificadores sanitários e civis.
   - `operadora_id: str | None`, `numero_carteirinha: str | None`: Dados do plano de saúde.
   - `modo_publico_sus: bool | None`: Sobrescrita explícita de modo público (opcional).
   - Deduplicação no enfileiramento via `_job_id=f"elegibilidade:{atendimento_id}"`.

2. **`ring_timeout_task` (`src/worker/tasks/ring_timeout.py:resolver_ring_timeout_task`)**:
   - `organizacao_id: int`: Tenant do atendimento.
   - `atendimento_id: str`: UUID do atendimento cujo tempo de ring expirou.
   - `medico_id: str`: UUID do médico que efetuou a chamada.
   - Enfileirada com adiamento de 45s via `_defer_by=timedelta(seconds=45)`.
   - Deduplicação via `_job_id=f"ring_timeout:{atendimento_id}"`.
   - Ação: se o paciente não conectou, marca abandono, libera o médico e cancela locks.

3. **`sweeper_reconciliation_task` (`src/worker/tasks/sweeper.py:reconciliar_fila_orphans_task`)**:
   - `organizacao_id: int | None`: Tenant específico ou `None` para varrer todas as organizações ativas.
   - `threshold_segundos: int = 60`: Janela temporal de corte para detecção de atendimentos órfãos.

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
{"status": "resolved", "action": "no_show", "atendimento_id": "uuid"}
```

## Onde no código

- Impl: `src/worker/settings.py:WorkerSettings`
- Impl: `src/worker/tasks/eligibility.py:validar_elegibilidade_task`
- Impl: `src/worker/tasks/ring_timeout.py:resolver_ring_timeout_task`
- Impl: `src/worker/tasks/sweeper.py:reconciliar_fila_orphans_task`
- Impl: `src/worker/tasks/base.py:monitored_task`
- Impl: `src/worker/tasks/base.py:on_job_failure`
- Impl: `src/worker/tasks/base.py:ping_task`
- Impl: `src/worker/health.py:check_worker_heartbeat`
- Spec: `docs/adrs/ADR-004-Worker-Assincrono-ARQ-sobre-Valkey.md`
- Prova viva: `tests/integration/test_arq_worker.py:test_arq_worker_executes_ping_task_with_shared_pools`
- Prova viva: `tests/integration/test_arq_worker.py:test_arq_worker_publishes_heartbeat_key`
- Prova viva: `tests/integration/test_arq_worker.py:test_arq_worker_unhandled_failure_logging`
- Prova viva: `tests/integration/test_arq_worker.py:test_worker_graceful_shutdown_timeout_configured`
- Ver: `rg -n "validar_elegibilidade_task" src/worker/tasks/`
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
