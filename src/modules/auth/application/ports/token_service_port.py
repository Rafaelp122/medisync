"""Port interface for JWT token issuance, decoding, and session lifecycle."""

from typing import Protocol, runtime_checkable
from uuid import UUID

from src.modules.auth.application.dtos import TokenPairDTO, TokenPayloadDTO


@runtime_checkable
class TokenServicePort(Protocol):
    """Port for JWT access/refresh token generation and cryptographical validation."""

    def gerar_tokens(
        self,
        usuario_id: UUID,
        organizacao_id: int,
        papel: str,
    ) -> TokenPairDTO:
        """Issue a pair of short-lived access token and rotatable refresh token."""
        ...

    def validar_access_token(self, token: str) -> TokenPayloadDTO:
        """Validate signature, type, and expiration of access token."""
        ...

    def validar_refresh_token(self, token: str) -> TokenPayloadDTO:
        """Validate signature, type, and expiration of refresh token."""
        ...
