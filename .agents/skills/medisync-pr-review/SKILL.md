---
name: medisync-pr-review
description: Revisão hostil independente do PR/diff em sessão limpa (Zero-Context / Segregação de Funções) em dois eixos (Standards vs Spec) com inventário mecânico de rotas via shell e achados concretos em 4 partes.
---

# MediSync PR Review: Revisão Hostil Independente em Dois Eixos

Esta skill define o protocolo mandatório de revisão rigorosa para validação de implementações e Pull Requests no MediSync Express. Ela é estruturada sob o princípio da **Segregação de Funções**, **dois eixos ortogonais isolados**, **inventário mecânico determinístico via shell** e **formato de achados objetivos em 4 partes**.

---

## 1. Princípios Fundamentais

1. **Segregação de Funções & Sessão Limpa (Zero-Context Isolation):**
   *A revisão NUNCA deve ser executada na mesma sessão de chat/agente que implementou o código.*
   A auto-revisão na mesma sessão gera viés de confirmação (*Goal Completion Bias*), contaminação de contexto e cegueira por saturação. A revisão deve ser iniciada pelo desenvolvedor em uma **sessão virgem e limpa**, sem memória de conversas ou justificativas prévias de quem implementou.
2. **Inventário Mecânico Determinístico (Zero Confiança em Leitura Visual):**
   *Não dependa de subagentes LLM para achar rotas ou métodos extras lendo centenas de linhas de diff.*
   O revisor executa extratores via shell determinísticos para extrair a lista exata de rotas HTTP/WS, schemas e métodos públicos criados no diff, confrontando essa lista 1:1 contra o escopo formal da Issue.
3. **Zero Speculative Code (Never Code Around Ambiguity):**
   Proibido criar rotas defensivas, aliases HTTP/WS redundantes, query params opcionais ou fallbacks especulativos para contornar ambiguidades da issue. Toda ação tem exatamente 1 contrato canônico. A presença de código especulativo acarreta reprovação imediata.
4. **Evidências sobre Narrativa (*Evidence over Narrative*):**
   Nenhuma alegação de desenvolvedor ou IA é aceita como verdade sem a saída do terminal comprovando código de retorno 0.
5. **Revisão em Dois Eixos Ortogonais (Standards vs. Spec):**
   - **Eixo Standards:** O código cumpre os padrões arquiteturais (Hexagonal, Routers Finos, ADRs), tipagem estrita, portões automatizados e ausência de code smells?
   - **Eixo Spec:** O código implementa fielmente o que a issue/spec pediu, sem itens parciais e com **zero scope creep**?
   - *Regra de Ouro:* Um eixo jamais mascara o outro (*Standards PASS + Spec FAIL* é tão reprovável quanto *Spec PASS + Standards FAIL*).
6. **Achados Objetivos e Verificáveis (No Vague Worries):**
   Proibido opiniões de gosto estilístico ou conjecturas vagas (*"no style taste, no 'consider'"*). Todo achado deve apresentar um caso de falha concreto (*input $\to$ resultado inválido ou violação de contrato*).

---

## 2. Processo de Revisão em 4 Fases

### Fase 1: Fixação do Ponto Fixo, Identificação da Spec & Inventário Mecânico

1. **Definir o Ponto Fixo:** Obtenha o branch base (default: `origin/main`).
   - Diff command: `git diff origin/main...HEAD` (ou `git diff HEAD~1..HEAD` se for commit avulso já integrado com a main).
   - Commits: `git log origin/main..HEAD --oneline`
   - Se o diff for vazio ou inválido, aborte imediatamente.
2. **Identificar a Issue Canônica no GitHub:**
   ```bash
   gh issue view <numero> --json title,body
   ```
   *(Caso o `gh` não esteja disponível, solicite o texto/corpo da issue ao desenvolvedor).*  
   Localize também a User Story correspondente em `docs/user-stories/` se for funcionalidade clínica.

