# Divergência claims: TokenPayloadDTO vs AuthenticatedUser

Data: 2026-10-04. Branch: refactor/routers-di. Escopo: item 5.2 (/auth/me).

## Evidência (JWT real via JWTTokenService)

Executado `gerar_tokens(usuario_id=11111111-..., organizacao_id=99, papel=MEDICO)`
e decodificado pelas duas vias:

- `AuthService.validar_access_token` -> `JWTTokenService.validar_access_token`
  -> `TokenPayloadDTO(sub=UUID(...), org_id=99, papel=MEDICO,
  exp=datetime UTC, jti='01a1081e-...', type='access')`
- `core.authz.token.decode_access_token`
  -> `AuthenticatedUser(usuario_id=UUID(...), organizacao_id=99, papel=MEDICO,
  token_id=UUID('01a1081e-...'), raw_token='eyJ...')`

Asserções verificadas em runtime:
- `payload.sub == user.usuario_id` -> True
- `payload.org_id == user.organizacao_id` -> True
- `payload.papel == user.papel` -> True

## Iguais em valor

| TokenPayloadDTO | AuthenticatedUser | Resultado |
|---|---|---|
| sub: UUID | usuario_id: UUID | iguais |
| org_id: int | organizacao_id: int | iguais |
| papel: str | papel: str | iguais |

## Divergentes (nomenclatura / tipo / retenção)

1. `sub` vs `usuario_id`: mesmo UUID, nome diferente.
2. `org_id` vs `organizacao_id`: mesmo int, nome diferente.
3. `jti: str` vs `token_id: UUID`: mesmo uuid7 em valor,
   tipo divergente (`str` no DTO, `UUID(...)` no principal central).
   `decode_access_token` faz `UUID(str(payload["jti"]))`; `JWTTokenService`
   mantém `str(claims["jti"])`.
4. `exp: datetime` retido só em `TokenPayloadDTO`; `AuthenticatedUser`
   valida `verify_exp=True` e descarta expiração.
5. `type: str` retido só em `TokenPayloadDTO`; `AuthenticatedUser`
   valida `type == "access"` e descarta.
6. `raw_token: str` existe só em `AuthenticatedUser`.
7. Erros: via serviço levanta `TokenExpiradoError` / `TokenInvalidoError`
   (subclasses `UnauthorizedError` -> 401); via central levanta
   `UnauthorizedError` direto (-> 401). Status igual, `title/code`
   divergem (`TOKEN_EXPIRADO` / `TOKEN_INVALIDO` vs `UNAUTHORIZED` genérico).
8. Decode central exige `require: [sub, org_id, papel, exp, jti, type]`;
   `JWTTokenService._decode_token` não passa `require`, checa
   `KeyError/ValueError` manual. Efeito prático igual para tokens gerados
   pelo emissor atual, mensagens divergem.

## Unificação adotada (sem inventar formato)

`GET /auth/me` passa a usar decode central via `CurrentUserDep`
(`get_current_user` -> `decode_access_token`), removendo parse manual
`Bearer/Header` e `service.validar_access_token` do router.
Mapeamento usado no service:

- `user.usuario_id` -> `obter_usuario_por_id(usuario_id, ...)`
- `user.organizacao_id` -> `obter_usuario_por_id(..., organizacao_id)`

Nenhum formato novo criado; nomes centrais (`usuario_id`,
`organizacao_id`) prevalecem no router. `TokenPayloadDTO` mantido
para login/refresh; sem alteração em guards clínicos, LiveKit, WS,
tenant-token, posse paciente (fora escopo).
