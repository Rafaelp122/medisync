"""Unit tests for AuditEvent domain model, actor validations, and immutability."""

import pytest
from src.core.audit.exceptions import (
    AuditoriaImutavelError,
    AuditoriaInvalidaError,
)
from src.core.audit.models import (
    AtorPapel,
    AtorTipo,
    AuditEvent,
)
from src.core.errors import DomainError, ValidationError
from src.core.uuid7 import uuid7

from tests.factories.audit import make_audit_event

_SAMPLE_TCLE_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_audit_exceptions_hierarchy_and_codes() -> None:
    err_imutavel = AuditoriaImutavelError("UPDATE proibido em auditoria.")
    assert isinstance(err_imutavel, DomainError)
    assert err_imutavel.status_code == 409
    assert err_imutavel.code == "AUDITORIA_IMUTAVEL"

    err_invalida = AuditoriaInvalidaError("Ator profissional requer ator_id.")
    assert isinstance(err_invalida, ValidationError)
    assert err_invalida.status_code == 422
    assert err_invalida.code == "AUDITORIA_INVALIDA"


def test_create_audit_event_profissional_actor_success() -> None:
    atend_id = uuid7()
    med_id = uuid7()
    event_id = uuid7()

    event = make_audit_event(
        organizacao_id=1,
        atendimento_id=atend_id,
        ator_tipo=AtorTipo.PROFISSIONAL,
        ator_papel=AtorPapel.MEDICO,
        tipo_evento="CHAMADA_INICIADA",
        ator_id=med_id,
        estado_anterior="APTO_PARA_CHAMADA",
        novo_estado="CHAMANDO_PACIENTE",
        tcle_hash=_SAMPLE_TCLE_HASH,
        payload={"sala_livekit": "org_1_atend_123"},
        ip_origem="192.168.1.100",
        id=event_id,
    )

    assert event.id == event_id
    assert event.organizacao_id == 1
    assert event.atendimento_id == atend_id
    assert event.ator_tipo == AtorTipo.PROFISSIONAL
    assert event.ator_papel == AtorPapel.MEDICO
    assert event.ator_id == med_id
    assert event.tipo_evento == "CHAMADA_INICIADA"
    assert event.estado_anterior == "APTO_PARA_CHAMADA"
    assert event.novo_estado == "CHAMANDO_PACIENTE"
    assert event.tcle_hash == _SAMPLE_TCLE_HASH
    assert event.payload == {"sala_livekit": "org_1_atend_123"}
    assert event.ip_origem == "192.168.1.100"
    assert event.registrado_em is not None


def test_create_audit_event_sistema_actor_without_ator_id() -> None:
    atend_id = uuid7()

    event = make_audit_event(
        organizacao_id=1,
        atendimento_id=atend_id,
        ator_tipo=AtorTipo.SISTEMA,
        ator_papel=AtorPapel.WORKER_ARQ,
        tipo_evento="CHECK_NO_SHOW_EXCEEDED",
        ator_id=None,  # SISTEMA pode ter ator_id nulo
        estado_anterior="CHAMANDO_PACIENTE",
        novo_estado="PACIENTE_AUSENTE",
    )

    assert event.ator_tipo == AtorTipo.SISTEMA
    assert event.ator_id is None
    assert event.ator_papel == AtorPapel.WORKER_ARQ


