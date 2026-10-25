# Estratégia de Testes (Testing Strategy)

> Filosofia, pirâmide de testes e garantias de isolamento no MediSync Express.

---

## 1. Visão Geral e Filosofia

No MediSync Express, os testes garantem conformidade clínica (CFM 2.314/2022, Portaria 344/98), robustez em alta concorrência médica (ADR-002) e isolamento multi-tenant estrito (RLS no PostgreSQL).

A estratégia de testes adota dois pilares fundamentais:
1. **Pirâmide Segregada Fail-Fast:** A validação rápida deve ocorrer sem I/O e sem infraestrutura de contêineres, falhando em poucos segundos antes de qualquer teste pesado de integração.
2. **Hexagonal Pragmático sem Mapper Hell (ADR-001):** Entidades SQLAlchemy 2.0 são modelos de domínio ricos. Testes unitários validam diretamente o comportamento do domínio sem necessidade de criar DTOs intermediários ou bancos em memória simulados imperfeitamente.

---

## 2. A Pirâmide de Testes MediSync

```
        / \
       /   \
      /  I  \    Testes de Integração (tests/integration/)
     /------- \   - PostgreSQL 17 com RLS ativo
    /    A    \   - Valkey 8.0 (Lua scripts atômicos)
   / ----------\  - MinIO S3 & LiveKit
  /      U      \ Testes Unitários & Arquiteturais (tests/unit/ & tests/architecture/)
 /---------------\ - 100% em memória, zero Docker, paralelos (-n auto)
```

### Camada U: Unitários e Arquitetura (`tests/unit/` & `tests/architecture/`)
* **Execução:** `just test-fast` ou `just test-unit`
* **Dependências Externas:** Zero contêineres Docker, zero rede, zero I/O de disco.
* **Escopo:**
  * Regras de negócio de modelos ricos (transições de status de atendimento, cálculo de score 64-bit, bloqueio de medicamentos Portaria 344/98).
  * Casos de uso e Services com dublês de teste canônicos (`tests/doubles.py` e mocks tipados).
  * Testes de arquitetura AST (`tests/architecture/test_routers_are_thin.py` e `tach check`), garantindo que routers permaneçam finos e camadas modulares sejam respeitadas.

### Camada I: Integração sobre Infraestrutura Real (`tests/integration/`)
* **Execução:** `just test-integration`
* **Dependências:** PostgreSQL (`localhost:5433`), Valkey (`localhost:6380`), MinIO e LiveKit rodando saudáveis.
* **Escopo:**
  * Políticas de segurança Row-Level Security (RLS) e troca de papéis (`SET LOCAL ROLE medisync_app`).
  * Concorrência real de 50 médicos concorrendo por pacientes via Lua scripts atômicos.
  * Tarefas do worker ARQ (expiração de ring timeout em 45s, reconciliação pelo sweeper).
  * Fluxo HTTP ponta a ponta via `AsyncClient` contra a aplicação FastAPI real.

---

## 3. Isolamento de Estado e Ciclo de Vida do Banco

### O Problema do DDL Destrutivo em Execuções Concorrentes
No passado, fixtures tentavam isolar testes executando `DROP SCHEMA public CASCADE;` ou chamadas ad-hoc de `Base.metadata.create_all`. Em execuções paralelas ou consecutivas, isso causava:
* Destruição de tabelas enquanto outros workers estavam rodando (`psycopg.errors.UndefinedTable`).
* Eliminação de roles DCL e grants de RLS necessários para a role `medisync_app`.

### O Padrão Canônico: `TRUNCATE TABLE ... CASCADE`
No MediSync, a infraestrutura de banco de teste é gerenciada canonicamente:
1. **Migrações via Alembic:** O schema é provisionado uma única vez até a revisão head (`just migrate`).
2. **Limpeza Declarativa e Rápida:** As fixtures utilizam `clean_database_tables()` ou `clean_database_and_valkey()`, que executam um único comando `TRUNCATE TABLE ... CASCADE` nas tabelas de domínio, preservando a estrutura de tabelas, índices, triggers de RLS e concessões DCL intactas.
3. **Limpeza de Valkey por Namespace:** Chaves voláteis de teste (`fila:*`, `lock:*`, `plantao:*`, etc.) são limpas via `clean_valkey_keys()` sem afetar outras chaves persistidas.

---

## 4. O Portão de Qualidade `just check`

O comando `just check` implementa a ordem estrita **Fail-Fast** unificada:

```
scan-secrets -> docs-check -> audit-ai-code -> fmt -> lint -> typecheck -> tach -> test-unit -> test-integration
```