3. **Inventário Mecânico de Superfície Pública (Extração via Shell):**
   Antes de despachar os subagentes, execute no terminal os extratores determinísticos:
   ```bash
   # 1. Rotas HTTP e WebSockets de Backend adicionadas no diff
   git diff origin/main...HEAD -- "src/modules/*/presentation/routers/*" | grep -A 2 -E "^\+\s*@.*router\.(get|post|put|delete|patch|websocket)"

   # 2. Schemas Pydantic de Request/Response de Backend adicionados
   git diff origin/main...HEAD -- "src/modules/*/presentation/schemas.py" | grep -E "^\+\s*class\s+[A-Za-z0-9_]+"

   # 3. Novos métodos públicos de serviço (sync e async)
   git diff origin/main...HEAD -- "src/modules/*/application/services/*" | grep -E "^\+\s*(async\s+)?def\s+[a-zA-Z0-9_]+" | grep -v "^\+\s*(async\s+)?def\s+_"

   # 4. Frontend: Componentes Visuais e Custom Hooks adicionados (se houver alteração em frontend/)
   git diff origin/main...HEAD -- "frontend/src/features/*/components/*" | grep -E "^\+\s*export\s+(function|const)\s+[A-Za-z0-9_]+"
   git diff origin/main...HEAD -- "frontend/src/features/*/api/*" | grep -E "^\+\s*export\s+function\s+use[A-Za-z0-9_]+"

   # 5. Frontend: Schemas Zod de Formulário adicionados
   git diff origin/main...HEAD -- "frontend/src/features/*/schemas/*" | grep -E "^\+\s*export\s+const\s+[A-Za-z0-9_]+"
   ```
   *Guarde a lista exata gerada por esses comandos: ela é o contrato físico incontestável do que foi alterado.*

---

### Fase 2: Portão Executável Automatizado (Fast-Fail)

Execute o portão orquestrado no terminal:

```bash
just check-fast
```
*(Se o diff incluir alterações em `frontend/`, execute também:)*
```bash
just frontend-check && just frontend-test
```

- **Critério de Bloqueio Imediato:** Se qualquer etapa falhar (`scan-secrets`, `docs-check`, `audit-ai-code`, `fmt`, `lint`, `typecheck`, `tach`, `test-unit`, `test-integration`, `frontend-check`, `frontend-test`), **REPROVE O PR IMEDIATAMENTE**. Não gaste tokens rodando subagentes se a base não compila, vaza segredos ou quebra testes.

---

### Fase 3: Disparo de Subagentes Paralelos (Os Dois Eixos)

Com o portão automatizado verde, execute dois subagentes concorrentes em modo *read-only* utilizando `invoke_subagent` com `TypeName="research"`:

#### 🅰️ Subagente 1 — Eixo Standards & Arquitetura
Configuração: `TypeName="research"`, `Role="Revisor Standards & Arquitetura"`  
Prompt do subagente:
- Fornecer o `git diff origin/main...HEAD`.
- Auditar contra os padrões do repositório (`AGENTS.md` e ADRs):
  1. **Backend - Routers Finos (ADR-001 §6-§7):** Routers nunca chamam banco, `.commit()`, `.refresh()`, `text()` nem importam `infrastructure`.
  2. **Backend - Zero Mapper Hell (ADR-008):** Proibido criar DTOs manuais duplicados. Schemas de resposta usam `from_attributes=True`.
  3. **Frontend - Zero DTO Duplication & Anti-Barrel Imports (ADR-011):** Proibido interfaces ou schemas manuais duplicando Pydantic. Proibido barrel imports da raiz `@/api/generated`.
  4. **Frontend - Componentes Compostos & React 19:** Proibido boolean props para alternar modos (`isDoctor`, `isEmergency`). Proibido `forwardRef` (usar prop `ref`). Contexto via `use(Context)`.
  5. **Frontend - Performance & View Transitions:** Timers e medidores em `useRef`. Polling em background nunca dispara view transitions (`default="none"`).
  6. **Testes com Fakes & Sem Fragilidade:** Backend usa doubles tipados de `tests/doubles.py`. Frontend usa MSW v2 (`server.resetHandlers()`), teardown obrigatório de fake timers (`afterEach(() => vi.useRealTimers())`). No Playwright, `page.clock.install()` **antes de `page.goto()`**, proibido `sleep()` / `waitForTimeout()`, encerramento explícito de contextos multi-usuário (`await context.close()`).
  7. **Docstrings de Proveniência & Erros com Offending Value:** Métodos públicos contêm links canônicos `docs/`. Erros interpolam valor ofensivo com máscara LGPD.
