# [ADR-004] Adoção do Motor de Tarefas Assíncronas ARQ sobre Valkey

| Metadado | Detalhe |
| :--- | :--- |
| **Status** | Aprovado |
| **Data** | 2026-09-30 |
| **Decisores** | Time de Arquitetura & Engenharia |
| **Referência** | [Overview](../03-architecture/overview.md), [Concorrência](../03-architecture/concurrency-and-queues.md) (RN02, RNF-02) |

---

## 1. Contexto e Declaração do Problema

O pronto-atendimento virtual requer execução assíncrona de rotinas em segundo plano:
1. Resolução de no-show via ring timeout de exatamente 45 segundos (RN02).
2. Validação concorrente de elegibilidade de convênio (RF-02).
3. Auto-cura e reconciliação da fila em memória com o banco relacional a cada 60 segundos.

---

## 2. Drivers de Decisão

* **Integração Nativa com `asyncio`**: O ecossistema do FastAPI e SQLAlchemy Async é não-bloqueante; o worker deve operar em corrotinas assíncronas compartilhando pools de conexão.
* **Agendamento com Precisão Temporal (`_defer_by`)**: Capacidade de postergar a execução de uma tarefa por exatamente $N$ segundos sem bloquear threads.
* **Economia de Recursos de Infraestrutura**: Evitar a inclusão de brokers adicionais (como RabbitMQ) quando o Valkey já está presente na stack.

---

## 3. Opções Consideradas

### Opção 1: Celery com RabbitMQ
* *Prós*: Padrão de mercado para tarefas distribuídas pesadas.
* *Contras*: Arquitetura complexa e síncrona por natureza; exige brokers adicionais (RabbitMQ), alto consumo de memória e fricção para rodar corrotinas assíncronas puras.

### Opção 2: RQ (Redis Queue)
* *Prós*: Simples de configurar com Redis.
* *Contras*: Bloqueante, baseado em processos síncronos forçados (`fork`), sem suporte nativo a corrotinas do `asyncio`.

### Opção 3: ARQ sobre Valkey (Adotada)
* *Prós*: 100% nativo em `asyncio` em Python; reutiliza a instância do Valkey já presente no projeto; suporte nativo a jobs diferidos (`_defer_by=timedelta(seconds=45)`) com precisão de milissegundos; compartilha as mesmas conexões do `asyncpg` e `httpx.AsyncClient`.
* *Contras*: Menor quantidade de extensões prontas em relação ao Celery, mas suficiente e perfeito para o ecossistema assíncrono moderno.

---

## 4. Decisão

Adotamos a **Opção 3: ARQ Task Worker sobre Valkey**.

### Diretrizes de Execução:
1. Tarefas executadas em processo `arq worker.WorkerSettings`.
2. Ring Timeout de 45 segundos agendado com deduplicação de ID (`_job_id=f"ring_timeout:{atendimento_id}"`).
3. Reconciliação periódica de consistência executada a cada 60s via cron nativo do ARQ.

---

## 5. Consequências

### Positivas:
* **Zero Overhead de Brokers Adicionais**: Uma única infraestrutura de Valkey atende fila rápida e tarefas em background.
* **Alta Eficiência de CPU e Memória**: Dezenas de milhares de jobs simultâneos em uma única thread com corrotinas.
