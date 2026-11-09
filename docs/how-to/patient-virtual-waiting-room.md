# Como Operar e Testar a Sala de Espera Virtual do Paciente

> Guia passo a passo da jornada do paciente na sala de espera virtual, acompanhamento de posição em tempo real, ring modal de 45s e salvaguardas clínicas.

## Contexto

A sala de espera virtual (`frontend/src/features/queue/`) é o ponto focal da experiência do paciente após o acolhimento e a triagem clínica (ADR-011 / RF-03 / RF-06). Ela substitui o modelo estático de atualização por uma arquitetura híbrida de baixa latência: conexão WebSocket para eventos de avanço de fila (`/ws/queue/{atendimento_id}`) combinada com polling gracioso de contingência (5s) via TanStack Query.

O componente orquestrador (`VirtualWaitingRoom`) encapsula quatro salvaguardas essenciais:
1. **Acompanhamento Transparente:** Exibição da posição ordinal atual e estimativa de espera calculada pelo TMA dos médicos ativos.
2. **Salvaguarda de Piora Clínica (RF-06):** Botão acessível que permite relatar agravamento dos sintomas; se classificado em Nível 1 (Vermelho), aciona imediatamente a salvaguarda SAMU 192 (`SamuEmergencyModal`).
3. **Convocação Médica e Ring Modal de 45s (RN02):** Ao ser convocado pelo médico, exibe modal fullscreen com alerta sonoro Web Audio API (chime 523Hz/659Hz) e contagem regressiva determinística de 45 segundos para ingresso na teleconsulta WebRTC.
4. **Resolução de No-Show:** Se os 45 segundos expirarem sem confirmação, transiciona deterministicamente para o estado `PACIENTE_AUSENTE` sem travamento da aplicação.

## Procedimento

### 1. Inicialização e Restauração de Sessão
Para que o paciente acesse a sala de espera, a sessão ativa deve conter `atendimentoId`, `token` e `pacienteId`. A rota canônica `/fila` (`frontend/src/routes/fila.tsx`) valida a sessão através de Route Guard declarativo (`beforeLoad`) e renderiza a sala de espera:

```bash
# Conferir rota /fila e validação de sessão
rg -n "getStoredSession|VirtualWaitingRoom|filaRoute" frontend/src/routes/fila.tsx
```

### 2. Acompanhamento em Tempo Real via WebSocket
A conexão WebSocket é gerenciada pelo hook `useQueueSocket`. O hook executa reconexão com backoff exponencial (1s a 30s) e silencia ruídos de polling:

```bash
# Conferir conexão ao canal WebSocket do atendimento
rg -n "new WebSocket|/ws/queue/" frontend/src/features/queue/api/use-queue-socket.ts
```

### 3. Comunicação de Deterioração Clínica (RF-06)
Quando o paciente relata piora através do `PioraClinicaModal`, a mutação `useComunicarPiora` envia o payload ao backend (`POST /api/v1/fila/piora`):
- Se `alerta_samu_disparado: true` ou `nova_prioridade: 1`: o estado local ativa o `SamuEmergencyModal`, oferecendo discagem rápida `tel:192` e bloqueando ações virtuais.
- Se `nova_prioridade: 2` (Laranja): a posição na fila é recalculada e atualizada na tela imediatamente.

### 4. Atendimento da Chamada e Ingresso na Teleconsulta (RF-03)
Ao receber o evento `CALLED` ou `CHAMANDO_PACIENTE`:
1. O `IncomingCallRingModal` abre em tela cheia com chime sonoro contínuo a cada 2,5 segundos.
2. O paciente clica em *"Entrar na Teleconsulta"*, disparando a mutação `useAtenderChamada` (`POST /api/v1/consultations/{id}/livekit/token`).
3. O token LiveKit emitido é repassado ao callback `onAtendimentoIniciado`, iniciando a sessão de vídeo.

### 5. Detecção Silenciosa de Biometria Passkey (US-14)
Enquanto aguarda na fila, o paciente pode visualizar o `PasskeyInvitationCard` caso `window.PublicKeyCredential` esteja disponível no navegador. A dispensa do card é armazenada em `sessionStorage`, respeitando o caráter opcional e não-bloqueante.

## Onde no código

- Orquestrador da tela: `frontend/src/features/queue/components/virtual-waiting-room.tsx:VirtualWaitingRoom`
- Card de posição e TMA: `frontend/src/features/queue/components/queue-position-card.tsx:QueuePositionCard`
- Ring modal de 45s: `frontend/src/features/queue/components/incoming-call-ring-modal.tsx:IncomingCallRingModal`
- Alerta sonoro sintetizado: `frontend/src/features/queue/lib/audio-chime.ts:iniciarToqueChamadaMedica`
- Modal de piora clínica: `frontend/src/features/queue/components/piora-clinica-modal.tsx:PioraClinicaModal`
- Diálogo de desistência (RN06): `frontend/src/features/queue/components/cancelar-fila-dialog.tsx:CancelarFilaDialog`
- Card de convite Passkey: `frontend/src/features/queue/components/passkey-invitation-card.tsx:PasskeyInvitationCard`
- Salvaguarda SAMU compartilhada: `frontend/src/features/onboarding/components/samu-emergency-modal.tsx:SamuEmergencyModal`
- Formatação e estimativas: `frontend/src/lib/formatters.ts:formatarPosicaoOrdinal`
- Hook de WebSocket: `frontend/src/features/queue/api/use-queue-socket.ts:useQueueSocket`
- Hook de posição REST: `frontend/src/features/queue/api/use-posicao-fila.ts:usePosicaoFila`
- Hook de teleconsulta: `frontend/src/features/queue/api/use-atender-chamada.ts:useAtenderChamada`

## Verificação

Execute os testes de unidade e integração de tela da fila virtual:

```bash
pnpm --dir frontend test src/features/queue/
```

Valide a orquestração de rotas declarativas e transição no `App.test.tsx`:

```bash
pnpm --dir frontend test src/App.test.tsx
```

Execute a auditoria de acessibilidade e diretrizes de frontend:

```bash
just audit-frontend
just frontend-check
```

## Ver também

- [ADR-011: Frontend Feature-Driven Headless](../adrs/ADR-011-Arquitetura-Frontend-SPA-PWA-e-Estrategia-de-Testes.md)
- [Domínio de Fila e ZSET](../explanation/domains/queue-domain.md)
- [US-07: Alocação Atômica de Chamada Médica](../user-stories/US-07-alocacao-chamada-medica.md)
- [US-08: Atendimento de Chamada e No-Show](../user-stories/US-08-atendimento-chamada-no-show.md)
- [US-06: Deterioração Clínica e Escape SAMU 192](../user-stories/US-06-deterioracao-clinica-escape-samu.md)
- [US-14: Biometria Passkeys / WebAuthn](../user-stories/US-14-biometria-passkeys-webauthn.md)
