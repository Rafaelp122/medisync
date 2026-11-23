"""Unit tests for US-15 Facial Liveness gate on controlled prescriptions."""

from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import pytest
from src.core.audit import AtorPapel
from src.core.errors import ForbiddenError
from src.core.uuid7 import uuid7
from src.modules.consultation.application.dtos import (
    CriarItemPrescricaoDTO,
    EmitirDocumentoClinicoCommand,
    VerificarLivenessCommand,
)
from src.modules.consultation.application.ports.atendimento_reader_port import (
    AtendimentoResumoDTO,
)
from src.modules.consultation.application.ports.liveness_verification_port import (
    LivenessVerificationPort,
)
from src.modules.consultation.application.services.documento_service import (
    DocumentoService,
)
from src.modules.consultation.domain.exceptions import (
    LivenessChallengeInvalidoError,
    ProvaDeVidaObrigatoriaError,
    SpoofingFacialDetectadoError,
)
from src.modules.consultation.domain.models import EvolucaoClinica
from src.modules.consultation.infrastructure.liveness_adapter import (
    MockLivenessAdapter,
    ValkeyLivenessAdapter,
)
from src.modules.consultation.infrastructure.memory_signed_cache import (
    MemorySignedCache,
)

from tests.doubles import (
    FakeAddedResult,
    FakeAsyncSession,
    FakeAtendimentoReader,
    FakeAuditTrail,
    FakeICPBrasilSigner,
    FakeMemoryStorage,
    FakePDFGenerator,
    FakeResult,
    FakeValkey,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


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
        ator_id=paciente_id,
        ator_papel=AtorPapel.PACIENTE.value,
        challenge_id=challenge.challenge_id,
        liveness_payload="SPOOF_STATIC_PHOTO_FRAME",
        latitude=-23.5505,
        longitude=-46.6333,
    )

    with pytest.raises(SpoofingFacialDetectadoError, match=r"score=0\.42"):
        await svc.verificar_liveness_prescricao(verify_cmd)

    assert session.commits == 1
    assert len(audit.get_events_by_type("SPOOFING_FACIAL_DETECTADO")) == 1
    assert await adapter.obter_hash_aprovado(atendimento_id) is None

    with pytest.raises(ProvaDeVidaObrigatoriaError):
        await svc.emitir_documento(_c1_command(atendimento_id, medico_id))


def _evolucao_verificada(atendimento_id: UUID, medico_id: UUID) -> EvolucaoClinica:
    return EvolucaoClinica(
        atendimento_id=atendimento_id,
        medico_id=medico_id,
        anamnese="Evaluacao clinica inicial",
        conduta="Prescricao controlada",
        identidade_verificada=True,
    )


