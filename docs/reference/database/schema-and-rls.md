# Database Schema & Row-Level Security (RLS)

> Catálogo físico das 12 tabelas relacionais, chaves primárias UUIDv7 e isolamento multi-tenant forçado via RLS no PostgreSQL 17.

## Contexto

O MediSync Express adota modelo de banco de dados compartilhado com schema único (`public`) no PostgreSQL 17. O isolamento lógico entre organizações hospitalares, operadoras e prefeituras do SUS é compulsório: dados sensíveis de pacientes, consultas e prescrições jamais podem vazar entre tenants, sob pena de infração direta ao Art. 11 da LGPD e às Resoluções CFM nº 2.314/2022 (telemedicina) e nº 1.821/2007 (guarda probatória do prontuário médico por no mínimo 20 anos).

Enquanto consultas na camada de aplicação aplicam convencionalmente filtros `WHERE organizacao_id = :id`, o filtro de software é uma convenção revogável sujeita a omissões acidentais em novos endpoints ou refatorações. A defesa em profundidade da plataforma é transferida para o próprio motor do banco de dados por meio de Row-Level Security (RLS) compulsório (`FORCE ROW LEVEL SECURITY`), papel restrito de execução (`medisync_app NOBYPASSRLS`), injeção transacional no hook `after_begin` da sessão assíncrona e trilha de auditoria append-only blindada contra mutações.

Este documento de referência cataloga formalmente as 12 tabelas relacionais do sistema, suas chaves primárias UUIDv7, estratégias de indexação composta para desempenho sub-200ms em busca $\mathcal{O}(1)$ e a especificação das políticas de isolamento RLS.

## Conceito

### 1. Catálogo Físico das 12 Tabelas Relacionais

Todas as entidades persistidas utilizam modelos ricos no SQLAlchemy 2.0 (`Mapped[...]`). A tabela `organizacoes` atua como catálogo raiz público de tenants (sem RLS), enquanto as outras 11 tabelas aplicam `FORCE ROW LEVEL SECURITY` com segregação estrita por `organizacao_id`.

| Tabela | Modelo SQLAlchemy | PK | `organizacao_id` | RLS | Principais Índices e Restrições |
|---|---|---|---|---|---|
| `organizacoes` | `Organizacao` | `id` (BigInt) | N/A (Tenant Raiz) | Não | `pk_organizacoes`, `uq_organizacoes_cnpj` |
| `profissionais` | `Profissional` | `id` (UUIDv7) | BigInt (RESTRICT) | FORCE | `uq_profissional_org_email`, `uq_profissional_org_cpf`, `idx_profissionais_org_papel` `(organizacao_id, papel)` |
| `pacientes` | `Paciente` | `id` (UUIDv7) | BigInt (RESTRICT) | FORCE | `uq_paciente_org_cpf`, `uq_paciente_org_cns` (parciais), `idx_pacientes_org_telefone`, `chk_documento_paciente_obrigatorio` |
| `dependentes` | `Dependente` | `id` (UUIDv7) | BigInt (RESTRICT) | FORCE | `uq_dependente_vinculo` `(titular_id, dependente_id)`, `idx_dependentes_org` |
| `atendimentos` | `Atendimento` | `id` (UUIDv7) | BigInt (RESTRICT) | FORCE | `idx_atendimentos_org_status`, `idx_atendimentos_fila` `(organizacao_id, status, prioridade_clinica, data_entrada_fila)` |
| `triagens` | `Triagem` | `id` (UUIDv7) | BigInt (RESTRICT) | FORCE | `uq_triagens_atendimento_id` (1:1), `idx_triagens_org`, `chk_triagem_prioridade` (1 a 5) |
| `evolucoes_clinicas` | `EvolucaoClinica` | `id` (UUIDv7) | BigInt (RESTRICT) | FORCE | `idx_evolucoes_atendimento`, `idx_evolucoes_org`, `finalizado_em` (congelamento de prontuário SOAP) |
| `documentos_clinicos` | `DocumentoClinico` | `id` (UUIDv7) | BigInt (RESTRICT) | FORCE | `idx_documentos_atendimento`, `idx_documentos_org`, `chk_documentos_tipo`, `chk_documentos_sha256_len` |
| `documento_itens` | `DocumentoItem` | `id` (UUIDv7) | BigInt (RESTRICT) | FORCE | `idx_documento_itens_doc`, `idx_documento_itens_org`, FK CASCADE em `documento_id` |
| `audit_events` | `AuditEvent` | `id` (UUIDv7) | BigInt (RESTRICT) | FORCE | `idx_audit_atendimento`, `idx_audit_ator` `(organizacao_id, ator_tipo, ator_id)`, trigger anti-mutação |
| `usuarios_credenciais` | `UsuarioCredencial` | `id` (UUIDv7) | BigInt (RESTRICT) | FORCE | `uq_usuarios_credenciais_org_identificador`, `idx_usuarios_credenciais_org_papel`, `idx_usuarios_credenciais_usuario_id` |
| `configuracoes_plantao` | `ConfiguracaoPlantao` | `id` (UUIDv7) | BigInt (RESTRICT) | FORCE | `uq_configuracoes_plantao_org` (1:1), checks de alpha, TMA, ring e modo de operação |

