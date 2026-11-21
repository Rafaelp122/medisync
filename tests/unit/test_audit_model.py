from typing import TYPE_CHECKING, cast

import pytest

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
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
        atendimento_id=atend_id,
        ator_tipo=AtorTipo.PROFISSIONAL,
        ator_papel=AtorPapel.MEDICO,
        tipo_evento="CHAMADA_INICIADA",
        ator_id=med_id,
        estado_anterior="APTO_PARA_CHAMADA",
        novo_estado="CHAMANDO_PACIENTE",
        tcle_hash=_SAMPLE_TCLE_HASH,
        payload={"sala_livekit": "atend_123"},
        ip_origem="192.168.1.100",
        id=event_id,
    )

    assert event.id == event_id
    assert not hasattr(event, "organizacao_id")
    assert event.atendimento_id == atend_id
    assert event.ator_tipo == AtorTipo.PROFISSIONAL
    assert event.ator_papel == AtorPapel.MEDICO
    assert event.ator_id == med_id
    assert event.tipo_evento == "CHAMADA_INICIADA"
    assert event.estado_anterior == "APTO_PARA_CHAMADA"
    assert event.novo_estado == "CHAMANDO_PACIENTE"
    assert event.tcle_hash == _SAMPLE_TCLE_HASH
    assert event.payload == {"sala_livekit": "atend_123"}
    assert event.ip_origem == "192.168.1.100"
    assert event.registrado_em is not None


def test_create_audit_event_sistema_actor_without_ator_id() -> None:
    atend_id = uuid7()

    event = make_audit_event(
        atendimento_id=atend_id,
        ator_tipo=AtorTipo.SISTEMA,
        ator_papel=AtorPapel.WORKER_ARQ,
        tipo_evento="CHECK_NO_SHOW_EXCEEDED",
        ator_id=None,
        estado_anterior="CHAMANDO_PACIENTE",
        novo_estado="PACIENTE_AUSENTE",
    )

    assert event.ator_tipo == AtorTipo.SISTEMA
    assert event.ator_id is None
    assert event.ator_papel == AtorPapel.WORKER_ARQ


def test_audit_event_validacoes_campos_obrigatorios() -> None:
    atend_id = uuid7()
    med_id = uuid7()

    # tipo_evento vazio
    with pytest.raises(AuditoriaInvalidaError, match="tipo_evento"):
        AuditEvent(
            atendimento_id=atend_id,
            ator_tipo=AtorTipo.PROFISSIONAL,
            ator_papel=AtorPapel.MEDICO,
            tipo_evento="   ",
            ator_id=med_id,
        )

    # Ator humano sem ator_id
    with pytest.raises(AuditoriaInvalidaError, match="ator_id"):
        AuditEvent(
            atendimento_id=atend_id,
            ator_tipo=AtorTipo.PROFISSIONAL,
            ator_papel=AtorPapel.MEDICO,
            tipo_evento="EVT",
            ator_id=None,
        )

    with pytest.raises(AuditoriaInvalidaError, match="ator_id"):
        AuditEvent(
            atendimento_id=atend_id,
            ator_tipo=AtorTipo.PACIENTE,
            ator_papel=AtorPapel.PACIENTE,
            tipo_evento="EVT",
            ator_id=None,
        )

    # tcle_hash com tamanho incorreto
    with pytest.raises(AuditoriaInvalidaError, match="TCLE"):
        AuditEvent(
            atendimento_id=atend_id,
            ator_tipo=AtorTipo.SISTEMA,
            ator_papel=AtorPapel.SISTEMA,
            tipo_evento="EVT",
            tcle_hash="invalid_hash_length",
        )

    # IP de origem inválido
    with pytest.raises(AuditoriaInvalidaError, match="IP"):
        AuditEvent(
            atendimento_id=atend_id,
            ator_tipo=AtorTipo.SISTEMA,
            ator_papel=AtorPapel.SISTEMA,
            tipo_evento="EVT",
            ip_origem="999.999.999.999",
        )

    # ator_tipo desconhecido
    with pytest.raises(AuditoriaInvalidaError, match="ator_tipo"):
        AuditEvent(
            atendimento_id=atend_id,
            ator_tipo="ATOR_ALIENIGENA",
            ator_papel=AtorPapel.SISTEMA,
            tipo_evento="EVT",
        )

    # ator_papel desconhecido
    with pytest.raises(AuditoriaInvalidaError, match="ator_papel"):
        AuditEvent(
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
    from src.core.audit.service import AuditService

    from tests.doubles import FakeAsyncSession

    session = FakeAsyncSession()
    atend_id = uuid7()
    med_id = uuid7()

    evt = await AuditService.record_event(
        cast("AsyncSession", session),
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
    assert evt in session.added


def test_audit_event_gestor_unidade_and_null_atendimento_id() -> None:
    assert set(AtorPapel) == {
        AtorPapel.PACIENTE,
        AtorPapel.MEDICO,
        AtorPapel.GESTOR_UNIDADE,
        AtorPapel.FATURAMENTO,
        AtorPapel.WORKER_ARQ,
        AtorPapel.SISTEMA,
    }
    gestor_id = uuid7()
    evt = AuditEvent(
        atendimento_id=None,
        ator_tipo=AtorTipo.PROFISSIONAL,
        ator_papel=AtorPapel.GESTOR_UNIDADE,
        tipo_evento="CONFIGURACAO_GERAL_ALTERADA",
        ator_id=gestor_id,
        payload={"parametro": "valor"},
    )
    assert evt.atendimento_id is None
    assert evt.ator_papel == "GESTOR_UNIDADE"
    assert evt.ator_id == gestor_id
    assert evt.tipo_evento == "CONFIGURACAO_GERAL_ALTERADA"


def test_audit_event_ator_papel_invalido_mensagem_ofensiva_e_esperados() -> None:
    with pytest.raises(AuditoriaInvalidaError) as exc_info:
        AuditEvent(
            atendimento_id=None,
            ator_tipo=AtorTipo.SISTEMA,
            ator_papel="PAPEL_INEXISTENTE",
            tipo_evento="SISTEMA_EVENTO",
        )
    msg = str(exc_info.value)
    assert "PAPEL_INEXISTENTE" in msg
    assert "esperados:" in msg
    assert "GESTOR_UNIDADE" in msg
    assert "ADMIN_GLOBAL" not in msg
