"""Unit tests for DocumentoService (canonical keys, SignedCachePort, no fallback)."""

from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import pytest
from src.core.uuid7 import uuid7
from src.modules.consultation.application.dtos import (
    CriarItemPrescricaoDTO,
    EmitirDocumentoClinicoCommand,
)
from src.modules.consultation.application.ports.document_directory_port import (
    DadosVerificacaoDirectory,
)
from src.modules.consultation.application.ports.icp_brasil_signer_port import (
    DoctorCertificateCredentials,
)
from src.modules.consultation.application.ports.storage_port import StoragePort
from src.modules.consultation.application.services.document_validation_service import (
    DocumentValidationService,
)
from src.modules.consultation.application.services.documento_service import (
    DocumentoService,
)
from src.modules.consultation.domain.exceptions import (
    ConsultaInvalidaError,
    PrescricaoFisicaObrigatoriaError,
)
from src.modules.consultation.domain.models import (
    DocumentoClinico,
    EvolucaoClinica,
)
from src.modules.consultation.domain.s3_keys import build_signed_document_key
from src.modules.consultation.infrastructure.memory_signed_cache import (
    MemorySignedCache,
)

from tests.doubles import (
    FakeAddedResult,
    FakeAsyncSession,
    FakeDocumentDirectory,
    FakeFilaService,
    FakeICPBrasilSigner,
    FakeMemoryStorage,
    FakePDFGenerator,
    FakeResult,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_SHA_FIXO = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def _emitir_command(
    atendimento_id: UUID, medico_id: UUID, chave_s3: str = ""
) -> EmitirDocumentoClinicoCommand:
    return EmitirDocumentoClinicoCommand(
        atendimento_id=atendimento_id,
        medico_id=medico_id,
        tipo_documento="RECEITA_SIMPLES",
        itens=[
            CriarItemPrescricaoDTO(
                medicamento="Dipirona 500mg",
                dosagem="1 cp",
                posologia="1 cp se dor",
                duracao="3 dias",
            )
        ],
        chave_s3=chave_s3,
    )


def _make_doc(atendimento_id: UUID, medico_id: UUID, doc_id: UUID) -> DocumentoClinico:
    return DocumentoClinico(
        atendimento_id=atendimento_id,
        medico_id=medico_id,
        tipo_documento="RECEITA_SIMPLES",
        chave_s3=build_signed_document_key(atendimento_id, doc_id),
        sha256_hash=_SHA_FIXO,
        id=doc_id,
    )


def _service(
    session: FakeAsyncSession,
    storage: StoragePort | None = None,
    cache: MemorySignedCache | None = None,
) -> DocumentoService:
    return DocumentoService(
        session=cast("AsyncSession", session),
        pdf_generator=FakePDFGenerator(),
        signer=FakeICPBrasilSigner(),
        storage=storage if storage is not None else FakeMemoryStorage(),
        cache=cache if cache is not None else MemorySignedCache(),
    )


def _make_evolucao_verificada(atendimento_id: UUID, medico_id: UUID) -> EvolucaoClinica:
    return EvolucaoClinica(
        atendimento_id=atendimento_id,
        medico_id=medico_id,
        anamnese="Anamnese registrada.",
        conduta="Conduta clinica definida.",
        identidade_verificada=True,
    )


@pytest.mark.asyncio
async def test_emitir_gera_chave_canonica_sem_legado() -> None:
    """Emitir without chave must generate consultations key, no s3://."""
    atend_id = uuid7()
    med_id = uuid7()
    added: list[Any] = []
    session = FakeAsyncSession(
        [
            FakeResult(_make_evolucao_verificada(atend_id, med_id)),
            FakeAddedResult(added),
        ],
        added,
    )
    svc = _service(session)

    doc = await svc.emitir_documento(_emitir_command(atend_id, med_id))

    expected = build_signed_document_key(atend_id, doc.id)
    assert doc.chave_s3 == expected
    assert doc.chave_s3.startswith(f"consultations/{atend_id}/")
    assert "s3://" not in doc.chave_s3
    assert len(doc.itens) == 1
    assert doc.itens[0].medicamento == "Dipirona 500mg"
    assert session.commits == 1


@pytest.mark.asyncio
async def test_emitir_preserva_chave_explicita() -> None:
    """Explicit chave_s3 in command must be preserved verbatim."""
    atend_id = uuid7()
    med_id = uuid7()
    added: list[Any] = []
    session = FakeAsyncSession(
        [
            FakeResult(_make_evolucao_verificada(atend_id, med_id)),
            FakeAddedResult(added),
        ],
        added,
    )
    svc = _service(session)
    explicita = f"consultations/{atend_id}/documents/custom.pdf"

    doc = await svc.emitir_documento(_emitir_command(atend_id, med_id, explicita))

    assert doc.chave_s3 == explicita


@pytest.mark.asyncio
async def test_emitir_tipo_proibido_portaria_344() -> None:
    """Yellow/blue pad types must fail before any persistence."""
    session = FakeAsyncSession([])
    svc = _service(session)
    cmd = EmitirDocumentoClinicoCommand(
        atendimento_id=uuid7(),
        medico_id=uuid7(),
        tipo_documento="NOTIFICACAO_RECEITA_B",
        itens=[],
    )
    with pytest.raises(PrescricaoFisicaObrigatoriaError):
        await svc.emitir_documento(cmd)
    assert session.executes == 0
    assert session.commits == 0


class _StaticSigner(FakeICPBrasilSigner):
    async def assinar_pdf(
        self,
        pdf_bytes: bytes,
        credenciais: Any,
        metadata: Any = None,
    ) -> bytes:
        return b"%PDF-signed-bytes%"


@pytest.mark.asyncio
async def test_compilar_storage_hit_nao_recompila() -> None:
    """Storage hit must return bytes without touching pdf generator or SQL blocks."""
    atend_id = uuid7()
    med_id = uuid7()
    doc_id = uuid7()
    doc = _make_doc(atend_id, med_id, doc_id)
    storage = FakeMemoryStorage()
    await storage.salvar_documento(doc.chave_s3, b"%PDF-armazenado%")
    pdf_generator = FakePDFGenerator()
    session = FakeAsyncSession([FakeResult(doc)])
    svc = DocumentoService(
        session=cast("AsyncSession", session),
        pdf_generator=pdf_generator,
        signer=FakeICPBrasilSigner(),
        storage=storage,
        cache=MemorySignedCache(),
    )

    assert await svc.compilar_pdf(doc_id) == b"%PDF-armazenado%"
    assert session.executes == 1
    assert pdf_generator.calls == 0


@pytest.mark.asyncio
async def test_compilar_storage_miss_compila_com_diretorio_sem_placeholders() -> None:
    """Storage miss compiles via DocumentDirectoryPort without placeholders."""
    atend_id = uuid7()
    med_id = uuid7()
    doc_id = uuid7()
    doc = _make_doc(atend_id, med_id, doc_id)
    storage = FakeMemoryStorage()
    pdf_generator = FakePDFGenerator(content=b"%PDF-compilado%")
    session = FakeAsyncSession([FakeResult(doc), FakeResult(None)])
    svc = DocumentoService(
        session=cast("AsyncSession", session),
        pdf_generator=pdf_generator,
        signer=FakeICPBrasilSigner(),
        storage=storage,
        cache=MemorySignedCache(),
        directory=FakeDocumentDirectory(),
    )

    assert await svc.compilar_pdf(doc_id, atendimento_id=atend_id) == b"%PDF-compilado%"
    assert pdf_generator.calls == 1


@pytest.mark.asyncio
async def test_compilar_falha_quando_diretorio_ausente_ou_idor() -> None:
    """Missing directory raises DocumentoIntegridadeError; mismatch raises 404."""
    from src.modules.consultation.domain.exceptions import (
        DocumentoClinicoNaoEncontradoError,
        DocumentoIntegridadeError,
    )

    atend_id = uuid7()
    med_id = uuid7()
    doc_id = uuid7()
    doc = _make_doc(atend_id, med_id, doc_id)
    session = FakeAsyncSession([FakeResult(doc)])
    svc = DocumentoService(
        session=cast("AsyncSession", session),
        pdf_generator=FakePDFGenerator(),
        signer=FakeICPBrasilSigner(),
        storage=FakeMemoryStorage(),
        cache=MemorySignedCache(),
        directory=None,
    )
    with pytest.raises(DocumentoIntegridadeError):
        await svc.compilar_pdf(doc_id, atendimento_id=atend_id)

    session_idor = FakeAsyncSession([FakeResult(doc)])
    svc_idor = DocumentoService(
        session=cast("AsyncSession", session_idor),
        pdf_generator=FakePDFGenerator(),
        signer=FakeICPBrasilSigner(),
        storage=FakeMemoryStorage(),
        cache=MemorySignedCache(),
        directory=FakeDocumentDirectory(),
    )
    with pytest.raises(DocumentoClinicoNaoEncontradoError):
        await svc_idor.compilar_pdf(doc_id, atendimento_id=uuid7())


@pytest.mark.asyncio
async def test_assinar_persiste_chave_canonica_e_marca_cache() -> None:
    """Assinar must store canonical key, update hash and mark SignedCachePort."""
    atend_id = uuid7()
    med_id = uuid7()
    doc_id = uuid7()
    doc = _make_doc(atend_id, med_id, doc_id)
    original_hash = doc.sha256_hash
    storage = FakeMemoryStorage()
    await storage.salvar_documento(doc.chave_s3, b"%PDF-nao-assinado%")
    signer = _StaticSigner()
    cache = MemorySignedCache()
    # ownership load + compilar reload.
    session = FakeAsyncSession([FakeResult(doc), FakeResult(doc)])
    svc = DocumentoService(
        session=cast("AsyncSession", session),
        pdf_generator=FakePDFGenerator(),
        signer=signer,
        storage=storage,
        cache=cache,
    )
    creds = DoctorCertificateCredentials(token="tok", provider="fake")

    result = await svc.assinar(doc_id, atend_id, creds)

    assert result.tamanho_bytes == len(b"%PDF-signed-bytes%")
    expected_key = build_signed_document_key(atend_id, doc_id)
    assert doc.chave_s3 == expected_key
    assert await storage.obter_documento(expected_key) == b"%PDF-signed-bytes%"
    assert len(result.sha256_hash) == 64
    assert result.sha256_hash != original_hash
    assert result.documento_id == doc_id
    assert result.status == "ASSINADO"
    assert await cache.is_assinado(doc_id) is True
    assert await svc.is_assinado(doc) is True
    assert session.commits == 1


@pytest.mark.asyncio
async def test_is_assinado_chave_legada_sem_cache() -> None:
    """Legacy key without cache entry must report not signed (no dict fallback)."""
    atend_id = uuid7()
    med_id = uuid7()
    doc = DocumentoClinico(
        atendimento_id=atend_id,
        medico_id=med_id,
        tipo_documento="RECEITA_SIMPLES",
        chave_s3="qualquer/chave/legada.pdf",
        sha256_hash=_SHA_FIXO,
        id=uuid7(),
    )
    svc = _service(FakeAsyncSession([]), cache=MemorySignedCache())
    assert await svc.is_assinado(doc) is False


@pytest.mark.asyncio
async def test_validacao_usa_cache_port_para_status_assinado() -> None:
    """Marked cache must flip validation status even with non-canonical key."""
    atend_id = uuid7()
    med_id = uuid7()
    doc = DocumentoClinico(
        atendimento_id=atend_id,
        medico_id=med_id,
        tipo_documento="RECEITA_SIMPLES",
        chave_s3="qualquer/chave/legada.pdf",
        sha256_hash=_SHA_FIXO,
        id=uuid7(),
    )
    cache = MemorySignedCache()

    async def _compiler(_doc_id: UUID) -> bytes:
        return b"%PDF-fake%"

    directory = FakeDocumentDirectory(
        dados=DadosVerificacaoDirectory(
            organizacao_nome="MediSync Telemedicina",
            medico_nome="Dra. Validação",
            medico_crm="99999",
            medico_crm_uf="SP",
            paciente_nome="Paciente Teste",
            paciente_cpf="12345678900",
        )
    )
    svc = DocumentValidationService(
        session=cast("AsyncSession", FakeAsyncSession([FakeResult(doc)])),
        directory=directory,
        storage=FakeMemoryStorage(),
        compilador_pdf=_compiler,
        cache=cache,
    )
    res_emitido = await svc.validar_documento(str(doc.id))
    assert res_emitido.status_documento == "EMITIDO"

    await cache.marcar_assinado(doc.id)
    svc2 = DocumentValidationService(
        session=cast("AsyncSession", FakeAsyncSession([FakeResult(doc)])),
        directory=directory,
        storage=FakeMemoryStorage(),
        compilador_pdf=_compiler,
        cache=cache,
    )
    res_assinado = await svc2.validar_documento(str(doc.id))
    assert res_assinado.status_documento == "ASSINADO"
    assert res_assinado.assinatura_digital_valida is True


@pytest.mark.asyncio
async def test_emitir_documento_bloqueia_sem_identidade_verificada_cfm() -> None:
    """CFM 2.314/2022 blocks document emission without verified patient identity."""
    atend_id = uuid7()
    med_id = uuid7()
    svc_sem_soap = _service(FakeAsyncSession([FakeResult(None)]))
    with pytest.raises(ConsultaInvalidaError, match="identidade_verificada"):
        await svc_sem_soap.emitir_documento(_emitir_command(atend_id, med_id))

    evolucao_nao_verificada = EvolucaoClinica(
        atendimento_id=atend_id,
        medico_id=med_id,
        anamnese="Queixa clinica",
        conduta="Observacao",
        identidade_verificada=False,
    )
    svc_nao_verificada = _service(
        FakeAsyncSession([FakeResult(evolucao_nao_verificada)])
    )
    with pytest.raises(ConsultaInvalidaError, match="identidade_verificada=False"):
        await svc_nao_verificada.emitir_documento(_emitir_command(atend_id, med_id))


@pytest.mark.asyncio
async def test_compilar_pdf_propaga_cnpj_e_cnes_do_diretorio() -> None:
    """Q4 Fix #2: compilar_pdf deve copiar organizacao_cnpj e cnes para o PDF."""
    atend_id = uuid7()
    med_id = uuid7()
    doc_id = uuid7()
    doc = _make_doc(atend_id, med_id, doc_id)
    spy_pdf = FakePDFGenerator(content=b"%PDF-q4-metadata")
    metadata_dir = FakeDocumentDirectory(
        dados=DadosVerificacaoDirectory(
            organizacao_nome="UPA Virtual Central",
            organizacao_cnpj="12.345.678/0001-99",
            cnes="2077558",
            medico_nome="Dra. Validação",
            medico_crm="99999",
            medico_crm_uf="SP",
            paciente_nome="Paciente Teste",
            paciente_cpf="12345678900",
        )
    )
    session = FakeAsyncSession([FakeResult(doc), FakeResult(None)])
    svc = DocumentoService(
        session=cast("AsyncSession", session),
        pdf_generator=spy_pdf,
        signer=FakeICPBrasilSigner(),
        storage=FakeMemoryStorage(),
        cache=MemorySignedCache(),
        directory=metadata_dir,
    )

    pdf_bytes = await svc.compilar_pdf(doc_id)

    assert pdf_bytes == b"%PDF-q4-metadata"
    assert len(spy_pdf.payloads) == 1
    assert spy_pdf.payloads[-1].organizacao_nome == "UPA Virtual Central"
    assert spy_pdf.payloads[-1].organizacao_cnpj == "12.345.678/0001-99"
    assert spy_pdf.payloads[-1].organizacao_cnes == "2077558"


@pytest.mark.asyncio
async def test_identity_directory_adapter_rejeita_campos_ausentes() -> None:
    """IdentityDocumentDirectoryAdapter raises DocumentoIntegridadeError when empty."""
    from datetime import UTC, datetime

    from src.modules.consultation.composition import IdentityDocumentDirectoryAdapter
    from src.modules.consultation.domain.exceptions import DocumentoIntegridadeError
    from src.modules.identity.application.ports.identity_reader_port import (
        IdentityDirectoryDTO,
    )
    from src.modules.queue.application.ports.queue_store_port import (
        AtendimentoSnapshotDTO,
        QueueStorePort,
    )

    from tests.doubles import FakeIdentityReader

    atend_id = uuid7()
    med_id = uuid7()
    pac_id = uuid7()

    snap_store = FakeFilaService(
        snapshots={
            atend_id: AtendimentoSnapshotDTO(
                id=atend_id,
                paciente_id=pac_id,
                medico_id=med_id,
                status="EM_ATENDIMENTO",
                prioridade_clinica=3,
                tcle_hash="a" * 64,
                data_entrada_fila=datetime.now(UTC),
                criado_em=datetime.now(UTC),
                is_terminal=False,
            )
        }
    )

    incompleto = IdentityDirectoryDTO(
        organizacao_nome="Unidade SUS",
        organizacao_cnpj=None,
        medico_id=med_id,
        medico_nome="Dr. Sem CRM",
        medico_crm=None,
        medico_crm_uf="SP",
        paciente_id=pac_id,
        paciente_nome="Paciente Sem CPF",
        paciente_cpf=None,
        paciente_data_nascimento=None,
        paciente_endereco=None,
    )
    adapter = IdentityDocumentDirectoryAdapter(
        identity_reader=FakeIdentityReader(diretorio=incompleto),
        queue_store=cast("QueueStorePort", snap_store),
    )
    with pytest.raises(DocumentoIntegridadeError, match="medico_crm"):
        await adapter.obter_dados_verificacao(medico_id=med_id, atendimento_id=atend_id)


@pytest.mark.asyncio
async def test_assinar_documento_inexistente_levanta_documento_nao_encontrado() -> None:
    """DocumentoService.assinar raises specific DocumentoClinicoNaoEncontradoError."""
    from src.modules.consultation.domain.exceptions import (
        DocumentoClinicoNaoEncontradoError,
    )

    svc = _service(FakeAsyncSession([FakeResult(None)]))
    with pytest.raises(DocumentoClinicoNaoEncontradoError):
        await svc.assinar(
            uuid7(),
            uuid7(),
            DoctorCertificateCredentials(token="tok", provider="fake"),
        )
