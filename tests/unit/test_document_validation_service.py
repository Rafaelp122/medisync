"""Unit tests for DocumentValidationService (TDD, fakes only, no DB)."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID, uuid4

import pytest
from src.core.errors import NotFoundError
from src.core.privacy import mascarar_cpf, mascarar_nome
from src.modules.consultation.application.ports.document_directory_port import (
    DadosVerificacaoDirectory,
    DocumentDirectoryPort,
)
from src.modules.consultation.application.ports.signed_cache_port import (
    SignedCachePort,
)
from src.modules.consultation.application.services.document_validation_service import (
    DocumentValidationService,
)
from src.modules.consultation.domain.exceptions import (
    DocumentoIntegridadeError,
    DocumentoNaoEncontradoNoStorageError,
)
from src.modules.consultation.infrastructure.document_directory_sql import (
    SqlDocumentDirectory,
)
from src.modules.consultation.infrastructure.memory_signed_cache import (
    MemorySignedCache,
)
from src.modules.consultation.infrastructure.s3_storage import FakeStorageAdapter

from tests.doubles import FakeAsyncSession, FakeResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


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
    cache: SignedCachePort | None = None,
) -> DocumentValidationService:
    async def _default_compiler(_doc_id: UUID) -> bytes:
        return b"%PDF-fake-bytes"

    return DocumentValidationService(
        session=cast("AsyncSession", FakeAsyncSession([FakeResult(doc)])),
        directory=FakeDirectory(dados or _dados_padrao(), exc),
        storage=storage or FakeStorageAdapter(),
        compilador_pdf=compiler or _default_compiler,
        cache=cache if cache is not None else MemorySignedCache(),
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
        atendimento_id=atend_id,
        medico_id=med_id,
        chave_s3=f"consultations/{atend_id}/documents/{doc_id}.pdf",
        assinado_em=datetime.now(UTC),
    )
    cache_assinado = MemorySignedCache()
    await cache_assinado.marcar_assinado(doc_id)
    svc = _service(doc_assinado, cache=cache_assinado)
    res = await svc.validar_documento(str(doc_id))
    assert res.status_documento == "ASSINADO"
    assert res.assinatura_digital_valida is True
    assert res.conformidade_icp_brasil is True
    assert res.assinado_em is not None
    assert res.paciente_cpf_mascarado == "123.***.***-00"
    assert res.paciente_nome_mascarado == "M**** J**** dos S*****"

    doc_emitido = FakeDoc(
        id=doc_id,
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
async def test_validar_chave_canonica_sem_cache_e_emitido() -> None:
    """Canonical key alone must not imply signed status (Task 8 regression)."""
    doc_id = uuid4()
    atend_id = uuid4()
    doc = FakeDoc(
        id=doc_id,
        atendimento_id=atend_id,
        medico_id=uuid4(),
        chave_s3=f"consultations/{atend_id}/documents/{doc_id}.pdf",
        assinado_em=datetime.now(UTC),
    )
    svc = _service(doc, cache=MemorySignedCache())
    res = await svc.validar_documento(str(doc_id))
    assert res.status_documento == "EMITIDO"
    assert res.assinatura_digital_valida is False
    assert res.assinado_em is None


@pytest.mark.asyncio
async def test_medico_ausente_erro_integridade() -> None:
    doc = FakeDoc(
        id=uuid4(),
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
    expected_key = f"consultations/{atend_id}/documents/{doc_id}.pdf"
    assert res.chave_s3 == expected_key


@pytest.mark.asyncio
async def test_download_storage_presente_nao_recompila() -> None:
    """Documentos legados (orgs/{id}/...) com chave_s3 continuam baixáveis."""
    doc_id = uuid4()
    atend_id = uuid4()
    key = f"orgs/9/consultations/{atend_id}/documents/{doc_id}.pdf"
    doc = FakeDoc(id=doc_id, atendimento_id=atend_id, medico_id=uuid4())
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


class _DirRowResult:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    def mappings(self) -> "_DirRowResult":
        return self

    def first(self) -> dict[str, Any] | None:
        return self._row


class _DirFakeSession:
    def __init__(self, rows: list[dict[str, Any] | None]) -> None:
        self._rows = list(rows)
        self.statements: list[str] = []
        self.params: list[Any] = []

    async def execute(self, stmt: Any, params: Any = None) -> _DirRowResult:
        self.statements.append(str(stmt))
        self.params.append(params)
        return _DirRowResult(self._rows.pop(0))


@pytest.mark.asyncio
async def test_sql_document_directory_consulta_configuracoes_unidade_cnpj_cnes() -> (
    None
):
    """Q4 Fix #1: SqlDocumentDirectory lê cnpj e cnes de configuracoes_unidade."""
    session = _DirFakeSession(
        [
            {
                "cnpj": "12.345.678/0001-99",
                "razao_social": "Consórcio Regional",
                "nome_fantasia": "UPA Virtual Central",
                "cnes": "2077558",
            },
            {"nome_completo": "Dra. Ana", "crm": "12345", "crm_uf": "SP"},
            {
                "nome_completo": "João Pedro",
                "cpf": "12345678900",
                "data_nascimento": None,
                "logradouro": None,
                "numero": None,
                "bairro": None,
                "cidade": None,
                "estado": None,
            },
        ]
    )
    directory = SqlDocumentDirectory(cast("AsyncSession", session))

    dto = await directory.obter_dados_verificacao(
        medico_id=uuid4(),
        atendimento_id=uuid4(),
    )

    assert "SELECT cnpj, razao_social, nome_fantasia, cnes" in session.statements[0]
    assert "FROM configuracoes_unidade LIMIT 1" in session.statements[0]
    assert "organizacoes" not in session.statements[0]
    assert session.params[0] is None
    assert dto.organizacao_nome == "UPA Virtual Central"
    assert dto.organizacao_cnpj == "12.345.678/0001-99"
    assert dto.cnes == "2077558"


