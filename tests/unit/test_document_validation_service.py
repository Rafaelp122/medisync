"""Unit tests for DocumentValidationService (TDD, fakes only, no DB)."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from src.core.errors import NotFoundError
from src.core.privacy import mascarar_cpf, mascarar_nome
from src.modules.consultation.application.ports.document_directory_port import (
    DadosVerificacaoDirectory,
    DocumentDirectoryPort,
)
from src.modules.consultation.application.services.document_validation_service import (
    DocumentValidationService,
)
from src.modules.consultation.domain.exceptions import (
    DocumentoIntegridadeError,
    DocumentoNaoEncontradoNoStorageError,
)
from src.modules.consultation.infrastructure.s3_storage import FakeStorageAdapter


@dataclass
class FakeDocItem:
    medicamento: str = "Paracetamol 750mg"
    dosagem: str = "750mg"
    posologia: str = "1cp 6/6h"
    duracao: str | None = "3 dias"
    controle_especial: bool = False


@dataclass
class FakeDoc:
    id: UUID
    organizacao_id: int
    atendimento_id: UUID
    medico_id: UUID
    tipo_documento: str = "RECEITA_SIMPLES"
    chave_s3: str = ""
    sha256_hash: str = (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
    assinado_em: datetime | None = None
    itens: Any = None

    def __post_init__(self) -> None:
        if self.itens is None:
            self.itens = [FakeDocItem()]


class FakeResult:
    def __init__(self, doc: FakeDoc | None) -> None:
        self._doc = doc

    def scalar_one_or_none(self) -> FakeDoc | None:
        return self._doc


class FakeSession:
    def __init__(self, doc: FakeDoc | None) -> None:
        self._doc = doc

    async def execute(self, *args: Any, **kwargs: Any) -> FakeResult:
        return FakeResult(self._doc)


class FakeDirectory(DocumentDirectoryPort):
    def __init__(
        self,
        dados: DadosVerificacaoDirectory | None = None,
        exc: Exception | None = None,
    ) -> None:
        self._dados = dados
        self._exc = exc

    async def obter_dados_verificacao(
        self,
        organizacao_id: int,
        medico_id: UUID,
        atendimento_id: UUID,
    ) -> DadosVerificacaoDirectory:
        if self._exc is not None:
            raise self._exc
        assert self._dados is not None
        return self._dados


def _dados_padrao() -> DadosVerificacaoDirectory:
    return DadosVerificacaoDirectory(
        organizacao_nome="MediSync Telemedicina",
        medico_nome="Dr. Roberto Carlos de Souza",
        medico_crm="12345",
        medico_crm_uf="SP",
        paciente_nome="Maria Joana dos Santos",
        paciente_cpf="12345678900",
    )


def _service(
    doc: FakeDoc | None,
    dados: DadosVerificacaoDirectory | None = None,
    exc: Exception | None = None,
    storage: FakeStorageAdapter | None = None,
    compiler: Callable[[UUID], Awaitable[bytes]] | None = None,
) -> DocumentValidationService:
    async def _default_compiler(_doc_id: UUID) -> bytes:
        return b"%PDF-fake-bytes"

    return DocumentValidationService(
        session=FakeSession(doc),  # type: ignore[arg-type]
        directory=FakeDirectory(dados or _dados_padrao(), exc),
        storage=storage or FakeStorageAdapter(),
        compilador_pdf=compiler or _default_compiler,
    )


def test_mascarar_cpf_valido_e_invalido() -> None:
    assert mascarar_cpf("111.222.333-44") == "111.***.***-44"
    assert mascarar_cpf("12345678901") == "123.***.***-01"
    assert mascarar_cpf("invalido") == "***.***.***-**"
    assert mascarar_cpf("") == "***.***.***-**"


def test_mascarar_nome_preposicoes_uma_letra_vazio() -> None:
    assert mascarar_nome("Maria Joana dos Santos") == "M**** J**** dos S*****"
    assert mascarar_nome("Ana de Souza") == "A** de S****"
    assert mascarar_nome("A") == "A"
    assert mascarar_nome("") == "***"
    assert mascarar_nome("   ") == "***"


@pytest.mark.asyncio
async def test_validar_assinado_vs_emitido() -> None:
    doc_id = uuid4()
    atend_id = uuid4()
    med_id = uuid4()
    doc_assinado = FakeDoc(
        id=doc_id,
        organizacao_id=7,
        atendimento_id=atend_id,
        medico_id=med_id,
        chave_s3=f"orgs/7/consultations/{atend_id}/documents/{doc_id}.pdf",
        assinado_em=datetime.now(UTC),
    )
    svc = _service(doc_assinado)
    res = await svc.validar_documento(str(doc_id))
    assert res.status_documento == "ASSINADO"
    assert res.assinatura_digital_valida is True
    assert res.conformidade_icp_brasil is True
    assert res.assinado_em is not None
    assert res.paciente_cpf_mascarado == "123.***.***-00"
    assert res.paciente_nome_mascarado == "M**** J**** dos S*****"

    doc_emitido = FakeDoc(
        id=doc_id,
        organizacao_id=7,
        atendimento_id=atend_id,
        medico_id=med_id,
        chave_s3="s3://medisync-docs/7/atendimentos/x/receita.pdf",
        assinado_em=datetime.now(UTC),
    )
    svc2 = _service(doc_emitido)
    res2 = await svc2.validar_documento(str(doc_id))
    assert res2.status_documento == "EMITIDO"
    assert res2.assinatura_digital_valida is False
    assert res2.assinado_em is None


@pytest.mark.asyncio
async def test_medico_ausente_erro_integridade() -> None:
    doc = FakeDoc(
        id=uuid4(),
        organizacao_id=1,
        atendimento_id=uuid4(),
        medico_id=uuid4(),
    )
    svc = _service(doc, exc=DocumentoIntegridadeError("médico ausente para documento"))
    with pytest.raises(DocumentoIntegridadeError):
        await svc.validar_documento(str(doc.id))


@pytest.mark.asyncio
async def test_paciente_ausente_erro_integridade() -> None:
    doc = FakeDoc(
        id=uuid4(),
        organizacao_id=1,
        atendimento_id=uuid4(),
        medico_id=uuid4(),
    )
    svc = _service(
        doc, exc=DocumentoIntegridadeError("paciente ausente para documento")
    )
    with pytest.raises(DocumentoIntegridadeError):
        await svc.validar_documento(str(doc.id))


@pytest.mark.asyncio
async def test_validar_token_invalido_404() -> None:
    svc = _service(None)
    with pytest.raises(NotFoundError):
        await svc.validar_documento("not-a-uuid")


@pytest.mark.asyncio
async def test_validar_doc_ausente_404() -> None:
    svc = _service(None)
    with pytest.raises(NotFoundError):
        await svc.validar_documento(str(uuid4()))


@pytest.mark.asyncio
async def test_download_doc_ausente_404() -> None:
    svc = _service(None)
    with pytest.raises(NotFoundError):
        await svc.gerar_url_download(str(uuid4()))


@pytest.mark.asyncio
async def test_download_storage_ausente_gera_sob_demanda() -> None:
    doc_id = uuid4()
    atend_id = uuid4()
    doc = FakeDoc(
        id=doc_id,
        organizacao_id=9,
        atendimento_id=atend_id,
        medico_id=uuid4(),
        chave_s3="",
    )
    storage = FakeStorageAdapter()
    compiled = {"called": False}

    async def _compiler(_did: UUID) -> bytes:
        compiled["called"] = True
        return b"%PDF-regenerado"

    svc = _service(doc, storage=storage, compiler=_compiler)
    res = await svc.gerar_url_download(str(doc_id), expiracao_segundos=300)
    assert compiled["called"] is True
    assert res.documento_id == doc_id
    assert str(doc_id) in res.download_url
    assert res.expires_in_seconds == 300
    expected_key = f"orgs/9/consultations/{atend_id}/documents/{doc_id}.pdf"
    assert res.chave_s3 == expected_key


@pytest.mark.asyncio
async def test_download_storage_presente_nao_recompila() -> None:
    doc_id = uuid4()
    atend_id = uuid4()
    key = f"orgs/9/consultations/{atend_id}/documents/{doc_id}.pdf"
    doc = FakeDoc(
        id=doc_id, organizacao_id=9, atendimento_id=atend_id, medico_id=uuid4()
    )
    doc.chave_s3 = key
    storage = FakeStorageAdapter()
    await storage.salvar_documento(key, b"%PDF-existente")

    async def _fail_compiler(_did: UUID) -> bytes:
        raise AssertionError("compilador não deveria ser chamado")

    svc = _service(doc, storage=storage, compiler=_fail_compiler)
    res = await svc.gerar_url_download(str(doc_id))
    assert res.chave_s3 == key
    assert str(doc_id) in res.download_url


@pytest.mark.asyncio
async def test_download_storage_falha_tipada_nao_suprime_generico() -> None:
    doc_id = uuid4()
    doc = FakeDoc(
        id=doc_id,
        organizacao_id=9,
        atendimento_id=uuid4(),
        medico_id=uuid4(),
        chave_s3="",
    )

    class ExplodingStorage(FakeStorageAdapter):
        async def obter_documento(self, chave: str) -> bytes:
            raise RuntimeError("boom inesperado")

        async def salvar_documento(
            self, chave: str, conteudo: bytes, content_type: str = "application/pdf"
        ) -> str:
            raise RuntimeError("boom salvar")

    async def _compiler(_did: UUID) -> bytes:
        return b"%PDF-x"

    svc = _service(doc, storage=ExplodingStorage(), compiler=_compiler)  # type: ignore[arg-type]
    with pytest.raises(DocumentoNaoEncontradoNoStorageError):
        await svc.gerar_url_download(str(doc_id))
