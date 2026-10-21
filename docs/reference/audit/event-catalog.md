# Catálogo Canônico de Eventos de Auditoria Clínica

> Catálogo de eventos auditáveis append-only sob ADR-007, CFM nº 2.314/2022, CFM nº 1.821/2007 e LGPD Art. 11.

## Contexto

A telemedicina no Brasil é estritamente regulamentada pelas Resoluções CFM nº 1.821/2007 e CFM nº 2.314/2022, bem como pela Lei Geral de Proteção de Dados (LGPD, Art. 11, dados sensíveis de saúde). Toda transição de estado clínico, alocação de plantonista, admissão de paciente, emissão ou assinatura de documento e encerramento de teleconsulta deve ser registrada em trilha imutável (*append-only*), vinculada à transação da ação clínica antes do commit.

Este catálogo define a taxonomia canônica dos 11 eventos clínicos do MediSync Express distribuídos entre os módulos `queue` e `consultation`.

## Conceito

### Princípios da Trilha Clínica (ADR-007)

1. **Atomicidade Estrita:** O evento de auditoria é persistido pelo `AuditTrailPort` (`SqlAuditTrailAdapter`) na mesma transação SQLAlchemy do caso de uso clínico. Se a transação falhar ou sofrer `rollback`, o evento não é gravado, eliminando órfãos.
2. **Imutabilidade Física:** A tabela `audit_events` é protegida pela trigger de banco de dados `trg_prevent_audit_mutation`, que bloqueia comandos `UPDATE` e `DELETE` em tempo de execução com exceção RestrictViolation.
3. **Não-Repúdio e Proveniência:** Cada evento registra o identificador do ator (`ator_id`), tipo (`ator_tipo`), papel funcional (`ator_papel`), hash do consentimento (`tcle_hash`), transição de estado (`estado_anterior` e `novo_estado`) e payload contextual.

### Taxonomia Canônica dos 11 Eventos

| Tipo de Evento | Módulo | Ator Canônico | Papel | Descrição Clínica |
|---|---|---|---|---|
| `ADMISSAO_PACIENTE` | `queue` | `PACIENTE` | `PACIENTE` | Admissão pós-triagem clínica na fila virtual com registro de protocolo e prioridade Manchester. |
| `ELEGIBILIDADE_CONFIRMADA` | `queue` | `SISTEMA` | `SISTEMA` | Confirmação de cobertura de operadora/SUS, habilitando chamada médica. |
| `CHAMADA_INICIADA` | `queue` | `PROFISSIONAL` | `MEDICO` | Plantonista aciona paciente; início da janela de ring de 45 segundos. |
| `CHAMADA_ATENDIDA` | `queue` | `PACIENTE` | `PACIENTE` | Paciente atende o toque WebRTC e ingressa na sala de teleconsulta. |
| `TIMEOUT_CHAMADA_NO_SHOW` | `queue` | `SISTEMA` | `SISTEMA` | Esgotamento do ring de 45s sem resposta; marcação de ausência (no-show). |
| `ATENDIMENTO_CANCELADO_PACIENTE` | `queue` | `PACIENTE` | `PACIENTE` | Desistência voluntária do atendimento solicitada pelo paciente na fila. |
| `PIORA_CLINICA_REGISTRADA` | `queue` | `PACIENTE` | `PACIENTE` | Deterioração clínica em espera; alerta SAMU 192 e reclassificação. |
| `EVOLUCAO_SOAP_REGISTRADA` | `consultation` | `PROFISSIONAL` | `MEDICO` | Registro ou retificação de notas SOAP (Subjetivo, Objetivo, Avaliação CID-10, Plano). |
| `DOCUMENTO_CLINICO_EMITIDO` | `consultation` | `PROFISSIONAL` | `MEDICO` | Emissão de receita, atestado ou laudo com validação da Portaria SVS/MS nº 344/98. |
| `DOCUMENTO_CLINICO_ASSINADO` | `consultation` | `PROFISSIONAL` | `MEDICO` | Assinatura digital ICP-Brasil PAdES via PSC com hash SHA-256 e storage S3. |
| `CONSULTA_FINALIZADA` | `consultation` | `PROFISSIONAL` | `MEDICO` | Encerramento formal do ato médico com trancamento imutável de prontuário e documentos. |

### Contrato de Dados do Evento

O schema da trilha de auditoria é normalizado conforme o modelo `AuditEvent`:

- `organizacao_id`: Inteiro (tenant multitenant sob RLS).
- `tipo_evento`: String maiúscula conforme tabela canônica acima.
- `ator_tipo`: `PACIENTE`, `PROFISSIONAL` ou `SISTEMA`.
- `ator_papel`: Papel funcional do ator (`PACIENTE`, `MEDICO`, `ENFERMEIRO`, `SISTEMA`, `RECEPCIONISTA`).
- `ator_id`: UUIDv7 do usuário ou profissional responsável.
- `atendimento_id`: UUIDv7 correlacionando todos os eventos do ciclo de vida clínico.
- `estado_anterior` / `novo_estado`: Transições de status da máquina de estados clínica.
- `tcle_hash`: Hash SHA-256 (64 hex) do Termo de Consentimento Livre e Esclarecido.
- `payload`: JSONB contendo metadados específicos do evento (ex.: `triagem_id`, `cid10`, `sha256_hash`, `chave_s3`).
- `ip_origem`: Endereço IP do solicitante para rastreabilidade de acesso forense.

## Onde no código

- Impl: `src/core/audit/ports.py:AuditTrailPort`
- Impl: `src/core/audit/adapter.py:SqlAuditTrailAdapter`
- Impl: `src/core/audit/models.py:AuditEvent`
- Impl: `src/modules/queue/application/services/fila_service.py:FilaService`
- Impl: `src/modules/consultation/application/services/pep_service.py:PEPService`
- Impl: `src/modules/consultation/application/services/evolucao_service.py:EvolucaoService`
- Impl: `src/modules/consultation/application/services/documento_service.py:DocumentoService`
- Prova viva: `tests/integration/test_clinical_audit_integration.py:test_pep_workflow_full_audit_trail_reconstruction`
- Prova viva: `tests/unit/test_queue_audit_events.py:test_admitir_paciente_records_admissao_audit_event`
- Prova viva: `tests/unit/test_consultation_audit_events.py:test_salvar_evolucao_soap_records_evolucao_audit_event`
- Ver: `rg -n "record_event" src/modules/queue/application/services/`
- Ver: `rg -n "record_event" src/modules/consultation/application/services/`

## Verificação

```bash
uv run pytest tests/unit/test_audit_port_adapter.py tests/unit/test_queue_audit_events.py tests/unit/test_consultation_audit_events.py
uv run pytest tests/integration/test_clinical_audit_integration.py
```

Esperado: todos os testes unitários e de integração passam com código de saída 0, confirmando persistência e integridade da trilha.

## Ver também

- [ADR-007: Trilha de Auditoria Imutável Append-Only](../../adrs/ADR-007-Auditoria-Imutavel-Append-Only.md)
- [ADR-006: Assinatura Digital ICP-Brasil](../../adrs/ADR-006-Assinatura-Digital-ICP-Brasil-Nuvem-PSC.md)
- [Explicação: Domínio de Fila](../../explanation/domains/queue-domain.md)
- [Explicação: Domínio de Consulta](../../explanation/domains/consultation-domain.md)
- [Referência: Database Schema & RLS](../database/schema-and-rls.md)
