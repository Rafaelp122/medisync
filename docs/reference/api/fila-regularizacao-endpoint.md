# Endpoint de Regularização e Contingência Assistencial na Fila Virtual

> **Referência de API:** `POST /api/v1/fila/atendimentos/{atendimento_id}/regularizar`  
> **Requisito:** RF-05, US-05, RN01, RN03  
> **Padrão:** Diátaxis Reference (5 seções obrigatórias)

---

## Contexto

Quando um paciente é acolhido e triado, seu atendimento ingressa com status `TRIADO_AGUARDANDO_ELEGIBILIDADE`. Se a validação com a operadora de saúde sofrer lentidão, indisponibilidade de gateway ou rejeição cadastral temporária, o paciente permanece retido sem ser convocado pelos médicos (desvio temporário RN03). 

Para evitar paywall obstrutivo e desassistência clínica (CFM 2.314/2022 e RN-NEG-01), este endpoint permite ao paciente ou operador submeter a regularização cadastral ou acionar contingência assistencial, promovendo o atendimento imediatamente para `APTO_PARA_CHAMADA` sem perder a antiguidade original acumulada desde o acolhimento inicial ($T_0$).

---

## Conceito

O endpoint opera sob os seguintes pilares conceituais:
1. **Preservação de Antiguidade ($T_0$ / NC-QUE-04):** Ao transicionar para `APTO_PARA_CHAMADA`, o cálculo do score no Valkey ZSET utiliza estritamente o timestamp original de acolhimento (`data_entrada_fila` ou `criado_em`), garantindo que o paciente recupere sua precedência justa frente a pacientes que chegaram depois.
2. **Idempotência Estrita:** Se o worker assíncrono de elegibilidade aprovar o convênio no mesmo instante em que a contingência for acionada, a operação retorna status `already_promoted` com HTTP 200, sem erros, sem mutação redundante e sem duplicar o score no ZSET.
3. **Proteção Anti-IDOR:** Acesso protegido por `PosseAtendimentoPathAuthDep`, exigindo que o solicitante seja o próprio paciente ou operador autorizado do mesmo tenant (`X-Tenant-ID`).

### Contrato HTTP

* **Método e Rota:** `POST /api/v1/fila/atendimentos/{atendimento_id}/regularizar`
* **Headers:**
  - `X-Tenant-ID: <int>` (Obrigatório)
  - `Authorization: Bearer <token_intake_ou_jwt>` (Obrigatório)
* **Path Parameters:**
  - `atendimento_id: UUID` (Identificador do atendimento)
* **Request Body (`RegularizacaoFilaRequest`):**
  - `motivo: str` (Obrigatório, 3 a 500 caracteres)
  - `tipo_contingencia: str` (Default: `"CONTINGENCIA_ASSISTENCIAL"`)
  - `operadora_id: str | None` (Opcional)
  - `numero_carteirinha: str | None` (Opcional)
* **Response Body (`RegularizacaoFilaResponse`):**
  - `atendimento_id: UUID`
  - `promovido: bool`
  - `status: str`
  - `score: int`
  - `tipo_contingencia: str`
  - `mensagem: str`

### Respostas e Envelopes de Erro

| Código HTTP | Erro RFC 7807/9457 | Causa |
| :--- | :--- | :--- |
| `200 OK` | — | Atendimento regularizado ou já previamente apto (idempotência). |
| `401 Unauthorized` | `UNAUTHORIZED` | Token ausente, expirado ou com assinatura inválida. |
| `403 Forbidden` | `FORBIDDEN` | Token sem posse sobre o atendimento (Anti-IDOR) ou tenant divergente. |
| `404 Not Found` | `NOT_FOUND` | Atendimento não encontrado na organização informada. |
| `409 Conflict` | `TRANSICAO_ESTADO_INVALIDA` | Atendimento finalizado ou em consulta (`EM_ATENDIMENTO`). |
| `422 Unprocessable Entity` | `VALIDATION_ERROR` | Motivo ausente ou com menos de 3 caracteres. |

---

## Onde no código

- `src/modules/queue/presentation/routers/fila_router.py`
- `src/modules/queue/presentation/schemas.py`
- `src/modules/queue/application/dtos.py`
- `src/modules/queue/application/services/fila_service.py`
- `src/modules/queue/domain/models/atendimento.py`

---

## Verificação

Execução dos testes unitários e de integração dedicados à regularização:

```bash
uv run pytest tests/unit/test_fila_router.py -k "test_post_regularizar"
uv run pytest tests/unit/test_fila_regularizacao.py
uv run pytest tests/integration/test_regularizacao_flow.py
```

---

## Ver também

- [`US-05 — Tratamento de Exceções e Regularização de Elegibilidade`](../../user-stories/US-05-regularizacao-elegibilidade-fila.md)
- [`Queue Domain Explanation`](../../explanation/domains/queue-domain.md)
- [`Envelope de Erros RFC 7807/9457`](./error-envelope.md)
