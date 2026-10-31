# US-15 — Verificação Facial e Prova de Vida para Receituário de Controle Especial

> **Requisito Base:** RF-07 (Prescrição e Documentos Clínicos), Portaria SVS/MS nº 344/1998, Resolução CFM nº 2.314/2022  
> **Invariantes Relacionadas:** LGPD Art. 11 (Dados Pessoais Sensíveis / Biometria), RDC ANVISA 20/2011  
> **Personas:** Dr. Eduardo Rocha (Médico Plantonista) e Juliana Silva (Paciente)  
> **Módulos:** `consultation`, `identity`  
> **Status de Qualidade:** 🔴 **Pendente (Backlog / Issue #116)**

---

## 1. Narrativa da História (User Voice)

**Como** médico plantonista em teleconsulta ao prescrever substâncias sob controle especial (Dr. Eduardo Rocha),  
**Quero** que o sistema exija uma prova de vida facial com detecção de vivacidade (*liveness detection*) da paciente antes da emissão de medicamentos de alto risco ou tarja preta permitidos,  
**Para que** a instituição comprove perante a ANVISA, CFM e conselhos regionais que a pessoa examinada em vídeo é a titular legítima do CPF, impedindo golpes de falsidade ideológica e usurpação de identidade para obtenção ilícita de psicotrópicos.

---

## 2. Critérios de Aceite Formais (Gherkin)

### Cenário 1: Acionamento automático da prova de vida para substâncias de controle especial (Caso Feliz)
- **Dado que** o médico prescreve um medicamento de controle especial (ex: Lista C1/C5 da Portaria 344/98 permitida com receita digital),
- **E** a organização possui política ativa de verificação biométrica para receituário de controle,
- **Quando** o médico clica em *"Emitir e Assinar Receita de Controle Especial"*,
- **Então** o sistema suspende temporariamente a emissão e solicita a verificação facial da paciente em `POST /api/v1/consultations/{id}/prescriptions/liveness/challenge`,
- **E** abre na tela da paciente uma janela segura guiada para captura da prova de vida com verificação de vivacidade ativa (piscar, sorrir ou movimento de cabeça),
- **Quando** a imagem e os frames de vivacidade são validados com score de confiança superior a 95% via adaptador do provedor (`LivenessVerificationPort`),
- **Então** o sistema registra a comprovação biométrica auditável com hash SHA-256 no prontuário,
- **E** libera o fluxo de assinatura digital ICP-Brasil do médico.

### Cenário 2: Falha ou detecção de spoofing (Foto estática / Deepfake)
- **Dado que** uma foto estática, vídeo pré-gravado ou máscara é apresentada à câmera durante a prova de vida,
- **Quando** o algoritmo de liveness processa os frames,
- **Então** o sistema rejeita a verificação com HTTP 422 Unprocessable Entity (`code: SPOOFING_FACIAL_DETECTADO`),
- **E** notifica o médico no painel clínico sobre a suspeita de fraude de identidade,
- **E** bloqueia sumariamente a emissão do receituário de controle especial, registrando o incidente na trilha de auditoria append-only (ADR-007).

### Cenário 3: Exceção de urgência médica justificada
- **Dado que** a paciente encontra-se em condição clínica aguda com incapacidade motora transitória para completar a prova de vida facial,
- **Quando** o médico avalia a situação e decide pela soberania clínica do ato médico,
- **Então** o médico pode assinalar a justificativa médica circunstanciada no prontuário PEP,
- **E** o sistema autoriza a emissão com carimbo de auditoria de exceção médica documentada.

---

## 3. Contrato de API

* **Solicitação de Desafio de Prova de Vida:** `POST /api/v1/consultations/{atendimento_id}/prescriptions/liveness/challenge`
  * *Headers:* `Authorization: Bearer <jwt_medico>`, `X-Tenant-ID: <org_id>`
  * *Resposta (`200 OK`):*
    ```json
    {
      "challenge_id": "ch_018f3a5b...",
      "instrucoes_movimento": ["piscar_olhos", "sorrir"],
      "timeout_segundos": 60
    }
    ```

* **Validação de Prova de Vida pelo Paciente:** `POST /api/v1/consultations/{atendimento_id}/prescriptions/liveness/verify`
  * *Headers:* `Authorization: Bearer <jwt_paciente>`, `X-Tenant-ID: <org_id>`
  * *Payload de Entrada:*
    ```json
    {
      "challenge_id": "ch_018f3a5b...",
      "liveness_payload": "base64_encoded_frames...",
      "geolocalizacao": { "latitude": -23.5505, "longitude": -46.6333 }
    }
    ```
  * *Resposta (`200 OK`):*
    ```json
    {
      "status": "APROVADO",
      "liveness_score": 0.98,
      "verificacao_hash": "sha256_e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "validado_em": "2026-10-31T12:00:00Z"
    }
    ```

---

## 4. Checklist de Inspeção de Código

- [ ] **Porta Arquitetural:** `LivenessVerificationPort` em `src/modules/consultation/application/ports/` (PEP 544 Protocol).
- [ ] **Adaptadores:** `GovBrLivenessAdapter`, `DatavalidLivenessAdapter` e `MockLivenessAdapter` para testes em memória.
- [ ] **Regra Farmacêutica:** Interceptador no `PrescriptionService` disparando a verificação apenas quando a classe do fármaco for Lista C1/C5 ou política da organização.
- [ ] **Frontend:** Componente modal `<CameraLivenessCheck />` em `frontend/src/features/consultation/components/`.
- [ ] **Testes:** Testes unitários com fakes de provedores de biometria e testes de integração com bloqueio de prescrição sem liveness prévio.

---

## 5. Critérios de Interface & Experiência (UI/UX, A11y & Troféu de Testes - ADR-011)

### 5.1 Validação e Interação de Tela
- **Guia Visual de Enquadramento:** Círculo/oval semântico com feedback de cor (amarelo: aproxime o rosto; verde: enquadramento ideal; azul: capturando).
- **Instruções Auditivas e Textuais:** Mensagens claras em português ("Pisque os olhos lentamente", "Olhe fixamente para a tela") com `aria-live="assertive"`.
- **Fallbacks Acessíveis:** Opção de justificativa assistencial pelo médico se o paciente tiver deficiência motora severa.

### 5.2 Troféu de Testes do Frontend
- **Integração de Tela (Vitest + RTL + MSW v2):** Renderização de `<CameraLivenessCheck />` com mock do stream de mídia (`navigator.mediaDevices.getUserMedia`).
