"""FastAPI router for passwordless patient OTP authentication."""

from typing import Annotated

from fastapi import APIRouter, Body, Request, status

from src.core.dependencies import TenantDep
from src.modules.auth.application.dtos import (
    IdentificarPacienteCommand,
    LoginPacienteSenhaCommand,
    RegistrarPacienteCommand,
)
from src.modules.auth.composition import PatientAuthServiceDep
from src.modules.auth.presentation.schemas import (
    AutenticarCadsusRequest,
    IdentificarPacienteRequest,
    IdentificarPacienteResponse,
    LoginPacienteSenhaRequest,
    MetodosAutenticacaoPacienteResponse,
    RegistrarPacienteRequest,
    RegistrarPacienteResponse,
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
async def verify_otp(
    body: Annotated[VerificarOtpRequest, Body()],
    tenant_id: TenantDep,
    service: PatientAuthServiceDep,
) -> VerificarOtpResponse:
    """Verify OTP code and issue patient Bearer JWT token."""
    result = await service.verificar_otp(tenant_id, body)
    return VerificarOtpResponse.model_validate(result)


@patient_auth_router.post(
    "/auth/patient/cadsus",
    status_code=status.HTTP_200_OK,
    summary="Autenticar paciente via CADSUS / Gov.br",
    description=(
        "Autenticação sem senha via desambiguação de dados civis "
        "(CPF, CNS, Data de Nascimento)."
    ),
    operation_id="post_auth_paciente_cadsus",
)
async def post_auth_paciente_cadsus(
    body: Annotated[AutenticarCadsusRequest, Body()],
    tenant_id: TenantDep,
    service: PatientAuthServiceDep,
) -> VerificarOtpResponse:
    """Authenticate patient via CADSUS / Gov.br civil registry lookup."""
    result = await service.autenticar_cadsus_govbr(
        organizacao_id=tenant_id,
        cpf=body.cpf,
        data_nascimento=body.data_nascimento,
        cns=body.cns,
        nome_mae=body.nome_mae,
    )
    return VerificarOtpResponse.model_validate(result)


@patient_auth_router.post(
    "/auth/patient/register",
    status_code=status.HTTP_201_CREATED,
    summary="Auto-cadastro do cidadão com disparo inicial de OTP",
    description=(
        "Registra novo paciente na organização com aceite LGPD, credencial "
        "opcional (e-mail/senha Argon2id) e envio inicial de código OTP via SMS."
    ),
    operation_id="post_auth_patient_register",
)
async def register_patient(
    request: Request,
    body: Annotated[RegistrarPacienteRequest, Body()],
    tenant_id: TenantDep,
    service: PatientAuthServiceDep,
) -> RegistrarPacienteResponse:
    """Register a new citizen patient and dispatch initial verification OTP."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    cmd = RegistrarPacienteCommand(
        organizacao_id=tenant_id,
        cpf=body.cpf,
        nome_completo=body.nome_completo,
        data_nascimento=body.data_nascimento,
        telefone=body.telefone,
        email=body.email,
        aceite_privacidade=body.aceite_privacidade,
        senha=body.senha,
        client_ip=client_ip,
    )
    result = await service.registrar_paciente(cmd)
    return RegistrarPacienteResponse.model_validate(result)


@patient_auth_router.post(
    "/auth/patient/identify",
    status_code=status.HTTP_200_OK,
    summary="Identificação única anti-enumeração do paciente",
    description=(
        "Consulta métodos de login habilitados para CPF ou e-mail com rate limiting "
        "e mascaramento estrito de dados pessoais."
    ),
    operation_id="post_auth_patient_identify",
)
async def identify_patient(
    request: Request,
    body: Annotated[IdentificarPacienteRequest, Body()],
    tenant_id: TenantDep,
    service: PatientAuthServiceDep,
) -> IdentificarPacienteResponse:
    """Identify available authentication methods for a patient identifier."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    cmd = IdentificarPacienteCommand(
        organizacao_id=tenant_id,
        identificador=body.identificador,
        client_ip=client_ip,
    )
    result = await service.identificar_paciente(cmd)
    return IdentificarPacienteResponse.model_validate(result)


@patient_auth_router.post(
    "/auth/patient/login-password",
    status_code=status.HTTP_200_OK,
    summary="Login tradicional do paciente com identificador e senha",
    description=(
        "Autentica paciente via Argon2id e lockout progressivo (sem MFA TOTP) "
        "emitindo Bearer JWT Role.PACIENTE."
    ),
    operation_id="post_auth_patient_login_password",
)
async def login_patient_password(
    request: Request,
    body: Annotated[LoginPacienteSenhaRequest, Body()],
    tenant_id: TenantDep,
    service: PatientAuthServiceDep,
) -> VerificarOtpResponse:
    """Authenticate patient with password fallback and issue patient JWT."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    cmd = LoginPacienteSenhaCommand(
        organizacao_id=tenant_id,
        identificador=body.identificador,
        senha=body.senha,
        client_ip=client_ip,
    )
    result = await service.autenticar_paciente_senha(cmd)
    return VerificarOtpResponse.model_validate(result)


@patient_auth_router.get(
    "/auth/patient/methods",
    status_code=status.HTTP_200_OK,
    summary="Consultar capacidades de autenticação habilitadas para pacientes",
    description=(
        "Retorna flags de disponibilidade dos métodos híbridos de autenticação "
        "(Gov.br OIDC, Passkeys, OTP e senha tradicional)."
    ),
    operation_id="get_auth_patient_methods",
)
async def get_patient_auth_methods(
    service: PatientAuthServiceDep,
) -> MetodosAutenticacaoPacienteResponse:
    """Return enabled patient authentication method capabilities."""
    result = service.obter_capacidades_metodos()
    return MetodosAutenticacaoPacienteResponse.model_validate(result)
