"""Presentation layer dependencies for shift telemetry endpoints."""

from typing import Annotated

from fastapi import Depends

from src.core.authz.dependencies import CurrentUserDep
from src.core.authz.models import AuthenticatedUser
from src.core.authz.roles import Permission, Role
from src.core.errors import ForbiddenError


async def require_telemetry_auth(
    current_user: CurrentUserDep,
) -> AuthenticatedUser:
    """Ensure caller possesses GESTOR_UNIDADE, ADMIN_GLOBAL, or TMA_CONFIG."""
    if not (
        current_user.papel in (Role.GESTOR_UNIDADE, Role.ADMIN_GLOBAL)
        or current_user.has_permission(Permission.TMA_CONFIG)
    ):
        raise ForbiddenError(
            f"Acesso negado: o papel '{current_user.papel}' não possui "
            "autorização para acessar a telemetria do plantão."
        )
    return current_user


TelemetryAuthDep = Annotated[AuthenticatedUser, Depends(require_telemetry_auth)]
