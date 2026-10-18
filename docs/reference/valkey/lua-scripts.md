# Valkey Lua Scripts

> Catálogo técnico, ciclo de vida e garantias de concorrência dos scripts Lua atômicos em `src/modules/queue/infrastructure/lua/`.

## Contexto

Em pronto-atendimento virtual de urgência sob picos de demanda clínica, múltiplos médicos plantonistas disputam simultaneamente os pacientes mais graves posicionados na cabeça da fila de atendimento. Mecanismos tradicionais baseados em travas de linha relacionais (`SELECT ... FOR UPDATE` ou `SKIP LOCKED`) no PostgreSQL impõem contenção severa de I/O em disco, risco elevado de deadlocks e degradação de latência que viola o teto estrito de $\le 200\text{ ms}$ exigido pelo requisito RNF-01.

Da mesma forma, mecanismos locais de sincronização no processo Python (`asyncio.Lock` ou semáforos) são incapazes de coordenar a concorrência entre múltiplos processos de workers Granian, instâncias réplicas de contêineres e tarefas do worker assíncrono ARQ.

Para eliminar integralmente condições de corrida (*race conditions*) e o risco crítico de *overbooking* (quando dois médicos disparam a chamada do mesmo paciente no mesmo instante e ambos recebem confirmação), o MediSync Express adota scripts Lua transacionais executados diretamente no motor do Valkey 8.0 (ADR-002).

Como o Valkey processa comandos de forma estritamente mono-thread (*single-threaded event loop*), o script Lua é executado de ponta a ponta sem qualquer possibilidade de intercalação de outras operações concorrentes, assegurando linearizabilidade perfeita, aplicação atômica de dual-locks temporizados e tempo de resposta sub-milissegundo (<5ms).

## Conceito

### Catálogo de Scripts Atômicos

Atualmente o sistema concentra a lógica de alocação de chamadas no script canônico:
- `alocar_chamada.lua`: Localizado fisicamente em `src/modules/queue/infrastructure/lua/alocar_chamada.lua`. Carregado e indexado automaticamente pelo gerenciador de scripts no diretório de infraestrutura do módulo.

### Especificação de `alocar_chamada.lua`

O script é disparado quando um médico plantonista solicita o atendimento do próximo paciente apto da fila ou atende uma chamada direcionada.

#### Parâmetros de Chaves (`KEYS`)
1. `KEYS[1]`: `lock:{org_id}:medico:{medico_id}` — Trava temporizada do profissional médico chamador.
2. `KEYS[2]`: `lock:{org_id}:atendimento:{atendimento_id}` — Trava temporizada do paciente/atendimento pretendido.
3. `KEYS[3]`: `fila:{org_id}:aptos` — Sorted Set (ZSET) da fila de pacientes aptos para atendimento clínico.

#### Parâmetros de Argumentos (`ARGV`)
1. `ARGV[1]`: `medico_id` — Identificador UUID do médico que está iniciando a chamada.
2. `ARGV[2]`: `atendimento_id` — Identificador UUIDv7 do atendimento clínico pretendido.
3. `ARGV[3]`: `ttl_segundos` — Tempo de expiração (TTL) em segundos para ambos os locks de ring (padrão canônico: 45s).

#### Contrato de Retorno e Códigos Numéricos

O script retorna códigos inteiros normalizados, mapeados pelo adapter para o enum tipado `AlocacaoCodigo`:

| Código Retorno | Significado Clínico / Operacional | Ação da Aplicação Python | Mapeamento de Domínio |
| :--- | :--- | :--- | :--- |
| `1` | **Sucesso na Alocação**: Locks duplos criados e paciente removido do ZSET com sucesso. | Dispara agendamento do ring timeout no ARQ (`_defer_by=45s`) e sinaliza Pub/Sub. | `AlocacaoCodigo.SUCESSO` |
| `0` | **Médico Ocupado**: `KEYS[1]` já existe; médico possui chamada ou consulta ativa. | Bloqueia operação imediatamente e devolve erro sem alterar fila ou locks. | `AlocacaoCodigo.MEDICO_OCUPADO` $\to$ `MedicoOcupadoError` (HTTP 409) |
| `-1` | **Atendimento Indisponível**: `KEYS[2]` já travada ou atendimento ausente do ZSET `KEYS[3]`. | Dispara retry automático em memória (até 3 tentativas) buscando o próximo paciente do ZSET. | `AlocacaoCodigo.INDISPONIVEL` $\to$ Retry / `AtendimentoNaoDisponivelError` |
| `-2` | **Conflito Específico de Lock do Atendimento**: Reservado para diagnóstico fino de captura concorrente de `KEYS[2]`. | Trata como indisponibilidade transitória com retry imediato no próximo da fila. | Tratado na camada de retry do `AlocacaoChamadaService` |
| `-3` | **Atendimento Ausente no ZSET**: Reservado para diagnóstico de desistência, evasão ou cancelamento simultâneo em `KEYS[3]`. | Registra telemetria de evasão concorrente e busca o próximo paciente apto. | Tratado na camada de retry do `AlocacaoChamadaService` |

