# Domain Events — Notificação Ponto a Ponto

> Eventos de domínio via ports de notificação e sinalização Pub/Sub, sem barramento central.

Eventos clínicos circulam ponto a ponto via ports tipadas ou por canais dedicados no Valkey Pub/Sub (`QueueEnginePort`), além do caso à parte de auditoria append-only (`AuditEvent`).

Cada evento é um dataclass imutável ou payload tipado, cada despacho é um método de port, cada default apenas loga.

Sem fila de eventos genérica, sem tópico compartilhado global, sem import cruzado de modelos.

## 1. Tabela geral

| evento | produtor | consumidores | port / canal |
|---|---|---|---|
| PacienteAusenteEvent | queue no timeout de ring | painel, métricas, telemetria | `src/modules/queue/application/ports/paciente_ausente_notifier.py` |
| ElegibilidadeFalhaEvent | ambulatory na falha de qualificação | sala de espera, paciente | `src/modules/ambulatory/application/ports/eligibility_notifier.py` |
| `INCOMING_CALL` / `CALLED` / `CALL_CANCELLED` | queue na alocação e recusa/cancelamento | WebSocket médico e paciente | `src/modules/queue/application/ports/queue_engine_port.py` |
| AuditEvent | núcleo em toda transição | cfm, lgpd, perícia | `src/core/audit/models.py` |

AuditEvent é caso à parte: tabela append-only, nunca notifier, nunca replay.

## 2. PacienteAusenteEvent — no-show em 45s

Emitido quando chamada expira sem resposta do paciente.

Produtor: `src/modules/queue/application/services/alocacao_service.py` abre janela chamando e agenda `resolver_ring_timeout_task`; worker `src/worker/tasks/ring_timeout.py` fecha ausência via `FilaService.resolver_ring_timeout`.

Port e dto: `src/modules/queue/application/ports/paciente_ausente_notifier.py` com `PacienteAusenteNotifierPort.emitir_paciente_ausente`.

Campos: `atendimento_id`, `medico_id`, `paciente_id`, `tempo_toque_segundos` (padrão 45s), `evento`, `disparado_em`.

Default: `LoggingPacienteAusenteNotifier` registra warning estruturado, sem efeito colateral clínico.

Consumidores lógicos: painel libera médico, métricas contam no-show, telemetria alerta recorrência.

Prova viva: `tests/unit/test_alocacao_service_notifications.py` garante que falha de notificação nunca bloqueia progressão da fila.

## 3. Bloqueio de Admissão por Backpressure (RN05)

Quando a admissão suspende entrada por falta de médico ativo (`SEM_MEDICOS_ATIVOS`), cota diária (`COTA_ATINGIDA`) ou carga estocástica (`CAPACIDADE_EXCEDIDA`), `ControleAdmissaoService.avaliar_admissao` (`src/modules/queue/application/services/controle_admissao_service.py`) registra log estruturado de transbordo (`logger.warning`) e `FilaService.admitir_paciente` levanta `AdmissaoFilaSuspensaError` (HTTP 503 RFC 7807) com orientação presencial pronta para UI — sem seam hipotético `QueueOverflowNotifierPort`.

## 4. ElegibilidadeFalhaEvent — cobertura e qualificação cadastral

Emitido quando qualificação cadastral SUS falha ou expira.

Produtor: `src/modules/ambulatory/application/services/eligibility_service.py` valida via provedor sob demanda (sem worker dedicado de elegibilidade após a admissão direta SUS da ADR-012).

Port e dto: `src/modules/ambulatory/application/ports/eligibility_notifier.py` com `ElegibilidadeNotifierPort.notificar_falha`.

Provedor abstrato: `src/modules/ambulatory/application/ports/eligibility_provider.py` separa verificação de alerta.

Campos: `atendimento_id`, `paciente_id`, `motivo`, `status`, `disparado_em`.

Default: `LoggingElegibilidadeNotifier` registra warning com contexto extra para sala de espera.

Consumidores lógicos: paciente regulariza cadastro via `POST /api/v1/fila/atendimentos/{atendimento_id}/regularizar`, mantendo $T_0$.

