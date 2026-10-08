# Design Document: Concepts (miolo do Explanation)

**Data:** 2026-10-07
**Status:** Aprovado
**Branch:** `docs/concepts` (a partir da `main` pós-#49)
**Escopo:** 4 concept docs densos em `docs/explanation/concepts/`. Batch 2 domínios, reference/how-to faltantes e worker-doc seguem no backlog.

---

## 1. Arquivos

- `hexagonal-pragmatico.md` — ADR-001 aplicado: modelos ricos, sem mapper hell, transação + router fino.
- `inter-module-protocols.md` — catálogo das ~15 Ports + composition roots + grafo Mermaid.
- `multi-tenancy-rls.md` — ContextVar → SET LOCAL → RLS + papel `medisync_app` + lição issue #38.
- `queue-lua-arq.md` — ZSET + Lua + ARQ defer + sweeper (ponte queue↔worker).

Template: mesmo dos domains (Contexto/Regras-Conceito/Mermaid/Relações/Peculiaridades/Onde/Verificação/Ver também), 80–250 linhas, só links, zero python >5, sem âncoras uppercase.

## 2. Âncoras verificadas

- Hexagonal: `src/modules/queue/domain/models/atendimento.py`, `src/modules/*/presentation/schemas.py`, `src/modules/*/composition.py` (auth/consultation/identity/queue), `tach.toml`, ADR-001 + ADR-008, prova `tests/architecture/`.
- Protocols: `allocation_port.py`, `eligibility_provider.py`, `signed_cache_port.py`, `atendimento_reader_port.py`, `emergency_notifier.py`, `pdf_generator_port.py`, `document_directory_port.py`, `validation_rate_limiter_port.py`, `icp_brasil_signer_port.py`, notifiers; composição em `src/modules/*/composition.py`.
- RLS: `src/core/context.py` (`tenant_context`, `set_current_tenant_id`), `src/core/database.py` (`SET LOCAL` + `SET LOCAL ROLE medisync_app`), `migrations/versions/0002_row_level_security.py` (role, grants, default privileges, 9 policies), prova `tests/integration/test_rls_security.py`, lição issue #38 (GRANT condicional `0003`, banco fora do Alembic).
- Lua/ARQ: `src/modules/queue/infrastructure/lua/alocar_chamada.lua`, `lua_loader.py`, `src/modules/queue/domain/scoring.py`, `src/worker/tasks/ring_timeout.py:resolver_ring_timeout_task`, `src/worker/tasks/sweeper.py:reconciliar_fila_orphans_task`, `src/worker/settings.py` (confirmar path na execução).

## 3. DoD

- [ ] 80–250 linhas cada; Mermaid renderizável (grafo em protocols, sequência em lua-arq).
- [ ] Zero bloco python >5; `just docs-check` verde.
- [ ] Verificação com comando real por doc.

## Self-review

- [x] Sem TBD; 4 arquivos + âncoras com paths verificados.
- [x] Consistente com fase 1/batch 1 (template, link-sem-cola, Mermaid).
- [x] Escopo único: concepts; resto no backlog (§4 do doc de domínios + resposta de cobertura).