@pytest.mark.asyncio
async def test_fluxo_completo_desafio_liveness_aprovado_permite_emissao_c1() -> None:
    """Approved facial liveness persists SHA-256 hash and unlocks Lista C1 emit."""
    atendimento_id = uuid7()
    medico_id = uuid7()
    paciente_id = uuid7()
    added: list[Any] = []
    session = FakeAsyncSession(
        [
            FakeResult(_evolucao_verificada(atendimento_id, medico_id)),
            FakeAddedResult(added),
        ],
        added,
    )
    adapter = MockLivenessAdapter(isolated=True)
    audit = FakeAuditTrail()
    svc = _make_service(session, liveness_verifier=adapter, audit_trail=audit)

    challenge = await svc.solicitar_desafio_liveness(atendimento_id)
    verification = await svc.verificar_liveness_prescricao(
        VerificarLivenessCommand(
            atendimento_id=atendimento_id,
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
    session = FakeAsyncSession(
        [
            FakeResult(_evolucao_verificada(atendimento_id, medico_id)),
            FakeAddedResult(added),
        ],
        added,
    )
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
    session = FakeAsyncSession(
        [
            FakeResult(_evolucao_verificada(atendimento_id, medico_id)),
            FakeAddedResult(added),
        ],
        added,
    )
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
async def test_verificar_liveness_rejeita_challenge_inexistente_ou_cruzado() -> None:
    """Forged, replayed, or cross-attendance challenge_id must be rejected."""
    atendimento_a = uuid7()
    atendimento_b = uuid7()
    paciente_id = uuid7()
    adapter = MockLivenessAdapter(isolated=True)
    session = FakeAsyncSession([])
    svc = _make_service(session, liveness_verifier=adapter)

    # 1. Non-existent challenge_id
    with pytest.raises(LivenessChallengeInvalidoError):
        await svc.verificar_liveness_prescricao(
            VerificarLivenessCommand(
                atendimento_id=atendimento_a,
                ator_id=paciente_id,
                ator_papel=AtorPapel.PACIENTE.value,
                challenge_id="ch_forged_unknown",
                liveness_payload="LIVE_FRAMES_OK",
            )
        )

    # 2. Challenge issued for atendimento_a used on atendimento_b
    ch_a = await svc.solicitar_desafio_liveness(atendimento_a)
    with pytest.raises(LivenessChallengeInvalidoError):
        await svc.verificar_liveness_prescricao(
            VerificarLivenessCommand(
                atendimento_id=atendimento_b,
                ator_id=paciente_id,
                ator_papel=AtorPapel.PACIENTE.value,
                challenge_id=ch_a.challenge_id,
                liveness_payload="LIVE_FRAMES_OK",
            )
        )


@pytest.mark.asyncio
async def test_emitir_documento_c1_rejeita_hash_forjado_no_atendimento() -> None:
    """Arbitrary sha256_ string not approved for the attendance must be rejected."""
    atendimento_id = uuid7()
    medico_id = uuid7()
    adapter = MockLivenessAdapter(isolated=True)
    session = FakeAsyncSession([])
    svc = _make_service(session, liveness_verifier=adapter)

    forged_hash = "sha256_" + "f" * 64
    with pytest.raises(ProvaDeVidaObrigatoriaError):
        await svc.emitir_documento(
            _c1_command(
                atendimento_id,
                medico_id,
                liveness_hash=forged_hash,
            )
        )


@pytest.mark.asyncio
async def test_valkey_liveness_adapter_compartilha_estado_entre_workers() -> None:
    """Challenge generated in worker A must verify in worker B using Valkey."""
    atendimento_id = uuid7()
    shared_valkey = FakeValkey()
    worker_a = ValkeyLivenessAdapter(valkey=cast("Any", shared_valkey))
    worker_b = ValkeyLivenessAdapter(valkey=cast("Any", shared_valkey))

    challenge = await worker_a.gerar_desafio(atendimento_id)
    result = await worker_b.verificar_prova_de_vida(
        atendimento_id=atendimento_id,
        challenge_id=challenge.challenge_id,
        liveness_payload="LIVE_FRAMES_WORKER_B_OK",
    )

    assert result.status == "APROVADO"
    assert await worker_a.obter_hash_aprovado(atendimento_id) == result.verificacao_hash

    replay = await worker_b.verificar_prova_de_vida(
        atendimento_id=atendimento_id,
        challenge_id=challenge.challenge_id,
        liveness_payload="LIVE_FRAMES_WORKER_B_OK",
    )
    assert replay.status == "DESAFIO_INVALIDO"


@pytest.mark.asyncio
async def test_challenge_ausente_nao_registra_spoofing_na_auditoria() -> None:
    """Missing/expired challenge must raise LivenessChallengeInvalidoError cleanly."""
    atendimento_id = uuid7()
    paciente_id = uuid7()
    adapter = ValkeyLivenessAdapter(valkey=cast("Any", FakeValkey()))
    audit = FakeAuditTrail()
    svc = _make_service(
        FakeAsyncSession([]), liveness_verifier=adapter, audit_trail=audit
    )

    with pytest.raises(LivenessChallengeInvalidoError):
        await svc.verificar_liveness_prescricao(
            VerificarLivenessCommand(
                atendimento_id=atendimento_id,
                ator_id=paciente_id,
                ator_papel=AtorPapel.PACIENTE.value,
                challenge_id="ch_inexistente",
                liveness_payload="LIVE_FRAMES_OK",
            )
        )

    assert len(audit.get_events_by_type("SPOOFING_FACIAL_DETECTADO")) == 0


@pytest.mark.asyncio
async def test_excecao_liveness_audita_justificativa_no_documento_emitido() -> None:
    """Clinical exception must audit excecao_liveness=True and justificativa."""
    atendimento_id = uuid7()
    medico_id = uuid7()
    added: list[Any] = []
    evolucao = EvolucaoClinica(
        atendimento_id=atendimento_id,
        medico_id=medico_id,
        anamnese="Paciente em atendimento domiciliar",
        conduta="Manter acompanhamento ambulatorial",
        identidade_verificada=True,
    )
    session = FakeAsyncSession([FakeResult(evolucao), FakeAddedResult(added)], added)
    audit = FakeAuditTrail()
    svc = _make_service(
        session,
        liveness_verifier=MockLivenessAdapter(isolated=True),
        audit_trail=audit,
    )
    justificativa = "Paciente tetraplegico em atendimento sem camera habilitada."

    await svc.emitir_documento(
        _c1_command(atendimento_id, medico_id, justificativa_excecao=justificativa)
    )

    events = audit.get_events_by_type("DOCUMENTO_CLINICO_EMITIDO")
    assert len(events) == 1
    assert events[0]["payload"]["excecao_liveness"] is True
    assert events[0]["payload"]["justificativa_excecao_liveness"] == justificativa


@pytest.mark.asyncio
async def test_lista_c5_exige_liveness_quando_politica_org_ativa() -> None:
    """Lista C5 substances trigger liveness gate unless org policy disables it."""
    atendimento_id = uuid7()
    medico_id = uuid7()
    cmd_c5 = EmitirDocumentoClinicoCommand(
        atendimento_id=atendimento_id,
        medico_id=medico_id,
        tipo_documento="RECEITA_SIMPLES",
        itens=[
            CriarItemPrescricaoDTO(
                medicamento="Oxandrolona 10mg",
                dosagem="1 cp",
                posologia="1 cp 12/12h",
                duracao="30 dias",
                controle_especial=False,
            )
        ],
    )

    resumo = AtendimentoResumoDTO(
        atendimento_id=atendimento_id,
        medico_id=medico_id,
        status="EM_ATENDIMENTO",
        tcle_hash="a" * 64,
        is_terminal=False,
    )
    svc_ativa = DocumentoService(
        session=cast("AsyncSession", FakeAsyncSession([])),
        pdf_generator=FakePDFGenerator(),
        signer=FakeICPBrasilSigner(),
        storage=FakeMemoryStorage(),
        cache=MemorySignedCache(),
        atendimento_reader=FakeAtendimentoReader(resumo=resumo),
        liveness_verifier=MockLivenessAdapter(isolated=True),
    )
    with pytest.raises(ProvaDeVidaObrigatoriaError):
        await svc_ativa.emitir_documento(cmd_c5)

    evolucao = EvolucaoClinica(
        atendimento_id=atendimento_id,
        medico_id=medico_id,
        anamnese="Reposicao controlada",
        conduta="Monitorizacao laboratorial periodica",
        identidade_verificada=True,
    )
    cmd_excecao = EmitirDocumentoClinicoCommand(
        atendimento_id=atendimento_id,
        medico_id=medico_id,
        tipo_documento="RECEITA_SIMPLES",
        itens=cmd_c5.itens,
        justificativa_excecao_liveness="Paciente sem câmera frontal em chamada de voz.",
    )
    svc_excecao = DocumentoService(
        session=cast(
            "AsyncSession",
            FakeAsyncSession([FakeResult(evolucao)]),
        ),
        pdf_generator=FakePDFGenerator(),
        signer=FakeICPBrasilSigner(),
        storage=FakeMemoryStorage(),
        cache=MemorySignedCache(),
        atendimento_reader=FakeAtendimentoReader(resumo=resumo),
        liveness_verifier=MockLivenessAdapter(isolated=True),
    )
    doc = await svc_excecao.emitir_documento(cmd_excecao)
    assert doc.liveness_verificacao_hash is None
    assert doc.justificativa_excecao_liveness is not None


@pytest.mark.asyncio
async def test_liveness_dependencies_separam_medico_challenge_de_paciente_verify() -> (
    None
):
    """Patient cannot trigger liveness challenge; physician cannot verify frames."""
    from fastapi.security import HTTPAuthorizationCredentials
    from src.modules.consultation.presentation.dependencies import (
        require_liveness_challenge_medico,
        require_liveness_verify_paciente,
    )

    from tests.helpers import auth_headers

    atendimento_id = uuid7()
    medico_id = uuid7()
    paciente_id = uuid7()
    reader = FakeAtendimentoReader(
        resumo=AtendimentoResumoDTO(
            atendimento_id=atendimento_id,
            medico_id=medico_id,
            paciente_id=paciente_id,
            status="EM_ATENDIMENTO",
            tcle_hash="a" * 64,
            is_terminal=False,
        )
    )
    pac_cred = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=auth_headers("PACIENTE", paciente_id)["Authorization"].removeprefix(
            "Bearer "
        ),
    )
    med_cred = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=auth_headers("MEDICO", medico_id)["Authorization"].removeprefix(
            "Bearer "
        ),
    )

    with pytest.raises(ForbiddenError):
        await require_liveness_challenge_medico(
            atendimento_id=atendimento_id,
            reader=reader,
            credentials=pac_cred,
        )

    with pytest.raises(ForbiddenError):
        await require_liveness_verify_paciente(
            atendimento_id=atendimento_id,
            reader=reader,
            credentials=med_cred,
        )

    actor_med = await require_liveness_challenge_medico(
        atendimento_id=atendimento_id,
        reader=reader,
        credentials=med_cred,
    )
    assert actor_med.actor_id == medico_id

    actor_pac = await require_liveness_verify_paciente(
        atendimento_id=atendimento_id,
        reader=reader,
        credentials=pac_cred,
    )
    assert actor_pac.actor_id == paciente_id
