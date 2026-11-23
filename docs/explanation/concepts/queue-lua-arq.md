# Queue Lua ARQ

Fila de aptos em Valkey com alocação atômica Lua e
resolução de ausência via worker ARQ. Três peças se
encaixam: score ordena, script Lua reserva, tarefas
de fundo fecham o ciclo quando ninguém atende.
Regra de ouro: Valkey decide velocidade; postgres
decide verdade; worker decide prazo.

Regras clínicas fonte moram no futuro
[queue-domain](../domains/queue-domain.md) (planejado,
detentor de RN01, RN02 e RN05); este conceito não
recopia regras, só o mecanismo que as executa.
Motor em
`docs/explanation/architecture/concurrency-and-queues.md`,
decisões em
`docs/adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md` e
`docs/adrs/ADR-004-Worker-Assincrono-ARQ-sobre-Valkey.md`.

## 1. Contexto

Vários médicos plantonistas disputam o mesmo paciente
no mesmo milissegundo. `select` travado estoura o
teto de resposta, e paciente que não atende não pode
travar a tela do médico. A resposta separa as
camadas: ZSET ordena por score, Lua aloca sem
corrida, ARQ resolve ausência com prazo exato e
sweeper cura divergência entre memória e banco.

Prova de existência das peças, confirmada por busca:

`ls src/modules/queue/infrastructure/lua/`
`rg -n "async def |_defer_by" src/worker/tasks/ring_timeout.py src/worker/tasks/sweeper.py`
`rg -n "def calcular_score" src/modules/queue/domain/scoring.py`

Retornam `alocar_chamada.lua`, `alocar_proximo.lua`, as duas tasks e
`calcular_score`, respectivamente.

## 2. Score ZSET de 64 bits e FIFO via UUIDv7

Ordenação mora em
`src/modules/queue/domain/scoring.py`. Função
`calcular_score` combina prioridade clínica (1 a 5,
fora disso levanta erro de validação) com epoch de
entrada: prioridade vezes `SCORE_PRIORITY_MULTIPLIER`
(1 trilhão) mais segundos. Menor número = maior
gravidade; dentro da mesma prioridade, entrou antes
vem antes.

Ingestão mora em
`src/modules/queue/application/services/fila_service.py` sobre `QueueEnginePort`.
Método `ingressar_fila` calcula o score e delega a `inserir_ou_atualizar_fila`
(em `ValkeyQueueEngine`), que grava com `zadd` na chave `fila:aptos` e lê
`zrank` em um único pipeline. Dicionário canônico de
chaves e TTLs em [Valkey Keys Dictionary](../../reference/valkey/keys-dictionary.md)
(`docs/reference/valkey/keys-dictionary.md`). Reentrada após
falha preserva score original porque a fórmula é
pura em cima de prioridade mais timestamp.

Empate no mesmo segundo e mesma prioridade gera
scores idênticos. O desempate é lexicográfico do
membro, e o membro é UUIDv7: `src/core/uuid7.py`
define `uuid7`, usado como default da chave primária
em `src/modules/queue/domain/models/atendimento.py`.
UUIDv7 carrega timestamp nos primeiros caracteres,
então ordem lexicográfica reflete ordem cronológica
de acolhimento sem risco de estouro de mantissa.
Detalhe na seção de desempate FIFO de
`docs/explanation/architecture/concurrency-and-queues.md`.

Busca de prova:

`rg -n "calcular_score|inserir_ou_atualizar_fila" src/modules/queue/application/services/fila_service.py`
`rg -n "zadd|zrank" src/modules/queue/infrastructure/valkey_queue_engine.py`
`rg -n "uuid7" src/modules/queue/domain/models/atendimento.py src/core/uuid7.py`

## 3. Alocação atômica Lua 4-Keys

Scripts em
`src/modules/queue/infrastructure/lua/alocar_chamada.lua` e
`src/modules/queue/infrastructure/lua/alocar_proximo.lua`,
carregados e executados via
`src/modules/queue/infrastructure/lua_loader.py` e encapsulados por
`ValkeyQueueEngine` (`src/modules/queue/infrastructure/valkey_queue_engine.py`,
implementando `QueueEnginePort`).
Especificação formal de parâmetros e retornos em
[Valkey Lua Scripts](../../reference/valkey/lua-scripts.md)
(`docs/reference/valkey/lua-scripts.md`).
Classe `LuaScriptManager` descobre os arquivos da
pasta `lua`, executa por `EVALSHA` com auto-cura em
`NOSCRIPT` (recarrega e reexecuta, com fallback para
`EVAL`), e expõe métodos tipados `alocar_chamada` e `alocar_proximo` que
convertem inteiros brutos em `AlocacaoCodigo`.

