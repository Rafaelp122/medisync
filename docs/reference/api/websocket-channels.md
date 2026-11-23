# WebSocket Channels

> Canais de sinalização em tempo real via Valkey Pub/Sub e WebSockets FastAPI; contrato vive em `src/core/realtime.py`.

## Contexto

Acompanhamento da fila de atendimento e recebimento de chamadas médicas exigem notificações push sub-500ms, eliminando polling HTTP.
A comunicação é unidirecional de eventos do servidor para os clientes (paciente e médico), utilizando canais dedicados no Valkey Pub/Sub.
A validação de credenciais ocorre na fase pré-accept do handshake WebSocket, abortando conexões espúrias com códigos 4401 e 4403 sem consumir buffers persistentes no servidor.
A sinalização orquestra as transições de estado clínico até a conexão na sala de videoconferência do LiveKit.

## Conceito

### Endpoints e Mapeamento de Rotas

O sistema expõe rotas de streaming em tempo real mapeadas para canais Pub/Sub correspondentes:

| Endpoint WebSocket | Canal Valkey | Destinatário | Propósito |
|---|---|---|---|
| `/ws/queue/{atendimento_id}` | `medisync:pubsub:queue:{atendimento_id}` | Paciente | Atualizações de fila (`QUEUE_POSITION_UPDATE`) e notificação de chamada iniciada (`CALLED`) |
| `/ws/doctor/{medico_id}` | `medisync:pubsub:doctor:{medico_id}` | Médico | Registro de presença em `plantao:medicos_ativos` e disparo/cancelamento de chamada (`INCOMING_CALL`, `CALL_CANCELLED`) |

### Handshake e Autenticação Pré-Accept

O cliente estabelece a conexão informando a credencial na query string `?token=<credencial>`.
A validação ocorre antes de `websocket.accept()` (`validar_ws_queue_token` e `validar_ws_doctor_token`):

1. **Token Provisório de Acolhimento (HMAC-SHA256, 2 partes):** Emitido durante a triagem inicial do paciente. Permite acesso exclusivo ao atendimento correspondente.
2. **Token JWT de Acesso (3 partes):** Emitido no login de usuário cadastrado.
   - Paciente: papel `PACIENTE` com checagem de posse Anti-IDOR (`PatientQueueOwnershipChecker`) vinculando `paciente_id` ao `atendimento_id`.
   - Médico: papel `MEDICO` onde `usuario_id` deve coincidir estritamente com `medico_id` da rota (sem bypass administrativo horizontal).
3. **Códigos de Rejeição WS:**
   - `4401`: Token ausente, assinatura inválida, formato corrompido ou token revogado.
   - `4403`: Papel não autorizado ou paciente sem posse sobre o atendimento.

### Catálogo de Tipos de Mensagem

Os eventos clínicos e de controle trafegam em formato JSON serializado via `ValkeyQueueEngine` (`publicar_evento_fila` / `publicar_evento_medico`) e `stream_channel`:

| Tipo de Mensagem (`event` / `type`) | Origem | Destino | Gatilho / Descrição |
|---|---|---|---|
| `CONNECTED` | WebSocket (`stream_channel`) | Paciente | Payload inicial imediato após handshake de `/ws/queue/{atendimento_id}` |
| `READY` | WebSocket (`stream_channel`) | Médico | Payload inicial de `/ws/doctor/{medico_id}` após `presence.registrar_medico_ativo(medico_id)` |
| `CALLED` | `AlocacaoChamadaService` $\to$ Pub/Sub | Paciente | Médico alocou o atendimento; envia `medico_id`, `status`, `ttl_segundos` (45s) e `chamada_iniciada_em` |
| `INCOMING_CALL` | `AlocacaoChamadaService` $\to$ Pub/Sub | Médico | Disparo de modal na estação médica com `atendimento_id`, `ttl_segundos` e `chamada_iniciada_em` |
| `CALL_CANCELLED` | `FilaService` $\to$ Pub/Sub | Médico | Paciente recusou/cancelou via `POST /api/v1/fila/cancelar/{id}` ou sofreu piora SAMU durante `CHAMANDO_PACIENTE`; desbloqueia a estação |
| `QUEUE_POSITION_UPDATE` | Valkey Pub/Sub | Paciente | Recálculo de prioridade ordinal na fila ZSET (`medisync:pubsub:queue:{atendimento_id}`) |
| `{"type": "ping"}` | Servidor (`_heartbeat_worker`) | Ambos | Batimento enviado a cada 25s para manter túneis NAT e balanceadores vivos |

