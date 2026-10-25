---
name: medisync-issue-planner
description: Planejamento técnico com gate de falsificabilidade prévia, pesquisa em dois eixos (Standards & Arquitetura vs Spec & Diátaxis), fatiamento TDD Inside-Out e aplicação da Menor Alteração Completa. Use sempre que iniciar a resolução de uma issue.
---

# MediSync Issue Planner: Planejamento em Dois Eixos & TDD Desacoplado em Pares

Este procedimento padroniza o ciclo de planejamento de engenharia no MediSync Express. Nenhuma linha de código de produção deve ser escrita sem que esta skill seja executada e o plano aprovado pelo usuário.

---

## 1. Princípios Fundamentais

1. **Separação Rígida entre Planejamento e Ação:** Pensar é barato; reescrever código desalinhado custa tokens, tempo e introduz bugs.
2. **Ceticismo Investigativo & Falsificabilidade Prévia:** Nunca assuma a issue como verdade canônica inquestionável (*Zero Sycophancy*). A IA deve confrontar as premissas, sintomas e alegações com a base de código real antes de qualquer plano. Se o bug não existir, já tiver sido corrigido ou a premissa for falsa, a menor alteração completa é **zero código**.
3. **Dois Eixos Ortogonais de Planejamento:**
   - **Eixo A (Standards & Arquitetura):** Mapeamento de precedentes, Fakes tipados existentes em `tests/doubles.py`, isolamento no `tach.toml`, routers finos e ADRs.
   - **Eixo B (Spec, Diátaxis & Contratos):** Mapeamento das regras canônicas, redação antecipada da documentação viva em `docs/` e definição prévia da matriz de testes.
4. **Menor Alteração Completa (The Smallest Complete Change):**
   - O melhor plano é aquele que resolve 100% da issue com o menor diff possível, sem inventar camadas, DTOs espelho manuais (Mapper Hell) ou opções que ninguém pediu.
5. **Desenvolvimento Desacoplado em Pares (TDD Inside-Out):**
   - O teste (Red) é concebido estritamente a partir da Spec; o código (Green) é implementado exclusivamente para satisfazer o teste sem *Speculative Generality*.
6. **Documentação é Entregável de Primeira Classe:** Nenhuma feature é concluída sem documentação Diátaxis atômica no mesmo ciclo.

---

## 2. Processo Operacional em 4 Fases

### Fase 1: Triagem, Falsificabilidade da Issue & Grep de Chamadores

1. Obtenha a issue oficial registrada:
   ```bash
   gh issue view <numero> --json title,body
   ```
2. **Gate de Falsificabilidade & Sanity Check Factual (A Issue é Verídica?):**
   - Não confie cegamente nas alegações da issue (*Zero Sycophancy*). Antes de despachar subagentes ou desenhar arquiteturas, confronte as afirmações com o código real:
     - **Existência Factual:** Os arquivos, classes, funções, endpoints e tabelas citados na issue existem no estado atual do branch?
     - **Verificação da Hipótese / Causa Raiz:**
       - *Se for `[Bugfix]`*: O comportamento defeituoso alegado realmente ocorre no código atual? Inspecione os guard clauses e testes existentes. O bug já foi corrigido por outro PR recente? O comportamento relatado não é, na verdade, o comportamento clinicamente esperado pelas regras (`RNxx`)?
       - *Se for `[Feature]` ou `[Refactor]`*: A funcionalidade apontada já não existe implementada total ou parcialmente em outro módulo, service ou sob nomenclatura canônica similar?
       - *Se for `[Security/Compliance/ADR]`*: A alegada violação de ADR (ex.: router não fino, mapper hell, concorrência de fila) é comprovada no código hoje ou as guardas (`tests/architecture`, `tach check`) já protegem?
   - **Fail-Fast por Inveracidade (Short-Circuit):** Se a premissa for refutada (problema inexistente, bug fantasma, código já corrigido ou premissa factual incorreta):
     - **PARADA IMEDIATA:** Não avance para a Fase 2 (não despache subagentes e não gere plano de código fictício).
     - Emita imediatamente ao usuário um **Relatório de Falsificação** detalhado, apontando arquivo e linhas exatas (`caminho/arquivo.py:Lxx-Lyy`) que refutam a premissa da issue, e aguarde orientações.
3. Isole as restrições:
   - Quais critérios estão no **In Scope**?
   - Quais comportamentos estão expressamente proibidos no **Out of Scope**?
   - Quais regras clínicas (`RNxx`), normas CFM/LGPD e User Stories governam a demanda?
4. **Paridade Estrita de Contratos & Zero Speculative Code (Never Code Around Ambiguity):**
   - Identifique nominalmente cada endpoint HTTP/WS e método de serviço solicitado na Issue.
   - **Proibido:** Propor rotas alternativas, aliases defensivos, parâmetros opcionais redundantes ou fallbacks especulativos para acomodar termos divergentes em narrativas. Toda ação tem exatamente 1 contrato canônico. Em caso de discrepância entre título e corpo da issue, liste em `Open Questions` para aprovação do usuário antes de desenhar o plano.
