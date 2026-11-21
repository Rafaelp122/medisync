"""Application service for patient FIDO2/WebAuthn Passkeys (US-14, ADR-005)."""

import base64
import hmac
import secrets
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.audit import AtorPapel, AtorTipo, AuditTrailPort
from src.core.authz.roles import Role
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
from src.modules.auth.application.ports.challenge_store_port import (
    ChallengeStorePort,
)
from src.modules.auth.application.ports.identity_reader_port import (
    IdentityReaderPort,
)
from src.modules.auth.application.ports.identity_writer_port import (
    IdentityWriterPort,
)
from src.modules.auth.application.ports.token_service_port import TokenServicePort
from src.modules.auth.application.services.webauthn_crypto import (
    decode_and_validate_client_data,
    extract_registration_key_and_count,
    verify_assertion_and_extract_sign_count,
)
from src.modules.auth.domain.exceptions import (
    PasskeyNaoEncontradaError,
    WebAuthnChallengeInvalidoError,
)

WEBAUTHN_CHALLENGE_TTL_SECONDS = 300
_DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


class PatientWebAuthnService:
    """Gerencia registro e autenticação biométrica Passkey FIDO2/WebAuthn de pacientes.

    Regras: RF-01, RF-07, ADR-005 (FIDO2/Passwordless), ADR-013, LGPD Art. 11 e US-14.
    Documentação: docs/user-stories/US-14-biometria-passkeys-webauthn.md
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        token_service: TokenServicePort,
        challenge_store: ChallengeStorePort,
        identity_reader: IdentityReaderPort,
        identity_writer: IdentityWriterPort,
        rp_id: str = "localhost",
        rp_name: str = "MediSync Express",
        allowed_origins: Sequence[str] = _DEFAULT_ALLOWED_ORIGINS,
        active_attendance_lookup: ActiveAttendanceLookupPort | None = None,
        audit_trail: AuditTrailPort | None = None,
    ) -> None:
        self._session = session
        self._token_service = token_service
        self._challenge_store = challenge_store
        self._identity_reader = identity_reader
        self._identity_writer = identity_writer
        self._rp_id = rp_id
        self._rp_name = rp_name
        self._allowed_origins = tuple(allowed_origins)
        self._active_attendance = active_attendance_lookup
        self._audit_trail = audit_trail

    async def _resolve_user_descriptor(self, paciente_id: UUID) -> WebAuthnUserDTO:
        user_handle = base64.urlsafe_b64encode(str(paciente_id).encode("utf-8")).decode(
            "ascii"
        )
        display = f"Paciente {str(paciente_id)[:8]}"
        pac = await self._identity_reader.buscar_paciente_por_id(
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
        paciente_id: UUID,
        tipo_evento: str,
        payload: dict[str, Any],
    ) -> None:
        if self._audit_trail is None:
            return
        await self._audit_trail.record_event(
            tipo_evento=tipo_evento,
            ator_tipo=AtorTipo.PACIENTE.value,
            ator_papel=AtorPapel.PACIENTE.value,
            ator_id=paciente_id,
            payload=payload,
        )

    async def _resolve_active_attendance(self, paciente_id: UUID) -> UUID | None:
        if self._active_attendance is None:
            return None
        return await self._active_attendance.buscar_atendimento_ativo_paciente(
            paciente_id=paciente_id,
        )

    async def gerar_opcoes_registro(
        self,
        paciente_id: UUID,
    ) -> WebAuthnRegisterOptionsDTO:
        """Gera opções WebAuthn indexadas por desafio único evitando colisão entre abas.

        Regras: RF-01, ADR-005, ADR-013 e US-14 (§3).
        Documentação: docs/user-stories/US-14-biometria-passkeys-webauthn.md
        """
        challenge = secrets.token_urlsafe(32)
        await self._challenge_store.store_one_time(
            key=f"webauthn:reg:{paciente_id}:{challenge}",
            value=challenge,
            ttl_seconds=WEBAUTHN_CHALLENGE_TTL_SECONDS,
        )
        user_dto = await self._resolve_user_descriptor(paciente_id)
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
        """Valida desafio WebAuthn de uso único e persiste chave pública Passkey.

        Regras: RF-01, ADR-001 (§6), ADR-005, ADR-007, ADR-013 e
        US-14 (PASSKEY_REGISTRADA).
        Documentação: docs/user-stories/US-14-biometria-passkeys-webauthn.md
        """
        client_challenge, _ = decode_and_validate_client_data(
            response=command.response,
            expected_type="webauthn.create",
            allowed_origins=self._allowed_origins,
        )
        reg_key = f"webauthn:reg:{command.paciente_id}:{client_challenge}"
        expected_challenge = await self._challenge_store.consume_one_time(reg_key)
        if expected_challenge is None:
            raise WebAuthnChallengeInvalidoError(
                "Desafio WebAuthn de registro divergente, ausente ou expirado para "
                f"o paciente '{command.paciente_id}' (challenge={client_challenge!r}); "
                f"esperado desafio ativo gerado há menos de "
                f"{WEBAUTHN_CHALLENGE_TTL_SECONDS}s."
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
        passkey = await self._identity_writer.registrar_passkey_paciente(
            paciente_id=command.paciente_id,
            credential_id=command.id,
            public_key=public_key,
            sign_count=initial_sign_count,
            device_name=command.device_name,
        )
        await self._record_audit_safe(
            paciente_id=command.paciente_id,
            tipo_evento="PASSKEY_REGISTRADA",
            payload={
                "credencial_id": passkey.credential_id,
                "device_name": command.device_name or "Dispositivo Biométrico",
            },
        )
        await self._session.commit()

        return WebAuthnRegisterResultDTO(
            status="registrado",
            credencial_id=passkey.credential_id,
        )

    async def gerar_opcoes_autenticacao(
        self,
        paciente_id: UUID | None = None,
    ) -> WebAuthnAuthOptionsDTO:
        """Gera opções e desafio FIDO2 para retorno biométrico do paciente em 1 toque.

        Regras: RF-01, ADR-005, ADR-013 e US-14 (§3).
        Documentação: docs/user-stories/US-14-biometria-passkeys-webauthn.md
        """
        challenge = secrets.token_urlsafe(32)
        await self._challenge_store.store_one_time(
            key=f"webauthn:auth:{challenge}",
            value=challenge,
            ttl_seconds=WEBAUTHN_CHALLENGE_TTL_SECONDS,
        )

        allowed: list[WebAuthnAllowCredentialDTO] = []
        if paciente_id is not None:
            passkeys = await self._identity_reader.listar_passkeys_paciente(
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

        Regras: RF-01, ADR-001 (§6), ADR-005, ADR-007, ADR-013 e US-14 (§2 Cenário 2).
        Documentação: docs/user-stories/US-14-biometria-passkeys-webauthn.md
        """
        client_challenge, raw_cdj_bytes = decode_and_validate_client_data(
            response=command.response,
            expected_type="webauthn.get",
            allowed_origins=self._allowed_origins,
        )
        expected_challenge = await self._challenge_store.consume_one_time(
            f"webauthn:auth:{client_challenge}"
        )
        if expected_challenge is None:
            raise WebAuthnChallengeInvalidoError(
                "Desafio WebAuthn de autenticação ausente ou expirado "
                f"(challenge recebido: {client_challenge!r}); "
                "esperado desafio ativo gerado há menos de "
                f"{WEBAUTHN_CHALLENGE_TTL_SECONDS}s."
            )

        if not hmac.compare_digest(client_challenge, expected_challenge):
            raise WebAuthnChallengeInvalidoError(
                f"Desafio WebAuthn divergente no clientDataJSON: recebido "
                f"'{client_challenge}', esperado '{expected_challenge}'."
            )

        passkey = await self._identity_reader.buscar_passkey_por_credencial(
            credential_id=command.id,
        )
        if passkey is None:
            raise PasskeyNaoEncontradaError(
                f"Credencial Passkey '{command.id}' não encontrada na plataforma; "
                "esperado credential_id previamente registrado para o paciente."
            )

        novo_sign_count = verify_assertion_and_extract_sign_count(
            passkey_id=passkey.credential_id,
            public_key_b64=passkey.public_key,
            current_sign_count=passkey.sign_count,
            rp_id=self._rp_id,
            response=command.response,
            raw_cdj_bytes=raw_cdj_bytes,
        )
        await self._identity_writer.atualizar_sign_count_passkey(
            credential_id=passkey.credential_id,
            novo_sign_count=novo_sign_count,
        )

        atendimento_id = await self._resolve_active_attendance(passkey.paciente_id)
        await self._record_audit_safe(
            paciente_id=passkey.paciente_id,
            tipo_evento="LOGIN_PASSKEY_SUCESSO",
            payload={
                "credencial_id": passkey.credential_id,
                "sign_count": novo_sign_count,
            },
        )
        await self._session.commit()

        token_pair = self._token_service.gerar_tokens(
            usuario_id=passkey.paciente_id,
            papel=Role.PACIENTE.value,
        )
        return VerificarOtpOutputDTO(
            access_token=token_pair.access_token,
            token_type="bearer",  # noqa: S106
            expires_in=token_pair.expires_in,
            paciente_id=passkey.paciente_id,
            role=Role.PACIENTE.value,
            atendimento_id=atendimento_id,
        )
