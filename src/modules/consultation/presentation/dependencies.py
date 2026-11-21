"""Presentation layer dependencies for clinical contextual authorization (Tier 3)."""

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import (
    Depends,
    HTTPException,
    Path,
    Query,
    Security,
    WebSocket,
    WebSocketException,
    status,
)
from fastapi.security import HTTPAuthorizationCredentials

from src.core.authz import (
    AuthenticatedUser,
    BearerAuthSettings,
    OptionalBearerAuthSettingsDep,
    OptionalTokenRevocationDep,
    Role,
    TokenRevocationPort,
    get_bearer_auth_settings,
    get_token_revocation,
    http_bearer_scheme,
    require_role,
    resolve_bearer_principal,
)
from src.core.database import DbSessionDep
from src.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
)
from src.modules.consultation.application.policies.clinical_access_policy import (
    ClinicalAccessPolicy,
)
from src.modules.consultation.application.ports.atendimento_reader_port import (
    AtendimentoReaderPort,
    AtendimentoResumoDTO,
)
from src.modules.consultation.application.ports.validation_rate_limiter_port import (
    ValidationRateLimiterPort,
)
from src.modules.consultation.composition import get_atendimento_reader
from src.modules.consultation.presentation.schemas import LiveKitTokenRequest

MedicoUserDep = Annotated[
    AuthenticatedUser, Security(require_role(Role.MEDICO), scopes=["medico"])
]


async def require_paciente_autenticado(
    current_user: Annotated[
        AuthenticatedUser,
        Security(require_role(Role.PACIENTE), scopes=["paciente"]),
    ],
) -> AuthenticatedUser:
    """Enforce Tier 1 PACIENTE RBAC and Anti-IDOR identity extraction.

    Garante chamador PACIENTE autenticado com usuario_id válido
    extraído exclusivamente do JWT (nunca de query/path params).
    """
    return current_user


PacienteAutenticadoDep = Annotated[
    AuthenticatedUser,
    Security(require_paciente_autenticado, scopes=["patient:doc_view"]),
]

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


ClinicalAccessReadDep = Annotated[
    AuthenticatedUser,
    Security(require_clinical_read_access, scopes=["clinical:read"]),
]
ClinicalAccessMutationDep = Annotated[
    AuthenticatedUser,
    Security(require_clinical_mutation_access, scopes=["clinical:write"]),
]


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
            detail=(
                f"Limite de requisições excedido para a chave '{chave}' "
                f"(máximo: {limite} a cada {janela_segundos}s; "
                f"aguarde {res.retry_after_segundos}s)."
            ),
            headers={"Retry-After": str(res.retry_after_segundos)},
        )


@dataclass(frozen=True)
class LivenessActor:
    """Identidade autenticada (médico ou paciente) para prova de vida US-15."""

    actor_id: UUID
    actor_papel: str


def _validar_participacao_atendimento_liveness(
    *,
    actor_id: UUID,
    actor_papel: str,
    atendimento_paciente_id: UUID | None,
    atendimento_medico_id: UUID | None,
) -> None:
    if actor_papel == Role.PACIENTE.value and atendimento_paciente_id != actor_id:
        raise ForbiddenError(
            f"Paciente '{actor_id}' não é o titular deste atendimento clínico "
            f"(esperado titular: '{atendimento_paciente_id}')."
        )
    if actor_papel == Role.MEDICO.value and atendimento_medico_id != actor_id:
        raise ForbiddenError(
            f"Médico '{actor_id}' não está alocado neste atendimento clínico "
            f"(esperado médico alocado: '{atendimento_medico_id}')."
        )