5. **Grep Every Caller (Mapeamento de Regressão Silenciosa):**
   - Se a demanda alterar a assinatura, retorno ou comportamento de qualquer função existente, execute uma busca global no terminal (`grep_search` ou `rg`) para mapear previamente todos os pontos de consumo que precisarão ser ajustados.

---

### Fase 2: Pesquisa em Dois Eixos via Subagentes Paralelos

Dispare dois subagentes concorrentes em modo *read-only* utilizando `invoke_subagent` com `TypeName="research"`:

#### 🅰️ Subagente 1 — Eixo Standards & Arquitetura
Configuração: `TypeName="research"`, `Role="Pesquisa Standards & Arquitetura"`
Prompt do subagente:
- Varrer o repositório para mapear precedentes técnicos:
  - Quais Fakes e test doubles em `tests/doubles.py` já atendem à demanda (`FakeAsyncSession`, `FakeValkey`, etc.)?
  - Quais camadas e regras de importação no `tach.toml` devem ser respeitadas?
  - Como o Composition Root (`composition.py`) do módulo deve orquestrar a injeção de dependências sem expor infraestrutura aos routers?
  - Identificar oportunidades de reuso para evitar duplicação ou wrappers desnecessários.
- Relatório esperado: Precedentes de doubles, portas e dependências do Tach.

#### 🅱️ Subagente 2 — Eixo Spec, Diátaxis & Matriz de Testes
Configuração: `TypeName="research"`, `Role="Pesquisa Spec & Diátaxis"`
Prompt do subagente:
- Mapear a documentação canônica a ser criada ou atualizada em `docs/`:
  - `docs/explanation/domains/<dominio>-domain.md` (regras `RNxx`);
  - `docs/user-stories/US-xx-*.md` (critérios de aceite BDD);
  - `docs/reference/...` (novas chaves, tabelas ou variáveis).
- Desenhar a **Matriz de Testes Red**: listar os cenários exatos de sucesso, erro com valor ofensivo e concorrência/borda que devem ser cobertos.
- Relatório esperado: Esboço Diátaxis e matriz de cenários de teste.

---

### Fase 3: Elaboração do Plano de Implementação (`implementation_plan.md`)

O orquestrador sintetiza os dois relatórios no artefato `implementation_plan.md`:

