"""Application service orchestrating FIDO2 / WebAuthn passkeys for patients."""

import base64
import hmac
import logging
import secrets
import time
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.audit import AtorPapel, AtorTipo, AuditTrailPort
from src.core.authz.roles import Role
from src.core.authz.token import create_access_token
from src.core.errors import TenantInvalidoError
from src.modules.auth.application.dtos import (
    VerificarOtpOutputDTO,
    WebAuthnAllowCredentialDTO,
    WebAuthnAuthenticatorSelectionDTO,
    WebAuthnAuthOptionsDTO,
    WebAuthnAuthVerifyCommand,
    WebAuthnPubKeyCredParamDTO,
    WebAuthnRegisterOptionsDTO,
    WebAuthnRegisterResultDTO,
    WebAuthnRegisterVerifyCommand,
    WebAuthnRpDTO,
    WebAuthnUserDTO,
)
from src.modules.auth.application.ports.active_attendance_lookup_port import (
    ActiveAttendanceLookupPort,
)
from src.modules.auth.application.ports.identity_reader_port import (
    IdentityReaderPort,
)
from src.modules.auth.application.services.webauthn_crypto import (
    decode_and_validate_client_data,
    extract_registration_key_and_count,
    verify_assertion_and_extract_sign_count,
)
from src.modules.auth.domain.exceptions import (
    PasskeyNaoEncontradaError,
    WebAuthnChallengeInvalidoError,
)

logger = logging.getLogger("medisync.auth.patient_webauthn")

WEBAUTHN_CHALLENGE_TTL_SECONDS = 60
_DEFAULT_ALLOWED_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


