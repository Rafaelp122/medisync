# US-05 — Tratamento de Exceções e Regularização de Elegibilidade

> **Tipo de Especificação:** Fluxo de Contingência e Regra de Negócio Transversal (RN01, RN03)  
> **Jornada Vinculada:** [`US-03 — Validação de Elegibilidade e Onboarding Fase 2`](./US-03-elegibilidade-onboarding-fase2.md)  
> **Requisito Base:** RF-05  
> **Invariantes Relacionadas:** RN01 (Prevalência Clínica), RN03 (Desvio Temporário e Preservação de Antiguidade)  
> **Personas:** Juliana Silva (Paciente) e Patrícia Mendes (Faturamento)  
> **Módulos:** `queue`, `billing`  
> **Status de Qualidade:** 🔴 **Não Conforme** *(Gap crítico NC-QUE-04: `promover_para_apto()` grava `data_entrada_fila = now` tardio violando antiguidade RN01/RN03 e ausência de rota REST de regularização)*

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

---

## 4. Checklist de Inspeção de Código

- [ ] **Preservação de Antiguidade:** Gap crítico NC-QUE-04: `promover_para_apto()` grava `data_entrada_fila = now` tardio violando antiguidade RN01/RN03 (`src/modules/queue/application/services/fila_service.py`).
- [ ] **Rota REST de Regularização:** Ausência de rota REST dedicada para regularização de elegibilidade.
- [x] **Desvio Temporário:** Médico consome exclusivamente o conjunto de aptos, ignorando atendimentos retidos (`src/modules/queue/infrastructure/lua/alocar_chamada.lua`).
- [x] **Testes Automatizados:**
  - `tests/unit/test_queue_scoring.py`
  - `tests/integration/test_eligibility_flow.py`
  - `tests/integration/test_queue_ingestion_and_fifo.py`