Os scripts validam 4 chaves: `lock:medico:{id}` (`KEYS[1]`),
`lock:atendimento:...` (`KEYS[2]`), `fila:aptos` (`KEYS[3]`) e
`lock:consulta_ativa:medico:{id}` (`KEYS[4]`). Médico com ring ativo ou
consulta ativa retorna `0`; atendimento indisponível ou janela sem livres
retorna `-1`; senão `alocar_proximo.lua` percorre `ZRANGE` até `max_scan`
em um único round-trip, remove com `ZREM`, cria os dois
locks de toque com `SET EX ttl` e retorna `{1, cand}`. TTL padrão de
toque é 45 segundos, lido de `ConfiguracaoPlantao` via `ShiftPolicyReaderPort`
(com fallback em `src/modules/queue/application/dtos.py`).

Orquestração em
`src/modules/queue/application/services/alocacao_service.py`.
Os métodos `alocar_chamada` e `alocar_proximo_paciente` chamam
`QueueEnginePort`, traduzem `0` em erro de médico ocupado (`MedicoOcupadoError`) e
`-1` em erro de indisponibilidade ou retorno `None` no `/chamar-proximo`,
persistem `iniciar_chamada` com commit único e, em qualquer falha de banco
ou de `enqueue_job` no ARQ, compensam via `devolver_para_fila(..., nx=True)`
e reversão para `APTO_PARA_CHAMADA`. Notificação WhatsApp e eventos Pub/Sub
(`INCOMING_CALL`, `CALLED`) rodam pós-commit sem bloquear a fila.

Busca de prova:

`rg -n "return 0|return -1|return 1" src/modules/queue/infrastructure/lua/alocar_chamada.lua`
`rg -n "devolver_para_fila|enqueue_job|_compensar_falha_agendamento" src/modules/queue/application/services/alocacao_service.py`

## 4. No-show determinístico via ARQ

Logo após alocar, o service agenda a tarefa com
`enqueue_job` para `resolver_ring_timeout_task`,
passando atendimento e médico, com
`_defer_by` igual ao ttl do comando e id de job
`ring_timeout:{atendimento_id}` para deduplicar.
Catálogo formal de tarefas em
[ARQ Background Tasks](../../reference/worker/arq-tasks.md)
(`docs/reference/worker/arq-tasks.md`).
Implementação em
`src/worker/tasks/ring_timeout.py`: se o estado
ainda é chamado tocando, registra ausência via
`registrar_ausencia_paciente`, commita, apaga os
dois locks de toque e emite o evento de paciente
ausente; se já virou consulta ativa, promove o lock
do médico para `consulta_ativa` com 2 horas de
contingência; estado terminal só limpa lock
residual.

Sobre não usar expiração com pub-sub: registrado
aqui como decisão de arquitetura, não como fato de
código — não há comentário no fonte afirmando o
motivo. A justificativa vive na seção de
expiração de
`docs/explanation/architecture/concurrency-and-queues.md`:
entrega fire-and-forget perde evento em restart e
expiração por amostragem atrasa além do prazo, o
que é inaceitável para fluxo crítico. Por isso a
decisão por jobs diferidos com precisão de
milissegundos, conforme
`docs/adrs/ADR-004-Worker-Assincrono-ARQ-sobre-Valkey.md`.

Busca de prova:

`rg -n "_defer_by|_job_id" src/modules/queue/application/services/alocacao_service.py`
`rg -n "async def resolver_ring_timeout_task|registrar_ausencia_paciente" src/worker/tasks/ring_timeout.py`

## 5. Sweeper de auto-cura sob lock distribuído

Dual-write ou queda pós-commit pode deixar atendimento apto no banco fora do
ZSET. Cura mora em `src/worker/tasks/sweeper.py`, função
`reconciliar_fila_orphans_task`, que adquire `lock:sweeper:fila_aptos`
(`NX EX 55` via `adquirir_lock_sweeper`, liberado em `finally`) para evitar
concorrência entre workers. `FilaService.reconciliar_fila_orfaos` pagina em
lotes keyset de `200` linhas (`APTO_PARA_CHAMADA` sem atualização além do
limiar padrão de 60s), verifica ZSET e locks em 1 pipeline
(`esta_bloqueado_para_reconciliacao`), revalida o status no banco e reinjeta
o órfão confirmado com `ZADD NX` (`inserir_ou_atualizar_fila(..., nx=True)`).

