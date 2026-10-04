# TID251 (sqlalchemy.text) — decisão de não aplicar ban global via ruff

Data: 2026-10-04. Branch: refactor/routers-di. Task: guards Tach strict + teste arquitetural.

## Pedido
Proibir `sqlalchemy.text` fora de `infrastructure/core/tests` via Ruff TID251
(flake8-tidy-imports `banned-api`), sem `per-file-ignores` permanentes.

## Apuração
- Ruff 0.16.9: `TID251` estável (`ruff rule TID251` OK). Config seria
  `[tool.ruff.lint.flake8-tidy-imports.banned-api]` com `"sqlalchemy.text"`.
- `TID251` é global: permitir em `infrastructure/core/tests` exigiria
  `per-file-ignores` para religar a regra nesses paths — vetado pela task
  ("sem per-file-ignores permanentes").
- Usos legítimos atuais fora do allowlist (sem mudança de comportamento):
  - `src/modules/consultation/application/policies/clinical_access_policy.py:11`
    (`text()` p/ ABAC Tier 3 — check TCLE/status/médico).
  - `src/worker/tasks/base.py:8` (`SELECT 1` healthcheck).
  - `src/worker/tasks/sweeper.py:7` (`SELECT id FROM organizacoes` + `select`).
  - `src/worker/tasks/eligibility.py:7` (`text()` elegibilidade).
  - Permitidos (infra/core): `consultation/infrastructure/document_directory_sql.py`,
    `src/core/database.py`.
- Habilitar o ban hoje quebraria `just lint` nesses 4 arquivos; corrigir
  exigiria extrair SQL p/ ports/adapters em infrastructure (policy + worker),
  com risco comportamental — fora do escopo "sem mudança comportamento".

## Decisão
NÃO habilitar `TID251` global agora. Sem alteração em `pyproject.toml`,
sem `per-file-ignores` adicionados.

## Guardas compensatórios ativos
- `tach.toml` Stage B estrito (camadas + composition) — `tach check` 0 violações.
- `tests/architecture/test_routers_are_thin.py` (AST): routers sem
  `sqlalchemy/infrastructure/domain.models`, sem `.commit/.refresh/text/select`,
  sem `HTTPException`, sem `*Service(`.

## Follow-up (issues, não Fase 10)
- Extrair `ClinicalAccessPolicy` SQL p/ `infrastructure` atrás de porta.
- Extrair `worker/tasks` `text()` p/ adapters.
- Reavaliar ban path-scoped (custom AST test `test_sql_text_confined.py`
  ou `TID251` + ignores só em `infrastructure/core/tests`) após extração.
