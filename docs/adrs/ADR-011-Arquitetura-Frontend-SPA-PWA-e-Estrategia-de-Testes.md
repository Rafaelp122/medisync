# [ADR-011] Arquitetura de Frontend SPA/PWA e Estratégia de Testes

| Metadado | Detalhe |
| :--- | :--- |
| **Status** | Aprovado |
| **Data** | 2026-10-25 |
| **Decisores** | Time de Arquitetura & Engenharia |
| **Referência** | [ADR-001](ADR-001-Hexagonal-Pragmatico-Modelos-Ricos-Protocols-e-Tach.md), [ADR-005](ADR-005-Desacoplamento-de-Midia-LiveKit-SFU.md), [ADR-008](ADR-008-Padronizacao-de-DTOs-e-Eliminacao-de-Mapper-Hell-na-Apresentacao.md), [Overview de Arquitetura](../explanation/architecture/overview.md), [Estratégia de Testes](../explanation/architecture/testing-strategy.md) |

---

## 1. Contexto e Declaração do Problema

Com a conclusão e estabilização de todos os bounded contexts clínicos do backend (admissão, triagem ACR, fila virtual, convocação médica atômica, teleconsulta LiveKit e prontuário PEP SOAP), o **MediSync Express** necessita de uma interface de usuário moderna, acessível e resiliente para duas personas críticas:
1. **O Paciente (Juliana Silva)**: Operando em dispositivos móveis (3G/4G, PWA), exigindo acolhimento rápido, transparência sobre a fila virtual, login sem senhas (OTP) e salvaguarda imediata em caso de emergência (SAMU 192).
2. **O Médico Plantonista (Dr. Eduardo Rocha)**: Operando em desktop/web clínica, exigindo visão unificada em tela única (Single-Pane Clinical Dashboard) com videoconferência WebRTC de baixa latência, prontuário estruturado SOAP e prescrição eletrônica.

Historicamente, o desenvolvimento de frontends em sistemas de saúde sofre com três armadilhas clássicas:
* **Mapper Hell e Dessincronização de Tipos**: Redigitação manual de DTOs e interfaces no frontend, gerando quebras silenciosas de contrato quando o backend evolui.
* **Complexidade Acoplada e Re-renders**: Telas sobrecarregadas com dezenas de propriedades booleanas (`isEmergency`, `isDoctor`, `isQueue`), gerando renderizações desnecessárias que travam feeds de áudio/vídeo WebRTC.
* **Testes Frágeis e Ilusórios**: Testes unitários focados em detalhes de implementação de componentes que quebram com qualquer alteração de CSS, mas não garantem que a jornada assistencial funcione.

---

## 2. Drivers de Decisão

* **Bala Traçante (*Tracer Bullet*)**: Fatiamento vertical por jornada assistencial ponta a ponta, evitando a construção de camadas horizontais isoladas sem validação real.
* **Contratos Tipados Automáticos (Zero DTO Duplication)**: Consumo direto da especificação OpenAPI 3.1 gerada pelo FastAPI via tooling oficialmente alinhado.
* **Segregação Estrita entre Dados e Visual**: Adoção do padrão Container/Presenter via *Custom Hooks* (Headless), isolando chamadas de rede e WebSockets de componentes de apresentação puros.
* **Performance e Acessibilidade Clínica (WCAG 2.1 AA)**: Respeito estrito a `prefers-reduced-motion`, contraste mínimo de 4.5:1 e carregamento dinâmico (*lazy loading*) de pacotes pesados de mídia (LiveKit).
* **Troféu de Testes Confiável**: Testes orientados ao comportamento observável do usuário com Vitest, React Testing Library, MSW e Playwright.

---

## 3. Opções Consideradas

### Opção 1: Next.js App Router (RSC + SSR)
* *Prós*: Suporte integrado a Server Components e renderização no servidor.
* *Contras*: Introduz um segundo servidor Node.js em produção, duplicando custos operacionais de infraestrutura onde o backend FastAPI já centraliza regras de negócio, autorização e RLS.

