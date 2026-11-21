# US-03 — Validação Concorrente de Elegibilidade e Enriquecimento CFM (Fase 2)

> **Requisito Base:** RF-02  
> **Invariantes Relacionadas:** RN03, RN-REG-02 (CFM 1.821/2007 e 2.314/2022)  
> **Personas:** Juliana Silva (Paciente) e Patrícia Mendes (Coordenação de Regulação e Produção Ambulatorial)  
> **Módulos:** `identity`, `ambulatory`, `queue`, `worker`  

> **Status de Qualidade:** 🟢 **Conforme**

---

## 1. Narrativa da História (User Voice)

**Como** paciente aguardando atendimento na fila virtual ou acessando meu perfil no portal SUS (Juliana Silva),  
**Quero** completar os dados regulatórios exigidos pelo Conselho Federal de Medicina (nome social, nome da mãe, sexo biológico e CEP) enquanto o sistema realiza a qualificação cadastral SUS em segundo plano,  
**Para que** meu prontuário esteja legalmente conforme sem bloqueios burocráticos ou financeiros ao atendimento.

---

## 2. Critérios de Aceite Formais (Gherkin)

### Cenário 1: Qualificação cadastral pública SUS (Caso Feliz Universal)
- **Dado que** o atendimento pertence a uma unidade do Sistema Único de Saúde (100% SUS, ADR-012),
- **Quando** a rotina de qualificação cadastral em segundo plano executa,
- **Então** a elegibilidade é aprovada imediatamente com isenção pública universal (`SUS-ISENTO`),
- **E** o atendimento permanece ou é promovido para `APTO_PARA_CHAMADA`,
- **E** a paciente fica disponível para convocação pelos médicos plantonistas sem qualquer paywall.

### Cenário 2: Atualização cadastral CFM contínua no Portal do Cidadão (`/perfil`)
- **Dado que** a paciente pulou o enriquecimento na fila ou retornou posteriormente ao Portal do Cidadão (`/perfil`),
- **Quando** preenche e submete `EnriquecimentoFase2Form` em `POST /api/v1/onboarding/fase-2`,
- **Então** os dados civis e de endereço do prontuário são atualizados com sucesso sem exigir nova entrada na fila de pronto-atendimento.

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
* **Headers:** `Authorization: Bearer <token_intake_ou_jwt>`
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
- [x] **Adaptadores:** `SusEligibilityAdapter` (isenção universal `SUS-ISENTO` no SUS / ADR-012) em `src/modules/ambulatory/infrastructure/adapters/sus_adapter.py`.
- [x] **Débito NC-IDN-01:** Dependência `validar_intake_fase2` aceitar polimorfismo de token JWT OTP (Resolvido na Issue #76).
- [x] **Frontend (Fase 2, ViaCEP & `/perfil`):** Formulário em `frontend/src/features/onboarding/components/enriquecimento-fase2-form.tsx` com autopreenchimento assíncrono e timeout de 5000ms (`frontend/src/features/onboarding/api/use-via-cep.ts`), integrado tanto à sala de espera `/fila` quanto ao perfil do cidadão em `/perfil` (`frontend/src/routes/perfil.tsx`, `ProfilePage`).
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
