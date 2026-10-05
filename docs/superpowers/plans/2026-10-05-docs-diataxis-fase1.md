# Docs Diátaxis Fase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar Diátaxis fase 1 (onboarding Setup + primeira feature) com notas atômicas densas linkadas, sem code drift.

**Architecture:** `git mv` de `01/02/03 → explanation/`, cria `tutorials/ + how-to/ + reference/` com `index.md` por pasta, adiciona `scripts/docs_check.py` + recipe `just docs-check`. Sem `mkdocs.yml` agora.

**Tech Stack:** Markdown + links relativos, Python stdlib (docs_check), just, rg, git mv.

---

## File Structure

Cria (conteúdo novo denso):

- `docs/index.md` — porta de entrada
- `docs/tutorials/index.md`, `docs/tutorials/onboarding-quickstart.md`, `docs/tutorials/backend-first-feature.md`
- `docs/how-to/index.md`, `docs/how-to/dev-environment/setup-local.md`, `docs/how-to/backend/create-module-endpoint.md`, `docs/how-to/backend/run-tests.md`
- `docs/reference/index.md`, `docs/reference/api/error-envelope.md`, `docs/reference/environment/variables.md`, `docs/reference/architecture-standards/documentation-standards.md`
- `docs/explanation/index.md`, `docs/explanation/concepts/index.md`, `docs/explanation/domains/index.md` (stubs)
- `scripts/docs_check.py` — valida links `src/...` e `docs/...` + proíbe bloco python >5 linhas

Move (sem reescrever):

- `docs/01-business/business-vision.md` → `docs/explanation/business-vision.md`
- `docs/02-product/specification.md` → `docs/explanation/product-specification.md`
- `docs/03-architecture/*` → `docs/explanation/architecture/*`

Modifica:

- `justfile` — adiciona recipe `docs-check` (NÃO toca em `check:` nesta fase)
- `README.md` (raiz) — atualiza tabela de links docs
- `docs/README.md` — atualiza árvore + redirects

Não mexer: `docs/adrs/`, `docs/superpowers/`.

Referências verificadas (usar nestes paths, não inventar):

- Lua: `src/modules/queue/infrastructure/lua/alocar_chamada.lua`, loader `src/modules/queue/infrastructure/lua_loader.py`
- Prova viva fila: `tests/unit/test_alocacao_service.py`
- Erros: `src/core/errors.py` (`ProblemDetail`, `TenantInvalido.code = "TENANT_INVALIDO"`)
- Rate limit: `src/modules/consultation/presentation/dependencies.py:54 exigir_rate_limit` (header `Retry-After`)
- Env: `.env.example` (37 linhas)

---

### Task 1: Estrutura base + index.md

**Files:**
- Create: `docs/index.md`, `docs/tutorials/index.md`, `docs/how-to/index.md`, `docs/reference/index.md`
- Test: nenhum (estrutural)

- [ ] **Step 1: Confirmar ausência da estrutura**

Run: `ls docs/tutorials docs/how-to docs/reference 2>&1 | head -5`
Expected: `No such file or directory` (prova que não existe)

- [ ] **Step 2: Criar diretórios**

Run: `mkdir -p docs/tutorials docs/how-to/dev-environment docs/how-to/backend docs/how-to/troubleshooting docs/reference/api docs/reference/environment docs/reference/architecture-standards docs/reference/testing`
Expected: exit 0

- [ ] **Step 3: Escrever `docs/index.md`**

```md
# MediSync Express — Documentação

> PA Digital 24/7 — Fila atômica Valkey + RLS + ARQ + LiveKit + PAdES.

## Por onde começar

- Novo aqui? → [Onboarding quickstart](tutorials/onboarding-quickstart.md) (15min até `just check` verde).
- Vai codar? → [Primeira feature backend](tutorials/backend-first-feature.md).
- Vai operar? → [Setup local](how-to/dev-environment/setup-local.md).

## Mapa Diátaxis

- [Tutorials](tutorials/index.md) — aprender fazendo.
- [How-to](how-to/index.md) — resolver tarefas.
- [Reference](reference/index.md) — consultar contratos.
- [Explanation](explanation/index.md) — entender o porquê.
- [ADRs](adrs/README.md) — trade-offs.

## Verificação

Run: `just check`
```

