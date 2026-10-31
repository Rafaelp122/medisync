# US-03 — Validação Concorrente de Elegibilidade e Enriquecimento CFM (Fase 2)

> **Requisito Base:** RF-02  
> **Invariantes Relacionadas:** RN03, RN-REG-02 (CFM 1.821/2007 e 2.314/2022)  
> **Personas:** Juliana Silva (Paciente) e Patrícia Mendes (Faturamento)  
> **Módulos:** `identity`, `billing`, `queue`, `worker`  
> **Status de Qualidade:** 🟢 **Conforme**

---

## 1. Narrativa da História (User Voice)

**Como** paciente aguardando atendimento na fila virtual (Juliana Silva),  
**Quero** completar os dados regulatórios exigidos pelo Conselho Federal de Medicina (nome social, nome da mãe, sexo biológico e CEP) enquanto o sistema valida meu convênio em segundo plano,  
**Para que** meu prontuário esteja legalmente conforme e eu seja promovida ao status de apta para consulta médica sem perda de tempo.

---

## 2. Critérios de Aceite Formais (Gherkin)

### Cenário 1: Validação assíncrona de cobertura pública SUS (Caso Feliz Público)
- **Dado que** o atendimento pertence a uma unidade operando em perfil público SUS,
- **Quando** a rotina de validação de elegibilidade em segundo plano executa,
- **Então** a elegibilidade é aprovada de forma imediata com isenção pública,
- **E** o atendimento transiciona para o status de apto para chamada médica,
- **E** a paciente passa a estar disponível para convocação pelos médicos plantonistas.

### Cenário 2: Validação assíncrona no perfil Saúde Suplementar (Privado)
- **Dado que** o atendimento é vinculado a convênio particular,
- **Quando** a rotina assíncrona consulta o gateway da operadora,
- **E** a operadora responde positivamente dentro da tolerância de 15 segundos com token de autorização,
- **Então** o atendimento é confirmado como elegível e promovido a apto para chamada médica.

### Cenário 3: Enriquecimento cadastral Fase 2 e conformidade CFM 1.821
- **Dado que** a paciente preenche o formulário da Fase 2 informando `nome_social` (opcional), nome completo da mãe, sexo biológico e CEP,
- **Quando** submete em `POST /api/v1/onboarding/fase-2`,
- **Então** os dados são registrados no prontuário civil da paciente,
- **E** o endereço é validado para garantia de eventual envio de ambulância pré-hospitalar em emergências.

### Cenário 4: Flexibilidade de autenticação na Fase 2 (Resolução NC-IDN-01)
- **Dado que** a paciente reconectou sua sessão via código OTP (portando JWT de paciente) ou via credencial provisória de admissão,
- **Quando** submete os dados da Fase 2,
- **Então** o sistema aceita ambos os formatos de autenticação sem rejeição indevida de credenciais.

---

## 3. Contrato de API

* **Endpoint:** `POST /api/v1/onboarding/fase-2`
* **Headers:** `X-Tenant-ID: <org_id>`, `Authorization: Bearer <token_intake_ou_jwt>`
* **Payload de Entrada (`OnboardingFase2Request`):**
  ```json
  {
    "paciente_id": "018f3a5b-...",
    "nome_social": "Juliana Santos Silva",
    "nome_mae": "Maria Aparecida Silva",
    "sexo_biologico": "FEMININO",
    "cep": "01310-100",
    "logradouro": "Avenida Paulista",
    "numero": "1000",
    "bairro": "Bela Vista",
    "cidade": "São Paulo",
    "estado": "SP"
  }
  ```
* **Resposta Esperada (`200 OK`):** Retorna DTO atualizado do paciente enriquecido.

---

## 4. Checklist de Inspeção de Código

- [x] **Modelo:** Suporte a `nome_social` e dados completos do CFM em `Paciente` (`src/modules/identity/domain/models/paciente.py`).
- [x] **Worker ARQ:** Tarefa `validar_elegibilidade_task` com idempotência e timeout de 15s (`src/worker/tasks/eligibility.py`).
- [x] **Adaptadores:** `SusEligibilityAdapter` (no-op) e `PrivateInsuranceGatewayAdapter` (`src/modules/billing/infrastructure/adapters/`).
- [x] **Débito NC-IDN-01:** Dependência `validar_intake_fase2` aceitar polimorfismo de token JWT OTP (Resolvido na Issue #76).
- [x] **Frontend (Fase 2 & ViaCEP):** Formulário em `frontend/src/features/onboarding/components/enriquecimento-fase2-form.tsx` com autopreenchimento assíncrono e timeout de 5000ms (`frontend/src/features/onboarding/api/use-via-cep.ts`).
- [x] **Frontend Hook:** `frontend/src/features/onboarding/api/use-enrichment-fase2.ts` integrando com SDK Hey API.
- [x] **Testes Automatizados:**
  - Backend: `tests/unit/test_onboarding_schemas.py`, `tests/unit/test_eligibility_task.py`, `tests/integration/test_eligibility_flow.py`
  - Frontend Schemas: `frontend/src/features/onboarding/schemas/onboarding-schema.test.ts`
  - Frontend Hooks: `frontend/src/features/onboarding/api/__tests__/onboarding-hooks.test.tsx`
  - Frontend Telas: `frontend/src/features/onboarding/tests/enriquecimento-fase2-form.test.tsx`
  - E2E / A11y: `frontend/e2e/onboarding-acolhimento.spec.ts` (`E2E-ONB-01`)

---

## 5. Critérios de Interface & Experiência (UI/UX, A11y & Troféu de Testes - ADR-011)

### 5.1 Enriquecimento Concorrente na Fila (RF-02)
- **Não-bloqueio:** O paciente já possui lugar garantido na fila virtual desde a admissão da Fase 1 e visualiza sua posição estimada enquanto completa o prontuário.
- **Autopreenchimento CEP:** Consulta à API pública ViaCEP (`https://viacep.com.br/ws/${cep}/json/`) com busca automática ao completar 8 dígitos, timeout nativo de 5000ms e desbloqueio manual gracioso em caso de falha de rede ou CEP inexistente.
- **Opção de Pular:** Botão "Completar mais tarde" permitindo seguir na fila sem preenchimento imediato.

### 5.2 Troféu de Testes do Frontend
- **Integração de Tela (Vitest + RTL + MSW v2):**
  - `frontend/src/features/onboarding/tests/enriquecimento-fase2-form.test.tsx`:
    - `IT-ONB-05`: Preenchimento com autopreenchimento dinâmico de endereço via ViaCEP.
    - `IT-ONB-06`: Resiliência em caso de CEP não localizado, permitindo digitação manual.
- **E2E e A11y (Playwright):**
  - `frontend/e2e/onboarding-acolhimento.spec.ts`: Jornada completa validando preenchimento da Fase 2 e transição para o estado confirmado.
