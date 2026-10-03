"""Presentation layer dependencies for clinical contextual authorization (Tier 3)."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.authz.dependencies import require_role
from src.core.authz.models import AuthenticatedUser
from src.core.authz.roles import Role
from src.core.database import get_db_session
from src.modules.consultation.application.policies.clinical_access_policy import (
    ClinicalAccessPolicy,
)

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
MedicoUserDep = Annotated[AuthenticatedUser, Depends(require_role(Role.MEDICO))]


async def require_clinical_access(
    atendimento_id: Annotated[
        UUID, Path(description="Identificador único do atendimento")
    ],
    current_user: MedicoUserDep,
    session: SessionDep,
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
