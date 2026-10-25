# Padrões de Teste de Frontend (Vitest & Playwright)

> Catálogo de padrões, dublês e regras de asserção para testes unitários, integração de componentes e jornadas E2E no frontend.

## Contexto

O frontend do MediSync Express opera sob duas personas com requisitos de alta criticidade: o paciente em dispositivo móvel (PWA) e o médico em dashboard clínico desktop com teleconsulta WebRTC ([ADR-011](../../adrs/ADR-011-Arquitetura-Frontend-SPA-PWA-e-Estrategia-de-Testes.md)).
Para evitar as armadilhas de testes frágeis acoplados a detalhes de implementação (como seletores CSS instáveis ou estado interno do React) e assegurar conformidade clínica (CFM nº 2.314/2022 e WCAG 2.1 AA), a suíte adota o **Troféu de Testes**:
1. Análise estática com TypeScript em modo estrito.
2. Testes unitários de funções puras com Vitest.
3. Testes de integração de componentes com Vitest, React Testing Library e MSW v2.
4. Testes ponta a ponta (E2E), colaboração em tempo real e acessibilidade com Playwright e Axe-Core.

## Conceito

A estratégia de testes do frontend é estruturada em três pilares fundamentais derivados das boas práticas de engenharia:

### 1. Testes de Integração de Telas (Vitest + MSW v2)

* **Ambiente de Execução**: `jsdom` para emulação completa de APIs de navegador necessárias ao React 19 e Radix UI.
* **Simulação de Rede Declarativa**: Proibido mockar bibliotecas HTTP (`fetch`) ou hooks do React (`useQuery`, `useMutation`). A simulação de rede ocorre no nível de transporte com Mock Service Worker (MSW v2), utilizando handlers e factories tipadas derivadas de `@/api/generated/msw.gen`.
* **Ciclo de Vida do MSW**: Setup global com `beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))`, `afterEach(() => server.resetHandlers())` para evitar contaminação entre testes, e `afterAll(() => server.close())`.
* **Interação de Usuário**: Uso de `@testing-library/user-event` configurado via `userEvent.setup()` para disparar eventos completos de teclado e ponteiro.
* **Controle de Tempo Local com Fake Timers**: Para contagens regressivas de tela (ex.: cooldown de 60 segundos para reenvio de SMS OTP), utilizar `vi.useFakeTimers()` e `await vi.advanceTimersByTimeAsync(60_000)` para avanço assíncrono determinístico que descarrega microtasks e re-renders no React 19. Teardown obrigatório com `afterEach(() => vi.useRealTimers())`.
* **Asserções de Comportamento**: Foco no comportamento observável pelo usuário (mensagens de erro em português, loading states acessíveis, botões desabilitados durante mutação).

### 2. Testes E2E com Playwright

* **Locators Baseados em Acessibilidade (User-Facing)**:
  - Preferência estrita: `page.getByRole()`, `page.getByLabel()`, `page.getByText()`.
  - Proibido: Seletores CSS frágeis (`.card > div:nth-child(2)`) ou `data-testid` quando existir um papel semântico ou rótulo acessível.
* **Asserções Web-First com Auto-Retry**:
  - Uso exclusivo de asserções assíncronas: `await expect(page.getByRole('alert')).toBeVisible()`.
  - **Proibição Absoluta**: `page.waitForTimeout()` ou chamadas a `sleep()`, que introduzem lentidão e intermitência (*flakiness*) no CI.
* **Avanço Determinístico de Relógio (`page.clock`)**:
  - Para eventos sensíveis ao tempo (timeout de 45 segundos de No-Show na convocação médica da [US-07](../../user-stories/US-07-alocacao-chamada-medica.md) e [US-08](../../user-stories/US-08-atendimento-chamada-no-show.md)), o relógio virtual deve ser instalado **obrigatoriamente antes da navegação**: `await page.clock.install()` seguido de `await page.goto('/fila')`. O tempo é avançado instantaneamente via `await page.clock.fastForward(45_000)`, validando a expiração e o status ausente.
* **Colaboração Multi-Contexto (Médico + Paciente)**:
  - Para fluxos simultâneos em tempo real (médico chamando paciente da fila virtual via WebSocket), instanciar contextos de navegador isolados (`const medicoCtx = await browser.newContext({ storageState: '.auth/medico.json' })`).
  - **Cleanup Mandatório**: Todos os contextos manuais devem ser encerrados explicitamente em bloco `finally`: `await medicoCtx.close(); await pacienteCtx.close()`.
* **Sessão Pré-Autenticada (`storageState`)**:
  - Armazenar tokens de autenticação em disco (`.auth/medico.json`, `.auth/paciente.json`) e reutilizá-los em fixtures de teste, evitando a repetição do fluxo completo de OTP em cada caso de teste.

### 3. Acessibilidade Clínica Automatizada (WCAG 2.1 AA)

* **Auditoria Contínua com Axe-Core**: Execução de `await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()` em todas as telas principais para assegurar conformidade com WCAG 2.1 AA (contraste mínimo de 4.5:1, rótulos ARIA, hierarquia de cabeçalhos e navegação por teclado sem falsos positivos experimentais).
* **Sensibilidade ao Movimento**: Validação de suporte a `@media (prefers-reduced-motion: reduce)` via `await page.emulateMedia({ reducedMotion: 'reduce' })`, garantindo que transições visuais sejam suprimidas e zeradas via CSS para pacientes em acolhimento ou triagem.

## Onde no código

* Decisão arquitetural e stack: [ADR-011](../../adrs/ADR-011-Arquitetura-Frontend-SPA-PWA-e-Estrategia-de-Testes.md).
* Pirâmide e troféu de testes: [testing-strategy.md](../../explanation/architecture/testing-strategy.md).
* Tutorial de implementação com testes: [frontend-first-feature.md](../../tutorials/frontend-first-feature.md).
* Configuração do Vitest: `frontend/vitest.config.ts`.
* Configuração do Playwright: `frontend/playwright.config.ts`.
* Servidor MSW de teste: `frontend/src/mocks/server.ts`.
* Testes de integração de telas: `frontend/src/features/<feature>/tests/`.
* Testes E2E de jornadas clínicas: `frontend/e2e/`.

## Verificação

Execução dos testes locais via `justfile`:

```bash
# Executa testes unitários e de integração de componentes com Vitest
just frontend-test

# Executa checagem de tipos estrita (tsc), lint e testes
just frontend-check

# Executa testes ponta a ponta e auditoria de acessibilidade com Playwright
just frontend-test-e2e
```

## Ver também

* [ADR-011: Arquitetura de Frontend SPA/PWA e Estratégia de Testes](../../adrs/ADR-011-Arquitetura-Frontend-SPA-PWA-e-Estrategia-de-Testes.md)
* [Estratégia de Testes](../../explanation/architecture/testing-strategy.md)
* [Tutorial: Frontend First Feature](../../tutorials/frontend-first-feature.md)
* [Fixtures e Dublês de Backend](fixtures-and-factories.md)
