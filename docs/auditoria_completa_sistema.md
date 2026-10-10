# Relatório Oficial de Auditoria do Sistema — MediSync Express

> **Status:** Concluído | **Data da Auditoria:** 2026-10-08 | **Versão do Sistema:** 0.1.0  
> **Escopo:** Auditoria Completa Módulo a Módulo (Business Vision, Especificação de Requisitos, Qualidade do Código e Acoplamento Inter-Modular)  
> **Metodologia:** Inspeção estática e dinâmica, AST de arquitetura, verificação formal de contratos e análise delegada via subagentes especializados.

---

## 1. Sumário Executivo

O **MediSync Express** é uma plataforma de código aberto para **Pronto-Atendimento Virtual (PA Digital 24/7)**, concebida para atender demandas espontâneas de saúde com suporte nativo a dois perfis operacionais: **Saúde Pública (SUS)** e **Saúde Suplementar / Particular**.

Esta auditoria independente avaliou a totalidade do código-fonte, suítes de testes, contratos de domínio e infraestrutura, confrontando o estado real do repositório contra as quatro bases de verdade do projeto:
1. **Business Vision (`docs/explanation/business-vision.md`)**: Personas (Juliana Silva, Dr. Eduardo Rocha, Patrícia Mendes, Carlos Drumond), metas SMART operacionais, esteira de valor assistencial integral e dualidade de modelos operacionais.
2. **Especificação de Requisitos e Invariantes (`docs/explanation/product-specification.md`)**: Requisitos funcionais (RF-01 a RF-10), regras contratuais (RN01 a RN07) e restrições ético-regulatórias (CFM nº 2.314/2022, CFM nº 1.821/2007, Portaria SVS/MS nº 344/98 e LGPD Art. 11).
3. **Qualidade do Código e Princípios Arquiteturais (`AGENTS.md` e ADRs 001 a 008)**: Hexagonal Pragmático sem Mapper Hell, modelos ricos com SQLAlchemy 2.0 (`Mapped[...]`), routers finos validados por AST, transação única no service (`await session.commit()`), tipagem estrita (`basedpyright strict`), isolamento de fronteiras (`tach check`) e RLS multi-tenant (`PostgreSQL RLS`).
4. **Acoplamento Inter-Modular e Context Map (`docs/explanation/domains/context-map.md`)**: Comunicação síncrona exclusiva via portas abstratas (`typing.Protocol` do PEP 544), DTOs imutáveis (`@dataclass(frozen=True)` ou Pydantic v2) e proibição absoluta de importação de modelos ou tabelas entre módulos.

### Veredito Geral
O sistema apresenta um **elevadíssimo nível de engenharia e maturidade técnica global (Média Geral Ponderada: 8.72 / 10.0)**. Destacam-se o motor de alocação atômica em Valkey com zero overbooking testado sob concorrência extrema de 50 médicos, a teleconsulta com LiveKit SFU desacoplado de mídia, o PEP SOAP append-only com assinatura ICP-Brasil PAdES e o isolamento multi-tenant PostgreSQL RLS com 100% de cobertura.

Entretanto, a auditoria identificou **duas violações arquiteturais de alto impacto**, um **desvio de fluxo de integração na admissão** e **três pendências regulatórias e funcionais** que demandam plano imediato de remediação.

---

## 2. Scorecard Consolidado de Maturidade do Sistema

A tabela abaixo sintetiza as notas atribuídas pelos subagentes em cada um dos quatro pilares de auditoria (escala de 0.0 a 10.0):

| Módulo / Camada | Business Vision (25%) | Requisitos & Invariantes (30%) | Qualidade Interna (25%) | Acoplamento Inter-Modular (20%) | Nota Final do Módulo | Status Global |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`triage` (Acolhimento e Triagem)** | 8.5 | 8.5 | 8.0 | 6.0 | **7.75 / 10** | **Aprovado com Ressalvas** |
| **`queue` (Fila, Alocação e Admissão)** | 8.5 | 8.0 | 8.8 | 6.8 | **8.08 / 10** | **Aprovado com Ressalvas** |
| **`consultation` (Teleconsulta e PEP)** | 9.5 | 9.8 | 9.5 | 9.2 | **9.54 / 10** | **Aprovado com Excelência** |
| **`billing` (Elegibilidade e Convênio)** | 8.5 | 7.5 | 9.0 | 9.0 | **8.43 / 10** | **Aprovado com Ressalvas** |
| **`auth` (Autenticação, RBAC e Tokens)** | 9.2 | 9.4 | 9.5 | 9.8 | **9.48 / 10** | **Aprovado com Excelência** |
| **`identity` (Identidade e Governança CFM)** | 8.5 | 8.5 | 9.0 | 8.0 | **8.52 / 10** | **Aprovado com Ressalvas** |
| **`core` / `worker` / Matriz Global** | 9.8 | 9.9 | 9.7 | 7.5 | **9.23 / 10** | **Aprovado com Ressalvas** |
| **MÉDIA PONDERADA GLOBAL DO SISTEMA** | **8.93** | **8.80** | **9.07** | **8.04** | **8.72 / 10** | **APROVADO COM RESSALVAS** |

