# [ADR-006] Resolução de No-Show com Ring Timeout Determinístico via Jobs Diferidos no ARQ

| Metadado | Detalhe |
| :--- | :--- |
| **Status** | Aprovado |
| **Data** | 2026-09-13 |
| **Decisores** | Time de Arquitetura & Engenharia |
| **Referência SRS** | [SRS-001 v1.0](../srs/SRS-001-MediSync-Express.md) (RN02, RF-03, NEC-04) |

---

## 1. Contexto e Declaração do Problema

Quando um médico plantonista aciona o chamado de um paciente, o sistema concede uma janela de tolerância de **exatamente 45 segundos** (ring timeout). Caso o paciente não estabeleça a conexão de áudio/vídeo nesse período, o atendimento deve ser marcado como `PACIENTE_AUSENTE` e o médico liberado imediatamente para nova chamada (invariante RN02).

Se o mecanismo de contagem desse tempo for impreciso ou falhar:
- A tela do médico permanece travada aguardando indefinidamente (*deadlock operacional*).
- Se dois timers concorrentes forem disparados, pode ocorrer transição inválida de estado após o paciente já ter atendido a chamada.

---

## 2. Drivers de Decisão

- **Precisão Temporal e Determinismo**: Execução pontual aos 45 segundos, independente de o médico fechar o navegador.
- **Idempotência Estrita**: Se o paciente atender no segundo 30, o timer de 45 segundos não pode prejudicar a consulta em andamento.
- **Tolerância a Falhas**: Sobreviver a reinicializações de contêineres sem perder o agendamento da checagem.

---

## 3. Opções Consideradas

### Opção 1: Espera Síncrona na Conexão HTTP (`asyncio.sleep(45)`)
Manter a requisição HTTP aberta no FastAPI segurando o processamento por 45 segundos.
- *Prós*: Fácil de escrever.
- *Contras*: Extremamente frágil. Se o médico recarregar a aba ou houver oscilação de rede, a conexão TCP é cancelada e o evento de no-show nunca é disparado; bloqueia conexões do servidor desnecessariamente.

### Opção 2: Notificações de Chaves Expiradas do Redis/Valkey (`__keyevent@0__:expired`)
Definir chave com TTL de 45 segundos no Valkey e assinar o tópico de expiração via Pub/Sub.
- *Prós*: Mecanismo nativo do Redis.
- *Contras*: A expiração de chaves no Redis/Valkey é **preguiçosa e probabilística** (o Redis só varre periodicamente uma amostra de chaves expiradas ou espera a chave ser acessada); a entrega de mensagens Pub/Sub não é garantida se o listener estiver momentaneamente desconectado; o evento de expiração não envia o valor da chave, apenas o nome.

### Opção 3: Job Diferido Determinístico no ARQ (`_defer_by=45`)
No momento em que a rota `/chamar-proximo` tem sucesso no script Lua, enfileira-se no ARQ uma tarefa diferida com `_defer_by=45` e ID deduplicado `ring_timeout_{atendimento_id}`.
- *Prós*: Agendamento persistente em Sorted Set do ARQ; tolerante a reinicializações; execução determinística; no worker, a checagem é uma transição de estado idempotente:
  ```python
  if atendimento.status == StatusAtendimento.CHAMANDO_PACIENTE:
      atendimento.registrar_no_show()
      await liberar_locks_valkey()
  ```
  Se o status já tiver mudado para `EM_ANDAMENTO`, a task encerra silenciosamente como *no-op*.
- *Contras*: Pequena latência de polling do ARQ (configurada para 200 ms).

---

## 4. Decisão

Adotamos a **Opção 3: Job Diferido Determinístico no ARQ (`_defer_by=45`)**.

### Diretrizes de Execução:
1. **Deduplicação Obrigatória**: Toda chamada agenda com `_job_id=f"ring_timeout_{atendimento_id}"` para evitar enfileiramento duplo em caso de retentativas de rede.
2. **Idempotência**: A função de domínio `atendimento.registrar_no_show()` só atua se o status atual for estritamente `CHAMANDO_PACIENTE`.
3. **Limpeza Imediata de Locks**: A task remove as chaves `lock:{org}:medico:{medico_id}` e `lock:{org}:atendimento:{atendimento_id}` no Valkey, notificando o frontend do médico via WebSocket para desobstrução imediata de tela.

---

## 5. Consequências

### Positivas:
- **Zero Deadlocks de Tela**: O médico nunca fica bloqueado por mais de 45 segundos se o paciente não comparecer.
- **Rastreabilidade**: O evento de no-show é gravado na tabela imutável `audit_events` com timestamp UTC exato.

### Negativas / Riscos Mitigados:
- *Carga de Tarefas*: Cada chamada cria um job. Como o ARQ opera diretamente em memória com índices ZSET no Valkey, a vazão suporta milhares de chamadas por minuto sem gargalo.
