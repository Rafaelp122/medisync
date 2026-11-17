# Scheduling Domain

> Agenda programada multiprofissional (eMulti: Psicologia e Nutrição) com geração dinâmica de slots, lock pessimista em mutações e prevenção de double-booking por exclusão temporal GiST no PostgreSQL 17.

## 1. Contexto

O domínio de Agendamento (`scheduling`) orquestra consultas programadas das equipes multiprofissionais (**eMulti**, Portaria GM/MS nº 635/2023) em paralelo à fila de pronto-atendimento espontâneo (`queue`). Enquanto `queue` ordena urgências imediatas no Valkey, `scheduling` mantém janelas semanais recorrentes de atendimento e reservas nominais no PostgreSQL 17.

Vocabulário ubíquo: `EspecialidadeAgenda` (`PSICOLOGIA`, `NUTRICAO`), `AgendaDisponibilidade` (janela semanal em horário UTC), `Agendamento`, `StatusAgendamento`, `SlotDisponivelDTO`, `excl_agendamento_slot_ativo` (exclusão temporal GiST), `AttendanceLookupPort`.

Multitenancy estrito: `agenda_disponibilidades` e `agendamentos` carregam `organizacao_id` (`ON DELETE RESTRICT`) com `FORCE ROW LEVEL SECURITY` e políticas `tenant_isolation_*`. Todas as datas operam normalizadas em UTC (`normalizar_utc`).

## 2. Regras

- **RN-SCH-01 — Catálogo de especialidades eMulti.** `ESPECIALIDADE_CATALOGO` publica `PSICOLOGIA` (duração padrão 50 min) e `NUTRICAO` (duração padrão 30 min); `validar_especialidade_agenda` normaliza entradas e rejeita códigos desconhecidos com `ValidationError`. [Fonte](../../user-stories/US-16-portal-cidadao-e-agendamento-emulti.md)
- **RN-SCH-02 — Janelas semanais e detecção de sobreposição.** `AgendaDisponibilidade` exige `dia_semana` entre `0` (segunda) e `6` (domingo), horários naive UTC com `hora_fim > hora_inicio` e `duracao_minutos` entre `15` e `120`. `cadastrar_disponibilidade` impede janelas ativas sobrepostas (`sobrepoe`) para o mesmo profissional e dia com `SlotIndisponivelError` (HTTP 409).
- **RN-SCH-03 — Validação de grade estrita, passado e anti-double-booking.** `agendar_consulta` bloqueia `slot_inicio < now(UTC)` (`ValidationError`), exige janela ativa cobrindo o intervalo exato (`AgendaDisponibilidade.cobre_slot`) e consulta `buscar_agendamento_conflitante` antes de gravar. No banco, `uq_agendamento_slot_ativo` e `excl_agendamento_slot_ativo` (`USING gist` com `tstzrange(slot_inicio, slot_fim, '[)')` e `where status NOT IN ('CANCELADO', 'FALTA')`) garantem atomicidade concorrente, traduzindo SQLSTATE `23505`/`23P01` em `SlotIndisponivelError`.
- **RN-SCH-04 — Ciclo de estados ativo com transições guardadas.** `StatusAgendamento` declara seis estados (`AGENDADO`, `CONFIRMADO`, `EM_ATENDIMENTO`, `CONCLUIDO`, `CANCELADO`, `FALTA`). No ciclo ativo implementado, agendamentos nascem em `AGENDADO` e transicionam via `iniciar_atendimento()` para `EM_ATENDIMENTO` ou via `cancelar()` para `CANCELADO` (admitindo `AGENDADO` ou `CONFIRMADO` como origem válida); saltos ilegais disparam `TransicaoAgendamentoInvalidaError` (HTTP 409).
- **RN-SCH-05 — Anti-IDOR, RBAC e leitura com lock (`for_update=True`).** Rotas públicas do tenant (`GET /especialidades`, `GET /slots`) exigem apenas `TenantDep` e limitam consultas a janelas de até `_MAX_JANELA_SLOTS_DIAS` (`31` dias). Operações do paciente exigem `Role.PACIENTE` (`PacienteSchedulingAuthDep`) extraindo `paciente_id` do JWT; operações de agenda exigem `Role.MEDICO` (`ProfissionalSchedulingAuthDep`). Mutações carregam registro via `buscar_agendamento_por_id(..., for_update=True)` antes de transicionar.

Guardiões: `Agendamento.__init__` valida `organizacao_id > 0`, `slot_fim > slot_inicio` e `observacoes <= 500` caracteres; `_validar_atendimento_vinculado` valida titularidade de `paciente_id`, `organizacao_id` e `medico_id` via `AttendanceLookupPort` antes de vincular `atendimento_id`.

## 3. Máquina de estados

```mermaid
stateDiagram-v2
    [*] --> AGENDADO: agendar_consulta (slot >= now UTC)
    AGENDADO --> EM_ATENDIMENTO: iniciar_atendimento (Role.MEDICO)
    AGENDADO --> CANCELADO: cancelar (Role.PACIENTE titular)
    CONFIRMADO --> EM_ATENDIMENTO: iniciar_atendimento (origem admitida)
    CONFIRMADO --> CANCELADO: cancelar (origem admitida)
    EM_ATENDIMENTO --> [*]
    CANCELADO --> [*]
```