```markdown
# [Objetivo da Issue / Feature]

Descrição concisa do problema, diagnóstico da causa raiz e solução arquitetural.

## 1. Alinhamento Arquitetural & Menor Alteração Completa
- **Diagnóstico de Veracidade & Causa Raiz:** Evidência factual coletada na Fase 1 comprovando a existência real do problema/necessidade no branch atual.
- A Menor Alteração Completa: o que podemos reutilizar (stdlib, doubles existentes, helpers) em vez de criar código novo?
- Camadas impactadas e garantia de portas/DTOs imutáveis.
- Garantia de routers finos (zero DB, zero commit no router).
- Schemas com `from_attributes = True` (zero mapper hell).
- Test doubles canônicos mapeados em `tests/doubles.py`.
- Resultado do "Grep Every Caller": lista de arquivos chamadores a ajustar.

## 2. Governança de Documentação Diátaxis (Obrigatório)
Listar explicitamente quais arquivos devem ser atualizados/criados:
- [ ] `docs/explanation/domains/<dominio>-domain.md`: Adicionar RN-xx.
- [ ] `docs/user-stories/US-xx-*.md`: Atualizar critérios de aceite.
- [ ] `docs/reference/...`: Atualizar se houver novas variáveis ou erros.

## 3. Matriz de Testes Previstos (Critérios de Aceite Red)
- [ ] `test_<cenario_sucesso>`: Comportamento esperado e commit único.
- [ ] `test_<cenario_erro_ofensivo>`: Lançamento de exceção rica contendo offending value.
- [ ] `test_<cenario_borda_ou_concorrencia>`: Idempotência, locks ou race conditions.

## 4. Fatiamento em Tarefas Atômicas

### 4.1 Fatiamento Backend (TDD Inside-Out Hexagonal)
#### Camada 1: Domínio & Validações Puras (Entidades Ricas & Exceptions)
- **Red:** Escrever `tests/unit/test_<modulo>_models.py` validando invariantes e mensagens com offending value. Executar e comprovar FALHA (Red).
- **Green:** Implementar entidade rica em `domain/models.py` e exceção em `domain/exceptions.py`. Executar `just test-fast` e comprovar SUCESSO (Green).

#### Camada 2: Aplicação, Portas & Fakes (Services & Ports)
- **Red:** Escrever `tests/unit/test_<modulo>_service.py` usando `FakeAsyncSession` e Fakes de `tests/doubles.py`. Comprovar FALHA (Red).
- **Green:** Implementar `application/dtos.py`, `ports/` e `services/` (commit único, docstrings de proveniência 3-5 linhas). Executar `just test-fast` e `just typecheck` e comprovar SUCESSO (Green).

#### Camada 3: Apresentação & Router Fino (Routers & Schemas)
- **Red:** Escrever `tests/unit/test_<modulo>_router.py` cobrindo endpoints HTTP/WS e status codes. Comprovar FALHA (Red).
- **Green:** Implementar `presentation/schemas.py`, `presentation/dependencies.py` e `presentation/routers/`. Executar `just test-fast` e `tests/architecture/test_routers_are_thin.py` e comprovar SUCESSO (Green).

#### Camada 4: Documentação Diátaxis & Quality Gate
- Atualizar arquivos de documentação conforme Seção 2.
- Executar portão unificado: `just check` (ou `just check-fast`).

---

### 4.2 Fatiamento Frontend (Troféu de Testes & Feature-Driven - ADR-011)
#### Fatia 1: Contratos de API & Schemas de Validação (Hey API + Zod)
- **Red:** Escrever testes unitários em Vitest para validações algorítmicas (`validators.ts`) e refinamentos de schemas Zod (`<feature>-schema.ts`). Comprovar FALHA.
- **Green:** Executar `just frontend-generate`. Declarar schema Zod estendendo `@/api/generated/zod.gen`. Executar `just frontend-test` e comprovar SUCESSO.

#### Fatia 2: Lógica Headless & Estado de Servidor (Custom Hooks + MSW v2)
- **Red:** Escrever teste de hook montando QueryClient e handler MSW via factory tipada de `@/api/generated/msw.gen`. Comprovar FALHA.
- **Green:** Implementar Custom Hook headless em `api/` consumindo serviço gerado diretamente (sem barrel import). Executar `just frontend-test` e comprovar SUCESSO. Setup global com `server.resetHandlers()`.

#### Fatia 3: Componente Visual Composto & Formulários (`shadcn/ui` + RHF)
- Implementar componente declarativo em `components/` sem boolean flags de modo (`isEmergency`, `isDoctor`).
- Integrar com `react-hook-form` + `zodResolver`.
- Aplicar padrões React 19 (prop `ref` direta, `use(Context)`). Isolar medidores e timers com `useRef`.

#### Fatia 4: Integração de Telas & Acessibilidade (Vitest + RTL + MSW v2)
- **Red:** Escrever teste de integração em `tests/<feature>.test.tsx` montando a árvore inteira em `jsdom`. Simular digitação e cliques reais com `userEvent.setup()`. Teardown mandatório de fake timers em `afterEach(() => vi.useRealTimers())`.
- **Green:** Conectar componente visual ao hook. Validar estados visíveis e avanço assíncrono com `await vi.advanceTimersByTimeAsync()`. Comprovar SUCESSO.

#### Fatia 5: Jornadas E2E & Acessibilidade Clínica (Playwright + Axe-Core)
- Escrever jornada completa em `e2e/<feature>.spec.ts` usando locators por papel/rótulo (`getByRole`, `getByLabel`).
- Para contagens temporizadas (45s No-Show), instalar `page.clock.install()` **antes de `page.goto()`** e avançar com `await page.clock.fastForward(45_000)`.
- Encerramento explícito de contextos multi-usuário (`await context.close()`).
- Auditoria com `AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()`.

#### Fatia 6: Documentação Diátaxis & Quality Gate
- Atualizar User Story canônica correspondente em `docs/user-stories/US-xx-*.md` com os critérios de tela.
- Executar portão unificado: `just frontend-check` e `just check-fast`.
```

---

## 3. Fase 4: Checkpoint de Aprovação & Transição para Revisão

1. **Parada Obrigatória:** Ao finalizar o `implementation_plan.md`, defina `RequestFeedback: true` no metadata e **AGUARDE** aprovação explícita do usuário antes de criar código.
2. **Execução Fiel ao Plano (Prompt-to-Plan Binding):**
   - Conduza as fatias TDD Inside-Out estritamente conforme o plano aprovado. É terminantemente proibido injetar rotas, aliases, fallbacks ou parâmetros não previstos no plano.
   - **Proporcionalidade Operacional:** Em demandas pontuais ou correções de pequeno/médio porte, o próprio agente orquestrador pode executar as camadas TDD diretamente na sessão (Red $\to$ Green), sem a necessidade de despachar múltiplos subagentes. Caso opte por despachar subagentes executores, utilize `TypeName="self"` (com permissões completas de escrita e comando).
3. **Entrega e Segregação de Funções (Anti-Self-Audit):** Ao concluir o desenvolvimento com `just check` verde e `walkthrough.md` gerado:
   - **Proibido Auto-Auditoria:** O agente de implementação **NÃO DEVE** executar a revisão nesta mesma sessão para evitar viés de confirmação e contaminação de contexto.
   - O agente encerra seu ciclo de trabalho orientando o usuário a abrir uma **nova sessão limpa (zero-context)** para executar a skill [`.agents/skills/medisync-pr-review`](../medisync-pr-review/SKILL.md) de forma independente e imparcial.
