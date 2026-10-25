# MediSync Express — Guia do Desenvolvedor de IA (AGENTS.md)

Este documento contém as instruções mandatórias para qualquer agente de IA ou desenvolvedor atuando neste repositório.

---

## 1. Comandos e Tooling

* **Gerenciador de Pacotes:** `uv` (Backend Python) e `pnpm` (Frontend TypeScript). Nunca use `pip install` ou `npm install` globais.
* **Automação:** Sempre utilize os comandos do `justfile`:
  * **Backend & Geral:**
    * `just install` — Sincroniza ambiente e dependências com `uv` (`uv sync`).
    * `just setup-dev` — Inicializa o ambiente de desenvolvimento completo (infra Docker, deps, migrações e validação rápida).
    * `just check` — Executa o portão de qualidade completo e unificado com Fail-Fast estrito (scan-secrets, docs-check, audit-ai-code, fmt, lint, typecheck, tach, test-unit, test-integration).
    * `just check-fast` — Executa a validação rápida completa em memória (zero Docker: scan-secrets, docs-check, audit-ai-code, fmt, lint, typecheck, tach, test-fast).
    * `just fmt` — Formata o código com `ruff`.
    * `just lint` — Executa lint com autofix seguro (`ruff check . --fix`).
    * `just typecheck` — Executa checagem estrita de tipos com `basedpyright`.
    * `just tach` — Valida as fronteiras modulares com `tach check`.
    * `just test-fast` — Executa testes rápidos em paralelo (100% em memória, zero Docker: `pytest tests/unit tests/architecture -n auto --no-cov`).
    * `just test-unit` — Executa testes unitários com cobertura (`pytest tests/unit tests/architecture --cov=src`).
    * `just test-integration` — Executa testes de integração sobre infraestrutura real (`pytest tests/integration`).
    * `just test` — Executa a suíte de testes completa com cobertura consolidada.
    * `just docs-check` — Valida links `src/docs`, referências relativas e proíbe código colado nos docs.
    * `just audit-ai-code` — Audita o código sob os princípios de Clean Code para Agentes de IA.
    * `just scaffold-module <nome>` — Cria esqueleto físico hexagonal para novo módulo e registra no `tach.toml`.
    * `just scan-secrets` — Audita o repositório com Gitleaks (ADR-010) para prevenir vazamento de credenciais.
    * `just bump-check` — Simula o próximo bump de versão semântica e changelog via Commitizen.
  * **Frontend (ADR-011):**
    * `just frontend-install` — Instala dependências do frontend com `pnpm`.
    * `just frontend-dev` — Inicia servidor de desenvolvimento Vite (`http://localhost:5173`).
    * `just frontend-generate` — Gera contratos tipados TypeScript via Hey API (`@hey-api/openapi-ts`) a partir do `/openapi.json`.
    * `just frontend-check` — Executa checagem estrita de tipos (`tsc --noEmit`), lint (`eslint`) e testes (`vitest run`).
    * `just frontend-test` — Executa a suíte de testes de tela e unitários do frontend (`vitest`).
    * `just frontend-test-e2e` — Executa testes ponta a ponta com Playwright.

---

## 2. Princípios Arquiteturais Pétreos (ADR-001 / ADR-011)

### 2.1 Backend: Hexagonal Pragmático & Domain-Driven Design (ADR-001 / ADR-008 / ADR-009)

1. **Hexagonal Pragmático sem Mapper Hell (ADR-001 / ADR-008):**
   * Entidades persistidas com SQLAlchemy 2.0 (`Mapped[...]`) são **modelos ricos** e residem no domínio do próprio módulo.
   * Encapsulam regras clínicas, validações e transições de estado.
   * **Proibido:** Criar DTOs espelho duplicados com conversores manuais (`to_domain`/`to_orm` ou `dto_to_schema`/`schema_to_dto`).
   * **Entradas (Requests):** Se os dados vêm 100% do corpo JSON, utilize o schema Pydantic (`frozen=True`) diretamente como entrada do Service. Use `@dataclass(frozen=True)` com sufixo `Command` em `application/dtos.py` apenas quando for necessário agregar dados de múltiplas origens (Path Params, Headers de Tenant, IP, etc.).
   * **Saídas (Responses):** Schemas de resposta devem usar `model_config = ConfigDict(from_attributes=True)` e conversão via `ResponseSchema.model_validate(objeto)`. Proibido mapeamento manual campo a campo.
   * **Organização Física:** Schemas Pydantic residem exclusivamente em `src/modules/<modulo>/presentation/schemas.py`. Commands/DTOs residem em `src/modules/<modulo>/application/dtos.py`.
