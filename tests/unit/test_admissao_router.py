"""Unit tests for patient queue admission router (Anti-IDOR and ADR-001/ADR-008)."""

from typing import cast
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from src.core.authz.token import create_access_token
from src.core.config import get_settings
from src.core.security import create_intake_token
from src.main import create_app
from src.modules.queue.application.dtos import AdmissaoAtendimentoResult
from src.modules.queue.composition import get_fila_service

from tests.doubles import FakeFilaService


def _make_intake_token(paciente_id: UUID) -> str:
    settings = get_settings()
    return create_intake_token(paciente_id, settings.SECRET_KEY)


def _make_jwt_token(user_id: UUID, papel: str = "PACIENTE") -> str:
    return create_access_token(usuario_id=user_id, papel=papel)


@pytest.mark.asyncio
async def test_admissao_sucesso_com_token_intake() -> None:
    """Verifica admissão autorizada com token de acolhimento válido do paciente."""
    app = create_app()
    paciente_id = uuid4()
    atendimento_id = uuid4()
    triagem_id = uuid4()

    tcle_hash = "b" * 64
    fake_service = FakeFilaService(
        admitir_result=AdmissaoAtendimentoResult(
            atendimento_id=atendimento_id,
            triagem_id=triagem_id,
            paciente_id=paciente_id,
            status_atendimento="APTO_PARA_CHAMADA",
            prioridade_clinica=3,
            alerta_samu_disparado=False,
            instrucoes=None,
            tcle_hash=tcle_hash,
        )
    )

    app.dependency_overrides[get_fila_service] = lambda: fake_service

    try:
        token = _make_intake_token(paciente_id)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/fila/admissao",
                headers={"Authorization": f"Bearer {token}"},
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
            assert "organizacao_id" not in data
            assert data["status_atendimento"] == "APTO_PARA_CHAMADA"
            assert data["prioridade_clinica"] == 3
            assert data["tcle_hash"] == tcle_hash
            assert len(fake_service.admitir_calls) == 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admissao_sucesso_com_token_jwt_paciente() -> None:
    """Verifica admissão autorizada com Bearer JWT de paciente autenticado."""
    app = create_app()
    paciente_id = uuid4()

    fake_service = FakeFilaService(
        admitir_result=AdmissaoAtendimentoResult(
            atendimento_id=uuid4(),
            triagem_id=uuid4(),
            paciente_id=paciente_id,
            status_atendimento="APTO_PARA_CHAMADA",
            prioridade_clinica=4,
            alerta_samu_disparado=False,
            instrucoes=None,
        )
    )
    app.dependency_overrides[get_fila_service] = lambda: fake_service

    try:
        token = _make_jwt_token(paciente_id, papel="PACIENTE")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/fila/admissao",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "paciente_id": str(paciente_id),
                    "queixa_principal": "Dor leve no joelho",
                    "tcle_texto": "Termo aceito",
                },
            )
            assert resp.status_code == 201
            assert len(fake_service.admitir_calls) == 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admissao_rejeitada_sem_credencial_anonima() -> None:
    """Verifica que a tentativa de injeção anônima é bloqueada com 401."""
    app = create_app()
    paciente_id = uuid4()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/fila/admissao",
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

    token = _make_intake_token(paciente_autorizado)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/fila/admissao",
            headers={"Authorization": f"Bearer {token}"},
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
