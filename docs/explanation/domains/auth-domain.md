# Auth Domain

> Autenticação OWASP com Argon2id, JWT curto, lockout progressivo, rate limit na borda e revogação distribuída via Valkey.

## 1. Contexto & Regras

- **Hash Seguro**: Argon2id via `PasswordHasherPort`.
- **JWT de Curto Prazo e Rotação**: Access token efêmero e refresh token com rotação de uso único.
- **Revogação Distribuída**: Invalidação imediata de tokens no logout ou após rotação via `TokenRevocationPort` / `ValkeyTokenRevocation` (`token:revoked:{jti}` com TTL de expiração).

## 2. Onde no código

- `src/modules/auth/application/ports/token_revocation_port.py` (Port de revogação distribuída)
- `src/modules/auth/infrastructure/valkey_token_revocation.py` (Adapter Valkey / fake em memória)
- `src/modules/auth/application/services/auth_service.py`
- `src/modules/auth/presentation/routers/auth_router.py`
- `tests/unit/test_token_revocation.py`

## 3. Ver também

- [Domains Index](./index.md)