2. **Comunicação Inter-Módulos:**
   * Os módulos em `src/modules/*` são independentes e fechados.
   * Comunicação síncrona ocorre exclusivamente via portas abstratas (`typing.Protocol` do PEP 544) e DTOs imutáveis (`@dataclass(frozen=True)` ou Pydantic v2).
   * **Proibido:** Importar modelos internos, tabelas ou repositórios de outro módulo.
   * Toda violação modular é bloqueada pelo `tach check`.
3. **Tipagem Estrita:**
   * O código deve passar em `basedpyright` com `typeCheckingMode = "strict"`.
   * Evite `Any`. Use tipos genéricos, `Union`, `Literal` ou `Protocol`.
4. **Transação + Router fino (ADR-001 §6-§7):**
   * Service commita, um por caso de uso (`await session.commit()` no fim do método público que persiste; helpers/policies nunca commitam).
   * Router nunca importa `sqlalchemy`/`infrastructure`/`domain.models`, nunca chama `.commit()/.refresh()/text()/select()`, nunca instancia `*Service(` (usa `*Dep` da `composition.py`).
   * `HTTPException` só em `presentation/dependencies.py` (ex.: `exigir_rate_limit` → 429); routers importam de lá. Erros de domínio via `src/core/errors.py` (`NotFoundError`, `ForbiddenError`, …).
   * Guardas: `tach check` (Stage B camadas + composition) + `tests/architecture/test_routers_are_thin.py` (AST) devem passar.