- [ ] **Step 4: Escrever indexes stub (mesmo padrão, 10–15 linhas cada)**

`docs/tutorials/index.md`:
```md
# Tutorials

> Aprender fazendo. Comece pelo quickstart.

- [Onboarding quickstart](onboarding-quickstart.md)
- [Backend first feature](backend-first-feature.md)

## Verificação

Run: `just check`
```
`docs/how-to/index.md`: mesma forma, links para `dev-environment/setup-local.md`, `backend/create-module-endpoint.md`, `backend/run-tests.md`.
`docs/reference/index.md`: mesma forma, links para `api/error-envelope.md`, `environment/variables.md`, `architecture-standards/documentation-standards.md`.

- [ ] **Step 5: Commit**

```bash
git add docs/index.md docs/tutorials/index.md docs/how-to/index.md docs/reference/index.md
git commit -m "docs: add diataxis base indexes"
```

---

### Task 2: Migrar 01/02/03 → explanation/ (git mv, sem reescrever)

**Files:**
- Move: `docs/01-business/business-vision.md` → `docs/explanation/business-vision.md`, `docs/02-product/specification.md` → `docs/explanation/product-specification.md`, `docs/03-architecture/` → `docs/explanation/architecture/`
- Create: `docs/explanation/index.md`, `docs/explanation/concepts/index.md`, `docs/explanation/domains/index.md`
- Modify: `README.md`, `docs/README.md`
- Test: `git log --follow` preservado

- [ ] **Step 1: Verificar origem**

Run: `ls docs/01-business docs/02-product docs/03-architecture`
Expected: lista `business-vision.md`, `specification.md`, `overview.md data-model.md concurrency-and-queues.md compliance-and-telemedicine.md security-and-authorization.md`

- [ ] **Step 2: Executar git mv**

Run: `mkdir -p docs/explanation/architecture docs/explanation/concepts docs/explanation/domains && git mv docs/01-business/business-vision.md docs/explanation/business-vision.md && git mv docs/02-product/specification.md docs/explanation/product-specification.md && git mv docs/03-architecture/overview.md docs/explanation/architecture/overview.md && git mv docs/03-architecture/data-model.md docs/explanation/architecture/data-model.md && git mv docs/03-architecture/concurrency-and-queues.md docs/explanation/architecture/concurrency-and-queues.md && git mv docs/03-architecture/compliance-and-telemedicine.md docs/explanation/architecture/compliance-and-telemedicine.md && git mv docs/03-architecture/security-and-authorization.md docs/explanation/architecture/security-and-authorization.md && rmdir docs/01-business docs/02-product docs/03-architecture 2>/dev/null; ls docs/explanation docs/explanation/architecture`
Expected: 5 arquivos em `architecture/`, sem `01/02/03/`

- [ ] **Step 3: Escrever `docs/explanation/index.md` (stub com links, sem duplicar)**

```md
# Explanation

> Entender o porquê. Fonte única de conceitos; tutoriais e how-tos linkam para cá.

- [Business vision](business-vision.md)
- [Product specification](product-specification.md)
- [Architecture overview](architecture/overview.md)
- [Data model](architecture/data-model.md)
- [Concurrency and queues](architecture/concurrency-and-queues.md)
- [Compliance and telemedicine](architecture/compliance-and-telemedicine.md)
- [Security and authorization](architecture/security-and-authorization.md)
- [Concepts](concepts/index.md) — fase 2 (atômicos densos)
- [Domains](domains/index.md) — fase 2 (um por bounded context)

## Verificação

Run: `rg -n "RN0[1-7]" docs/explanation/product-specification.md | head -10`
```

`docs/explanation/concepts/index.md` e `docs/explanation/domains/index.md`: 1 parágrafo + lista futura (`hexagonal-pragmatico`, `inter-module-protocols`, `multi-tenancy-rls`, `queue-lua-arq` / `identity`, `triage`, `queue`, `consultation`, `billing`) marcada como `fase 2`.

