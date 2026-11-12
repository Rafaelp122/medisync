"""Unit tests for ambulatory production HTTP router (US-11, RF-08)."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from src.core.config import get_settings
from src.main import create_app
from src.modules.ambulatory.application.dtos import (
    BpaArquivoExportadoDTO,
    BpaProducaoDTO,
    ListaProducaoAmbulatorialDTO,
)
from src.modules.ambulatory.composition import get_producao_ambulatorial_service
from src.modules.ambulatory.domain.exceptions import (
    CompetenciaInvalidaError,
    ProducaoNaoEncontradaError,
)
from src.modules.auth.infrastructure.jwt_token_service import JWTTokenService


class FakeProducaoAmbulatorialService:
    """Fake em memória para testes do router ambulatorial (ADR-001/ADR-008)."""

    def __init__(
        self,
        *,
        lista_result: ListaProducaoAmbulatorialDTO | Exception | None = None,
        export_result: BpaArquivoExportadoDTO | Exception | None = None,
    ) -> None:
        self.lista_result = lista_result
        self.export_result = export_result

    async def listar_producao_por_competencia(
        self,
        *,
        organizacao_id: int,
        competencia: str,
        page: int = 1,
        size: int = 50,
    ) -> ListaProducaoAmbulatorialDTO:
        if isinstance(self.lista_result, Exception):
            raise self.lista_result
        if self.lista_result is not None:
            return self.lista_result
        return ListaProducaoAmbulatorialDTO(
            items=[],
            total=0,
            competencia=competencia,
            organizacao_id=organizacao_id,
            page=page,
            size=size,
        )

    async def gerar_arquivo_bpa_i(
        self,
        *,
        organizacao_id: int,
        competencia: str,
    ) -> BpaArquivoExportadoDTO:
        if isinstance(self.export_result, Exception):
            raise self.export_result
        if self.export_result is not None:
            return self.export_result
        raise ProducaoNaoEncontradaError(
            competencia=competencia, organizacao_id=organizacao_id
        )


def _make_jwt_token(org_id: int = 10, papel: str = "GESTOR_UNIDADE") -> str:
    service = JWTTokenService(secret_key=get_settings().JWT_SECRET_KEY)
    return service.gerar_tokens(
        usuario_id=uuid4(), organizacao_id=org_id, papel=papel
    ).access_token


@pytest.mark.asyncio
async def test_listar_producao_200_ok() -> None:
    app = create_app()
    atend_id = uuid4()
    item_dto = BpaProducaoDTO(
        atendimento_id=atend_id,
        cnes="2000001",
        codigo_sigtap="03.01.01.025-0",
        carater_atendimento="02",
        consolidado_em=datetime.now(UTC),
    )
    fake_service = FakeProducaoAmbulatorialService(
        lista_result=ListaProducaoAmbulatorialDTO(
            items=[item_dto],
            total=1,
            competencia="202611",
            organizacao_id=10,
            page=1,
            size=50,
        )
    )
    app.dependency_overrides[get_producao_ambulatorial_service] = lambda: fake_service

    token = _make_jwt_token(org_id=10, papel="GESTOR_UNIDADE")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/ambulatory/producao?competencia=202611",
            headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "10"},
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

    token = _make_jwt_token(org_id=10, papel="GESTOR_UNIDADE")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/ambulatory/producao?competencia=202699",
            headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "10"},
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

    token = _make_jwt_token(org_id=10, papel="FATURAMENTO")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/ambulatory/producao/exportar?competencia=202611",
            headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "10"},
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
        export_result=ProducaoNaoEncontradaError(
            competencia="202611", organizacao_id=10
        )
    )
    app.dependency_overrides[get_producao_ambulatorial_service] = lambda: fake_service

    token = _make_jwt_token(org_id=10, papel="ADMIN_GLOBAL")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/ambulatory/producao/exportar?competencia=202611",
            headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "10"},
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
        resp = await client.get(
            "/api/v1/ambulatory/producao?competencia=202611",
            headers={"X-Tenant-ID": "10"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_ambulatory_papel_paciente_retorna_403() -> None:
    app = create_app()
    token = _make_jwt_token(org_id=10, papel="PACIENTE")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/ambulatory/producao?competencia=202611",
            headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "10"},
        )
    assert resp.status_code == 403
    data = resp.json()
    assert "PACIENTE" in data["detail"]