O método privado `_transicionar` valida pertencimento ao conjunto de origens permitidas, atualiza `status` e `atualizado_em = datetime.now(UTC)` e delega o `commit()` único ao `SchedulingService` (ADR-001 §6).

## 4. Relações

- **Referências relacionais (FKs `RESTRICT`):** `agenda_disponibilidades` referencia `organizacoes.id` e `profissionais.id`; `agendamentos` referencia `organizacoes.id`, `pacientes.id`, `profissionais.id` e `atendimentos.id` (nullable, índice único parcial `uq_agendamento_atendimento_id`). [Schema](../../reference/database/schema-and-rls.md)
- **Integração cross-module desacoplada:** `AttendanceLookupPort` (`src/modules/scheduling/application/ports/attendance_lookup_port.py`) é adaptada em `src/modules/scheduling/composition.py:QueueStoreAttendanceLookupAdapter` sobre `QueueStorePort.buscar_atendimento`, respeitando fronteiras Tach sem importar modelos de `queue`.
- **Persistência e apresentação fina:** `SchedulingRepositoryPort` é implementada por `SqlSchedulingRepository`; `scheduling_router.py` agrega rotas sob `/api/v1/scheduling` delegando a `SchedulingServiceDep` (`composition.py`).
- **Frontend Feature-Driven:** `frontend/src/features/scheduling/` consome contratos `@/api/generated` em `/agendar` (`ScheduleAppointmentPage`) e na aba de agenda de `/medico` (`ProfessionalSchedulePanel`).

## 5. Peculiaridades

- **Exclusão temporal por intervalo (`btree_gist`):** Além da unicidade exata por `slot_inicio`, `excl_agendamento_slot_ativo` bloqueia qualquer sobreposição parcial de intervalos `[slot_inicio, slot_fim)` enquanto o status estiver ativo (`status NOT IN ('CANCELADO', 'FALTA')`).
- **Default UTC na agenda do dia:** `GET /api/v1/scheduling/agenda/dia` resolve datas omitidas (`data`, `data_inicio`, `data_fim`) para a data UTC corrente via `_resolver_periodo_agenda`.
- **Sinalização de violação de grade vs ocupação:** Quando o horário pedido cai dentro de uma janela ativa mas diverge da duração ou alinhamento de passos, `_casar_disponibilidade` responde HTTP 422 (`ValidationError`) em vez de 409 (`SlotIndisponivelError`).

## 6. Onde no código

- `src/modules/scheduling/domain/models.py`
- `src/modules/scheduling/domain/exceptions.py`
- `src/modules/scheduling/application/dtos.py`
- `src/modules/scheduling/application/ports/scheduling_repository_port.py`
- `src/modules/scheduling/application/ports/attendance_lookup_port.py`
- `src/modules/scheduling/application/services/scheduling_service.py`
- `src/modules/scheduling/infrastructure/adapters/sql_scheduling_repository.py`
- `src/modules/scheduling/composition.py`
- `src/modules/scheduling/presentation/schemas.py`
- `src/modules/scheduling/presentation/dependencies.py`
- `src/modules/scheduling/presentation/routers/scheduling_router.py`
- `migrations/versions/0015_scheduling_tables.py`
- `frontend/src/features/scheduling/pages/schedule-appointment-page.tsx`
- `frontend/src/features/scheduling/components/professional-schedule-panel.tsx`

Prova viva:

```bash
ls tests/unit | rg scheduling
# test_scheduling_models.py
# test_scheduling_router.py
# test_scheduling_service.py

ls frontend/src/features/scheduling/tests
# fixtures.ts
# professional-schedule-panel.test.tsx
# schedule-appointment-page.test.tsx
```

## 7. Verificação

```bash
rg -n "excl_agendamento_slot_ativo|AttendanceLookupPort|SchedulingService" src/modules/scheduling/
# models.py:317 excl_agendamento_slot_ativo | attendance_lookup_port.py:18 | scheduling_service.py:140

uv run pytest tests/unit/test_scheduling_models.py tests/unit/test_scheduling_service.py tests/unit/test_scheduling_router.py -q --no-cov
# 37 passed
```

## 8. Ver também

- [Product Specification](../product-specification.md) — suporte eMulti (RT-01) e universalidade SUS
- [ADR-012](../../adrs/ADR-012-Transicao-100-SUS-Consorcios-Intermunicipais-e-Autenticacao-Tripartida.md) — atendimento agendado multiprofissional eMulti
- [Database Schema & RLS](../../reference/database/schema-and-rls.md) — tabelas `agenda_disponibilidades` e `agendamentos`
- [US-16 Portal do Cidadão e Agendamento eMulti](../../user-stories/US-16-portal-cidadao-e-agendamento-emulti.md) — critérios BDD e interface
- [Queue Domain](./queue-domain.md) — fila imediata de pronto-atendimento por demanda espontânea
- [Domains Index](./index.md) — catálogo geral dos domínios da aplicação
