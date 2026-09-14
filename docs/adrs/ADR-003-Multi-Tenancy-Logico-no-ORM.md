# [ADR-003] Multi-Tenancy Lógico por Linha com Interceptação no ORM

| Metadado | Detalhe |
| :--- | :--- |
| **Status** | Aprovado |
| **Data** | 2026-09-13 |
| **Decisores** | Time de Arquitetura & Engenharia |
| **Referência SRS** | [SRS-001 v1.0](../srs/SRS-001-MediSync-Express.md) (RN-REG-02, RT-01) |

---

## 1. Contexto e Declaração do Problema

O **MediSync Express** é projetado para atender múltiplos municípios do SUS e operadoras privadas simultaneamente em uma mesma infraestrutura compartilhada.

Como lidamos com dados sensíveis de saúde protegidos pelo Art. 11 da LGPD, o vazamento de registros clínicos entre organizações acarreta severas sanções éticas, administrativas e penais. Precisamos de uma estratégia de multi-tenancy que garanta isolamento absoluto de dados sem inviabilizar os custos operacionais em servidores modestos.

---

## 2. Drivers de Decisão

- **Custo e Simplicidade de Infraestrutura**: Viabilidade de hospedar dezenas de pequenos municípios em uma única instância gerenciada de banco de dados.
- **Simplicidade de Migrações**: Aplicação unificada e atômica de migrações de esquema com Alembic sem a necessidade de rodar scripts em centenas de bancos separados.
- **Blindagem Contra Erro Humano**: Garantir que o isolamento ocorra de forma automática e transparente, sem depender de o desenvolvedor lembrar de incluir cláusulas manuais `WHERE organizacao_id = X` em cada repositório.

---

## 3. Opções Consideradas

### Opção 1: Banco de Dados Físico por Tenant (Database-per-Tenant)
Cada organização possui sua própria instância ou banco de dados PostgreSQL isolado.
- *Prós*: Isolamento físico absoluto.
- *Contras*: Custo proibitivo de infraestrutura para cidades com menos de 30 mil habitantes; enorme complexidade operacional para aplicar migrações de esquema assíncronas em paralelo; pool de conexões saturado por bancos ociosos.

### Opção 2: Schema por Tenant (Schema-per-Tenant)
Um único banco de dados contendo múltiplos schemas PostgreSQL (`org_1`, `org_2`).
- *Prós*: Bom nível de isolamento lógico no banco.
- *Contras*: O Alembic não gerencia schemas dinâmicos de forma trivial; limite prático de conexões e tabelas no catálogo do PostgreSQL; migrações lentas à medida que novos tenants são criados.

### Opção 3: Multi-Tenancy Lógico por Linha com Defesa em Profundidade (ORM + PostgreSQL RLS)
Todas as tabelas compartilham a coluna discriminadora `organizacao_id`. A segurança opera em duas camadas complementares:
1. **Camada de Aplicação (ORM Hook)**: O SQLAlchemy 2.0 intercepta as consultas no evento `do_orm_execute` e injeta compulsoriamente o filtro do tenant ativo, extraído de uma `ContextVar` populada no middleware de autenticação.
2. **Camada de Dados (PostgreSQL RLS Nativo)**: Cada conexão/transação executa `SET LOCAL app.current_tenant_id = :id`. O motor do banco aplica políticas nativas de Row-Level Security (`ENABLE ROW LEVEL SECURITY; FORCE ROW LEVEL SECURITY`), blindando o acesso mesmo contra queries SQL brutas (`text()`), inserções em massa ou joins complexos.
- *Prós*: Custo operacional mínimo (única base compartilhada); segurança em profundidade sem pontos cegos (nem consultas SQL puras conseguem vazar dados entre organizações); migrações atômicas e instantâneas com Alembic.
- *Contras*: Exige configuração das políticas RLS no PostgreSQL e listener de checkout de conexão para setar a variável de sessão.

---

## 4. Decisão

Adotamos a **Opção 3: Multi-Tenancy Lógico por Linha com Defesa em Profundidade (ORM Listener + PostgreSQL RLS Nativo)**.

### Diretrizes de Execução:
1. **Propagação de Contexto**: O middleware JWT extrai a claim `org_id` e a armazena em `tenant_context_var: ContextVar[int | None]`.
2. **Sessão do Banco de Dados**: No checkout de cada transação do SQLAlchemy/asyncpg, a sessão executa compulsoriamente:
   ```sql
   SET LOCAL app.current_tenant_id = :tenant_id;
   ```
3. **Políticas de Row-Level Security (RLS)**: Todas as tabelas multi-tenant possuem RLS ativado e forçado:
   ```sql
   ALTER TABLE atendimentos ENABLE ROW LEVEL SECURITY;
   ALTER TABLE atendimentos FORCE ROW LEVEL SECURITY;
   CREATE POLICY tenant_isolation_policy ON atendimentos
     USING (organizacao_id = NULLIF(current_setting('app.current_tenant_id', true), '')::bigint)
     WITH CHECK (organizacao_id = NULLIF(current_setting('app.current_tenant_id', true), '')::bigint);
   ```
4. **Interceptação no ORM (`do_orm_execute`)**: Atua como otimizador de primeira camada, injetando `WHERE organizacao_id = :tenant_id` nas árvores de compilação do SQLAlchemy antes do envio à rede.
5. **Escape Declarativo para Rotinas Globais**: Tarefas do sistema que precisam acessar dados globais (como workers de reconciliação) usam a flag explícita `execution_options(ignorar_tenant=True)` e executam `RESET app.current_tenant_id`.

---

## 5. Consequências

### Positivas:
- **Blindagem Absoluta (Defesa em Profundidade)**: O isolamento não depende da disciplina do desenvolvedor; consultas via `text()`, bulk inserts ou subqueries complexas são contidas no nível do motor do PostgreSQL 16.
- **Custo Mínimo**: Permite disponibilizar o sistema para pequenos municípios do SUS com custo de hospedagem próximo de zero.
- **Migrações Ágeis**: Atualizações de banco levam segundos via pipeline de CI/CD.

### Negativas / Riscos Mitigados:
- *Overhead de Sessão*: O `SET LOCAL app.current_tenant_id` é uma operação ultraleve em memória de sessão de conexão do PostgreSQL, com impacto de latência $< 0{,}2\text{ ms}$.
