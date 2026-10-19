# Emitir e Consumir Eventos de Domínio em Tempo Real

> Como publicar eventos clínicos via Valkey Pub/Sub e transmiti-los aos clientes via WebSockets.

## Contexto

No MediSync Express, a comunicação bidirecional de baixa latência (sub-500ms) entre a API e as interfaces de pacientes e médicos é realizada através de WebSockets integrados ao Valkey Pub/Sub (ADR-002, US-07).

Eventos como a alteração na posição da fila (`QUEUE_POSITION_UPDATE`), chamadas médicas ativas (`INCOMING_CALL`, `CALLED`) e fechamento de atendimento precisam ser transmitidos de forma assíncrona e desacoplada. Os serviços de aplicação publicam mensagens padronizadas em tópicos isolados do Valkey, enquanto os roteadores FastAPI realizam o streaming contínuo das mensagens para as conexões ativas.

## Conceito

A transmissão de eventos em tempo real obedece a um fluxo em quatro etapas:

### 1. Obter o canal canônico de mensageria

Sempre utilize as funções auxiliares em `src/modules/queue/application/realtime_channels.py` e `src/modules/consultation/application/realtime_channels.py` para construir nomes determinísticos de tópicos:

```python
channel_paciente = channel_queue_patient(atendimento_id)
channel_medico = channel_doctor_calls(medico_id)
```

Isso garante a uniformidade das chaves Pub/Sub (`medisync:pubsub:queue:{id}` e `medisync:pubsub:doctor:{id}`).

### 2. Disparar o evento no serviço de aplicação

Injete a conexão Valkey no serviço e invoque a função de publicação assíncrona:

```python
payload = {"event": "CALLED", "atendimento_id": str(atend_id), "medico_id": str(med_id)}
await publish_realtime_event(valkey=self._valkey, channel=channel_paciente, payload=payload)
```

Sempre envolva a emissão em bloco de proteção (`try/except`) para evitar que falhas de rede na sinalização interfiram na persistência transacional da regra de negócio.

### 3. Expor o endpoint WebSocket

No roteador de apresentação, receba o canal e faça o streaming com `stream_channel`:

```python
@queue_ws_router.websocket("/ws/queue/{atendimento_id}")
async def ws_queue_patient(websocket: WebSocket, atendimento_id: UUID, valkey: ValkeyDep, _auth: QueueWsAuthDep):
    await stream_channel(websocket, valkey, channel_queue_patient(atendimento_id), "CONNECTED", atendimento_id=str(atendimento_id))
```

O helper gerencia o ciclo completo de handshake, transmissão de payload inicial e escuta contínua de mensagens.

### 4. Gerenciamento e encerramento de conexão

O utilitário `forward_pubsub_to_websocket` mantém a subscrição ativa e cancela as corrotinas em background de forma limpa quando o cliente desconecta, prevenindo vazamentos de recursos no pool do Valkey.

## Onde no código

- Utilitários centrais de Pub/Sub: `src/core/realtime.py:publish_realtime_event`
- Roteador WebSocket da fila de espera: `src/modules/queue/presentation/routers/queue_ws_router.py:ws_queue_patient`
- Emissão de chamada médica no serviço: `src/modules/queue/application/services/alocacao_service.py:AlocacaoService`
- Suíte de integração WebSocket: `tests/integration/test_websocket_endpoints.py`
- Referência de canais em tempo real: `docs/reference/api/websocket-channels.md`

Verifique os canais Pub/Sub e utilitários de streaming:

```bash
rg -n "def channel_" src/modules/*/application/realtime_channels.py
```

Inspecione pontos de emissão de eventos em tempo real no módulo de fila:

```bash
rg -n "publish_realtime_event" src/modules/queue/
```

## Verificação

Execute a suíte de testes de integração para validar a transmissão em menos de 500ms:

```bash
uv run pytest tests/integration/test_websocket_endpoints.py --no-cov -v
```

Expected: Todos os testes aprovados, confirmando a recepção do evento inicial `CONNECTED` e o push instantâneo do payload.

Monitore os canais ativos em tempo real no contêiner do Valkey:

```bash
docker compose exec -T valkey valkey-cli pubsub channels "medisync:pubsub:*"
```

Assine os tópicos diretamente para inspecionar eventos publicados durante a operação:

```bash
docker compose exec -T valkey valkey-cli psubscribe "medisync:pubsub:*"
```

## Ver também

- [Create module endpoint](create-module-endpoint.md)
- [Wire module dependencies](wire-module-dependencies.md)
- [Run tests](run-tests.md)
- [ADR-002](../../adrs/ADR-002-Alocacao-Atomica-Valkey-Lua.md)
- [Canais WebSocket Reference](../../reference/api/websocket-channels.md)
- [Dicionário de Chaves Valkey](../../reference/valkey/keys-dictionary.md)
