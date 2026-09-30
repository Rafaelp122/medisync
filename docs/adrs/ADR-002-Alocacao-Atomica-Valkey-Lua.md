# [ADR-002] Alocação Atômica de Chamadas via Valkey Sorted Sets e Scripts Lua

| Metadado | Detalhe |
| :--- | :--- |
| **Status** | Aprovado |
| **Data** | 2026-09-30 |
| **Decisores** | Time de Arquitetura & Engenharia |
| **Referência** | [Overview](../03-architecture/overview.md), [Concorrência](../03-architecture/concurrency-and-queues.md) (RN01, RN02, RNF-01) |

---

## 1. Contexto e Declaração do Problema

Em pronto-atendimento virtual com múltiplos médicos chamando pacientes simultaneamente em alta demanda:
1. **Risco Crítico de Overbooking**: Dois médicos clicarem em *"Chamar Próximo"* simultaneamente e receberem o mesmo paciente.
2. **Tempo de Resposta**: A reordenação contínua da fila e a captura da trava devem ocorrer em $\le 200\text{ ms}$ (RNF-01).
3. **Escalabilidade Multi-Processo**: A solução precisa funcionar com múltiplos workers Uvicorn e réplicas de contêineres sem depender de travas em memória de um único processo Python.

---

## 2. Drivers de Decisão

* **Atomicidade Estrita**: A busca do próximo paciente mais urgente, a trava do médico, a trava do paciente e a remoção da fila devem ocorrer em uma única operação indivisível.
* **Complexidade Algorítmica**: Busca e ordenação em $\mathcal{O}(\log N)$ em vez de varreduras lineares $\mathcal{O}(N)$ no banco.
* **Licenciamento Open Source Permissivo**: Utilização de ferramentas sob licenças livres comunitárias sem restrições proprietárias.

---

## 3. Opções Consideradas

### Opção 1: Travas Transacionais no PostgreSQL (`SELECT ... FOR UPDATE SKIP LOCKED`)
* *Prós*: Não introduz componente adicional de infraestrutura.
* *Contras*: Contenção intensa de I/O em disco sob rajadas de concorrência, risco de deadlocks em transações concorrentes e lentidão que viola o teto de 200 ms.

### Opção 2: Travas em Memória no Processo Python (`asyncio.Lock`)
* *Prós*: Desempenho em nanossegundos em teste local.
* *Contras*: Inviável em produção, pois não sincroniza múltiplos workers do Uvicorn nem múltiplos nós de contêiner.

### Opção 3: Valkey 7+ com Sorted Sets (ZSET) e Script Lua Atômico (Adotada)
* *Prós*: Operação indivisível em motor single-threaded em memória; pontuação determinística de 64 bits combinando prioridade e timestamp; lock duplo (`lock:medico`, `lock:atendimento`) com TTL de 45 segundos; licença BSD 3-Clause permissiva (Linux Foundation).
* *Contras*: Exige manutenção de servidor Valkey em memória e reconciliação com o PostgreSQL.

---

## 4. Decisão

Adotamos a **Opção 3: Valkey 7+ com ZSET e Script Lua Atômico (`alocar_chamada.lua`)**.

### Diretrizes de Execução:
1. Fila indexada no ZSET com chave `fila:{organizacao_id}:aptos`, score ponderado de 64 bits e membros em string UUIDv7.
2. Desempate FIFO nativo em nível de milissegundos via ordenação lexicográfica de UUIDv7 (RN01).
3. Execução atômica via `EVALSHA` com códigos de retorno discriminados: `0` para médico ocupado (HTTP 409) e `-1` para atendimento capturado simultaneamente (aciona retry automático na aplicação).
4. Locks duplos de 45 segundos para médico e paciente durante a fase de ring, promovidos a lock de consulta ativa (`EM_ANDAMENTO`) quando o paciente atende.
5. Auto-cura garantida por persistência AOF (`--appendonly yes`) e reconciliação periódica no ARQ.

---

## 5. Consequências

### Positivas:
* **Zero Race Conditions**: Eliminação matemática de duplicidade de chamadas.
* **Desempenho Sub-Milissegundo**: Alocação concluída em $< 10\text{ ms}$, muito abaixo da meta de 200 ms.
* **Tolerância a Falhas**: Locks expiram por TTL caso o nó da API sofra uma queda repentina.
