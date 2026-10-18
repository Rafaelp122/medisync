---
name: medisync-pr-auditor
description: Auditoria hostil pré-merge em dois eixos (Standards vs Spec) executados via subagentes paralelos com base em evidências ("Evidence over Narrative"). Audita gates automatizados, arquitetura hexagonal, routers finos, fakes tipados, baseline de code smells e fidelidade à Issue/Spec sem scope creep.
---

# MediSync PR Auditor: Auditoria Hostil em Dois Eixos Baseada em Evidências

Esta skill define o protocolo de auditoria rigoroso para validação de implementações e pull requests no MediSync Express, estruturada em **dois eixos ortogonais** executados em subagentes paralelos isolados.

---

## 1. Princípios Fundamentais

1. **Evidências sobre Narrativa (*Evidence over Narrative*):** Nenhuma alegação de desenvolvedor ou IA é aceita como verdade sem a saída do terminal comprovando código de retorno 0.
2. **Revisão em Dois Eixos Ortogonais (Standards vs. Spec):**
   - **Eixo Standards:** O código cumpre os padrões arquiteturais, tipagem estrita, portões automatizados e ausência de code smells?
   - **Eixo Spec:** O código implementa fielmente o que a issue/spec pediu, sem itens parciais e sem *scope creep*?
   - *Regra de Ouro:* Um eixo jamais mascara o outro (*Standards PASS + Spec FAIL* é tão reprovável quanto *Spec PASS + Standards FAIL*).
3. **Isolamento de Contexto via Subagentes Paralelos:** Os dois eixos rodam como subagentes separados para não haver contaminação de contexto (*context pollution*).

---

## 2. Processo de Auditoria em 4 Fases

### Fase 1: Fixação do Ponto de Comparação & Identificação da Spec

1. **Definir o Ponto Fixo:** Obtenha o branch base (default: `origin/main`).
   - Diff command: `git diff origin/main...HEAD`
   - Commits: `git log origin/main..HEAD --oneline`
   - Valide se há diff: se o diff for vazio ou o ref for inválido, aborte imediatamente.
2. **Identificar a Issue / Spec:**
   - Obtenha o número da issue associada (`#xyz` nos commits ou fornecida pelo usuário).
   - Inspecione a issue canônica via:
     ```bash
     gh issue view <numero> --json title,body
     ```
   - Localize a User Story canônica correspondente em `docs/user-stories/` se for funcionalidade clínica.

---

### Fase 2: Portão Executável Automatizado (Fast-Fail)

Antes de despachar subagentes de leitura, execute o portão orquestrado no terminal:

```bash
just check
```
*(Em ambiente local de desenvolvimento sem contêineres Docker, execute `just check-fast`).*

- **Critério de Bloqueio Imediato:** Se `just check` (ou `check-fast`) falhar em qualquer etapa (`scan-secrets`, `docs-check`, `audit-ai-code`, `fmt`, `lint`, `typecheck`, `tach`, `test-unit`, `test-integration`), **REPROVE O PR IMEDIATAMENTE**. Não gaste tokens rodando subagentes se a base não compila, vaza segredos ou quebra testes.

---

### Fase 3: Disparo de Subagentes Paralelos (Os Dois Eixos)

Com o portão automatizado verde, execute dois subagentes concorrentes:

#### 🅰️ Subagente 1 — Eixo Standards & Arquitetura
Prompt do subagente:
- Fornecer o `git diff origin/main...HEAD`.
- Auditar contra os padrões do repositório (`AGENTS.md` e ADRs):
  1. **Routers Finos (ADR-001 §6-§7):** Routers nunca chamam banco, `.commit()`, `.refresh()`, `text()` nem importam `infrastructure`.
  2. **Zero Mapper Hell (ADR-008):** Proibido criar DTOs manuais duplicados com conversores `to_domain`/`to_orm`. Schemas de resposta usam `from_attributes=True`.
  3. **Testes com Fakes Tipados:** Proibido mocks anônimos (`MagicMock`, `patch`) onde cabem os fakes de `tests/doubles.py`.
  4. **Docstrings de Proveniência:** Métodos públicos de negócio contêm docstring enxuta (3-5 linhas) apontando para `Regras: docs/...`.
  5. **Exceções com Offending Value:** Erros interpolam valor recebido com valor esperado e máscara LGPD.
- **Smell Baseline (Fowler Heuristics):**
  - *Speculative Generality:* Criou abstrações, hooks ou parâmetros para necessidades não existentes?
  - *Middle Man:* Criou classes ou métodos que apenas delegam sem agregar regra?
  - *Feature Envy:* Método acessando mais dados de outro módulo/objeto do que os seus?
  - *Data Clumps:* Campos viajando repetidamente soltos que deveriam ser um DTO imutável?

#### 🅱️ Subagente 2 — Eixo Spec & Scope Creep
Prompt do subagente:
- Fornecer o `git diff origin/main...HEAD` e o corpo da Issue / User Story.
- Auditar rigorosamente:
  1. **Requisitos Faltantes/Parciais:** Requisitos solicitados no *In Scope* ou critérios de aceitação da issue que não foram implementados no diff.
  2. **Scope Creep (Não Solicitado):** Comportamentos, refatorações não relacionadas ou endpoints adicionados que NÃO estavam no escopo ou que violam a seção *Out of Scope* da issue.
  3. **Divergência Lógica:** Código implementado cuja regra diverge do comportamento esperado descrito na issue.

---

### Fase 4: Agregação & Parecer Final

Apresente os resultados sob os dois eixos e emita o veredito formal:

```markdown
### 📋 Relatório de Auditoria Hostil de PR

#### 1. Portões de Execução Automatizada (`just check`)
- **Secrets (Gitleaks):** ✅ PASS (zero leaks)
- **Docs Diátaxis:** ✅ PASS (zero links quebrados, zero código colado)
- **Clean Code IA:** ✅ PASS (zero funções com aninhamento > 2)
- **Tipos & Linters:** ✅ PASS (basedpyright strict + ruff)
- **Fronteiras Modulares:** ✅ PASS (tach check)
- **Suíte de Testes:** ✅ PASS (unitários + integração verdes)

#### 2. Eixo Standards & Arquitetura (Subagente 1)
- **Routers Finos & DI:** [PASS / FAIL] — detalhes...
- **Mapper Hell (ADR-008):** [PASS / FAIL] — detalhes...
- **Fakes Tipados:** [PASS / FAIL] — detalhes...
- **Fowler Smells:** [Nenhum smell detectado / Smells encontrados...]

#### 3. Eixo Spec & Scope Creep (Subagente 2)
- **Fidelidade aos Requisitos:** [100% Atendido / Requisitos pendentes...]
- **Filtro Anti-Scope-Creep:** [Respeitado / Violações de não-escopo...]
- **Critérios de Aceite da Issue:** [Atendidos / Pendentes...]

---

### ⚖️ Veredito Final
**[APROVADO PARA MERGE]** ou **[REPROVADO COM PENDÊNCIAS]**

*(Se reprovado, listar arquivos, linhas e comandos exatos de correção necessários).*
```
