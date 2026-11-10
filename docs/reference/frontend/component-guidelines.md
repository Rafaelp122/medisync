# Diretrizes de Componentes Frontend (Decomposição & Performance)

> Especificação canônica para arquitetura de componentes React 19, decomposição de monólitos, memoização WebRTC e governança de complexidade.

## Contexto

À medida que fluxos clínicos crescem em complexidade (ex.: evolução SOAP integrada a videoconferência, prescrição médica em tempo real e painéis operacionais de gestão), componentes visuais tendem a se transformar em monólitos de 400 a 700 linhas.
Esses monólitos acumulam múltiplos estados, causam lentidão de renderização (re-renders da mídia WebRTC durante digitação do prontuário) e dificultam testes unitários pontuais.
Sob a [ADR-011](../../adrs/ADR-011-Arquitetura-Frontend-SPA-PWA-e-Estrategia-de-Testes.md), o MediSync Express estabelece regras estritas de composição, decomposição e limite de complexidade.

## Conceito

A governança arquitetural de componentes adota as seguintes diretrizes:

### 1. Limiar de Complexidade e Alerta (>300 Linhas)

Arquivos de componentes em `frontend/src` devem buscar concisão e foco assistencial único:
* **Alerta em 300 Linhas:** O linter estático `scripts/audit_frontend_guidelines.py` emite avisos (*warnings*) para componentes `.tsx` que excedam 300 linhas de código, sinalizando a oportunidade de decomposição em *compound components*.
* **Política Não Bloqueante:** A regra atua como ferramenta educativa e preventiva sem interromper o pipeline de CI (código de saída 0), permitindo transição gradual para formulários extensos legados.

### 2. Decomposição em Componentes Compostos (Compound Components)

Em vez de concentrar múltiplos subprocessos em uma única função React, monólitos devem ser fatiados em submódulos coesos compartilhando o mesmo bounded context:
* **PrescriptionBuilder:** Decomposto em orquestrador enxuto e submódulos dedicados:
  - `PrescriptionForm`: Seleção de medicamentos, posologia e duração.
  - `AtestadoForm`: Campos de afastamento, CID-10 e emissão de declarações.
  - `PrescriptionItemsList`: Tabela de itens acumulados com remoção e resumo.
* **PainelGestor:** Decomposto em orquestrador de telemetria e cartões de visualização:
  - `PainelHeader`: Cabeçalho institucional e seletor de consórcio/período.
  - `AcrTriageDistributionGrid`: Grid de cartões de distribuição de gravidade SUS (Nível 1 a Nível 5).
  - `TaxasOperacionaisCard`: Métricas de TMA, No-Show e evasão.
  - `MedicosTmaCard`: Monitoramento individual de produtividade médica.

### 3. Isolamento de Mídia WebRTC com `React.memo`

A renderização de fluxos de vídeo WebRTC consome buffers de decodificação de hardware e conexões SFU com o servidor LiveKit.
* Mudanças de estado de alta frequência no componente pai (digitação no editor SOAP, inclusão de medicamentos na prescrição ou polling de telemetria da fila a cada 5s) não podem provocar re-renders no canvas de vídeo.
* O contêiner de videoconferência é encapsulado em `WorkstationMediaPane` memoizado com `React.memo`, re-renderizando estritamente quando `atendimentoId`, `livekitToken` ou participantes mudarem.

### 4. Padrões React 19 e Eliminação de Boolean Props

* **Proibição de Boolean Props de Modo:** Proibido utilizar props como `isDoctor`, `isEmergency`, `isQueue`. O código deve empregar variantes explícitas e composição declarativa.
* **Ref como Prop Comum:** Não utilizar `forwardRef`; passar `ref` diretamente como prop funcional.
* **Leitura de Contextos:** Utilizar a API `use(Context)` do React 19 em vez de `useContext()`.

### 5. Silenciamento de View Transitions em Revalidações de Background (ADR-011 §2.8)

