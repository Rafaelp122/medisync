# Domain Docs Batch 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Documentar os 4 domínios do fluxo assistencial + 2 transversais em `docs/explanation/domains/`, padrão atomic-denso com Mermaid.

**Architecture:** 1 task por arquivo (triage → queue → consultation → billing → context-map → domain-events → verificação). Cada doc segue o template da spec (Contexto/Regras/StateDiagram/Relações/Peculiaridades/Onde/Verificação/Ver também), só links para código (zero bloco python >5 linhas), Mermaid espelhando métodos guardiões reais.

**Tech Stack:** Markdown + Mermaid (`stateDiagram-v2`, `flowchart`), `rg` para âncoras, `just docs-check`, `wc -l`.

**Correção vs spec:** não existe `src/core/event_bus.py` — events são dataclasses frozen + `Protocol` notifier ports ponto-a-ponto. `domain-events.md` cataloga as Ports, sem bus central.

---

## File Structure

Criar (densos 80–250 linhas):

- `docs/explanation/domains/triage-domain.md` (RN01, RN04, RN07)
- `docs/explanation/domains/queue-domain.md` (RN01, RN02, RN05 — maior, ~200 linhas)
- `docs/explanation/domains/consultation-domain.md` (RN06, RN07)
- `docs/explanation/domains/billing-domain.md` (RN03)
- `docs/explanation/domains/context-map.md` (transversal Ports)
- `docs/explanation/domains/domain-events.md` (transversal events)

Criar (stubs ~10 linhas, batch 2):

- `docs/explanation/domains/identity-domain.md`
- `docs/explanation/domains/auth-domain.md`

Modificar: `docs/explanation/domains/index.md` (linkar os 8 arquivos).

Âncoras verificadas (usar estes paths/símbolos, não inventar):

- triage: `src/modules/triage/domain/models/triagem.py:Triagem, disparar_alerta_samu, is_emergencia_critica`, `src/modules/triage/domain/classification.py:calcular_hash_tcle, classificar_risco_clinico`, `src/modules/triage/application/ports/emergency_notifier.py`
- queue: `src/modules/queue/domain/models/atendimento.py:StatusAtendimento, PrioridadeClinica, registrar_tcle, promover_para_apto, iniciar_chamada, atender_chamada, registrar_ausencia_paciente, concluir_atendimento, cancelar_pelo_paciente, calcular_score_fila`, `src/modules/queue/domain/scoring.py:calcular_score`, `src/modules/queue/infrastructure/lua/alocar_chamada.lua`, `src/modules/queue/application/services/alocacao_service.py`, `controle_admissao_service.py`, `fila_service.py`; prova viva `tests/unit/test_alocacao_service.py`, `test_atendimento_model.py`, `test_controle_admissao.py`, `test_fila_service.py`
- consultation: `src/modules/consultation/domain/models/evolucao_clinica.py:EvolucaoClinica, marcar_finalizado, validar_pode_excluir`, `documento_clinico.py:TipoDocumentoClinico, DocumentoClinico, adicionar_item`, `src/modules/consultation/domain/s3_keys.py`, `src/modules/consultation/infrastructure/livekit_adapter.py`; prova viva `tests/unit/test_consultation_models.py`, `test_evolucao_service.py`, `test_documento_service.py`, `test_livekit_token.py`
- billing: `src/modules/billing/domain/enums.py:StatusElegibilidade (APROVADO/REJEITADO/TIMEOUT/PENDENTE)`, `src/modules/billing/application/services/eligibility_service.py`, `src/modules/billing/infrastructure/adapters/sus_adapter.py`, `private_gateway_adapter.py`, `src/modules/billing/application/ports/eligibility_provider.py`; prova viva `tests/unit/test_billing_eligibility.py`
- events: `src/modules/queue/application/ports/paciente_ausente_notifier.py:PacienteAusenteEvent`, `queue_overflow_notifier.py:QueueOverflowEvent`, `src/modules/billing/application/ports/eligibility_notifier.py:ElegibilidadeFalhaEvent`, `src/core/audit/models.py:AuditEvent`
- RNs fonte única: `docs/explanation/product-specification.md` (RN01 l.42, RN02 l.47, RN03 l.54, RN04 l.60, RN05 l.64, RN06 l.73, RN07 l.76)

---

### Task 1: triage-domain.md

**Files:**
- Create: `docs/explanation/domains/triage-domain.md`