- [ ] **Step 4: Atualizar `README.md` raiz (só tabela docs, linhas ~160-166)**

Substituir `docs/01-business/business-vision.md` → `docs/explanation/business-vision.md`, `docs/02-product/specification.md` → `docs/explanation/product-specification.md`, `docs/03-architecture/...` → `docs/explanation/architecture/...`. Não reescrever outras seções.

- [ ] **Step 5: Atualizar `docs/README.md` (árvore + links adrs, mesma substituição de prefixo)**

- [ ] **Step 6: Commit**

```bash
git add -A docs/ README.md
git commit -m "docs: move 01-02-03 to explanation preserving history"
```

---

### Task 3: Tutorials (quickstart + first-feature)

**Files:**
- Create: `docs/tutorials/onboarding-quickstart.md`, `docs/tutorials/backend-first-feature.md`
- Test: comandos da seção Verificação de cada arquivo

- [ ] **Step 1: Escrever `docs/tutorials/onboarding-quickstart.md` (template Seção 2, links sem cola)**

```md
# Onboarding quickstart

> Do zero até API respondendo + `just check` verde em ~15min.

## Contexto

Precisa de Docker + `uv`. Infra: postgres, valkey, livekit, minio.

## Conceito

Setup = `just up` (infra) → `uv sync` (deps) → `migrate` → `just check`.

## Onde no código (só links)

- Infra: `docker-compose.yml`
- Deps: `pyproject.toml`
- Receitas: `justfile:up, install, migrate, check`

## Verificação

Run: `just up && uv sync && just migrate && just check`
Expected: `tach check` pass + `pytest` pass.

## Ver também

- [Setup local detalhado](../how-to/dev-environment/setup-local.md)
- [Run tests](../how-to/backend/run-tests.md)
```

- [ ] **Step 2: Validar comandos do quickstart existem**

Run: `rg -n "^(up|install|migrate|check):" justfile`
Expected: 4 matches.

- [ ] **Step 3: Escrever `docs/tutorials/backend-first-feature.md` (denso, exemplo linkado)**

Estrutura obrigatória: Contexto → Conceito (router fino → `*Dep` composition → service com `commit()` → helpers nunca commitam; `HTTPException` só em `presentation/dependencies.py`; erros domínio via `src/core/errors.py`) → Onde no código (links, sem colar):
  - Exemplo router fino: link para 1 router real em `src/modules/queue/presentation/` ou `src/modules/consultation/presentation/routers/`
  - Exemplo service commit: link para 1 service em `src/modules/queue/application/` com `await session.commit()`
  - Erros: `src/core/errors.py:ProblemDetail, TenantInvalido`
  - Fronteira: `tach.toml`
→ Verificação (`just tach`, `pytest -k ...`, `just check`) → Ver também (`create-module-endpoint.md`, `routers-finos` futuro, ADR-001).

Comando de apoio para achar exemplo real na hora de escrever:
Run: `rg -n "await session.commit\(\)" src/modules/queue/application/ | head -5; ls src/modules/queue/presentation/`
Expected: pelo menos 1 match de commit + lista de routers.

- [ ] **Step 4: Commit**

```bash
git add docs/tutorials/
git commit -m "docs: add onboarding tutorials"
```

---

### Task 4: How-to (setup + endpoint + testes)

**Files:**
- Create: `docs/how-to/dev-environment/setup-local.md`, `docs/how-to/backend/create-module-endpoint.md`, `docs/how-to/backend/run-tests.md`
- Test: executar cada bloco Verificação

- [ ] **Step 1: Escrever `setup-local.md` (fonte única de comandos)**

Conteúdo: pré-reqs (Python 3.12+, uv, Docker) → `just up` → `uv sync` → `cp .env.example .env` → `just migrate` → `just check` → `just logs/ps/down`. Cada comando 1 bloco bash + expected output 1 linha. Links: `docker-compose.yml`, `justfile`, `.env.example`.

Validar:
Run: `rg -n "^(up|down|logs|ps|migrate|check):" justfile`
Expected: 6 matches.

