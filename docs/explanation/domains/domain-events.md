# Domain Events — Notificação Ponto a Ponto

> Eventos de domínio via ports de notificação, sem barramento central.

Três eventos clínicos circulam ponto a ponto, mais um caso à parte de auditoria append-only.

Cada evento é um dataclass imutável, cada despacho é um método de port, cada default apenas loga.

Sem fila de mensagens, sem tópico compartilhado, sem import cruzado de modelos.

## 1. Tabela geral

| evento | produtor | consumidores | port |
|---|---|---|---|
| PacienteAusenteEvent | queue no timeout de ring | painel, métricas, telemetria | `src/modules/queue/application/ports/paciente_ausente_notifier.py` |
| QueueOverflowEvent | queue na admissão suspensa | regulação, painel, ui | `src/modules/queue/application/ports/queue_overflow_notifier.py` |
| ElegibilidadeFalhaEvent | billing na falha de cobertura | sala de espera, paciente | `src/modules/billing/application/ports/eligibility_notifier.py` |
| AuditEvent | núcleo em toda transição | cfm, lgpd, perícia | `src/core/audit/models.py` |

AuditEvent é caso à parte: tabela append-only, nunca notifier, nunca replay.

## 2. PacienteAusenteEvent — no-show em 45s

Emitido quando chamada expira sem resposta do paciente.

Produtor: `src/modules/queue/application/services/alocacao_service.py` abre janela chamando, worker `src/worker/tasks/ring_timeout.py` fecha ausência.

Port e dto: `src/modules/queue/application/ports/paciente_ausente_notifier.py` com `PacienteAusenteNotifierPort.emitir_paciente_ausente`.

Campos: atendimento, organização, médico, paciente, tempo de toque padrão quarenta e cinco segundos, carimbo de disparo.

Default: `LoggingPacienteAusenteNotifier` registra warning estruturado, sem efeito colateral clínico.

Consumidores lógicos: painel libera médico, métricas contam no-show, telemetria alerta recorrência.

Prova viva: `tests/unit/test_alocacao_service_notifications.py` garante que falha de notificação nunca bloqueia progressão da fila.

## 3. QueueOverflowEvent — transbordo regulatório

Emitido quando admissão suspende entrada por falta de médico, cota ou carga estocástica.

Produtor: `src/modules/queue/application/services/controle_admissao_service.py` avalia capacidade antes de inserir no zset.

Port e dto: `src/modules/queue/application/ports/queue_overflow_notifier.py` com `QueueOverflowNotifierPort.emitir_transbordo`.

Campos: organização, motivo, aguardando, médicos ativos, tempo restante, carga estimada, mensagem de orientação, alpha utilizado.

Default: `LoggingQueueOverflowNotifier` registra warning com carga e alpha, integração regulatória pluga por fora.

Motivos conhecidos: sem médicos ativos, cota atingida, capacidade excedida.

Consumidores lógicos: regulação recebe contingência, ui exibe mensagem pronta, painel ajusta plantão.

## 4. ElegibilidadeFalhaEvent — cobertura negada

Emitido quando verificação de convênio falha ou expira.

Produtor: `src/modules/billing/application/services/eligibility_service.py` valida via provedor, worker `src/worker/tasks/eligibility.py` roda fora do request.

Port e dto: `src/modules/billing/application/ports/eligibility_notifier.py` com `ElegibilidadeNotifierPort.notificar_falha`.

Provedor abstrato: `src/modules/billing/application/ports/eligibility_provider.py` separa verificação de alerta.

Campos: atendimento, organização, paciente, motivo, status de elegibilidade, carimbo de disparo.

Default: `LoggingElegibilidadeNotifier` registra warning com contexto extra para sala de espera.

Consumidores lógicos: paciente regulariza pagamento ou dado, painel acompanha pendência, fila segura promoção para apto.

## 5. AuditEvent — caso à parte

Modelo append-only para conformidade cfm e lgpd, definido em `src/core/audit/models.py`.

Não é notifier port, não circula ponto a ponto, não admite replay ou reemissão.

Toda transição relevante grava registro com ator, papel, tipo de evento, estados anterior e novo, hash de tcle e payload.

Imutabilidade garantida por listeners que vetam update e delete, qualquer tentativa levanta erro de domínio.

Uso: perícia reconstrói jornada por atendimento, auditoria prova consentimento, lgpd rastreia acesso a dado sensível.

Diferença central: eventos acima avisam o presente, auditoria prova o passado.

## 6. Sem barramento central

Nota explícita: não há bus central de eventos neste repositório.

O arquivo src/core/event_bus.py não existe, verificado com ls que retorna arquivo ou diretório inexistente.

Despacho ocorre via notifier ports ponto a ponto, cada serviço recebe a port por injeção e chama um método.

Consequências: sem assinatura dinâmica, sem roteamento implícito, sem ordem global prometida.

Teste de alocação mostra a filosofia: `tests/unit/test_alocacao_service_notifications.py` usa adaptador de log ou mock, falha de rede nunca reverte commit.

Notificação genérica segue o mesmo desenho em `src/core/notifications.py`, reexportada por `src/modules/queue/application/ports/notification_port.py`.

Quando precisar de novo evento: criar dto imutável mais port no módulo produtor, default de log, injetar no serviço, nunca importar modelo alheio.

## 7. Verificação

```bash
ls src/core/event_bus.py
# ls: nao foi possivel acessar, arquivo ou diretorio inexistente

rg -n "class \\w+Event" src/modules/ --glob "*notifier*.py"
# PacienteAusenteEvent, QueueOverflowEvent, ElegibilidadeFalhaEvent

ls src/core/audit/models.py tests/unit/test_alocacao_service_notifications.py
# ambos existem, auditoria e prova viva presentes

uv run python scripts/docs_check.py
# exit 0, links validos e sem bloco python longo
```

Divergência entre tabela e port real exige atualizar a tabela, nunca inventar consumidor fantasma.

## 8. Ver também

- [context map](./context-map.md) — quem consome e quem expõe cada port
- [queue domain](./queue-domain.md) — ring de 45s e backpressure
- [billing domain](./billing-domain.md) — elegibilidade e cobertura
- [product specification](../product-specification.md) — requisitos de notificação
