"""Unit tests for Tier 3 Contextual Clinical ABAC/ReBAC policy (CFM 2.314/2022)."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from src.core.errors import ForbiddenError, NotFoundError
from src.modules.consultation.application.policies.clinical_access_policy import (
    ClinicalAccessPolicy,
)
from src.modules.consultation.application.ports.atendimento_reader_port import (
    AtendimentoResumoDTO,
)


def _make_reader(
    atend_id: object = None,
    medico_id: object = None,
    status: str = "EM_ATENDIMENTO",
    tcle_hash: str | None = "a" * 64,
) -> AsyncMock:
    from uuid import UUID

    aid = atend_id if isinstance(atend_id, UUID) else uuid4()
    mid = medico_id if isinstance(medico_id, UUID) else uuid4()
    reader = AsyncMock()
    reader.obter_resumo.return_value = AtendimentoResumoDTO(
        atendimento_id=aid,
        organizacao_id=1,
        medico_id=mid,
        status=status,
        tcle_hash=tcle_hash,
        is_terminal=status in {"CONCLUIDO", "PACIENTE_AUSENTE", "CANCELADO_PACIENTE"},
    )
    return reader


@pytest.mark.asyncio
async def test_clinical_access_not_found() -> None:
    """Verify NotFoundError is raised when attendance record does not exist."""
    reader = AsyncMock()
    reader.obter_resumo.return_value = None

    with pytest.raises(NotFoundError, match="não encontrado"):
        await ClinicalAccessPolicy.validar_acesso_clinico(
            atendimento_id=uuid4(),
            medico_id=uuid4(),
            reader=reader,
        )


@pytest.mark.asyncio
async def test_clinical_access_missing_tcle() -> None:
    """Verify ForbiddenError is raised when patient has not signed digital TCLE."""
    atend_id = uuid4()
    medico_id = uuid4()
    reader = _make_reader(atend_id=atend_id, medico_id=medico_id, tcle_hash=None)

    with pytest.raises(ForbiddenError, match="TCLE"):
        await ClinicalAccessPolicy.validar_acesso_clinico(
            atendimento_id=atend_id,
            medico_id=medico_id,
            reader=reader,
        )


@pytest.mark.asyncio
async def test_clinical_access_physician_mismatch() -> None:
    """Verify ForbiddenError when caller is not the assigned physician."""
    atend_id = uuid4()
    atend_medico_id = uuid4()
    intruding_medico_id = uuid4()
    reader = _make_reader(atend_id=atend_id, medico_id=atend_medico_id)

    with pytest.raises(ForbiddenError, match="médico autenticado não é o profissional"):
        await ClinicalAccessPolicy.validar_acesso_clinico(
            atendimento_id=atend_id,
            medico_id=intruding_medico_id,
            reader=reader,
        )


@pytest.mark.asyncio
async def test_clinical_access_inactive_encounter() -> None:
    """Verify ForbiddenError when attendance is not in active consultation status."""
    atend_id = uuid4()
    medico_id = uuid4()
    reader = _make_reader(atend_id=atend_id, medico_id=medico_id, status="CONCLUIDO")

    with pytest.raises(ForbiddenError, match="atendimento ativo"):
        await ClinicalAccessPolicy.validar_acesso_clinico(
            atendimento_id=atend_id,
            medico_id=medico_id,
            reader=reader,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["EM_ATENDIMENTO", "CHAMANDO_PACIENTE"])
async def test_clinical_access_granted_when_all_conditions_met(status: str) -> None:
    """Verify access granted when TCLE is signed and physician matches."""
    atend_id = uuid4()
    medico_id = uuid4()
    reader = _make_reader(atend_id=atend_id, medico_id=medico_id, status=status)

    # Should complete without raising any exception
    await ClinicalAccessPolicy.validar_acesso_clinico(
        atendimento_id=atend_id,
        medico_id=medico_id,
        reader=reader,
    )
