"""Presentation layer dependencies for shift telemetry endpoints."""

from typing import Annotated

from fastapi import Depends

from src.core.authz.dependencies import CurrentUserDep
from src.core.authz.models import AuthenticatedUser
from src.core.authz.roles import Permission, Role
from src.core.errors import ForbiddenError

_ALLOWED_VIEW_ROLES: frozenset[str] = frozenset(
    {Role.MEDICO.value, Role.GESTOR_UNIDADE.value, Role.ADMIN_GLOBAL.value}
)
_ALLOWED_CONFIG_ROLES: frozenset[str] = frozenset(
    {Role.GESTOR_UNIDADE.value, Role.ADMIN_GLOBAL.value}
)


async def require_telemetry_view_auth(
    current_user: CurrentUserDep,
) -> AuthenticatedUser:
    """Garante autorização para consulta do painel analítico da unidade (RF-10).

    Valida papéis clínicos e de gestão ou permissão granular TMA_CONFIG.
    Regras: docs/explanation/domains/telemetry-domain.md (RN-TEL-06)
    História: docs/user-stories/US-13-telemetria-painel-operacional.md (NC-TEL-02)
    """
    if not (
        current_user.has_role(*_ALLOWED_VIEW_ROLES)
        or current_user.has_permission(Permission.TMA_CONFIG)
    ):
        allowed_desc = (
            f"{sorted(_ALLOWED_VIEW_ROLES)} ou permissão "
            f"'{Permission.TMA_CONFIG.value}'"
        )
        raise ForbiddenError(
            f"Acesso negado: o papel '{current_user.papel}' não possui "
            "autorização para visualizar o painel operacional de telemetria "
            f"(esperados: {allowed_desc})."
        )
    return current_user


async def require_telemetry_config_auth(
    current_user: CurrentUserDep,
) -> AuthenticatedUser:
    """Garante autorização restrita para parametrização de políticas do plantão (RF-09).

    Valida papéis de gestão e administração ou permissão granular TMA_CONFIG.
    Regras: docs/explanation/domains/telemetry-domain.md (RN-TEL-06)
    História: docs/user-stories/US-12-parametrizacao-politicas-plantao.md
    """
    if not (
        current_user.has_role(*_ALLOWED_CONFIG_ROLES)
        or current_user.has_permission(Permission.TMA_CONFIG)
    ):
        allowed_desc = (
            f"{sorted(_ALLOWED_CONFIG_ROLES)} ou permissão "
            f"'{Permission.TMA_CONFIG.value}'"
        )
        raise ForbiddenError(
            f"Acesso negado: o papel '{current_user.papel}' não possui "
            "autorização para parametrizar as políticas do plantão "
            f"(esperados: {allowed_desc})."
        )
    return current_user


TelemetryViewAuthDep = Annotated[
    AuthenticatedUser, Depends(require_telemetry_view_auth)
]
TelemetryConfigAuthDep = Annotated[
    AuthenticatedUser, Depends(require_telemetry_config_auth)
]