As tabelas decompõem-se funcionalmente em cinco grupos de agregados:
- **Identidade e Acesso**: `organizacoes`, `profissionais`, `pacientes`, `dependentes` e `usuarios_credenciais`.
- **Acolhimento e Triagem**: `triagens` com priorização clínica determinística de 1 a 5.
- **Fila e Atendimento**: `atendimentos` governando o ciclo de vida da consulta médica virtual.
- **Ato Médico e Prontuário**: `evolucoes_clinicas`, `documentos_clinicos` e `documento_itens` (com integridade referencial `ON DELETE RESTRICT` nas raízes e `CASCADE` nos itens prescritos).
- **Auditoria e Telemetria**: `audit_events` (trilha imutável append-only) e `configuracoes_plantao` (parâmetros de plantão e SLAs por organização).

### 2. Chave Primária UUIDv7 (RFC 9562)

Com exceção da tabela raiz `organizacoes` (que utiliza `BigInteger` auto-incrementado como identificador numérico conciso de tenant), todas as 11 tabelas de domínio adotam UUIDv7 como chave primária.
- **Layout de Bits RFC 9562**: Os primeiros 48 bits codificam o timestamp Unix em milissegundos (`clock_timestamp()`), seguidos por 4 bits de versão (`0111`), 12 bits de fração/entropia sub-milissegundo, 2 bits de variante (`10` binário) e 62 bits de entropia aleatória criptográfica (`gen_random_bytes(10)`).
- **Localidade B-Tree e Inserção Monotônica**: Inserções ocorrem monotonicamente à direita da árvore B-Tree do PostgreSQL 17. Esse comportamento elimina o *page splitting* e a fragmentação severa de nós folhas típicos do UUIDv4 aleatório, mantendo performance de inserção equivalente a sequências inteiras.
- **Segurança Anti-IDOR**: Protege rotas da API, endpoints de teleconsulta WebRTC e identificadores de pacientes contra ataques de enumeração horizontal previsível (*Insecure Direct Object References*).
- **Geração Dupla**: No banco, gerado nativamente pela função PL/pgSQL `gen_uuidv7()` definida em `migrations/versions/0001_initial_schema.py` (`server_default=sa.text("gen_uuidv7()")`). Na camada Python, instanciado via `src/core/uuid7.py:uuid7` para viabilizar relacionamentos de entidades em memória antes do `flush`/`commit`.

### 3. Denormalização Pragmática de `organizacao_id` e Índices Compostos

Para viabilizar consultas em $\mathcal{O}(1)$ sem junções relacionais recursivas, toda tabela multi-tenant denormaliza a coluna `organizacao_id` (BigInteger, FK para `organizacoes.id` com `ON DELETE RESTRICT`).
- **Alinhamento de Prefixo com B-Tree**: As políticas de RLS injetam o predicado pontual `WHERE organizacao_id = :tenant`. Como `organizacao_id` compõe a primeira coluna de todos os índices de negócio, o planejador de consultas executa *Index Scan* ou *Index-Only Scan* direto, dispensando filtragens seqüenciais custosas pós-leitura.
- **Índice Crítico de Fila**: O índice `idx_atendimentos_fila` sobre `(organizacao_id, status, prioridade_clinica, data_entrada_fila)` suporta diretamente a regra RN02 de ordenação determinística de chamadas e alocação médica sem necessidade de ordenação em memória (*Sort/Top-N Heap*).
- **Índices Parciais de Unicidade**: Para a tabela `pacientes`, a identificação civil permite CPF ou CNS (ou ambos, via `chk_documento_paciente_obrigatorio`). A unicidade é garantida por índices parciais compostos com o tenant: `uq_paciente_org_cpf` (`WHERE cpf IS NOT NULL`) e `uq_paciente_org_cns` (`WHERE cns IS NOT NULL`).
- **Unicidade Escopada por Tenant**: As restrições de integridade em credenciais e profissionais (`uq_profissional_org_email`, `uq_profissional_org_cpf`, `uq_usuarios_credenciais_org_identificador`) combinam `organizacao_id`, permitindo que diferentes instituições de saúde cadastrem os mesmos dados civis de forma independente.
- **Índices Operacionais Especializados**: O índice `idx_profissionais_org_papel` acelera a localização de médicos disponíveis por papel; `idx_pacientes_org_telefone` viabiliza a reconciliação rápida em canais de mensageria; e `idx_audit_ator` otimiza relatórios de conformidade e investigações periciais de segurança.