### Opção 2: Vite SPA/PWA com Axios Manual e Tipos Redigitados
* *Prós*: Configuração simples e tradicional.
* *Contras*: Reintroduz o *Mapper Hell* no frontend; exige manutenção manual de centenas de interfaces TypeScript, violando o princípio de Menor Alteração Completa e YAGNI.

### Opção 3: Vite SPA/PWA + React 19 + Hey API + TanStack Query + Zod + Troféu de Testes (Adotada)
* *Prós*: 
  - Cliente OpenAPI gerado automaticamente pelo **Hey API (`@hey-api/openapi-ts`)**, patrocinado oficialmente pelo criador do FastAPI.
  - Estado de servidor e revalidação de fila gerenciados via **TanStack React Query**.
  - Formulários e validação em tempo de execução via **React Hook Form + Zod**.
  - Design system acessível e composicional com **Tailwind CSS + `shadcn/ui`**.
  - Testes sem fragilidade via **Vitest + React Testing Library + MSW + Playwright**.
* *Contras*: Exige disciplina na execução do script de geração de contratos OpenAPI antes de builds locais.

---

## 4. Decisão

Adotamos a **Opção 3: Arquitetura de Frontend SPA/PWA com React 19, Hey API e Troféu de Testes**.

### 4.1 Pilha Tecnológica Base
* **Runtime & Bundler**: Node.js v24+, `pnpm`, Vite e React 19 (modo SPA com suporte a Service Worker / PWA).
* **Design System & Estilos**: Tailwind CSS com tokens semânticos clínicos (`globals.css`) e primitivas acessíveis do `shadcn/ui` (Radix UI).
* **Contratos de API, Schemas e Mocks**: `@hey-api/openapi-ts` configurado com 4 plugins oficiais:
  1. `@hey-api/client-fetch`: cliente HTTP nativo ultraleve baseado no `fetch` do navegador e tipos TypeScript estritos (`types.gen.ts`).
  2. `@tanstack/react-query`: geração de hooks de query e mutation tipados para cada endpoint.
  3. `zod`: conversão automática dos schemas Pydantic/OpenAPI em schemas Zod (`zod.gen.ts`), eliminando 100% da duplicação manual de validações de formulário.
  4. `msw`: geração automática de factories de mock tipadas para MSW v2 (`msw.gen.ts`), garantindo que testes de tela quebrem em tempo de compilação se a API mudar.
* **Estado de Servidor & Cache**: `@tanstack/react-query` para polling inteligente da fila virtual, mutações e invalidação atômica de cache.
* **Formulários e Validações**: `react-hook-form` acoplado aos schemas Zod gerados via `@hookform/resolvers/zod`, utilizando `.refine()` e `.extend()` apenas para máscaras locais e algoritmos brasileiros de CPF/CNS e telefone celular.

### 4.2 Padrões de Composição e Clean Code (Skills Vercel)
1. **Zero Boolean Props em Componentes Complexos**: Proibida a proliferação de flags booleanas para alternar comportamentos visuais; adotar componentes compostos (*Compound Components*) e variantes explícitas (`<SamuEmergencyModal />` em vez de `<Modal isSamu={true} />`).
2. **Desacoplamento Headless & Convenções React 19**: A lógica de chamada de rede, reconexão WebSocket e tratamento RFC 7807 reside exclusivamente em *Custom Hooks* (`useQueuePosition`, `useLiveKitRoom`). Os componentes visuais são funções puras que recebem props primitivas. Proibido `forwardRef` (usar prop `ref` convencional do React 19) e consumo de contexto com `use(Context)`.
3. **Proibição de Barrel Imports no Hey API**: Importar diretamente dos arquivos folha (`@/api/generated/services.gen`, `@/api/generated/types.gen`, `@/api/generated/zod.gen`, `@/api/generated/msw.gen`) para evitar inchaço no bundle e degradação do HMR no Vite.
4. **Blindagem contra Re-renders Críticos (WebRTC e Fila)**: Valores transientes de alta frequência (medidores de volume WebRTC, timers de contagem regressiva) devem residir em `useRef` ou componentes folha isolados, sem provocar re-render na árvore inteira. Utilizar `startTransition` para atualizações de baixa prioridade (ex.: filtros de busca na fila médica).
5. **Lazy-Loading de Mídia (LiveKit SDK)**: O SDK do LiveKit (`livekit-client`, `@livekit/components-react`) e visualizadores de PDF devem ser carregados dinamicamente via `React.lazy()`, impedindo o inchaço do bundle inicial do paciente.
6. **View Transitions SPA e Acessibilidade**: Transições visuais comunicam continuidade espacial em Vite SPA via `document.startViewTransition`. Polling e revalidações em segundo plano (TanStack Query a cada 5s) nunca disparam animações de transição (`default="none"`). Respeito estrito a `@media (prefers-reduced-motion: reduce)`, desativando animações e zerando durações via CSS para pacientes sensíveis.

