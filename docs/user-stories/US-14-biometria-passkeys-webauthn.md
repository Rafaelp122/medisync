# US-14 — Autenticação e Registro de Biometria do Dispositivo (Passkeys / WebAuthn)

> **Requisito Base:** RF-01, RF-07 (Segurança e Identidade)  
> **Invariantes Relacionadas:** LGPD Art. 11 (Dados Sensíveis), OWASP ASVS (FIDO2 / Passwordless), W3C WebAuthn Level 3  
> **Persona:** Juliana Silva (Paciente Espontânea)  
> **Módulos:** `identity`, `auth`  
> **Status de Qualidade:** 🔴 **Pendente (Backlog / Issue #115)**

---

## 1. Narrativa da História (User Voice)

**Como** paciente que utiliza o MediSync Express pelo celular ou computador (Juliana Silva),  
**Quero** cadastrar a biometria nativa do meu aparelho (TouchID, FaceID ou impressão digital Android via Passkeys) enquanto aguardo na sala de espera ou ao término do acolhimento,  
**Para que** eu possa me reconectar à fila ou acessar meu histórico clínico futuro com um único toque, ficando totalmente blindada contra golpes de engenharia social por telefone, furto de senhas e clonagem de chip (SIM swap).

---

## 2. Critérios de Aceite Formais (Gherkin)

### Cenário 1: Registro de biometria Passkey durante a espera na fila virtual (Caso Feliz)
- **Dado que** concluí a triagem ou estou aguardando na fila virtual com sessão autenticada,
- **E** meu dispositivo/navegador possui suporte à Web Authentication API (`PublicKeyCredential`),
- **Quando** clico em *"Ativar Biometria deste Aparelho"* no card de segurança da sala de espera,
- **Então** o sistema requisita ao backend as opções de desafio criptográfico em `POST /api/v1/auth/patient/webauthn/register/options`,
- **E** o navegador aciona o sensor biométrico nativo do aparelho (TouchID/FaceID) sem que a imagem da digital ou rosto saia do hardware criptográfico local (Secure Enclave / TPM),
- **Quando** o frontend submete a credencial pública assinada em `POST /api/v1/auth/patient/webauthn/register/verify`,
- **Então** o sistema valida o desafio, registra a chave pública vinculada ao prontuário do paciente (`paciente_id`),
- **E** persiste o evento auditável 'PASSKEY_REGISTRADA' com metadados do autenticador,
- **E** exibe confirmação visual de biometria ativada com sucesso.

### Cenário 2: Autenticação rápida de retorno via biometria (Login em 1 Toque)
- **Dado que** possuo uma Passkey registrada previamente neste navegador ou ecossistema (Apple/Google/Windows),
- **Quando** acesso o MediSync para retomar um atendimento ou acessar meu histórico e clico em *"Entrar com Biometria do Aparelho"*,
- **Então** o sistema obtém o desafio em `POST /api/v1/auth/patient/webauthn/authenticate/options`,
- **E** solicita o toque da digital ou FaceID no dispositivo,
- **E** valida a assinatura criptográfica em `POST /api/v1/auth/patient/webauthn/authenticate/verify`,
- **E** emite o token de acesso Bearer JWT com papel `PACIENTE` e permissões `patient:queue_track` e `patient:doc_view` (HTTP 200 OK) sem necessidade de envio de SMS.

### Cenário 3: Tentativa de ataque por Phishing ou Engenharia Social (Imunidade Criptográfica)
- **Dado que** um terceiro tenta se passar pela clínica ou obter códigos de acesso via ligação telefônica,
- **Quando** o paciente utiliza autenticação por Passkey,
- **Então** não existe nenhum código OTP de 6 dígitos que possa ser transmitido por voz,
- **E** a chave privada nunca deixa o hardware do paciente, tornando a autenticação matematicamente imune a clonagem de chip (SIM swap) e phishing remoto.

---

## 3. Contrato de API

* **Opções de Registro:** `POST /api/v1/auth/patient/webauthn/register/options`
  * *Headers:* `Authorization: Bearer <jwt_paciente>`, `X-Tenant-ID: <org_id>`
  * *Resposta (`200 OK`):*
    ```json
    {
      "challenge": "base64url...",
      "rp": { "name": "MediSync Express", "id": "medisync.app" },
      "user": { "id": "base64url_paciente_id", "name": "Juliana Silva", "displayName": "Juliana Silva" },
      "pubKeyCredParams": [{ "alg": -7, "type": "public-key" }, { "alg": -257, "type": "public-key" }],
      "timeout": 60000,
      "attestation": "none"
    }
    ```

* **Verificação de Registro:** `POST /api/v1/auth/patient/webauthn/register/verify`
  * *Headers:* `Authorization: Bearer <jwt_paciente>`, `X-Tenant-ID: <org_id>`
  * *Payload de Entrada:* Credencial gerada pelo navegador (`id`, `rawId`, `response`, `type: "public-key"`)
  * *Resposta (`200 OK`):* `{ "status": "registrado", "credencial_id": "cred_xyz" }`

* **Opções de Autenticação:** `POST /api/v1/auth/patient/webauthn/authenticate/options`
  * *Headers:* `X-Tenant-ID: <org_id>`
  * *Resposta (`200 OK`):* Desafio e lista de credenciais permitidas (ou desafio aberto para *discoverable credentials*).

* **Verificação de Autenticação:** `POST /api/v1/auth/patient/webauthn/authenticate/verify`
  * *Payload de Entrada:* Assinatura criptográfica do desafio.
  * *Resposta (`200 OK`):* `{ "access_token": "eyJhbGciOi...", "token_type": "bearer", "role": "PACIENTE" }`

---

## 4. Checklist de Inspeção de Código

- [ ] **Modelo:** Tabela `paciente_passkeys` no módulo `identity` com `credential_id`, `public_key`, `sign_count`, `device_name` e `created_at`.
- [ ] **Aplicação:** Serviço `PatientWebAuthnService` utilizando `py_webauthn` para geração de desafios e verificação de assinaturas FIDO2/WebAuthn.
- [ ] **Apresentação:** Router fino `patient_webauthn_router.py` integrado em `/api/v1/auth/patient/webauthn`.
- [ ] **Frontend (ADR-011):** Hook headless `usePasskey` em `frontend/src/features/onboarding/api/` e componente `<BiometriaConviteCard />`.
- [ ] **Testes:** Testes unitários com fakes de WebAuthn e testes de integração com verificação criptográfica.

---

## 5. Critérios de Interface & Experiência (UI/UX, A11y & Troféu de Testes - ADR-011)

### 5.1 Validação e Interação de Tela
- **Detecção Silenciosa de Suporte:** O card de convite à biometria só é renderizado se `window.PublicKeyCredential` for suportado pelo dispositivo.
- **UX Não-Bloqueante na Sala de Espera:** O convite a biometria é exibido como benefício de segurança opcional; recusar ou fechar o card não altera a posição nem o tempo na fila virtual.
- **Feedback Háptico e Acessibilidade:** Uso de estados acessíveis (`aria-live="polite"`, `aria-busy="true"`) durante o acionamento do sensor biométrico.

### 5.2 Troféu de Testes do Frontend
- **Integração de Tela (Vitest + RTL + MSW v2):** Testes de renderização condicional com mock da WebAuthn API no `jsdom`.
- **E2E (Playwright):** Simulação de credencial virtual WebAuthn via CDP (`client.send('WebAuthn.enable')`, `client.send('WebAuthn.addVirtualAuthenticator')`).