### 4. Row-Level Security (RLS) e Isolamento no PostgreSQL

O isolamento multi-tenant apoia-se em cinco componentes configurados em `migrations/versions/0002_row_level_security.py` e migrações complementares:

1. **Ativação e Imposição Forçada (`FORCE ROW LEVEL SECURITY`)**:
   - `ALTER TABLE <tabela> ENABLE ROW LEVEL SECURITY;`
   - `ALTER TABLE <tabela> FORCE ROW LEVEL SECURITY;`
   - O modificador `FORCE` assegura que mesmo o usuário proprietário da tabela (*table owner*) tenha suas queries filtradas pelo motor de segurança quando operando sob a role da aplicação.

2. **Predicado Universal das Políticas `tenant_isolation_*`**:
   O predicado idêntico governa tanto a leitura (`USING`) quanto a inserção/atualização (`WITH CHECK`):
```sql
organizacao_id = NULLIF(current_setting('app.current_tenant_id', true), '')::bigint
```

3. **Papel de Aplicação `medisync_app` com `NOBYPASSRLS`**:
   - Papel de banco dedicado criado com a cláusula explícita `NOBYPASSRLS`.
   - O hook `_set_tenant_rls_on_begin` em `src/core/database.py` escuta o evento `after_begin` da sessão SQLAlchemy e executa `SET LOCAL ROLE medisync_app` mais `SELECT set_config('app.current_tenant_id', :tenant_id, true)`.
   - O parâmetro `is_local=true` e o comando `SET LOCAL` delimitam a configuração estritamente ao escopo da transação ativa, impedindo contaminação de conexões reaproveitadas no pool assíncrono.

4. **Comportamento Fail-Safe Deny (Negação Padrão)**:
   - Se uma requisição ou worker assíncrono executar queries sem tenant ativo (`current_tenant_id` nulo ou vazio), `current_setting('app.current_tenant_id', true)` retorna string vazia.
   - A cláusula `NULLIF('', '')` avalia para `NULL`. A expressão `organizacao_id = NULL` resulta em valor lógico SQL `UNKNOWN` (falso).
   - O banco recusa imediatamente qualquer tentativa de escrita (`WITH CHECK violation`) e retorna zero registros em leituras (`SELECT`), impedindo vazamento de dados mesmo em falhas de contexto.

5. **Blindagem DCL e Trigger da Trilha Forense (`audit_events`)**:
   - Em conformidade com ADR-007, o papel `medisync_app` tem apenas concessões de `SELECT` e `INSERT` em `audit_events`. Privilégios de `UPDATE`, `DELETE` e `TRUNCATE` são sumariamente revogados (`REVOKE`).
   - A trigger `trg_audit_events_immutable` bloqueia mutações no nível da linha, levantando exceção `restrict_violation` (código SQLSTATE 23001) caso qualquer operação de modificação seja tentada.

6. **Diferença entre `organizacoes` e as Tabelas de Domínio**:
   A tabela `organizacoes` é intencionalmente isenta de RLS (`relrowsecurity = false`). Ela atua como catálogo mestre público acessível durante a resolução de identificadores, validação de CNPJ e verificação prévia de tenants em middlewares. Todas as 11 tabelas filhas possuem foreign key direta para `organizacoes.id` com integridade referencial estrita (`ON DELETE RESTRICT`), impedindo desativações que deixem registros órfãos.

7. **Prevenção de Ataques Cross-Tenant no `INSERT` (`WITH CHECK`)**:
   A cláusula `WITH CHECK` avalia a nova linha proposta contra o `app.current_tenant_id` ativo. Se um cliente autenticado no tenant 1 tentar injetar um payload com `{"organizacao_id": 2}`, o PostgreSQL rejeita a transação antes da escrita com erro de violação de RLS (`new row violates row-level security policy for table ...`), prevenindo poluição de dados e sequestro de chaves.

8. **Isolamento de Sessão e Reúso no Connection Pool**:
   O `AsyncEngine` mantém conexões assíncronas persistentes no pool. O comando `SET LOCAL ROLE` e a função `set_config('...', true)` possuem escopo transacional estrito: no término do bloco da transação (`commit` ou `rollback`), o PostgreSQL restaura o estado inicial da conexão, garantindo que conexões recicladas não retenham permissões ou tenant anterior.