class PatientWebAuthnService:
    """Serviço de registro e autenticação WebAuthn / Passkeys para pacientes.

    Regras: RF-01, RF-07, ADR-005 (FIDO2/Passwordless), LGPD Art. 11 e US-14.
    Documentação: docs/user-stories/US-14-biometria-passkeys-webauthn.md
    """

    def __init__(
        self,
        *,
        jwt_secret: str,
        valkey_client: Redis | None = None,
        jwt_algorithm: str = "HS256",
        access_token_expire_minutes: int = 60,
        rp_id: str = "localhost",
        rp_name: str = "MediSync Express",
        allowed_origins: Sequence[str] = _DEFAULT_ALLOWED_ORIGINS,
        allow_memory_fallback: bool = True,
        identity_reader: IdentityReaderPort | None = None,
        active_attendance_lookup: ActiveAttendanceLookupPort | None = None,
        audit_trail: AuditTrailPort | None = None,
        session: AsyncSession | None = None,
    ) -> None:
        self._jwt_secret = jwt_secret
        self._valkey = valkey_client
        self._jwt_algorithm = jwt_algorithm
        self._access_token_expire_minutes = access_token_expire_minutes
        self._rp_id = rp_id
        self._rp_name = rp_name
        self._allowed_origins = tuple(allowed_origins)
        self._allow_memory_fallback = allow_memory_fallback
        self._identity_reader = identity_reader
        self._active_attendance = active_attendance_lookup
        self._audit_trail = audit_trail
        self._session = session
        self._memory_challenges: dict[str, tuple[str, float]] = {}

    async def _save_challenge(self, key: str, challenge: str) -> None:
        """Persist short-lived WebAuthn challenge in Valkey or test memory."""
        if self._valkey is not None:
            saved = await self._valkey_set(key, challenge)
            if saved:
                return
            if not self._allow_memory_fallback:
                raise WebAuthnChallengeInvalidoError(
                    "Serviço de desafios WebAuthn (Valkey) indisponível no momento."
                )
        elif not self._allow_memory_fallback:
            raise WebAuthnChallengeInvalidoError(
                "Serviço de desafios WebAuthn (Valkey) não configurado neste perfil."
            )

        expires_at = time.time() + WEBAUTHN_CHALLENGE_TTL_SECONDS
        self._memory_challenges[key] = (challenge, expires_at)

    async def _valkey_set(self, key: str, value: str) -> bool:
        if self._valkey is None:
            return False
        try:
            await self._valkey.set(  # pyright: ignore[reportUnknownMemberType]
                key, value, ex=WEBAUTHN_CHALLENGE_TTL_SECONDS
            )
            return True
        except Exception as exc:
            logger.warning("Valkey set webauthn challenge failed: %s", exc)
            return False

    async def _consume_valkey_challenge(self, key: str) -> str | None:
        if self._valkey is None:
            return None
        try:
            raw: bytes | str | None = await self._valkey.getdel(key)  # pyright: ignore[reportUnknownMemberType]
            if raw is None:
                return None
            if isinstance(raw, (bytes, bytearray)):
                return raw.decode("utf-8")
            return str(raw)
        except Exception as exc:
            logger.warning("Valkey getdel webauthn challenge failed: %s", exc)
            if not self._allow_memory_fallback:
                raise WebAuthnChallengeInvalidoError(
                    "Falha ao consumir desafio WebAuthn no armazenamento distribuído."
                ) from exc
            return None

    async def _consume_challenge(self, key: str) -> str | None:
        """Fetch and atomically invalidate a stored WebAuthn challenge."""
        if self._valkey is not None:
            valkey_val = await self._consume_valkey_challenge(key)
            if valkey_val is not None:
                self._memory_challenges.pop(key, None)
                return valkey_val
            if not self._allow_memory_fallback:
                return None

        mem_entry = self._memory_challenges.pop(key, None)
        if mem_entry is None:
            return None
        challenge, expires_at = mem_entry
        if time.time() > expires_at:
            return None
        return challenge

    async def _resolve_user_descriptor(
        self, organizacao_id: int, paciente_id: UUID
    ) -> WebAuthnUserDTO:
        user_handle = base64.urlsafe_b64encode(str(paciente_id).encode("utf-8")).decode(
            "ascii"
        )
        display = f"Paciente {str(paciente_id)[:8]}"
        if self._identity_reader is not None:
            pac = await self._identity_reader.buscar_paciente_por_id(
                organizacao_id=organizacao_id,
                paciente_id=paciente_id,
            )
            if pac is not None and pac.nome_completo.strip():
                display = pac.nome_completo.strip()
        return WebAuthnUserDTO(
            id=user_handle.rstrip("="),
            name=display,
            displayName=display,
        )

    async def _record_audit_safe(
        self,
        *,
        organizacao_id: int,
        paciente_id: UUID,
        tipo_evento: str,
        payload: dict[str, Any],
    ) -> None:
        if self._audit_trail is None:
            return
        await self._audit_trail.record_event(
            organizacao_id=organizacao_id,
            tipo_evento=tipo_evento,
            ator_tipo=AtorTipo.PACIENTE.value,
            ator_papel=AtorPapel.PACIENTE.value,
            ator_id=paciente_id,
            payload=payload,
        )

    async def _resolve_active_attendance(
        self, organizacao_id: int, paciente_id: UUID
    ) -> UUID | None:
        if self._active_attendance is None:
            return None
        return await self._active_attendance.buscar_atendimento_ativo_paciente(
            organizacao_id=organizacao_id,
            paciente_id=paciente_id,
        )

    def _validate_tenant(self, organizacao_id: int) -> None:
        if organizacao_id <= 0:
            raise TenantInvalidoError(
                f"Identificador da organização '{organizacao_id}' deve ser "
                "positivo; esperado inteiro > 0."
            )

    def _validate_identity_reader(self) -> IdentityReaderPort:
        if self._identity_reader is None:
            raise ValueError(
                f"IdentityReaderPort não configurado no PatientWebAuthnService "
                f"(recebido: {self._identity_reader!r}; esperado instância de "
                "IdentityReaderPort)."
            )
        return self._identity_reader

    async def gerar_opcoes_registro(
        self,
        organizacao_id: int,
        paciente_id: UUID,
    ) -> WebAuthnRegisterOptionsDTO:
        """Gera opções criptográficas WebAuthn para cadastro de biometria do aparelho.

        Regras: RF-01, ADR-005 e US-14 (§3).
        Documentação: docs/user-stories/US-14-biometria-passkeys-webauthn.md
        """
        self._validate_tenant(organizacao_id)
        challenge = secrets.token_urlsafe(32)
        await self._save_challenge(
            f"webauthn:reg:{organizacao_id}:{paciente_id}", challenge
        )
        user_dto = await self._resolve_user_descriptor(organizacao_id, paciente_id)
        return WebAuthnRegisterOptionsDTO(
            challenge=challenge,
            rp=WebAuthnRpDTO(name=self._rp_name, id=self._rp_id),
            user=user_dto,
            pubKeyCredParams=[
                WebAuthnPubKeyCredParamDTO(alg=-7, type="public-key"),
                WebAuthnPubKeyCredParamDTO(alg=-257, type="public-key"),
            ],
            timeout=WEBAUTHN_CHALLENGE_TTL_SECONDS * 1000,
            attestation="none",
            authenticatorSelection=WebAuthnAuthenticatorSelectionDTO(),
        )

    async def verificar_registro(
        self,
        command: WebAuthnRegisterVerifyCommand,
    ) -> WebAuthnRegisterResultDTO:
        """Valida desafio WebAuthn e persiste chave pública Passkey do paciente.

        Regras: RF-01, ADR-001 (§6), ADR-005, ADR-007 e US-14 (PASSKEY_REGISTRADA).
        Documentação: docs/user-stories/US-14-biometria-passkeys-webauthn.md
        """
        self._validate_tenant(command.organizacao_id)
        reader = self._validate_identity_reader()
        reg_key = f"webauthn:reg:{command.organizacao_id}:{command.paciente_id}"
        expected_challenge = await self._consume_challenge(reg_key)
        if expected_challenge is None:
            raise WebAuthnChallengeInvalidoError(
                "Desafio WebAuthn de registro ausente ou expirado para o paciente "
                f"'{command.paciente_id}' (org '{command.organizacao_id}'); "
                "esperado desafio ativo gerado há menos de "
                f"{WEBAUTHN_CHALLENGE_TTL_SECONDS}s."
            )

        client_challenge, _ = decode_and_validate_client_data(
            response=command.response,
            expected_type="webauthn.create",
            allowed_origins=self._allowed_origins,
        )
        if not hmac.compare_digest(client_challenge, expected_challenge):
            raise WebAuthnChallengeInvalidoError(
                f"Desafio WebAuthn divergente no clientDataJSON: recebido "
                f"{client_challenge!r}, esperado '{expected_challenge}'."
            )

        public_key, initial_sign_count = extract_registration_key_and_count(
            credential_id=command.id,
            response=command.response,
            rp_id=self._rp_id,
        )
        passkey = await reader.registrar_passkey_paciente(
            organizacao_id=command.organizacao_id,
            paciente_id=command.paciente_id,
            credential_id=command.id,
            public_key=public_key,
            sign_count=initial_sign_count,
            device_name=command.device_name,
        )
        await self._record_audit_safe(
            organizacao_id=command.organizacao_id,
            paciente_id=command.paciente_id,
            tipo_evento="PASSKEY_REGISTRADA",
            payload={
                "credencial_id": passkey.credential_id,
                "device_name": command.device_name or "Dispositivo Biométrico",
            },
        )
        if self._session is not None:
            await self._session.commit()

        return WebAuthnRegisterResultDTO(
            status="registrado",
            credencial_id=passkey.credential_id,
        )

    async def gerar_opcoes_autenticacao(
        self,
        organizacao_id: int,
        paciente_id: UUID | None = None,
    ) -> WebAuthnAuthOptionsDTO:
        """Gera opções e desafio FIDO2 para retorno biométrico do paciente em 1 toque.

        Regras: RF-01, ADR-005 e US-14 (§3).
        Documentação: docs/user-stories/US-14-biometria-passkeys-webauthn.md
        """
        self._validate_tenant(organizacao_id)
        challenge = secrets.token_urlsafe(32)
        await self._save_challenge(
            f"webauthn:auth:{organizacao_id}:{challenge}", challenge
        )

        allowed: list[WebAuthnAllowCredentialDTO] = []
        if paciente_id is not None and self._identity_reader is not None:
            passkeys = await self._identity_reader.listar_passkeys_paciente(
                organizacao_id=organizacao_id,
                paciente_id=paciente_id,
            )
            allowed = [
                WebAuthnAllowCredentialDTO(id=pk.credential_id, type="public-key")
                for pk in passkeys
            ]

        return WebAuthnAuthOptionsDTO(
            challenge=challenge,
            rpId=self._rp_id,
            allowCredentials=allowed,
            timeout=WEBAUTHN_CHALLENGE_TTL_SECONDS * 1000,
            userVerification="preferred",
        )

    async def verificar_autenticacao(
        self,
        command: WebAuthnAuthVerifyCommand,
    ) -> VerificarOtpOutputDTO:
        """Valida asserção Passkey, atualiza sign_count e emite JWT Role.PACIENTE.

        Regras: RF-01, ADR-001 (§6), ADR-005, ADR-007 e US-14 (§2 Cenário 2).
        Documentação: docs/user-stories/US-14-biometria-passkeys-webauthn.md
        """
        self._validate_tenant(command.organizacao_id)
        reader = self._validate_identity_reader()
        client_challenge, raw_cdj_bytes = decode_and_validate_client_data(
            response=command.response,
            expected_type="webauthn.get",
            allowed_origins=self._allowed_origins,
        )
        expected_challenge = await self._consume_challenge(
            f"webauthn:auth:{command.organizacao_id}:{client_challenge}"
        )
        if expected_challenge is None:
            raise WebAuthnChallengeInvalidoError(
                "Desafio WebAuthn de autenticação ausente ou expirado para a "
                f"organização '{command.organizacao_id}' "
                f"(challenge recebido: {client_challenge!r}); "
                "esperado desafio ativo gerado há menos de "
                f"{WEBAUTHN_CHALLENGE_TTL_SECONDS}s."
            )

        if not hmac.compare_digest(client_challenge, expected_challenge):
            raise WebAuthnChallengeInvalidoError(
                f"Desafio WebAuthn divergente no clientDataJSON: recebido "
                f"'{client_challenge}', esperado '{expected_challenge}'."
            )

        passkey = await reader.buscar_passkey_por_credencial(
            organizacao_id=command.organizacao_id,
            credential_id=command.id,
        )
        if passkey is None:
            raise PasskeyNaoEncontradaError(
                f"Credencial Passkey '{command.id}' não encontrada na organização "
                f"'{command.organizacao_id}'; esperado credential_id previamente "
                "registrado para o paciente."
            )

        novo_sign_count = verify_assertion_and_extract_sign_count(
            passkey_id=passkey.credential_id,
            public_key_b64=passkey.public_key,
            current_sign_count=passkey.sign_count,
            rp_id=self._rp_id,
            response=command.response,
            raw_cdj_bytes=raw_cdj_bytes,
        )
        await reader.atualizar_sign_count_passkey(
            organizacao_id=command.organizacao_id,
            credential_id=passkey.credential_id,
            novo_sign_count=novo_sign_count,
        )

        atendimento_id = await self._resolve_active_attendance(
            command.organizacao_id, passkey.paciente_id
        )
        await self._record_audit_safe(
            organizacao_id=command.organizacao_id,
            paciente_id=passkey.paciente_id,
            tipo_evento="LOGIN_PASSKEY_SUCESSO",
            payload={
                "credencial_id": passkey.credential_id,
                "sign_count": novo_sign_count,
            },
        )
        if self._session is not None:
            await self._session.commit()

        token = create_access_token(
            usuario_id=passkey.paciente_id,
            organizacao_id=command.organizacao_id,
            papel=Role.PACIENTE.value,
            secret_key=self._jwt_secret,
            algorithm=self._jwt_algorithm,
            expire_minutes=self._access_token_expire_minutes,
        )
        return VerificarOtpOutputDTO(
            access_token=token,
            token_type="bearer",  # noqa: S106
            expires_in=self._access_token_expire_minutes * 60,
            paciente_id=passkey.paciente_id,
            role=Role.PACIENTE.value,
            atendimento_id=atendimento_id,
        )
