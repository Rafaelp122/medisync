# Concorrência, Motor de Fila Valkey e Ring Timeout (Concurrency & Queues)

> Mecanismo atômico de admissão, ordenação por ZSET no Valkey, alocação de chamadas via Lua e resolução determinística de no-show em `src/modules/queue/`.

| Metadado | Detalhamento |
| :--- | :--- |
| **Componentes Centrais** | Valkey 7+, Scripts Lua Atômicos, Sorted Sets (ZSET), ARQ Task Worker |
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

A fila é segregada por organização utilizando **Sorted Sets (ZSET)** do Valkey:
- **Namespace da Chave**: `fila:{organizacao_id}:aptos`
- **Membro (Member)**: ID do atendimento (`atendimento_id` em formato UUIDv7).
- **Pontuação (Score)**: Valor numérico inteiro de 64 bits calculado deterministicamente por prioridade clínica (níveis 1 a 5, onde menor valor numérico representa maior gravidade):

$$\text{Score} = (\text{prioridade\_clinica} \times 10^{12}) + \text{timestamp\_entrada\_epoch}$$

#### Desempate Determinístico FIFO via UUIDv7 (RN01)
Quando múltiplos pacientes chegam no mesmo segundo e possuem a mesma gravidade clínica, seus scores numéricos serão idênticos. O Valkey aplica o desempate por ordem lexicográfica do membro. Como o **UUIDv7** embute um timestamp Unix de 48 bits em milissegundos nos seus primeiros caracteres hexadecimais, a comparação lexicográfica do `atendimento_id` reflete rigorosamente a ordem cronológica real de acolhimento (FIFO), sem risco de estouro da mantissa do float de 64 bits.

A busca do próximo atendimento opera em tempo logarítmico $\mathcal{O}(\log N)$:
```redis
ZRANGE fila:{organizacao_id}:aptos 0 0
```

### 2. Alocação Atômica Médico-Paciente via Script Lua (RN02)

Para garantir que a verificação de disponibilidade do médico, a reserva exclusiva do paciente e a remoção da fila ocorram em uma única etapa indivisível sem race conditions, executa-se o script Lua atômico via `EVALSHA`:

```lua
-- KEYS[1]: lock:{org}:medico:{medico_id} | KEYS[2]: lock:{org}:atendimento:{atendimento_id} | KEYS[3]: fila:{org}:aptos
-- ARGV[1]: medico_id | ARGV[2]: atendimento_id | ARGV[3]: ttl_segundos (45s)
-- Retorno: 1 (Sucesso: locks ativados e removido do ZSET) | 0 (Conflito: médico ocupado - HTTP 409)
--         -1 (Indisponível: atendimento capturado concorrentemente - aciona retry em memória)
```
Script canônico em `src/modules/queue/infrastructure/lua/alocar_chamada.lua`.

Quando o script retorna `-1`, o serviço em Python executa um retry em memória (até 3 tentativas) buscando o próximo elemento retornado por `ZRANGE`.

### 3. Resolução Determinística de No-Show e Ciclo de Vida de Locks

Notificações pub/sub baseadas em expiração de chave (`notify-keyspace-events`) são *fire-and-forget* e podem atrasar ou se perder em reinicializações da API. Por isso, adota-se o agendamento de jobs diferidos com precisão de milissegundos no ARQ:

```python
await arq_pool.enqueue_job(
    "resolver_ring_timeout_task", organizacao_id=org_id,
    atendimento_id=str(atendimento_id), medico_id=str(medico_id),
    _defer_by=timedelta(seconds=45), _job_id=f"ring_timeout:{atendimento_id}",
)
```

No vencimento dos 45 segundos, o worker ARQ despacha a resolução delegando a transição de estado e limpeza de locks ao serviço de domínio:

```python
action = await fila_service.resolver_ring_timeout(
    organizacao_id=organizacao_id, atendimento_id=atend_uuid,
    medico_id=med_uuid, notifier=notifier,
)
```

#### Transição de Locks
1. **Fase de Toque (Ring - 45s)**: Protegida por `lock:{org}:medico:{medico_id}` com TTL de 45s.
2. **Fase de Teleconsulta (`EM_ATENDIMENTO`)**: Ao atender, o lock é promovido para `lock:{org}:consulta_ativa:medico:{medico_id}` com renovação por heartbeat da sessão WebRTC.
3. **Conclusão Clínica**: O lock é removido explicitamente quando o médico finaliza o atendimento (`CONCLUIDO`).

### 4. Controle de Admissão e Backpressure Estocástico (RN05)

O ingresso de novos atendimentos na fila virtual é preventivamente suspenso se:
1. **Ausência de Médicos**: $\text{Médicos Ativos} \le 0$.
2. **Cota Diária**: $\text{Total de Admissões do Dia} \ge \text{Cota Diária Máxima}$.
3. **Capacidade vs. Demanda Restante**:

$$\frac{\text{Pacientes Aguardando} \times \text{TMA Estimado} \times \alpha}{\text{Médicos Ativos no Turno}} > \text{Tempo Restante de Plantão}$$

Onde $\alpha$ representa a margem estocástica de segurança operacional ($1{,}20 \le \alpha \le 1{,}30$). Quando suspenso, o sistema dispara o evento `QUEUE_OVERFLOW_TRANSIT`.

### 5. Auto-Cura e Reconciliação (Sweeper Periódico)

Caso ocorra uma interrupção inesperada do servidor após o script Lua mas antes da persistência no banco, um sweeper periódico no ARQ executa a cada 60 segundos reconciliando atendimentos em `APTO_PARA_CHAMADA` órfãos no PostgreSQL de volta ao ZSET do Valkey com pontuação e prioridade originais.

## Onde no código

- Impl: `src/modules/queue/infrastructure/lua/alocar_chamada.lua:alocar_chamada`
- Impl: `src/modules/queue/application/services/alocacao_service.py:AlocacaoService.alocar_chamada`
- Impl: `src/modules/queue/application/services/fila_service.py:FilaService.resolver_ring_timeout`
- Impl: `src/modules/queue/application/services/controle_admissao_service.py:ControleAdmissaoService`
- Impl: `src/worker/tasks/ring_timeout.py:resolver_ring_timeout_task`
- Spec: `src/modules/queue/application/ports/allocation_port.py:AllocationPort`
- Spec: `docs/adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md`
- Prova viva: `tests/unit/test_alocacao_service.py:test_alocar_chamada_sucesso`
- Prova viva: `tests/unit/test_fila_service.py`
- Prova viva: `tests/unit/test_ring_timeout_task.py`
- Ver: `rg -n "resolver_ring_timeout" src/modules/queue/application/services/fila_service.py`
- Ver: `rg -n "alocar_chamada" src/modules/queue/infrastructure/lua/`

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
