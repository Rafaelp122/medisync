# Relatório Oficial de Auditoria do Sistema — MediSync Express

> **Status:** Concluído | **Data da Auditoria:** 2026-10-17 | **Versão do Sistema:** 1.1.0  
> **Escopo:** Auditoria Exaustiva de Conformidade das 13 User Stories, Requisitos de Produto (RF-01 a RF-10), Invariantes de Negócio e Qualidade Arquitetural sob o Domínio de Missão Crítica para a UPA Digital Nacional / PA Virtual 24/7.  
> **Metodologia:** Inspeção estática e dinâmica profunda de código, rastreabilidade bidirecional, análise de regras de domínio e delegação concorrente a 4 subagentes especializados.

---

## 1. Sumário Executivo

O **MediSync Express** é uma plataforma de infraestrutura de missão crítica para **Pronto-Atendimento Virtual (UPA Digital Nacional / PA Virtual 24/7)**, desenhada para absorver volumes massivos de consultas espontâneas de baixa e média complexidade em implantações dedicadas de grande escala (SUS Nacional/Estadual ou Grandes Operadoras de Saúde), assegurando segregação multi-unidade/regional sem compartilhamento promíscuo de banco de dados.

Esta auditoria independente consolidou as análises dos 4 streams de trabalho especializados, avaliando o código-fonte em `src/modules/` e testes em `tests/` contra as bases oficiais de especificação:
1. **Especificação de Requisitos e Invariantes (`docs/explanation/product-specification.md`)**: Requisitos funcionais (RF-01 a RF-10), invariantes contratuais (RN01 a RN07), requisitos de transição (RT-01 a RT-03) e requisitos não-funcionais (RNF-01 a RNF-10).
2. **Catálogo de User Stories (`docs/user-stories/README.md`)**: Jornadas de valor das personas (US-01 a US-13) em formato BDD puro e contratos de API.
3. **Visão de Negócio e Metas Clínicas SMART (`docs/explanation/business-vision.md`)**: Resolutividade assistencial $\ge 80\%$, cumprimento de SLA $\ge 95\%$, tempo porta-médico $\le 15$ min e taxa de abandono $\le 3\%$.
4. **Marco Regulatório e Ético:** Resoluções CFM nº 2.314/2022 (telemedicina) e nº 1.821/2007 (prontuário estruturado), LGPD Art. 11 (TCLE imutável), Portaria SVS/MS nº 344/98 e RDC ANVISA nº 20/2011 (salvaguardas farmacêuticas).
5. **Diretrizes Arquiteturais (`AGENTS.md` e ADRs 001 a 008):** Hexagonal Pragmático sem Mapper Hell, modelos ricos com SQLAlchemy 2.0 (`Mapped[...]`), routers finos sem chamadas ao ORM, tipagem estrita `basedpyright` e isolamento modular `tach check`.

---

## 2. Scorecard Consolidado de Maturidade do Sistema

| Módulo / Subsistema | Visão de Negócio (25%) | Requisitos & Invariantes (30%) | Qualidade Interna (25%) | Acoplamento & Arquitetura (20%) | Nota Final | Status Global |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`triage` (Acolhimento e Triagem ACR)** | 9.5 | 9.5 | 9.5 | 9.2 | **9.43 / 10** | **Aprovado com Excelência** |
| **`identity` (Identidade e Governança CFM)** | 9.0 | 8.8 | 9.2 | 8.8 | **8.95 / 10** | **Aprovado com Ressalvas** |
| **`queue` (Fila, Alocação e Admissão)** | 9.2 | 8.8 | 9.5 | 9.0 | **9.11 / 10** | **Aprovado com Ressalvas** |
| **`billing` (Elegibilidade e Faturamento)** | 6.0 | 5.5 | 8.0 | 5.5 | **6.18 / 10** | **Reprovado com Pendência Crítica** |
| **`consultation` (Teleconsulta, PEP e ICP)** | 9.5 | 9.8 | 9.2 | 8.8 | **9.38 / 10** | **Aprovado com Excelência** |
| **`telemetry` (Telemetria e Plantão)** | 9.4 | 9.2 | 9.8 | 9.8 | **9.51 / 10** | **Aprovado com Excelência** |
| **`auth` / `core` / `worker` (Infraestrutura)** | 9.8 | 9.8 | 9.7 | 9.5 | **9.71 / 10** | **Aprovado com Excelência** |
| **MÉDIA PONDERADA GLOBAL DO SISTEMA** | **8.91** | **8.77** | **9.27** | **8.66** | **8.89 / 10** | **APROVADO COM RESSALVAS** |

