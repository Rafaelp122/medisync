"""Unit tests for LiveKit presentation dependencies (validar_acesso_livekit)."""

from uuid import UUID, uuid4

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from src.core.config import get_settings
from src.core.errors import ConflictError, ForbiddenError
from src.modules.auth.infrastructure.jwt_token_service import JWTTokenService
from src.modules.consultation.application.ports.atendimento_reader_port import (
    AtendimentoResumoDTO,
)
from src.modules.consultation.presentation.dependencies import validar_acesso_livekit
from src.modules.consultation.presentation.schemas import LiveKitTokenRequest

from tests.doubles import FakeAtendimentoReader


def _make_doctor_token(doctor_id: UUID, org_id: int) -> HTTPAuthorizationCredentials:
    service = JWTTokenService(secret_key=get_settings().JWT_SECRET_KEY)
    token = service.gerar_tokens(
        usuario_id=doctor_id,
        organizacao_id=org_id,
        papel="MEDICO",  # type: ignore[arg-type]
    ).access_token
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@pytest.mark.asyncio
async def test_validar_acesso_livekit_paciente_ausente_retorna_conflict_error() -> None:
    """Verifica que status PACIENTE_AUSENTE lança ConflictError (HTTP 409)
    com código ATENDIMENTO_EXPIRADO_NO_SHOW (US-08).
    """
    atend_id = uuid4()
    doc_id = uuid4()
    org_id = 1
    reader = FakeAtendimentoReader(
        AtendimentoResumoDTO(
            atendimento_id=atend_id,
            organizacao_id=org_id,
            medico_id=doc_id,
            paciente_id=uuid4(),
            status="PACIENTE_AUSENTE",
            tcle_hash="a" * 64,
            is_terminal=True,
        )
    )
    req = LiveKitTokenRequest(
        organizacao_id=org_id,
        participant_id=doc_id,
        role="medico",
    )
    creds = _make_doctor_token(doc_id, org_id)

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
    org_id = 1
    reader = FakeAtendimentoReader(
        AtendimentoResumoDTO(
            atendimento_id=atend_id,
            organizacao_id=org_id,
            medico_id=doc_id,
            paciente_id=uuid4(),
            status="CONCLUIDO",
            tcle_hash="a" * 64,
            is_terminal=True,
        )
    )
    req = LiveKitTokenRequest(
        organizacao_id=org_id,
        participant_id=doc_id,
        role="medico",
    )
    creds = _make_doctor_token(doc_id, org_id)

    with pytest.raises(ForbiddenError) as exc_info:
        await validar_acesso_livekit(
            atendimento_id=atend_id,
            request=req,
            reader=reader,
            credentials=creds,
        )

    assert "CONCLUIDO" in exc_info.value.detail
    assert exc_info.value.status_code == 403
