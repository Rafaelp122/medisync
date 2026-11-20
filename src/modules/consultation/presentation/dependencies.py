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

from src.core.authz.dependencies import (
    HTTPAuthorizationCredentials,
    http_bearer_scheme,
    require_role,
)
from src.core.authz.models import AuthenticatedUser
from src.core.authz.revocation import is_token_revoked
from src.core.authz.roles import Role
from src.core.authz.token import decode_access_token
from src.core.config import get_settings
from src.core.database import DbSessionDep
from src.core.errors import (
    ConflictError,
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


async def _autenticar_chamador_medico(raw_token: str) -> UUID:
    """Valida token JWT de médico e retorna usuario_id."""
    try:
        user = decode_access_token(raw_token)
    except Exception as exc:
        raise UnauthorizedError(
            f"Token de acesso inválido ou expirado: {exc}."
        ) from exc

    if await is_token_revoked(user.token_id):
        raise TokenRevogadoError(
            f"Token de acesso '{user.token_id}' revogado. Realize novo login."
        )

    if user.papel != Role.MEDICO:
        raise ForbiddenError(
            f"Acesso negado: papel '{user.papel}' sem permissão para sala "
            f"como médico (esperado: '{Role.MEDICO.value}')."
        )

    return user.usuario_id


def _autenticar_chamador_paciente_intake(raw_token: str) -> UUID:
    """Valida token HMAC de acolhimento do paciente (2 partes)."""
    settings = get_settings()
    try:
        claims = verify_intake_token(raw_token, settings.SECRET_KEY)
    except ValueError as exc:
        raise UnauthorizedError(
            f"Token de acolhimento em formato inválido: {exc}."
        ) from exc

    return UUID(str(claims["paciente_id"]))


async def _autenticar_chamador_paciente_jwt(raw_token: str) -> UUID:
    """Valida token JWT do paciente (3 partes)."""
    try:
        user = decode_access_token(raw_token)
    except Exception as exc:
        raise UnauthorizedError(
            f"Token de acesso inválido ou expirado: {exc}."
        ) from exc

    if await is_token_revoked(user.token_id):
        raise TokenRevogadoError(
            f"Token de acesso '{user.token_id}' revogado. Realize novo login."
        )

    if user.papel != Role.PACIENTE:
        raise ForbiddenError(
            f"Acesso negado: papel '{user.papel}' sem permissão para sala "
            f"como paciente (esperado: '{Role.PACIENTE.value}')."
        )

    return user.usuario_id


async def _autenticar_chamador_paciente(raw_token: str) -> UUID:
    """Autentica chamador paciente via token de acolhimento ou JWT completo."""
    token_parts = raw_token.split(".")
    if len(token_parts) == 2:
        return _autenticar_chamador_paciente_intake(raw_token)
    if len(token_parts) == 3:
        return await _autenticar_chamador_paciente_jwt(raw_token)
    raise UnauthorizedError(
        f"Token em formato inválido ({len(token_parts)} partes; esperados: 2 ou 3)."
    )


@dataclass(frozen=True)
class LivenessActor:
    """Identidade autenticada (médico ou paciente) para prova de vida US-15."""

    actor_id: UUID
    actor_papel: str


async def _autenticar_chamador_liveness(
    raw_token: str,
    allowed_roles: tuple[Role, ...],
) -> tuple[UUID, str]:
    """Extrai identidade clínica de JWT ou HMAC validando papéis permitidos."""
    parts = raw_token.split(".")
    if len(parts) == 2:
        actor_id = _autenticar_chamador_paciente_intake(raw_token)
        if Role.PACIENTE not in allowed_roles:
            raise ForbiddenError(
                f"Papel '{Role.PACIENTE.value}' não autorizado para esta ação "
                f"(esperados: {[r.value for r in allowed_roles]})."
            )
        return actor_id, Role.PACIENTE.value
    if len(parts) != 3:
        raise UnauthorizedError(
            f"Token em formato inválido ({len(parts)} partes; esperados: 2 ou 3)."
        )

    try:
        user = decode_access_token(raw_token)
    except Exception as exc:
        raise UnauthorizedError(
            f"Token de acesso inválido ou expirado: {exc}."
        ) from exc

    if await is_token_revoked(user.token_id):
        raise TokenRevogadoError(
            f"Token de acesso '{user.token_id}' revogado. Realize novo login."
        )

    if user.papel not in allowed_roles:
        raise ForbiddenError(
            f"Papel '{user.papel}' não autorizado para prova de vida facial "
            f"(esperados: {[r.value for r in allowed_roles]})."
        )
    return user.usuario_id, str(user.papel)


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
) -> LivenessActor:
    """Valida participante autorizado para etapa específica de prova de vida US-15."""
    if credentials is None or not credentials.credentials.strip():
        raise UnauthorizedError(
            "Credencial de autenticação obrigatória para prova de vida facial "
            f"(recebido: {credentials!r}; "
            "esperado cabeçalho 'Authorization: Bearer <token>')."
        )

    actor_id, actor_papel = await _autenticar_chamador_liveness(
        credentials.credentials,
        allowed_roles,
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
        actor_id=actor_id,
        actor_papel=actor_papel,
        atendimento_paciente_id=resumo.paciente_id,
        atendimento_medico_id=resumo.medico_id,
    )
    return LivenessActor(
        actor_id=actor_id,
        actor_papel=actor_papel,
    )


