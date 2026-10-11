"""Presentation layer dependencies for clinical contextual authorization (Tier 3)."""

from typing import Annotated
from uuid import UUID

from fastapi import (
    Depends,
    Header,
    HTTPException,
    Path,
    Query,
    WebSocket,
    WebSocketException,
    status,
)

from src.core.authz.dependencies import require_role
from src.core.authz.models import AuthenticatedUser
from src.core.authz.revocation import is_token_revoked
from src.core.authz.roles import Role
from src.core.authz.token import decode_access_token
from src.core.config import get_settings
from src.core.database import DbSessionDep
from src.core.errors import (
    ForbiddenError,
    NotFoundError,
    TokenRevogadoError,
    UnauthorizedError,
)
from src.core.security import verify_intake_token
from src.modules.consultation.application.policies.clinical_access_policy import (
    ClinicalAccessPolicy,
)
from src.modules.consultation.application.ports.atendimento_reader_port import (
    AtendimentoReaderPort,
)
from src.modules.consultation.application.ports.validation_rate_limiter_port import (
    ValidationRateLimiterPort,
)
from src.modules.consultation.composition import get_atendimento_reader
from src.modules.consultation.presentation.schemas import LiveKitTokenRequest

MedicoUserDep = Annotated[AuthenticatedUser, Depends(require_role(Role.MEDICO))]

AtendimentoIdPath = Annotated[
    UUID, Path(description="Identificador único do atendimento")
]
DocumentoIdPath = Annotated[
    UUID, Path(description="Identificador único do documento clínico")
]


async def require_clinical_read_access(
    atendimento_id: AtendimentoIdPath,
    current_user: MedicoUserDep,
    session: DbSessionDep,
) -> AuthenticatedUser:
    """Enforce Tier 3 Clinical ABAC/ReBAC context for reading records.

    Validates:
    1. Caller holds Role.MEDICO (Tier 1 RBAC).
    2. Patient has valid signed digital TCLE.
    3. Caller is the physician assigned to this attendance.
    4. Attendance status allows reading (active or CONCLUIDO).
    """
    await ClinicalAccessPolicy.validar_acesso_clinico(
        atendimento_id=atendimento_id,
        medico_id=current_user.usuario_id,
        reader=get_atendimento_reader(session),
        is_mutation=False,
    )
    return current_user


async def require_clinical_mutation_access(
    atendimento_id: AtendimentoIdPath,
    current_user: MedicoUserDep,
    session: DbSessionDep,
) -> AuthenticatedUser:
    """Enforce Tier 3 Clinical ABAC/ReBAC context for mutating records.

    Validates:
    1. Caller holds Role.MEDICO (Tier 1 RBAC).
    2. Patient has valid signed digital TCLE.
    3. Caller is the physician assigned to this attendance.
    4. Attendance is in active state (EM_ATENDIMENTO or CHAMANDO_PACIENTE).
    """
    await ClinicalAccessPolicy.validar_acesso_clinico(
        atendimento_id=atendimento_id,
        medico_id=current_user.usuario_id,
        reader=get_atendimento_reader(session),
        is_mutation=True,
    )
    return current_user


require_clinical_access = require_clinical_read_access

ClinicalAccessReadDep = Annotated[
    AuthenticatedUser, Depends(require_clinical_read_access)
]
ClinicalAccessMutationDep = Annotated[
    AuthenticatedUser, Depends(require_clinical_mutation_access)
]
ClinicalAccessDep = ClinicalAccessReadDep


async def exigir_rate_limit(
    limiter: ValidationRateLimiterPort,
    chave: str,
    limite: int,
    janela_segundos: int = 60,
) -> None:
    """Enforce sliding-window rate limit for public validation endpoints.

    Single place in consultation presentation allowed to raise HTTP 429.
    Routers must import this helper instead of raising HTTPException directly.
    """
    res = await limiter.verificar_e_incrementar(
        chave=chave, limite=limite, janela_segundos=janela_segundos
    )
    if not res.permitido:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas requisições. Tente novamente em instantes.",
            headers={"Retry-After": str(res.retry_after_segundos)},
        )


