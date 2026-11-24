# US-16 — Portal do Cidadão, IAM Híbrido e Agendamento Multiprofissional (eMulti)

> **Requisito Base:** RF-01, RF-07, RT-01, ADR-011, ADR-012  
> **Invariantes Relacionadas:** RN-AUT-09, RN-SCH-01 a RN-SCH-05, LGPD Art. 11 e 18, Portaria GM/MS nº 635/2023  
> **Personas:** Juliana Silva (Cidadã / Paciente) e Dr. Eduardo Rocha (Profissional eMulti)  
> **Módulos:** `auth`, `identity`, `consultation`, `scheduling`  
> **Status de Qualidade:** 🟢 **Conforme**

---

## 1. Narrativa da História (User Voice)

**Como** cidadã que utiliza a rede pública SUS (Juliana Silva),  
**Quero** me cadastrar ou entrar por múltiplos métodos (OTP SMS, Passkey ou senha opcional) em um portal exclusivo do cidadão (`/home`) para consultar meu histórico de atendimentos, baixar receitas assinadas, gerenciar dependentes e agendar consultas multiprofissionais eMulti (Psicologia e Nutrição),  
**Para que** eu acompanhe toda a minha jornada de saúde em um único lugar, sem misturar o acesso público com o portal interno da equipe médica e gestora (`/interno/login`).

**Como** profissional multiprofissional da equipe eMulti (Dr. Eduardo Rocha),  
**Quero** configurar minhas janelas semanais de atendimento, visualizar a agenda do dia e iniciar consultas agendadas sem risco de conflito de horário,  
**Para que** os atendimentos programados ocorram com segurança e exclusividade transacional no banco.

---

## 2. Critérios de Aceite Formais (Gherkin)

### Cenário 1: Auto-cadastro e IAM Híbrido do Cidadão (`/cadastro` e `/entrar`)
- **Dado que** acesso `/cadastro` (`frontend/src/routes/cadastro.tsx`), informo CPF, nome completo, data de nascimento, celular, e-mail obrigatório, aceite LGPD e (opcionalmente) uma senha Argon2id,
- **Quando** submeto o formulário para `POST /api/v1/auth/patient/register`,
- **Então** o sistema cria o registro via `IdentityWriterPort` e `UsuarioCredencial` (`papel=PACIENTE`, ou marcador `!UNUSABLE:` quando sem senha), dispara o OTP inicial de 6 dígitos e permite concluir o acesso.
- **Quando** retorno posteriormente em `/entrar`, informo CPF ou e-mail em `POST /api/v1/auth/patient/identify`,
- **Então** recebo apenas os métodos habilitados (`otp`, `senha`, `passkey`, `govbr` conforme `GOVBR_OIDC_ENABLED`) sem enumeração nem vazamento de PII.

### Cenário 2: Portal Longitudinal do Cidadão (`/home`, `/historico`, `/receitas`, `/perfil`)
- **Dado que** estou autenticada com `Role.PACIENTE` e possuo sessão em `medisync_session`,
- **Quando** acesso `/home` e navego pela barra do cidadão para `/historico`, `/receitas` e `/perfil`,
- **Então** visualizo meu histórico unificado de atendimentos de PA (`GET /api/v1/consultations/me/historico`, omitindo rascunhos SOAP não finalizados) e agendamentos eMulti,
- **E** listo e baixo minhas receitas em PDF/A (`GET /api/v1/consultations/me/documentos` e `GET /api/v1/consultations/me/documents/{documento_id}/pdf`) com atalho para validação pública em `/validar/$token`,
- **E** gerencio dados cadastrais CFM, dependentes familiares (`POST/GET /api/v1/pacientes/{id}/dependentes`) e biometria Passkey em `/perfil`.

