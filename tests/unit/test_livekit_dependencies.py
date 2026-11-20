"""Unit tests for LiveKit presentation dependencies (validar_acesso_livekit)."""

from uuid import UUID, uuid4

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from src.core.authz.token import create_access_token
from src.core.errors import ConflictError, ForbiddenError
from src.modules.consultation.application.ports.atendimento_reader_port import (
    AtendimentoResumoDTO,
)
from src.modules.consultation.presentation.dependencies import validar_acesso_livekit
from src.modules.consultation.presentation.schemas import LiveKitTokenRequest

from tests.doubles import FakeAtendimentoReader


def _make_doctor_token(doctor_id: UUID) -> HTTPAuthorizationCredentials:
    token = create_access_token(
        usuario_id=doctor_id,
        papel="MEDICO",
    )
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@pytest.mark.asyncio
async def test_validar_acesso_livekit_paciente_ausente_retorna_conflict_error() -> None:
    """Verifica que status PACIENTE_AUSENTE lança ConflictError (HTTP 409)
    com código ATENDIMENTO_EXPIRADO_NO_SHOW (US-08).
    """
    atend_id = uuid4()
    doc_id = uuid4()
    reader = FakeAtendimentoReader(
        AtendimentoResumoDTO(
            atendimento_id=atend_id,
            medico_id=doc_id,
            paciente_id=uuid4(),
            status="PACIENTE_AUSENTE",
            tcle_hash="a" * 64,
            is_terminal=True,
        )
    )
    req = LiveKitTokenRequest(
        participant_id=doc_id,
        role="medico",
    )
    creds = _make_doctor_token(doc_id)

    with pytest.raises(ConflictError) as exc_info:
        await validar_acesso_livekit(
            atendimento_id=atend_id,
            request=req,
            reader=reader,
            credentials=creds,
        )

    assert "PACIENTE_AUSENTE" in exc_info.value.detail
    assert exc_info.value.code == "ATENDIMENTO_EXPIRADO_NO_SHOW"
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_validar_acesso_livekit_status_concluido_mantem_forbidden_error() -> None:
    """Verifica que outros status terminais (ex.: CONCLUIDO) continuam
    lançando ForbiddenError (HTTP 403).
    """
    atend_id = uuid4()
    doc_id = uuid4()
    reader = FakeAtendimentoReader(
        AtendimentoResumoDTO(
            atendimento_id=atend_id,
            medico_id=doc_id,
            paciente_id=uuid4(),
            status="CONCLUIDO",
            tcle_hash="a" * 64,
            is_terminal=True,
        )
    )
    req = LiveKitTokenRequest(
        participant_id=doc_id,
        role="medico",
    )
    creds = _make_doctor_token(doc_id)

    with pytest.raises(ForbiddenError) as exc_info:
        await validar_acesso_livekit(
            atendimento_id=atend_id,
            request=req,
            reader=reader,
            credentials=creds,
        )

    assert "CONCLUIDO" in exc_info.value.detail
    assert exc_info.value.status_code == 403