---

## 3. Matriz de Conformidade das 13 User Stories (Living Specification)

| ID | User Story | Status | Evidências no Código | Evidências em Testes | Diagnóstico da Auditoria |
| :---: | :--- | :---: | :--- | :--- | :--- |
| **US-01** | Acolhimento, Triagem Clínica ACR e TCLE Digital | 🟡 Parcial | [`classification.py`](file:///home/rafael/projetos/medisync/src/modules/triage/domain/classification.py)<br>[`admissao_router.py`](file:///home/rafael/projetos/medisync/src/modules/queue/presentation/routers/admissao_router.py)<br>[`fila_service.py`](file:///home/rafael/projetos/medisync/src/modules/queue/application/services/fila_service.py) | `test_triage_model.py`<br>`test_admissao_service.py`<br>`test_admissao_integrada_flow.py` | Estratificação ACR em 5 níveis e hash SHA-256 no banco conformes. *Divergência:* schema `AdmissaoResponse` omite o campo `tcle_hash`. |
| **US-02** | Autenticação Passwordless OTP no Celular | 🟡 Parcial | [`patient_auth_router.py`](file:///home/rafael/projetos/medisync/src/modules/auth/presentation/routers/patient_auth_router.py)<br>[`patient_auth_service.py`](file:///home/rafael/projetos/medisync/src/modules/auth/application/services/patient_auth_service.py) | `test_patient_auth_service.py`<br>`test_patient_auth_endpoints.py` | OTP CSPRNG, hash no Valkey (TTL 300s) e rate limit (3/15min) conformes. *Divergência:* 3 falhas retornam HTTP 401 em vez de 429 (`OtpTentativasExcedidasError`); response omite `role`. |
| **US-03** | Validação de Cobertura e Onboarding Fase 2 | 🟡 Parcial | [`eligibility.py`](file:///home/rafael/projetos/medisync/src/worker/tasks/eligibility.py)<br>[`onboarding_service.py`](file:///home/rafael/projetos/medisync/src/modules/identity/application/services/onboarding_service.py)<br>[`paciente.py`](file:///home/rafael/projetos/medisync/src/modules/identity/domain/models/paciente.py) | `test_eligibility_task.py`<br>`test_eligibility_flow.py`<br>`test_onboarding_schemas.py` | Worker ARQ valida cobertura e persiste dados CFM 1.821. Token polimórfico (HMAC e JWT OTP) aceito em validar_intake_fase2 (Issue #76). Schema aceita apenas M/F (Issue #86). |
| **US-04** | Controle de Admissão por Capacidade e Backpressure | 🟢 Conforme | [`controle_admissao_service.py`](file:///home/rafael/projetos/medisync/src/modules/queue/application/services/controle_admissao_service.py)<br>[`sweeper.py`](file:///home/rafael/projetos/medisync/src/worker/tasks/sweeper.py) | `test_controle_admissao.py`<br>`test_queue_cota_diaria.py`<br>`test_queue_admission_backpressure.py` | Fórmula $\alpha \in [1{,}20; 1{,}30]$, cota diária no Valkey, suspensão com HTTP 503 e emissão de `QUEUE_OVERFLOW_TRANSIT` sem afetar pacientes já admitidos. |
| **US-05** | Tratamento de Falhas e Regularização na Fila | 🔴 Não Conforme | [`atendimento.py`](file:///home/rafael/projetos/medisync/src/modules/queue/domain/models/atendimento.py)<br>[`fila_service.py`](file:///home/rafael/projetos/medisync/src/modules/queue/application/services/fila_service.py) | `test_eligibility_flow.py`<br>`test_billing_eligibility.py` | Isolamento em `fila:*:aptos` preserva paciente. *Gaps Críticos:* `promover_para_apto()` grava `data_entrada_fila = now` tardio, violando antiguidade (RN01/RN03); ausência de endpoint REST de regularização. |
| **US-06** | Deterioração Clínica na Fila e Rota SAMU 192 | 🟢 Conforme | [`fila_router.py`](file:///home/rafael/projetos/medisync/src/modules/queue/presentation/routers/fila_router.py)<br>[`fila_service.py`](file:///home/rafael/projetos/medisync/src/modules/queue/application/services/fila_service.py) | `test_fila_router.py`<br>`test_admissao_integrada_flow.py` | Botão `POST /fila/piora` reavalia risco. Nível 1 Vermelho cancela atendimento e aciona escape SAMU 192. Agravamento sem emergência reposiciona score preservando entrada original. |
| **US-07** | Alocação e Convocação Médica com Lock Atômico | 🟢 Conforme | [`alocar_chamada.lua`](file:///home/rafael/projetos/medisync/src/modules/queue/infrastructure/lua/alocar_chamada.lua)<br>[`alocacao_router.py`](file:///home/rafael/projetos/medisync/src/modules/queue/presentation/routers/alocacao_router.py) | `test_alocar_chamada_concurrency.py`<br>`test_alocacao_router.py` | Script Lua com locks duplos de 45s. Latência de benchmark comprovada de 0,42ms. Teste sob 50 médicos concorrentes garante 1 vencedor e 49 perdedores (HTTP 409). |
| **US-08** | Ingresso na Teleconsulta e Resolução de No-Show | 🟢 Conforme | [`livekit_router.py`](file:///home/rafael/projetos/medisync/src/modules/consultation/presentation/routers/livekit_router.py)<br>[`ring_timeout.py`](file:///home/rafael/projetos/medisync/src/worker/tasks/ring_timeout.py) | `test_ring_timeout_flow.py`<br>`test_ring_timeout_task.py`<br>`test_livekit_lifecycle.py` | Ring timeout aos 45s, promoção atômica para consulta ativa (7200s) e transição para `EM_ATENDIMENTO` na emissão de token LiveKit pelo paciente conformes (Issue #76). |
| **US-09** | Teleconsulta, Prontuário PEP SOAP e Soberania | 🟢 Conforme | [`evolucao_clinica.py`](file:///home/rafael/projetos/medisync/src/modules/consultation/domain/models/evolucao_clinica.py)<br>[`pep_service.py`](file:///home/rafael/projetos/medisync/src/modules/consultation/application/services/pep_service.py) | `test_consultation_endpoints.py`<br>`test_pep_soap_service.py`<br>`test_pep_transaction.py` | Evolução SOAP estruturada com CID-10, telemetria passiva de TMA sem desconexão forçada (CFM 2.314/2022) e imutabilidade do PEP em 3 camadas (ABAC, service e ORM). |
| **US-10** | Prescrição Digital com Assinatura ICP-Brasil | 🟢 Conforme | [`pdf_generator.py`](file:///home/rafael/projetos/medisync/src/modules/consultation/infrastructure/pdf_generator.py)<br>[`pyhanko_signer.py`](file:///home/rafael/projetos/medisync/src/modules/consultation/infrastructure/pyhanko_signer.py) | `test_document_signing_endpoint.py`<br>`test_pdf_generator.py`<br>`test_pyhanko_signer.py` | PDF/A-1b, via dupla automática para antimicrobianos e Lista C1 com QR Code ITI, assinatura PAdES e blacklist das Listas A e B da Portaria 344/98 (HTTP 422). |
| **US-11** | Fechamento Contábil e Liquidação Pós-Consulta | 🔴 Não Conforme | [`pep_service.py`](file:///home/rafael/projetos/medisync/src/modules/consultation/application/services/pep_service.py) | *Nenhum teste existente* | **NC-BIL-02 (GAP CRÍTICO - Issue #78):** Inexistência de `LiquidacaoService`, sem entidade `FaturaAtendimento`, sem guias TISS, sem lotes ambulatoriais BPA/APAC e sem apresentação de faturamento. |
| **US-12** | Parametrização Dinâmica de Políticas de Plantão | 🟢 Conforme | [`models.py`](file:///home/rafael/projetos/medisync/src/modules/telemetry/domain/models.py)<br>[`telemetry_router.py`](file:///home/rafael/projetos/medisync/src/modules/telemetry/presentation/routers/telemetry_router.py) | `test_telemetry_model.py`<br>`test_telemetry_router.py`<br>`0006_telemetry_config_plantao.py` | Entidade rica `ConfiguracaoPlantao` validando $\alpha \in [1{,}20; 1{,}30]$, médicos $\ge 1$, limites de TMA/SLA e rotas `GET/PUT /api/v1/telemetria/config-plantao`. |
| **US-13** | Telemetria Operacional e Painel em Tempo Real | 🟡 Parcial | [`telemetry_reader_sql.py`](file:///home/rafael/projetos/medisync/src/modules/telemetry/infrastructure/telemetry_reader_sql.py)<br>[`telemetry_service.py`](file:///home/rafael/projetos/medisync/src/modules/telemetry/application/services/telemetry_service.py) | `test_telemetry_service.py`<br>`test_telemetry_router.py`<br>`test_telemetry_infra.py` | Read Model CQRS desacoplado com TTL de cache de 5s (Issue #76). *Gap remanescente:* médico recebe 403 no painel (Issue #87). |

---

## 4. Matriz de Requisitos Funcionais e Não-Funcionais

### 4.1 Requisitos Funcionais (RF-01 a RF-10)

| Requisito | Título e Descrição | Status | Evidências no Código | Diagnóstico Técnico |
| :--- | :--- | :---: | :--- | :--- |
| **RF-01** | Acolhimento, Triagem Estruturada e TCLE Digital | 🟡 Parcial | [`classification.py`](file:///home/rafael/projetos/medisync/src/modules/triage/domain/classification.py)<br>[`fila_service.py`](file:///home/rafael/projetos/medisync/src/modules/queue/application/services/fila_service.py) | Acolhimento em $< 45\text{ s}$ e hash SHA-256 conformes; payload `AdmissaoResponse` omite `tcle_hash`. |
| **RF-01 (#44)** | Reconexão e Autenticação Passwordless OTP | 🟡 Parcial | [`patient_auth_service.py`](file:///home/rafael/projetos/medisync/src/modules/auth/application/services/patient_auth_service.py) | OTP CSPRNG e rate limit conformes; bloqueio retorna 401 em vez de 429; response sem `role`. |
| **RF-02** | Validação Concorrente de Elegibilidade e Enriquecimento CFM | 🟡 Parcial | [`eligibility.py`](file:///home/rafael/projetos/medisync/src/worker/tasks/eligibility.py)<br>[`paciente.py`](file:///home/rafael/projetos/medisync/src/modules/identity/domain/models/paciente.py) | Validação SUS/Privada em background e dados CFM conformes; dependência aceita token polimórfico HMAC e JWT OTP (Issue #76). |
| **RF-03** | Convocação, Ingresso na Teleconsulta e Resolução de No-Show | 🟢 Conforme | [`alocacao_router.py`](file:///home/rafael/projetos/medisync/src/modules/queue/presentation/routers/alocacao_router.py)<br>[`livekit_router.py`](file:///home/rafael/projetos/medisync/src/modules/consultation/presentation/routers/livekit_router.py) | Alocação Lua atômica, ring timeout 45s e transição imediata para `EM_ATENDIMENTO` ao emitir token LiveKit para paciente conformes (Issue #76). |
| **RF-04** | Fila Dinâmica e Controle de Admissão (Backpressure) | 🟢 Conforme | [`controle_admissao_service.py`](file:///home/rafael/projetos/medisync/src/modules/queue/application/services/controle_admissao_service.py) | Backpressure estocástico $\alpha$, cota diária e evento de saturação operacional conformes. |
| **RF-05** | Tratamento de Exceções e Falhas de Elegibilidade | 🔴 Não Conforme | [`atendimento.py`](file:///home/rafael/projetos/medisync/src/modules/queue/domain/models/atendimento.py) | Desvio sem expulsão conforme; regularização perde timestamp original e inexiste rota REST de regularização. |
| **RF-06** | Deterioração Clínica na Fila (Escape SAMU 192) | 🟢 Conforme | [`fila_router.py`](file:///home/rafael/projetos/medisync/src/modules/queue/presentation/routers/fila_router.py) | Reclassificação imediata no ZSET e bloqueio com SAMU 192 em Nível 1 Vermelho conformes. |
| **RF-07** | Teleconsulta, PEP SOAP e Prescrição Digital ICP-Brasil | 🟢 Conforme | [`evolucao_clinica.py`](file:///home/rafael/projetos/medisync/src/modules/consultation/domain/models/evolucao_clinica.py)<br>[`pyhanko_signer.py`](file:///home/rafael/projetos/medisync/src/modules/consultation/infrastructure/pyhanko_signer.py) | PEP SOAP imutável, PDF/A-1b, via dupla antimicrobianos e bloqueio da Portaria 344/98 conformes. |
| **RF-08** | Conclusão Clínica e Fechamento Contábil pós-consulta | 🔴 Não Conforme | [`pep_service.py`](file:///home/rafael/projetos/medisync/src/modules/consultation/application/services/pep_service.py) | **NC-BIL-02 (GAP CRÍTICO):** Inexistência de liquidação financeira e geração de BPA/APAC ou TISS. |
| **RF-09** | Parametrização Dinâmica de Políticas Operacionais | 🟢 Conforme | [`models.py`](file:///home/rafael/projetos/medisync/src/modules/telemetry/domain/models.py) | Entidade rica `ConfiguracaoPlantao` com RLS, validação de $\alpha \in [1{,}20; 1{,}30]$ e rotas REST. |
| **RF-10** | Telemetria Operacional, SLA e Auditoria de Capacidade | 🟡 Parcial | [`telemetry_reader_sql.py`](file:///home/rafael/projetos/medisync/src/modules/telemetry/infrastructure/telemetry_reader_sql.py) | Read Model CQRS com TME, TMA e SLA $\ge 95\%$ conforme; TTL de cache excede teto do RNF-10. |

---

## 5. Mapeamento Consolidado de Não-Conformidades (Gaps)

### 5.1 Gaps Críticos e de Alta Prioridade (P0)

1. **NC-BIL-02 [P0 / RF-08 / Issue #78]: Inexistência de Fechamento Contábil e Liquidação no Módulo Billing.**
   - *Evidência:* [`pep_service.py`](file:///home/rafael/projetos/medisync/src/modules/consultation/application/services/pep_service.py) finaliza a consulta sem notificar o financeiro. O módulo `src/modules/billing/` possui apenas `eligibility_service.py`.
   - *Impacto:* Ausência de persistência contábil, impossibilitando exportação de lotes SUS (BPA/APAC) e liquidação particular.
2. **NC-QUE-03 [P0 / RF-03 / Issue #76]: Ingresso na Teleconsulta Não Dispara Transição para `EM_ATENDIMENTO`.** *(Resolvido na Issue #76)*
   - *Evidência:* [`livekit_router.py`](file:///home/rafael/projetos/medisync/src/modules/consultation/presentation/routers/livekit_router.py) gera o token JWT do LiveKit sem invocar `Atendimento.atender_chamada()`.
   - *Impacto:* O atendimento permanece em `CHAMANDO_PACIENTE`, fazendo com que aos 45 segundos o worker de ring timeout encerre a consulta por falso no-show (`PACIENTE_AUSENTE`) enquanto médico e paciente estão na sala.
3. **NC-QUE-04 [P0 / RF-05 / US-05]: Perda de Antiguidade na Fila e Ausência de Rota de Regularização.**
   - *Evidência:* [`atendimento.py:228`](file:///home/rafael/projetos/medisync/src/modules/queue/domain/models/atendimento.py) preenche `data_entrada_fila = now` tardio no momento da promoção para apto, penalizando o score ZSET $(P \times 10^{12} + \text{ts})$. Inexiste endpoint REST para regularizar pendência cadastral ou escolher contingência.
4. **NC-IDN-01 [P0 / RF-02 / US-03]: Rejeição de Pacientes Reconectados por OTP na Fase 2 de Onboarding.** *(Resolvido na Issue #76)*
   - *Evidência:* [`dependencies.py`](file:///home/rafael/projetos/medisync/src/modules/identity/presentation/dependencies.py) aceita apenas token HMAC de 2 partes, rejeitando JWT de 3 partes de pacientes reconectados por OTP com HTTP 401 Unauthorized.

### 5.2 Gaps Médios e Ajustes Contratuais (P1)

5. **NC-AUT-02 [P1 / RF-01 (#44) / US-02]: Código HTTP Incorreto no Bloqueio por Força Bruta de OTP.**
   - *Evidência:* Ao atingir 3 tentativas inválidas de OTP, o serviço lança erro que mapeia para HTTP 401 em vez do mandatório **HTTP 429 Too Many Requests** (`OtpTentativasExcedidasError`).
6. **NC-TEL-01 [P1 / RNF-10 / Meta SMART 5]: TTL do Cache de Telemetria Excede Teto Estipulado.** *(Resolvido na Issue #76)*
   - *Evidência:* [`telemetry_service.py`](file:///home/rafael/projetos/medisync/src/modules/telemetry/application/services/telemetry_service.py) define `_CACHE_TTL_SEGUNDOS = 15`, violando o teto de defasagem de 5 segundos exigido pela especificação.
7. **NC-TEL-02 [P1 / RF-10 / US-13]: Médico Bloqueado com HTTP 403 no Painel de Telemetria.**
   - *Evidência:* A dependência de autorização do painel exige permissão `tma:config`, indisponível para o perfil médico.
8. **NC-CON-02 [P1 / Resiliência]: Supressão Silenciosa de Erro ao Concluir Consulta no PEP.**
   - *Evidência:* [`pep_service.py:164`](file:///home/rafael/projetos/medisync/src/modules/consultation/application/services/pep_service.py) utiliza `with contextlib.suppress(Exception):` ao sincronizar a conclusão na fila.

---

## 6. Avaliação do Portão Oficial de Qualidade

* `uv run tach check`: **0 erros** (arquitetura modular blindada).
* `uv run basedpyright`: **0 erros, 0 warnings** (modo estrito).
* `uv run ruff check .`: **0 erros** (todos os linters conformes).
* `uv run pytest tests/architecture`: **3/3 suítes passando** (routers finos e composition root enxuto).
* `uv run pytest tests/unit tests/architecture -n auto`: **577/577 testes passando (100% verde)**.
* `uv run python scripts/docs_check.py`: **0 links quebrados**.

---

## 7. Backlog Priorizado de Remediação

### Sprint 1: Bloqueios Clínicos e Operacionais Imediatos (P0)
1. **Conectar Ingresso LiveKit ao `atender_chamada()` (NC-QUE-03 / Issue #76):** *(Concluído na Issue #76)*
   - Ao emitir o token LiveKit para o paciente (`POST /consultations/{id}/livekit/token`), transicionar o atendimento para `EM_ATENDIMENTO`, converter o lock no Valkey para consulta ativa (TTL 7200s) e cancelar o timer de ring timeout de 45s.
2. **Preservar Antiguidade na Regularização e Endpoint REST (NC-QUE-04 / US-05):**
   - Alterar `promover_para_apto()` para inicializar `data_entrada_fila` com `criado_em` (momento original da triagem), preservando a posição justa do paciente.
   - Criar rota `POST /api/v1/fila/atendimentos/{id}/regularizar`.
3. **Polimorfismo de Token na Fase 2 de Onboarding (NC-IDN-01 / US-03):** *(Concluído na Issue #76)*
   - Habilitar `validar_intake_fase2` para aceitar tanto token provisório HMAC quanto JWT de paciente autenticado via OTP.
4. **Saneamento da Conclusão do PEP (NC-CON-02):**
   - Remover `with contextlib.suppress(Exception):` em `pep_service.py` e tratar erros explicitamente.

### Sprint 2: Fechamento Contábil e Faturamento Pós-Consulta (P0/P1 - Issue #78)
5. **Implementar Módulo de Faturamento e Liquidação (`src/modules/billing/`):**
   - Criar modelo rico `FaturaAtendimento` com RLS multi-tenant e migration Alembic.
   - Implementar `LiquidacaoService` com suporte a faturamento ambulatorial SUS (BPA/APAC) e liquidação particular.
   - Definir porta `LiquidacaoPort` em `consultation` e acioná-la no método `finalizar_consulta` do `PEPService`.
   - Expor router REST `GET /api/v1/billing/atendimentos/{id}/fatura` e registrar em `src/main.py`.

### Sprint 3: Alinhamento de Contratos, Telemetria e Hardening (P1/P2)
6. **Ajuste de TTL de Telemetria e Permissões (NC-TEL-01 / NC-TEL-02):** *(Concluído na Issue #76)*
   - Reduzir `_CACHE_TTL_SEGUNDOS` de 15s para 5s em `telemetry_service.py`.
   - Permitir visualização do painel operacional para a role médica.
7. **Tratamento de Força Bruta OTP (NC-AUT-02):**
   - Retornar HTTP 429 Too Many Requests quando 3 tentativas de OTP falharem.
8. **Harmonização de Schemas de Apresentação:**
   - Adicionar `tcle_hash` em `AdmissaoResponse`.
   - Adicionar `role: str = "PACIENTE"` em `VerificarOtpResponse`.
   - Aceitar formatos textuais em `Fase2Request.sexo_biologico`.

---

## 8. Mapeamento no Backlog do GitHub (Issues)

| Issue | Tipo / Prioridade | Módulo | Descrição / Escopo |
| :--- | :--- | :--- | :--- |
| [#76](https://github.com/Rafaelp122/medisync/issues/76) | `bug` / `high` (3pt) | `queue`, `identity`, `telemetry` | **NC-QUE-03, NC-IDN-01, NC-TEL-01:** Conectar emissão de token LiveKit a `atender_chamada()`, onboarding OTP e TTL de telemetria. *(Concluída)* |
| [#77](https://github.com/Rafaelp122/medisync/issues/77) | `refactor` / `medium` (3pt) | `consultation`, `billing`, `worker` | **NC-CON-01, NC-CON-02, NC-BIL-03, NC-CON-03:** Hardening de cache distribuído, composition root de billing e blindagem de conclusão do PEP. |
| [#78](https://github.com/Rafaelp122/medisync/issues/78) | `type:feature` / `epic` (8pt) | `billing`, `consultation` | **NC-BIL-02 (RF-08):** Fechamento contábil, modelo de faturamento e liquidação pós-consulta SUS/Particular. |
| [#85](https://github.com/Rafaelp122/medisync/issues/85) | `bug` / `high` (3pt) | `queue`, `worker` | **NC-QUE-04 (US-05 / RF-05):** Preservar timestamp original de admissão na regularização de fila e criar endpoint de contingência. |
| [#86](https://github.com/Rafaelp122/medisync/issues/86) | `bug` / `medium` (2pt) | `auth`, `identity` | **NC-AUT-02 (US-02 / US-03):** Retornar HTTP 429 no bloqueio de tentativas OTP, role no response e flexibilizar sexo biológico. |
| [#87](https://github.com/Rafaelp122/medisync/issues/87) | `bug` / `medium` (2pt) | `telemetry`, `core` | **NC-TEL-02, NC-SEC-01 (US-13):** Conceder acesso de leitura ao painel para médicos e incluir configuracoes_plantao nos testes RLS. |
| [#88](https://github.com/Rafaelp122/medisync/issues/88) | `enhancement` / `low` (2pt) | `queue`, `presentation` | **Harmonização de Schemas:** Adicionar `tcle_hash` em AdmissaoResponse, campos de PioraClinicaResponse e ChamarProximoResponse. |
