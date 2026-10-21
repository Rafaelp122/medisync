# US-09 — Teleconsulta, Registro PEP SOAP e Soberania Médica

> **Requisito Base:** RF-07  
> **Invariantes Relacionadas:** RN06 (Sem Desconexão Forçada por TMA), RN-REG-01 (CFM 2.314/2022)  
> **Persona:** Dr. Eduardo Rocha (Médico Plantonista)  
> **Módulos:** `consultation`, `queue`  
> **Status de Qualidade:** 🟢 **Conforme**

---

## 1. Narrativa da História (User Voice)

**Como** médico plantonista em teleconsulta com o paciente (Dr. Eduardo Rocha),  
**Quero** registrar a evolução clínica estruturada no padrão PEP SOAP (Subjetivo, Objetivo, Avaliação, Plano) e diagnosticar via CID-10,  
**Para que** o histórico clínico seja arquivado com rigor legal sem o risco de ser interrompido ou desconectado pelo sistema caso a consulta exceda o TMA previsto.

---

## 2. Critérios de Aceite Formais (Gherkin)

### Cenário 1: Registro e atualização da evolução SOAP durante a consulta (Caso Feliz)
- **Dado que** estou em atendimento médico ativo (`EM_ATENDIMENTO`) com o paciente,
- **Quando** submeto as notas de anamnese, exame físico virtual, hipótese diagnóstica CID-10 e conduta em `POST /api/v1/consultations/{id}/soap`,
- **Então** o registro da evolução clínica é arquivado com sucesso no prontuário,
- **E** persiste atomicamente o evento auditável 'EVOLUCAO_SOAP_REGISTRADA' na trilha append-only (ADR-007),
- **E** o sistema permite atualizações e complementações incrementais enquanto a consulta médica permanecer aberta.

### Cenário 2: Preservação Soberana do Ato Médico (Estouro de TMA sem desconexão forçada)
- **Dado que** o TMA previsto da unidade é de 15 minutos e a complexidade clínica da consulta alcança 25 minutos,
- **Quando** o tempo estimado é ultrapassado,
- **Então** o sistema exibe apenas um indicador visual passivo de tempo transcorrido no prontuário,
- **E** NÃO desconecta a videoconferência nem bloqueia as ações do médico, garantindo a soberania do ato médico (CFM 2.314/2022 e RN06).

### Cenário 3: Imutabilidade após a finalização da consulta
- **Dado que** finalizei formalmente o atendimento clínico através do comando de conclusão,
- **E** o sistema persistiu atomicamente o evento auditável 'CONSULTA_FINALIZADA' com transição de EM_ATENDIMENTO para CONCLUIDO (ADR-007),
- **Quando** qualquer usuário tenta submeter nova alteração clínica no SOAP desse atendimento encerrado,
- **Então** o sistema bloqueia a mutação (HTTP 409 Conflict ou 422 Unprocessable Entity), garantindo a imutabilidade do prontuário médico.

---

## 3. Contrato de API

* **Endpoint:** `POST /api/v1/consultations/{atendimento_id}/soap`
* **Headers:** `Authorization: Bearer <jwt_medico>`, `X-Tenant-ID: <org_id>`
* **Payload de Entrada (`SoapNotesRequest`):**
  ```json
  {
    "anamnese": "Paciente refere dor de garganta, febre aferida em 38.5C e tosse seca.",
    "exame_fisico_virtual": "Orofaringe hiperemiada com exsudato purulento amigdaliano.",
    "cid10_principal": "J03.0",
    "conduta": "Prescrito Amoxicilina 500mg por 7 dias e repouso."
  }
  ```
* **Resposta Esperada (`200 OK`):** Retorna o objeto da evolução clínica persistida.

---

## 4. Checklist de Inspeção de Código

- [x] **Modelo:** Entidade `EvolucaoClinica` com campos SOAP, CID-10 e flags de finalização (`src/modules/consultation/domain/models/evolucao_clinica.py`).
- [x] **Imutabilidade:** Guardas de finalização bloqueiam alterações pós-fechamento (`PEPService.salvar_soap()`).
- [x] **Apresentação:** Router fino `consultation_router.py` integrado em `/api/v1/consultations`.
- [x] **Testes Automatizados:**
  - `tests/unit/test_pep_soap_service.py`
  - `tests/integration/test_consultation_endpoints.py`
  - `tests/integration/test_pep_transaction.py`
