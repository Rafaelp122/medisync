# US-11 — Conclusão de Atendimento e Consolidação Ambulatorial SUS (BPA-I)

> **Requisito Base:** RF-08  
> **Invariantes Relacionadas:** RN-NEG-01 (Universalidade e Ponto de Telessaúde Regulamentado), ADR-012  
> **Persona:** Patrícia Mendes (Coordenadora de Produção Ambulatorial do Consórcio Intermunicipal)  
> **Módulos:** `ambulatory`, `consultation`, `queue`  
> **Status de Qualidade:** 🟢 **Conforme**

---

## 1. Narrativa da História (User Voice)

**Como** coordenadora de produção ambulatorial do consórcio intermunicipal (Patrícia Mendes),  
**Quero** que a finalização da teleconsulta médica no PEP acione automaticamente a consolidação do procedimento em lote de faturamento SUS (BPA-I / SISAB sob o código SIGTAP `03.01.01.025-0` e ponto de telessaúde CNES 160/006),  
**Para que** o consórcio e os municípios consorciados comprovem a produção assistencial pública junto ao Ministério da Saúde, viabilizem o incentivo financeiro eMulti (Portaria GM/MS nº 635/2023) e mantenham o registro ambulatorial 100% auditável sem glosas ou duplicidades.

---

## 2. Critérios de Aceite Formais (Gherkin)

### Cenário 1: Consolidação automática de teleconsulta SUS em lote BPA-I após encerramento do prontuário
- **Dado que** o médico assistente conclui formalmente o atendimento clínico no prontuário eletrônico em `POST /api/v1/consultations/{id}/finalize`,
- **Quando** o encerramento do prontuário é efetivado com notas SOAP e documentos clínicos assinados,
- **Então** o sistema aciona internamente o serviço de produção ambulatorial (`ProducaoAmbulatorialService`),
- **E** associa o procedimento executado ao código SIGTAP `03.01.01.025-0` (Consulta / Teleconsulta na Atenção Básica) e caráter de atendimento `02` (Urgência),
- **E** vincula a produção ao CNES da unidade de telessaúde (ponto de telessaúde CNES 160/006),
- **E** consolida o registro com status `CONSOLIDADO` na competência mensal corrente (`YYYYMM`), pronto para exportação BPA-I / SISAB.

### Cenário 2: Validação de consistência cadastral (CNS/CPF, carimbo temporal, CBO)
- **Dado que** a teleconsulta foi concluída e está apta para consolidação ambulatorial SUS,
- **Quando** a rotina de produção processa os metadados do atendimento,
- **Então** valida a consistência cadastral do paciente (presença de CPF ou Cartão Nacional de Saúde - CNS válido e data de nascimento),
- **E** valida a qualificação do profissional de saúde (CBO médico, identificador e carimbo temporal da consulta),
- **E** em caso de inconformidade cadastral impeditiva para lote oficial, registra a pendência cadastral em auditoria sem bloquear a entrega de receitas e atestados emitidos ao paciente.

### Cenário 3: Idempotência na consolidação ambulatorial (reprocessamento não duplica registros BPA-I)
- **Dado que** um atendimento médico já teve seu registro de produção ambulatorial consolidado anteriormente,
- **Quando** uma rotina de reprocessamento ou chamada subsequente tenta consolidar o mesmo `atendimento_id`,
- **Então** o serviço ambulatorial detecta o registro preexistente pelo identificador único de atendimento,
- **E** retorna o DTO de produção ambulatorial existente sem persistir novas linhas na tabela `producoes_ambulatoriais`,
- **E** previne a duplicação de faturamento público e inconformidades no lote BPA-I perante o Datasus.

---

## 3. Contrato de Integração e Domínio

* **Invocação Interna:** Acionada internamente pelo encerramento de consulta no PEP (`src/modules/consultation/application/services/pep_service.py:PEPService.finalizar_consulta`) ou rotinas de produção ambulatorial, consumindo `src/modules/ambulatory/application/services/producao_service.py:ProducaoAmbulatorialService`.
* **Comando de Entrada (`ConsolidarTeleconsultaCommand`):**
  - `atendimento_id`: UUIDv7 do atendimento concluído.
  - `profissional_id`: UUIDv7 do médico assistente.
  - `paciente_id`: UUIDv7 do paciente atendido.
  - `cnes`: Código CNES do ponto de telessaúde (até 7 dígitos).
  - `codigo_sigtap`: `"03.01.01.025-0"` (padrão teleconsulta SUS).
  - `carater_atendimento`: `"02"` (urgência ambulatorial).
* **DTO de Saída (`BpaProducaoDTO`):**
  - `atendimento_id`: UUIDv7 do atendimento.
  - `cnes`: Código CNES da unidade.
  - `codigo_sigtap`: Procedimento SIGTAP consolidado.
  - `carater_atendimento`: Caráter do atendimento.
  - `consolidado_em`: Carimbo de data/hora UTC de consolidação.
* **Evento de Auditoria Forense:**
  - Emissão compulsória do evento `PRODUCAO_AMBULATORIAL_CONSOLIDADA` (Módulo: `ambulatory`, Ator: `SISTEMA` / `WORKER_ARQ`), registrando `sigtap`, `cnes`, `atendimento_id` e tenant municipal (`organizacao_id`) sob RLS PostgreSQL.

---

## 4. Checklist de Inspeção de Código

- [x] **Modelo de Produção Ambulatorial:** Entidade rica `ProducaoAmbulatorial` com multi-tenant PostgreSQL RLS (`src/modules/ambulatory/domain/models/producao_ambulatorial.py`) e migração `migrations/versions/0012_producao_ambulatorial_bpa.py`.
- [x] **Serviço de Consolidação e BPA-I:** `ProducaoAmbulatorialService` com suporte a SIGTAP `03.01.01.025-0` e verificação estrita de idempotência (`src/modules/ambulatory/application/services/producao_service.py`).
- [x] **DTOs de Aplicação:** `ConsolidarTeleconsultaCommand` e `BpaProducaoDTO` em `src/modules/ambulatory/application/dtos.py`.
- [x] **Composition Root de Ambulatory:** `src/modules/ambulatory/composition.py` exportando `get_producao_ambulatorial_service` e `ProducaoAmbulatorialServiceDep`.
- [x] **Testes Automatizados:** Testes unitários para o modelo e serviço em `tests/unit/test_ambulatory_production_service.py`.

