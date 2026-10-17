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
* **Headers:** `X-Tenant-ID: <org_id>`
* **Payload de Entrada (`PioraClinicaRequest`):**
  ```json
  {
    "atendimento_id": "018f3a5b-...",
    "novos_sintomas": ["dor_no_peito_irradiando", "sudorese_fria"],
    "escala_dor": 9
  }
  ```
* **Resposta Esperada em Caso de Emergência Nível 1 (`200 OK`):**
  ```json
  {
    "atendimento_id": "018f3a5b-...",
    "nova_prioridade": 1,
    "status_atendimento": "CANCELADO_PELO_PACIENTE",
    "alerta_samu_disparado": true,
    "orientacoes_emergencia": "Ligue imediatamente para o SAMU 192 ou dirija-se à UPA/Hospital mais próximo."
  }
  ```

---

## 4. Checklist de Inspeção de Código

- [x] **Desacoplamento Modular:** Comunicação via porta abstrata `TriagePort` injetada no composition root de `queue` (`src/modules/queue/application/ports/triage_port.py`).
- [x] **Remoção Atômica:** Atendimento Nível 1 é expurgado atômica e deterministicamente do conjunto de aptos no Valkey (`FilaService.registrar_piora_clinica()`).
- [x] **Apresentação:** Rota REST implementada em `src/modules/queue/presentation/routers/fila_router.py`.
- [x] **Testes Automatizados:**
  - `tests/unit/test_fila_router.py`
  - `tests/unit/test_admissao_service.py`
  - `tests/integration/test_admissao_integrada_flow.py`
