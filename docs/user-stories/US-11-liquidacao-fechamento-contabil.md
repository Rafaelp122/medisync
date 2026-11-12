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
- **E** devolve a produção existente sem criar novo registro duplicado no banco nem emitir novo evento de auditoria.

### Cenário 4: Listagem paginada da produção ambulatorial consolidada por competência
- **Dado que** o gestor municipal ou coordenador de faturamento do consórcio precisa auditar a produção,
- **Quando** requisita `GET /api/v1/ambulatory/producao?competencia=YYYYMM` com token corporativo autorizado,
- **Então** o sistema valida a competência no formato `YYYYMM`,
- **E** devolve a listagem paginada de itens consolidados com contagem total e metadados de paginação.

### Cenário 5: Exportação e download do arquivo magnético BPA-I do SIA-SUS
- **Dado que** a competência mensal está fechada para envio ao DATASUS / Ministério da Saúde,
- **Quando** o coordenador de faturamento aciona `GET /api/v1/ambulatory/producao/exportar?competencia=YYYYMM`,
- **Então** o sistema gera o arquivo magnético posicional em ASCII puro,
- **E** formata a linha de cabeçalho tipo 01 com 130 caracteres e checksum `cbc-smt-vrf` no intervalo `[1111..2221]`,
- **E** formata as linhas de detalhe individualizado tipo 03 com 152 caracteres e paginação de 20 registros por folha,
- **E** devolve o arquivo com header `Content-Disposition: attachment; filename="BPA_I_{competencia}_{cnes}.txt"`.

---

## 3. Contrato de Integração e Domínio

* **Invocação Interna:** Acionada internamente pelo encerramento de consulta no PEP (`src/modules/consultation/application/services/pep_service.py:PEPService.finalizar_consulta`) ou rotinas de produção ambulatorial, consumindo `src/modules/ambulatory/application/services/producao_service.py:ProducaoAmbulatorialService`.
* **Endpoints HTTP:** `GET /api/v1/ambulatory/producao` (listagem) e `GET /api/v1/ambulatory/producao/exportar` (download magnético DATASUS).
* **Comando de Entrada (`ConsolidarTeleconsultaCommand`):**
  - `atendimento_id`: UUIDv7 do atendimento concluído.
  - `profissional_id`: UUIDv7 do médico assistente.
  - `paciente_id`: UUIDv7 do paciente atendido.
  - `cnes`: Código CNES do ponto de telessaúde (até 7 dígitos).
  - `codigo_sigtap`: `"03.01.01.025-0"` (padrão teleconsulta SUS).
  - `carater_atendimento`: `"02"` (urgência ambulatorial).
* **DTO de Saída (`BpaProducaoDTO` e `BpaArquivoExportadoDTO`):**
  - `atendimento_id`: UUIDv7 do atendimento.
  - `cnes`: Código CNES da unidade.
  - `codigo_sigtap`: Procedimento SIGTAP consolidado.
  - `carater_atendimento`: Caráter do atendimento.
  - `consolidado_em`: Carimbo de data/hora UTC de consolidação.
  - `conteudo`: Texto plano posicional formatado para o aplicativo BPA-Mag.
* **Evento de Auditoria Forense:**
  - Emissão compulsória do evento `PRODUCAO_AMBULATORIAL_CONSOLIDADA` (Módulo: `ambulatory`, Ator: `SISTEMA` / `WORKER_ARQ`), registrando `sigtap`, `cnes`, `atendimento_id` e tenant municipal (`organizacao_id`) sob RLS PostgreSQL.

---

## 4. Checklist de Inspeção de Código

- [x] **Modelo de Produção Ambulatorial:** Entidade rica `ProducaoAmbulatorial` com multi-tenant PostgreSQL RLS (`src/modules/ambulatory/domain/models/producao_ambulatorial.py`) e migração `migrations/versions/0012_producao_ambulatorial_bpa.py`.
- [x] **Serviço de Consolidação e BPA-I:** `ProducaoAmbulatorialService` com suporte a SIGTAP `03.01.01.025-0` e verificação estrita de idempotência (`src/modules/ambulatory/application/services/producao_service.py`).
- [x] **Formatador Posicional SIA-SUS:** `BpaPositionalFormatter` com header (130 chars), detalhes (152 chars) e checksum no intervalo `[1111..2221]` (`src/modules/ambulatory/domain/bpa_formatter.py`).
- [x] **DTOs de Aplicação:** `ConsolidarTeleconsultaCommand`, `BpaProducaoDTO`, `BpaArquivoExportadoDTO` e `ListaProducaoAmbulatorialDTO` em `src/modules/ambulatory/application/dtos.py`.
- [x] **Composition Root de Ambulatory:** `src/modules/ambulatory/composition.py` exportando `get_producao_ambulatorial_service` e `ProducaoServiceDep`.
- [x] **Camada de Apresentação HTTP Fina:** Schemas em `presentation/schemas.py`, autenticação em `presentation/dependencies.py` e rotas em `presentation/routers/producao_router.py`.
- [x] **Testes Automatizados:** Testes unitários para o domínio, serviço e router em `tests/unit/test_ambulatory_domain.py`, `test_ambulatory_production_service.py` e `test_ambulatory_router.py`.

