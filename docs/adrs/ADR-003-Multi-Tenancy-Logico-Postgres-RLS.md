# [ADR-003] Multi-Tenancy Lógico com Defesa em Profundidade no PostgreSQL (RLS)

| Metadado | Detalhe |
| :--- | :--- |
| **Status** | Aprovado |
| **Data** | 2026-09-30 |
| **Decisores** | Time de Arquitetura & Engenharia |
| **Referência** | [Overview](../03-architecture/overview.md), [Data Model](../03-architecture/data-model.md) (RN-REG-02, RNF-05) |

---

## 1. Contexto e Declaração do Problema

O **MediSync Express** opera em modelo multi-tenant atendendo simultaneamente municípios do SUS e instituições de saúde privadas. Tratando-se de dados sensíveis de saúde (Art. 11 da LGPD), é mandatório garantir que nenhum usuário, query de relatório ou falha em código de aplicação consiga vazar prontuários de uma organização para outra.

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
* *Prós*: Coluna discriminadora `organizacao_id` combinada com **Row-Level Security (RLS)** nativo do PostgreSQL 16. O middleware HTTP injeta o tenant em um `ContextVar` e a sessão assíncrona executa `SET LOCAL app.current_tenant_id = X`. Caso o código da aplicação execute um `SELECT * FROM pacientes` sem cláusula `WHERE`, o kernel do PostgreSQL filtra automaticamente apenas as linhas da organização ativa.
* *Contras*: Exige configuração explícita de políticas de RLS e suporte a superusuário/bypass restrito em scripts de migração.

---

## 4. Decisão

Adotamos a **Opção 3: Multi-Tenancy Lógico com Defesa em Profundidade via PostgreSQL RLS**.

### Diretrizes de Execução:
1. Todas as tabelas multi-tenant (inclusive `dependentes` e `documento_itens`) contêm `organizacao_id BIGINT NOT NULL` indexada diretamente.
2. Políticas `tenant_isolation_*` declaradas e habilitadas com `ENABLE ROW LEVEL SECURITY` e `FORCE ROW LEVEL SECURITY` em 100% das tabelas, eliminando bloqueios silenciosos (*silent deny*).
3. Listener do SQLAlchemy injeta o comando `SET LOCAL app.current_tenant_id` no início de cada transação assíncrona.

---

## 5. Consequências

### Positivas:
* **Segurança Imutável contra Vazamento**: Mesmo em caso de bug de aplicação ou SQL injection de leitura, o banco bloqueia o acesso cruzado entre organizações.
* **Baixíssimo Custo Operacional**: Roda em um único banco de dados otimizado com pool compartilhado.
* **Migrações Instantâneas**: Alembic executa em segundos em um único schema.
