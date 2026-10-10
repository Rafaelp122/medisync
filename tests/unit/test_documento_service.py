"""Unit tests for DocumentoService (canonical keys, SignedCachePort, no fallback)."""

from typing import TYPE_CHECKING, Any, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from src.core.uuid7 import uuid7
from src.modules.consultation.application.dtos import (
    CriarItemPrescricaoDTO,
    EmitirDocumentoClinicoCommand,
)
from src.modules.consultation.application.ports.document_directory_port import (
    DadosVerificacaoDirectory,
    DocumentDirectoryPort,
)
from src.modules.consultation.application.ports.icp_brasil_signer_port import (
    DoctorCertificateCredentials,
)
from src.modules.consultation.application.services.document_validation_service import (
    DocumentValidationService,
)
from src.modules.consultation.application.services.documento_service import (
    DocumentoService,
)
from src.modules.consultation.domain.exceptions import (
    PrescricaoFisicaObrigatoriaError,
)
from src.modules.consultation.domain.models import DocumentoClinico
from src.modules.consultation.domain.s3_keys import build_signed_document_key
from src.modules.consultation.infrastructure.memory_signed_cache import (
    MemorySignedCache,
)
from src.modules.consultation.infrastructure.s3_storage import FakeStorageAdapter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from tests.doubles import FakeAddedResult, FakeAsyncSession, FakeResult

_ORG_ID = 7
_SHA_FIXO = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def _emitir_command(
    atendimento_id: UUID, medico_id: UUID, chave_s3: str = ""
) -> EmitirDocumentoClinicoCommand:
    return EmitirDocumentoClinicoCommand(
        atendimento_id=atendimento_id,
        organizacao_id=_ORG_ID,
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
        organizacao_id=_ORG_ID,
        atendimento_id=atendimento_id,
        medico_id=medico_id,
        tipo_documento="RECEITA_SIMPLES",
        chave_s3=build_signed_document_key(_ORG_ID, atendimento_id, doc_id),
        sha256_hash=_SHA_FIXO,
        id=doc_id,
    )


def _service(
    session: FakeAsyncSession,
    storage: Any | None = None,
    cache: MemorySignedCache | None = None,
) -> DocumentoService:
    return DocumentoService(
        session=cast("AsyncSession", session),
        pdf_generator=cast("Any", MagicMock()),
        signer=cast("Any", AsyncMock()),
        storage=storage if storage is not None else cast("Any", AsyncMock()),
        cache=cache if cache is not None else MemorySignedCache(),
    )


@pytest.mark.asyncio
async def test_emitir_gera_chave_canonica_sem_legado() -> None:
    """Emitir without chave must generate orgs/{org}/consultations key, no s3://."""
    atend_id = uuid7()
    med_id = uuid7()
    added: list[Any] = []
    session = FakeAsyncSession([FakeResult(None), FakeAddedResult(added)], added)
    svc = _service(session)

    doc = await svc.emitir_documento(_emitir_command(atend_id, med_id))

    expected = build_signed_document_key(_ORG_ID, atend_id, doc.id)
    assert doc.chave_s3 == expected
    assert doc.chave_s3.startswith(f"orgs/{_ORG_ID}/consultations/{atend_id}/")
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
    session = FakeAsyncSession([FakeResult(None), FakeAddedResult(added)], added)
    svc = _service(session)
    explicita = f"orgs/{_ORG_ID}/consultations/{atend_id}/documents/custom.pdf"

    doc = await svc.emitir_documento(_emitir_command(atend_id, med_id, explicita))

    assert doc.chave_s3 == explicita


@pytest.mark.asyncio
async def test_emitir_tipo_proibido_portaria_344() -> None:
    """Yellow/blue pad types must fail before any persistence."""
    session = FakeAsyncSession([])
    svc = _service(session)
    cmd = EmitirDocumentoClinicoCommand(
        atendimento_id=uuid7(),
        organizacao_id=_ORG_ID,
        medico_id=uuid7(),
        tipo_documento="NOTIFICACAO_RECEITA_B",
        itens=[],
    )
    with pytest.raises(PrescricaoFisicaObrigatoriaError):
        await svc.emitir_documento(cmd)
    assert session.executes == 0
    assert session.commits == 0


@pytest.mark.asyncio
async def test_compilar_storage_hit_nao_recompila() -> None:
    """Storage hit must return bytes without touching pdf generator or SQL blocks."""
    atend_id = uuid7()
    med_id = uuid7()
    doc_id = uuid7()
    doc = _make_doc(atend_id, med_id, doc_id)
    storage = FakeStorageAdapter()
    await storage.salvar_documento(doc.chave_s3, b"%PDF-armazenado%")
    pdf_generator: Any = MagicMock()
    pdf_generator.gerar_pdf.side_effect = AssertionError("não deve recompilar")
    session = FakeAsyncSession([FakeResult(doc)])
    svc = DocumentoService(
        session=cast("AsyncSession", session),
        pdf_generator=pdf_generator,
        signer=cast("Any", AsyncMock()),
        storage=storage,
        cache=MemorySignedCache(),
    )

    assert await svc.compilar_pdf(doc_id) == b"%PDF-armazenado%"
    assert session.executes == 1


