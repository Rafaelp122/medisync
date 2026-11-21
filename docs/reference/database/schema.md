# Database Schema (Plataforma Única)

> Catálogo físico das 16 tabelas relacionais da plataforma única MediSync Express no PostgreSQL 17, chaves primárias UUIDv7 (RFC 9562) e invariantes estruturais de integridade.

## Contexto

Sob a [ADR-013](../../adrs/ADR-013-Simplificacao-Plataforma-Unica-e-Remocao-RLS.md), o MediSync Express adota um banco relacional de **plataforma única** em PostgreSQL 17 (extensões `uuid-ossp`, `pgcrypto` e `btree_gist`), conectando cidadãos, profissionais de saúde e gestão operacional da unidade sem particionamento multi-tenant nem políticas RLS.

O controle de acesso aos dados clínicos apoia-se em **RBAC estrito** (`src/core/authz/roles.py:Role`) e **checagem horizontal de titularidade Anti-IDOR** na camada de apresentação e serviços, preservando integralmente a conformidade com o Art. 11 da LGPD e as Resoluções CFM nº 2.314/2022 e nº 1.821/2007 (guarda mínima de 20 anos e trilha imutável `audit_events`).

Este documento cataloga as 16 tabelas criadas pela migração consolidada `migrations/versions/0001_initial_schema.py` e evoluídas incrementalmente pelas migrações subsequentes (como `migrations/versions/0002_add_outorga_tcle_dependentes.py` adicionando `outorga_tcle` em `dependentes`).

## Conceito

### 1. Catálogo Físico das 16 Tabelas Relacionais

Todas as entidades persistidas utilizam modelos ricos no SQLAlchemy 2.0 (`Mapped[...]`) e chaves primárias **UUIDv7** (`gen_uuidv7()` no banco / `src/core/uuid7.py:uuid7` em Python):

| Tabela | Modelo SQLAlchemy | PK | Principais Índices e Restrições |
|---|---|---|---|
| `configuracoes_unidade` | `ConfiguracaoUnidade` | `id` (UUIDv7) | Singleton (`uq_configuracoes_unidade_singleton`, `chk_configuracoes_unidade_singleton`), metadados SUS/CNES/CNPJ/IBGE |
| `profissionais` | `Profissional` | `id` (UUIDv7) | `uq_profissional_email`, `uq_profissional_cpf`, `idx_profissionais_papel` |
| `pacientes` | `Paciente` | `id` (UUIDv7) | `uq_paciente_cpf`, `uq_paciente_cns` (parciais `IS NOT NULL`), `idx_pacientes_telefone`, `chk_documento_paciente_obrigatorio` |
| `dependentes` | `Dependente` | `id` (UUIDv7) | `uq_dependente_vinculo` `(titular_id, dependente_id)`, `outorga_tcle` (`NOT NULL DEFAULT false`, RN-IDE-05), FKs `RESTRICT` para `pacientes.id` |
| `paciente_passkeys` | `PacientePasskey` | `id` (UUIDv7) | `uq_paciente_passkeys_cred` (`credential_id`), `idx_paciente_passkeys_paciente`, FK `CASCADE` em `paciente_id` |
| `usuarios_credenciais` | `UsuarioCredencial` | `id` (UUIDv7) | `uq_usuarios_credenciais_identificador`, `idx_usuarios_credenciais_papel`, `idx_usuarios_credenciais_usuario_id` |
| `atendimentos` | `Atendimento` | `id` (UUIDv7) | `idx_atendimentos_status`, `idx_atendimentos_paciente`, `idx_atendimentos_medico`, `idx_atendimentos_fila`, `chk_atendimento_prioridade` |
| `triagens` | `Triagem` | `id` (UUIDv7) | `uq_triagens_atendimento_id` (1:1), `chk_triagem_prioridade` (1–5), `chk_triagem_escala_dor` (0–10) |
| `evolucoes_clinicas` | `EvolucaoClinica` | `id` (UUIDv7) | `uq_evolucoes_clinicas_atendimento_id`, `idx_evolucoes_atendimento`, `finalizado_em` (congelamento SOAP) |
| `documentos_clinicos` | `DocumentoClinico` | `id` (UUIDv7) | `idx_documentos_atendimento`, `chk_documentos_tipo`, `chk_documentos_sha256_len` |
| `documento_itens` | `DocumentoItem` | `id` (UUIDv7) | `idx_documento_itens_doc`, FK `ON DELETE CASCADE` em `documento_id` |
| `audit_events` | `AuditEvent` | `id` (UUIDv7) | `idx_audit_atendimento`, `idx_audit_ator`, `chk_audit_ator_tipo`, trigger `trg_audit_events_immutable` |
| `configuracoes_plantao` | `ConfiguracaoPlantao` | `id` (UUIDv7) | Singleton (`uq_configuracoes_plantao_singleton`, `chk_configuracoes_plantao_singleton`), `chk_config_plantao_alpha`, `chk_config_plantao_tma`, `chk_config_plantao_ring`, `chk_config_plantao_modo` |
| `producoes_ambulatoriais` | `ProducaoAmbulatorial` | `id` (UUIDv7) | `uq_producoes_ambulatoriais_atendimento_id` (1:1), `idx_producao_atendimento`, `idx_producao_competencia` |
| `agenda_disponibilidades` | `AgendaDisponibilidade` | `id` (UUIDv7) | `idx_agenda_disp_esp`, `idx_agenda_disp_prof`, `chk_agenda_disp_dia_semana`, `chk_agenda_disp_horarios`, `chk_agenda_disp_duracao` |
| `agendamentos` | `Agendamento` | `id` (UUIDv7) | `excl_agendamento_slot_ativo` (GiST `tstzrange`), `uq_agendamento_slot_ativo` (parcial), `uq_agendamento_atendimento_id`, `idx_agendamentos_paciente`, `idx_agendamentos_profissional` |