1. **`just scan-secrets` (Gitleaks):** Audita o repositório prevenindo vazamento de credenciais e chaves (~1.2s).
2. **`just docs-check` (Python AST/Markdown):** Valida links relativos, referências de símbolos e limites Diátaxis (<1s).
3. **`just audit-ai-code` (Python AST):** Audita teto de aninhamento ($\le 2$), exceções com offending values e proveniência (~1s).
4. **`just fmt` (Ruff):** Valida e formata o estilo do código em <1s.
5. **`just lint` (Ruff):** Detecta problemas estáticos e aplica correções seguras em <1s.
6. **`just typecheck` (Basedpyright):** Validação estrita de tipos (`typeCheckingMode = "strict"` em `src/` e `tests/`).
7. **`just tach` (Tach):** Validação estrita de fronteiras modulares hexagonais.
8. **`just test-unit` (Pytest + Cov):** 611 testes unitários e de arquitetura com checagem de cobertura (mínimo de 85%).
9. **`just test-integration` (Pytest):** Testes ponta a ponta sobre contêineres reais (Postgres, Valkey, LiveKit, MinIO).

> **Dica de DX:** Em desenvolvimento ativo sem Docker local, utilize `just check-fast`, que executa as etapas 1 a 7 e roda `test-fast` (100% em memória, zero Docker) em ~15 segundos.

---

## 5. Estratégia de Testes do Frontend (ADR-011)

No frontend SPA/PWA ([ADR-011](../../adrs/ADR-011-Arquitetura-Frontend-SPA-PWA-e-Estrategia-de-Testes.md)), a suíte adota o **Troféu de Testes** (Testing Trophy) para priorizar testes de integração de tela sobre testes unitários frágeis de componentes:

```
        / \
       / E \     E2E & A11y (Playwright + @axe-core/playwright)
      /-----\    - Jornadas clínicas reais, multi-contexto (Médico + Paciente) e WCAG 2.1 AA
     /   I   \   Integração de Componentes (Vitest + Testing Library + MSW v2)
    /---------\  - Telas completas montadas em jsdom com simulação HTTP declarativa
   /     U     \ Unitários Puros (Vitest)
  /-------------\ - Algoritmos de CPF/CNS, validadores locais e schemas Zod
 /       S       \ Análise Estática (TypeScript strict + ESLint)
/-----------------\ - Contratos tipados e schemas gerados via Hey API (@hey-api/openapi-ts)
```

### 5.1 Camada de Integração de Telas & Unitários (Vitest + MSW v2)

* **Fidelidade Comportamental**: Proibido mockar componentes React ou hooks de negócio. O teste monta a árvore visual real em ambiente `jsdom` e simula a rede na camada de transporte via **Mock Service Worker (MSW v2)**, utilizando factories tipadas de `@/api/generated/msw.gen`.
* **Interações Reais do Usuário**: Utilização exclusiva de `@testing-library/user-event` (`userEvent.setup()`) para simular digitação e cliques reais.
* **Fake Timers**: Contagens regressivas de tela (como cooldown de 60s para reenvio de OTP) utilizam `vi.useFakeTimers()` e `vi.advanceTimersByTime()` para avanço determinístico sem lentidão.
* **Unitários Puros**: Reservados para funções matemáticas e algoritmos de validação (algoritmo módulo 11 de CPF, CNS brasileiro, máscaras e cálculos de tempo).

### 5.2 Camada E2E, Colaboração e Acessibilidade (Playwright)

* **Locators Acessíveis (User-Facing)**: Seleção de elementos estritamente por papéis semânticos e rótulos (`page.getByRole()`, `page.getByLabel()`), eliminando seletores CSS quebradiços.
* **Asserções Web-First com Auto-Retry**: Proibição de `page.waitForTimeout()` ou `sleep()`. Toda sincronização baseia-se em asserções reativas do Playwright (`await expect(locator).toBeVisible()`).
* **Avanço Determinístico de Relógio (`page.clock`)**: Para eventos clínicos temporizados — como o timeout de 45 segundos de No-Show na convocação médica ([US-07](../../user-stories/US-07-alocacao-chamada-medica.md) e [US-08](../../user-stories/US-08-atendimento-chamada-no-show.md)) —, o teste utiliza `page.clock.install()` e `page.clock.fastForward(45_000)` para testar a expiração e o status ausente instantaneamente.
* **Colaboração Multi-Contexto**: Testes de interação entre médico e paciente em tempo real utilizam múltiplos contextos isolados de navegador (`browser.newContext()`) com sessões pré-autenticadas via `storageState`.
* **Auditoria de Acessibilidade Clínica (WCAG 2.1 AA)**: Validação automatizada com `@axe-core/playwright` e verificação de desativação de transições de lista sob `@media (prefers-reduced-motion: reduce)`.

Para detalhes operacionais e exemplos de código, consulte o catálogo canônico em [Frontend Testing Patterns](../../reference/testing/frontend-testing-patterns.md).

