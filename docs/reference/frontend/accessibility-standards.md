# Padrões de Acessibilidade Clínica (WCAG 2.1 AA & Ergonomia Mobile)

> Especificação canônica de acessibilidade visual, ergonomia móvel e conformidade WCAG 2.1 AA no MediSync Express.

## Contexto

O MediSync Express atende pacientes em situação de vulnerabilidade clínica e médicos em teleconsulta de alta demanda.
Para assegurar usabilidade sem barreiras em conformidade com a Portaria GM/MS nº 1.348/2022, normas do CFM e o padrão internacional WCAG 2.1 AA ([ADR-011](../../adrs/ADR-011-Arquitetura-Frontend-SPA-PWA-e-Estrategia-de-Testes.md)), a interface deve garantir legibilidade de gravidade sob luz solar, alvos de toque operáveis por pacientes com dor aguda ou tremor motor, preservação de safe areas em dispositivos móveis modernos e eliminação de armadilhas de teclado (*keyboard traps*).

## Conceito

A governança de acessibilidade clínica é estruturada em quatro pilares mandatórios:

### 1. Contraste de Cores em Badges Clínicos (WCAG 1.4.3 - Mínimo 4.5:1)

Os crachás de classificação de risco do Protocolo de Manchester / ACR e estados do sistema devem apresentar contraste cromático mínimo de 4.5:1 contra seus respectivos fundos:
* **Vermelho (Emergência / Nível 1):** Fundo vermelho com texto branco puro (`bg-red-700 text-white`). Contraste aferido: ~6.38:1.
* **Laranja (Muito Urgente / Nível 2):** Fundo laranja profundo com texto branco puro (`bg-orange-700 text-white`). Contraste aferido: ~5.20:1.
* **Amarelo (Urgente / Nível 3):** Fundo amarelo com texto amarelo escuro em negrito (`bg-yellow-400 text-yellow-950 font-bold`). Contraste aferido: ~10.0:1.
* **Verde (Pouco Urgente / Nível 4 / Success):** Fundo esmeralda profundo com texto branco puro (`bg-emerald-700 text-white`). Contraste aferido: ~5.50:1.
* **Azul (Não Urgente / Nível 5):** Fundo azul vibrante com texto branco puro (`bg-blue-600 text-white`). Contraste aferido: ~5.18:1.
* **Aviso Geral (Warning):** Fundo âmbar com texto âmbar escuro em negrito (`bg-amber-400 text-amber-950 font-bold`). Contraste aferido: ~8.88:1.

### 2. Ergonomia Móvel & Alvos de Toque (WCAG 2.5.5 / 2.5.8 - Mínimo 44x44px)

Dispositivos móveis (smartphones SUS com largura a partir de 360px) exigem alvos de toque mínimos de 44x44px para prevenir acionamentos acidentais por pacientes em crise álgica:
* **Escala Visual Analógica de Dor (EVA 0–10):** Layout responsivo `grid-cols-6 sm:grid-cols-11` com botões configurados em `min-w-[44px] min-h-[44px]` e espaçamento de 1.5 (`gap-1.5`).
* **Navegação por Teclado:** Suporte contínuo às setas direcionais (`ArrowLeft`, `ArrowRight`, `ArrowDown`, `ArrowUp`, `Home`, `End`) gerenciado pelo Radix UI ToggleGroup.

### 3. Safe Area Inset em Modais e Diálogos Clínicos

Diálogos e gavetas operando em navegadores móveis e PWAs (iOS Safari e Android WebView) devem compensar o recorte físico de tela e a barra de navegação gestual do sistema operacional:
* O contêiner de diálogo (`DialogContent`) implementa padding inferior dinâmico: `pb-[max(1.5rem,calc(1.5rem+env(safe-area-inset-bottom,0px)))]`.
* Limitação de altura com rolagem interna: `max-h-[calc(100dvh-2rem)] overflow-y-auto`.

### 4. Eliminação de Keyboard Traps e Gestão de Foco (WCAG 2.1.2)

Modais críticos de alerta clínico não podem aprisionar o foco do teclado de forma perpétua:
* **Modal de Emergência SAMU 192 (`SamuEmergencyModal`):** O fechamento via tecla `Escape` dispara o evento de cancelamento ou saída voluntária sem travar o teclado.
* **Modal de Chamada Recebida (`IncomingCallRingModal`):** Fornece botão de rejeição/fechamento acessível com `aria-label="Recusar chamada médica"` e dismiss via `Escape`.
* **Restauração de Foco:** O fechamento de qualquer modal preserva a árvore do componente invocador na fila virtual, restaurando o foco no elemento de disparo original.

### 5. Alertas Sonoros Sintetizados Multimodais (WCAG 1.4.2 / RN04)

Como canal complementar à notificação visual para pacientes com baixa visão, idosos ou atenção dividida:
* **Alerta SAMU 192 (`reproduzirSireneSamu`):** Oscilação bifrequencial de onda senoidal de 880Hz e 440Hz via Web Audio API, operando sem dependências de arquivos de mídia externos ou buffers pesados.
* **Toque de Chamada Médica (`iniciarToqueChamadaMedica`):** Chime suave em acordes C5/E5 (523Hz e 659Hz) repetido a cada 2.5s durante a janela de ring de 45 segundos, silenciado instantaneamente ao atender, recusar ou pressionar Escape.

## Onde no código

* Impl: `frontend/src/components/ui/badge.tsx:badgeVariants`
* Impl: `frontend/src/components/ui/dialog.tsx:DialogContent`
* Impl: `frontend/src/features/onboarding/components/pain-scale-selector.tsx:PainScaleSelector`
* Impl: `frontend/src/components/samu-emergency-modal.tsx:SamuEmergencyModal`
* Impl: `frontend/src/features/queue/components/incoming-call-ring-modal.tsx:IncomingCallRingModal`
* Impl: `frontend/src/features/queue/lib/audio-chime.ts:iniciarToqueChamadaMedica`
* Spec: `docs/user-stories/US-01-acolhimento-triagem-tcle.md`
* Prova viva: `frontend/src/components/ui/badge.test.tsx`
* Prova viva: `frontend/src/components/ui/dialog.test.tsx`
* Prova viva: `frontend/src/features/onboarding/tests/pain-scale-selector.test.tsx`
* Prova viva: `frontend/src/features/onboarding/tests/samu-emergency-modal.test.tsx`
* Prova viva: `frontend/src/features/queue/tests/incoming-call-ring-modal.test.tsx`
* Ver: `rg -n "min-w-\[44px\]" frontend/src/`
* Ver: `rg -n "safe-area-inset-bottom" frontend/src/`

## Verificação

Execução da suíte de acessibilidade e testes de componentes visuais:

```bash
# Executa testes unitários de contraste, safe areas e touch targets
pnpm --dir frontend test src/components/ui/badge.test.tsx src/components/ui/dialog.test.tsx src/features/onboarding/tests/pain-scale-selector.test.tsx

# Executa testes de teclado e foco nos modais clínicos
pnpm --dir frontend test src/features/onboarding/tests/samu-emergency-modal.test.tsx src/features/queue/tests/incoming-call-ring-modal.test.tsx
```

## Ver também

* [ADR-011: Arquitetura Frontend SPA/PWA e Estratégia de Testes](../../adrs/ADR-011-Arquitetura-Frontend-SPA-PWA-e-Estrategia-de-Testes.md)
* [Frontend Testing Patterns](../testing/frontend-testing-patterns.md)
* [Component Guidelines](component-guidelines.md)