### 2. Grupos Funcionais de Agregados

- **Unidade e Identidade**: `configuracoes_unidade` (singleton CNES/CNPJ/IBGE), `profissionais`, `pacientes`, `dependentes`, `paciente_passkeys` e `usuarios_credenciais`.
- **Acolhimento e Triagem**: `triagens` com priorização clínica determinística de 1 a 5.
- **Fila e Atendimento**: `atendimentos` governando o ciclo de vida da consulta virtual (RN01–RN03).
- **Agenda Programada (eMulti)**: `agenda_disponibilidades` e `agendamentos` com exclusão temporal GiST (`btree_gist`) prevenindo conflitos de horário (`excl_agendamento_slot_ativo`).
- **Ato Médico e Prontuário**: `evolucoes_clinicas`, `documentos_clinicos` e `documento_itens` (`ON DELETE RESTRICT` nas raízes clínicas e `CASCADE` nos itens prescritos).
- **Produção Ambulatorial SUS**: `producoes_ambulatoriais` consolidando lotes BPA-I / SISAB sob SIGTAP `03.01.01.025-0`.
- **Auditoria e Telemetria**: `audit_events` (append-only) e `configuracoes_plantao` (parâmetros singleton de escala e backpressure).

### 3. Chaves UUIDv7, Índices e Imutabilidade Forense

- **Chave Primária UUIDv7 em 100% das Tabelas**: Gerada em Python (`src/core/uuid7.py:uuid7`) e no banco (`gen_uuidv7()` em `migrations/versions/0001_initial_schema.py`), mantendo inserção monotônica na B-Tree e proteção anti-enumeração (anti-IDOR).
- **Tabelas Singleton via Guard Booleano (`singleton_guard`)**: `configuracoes_unidade` e `configuracoes_plantao` impõem registro único por banco sem números mágicos (`UniqueConstraint` + `CheckConstraint("singleton_guard IS TRUE")`).
- **Índice Crítico de Fila**: `idx_atendimentos_fila` sobre `(status, prioridade_clinica, data_entrada_fila)` acelera consultas de ordenação FIFO/prioridade sem sort em memória.
- **Unicidade Global de Identificadores**: CPF, CNS e credenciais possuem índices únicos globais (`uq_paciente_cpf`, `uq_paciente_cns`, `uq_profissional_email`, `uq_profissional_cpf`, `uq_usuarios_credenciais_identificador`).
- **Blindagem Forense de Auditoria (ADR-007)**: Trigger `trg_audit_events_immutable` (`trg_prevent_audit_mutation()`) levanta erro `restrict_violation` contra qualquer tentativa de `UPDATE` ou `DELETE` em `audit_events`.

