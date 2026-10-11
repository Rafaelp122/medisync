"""FastAPI router for passwordless patient OTP authentication."""

from typing import Annotated

from fastapi import APIRouter, Body, status

from src.core.dependencies import TenantDep
from src.modules.auth.composition import PatientAuthServiceDep
from src.modules.auth.presentation.schemas import (
    SolicitarOtpRequest,
    SolicitarOtpResponse,
    VerificarOtpRequest,
    VerificarOtpResponse,
)

patient_auth_router = APIRouter(
    tags=["Auth Paciente"],
)


@patient_auth_router.post(
    "/auth/patient/otp/request",
    status_code=status.HTTP_200_OK,
    summary="Solicitar código OTP para autenticação passwordless",
    description=(
        "Envia um código OTP de 6 dígitos via SMS para o telefone informado, "
        "com controle de taxa de até 3 envios por janela de 15 minutos."
    ),
)
@patient_auth_router.post(
    "/pacientes/auth/otp/solicitar",
    status_code=status.HTTP_200_OK,
    summary="Solicitar código OTP para autenticação passwordless (alias)",
    description=(
        "Envia um código OTP de 6 dígitos via SMS para o telefone informado, "
        "com controle de taxa de até 3 envios por janela de 15 minutos."
    ),
    include_in_schema=False,
)
async def request_otp(
    body: Annotated[SolicitarOtpRequest, Body()],
    tenant_id: TenantDep,
    service: PatientAuthServiceDep,
) -> SolicitarOtpResponse:
    """Request an OTP verification code via SMS."""
    result = await service.solicitar_otp(tenant_id, body)
    return SolicitarOtpResponse.model_validate(result)


@patient_auth_router.post(
    "/auth/patient/otp/verify",
    status_code=status.HTTP_200_OK,
    summary="Verificar código OTP e obter token de paciente",
    description=(
        "Valida o código OTP informado e emite um token Bearer JWT leve "
        "com claim papel='PACIENTE' para rastreamento de fila e teleconsulta."
    ),
)
@patient_auth_router.post(
    "/pacientes/auth/otp/verificar",
    status_code=status.HTTP_200_OK,
    summary="Verificar código OTP e obter token de paciente (alias)",
    description=(
        "Valida o código OTP informado e emite um token Bearer JWT leve "
        "com claim papel='PACIENTE' para rastreamento de fila e teleconsulta."
    ),
    include_in_schema=False,
)
async def verify_otp(
    body: Annotated[VerificarOtpRequest, Body()],
    tenant_id: TenantDep,
    service: PatientAuthServiceDep,
) -> VerificarOtpResponse:
    """Verify OTP code and issue patient Bearer JWT token."""
    result = await service.verificar_otp(tenant_id, body)
    return VerificarOtpResponse.model_validate(result)
