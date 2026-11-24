# Concorrência, Motor de Fila Valkey e Ring Timeout (Concurrency & Queues)

> Mecanismo atômico de admissão, ordenação por ZSET no Valkey, alocação de chamadas via Lua e resolução determinística de no-show em `src/modules/queue/`.

| Metadado | Detalhamento |
| :--- | :--- |
| **Componentes Centrais** | Valkey 8.0, Scripts Lua Atômicos, Sorted Sets (ZSET), ARQ Task Worker |
| **Padrão de Concorrência** | Alocação Atômica por Script Lua com Lock Duplo Temporizado (45 segundos) |
| **Identificadores de Fila** | UUIDv7 (RFC 9562) com Desempate Determinístico FIFO Sub-Milissegundo |
| **Resolução de No-Show** | Ring Timeout Determinístico via Jobs Diferidos (`_defer_by=45`) no ARQ |

## Contexto

Em uma unidade de pronto-atendimento virtual com múltiplos médicos atendendo simultaneamente em picos de demanda, o sistema enfrenta três desafios críticos de concorrência:
1. **Risco de Overbooking (Race Condition)**: Dois ou mais médicos clicarem em *"Chamar Próximo"* no mesmo milissegundo e receberem o mesmo paciente.
2. **Contenção Relacional no Banco**: Ordenar filas clínicas em tempo real com `SELECT ... FOR UPDATE` no PostgreSQL sob concorrência degrada o tempo de resposta, violando o SLA de $\le 200\text{ ms}$ (RNF-01).
3. **Deadlocks Operacionais por No-Show**: Quando o paciente chamado não atende, o médico não pode ter a tela travada indefinidamente.

## Conceito

### 1. Estrutura de Dados e Indexação da Fila em Memória

A fila é mantida em **Sorted Sets (ZSET)** do Valkey com namespace único de plataforma:
- **Namespace da Chave**: `fila:aptos`
- **Membro (Member)**: ID do atendimento (`atendimento_id` em formato UUIDv7).
- **Pontuação (Score)**: Valor numérico inteiro de 64 bits calculado deterministicamente por prioridade clínica (níveis 1 a 5, onde menor valor numérico representa maior gravidade):

$$\text{Score} = (\text{prioridade\_clinica} \times 10^{12}) + \text{timestamp\_entrada\_epoch}$$

#### Desempate Determinístico FIFO via UUIDv7 (RN01)
Quando múltiplos pacientes chegam no mesmo segundo e possuem a mesma gravidade clínica, seus scores numéricos serão idênticos. O Valkey aplica o desempate por ordem lexicográfica do membro. Como o **UUIDv7** embute um timestamp Unix de 48 bits em milissegundos nos seus primeiros caracteres hexadecimais, a comparação lexicográfica do `atendimento_id` reflete rigorosamente a ordem cronológica real de acolhimento (FIFO), sem risco de estouro da mantissa do float de 64 bits.

A busca do próximo atendimento opera em tempo logarítmico $\mathcal{O}(\log N)$:
```redis
ZRANGE fila:aptos 0 0
```

### 2. Alocação Atômica Médico-Paciente via Scripts Lua 4-Keys (RN02)

Para garantir que a verificação de disponibilidade do médico (tanto em toque quanto em teleconsulta ativa), a seleção e reserva exclusiva do paciente e a remoção da fila ocorram em uma única etapa indivisível sem race conditions, o motor `ValkeyQueueEngine` (`QueueEnginePort`) executa scripts Lua 4-Keys via `EVALSHA`:

```lua
-- KEYS[1]: lock:medico:{medico_id} | KEYS[2]: lock:atendimento:{id} (ou prefixo) | KEYS[3]: fila:aptos
-- KEYS[4]: lock:consulta_ativa:medico:{medico_id}
-- alocar_chamada.lua -> 1 (sucesso), 0 (medico ocupado/consulta ativa), -1 (indisponivel)
-- alocar_proximo.lua -> {1, cand}, {0, ''}, {-1, ''} apos varredura ZRANGE 0..(max_scan-1)
```
Scripts canônicos em `src/modules/queue/infrastructure/lua/alocar_chamada.lua` e `src/modules/queue/infrastructure/lua/alocar_proximo.lua`.

Em `/chamar-proximo`, `alocar_proximo.lua` verifica `KEYS[1]` e `KEYS[4]`, percorre a janela `ZRANGE KEYS[3] 0 (max_scan - 1)` (padrão `max_scan=50`) pulando candidatos já bloqueados por `lock:atendimento:{cand}`, executa `ZREM` + `SET EX` atômico e retorna `{1, cand}` em um único round-trip — eliminando corridas em cascata quando 10+ médicos chamam simultaneamente. Em falha de persistência no PostgreSQL ou de enfileiramento no ARQ pós-Lua, `AlocacaoChamadaService` compensa devolvendo o atendimento ao ZSET (`devolver_para_fila(..., nx=True)`).

### 3. Resolução Determinística de No-Show e Ciclo de Vida de Locks

Notificações pub/sub baseadas em expiração de chave (`notify-keyspace-events`) são *fire-and-forget* e podem atrasar ou se perder em reinicializações da API. Por isso, adota-se o agendamento de jobs diferidos com precisão de milissegundos no ARQ:

```python
await arq_pool.enqueue_job(
    "resolver_ring_timeout_task",
    atendimento_id=str(atendimento_id), medico_id=str(medico_id),
    _defer_by=timedelta(seconds=ttl_segundos), _job_id=f"ring_timeout:{atendimento_id}",
)
```

No vencimento do ring (`tempo_tolerancia_ring_segundos`, padrão 45s), o worker ARQ despacha a resolução delegando a transição de estado e limpeza de locks ao serviço de domínio:

```python
action = await fila_service.resolver_ring_timeout(
    atendimento_id=atend_uuid, medico_id=med_uuid, notifier=notifier,
)
```

#### Transição de Locks e Transação Única PEP
1. **Fase de Toque (Ring - 45s)**: Protegida por `lock:medico:{medico_id}` e `lock:atendimento:{atendimento_id}` com TTL configurado.
2. **Fase de Teleconsulta (`EM_ATENDIMENTO`)**: Ao atender, `ValkeyQueueEngine.promover_para_consulta` apaga os locks de ring em pipeline e grava `lock:consulta_ativa:medico:{medico_id}` (TTL 7200s), bloqueando novas chamadas em `KEYS[4]` dos scripts Lua.
3. **Conclusão Clínica (ADR-001 §6)**: `PEPService.finalizar_consulta` chama `concluir_atendimento(..., auto_commit=False)` (que carrega `Atendimento` com `with_for_update=True` e faz apenas `flush()`), executa um único `commit()` no PostgreSQL e libera `lock:consulta_ativa:medico:{medico_id}` estritamente pós-commit via `liberar_consulta_ativa_medico`.

### 4. Controle de Admissão, Política de Plantão e Backpressure Estocástico (RN05)

`FilaService.admitir_paciente` lê parâmetros operacionais em `ConfiguracaoPlantao` via `ShiftPolicyReaderPort` e consulta médicos ativos diretamente em `plantao:medicos_ativos` (alimentado por login/MFA/logout em `auth` via `DoctorPresencePort`, `/chamar-proximo` e `/ws/doctor/{id}`). A entrada é preventivamente suspensa com `AdmissaoFilaSuspensaError` (HTTP 503) e log estruturado se:
1. **Ausência de Médicos**: $\text{Médicos Ativos} \le 0$ (`SEM_MEDICOS_ATIVOS`).
2. **Cota Diária**: Reserva atômica via `consumir_cota_ou_bloquear` (`INCR` + `DECR` imediato se estourar `cota_diaria_maxima`, com `estornar_cota_diaria` em rollback de banco — `COTA_ATINGIDA`).
3. **Capacidade vs. Demanda Restante (`CAPACIDADE_EXCEDIDA`)**:

$$\frac{\text{Pacientes Aguardando} \times \text{TMA Estimado} \times \alpha}{\text{Médicos Ativos no Turno}} > \text{Tempo Restante de Plantão}$$

Onde $\alpha$ provém da configuração do plantão (padrão `1,25`; intervalo válido $1{,}20 \le \alpha \le 1{,}30$). Todas as inserções no ZSET `fila:aptos` ocorrem exclusivamente **após** o `commit()` no PostgreSQL.

### 5. Auto-Cura e Reconciliação (Sweeper Blindado)

Caso ocorra interrupção entre escrita no PostgreSQL e mutação pós-commit no Valkey, `reconciliar_fila_orphans_task` executa a cada 60 segundos adquirindo `lock:sweeper:fila_aptos` (`NX EX 55`), paginando órfãos em lotes keyset (`LIMIT 200` por `(criado_em, id)`), checando ZSET e locks em 1 pipeline (`esta_bloqueado_para_reconciliacao`), revalidando status `APTO_PARA_CHAMADA` e reinjetando no ZSET via `ZADD NX`.

## Onde no código

- Impl: `src/modules/queue/infrastructure/lua/alocar_chamada.lua`
- Impl: `src/modules/queue/infrastructure/lua/alocar_proximo.lua`
- Impl: `src/modules/queue/infrastructure/valkey_queue_engine.py:ValkeyQueueEngine`
- Impl: `src/modules/queue/application/services/alocacao_service.py:AlocacaoChamadaService.alocar_chamada`
- Impl: `src/modules/queue/application/services/fila_service.py:FilaService.resolver_ring_timeout`
- Impl: `src/modules/queue/application/services/fila_service.py:FilaService.reconciliar_fila_orfaos`
- Impl: `src/modules/queue/application/services/controle_admissao_service.py:ControleAdmissaoService`
- Impl: `src/worker/tasks/ring_timeout.py:resolver_ring_timeout_task`
- Impl: `src/worker/tasks/sweeper.py:reconciliar_fila_orphans_task`
- Spec: `src/modules/queue/application/ports/queue_engine_port.py:QueueEnginePort`
- Spec: `src/modules/queue/application/ports/shift_policy_reader_port.py:ShiftPolicyReaderPort`
- Spec: `src/modules/queue/application/ports/allocation_port.py:AlocacaoCodigo`
- Spec: `docs/adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md`
- Prova viva: `tests/unit/test_alocacao_service.py:test_alocar_chamada_sucesso`
- Prova viva: `tests/unit/test_fila_service.py`
- Prova viva: `tests/unit/test_ring_timeout_task.py`
- Prova viva: `tests/unit/test_sweeper_task.py`
- Ver: `rg -n "resolver_ring_timeout" src/modules/queue/application/services/fila_service.py`
- Ver: `rg -n "alocar_chamada|alocar_proximo" src/modules/queue/infrastructure/lua/`

## Verificação

```bash
uv run pytest tests/unit/test_alocacao_service.py tests/unit/test_fila_service.py tests/unit/test_ring_timeout_task.py
```

## Ver também

- [Macro-Arquitetura (Overview)](overview.md)
- [Modelo de Dados (Data Model)](data-model.md)
- [Conformidade Clínica e Telemedicina](compliance-and-telemedicine.md)
- [Hexagonal Pragmático](../concepts/hexagonal-pragmatico.md)
- [Inter-Module Protocols](../concepts/inter-module-protocols.md)
- `docs/adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md`
- `docs/adrs/ADR-004-Worker-Assincrono-ARQ-sobre-Valkey.md`