Em aplicações clínicas com polling contínuo (ex.: TanStack Query refetch a cada 5s na sala de espera ou no painel de telemetria):
* **Silenciamento Estrito (`default="none"`):** Transições visuais (`document.startViewTransition`) só devem ser disparadas por intenção explícita do usuário (mudança de rota ou ação de clique). Polling em segundo plano nunca deve disparar animações de transição, prevenindo flicker visual e sobrecarga de CPU/GPU.
* **Respeito a `prefers-reduced-motion`:** Usuários com sensibilidade vestibular têm todas as durações de transição zeradas automaticamente via Tailwind `motion-reduce:transition-none`.

### 6. Governança de Tokens Semânticos Clínicos SUS (Proibição de Raw Palette)

Em conformidade com a Portaria GM/MS nº 2.048/2002 e a WCAG 2.1 AA ([ADR-011](../../adrs/ADR-011-Arquitetura-Frontend-SPA-PWA-e-Estrategia-de-Testes.md)):
* **Proibição de Classes Hardcoded:** É expressamente proibido o uso de classes de cores brutas da paleta Tailwind (ex.: `bg-red-700`, `bg-orange-700`, `bg-yellow-400`, `bg-emerald-700`, `bg-blue-600`, `border-red-500`, `text-yellow-950`) para expressar níveis de risco clínico, estados de triagem ou escalas de dor.
* **Uso Obrigatório de Tokens Semânticos:**
  - Componentes de crachá de risco devem utilizar exclusivamente `<Badge variant="nivel1" | "nivel2" | "nivel3" | "nivel4" | "nivel5">`.
  - Componentes de contêiner ou seletores específicos (`AcrTriageDistributionGrid`, `PainScaleSelector`) devem compor estilos utilizando os tokens de tema `bg-acr-*`, `text-acr-*-foreground`, `border-acr-*` e `ring-acr-*`.
* **Zero Discrepância em Dark Mode:** Badges e cartões clínicos delegam a adaptação luminosa e a conformidade de contraste estritamente às variáveis CSS de tema (`frontend/src/globals.css`), sendo proibidos overrides manuais ad-hoc (ex.: `dark:bg-red-900`).

## Onde no código

* Impl: `scripts/audit_frontend_guidelines.py:audit_component_line_length`
* Impl: `frontend/src/components/ui/badge.tsx:badgeVariants`
* Impl: `frontend/src/features/consultation/components/workstation-media-pane.tsx:WorkstationMediaPane`
* Impl: `frontend/src/features/consultation/components/prescription-builder.tsx:PrescriptionBuilder`
* Impl: `frontend/src/features/telemetry/components/painel-gestor.tsx:PainelGestor`
* Prova viva: `tests/unit/test_audit_frontend_guidelines.py`
* Prova viva: `frontend/src/components/ui/badge.test.tsx`
* Prova viva: `frontend/src/features/consultation/tests/doctor-workstation-performance.test.tsx`
* Prova viva: `frontend/src/features/consultation/tests/prescription-builder.test.tsx`
* Prova viva: `frontend/src/features/telemetry/tests/painel-gestor.test.tsx`
* Ver: `rg -n "audit_component_line_length" scripts/`
* Ver: `rg -n "React\.memo" frontend/src/features/consultation/`

## Verificação

Execução da verificação de arquitetura e linters de frontend:

```bash
# Executa a auditoria de diretrizes e limite de 300 linhas
just audit-frontend

# Executa testes de performance e memoização da workstation
pnpm --dir frontend test src/features/consultation/tests/doctor-workstation-performance.test.tsx

# Executa testes unitários do linter de frontend
uv run pytest tests/unit/test_audit_frontend_guidelines.py -v
```

## Ver também

* [ADR-011: Arquitetura Frontend SPA/PWA e Estratégia de Testes](../../adrs/ADR-011-Arquitetura-Frontend-SPA-PWA-e-Estrategia-de-Testes.md)
* [Accessibility Standards](accessibility-standards.md)
* [Frontend Testing Patterns](../testing/frontend-testing-patterns.md)
