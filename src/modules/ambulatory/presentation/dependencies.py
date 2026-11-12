"""Presentation layer dependencies for SUS ambulatory production endpoints."""

from typing import Annotated

from fastapi import Depends

from src.core.authz.dependencies import CurrentUserDep
from src.core.authz.models import AuthenticatedUser
from src.core.authz.roles import Permission, Role
from src.core.errors import ForbiddenError

_ALLOWED_AMBULATORY_ROLES: frozenset[str] = frozenset(
    {Role.FATURAMENTO.value, Role.GESTOR_UNIDADE.value, Role.ADMIN_GLOBAL.value}
)


async def require_ambulatory_auth(
    current_user: CurrentUserDep,
) -> AuthenticatedUser:
    """Garante autorização para gestão de produção ambulatorial SUS (RF-08, US-11).

    Valida papéis de faturamento e gestão ou permissão granular AMBULATORY_CONSOLIDATE.
    Regras: docs/explanation/domains/ambulatory-domain.md e US-11.
    """
    if not (
        current_user.has_role(*_ALLOWED_AMBULATORY_ROLES)
        or current_user.has_permission(Permission.AMBULATORY_CONSOLIDATE)
    ):
        allowed_desc = (
            f"{sorted(_ALLOWED_AMBULATORY_ROLES)} ou permissão "
            f"'{Permission.AMBULATORY_CONSOLIDATE.value}'"
        )
        raise ForbiddenError(
            f"Acesso negado: o papel '{current_user.papel}' não possui "
            "autorização para gerenciar a produção ambulatorial SUS "
            f"(esperados: {allowed_desc})."
        )
    return current_user


AmbulatoryAuthDep = Annotated[AuthenticatedUser, Depends(require_ambulatory_auth)]
