# Design Document: Domain Docs Batch 1 (fluxo assistencial)

**Data:** 2026-10-05
**Status:** Aprovado (seções 1–4 validadas com usuário)
**Branch:** `docs/domains-batch1` (a partir de `docs/diataxis-fase1`, PR #49)
**Escopo:** 4 domain docs densos (triage, queue, consultation, billing) + 2 transversais (context-map, domain-events). `identity` + `auth` ficam para batch 2.

---

## 1. Visão Geral & Contexto

A fase 1 Diátaxis entregou estrutura + onboarding, com `docs/explanation/domains/index.md` como stub e `concepts/*` vazios. Este batch preenche os domínios do **fluxo assistencial** (triage → queue → consultation → billing), cada um com regras de negócio (RNs), peculiaridades e relações — no padrão atomic-denso + link-sem-cola + Mermaid (sem visual companion, por decisão do usuário).

Mapeamento RN→domínio (fonte: `docs/explanation/product-specification.md`):

| Domínio | RNs | Agregado raiz |
|---|---|---|
| triage | RN01, RN04, RN07 | `Triagem` (`src/modules/triage/domain/models/triagem.py`) |
| queue | RN01, RN02, RN05 | `Atendimento` (`src/modules/queue/domain/models/atendimento.py`) |
| consultation | RN06, RN07 | `EvolucaoClinica`, `DocumentoClinico` (`src/modules/consultation/domain/models/`) |
| billing | RN03 | máquina de estados (`src/modules/billing/domain/enums.py`) |

## 2. Arquivos (Seção 1, aprovada)

Criar em `docs/explanation/domains/` (substituem stubs):

- `triage-domain.md` — RN01, RN04, RN07
- `queue-domain.md` — RN01, RN02, RN05 (~200 linhas, maior do batch)
- `consultation-domain.md` — RN06, RN07
- `billing-domain.md` — RN03
- `context-map.md` — transversal: Ports síncronas (Mermaid `flowchart`)
- `domain-events.md` — transversal: catálogo de events + EventBus

`identity-domain.md` + `auth-domain.md`: stubs de ~10 linhas apontando para batch 2.

Template único por domain doc: Contexto (posição no fluxo) → Regras (RN→comportamento→links) → Máquina de estados (`stateDiagram`, se houver) → Relações (ports consumidas/expostas + tabelas/RLS) → Peculiaridades → Onde no código (models/services/ports/testes-prova-viva) → Verificação (comando rodável) → Ver também.

## 3. Âncoras por Domínio (Seção 2, aprovada)

- **triage:** `domain/classification.py` (5 níveis), `domain/models/triagem.py`, `application/ports/emergency_notifier.py` (SAMU 192), TCLE hash <45s. Peculiaridade: classificação alimenta o score da fila via dado, não via chamada.
- **queue:** `domain/scoring.py` (score 64 bits + FIFO UUIDv7), `domain/models/atendimento.py` (`alocar_para_medico()` e transições), `infrastructure/lua/alocar_chamada.lua` (locks 45s, códigos `0`/`-1`), `application/services/alocacao_service.py`, `controle_admissao_service.py` (backpressure α). Prova viva: `tests/unit/test_alocacao_service.py`.
- **consultation:** `domain/models/evolucao_clinica.py`, `documento_clinico.py`, `documento_item.py`, `domain/s3_keys.py`, `infrastructure/livekit_adapter.py` (só emite JWT, nunca toca mídia), PAdES via PyHanko. Prova viva: testes PEP/documentos em `tests/unit` + integração.
- **billing:** `domain/enums.py` (`stateDiagram`), `application/services/eligibility_service.py`, `infrastructure/adapters/sus_adapter.py` (no-op) vs `private_gateway_adapter.py`. Peculiaridade: pendência financeira nunca expulsa da fila (RN03).
- **context-map.md:** `flowchart` triage→queue→consultation→billing com arestas rotuladas pela Port (`allocation_port`, `eligibility_provider`, notifiers). Links para `application/ports/*` de cada módulo.
- **domain-events.md:** tabela evento→produtor→consumidores→port (`QueueOverflowEvent`, `PacienteAusenteEvent`, `ElegibilidadeFalhaEvent`, + `AuditEvent` em `src/core/audit/models.py`) e despacho via `src/core/event_bus.py`.

## 4. Anti-drift + DoD (Seção 3, aprovada)

- `stateDiagram` espelha transições do código; cada diagrama cita o método guardião (ex: `atendimento.alocar_para_medico()`).
- RNs com 1–2 linhas + link para `product-specification.md#RN0X` (fonte única) + teste-prova-viva. Sem recopiar regras.
- DoD por arquivo: template completo, Mermaid renderizável, zero bloco python >5 linhas, `just docs-check` verde, `Verificação` com comando real (`pytest -k ...`, `rg ...`).

## 5. Batch 2 Backlog (Seção 4, fora deste ciclo)

- `identity-domain.md`: onboarding, CPF/CNS, dependentes, profissionais CRM/UF, RLS `organizacao_id`.
- `auth-domain.md`: OWASP, Argon2id, JWT, lockout, rate limit, `usuarios_credenciais` + lição do GRANT (issue #38).
- Possíveis se os 4 docs provarem valor: glossário ubiquitous language, índice RN→código.

## 6. Alternativas Consideradas

- **B) Piloto queue-only:** calibraria template mais barato, mas deixaria fluxo incompleto e context-map sem material. Rejeitado.
- **C) 6 domínios de uma vez:** `identity` + `auth` têm densidade própria (onboarding/CPF + OWASP/lockout); misturar estouraria 250 linhas ou viraria god-note. Rejeitado.

## Self-review

- [x] Sem TBD/TODO; 6 arquivos nomeados + stubs batch 2 explícitos.
- [x] Consistente com fase 1 (mesmo template, mesma regra link-sem-cola, Mermaid em vez de companion).
- [x] Foco único: fluxo assistencial; identity/auth/glossário no backlog.
- [x] Sem ambiguidade: âncoras com paths verificados via `find`/`rg`; profundidade 80–250 linhas.