- [ ] **Step 2: Escrever `create-module-endpoint.md` (checklist router-fino)**

Checklist (sem colar código, só regras + onde conferir):
1. Router nunca importa `sqlalchemy/infrastructure/domain.models`, nunca `.commit()/.refresh()/text()/select()`, nunca instancia `*Service(` (usa `*Dep` de `composition.py`).
2. Service commita 1x por caso de uso; helpers nunca.
3. `HTTPException` só em `presentation/dependencies.py` (ex: `exigir_rate_limit` → 429).
4. Teste AST: `tests/architecture/test_routers_are_thin.py` deve passar.
Onde no código: `tach.toml`, `src/modules/consultation/presentation/dependencies.py:54`, 1 router + 1 composition reais (achar com `ls src/modules/*/presentation/ src/modules/*/composition*`).
Verificação:
Run: `just tach && just test-fast`
Expected: PASS.

- [ ] **Step 3: Escrever `run-tests.md`**

Conteúdo: `just test` (com cov) vs `just test-fast` (`pytest -n auto --no-cov`) vs `pytest tests/unit/test_alocacao_service.py -v` (exemplo fila). Links: `pyproject.toml` (pytest config), `tests/unit/test_alocacao_service.py`.
Validar:
Run: `just test-fast 2>&1 | tail -5`
Expected: suite passa (ou lista falhas pré-existentes para registrar no PR, sem corrigir aqui).

- [ ] **Step 4: Commit**

```bash
git add docs/how-to/
git commit -m "docs: add setup and backend how-tos"
```

---

### Task 5: Reference (error-envelope + variables + standards)

**Files:**
- Create: `docs/reference/api/error-envelope.md`, `docs/reference/environment/variables.md`, `docs/reference/architecture-standards/documentation-standards.md`
- Test: conferir contra `src/core/errors.py` e `.env.example`

- [ ] **Step 1: Escrever `error-envelope.md` (fonte única de códigos)**

Levantar antes:
Run: `rg -n "code = |class \w+Error|status_code" src/core/errors.py | head -20; rg -n "Retry-After" src/modules/consultation/presentation/dependencies.py`
Expected: `TENANT_INVALIDO`, classes 400/401/403/404/409/422 + `Retry-After` linha 72.
Conteúdo: envelope RFC7807 (`title/status/detail/code` de `src/core/errors.py:ProblemDetail`) → tabela: tenant ausente `400 TENANT_INVALIDO` | login sem tenant `422` | rate limit `429 + Retry-After` (`dependencies.py:54 exigir_rate_limit`) | `EVOLUCAO_NAO_ENCONTRADA / DOCUMENTO_CLINICO_NAO_ENCONTRADO → 404` | validação órfã `500 DOCUMENTO_INTEGRIDADE`. Zero exemplo colado além de 5 linhas de contrato; resto links.

- [ ] **Step 2: Escrever `variables.md` (espelho comentado do `.env.example`)**

Regra: lista as 7 seções do `.env.example` (app core, postgres, valkey, livekit, minio) com 1 linha por variável + onde usada (`src/core/config.py`). Não duplica valores secrets; manda copiar com `cp .env.example .env`.
Validar:
Run: `rg -c "^[A-Z_]+=" .env.example`
Expected: número de vars para conferir cobertura (deve bater com lista no md).

- [ ] **Step 3: Escrever `documentation-standards.md` (governança atomic-denso + link-sem-cola)**

Conteúdo obrigatório: definição 80–250 linhas / <40 funde / >300 quebra; template das 5 seções; formato `Impl/Spec/Prova viva/Ver(rg)`; proibição bloco python >5 linhas; exemplos bom/ruim/drift usando `src/modules/queue/infrastructure/lua/alocar_chamada.lua` + `tests/unit/test_alocacao_service.py`; regra quando atualizar docs; DoD checklist.

- [ ] **Step 4: Commit**

```bash
git add docs/reference/
git commit -m "docs: add reference error envelope variables standards"
```

---

### Task 6: `scripts/docs_check.py` + `just docs-check` (sem wire no `check:` ainda)

