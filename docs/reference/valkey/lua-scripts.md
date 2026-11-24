# Valkey Lua Scripts

> Catálogo técnico, ciclo de vida e garantias de concorrência dos scripts Lua atômicos em `src/modules/queue/infrastructure/lua/`.

## Contexto

Em pronto-atendimento virtual de urgência sob picos de demanda clínica, múltiplos médicos plantonistas disputam simultaneamente os pacientes mais graves posicionados na cabeça da fila de atendimento. Mecanismos tradicionais baseados em travas de linha relacionais (`SELECT ... FOR UPDATE` ou `SKIP LOCKED`) no PostgreSQL impõem contenção severa de I/O em disco, risco elevado de deadlocks e degradação de latência que viola o teto estrito de $\le 200\text{ ms}$ exigido pelo requisito RNF-01.

Da mesma forma, mecanismos locais de sincronização no processo Python (`asyncio.Lock` ou semáforos) são incapazes de coordenar a concorrência entre múltiplos processos de workers Granian, instâncias réplicas de contêineres e tarefas do worker assíncrono ARQ.

Para eliminar integralmente condições de corrida (*race conditions*) e o risco crítico de *overbooking* (quando dois médicos disparam a chamada do mesmo paciente no mesmo instante e ambos recebem confirmação), o MediSync Express adota scripts Lua transacionais executados diretamente no motor do Valkey 8.0 (ADR-002).

Como o Valkey processa comandos de forma estritamente mono-thread (*single-threaded event loop*), o script Lua é executado de ponta a ponta sem qualquer possibilidade de intercalação de outras operações concorrentes, assegurando linearizabilidade perfeita, aplicação atômica de dual-locks temporizados e tempo de resposta sub-milissegundo (<5ms).

## Conceito

### Catálogo de Scripts Atômicos

O módulo `queue` mantém dois scripts Lua atômicos em `src/modules/queue/infrastructure/lua/`, descobertos automaticamente pelo `LuaScriptManager` e encapsulados pelo motor `ValkeyQueueEngine`:
- `alocar_chamada.lua`: Alocação atômica 4-Keys de um `atendimento_id` específico com guarda anti-overbooking em ring e consulta ativa.
- `alocar_proximo.lua`: Seleção e alocação atômica 4-Keys multi-candidato via varredura `ZRANGE` de uma janela configurável (`max_scan`, padrão `50`), pulando candidatos já bloqueados em `lock:atendimento:{cand}`.

### Especificação de `alocar_chamada.lua` e `alocar_proximo.lua`

Ambos os scripts validam exclusividade do médico antes de qualquer mutação, eliminando o risco de um profissional em teleconsulta ativa (`EM_ATENDIMENTO`) ou com toque pendente (`CHAMANDO_PACIENTE`) capturar outro paciente.

#### Parâmetros de Chaves (`KEYS` — 4 Chaves)
1. `KEYS[1]`: `lock:medico:{medico_id}` — Trava temporizada de ring do profissional médico chamador.
2. `KEYS[2]`: `lock:atendimento:{atendimento_id}` (em `alocar_chamada.lua`) ou prefixo `lock:atendimento:` concatenado a cada candidato `cand` (em `alocar_proximo.lua`).
3. `KEYS[3]`: `fila:aptos` — Sorted Set (ZSET) da fila de pacientes aptos para atendimento clínico.
4. `KEYS[4]`: `lock:consulta_ativa:medico:{medico_id}` — Trava de teleconsulta em andamento (TTL 7200s), bloqueando overbooking de médico em consulta ativa.

#### Parâmetros de Argumentos (`ARGV`)
- **Em `alocar_chamada.lua`:** `ARGV[1] = medico_id`, `ARGV[2] = atendimento_id`, `ARGV[3] = ttl_segundos` (padrão: `45`).
- **Em `alocar_proximo.lua`:** `ARGV[1] = medico_id`, `ARGV[2] = ttl_segundos` (padrão: `45`), `ARGV[3] = max_scan` (padrão: `50`).

