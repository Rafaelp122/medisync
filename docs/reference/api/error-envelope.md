# API Error Envelope

> Envelope único RFC 7807 para todos os erros; contrato vive em `src/core/errors.py:ProblemDetails`.

## Contexto

Toda resposta de erro usa `application/problem+json`, nunca corpo ad-hoc por módulo.
Routers não montam envelope na mão; handlers centrais convertem exceção em problema.
Rate limit 429 é exceção: único `HTTPException` permitido fora de `DomainError`, isolado em helper.

## Conceito

Envelope tem 4 campos obrigatórios + 4 opcionais. Obrigatórios respondem sozinhos sem abrir código.

| Campo | Origem | Papel |
|---|---|---|
| `title` | `DomainError.title` | Resumo legível do tipo |
| `status` | `DomainError.status_code` | HTTP status espelhado no corpo |
| `detail` | argumento do `raise` | Explicação específica da ocorrência |
| `code` | `DomainError.code` | Código estável para branch no cliente |
| `type` | `error_type`, default `about:blank` | URI do tipo de problema |
| `instance` | `request.url.path` | Onde ocorreu |
| `request_id` | `get_current_request_id` + header `X-Request-ID` | Correlação |
| `invalid_params` | `RequestValidationError.errors()` | Breakdown nome/motivo/tipo, só 422 |

Contrato mínimo (spec, 5 linhas):

```json
{"title": "...", "status": 400, "detail": "...", "code": "..."}
```

Tabela de códigos (fonte única; detalhe completo só no `raise`):

| Status | `code` | Quando |
|---|---|---|
| 400 | `TENANT_INVALIDO` | Header `X-Tenant-ID` ausente ou não-positivo |
| 422 | `VALIDATION_ERROR` | Login sem tenant (nem `organizacao_id` no corpo nem header) |
| 429 | sem `code` + header `Retry-After` | `exigir_rate_limit` negou; tentar após segundos indicados |
| 404 | `EVOLUCAO_NAO_ENCONTRADA` | SOAP inexistente para o atendimento |
| 404 | `DOCUMENTO_CLINICO_NAO_ENCONTRADO` | `documento_id` inexistente |
| 404 | `DOCUMENTO_STORAGE_NAO_ENCONTRADO` | Chave ausente no object storage |
| 422 | `PRESCRICAO_FISICA_OBRIGATORIA`, `CONSULTA_INVALIDA`, `ASSINATURA_DIGITAL_INVALIDA` | Regra clínica / Portaria 344/98 / ICP-Brasil |
| 409 | `CONSULTA_FINALIZADA_IMUTAVEL`, `CONFLICT` | Registro imutável ou conflito de estado |
| 401 / 403 | `UNAUTHORIZED` / `FORBIDDEN` | Sem credencial / sem papel clínico |
| 500 | `DOCUMENTO_INTEGRIDADE` | Dados médico/paciente ausentes, nunca fabricar |
| 500 | `INTERNAL_SERVER_ERROR` | Fallback genérico, detalhe suprimido, log com stack |

Notas de semântica:

- 400 vs 422: tenant malformado em rota autenticada é 400; login sem tenant resolvível é 422 porque corpo/header falhou validação.
- 404 carrega `code` específico para cliente distinguir "evolução" de "documento" sem parsear `detail`.
- 429 não passa por `DomainError`; header `Retry-After` em segundos é obrigatório.
- 500 nunca vaza stack; `detail` fixo pede contato com suporte.

## Onde no código

- Impl: `src/core/errors.py:ProblemDetails`
- Impl: `src/core/errors.py:DomainError`
- Impl: `src/core/errors.py:TenantInvalidoError`
- Impl: `src/core/errors.py:create_problem_response`
- Impl: `src/core/errors.py:domain_error_handler`
- Impl: `src/core/errors.py:validation_error_handler`
- Impl: `src/core/errors.py:register_exception_handlers`
- Impl: `src/modules/consultation/presentation/dependencies.py:exigir_rate_limit`
- Spec: `src/modules/consultation/domain/exceptions.py:EvolucaoNaoEncontradaError`
- Spec: `src/modules/consultation/domain/exceptions.py:DocumentoClinicoNaoEncontradoError`
- Spec: `src/modules/consultation/domain/exceptions.py:DocumentoIntegridadeError`
- Spec: `src/modules/auth/presentation/helpers.py:resolve_login_tenant_id`
- Ver: `rg -n "code = |class \w+Error|status_code" src/core/errors.py | head -20`
- Ver: `rg -n "Retry-After" src/modules/consultation/presentation/dependencies.py`

## Verificação

```bash
rg -n "code = |class \w+Error|status_code" src/core/errors.py | head -20
rg -n "Retry-After" src/modules/consultation/presentation/dependencies.py
rg -n "EVOLUCAO_NAO_ENCONTRADA|DOCUMENTO_CLINICO_NAO_ENCONTRADO|DOCUMENTO_INTEGRIDADE" src/modules/consultation/domain/exceptions.py
```

Esperado: `TENANT_INVALIDO` em `src/core/errors.py:115`, `Retry-After` em `dependencies.py:72`, três códigos clínicos em `exceptions.py:55,63,71`.

## Ver também

- [Documentation standards](../architecture-standards/documentation-standards.md)
- [Setup local](../../how-to/dev-environment/setup-local.md)
- [Create module endpoint](../../how-to/backend/create-module-endpoint.md)
- `docs/explanation/architecture/security-and-authorization.md`
- `docs/explanation/architecture/compliance-and-telemedicine.md`
