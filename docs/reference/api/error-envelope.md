# API Error Envelope

> Envelope único RFC 7807 para todos os erros; contrato vive em `src/core/errors.py:ProblemDetails`.

## Contexto

Toda resposta de erro usa `application/problem+json`, nunca corpo ad-hoc por módulo.
Routers não montam envelope na mão; handlers centrais convertem exceção em problema.
Exceções de negócio herdam de `DomainError` e expõem `status_code` e `code` estáveis.
O status 429 atua em duas frentes: `OtpRateLimitExcedidoError` como `DomainError` estruturado (`OTP_RATE_LIMIT_EXCEEDED`) e `exigir_rate_limit` (helper de IP) como único `HTTPException` permitido fora de `DomainError` com header `Retry-After`.

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

| Status | `code` | Quando / Origem |
|---|---|---|
| 400 | `DOMAIN_ERROR`, `BAD_REQUEST` | Erro genérico de domínio ou payload malformado (`DomainError`, `BadRequestError`) |
| 400 | `TENANT_INVALIDO` | Header `X-Tenant-ID` ausente ou não-positivo (`TenantInvalidoError`) |
| 400 | `AUTH_ERROR` | Falha genérica de autenticação (`AuthError`) |
| 400 | `DEPENDENTE_AUTO_REFERENCIA` | Paciente indicado como dependente de si mesmo (`DependenteAutoReferenciaError`) |
| 401 | `UNAUTHORIZED` | Ausência de credencial válida (`UnauthorizedError`) |
| 401 | `CREDENCIAIS_INVALIDAS` | Identificador ou senha incorretos (`CredenciaisInvalidasError`) |
| 401 | `TOKEN_INVALIDO`, `TOKEN_EXPIRADO` | JWT malformado, assinatura inválida ou expirado (`TokenInvalidoError`, `TokenExpiradoError`) |
| 401 | `TOKEN_REVOGADO` | Token revogado ou reutilizado após renovação (`TokenRevogadoError`) |
| 401 | `TOKEN_ACOLHIMENTO_INVALIDO` | Token provisório de triagem expirado ou inválido (`TokenAcolhimentoInvalidoError`) |
| 401 | `OTP_INVALIDO` | Código OTP incorreto ou expirado (`OtpInvalidoOuExpiradoError`) |
| 403 | `FORBIDDEN` | Acesso negado por falta de papel clínico ou escopo (`ForbiddenError`) |
| 403 | `CONTA_DESATIVADA` | Usuário inativo tentando autenticar (`ContaDesativadaError`) |
| 404 | `NOT_FOUND` | Recurso genérico não encontrado (`NotFoundError`) |
| 404 | `PACIENTE_NAO_ENCONTRADO` | Paciente não cadastrado no tenant (`PacienteNaoEncontradoError`) |
| 404 | `ATENDIMENTO_NAO_ENCONTRADO` | Atendimento não localizado no banco (`AtendimentoNaoEncontradoError`) |
| 404 | `FILA_VAZIA` | Sem pacientes elegíveis na fila de espera (`FilaVaziaError`) |
| 404 | `EVOLUCAO_NAO_ENCONTRADA` | SOAP inexistente para o atendimento (`EvolucaoNaoEncontradaError`) |
| 404 | `DOCUMENTO_CLINICO_NAO_ENCONTRADO` | Documento clínico inexistente (`DocumentoClinicoNaoEncontradoError`) |
| 404 | `DOCUMENTO_STORAGE_NAO_ENCONTRADO` | Chave de arquivo ausente no MinIO/S3 (`DocumentoNaoEncontradoNoStorageError`) |
| 409 | `CONFLICT` | Conflito de estado concorrente genérico (`ConflictError`) |
| 409 | `VINCULO_DEPENDENTE_EXISTENTE` | Vínculo titular-dependente já existente (`VinculoDependenteExistenteError`) |
| 409 | `TRANSICAO_ESTADO_INVALIDA` | Transição ilegal na máquina de estados de atendimento (`TransicaoEstadoInvalidaError`) |
| 409 | `MEDICO_OCUPADO` | Médico com chamada ativa ou lock de consulta - RN02 (`MedicoOcupadoError`) |
| 409 | `ATENDIMENTO_NAO_DISPONIVEL` | Atendimento capturado por outro médico (`AtendimentoNaoDisponivelError`) |
| 409 | `CONSULTA_FINALIZADA_IMUTAVEL` | Alteração de prontuário de consulta encerrada (`ConsultaFinalizadaError`) |
| 409 | `AUDITORIA_IMUTAVEL` | Tentativa de mutação UPDATE/DELETE em trilha forense (`AuditoriaImutavelError`) |
| 422 | `VALIDATION_ERROR` | Falha de validação estrutural Pydantic (`ValidationError`) |
| 422 | `IDENTIFICACAO_OBRIGATORIA` | Paciente sem CPF nem CNS (`IdentificacaoObrigatoriaError`) |
| 422 | `EMERGENCIA_CRITICA_SAMU_192` | Gravidade Vermelha / SAMU 192 imediato - RN04 (`EmergenciaCriticaSamuError`) |
| 422 | `TRIAGEM_INVALIDA` | Parâmetros de triagem inválidos (`TriagemInvalidaError`) |
| 422 | `PRESCRICAO_FISICA_OBRIGATORIA` | Notificação amarela/azul Portaria 344/98 (`PrescricaoFisicaObrigatoriaError`) |
| 422 | `CONSULTA_INVALIDA` | Violação de regra clínica em evolução/prescrição (`ConsultaInvalidaError`) |
| 422 | `ASSINATURA_DIGITAL_INVALIDA` | Falha na assinatura digital ICP-Brasil (`AssinaturaDigitalInvalidaError`) |
| 422 | `AUDITORIA_INVALIDA` | Inconsistência nos atributos do evento forense (`AuditoriaInvalidaError`) |
| 423 | `CONTA_BLOQUEADA` | Bloqueio temporário por tentativas falhas consecutivas (`ContaBloqueadaError`) |
| 429 | `OTP_RATE_LIMIT_EXCEEDED` | Limite de requisições de OTP excedido (`OtpRateLimitExcedidoError`) |
| 429 | sem `code` | Rate limit de rede por IP (`Retry-After` obrigatório via `exigir_rate_limit`) |
| 500 | `DOCUMENTO_INTEGRIDADE` | Metadados de médico/paciente ausentes (`DocumentoIntegridadeError`) |
| 500 | `INTERNAL_SERVER_ERROR` | Fallback genérico para erros internos não tratados |
| 503 | `ADMISSAO_FILA_SUSPENSA` | Admissão suspensa por backpressure estocástico ou cota atingida - RN05 (`AdmissaoFilaSuspensaError`) |