@pytest.mark.asyncio
async def test_sql_document_directory_medico_ausente_raises_with_offending_id() -> None:
    """DocumentoIntegridadeError interpola medico_id quando profissional ausente."""
    med_id = uuid4()
    atend_id = uuid4()
    session = _DirFakeSession(
        [
            {
                "cnpj": "12345678000199",
                "razao_social": "UPA",
                "nome_fantasia": "UPA",
                "cnes": "2077558",
            },
            None,
        ]
    )
    directory = SqlDocumentDirectory(cast("AsyncSession", session))

    with pytest.raises(DocumentoIntegridadeError, match=str(med_id)):
        await directory.obter_dados_verificacao(
            medico_id=med_id,
            atendimento_id=atend_id,
        )


@pytest.mark.asyncio
async def test_sql_document_directory_medico_sem_crm_raises_with_offending_id() -> None:
    """DocumentoIntegridadeError interpola medico_id quando CRM/UF ausentes."""
    med_id = uuid4()
    atend_id = uuid4()
    session = _DirFakeSession(
        [
            {
                "cnpj": "12345678000199",
                "razao_social": "UPA",
                "nome_fantasia": "UPA",
                "cnes": "2077558",
            },
            {"nome_completo": "Dra. Ana", "crm": "", "crm_uf": ""},
        ]
    )
    directory = SqlDocumentDirectory(cast("AsyncSession", session))

    with pytest.raises(DocumentoIntegridadeError, match=str(med_id)):
        await directory.obter_dados_verificacao(
            medico_id=med_id,
            atendimento_id=atend_id,
        )


@pytest.mark.asyncio
async def test_sql_document_directory_paciente_ausente_raises_with_offending_id() -> (
    None
):
    """DocumentoIntegridadeError interpola atendimento_id quando paciente ausente."""
    med_id = uuid4()
    atend_id = uuid4()
    session = _DirFakeSession(
        [
            {
                "cnpj": "12345678000199",
                "razao_social": "UPA",
                "nome_fantasia": "UPA",
                "cnes": "2077558",
            },
            {"nome_completo": "Dra. Ana", "crm": "12345", "crm_uf": "SP"},
            None,
        ]
    )
    directory = SqlDocumentDirectory(cast("AsyncSession", session))

    with pytest.raises(DocumentoIntegridadeError, match=str(atend_id)):
        await directory.obter_dados_verificacao(
            medico_id=med_id,
            atendimento_id=atend_id,
        )