Agendamento em `src/worker/settings.py`: função
registrada no worker mais cron por minuto
(`reconciliar_fila_orphans_cron`). Varre a fila única
da plataforma (`fila:aptos`) e reconstrói órfãos reais.

Busca de prova:

`rg -n "async def reconciliar_fila_orphans_task|adquirir_lock_sweeper" src/worker/tasks/sweeper.py`
`rg -n "reconciliar_fila_orphans_cron|cron" src/worker/settings.py`

## 6. Fluxo ponta a ponta

Diagrama contém só funções reais confirmadas nas
buscas acima.

```mermaid
sequenceDiagram
    autonumber
    participant M as medico
    participant F as ingressar_fila
    participant A as alocar_proximo_paciente
    participant L as alocar_proximo_lua
    participant R as resolver_ring_timeout_task
    participant S as reconciliar_fila_orphans_task
    M->>F: entra na fila (pos-commit)
    F->>F: calcular_score + ZADD
    M->>A: chamar proximo paciente
    A->>L: EVALSHA 4-Keys + ZRANGE
    L-->>A: {1, cand} reserva, {0} ocupado, {-1} sem livres
    A->>R: enqueue_job defer_by ttl
    alt paciente atende em 45s
        R->>R: promove lock consulta_ativa (7200s)
    else timeout sem resposta
        R->>R: registra ausencia + limpa ring locks
    end
    S->>S: adquire lock_sweeper + pagina 200 + ZADD NX
```

Leitura: `ingressar_fila` publica posição;
`alocar_proximo_paciente` reserva via `L`; `R` fecha o toque;
`S` devolve ao ZSET quem caiu no vão entre banco e
memória.

## 7. Limites verificados por máquina

Execução real para registro:

`uv run pytest tests/unit/test_alocacao_service.py tests/unit/test_sweeper_task.py -q --no-cov`

Guardas repetíveis sem infra:

- `uv run python scripts/docs_check.py` sai 0; só
  links curtos e um bloco mermaid, zero python >5.
- `rg -n "async def |_defer_by" src/worker/tasks/ring_timeout.py src/worker/tasks/sweeper.py`
  ancora as tasks do diagrama.
- `rg -n "def calcular_score" src/modules/queue/domain/scoring.py`
  ancora a fórmula. Comando em `justfile`.

## 8. Referências

- Score: `src/modules/queue/domain/scoring.py`
- Ingestão e reconciliação: `src/modules/queue/application/services/fila_service.py`
- Id ordenável: `src/core/uuid7.py`, `src/modules/queue/domain/models/atendimento.py`
- Motor Valkey: `src/modules/queue/infrastructure/valkey_queue_engine.py`, `src/modules/queue/application/ports/queue_engine_port.py`
- Dicionário de chaves Valkey: [Valkey Keys Dictionary](../../reference/valkey/keys-dictionary.md) (`docs/reference/valkey/keys-dictionary.md`)
- Scripts Lua atômicos: [Valkey Lua Scripts](../../reference/valkey/lua-scripts.md) (`docs/reference/valkey/lua-scripts.md`)
- Tarefas assíncronas do worker: [ARQ Background Tasks](../../reference/worker/arq-tasks.md) (`docs/reference/worker/arq-tasks.md`)
- Scripts: `src/modules/queue/infrastructure/lua/alocar_chamada.lua`, `src/modules/queue/infrastructure/lua/alocar_proximo.lua`
- Loader: `src/modules/queue/infrastructure/lua_loader.py`
- Orquestra, ttl, defer: `src/modules/queue/application/services/alocacao_service.py`, `src/modules/queue/application/dtos.py`
- Timeout: `src/worker/tasks/ring_timeout.py`
- Reconciliação: `src/worker/tasks/sweeper.py`, `src/worker/settings.py`
- Motor e porquê: `docs/explanation/architecture/concurrency-and-queues.md`
- Decisões: `docs/adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md`, `docs/adrs/ADR-004-Worker-Assincrono-ARQ-sobre-Valkey.md`
- Regras fonte: [queue-domain](../domains/queue-domain.md)
