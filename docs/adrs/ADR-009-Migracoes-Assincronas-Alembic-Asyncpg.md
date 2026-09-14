# [ADR-009] Governança de Esquema e Migrações Assíncronas via Alembic e asyncpg

| Metadado | Detalhe |
| :--- | :--- |
| **Status** | Aprovado |
| **Data** | 2026-09-13 |
| **Decisores** | Time de Arquitetura & Engenharia |
| **Referência SRS** | [SRS-001 v1.0](../srs/SRS-001-MediSync-Express.md) (RNF-08) |

---

## 1. Contexto e Declaração do Problema

O **MediSync Express** utiliza o PostgreSQL 16 com o driver assíncrono `asyncpg` como motor relacional de persistência. A evolução do modelo de dados precisa ser versionada, declarativa e automatizada para permitir que qualquer contêiner suba aplicando as alterações necessárias em menos de 10 minutos (RNF-08).

Tradicionalmente, ferramentas de migração em Python operam de forma síncrona. Precisamos decidir como orquestrar as migrações sem exigir a inclusão de drivers síncronos legados duplicados (como `psycopg2`) na imagem Docker.

---

## 2. Drivers de Decisão

- **Driver Único em Produção**: Utilizar exclusivamente `asyncpg` para runtime e migrações, reduzindo o tamanho da imagem de contêiner e evitando dependências de compilação C do libpq.
- **Detecção Declarativa de Modelos**: Compatibilidade com `DeclarativeBase` do SQLAlchemy 2.0 e geração automática de diffs (`autogenerate`).
- **Suporte a Objetos Customizados do PostgreSQL**: Capacidade de criar e versionar regras (`RULES`), índices parciais e tipos ENUM nos scripts de migração.

---

## 3. Opções Consideradas

### Opção 1: Migrações Síncronas com Driver Duplo (`psycopg2-binary`)
Manter o Alembic configurado com `psycopg2` para rodar migrações síncronas e usar `asyncpg` para a aplicação FastAPI.
- *Prós*: Configuração padrão histórica da documentação do Alembic.
- *Contras*: Duplicação desnecessária de dependências no `pyproject.toml`; risco de diferenças sutis de parsing de tipos entre drivers; imagens Docker maiores.

### Opção 2: Scripts de Banco SQL Puros Gerenciados por Bash
Executar arquivos `.sql` ordenados via `psql` na inicialização do contêiner.
- *Prós*: Sem dependência de bibliotecas Python.
- *Contras*: Sem controle confiável de histórico de versões, sem suporte a rollbacks incrementais e sem validação estática de tipos contra os modelos SQLAlchemy.

### Opção 3: Runner Assíncrono Nativo do Alembic com `asyncpg`
Configurar o `src/migrations/env.py` com `create_async_engine` do SQLAlchemy, executando as migrações através do adaptador `connection.run_sync()`.
- *Prós*: Utiliza a mesma `DATABASE_URL` e o mesmo driver `asyncpg` da aplicação; compatibilidade total com comandos `alembic upgrade head` e `alembic revision --autogenerate`; suporte nativo a execuções de comandos SQL brutos (`op.execute()`) para criação de regras de auditoria imutáveis.
- *Contras*: Exige o wrapper `asyncio.run()` na função `run_migrations_online()` do Alembic.

---

## 4. Decisão

Adotamos a **Opção 3: Runner Assíncrono Nativo do Alembic com `asyncpg`**.

### Diretrizes de Execução:
1. **Configuração de `env.py`**: O runner cria um `async_engine`, conecta via `asyncpg` e delega a execução síncrona interna para o contexto do Alembic via `connection.run_sync(do_run_migrations)`.
2. **Registro Centralizado de Metadados**: Todos os modelos de todos os módulos (`identidade`, `triagem`, `fila`, `teleconsulta`, `auditoria`) são importados explicitamente em `env.py` para que `target_metadata = Base.metadata` detecte automaticamente todas as tabelas.
3. **Detecção Estrita de Tipos**: Habilitação de `compare_type=True` para detectar mudanças de tamanho de strings e enums.

---

## 5. Consequências

### Positivas:
- **Zero Redundância**: Uma única stack de banco (`asyncpg`) atende a aplicação, os workers e as migrações.
- **Deploy Declarativo**: O comando de subida do contêiner executa `alembic upgrade head` de forma autônoma e segura antes do Uvicorn iniciar.

### Negativas / Riscos Mitigados:
- *Curva de Configuração*: O template de `env.py` precisa ser configurado com precisão assíncrona, o que fica totalmente documentado e resolvido na [RFC-002](../rfcs/RFC-002-Modelo-de-Dados-Agregados-e-Migracoes.md).