async def require_liveness_challenge_medico(
    atendimento_id: AtendimentoIdPath,
    reader: Annotated[AtendimentoReaderPort, Depends(get_atendimento_reader)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(http_bearer_scheme),
    ] = None,
) -> LivenessActor:
    """Restringe solicitação de desafio facial ao médico alocado."""
    return await _require_liveness_actor(
        atendimento_id=atendimento_id,
        reader=reader,
        credentials=credentials,
        allowed_roles=(Role.MEDICO,),
    )


async def require_liveness_verify_paciente(
    atendimento_id: AtendimentoIdPath,
    reader: Annotated[AtendimentoReaderPort, Depends(get_atendimento_reader)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(http_bearer_scheme),
    ] = None,
) -> LivenessActor:
    """Restringe submissão dos frames biométricos ao paciente titular."""
    return await _require_liveness_actor(
        atendimento_id=atendimento_id,
        reader=reader,
        credentials=credentials,
        allowed_roles=(Role.PACIENTE,),
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
) -> None:
    """Valida acesso para emissão de token LiveKit WebRTC (Issue #42).

    Garante conformidade com a Resolução CFM nº 2.314/2022 e RN02:
    - Rejeita requisições anônimas ou com token inválido com RFC 7807 401.
    - Se papel 'medico': exige JWT válido, papel MEDICO e alocação ativa.
    - Se papel 'paciente': exige token de acolhimento (HMAC) ou JWT.
    - Rejeita atendimentos terminais e divergência de organização com 403.
    """
    if credentials is None:
        raise UnauthorizedError(
            f"Credencial de autenticação não fornecida (recebido: {credentials!r}; "
            "esperado cabeçalho 'Authorization: Bearer <token>')."
        )

    raw_token = credentials.credentials

    # 1. Autenticação e extração de identidade do chamador (401 se credencial inválida)
    if request.role not in ("medico", "paciente"):
        raise UnauthorizedError(
            f"Papel clínico '{request.role}' não suportado; "
            "esperados: 'medico' ou 'paciente'."
        )

    if request.role == "medico":
        caller_id = await _autenticar_chamador_medico(raw_token)
    else:
        caller_id = await _autenticar_chamador_paciente(raw_token)

    # 2. Busca do atendimento via reader (404 se não existir)
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

    # 3. Micro-autorização ReBAC/ABAC
    _validar_permissao_sala_livekit(
        role=request.role,
        participant_id=request.participant_id,
        caller_id=caller_id,
        atendimento=atendimento,
    )


LiveKitAccessDep = Annotated[
    None, Security(validar_acesso_livekit, scopes=["livekit:access"])
]


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
            reason=f"Credencial não fornecida na query string: {token!r}.",
        )

    try:
        user = decode_access_token(token)
    except Exception as exc:
        raise WebSocketException(
            code=4401,
            reason=f"Token de autenticação inválido ou expirado: {exc}.",
        ) from exc

    if await is_token_revoked(user.token_id):
        raise WebSocketException(
            code=4401,
            reason=f"Token de autenticação '{user.token_id}' revogado.",
        )

    if user.papel != Role.MEDICO:
        raise WebSocketException(
            code=4403,
            reason=(
                f"Acesso negado: usuário possui papel '{user.papel}'; "
                "esperado papel médico."
            ),
        )

    if user.usuario_id != medico_id:
        raise WebSocketException(
            code=4403,
            reason=(
                f"Acesso negado: token pertence ao médico '{user.usuario_id}', "
                f"divergindo de '{medico_id}'."
            ),
        )


DoctorWsAuthDep = Annotated[None, Depends(validar_ws_doctor_token)]
