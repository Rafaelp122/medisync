"""Unit tests for Patient Portal consultation history and documents endpoints."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from src.core.authz.roles import Role
from src.core.authz.token import create_access_token
from src.core.errors import ForbiddenError, NotFoundError
from src.core.uuid7 import uuid7
from src.main import create_app
from src.modules.consultation.application.ports.atendimento_reader_port import (
    AtendimentoHistoricoDTO,
    AtendimentoReaderPort,
    AtendimentoResumoDTO,
    HistoricoAtendimentoReaderPort,
)
from src.modules.consultation.application.services.documento_service import (
    DocumentoService,
)
from src.modules.consultation.application.services.pep_service import PEPService
from src.modules.consultation.composition import (
    QueueStoreAtendimentoReaderAdapter,
    get_pep_service,
)
from src.modules.consultation.domain.exceptions import (
    DocumentoClinicoNaoEncontradoError,
)
from src.modules.consultation.domain.models import (
    DocumentoClinico,
    EvolucaoClinica,
    TipoDocumentoClinico,
)
from src.modules.consultation.infrastructure.atendimento_reader_sql import (
    SqlAtendimentoReader,
)
from src.modules.consultation.infrastructure.memory_signed_cache import (
    MemorySignedCache,
)
from src.modules.queue.application.ports.queue_store_port import (
    AtendimentoHistoricoQueueDTO,
    QueueStorePort,
)
from src.modules.queue.application.ports.triage_port import TriagePort
from src.modules.queue.application.services.fila_service import FilaService
from src.modules.queue.domain.models import Atendimento
from src.modules.queue.domain.models.atendimento import StatusAtendimento
from src.modules.queue.infrastructure.valkey_queue_engine import ValkeyQueueEngine
from src.modules.triage.application.dtos import TriageRiskEvaluationDTO
from src.modules.triage.application.services.triage_service import TriageService
from src.modules.triage.domain.models.triagem import Triagem

from tests.doubles import (
    FakeAsyncSession,
    FakeAtendimentoReader,
    FakeICPBrasilSigner,
    FakeMemoryStorage,
    FakePDFGenerator,
    FakeResult,
    FakeTriagePort,
    FakeValkey,
)

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession


class _FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def all(self) -> list[dict[str, Any]]:
        return list(self._rows)

    def one_or_none(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class _FakeMappingsResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> _FakeMappings:
        return _FakeMappings(self._rows)


class _FakeHistoricoAtendimentoReader(AtendimentoReaderPort):
    """In-memory double implementing AtendimentoReaderPort and Historico port."""

    def __init__(
        self,
        historico: list[AtendimentoHistoricoDTO] | None = None,
        resumos: dict[UUID, AtendimentoResumoDTO] | None = None,
    ) -> None:
        self._historico = historico or []
        self._resumos = resumos or {}
        self.chamadas_historico: list[UUID] = []

    async def obter_resumo(self, atendimento_id: UUID) -> AtendimentoResumoDTO | None:
        return self._resumos.get(atendimento_id)

    async def concluir_atendimento(
        self,
        atendimento_id: UUID,
        *,
        auto_commit: bool = True,
    ) -> UUID | None:
        return None

    async def liberar_consulta_ativa_medico(self, medico_id: UUID) -> None:
        return None

    async def atender_chamada(self, atendimento_id: UUID) -> None:
        return None

    async def listar_historico_paciente(
        self,
        paciente_id: UUID,
    ) -> list[AtendimentoHistoricoDTO]:
        self.chamadas_historico.append(paciente_id)
        return [item for item in self._historico if item.paciente_id == paciente_id]


def _build_pep_service(
    session: FakeAsyncSession,
    reader: AtendimentoReaderPort | None = None,
    pdf_bytes: bytes = b"%PDF-1.4-paciente-portal%",
) -> PEPService:
    pdf_gen = FakePDFGenerator(content=pdf_bytes)
    signer = FakeICPBrasilSigner()
    storage = FakeMemoryStorage()
    doc_svc = DocumentoService(
        session=cast("AsyncSession", session),
        pdf_generator=pdf_gen,
        signer=signer,
        storage=storage,
        cache=MemorySignedCache(),
    )
    return PEPService(
        session=cast("AsyncSession", session),
        pdf_generator=pdf_gen,
        signer=signer,
        storage=storage,
        documento_service=doc_svc,
        atendimento_reader=reader,
    )


def _issue_jwt(usuario_id: UUID, papel: Role) -> str:
    return create_access_token(
        usuario_id=usuario_id,
        papel=papel.value,
    )


class _RecordingMappingsSession(FakeAsyncSession):
    """Fake session capturing executed SQL/ORM statements for inspection."""

    def __init__(self, results: list[Any] | None = None) -> None:
        super().__init__(results=results)
        self.executed_statements: list[Any] = []

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        if args:
            self.executed_statements.append(args[0])
        return await super().execute(*args, **kwargs)


class _FakeQueueStoreHistorico:
    """Minimal in-memory QueueStore double for QueueStoreAtendimentoReaderAdapter."""

    def __init__(self, historico: list[AtendimentoHistoricoQueueDTO]) -> None:
        self._historico = historico
        self.chamadas: list[UUID] = []

    async def listar_historico_paciente(
        self,
        paciente_id: UUID,
    ) -> list[AtendimentoHistoricoQueueDTO]:
        self.chamadas.append(paciente_id)
        return [item for item in self._historico if item.paciente_id == paciente_id]


@pytest.mark.asyncio
async def test_sql_atendimento_reader_listar_historico_paciente_maps_rows() -> None:
    """SqlAtendimentoReader reads only atendimentos without JOINing triagens."""
    atend_1 = uuid7()
    atend_2 = uuid7()
    paciente_id = uuid7()
    medico_id = uuid7()
    t1 = datetime(2026, 11, 10, 14, 0, tzinfo=UTC)
    t2 = datetime(2026, 11, 11, 10, 30, tzinfo=UTC)

    fake_session = _RecordingMappingsSession(
        results=[
            _FakeMappingsResult(
                [
                    {
                        "atendimento_id": atend_2,
                        "paciente_id": paciente_id,
                        "status": "em_atendimento",
                        "prioridade_clinica": 2,
                        "criado_em": t2,
                        "finalizado_em": None,
                        "medico_id": str(medico_id),
                    },
                    {
                        "atendimento_id": str(atend_1),
                        "paciente_id": str(paciente_id),
                        "status": "CONCLUIDO",
                        "prioridade_clinica": 4,
                        "criado_em": t1,
                        "finalizado_em": t1 + timedelta(minutes=15),
                        "medico_id": None,
                    },
                ]
            )
        ]
    )
    reader = SqlAtendimentoReader(cast("AsyncSession", fake_session))
    assert isinstance(reader, HistoricoAtendimentoReaderPort)

    items = await reader.listar_historico_paciente(paciente_id)

    assert len(fake_session.executed_statements) == 1
    sql_text = str(fake_session.executed_statements[0]).lower()
    assert "from atendimentos" in sql_text
    assert "triagens" not in sql_text
    assert "join" not in sql_text

    assert len(items) == 2
    assert items[0].atendimento_id == atend_2
    assert items[0].status == "EM_ATENDIMENTO"
    assert items[0].prioridade_clinica == 2
    assert items[0].medico_id == medico_id
    assert items[0].queixa_principal is None
    assert items[1].atendimento_id == atend_1
    assert items[1].queixa_principal is None
    assert items[1].medico_id is None


@pytest.mark.asyncio
async def test_pep_service_listar_historico_omits_unfinalized_soap_notes() -> None:
    """PEPService exposes CID-10 and conduta ONLY when EvolucaoClinica is finalized."""
    paciente_id = uuid7()
    medico_id = uuid7()
    atend_finalizado = uuid7()
    atend_rascunho = uuid7()
    now = datetime.now(UTC)

    historico = [
        AtendimentoHistoricoDTO(
            atendimento_id=atend_finalizado,
            paciente_id=paciente_id,
            status="CONCLUIDO",
            prioridade_clinica=3,
            criado_em=now - timedelta(days=1),
            finalizado_em=now - timedelta(days=1, minutes=-15),
            medico_id=medico_id,
            queixa_principal="Dor de garganta",
        ),
        AtendimentoHistoricoDTO(
            atendimento_id=atend_rascunho,
            paciente_id=paciente_id,
            status="EM_ATENDIMENTO",
            prioridade_clinica=4,
            criado_em=now,
            finalizado_em=None,
            medico_id=medico_id,
            queixa_principal="Tosse seca",
        ),
    ]
    ev_finalizada = EvolucaoClinica(
        atendimento_id=atend_finalizado,
        medico_id=medico_id,
        anamnese="Anotação privada sigilosa do médico",
        conduta="Hidratação e sintomáticos por 5 dias",
        cid10_principal="J02.9",
        identidade_verificada=True,
        finalizado_em=now - timedelta(days=1, minutes=-15),
    )
    ev_rascunho = EvolucaoClinica(
        atendimento_id=atend_rascunho,
        medico_id=medico_id,
        anamnese="Rascunho privado",
        conduta="Suspeita em investigação",
        cid10_principal="R05",
        identidade_verificada=True,
        finalizado_em=None,
    )

    fake_session = FakeAsyncSession(results=[FakeResult([ev_finalizada, ev_rascunho])])
    reader = _FakeHistoricoAtendimentoReader(historico=historico)
    svc = _build_pep_service(fake_session, reader=reader)

    resultado = await svc.listar_historico_paciente(paciente_id)

    assert reader.chamadas_historico == [paciente_id]
    assert len(resultado) == 2

    item_fin = resultado[0]
    assert item_fin.atendimento_id == atend_finalizado
    assert item_fin.diagnostico_cid10 == "J02.9"
    assert item_fin.conduta_resumo == "Hidratação e sintomáticos por 5 dias"
    assert not hasattr(item_fin, "anamnese")

    item_draft = resultado[1]
    assert item_draft.atendimento_id == atend_rascunho
    assert item_draft.diagnostico_cid10 is None
    assert item_draft.conduta_resumo is None


@pytest.mark.asyncio
async def test_pep_service_requires_historico_and_reader_ports_no_raw_sql() -> None:
    """PEPService refuses raw SQL fallback when reader lacks Historico port."""
    paciente_id = uuid7()
    doc_id = uuid7()
    atend_id = uuid7()
    medico_id = uuid7()

    # FakeAtendimentoReader does not implement listar_historico_paciente
    fake_session = FakeAsyncSession()
    svc_no_hist = _build_pep_service(fake_session, reader=FakeAtendimentoReader())
    with pytest.raises(RuntimeError, match="HistoricoAtendimentoReaderPort"):
        await svc_no_hist.listar_historico_paciente(paciente_id)
    with pytest.raises(RuntimeError, match="HistoricoAtendimentoReaderPort"):
        await svc_no_hist.listar_documentos_paciente(paciente_id)
    assert fake_session.executes == 0

    # reader=None in compilar_pdf_para_paciente must fail explicitly without raw SQL
    doc = DocumentoClinico(
        id=doc_id,
        atendimento_id=atend_id,
        medico_id=medico_id,
        tipo_documento=TipoDocumentoClinico.RECEITA_SIMPLES,
        chave_s3="consultations/doc.pdf",
    )
    session_doc = FakeAsyncSession(results=[FakeResult(doc)])
    svc_no_reader = _build_pep_service(session_doc, reader=None)
    with pytest.raises(RuntimeError, match="AtendimentoReaderPort"):
        await svc_no_reader.compilar_pdf_para_paciente(doc_id, paciente_id)
    assert session_doc.executes == 1


@pytest.mark.asyncio
async def test_queue_store_adapter_implements_historico_port_and_maps_dtos() -> None:
    """QueueStoreAtendimentoReaderAdapter implements HistoricoAtendimentoReaderPort."""
    paciente_id = uuid7()
    medico_id = uuid7()
    atend_id = uuid7()
    now = datetime.now(UTC)

    queue_store = _FakeQueueStoreHistorico(
        historico=[
            AtendimentoHistoricoQueueDTO(
                atendimento_id=atend_id,
                paciente_id=paciente_id,
                status="CONCLUIDO",
                prioridade_clinica=3,
                criado_em=now - timedelta(hours=1),
                finalizado_em=now,
                medico_id=medico_id,
                queixa_principal="Dor torácica leve",
            )
        ]
    )
    adapter = QueueStoreAtendimentoReaderAdapter(cast("QueueStorePort", queue_store))
    assert isinstance(adapter, AtendimentoReaderPort)
    assert isinstance(adapter, HistoricoAtendimentoReaderPort)

    items = await adapter.listar_historico_paciente(paciente_id)
    assert queue_store.chamadas == [paciente_id]
    assert len(items) == 1
    assert isinstance(items[0], AtendimentoHistoricoDTO)
    assert items[0].atendimento_id == atend_id
    assert items[0].queixa_principal == "Dor torácica leve"
    assert items[0].medico_id == medico_id


@pytest.mark.asyncio
async def test_triage_service_obter_queixas_por_atendimentos() -> None:
    """TriageService fetches primary complaints via ORM cleanly."""
    atend_1 = uuid7()
    atend_2 = uuid7()

    # Empty input returns empty mapping without touching DB
    svc_no_session = TriageService()
    assert await svc_no_session.obter_queixas_por_atendimentos([]) == {}

    with pytest.raises(RuntimeError, match="AsyncSession"):
        await svc_no_session.obter_queixas_por_atendimentos([atend_1])

    triagem_1 = Triagem(
        atendimento_id=atend_1,
        queixa_principal="Dor de garganta leve",
        prioridade_calculada=5,
        escala_dor=0,
    )
    triage_session = FakeAsyncSession(results=[FakeResult([triagem_1])])
    svc = TriageService(session=cast("AsyncSession", triage_session))
    assert isinstance(svc, TriagePort)

    queixas = await svc.obter_queixas_por_atendimentos([atend_1, atend_2])
    assert queixas == {atend_1: "Dor de garganta leve"}


@pytest.mark.asyncio
async def test_hexagonal_chain_pep_queue_triage_without_raw_sql() -> None:
    """End-to-end in-memory boundary: PEP -> Adapter -> FilaService -> TriageService."""
    paciente_id = uuid7()
    medico_id = uuid7()
    atend_id = uuid7()
    now = datetime.now(UTC)

    atendimento = Atendimento(
        id=atend_id,
        paciente_id=paciente_id,
        medico_id=medico_id,
        status=StatusAtendimento.CONCLUIDO,
        prioridade_clinica=4,
        tcle_hash="a" * 64,
        criado_em=now - timedelta(hours=2),
        chamada_finalizada_em=now - timedelta(hours=1),
    )
    triagem = Triagem(
        atendimento_id=atend_id,
        queixa_principal="Tosse seca há 3 dias",
        prioridade_calculada=4,
        escala_dor=2,
    )
    evolucao = EvolucaoClinica(
        atendimento_id=atend_id,
        medico_id=medico_id,
        anamnese="Sigilo médico",
        conduta="Hidratação oral",
        cid10_principal="R05",
        identidade_verificada=True,
        finalizado_em=now - timedelta(hours=1),
    )

    triage_svc = TriageService(
        session=cast("AsyncSession", FakeAsyncSession(results=[FakeResult([triagem])]))
    )
    fila_svc = FilaService(
        queue_engine=ValkeyQueueEngine(valkey=cast("Redis", FakeValkey())),
        db_session=cast(
            "AsyncSession", FakeAsyncSession(results=[FakeResult([atendimento])])
        ),
        triage_port=triage_svc,
    )
    assert isinstance(fila_svc, QueueStorePort)

    adapter = QueueStoreAtendimentoReaderAdapter(fila_svc)
    assert isinstance(adapter, HistoricoAtendimentoReaderPort)

    pep_svc = _build_pep_service(
        FakeAsyncSession(results=[FakeResult([evolucao])]),
        reader=adapter,
    )
    historico = await pep_svc.listar_historico_paciente(paciente_id)

    assert len(historico) == 1
    assert historico[0].atendimento_id == atend_id
    assert historico[0].queixa_principal == "Tosse seca há 3 dias"
    assert historico[0].diagnostico_cid10 == "R05"
    assert historico[0].conduta_resumo == "Hidratação oral"


@pytest.mark.asyncio
async def test_fila_service_listar_historico_com_fake_triage_port_unificado() -> None:
    """FilaService queries unified FakeTriagePort without isinstance splits."""
    paciente_id = uuid7()
    atend_id = uuid7()
    now = datetime.now(UTC)

    atendimento = Atendimento(
        id=atend_id,
        paciente_id=paciente_id,
        status=StatusAtendimento.APTO_PARA_CHAMADA,
        prioridade_clinica=3,
        tcle_hash="b" * 64,
        criado_em=now,
    )
    fake_triage = FakeTriagePort(
        evaluation=TriageRiskEvaluationDTO(
            prioridade_clinica=3,
            tcle_hash="b" * 64,
        ),
        queixas={atend_id: "Cefaleia intensa"},
    )
    assert isinstance(fake_triage, TriagePort)

    fila_svc = FilaService(
        queue_engine=ValkeyQueueEngine(valkey=cast("Redis", FakeValkey())),
        db_session=cast(
            "AsyncSession", FakeAsyncSession(results=[FakeResult([atendimento])])
        ),
        triage_port=fake_triage,
    )
    items = await fila_svc.listar_historico_paciente(paciente_id)
    assert len(items) == 1
    assert items[0].atendimento_id == atend_id
    assert items[0].queixa_principal == "Cefaleia intensa"


@pytest.mark.asyncio
async def test_pep_service_listar_docs_paciente_orders_desc_and_omits_s3() -> None:
    """Documents are sorted newest first, filtered by patient, without s3_key."""
    paciente_id = uuid7()
    medico_id = uuid7()
    atend_id = uuid7()
    atend_outro = uuid7()
    now = datetime.now(UTC)

    doc_old = DocumentoClinico(
        id=uuid4(),
        atendimento_id=atend_id,
        medico_id=medico_id,
        tipo_documento=TipoDocumentoClinico.ATESTADO_MEDICO,
        chave_s3="consultations/old.pdf",
        sha256_hash="a" * 64,
        assinado_em=now - timedelta(hours=3),
    )
    doc_new = DocumentoClinico(
        id=uuid4(),
        atendimento_id=atend_id,
        medico_id=medico_id,
        tipo_documento=TipoDocumentoClinico.RECEITA_SIMPLES,
        chave_s3="consultations/new.pdf",
        sha256_hash="b" * 64,
        assinado_em=now - timedelta(minutes=10),
    )
    doc_outro_paciente = DocumentoClinico(
        id=uuid4(),
        atendimento_id=atend_outro,
        medico_id=medico_id,
        tipo_documento=TipoDocumentoClinico.RECEITA_SIMPLES,
        chave_s3="consultations/other.pdf",
        assinado_em=now,
    )

    historico = [
        AtendimentoHistoricoDTO(
            atendimento_id=atend_id,
            paciente_id=paciente_id,
            status="CONCLUIDO",
            prioridade_clinica=3,
            criado_em=now - timedelta(hours=4),
        )
    ]
    fake_session = FakeAsyncSession(
        results=[FakeResult([doc_old, doc_new, doc_outro_paciente])]
    )
    reader = _FakeHistoricoAtendimentoReader(historico=historico)
    svc = _build_pep_service(fake_session, reader=reader)

    docs = await svc.listar_documentos_paciente(paciente_id)

    assert len(docs) == 2
    assert docs[0].documento_id == doc_new.id
    assert docs[1].documento_id == doc_old.id
    assert docs[0].status_assinatura == "ASSINADO"
    assert docs[0].token_validacao == str(doc_new.id)
    assert not hasattr(docs[0], "chave_s3")
    assert not hasattr(docs[0], "s3_key")


@pytest.mark.asyncio
async def test_pep_service_compilar_pdf_para_paciente_enforces_ownership() -> None:
    """PDF compilation succeeds for owner patient and rejects IDOR."""
    paciente_dono = uuid7()
    paciente_invasor = uuid7()
    medico_id = uuid7()
    atend_id = uuid7()
    doc_id = uuid7()

    doc = DocumentoClinico(
        id=doc_id,
        atendimento_id=atend_id,
        medico_id=medico_id,
        tipo_documento=TipoDocumentoClinico.RECEITA_SIMPLES,
        chave_s3="consultations/doc.pdf",
    )
    # Force non-empty chave_s3 on model instance for storage miss -> generator
    resumo = AtendimentoResumoDTO(
        atendimento_id=atend_id,
        medico_id=medico_id,
        paciente_id=paciente_dono,
        status="CONCLUIDO",
        tcle_hash="t" * 64,
        is_terminal=True,
    )
    reader = _FakeHistoricoAtendimentoReader(resumos={atend_id: resumo})

    # 1. Owner succeeds
    svc_ok = _build_pep_service(
        FakeAsyncSession(results=[FakeResult(doc), FakeResult(doc), FakeResult(None)]),
        reader=reader,
        pdf_bytes=b"%PDF-owner-ok%",
    )
    pdf = await svc_ok.compilar_pdf_para_paciente(doc_id, paciente_dono)
    assert pdf == b"%PDF-owner-ok%"

    # 2. Wrong patient -> ForbiddenError (Anti-IDOR)
    svc_idor = _build_pep_service(
        FakeAsyncSession(results=[FakeResult(doc)]),
        reader=reader,
    )
    with pytest.raises(ForbiddenError, match=str(paciente_invasor)):
        await svc_idor.compilar_pdf_para_paciente(doc_id, paciente_invasor)

    # 3. Missing document -> DocumentoClinicoNaoEncontradoError (NotFoundError)
    svc_missing = _build_pep_service(
        FakeAsyncSession(results=[FakeResult(None)]),
        reader=reader,
    )
    with pytest.raises(DocumentoClinicoNaoEncontradoError, match=str(doc_id)):
        await svc_missing.compilar_pdf_para_paciente(doc_id, paciente_dono)

    # 4. Missing attendance -> NotFoundError
    svc_no_atend = _build_pep_service(
        FakeAsyncSession(results=[FakeResult(doc)]),
        reader=_FakeHistoricoAtendimentoReader(resumos={}),
    )
    with pytest.raises(NotFoundError, match=str(atend_id)):
        await svc_no_atend.compilar_pdf_para_paciente(doc_id, paciente_dono)


@pytest.mark.asyncio
async def test_patient_portal_routes_enforce_rbac_anti_idor_and_contracts() -> None:
    """HTTP routes enforce PACIENTE RBAC, Anti-IDOR isolation, and omit s3_key."""
    app = create_app()
    paciente_id = uuid7()
    medico_id = uuid7()
    atend_id = uuid7()
    doc_id = uuid7()
    now = datetime.now(UTC)

    historico = [
        AtendimentoHistoricoDTO(
            atendimento_id=atend_id,
            paciente_id=paciente_id,
            status="CONCLUIDO",
            prioridade_clinica=3,
            criado_em=now - timedelta(hours=1),
            finalizado_em=now,
            medico_id=medico_id,
            queixa_principal="Dor lombar",
        )
    ]
    ev = EvolucaoClinica(
        atendimento_id=atend_id,
        medico_id=medico_id,
        anamnese="Sigilo médico",
        conduta="Repouso relativo e fisioterapia",
        cid10_principal="M54.5",
        identidade_verificada=True,
        finalizado_em=now,
    )
    doc = DocumentoClinico(
        id=doc_id,
        atendimento_id=atend_id,
        medico_id=medico_id,
        tipo_documento=TipoDocumentoClinico.ATESTADO_MEDICO,
        chave_s3="consultations/secret.pdf",
        sha256_hash="c" * 64,
        assinado_em=now,
    )
    resumo = AtendimentoResumoDTO(
        atendimento_id=atend_id,
        medico_id=medico_id,
        paciente_id=paciente_id,
        status="CONCLUIDO",
        tcle_hash="t" * 64,
        is_terminal=True,
    )
    reader = _FakeHistoricoAtendimentoReader(
        historico=historico,
        resumos={atend_id: resumo},
    )

    def _service_factory() -> PEPService:
        # Each request gets its own FakeAsyncSession script based on route
        return _build_pep_service(
            FakeAsyncSession(results=[FakeResult([ev])]),
            reader=reader,
        )

    patient_jwt = _issue_jwt(paciente_id, Role.PACIENTE)
    doctor_jwt = _issue_jwt(medico_id, Role.MEDICO)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Unauthenticated -> 401
        r_unauth = await client.get("/api/v1/consultations/me/historico")
        assert r_unauth.status_code == 401

        # Doctor role -> 403
        r_doc_role = await client.get(
            "/api/v1/consultations/me/historico",
            headers={"Authorization": f"Bearer {doctor_jwt}"},
        )
        assert r_doc_role.status_code == 403

        # Valid patient -> GET /me/historico (ignores spoofed query param)
        app.dependency_overrides[get_pep_service] = _service_factory
        r_hist = await client.get(
            f"/api/v1/consultations/me/historico?paciente_id={uuid4()}",
            headers={"Authorization": f"Bearer {patient_jwt}"},
        )
        assert r_hist.status_code == 200
        hist_json = r_hist.json()
        assert len(hist_json) == 1
        assert hist_json[0]["atendimento_id"] == str(atend_id)
        assert hist_json[0]["diagnostico_cid10"] == "M54.5"
        assert hist_json[0]["conduta_resumo"] == "Repouso relativo e fisioterapia"
        assert "anamnese" not in hist_json[0]

        # Valid patient -> GET /me/documentos (never leaks s3_key/chave_s3)
        app.dependency_overrides[get_pep_service] = lambda: _build_pep_service(
            FakeAsyncSession(results=[FakeResult([doc])]),
            reader=reader,
        )
        r_docs = await client.get(
            "/api/v1/consultations/me/documentos",
            headers={"Authorization": f"Bearer {patient_jwt}"},
        )
        assert r_docs.status_code == 200
        docs_json = r_docs.json()
        assert len(docs_json) == 1
        assert docs_json[0]["documento_id"] == str(doc_id)
        assert docs_json[0]["status_assinatura"] == "ASSINADO"
        assert docs_json[0]["token_validacao"] == str(doc_id)
        assert "s3_key" not in docs_json[0]
        assert "chave_s3" not in docs_json[0]

        # Valid patient -> GET /me/documents/{documento_id}/pdf
        pdf_session = FakeAsyncSession(
            results=[FakeResult(doc), FakeResult(doc), FakeResult(None)]
        )
        app.dependency_overrides[get_pep_service] = lambda: _build_pep_service(
            pdf_session,
            reader=reader,
            pdf_bytes=b"%PDF-portal-download%",
        )
        r_pdf = await client.get(
            f"/api/v1/consultations/me/documents/{doc_id}/pdf",
            headers={"Authorization": f"Bearer {patient_jwt}"},
        )
        assert r_pdf.status_code == 200
        assert r_pdf.content == b"%PDF-portal-download%"
        assert r_pdf.headers["content-type"] == "application/pdf"

        # Another patient -> 403 IDOR block
        other_patient_jwt = _issue_jwt(uuid7(), Role.PACIENTE)
        app.dependency_overrides[get_pep_service] = lambda: _build_pep_service(
            FakeAsyncSession(results=[FakeResult(doc)]),
            reader=reader,
        )
        r_idor = await client.get(
            f"/api/v1/consultations/me/documents/{doc_id}/pdf",
            headers={"Authorization": f"Bearer {other_patient_jwt}"},
        )
        assert r_idor.status_code == 403