@pytest.mark.asyncio
async def test_compilar_storage_miss_compila_4_blocos() -> None:
    """Storage miss must compile via SQL blocks and pdf generator."""
    atend_id = uuid7()
    med_id = uuid7()
    doc_id = uuid7()
    doc = _make_doc(atend_id, med_id, doc_id)
    storage = FakeStorageAdapter()
    pdf_generator: Any = MagicMock()
    pdf_generator.gerar_pdf.return_value = b"%PDF-compilado%"
    # doc load + org + medico + paciente + cid10 (all empty -> defaults).
    session = FakeAsyncSession(
        [
            FakeResult(doc),
            FakeResult(None),
            FakeResult(None),
            FakeResult(None),
            FakeResult(None),
        ]
    )
    svc = DocumentoService(
        session=cast("AsyncSession", session),
        pdf_generator=pdf_generator,
        signer=cast("Any", AsyncMock()),
        storage=storage,
        cache=MemorySignedCache(),
    )

    assert await svc.compilar_pdf(doc_id) == b"%PDF-compilado%"
    pdf_generator.gerar_pdf.assert_called_once()


@pytest.mark.asyncio
async def test_assinar_persiste_chave_canonica_e_marca_cache() -> None:
    """Assinar must store canonical key, update hash and mark SignedCachePort."""
    atend_id = uuid7()
    med_id = uuid7()
    doc_id = uuid7()
    doc = _make_doc(atend_id, med_id, doc_id)
    original_hash = doc.sha256_hash
    storage = FakeStorageAdapter()
    await storage.salvar_documento(doc.chave_s3, b"%PDF-nao-assinado%")
    signer: Any = AsyncMock()
    signer.assinar_pdf.return_value = b"%PDF-signed-bytes%"
    cache = MemorySignedCache()
    # ownership load + compilar reload.
    session = FakeAsyncSession([FakeResult(doc), FakeResult(doc)])
    svc = DocumentoService(
        session=cast("AsyncSession", session),
        pdf_generator=cast("Any", MagicMock()),
        signer=signer,
        storage=storage,
        cache=cache,
    )
    creds = DoctorCertificateCredentials(token="tok", provider="fake")

    signed_doc, signed_bytes = await svc.assinar(doc_id, atend_id, creds)

    assert signed_bytes == b"%PDF-signed-bytes%"
    expected_key = build_signed_document_key(_ORG_ID, atend_id, doc_id)
    assert signed_doc.chave_s3 == expected_key
    assert await storage.obter_documento(expected_key) == b"%PDF-signed-bytes%"
    assert len(signed_doc.sha256_hash) == 64
    assert signed_doc.sha256_hash != original_hash
    assert await cache.is_assinado(doc_id) is True
    assert await svc.is_assinado(signed_doc) is True
    assert session.commits == 1


@pytest.mark.asyncio
async def test_is_assinado_chave_legada_sem_cache() -> None:
    """Legacy key without cache entry must report not signed (no dict fallback)."""
    atend_id = uuid7()
    med_id = uuid7()
    doc = DocumentoClinico(
        organizacao_id=_ORG_ID,
        atendimento_id=atend_id,
        medico_id=med_id,
        tipo_documento="RECEITA_SIMPLES",
        chave_s3="qualquer/chave/legada.pdf",
        sha256_hash=_SHA_FIXO,
        id=uuid7(),
    )
    svc = _service(FakeAsyncSession([]), cache=MemorySignedCache())
    assert await svc.is_assinado(doc) is False


class _StubDirectory(DocumentDirectoryPort):
    async def obter_dados_verificacao(
        self,
        organizacao_id: int,
        medico_id: UUID,
        atendimento_id: UUID,
    ) -> DadosVerificacaoDirectory:
        return DadosVerificacaoDirectory(
            organizacao_nome="MediSync Telemedicina",
            medico_nome="Dra. Validação",
            medico_crm="99999",
            medico_crm_uf="SP",
            paciente_nome="Paciente Teste",
            paciente_cpf="12345678900",
        )


@pytest.mark.asyncio
async def test_validacao_usa_cache_port_para_status_assinado() -> None:
    """Marked cache must flip validation status even with non-canonical key."""
    atend_id = uuid7()
    med_id = uuid7()
    doc = DocumentoClinico(
        organizacao_id=_ORG_ID,
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

    svc = DocumentValidationService(
        session=cast("AsyncSession", FakeAsyncSession([FakeResult(doc)])),
        directory=_StubDirectory(),
        storage=FakeStorageAdapter(),
        compilador_pdf=_compiler,
        cache=cache,
    )
    res_emitido = await svc.validar_documento(str(doc.id))
    assert res_emitido.status_documento == "EMITIDO"

    await cache.marcar_assinado(doc.id)
    svc2 = DocumentValidationService(
        session=cast("AsyncSession", FakeAsyncSession([FakeResult(doc)])),
        directory=_StubDirectory(),
        storage=FakeStorageAdapter(),
        compilador_pdf=_compiler,
        cache=cache,
    )
    res_assinado = await svc2.validar_documento(str(doc.id))
    assert res_assinado.status_documento == "ASSINADO"
    assert res_assinado.assinatura_digital_valida is True
