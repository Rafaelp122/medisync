"""Unit tests for patient queue admission router (Anti-IDOR and ADR-001/ADR-008)."""

from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from src.core.config import get_settings
from src.core.security import create_intake_token
from src.main import create_app
from src.modules.auth.infrastructure.jwt_token_service import JWTTokenService
from src.modules.queue.application.dtos import AdmissaoAtendimentoResult
from src.modules.queue.application.services.fila_service import FilaService
from src.modules.queue.composition import get_fila_service


def _make_intake_token(paciente_id: UUID, org_id: int) -> str:
    settings = get_settings()
    return create_intake_token(paciente_id, org_id, settings.SECRET_KEY)


def _make_jwt_token(user_id: UUID, org_id: int, papel: str = "PACIENTE") -> str:
    service = JWTTokenService(secret_key=get_settings().JWT_SECRET_KEY)
    return service.gerar_tokens(
        usuario_id=user_id, organizacao_id=org_id, papel=papel
    ).access_token


@pytest.mark.asyncio
async def test_admissao_sucesso_com_token_intake() -> None:
    """Verifica admissão autorizada com token de acolhimento válido do paciente."""
    app = create_app()
    paciente_id = uuid4()
    atendimento_id = uuid4()
    triagem_id = uuid4()
    org_id = 42

    mock_service = MagicMock(spec=FilaService)
    mock_service.admitir_paciente = AsyncMock(
        return_value=AdmissaoAtendimentoResult(
            atendimento_id=atendimento_id,
            triagem_id=triagem_id,
            organizacao_id=org_id,
            paciente_id=paciente_id,
            status_atendimento="TRIADO_AGUARDANDO_ELEGIBILIDADE",
            prioridade_clinica=3,
            alerta_samu_disparado=False,
            instrucoes=None,
        )
    )

    app.dependency_overrides[get_fila_service] = lambda: mock_service

    try:
        token = _make_intake_token(paciente_id, org_id)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/fila/admissao",
                headers={
                    "X-Tenant-ID": str(org_id),
                    "Authorization": f"Bearer {token}",
                },
                json={
                    "paciente_id": str(paciente_id),
                    "queixa_principal": "Febre e dor de cabeça há 2 dias",
                    "sintomas": ["febre", "cefaleia"],
                    "escala_dor": 5,
                    "tcle_texto": "Termo de consentimento informado",
                },
            )

            assert resp.status_code == 201
            data = cast("dict[str, object]", resp.json())
            assert data["atendimento_id"] == str(atendimento_id)
            assert data["triagem_id"] == str(triagem_id)
            assert data["paciente_id"] == str(paciente_id)
            assert data["organizacao_id"] == org_id
            assert data["prioridade_clinica"] == 3
            mock_service.admitir_paciente.assert_awaited_once()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admissao_sucesso_com_token_jwt_paciente() -> None:
    """Verifica admissão autorizada com Bearer JWT de paciente autenticado."""
    app = create_app()
    paciente_id = uuid4()
    org_id = 10

    mock_service = MagicMock(spec=FilaService)
    mock_service.admitir_paciente = AsyncMock(
        return_value=AdmissaoAtendimentoResult(
            atendimento_id=uuid4(),
            triagem_id=uuid4(),
            organizacao_id=org_id,
            paciente_id=paciente_id,
            status_atendimento="TRIADO_AGUARDANDO_ELEGIBILIDADE",
            prioridade_clinica=4,
            alerta_samu_disparado=False,
            instrucoes=None,
        )
    )
    app.dependency_overrides[get_fila_service] = lambda: mock_service

    try:
        token = _make_jwt_token(paciente_id, org_id, papel="PACIENTE")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/fila/admissao",
                headers={
                    "X-Tenant-ID": str(org_id),
                    "Authorization": f"Bearer {token}",
                },
                json={
                    "paciente_id": str(paciente_id),
                    "queixa_principal": "Dor leve no joelho",
                    "tcle_texto": "Termo aceito",
                },
            )
            assert resp.status_code == 201
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admissao_rejeitada_sem_credencial_anonima() -> None:
    """Verifica que a tentativa de injeção anônima é bloqueada com 401."""
    app = create_app()
    paciente_id = uuid4()
    org_id = 42

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/fila/admissao",
            headers={"X-Tenant-ID": str(org_id)},
            json={
                "paciente_id": str(paciente_id),
                "queixa_principal": "Injeção não autorizada",
                "tcle_texto": "TCLE fake",
            },
        )
        assert resp.status_code == 401
        data = cast("dict[str, object]", resp.json())
        assert data["code"] == "UNAUTHORIZED"
        assert "Credencial de autenticação não fornecida" in str(data["detail"])


@pytest.mark.asyncio
async def test_admissao_rejeitada_com_paciente_divergente_idor() -> None:
    """Verifica proteção anti-IDOR: token não pode admitir outro paciente."""
    app = create_app()
    paciente_autorizado = uuid4()
    paciente_alvo = uuid4()
    org_id = 42

    token = _make_intake_token(paciente_autorizado, org_id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/fila/admissao",
            headers={
                "X-Tenant-ID": str(org_id),
                "Authorization": f"Bearer {token}",
            },
            json={
                "paciente_id": str(paciente_alvo),
                "queixa_principal": "Tentativa de admissão fraudulenta",
                "tcle_texto": "TCLE",
            },
        )
        assert resp.status_code == 403
        data = cast("dict[str, object]", resp.json())
        assert data["code"] == "FORBIDDEN"
        assert "Acesso negado" in str(data["detail"])


@pytest.mark.asyncio
async def test_admissao_rejeitada_com_organizacao_divergente() -> None:
    """Verifica que token de org A não pode admitir na organização B."""
    app = create_app()
    paciente_id = uuid4()
    org_a = 42
    org_b = 99

    token = _make_intake_token(paciente_id, org_a)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/fila/admissao",
            headers={
                "X-Tenant-ID": str(org_b),
                "Authorization": f"Bearer {token}",
            },
            json={
                "paciente_id": str(paciente_id),
                "queixa_principal": "Queixa",
                "tcle_texto": "TCLE",
            },
        )
        assert resp.status_code == 403
        data = cast("dict[str, object]", resp.json())
        assert data["code"] == "FORBIDDEN"
