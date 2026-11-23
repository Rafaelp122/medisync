# US-07 — Alocação Atômica de Chamada e Zero Overbooking

> **Requisito Base:** RF-03  
> **Invariantes Relacionadas:** RN01 (Prevalência Clínica), RN02 (Zero Overbooking e Ring Timeout 45s)  
> **Persona:** Dr. Eduardo Rocha (Médico Plantonista)  
> **Módulos:** `queue`, `worker`  
> **Status de Qualidade:** 🟢 **Conforme**

---

## 1. Narrativa da História (User Voice)

**Como** médico plantonista ativo na estação de telemedicina (`/medico`) (Dr. Eduardo Rocha),  
**Quero** clicar em *"Chamar Próximo"* e receber instantaneamente o paciente mais prioritário da fila com garantia de exclusividade absoluta,  
**Para que** eu nunca dispute o mesmo paciente com outro médico (zero overbooking) e inicie a chamada com segurança em menos de 10 milissegundos.

---

## 2. Critérios de Aceite Formais (Gherkin)

### Cenário 1: Convocação atômica do paciente mais prioritário (Caso Feliz)
- **Dado que** estou autenticado como médico (`Role.MEDICO`) na rota protegida `/medico` (`frontend/src/routes/medico.tsx`) com sessão corporativa sem tokens em storage (Issue #144), access token mantido exclusivamente em memória volátil e reidratado via cookie HttpOnly silencioso no F5, e não possuo nenhuma consulta ativa em andamento,
- **E** a fila possui pacientes nos Níveis 3 e 2 aguardando aptos,
- **Quando** solicito o próximo atendimento em `POST /api/v1/fila/chamar-proximo`,
- **Então** o sistema aloca com exclusividade o paciente apto de maior urgência clínica e maior tempo de espera,
- **E** reserva mutuamente o médico e o paciente por 45 segundos, impedindo que outro profissional o convoque,
- **E** remove o paciente da lista de espera de novos atendimentos,
- **E** transiciona o atendimento para em chamada (`CHAMANDO_PACIENTE`),
- **E** persiste atomicamente o evento auditável 'CHAMADA_INICIADA' na trilha append-only (ADR-007),
- **E** inicia o timer de 45 segundos para resposta do paciente,
- **E** retorna HTTP 200 OK com os dados do atendimento alocado em menos de 20 milissegundos.

### Cenário 2: Concorrência simultânea de 50 médicos (Garantia de Zero Overbooking)
- **Dado que** 50 médicos clicam em *"Chamar Próximo"* exatamente no mesmo milissegundo disputando 1 único paciente elegível,
- **Quando** as 50 requisições são processadas pelo motor de alocação atômica (`alocar_proximo.lua`),
- **Então** exatamente 1 médico recebe HTTP 200 OK com `{alocado: true, ...}`,
- **E** os outros 49 médicos recebem HTTP 200 OK com `{alocado: false, mensagem: "Fila vazia. Não há pacientes aguardando atendimento no momento."}`, sem qualquer sobreposição ou HTTP 409 falso.

### Cenário 3: Médico tenta chamar outro paciente com chamada ou consulta ativa
- **Dado que** o médico já possui um toque ativo (`lock:medico:{id}`) ou consulta em andamento (`EM_ATENDIMENTO` / `lock:consulta_ativa:medico:{id}`),
- **Quando** tenta solicitar novo paciente em `POST /api/v1/fila/chamar-proximo`,
- **Então** os scripts Lua 4-Keys retornam `0` (`AlocacaoCodigo.MEDICO_OCUPADO`) e o sistema bloqueia a requisição com **HTTP 409 Conflict** (`code: "MEDICO_OCUPADO"`), preservando a invariante da RN02.

### Cenário 4: Restauração de timer pós-F5 e recusa canônica pelo paciente
- **Dado que** o paciente recebeu a chamada (`CHAMANDO_PACIENTE`) e recarregou a página (F5) ou recusou o toque na interface,
- **Quando** consulta `GET /api/v1/fila/posicao/{atendimento_id}` ou aciona recusa via `POST /api/v1/fila/cancelar/{atendimento_id}`,
- **Então** `PosicaoFilaResponse` devolve `chamada_iniciada_em`, `ttl_segundos` e `prioridade_clinica` para restaurar o countdown de 45s,
- **E** o cancelamento/recusa com `with_for_update=True` limpa os locks pós-commit e emite `CALL_CANCELLED` em `medisync:pubsub:doctor:{medico_id}` para desbloquear imediatamente a estação médica.

---

## 3. Contrato de API

* **Endpoint:** `POST /api/v1/fila/chamar-proximo`
* **Headers:** `Authorization: Bearer <jwt_medico>`
* **Resposta de Sucesso com Alocação (`200 OK`):**
  ```json
  {
    "alocado": true,
    "atendimento_id": "018f3a5b-...",
    "medico_id": "018f3a5b-...",
    "paciente_id": "018f3a5b-...",
    "prioridade_clinica": 2,
    "status": "CHAMANDO_PACIENTE",
    "chamada_iniciada_em": "2026-10-25T00:30:00Z",
    "ttl_segundos": 45,
    "mensagem": "Paciente alocado com sucesso para chamada."
  }
  ```
* **Resposta de Fila Vazia (`200 OK`):**
  ```json
  {
    "alocado": false,
    "atendimento_id": null,
    "medico_id": null,
    "paciente_id": null,
    "prioridade_clinica": null,
    "status": null,
    "chamada_iniciada_em": null,
    "ttl_segundos": null,
    "mensagem": "Fila vazia. Não há pacientes aguardando atendimento no momento."
  }
  ```

---

## 4. Checklist de Inspeção de Código

- [x] **Scripts Lua 4-Keys Atômicos:** Execução via `ValkeyQueueEngine` (`src/modules/queue/infrastructure/valkey_queue_engine.py`) dos scripts `alocar_chamada.lua` e `alocar_proximo.lua` (varredura `ZRANGE` multi-candidato + proteção `KEYS[4]: lock:consulta_ativa:medico:{id}`).
- [x] **Latência Submilisegundo:** Tempo de resposta comprovado em suíte de teste de estresse concorrente.
- [x] **Agendamento do Timeout e Compensação:** Enfileiramento de `resolver_ring_timeout_task` com `_defer_by=timedelta(seconds=ttl_segundos)` (`src/worker/tasks/ring_timeout.py`) e compensação segura (`devolver_para_fila(..., nx=True)`) em falha de banco ou ARQ (`src/modules/queue/application/services/alocacao_service.py`).
- [x] **Apresentação & Contratos:** `alocacao_router.py` (`/api/v1/fila/chamar-proximo`), `PosicaoFilaResponse` (com `chamada_iniciada_em`, `ttl_segundos`, `prioridade_clinica`) e recusa canônica em `POST /api/v1/fila/cancelar/{atendimento_id}` (`src/modules/queue/presentation/routers/fila_router.py`).
- [x] **Frontend Rota & Workstation (Issue #141 / Issue #144):** Rota declarativa `/medico` (`frontend/src/routes/medico.tsx`) com guard `beforeLoad` validando sessão médica e reidratação silenciosa de access token via cookie HttpOnly, sem persistência de credenciais em Web Storage.
- [x] **Frontend Ring Modal (RF-03, RN02, WCAG 2.1.2):** Modal fullscreen `IncomingCallRingModal` com contagem regressiva de 45 segundos, compensação de safe area inset, botão acessível de recusa/escape hatch com `aria-label="Recusar chamada médica"`, dismiss via `Escape` (sem aprisionamento de teclado / WCAG 2.1.2), chime sonoro sintetizado em Web Audio API e auto-dismiss (`frontend/src/features/queue/components/incoming-call-ring-modal.tsx`).
- [x] **Testes Automatizados:**
  - Backend: `tests/unit/test_queue_schemas.py`, `tests/unit/test_alocacao_service.py`, `tests/unit/test_alocacao_router.py`, `tests/integration/test_alocar_chamada_concurrency.py`, `tests/integration/test_ring_timeout_flow.py`
  - Frontend: `frontend/src/features/queue/tests/incoming-call-ring-modal.test.tsx`, `frontend/src/features/queue/tests/virtual-waiting-room.test.tsx`