#### Contrato de Retorno e Códigos Reais

Os códigos inteiros são convertidos para o enum tipado `AlocacaoCodigo` (`src/modules/queue/application/ports/allocation_port.py`):

| Script | Retorno Bruto | Significado Clínico / Operacional | Mapeamento de Domínio |
| :--- | :--- | :--- | :--- |
| `alocar_chamada.lua` | `1` | **Sucesso na Alocação**: `ZREM` + `SET EX` em `KEYS[1]` e `KEYS[2]` concluídos. | `AlocacaoCodigo.SUCESSO` |
| `alocar_chamada.lua` | `0` | **Médico Ocupado**: `KEYS[1]` (`lock:medico`) ou `KEYS[4]` (`lock:consulta_ativa`) existe. | `AlocacaoCodigo.MEDICO_OCUPADO` $\to$ `MedicoOcupadoError` (HTTP 409) |
| `alocar_chamada.lua` | `-1` | **Atendimento Indisponível**: `KEYS[2]` já existe ou `ARGV[2]` ausente de `KEYS[3]`. | `AlocacaoCodigo.INDISPONIVEL` $\to$ `AtendimentoNaoDisponivelError` (HTTP 409) |
| `alocar_proximo.lua` | `{1, cand}` | **Sucesso Multi-Candidato**: Primeiro candidato sem `lock:atendimento:{cand}` removido e travado. | `(AlocacaoCodigo.SUCESSO, UUID(cand))` |
| `alocar_proximo.lua` | `{0, ""}` | **Médico Ocupado**: `KEYS[1]` ou `KEYS[4]` existe antes de varrer `ZRANGE`. | `(AlocacaoCodigo.MEDICO_OCUPADO, None)` $\to$ `MedicoOcupadoError` (HTTP 409) |
| `alocar_proximo.lua` | `{-1, ""}` | **Sem Elegíveis Livres**: ZSET vazio ou todos os candidatos da janela `0..max_scan-1` travados. | `(AlocacaoCodigo.INDISPONIVEL, None)` $\to$ HTTP 200 `{alocado: false}` |

### Garantias de Atomicidade e Latência (<5ms)

- **Atomicidade Indivisível 4-Keys**: A checagem de `KEYS[1]` e `KEYS[4]`, a inspeção de `KEYS[2]` (ou loop sobre `ZRANGE KEYS[3] 0 (max_scan - 1)` em `alocar_proximo.lua`), a remoção (`ZREM`) e a aplicação das travas duplas (`SET ... EX`) ocorrem em uma única transação no event loop single-threaded do Valkey.
- **Eliminação de Corridas em Cascata (>3 Médicos)**: Antes de `alocar_proximo.lua`, leituras isoladas de `ZRANGE 0 0` com retry limitado falhavam sob disputa simultânea. A varredura atômica da janela `0..max_scan-1` dentro do próprio Lua permite que 10+ médicos simultâneos recebam pacientes distintos em 1 único round-trip sem HTTP 409 falso.
- **Zero Overbooking em Consulta Ativa**: A inclusão obrigatória de `KEYS[4]` (`lock:consulta_ativa:medico:{medico_id}`) garante que nenhum médico com teleconsulta `EM_ATENDIMENTO` consiga puxar um segundo paciente pela rota `/chamar-proximo`.
- **Tolerância a Falhas e Compensação Pós-Lua**: Em falha de persistência no PostgreSQL ou no agendamento do job ARQ após execução do Lua, `AlocacaoChamadaService` executa compensação automática via `ValkeyQueueEngine.devolver_para_fila(..., nx=True)` (e reversão de status para `APTO_PARA_CHAMADA` se necessário); o sweeper periódico (`reconciliar_fila_orphans_task`) cura divergências residuais.

