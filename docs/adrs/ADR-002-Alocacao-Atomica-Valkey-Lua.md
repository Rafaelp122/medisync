# [ADR-002] Alocação Atômica de Chamadas via Valkey Sorted Sets e Scripts Lua

| Metadado | Detalhe |
| :--- | :--- |
| **Status** | Aprovado |
| **Data** | 2026-09-13 |
| **Decisores** | Time de Arquitetura & Engenharia |
| **Referência SRS** | [SRS-001 v1.0](../srs/SRS-001-MediSync-Express.md) (RN01, RN02, RNF-01) |

---

## 1. Contexto e Declaração do Problema

No regime de demanda espontânea do PA Virtual, dezenas de médicos plantonistas podem clicar simultaneamente no botão *"Chamar Próximo"*. 

Duas falhas graves de integridade concorrente precisam ser prevenidas com latência $\le 200\text{ ms}$ (RNF-01):
1. **Overbooking de Médico (RN02)**: O mesmo médico ter duas chamadas ou teleconsultas atribuídas a ele simultaneamente.
2. **Dupla Alocação de Paciente**: Dois médicos receberem o mesmo paciente no exato mesmo milissegundo.

---

## 2. Drivers de Decisão

- **Latência de Alocação**: Reordenação e lock em tempo $\le 200\text{ ms}$ sob concorrência intensa (RNF-01).
- **Consistência Estrita**: Zero possibilidade de race condition ou deadlocks de chamadas.
- **Ordem Clínica FIFO com Prioridade**: Pacientes mais graves são sempre atendidos primeiro; em caso de empate de gravidade, respeita-se a cronologia estrita de entrada (RN01).

---

## 3. Opções Consideradas

### Opção 1: Bloqueio Transacional no PostgreSQL (`SELECT ... FOR UPDATE`)
Utilizar transações de banco com `SELECT id FROM atendimentos WHERE status = 'APTO' ORDER BY prioridade, data_criacao LIMIT 1 FOR UPDATE SKIP LOCKED`.
- *Prós*: Não requer serviço adicional de memória em cache; persistência imediata no banco.
- *Contras*: Em alta concorrência de médicos e pacientes sendo inseridos, gera contenção de escrita de disco e locks em tabelas transacionais, elevando a latência para 400 ms a 1,2 s sob pico e violando o RNF-01 ($\le 200\text{ ms}$).

### Opção 2: Locks Distribuídos no Python (Redlock)
Adquirir múltiplos locks no Redis/Valkey através da biblioteca Python antes de consultar o banco.
- *Prós*: Evita sobrecarga direta de escrita no banco.
- *Contras*: Exige múltiplos round-trips de rede entre o backend e o Redis para cada etapa (verificar médico, verificar paciente, remover da fila), aumentando a latência e a complexidade de liberação de locks parciais em falha.

### Opção 3: Atomicidade Nativa via Sorted Sets (ZSET) e Script Lua no Valkey
Armazenar a fila ativa de aptos em um Sorted Set no Valkey com score determinístico $(prioridade \times 10^{12}) + timestamp$. A remoção da fila e a aplicação simultânea dos locks com TTL de 45 segundos ocorrem em um único script Lua (`alocar_chamada.lua`) executado atomicamente pelo motor single-threaded do Valkey.
- *Prós*: Complexidade $\mathcal{O}(\log N)$, execução em menos de 5 ms no Valkey, zero possibilidade de race condition (o script Lua é atômico e indivisível) e garantia de que nenhum outro nó pode intervir entre a leitura e a escrita.
- *Contras*: O estado volátil da fila em memória precisa de mecanismo de persistência e auto-cura em caso de reinicialização do Valkey.

---

## 4. Decisão

Adotamos a **Opção 3: Sorted Sets e Scripts Lua no Valkey**.

### Diretrizes de Execução:
1. **Namespace por Tenant**: Cada organização opera com chave isolada `fila:{organizacao_id}:aptos`.
2. **Lock Duplo com TTL de 45s**: O script Lua trava `lock:{org}:medico:{medico_id}` e `lock:{org}:atendimento:{atendimento_id}` simultaneamente.
3. **Persistência AOF**: Valkey configurado com `--appendonly yes --appendfsync everysec`.
4. **Reconciliação no Startup**: Durante o lifespan do FastAPI, uma rotina varre o PostgreSQL e reinsere no Valkey todos os atendimentos com status `APTO_PARA_CHAMADA`, tornando o sistema imune à perda de cache.
5. **Mitigação do Dual-Write Hazard (Reconciliador Periódico a Cada 60s)**: Caso ocorra um crash abrupto do processo Python após o script Lua remover o paciente da fila mas antes de o commit transacional gravar `CHAMANDO_PACIENTE` no PostgreSQL ou antes de enfileirar o job no ARQ, um worker periódico leve roda a cada 60 segundos buscando atendimentos com status `APTO_PARA_CHAMADA` que não estejam no ZSET do Valkey nem com locks ativos de atendimento, reinjetando-os na fila com pontuação e timestamp originais (*self-healing*).

---

## 5. Consequências

### Positivas:
- **Desempenho Excepcional**: A operação completa de busca e trava atômica ocorre em $< 10\text{ ms}$, cumprindo o RNF-01 com folga de mais de 90%.
- **Zero Overbooking**: Impossibilidade matemática de dois médicos receberem o mesmo paciente ou de um médico prender duas chamadas ativas.

### Negativas / Riscos Mitigados:
- *Dependência de Memória & Risco de Limbo Transacional (Dual-Write)*: Mitigados pela persistência AOF, reconciliação declarada no startup e pelo worker de integridade periódico (*self-healing sweeper* a cada 60s).
