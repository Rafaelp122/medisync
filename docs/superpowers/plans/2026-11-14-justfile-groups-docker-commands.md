# Justfile Grouping and Container Commands Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganizar o `justfile` com grupos nativos (`[group('...')]`), parametrizar `just logs [service]`, adicionar comandos espelho para contêiner sob o grupo `[infra]` delegando para dentro do contêiner backend (`docker-migrate`, `docker-seed`, `docker-shell`, `docker-test`), e atualizar a documentação (`README.md`, `AGENTS.md`, `docs/how-to/dev-environment/run-docker.md` e `docs/how-to/dev-environment/setup-local.md`).

**Architecture:** Adotar os recursos nativos do `just 1.58.0` (`[group('...')]`) para categorização visual (`geral`, `infra`, `backend`, `frontend`) sem quebrar compatibilidade retroativa nem alterar nomes de receitas existentes. Comandos locais continuam o padrão no host via `uv`/`pnpm`, enquanto comandos de contêiner (`docker compose exec backend ...`) oferecem interface espelho explícita em `[infra]`.

**Tech Stack:** `just 1.58.0`, Docker Compose, Python 3.14 / uv, Pytest.

**Spec:** Brainstorming acordado nesta conversa (Opção A com comandos locais padrão + comandos de contêiner em `[infra]` + `logs [service]`).

## Global Constraints

- Preservar 100% dos nomes e comportamentos das receitas existentes (Zero Breaking Changes).
- Comandos locais de desenvolvimento permanecem como padrão (`just migrate`, `just seed-dev`, `just test-fast`, `just check-fast`, etc.).
- Comandos de contêiner operam exclusivamente através de `docker compose exec backend ...`.
- Receita `logs` deve aceitar argumento opcional `service=""` executando `docker compose logs -f {{service}}`.
- Todas as receitas públicas do `justfile` devem possuir anotação `[group(...)]`.
- Documentação em `docs/` deve respeitar o padrão Diátaxis e a regra de proibir blocos de código colados > 5 linhas (usar referências simbólicas).
- Todo o portão rápido (`just check-fast` e `just docs-check`) deve passar com código de retorno 0.

## Review Focus

1. `just --list` deve exibir os 4 grupos canônicos (`geral`, `infra`, `backend`, `frontend`) com suas respectivas receitas.
2. `just logs` (sem argumentos) deve continuar acompanhando todos os serviços sem erro de sintaxe.
3. `just logs backend` (com argumento) deve delegar para `docker compose logs -f backend`.
4. `test_readme_just_commands_exist_in_justfile` e `scripts/docs_check.py` devem passar sem erros de comandos desconhecidos.
5. Nenhuma receita interna ou pública deve ficar órfã (sem grupo atribuído).

---

### Task 1: Testes de Arquitetura para Grupos e Comandos do Justfile

**Files:**
- Modify: `tests/architecture/test_docs_and_stack_consistency.py`

- [x] **Step 1: Escrever teste de arquitetura para validar grupos e novas receitas**
  Adicionar testes em `tests/architecture/test_docs_and_stack_consistency.py`:
  - `test_justfile_recipes_are_grouped()`: Valida que toda receita no `justfile` (exceto `default`) possui um atributo `[group('...')]` associado e que os grupos permitidos são exatamente `{'geral', 'infra', 'backend', 'frontend'}`.
  - `test_justfile_container_and_log_recipes_exist()`: Valida a presença de `logs`, `docker-migrate`, `docker-seed`, `docker-shell` e `docker-test`.

- [x] **Step 2: Executar o teste e confirmar falha (Red)**
  Executar:
  ```bash
  uv run pytest tests/architecture/test_docs_and_stack_consistency.py -k "justfile"
  ```
  Confirmar que falha porque os grupos e comandos ainda não foram adicionados ao `justfile`.

---

### Task 2: Reorganização do `justfile` com Grupos e Novos Comandos

**Files:**
- Modify: `justfile`

- [x] **Step 1: Aplicar atributos `[group('...')]` a todas as receitas existentes**
  - Grupo `geral`: `dev`, `setup-dev`, `check`, `check-fast`, `scan-secrets`, `docs-check`, `audit-ai-code`, `audit-frontend`, `bump-check`, `bump`, `pre-commit-install`.
  - Grupo `infra`: `up-infra`, `up`, `down`, `ps`, `logs`, `clean-docker`, `migrate`, `seed-dev`, `rollback`, `rollback-base`, `migration-history`, `check-migrations`, `docker-build`, `docker-build-dev`, `smoke-docker`.
  - Grupo `backend`: `install`, `backend-dev`, `worker`, `fmt`, `lint`, `typecheck`, `tach`, `test-fast`, `test-unit`, `test-integration`, `test`, `test-parallel`, `dump-openapi`, `scaffold-module`.
  - Grupo `frontend`: `frontend-install`, `frontend-dev`, `frontend-generate`, `frontend-check`, `frontend-test`, `frontend-test-e2e`.

