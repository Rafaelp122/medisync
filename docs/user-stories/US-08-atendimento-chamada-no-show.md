# US-08 — Ingresso na Teleconsulta e Resolução de No-Show (45s)

> **Requisito Base:** RF-03  
> **Invariantes Relacionadas:** RN02 (Ring Timeout e Liberação de Lock), RN03  
> **Personas:** Juliana Silva (Paciente) e Dr. Eduardo Rocha (Médico)  
> **Módulos:** `queue`, `worker`, `consultation`  
> **Status de Qualidade:** 🟢 **Conforme**

---

## 1. Narrativa da História (User Voice)

**Como** paciente convocada para a teleconsulta (Juliana Silva),  
**Quero** receber a notificação sonora e visual em tempo real e clicar em *"Entrar na Teleconsulta"* para acessar a sala de vídeo,  
**Para que** meu atendimento transicione para `EM_ATENDIMENTO`, a contagem regressiva de 45 segundos de no-show seja cancelada e minha consulta com o Dr. Eduardo seja iniciada sem falsos descartes.

---

## 2. Critérios de Aceite Formais (Gherkin)

### Cenário 1: Paciente ingressa na teleconsulta dentro dos 45 segundos (Caso Feliz)
- **Dado que** o atendimento está no status de chamada ativa (`CHAMANDO_PACIENTE`) com contagem regressiva de 45 segundos,
- **Quando** a paciente clica em entrar na consulta e solicita o token de acesso à sala em `POST /api/v1/consultations/{atendimento_id}/livekit/token`,
- **Então** o sistema valida que o atendimento está aguardando o ingresso da paciente,
- **E** transiciona o atendimento para `EM_ATENDIMENTO`,
- **E** persiste atomicamente o evento auditável 'CHAMADA_ATENDIDA' na trilha append-only (ADR-007),
- **E** cancela e neutraliza a contagem regressiva de no-show de 45 segundos,
- **E** promove o lock temporário de chamada em lock de consulta médica ativa,
- **E** retorna o token assinado e metadados de conexão à sala de videoconferência (HTTP 200 OK).

### Cenário 2: Paciente não ingressa em 45 segundos (Resolução Determinística de No-Show)
- **Dado que** a chamada foi iniciada e decorreram 45 segundos sem que a paciente tenha ingressado na teleconsulta,
- **Quando** a rotina assíncrona de timeout de chamada é acionada,
- **E** verifica que o atendimento ainda permanece no status `CHAMANDO_PACIENTE`,
- **Então** o sistema marca o atendimento como `PACIENTE_AUSENTE`,
- **E** persiste atomicamente o evento auditável 'TIMEOUT_CHAMADA_NO_SHOW' na trilha append-only (ADR-007),
- **E** desfaz a reserva temporária do médico e do atendimento,
- **E** notifica o médico via canal em tempo real de que a paciente não compareceu,
- **E** libera imediatamente o painel do médico para convocar o próximo paciente da fila.

### Cenário 3: Tentativa de ingresso após expiração do tempo (No-Show já consolidado)
- **Dado que** o atendimento já transicionou para `PACIENTE_AUSENTE` após a expiração dos 45 segundos,
- **Quando** a paciente tenta tardiamente ingressar na sala solicitando o token de acesso,
- **Então** o sistema rejeita a emissão do token informando recurso expirado ou conflito (HTTP 409 Conflict ou 410 Gone), sinalizando que o prazo de atendimento expirou por ausência.

---

## 3. Contrato de API

* **Endpoint de Ingresso e Emissão de Token:** `POST /api/v1/consultations/{atendimento_id}/livekit/token`
* **Headers:** `Authorization: Bearer <jwt_paciente>`, `X-Tenant-ID: <org_id>`
* **Payload de Entrada (`LiveKitTokenRequest`):**
  ```json
  {
    "organizacao_id": 1,
    "participant_id": "018f3a5b-...",
    "role": "PACIENTE",
    "is_publisher": true,
    "participant_name": "Juliana Santos Silva",
    "ttl_seconds": 3600
  }
  ```
* **Resposta Esperada (`200 OK`):**
  ```json
  {
    "token": "eyJhbGciOi...",
    "server_url": "http://localhost:7880",
    "room_name": "room_018f3a5b...",
    "participant_identity": "paciente:018f3a5b..."
  }
  ```

---

## 4. Checklist de Inspeção de Código

- [x] **Domínio:** Método `Atendimento.atender_chamada()` implementado e testado no modelo (`src/modules/queue/domain/models/atendimento.py`).
- [x] **Worker de No-Show:** Tarefa assíncrona `ring_timeout_task` libera locks e transiciona para `PACIENTE_AUSENTE` (`src/worker/tasks/ring_timeout.py`).
- [x] **Integração de Ingresso (NC-QUE-03):** Acionar `Atendimento.atender_chamada()` e neutralização do timeout na emissão de token LiveKit do paciente em `TeleconsultaService` (`src/modules/consultation/application/services/teleconsulta_service.py`).
- [x] **Testes Automatizados:**
  - `tests/unit/test_atendimento_model.py`
  - `tests/integration/test_ring_timeout_flow.py`
  - `tests/integration/test_livekit_lifecycle.py`
