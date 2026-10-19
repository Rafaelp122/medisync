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
   # 1. Rotas HTTP e WebSockets adicionadas no diff (método e path)
   git diff origin/main...HEAD -- "src/modules/*/presentation/routers/*" | grep -A 2 -E "^\+\s*@.*router\.(get|post|put|delete|patch|websocket)"

   # 2. Schemas de Request/Response adicionados
   git diff origin/main...HEAD -- "src/modules/*/presentation/schemas.py" | grep -E "^\+\s*class\s+[A-Za-z0-9_]+"

   # 3. Novos métodos públicos de serviço (sync e async)
   git diff origin/main...HEAD -- "src/modules/*/application/services/*" | grep -E "^\+\s*(async\s+)?def\s+[a-zA-Z0-9_]+" | grep -v "^\+\s*(async\s+)?def\s+_"
   ```
   *Guarde a lista exata gerada por esses comandos: ela é o contrato físico incontestável do que foi alterado.*

---

### Fase 2: Portão Executável Automatizado (Fast-Fail)

Execute o portão orquestrado no terminal:

```bash
just check
```
*(Em ambiente local de desenvolvimento sem contêineres Docker, execute `just check-fast`).*

- **Critério de Bloqueio Imediato:** Se `just check` (ou `check-fast`) falhar em qualquer etapa (`scan-secrets`, `docs-check`, `audit-ai-code`, `fmt`, `lint`, `typecheck`, `tach`, `test-unit`, `test-integration`), **REPROVE O PR IMEDIATAMENTE**. Não gaste tokens rodando subagentes se a base não compila, vaza segredos ou quebra testes.

---

### Fase 3: Disparo de Subagentes Paralelos (Os Dois Eixos)

Com o portão automatizado verde, execute dois subagentes concorrentes em modo *read-only* utilizando `invoke_subagent` com `TypeName="research"`:

#### 🅰️ Subagente 1 — Eixo Standards & Arquitetura
Configuração: `TypeName="research"`, `Role="Revisor Standards & Arquitetura"`  
Prompt do subagente:
- Fornecer o `git diff origin/main...HEAD`.
- Auditar contra os padrões do repositório (`AGENTS.md` e ADRs):
  1. **Routers Finos (ADR-001 §6-§7):** Routers nunca chamam banco, `.commit()`, `.refresh()`, `text()` nem importam `infrastructure`.
  2. **Zero Mapper Hell (ADR-008):** Proibido criar DTOs manuais duplicados com conversores `to_domain`/`to_orm`. Schemas de resposta usam `from_attributes=True`.
  3. **Testes com Fakes Tipados:** Proibido mocks anônimos (`MagicMock`, `patch`) onde cabem os fakes canônicos de `tests/doubles.py` (`FakeAsyncSession`, `FakeValkey`, `FakeMemoryStorage`, `FakePDFGenerator`, `FakeArqPool`).
  4. **Docstrings de Proveniência:** Métodos públicos de negócio contêm docstring enxuta (3-5 linhas) apontando para `Regras: docs/...`.
  5. **Exceções com Offending Value:** Erros interpolam valor recebido com valor esperado e máscara LGPD.
- **Smell Baseline & Menor Mudança:**
  - *Speculative Generality:* Criou abstrações, helpers ou parâmetros para necessidades não existentes?
  - *Middle Man:* Criou classes ou métodos que apenas delegam sem agregar regra?
  - *Feature Envy / Data Clumps:* Violações de coesão nos serviços e DTOs.
  - *No Vague Worries:* Apenas reporte problemas com evidência de código e linha exata.

#### 🅱️ Subagente 2 — Eixo Spec & Zero Speculative Code
Configuração: `TypeName="research"`, `Role="Revisor Spec & Escopo"`  
Prompt do subagente:
- Fornecer a saída do **Inventário Mecânico de Superfície Pública**, o `git diff origin/main...HEAD` e o corpo da Issue / User Story.
- Auditar com foco estrito em conformidade:
  1. **Confronto Mecânico de Rotas & Aliases (FAIL Imediato):** 
     - Confrontar cada rota extraída no inventário mecânico contra as rotas solicitadas no *In Scope* da issue.
     - **Regra Zero Speculative Code:** A presença de qualquer rota extra, rota espelho ou alias defensivo (`@router.*` redundante) acarreta **FAIL automático e imediato** no Eixo Spec.
  2. **Requisitos Faltantes/Parciais:** Requisitos solicitados no *In Scope* ou critérios de aceitação da issue que não foram implementados no diff.
  3. **Scope Creep Geral:** Métodos públicos, tabelas ou parâmetros não relacionados ao problema da issue.
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
