# [ADR-005] Adoção do Motor de Tarefas Assíncronas ARQ sobre Valkey

| Metadado | Detalhe |
| :--- | :--- |
| **Status** | Aprovado |
| **Data** | 2026-09-13 |
| **Decisores** | Time de Arquitetura & Engenharia |
| **Referência SRS** | [SRS-001 v1.0](../srs/SRS-001-MediSync-Express.md) (RF-02, RNF-02, RNF-08) |

---

## 1. Contexto e Declaração do Problema

O backend do MediSync Express executa processamentos assíncronos em segundo plano que não devem bloquear o loop principal de eventos do FastAPI:
1. Consulta concorrente de elegibilidade em operadoras de saúde com recuo exponencial e timeout de 15 segundos (RF-02, RNF-02).
2. Agendamento diferido de verificação de abandono de chamada médica aos 45 segundos (RN02).
3. Retry assíncrono de assinaturas digitais ICP-Brasil com PSCs externos (RNF-06).

Precisamos escolher um framework de tarefas assíncronas que se integre nativamente ao runtime `asyncio` e mantenha a pegada de recursos reduzida para implantação em contêineres econômicos (RNF-08).

---

## 2. Drivers de Decisão

- **Compatibilidade Nativa com `asyncio`**: Executar tarefas assíncronas escritas como corrotinas Python sem bloqueios de thread.
- **Suporte a Tarefas Diferidas (*Deferred Jobs*)**: Capacidade de agendar execuções com atraso determinístico (`delay` em segundos).
- **Simplicidade Operacional**: Evitar a necessidade de instalar novos brokers de mensageria além do Valkey já presente na arquitetura.
- **Eficiência de Memória**: Baixo consumo de RAM para viabilizar execução em servidores com 2 GB de memória.

---

## 3. Opções Consideradas

### Opção 1: Celery com RabbitMQ
A solução mais tradicional no ecossistema Python.
- *Prós*: Ecossistema maduro, suporte a padrões complexos de workflow (Canvas).
- *Contras*: O Celery é historicamente síncrono e baseado em threads/processos pesados (o suporte a `asyncio` é precário); exige a adição do RabbitMQ (serviço em Erlang com alto consumo de memória) ou opera com limitações graves no Redis; viola o objetivo de inicialização em menos de 10 minutos em servidores modestos (RNF-08).

### Opção 2: Dramatiq / Huey
Alternativas modernas ao Celery com suporte a Redis.
- *Prós*: Menos verboso que o Celery.
- *Contras*: Huey e Dramatiq priorizam modelos síncronos com pools de threads, exigindo adaptações artificiais (`async_to_sync`) para reutilizar clientes `asyncpg` e `httpx` assíncronos.

### Opção 3: ARQ (`arq` sobre `redis-py` async)
Framework de fila de tarefas projetado especificamente para o modelo assíncrono moderno do Python, operando diretamente sobre o Redis/Valkey.
- *Prós*: 100% nativo em corrotinas `asyncio`; compartilha a mesma infraestrutura de cache Valkey existente; suporte nativo de primeira classe a jobs diferidos (`_defer_by=45`); deduplicação nativa via `_job_id`; compartilha sessões `asyncpg` e pools de conexões HTTP da aplicação; pegada de memória mínima (< 50 MB por worker).
- *Contras*: Comunidade menor que a do Celery, porém altamente estável e focada exclusivamente no ecossistema assíncrono.

---

## 4. Decisão

Adotamos a **Opção 3: ARQ sobre Valkey**.

### Diretrizes de Execução:
1. **Compartilhamento de Broker**: As filas do ARQ residem no mesmo cluster/instância Valkey utilizado pelo motor de filas em memória.
2. **Contexto Unificado**: O worker instancia um único contexto compartilhado (`WorkerSettings`) contendo a `session_factory` do SQLAlchemy assíncrono e clientes HTTP poolados.
3. **Padrão de Retries**: Falhas de comunicação externa (ex.: operadoras) utilizam retries com recuo exponencial assíncrono configurado via decorators do ARQ.

---

## 5. Consequências

### Positivas:
- **Zero Infraestrutura Adicional**: Não há necessidade de subir e manter instâncias RabbitMQ.
- **Código Coeso**: As tasks são funções `async def` comuns que utilizam os mesmos repositórios e serviços do monólito.
- **Alta Eficiência**: Um único processo worker gerencia centenas de tarefas concorrentes I/O-bound sem contenção de threads.

### Negativas / Riscos Mitigados:
- *Menos Plugins de Terceiros*: As necessidades do projeto (retries, timeouts, deferimento) são nativas do ARQ, eliminando a dependência de plugins adicionais.