**Files:**
- Create: `scripts/docs_check.py`
- Modify: `justfile` (adiciona recipe, NÃO altera `check:`)
- Test: `just docs-check`

- [ ] **Step 1: Confirmar que script não existe**

Run: `ls scripts/docs_check.py 2>&1`
Expected: `No such file`.

- [ ] **Step 2: Escrever `scripts/docs_check.py` (stdlib only, ~40 linhas)**

```python
#!/usr/bin/env python3
"""Fail if docs reference missing src/docs paths or paste code >5 lines."""
from __future__ import annotations
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH_RE = re.compile(r"`((?:src|docs|tests)/[^`:\s]+)")
FENCE_RE = re.compile(r"```python(.*?)```", re.DOTALL)

def main() -> int:
    errors: list[str] = []
    for md in (ROOT / "docs").rglob("*.md"):
        text = md.read_text(encoding="utf-8")
        for m in PATH_RE.finditer(text):
            ref = m.group(1).split("#")[0]
            if not (ROOT / ref).exists():
                errors.append(f"{md.relative_to(ROOT)}: missing {ref}")
        for m in FENCE_RE.finditer(text):
            lines = [ln for ln in m.group(1).strip().splitlines() if ln.strip()]
            if len(lines) > 5 and "reference/" not in str(md):
                errors.append(f"{md.relative_to(ROOT)}: python block {len(lines)} lines >5")
    for e in errors:
        print(e)
    return 1 if errors else 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Adicionar recipe no `justfile` (append, sem tocar `check:`)**

```just
# Valida links src/docs referenciados nos .md e proíbe cola >5 linhas
docs-check:
    uv run python scripts/docs_check.py
```

- [ ] **Step 4: Rodar e corrigir links quebrados da fase 1**

Run: `just docs-check`
Expected: exit 0. Se falhar, corrigir paths nos .md (ex: trocar `valkey_adapter.py` por `lua/alocar_chamada.lua`) até verde. NÃO wiring em `check:` nesta fase.

- [ ] **Step 5: Commit**

```bash
git add scripts/docs_check.py justfile
git commit -m "docs: add docs-check without wiring to check"
```

---

### Task 7: Verificação final fase 1

**Files:** nenhum novo (só leitura)

- [ ] **Step 1: Árvore completa**

Run: `find docs/tutorials docs/how-to docs/reference docs/explanation -type f | sort`
Expected: 4 indexes + quickstart + first-feature + setup-local + create-endpoint + run-tests + error-envelope + variables + documentation-standards + explanation/index + concepts/index + domains/index + moves de architecture/business/product.

- [ ] **Step 2: Grep anti-duplicação (amostragem)**

Run: `rg -l "alocar_chamada" docs/ | head; echo "---"; rg -U '```python[^`]{600,}' docs/tutorials docs/how-to | head -3`
Expected: referências via links, nenhum bloco python gigante em tutorials/how-to.

- [ ] **Step 3: Smoke comandos de dev pelos docs**

Run: `just tach 2>&1 | tail -3 && just test-fast 2>&1 | tail -3`
Expected: ambos PASS (ou falhas pré-existentes documentadas, sem escopo de fix aqui).

- [ ] **Step 4: Commit final vazio? Não — só confirma limpo**

Run: `git status --short`
Expected: vazio (tudo commitado por task).

---

## Self-Review

- **Spec coverage:** árvore §2 → Tasks 1–2; atomic-denso + link-sem-cola §3 → Tasks 3–5 (template) + Task 6 (enforcement); fase 1 §4 (8 arquivos + moves) → Tasks 1–5; governança §5 (`docs-check`, DoD, sem wire no `check:`) → Task 6; YAGNI (sem mkdocs/frontend/terraform) respeitado.
- **Placeholder scan:** sem TBD/TODO; comandos com expected; paths verificados via rg (`lua/`, `errors.py`, `dependencies.py:54`, `.env.example`, `test_alocacao_service.py`).
- **Type consistency:** `docs-check` via `uv run python`; recipes `just ...` batem com `justfile`; `path:símbolo` + `rg` em todos os templates.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-10-05-docs-diataxis-fase1.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
