"""Unit tests for identity presentation proof-of-possession dependencies."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi.security import HTTPAuthorizationCredentials
from src.core.authz.revocation import MemoryTokenRevocation
from src.core.authz.roles import Role
from src.core.config import get_settings
from src.core.errors import ForbiddenError, TokenRevogadoError, UnauthorizedError
from src.core.security import create_intake_token
from src.core.uuid7 import uuid7
from src.modules.identity.presentation.dependencies import (
    validar_intake_fase2,
    validar_posse_titular,
)
from src.modules.identity.presentation.schemas import Fase2Request


def _make_jwt(
    usuario_id: UUID,
    papel: str,
    secret_key: str,
    expires_in_seconds: int = 900,
    jti: UUID | None = None,
) -> str:
    now = datetime.now(UTC)
    exp = now + timedelta(seconds=expires_in_seconds)
    payload = {
        "sub": str(usuario_id),
        "papel": papel,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": str(jti or uuid4()),
        "type": "access",
    }
    return jwt.encode(payload, secret_key, algorithm="HS256")


def _make_fase2_request(paciente_id: UUID, token: str | None = None) -> Fase2Request:
    return Fase2Request(
        paciente_id=paciente_id,
        nome_mae="Maria Teste da Silva",
        sexo_biologico="F",
        cep="01310-100",
        logradouro="Avenida Paulista",
        numero="1000",
        bairro="Bela Vista",
        cidade="São Paulo",
        estado="SP",
        token=token,
    )


@pytest.mark.asyncio
async def test_validar_intake_fase2_via_header_success() -> None:
    settings = get_settings()
    paciente_id = uuid7()
    token = create_intake_token(paciente_id, settings.SECRET_KEY)
    body = _make_fase2_request(paciente_id)

    await validar_intake_fase2(
        body=body,
        credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
    )


@pytest.mark.asyncio
async def test_validar_intake_fase2_via_header_with_whitespace_success() -> None:
    settings = get_settings()
    paciente_id = uuid7()
    token = create_intake_token(paciente_id, settings.SECRET_KEY)
    body = _make_fase2_request(paciente_id)

    await validar_intake_fase2(
        body=body,
        credentials=HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=f"  {token}  "
        ),
    )


@pytest.mark.asyncio
async def test_validar_intake_fase2_via_body_success() -> None:
    settings = get_settings()
    paciente_id = uuid7()
    token = create_intake_token(paciente_id, settings.SECRET_KEY)
    body = _make_fase2_request(paciente_id, token=token)

    await validar_intake_fase2(
        body=body,
        credentials=None,
    )


@pytest.mark.asyncio
async def test_validar_intake_fase2_missing_token_raises_401() -> None:
    paciente_id = uuid7()
    body = _make_fase2_request(paciente_id, token=None)

    with pytest.raises(UnauthorizedError, match="Token de acolhimento não fornecido"):
        await validar_intake_fase2(body=body, credentials=None)


@pytest.mark.asyncio
async def test_validar_intake_fase2_expired_token_raises_401() -> None:
    settings = get_settings()
    paciente_id = uuid7()
    expired_token = create_intake_token(
        paciente_id, settings.SECRET_KEY, expires_in_seconds=-10
    )
    body = _make_fase2_request(paciente_id)

    with pytest.raises(UnauthorizedError, match="expirado"):
        await validar_intake_fase2(
            body=body,
            credentials=HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=expired_token
            ),
        )


@pytest.mark.asyncio
async def test_validar_intake_fase2_mismatched_paciente_raises_403() -> None:
    settings = get_settings()
    paciente_a = uuid7()
    paciente_b = uuid7()
    token_a = create_intake_token(paciente_a, settings.SECRET_KEY)
    body_b = _make_fase2_request(paciente_b)

    with pytest.raises(ForbiddenError, match="não confere posse"):
        await validar_intake_fase2(
            body=body_b,
            credentials=HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=token_a
            ),
        )


@pytest.mark.asyncio
async def test_validar_intake_fase2_via_jwt_patient_success() -> None:
    settings = get_settings()
    paciente_id = uuid7()
    token = _make_jwt(
        usuario_id=paciente_id,
        papel=Role.PACIENTE,
        secret_key=settings.JWT_SECRET_KEY,
    )
    body = _make_fase2_request(paciente_id)

    await validar_intake_fase2(
        body=body,
        credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
    )


@pytest.mark.asyncio
async def test_validar_intake_fase2_via_jwt_gestor_unidade_raises_403() -> None:
    """RN-IDE-07: GESTOR_UNIDADE is forbidden from bypassing Phase 2 ownership."""
    settings = get_settings()
    paciente_id = uuid7()
    gestor_id = uuid7()
    token = _make_jwt(
        usuario_id=gestor_id,
        papel=Role.GESTOR_UNIDADE,
        secret_key=settings.JWT_SECRET_KEY,
    )
    body = _make_fase2_request(paciente_id)

    with pytest.raises(ForbiddenError, match="não possui permissão"):
        await validar_intake_fase2(
            body=body,
            credentials=HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=token
            ),
            revocation=MemoryTokenRevocation(),
        )


@pytest.mark.asyncio
async def test_validar_intake_fase2_via_jwt_mismatched_patient_raises_403() -> None:
    settings = get_settings()
    paciente_a = uuid7()
    paciente_b = uuid7()
    token = _make_jwt(
        usuario_id=paciente_a,
        papel=Role.PACIENTE,
        secret_key=settings.JWT_SECRET_KEY,
    )
    body_b = _make_fase2_request(paciente_b)

    with pytest.raises(ForbiddenError, match="não é o paciente informado"):
        await validar_intake_fase2(
            body=body_b,
            credentials=HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=token
            ),
        )


@pytest.mark.asyncio
async def test_validar_intake_fase2_via_jwt_unauthorized_role_raises_403() -> None:
    settings = get_settings()
    doctor_id = uuid7()
    paciente_id = uuid7()
    token = _make_jwt(
        usuario_id=doctor_id,
        papel=Role.MEDICO,
        secret_key=settings.JWT_SECRET_KEY,
    )
    body = _make_fase2_request(paciente_id)

    with pytest.raises(ForbiddenError, match="não possui permissão"):
        await validar_intake_fase2(
            body=body,
            credentials=HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=token
            ),
        )


@pytest.mark.asyncio
async def test_validar_intake_fase2_via_jwt_expired_raises_401() -> None:
    settings = get_settings()
    paciente_id = uuid7()
    expired_token = _make_jwt(
        usuario_id=paciente_id,
        papel=Role.PACIENTE,
        secret_key=settings.JWT_SECRET_KEY,
        expires_in_seconds=-10,
    )
    body = _make_fase2_request(paciente_id)

    with pytest.raises(UnauthorizedError, match="expirado"):
        await validar_intake_fase2(
            body=body,
            credentials=HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=expired_token
            ),
        )


@pytest.mark.asyncio
async def test_validar_intake_fase2_via_jwt_revogado_raises_401() -> None:
    settings = get_settings()
    paciente_id = uuid7()
    jti = uuid4()
    revocation = MemoryTokenRevocation()
    await revocation.revogar(str(jti))
    token = _make_jwt(
        usuario_id=paciente_id,
        papel=Role.PACIENTE,
        secret_key=settings.JWT_SECRET_KEY,
        jti=jti,
    )
    body = _make_fase2_request(paciente_id)

    with pytest.raises(TokenRevogadoError, match="revogado"):
        await validar_intake_fase2(
            body=body,
            credentials=HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=token
            ),
            revocation=revocation,
        )


@pytest.mark.asyncio
async def test_validar_intake_fase2_malformed_token_raises_401() -> None:
    paciente_id = uuid7()
    body = _make_fase2_request(paciente_id)

    with pytest.raises(UnauthorizedError, match="formato inválido"):
        await validar_intake_fase2(
            body=body,
            credentials=HTTPAuthorizationCredentials(
                scheme="Bearer", credentials="single_part_token"
            ),
        )


@pytest.mark.asyncio
async def test_validar_intake_fase2_four_parts_raises_401() -> None:
    paciente_id = uuid7()
    body = _make_fase2_request(paciente_id)

    with pytest.raises(UnauthorizedError, match="formato inválido"):
        await validar_intake_fase2(
            body=body,
            credentials=HTTPAuthorizationCredentials(
                scheme="Bearer", credentials="a.b.c.d"
            ),
        )


@pytest.mark.asyncio
async def test_validar_posse_titular_missing_header_raises_401() -> None:
    titular_id = uuid7()
    with pytest.raises(UnauthorizedError, match="não fornecida"):
        await validar_posse_titular(id=titular_id, credentials=None)


@pytest.mark.asyncio
async def test_validar_posse_titular_intake_token_success() -> None:
    settings = get_settings()
    titular_id = uuid7()
    token = create_intake_token(titular_id, settings.SECRET_KEY)

    await validar_posse_titular(
        id=titular_id,
        credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
    )


@pytest.mark.asyncio
async def test_validar_posse_titular_intake_token_other_patient_raises_403() -> None:
    settings = get_settings()
    titular_id = uuid7()
    other_id = uuid7()
    token = create_intake_token(other_id, settings.SECRET_KEY)

    with pytest.raises(ForbiddenError, match="não confere posse"):
        await validar_posse_titular(
            id=titular_id,
            credentials=HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=token
            ),
        )


@pytest.mark.asyncio
async def test_validar_posse_titular_gestor_unidade_jwt_raises_403() -> None:
    """RN-IDE-07: GESTOR_UNIDADE is forbidden from accessing titular dependents."""
    settings = get_settings()
    titular_id = uuid7()

    gestor_jwt = _make_jwt(uuid4(), Role.GESTOR_UNIDADE, settings.JWT_SECRET_KEY)
    with pytest.raises(ForbiddenError, match="não possui permissão"):
        await validar_posse_titular(
            id=titular_id,
            credentials=HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=gestor_jwt
            ),
            revocation=MemoryTokenRevocation(),
        )


@pytest.mark.asyncio
async def test_validar_posse_titular_patient_jwt_success() -> None:
    settings = get_settings()
    titular_id = uuid7()
    patient_jwt = _make_jwt(titular_id, Role.PACIENTE, settings.JWT_SECRET_KEY)

    await validar_posse_titular(
        id=titular_id,
        credentials=HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=patient_jwt
        ),
    )


@pytest.mark.asyncio
async def test_validar_posse_titular_patient_jwt_other_patient_raises_403() -> None:
    settings = get_settings()
    titular_id = uuid7()
    other_patient_id = uuid7()
    patient_jwt = _make_jwt(other_patient_id, Role.PACIENTE, settings.JWT_SECRET_KEY)

    with pytest.raises(ForbiddenError, match="não é o titular informado"):
        await validar_posse_titular(
            id=titular_id,
            credentials=HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=patient_jwt
            ),
        )


@pytest.mark.asyncio
async def test_validar_posse_titular_unauthorized_role_raises_403() -> None:
    settings = get_settings()
    titular_id = uuid7()
    medico_jwt = _make_jwt(uuid4(), Role.MEDICO, settings.JWT_SECRET_KEY)

    with pytest.raises(ForbiddenError, match="não possui permissão"):
        await validar_posse_titular(
            id=titular_id,
            credentials=HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=medico_jwt
            ),
        )


@pytest.mark.asyncio
async def test_validar_posse_titular_jwt_revogado_raises_401() -> None:
    settings = get_settings()
    titular_id = uuid7()
    jti = uuid4()
    revocation = MemoryTokenRevocation()
    await revocation.revogar(str(jti))
    patient_jwt = _make_jwt(titular_id, Role.PACIENTE, settings.JWT_SECRET_KEY, jti=jti)

    with pytest.raises(TokenRevogadoError, match="revogado"):
        await validar_posse_titular(
            id=titular_id,
            credentials=HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=patient_jwt
            ),
            revocation=revocation,
        )


@pytest.mark.asyncio
async def test_validar_posse_titular_rejeita_intake_restrito_403() -> None:
    """Conta existente não gerencia dependentes com intake_token restrito."""
    settings = get_settings()
    titular_id = uuid7()
    restricted_intake = create_intake_token(
        titular_id,
        settings.SECRET_KEY,
        is_novo_paciente=False,
    )

    with pytest.raises(ForbiddenError, match="Token de acolhimento restrito"):
        await validar_posse_titular(
            id=titular_id,
            credentials=HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=restricted_intake
            ),
        )