## Onde no código

- Impl: `migrations/versions/0001_initial_schema.py:upgrade`
- Impl: `migrations/versions/0002_add_outorga_tcle_dependentes.py:upgrade`
- Impl: `scripts/postgres/01-init-extensions.sql`
- Impl: `src/core/database.py:Base`
- Impl: `src/core/uuid7.py:uuid7`
- Impl: `src/core/audit/models.py:AuditEvent`
- Impl: `src/modules/identity/domain/models/configuracao_unidade.py:ConfiguracaoUnidade`
- Impl: `src/modules/identity/domain/models/profissional.py:Profissional`
- Impl: `src/modules/identity/domain/models/paciente.py:Paciente`
- Impl: `src/modules/identity/domain/models/dependente.py:Dependente`
- Impl: `src/modules/identity/domain/models/passkey.py:PacientePasskey`
- Impl: `src/modules/queue/domain/models/atendimento.py:Atendimento`
- Impl: `src/modules/triage/domain/models/triagem.py:Triagem`
- Impl: `src/modules/consultation/domain/models/evolucao_clinica.py:EvolucaoClinica`
- Impl: `src/modules/consultation/domain/models/documento_clinico.py:DocumentoClinico`
- Impl: `src/modules/consultation/domain/models/documento_item.py:DocumentoItem`
- Impl: `src/modules/auth/domain/models/usuario_credencial.py:UsuarioCredencial`
- Impl: `src/modules/ambulatory/domain/models/producao_ambulatorial.py:ProducaoAmbulatorial`
- Impl: `src/modules/scheduling/domain/models.py:AgendaDisponibilidade`
- Impl: `src/modules/scheduling/domain/models.py:Agendamento`
- Impl: `src/modules/telemetry/domain/models.py:ConfiguracaoPlantao`
- Spec: `docs/adrs/ADR-013-Simplificacao-Plataforma-Unica-e-Remocao-RLS.md`
- Spec: `docs/adrs/ADR-007-Auditoria-Imutavel-Append-Only.md`
- Spec: `docs/explanation/architecture/data-model.md`
- Prova viva: `tests/integration/test_migrations.py:test_migration_creates_all_single_platform_tables`
- Prova viva: `tests/integration/test_migrations.py:test_zero_rls_policies_and_zero_organizacao_id_columns`
- Prova viva: `tests/integration/test_migrations.py:test_singleton_constraints_on_unidade_and_plantao`
- Prova viva: `tests/integration/test_migrations.py:test_audit_immutable_trigger_blocks_mutations`
- Prova viva: `tests/unit/test_atendimento_model.py:test_criar_atendimento_admissao_direta_sus_apto`
- Prova viva: `tests/unit/test_audit_model.py:test_audit_event_immutability_hooks_raise_error`
- Ver: `rg -n "op\.create_table|ExcludeConstraint" migrations/versions/0001_initial_schema.py`
- Ver: `rg -n "gen_uuidv7" migrations/versions/0001_initial_schema.py`

## Verificação

```bash
uv run pytest --noconftest tests/integration/test_migrations.py -v
uv run pytest tests/unit/test_atendimento_model.py tests/unit/test_audit_model.py -q --no-cov
uv run alembic check
```

## Ver também

- [Data Model](../../explanation/architecture/data-model.md)
- [ADR-013 Simplificação para Plataforma Única e Remoção de RLS](../../adrs/ADR-013-Simplificacao-Plataforma-Unica-e-Remocao-RLS.md)
- [ADR-007 Auditoria Imutável](../../adrs/ADR-007-Auditoria-Imutavel-Append-Only.md)
- [Documentation Standards](../architecture-standards/documentation-standards.md)
- [Testing Fixtures & Factories](../testing/fixtures-and-factories.md)
- [API Error Envelope](../api/error-envelope.md)
