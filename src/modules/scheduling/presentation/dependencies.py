"""Dependências FastAPI de autorização da apresentação do módulo scheduling."""

from typing import Annotated

from fastapi import Security

from src.core.authz.dependencies import require_role
from src.core.authz.models import AuthenticatedUser
from src.core.authz.roles import Role

PacienteSchedulingAuthDep = Annotated[
    AuthenticatedUser, Security(require_role(Role.PACIENTE))
]
ProfissionalSchedulingAuthDep = Annotated[
    AuthenticatedUser, Security(require_role(Role.MEDICO))
]