- [ ] **Step 1: Confirmar âncoras**

Run: `rg -n "def disparar_alerta_samu|def classificar_risco_clinico|def calcular_hash_tcle" src/modules/triage/ | head -5`
Expected: 3 matches nos paths da spec.

- [ ] **Step 2: Escrever `docs/explanation/domains/triage-domain.md` (80–250 linhas, template spec)**

Conteúdo obrigatório:
- Regras: RN01 (5 níveis `PrioridadeClinica` 1–5 → alimenta score fila via dado), RN04 (`disparar_alerta_samu` + `emergency_notifier` → SAMU 192), RN07 (`calcular_hash_tcle` + TCLE <45s) — 1–2 linhas cada + link `../product-specification.md#RN0X`.
- `stateDiagram-v2` da triagem espelhando `Triagem` (`is_emergencia_critica` → `disparar_alerta_samu`).
- Relações: consome nada; expõe classificação (dado) para queue; tabelas `triagens` (RLS) — link `../architecture/data-model.md`.
- Peculiaridade: acoplamento triage→queue via dado (score), não via chamada.
- Onde no código: models/classification/ports acima (só links) + prova viva (achar com `ls tests/unit | rg -i triag`).
- Verificação: `rg -n "classificar_risco_clinico" src/ ` + `pytest tests/unit -k triag -q --no-cov`.

- [ ] **Step 3: Checar tamanho e docs-check**

Run: `wc -l docs/explanation/domains/triage-domain.md && uv run python scripts/docs_check.py`
Expected: 80–250 linhas; docs-check EXIT 0 (fora `adrs/`/`superpowers/`).

- [ ] **Step 4: Commit**

```bash
git add docs/explanation/domains/triage-domain.md
git commit -m "docs: add triage domain doc"
```

---

### Task 2: queue-domain.md

**Files:**
- Create: `docs/explanation/domains/queue-domain.md`

- [ ] **Step 1: Confirmar âncoras**

Run: `rg -n "def calcular_score|def iniciar_chamada|def registrar_ausencia_paciente" src/modules/queue/domain/ | head -5; ls src/modules/queue/infrastructure/lua/`
Expected: matches + `alocar_chamada.lua`.

- [ ] **Step 2: Escrever `docs/explanation/domains/queue-domain.md` (~200 linhas, template spec)**

Conteúdo obrigatório:
- Regras: RN01 (`scoring.py:calcular_score` 64 bits + desempate FIFO UUIDv7), RN02 (`alocar_chamada.lua` double-lock 45s códigos `0`/`-1` + `iniciar_chamada`/`registrar_ausencia_paciente`), RN05 (`controle_admissao_service.py` α + transbordo via `queue_overflow_notifier`).
- `stateDiagram-v2` com os 7 `StatusAtendimento` (TRIADO_AGUARDANDO_ELEGIBILIDADE → APTO_PARA_CHAMADA → CHAMANDO_PACIENTE → EM_ATENDIMENTO → CONCLUIDO; ramos PACIENTE_AUSENTE, CANCELADO_PACIENTE; `TERMINAL_STATUSES`), cada transição citando o método guardião (`promover_para_apto`, `atender_chamada`, `concluir_atendimento`, ...).
- Relações: consome `eligibility_provider` (billing); expõe `allocation_port`; tabelas `atendimentos` (RLS).
- Peculiaridades: score determinístico; ato médico nunca cortado por tempo (ponte RN06).
- Onde: models/scoring/lua/services acima + provas `test_alocacao_service.py`, `test_atendimento_model.py`, `test_controle_admissao.py`, `test_fila_service.py`.
- Verificação: `pytest tests/unit/test_alocacao_service.py tests/unit/test_atendimento_model.py -q --no-cov`.

- [ ] **Step 3: Checar tamanho e docs-check**

Run: `wc -l docs/explanation/domains/queue-domain.md && uv run python scripts/docs_check.py`
Expected: 80–250 linhas; EXIT 0.

- [ ] **Step 4: Commit**

```bash
git add docs/explanation/domains/queue-domain.md
git commit -m "docs: add queue domain doc"
```

---

### Task 3: consultation-domain.md

**Files:**
- Create: `docs/explanation/domains/consultation-domain.md`

- [ ] **Step 1: Confirmar âncoras**

Run: `rg -n "def marcar_finalizado|def adicionar_item|def validar_pode_excluir" src/modules/consultation/domain/ | head -6`
Expected: matches em `evolucao_clinica.py` + `documento_clinico.py`.