## 5. Sinalização Realtime via `QueueEnginePort`

Eventos efêmeros de ciclo de chamada trafegam via `ValkeyQueueEngine.publicar_evento_fila` e `publicar_evento_medico` (`src/modules/queue/infrastructure/valkey_queue_engine.py`):

- `INCOMING_CALL` e `CALLED`: emitidos por `AlocacaoChamadaService` pós-commit para abrir modal de chamada no médico e no paciente.
- `CALL_CANCELLED`: emitido por `FilaService._notificar_cancelamento_chamada_medico` quando o paciente recusa/cancela (`POST /api/v1/fila/cancelar/{atendimento_id}`) ou sofre piora Nível 1 enquanto estava em `CHAMANDO_PACIENTE`.

## 6. AuditEvent — caso à parte

Modelo append-only para conformidade cfm e lgpd, definido em `src/core/audit/models.py`, acessado através da porta transversal `src/core/audit/ports.py` (`AuditTrailPort`) e adaptador `src/core/audit/adapter.py` (`SqlAuditTrailAdapter`).

Não é notifier port, não circula ponto a ponto, não admite replay ou reemissão.

Toda transição clínica relevante dos módulos `queue`, `consultation`, `auth` e `ambulatory` grava registro na mesma transação SQLAlchemy antes do commit, com ator, papel, tipo de evento, estados anterior e novo, hash de tcle e payload. Catálogo completo dos 21 eventos: [Catálogo de Eventos de Auditoria Clínica](../../reference/audit/event-catalog.md).

Imutabilidade garantida no PostgreSQL por trigger `trg_prevent_audit_mutation` e listeners de ORM que vetam update e delete, qualquer tentativa levanta erro de domínio. Provas vivas: `tests/integration/test_clinical_audit_integration.py` e `tests/unit/test_audit_port_adapter.py`.

Uso: perícia reconstrói jornada por atendimento, auditoria prova consentimento, lgpd rastreia acesso a dado sensível.

Diferença central: eventos acima avisam o presente, auditoria prova o passado.

## 7. Sem barramento central

Nota explícita: não há bus central de eventos neste repositório.

O arquivo src/core/event_bus.py não existe, verificado com ls que retorna arquivo ou diretório inexistente.

Despacho ocorre via notifier ports ponto a ponto e Pub/Sub tipado em `QueueEnginePort`.

Consequências: sem assinatura dinâmica, sem roteamento implícito, sem ordem global prometida.

Teste de alocação mostra a filosofia: `tests/unit/test_alocacao_service_notifications.py` usa adaptador de log ou dublê nomeado, falha de rede nunca reverte commit.

Notificação WhatsApp segue o mesmo desenho em `src/modules/queue/application/ports/notification_port.py` com implementações em `src/modules/queue/infrastructure/notifications/`.

Quando precisar de novo evento: criar dto imutável mais port no módulo produtor, default de log, injetar no serviço, nunca importar modelo alheio.

## 8. Verificação

```bash
ls src/core/event_bus.py
# ls: nao foi possivel acessar, arquivo ou diretorio inexistente

rg -n "class \w+Event" src/modules/ --glob "*notifier*.py"
# PacienteAusenteEvent, ElegibilidadeFalhaEvent

ls src/core/audit/models.py tests/unit/test_alocacao_service_notifications.py
# ambos existem, auditoria e prova viva presentes

uv run python scripts/docs_check.py
# exit 0, links validos e sem bloco python longo
```

Divergência entre tabela e port real exige atualizar a tabela, nunca inventar consumidor fantasma.

## 9. Ver também

- [context map](./context-map.md) — quem consome e quem expõe cada port
- [queue domain](./queue-domain.md) — ring de 45s e backpressure
- [ambulatory domain](./ambulatory-domain.md) — produção ambulatorial SUS e qualificação cadastral
- [product specification](../product-specification.md) — requisitos de notificação
- [websocket channels](../../reference/api/websocket-channels.md) — contratos Pub/Sub realtime