- [x] **Step 2: Atualizar a receita `logs` para aceitar `service=""`**
  Modificar a receita `logs`:
  ```just
  [group('infra')]
  # Acompanha logs dos contêineres em tempo real (ex.: just logs, just logs backend)
  logs service="":
      docker compose logs -f {{service}}
  ```

- [x] **Step 3: Adicionar comandos de contêiner em `[group('infra')]`**
  Adicionar as receitas sob `[group('infra')]`:
  ```just
  [group('infra')]
  # Executa migrações do Alembic dentro do contêiner backend
  docker-migrate:
      docker compose exec backend alembic upgrade head

  [group('infra')]
  # Popula dados de desenvolvimento dentro do contêiner backend
  docker-seed:
      docker compose exec backend python -m scripts.seed_dev

  [group('infra')]
  # Abre um terminal interativo bash dentro do contêiner backend
  docker-shell:
      docker compose exec -it backend /bin/bash

  [group('infra')]
  # Executa a suíte de testes unitários e de arquitetura dentro do contêiner backend
  docker-test:
      docker compose exec backend pytest tests/unit tests/architecture
  ```

- [x] **Step 4: Executar os testes de arquitetura e validar sucesso (Green)**
  Executar:
  ```bash
  uv run pytest tests/architecture/test_docs_and_stack_consistency.py -k "justfile"
  ```
  Validar também a listagem visual no terminal:
  ```bash
  just --list
  just --groups
  ```

---

### Task 3: Atualização do `README.md` e `AGENTS.md`

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`

- [x] **Step 1: Atualizar `README.md`**
  - Na seção "Como Executar o Projeto", detalhar o uso de `just backend-dev` / `just dev`.
  - Mencionar que os comandos do `just` estão organizados por grupos (`just --groups` e `just --list`).
  - Documentar `just logs [serviço]` e os comandos de contêiner (`just docker-migrate`, `just docker-seed`, `just docker-shell`).

- [x] **Step 2: Atualizar `AGENTS.md`**
  - Na Seção 1 ("Comandos e Tooling"), atualizar a lista de comandos de Infraestrutura para incluir `docker-migrate`, `docker-seed`, `docker-shell`, `docker-test` e o parâmetro opcional em `just logs [serviço]`.
  - Mencionar o suporte a grupos no Just (`just --group <grupo>`).

---

### Task 4: Atualização da Documentação Técnica (`docs/`)

**Files:**
- Modify: `docs/how-to/dev-environment/run-docker.md`
- Modify: `docs/how-to/dev-environment/setup-local.md`

- [x] **Step 1: Atualizar `docs/how-to/dev-environment/run-docker.md`**
  - Documentar os comandos de contêiner: `just docker-migrate`, `just docker-seed`, `just docker-shell`, `just docker-test`.
  - Atualizar instruções de inspeção interativa usando `just docker-shell`.
  - Reforçar na seção de resolução de problemas a distinção entre `just up` (sobe o backend no container ocupando a porta 8000) e `just up-infra` (apenas infraestrutura, ideal para desenvolvimento com `just backend-dev` / `just dev`).

- [x] **Step 2: Atualizar `docs/how-to/dev-environment/setup-local.md`**
  - Atualizar o passo de logs para indicar que `just logs` aceita o serviço como argumento opcional (ex.: `just logs backend`).

---

### Task 5: Validação Integrada do Portão de Qualidade

**Files:**
- Teste e verificação geral

- [x] **Step 1: Executar linters de documentação**
  Executar:
  ```bash
  just docs-check
  just audit-ai-code
  ```
  Garantir zero erros de paridade entre `README.md` e `justfile`.

- [x] **Step 2: Executar portão rápido unificado**
  Executar:
  ```bash
  just check-fast
  ```
  Garantir que formatação, linter, checagem de tipos, tach e testes rápidos passem 100% verde (exit code 0).

- [ ] **Step 3: Commit semântico**
  Criar commit semântico padronizado:
  ```bash
  git commit -m "feat(tooling): segregar receitas do justfile por grupos e adicionar comandos de container"
  ```
