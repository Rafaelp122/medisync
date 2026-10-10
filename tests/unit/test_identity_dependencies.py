"""Unit tests for identity presentation proof-of-possession dependencies."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest
from src.core.authz.roles import Role
from src.core.config import get_settings
from src.core.errors import ForbiddenError, UnauthorizedError
from src.core.security import create_intake_token
from src.core.uuid7 import uuid7
from src.modules.identity.presentation.dependencies import (
    validar_intake_fase2,
    validar_posse_titular,
)
from src.modules.identity.presentation.schemas import Fase2Request


def _make_jwt(
    usuario_id: UUID,
    organizacao_id: int,
    papel: str,
    secret_key: str,
    expires_in_seconds: int = 900,
) -> str:
    now = datetime.now(UTC)
    exp = now + timedelta(seconds=expires_in_seconds)
    payload = {
        "sub": str(usuario_id),
        "org_id": organizacao_id,
        "papel": papel,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": str(uuid4()),
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
    org_id = 10
    token = create_intake_token(paciente_id, org_id, settings.SECRET_KEY)
    body = _make_fase2_request(paciente_id)

    # Should not raise any error
    await validar_intake_fase2(
        body=body,
        tenant_id=org_id,
        authorization=f"Bearer {token}",
    )


@pytest.mark.asyncio
async def test_validar_intake_fase2_via_body_success() -> None:
    settings = get_settings()
    paciente_id = uuid7()
    org_id = 10
    token = create_intake_token(paciente_id, org_id, settings.SECRET_KEY)
    body = _make_fase2_request(paciente_id, token=token)

    # Should not raise any error
    await validar_intake_fase2(
        body=body,
        tenant_id=org_id,
        authorization=None,
    )


@pytest.mark.asyncio
async def test_validar_intake_fase2_missing_token_raises_401() -> None:
    paciente_id = uuid7()
    body = _make_fase2_request(paciente_id, token=None)

    with pytest.raises(UnauthorizedError, match="Token de acolhimento não fornecido"):
        await validar_intake_fase2(body=body, tenant_id=1, authorization=None)


@pytest.mark.asyncio
async def test_validar_intake_fase2_malformed_header_raises_401() -> None:
    paciente_id = uuid7()
    body = _make_fase2_request(paciente_id)

    with pytest.raises(UnauthorizedError, match="Formato do cabeçalho"):
        await validar_intake_fase2(body=body, tenant_id=1, authorization="Basic abc123")


@pytest.mark.asyncio
async def test_validar_intake_fase2_expired_token_raises_401() -> None:
    settings = get_settings()
    paciente_id = uuid7()
    org_id = 10
    expired_token = create_intake_token(
        paciente_id, org_id, settings.SECRET_KEY, expires_in_seconds=-10
    )
    body = _make_fase2_request(paciente_id)

    with pytest.raises(UnauthorizedError, match="expirado"):
        await validar_intake_fase2(
            body=body,
            tenant_id=org_id,
            authorization=f"Bearer {expired_token}",
        )


@pytest.mark.asyncio
async def test_validar_intake_fase2_mismatched_paciente_raises_403() -> None:
    settings = get_settings()
    paciente_a = uuid7()
    paciente_b = uuid7()
    org_id = 10
    token_a = create_intake_token(paciente_a, org_id, settings.SECRET_KEY)
    body_b = _make_fase2_request(paciente_b)

    with pytest.raises(ForbiddenError, match="não confere posse"):
        await validar_intake_fase2(
            body=body_b,
            tenant_id=org_id,
            authorization=f"Bearer {token_a}",
        )


@pytest.mark.asyncio
async def test_validar_intake_fase2_mismatched_tenant_raises_403() -> None:
    settings = get_settings()
    paciente_id = uuid7()
    token = create_intake_token(paciente_id, 1, settings.SECRET_KEY)
    body = _make_fase2_request(paciente_id)

    with pytest.raises(ForbiddenError, match="pertence à organização"):
        await validar_intake_fase2(
            body=body,
            tenant_id=2,
            authorization=f"Bearer {token}",
        )


@pytest.mark.asyncio
async def test_validar_posse_titular_missing_header_raises_401() -> None:
    titular_id = uuid7()
    with pytest.raises(UnauthorizedError, match="não fornecida"):
        await validar_posse_titular(id=titular_id, tenant_id=1, authorization=None)


@pytest.mark.asyncio
async def test_validar_posse_titular_intake_token_success() -> None:
    settings = get_settings()
    titular_id = uuid7()
    org_id = 5
    token = create_intake_token(titular_id, org_id, settings.SECRET_KEY)

    await validar_posse_titular(
        id=titular_id,
        tenant_id=org_id,
        authorization=f"Bearer {token}",
    )


@pytest.mark.asyncio
async def test_validar_posse_titular_intake_token_other_patient_raises_403() -> None:
    settings = get_settings()
    titular_id = uuid7()
    other_id = uuid7()
    org_id = 5
    token = create_intake_token(other_id, org_id, settings.SECRET_KEY)

    with pytest.raises(ForbiddenError, match="não confere posse"):
        await validar_posse_titular(
            id=titular_id,
            tenant_id=org_id,
            authorization=f"Bearer {token}",
        )


@pytest.mark.asyncio
async def test_validar_posse_titular_intake_token_other_org_raises_403() -> None:
    settings = get_settings()
    titular_id = uuid7()
    token = create_intake_token(titular_id, 1, settings.SECRET_KEY)

    with pytest.raises(ForbiddenError, match="pertence à organização"):
        await validar_posse_titular(
            id=titular_id,
            tenant_id=2,
            authorization=f"Bearer {token}",
        )


@pytest.mark.asyncio
async def test_validar_posse_titular_corporate_jwt_success() -> None:
    settings = get_settings()
    titular_id = uuid7()
    org_id = 5

    # ADMIN_GLOBAL
    admin_jwt = _make_jwt(uuid4(), org_id, Role.ADMIN_GLOBAL, settings.JWT_SECRET_KEY)
    await validar_posse_titular(
        id=titular_id, tenant_id=org_id, authorization=f"Bearer {admin_jwt}"
    )

    # GESTOR_UNIDADE
    gestor_jwt = _make_jwt(
        uuid4(), org_id, Role.GESTOR_UNIDADE, settings.JWT_SECRET_KEY
    )
    await validar_posse_titular(
        id=titular_id, tenant_id=org_id, authorization=f"Bearer {gestor_jwt}"
    )


@pytest.mark.asyncio
async def test_validar_posse_titular_patient_jwt_success() -> None:
    settings = get_settings()
    titular_id = uuid7()
    org_id = 5
    patient_jwt = _make_jwt(titular_id, org_id, Role.PACIENTE, settings.JWT_SECRET_KEY)

    await validar_posse_titular(
        id=titular_id, tenant_id=org_id, authorization=f"Bearer {patient_jwt}"
    )


@pytest.mark.asyncio
async def test_validar_posse_titular_patient_jwt_other_patient_raises_403() -> None:
    settings = get_settings()
    titular_id = uuid7()
    other_patient_id = uuid7()
    org_id = 5
    patient_jwt = _make_jwt(
        other_patient_id, org_id, Role.PACIENTE, settings.JWT_SECRET_KEY
    )

    with pytest.raises(ForbiddenError, match="não é o titular informado"):
        await validar_posse_titular(
            id=titular_id, tenant_id=org_id, authorization=f"Bearer {patient_jwt}"
        )


@pytest.mark.asyncio
async def test_validar_posse_titular_unauthorized_role_raises_403() -> None:
    settings = get_settings()
    titular_id = uuid7()
    org_id = 5
    medico_jwt = _make_jwt(uuid4(), org_id, Role.MEDICO, settings.JWT_SECRET_KEY)

    with pytest.raises(ForbiddenError, match="não possui permissão"):
        await validar_posse_titular(
            id=titular_id, tenant_id=org_id, authorization=f"Bearer {medico_jwt}"
        )
