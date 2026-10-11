"""Unit tests for medical queue allocation router (RF-03, RN02, and ADR-001/ADR-008)."""

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from src.core.config import get_settings
from src.main import create_app
from src.modules.auth.infrastructure.jwt_token_service import JWTTokenService
from src.modules.queue.application.dtos import AlocacaoChamadaResult
from src.modules.queue.application.services.fila_service import FilaService
from src.modules.queue.composition import get_fila_service
from src.modules.queue.domain.exceptions import MedicoOcupadoError


def _make_jwt_token(user_id: UUID, org_id: int, papel: str = "MEDICO") -> str:
    service = JWTTokenService(secret_key=get_settings().JWT_SECRET_KEY)
    return service.gerar_tokens(
        usuario_id=user_id, organizacao_id=org_id, papel=papel
    ).access_token


@pytest.mark.asyncio
async def test_chamar_proximo_sucesso_com_paciente_alocado() -> None:
    """Verifica chamada de próximo paciente alocado com sucesso por médico."""
    app = create_app()
    medico_id = uuid4()
    atendimento_id = uuid4()
    org_id = 42

    mock_service = MagicMock(spec=FilaService)
    mock_service.adquirir_proximo_paciente = AsyncMock(
        return_value=AlocacaoChamadaResult(
            atendimento_id=atendimento_id,
            medico_id=medico_id,
            status="CHAMADO",
            chamada_iniciada_em=datetime.now(UTC),
            ttl_segundos=45,
        )
    )
    app.dependency_overrides[get_fila_service] = lambda: mock_service

    try:
        token = _make_jwt_token(medico_id, org_id, papel="MEDICO")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/fila/chamar-proximo",
                headers={
                    "X-Tenant-ID": str(org_id),
                    "Authorization": f"Bearer {token}",
                },
            )
            assert resp.status_code == 200
            data = cast("dict[str, object]", resp.json())
            assert data["alocado"] is True
            assert data["atendimento_id"] == str(atendimento_id)
            assert data["medico_id"] == str(medico_id)
            assert data["status"] == "CHAMADO"
            assert data["ttl_segundos"] == 45
            mock_service.adquirir_proximo_paciente.assert_awaited_once()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_chamar_proximo_fila_vazia_retorna_200_com_alocado_false() -> None:
    """Verifica retorno 200 com alocado=False e mensagem explicativa em fila vazia."""
    app = create_app()
    medico_id = uuid4()
    org_id = 42

    mock_service = MagicMock(spec=FilaService)
    mock_service.adquirir_proximo_paciente = AsyncMock(return_value=None)
    app.dependency_overrides[get_fila_service] = lambda: mock_service

    try:
        token = _make_jwt_token(medico_id, org_id, papel="MEDICO")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/fila/chamar-proximo",
                headers={
                    "X-Tenant-ID": str(org_id),
                    "Authorization": f"Bearer {token}",
                },
            )
            assert resp.status_code == 200
            data = cast("dict[str, object]", resp.json())
            assert data["alocado"] is False
            assert "Fila vazia" in str(data["mensagem"])
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_chamar_proximo_rejeitado_sem_autenticacao() -> None:
    """Verifica bloqueio 401 Unauthorized para chamada sem credenciais."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/fila/chamar-proximo",
            headers={"X-Tenant-ID": "42"},
        )
        assert resp.status_code == 401
        data = cast("dict[str, object]", resp.json())
        assert data["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_chamar_proximo_rejeitado_papel_nao_autorizado() -> None:
    """Verifica bloqueio 403 Forbidden se usuário com papel PACIENTE tentar chamar."""
    app = create_app()
    paciente_id = uuid4()
    org_id = 42

    token = _make_jwt_token(paciente_id, org_id, papel="PACIENTE")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/fila/chamar-proximo",
            headers={
                "X-Tenant-ID": str(org_id),
                "Authorization": f"Bearer {token}",
            },
        )
        assert resp.status_code == 403
        data = cast("dict[str, object]", resp.json())
        assert data["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_chamar_proximo_medico_ocupado_retorna_409() -> None:
    """Verifica retorno 409 Conflict quando o médico já possui chamada ativa (RN02)."""
    app = create_app()
    medico_id = uuid4()
    org_id = 42

    mock_service = MagicMock(spec=FilaService)
    mock_service.adquirir_proximo_paciente = AsyncMock(
        side_effect=MedicoOcupadoError("Médico possui chamada ativa.")
    )
    app.dependency_overrides[get_fila_service] = lambda: mock_service

    try:
        token = _make_jwt_token(medico_id, org_id, papel="MEDICO")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/fila/chamar-proximo",
                headers={
                    "X-Tenant-ID": str(org_id),
                    "Authorization": f"Bearer {token}",
                },
            )
            assert resp.status_code == 409
            data = cast("dict[str, object]", resp.json())
            assert data["code"] == "MEDICO_OCUPADO"
    finally:
        app.dependency_overrides.clear()
