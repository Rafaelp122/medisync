"""Unit tests for ambulatory production HTTP router (US-11, RF-08)."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from src.core.authz.token import create_access_token
from src.main import create_app
from src.modules.ambulatory.application.dtos import (
    BpaArquivoExportadoDTO,
    BpaRegistroDetalheDTO,
)
from src.modules.ambulatory.application.services.producao_service import (
    ProducaoAmbulatorialService,
)
from src.modules.ambulatory.composition import get_producao_ambulatorial_service
from src.modules.ambulatory.domain.exceptions import (
    CompetenciaInvalidaError,
    ProducaoNaoEncontradaError,
)
from src.modules.ambulatory.domain.models.producao_ambulatorial import (
    ProducaoAmbulatorial,
)

from tests.doubles import FakeAsyncSession, FakeAuditTrail, FakeBpaDirectory


class FakeProducaoAmbulatorialService:
    """Fake em memória para testes do router ambulatorial (ADR-001/ADR-008)."""

    def __init__(
        self,
        *,
        lista_result: tuple[list[ProducaoAmbulatorial], int] | Exception | None = None,
        export_result: BpaArquivoExportadoDTO | Exception | None = None,
    ) -> None:
        self.lista_result = lista_result
        self.export_result = export_result

    async def listar_producao_por_competencia(
        self,
        *,
        competencia: str,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[ProducaoAmbulatorial], int]:
        if isinstance(self.lista_result, Exception):
            raise self.lista_result
        if self.lista_result is not None:
            return self.lista_result
        return [], 0

    async def gerar_arquivo_bpa_i(
        self,
        *,
        competencia: str,
    ) -> BpaArquivoExportadoDTO:
        if isinstance(self.export_result, Exception):
            raise self.export_result
        if self.export_result is not None:
            return self.export_result
        raise ProducaoNaoEncontradaError(competencia=competencia)


def _make_jwt_token(papel: str = "GESTOR_UNIDADE") -> str:
    return create_access_token(usuario_id=uuid4(), papel=papel)


@pytest.mark.asyncio
async def test_listar_producao_200_ok() -> None:
    app = create_app()
    atend_id = uuid4()
    item_model = ProducaoAmbulatorial(
        atendimento_id=atend_id,
        profissional_id=uuid4(),
        paciente_id=uuid4(),
        cnes="2000001",
        codigo_sigtap="03.01.01.025-0",
        carater_atendimento="02",
        competencia="202611",
    )
    fake_service = FakeProducaoAmbulatorialService(lista_result=([item_model], 1))
    app.dependency_overrides[get_producao_ambulatorial_service] = lambda: fake_service

    token = _make_jwt_token(papel="GESTOR_UNIDADE")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/ambulatory/producao?competencia=202611",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["competencia"] == "202611"
    assert len(data["items"]) == 1
    assert data["items"][0]["atendimento_id"] == str(atend_id)
    assert data["items"][0]["codigo_sigtap"] == "03.01.01.025-0"


@pytest.mark.asyncio
async def test_listar_producao_competencia_invalida_retorna_400() -> None:
    app = create_app()
    fake_service = FakeProducaoAmbulatorialService(
        lista_result=CompetenciaInvalidaError("202699")
    )
    app.dependency_overrides[get_producao_ambulatorial_service] = lambda: fake_service

    token = _make_jwt_token(papel="GESTOR_UNIDADE")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/ambulatory/producao?competencia=202699",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 400
    data = resp.json()
    assert data["code"] == "COMPETENCIA_INVALIDA"
    assert "202699" in data["detail"]


@pytest.mark.asyncio
async def test_exportar_bpa_200_download() -> None:
    app = create_app()
    fake_service = FakeProducaoAmbulatorialService(
        export_result=BpaArquivoExportadoDTO(
            conteudo="01#BPA#202611...\r\n032000001...\r\n",
            nome_arquivo="BPA_I_202611_2000001.txt",
            total_registros=1,
            total_folhas=1,
            competencia="202611",
        )
    )
    app.dependency_overrides[get_producao_ambulatorial_service] = lambda: fake_service

    token = _make_jwt_token(papel="FATURAMENTO")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/ambulatory/producao/exportar?competencia=202611",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    assert (
        'attachment; filename="BPA_I_202611_2000001.txt"'
        in resp.headers["content-disposition"]
    )
    assert resp.text.startswith("01#BPA#202611")


@pytest.mark.asyncio
async def test_exportar_bpa_sem_registros_retorna_404() -> None:
    app = create_app()
    fake_service = FakeProducaoAmbulatorialService(
        export_result=ProducaoNaoEncontradaError(competencia="202611")
    )
    app.dependency_overrides[get_producao_ambulatorial_service] = lambda: fake_service

    token = _make_jwt_token(papel="GESTOR_UNIDADE")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/ambulatory/producao/exportar?competencia=202611",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 404
    data = resp.json()
    assert data["code"] == "PRODUCAO_NAO_ENCONTRADA"
    assert "202611" in data["detail"]


@pytest.mark.asyncio
async def test_ambulatory_sem_token_retorna_401() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/ambulatory/producao?competencia=202611")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_ambulatory_papel_paciente_retorna_403() -> None:
    app = create_app()
    token = _make_jwt_token(papel="PACIENTE")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/ambulatory/producao?competencia=202611",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 403
    data = resp.json()
    assert "PACIENTE" in data["detail"]


@pytest.mark.asyncio
async def test_exportar_bpa_read_only_com_pendencia_sem_record_event() -> None:
    app = create_app()
    fake_session = FakeAsyncSession()
    fake_audit = FakeAuditTrail()
    registro = BpaRegistroDetalheDTO(
        producao_id=uuid4(),
        atendimento_id=uuid4(),
        profissional_id=uuid4(),
        paciente_id=uuid4(),
        cnes="2000001",
        codigo_sigtap="03.01.01.025-0",
        carater_atendimento="02",
        competencia="202611",
        consolidado_em=datetime.now(UTC),
        paciente_nome="PACIENTE SEM CNS",
        paciente_cns=None,
        paciente_cpf="12345678900",
        paciente_data_nascimento="20000101",
        paciente_sexo="F",
        paciente_ibge="355030",
        medico_cns=None,
        medico_cbo="225125",
        unidade_nome="UPA DIGITAL UNICA",
        unidade_sigla="MSYNC",
        unidade_cnpj="12345678000199",
        idade=0,
    )
    service = ProducaoAmbulatorialService(
        session=fake_session,  # pyright: ignore[reportArgumentType]
        audit_trail=fake_audit,
        bpa_directory=FakeBpaDirectory([registro]),
    )
    app.dependency_overrides[get_producao_ambulatorial_service] = lambda: service

    token = _make_jwt_token(papel="FATURAMENTO")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/ambulatory/producao/exportar?competencia=202611",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    assert fake_audit.events == []
    assert fake_session.commits == 0
    assert fake_session.flushes == 0
    assert fake_session.added == []
