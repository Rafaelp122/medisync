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

### Cenário 4: Gate Mandatório de Conferência de Identidade Visual e Documento Oficial (CFM nº 2.314/2022)
- **Dado que** o médico plantonista está em videoconferência ativa com a paciente,
- **Quando** realiza a abertura da teleconsulta,
- **Então** o médico deve solicitar a apresentação de documento oficial com foto (RG/CNH/CNS) na câmera e registrar no PEP a validação de identidade (`identidade_verificada: true`, `tipo_documento_apresentado: "RG"` ou justificativa formal em caso de impossibilidade/urgência extrema),
- **E** a interface do prontuário bloqueia preventivamente o comando de finalização e a assinatura de prescrições enquanto a identidade não for confirmada,
- **E** a confirmação é registrada com carimbo de tempo oficial na evolução clínica do atendimento (ADR-007).

### Cenário 5: Estação Médica Clínica Single-Pane e Topologia de Rotas Teleconsulta (Issue #141)
- **Dado que** o médico Dr. Eduardo Rocha acessa a rota protegida `/medico` (`frontend/src/routes/medico.tsx`) e a paciente acessa a sala de teleconsulta em `/chamada` (`frontend/src/routes/chamada.tsx`),
- **Quando** aloca um paciente da fila virtual via "Chamar Próximo Paciente",
- **Então** o sistema renderiza simultaneamente a tela unificada do médico em 3 colunas:
  1. **Coluna 1 (Esquerda):** Mídia WebRTC LiveKit, badge passivo de TMA decorrido (RN06) e Gate CFM nº 2.314/2022 com conferência visual de RG/CNH/CNS;
  2. **Coluna 2 (Centro):** Prontuário Eletrônico com classificação Manchester via variantes canônicas de `Badge` (`nivel1` a `nivel5`) com tokens semânticos OKLCH e histórico de documentos clínicos emitidos;
  3. **Coluna 3 (Direita):** Editor SOAP estruturado, prescritor digital com salvaguarda da Portaria 344/98 e acionamento de conclusão com assinatura ICP-Brasil;
- **E** todas as atualizações de formulários e controles WebRTC ocorrem sem perda de foco, sem re-renders indesejados da árvore e sem navegação entre abas,
- **E** ao finalizar a consulta médica ou desconectar a chamada, a paciente é automaticamente redirecionada para a rota pós-consulta `/pos-consulta` (`frontend/src/routes/pos-consulta.tsx`).

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
    "conduta": "Prescrito Amoxicilina 500mg por 7 dias e repouso.",
    "identidade_verificada": true,
    "tipo_documento_verificado": "RG",
    "justificativa_excecao_identidade": null
  }
  ```
* **Resposta Esperada (`200 OK`):** Retorna o objeto da evolução clínica persistida.

---

## 4. Checklist de Inspeção de Código

- [x] **Modelo:** Entidade `EvolucaoClinica` com campos SOAP, CID-10, campos de conferência de identidade e flags de finalização (`src/modules/consultation/domain/models/evolucao_clinica.py`).
- [x] **Imutabilidade e Salvaguarda:** Guardas de finalização bloqueiam alterações pós-fechamento e exigem verificação de identidade antes da emissão de prescrição digital (`PEPService.salvar_soap()`).
- [x] **Apresentação Backend:** Router fino `consultation_router.py` integrado em `/api/v1/consultations`.
- [x] **Frontend Workstation Single-Pane:**
  - Rotas dedicadas: `/medico` (`frontend/src/routes/medico.tsx`), `/chamada` (`frontend/src/routes/chamada.tsx`) e `/pos-consulta` (`frontend/src/routes/pos-consulta.tsx`) (Issue #141)
  - Componente mestre: `frontend/src/features/consultation/components/doctor-workstation.tsx`
  - Painéis compostos: `workstation-media-pane.tsx` (isolado com `React.memo` para blindar o streaming WebRTC contra re-renders acidentais por digitação SOAP ou telemetria), `video-pane.tsx`, `medical-records-pane.tsx`, `soap-editor.tsx`, `prescription-builder.tsx` (decomposto em `prescription-form.tsx`, `atestado-form.tsx`, `prescription-items-list.tsx`), `cfm-identity-gate.tsx`, `finalize-consultation-modal.tsx`, `tma-timer-badge.tsx`
  - Hooks TanStack Query: `frontend/src/features/consultation/api/`
  - Schemas Zod: `frontend/src/features/consultation/schemas/consultation-schema.ts`
- [x] **Testes Automatizados:**
  - `tests/unit/test_pep_soap_service.py`
  - `tests/integration/test_consultation_endpoints.py`
  - `tests/integration/test_pep_transaction.py`
  - `frontend/src/features/consultation/schemas/consultation-schema.test.ts`
  - `frontend/src/features/consultation/api/__tests__/consultation-hooks.test.tsx`
  - `frontend/src/features/consultation/api/__tests__/use-download-document-pdf.test.tsx`
  - `frontend/src/features/consultation/tests/medical-records-pane.test.tsx`
  - `frontend/src/features/consultation/tests/consultation-workstation.test.tsx`
  - `frontend/src/features/consultation/tests/doctor-workstation-performance.test.tsx`
  - `frontend/src/features/consultation/tests/prescription-builder.test.tsx`
