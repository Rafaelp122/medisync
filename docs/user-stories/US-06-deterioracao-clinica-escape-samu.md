# US-06 — Monitoramento de Deterioração Clínica na Fila (Escape SAMU 192)

> **Requisito Base:** RF-06  
> **Invariantes Relacionadas:** RN04 (Salvaguarda SAMU 192), RN-REG-01  
> **Persona:** Juliana Silva (Paciente Espontânea)  
> **Módulos:** `queue`, `triage`  
> **Status de Qualidade:** 🟢 **Conforme**

---

## 1. Narrativa da História (User Voice)

**Como** paciente aguardando atendimento na fila virtual que sente agravamento súbito dos sintomas (Juliana Silva),  
**Quero** acionar o botão de emergência *"Sentiu piora nos sintomas?"*,  
**Para que** o sistema reavalie meu risco em tempo real e, caso identifique sinais de emergência crítica (Nível 1), interrompa imediatamente o atendimento virtual e me forneça instruções de socorro do SAMU 192.

---

## 2. Critérios de Aceite Formais (Gherkin)

### Cenário 1: Reavaliação detecta Emergência Crítica Nível 1 (Escape SAMU 192)
- **Dado que** estou aguardando na fila com classificação inicial Nível 3 (Amarelo - Urgente),
- **Quando** aciono o botão de piora e declaro novos sintomas graves (ex: dor torácica opressiva ou perda de consciência) em `POST /api/v1/fila/piora`,
- **Então** o sistema reclassifica o risco clínico para Nível 1 (Vermelho - Emergência),
- **E** remove imediatamente o paciente da fila de espera virtual,
- **E** encerra o atendimento com justificativa de emergência médica pré-hospitalar,
- **E** persiste atomicamente o evento auditável 'PIORA_CLINICA_REGISTRADA' na trilha append-only (ADR-007),
- **E** dispara notificação de alerta para o serviço de emergência,
- **E** retorna confirmação imediata (HTTP 200 OK) com `alerta_samu_disparado = true` e orientações de socorro pelo SAMU 192.

### Cenário 2: Reavaliação indica agravamento sem emergência crítica (Promoção de Posição)
- **Dado que** estou aguardando na fila com classificação Nível 4 (Verde - Pouco Urgente),
- **Quando** reporto piora que eleva meu quadro clínico para Nível 2 (Laranja - Muito Urgente),
- **Então** o sistema atualiza a prioridade clínica do atendimento para 2,
- **E** recalcula a posição do paciente na fila, promovendo-o à frente dos casos de menor urgência,
- **E** retorna HTTP 200 com a nova prioridade e `alerta_samu_disparado = false`.

---

## 3. Contrato de API

* **Endpoint:** `POST /api/v1/fila/piora`
* **Headers:** `Authorization: Bearer <token_intake_ou_jwt>`
* **Payload de Entrada (`PioraClinicaRequest`):**
  ```json
  {
    "atendimento_id": "018f3a5b-...",
    "novos_sintomas": ["dor_toracica_irradiada", "falta_de_ar"],
    "escala_dor": 9,
    "queixa_adicional": "Aperto no peito com falta de ar"
  }
  ```
  *(Nota: `normalizar_sintomas` aceita tanto os IDs canônicos `dor_toracica_irradiada`, `dispneia_grave`, `inconsciencia`, `confusao_mental`, `hemorragia_grave`, `febre` quanto os aliases de UI `dor_no_peito`, `falta_de_ar`, `tontura_desmaio`, `sangramento_grave`, `febre_alta`.)*
* **Resposta Esperada em Caso de Emergência Nível 1 (`200 OK` — `PioraClinicaResponse`):**
  ```json
  {
    "atendimento_id": "018f3a5b-...",
    "prioridade_clinica": 1,
    "status_atendimento": "CANCELADO_PACIENTE",
    "alerta_samu_disparado": true,
    "redirecionado_emergencia": true,
    "nova_posicao": null,
    "instrucoes": "Ligue imediatamente para o SAMU 192 ou procure o pronto-socorro mais próximo."
  }
  ```
* **Resposta Esperada em Caso de Agravamento Nível 2 (`200 OK` — `PioraClinicaResponse`):**
  ```json
  {
    "atendimento_id": "018f3a5b-...",
    "prioridade_clinica": 2,
    "status_atendimento": "APTO_PARA_CHAMADA",
    "alerta_samu_disparado": false,
    "redirecionado_emergencia": false,
    "nova_posicao": 1,
    "instrucoes": "Prioridade recalculada com sucesso na fila de espera."
  }
  ```

---

## 4. Checklist de Inspeção de Código

