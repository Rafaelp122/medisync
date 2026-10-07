# Design Document: Documentação Diátaxis Adaptada (foco onboarding)

**Data:** 2026-10-05
**Status:** Aprovado (seções 1–4 validadas com usuário)
**Autor:** OpenCode + Rafael
**Escopo:** Fase 1 = onboarding Setup + primeira feature. Sem MkDocs agora, estrutura compatível.

---

## 1. Visão Geral & Contexto

Docs atuais cobrem bem o quadrante Explanation:

- `docs/01-business/business-vision.md` (Problem Space)
- `docs/02-product/specification.md` (Solution Space, RN01–RN07, RF-01–RF-10)
- `docs/03-architecture/overview.md + data-model.md + concurrency-and-queues.md + compliance-and-telemedicine.md + security-and-authorization.md`
- `docs/adrs/ADR-001 a ADR-008` + README
- `docs/superpowers/plans/ + specs/`

Falta Diátaxis completo: Tutorials (aprender), How-to (fazer), Reference (consultar). Referência de padrão: `wedding_management/docs` (tutorials/onboarding, guides, reference, explanation/concepts/domains, ADRs, MkDocs Material), adaptado — sem copiar `frontend/`, `terraform/`, `R2/` que não existem no MediSync.

Decisões do usuário:

1. Público primeiro: onboarding de devs.
2. Sem `mkdocs.yml` agora, mas pastas + `index.md` por pasta para plugar MkDocs depois sem refatorar.
3. Jornada: Setup até `just check` verde + primeira feature fim-a-fim.
4. Notas atômicas densas (Zettelkasten): 1 arquivo = 1 conceito, 80–250 linhas, sem repetição via links.
5. Exemplo real do repo nunca colado; só linkado (`path:símbolo` + `rg` + teste-link) para evitar code drift. Futuro: `pymdownx.snippets`.

---

## 2. Árvore Diátaxis Adaptada (Seção 1, aprovada)

```text
docs/
├── index.md
├── tutorials/
│   ├── index.md
│   ├── onboarding-quickstart.md
│   └── backend-first-feature.md
├── how-to/
│   ├── index.md
│   ├── dev-environment/
│   │   ├── setup-local.md
│   │   ├── migrations.md
│   │   └── task-runner-just.md
│   ├── backend/
│   │   ├── create-module-endpoint.md
│   │   ├── run-tests.md
│   │   └── debug-valkey-lua.md
│   └── troubleshooting/
│       ├── db-connection-locks.md
│       └── rls-tenant-missing.md
├── reference/
│   ├── index.md
│   ├── api/
│   │   ├── error-envelope.md
│   │   └── openapi.md
│   ├── environment/
│   │   └── variables.md
│   ├── architecture-standards/
│   │   ├── routers-finos.md
│   │   ├── dtos-commands.md
│   │   ├── tach-boundaries.md
│   │   └── documentation-standards.md
│   └── testing/
│       └── backend-testing-spec.md
├── explanation/
│   ├── index.md
│   ├── business-vision.md            # git mv de 01-business/
│   ├── product-specification.md      # git mv de 02-product/
│   ├── architecture/
│   │   ├── overview.md               # git mv de 03-architecture/
│   │   ├── data-model.md
│   │   ├── concurrency-and-queues.md
│   │   ├── compliance-telemedicine.md
│   │   └── security-authorization.md
│   ├── concepts/
│   │   ├── hexagonal-pragmatico.md
│   │   ├── inter-module-protocols.md
│   │   ├── multi-tenancy-rls.md
│   │   └── queue-lua-arq.md
│   └── domains/
│       ├── identity-domain.md
│       ├── triage-domain.md
│       ├── queue-domain.md
│       ├── consultation-domain.md
│       └── billing-domain.md
├── adrs/                             # mantém (ADR-001 a 008)
└── superpowers/                      # mantém plans/ + specs/
```

Regras estruturais:

- `git mv` preserva histórico de `01/02/03/` para `explanation/`; atualiza `README.md` raiz + `docs/README.md` com redirects.
- Toda pasta tem `index.md`.
- YAGNI: nada de `frontend/`, `terraform/`, `landing-page` nesta fase.

---

## 3. Notas Atômicas Densas sem DRY (Seção 2, aprovada + revisão anti-drift)

### 3.1 Definição

- 1 arquivo = 1 conceito testável no código. Ex: `queue-lua-arq.md` cobre score ZSET + `alocar_chamada.lua` + locks 45s + ARQ defer juntos. Não quebrar em `score.md` + `lua.md`.
- Denso = responde sozinho: o quê, por quê, onde no código, como verificar. Alvo 80–250 linhas. <40 funde com pai. >300 quebra.
- Exceção: `business-vision.md` e `product-specification.md` continuam longos (documentos raiz).

### 3.2 Sem repetição, sem notas finas

- Fonte única por fato. Fórmula do score mora em `explanation/architecture/concurrency-and-queues.md`; `concepts/` e `how-to/` linkam.
- Fora de escopo = link relativo + 1 frase de contexto, sem resumir o outro arquivo.
- Proibido: mesmo bloco de comando/código em 2 lugares. Comandos canônicos moram em `how-to/`; resto referencia.