### Cenário 3: Agendamento Programado eMulti e Prevenção de Double-Booking (`/agendar`)
- **Dado que** estou autenticada no portal e acesso `/agendar`,
- **Quando** seleciono uma especialidade (`PSICOLOGIA` ou `NUTRICAO`), consulto horários livres em `GET /api/v1/scheduling/slots` (que omite horários já decorridos com `slot_inicio < agora_utc`) e reservo um slot futuro em `POST /api/v1/scheduling/agendamentos`,
- **Então** o agendamento nasce em status `AGENDADO` e aparece em `GET /api/v1/scheduling/agendamentos/me`;
- **Mas se** outro paciente reservar o mesmo intervalo simultaneamente ou se eu já possuir outro agendamento ativo sobreposto com outro profissional, as exclusões temporais GiST (`excl_agendamento_slot_ativo` e `excl_agendamento_paciente_ativo`) rejeitam a transação conflitante com HTTP 409 (`code: SLOT_INDISPONIVEL`).

### Cenário 4: Gestão de Disponibilidade, Agenda e Ciclo Clínico do Profissional (`/medico`)
- **Dado que** estou autenticado como profissional (`Role.MEDICO`) em `/medico`,
- **Quando** cadastro janela semanal em `POST /api/v1/scheduling/disponibilidades` (protegida contra janelas concorrentes sobrepostas por `pg_advisory_xact_lock` e `excl_agenda_disp_sobreposicao`) e consulto `GET /api/v1/scheduling/agenda/dia`,
- **Então** visualizo meus agendamentos da data UTC corrente, inicio o atendimento via `POST /api/v1/scheduling/agendamentos/{agendamento_id}/iniciar` (`EM_ATENDIMENTO`, respondendo 409 `CONFLICT` em vínculo concorrente duplicado de `atendimento_id`), concluo via `POST /api/v1/scheduling/agendamentos/{agendamento_id}/concluir` (`CONCLUIDO`) ou registro ausência via `POST /api/v1/scheduling/agendamentos/{agendamento_id}/falta` (`FALTA`, liberando o slot nas constraints GiST).

### Cenário 5: Isolamento Estrito de Portais (`/interno/login`)
- **Dado que** acesso a landing page `/` ou o portal do cidadão `/entrar`,
- **Então** não há exibição de abas corporativas na entrada do cidadão (`TripartiteAuthCard` aposentado),
- **E** tentativas de autenticar credencial `Role.PACIENTE` em `POST /api/v1/auth/login` são rejeitadas em tempo constante (`CredenciaisInvalidasError`), mantendo médicos e gestores restritos a `/interno/login`.

---

## 3. Contrato de API

* **IAM Híbrido do Cidadão (`auth`):**
  * `POST /api/v1/auth/patient/register` (HTTP 201), `POST /api/v1/auth/patient/identify` (HTTP 200), `POST /api/v1/auth/patient/login-password` (HTTP 200), `POST /api/v1/auth/patient/cadsus` (HTTP 200), `GET /api/v1/auth/patient/methods` (HTTP 200).
* **Portal Longitudinal do Cidadão (`consultation`):**
  * `GET /api/v1/consultations/me/historico`, `GET /api/v1/consultations/me/documentos`, `GET /api/v1/consultations/me/documents/{documento_id}/pdf` (`PacienteAutenticadoDep` + Anti-IDOR).
* **Agenda eMulti (`scheduling`):**
  * `GET /api/v1/scheduling/especialidades` e `GET /api/v1/scheduling/slots` (consulta pública da unidade, omitindo slots no passado).
  * `POST /api/v1/scheduling/agendamentos`, `GET /api/v1/scheduling/agendamentos/me`, `POST /api/v1/scheduling/agendamentos/{agendamento_id}/cancelar` (`Role.PACIENTE`).
  * `POST /api/v1/scheduling/disponibilidades`, `GET /api/v1/scheduling/agenda/dia`, `POST /api/v1/scheduling/agendamentos/{agendamento_id}/iniciar`, `POST /api/v1/scheduling/agendamentos/{agendamento_id}/concluir`, `POST /api/v1/scheduling/agendamentos/{agendamento_id}/falta` (`Role.MEDICO`).

---

## 4. Checklist de Inspeção de Código

