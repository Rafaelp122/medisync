# US-01 — Acolhimento, Triagem Estruturada e TCLE Digital (Fase 1)

> **Requisito Base:** RF-01  
> **Invariantes Relacionadas:** RN07, RN-REG-02, RN-REG-03  
> **Persona:** Juliana Silva (Paciente Espontânea)  
> **Módulos:** `identity`, `triage`, `queue`  
> **Status de Qualidade:** 🟡 **Parcial** *(Endpoint de admissão omite o campo `tcle_hash` no schema `AdmissaoResponse`)*

---

## 1. Narrativa da História (User Voice)

**Como** paciente com sintomas agudos ou dor (Juliana Silva),  
**Quero** preencher rapidamente meus dados essenciais, queixa clínica e aceitar o termo de consentimento (TCLE) em menos de 45 segundos,  
**Para que** eu seja triada de forma segura e ingresse imediatamente na fila de espera virtual sem barreiras burocráticas ou paywalls.

---

## 2. Critérios de Aceite Formais (Gherkin)

### Cenário 1: Acolhimento e admissão com sucesso (Caso Feliz)
- **Dado que** informo meu CPF válido, data de nascimento, telefone celular, queixa principal, sintomas e escala de dor (ex: nível 4),
- **E** manifesto aceite formal ao Termo de Consentimento Livre e Esclarecido (TCLE),
- **Quando** submeto o formulário de admissão em `POST /api/v1/fila/admissao`,
- **Então** o sistema registra a comprovação imutável do consentimento com carimbo de data/hora oficial UTC,
- **E** estratifica o risco clínico preliminar segundo a taxonomia aberta ACR em 5 níveis (ex: Nível 3 - Urgente),
- **E** admite o atendimento na unidade aguardando a validação de elegibilidade,
- **E** persiste atomicamente o evento auditável 'ADMISSAO_PACIENTE' na trilha append-only (ADR-007 / CFM nº 2.314/2022),
- **E** inicia a verificação assíncrona de cobertura em segundo plano sem bloquear a paciente,
- **E** retorna confirmação de admissão (HTTP 201 Created) com identificador do atendimento e credencial provisória de acesso.

### Cenário 2: Detecção de Emergência Iminente (Salvaguarda SAMU 192)
- **Dado que** minhas respostas na triagem inicial acusam sinais clínicos de Nível 1 (Risco Crítico / Vermelho),
- **Quando** tento concluir a admissão,
- **Então** o sistema interrompe imediatamente o acolhimento virtual,
- **E** NÃO insere o atendimento na fila de espera,
- **E** retorna rejeição clínica (HTTP 422 Unprocessable Entity) informando emergência médica,
- **E** fornece orientações audiovisuais para acionamento imediato do SAMU 192 ou deslocamento pré-hospitalar urgente.

### Cenário 3: Ausência de consentimento do TCLE
- **Dado que** preenchi todos os dados clínicos mas não forneci a confirmação de aceite do TCLE,
- **Quando** submeto a requisição,
- **Então** o sistema rejeita a admissão com HTTP 422 e mensagem explicativa sobre a obrigatoriedade legal do consentimento (LGPD Art. 11 / CFM 2.314).

---

## 3. Contrato de API

* **Endpoint:** `POST /api/v1/fila/admissao`
* **Headers:** `X-Tenant-ID: <organizacao_id>`
* **Payload de Entrada (`AdmissaoRequest`):**
  ```json
  {
    "paciente_id": "018f3a5b-...",
    "queixa_principal": "Febre moderada e dor de cabeça há 2 dias",
    "sintomas": ["febre", "cefaleia"],
    "escala_dor": 4,
    "tcle_texto": "Texto integral do termo de consentimento apresentado ao paciente...",
    "medicos_ativos": 2
  }
  ```
* **Resposta Esperada (`201 Created`):**
  ```json
  {
    "atendimento_id": "018f3a5b-...",
    "prioridade_clinica": 3,
    "status_atendimento": "TRIADO_AGUARDANDO_ELEGIBILIDADE",
    "tcle_hash": "a1b2c3d4...",
    "alerta_samu_disparado": false
  }
  ```

---

## 4. Checklist de Inspeção de Código

- [x] **Domínio:** Entidade rica `Triagem` com cálculo de prioridade aberta ACR (`src/modules/triage/domain/classification.py`).
- [x] **Hash TCLE:** Hash SHA-256 gerado e armazenado com timestamp UTC (`src/modules/triage/domain/classification.py`).
- [x] **Aplicação:** `FilaService.admitir_paciente()` orquestra persistência atômica e enfileira job ARQ de elegibilidade (`src/modules/queue/application/services/fila_service.py`).
- [ ] **Apresentação:** Router fino `admissao_router.py` montado em `/api/v1/fila/admissao` (omite campo `tcle_hash` no schema `AdmissaoResponse`).
- [x] **Testes Automatizados:**
  - `tests/unit/test_triage_model.py`
  - `tests/unit/test_admissao_service.py`
  - `tests/integration/test_admissao_integrada_flow.py`
