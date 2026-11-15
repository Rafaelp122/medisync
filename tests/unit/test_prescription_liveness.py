"""Unit tests for US-15 Facial Liveness gate on controlled prescriptions."""

from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import pytest
from src.core.audit import AtorPapel
from src.core.uuid7 import uuid7
from src.modules.consultation.application.dtos import (
    CriarItemPrescricaoDTO,
    EmitirDocumentoClinicoCommand,
    VerificarLivenessCommand,
)
from src.modules.consultation.application.ports.liveness_verification_port import (
    LivenessVerificationPort,
)
from src.modules.consultation.application.services.documento_service import (
    DocumentoService,
)
from src.modules.consultation.domain.exceptions import (
    ProvaDeVidaObrigatoriaError,
    SpoofingFacialDetectadoError,
)
from src.modules.consultation.infrastructure.liveness_adapter import (
    DatavalidLivenessAdapter,
    GovBrLivenessAdapter,
    MockLivenessAdapter,
)
from src.modules.consultation.infrastructure.memory_signed_cache import (
    MemorySignedCache,
)

from tests.doubles import (
    FakeAddedResult,
    FakeAsyncSession,
    FakeAuditTrail,
    FakeICPBrasilSigner,
    FakeMemoryStorage,
    FakePDFGenerator,
    FakeResult,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_ORG_ID = 5


def _make_service(
    session: FakeAsyncSession,
    *,
    liveness_verifier: LivenessVerificationPort | None = None,
    audit_trail: FakeAuditTrail | None = None,
) -> DocumentoService:
    return DocumentoService(
        session=cast("AsyncSession", session),
        pdf_generator=FakePDFGenerator(),
        signer=FakeICPBrasilSigner(),
        storage=FakeMemoryStorage(),
        cache=MemorySignedCache(),
        audit_trail=audit_trail,
        liveness_verifier=liveness_verifier,
    )


def _c1_command(
    atendimento_id: UUID,
    medico_id: UUID,
    *,
    tipo_documento: str = "RECEITA_CONTROLE_ESPECIAL_C1",
    controle_especial: bool = True,
    liveness_hash: str | None = None,
    justificativa_excecao: str | None = None,
) -> EmitirDocumentoClinicoCommand:
    return EmitirDocumentoClinicoCommand(
        atendimento_id=atendimento_id,
        organizacao_id=_ORG_ID,
        medico_id=medico_id,
        tipo_documento=tipo_documento,
        itens=[
            CriarItemPrescricaoDTO(
                medicamento="Fluoxetina 20mg"
                if controle_especial
                else "Dipirona 500mg",
                dosagem="1 cp",
                posologia="1 cp ao dia pela manhã",
                duracao="30 dias",
                controle_especial=controle_especial,
            )
        ],
        liveness_verificacao_hash=liveness_hash,
        justificativa_excecao_liveness=justificativa_excecao,
    )


@pytest.mark.asyncio
async def test_emissao_lista_c1_sem_liveness_bloqueada() -> None:
    """Controlled C1 prescription without liveness proof or justification raises 422."""
    atendimento_id = uuid7()
    medico_id = uuid7()
    adapter = MockLivenessAdapter(isolated=True)
    session = FakeAsyncSession([])
    svc = _make_service(session, liveness_verifier=adapter)

    with pytest.raises(ProvaDeVidaObrigatoriaError, match="controle especial"):
        await svc.emitir_documento(_c1_command(atendimento_id, medico_id))

    # Even if declared RECEITA_SIMPLES, controle_especial=True still triggers gate.
    with pytest.raises(ProvaDeVidaObrigatoriaError):
        await svc.emitir_documento(
            _c1_command(
                atendimento_id,
                medico_id,
                tipo_documento="RECEITA_SIMPLES",
                controle_especial=True,
                justificativa_excecao="Curto",
            )
        )


@pytest.mark.asyncio
async def test_liveness_spoofing_detectado_bloqueia_e_audita() -> None:
    """Spoof frames raise SpoofingFacialDetectadoError, audit event, and block emit."""
    atendimento_id = uuid7()
    medico_id = uuid7()
    paciente_id = uuid7()
    adapter = MockLivenessAdapter(isolated=True)
    audit = FakeAuditTrail()
    session = FakeAsyncSession([])
    svc = _make_service(session, liveness_verifier=adapter, audit_trail=audit)

    challenge = await svc.solicitar_desafio_liveness(atendimento_id)
    assert len(challenge.instrucoes_movimento) >= 1

    verify_cmd = VerificarLivenessCommand(
        atendimento_id=atendimento_id,
        organizacao_id=_ORG_ID,
        ator_id=paciente_id,
        ator_papel=AtorPapel.PACIENTE.value,
        challenge_id=challenge.challenge_id,
        liveness_payload="SPOOF_STATIC_PHOTO_FRAME",
        latitude=-23.5505,
        longitude=-46.6333,
    )

    with pytest.raises(SpoofingFacialDetectadoError, match=r"score=0\.42"):
        await svc.verificar_liveness_prescricao(verify_cmd)

    assert len(audit.get_events_by_type("SPOOFING_FACIAL_DETECTADO")) == 1
    assert await adapter.obter_hash_aprovado(atendimento_id) is None

    with pytest.raises(ProvaDeVidaObrigatoriaError):
        await svc.emitir_documento(_c1_command(atendimento_id, medico_id))


@pytest.mark.asyncio
async def test_fluxo_completo_desafio_liveness_aprovado_permite_emissao_c1() -> None:
    """Approved facial liveness persists SHA-256 hash and unlocks Lista C1 emit."""
    atendimento_id = uuid7()
    medico_id = uuid7()
    paciente_id = uuid7()
    added: list[Any] = []
    session = FakeAsyncSession([FakeResult(None), FakeAddedResult(added)], added)
    adapter = MockLivenessAdapter(isolated=True)
    audit = FakeAuditTrail()
    svc = _make_service(session, liveness_verifier=adapter, audit_trail=audit)

    challenge = await svc.solicitar_desafio_liveness(atendimento_id)
    verification = await svc.verificar_liveness_prescricao(
        VerificarLivenessCommand(
            atendimento_id=atendimento_id,
            organizacao_id=_ORG_ID,
            ator_id=paciente_id,
            ator_papel=AtorPapel.PACIENTE.value,
            challenge_id=challenge.challenge_id,
            liveness_payload="LIVE_FRAMES_PISCAR_SORRIR_OK",
        )
    )

    assert verification.status == "APROVADO"
    assert verification.liveness_score >= 0.95
    assert verification.verificacao_hash.startswith("sha256_")
    assert len(audit.get_events_by_type("LIVENESS_FACIAL_APROVADO")) == 1

    doc = await svc.emitir_documento(
        _c1_command(
            atendimento_id,
            medico_id,
            liveness_hash=verification.verificacao_hash,
        )
    )

    assert doc.liveness_verificacao_hash == verification.verificacao_hash
    assert doc.justificativa_excecao_liveness is None
    assert session.commits == 2


@pytest.mark.asyncio
async def test_excecao_clinica_justificada_permite_emissao_sem_liveness() -> None:
    """Medical justification >= 10 chars allows C1 emit if camera unavailable."""
    atendimento_id = uuid7()
    medico_id = uuid7()
    added: list[Any] = []
    session = FakeAsyncSession([FakeResult(None), FakeAddedResult(added)], added)
    svc = _make_service(session, liveness_verifier=MockLivenessAdapter(isolated=True))

    justificativa = "Paciente acamado em domicilio sem camera frontal disponivel."
    doc = await svc.emitir_documento(
        _c1_command(
            atendimento_id,
            medico_id,
            justificativa_excecao=justificativa,
        )
    )

    assert doc.liveness_verificacao_hash is None
    assert doc.justificativa_excecao_liveness == justificativa


@pytest.mark.asyncio
async def test_receita_simples_sem_item_especial_nao_exige_liveness() -> None:
    """Regular non-controlled prescription skips facial liveness verification."""
    atendimento_id = uuid7()
    medico_id = uuid7()
    added: list[Any] = []
    session = FakeAsyncSession([FakeResult(None), FakeAddedResult(added)], added)
    svc = _make_service(session, liveness_verifier=MockLivenessAdapter(isolated=True))

    doc = await svc.emitir_documento(
        _c1_command(
            atendimento_id,
            medico_id,
            tipo_documento="RECEITA_SIMPLES",
            controle_especial=False,
        )
    )

    assert doc.liveness_verificacao_hash is None
    assert doc.justificativa_excecao_liveness is None


@pytest.mark.asyncio
async def test_govbr_e_datavalid_adapters_retornam_hashes_distintos() -> None:
    """Provider-specific adapters must bind provider namespace into output hash."""
    atendimento_id = uuid7()
    govbr = GovBrLivenessAdapter(isolated=True)
    datavalid = DatavalidLivenessAdapter(isolated=True)

    c1 = await govbr.gerar_desafio(atendimento_id)
    c2 = await datavalid.gerar_desafio(atendimento_id)
    r1 = await govbr.verificar_prova_de_vida(atendimento_id, c1.challenge_id, "LIVE_OK")
    r2 = await datavalid.verificar_prova_de_vida(
        atendimento_id, c2.challenge_id, "LIVE_OK"
    )

    assert r1.status == "APROVADO"
    assert r2.status == "APROVADO"
    assert r1.verificacao_hash.startswith("sha256_")
    assert r2.verificacao_hash.startswith("sha256_")
    assert r1.verificacao_hash != r2.verificacao_hash
