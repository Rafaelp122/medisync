# [ADR-003] Multi-Tenancy Lógico com Defesa em Profundidade no PostgreSQL (RLS)

| Metadado | Detalhe |
| :--- | :--- |
| **Status** | **Superseded** por [ADR-013](ADR-013-Simplificacao-Plataforma-Unica-e-Remocao-RLS.md) |
| **Data** | 2026-09-30 (Substituída em 2026-11-20) |
| **Decisores** | Time de Arquitetura & Engenharia |
| **Referência** | [ADR-013](ADR-013-Simplificacao-Plataforma-Unica-e-Remocao-RLS.md), [Overview](../explanation/architecture/overview.md), [Data Model](../explanation/architecture/data-model.md) (RN-REG-02, RNF-05) |

> **Aviso Histórico:** Esta ADR foi substituída pela [ADR-013](ADR-013-Simplificacao-Plataforma-Unica-e-Remocao-RLS.md), que simplificou o MediSync Express para o modelo nativo de **Plataforma Única**, removendo `organizacoes`, `organizacao_id`, `X-Tenant-ID`, `TenantResolutionMiddleware`, `ContextVar` de tenant e políticas PostgreSQL RLS. O texto abaixo permanece apenas como registro histórico da decisão original.

---

## 1. Contexto e Declaração do Problema

O **MediSync Express** opera em modelo multi-tenant atendendo simultaneamente municípios e consórcios públicos intermunicipais do SUS (ADR-012), além de permitir implantação dedicada a um único município (modo single-tenant configurável). Tratando-se de dados sensíveis de saúde (Art. 11 da LGPD), é mandatório garantir que nenhum usuário, query de relatório ou falha em código de aplicação consiga vazar prontuários de uma organização para outra.

---

## 2. Drivers de Decisão

* **Custo e Simplicidade Operacional**: A plataforma deve rodar com eficiência em servidores modestos (1 a 2 vCPUs) em pequenos municípios, inviabilizando a gestão de centenas de bancos separados.
* **Defesa em Profundidade**: O isolamento não pode depender exclusivamente da boa vontade do desenvolvedor em lembrar de colocar `where(organizacao_id == X)` em todas as queries.
* **Agilidade em Migrações**: Aplicação de novas versões de banco em segundos em um único schema compartilhado.

---

## 3. Opções Consideradas

### Opção 1: Banco de Dados Dedicado por Tenant (Database-per-Tenant)
* *Prós*: Isolamento físico máximo.
* *Contras*: Custo proibitivo de infraestrutura, exaustão rápida de pools de conexão e pesadelo de manutenção para dezenas de instâncias municipais.

### Opção 2: Schema Dedicado por Tenant (Schema-per-Tenant)
* *Prós*: Isolamento lógico em tabelas separadas.
* *Contras*: Execução de migrações do Alembic repetida em loops lentos sobre centenas de schemas; problemas de *search_path*.

### Opção 3: Tabela Compartilhada com Defesa em Profundidade (ContextVar + Postgres RLS) (Adotada)
* *Prós*: Coluna discriminadora `organizacao_id` combinada com **Row-Level Security (RLS)** nativo do PostgreSQL 17. O middleware HTTP injeta o tenant em um `ContextVar` e a sessão assíncrona executa `SET LOCAL app.current_tenant_id = X`. Caso o código da aplicação execute um `SELECT * FROM pacientes` sem cláusula `WHERE`, o kernel do PostgreSQL filtra automaticamente apenas as linhas da organização ativa.
* *Contras*: Exige configuração explícita de políticas de RLS e suporte a superusuário/bypass restrito em scripts de migração.

---

## 4. Decisão

Adotamos a **Opção 3: Multi-Tenancy Lógico com Defesa em Profundidade via PostgreSQL RLS**.

### Diretrizes de Execução:
1. Todas as tabelas multi-tenant (inclusive `dependentes` e `documento_itens`) contêm `organizacao_id BIGINT NOT NULL` indexada diretamente.
2. Políticas `tenant_isolation_*` declaradas e habilitadas com `ENABLE ROW LEVEL SECURITY` e `FORCE ROW LEVEL SECURITY` em 100% das tabelas, eliminando bloqueios silenciosos (*silent deny*).
3. Listener do SQLAlchemy injeta o comando `SET LOCAL app.current_tenant_id` no início de cada transação assíncrona.
4. **Modo Multi-Tenant vs. Single-Tenant Opcional (IoC via Settings)**:
   - Por padrão (`MULTI_TENANCY_ENABLED=True`), o `TenantResolutionMiddleware` resolve o tenant estritamente na ordem `X-Tenant-ID` $\to$ JWT Bearer $\to$ subdomínio, sem fallback silencioso (`DEFAULT_TENANT_ID` deve ser `None`).
   - Em implantações dedicadas a uma única prefeitura/unidade (`MULTI_TENANCY_ENABLED=False`), `DEFAULT_TENANT_ID` ($\ge 1$) era validado em *fail-fast* no boot e injetado no antigo `TenantResolutionMiddleware` (posteriormente removido na [ADR-013](ADR-013-Simplificacao-Plataforma-Unica-e-Remocao-RLS.md)).

---

## 5. Consequências

### Positivas:
* **Segurança Imutável contra Vazamento**: Mesmo em caso de bug de aplicação ou SQL injection de leitura, o banco bloqueia o acesso cruzado entre organizações.
* **Baixíssimo Custo Operacional**: Roda em um único banco de dados otimizado com pool compartilhado.
* **Migrações Instantâneas**: Alembic executa em segundos em um único schema.