async def _require_liveness_actor(
    *,
    atendimento_id: AtendimentoIdPath,
    reader: AtendimentoReaderPort,
    credentials: HTTPAuthorizationCredentials | None,
    allowed_roles: tuple[Role, ...],
    revocation: TokenRevocationPort | None = None,
    auth_settings: BearerAuthSettings | None = None,
) -> LivenessActor:
    """Valida participante autorizado para etapa específica de prova de vida US-15."""
    if credentials is None or not credentials.credentials.strip():
        raise UnauthorizedError(
            "Credencial de autenticação obrigatória para prova de vida facial "
            f"(recebido: {credentials!r}; "
            "esperado cabeçalho 'Authorization: Bearer <token>')."
        )

    resolved_settings = auth_settings or get_bearer_auth_settings()
    resolved_revocation = revocation or get_token_revocation()
    principal = await resolve_bearer_principal(
        credentials.credentials,
        allowed_roles=allowed_roles,
        accept_intake=True,
        revocation=resolved_revocation,
        secret_key=resolved_settings.secret_key,
        jwt_secret=resolved_settings.jwt_secret,
        jwt_algorithm=resolved_settings.jwt_algorithm,
        transport="http",
    )
    resumo = await reader.obter_resumo(atendimento_id)
    if resumo is None:
        raise NotFoundError(
            f"Atendimento '{atendimento_id}' não encontrado para prova de vida facial."
        )
    if resumo.is_terminal:
        raise ForbiddenError(
            f"Atendimento '{atendimento_id}' encontra-se em estado terminal "
            f"('{resumo.status}'); esperados estados ativos para prova de vida."
        )

    _validar_participacao_atendimento_liveness(
        actor_id=principal.actor_id,
        actor_papel=principal.papel,
        atendimento_paciente_id=resumo.paciente_id,
        atendimento_medico_id=resumo.medico_id,
    )
    return LivenessActor(
        actor_id=principal.actor_id,
        actor_papel=principal.papel,
    )


async def require_liveness_challenge_medico(
    atendimento_id: AtendimentoIdPath,
    reader: Annotated[AtendimentoReaderPort, Depends(get_atendimento_reader)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(http_bearer_scheme),
    ] = None,
    revocation: OptionalTokenRevocationDep = None,
    auth_settings: OptionalBearerAuthSettingsDep = None,
) -> LivenessActor:
    """Restringe solicitação de desafio facial ao médico alocado."""
    return await _require_liveness_actor(
        atendimento_id=atendimento_id,
        reader=reader,
        credentials=credentials,
        allowed_roles=(Role.MEDICO,),
        revocation=revocation,
        auth_settings=auth_settings,
    )


async def require_liveness_verify_paciente(
    atendimento_id: AtendimentoIdPath,
    reader: Annotated[AtendimentoReaderPort, Depends(get_atendimento_reader)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(http_bearer_scheme),
    ] = None,
    revocation: OptionalTokenRevocationDep = None,
    auth_settings: OptionalBearerAuthSettingsDep = None,
) -> LivenessActor:
    """Restringe submissão dos frames biométricos ao paciente titular."""
    return await _require_liveness_actor(
        atendimento_id=atendimento_id,
        reader=reader,
        credentials=credentials,
        allowed_roles=(Role.PACIENTE,),
        revocation=revocation,
        auth_settings=auth_settings,
    )


LivenessChallengeMedicoDep = Annotated[
    LivenessActor, Depends(require_liveness_challenge_medico)
]
LivenessVerifyPacienteDep = Annotated[
    LivenessActor, Depends(require_liveness_verify_paciente)
]


def _validar_permissao_sala_livekit(
    role: str,
    participant_id: UUID,
    caller_id: UUID,
    atendimento: AtendimentoResumoDTO,
) -> None:
    """Verifica micro-autorização ReBAC/ABAC para entrada em sala virtual."""
    if role == "medico":
        if atendimento.medico_id is None or str(atendimento.medico_id) != str(
            caller_id
        ):
            raise ForbiddenError(
                f"Acesso negado: médico '{caller_id}' não alocado ao "
                f"atendimento (alocado: '{atendimento.medico_id}')."
            )
    else:
        if atendimento.paciente_id is None or str(atendimento.paciente_id) != str(
            caller_id
        ):
            raise ForbiddenError(
                f"Acesso negado: o paciente autenticado '{caller_id}' não é o titular "
                f"deste atendimento (titular: '{atendimento.paciente_id}')."
            )

    if str(participant_id) != str(caller_id):
        raise ForbiddenError(
            f"Acesso negado: participant_id '{participant_id}' diverge "
            f"do usuário autenticado '{caller_id}'."
        )