def test_audit_event_validacoes_campos_obrigatorios() -> None:
    atend_id = uuid7()
    med_id = uuid7()

    # organizacao_id inválido
    with pytest.raises(AuditoriaInvalidaError, match="organizacao_id"):
        AuditEvent(
            organizacao_id=0,
            atendimento_id=atend_id,
            ator_tipo=AtorTipo.PROFISSIONAL,
            ator_papel=AtorPapel.MEDICO,
            tipo_evento="EVT",
            ator_id=med_id,
        )

    # tipo_evento vazio
    with pytest.raises(AuditoriaInvalidaError, match="tipo_evento"):
        AuditEvent(
            organizacao_id=1,
            atendimento_id=atend_id,
            ator_tipo=AtorTipo.PROFISSIONAL,
            ator_papel=AtorPapel.MEDICO,
            tipo_evento="   ",
            ator_id=med_id,
        )

    # Ator humano sem ator_id
    with pytest.raises(AuditoriaInvalidaError, match="ator_id"):
        AuditEvent(
            organizacao_id=1,
            atendimento_id=atend_id,
            ator_tipo=AtorTipo.PROFISSIONAL,
            ator_papel=AtorPapel.MEDICO,
            tipo_evento="EVT",
            ator_id=None,
        )

    with pytest.raises(AuditoriaInvalidaError, match="ator_id"):
        AuditEvent(
            organizacao_id=1,
            atendimento_id=atend_id,
            ator_tipo=AtorTipo.PACIENTE,
            ator_papel=AtorPapel.PACIENTE,
            tipo_evento="EVT",
            ator_id=None,
        )

    # tcle_hash com tamanho incorreto
    with pytest.raises(AuditoriaInvalidaError, match="TCLE"):
        AuditEvent(
            organizacao_id=1,
            atendimento_id=atend_id,
            ator_tipo=AtorTipo.SISTEMA,
            ator_papel=AtorPapel.SISTEMA,
            tipo_evento="EVT",
            tcle_hash="invalid_hash_length",
        )

    # IP de origem inválido
    with pytest.raises(AuditoriaInvalidaError, match="IP"):
        AuditEvent(
            organizacao_id=1,
            atendimento_id=atend_id,
            ator_tipo=AtorTipo.SISTEMA,
            ator_papel=AtorPapel.SISTEMA,
            tipo_evento="EVT",
            ip_origem="999.999.999.999",
        )

    # ator_tipo desconhecido
    with pytest.raises(AuditoriaInvalidaError, match="ator_tipo"):
        AuditEvent(
            organizacao_id=1,
            atendimento_id=atend_id,
            ator_tipo="ATOR_ALIENIGENA",
            ator_papel=AtorPapel.SISTEMA,
            tipo_evento="EVT",
        )

    # ator_papel desconhecido
    with pytest.raises(AuditoriaInvalidaError, match="ator_papel"):
        AuditEvent(
            organizacao_id=1,
            atendimento_id=atend_id,
            ator_tipo=AtorTipo.SISTEMA,
            ator_papel="PAPEL_INEXISTENTE",
            tipo_evento="EVT",
        )


def test_audit_event_immutability_hooks_raise_error() -> None:
    from src.core.audit.models import (
        impedir_delete_audit_event,
        impedir_update_audit_event,
    )

    event = make_audit_event(
        organizacao_id=1,
        ator_tipo=AtorTipo.SISTEMA,
        ator_papel=AtorPapel.SISTEMA,
        tipo_evento="TEST_IMMUTABLE",
    )

    with pytest.raises(AuditoriaImutavelError, match=r"UPDATE.*proibidas"):
        impedir_update_audit_event(None, None, event)

    with pytest.raises(AuditoriaImutavelError, match=r"DELETE.*proibidas"):
        impedir_delete_audit_event(None, None, event)


@pytest.mark.asyncio
async def test_audit_service_record_event_sync_dispatch() -> None:
    from unittest.mock import MagicMock

    from src.core.audit.service import AuditService

    mock_session = MagicMock()
    atend_id = uuid7()
    med_id = uuid7()

    evt = await AuditService.record_event(
        mock_session,
        organizacao_id=1,
        atendimento_id=atend_id,
        ator_tipo=AtorTipo.PROFISSIONAL,
        ator_papel=AtorPapel.MEDICO,
        tipo_evento="CONSULTA_INICIADA",
        ator_id=med_id,
        estado_anterior="APTO_PARA_CHAMADA",
        novo_estado="EM_ATENDIMENTO",
    )

    assert evt.id is not None
    assert evt.tipo_evento == "CONSULTA_INICIADA"
    assert evt.ator_id == med_id
    mock_session.add.assert_called_once_with(evt)
