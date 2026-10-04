# RLS Pública — Validação de Documentos (Fase 6)

## Decisão

Rota pública sem tenant usa bypass via role `medisync` (superuser + BYPASSRLS),
sem `SET LOCAL ROLE medisync_app`. Rotas com tenant usam `medisync_app`
(NOBYPASSRLS) com `app.current_tenant_id` + FORCE RLS.

- `medisync`: rolsuper=true, rolbypassrls=true → bypassa RLS mesmo com FORCE.
- `medisync_app`: rolsuper=false, rolbypassrls=false → RLS enforced.
- Listener `src/core/database.py:_set_tenant_rls_on_begin`:
  sem tenant → `set_config('', true)`, sem SET ROLE → fica `medisync` (bypass).
  com tenant → `SET LOCAL ROLE medisync_app` + tenant → RLS filtra.

## Por que seguro

- Lookup por UUIDv7 não-adivinhável (token QR Code).
- Resposta só metadados + nome/CPF mascarados LGPD (`src/core/privacy.py`).
- Rate-limit sliding-window Valkey: validate 30/60s por IP, download 20/60s por IP,
  fail-open se Valkey fora, 429 com Retry-After.
- Download via presigned curta (60–3600s, padrão 300s).
- Sem fabricar médico/paciente: ausente → `DocumentoIntegridadeError` 500 + log.
- Sem bypass genérico: só leitura por PK + directory SQL isolado em infra.

## Alternativa rejeitada

Role/serviço novo com BYPASSRLS exigiria migration + grants. Tenant sistema
exigiria descobrir org antes do lookup (chicken-egg). Bypass superuser já
existe, é mínimo, testado.

## Teste

`tests/integration/test_validation_public_rls.py`:
cria org/medico/paciente/atendimento/documento com tenant, depois chama
`GET /api/v1/documents/validate/{id}` e `download?redirect=false` SEM
`X-Tenant-ID`. Deve retornar 200 com mascaramento + presigned. Com RLS ligado,
sem tenant, ainda enxerga via bypass `medisync`. Falha se virar `medisync_app`
sem tenant (zero linhas — fail-safe).
