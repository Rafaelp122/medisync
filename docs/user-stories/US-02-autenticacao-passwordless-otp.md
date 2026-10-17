# US-02 — Reconexão e Autenticação Passwordless OTP

> **Requisito Base:** RF-01 (#44)  
> **Invariantes Relacionadas:** RN-REG-02 (LGPD), OWASP ASVS  
> **Persona:** Juliana Silva (Paciente Espontânea)  
> **Módulos:** `auth`, `identity`  
> **Status de Qualidade:** 🟢 **Conforme**

---

## 1. Narrativa da História (User Voice)

**Como** paciente com urgência de saúde que teve a conexão interrompida ou trocou de dispositivo (Juliana Silva),  
**Quero** me autenticar informando apenas meu número de telefone celular e um código de 6 dígitos recebido por SMS/WhatsApp,  
**Para que** eu recupere o acesso à minha sessão de atendimento sem precisar criar ou lembrar de senhas complexas em um momento de vulnerabilidade.

---

## 2. Critérios de Aceite Formais (Gherkin)

### Cenário 1: Solicitação e verificação de OTP com sucesso (Caso Feliz)
- **Dado que** informo meu telefone celular previamente cadastrado em formato internacional válido,
- **Quando** solicito o código de acesso em `POST /api/v1/auth/patient/otp/request`,
- **Então** o sistema gera um código numérico temporário de 6 dígitos com validade de 5 minutos,
- **E** encaminha o código para o canal de mensageria da paciente.
- **Quando** submeto o código correto dentro da janela de validade em `POST /api/v1/auth/patient/otp/verify`,
- **Então** o sistema valida a autenticidade, invalida o código consumido para impedir reuso,
- **E** emite uma credencial de acesso com o papel de `PACIENTE` (HTTP 200 OK).

### Cenário 2: Proteção contra força bruta (Rate Limiting de Tentativas)
- **Dado que** ocorre uma tentativa de adivinhar o código OTP submetendo valores incorretos,
- **Quando** são registradas 3 tentativas consecutivas com código inválido,
- **Então** o sistema invalida sumariamente o código ativo,
- **E** bloqueia novas tentativas imediatas por excesso de requisições (HTTP 429 Too Many Requests), exigindo nova solicitação de OTP.

### Cenário 3: Proteção contra flooding de envio de mensagens
- **Dado que** solicitei o envio de código OTP recentemente,
- **Quando** tento solicitar novo envio mais de 3 vezes em um intervalo de 15 minutos,
- **Então** o sistema bloqueia preventivamente o envio com HTTP 429, instruindo aguardar o encerramento da janela de proteção.

---

## 3. Contrato de API

* **Solicitação:** `POST /api/v1/auth/patient/otp/request`
  ```json
  { "telefone": "+5511999998888" }
  ```
  *Resposta (`200 OK`):* `{ "mensagem": "Código enviado com sucesso.", "expira_em_segundos": 300 }`

* **Validação:** `POST /api/v1/auth/patient/otp/verify`
  ```json
  {
    "telefone": "+5511999998888",
    "codigo": "123456"
  }
  ```
  *Resposta (`200 OK`):*
  ```json
  {
    "access_token": "eyJhbGciOi...",
    "token_type": "bearer",
    "role": "PACIENTE",
    "paciente_id": "018f3a5b-..."
  }
  ```

---

## 4. Checklist de Inspeção de Código

- [x] **Segurança Criptográfica:** Geração via CSPRNG (`secrets.choice`) e armazenamento com hash SHA-256 no Valkey com TTL de 300s (`src/modules/auth/application/services/patient_auth_service.py`).
- [x] **Proteção de Acesso:** Rate limiting com contadores voláteis no Valkey bloqueando após 3 falhas ou 3 envios/15min (`patient_auth_service.py`).
- [x] **Apresentação:** Router fino `patient_auth_router.py` integrado em `src/modules/auth/presentation/routers/`.
- [x] **Testes Automatizados:**
  - `tests/unit/test_patient_auth_service.py`
  - `tests/integration/test_patient_auth_endpoints.py`