### Garantias de Atomicidade e Latência (<5ms)

- **Atomicidade Indivisível**: A inspeção de `KEYS[1]`, a validação de `KEYS[2]`, a verificação de presença em `KEYS[3]` (`ZRANK`), a remoção da fila (`ZREM`) e a atribuição dos locks mútuos (`SET ... EX`) são executadas em bloco mono-operacional. Nenhuma instrução externa pode observar estado intermediário.
- **Teto de Latência Sub-5ms**: As operações executadas operam exclusivamente em memória principal: `EXISTS` em $\mathcal{O}(1)$, `ZRANK` em $\mathcal{O}(\log N)$, `ZREM` em $\mathcal{O}(\log N)$ e `SET` com expiração em $\mathcal{O}(1)$. O tempo medido de execução interna no Valkey é inferior a 2ms, garantindo o cumprimento folgado do limite de 5ms mesmo sob saturação de conexões.
- **Zero Overbooking sob Estresse**: Em testes de carga concorrente com 20 médicos disputando exatamente o mesmo paciente no mesmo instante, o script garante matematicamente 1 vencedor (`código 1`) e 19 perdedores imediatos (`código -1`), sem duplicidade de chamadas.
- **Tolerância a Falhas e Desconexão**: Se o cliente Python sofrer crash imediatamente após o script rodar no Valkey, os locks duplos de 45 segundos evitam que o paciente e o médico fiquem presos indefinidamente; o sweeper periódico do ARQ (`reconciliar_fila_orphans_task`) recupera eventuais divergências entre banco e memória.

### Gerenciamento de Scripts e Ciclo de Vida (`LuaScriptManager`)

O carregamento e despacho de scripts é orquestrado pela classe `LuaScriptManager` (`src/modules/queue/infrastructure/lua_loader.py`):
1. **Descoberta Dinâmica e Registro**: Ao inicializar, a classe varre o diretório `lua/` e registra os scripts em memória calculando antecipadamente os hashes criptográficos SHA-1.
2. **Preload no Startup**: No bootstrap da aplicação, `preload_scripts` registra o script no servidor Valkey via `SCRIPT LOAD`, confirmando prontidão antes de receber tráfego HTTP.
3. **Execução Otimizada com `EVALSHA`**: As chamadas subsequentes utilizam `EVALSHA <sha1>`, trafegando apenas o hash do script na rede em vez do código fonte completo.
4. **Resiliência e Auto-Cura (Auto-Healing)**: Em caso de restart do nó Valkey ou expurgo de scripts (`SCRIPT FLUSH`), a chamada falha com `NoScriptError` (`NOSCRIPT`). O `LuaScriptManager` intercepta a exceção transparentemente, recarrega o arquivo `.lua` em tempo de execução via `SCRIPT LOAD`, renova o cache SHA-1 e repete o `EVALSHA`, dispondo ainda de fallback final para `EVAL` caso persista a falha transitória.
5. **Isolamento de Tipagem (Hexagonal)**: A camada de aplicação consome a porta abstrata `AllocationPort`, garantindo que inteiros crus de Lua nunca vazem para serviços de domínio ou controllers de apresentação.

## Onde no código

- Impl: `src/modules/queue/infrastructure/lua/alocar_chamada.lua:alocar_chamada`
- Impl: `src/modules/queue/infrastructure/lua_loader.py:LuaScriptManager`
- Impl: `src/modules/queue/application/services/alocacao_service.py:AlocacaoChamadaService.alocar_chamada`
- Spec: `src/modules/queue/application/ports/allocation_port.py:AlocacaoCodigo`
- Spec: `src/modules/queue/application/ports/allocation_port.py:AllocationPort`
- Spec: `docs/adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md`
- Prova viva: `tests/integration/test_lua_scripts.py:test_alocar_chamada_adr002_scenarios`
- Prova viva: `tests/integration/test_lua_scripts.py:test_alocar_chamada_race_condition_zero_overbooking`
- Prova viva: `tests/integration/test_lua_scripts.py:test_lua_manager_self_healing_after_script_flush`
- Prova viva: `tests/unit/test_lua_manager.py:test_execute_script_recovers_from_noscript_error`
- Prova viva: `tests/unit/test_alocacao_service.py:test_alocar_chamada_medico_ocupado_retorna_409`
- Ver: `rg -n "alocar_chamada" src/modules/queue/infrastructure/lua/`
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