- **Smell Baseline & Menor Mudança:** Reportar apenas problemas com evidência de código e linha exata.

#### 🅱️ Subagente 2 — Eixo Spec & Zero Speculative Code
Configuração: `TypeName="research"`, `Role="Revisor Spec & Escopo"`  
Prompt do subagente:
- Fornecer a saída do **Inventário Mecânico de Superfície Pública**, o `git diff origin/main...HEAD` e o corpo da Issue / User Story.
- Auditar com foco estrito em conformidade:
  1. **Confronto Mecânico de Rotas, Componentes & Aliases (FAIL Imediato):** 
     - Confrontar cada rota/componente extraído no inventário mecânico contra o *In Scope* da issue.
     - **Regra Zero Speculative Code:** A presença de qualquer rota extra, componente defensivo ou alias não solicitado acarreta **FAIL automático e imediato** no Eixo Spec.
  2. **Requisitos Faltantes/Parciais:** Requisitos solicitados no *In Scope* ou critérios de aceitação da issue que não foram implementados no diff.
  3. **Scope Creep Geral:** Métodos públicos, telas ou parâmetros não relacionados ao problema da issue.
  4. **Divergência Lógica:** Código implementado cuja regra diverge do comportamento esperado descrito na issue ou User Story canônica.

---

### Fase 4: Agregação & Parecer Final

Apresente os resultados sob os dois eixos com achados classificados em **três níveis de severidade** e estruturados no **template de 4 partes**:

```markdown
### 📋 Relatório de Revisão Hostil de PR

#### 1. Portões de Execução Automatizada (`just check`)
- **Secrets (Gitleaks):** ✅ PASS (zero leaks)
- **Docs Diátaxis:** ✅ PASS (zero links quebrados, zero código colado)
- **Clean Code IA:** ✅ PASS (zero funções com aninhamento > 2)
- **Tipos & Linters:** ✅ PASS (basedpyright strict + ruff)
- **Fronteiras Modulares:** ✅ PASS (tach check)
- **Suíte de Testes:** ✅ PASS (unitários + integração verdes)

#### 2. Inventário Mecânico de Superfície Pública (Extração via Shell)
- **Rotas Adicionadas no Diff:**
  - `MÉTODO /api/v1/modulo/recurso` -> [AUTORIZADA NA ISSUE / NÃO SOLICITADA (FAIL)]
- **Zero Speculative Code:** [CONFORME (zero aliases/rotas defensivas) / DETECTADO CÓDIGO ESPECULATIVO (FAIL)]
- **Veredito da Superfície Pública:** [PASS / FAIL]

#### 3. Achados de Revisão (Formato Canônico em 4 Partes)

##### 🚨 Must Fix (Impede o Merge)
*(Bugs, requisitos faltantes, rotas especulativas, quebras de ADR/Tach, falhas de teste)*
1. **[Título do Achado]** (`modulo/arquivo.py:L40-52`)
   - **O que é:** [1-2 frases sobre o trecho alterado]
   - **Problema:** [Violação concreta de regra, contrato ou bug]
   - **Fix:** [A menor alteração que resolve de fato]
   - **Se ignorarmos:** [Risco real assistencial, técnico ou regulatório]

##### ⚠️ Should Fix (Ajuste Necessário antes de Merge)
*(Ausência de docstrings de proveniência, pequenas duplicações, cenários de borda sem teste unitário)*
2. **[Título do Achado]** (`modulo/arquivo.py:L15-20`)
   - **O que é:** ...
   - **Problema:** ...
   - **Fix:** ...
   - **Se ignorarmos:** ...

##### 💡 Nice to Have (Sugestões Não-Bloqueantes)
*(Oportunidades de simplificação ou micro-otimizações)*
3. **[Título do Achado]** (`modulo/arquivo.py:L80`)
   - **O que é:** ...
   - **Problema:** ...
   - **Fix:** ...
   - **Se ignorarmos:** ...

---

### ⚖️ Veredito Final
**[APROVADO PARA MERGE]** ou **[REPROVADO COM PENDÊNCIAS]**

*(Se aprovado com apenas 'Nice to Have', o PR pode ser integrado; havendo itens em 'Must Fix' ou 'Should Fix', a aprovação é bloqueada até correção).*
```