### Gerenciamento de Scripts e Ciclo de Vida (`LuaScriptManager` & `ValkeyQueueEngine`)

O carregamento e despacho de scripts é orquestrado por `LuaScriptManager` (`src/modules/queue/infrastructure/lua_loader.py`) e exposto à camada de aplicação exclusivamente atrás de `QueueEnginePort`:
1. **Descoberta Dinâmica e Registro**: Ao inicializar, `LuaScriptManager` varre `lua/` (`alocar_chamada.lua` e `alocar_proximo.lua`), registra os conteúdos e calcula os hashes SHA-1.
2. **Preload no Startup**: No hook `src/modules/queue/composition.py:on_startup`, `preload_scripts` carrega todos os scripts via `SCRIPT LOAD`.
3. **Execução Otimizada com `EVALSHA` e Auto-Healing**: Executa via `EVALSHA <sha1>`; em `NOSCRIPT`, recarrega o script on-the-fly (`SCRIPT LOAD` + `EVALSHA`) com fallback final para `EVAL`.
4. **Isolamento Hexagonal (`QueueEnginePort`)**: Os serviços de aplicação (`AlocacaoChamadaService`, `FilaService`) consomem `QueueEnginePort` (`src/modules/queue/application/ports/queue_engine_port.py`), implementado na infraestrutura por `ValkeyQueueEngine` (`src/modules/queue/infrastructure/valkey_queue_engine.py`), sem vazar chaves brutas ou comandos `redis.asyncio` para a camada `application` (substituindo o antigo seam `LuaScriptPort`).

## Onde no código

- Impl: `src/modules/queue/infrastructure/lua/alocar_chamada.lua`
- Impl: `src/modules/queue/infrastructure/lua/alocar_proximo.lua`
- Impl: `src/modules/queue/infrastructure/lua_loader.py:LuaScriptManager`
- Impl: `src/modules/queue/infrastructure/valkey_queue_engine.py:ValkeyQueueEngine`
- Impl: `src/modules/queue/application/services/alocacao_service.py:AlocacaoChamadaService`
- Spec: `src/modules/queue/application/ports/queue_engine_port.py:QueueEnginePort`
- Spec: `src/modules/queue/application/ports/allocation_port.py:AlocacaoCodigo`
- Spec: `docs/adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md`
- Prova viva: `tests/integration/test_lua_scripts.py:test_alocar_chamada_adr002_scenarios`
- Prova viva: `tests/integration/test_lua_scripts.py:test_alocar_chamada_race_condition_zero_overbooking`
- Prova viva: `tests/integration/test_lua_scripts.py:test_lua_manager_self_healing_after_script_flush`
- Prova viva: `tests/integration/test_alocar_chamada_concurrency.py:test_parallel_race_condition_50_doctors_single_winner`
- Prova viva: `tests/unit/test_lua_manager.py:test_execute_script_recovers_from_noscript_error`
- Prova viva: `tests/unit/test_alocacao_service.py:test_alocar_chamada_medico_ocupado_por_ring_ou_consulta_ativa`
- Ver: `rg -n "alocar_chamada|alocar_proximo" src/modules/queue/infrastructure/`
- Ver: `rg -n "evalsha" src/modules/queue/infrastructure/lua_loader.py`

## Verificação

```bash
uv run pytest tests/integration/test_lua_scripts.py tests/integration/test_valkey_pool.py
```

## Ver também

- [Keys Dictionary](keys-dictionary.md)
- [ADR-002: Alocação Atômica Valkey Lua](../../adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md)
- [ADR-004: Worker Assíncrono ARQ](../../adrs/ADR-004-Worker-Assincrono-ARQ-sobre-Valkey.md)
- [Concurrency and Queues](../../explanation/architecture/concurrency-and-queues.md)
- [Queue Lua ARQ](../../explanation/concepts/queue-lua-arq.md)
- [Documentation Standards](../architecture-standards/documentation-standards.md)