### Envelope JSON de Sinalização

Contrato mínimo do evento em tempo real (spec, 5 linhas):

```json
{"event": "CALLED", "atendimento_id": "uuid", "medico_id": "uuid", "status": "CHAMANDO_PACIENTE", "ttl_segundos": 45}
```

Campos obrigatórios e opcionais do envelope:

| Campo | Tipo | Presença | Descrição |
|---|---|---|---|
| `event` | `string` | Obrigatório (eventos de domínio) | Discriminador (`CONNECTED`, `READY`, `CALLED`, `INCOMING_CALL`, `CALL_CANCELLED`, `QUEUE_POSITION_UPDATE`) |
| `timestamp` / `chamada_iniciada_em` | `string (ISO-8601)` | Contextual | Carimbo UTC de geração ou início da chamada |
| `atendimento_id` | `string (UUID)` | Contextual | Identificador único do atendimento vinculado |
| `medico_id` | `string (UUID)` | Contextual | Identificador do profissional alocado |
| `status` | `string` | Contextual | Estado resultante do atendimento (`CHAMANDO_PACIENTE`, `CANCELADO_PACIENTE`) |
| `motivo` | `string \| null` | Opcional | Motivo em `CALL_CANCELLED` (ex.: recusa do paciente ou `ENCAMINHADO_SAMU_PIORA_CLINICA`) |
| `posicao` | `integer` | Opcional | Posição ordinal calculada na fila de espera |
| `ttl_segundos` | `integer` | Opcional | Janela temporal limite para resposta (ex.: 45s no ring) |

## Onde no código

- Impl: `src/modules/queue/application/realtime_channels.py:channel_queue_patient`
- Impl: `src/modules/consultation/application/realtime_channels.py:channel_doctor_calls`
- Spec: `src/modules/queue/application/ports/queue_engine_port.py:QueueEnginePort`
- Impl: `src/modules/queue/infrastructure/valkey_queue_engine.py:ValkeyQueueEngine`
- Impl: `src/modules/queue/application/services/alocacao_service.py:AlocacaoChamadaService._publicar_eventos_chamada`
- Impl: `src/modules/queue/application/services/fila_service.py:FilaService._notificar_cancelamento_chamada_medico`
- Impl: `src/core/realtime.py:stream_channel`
- Impl: `src/core/realtime.py:forward_pubsub_to_websocket`
- Impl: `src/core/realtime.py:publish_realtime_event`
- Impl: `src/modules/queue/presentation/routers/queue_ws_router.py:ws_queue_patient`
- Impl: `src/modules/queue/presentation/dependencies.py:validar_ws_queue_token`
- Impl: `src/modules/consultation/presentation/routers/doctor_ws_router.py:ws_doctor_calls`
- Impl: `src/modules/consultation/presentation/dependencies.py:validar_ws_doctor_token`
- Spec: `docs/adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md`
- Prova viva: `tests/integration/test_websocket_endpoints.py:test_ws_queue_patient_receives_updates_sub_500ms`
- Prova viva: `tests/integration/test_websocket_endpoints.py:test_ws_doctor_receives_incoming_call_modal_trigger`
- Prova viva: `tests/integration/test_websocket_endpoints.py:test_ws_clean_disconnect_without_memory_leaks`
- Ver: `rg -n "stream_channel" src/core/realtime.py`
- Ver: `rg -n "ws_queue_patient" src/modules/queue/presentation/routers/queue_ws_router.py`
- Ver: `rg -n "validar_ws_queue_token" src/modules/queue/presentation/dependencies.py`

## Verificação

```bash
uv run pytest tests/integration/test_websocket_endpoints.py tests/integration/test_arq_worker.py
```

## Ver também

- [Error envelope](error-envelope.md)
- [Environment variables](../environment/variables.md)
- [ARQ background tasks](../worker/arq-tasks.md)
- [Documentation standards](../architecture-standards/documentation-standards.md)
- [ADR-002: Alocação Atômica Valkey Lua](../../adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md)
- [Queue domain](../../explanation/domains/queue-domain.md)
- [Security and authorization](../../explanation/architecture/security-and-authorization.md)