- [ ] **Step 2: Escrever `docs/explanation/domains/consultation-domain.md` (80–250 linhas, template spec)**

Conteúdo obrigatório:
- Regras: RN06 (`marcar_finalizado`/`validar_pode_excluir` — sem desconexão forçada; backend só emite JWT via `livekit_adapter.py`), RN07 (append-only `EvolucaoClinica`/`DocumentoClinico`, UTC, PAdES; `s3_keys.py` para guarda).
- `stateDiagram-v2` evolução/documento (rascunho → finalizado; `adicionar_item` só antes de finalizar) citando guardiões.
- Relações: lê `atendimento_reader_port` (queue, sem importar models dele); emite via `storage_port`/`pdf_generator_port`/`icp_brasil_signer_port`; tabelas `evolucoes_clinicas`, `documentos_clinicos`, `documento_itens` (RLS).
- Peculiaridade: mídia nunca passa pelo Python (LiveKit SFU); `TipoDocumentoClinico` fecha o vocabulário.
- Onde: models/s3_keys/livekit acima + provas `test_consultation_models.py`, `test_evolucao_service.py`, `test_documento_service.py`, `test_livekit_token.py`.
- Verificação: `pytest tests/unit/test_consultation_models.py -q --no-cov`.

- [ ] **Step 3: Checar tamanho e docs-check**

Run: `wc -l docs/explanation/domains/consultation-domain.md && uv run python scripts/docs_check.py`
Expected: 80–250 linhas; EXIT 0.

- [ ] **Step 4: Commit**

```bash
git add docs/explanation/domains/consultation-domain.md
git commit -m "docs: add consultation domain doc"
```

---

### Task 4: billing-domain.md

**Files:**
- Create: `docs/explanation/domains/billing-domain.md`

- [ ] **Step 1: Confirmar âncoras**

Run: `rg -n "APROVADO|REJEITADO|TIMEOUT|PENDENTE" src/modules/billing/domain/enums.py; ls src/modules/billing/infrastructure/adapters/`
Expected: 4 status + `sus_adapter.py`, `private_gateway_adapter.py`.

- [ ] **Step 2: Escrever `docs/explanation/domains/billing-domain.md` (80–250 linhas, template spec)**

Conteúdo obrigatório:
- Regras: RN03 (elegibilidade concorrente em background; SUS `sus_adapter.py` no-op aprova de imediato; privado `private_gateway_adapter.py` com timeout; `eligibility_service.py` orquestra).
- `stateDiagram-v2` com os 4 `StatusElegibilidade` citando transições do service.
- Relações: expõe `eligibility_provider` para queue; notifica via `eligibility_notifier` (`ElegibilidadeFalhaEvent`); sem tabelas clínicas próprias pesadas (apontar `data-model.md`).
- Peculiaridade: pendência financeira nunca expulsa paciente da posição clínica.
- Onde: enums/service/adapters/ports acima + prova `test_billing_eligibility.py` (+ `test_eligibility_task.py` do worker se existir em unit).
- Verificação: `pytest tests/unit/test_billing_eligibility.py -q --no-cov`.

- [ ] **Step 3: Checar tamanho e docs-check**

Run: `wc -l docs/explanation/domains/billing-domain.md && uv run python scripts/docs_check.py`
Expected: 80–250 linhas; EXIT 0.

- [ ] **Step 4: Commit**

```bash
git add docs/explanation/domains/billing-domain.md
git commit -m "docs: add billing domain doc"
```

---

### Task 5: context-map.md + domain-events.md (transversais)

**Files:**
- Create: `docs/explanation/domains/context-map.md`, `docs/explanation/domains/domain-events.md`

- [ ] **Step 1: Confirmar ports e events**

Run: `ls src/modules/queue/application/ports/ src/modules/billing/application/ports/ src/modules/consultation/application/ports/ src/modules/triage/application/ports/; rg -n "class \w+Event" src/modules/ --glob "*notifier*.py" | grep -v __pycache__`
Expected: `allocation_port`, `eligibility_provider`, `atendimento_reader_port`, `emergency_notifier`, notifiers; events `PacienteAusenteEvent`, `QueueOverflowEvent`, `ElegibilidadeFalhaEvent`.

- [ ] **Step 2: Escrever `context-map.md` (80–200 linhas)**