### 4.3 Estratégia de Testes (O Troféu de Testes)
* **Estático**: `tsc --noEmit` em modo estrito (`strict: true`) e ESLint sobre os contratos gerados pelo Hey API.
* **Unitário (Vitest)**: Exclusivo para funções puras de negócio (cálculo de score clínico, validação algorítmica de CPF/CNS, sanitização e refinamentos de schemas Zod).
* **Integração de Componentes (Vitest + React Testing Library + MSW v2)**: Renderização de telas completas em ambiente `jsdom` com simulação de rede na camada HTTP via Mock Service Worker (MSW v2) usando factories tipadas de `@/api/generated/msw.gen`. Proibido mockar componentes ou hooks internos. Contagens regressivas locais utilizam `vi.useFakeTimers()` e `await vi.advanceTimersByTimeAsync()`, com teardown obrigatório em `afterEach(() => vi.useRealTimers())` e `afterEach(() => server.resetHandlers())`.
* **End-to-End & Colaboração (Playwright)**: Jornadas assistenciais completas no Chromium/Firefox com locators acessíveis (`getByRole`, `getByLabel`) e asserções web-first sem `sleep()` arbitrário. O timeout de 45 segundos de No-Show ([US-07](../user-stories/US-07-alocacao-chamada-medica.md)/[US-08](../user-stories/US-08-atendimento-chamada-no-show.md)) é testado determinística e instantaneamente via `page.clock.install()` invocado **obrigatoriamente antes de `page.goto()`**, avançando com `await page.clock.fastForward(45_000)`. A colaboração em tempo real médico-paciente utiliza múltiplos contextos isolados de navegador (`browser.newContext()`) com encerramento explícito (`await context.close()`).
* **Acessibilidade Clínica Automatizada (WCAG 2.1 AA)**: Auditoria contínua com `@axe-core/playwright` configurado com tags canônicas `['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']` e validação de supressão de animações para pacientes sensíveis sob `@media (prefers-reduced-motion: reduce)`.
* **Padrões Canônicos**: Detalhados em [Frontend Testing Patterns](../reference/testing/frontend-testing-patterns.md).

---

## 5. Consequências e Trade-offs

### Positivas:
* **Zero Mapper Hell no Frontend**: Alterações no backend FastAPI refletem imediatamente nos tipos TypeScript do frontend com um único comando (`pnpm generate:api`).
* **Confiabilidade Assistencial Máxima**: Validação de entrada imediata no browser (Zod) reduz requisições inválidas ao backend e melhora a experiência de pacientes com dor.
* **Isolamento de Testes**: Fim dos testes frágeis de componentes mockados internamente; o MSW garante que o frontend se comporte exatamente como em produção.

### Negativas / Custos de Mitigação:
* **Dependência do OpenAPI**: O frontend precisa do `/openapi.json` gerado pelo backend para atualizar os clientes. Mitigado através da exportação estática do OpenAPI em disco durante o pipeline de CI (`just dump-openapi`).
