# US-05 — Tratamento de Exceções e Regularização de Elegibilidade

> **Tipo de Especificação:** Fluxo de Contingência e Regra de Negócio Transversal (RN01, RN03)  
> **Jornada Vinculada:** [`US-03 — Validação de Elegibilidade e Onboarding Fase 2`](./US-03-elegibilidade-onboarding-fase2.md)  
> **Requisito Base:** RF-05  
> **Invariantes Relacionadas:** RN01 (Prevalência Clínica), RN03 (Desvio Temporário e Preservação de Antiguidade)  
> **Personas:** Juliana Silva (Paciente) e Patrícia Mendes (Faturamento)  
> **Módulos:** `queue`, `billing`  
> **Status de Qualidade:** 🟢 **Conforme** *(Resolução NC-QUE-04: preservação de timestamp de acolhimento original e endpoint REST de regularização/contingência)*

---

## 1. Narrativa da Regra (User Voice)

**Como** paciente com pendência temporária de convênio ou divergência cadastral (Juliana Silva),  
**Quero** permanecer na esteira virtual enquanto regularizo minha cobertura sem ser sumariamente expulsa da unidade,  
**Para que**, ao confirmar a autorização ou optar por contingência particular/SUS, eu seja promovida a apta preservando meu tempo de espera original na fila.

---

## 2. Critérios de Aceite Formais (Gherkin)

### Cenário 1: Reprovação temporária não expulsa o paciente da unidade
- **Dado que** a validação com a operadora de saúde resultou em rejeição cadastral ou timeout de 15 segundos,
- **Quando** o resultado da elegibilidade é registrado,
- **Então** o atendimento permanece aguardando regularização ou opção de contingência,
- **E** NÃO é disponibilizado para a equipe médica enquanto a cobertura estiver pendente,
- **E** os médicos plantonistas continuam convocando normalmente os demais pacientes aptos da fila (desvio temporário RN03).

### Cenário 2: Regularização recupera antiguidade original (Score Imutável)
- **Dado que** o paciente regulariza sua autorização de convênio ou migra para contingência 20 minutos após o ingresso inicial,
- **Quando** o sistema processa a aprovação da elegibilidade,
- **Então** o atendimento transiciona para apto para atendimento médico,
- **E** a priorização do paciente na fila é calculada com base no carimbo de data/hora do acolhimento inicial,
- **E** o paciente assume imediatamente a posição prioritária que lhe cabia por antiguidade clínica, sem ser penalizado pela lentidão do convênio.

---

## 3. Contrato de Domínio / Regra de Priorização

* **Cálculo de Priorização Dinâmica (RN01):**
  $$\text{Prioridade Efetiva} = (\text{Nível Clínico} \times 10^{12}) + \text{Timestamp}(\text{Momento do Acolhimento})$$
* A regularização promove o atendimento na fila de aptos preservando integralmente o timestamp original de entrada.
* **Endpoint de Regularização:**
  - `POST /api/v1/fila/atendimentos/{atendimento_id}/regularizar`
  - Headers: `X-Tenant-ID: <org_id>`, `Authorization: Bearer <token_intake_ou_jwt>`
  - Request: `src/modules/queue/presentation/schemas.py:RegularizacaoFilaRequest`
  - Response: `src/modules/queue/presentation/schemas.py:RegularizacaoFilaResponse`
  - **Prevalência Assistencial e Desacoplamento da Fase 2 (CFM 2.314/2022 / RN-NEG-01):** A contingência assistencial promove imediatamente o atendimento com base no TCLE forense (RN07), assegurando o acesso médico sem paywall burocrático. O preenchimento da Fase 2 (CFM 1.821/2007) corre em paralelo e é exigido para o fechamento do prontuário eletrônico e emissão de receitas médicas.

---

## 4. Checklist de Inspeção de Código

- [x] **Preservação de Antiguidade:** Gap crítico NC-QUE-04 resolvido em `Atendimento.promover_para_apto()` e `FilaService.regularizar_atendimento()` (`src/modules/queue/application/services/fila_service.py`).
- [x] **Rota REST de Regularização:** Endpoint dedicado `POST /api/v1/fila/atendimentos/{atendimento_id}/regularizar` em `src/modules/queue/presentation/routers/fila_router.py`.
- [x] **Desvio Temporário:** Médico consome exclusivamente o conjunto de aptos, ignorando atendimentos retidos (`src/modules/queue/infrastructure/lua/alocar_chamada.lua`).
- [x] **Testes Automatizados:**
  - `tests/unit/test_queue_scoring.py`
  - `tests/unit/test_atendimento_model.py`
  - `tests/unit/test_fila_regularizacao.py`
  - `tests/unit/test_fila_router.py`
  - `tests/integration/test_eligibility_flow.py`
  - `tests/integration/test_queue_ingestion_and_fifo.py`
  - `tests/integration/test_regularizacao_flow.py`
