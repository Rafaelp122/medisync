"""Presentation layer dependencies for clinical contextual authorization (Tier 3)."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Path, status

from src.core.authz.dependencies import require_role
from src.core.authz.models import AuthenticatedUser
from src.core.authz.roles import Role
from src.core.database import DbSessionDep
from src.modules.consultation.application.policies.clinical_access_policy import (
    ClinicalAccessPolicy,
)
from src.modules.consultation.application.ports.validation_rate_limiter_port import (
    ValidationRateLimiterPort,
)

MedicoUserDep = Annotated[AuthenticatedUser, Depends(require_role(Role.MEDICO))]

AtendimentoIdPath = Annotated[
    UUID, Path(description="Identificador único do atendimento")
]
DocumentoIdPath = Annotated[
    UUID, Path(description="Identificador único do documento clínico")
]


async def require_clinical_access(
    atendimento_id: AtendimentoIdPath,
    current_user: MedicoUserDep,
    session: DbSessionDep,
) -> AuthenticatedUser:
    """Enforce Tier 3 Clinical ABAC/ReBAC context for the requested attendance.

    Validates:
    1. Caller holds Role.MEDICO (Tier 1 RBAC).
    2. Patient has valid signed digital TCLE.
    3. Caller is the physician assigned to this attendance.
    4. Attendance is in active state (EM_ATENDIMENTO or CHAMANDO_PACIENTE).
    """
    await ClinicalAccessPolicy.validar_acesso_clinico(
        atendimento_id=atendimento_id,
        medico_id=current_user.usuario_id,
        session=session,
    )
    return current_user


ClinicalAccessDep = Annotated[AuthenticatedUser, Depends(require_clinical_access)]


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
