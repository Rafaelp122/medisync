"""Unit tests for Tier 3 Contextual Clinical ABAC/ReBAC policy (CFM 2.314/2022)."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.errors import ForbiddenError, NotFoundError
from src.modules.consultation.application.policies.clinical_access_policy import (
    ClinicalAccessPolicy,
)


@pytest.mark.asyncio
async def test_clinical_access_not_found() -> None:
    """Verify NotFoundError is raised when attendance record does not exist."""
    session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.mappings.return_value.one_or_none.return_value = None
    session.execute.return_value = mock_result

    with pytest.raises(NotFoundError, match="não encontrado"):
        await ClinicalAccessPolicy.validar_acesso_clinico(
            atendimento_id=uuid4(),
            medico_id=uuid4(),
            session=session,
        )


@pytest.mark.asyncio
async def test_clinical_access_missing_tcle() -> None:
    """Verify ForbiddenError is raised when patient has not signed digital TCLE."""
    atend_id = uuid4()
    medico_id = uuid4()

    session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.mappings.return_value.one_or_none.return_value = {
        "id": atend_id,
        "organizacao_id": 1,
        "medico_id": medico_id,
        "status": "EM_ATENDIMENTO",
        "tcle_hash": None,  # No TCLE
    }
    session.execute.return_value = mock_result

    with pytest.raises(ForbiddenError, match="TCLE"):
        await ClinicalAccessPolicy.validar_acesso_clinico(
            atendimento_id=atend_id,
            medico_id=medico_id,
            session=session,
        )


@pytest.mark.asyncio
async def test_clinical_access_physician_mismatch() -> None:
    """Verify ForbiddenError when caller is not the assigned physician."""
    atend_id = uuid4()
    atend_medico_id = uuid4()
    intruding_medico_id = uuid4()

    session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.mappings.return_value.one_or_none.return_value = {
        "id": atend_id,
        "organizacao_id": 1,
        "medico_id": atend_medico_id,
        "status": "EM_ATENDIMENTO",
        "tcle_hash": "a" * 64,
    }
    session.execute.return_value = mock_result

    with pytest.raises(ForbiddenError, match="médico autenticado não é o profissional"):
        await ClinicalAccessPolicy.validar_acesso_clinico(
            atendimento_id=atend_id,
            medico_id=intruding_medico_id,
            session=session,
        )


@pytest.mark.asyncio
async def test_clinical_access_inactive_encounter() -> None:
    """Verify ForbiddenError when attendance is not in active consultation status."""
    atend_id = uuid4()
    medico_id = uuid4()

    session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.mappings.return_value.one_or_none.return_value = {
        "id": atend_id,
        "organizacao_id": 1,
        "medico_id": medico_id,
        "status": "CONCLUIDO",  # Inactive
        "tcle_hash": "b" * 64,
    }
    session.execute.return_value = mock_result

    with pytest.raises(ForbiddenError, match="atendimento ativo"):
        await ClinicalAccessPolicy.validar_acesso_clinico(
            atendimento_id=atend_id,
            medico_id=medico_id,
            session=session,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["EM_ATENDIMENTO", "CHAMANDO_PACIENTE"])
async def test_clinical_access_granted_when_all_conditions_met(status: str) -> None:
    """Verify access granted when TCLE is signed and physician matches."""
    atend_id = uuid4()
    medico_id = uuid4()

    session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.mappings.return_value.one_or_none.return_value = {
        "id": atend_id,
        "organizacao_id": 1,
        "medico_id": medico_id,
        "status": status,
        "tcle_hash": "c" * 64,
    }
    session.execute.return_value = mock_result

    # Should complete without raising any exception
    await ClinicalAccessPolicy.validar_acesso_clinico(
        atendimento_id=atend_id,
        medico_id=medico_id,
        session=session,
    )
