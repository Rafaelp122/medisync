# Concorrência, Motor de Fila Valkey e Ring Timeout (Concurrency & Queues)

## MediSync Express — Plataforma de Código Aberto para Pronto-Atendimento Virtual (PA Digital 24/| **Metadado** | Detalhamento |
| :--- | :--- |
| **Componentes Centrais** | Valkey 7+, Scripts Lua Atômicos, Sorted Sets (ZSET), ARQ Task Worker |
| **Padrão de Concorrência** | Alocação Atômica por Script Lua com Lock Duplo Temporizado (45 segundos) |
| **Identificadores de Fila** | UUIDv7 (RFC 9562) com Desempate Determinístico FIFO Sub-Milissegundo |
| **Resolução de No-Show** | Ring Timeout Determinístico via Jobs Diferidos (`_defer_by=45`) no ARQ |
| **Status** | Aprovado (Documento Vivo de Engenharia) |

---

## 1. Desafios Críticos de Concorrência

Em uma unidade de Pronto-Atendimento Virtual com múltiplos médicos plantonistas atendendo simultaneamente em alta demanda:
1. **Risco de Overbooking (Race Condition)**: Dois ou mais médicos clicarem em *"Chamar Próximo"* no mesmo milissegundo e receberem o mesmo paciente.
2. **Contenção Relacional**: Tentar ordenar filas clínicas em tempo real com `SELECT ... FOR UPDATE` no PostgreSQL sob concorrência degrada o tempo de resposta, violando o SLA de $\le 200\text{ ms}$ (RNF-01).
3. **Deadlocks Operacionais por No-Show**: Quando o paciente chamado não atende, o médico não pode ficar com a tela travada indefinidamente.

---

## 2. Estrutura de Dados e Indexação da Fila em Memória

A fila é segregada por organização utilizando **Sorted Sets (ZSET)** do Valkey:

* **Namespace da Chave**: `fila:{organizacao_id}:aptos`
* **Membro (Member)**: ID do atendimento (`atendimento_id` em formato string UUIDv7).
* **Pontuação (Score)**: Valor numérico inteiro de 64 bits calculado deterministicamente para garantir ordenação por prioridade clínica (níveis 1 a 5, onde menor valor numérico representa maior gravidade):

$$\text{Score} = (\text{prioridade\_clinica} \times 10^{12}) + \text{timestamp\_entrada\_epoch}$$

*Exemplo*:
* Paciente Nível 2 (Laranja - Muito Urgente) entrado às 14:00:00 (`1726250000`):  
  $\text{Score} = (2 \times 10^{12}) + 1726250000 = 2001726250000$
* Paciente Nível 4 (Verde - Pouco Urgente) entrado 10 minutos antes (`1726249400`):  
  $\text{Score} = (4 \times 10^{12}) + 1726249400 = 4001726249400$

### 2.1 Desempate Determinístico FIFO via UUIDv7 (RN01)
Quando múltiplos pacientes chegam no mesmo segundo e possuem a mesma gravidade clínica, seus scores numéricos serão idênticos. O Valkey aplica nativamente o critério de desempate por **ordem lexicográfica do membro**. 

Como o **UUIDv7** embute um timestamp Unix de 48 bits em milissegundos nos seus primeiros caracteres hexadecimais (ex.: `01924b...`), a comparação lexicográfica do `atendimento_id` reflete rigorosamente a ordem cronológica real de acolhimento (FIFO). Isso garante o cumprimento inalienável da invariante **RN01** em nível de milissegundos sem risco de estouro da mantissa do float de 64 bits.

A busca do próximo atendimento mais urgente opera em tempo logarítmico $\mathcal{O}(\log N)$:
```redis
ZRANGE fila:{organizacao_id}:aptos 0 0
```

---

## 3. Alocação Atômica Médico-Paciente via Script Lua (RN02)

Para garantir que a verificação de disponibilidade do médico, a reserva exclusiva do paciente e a remoção da fila ocorram em uma única etapa indivisível, adota-se um script Lua executado no Valkey via comando `EVALSHA`.

### 3.1 Script de Alocação (`src/modules/queue/infrastructure/lua/alocar_chamada.lua`)

```lua
-- KEYS[1]: lock:{org_id}:medico:{medico_id}
-- KEYS[2]: lock:{org_id}:atendimento:{atendimento_id}
-- KEYS[3]: fila:{org_id}:aptos
-- ARGV[1]: medico_id
-- ARGV[2]: atendimento_id
-- ARGV[3]: ttl_segundos (padrão: 45)

-- 1. Verifica se o médico chamador já possui lock ativo (bloqueio do profissional)
if redis.call('EXISTS', KEYS[1]) == 1 then
    return 0 -- Conflito: médico já ocupado com chamada ou consulta em andamento (HTTP 409)
end

-- 2. Verifica se o atendimento pretendido já foi capturado por outro médico
if redis.call('EXISTS', KEYS[2]) == 1 then
    return -1 -- Atendimento já reservado simultaneamente (aciona retry na aplicação)
end

-- 3. Confirma se o atendimento ainda está de fato presente na fila de aptos
local rank = redis.call('ZRANK', KEYS[3], ARGV[2])
if not rank then
    return -1 -- Atendimento não disponível mais na fila (aciona retry na aplicação)
end

-- 4. Remove atomicamente da fila e aplica ambos os locks vinculados com TTL de ring
redis.call('ZREM', KEYS[3], ARGV[2])
redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
redis.call('SET', KEYS[2], ARGV[1], 'EX', ARGV[3])

return 1 -- Alocação atômica confirmada com sucesso
```