- [x] **Desacoplamento Modular & Zero Mapper Hell:** Comunicação via `TriagePort` unificado (`src/modules/queue/application/ports/triage_port.py`) e protocolo `PioraClinicaInput` (`src/modules/queue/application/dtos.py`) sem `PioraClinicaCommand` nem campos espelho em `PioraClinicaResponse` (`src/modules/queue/presentation/schemas.py`).
- [x] **Pós-Commit Estrito & Notificação de Chamada Ativa:** `FilaService.processar_piora_clinica()` carrega com `with_for_update=True`, executa mutações Valkey (`remover_da_fila`, `liberar_ring`, `inserir_ou_atualizar_fila` usando `atendimento.prioridade_clinica`) somente após `commit()`, e emite `CALL_CANCELLED` ao médico caso o paciente estivesse em `CHAMANDO_PACIENTE`.
- [x] **Taxonomia Red Flags Canônica:** Normalização de aliases em `src/modules/triage/domain/classification.py:normalizar_sintomas` garante Nível 1 e SAMU 192 mesmo quando `escala_dor=0`.
- [x] **Frontend (Salvaguarda SAMU 192):** Componente composto `frontend/src/features/onboarding/components/samu-emergency-modal.tsx` com `role="alertdialog"`, bloqueio de dismiss em backdrop/esc e discagem rápida `tel:192`.
- [x] **Frontend Fila (Piora Clínica - RF-06):** Modal `PioraClinicaModal` em `frontend/src/features/queue/components/piora-clinica-modal.tsx` integrado à `VirtualWaitingRoom` para relato de novos sintomas e reavaliação imediata.
- [x] **Detecção de Red Flags:** Chips de sinais clínicos críticos em `frontend/src/features/onboarding/components/acolhimento-fase1-form.tsx:SINAIS_ALARME_CRITICOS` e interceptação de HTTP 422 `EMERGENCIA_CRITICA_SAMU_192`.
- [x] **Testes Automatizados:**
  - Backend: `tests/unit/test_queue_schemas.py`, `tests/unit/test_fila_router.py`, `tests/unit/test_admissao_service.py`, `tests/integration/test_admissao_integrada_flow.py`
  - Frontend Modal: `frontend/src/features/onboarding/tests/samu-emergency-modal.test.tsx` (`IT-SAMU-01`, `IT-SAMU-02`, `IT-SAMU-03`)
  - Frontend Fila: `frontend/src/features/queue/schemas/piora-clinica-schema.test.ts`, `frontend/src/features/queue/tests/virtual-waiting-room.test.tsx` (`IT-WAIT-02`, `IT-WAIT-03`)
  - Frontend Telas: `frontend/src/features/onboarding/tests/acolhimento-triagem-form.test.tsx` (`IT-ONB-03`, `IT-ONB-04`)
  - E2E / A11y: `frontend/e2e/onboarding-acolhimento.spec.ts` (`E2E-ONB-02`, `E2E-ONB-03`)

---

## 5. Critérios de Interface & Experiência (UI/UX, A11y & Troféu de Testes - ADR-011)

### 5.1 Salvaguarda Clínica SAMU 192 (RN04)
- **Bloqueio Crítico (`alertdialog`):** Diálogo modal com `role="alertdialog"`, impossibilitando fechamento acidental via clique no backdrop ou tecla Escape.
- **Acionamento Imediato:** Botão de destaque com link telefônico nativo (`tel:192`) para chamada imediata de socorro pré-hospitalar móvel.
- **Duplo Gatilho de Segurança:**
  1. *Preventivo no Cliente:* Seleção direta de sinais de alarme de risco iminente de morte (dor precordial típica, perda de consciência, anafilaxia, etc.).
  2. *Reativo do Backend:* Tratamento unificado do erro RFC 7807 com código `EMERGENCIA_CRITICA_SAMU_192` retornado na admissão ou reclassificação.

### 5.2 Troféu de Testes do Frontend
- **Integração de Componente e Tela (Vitest + RTL):**
  - `frontend/src/features/onboarding/tests/samu-emergency-modal.test.tsx`: Renderização com `role="alertdialog"`, presença do link `tel:192` e acionamento de callback de saída presencial.
  - `frontend/src/features/onboarding/tests/acolhimento-triagem-form.test.tsx`: Abertura imediata do modal ao clicar em chip de alerta crítico e ao receber HTTP 422 do backend.
- **E2E e A11y (Playwright):**
  - `frontend/e2e/onboarding-acolhimento.spec.ts`: Testes ponta a ponta `E2E-ONB-02` (sintoma crítico) e `E2E-ONB-03` (422 backend) validando a salvaguarda em navegador real.
