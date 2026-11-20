"""FastAPI thin router for patient FIDO2 / WebAuthn passkeys (US-14)."""

from typing import Annotated

from fastapi import APIRouter, Body, status

from src.modules.auth.application.dtos import (
    WebAuthnAuthVerifyCommand,
    WebAuthnRegisterVerifyCommand,
)
from src.modules.auth.composition import PatientWebAuthnServiceDep
from src.modules.auth.presentation.dependencies import PatientAuthDep
from src.modules.auth.presentation.schemas import (
    VerificarOtpResponse,
    WebAuthnAuthOptionsRequest,
    WebAuthnAuthOptionsResponse,
    WebAuthnAuthVerifyRequest,
    WebAuthnRegisterOptionsResponse,
    WebAuthnRegisterVerifyRequest,
    WebAuthnRegisterVerifyResponse,
)

patient_webauthn_router = APIRouter(
    prefix="/auth/patient/webauthn",
    tags=["Autenticação de Pacientes (WebAuthn)"],
)


@patient_webauthn_router.post(
    "/register/options",
    status_code=status.HTTP_200_OK,
    summary="Gerar opções e desafio para cadastro de biometria Passkey (US-14)",
    operation_id="post_auth_patient_webauthn_register_options",
)
async def register_options(
    paciente_id: PatientAuthDep,
    service: PatientWebAuthnServiceDep,
) -> WebAuthnRegisterOptionsResponse:
    """Generate WebAuthn PublicKeyCredentialCreationOptions for patient."""
    dto = await service.gerar_opcoes_registro(paciente_id=paciente_id)
    return WebAuthnRegisterOptionsResponse.model_validate(dto)


@patient_webauthn_router.post(
    "/register/verify",
    status_code=status.HTTP_200_OK,
    summary="Verificar atestação e persistir chave pública Passkey do paciente",
    operation_id="post_auth_patient_webauthn_register_verify",
)
async def register_verify(
    body: Annotated[WebAuthnRegisterVerifyRequest, Body()],
    paciente_id: PatientAuthDep,
    service: PatientWebAuthnServiceDep,
) -> WebAuthnRegisterVerifyResponse:
    """Verify WebAuthn registration response and bind public key to patient."""
    cmd = WebAuthnRegisterVerifyCommand(
        paciente_id=paciente_id,
        id=body.id,
        raw_id=body.rawId,
        response=body.response,
        type=body.type,
        device_name=body.device_name,
    )
    dto = await service.verificar_registro(cmd)
    return WebAuthnRegisterVerifyResponse.model_validate(dto)


@patient_webauthn_router.post(
    "/authenticate/options",
    status_code=status.HTTP_200_OK,
    summary="Gerar desafio criptográfico para login em 1 toque via Passkey (US-14)",
    operation_id="post_auth_patient_webauthn_authenticate_options",
)
async def authenticate_options(
    service: PatientWebAuthnServiceDep,
    body: Annotated[WebAuthnAuthOptionsRequest | None, Body()] = None,
) -> WebAuthnAuthOptionsResponse:
    """Generate WebAuthn PublicKeyCredentialRequestOptions for patient login."""
    dto = await service.gerar_opcoes_autenticacao(
        paciente_id=body.paciente_id if body is not None else None,
    )
    return WebAuthnAuthOptionsResponse.model_validate(dto)


@patient_webauthn_router.post(
    "/authenticate/verify",
    status_code=status.HTTP_200_OK,
    summary="Validar asserção Passkey e emitir token Bearer Role.PACIENTE",
    operation_id="post_auth_patient_webauthn_authenticate_verify",
)
async def authenticate_verify(
    body: Annotated[WebAuthnAuthVerifyRequest, Body()],
    service: PatientWebAuthnServiceDep,
) -> VerificarOtpResponse:
    """Verify WebAuthn assertion and issue patient JWT access token."""
    cmd = WebAuthnAuthVerifyCommand(
        id=body.id,
        raw_id=body.rawId,
        response=body.response,
        type=body.type,
    )
    dto = await service.verificar_autenticacao(cmd)
    return VerificarOtpResponse.model_validate(dto)
