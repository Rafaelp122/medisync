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
| `/ws/queue/{atendimento_id}` | `medisync:pubsub:queue:{atendimento_id}` | Paciente | Posição ordinal na fila e notificação de chamada iniciada |
| `/api/v1/queue/ws/atendimentos/{atendimento_id}` | `medisync:pubsub:queue:{atendimento_id}` | Paciente | Alias canônico do contrato da fila sob o prefixo da API |
| `/ws/doctor/{medico_id}` | `medisync:pubsub:doctor:{medico_id}` | Médico | Disparo de modal e evento de chamada alocada |

### Handshake e Autenticação Pré-Accept

O cliente estabelece a conexão informando a credencial na query string `?token=<credencial>`.
A validação ocorre antes de `websocket.accept()` (`validar_ws_queue_token` e `validar_ws_doctor_token`):

1. **Token Provisório de Acolhimento (HMAC-SHA256, 2 partes):** Emitido durante a triagem inicial do paciente. Permite acesso exclusivo ao atendimento correspondente.
2. **Token JWT de Acesso (3 partes):** Emitido no login de usuário cadastrado.
   - Paciente: papel `PACIENTE` com checagem de posse ReBAC (`PatientQueueOwnershipChecker`) vinculando `paciente_id` ao `atendimento_id`.
   - Administrador: papel `ADMIN_GLOBAL` possui permissão irrestrita de observabilidade.
   - Médico: papel `MEDICO` onde `usuario_id` deve coincidir estritamente com `medico_id` da rota.
3. **Códigos de Rejeição WS:**
   - `4401`: Token ausente, assinatura inválida, formato corrompido ou token revogado.
   - `4403`: Papel não autorizado ou paciente sem posse sobre o atendimento.

### Catálogo de Tipos de Mensagem

Os eventos clínicos e de controle trafegam em formato JSON serializado:

| Tipo de Mensagem | Origem | Destino | Gatilho / Descrição |
|---|---|---|---|
| `CHAMADA_INICIADA` | Valkey Pub/Sub | Paciente | Médico aceitou/alocou o atendimento; aciona ring de 45 segundos |
| `PACIENTE_CONECTADO` | WebSocket (`CONNECTED`) | Paciente | Confirmação de conexão inicial bem-sucedida do paciente no canal |
| `MEDICO_CONECTADO` | WebSocket (`READY`) | Médico | Confirmação de prontidão do médico para recebimento de consultas |
| `PULSE_HEARTBEAT` | Servidor (`{"type":"ping"}`) | Ambos | Batimento enviado a cada 25s para manter túneis NAT e balanceadores vivos |
| `ATENDIMENTO_ENCERRADO` | Valkey Pub/Sub | Ambos | Finalização formal ou cancelamento clínico da consulta |
| `DESCONEXAO_TIMEOUT` | Valkey / ARQ | Ambos | Abandono por no-show (45s) ou queda de conexão do cliente |
| `QUEUE_POSITION_UPDATE` | Valkey Pub/Sub | Paciente | Recálculo de prioridade ordinal na fila ZSET |
| `INCOMING_CALL` | Valkey Pub/Sub | Médico | Disparo de modal na tela médica com ID do atendimento e TTL de 45s |

### Envelope JSON de Sinalização

Contrato mínimo do evento em tempo real (spec, 5 linhas):

```json
{"event": "QUEUE_POSITION_UPDATE", "timestamp": "2026-10-18T00:00:00Z", "atendimento_id": "uuid", "posicao": 1}
```

Campos obrigatórios e opcionais do envelope:

| Campo | Tipo | Presença | Descrição |
|---|---|---|---|
| `event` | `string` | Obrigatório | Identificador discriminador do tipo de evento |
| `timestamp` | `string (ISO-8601)` | Obrigatório | Momento UTC da geração da mensagem |
| `atendimento_id` | `string (UUID)` | Contextual | Identificador único do atendimento vinculado |
| `medico_id` | `string (UUID)` | Contextual | Identificador do profissional alocado |
| `posicao` | `integer` | Opcional | Posição ordinal calculada na fila de espera |
| `ttl_segundos` | `integer` | Opcional | Janela temporal limite para resposta (ex.: 45s no ring) |

## Onde no código

- Impl: `src/modules/queue/application/realtime_channels.py:channel_queue_patient`
- Impl: `src/modules/consultation/application/realtime_channels.py:channel_doctor_calls`
- Impl: `src/modules/queue/application/ports/doctor_call_notifier_port.py:DoctorCallNotifierPort`
- Impl: `src/modules/queue/composition.py:ValkeyDoctorCallNotifier`
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
