"""JWT token issuer and validator adapter implementing TokenServicePort."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt

from src.core.uuid7 import uuid7
from src.modules.auth.application.dtos import TokenPairDTO, TokenPayloadDTO
from src.modules.auth.application.ports.token_service_port import TokenServicePort
from src.modules.auth.domain.exceptions import (
    TokenExpiradoError,
    TokenInvalidoError,
)


class JWTTokenService(TokenServicePort):
    """JWT Token generator and validator using HMAC-SHA256 and UTC timestamps."""

    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 15,
        refresh_token_expire_days: int = 7,
    ) -> None:
        self._secret_key = secret_key
        self._algorithm = algorithm
        self._access_expire_minutes = access_token_expire_minutes
        self._refresh_expire_days = refresh_token_expire_days

    def gerar_tokens(
        self,
        usuario_id: UUID,
        organizacao_id: int,
        papel: str,
    ) -> TokenPairDTO:
        """Issue access and refresh token pair with distinct jti claims."""
        now = datetime.now(UTC)
        access_exp = now + timedelta(minutes=self._access_expire_minutes)
        refresh_exp = now + timedelta(days=self._refresh_expire_days)

        access_payload: dict[str, Any] = {
            "sub": str(usuario_id),
            "org_id": organizacao_id,
            "papel": papel,
            "iat": int(now.timestamp()),
            "exp": int(access_exp.timestamp()),
            "jti": str(uuid7()),
            "type": "access",
        }
        refresh_payload: dict[str, Any] = {
            "sub": str(usuario_id),
            "org_id": organizacao_id,
            "papel": papel,
            "iat": int(now.timestamp()),
            "exp": int(refresh_exp.timestamp()),
            "jti": str(uuid7()),
            "type": "refresh",
        }

        access_token: str = jwt.encode(  # pyright: ignore[reportUnknownMemberType]
            access_payload, self._secret_key, algorithm=self._algorithm
        )
        refresh_token: str = jwt.encode(  # pyright: ignore[reportUnknownMemberType]
            refresh_payload, self._secret_key, algorithm=self._algorithm
        )

        return TokenPairDTO(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",  # noqa: S106
            expires_in=self._access_expire_minutes * 60,
            refresh_expires_in=self._refresh_expire_days * 86400,
        )

    def validar_access_token(self, token: str) -> TokenPayloadDTO:
        """Validate signature, expiration, and access type of a JWT token."""
        return self._decode_token(token, expected_type="access")

    def validar_refresh_token(self, token: str) -> TokenPayloadDTO:
        """Validate signature, expiration, and refresh type of a JWT token."""
        return self._decode_token(token, expected_type="refresh")

    def _decode_token(self, token: str, expected_type: str) -> TokenPayloadDTO:
        try:
            claims: dict[str, Any] = jwt.decode(  # pyright: ignore[reportUnknownMemberType]
                token,
                self._secret_key,
                algorithms=[self._algorithm],
            )
        except jwt.ExpiredSignatureError as err:
            raise TokenExpiradoError(f"Token de {expected_type} expirado.") from err
        except jwt.InvalidTokenError as err:
            raise TokenInvalidoError(
                f"Token de {expected_type} inválido ou adulterado."
            ) from err

        token_type = str(claims.get("type", ""))
        if token_type != expected_type:
            raise TokenInvalidoError(
                f"Tipo de token inválido: esperado '{expected_type}', "
                f"recebido '{token_type}'."
            )

        try:
            sub = UUID(str(claims["sub"]))
            org_id = int(claims["org_id"])
            papel = str(claims["papel"])
            exp_ts = int(claims["exp"])
            exp = datetime.fromtimestamp(exp_ts, tz=UTC)
            jti = str(claims["jti"])
        except (KeyError, ValueError) as err:
            raise TokenInvalidoError(
                "Estrutura de claims do token incompleta ou corrompida."
            ) from err

        return TokenPayloadDTO(
            sub=sub,
            org_id=org_id,
            papel=papel,
            exp=exp,
            jti=jti,
            type=token_type,
        )