5. **Composition Root Enxuto e Agregação de Rotas (ADR-001 §7.1 / Issue #68):**
   * `src/main.py` é composition root enxuto: proibido importar `modules/*/infrastructure` (guard AST `tests/architecture/test_main_composition_root.py`).
   * Cada módulo agrega suas rotas em `src/modules/<modulo>/presentation/routers/__init__.py` exportando `http_router` (e `ws_router`). `main.py` inclui apenas 1 router HTTP por módulo sob `/api/v1`.
   * Endpoint de saúde `/healthz` reside em `src/core/health_router.py` sob o guard de routers finos e versão via `Settings.APP_VERSION`.
   * Ciclo de vida (`lifespan`) delega inicializações para hooks assíncronos nos composition roots dos módulos (ex: `queue.composition.on_startup`).
6. **Configurações Desacopladas por Perfil (ADR-009):**
   * Services e domínio nunca importam `get_settings()` ou `src.core.config`.
   * Dependências de ambiente são resolvidas exclusivamente nas composition roots (`composition.py`) e injetadas como tipos primitivos ou ports no service (guard AST `tests/architecture/test_services_and_composition.py`).

### 2.2 Frontend: Feature-Driven SPA/PWA, Zero DTO Duplication & Troféu de Testes (ADR-011)

1. **Organização Física Feature-Driven (Slices Verticais):**
   * O código do frontend reside em `frontend/src/features/<feature>/` (ex.: `onboarding`, `queue`, `consultation`), organizado internamente em:
     - `api/`: Custom hooks de rede baseados em TanStack Query (`use<Feature>Query`, `use<Feature>Mutation`).
     - `components/`: Componentes visuais puros e compostos da feature.
     - `schemas/`: Schemas Zod de validação de formulários (`<feature>-schema.ts`).
     - `tests/`: Testes de integração de tela (`<feature>.test.tsx`) com Vitest + RTL + MSW.
   * Primitivas agnósticas de design system residem em `frontend/src/components/ui/` (`shadcn/ui` / Radix).
   * **Proibido:** Criar pastas horizontais genéricas com componentes de features distintas misturados.
2. **Zero DTO Duplication & Proibição de Barrel Imports (Hey API):**
   * Tipos de requisição e resposta do backend derivam 100% de `@/api/generated`, gerados automaticamente pelo Hey API (`@hey-api/openapi-ts` + `@hey-api/client-fetch`).
   * Schemas Zod derivam de `@/api/generated/zod.gen`. Proibido recriar schemas Zod manuais do zero; estenda os gerados com `.extend()` e `.refine()`.
   * Factories de mock tipadas para testes derivam de `@/api/generated/msw.gen`.
   * **Proibido Barrel Imports:** Importe diretamente dos arquivos gerados (`@/api/generated/services.gen`, `@/api/generated/types.gen`, etc.) para prevenir inchaço no bundle e lentidão de HMR no Vite. Proibido redigitar ou criar interfaces manuais que espelhem schemas Pydantic do backend.
3. **Desacoplamento Headless & Padrões React 19:**
   * Componentes visuais nunca realizam chamadas HTTP nem abrem WebSockets diretamente.
   * Toda lógica de rede, polling e tratamento RFC 7807 reside em Custom Hooks (`useVirtualQueue`, `useLiveKitRoom`). Os componentes visuais recebem apenas dados primitivos e callbacks.
   * **Convenções React 19:** Proibido o uso de `forwardRef` (passe `ref` como prop comum: `function Input({ ref, ...props })`). Leitura de contextos deve utilizar `use(Context)` em vez de `useContext()`.
4. **Componentes Compostos sobre Boolean Props:**
   * **Proibido:** Criar props booleanas para alternar modos ou visões (`isDoctor`, `isEmergency`, `isQueue`, `showActions`).
   * Adotar Componentes Compostos declarativos (`Compound Components`) e variantes explícitas (`<SamuEmergencyModal />` em vez de `<Modal isSamu={true} />`).
5. **Mitigação de Re-renders Críticos (WebRTC e Fila):**
   * Valores transientes ou de alta frequência (medidores de volume WebRTC, timers de contagem regressiva) devem residir em `useRef` ou componentes folha isolados, sem provocar re-render na árvore inteira.
   * Utilizar `startTransition` para atualizações de baixa prioridade (ex.: filtros e buscas na fila virtual do médico).
6. **Validação Estrita de Entrada em Runtime (Zod + React Hook Form):**
   * Nenhum formulário é enviado sem validação prévia via schema Zod derivado de `@/api/generated/zod.gen` com mensagens em português.
   * Validação algorítmica de CPF, CNS e telefone celular em `frontend/src/lib/validators.ts`.
7. **Lazy-Loading de Mídia e Visualizadores:**
   * SDKs pesados (`livekit-client`, `@livekit/components-react`, visualizadores PDF) devem ser importados dinamicamente via `React.lazy()`.
8. **View Transitions Clínicas e Acessibilidade Obrigatória (WCAG 2.1 AA):**
   * Transições visuais comunicam continuidade espacial em Vite SPA via `document.startViewTransition`.
   * **Silenciamento em Polling:** Polling e revalidações em segundo plano (TanStack Query a cada 5s) nunca disparam animações de transição (`default="none"`).
   * Respeito estrito a `@media (prefers-reduced-motion: reduce)`, desativando transições de lista para pacientes sensíveis e zerando durações via CSS.
   * Contraste mínimo de 4.5:1 para textos e rótulos de gravidade clínica.
9. **Troféu de Testes do Frontend (Fidelidade sobre Fragilidade):**
   * **Unitário (Vitest):** Funções puras, algoritmos de CPF/CNS, refinamentos de schemas Zod e cálculos de datas.
   * **Integração de Telas (Vitest + React Testing Library + MSW v2):** Renderização de telas completas em ambiente `jsdom` com simulação de rede na camada HTTP via factories tipadas de `@/api/generated/msw.gen`. Interações com `@testing-library/user-event` (`userEvent.setup()`). Teardown mandatório de fake timers em `afterEach(() => vi.useRealTimers())` e avanço com `await vi.advanceTimersByTimeAsync()`. Setup global do MSW com `afterEach(() => server.resetHandlers())`. **Proibido:** Mockar componentes internos do React ou hooks de tela; teste o comportamento visível pelo usuário.
   * **E2E e Colaboração (Playwright):** Jornadas clínicas completas no Chromium/Firefox com locators acessíveis (`getByRole`, `getByLabel`, `getByText`) e asserções web-first com auto-retry. **Proibido:** `page.waitForTimeout()` ou `sleep()` arbitrários. Para eventos temporizados (45s de No-Show na US-07/US-08), `page.clock.install()` deve ser chamado **obrigatoriamente antes de `page.goto()`**, avançando com `await page.clock.fastForward(45_000)`. Testes colaborativos multi-contexto (médico + paciente) encerram instâncias explicitamente com `await context.close()`.
   * **Acessibilidade Clínica Automatizada (WCAG 2.1 AA):** Auditoria contínua de conformidade com `@axe-core/playwright` utilizando tags explícitas `['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']` e validação de desativação de animações sob `@media (prefers-reduced-motion: reduce)`.

### 2.3 Diretrizes Transversais de Clean Code para Agentes de IA

1. **Governança de Documentação Diátaxis (Padrão Atômico-Denso):**
   * Toda nova feature, regra de negócio ou endpoint deve atualizar a documentação no mesmo PR: 1 conceito por arquivo (80–250 linhas), template obrigatório de 5 seções, zero código colado >5 linhas (usar `path:símbolo` + `rg`).
   * Novo `.env` $\to$ atualizar `docs/reference/environment/variables.md`; novo erro $\to$ `docs/reference/api/error-envelope.md`.
2. **Nomes Únicos e 'Greppáveis' (<5 matches no `rg`):** Símbolos públicos (classes, métodos de serviço, hooks, ports, exceptions) devem ter nomes distintivos e rastreáveis. Proibido nomes genéricos como `data`, `handler`, `Manager`, `process()`, `execute()`.
3. **Exceções com Contexto do Valor Ofensivo (*Offending Value + Expected Shape*):** Exceções de domínio e validações devem sempre interpolar o valor recebido e o valor esperado (ex.: `raise StatusInvalidoError(f"Status '{status}' inválido; esperados: {sorted(StatusAtendimento)}")`), viabilizando diagnóstico instantâneo no traceback.
4. **Early Returns e Aninhamento Raso (Max 2 níveis):** Guard clauses imediatas no topo de funções e métodos. Proibido aninhamento profundo (`if/else` encadeados dentro de loops). Limite máximo de 2 níveis de estruturas de controle por função.
5. **Docstrings Atômicas de Proveniência (WHY, not WHAT):** Docstrings atômicas de 3 a 5 linhas em métodos públicos de services e modelos clínicos com regras de negócio, referenciando explicitamente a regra canônica (`RN01-RN07`, `RF-01-RF-10`, `ADR-xxx`, normas CFM/LGPD) e o link do documento em `docs/`. Código aponta para doc (`Regras: docs/...`), doc aponta para código (`Impl: src/...:simbolo`).
6. **Fakes Nomeados sobre Mocks Inline Anônimos:** Testes de backend utilizam Fakes em memória tipados (`MemoryTokenRevocation`, `MemoryQueuePort`). Testes de frontend utilizam handlers tipados do MSW. Proibido mocks anônimos inline (`MagicMock()`, `patch()`).
7. **Menor Alteração Completa & YAGNI Radical (The Smallest Complete Change):** O melhor código é aquele que não precisa ser escrito. Resolva o problema por completo com a menor quantidade de código novo legível. Antes de criar código, siga a escada de decisão: (1) Precisa existir? (2) Já existe no codebase (helper, fake, port)? Reutilize; (3) A biblioteca padrão ou linguagem já faz? Use-a; (4) Uma dependência já instalada resolve? Use-a sem adicionar novos pacotes; (5) Só então escreva novo código.
8. **Zero Speculative Code (Never Code Around Ambiguity):** Proibido criar código defensivo, opções não solicitadas, fallbacks especulativos ou rotas/componentes alternativos para acomodar ambiguidades. Toda ação possui exatamente 1 contrato canônico RESTful/WS e visual.
9. **Grep Every Caller (Proteção contra Regressão Silenciosa):** Antes de alterar a assinatura, retorno ou comportamento de qualquer função, hook, DTO ou modelo, execute obrigatoriamente uma busca global (`grep_search`) por todos os chamadores no repositório e ajuste-os no mesmo ciclo.

---

## 3. Catálogo de Skills do Projeto

Consulte e utilize as skills especializadas localizadas em `.agents/skills/`:
* [`.agents/skills/medisync-issue-creator`](.agents/skills/medisync-issue-creator/SKILL.md): Formalização de necessidades e gestão de escopo em dois eixos ortogonais (Diagnóstico & Impacto vs YAGNI & Guardrails) via subagentes paralelos. Transforma ideias, bugs e débitos em issues canônicas blindadas contra scope creep antes do planejamento.
* [`.agents/skills/medisync-issue-planner`](.agents/skills/medisync-issue-planner/SKILL.md): Planejamento técnico com gate de falsificabilidade prévia, pesquisa em dois eixos (Standards & Arquitetura vs Spec & Diátaxis), fatiamento TDD Inside-Out e aplicação da Menor Alteração Completa.
* [`.agents/skills/medisync-pr-review`](.agents/skills/medisync-pr-review/SKILL.md): Revisão hostil independente do PR/diff em sessão limpa (Zero-Context / Segregação de Funções) em dois eixos (Standards vs Spec) com inventário mecânico de rotas via shell e achados concretos em 4 partes.
* [`.agents/skills/medisync-module-audit`](.agents/skills/medisync-module-audit/SKILL.md): Auditoria cirúrgica e aprofundada de um módulo hexagonal (bounded context) em repouso: integridade clínica, routers finos, conformidade Diátaxis/ADRs, concorrência e oportunidades de deleção lean.
* [`.agents/skills/fastapi`](.agents/skills/fastapi/SKILL.md): Boas práticas com FastAPI, injeção de dependências, routers e Pydantic v2.
* [`.agents/skills/sqlalchemy-alembic-expert-best-practices-code-review`](.agents/skills/sqlalchemy-alembic-expert-best-practices-code-review/SKILL.md): Padrões de queries assíncronas no SQLAlchemy 2.0, migrations idempotentes e modelagem relacional.
* [`.agents/skills/valkey`](.agents/skills/valkey/SKILL.md): Comandos atômicos, Sorted Sets (ZSET), scripts Lua e caching de alta performance.
* [`.agents/skills/codebase-design`](.agents/skills/codebase-design/SKILL.md): Design de módulos profundos, interfaces coesas e encapsulamento.
* [`.agents/skills/vercel-composition-patterns`](.agents/skills/vercel-composition-patterns/SKILL.md): Padrões de composição React, eliminação de boolean props, interfaces de contexto e React 19.
* [`.agents/skills/vercel-react-best-practices`](.agents/skills/vercel-react-best-practices/SKILL.md): Otimização de performance, eliminação de waterfalls, lazy loading de LiveKit e redução de bundle.
* [`.agents/skills/vercel-react-view-transitions`](.agents/skills/vercel-react-view-transitions/SKILL.md): Animações com propósito assistencial e respeito estrito a `prefers-reduced-motion` (WCAG 2.1 AA).
* [`.agents/skills/vitest`](.agents/skills/vitest/SKILL.md): Testes unitários rápidos e de integração de componentes com Vitest, `jsdom`, Fake Timers e simulação de rede via MSW v2.
* [`.agents/skills/playwright-best-practices`](.agents/skills/playwright-best-practices/SKILL.md): Testes ponta a ponta (E2E), locators acessíveis baseados em papéis (`getByRole`), avanço determinístico de tempo com `page.clock` (45s No-Show), testes colaborativos multi-contexto (médico + paciente) e auditoria de acessibilidade WCAG 2.1 AA (`@axe-core/playwright`).

---

## 4. Definição de Pronto (DoD)

Antes de finalizar qualquer tarefa ou abrir PR:
- [ ] O código adere aos padrões do Hexagonal Pragmático (Backend) ou Feature-Driven Headless (Frontend - ADR-011).
- [ ] No frontend, tipos derivam 100% de `@/api/generated` (zero DTOs manuais) e formulários possuem validação Zod.
- [ ] Novos testes foram adicionados (unitários com fakes/MSW, integração ou E2E).
- [ ] Exceções levantadas contêm o valor ofensivo e a restrição esperada.
- [ ] Aninhamento de controle de fluxo respeita o teto de 2 níveis.
- [ ] Docstrings de regras de negócio contêm links atômicos de proveniência para `docs/`.
- [ ] Documentação correspondente atualizada sob o padrão Diátaxis (sem código colado >5 linhas).
- [ ] Portões de qualidade automatizados foram executados e passaram com código de retorno 0 (`just check` / `just check-fast`).