- [x] **Domínio & Persistência `scheduling`:** `src/modules/scheduling/domain/models.py`, `src/modules/scheduling/domain/exceptions.py`, `src/modules/scheduling/infrastructure/adapters/sql_scheduling_repository.py`, `migrations/versions/0001_initial_schema.py` e `migrations/versions/0003_scheduling_gist_constraints.py` (GiST `excl_agenda_disp_sobreposicao`, `excl_agendamento_slot_ativo` e `excl_agendamento_paciente_ativo` sem RLS).
- [x] **Serviços & Portas:** `src/modules/scheduling/application/services/scheduling_service.py:SchedulingService`, `AttendanceLookupPort` (`src/modules/scheduling/composition.py:QueueAttendanceSnapshotLookupAdapter` + `src/modules/queue/composition.py:build_attendance_lookup_reader`), `PatientAuthService` (`src/modules/auth/application/services/patient_auth_service.py`), `IdentityWriterPort`/`SqlIdentityWriter` (`src/modules/identity/infrastructure/identity_writer_sql.py`) e `HistoricoAtendimentoReaderPort`/`QueueStoreAtendimentoReaderAdapter` (`src/modules/consultation/composition.py`).
- [x] **Routers Finos:** `src/modules/scheduling/presentation/routers/scheduling_router.py`, `src/modules/auth/presentation/routers/patient_auth_router.py`, `src/modules/consultation/presentation/routers/consultation_router.py`.
- [x] **Frontend Rotas & Features:** `/`, `/entrar`, `/cadastro`, `/interno/login`, `/home`, `/agendar`, `/historico`, `/receitas`, `/perfil`, `/validar/$token` em `frontend/src/routes/`, `frontend/src/features/auth/`, `frontend/src/features/citizen/`, `frontend/src/features/scheduling/` e `frontend/src/features/landing/`.
- [x] **Integração Agenda -> Teleconsulta (`/medico`):** Callback `onAtendimentoIniciado` conectando `frontend/src/features/scheduling/components/professional-schedule-panel.tsx:ProfessionalSchedulePanel` em `frontend/src/routes/medico.tsx` e `frontend/src/features/consultation/pages/doctor-workstation-page.tsx:DoctorWorkstationPage` para abertura direta da sala LiveKit + PEP (`ConsultationEncounterProvider` com `key={atendimentoId}`) a partir de consulta eMulti iniciada.
- [x] **Testes Automatizados:**
  - Backend: `tests/unit/test_patient_hybrid_auth.py`, `tests/unit/test_consultation_patient_portal.py`, `tests/unit/test_scheduling_models.py`, `tests/unit/test_scheduling_service.py`, `tests/unit/test_scheduling_router.py`, `tests/integration/test_scheduling_persistence.py`
  - Frontend: `frontend/src/features/auth/tests/patient-hybrid-auth.test.tsx`, `frontend/src/features/auth/tests/staff-auth.test.tsx`, `frontend/src/features/citizen/tests/*.test.tsx`, `frontend/src/features/scheduling/tests/*.test.tsx`, `frontend/src/features/landing/tests/portfolio-landing-page.test.tsx`, `frontend/src/routes/medico.test.tsx`
  - E2E / A11y: `frontend/e2e/citizen-portal-and-scheduling.spec.ts` e `frontend/e2e/patient-hybrid-auth.spec.ts`

---

## 5. Critérios de Interface & Experiência (UI/UX, A11y & Troféu de Testes - ADR-011)

- **Navegação Não-Bloqueante:** Filtros de tipo e status em `/historico` (`HistoryPage`) utilizam `startTransition` para manter responsividade.
- **Composição Declarativa:** Fluxos de autenticação segregados (`PatientHybridAuthCard` vs `StaffAuthCard`) sem flags booleanas de perfil.
- **Acessibilidade Clínica (WCAG 2.1 AA):** Auditoria contínua com `@axe-core/playwright` em `citizen-portal-and-scheduling.spec.ts` (`E2E-CITIZEN-03`) e `patient-hybrid-auth.spec.ts` (`E2E-HYBRID-03`), com respeito a `prefers-reduced-motion`.