### 3.2 Interpretação Rigorosa dos Códigos de Retorno
* **`1` (Sucesso)**: O atendimento foi reservado exclusivamente para o médico, removido da fila pública e os locks duplos de 45s foram ativados.
* **`0` (Conflito de Lock do Médico)**: O médico chamador já possui uma chamada ou teleconsulta ativa. A API rejeita com HTTP 409 (Conflict), impedindo sobreposição de atendimentos pelo mesmo profissional (RN02).
* **`-1` (Atendimento Indisponível / Concorrência Concorrente)**: O atendimento pretendido foi reservado por outro médico milissegundos antes ou retirado da fila. O serviço em Python **não** emite erro 409; ele executa imediatamente um loop de *retry* em memória (até 3 iterações) buscando o próximo elemento retornado por `ZRANGE fila:{org}:aptos 0 0`.

---

## 4. Resolução Determinística de No-Show e Ciclo de Vida de Locks

### 4.1 Por que `notify-keyspace-events` do Redis Falha para No-Show?
Mecanismos baseados em expiração de chaves pub/sub do Redis são inadequados para fluxos críticos de saúde:
1. Notificações do Redis são do tipo *fire-and-forget*; se a API estiver reiniciando, o evento de expiração é perdido.
2. A expiração do Redis ocorre por amostragem passiva em segundo plano ou no acesso à chave, podendo atrasar segundos ou minutos além do tempo programado.

### 4.2 A Solução: Jobs Diferidos no ARQ (`_defer_by=45`)

Imediatamente após o script Lua alocar o paciente, a API agenda uma tarefa no ARQ com precisão de milissegundos:

```python
await arq_pool.enqueue_job("resolver_ring_timeout_task", organizacao_id=org_id,
    atendimento_id=atendimento_id, medico_id=medico_id,
    _defer_by=timedelta(seconds=45),
    _job_id=f"ring_timeout:{atendimento_id}")
```
Ver chamada real em `src/modules/queue/application/services/alocacao_service.py`.

### 4.3 Tarefa do Worker (`resolver_ring_timeout_task`)

```python
atendimento = await session.get(Atendimento, atendimento_id)
if atendimento.status == "CHAMANDO_PACIENTE":
    atendimento.registrar_no_show()
    await session.commit()
```
Ver worker completo em `src/worker/tasks/ring_timeout.py`.

### 4.4 Transição de Locks: Ring Timeout vs. Teleconsulta Ativa (RN02)
Para assegurar a invariante de que um médico jamais possua duas consultas em andamento ao mesmo tempo:
1. **Fase de Toque (Ring - 45s)**: Protegida por `lock:{org}:medico:{medico_id}` com TTL de 45 segundos.
2. **Fase de Teleconsulta (`EM_ANDAMENTO`)**: Quando o paciente atende a chamada e a videoconferência WebRTC é iniciada, o endpoint de atendimento renova e promove o lock do médico para `lock:{org}:consulta_ativa:medico:{medico_id}` com TTL seguro de contingência (ex.: 2 horas) e mecanismo de heartbeat da sessão de telemedicina.
3. **Conclusão Clínica**: O lock é removido explicitamente no momento em que o médico finaliza o atendimento (`CONCLUIDO`) e assina o prontuário.

---

## 5. Controle de Admissão e Backpressure Estocástico (RN05)

O ingresso de novos atendimentos na fila virtual é suspenso preventivamente se:

1. **Ausência de Médicos**: $\text{Médicos Ativos} \le 0$ (previne divisão por zero e represamento).
2. **Cota Diária**: $\text{Total de Admissões do Dia} \ge \text{Cota Diária Máxima}$.
3. **Capacidade vs. Demanda Restante**:
   $$\frac{\text{Pacientes Aguardando} \times \text{TMA Estimado} \times \alpha}{\text{Médicos Ativos no Turno}} > \text{Tempo Restante de Plantão}$$

* Onde $\alpha$ representa a margem estocástica de segurança operacional ($1{,}20 \le \alpha \le 1{,}30$).
* Quando suspenso, o sistema dispara o evento de transbordo `QUEUE_OVERFLOW_TRANSIT` para integração com centrais de regulação ou envio de orientações aos pacientes.

---

## 6. Auto-Cura e Reconciliação (Sweeper Periódico)

Para mitigar o risco de inconsistência transacional entre o Valkey e o PostgreSQL (caso ocorra um crash do servidor exatamente após o script Lua mas antes do commit no banco), um cron no ARQ executa a cada 60 segundos uma rotina de auto-cura:

* Varre atendimentos no banco com status `APTO_PARA_CHAMADA` sem atualização há mais de 60 segundos.
* Se o atendimento não estiver presente no ZSET do Valkey nem possuir locks de chamada ativos, o reinjeta automaticamente no ZSET com prioridade e timestamp originais preservados.