### 3.3 Link-sem-cola (anti-drift)

Docs não colam código-fonte. Formato padrão em `Onde no código`:

```md
- Impl: `src/modules/queue/infrastructure/valkey_adapter.py:alocar_chamada`
- Spec: `docs/explanation/architecture/concurrency-and-queues.md#score`
- Prova viva: `tests/modules/queue/test_alloc.py::test_double_lock`
- Ver: `rg -n "alocar_chamada" src/`
```

- Máximo 5 linhas de contrato/spec (ex: fórmula score, códigos `0` vs `-1`) quando inevitável, marcadas como spec.
- Agora: links relativos checáveis por humano + script. Depois (MkDocs): `pymdownx.snippets` (`--8<--`) inclui trecho no build sem drift, sem mudar `.md`.

### 3.4 Template obrigatório

```md
# Título-conceito
> 1 frase: o que é + onde vive no código

## Contexto
## Conceito (denso, sem colar código)
## Onde no código (só links, sem colar)
## Verificação (comando rodável)
## Ver também (links)
```

Exemplos de calibragem: FINO proibido (`valkey.md` 12 linhas), DENSO desejado (`queue-lua-arq.md` com fórmula, path `.lua`, `0` vs `-1`, `just up/worker`, `pytest -k queue`), GOD proibido (`queue-tudo.md` com RLS + LiveKit + PAdES).

---

## 4. Fase 1 Enxuta (Seção 3, aprovada)

Criar com conteúdo denso novo (~8 arquivos):

1. `docs/index.md` — porta de entrada.
2. `tutorials/index.md` + `tutorials/onboarding-quickstart.md` — 15min até API + `just check` verde.
3. `tutorials/backend-first-feature.md` — endpoint fino → composition → service `commit()` → teste.
4. `how-to/index.md` + `how-to/dev-environment/setup-local.md` — `just up`, `uv sync`, `migrate`, `just check` (fonte única de comandos).
5. `how-to/backend/create-module-endpoint.md` + `how-to/backend/run-tests.md`.
6. `reference/index.md` + `reference/api/error-envelope.md` — RFC7807, `TENANT_INVALIDO`, 422/429/500, `Retry-After`.
7. `reference/environment/variables.md` — espelho comentado do `.env.example`.
8. `reference/architecture-standards/documentation-standards.md` — esta regra atomic-denso + link-sem-cola + template.

Mover sem reescrever: `git mv 01/02/03 → explanation/`, criar `explanation/index.md`, `concepts/index.md`, `domains/index.md` como stubs (1 parágrafo + links). `concepts/*` e `domains/*` densos ficam para fase 2.

Não mexer: `adrs/`, `superpowers/`. `README.md` raiz: só atualiza tabela de links.

Pronto fase 1: novo dev sai do zero até feature merged seguindo só docs. Prova: `just up && just check` + 1 teste novo passando.

---

## 5. Governança e DoD (Seção 4, aprovada)

Quando atualizar:

- Router/composition/service/commit → `how-to/backend/create-module-endpoint.md`.
- RN/score/Lua/RLS → `explanation/...`; `concepts/` referencia.
- Novo `.env` → `reference/environment/variables.md` no mesmo PR.

`just docs-check` (`scripts/docs_check.py` ~40 linhas): percorre `docs/**/*.md`, extrai `src/...` e `docs/...` referenciados, falha se path não existir; falha se achar bloco python >5 linhas fora de `reference/`. Entra no `just check` após fase 1 verde (para não quebrar CI agora).

DoD docs:

- [ ] 1 conceito por arquivo, 80–250 linhas (exceto business/product raiz).
- [ ] Zero código colado >5 linhas; resto `path:símbolo` + `rg` + teste-link.
- [ ] Seção `Verificação` com comando rodável.
- [ ] `just docs-check` verde.

Compatibilidade MkDocs futura garantida por: `index.md` por pasta, links relativos, kebab-case, sem `mkdocs.yml` agora.

---

## 6. Alternativas Consideradas

- **B) Híbrido incremental** (manter `01/02/03/` + adicionar `onboarding/guides/reference/`): zero quebra, mas mistura dois sistemas, dívida para MkDocs. Rejeitado.
- **C) Só onboarding mínimo** (3 arquivos): rápido, mas sem padrão, cada PR inventa lugar novo. Rejeitado.

## 7. Riscos

- Docs desatualizam em 2 sprints → mitigado por link-sem-cola + `docs-check` + DoD.
- `git mv` quebra links externos → mitigado atualizando `README.md` + `docs/README.md` no mesmo commit.
- Notas finas proliferam → mitigado por template + limite 80–250 linhas + revisão.

---

## Self-review

- [x] Sem TBD/TODO; escopo fase 1 explícito (~8 arquivos novos + moves).
- [x] Sem contradição: `explanation/` absorve `01/02/03`; `adrs/` e `superpowers/` intactos.
- [x] Foco único: onboarding Setup + primeira feature; concepts/domains densos na fase 2.
- [x] Ambiguidade removida: "denso" = 80–250 linhas + template; "link" = `path:símbolo` + `rg` + teste-link; código colado >5 linhas proibido.