---

## 3. Matriz de Acoplamento Inter-Modular e Conformidade com o Context Map

O [Context Map](file:///home/rafael/projetos/medisync/docs/explanation/domains/context-map.md) define a Regra de Ouro:
> *"Nunca importar modelos, tabelas ou repositórios de outro módulo. Comunicação síncrona ocorre exclusivamente via ports abstratas e DTOs imutáveis."*

### Análise Detalhada dos Desvios de Acoplamento:

1. **Violação Crítica: `queue.application` $\rightarrow$ `triage.domain`**:
   - **Localização:** [`src/modules/queue/application/services/admissao_service.py:19-24`](file:///home/rafael/projetos/medisync/src/modules/queue/application/services/admissao_service.py#L19-L24)
   - **Evidência:** `from src.modules.triage.domain.models.triagem import Triagem`
   - **Impacto:** O serviço de fila instancia `Triagem(...)` e chama `self._session.add(triagem)`. Para permitir isso, [`tach.toml:108`](file:///home/rafael/projetos/medisync/tach.toml#L108) concedeu uma permissão indevida (`"src.modules.triage.domain"`). Essa violação contraria diretamente o Context Map, que previa `triage` produzindo dados e `queue` consumindo apenas o inteiro de prioridade.
2. **Violação Média: `worker` $\rightarrow$ `billing.infrastructure`**:
   - **Localização:** [`src/worker/tasks/eligibility.py:14-16`](file:///home/rafael/projetos/medisync/src/worker/tasks/eligibility.py#L14-L16) e [`tach.toml:148`](file:///home/rafael/projetos/medisync/tach.toml#L148)
   - **Evidência:** O módulo `billing` não possui `composition.py`. O worker importa os adaptadores de infraestrutura (`PrivateInsuranceGatewayAdapter` e `SusEligibilityAdapter`) diretamente, forçando uma exceção no `tach.toml`.
3. **Violação Média: Consulta SQL Textual Cruzada em Consultation (`SqlDocumentDirectory`)**:
   - **Localização:** [`src/modules/consultation/infrastructure/document_directory_sql.py:20-130`](file:///home/rafael/projetos/medisync/src/modules/consultation/infrastructure/document_directory_sql.py#L20-L130)
   - **Evidência:** Há um fallback SQL com raw queries sobre `organizacoes`, `profissionais` e `pacientes` dentro de `consultation`. Embora a injeção em [`composition.py:211`](file:///home/rafael/projetos/medisync/src/modules/consultation/composition.py#L211) priorize o `IdentityDocumentDirectoryAdapter` (que consome `IdentityReaderPort`), manter esse fallback ativo fura o isolamento de dados do módulo `identity`.
4. **Omissão Documental no Context Map**:
   - **Evidência:** O arquivo [`docs/explanation/domains/context-map.md`](file:///home/rafael/projetos/medisync/docs/explanation/domains/context-map.md) omite completamente o módulo `identity` e sua porta [`IdentityReaderPort`](file:///home/rafael/projetos/medisync/src/modules/identity/application/ports/identity_reader_port.py), apesar de ser upstream vital para `consultation` e `worker`.

---

## 4. Avaliação Aprofundada por Módulo

### 4.1 Módulo TRIAGE (`src/modules/triage`) — Nota: 7.75/10
* **Pontos Fortes:** Classificador puro determinístico de 5 níveis com NFKD e remoção de diacríticos; modelo rico `Triagem` com `Mapped[...]`, `CheckConstraint` e relação 1:1; hash SHA-256 do TCLE em UTC.
* **Gaps:** Orfandade de `EmergencyNotifierPort` e `TriageService` no fluxo real de admissão (SAMU 192 nunca notificado em produção); inexistência do fluxo de piora na fila (RF-06); vazamento de `Triagem` em `ResultadoTriagemDTO`; descarte de `escala_dor` no banco.

### 4.2 Módulo QUEUE (`src/modules/queue`) — Nota: 8.08/10
* **Pontos Fortes:** Score determinístico de 64 bits (`prioridade * 10^12 + epoch`); double-lock atômico em Lua com latência < 10ms e zero overbooking (50 médicos concorrentes); ring timeout de 45s para no-show; sweeper periódico de auto-cura.
* **Gaps:** Acoplamento ilegal com persistência direta de `Triagem`; bypass de cota diária (`total_admissoes_hoje=0` hardcoded na admissão); falta de endpoints REST para "Chamar Próximo" (RF-03) e cancelamento; ausência de alertas de estouro de SLA (95%).

### 4.3 Módulo CONSULTATION (`src/modules/consultation`) — Nota: 9.54/10
* **Pontos Fortes:** Soberania absoluta do ato médico sem corte temporal (RN06); LiveKit SFU desacoplado de mídia (ADR-005); assinatura digital ICP-Brasil PAdES com PyHanko (ADR-006); PDF/A-1b com QR Code; salvaguardas da Portaria SVS/MS 344/98 e RDC ANVISA 20/2011; "lê sem possuir" via `AtendimentoReaderPort`.
* **Gaps:** `MemorySignedCache` instanciado no composition root em vez do distribuído `ValkeySignedCache`; supressão silenciosa com `contextlib.suppress(Exception)` ao concluir atendimento; falta de autenticação de token no WebSocket `/ws/doctor/{medico_id}`.

### 4.4 Módulo BILLING (`src/modules/billing`) — Nota: 8.43/10
* **Pontos Fortes:** Dualidade operacional perfeita (SUS no-op instantâneo `SUS-ISENTO` vs Privado com timeout de 15s); fluxo financeiro não obstrutivo (RN-NEG-01); worker ARQ em background; isolamento total sem imports de outros domínios.
* **Gaps:** Endpoint de admissão não enfileira `validar_elegibilidade_task` no pool ARQ (paciente congela em triagem); fechamento contábil pós-consulta (RF-08) não implementado; falta de composition root.

### 4.5 Módulo AUTH (`src/modules/auth`) — Nota: 9.48/10
* **Pontos Fortes:** Criptografia OWASP Argon2id com tempo constante e dummy_verify anti-timing attack; JWT curto (15min) + Refresh de uso único (7 dias) com revogação Valkey; rate limiting em janela deslizante (ZSET); RBAC multi-tier; routers finos AST-validated.
* **Gaps:** `get_current_user` não checa revogação de access tokens no Valkey em tempo real; falta de script Lua unificado no rate limiter.

### 4.6 Módulo IDENTITY (`src/modules/identity`) — Nota: 8.52/10
* **Pontos Fortes:** Cadastro progressivo Fases 1 e 2; validadores matemáticos de CPF e CNS mod-11; gestão de dependentes pediátricos sem CPF; PostgreSQL RLS estrito em `pacientes`, `profissionais` e `dependentes`; `IdentityReaderPort`.
* **Gaps:** Ausência do campo mandatório `nome_social` exigido por RN-REG-02 / CFM 1.821/2007; falta de validador de CRM/UF e campo de especialidade médica; fallback de SQL raw em `document_directory_sql.py`.

### 4.7 Camada Transversal & Matriz Global (`src/core` & `src/worker`) — Nota: 9.23/10
* **Pontos Fortes:** PostgreSQL RLS com 100% de cobertura em 9 tabelas de domínio; auditoria append-only imutável em UTC com triggers e DCL no PostgreSQL; worker assíncrono ARQ sobre Valkey 8.0; routers finos 100% em conformidade com AST; RFC 7807 problem details.
* **Gaps:** Bypasses no `tach.toml` para `queue.application -> triage.domain` e `worker -> billing.infrastructure`.

---

## 5. Mapeamento Consolidado de Não-Conformidades

### Críticas (Ação Imediata)
1. **NC-ARQ-01:** Queue importa e persiste o Aggregate `Triagem` em `admissao_service.py:19-24`.
2. **NC-MED-01:** Orfandade de `EmergencyNotifierPort` e `TriageService` no fluxo real de admissão (SAMU 192 nunca notificado em produção).

### Altas (Prioridade no Próximo Sprint)
3. **NC-BIL-01:** Admissão na fila não enfileira `validar_elegibilidade_task` no pool ARQ (paciente congela em triagem).
4. **NC-REG-01:** Ausência do campo mandatório `nome_social` em `Paciente` e schemas (CFM 1.821/2007 e LGPD).
5. **NC-QUE-01:** Bypass da Cota Diária Máxima (RN05) com `total_admissoes_hoje=0` hardcoded na admissão.

### Médias
6. **NC-QUE-02:** Falta de routers REST para "Chamar Próximo" (RF-03), consulta de posição e cancelamento pelo paciente.
7. **NC-MED-02:** Inexistência do caso de uso de Salvaguarda de Piora Clínica na Fila (RF-06).
8. **NC-BIL-02:** Inexistência do fechamento contábil e liquidação pós-consulta (RF-08).
9. **NC-CON-01:** Instanciação de `MemorySignedCache` no composition root de Consultation em vez de `ValkeySignedCache`.
10. **NC-CON-02:** Supressão silenciosa com `contextlib.suppress(Exception)` ao concluir atendimento em `pep_service.py`.
11. **NC-AUT-01:** Falta de validação ativa de revogação de access token no gateway de autenticação.
12. **NC-BIL-03:** Ausência de `composition.py` em Billing gerando bypass no `tach.toml`.

---

## 6. Avaliação do Portão Oficial de Qualidade

* `uv run tach check`: **0 erros** (com bypasses existentes).
* `uv run basedpyright`: **0 erros, 0 warnings, 0 notes** (modo estrito).
* `uv run ruff check .`: **0 erros** (todos os checks passando).
* `uv run python scripts/docs_check.py`: **0 erros** (documentação íntegra).
* `uv run pytest tests/architecture`: **5/5 testes passando** (routers finos).
* `uv run pytest tests/unit`: **418/418 testes passando em 8.58s**.

---

## 7. Plano de Remediação Técnico Recomendado

### Sprint 1: Bloqueios Críticos
1. **Saneamento do Acoplamento Queue $\rightarrow$ Triage:** Definir `TriageClassifierPort` na fila, eliminar a importação direta de `Triagem` de `admissao_service.py` e revogar a permissão no `tach.toml`.
2. **Conexão com Worker ARQ de Elegibilidade:** Injetar o cliente ARQ no serviço de admissão e despachar a tarefa assíncrona após o commit do atendimento.
3. **Ativação da Salvaguarda SAMU 192:** Implementar adaptador concreto para `EmergencyNotifierPort` e conectá-lo na admissão para emergências Nível 1.

### Sprint 2: Requisitos e Conformidade Regulatória
4. **Campo `nome_social`:** Adicionar migration com `nome_social` na tabela `pacientes`, atualizando o modelo e os schemas da Fase 2.
5. **Cota Diária RN05:** Corrigir a leitura da cota diária no Valkey e o incremento pós-admissão.
6. **Routers REST de Fila:** Expor `POST /fila/chamar-proximo`, `GET /fila/posicao/{id}` e `POST /fila/cancelar/{id}`.
7. **Botão de Piora na Fila (RF-06):** Criar serviço e rota para reavaliação de sintomas em fila com recálculo de score ou escape SAMU.

### Sprint 3: Resiliência e Infraestrutura
8. **Composition Root em Billing:** Criar `billing/composition.py` e remover o bypass no `tach.toml`.
9. **ValkeySignedCache no Consultation:** Substituir o cache de memória local pelo adaptador distribuído do Valkey no composition root.
10. **Liquidação Contábil (RF-08):** Criar serviço de faturamento pós-consulta integrado ao encerramento do PEP.
11. **Validação Ativa de Tokens:** Implementar verificação de revogação de access token no gateway.

---

## 8. Mapeamento no Backlog do GitHub (Issues)

| Issue | Tipo | Módulo | Descrição / Escopo |
|---|---|---|---|
| [#52](https://github.com/Rafaelp122/medisync/issues/52) | `bug` / `critical` | `queue`, `triage`, `worker` | **NC-ARQ-01, NC-BIL-01, NC-MED-01:** Sanear acoplamento `queue -> triage`, conectar worker ARQ e ativar salvaguarda SAMU 192. |
| [#53](https://github.com/Rafaelp122/medisync/issues/53) | `feat` | `queue`, `identidade` | **NC-QUE-01, NC-QUE-02, NC-MED-02, NC-REG-01:** Routers REST da fila, cálculo de cota diária no Valkey, botão de piora e `nome_social` (CFM). |
| [#54](https://github.com/Rafaelp122/medisync/issues/54) | `feat` | `telemetry`, `core` | **RF-10, RF-09:** Módulo desacoplado de telemetria operacional (Read Model/CQRS) e parametrização do plantão. |
| [#39](https://github.com/Rafaelp122/medisync/issues/39) | `type:security` | `core`, `auditoria` | Hardening de integridade criptográfica da trilha de auditoria. |
| [#40](https://github.com/Rafaelp122/medisync/issues/40) | `type:security` | `identidade` | Hardening de permissões de papéis e access control. |
| [#41](https://github.com/Rafaelp122/medisync/issues/41) | `type:security` | `identidade` | Hardening do fluxo de autenticação e proteção contra brute-force. |
| [#42](https://github.com/Rafaelp122/medisync/issues/42) | `type:security` | `identidade` | Hardening e blindagem de segurança para cadastro de pacientes. |
| [#38](https://github.com/Rafaelp122/medisync/issues/38) | `type:test` / `bug` | `core`, `testes` | Segregar suítes fail-fast (`test-fast` unitário) e isolar banco de integração por `worker_id` no xdist. |

