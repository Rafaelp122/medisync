# US-07 — Alocação Atômica de Chamada e Zero Overbooking

> **Requisito Base:** RF-03  
> **Invariantes Relacionadas:** RN01 (Prevalência Clínica), RN02 (Zero Overbooking e Ring Timeout 45s)  
> **Persona:** Dr. Eduardo Rocha (Médico Plantonista)  
> **Módulos:** `queue`, `worker`  
> **Status de Qualidade:** 🟢 **Conforme**

---

## 1. Narrativa da História (User Voice)

**Como** médico plantonista ativo (Dr. Eduardo Rocha),  
**Quero** clicar em *"Chamar Próximo"* e receber instantaneamente o paciente mais prioritário da fila com garantia de exclusividade absoluta,  
**Para que** eu nunca dispute o mesmo paciente com outro médico (zero overbooking) e inicie a chamada com segurança em menos de 10 milissegundos.

---

## 2. Critérios de Aceite Formais (Gherkin)

### Cenário 1: Convocação atômica do paciente mais prioritário (Caso Feliz)
- **Dado que** estou autenticado como médico (`Role.MEDICO`) e não possuo nenhuma consulta ativa em andamento,
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
- **Quando** as 50 requisições são processadas pelo motor de alocação atômica,
- **Então** exatamente 1 médico recebe HTTP 200 OK com a alocação do paciente,
- **E** os outros 49 médicos recebem indicação de inexistência de paciente disponível ou conflito (HTTP 409/204), sem qualquer sobreposição.

### Cenário 3: Médico tenta chamar outro paciente com consulta em andamento
- **Dado que** o médico já possui um atendimento ativo no status `EM_ATENDIMENTO`,
- **Quando** tenta solicitar novo paciente,
- **Então** o sistema bloqueia a requisição informando conflito operacional (HTTP 400 ou 409), preservando a invariante profissional da RN02.

---

## 3. Contrato de API

* **Endpoint:** `POST /api/v1/fila/chamar-proximo`
* **Headers:** `Authorization: Bearer <jwt_medico>`, `X-Tenant-ID: <org_id>`
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

- [x] **Script Lua Atômico:** Execução de `alocar_chamada.lua` com EVALSHA e locks atômicos duplos (`src/modules/queue/infrastructure/lua/alocar_chamada.lua`).
- [x] **Latência Submilisegundo:** Tempo de resposta comprovado em suíte de teste de estresse concorrente.
- [x] **Agendamento do Timeout:** Enfileiramento do job ARQ `ring_timeout_task` com `_defer_by=45` (`src/worker/tasks/ring_timeout.py`).
- [x] **Apresentação:** Router fino `alocacao_router.py` montado em `/api/v1/fila/chamar-proximo` com `ChamarProximoResponse` validado via `model_validate` e expondo `paciente_id` e `prioridade_clinica` (ADR-001/ADR-008).
- [x] **Testes Automatizados:**
  - `tests/unit/test_queue_schemas.py`
  - `tests/unit/test_alocacao_service.py`
  - `tests/unit/test_alocacao_router.py`
  - `tests/integration/test_alocar_chamada_concurrency.py`
  - `tests/integration/test_ring_timeout_flow.py`
