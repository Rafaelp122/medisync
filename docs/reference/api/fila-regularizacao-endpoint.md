# Endpoint de Regularização e Contingência Assistencial na Fila Virtual

> **Referência de API:** `POST /api/v1/fila/atendimentos/{atendimento_id}/regularizar`  
> **Requisito:** RF-05, US-05, RN01, RN03  
> **Padrão:** Diátaxis Reference (5 seções obrigatórias)

---

## Contexto

Quando um paciente é acolhido e triado sob fluxo de contingência cadastral, seu atendimento ingressa com status `TRIADO_AGUARDANDO_ELEGIBILIDADE`. Em cenários de indisponibilidade externa (CADSUS) ou divergência demográfica temporária na rede 100% SUS (ADR-012), o paciente aguarda regularização antes da alocação clínica sem ser descartado da esteira.

Para evitar barreiras burocráticas e desassistência clínica (CFM 2.314/2022 e RN-NEG-01), este endpoint permite ao paciente ou operador submeter a regularização cadastral ou acionar contingência assistencial, promovendo o atendimento imediatamente para `APTO_PARA_CHAMADA` sem perder a antiguidade original acumulada desde o acolhimento inicial ($T_0$).

---

## Conceito

O endpoint opera sob os seguintes pilares conceituais:
1. **Preservação de Antiguidade ($T_0$ / NC-QUE-04):** Ao transicionar para `APTO_PARA_CHAMADA`, o cálculo do score no Valkey ZSET utiliza estritamente o timestamp original de acolhimento (`data_entrada_fila` ou `criado_em`), garantindo que o paciente recupere sua precedência justa frente a pacientes que chegaram depois.
2. **Idempotência Estrita:** Se o atendimento já estiver promovido para `APTO_PARA_CHAMADA` em acionamento concorrente, a operação retorna `promovido: false` com `status: "already_promoted"` e HTTP 200, sem erros, sem mutação redundante e sem duplicar o score no ZSET.
3. **Proteção Anti-IDOR:** Acesso protegido por `PosseAtendimentoPathAuthDep`, exigindo que o solicitante seja o próprio paciente titular do atendimento.

### Contrato HTTP

* **Método e Rota:** `POST /api/v1/fila/atendimentos/{atendimento_id}/regularizar`
* **Headers:**
  - `Authorization: Bearer <token_intake_ou_jwt>` (Obrigatório)
* **Path Parameters:**
  - `atendimento_id: UUID` (Identificador do atendimento)
* **Request Body (`RegularizacaoFilaRequest`):**
  - `motivo: str` (Obrigatório, 3 a 500 caracteres)
  - `tipo_contingencia: str` (Default: `"CONTINGENCIA_ASSISTENCIAL"`)
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
| `403 Forbidden` | `FORBIDDEN` | Token sem posse sobre o atendimento (Anti-IDOR). |
| `404 Not Found` | `ATENDIMENTO_NAO_ENCONTRADO` | Atendimento não encontrado (`AtendimentoNaoEncontradoError`). |
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
