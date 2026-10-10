# Estratégia de Testes (Testing Strategy)

> Filosofia, pirâmide de testes e garantias de isolamento no MediSync Express.

---

## 1. Visão Geral e Filosofia

No MediSync Express, os testes garantem conformidade clínica (CFM 2.314/2022, Portaria 344/98), robustez em alta concorrência médica (ADR-002) e isolamento multi-tenant estrito (RLS no PostgreSQL).

A estratégia de testes adota dois pilares fundamentais:
1. **Pirâmide Segregada Fail-Fast:** A validação rápida deve ocorrer sem I/O e sem infraestrutura de contêineres, falhando em poucos segundos antes de qualquer teste pesado de integração.
2. **Hexagonal Pragmático sem Mapper Hell (ADR-001):** Entidades SQLAlchemy 2.0 são modelos de domínio ricos. Testes unitários validam diretamente o comportamento do domínio sem necessidade de criar DTOs intermediários ou bancos em memória simulados imperfeitamente.

---

## 2. A Pirâmide de Testes MediSync

```
        / \
       /   \
      /  I  \    Testes de Integração (tests/integration/)
     /------- \   - PostgreSQL 16 com RLS ativo
    /    A    \   - Valkey 8.0 (Lua scripts atômicos)
   / ----------\  - MinIO S3 & LiveKit
  /      U      \ Testes Unitários & Arquiteturais (tests/unit/ & tests/architecture/)
 /---------------\ - 100% em memória, zero Docker, paralelos (-n auto)
```

### Camada U: Unitários e Arquitetura (`tests/unit/` & `tests/architecture/`)
* **Execução:** `just test-fast` ou `just test-unit`
* **Dependências Externas:** Zero contêineres Docker, zero rede, zero I/O de disco.
* **Escopo:**
  * Regras de negócio de modelos ricos (transições de status de atendimento, cálculo de score 64-bit, bloqueio de medicamentos Portaria 344/98).
  * Casos de uso e Services com dublês de teste canônicos (`tests/doubles.py` e mocks tipados).
  * Testes de arquitetura AST (`tests/architecture/test_routers_are_thin.py` e `tach check`), garantindo que routers permaneçam finos e camadas modulares sejam respeitadas.

### Camada I: Integração sobre Infraestrutura Real (`tests/integration/`)
* **Execução:** `just test-integration`
* **Dependências:** PostgreSQL (`localhost:5433`), Valkey (`localhost:6380`), MinIO e LiveKit rodando saudáveis.
* **Escopo:**
  * Políticas de segurança Row-Level Security (RLS) e troca de papéis (`SET LOCAL ROLE medisync_app`).
  * Concorrência real de 50 médicos concorrendo por pacientes via Lua scripts atômicos.
  * Tarefas do worker ARQ (expiração de ring timeout em 45s, reconciliação pelo sweeper).
  * Fluxo HTTP ponta a ponta via `AsyncClient` contra a aplicação FastAPI real.

---

## 3. Isolamento de Estado e Ciclo de Vida do Banco

### O Problema do DDL Destrutivo em Execuções Concorrentes
No passado, fixtures tentavam isolar testes executando `DROP SCHEMA public CASCADE;` ou chamadas ad-hoc de `Base.metadata.create_all`. Em execuções paralelas ou consecutivas, isso causava:
* Destruição de tabelas enquanto outros workers estavam rodando (`psycopg.errors.UndefinedTable`).
* Eliminação de roles DCL e grants de RLS necessários para a role `medisync_app`.

### O Padrão Canônico: `TRUNCATE TABLE ... CASCADE`
No MediSync, a infraestrutura de banco de teste é gerenciada canonicamente:
1. **Migrações via Alembic:** O schema é provisionado uma única vez até a revisão head (`just migrate`).
2. **Limpeza Declarativa e Rápida:** As fixtures utilizam `clean_database_tables()` ou `clean_database_and_valkey()`, que executam um único comando `TRUNCATE TABLE ... CASCADE` nas tabelas de domínio, preservando a estrutura de tabelas, índices, triggers de RLS e concessões DCL intactas.
3. **Limpeza de Valkey por Namespace:** Chaves voláteis de teste (`fila:*`, `lock:*`, `plantao:*`, etc.) são limpas via `clean_valkey_keys()` sem afetar outras chaves persistidas.

---

## 4. O Portão de Qualidade `just check`

O comando `just check` implementa a ordem estrita **Fail-Fast**:

```
fmt -> lint -> typecheck -> tach -> test-unit -> test-integration
```

1. **`just fmt` (Ruff):** Valida e formata o estilo do código em <1s.
2. **`just lint` (Ruff):** Detecta problemas estáticos e aplica correções seguras em <1s.
3. **`just typecheck` (Basedpyright):** Validação estrita de tipos (`typeCheckingMode = "strict"` tanto em `src/` quanto em `tests/`).
4. **`just tach` (Tach):** Validação estrita de fronteiras modulares hexagonais.
5. **`just test-unit` (Pytest + Cov):** 423 testes unitários com checagem de cobertura (mínimo de 85%).
6. **`just test-integration` (Pytest):** Testes ponta a ponta sobre contêineres reais.