## Onde no código

- Impl: `migrations/versions/0001_initial_schema.py:upgrade`
- Impl: `migrations/versions/0002_row_level_security.py:upgrade`
- Impl: `migrations/versions/0003_auth_credentials.py:upgrade`
- Impl: `migrations/versions/0004_evolucao_finalizado_em.py:upgrade`
- Impl: `migrations/versions/0005_paciente_nome_social.py:upgrade`
- Impl: `migrations/versions/0006_telemetry_config_plantao.py:upgrade`
- Impl: `src/core/database.py:_set_tenant_rls_on_begin`
- Impl: `src/core/context.py:tenant_context`
- Impl: `src/core/uuid7.py:uuid7`
- Impl: `src/core/audit/models.py:AuditEvent`
- Impl: `src/modules/identity/domain/models/organizacao.py:Organizacao`
- Impl: `src/modules/identity/domain/models/profissional.py:Profissional`
- Impl: `src/modules/identity/domain/models/paciente.py:Paciente`
- Impl: `src/modules/identity/domain/models/dependente.py:Dependente`
- Impl: `src/modules/queue/domain/models/atendimento.py:Atendimento`
- Impl: `src/modules/triage/domain/models/triagem.py:Triagem`
- Impl: `src/modules/consultation/domain/models/evolucao_clinica.py:EvolucaoClinica`
- Impl: `src/modules/consultation/domain/models/documento_clinico.py:DocumentoClinico`
- Impl: `src/modules/consultation/domain/models/documento_item.py:DocumentoItem`
- Impl: `src/modules/auth/domain/models/usuario_credencial.py:UsuarioCredencial`
- Impl: `src/modules/telemetry/domain/models.py:ConfiguracaoPlantao`
- Spec: `docs/adrs/ADR-003-Multi-Tenancy-Logico-Postgres-RLS.md`
- Spec: `docs/adrs/ADR-007-Auditoria-Imutavel-Append-Only.md`
- Spec: `docs/explanation/architecture/data-model.md`
- Prova viva: `tests/integration/test_rls_security.py:test_rls_flags_and_policies_on_all_tables`
- Prova viva: `tests/integration/test_rls_security.py:test_tenant_isolation_across_all_nine_tables`
- Prova viva: `tests/integration/test_rls_security.py:test_rls_with_check_blocks_cross_tenant_insert`
- Prova viva: `tests/integration/test_rls_security.py:test_fail_safe_deny_without_tenant`
- Prova viva: `tests/integration/test_rls_security.py:test_audit_events_dcl_and_trigger_security`
- Prova viva: `tests/unit/test_atendimento_model.py:test_atendimento_criacao_sucesso`
- Prova viva: `tests/unit/test_audit_model.py:test_audit_event_impedir_update`
- Ver: `rg -n "FORCE ROW LEVEL SECURITY" migrations/versions/`
- Ver: `rg -n "current_setting\('app.current_tenant_id'" migrations/versions/`
- Ver: `rg -n "SET LOCAL ROLE medisync_app" src/core/database.py`
- Ver: `rg -n "gen_uuidv7" migrations/versions/0001_initial_schema.py`

## Verificação

```bash
uv run pytest tests/integration/test_rls_security.py
uv run pytest tests/unit/test_atendimento_model.py tests/unit/test_audit_model.py -q --no-cov
rg -n "FORCE ROW LEVEL SECURITY" migrations/versions/
rg -n "NULLIF\(current_setting" migrations/versions/
```

Comandos adicionais para auditoria física direta no PostgreSQL:

```bash
# Validar flags de RLS em pg_class (relrowsecurity e relforcerowsecurity)
psql -d medisync -c "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname IN ('profissionais', 'pacientes', 'organizacoes');"

# Listar todas as políticas tenant_isolation ativas em pg_policies
psql -d medisync -c "SELECT tablename, policyname, cmd FROM pg_policies WHERE schemaname = 'public';"
```

## Ver também

- [Data Model](../../explanation/architecture/data-model.md)
- [Multi-tenancy RLS](../../explanation/concepts/multi-tenancy-rls.md)
- [ADR-003 Multi-Tenancy Lógico](../../adrs/ADR-003-Multi-Tenancy-Logico-Postgres-RLS.md)
- [ADR-007 Auditoria Imutável](../../adrs/ADR-007-Auditoria-Imutavel-Append-Only.md)
- [Documentation Standards](../architecture-standards/documentation-standards.md)
- [Testing Fixtures & Factories](../testing/fixtures-and-factories.md)
- [API Error Envelope](../api/error-envelope.md)