async def validar_acesso_livekit(
    atendimento_id: AtendimentoIdPath,
    request: LiveKitTokenRequest,
    reader: Annotated[AtendimentoReaderPort, Depends(get_atendimento_reader)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(http_bearer_scheme),
    ] = None,
    revocation: OptionalTokenRevocationDep = None,
    auth_settings: OptionalBearerAuthSettingsDep = None,
) -> None:
    """Valida acesso para emissão de token LiveKit WebRTC (Issue #42).

    Garante conformidade com a Resolução CFM nº 2.314/2022 e RN02:
    - Rejeita requisições anônimas ou com token inválido com RFC 7807 401.
    - Se papel 'medico': exige JWT válido, papel MEDICO e alocação ativa.
    - Se papel 'paciente': exige token de acolhimento (HMAC) ou JWT.
    - Rejeita atendimentos em estado terminal com 403/409.
    """
    if credentials is None:
        raise UnauthorizedError(
            f"Credencial de autenticação não fornecida (recebido: {credentials!r}; "
            "esperado cabeçalho 'Authorization: Bearer <token>')."
        )

    if request.role not in ("medico", "paciente"):
        raise UnauthorizedError(
            f"Papel clínico '{request.role}' não suportado; "
            "esperados: 'medico' ou 'paciente'."
        )

    resolved_settings = auth_settings or get_bearer_auth_settings()
    resolved_revocation = revocation or get_token_revocation()
    allowed_roles = (Role.MEDICO,) if request.role == "medico" else (Role.PACIENTE,)
    accept_intake = request.role == "paciente"
    principal = await resolve_bearer_principal(
        credentials.credentials,
        allowed_roles=allowed_roles,
        accept_intake=accept_intake,
        revocation=resolved_revocation,
        secret_key=resolved_settings.secret_key,
        jwt_secret=resolved_settings.jwt_secret,
        jwt_algorithm=resolved_settings.jwt_algorithm,
        transport="http",
    )

    atendimento = await reader.obter_resumo(atendimento_id)
    if atendimento is None:
        raise NotFoundError(f"Atendimento '{atendimento_id}' não encontrado.")

    if atendimento.is_terminal:
        if atendimento.status == "PACIENTE_AUSENTE":
            raise ConflictError(
                f"Acesso negado: atendimento '{atendimento_id}' expirou por "
                f"ausência do paciente (status recebido: '{atendimento.status}'; "
                "esperados status ativos: ['CHAMANDO_PACIENTE', 'EM_ATENDIMENTO']).",
                code="ATENDIMENTO_EXPIRADO_NO_SHOW",
            )
        raise ForbiddenError(
            f"Acesso negado: atendimento '{atendimento_id}' já finalizado com status "
            f"'{atendimento.status}'."
        )

    _validar_permissao_sala_livekit(
        role=request.role,
        participant_id=request.participant_id,
        caller_id=principal.actor_id,
        atendimento=atendimento,
    )


LiveKitAccessDep = Annotated[
    None, Security(validar_acesso_livekit, scopes=["livekit:access"])
]


async def validar_ws_doctor_token(
    websocket: WebSocket,
    medico_id: UUID,
    token: str | None = Query(default=None),
    revocation: OptionalTokenRevocationDep = None,
    auth_settings: OptionalBearerAuthSettingsDep = None,
) -> None:
    """Valida o handshake WebSocket do médico via query ?token= (Issue #42).

    Rejeita requisições não autorizadas com código de encerramento WS 4401 ou 4403
    antes de invocar websocket.accept().
    """
    resolved_settings = auth_settings or get_bearer_auth_settings()
    resolved_revocation = revocation or get_token_revocation()
    principal = await resolve_bearer_principal(
        token,
        allowed_roles=(Role.MEDICO,),
        accept_intake=False,
        revocation=resolved_revocation,
        secret_key=resolved_settings.secret_key,
        jwt_secret=resolved_settings.jwt_secret,
        jwt_algorithm=resolved_settings.jwt_algorithm,
        transport="ws",
    )

    if principal.actor_id != medico_id:
        raise WebSocketException(
            code=4403,
            reason=(
                f"Acesso negado: token pertence ao médico '{principal.actor_id}', "
                f"divergindo de '{medico_id}'."
            ),
        )


DoctorWsAuthDep = Annotated[None, Depends(validar_ws_doctor_token)]
