# Create Alembic Migration with Row-Level Security (RLS)

> Como criar migrações seguras para tabelas multi-tenant com isolamento Postgres RLS e papel restrito.

## Contexto

No MediSync Express, o isolamento lógico entre organizações hospitalares e clínicas é assegurado diretamente no banco de dados via PostgreSQL Row-Level Security (RLS), em conformidade com a ADR-003.

Ao criar uma nova tabela que armazena dados clínicos, cadastrais ou administrativos vinculados a uma organização, a migração do Alembic não pode se limitar ao `op.create_table`. O gerador padrão do Alembic (`--autogenerate`) desconhece políticas de RLS e papéis restritos. É obrigatório habilitar e forçar o RLS (`ENABLE` e `FORCE ROW LEVEL SECURITY`), definir a política canônica de isolamento baseada na variável de sessão `app.current_tenant_id` e conceder privilégios ao papel de aplicação `medisync_app` (configurado com `NOBYPASSRLS`).

## Conceito

Toda migração de tabela multi-tenant segue o roteiro operacional estrito de seis etapas:

### 1. Gerar o arquivo de migração

Crie o arquivo de migração vazio com identificador cronológico:

```bash
uv run alembic revision -m "add_table_with_rls"
```

### 2. Estruturar a coluna de tenant

A tabela deve conter a coluna de chave estrangeira referenciando `organizacoes`:

```python
op.add_column("nova_tabela", sa.Column("organizacao_id", sa.BigInteger(), nullable=False))
op.create_foreign_key("fk_nova_tabela_org", "nova_tabela", "organizacoes", ["organizacao_id"], ["id"])
op.create_index("ix_nova_tabela_organizacao_id", "nova_tabela", ["organizacao_id"])
```

### 3. Conceder permissões DCL ao papel medisync_app

O papel `medisync_app` opera sem privilégios de superusuário e com `NOBYPASSRLS`:

```bash
op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON nova_tabela TO medisync_app;")
```

### 4. Habilitar e forçar RLS na tabela

A cláusula `FORCE` é mandatória para impedir que proprietários da tabela ignorem a política:

```bash
op.execute("ALTER TABLE nova_tabela ENABLE ROW LEVEL SECURITY;")
op.execute("ALTER TABLE nova_tabela FORCE ROW LEVEL SECURITY;")
```

### 5. Criar a política canônica de isolamento

A política utiliza a expressão canônica parametrizada por `app.current_tenant_id`:

```bash
op.execute("""
    CREATE POLICY tenant_isolation_nova_tabela ON nova_tabela
    USING (organizacao_id = NULLIF(current_setting('app.current_tenant_id', true), '')::bigint)
    WITH CHECK (organizacao_id = NULLIF(current_setting('app.current_tenant_id', true), '')::bigint);
""")
```

### 6. Implementar o downgrade correspondente

A função `downgrade()` deve realizar o rollback simétrico: revogar políticas, desativar o RLS e remover a tabela.

```bash
op.execute("DROP POLICY IF EXISTS tenant_isolation_nova_tabela ON nova_tabela;")
op.execute("ALTER TABLE IF EXISTS nova_tabela NO FORCE ROW LEVEL SECURITY;")
op.execute("ALTER TABLE IF EXISTS nova_tabela DISABLE ROW LEVEL SECURITY;")
```

## Onde no código

- Migração canônica RLS: `migrations/versions/0002_row_level_security.py`
- Injetor de tenant na sessão: `src/core/database.py:_set_tenant_rls_on_begin`
- Contexto de execução assíncrona: `src/core/context.py:tenant_context`
- Testes de isolamento multi-tenant: `tests/integration/test_rls_security.py`
- Referência de schema e RLS: `docs/reference/database/schema-and-rls.md`

Audite se todas as tabelas multi-tenant possuem RLS ativado no histórico:

```bash
rg -n "FORCE ROW LEVEL SECURITY" migrations/versions/
```

Verifique a injeção do papel restrito na conexão ativa do SQLAlchemy:

```bash
rg -n "SET LOCAL ROLE medisync_app" src/core/database.py
```

## Verificação

Aplique a migração pendente no banco de dados local:

```bash
just migrate
```

Execute a suíte de integração de segurança RLS para validar o isolamento estrito:

```bash
uv run pytest tests/integration/test_rls_security.py --no-cov -q
```

Expected: Todos os testes aprovados validando `rowsecurity=True`, `forcerowsecurity=True` e bloqueio de vazamento entre tenants.

Reverta a migração para validar a integridade da função `downgrade()`:

```bash
just rollback
```

Reaplique para restaurar o estado atualizado:

```bash
just migrate
```

## Ver também

- [Create module endpoint](create-module-endpoint.md)
- [Wire module dependencies](wire-module-dependencies.md)
- [Run tests](run-tests.md)
- [ADR-003](../../adrs/ADR-003-Multi-Tenancy-Logico-Postgres-RLS.md)
- [Multi-tenancy RLS Concept](../../explanation/concepts/multi-tenancy-rls.md)
- [Schema e RLS Reference](../../reference/database/schema-and-rls.md)