async def validar_acesso_livekit(
    atendimento_id: AtendimentoIdPath,
    request: LiveKitTokenRequest,
    reader: Annotated[AtendimentoReaderPort, Depends(get_atendimento_reader)],
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> None:
    """Valida acesso para emissão de token LiveKit WebRTC (Issue #42).

    Garante conformidade com a Resolução CFM nº 2.314/2022 e RN02:
    - Rejeita requisições anônimas ou com token inválido com RFC 7807 401.
    - Se papel 'medico': exige JWT válido, papel MEDICO e alocação ativa.
    - Se papel 'paciente': exige token de acolhimento (HMAC) ou JWT.
    - Rejeita atendimentos terminais e divergência de organização com 403.
    """
    if not authorization:
        raise UnauthorizedError(
            "Credencial de autenticação não fornecida. "
            "Envie o token no cabeçalho Authorization: Bearer <token>."
        )

    parts = authorization.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise UnauthorizedError(
            "Formato do cabeçalho Authorization inválido. Esperado 'Bearer <token>'."
        )

    raw_token = parts[1]

    # 1. Autenticação e extração de identidade do chamador (401 se credencial inválida)
    if request.role not in ("medico", "paciente"):
        raise UnauthorizedError("Papel clínico não suportado.")

    caller_id: UUID
    caller_org_id: int
    is_admin: bool

    if request.role == "medico":
        try:
            user = decode_access_token(raw_token)
        except Exception as exc:
            raise UnauthorizedError("Token de acesso inválido ou expirado.") from exc

        if await is_token_revoked(user.token_id):
            raise TokenRevogadoError("Token de acesso revogado. Realize novo login.")

        if user.papel not in (Role.MEDICO, Role.ADMIN_GLOBAL):
            raise ForbiddenError(
                f"Acesso negado: o papel '{user.papel}' não possui permissão "
                "para sala de teleconsulta como médico."
            )

        caller_id = user.usuario_id
        caller_org_id = user.organizacao_id
        is_admin = user.papel == Role.ADMIN_GLOBAL

    else:
        token_parts = raw_token.split(".")
        if len(token_parts) == 2:
            settings = get_settings()
            try:
                claims = verify_intake_token(raw_token, settings.SECRET_KEY)
            except ValueError as exc:
                raise UnauthorizedError(str(exc)) from exc

            caller_id = UUID(str(claims["paciente_id"]))
            caller_org_id = int(claims["organizacao_id"])
            is_admin = False
        elif len(token_parts) == 3:
            try:
                user = decode_access_token(raw_token)
            except Exception as exc:
                raise UnauthorizedError(
                    "Token de acesso inválido ou expirado."
                ) from exc

            if await is_token_revoked(user.token_id):
                raise TokenRevogadoError(
                    "Token de acesso revogado. Realize novo login."
                )

            if user.papel not in (Role.PACIENTE, Role.ADMIN_GLOBAL):
                raise ForbiddenError(
                    f"Acesso negado: o papel '{user.papel}' não possui permissão "
                    "para sala de teleconsulta como paciente."
                )
            caller_id = user.usuario_id
            caller_org_id = user.organizacao_id
            is_admin = user.papel == Role.ADMIN_GLOBAL
        else:
            raise UnauthorizedError("Token fornecido em formato inválido.")

    # 2. Busca do atendimento via reader (404 se não existir)
    atendimento = await reader.obter_resumo(atendimento_id)
    if atendimento is None:
        raise NotFoundError(f"Atendimento '{atendimento_id}' não encontrado.")

    if atendimento.is_terminal:
        raise ForbiddenError(
            "Acesso negado: atendimento já finalizado com status "
            f"'{atendimento.status}'."
        )

    # 3. Micro-autorização ReBAC/ABAC
    if request.role == "medico":
        if not is_admin:
            if atendimento.medico_id is None or str(atendimento.medico_id) != str(
                caller_id
            ):
                raise ForbiddenError(
                    "Acesso negado: o médico autenticado não é o profissional "
                    "alocado a este atendimento ativo."
                )
            if str(request.participant_id) != str(caller_id):
                raise ForbiddenError(
                    "Acesso negado: participant_id diverge do médico autenticado."
                )
            if atendimento.organizacao_id != caller_org_id:
                raise ForbiddenError(
                    f"Acesso negado: o token pertence à organização {caller_org_id}, "
                    f"mas o atendimento é da organização {atendimento.organizacao_id}."
                )

    else:
        if not is_admin:
            if atendimento.paciente_id is None or str(atendimento.paciente_id) != str(
                caller_id
            ):
                raise ForbiddenError(
                    "Acesso negado: o paciente autenticado não é o titular "
                    "deste atendimento."
                )
            if str(request.participant_id) != str(caller_id):
                raise ForbiddenError(
                    "Acesso negado: participant_id diverge do paciente autenticado."
                )
            if atendimento.organizacao_id != caller_org_id:
                raise ForbiddenError(
                    f"Acesso negado: o token pertence à organização {caller_org_id}, "
                    f"mas o atendimento é da organização {atendimento.organizacao_id}."
                )

    if request.organizacao_id != atendimento.organizacao_id:
        raise ForbiddenError(
            f"Acesso negado: organizacao_id informada ({request.organizacao_id}) "
            f"diverge do atendimento ({atendimento.organizacao_id})."
        )


LiveKitAccessDep = Annotated[None, Depends(validar_acesso_livekit)]


async def validar_ws_doctor_token(
    websocket: WebSocket,
    medico_id: UUID,
    token: str | None = Query(default=None),
) -> None:
    """Valida o handshake WebSocket do médico via query ?token= (Issue #42).

    Rejeita requisições não autorizadas com código de encerramento WS 4401 ou 4403
    antes de invocar websocket.accept().
    """
    if not token:
        raise WebSocketException(
            code=4401,
            reason="Credencial de autenticação não fornecida.",
        )

    try:
        user = decode_access_token(token)
    except Exception as exc:
        raise WebSocketException(
            code=4401,
            reason="Token de autenticação inválido ou expirado.",
        ) from exc

    if await is_token_revoked(user.token_id):
        raise WebSocketException(
            code=4401,
            reason="Token de autenticação revogado.",
        )

    if user.papel not in (Role.MEDICO, Role.ADMIN_GLOBAL):
        raise WebSocketException(
            code=4403,
            reason="Acesso negado: o usuário não possui papel de médico.",
        )

    if user.papel != Role.ADMIN_GLOBAL and user.usuario_id != medico_id:
        raise WebSocketException(
            code=4403,
            reason="Acesso negado: o token não confere com o médico solicitado.",
        )


DoctorWsAuthDep = Annotated[None, Depends(validar_ws_doctor_token)]