`flowchart LR` triage→queue→consultation→billing com arestas rotuladas pela Port consumida + tabela upstream/downstream por módulo (consome/expõe caminho do port) + regra de ouro (nunca importar models de outro módulo — `tach check`). Links para `application/ports/*` reais.

- [ ] **Step 3: Escrever `domain-events.md` (80–200 linhas)**

Tabela evento→produtor→consumidores→port para `PacienteAusenteEvent`, `QueueOverflowEvent`, `ElegibilidadeFalhaEvent` (+ `AuditEvent` de `src/core/audit/models.py` como caso à parte append-only). Nota explícita: **não há bus central** (`src/core/event_bus.py` não existe) — despacho via notifier Ports ponto-a-ponto. Links para os 4 arquivos de port + testes `test_alocacao_service_notifications.py` onde aplicável.

- [ ] **Step 4: Checar tamanhos e docs-check**

Run: `wc -l docs/explanation/domains/context-map.md docs/explanation/domains/domain-events.md && uv run python scripts/docs_check.py`
Expected: ambos 80–200; EXIT 0.

- [ ] **Step 5: Commit**

```bash
git add docs/explanation/domains/context-map.md docs/explanation/domains/domain-events.md
git commit -m "docs: add context map and domain events"
```

---

### Task 6: stubs batch 2 + index

**Files:**
- Create: `docs/explanation/domains/identity-domain.md`, `docs/explanation/domains/auth-domain.md`
- Modify: `docs/explanation/domains/index.md`

- [ ] **Step 1: Escrever stubs (~10 linhas cada)**

`identity-domain.md`: 1 frase (cadastro, CPF/CNS, dependentes, CRM/UF, RLS `organizacao_id`) + `Em construção — batch 2` + links `src/modules/identity/domain/models/` + prova `tests/unit/test_identity_models.py`.
`auth-domain.md`: 1 frase (OWASP, Argon2id, JWT, lockout, rate limit) + batch 2 + link `src/modules/auth/` + nota GRANT issue #38.

- [ ] **Step 2: Atualizar `docs/explanation/domains/index.md`**

Listar os 8 arquivos (4 densos + 2 transversais + 2 stubs batch 2) com 1 linha cada. Ler arquivo atual antes de editar.

- [ ] **Step 3: Commit**

```bash
git add docs/explanation/domains/identity-domain.md docs/explanation/domains/auth-domain.md docs/explanation/domains/index.md
git commit -m "docs: add batch2 stubs and domains index"
```

---

### Task 7: Verificação final batch 1

**Files:** nenhum novo (só leitura)

- [ ] **Step 1: Árvore e tamanhos**

Run: `find docs/explanation/domains -type f | sort; wc -l docs/explanation/domains/*.md`
Expected: 6 densos (80–250) + 2 stubs (~10) + index.

- [ ] **Step 2: Anti-drift**

Run: `uv run python scripts/docs_check.py && echo CLEAN; rg -U '```python[^`]{400,}' docs/explanation/domains/ | head -3; echo "EXIT:$?"`
Expected: CLEAN; nenhum bloco python gigante.

- [ ] **Step 3: Mermaid sanity**

Run: `rg -c "stateDiagram-v2|flowchart" docs/explanation/domains/*.md`
Expected: stateDiagram em triage/queue/consultation/billing (4), flowchart em context-map (≥1).

- [ ] **Step 4: Status limpo**

Run: `git status --short; git log --oneline -9`
Expected: vazio (tudo commitado por task).

---

## Self-Review

- **Spec coverage:** arquivos §2 → Tasks 1–6 (4 domínios + 2 transversais + 2 stubs + index); âncoras §3 → comandos Step 1 de cada task (métodos, enums, lua, ports, testes); DoD §4 (template, Mermaid citando guardiões, RNs linkadas, docs-check) → Steps 2–3; batch 2 §5 → Task 6 stubs, fora do ciclo denso.
- **Placeholder scan:** sem TBD/TODO; comandos com expected; Mermaid exigido com tipos (`stateDiagram-v2`/`flowchart`); correção event_bus (não existe) embutida na Task 5.
- **Type consistency:** nomes de métodos/enums/ports idênticos aos verificados via `rg` nesta sessão (`StatusAtendimento`, `PrioridadeClinica`, `StatusElegibilidade`, `PacienteAusenteEvent`, `calcular_score`, `disparar_alerta_samu`).

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-10-05-domains-batch1.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