Notas de semântica:

- 400 vs 422: payload malformado ou tenant ausente em rota autenticada é 400; falha de validação de corpo ou regra clínica é 422.
- 404 carrega `code` discriminado para o cliente diferenciar recursos clínicos sem inspecionar `detail`.
- 409 protege concorrência de alocação médica e imutabilidade de prontuário e registros forenses.
- 423 (Locked): formalmente mapeado para contas bloqueadas temporariamente por proteção contra força bruta.
- 429 (Too Many Requests): suporta tanto `DomainError` com código `OTP_RATE_LIMIT_EXCEEDED` quanto `HTTPException` com header `Retry-After`.
- 503 (Service Unavailable): formalmente mapeado para suspensão de admissão por backpressure ou cota saturada.
- 500: falha de integridade documental ou fallback interno; jamais vaza stack traces.

## Onde no código

- Impl: `src/core/errors.py:ProblemDetails`
- Impl: `src/core/errors.py:DomainError`
- Impl: `src/core/errors.py:TenantInvalidoError`
- Impl: `src/core/errors.py:create_problem_response`
- Impl: `src/core/errors.py:register_exception_handlers`
- Impl: `src/core/audit/exceptions.py:AuditoriaImutavelError`
- Impl: `src/modules/auth/domain/exceptions.py:ContaBloqueadaError`
- Impl: `src/modules/auth/domain/exceptions.py:OtpRateLimitExcedidoError`
- Impl: `src/modules/identity/domain/exceptions.py:IdentificacaoObrigatoriaError`
- Impl: `src/modules/queue/domain/exceptions.py:AdmissaoFilaSuspensaError`
- Impl: `src/modules/queue/domain/exceptions.py:MedicoOcupadoError`
- Impl: `src/modules/triage/domain/exceptions.py:EmergenciaCriticaSamuError`
- Impl: `src/modules/consultation/domain/exceptions.py:PrescricaoFisicaObrigatoriaError`
- Impl: `src/modules/consultation/presentation/dependencies.py:exigir_rate_limit`

## Verificação

```bash
rg -n "code = |class \w+Error|status_code" src/core/errors.py | head -15
rg -n "status_code = (423|429|503)" src/
rg -n "ADMISSAO_FILA_SUSPENSA|CONTA_BLOQUEADA|OTP_RATE_LIMIT_EXCEEDED" src/
```

## Ver também

- [Documentation standards](../architecture-standards/documentation-standards.md)
- [Setup local](../../how-to/dev-environment/setup-local.md)
- [Create module endpoint](../../how-to/backend/create-module-endpoint.md)
- `docs/explanation/architecture/overview.md`
- `docs/explanation/architecture/compliance-and-telemedicine.md`
