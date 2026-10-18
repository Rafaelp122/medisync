# Debug Background Task com ARQ e Valkey

> Como depurar, executar localmente e diagnosticar falhas em tarefas assíncronas do ARQ worker.

## Contexto

O processamento assíncrono do MediSync Express é executado sobre o ARQ worker conectado ao Valkey (ADR-004). O worker orquestra rotinas em segundo plano cruciais, como expiração de chamadas clínicas (ring timeout), reconciliação de pacientes órfãos na fila e validação assíncrona de elegibilidade.

Quando uma tarefa em background apresenta lentidão, falha silenciosa ou comportamento inesperado, depurar via servidor de produção ou logs dispersos é ineficiente. Este guia apresenta os passos operacionais para depurar tarefas localmente em modo burst, inspecionar a fila no Valkey e isolar falhas de execução.

## Conceito

O fluxo de diagnóstico e depuração de tarefas do ARQ é estruturado em cinco procedimentos:

### 1. Iniciar o worker em modo de desenvolvimento contínuo

Para acompanhar o processamento de tarefas em tempo real com hot-reload e logs estruturados:

```bash
just worker
```

O comando executa `arq src.worker.WorkerSettings` com heartbeat periódico e reconexão automática.

### 2. Executar em modo Burst para depuração pontual

O modo burst consome todos os jobs enfileirados até o esvaziamento da fila e encerra o processo imediatamente:

```bash
uv run python -c "from arq.worker import create_worker; from src.worker.settings import WorkerSettings; create_worker(WorkerSettings, burst=True).run()"
```

Ideal para reproduzir cenários controlados em scripts de depuração ou pontos de parada (`breakpoint()`).

### 3. Enfileirar tarefa de teste diagnóstico (Ping)

Para verificar a comunicação simultânea entre o worker, o Valkey e o banco de dados:

```python
pool = await create_pool(WorkerSettings.redis_settings)
job = await pool.enqueue_job("ping_task", message="debug-probe")
result = await job.result(timeout=5)
```

O resultado esperado é a string de diagnóstico `debug-probe:valkey=True:db=True`.

### 4. Inspecionar o estado da fila e chaves no Valkey

Consulte o volume de jobs pendentes e o registro de heartbeat operacional:

```bash
docker compose exec -T valkey valkey-cli zcard arq:queue
docker compose exec -T valkey valkey-cli get medisync:worker:heartbeat
```

Se o zcard for superior a zero e o worker não consumir, certifique-se de que a função está registrada em `WorkerSettings.functions`.

### 5. Rastrear exceções com telemetria de falha

Todas as tarefas de `src/worker/tasks/` utilizam o decorator `@monitored_task`, que intercepta erros não tratados e os encaminha para `on_job_failure` com contexto completo (job ID, payload, retentativas e traceback).

## Onde no código

- Orquestração e ciclo de vida do worker: `src/worker/settings.py:WorkerSettings`
- Decorator de telemetria e task de ping: `src/worker/tasks/base.py:monitored_task`
- Diretório de tarefas assíncronas: `src/worker/tasks/`
- Monitoramento de heartbeat operacional: `src/worker/health.py:check_worker_heartbeat`
- Suíte de integração do worker: `tests/integration/test_arq_worker.py`
- Referência de tarefas em background: `docs/reference/worker/arq-tasks.md`

Localize a lista de tarefas registradas no worker:

```bash
rg -n "functions = \[" src/worker/settings.py -A 10
```

Verifique a captura contextual de exceções no worker:

```bash
rg -n "on_job_failure" src/worker/tasks/base.py -A 10
```

## Verificação

Execute a suíte de testes de integração do worker ARQ em modo isolado:

```bash
uv run pytest tests/integration/test_arq_worker.py --no-cov -q
```

Expected: 3 testes aprovados (`test_arq_worker_executes_ping_task_with_shared_pools`, `test_arq_worker_publishes_heartbeat_key`, `test_arq_worker_unhandled_failure_logging`).

Valide a integridade do heartbeat do worker via Python:

```bash
uv run python -c "import asyncio; from arq.connections import create_pool; from src.worker.settings import WorkerSettings; from src.worker.health import check_worker_heartbeat; p = asyncio.run(create_pool(WorkerSettings.redis_settings)); print(asyncio.run(check_worker_heartbeat(p)))"
```

Expected: Dicionário contendo `status: healthy` e `is_alive: True`.

## Ver também

- [Wire module dependencies](wire-module-dependencies.md)
- [Run tests](run-tests.md)
- [ADR-004](../../adrs/ADR-004-Worker-Assincrono-ARQ-sobre-Valkey.md)
- [ARQ Tasks Reference](../../reference/worker/arq-tasks.md)
- [Queue Lua ARQ Concept](../../explanation/concepts/queue-lua-arq.md)
