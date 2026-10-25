"""Unit tests for patient queue router (position, cancel, deterioration)."""

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from src.core.config import get_settings
from src.core.errors import NotFoundError
from src.core.security import create_intake_token
from src.main import create_app
from src.modules.auth.infrastructure.jwt_token_service import JWTTokenService
from src.modules.queue.application.dtos import (
    AdmissaoAtendimentoResult,
    CancelarAtendimentoResult,
    PioraClinicaResult,
    PosicaoFilaResult,
    RegularizacaoFilaResult,
)
from src.modules.queue.application.services.fila_service import FilaService
from src.modules.queue.composition import (
    get_fila_service,
    get_patient_queue_ownership_checker,
)
from src.modules.queue.domain.exceptions import TransicaoEstadoInvalidaError


def _make_intake_token(paciente_id: UUID, org_id: int) -> str:
    settings = get_settings()
    return create_intake_token(paciente_id, org_id, settings.SECRET_KEY)


def _make_jwt_token(user_id: UUID, org_id: int, papel: str = "PACIENTE") -> str:
    service = JWTTokenService(secret_key=get_settings().JWT_SECRET_KEY)
    return service.gerar_tokens(
        usuario_id=user_id, organizacao_id=org_id, papel=papel
    ).access_token


@pytest.mark.asyncio
async def test_obter_posicao_sucesso_com_token_intake() -> None:
    """Verifica consulta de posição ordinal com token provisório de intake."""
    app = create_app()
    paciente_id = uuid4()
    atendimento_id = uuid4()
    org_id = 42

    mock_service = MagicMock(spec=FilaService)
    mock_service.obter_posicao_e_estimativa = AsyncMock(
        return_value=PosicaoFilaResult(
            atendimento_id=atendimento_id,
            status="APTO_PARA_CHAMADA",
            posicao=2,
            total_aguardando=5,
            tempo_estimado_segundos=1800,
        )
    )
    mock_checker = AsyncMock(return_value=True)

    app.dependency_overrides[get_fila_service] = lambda: mock_service
    app.dependency_overrides[get_patient_queue_ownership_checker] = lambda: mock_checker

    try:
        token = _make_intake_token(paciente_id, org_id)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/api/v1/fila/posicao/{atendimento_id}",
                headers={
                    "X-Tenant-ID": str(org_id),
                    "Authorization": f"Bearer {token}",
                },
            )
            assert resp.status_code == 200
            data = cast("dict[str, object]", resp.json())
            assert data["atendimento_id"] == str(atendimento_id)
            assert data["posicao"] == 2
            assert data["total_aguardando"] == 5
            assert data["tempo_estimado_segundos"] == 1800
            mock_service.obter_posicao_e_estimativa.assert_awaited_once_with(
                organizacao_id=org_id,
                atendimento_id=atendimento_id,
            )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_obter_posicao_rejeitada_sem_posse_idor() -> None:
    """Verifica bloqueio 403 Forbidden quando o token não possui posse (Anti-IDOR)."""
    app = create_app()
    paciente_id = uuid4()
    atendimento_id = uuid4()
    org_id = 42

    mock_checker = AsyncMock(return_value=False)
    app.dependency_overrides[get_patient_queue_ownership_checker] = lambda: mock_checker

    try:
        token = _make_intake_token(paciente_id, org_id)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/api/v1/fila/posicao/{atendimento_id}",
                headers={
                    "X-Tenant-ID": str(org_id),
                    "Authorization": f"Bearer {token}",
                },
            )
            assert resp.status_code == 403
            data = cast("dict[str, object]", resp.json())
            assert data["code"] == "FORBIDDEN"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_obter_posicao_nao_encontrado_retorna_404() -> None:
    """Verifica retorno 404 quando atendimento não existe no banco."""
    app = create_app()
    paciente_id = uuid4()
    atendimento_id = uuid4()
    org_id = 42

    mock_service = MagicMock(spec=FilaService)
    mock_service.obter_posicao_e_estimativa = AsyncMock(
        side_effect=NotFoundError("Atendimento não encontrado.")
    )
    mock_checker = AsyncMock(return_value=True)

    app.dependency_overrides[get_fila_service] = lambda: mock_service
    app.dependency_overrides[get_patient_queue_ownership_checker] = lambda: mock_checker

    try:
        token = _make_intake_token(paciente_id, org_id)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/api/v1/fila/posicao/{atendimento_id}",
                headers={
                    "X-Tenant-ID": str(org_id),
                    "Authorization": f"Bearer {token}",
                },
            )
            assert resp.status_code == 404
            data = cast("dict[str, object]", resp.json())
            assert data["code"] == "NOT_FOUND"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cancelar_atendimento_sucesso() -> None:
    """Verifica cancelamento voluntário com sucesso pelo paciente na fila (RN06)."""
    app = create_app()
    paciente_id = uuid4()
    atendimento_id = uuid4()
    org_id = 42

    now = datetime.now(UTC)
    mock_service = MagicMock(spec=FilaService)
    mock_service.cancelar_atendimento_paciente = AsyncMock(
        return_value=CancelarAtendimentoResult(
            atendimento_id=atendimento_id,
            status="CANCELADO",
            cancelado_em=now,
            motivo="Melhora espontânea dos sintomas",
        )
    )
    mock_checker = AsyncMock(return_value=True)

    app.dependency_overrides[get_fila_service] = lambda: mock_service
    app.dependency_overrides[get_patient_queue_ownership_checker] = lambda: mock_checker

    try:
        token = _make_jwt_token(paciente_id, org_id, papel="PACIENTE")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/fila/cancelar/{atendimento_id}",
                headers={
                    "X-Tenant-ID": str(org_id),
                    "Authorization": f"Bearer {token}",
                },
                json={"motivo": "Melhora espontânea dos sintomas"},
            )
            assert resp.status_code == 200
            data = cast("dict[str, object]", resp.json())
            assert data["atendimento_id"] == str(atendimento_id)
            assert data["status"] == "CANCELADO"
            assert data["motivo"] == "Melhora espontânea dos sintomas"
            mock_service.cancelar_atendimento_paciente.assert_awaited_once_with(
                organizacao_id=org_id,
                atendimento_id=atendimento_id,
                motivo="Melhora espontânea dos sintomas",
            )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_comunicar_piora_clinica_reclassificacao_sucesso() -> None:
    """Verifica comunicação de piora clínica e reclassificação na fila (RF-06)."""
    app = create_app()
    paciente_id = uuid4()
    atendimento_id = uuid4()
    org_id = 42

    mock_service = MagicMock(spec=FilaService)
    mock_service.processar_piora_clinica = AsyncMock(
        return_value=PioraClinicaResult(
            atendimento_id=atendimento_id,
            prioridade_clinica=2,
            alerta_samu_disparado=False,
            redirecionado_emergencia=False,
            nova_posicao=1,
            instrucoes="Prioridade atualizada para Laranja.",
        )
    )
    mock_checker = AsyncMock(return_value=True)

    app.dependency_overrides[get_fila_service] = lambda: mock_service
    app.dependency_overrides[get_patient_queue_ownership_checker] = lambda: mock_checker

    try:
        token = _make_jwt_token(paciente_id, org_id, papel="PACIENTE")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/fila/piora",
                headers={
                    "X-Tenant-ID": str(org_id),
                    "Authorization": f"Bearer {token}",
                },
                json={
                    "atendimento_id": str(atendimento_id),
                    "novos_sintomas": ["dor no peito irradiando para o braço"],
                    "escala_dor": 9,
                    "queixa_adicional": "Dor intensa súbita",
                },
            )
            assert resp.status_code == 200
            data = cast("dict[str, object]", resp.json())
            assert data["atendimento_id"] == str(atendimento_id)
            assert data["prioridade_clinica"] == 2
            assert data["nova_prioridade"] == 2
            assert data["alerta_samu_disparado"] is False
            assert data["redirecionado_emergencia"] is False
            assert data["nova_posicao"] == 1
            mock_service.processar_piora_clinica.assert_awaited_once()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_comunicar_piora_clinica_emergencia_samu() -> None:
    """Verifica salvaguarda de emergência imediata (Vermelho) com alerta SAMU."""
    app = create_app()
    paciente_id = uuid4()
    atendimento_id = uuid4()
    org_id = 42

    mock_service = MagicMock(spec=FilaService)
    mock_service.processar_piora_clinica = AsyncMock(
        return_value=PioraClinicaResult(
            atendimento_id=atendimento_id,
            prioridade_clinica=1,
            alerta_samu_disparado=True,
            redirecionado_emergencia=True,
            nova_posicao=None,
            instrucoes="Emergência detectada. SAMU 192 notificado imediatamente.",
            nova_prioridade=1,
            status_atendimento="CANCELADO_PELO_PACIENTE",
            orientacoes_emergencia=(
                "Emergência detectada. SAMU 192 notificado imediatamente."
            ),
        )
    )
    mock_checker = AsyncMock(return_value=True)

    app.dependency_overrides[get_fila_service] = lambda: mock_service
    app.dependency_overrides[get_patient_queue_ownership_checker] = lambda: mock_checker

    try:
        token = _make_intake_token(paciente_id, org_id)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/fila/piora",
                headers={
                    "X-Tenant-ID": str(org_id),
                    "Authorization": f"Bearer {token}",
                },
                json={
                    "atendimento_id": str(atendimento_id),
                    "novos_sintomas": ["perda de consciência", "dispneia severa"],
                    "escala_dor": 10,
                },
            )
            assert resp.status_code == 200
            data = cast("dict[str, object]", resp.json())
            assert data["atendimento_id"] == str(atendimento_id)
            assert data["prioridade_clinica"] == 1
            assert data["nova_prioridade"] == 1
            assert data["status_atendimento"] == "CANCELADO_PELO_PACIENTE"
            assert data["alerta_samu_disparado"] is True
            assert data["redirecionado_emergencia"] is True
            assert data["nova_posicao"] is None
            assert (
                data["orientacoes_emergencia"]
                == "Emergência detectada. SAMU 192 notificado imediatamente."
            )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admissao_paciente_unificada_no_fila_router() -> None:
    """Verifica admissão de paciente via endpoint unificado da fila (/fila/admissao)."""
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
                    "queixa_principal": "Febre e tosse",
                    "sintomas": ["febre"],
                    "escala_dor": 3,
                    "tcle_texto": "Termo de consentimento aceito",
                },
            )
            assert resp.status_code == 201
            data = cast("dict[str, object]", resp.json())
            assert data["atendimento_id"] == str(atendimento_id)
            assert data["triagem_id"] == str(triagem_id)
            assert data["prioridade_clinica"] == 3
            mock_service.admitir_paciente.assert_awaited_once()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_post_regularizar_sucesso_com_token_intake() -> None:
    """Verifica regularização de atendimento na fila com token de intake (US-05)."""
    app = create_app()
    paciente_id = uuid4()
    atendimento_id = uuid4()
    org_id = 42

    mock_service = MagicMock(spec=FilaService)
    mock_service.regularizar_atendimento = AsyncMock(
        return_value=RegularizacaoFilaResult(
            atendimento_id=atendimento_id,
            promovido=True,
            status="APTO_PARA_CHAMADA",
            score=3000000000000,
            tipo_contingencia="CONTINGENCIA_ASSISTENCIAL",
            mensagem="Atendimento regularizado com sucesso.",
        )
    )
    mock_checker = AsyncMock(return_value=True)

    app.dependency_overrides[get_fila_service] = lambda: mock_service
    app.dependency_overrides[get_patient_queue_ownership_checker] = lambda: mock_checker

    try:
        token = _make_intake_token(paciente_id, org_id)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/fila/atendimentos/{atendimento_id}/regularizar",
                headers={
                    "X-Tenant-ID": str(org_id),
                    "Authorization": f"Bearer {token}",
                },
                json={
                    "motivo": "Gateway da operadora fora do ar",
                    "tipo_contingencia": "CONTINGENCIA_ASSISTENCIAL",
                },
            )
            assert resp.status_code == 200
            data = cast("dict[str, object]", resp.json())
            assert data["atendimento_id"] == str(atendimento_id)
            assert data["promovido"] is True
            assert data["status"] == "APTO_PARA_CHAMADA"
            assert data["score"] == 3000000000000
            assert data["tipo_contingencia"] == "CONTINGENCIA_ASSISTENCIAL"
            assert data["mensagem"] == "Atendimento regularizado com sucesso."
            mock_service.regularizar_atendimento.assert_awaited_once()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_post_regularizar_sucesso_com_jwt_paciente() -> None:
    """Verifica regularização de atendimento com JWT de paciente autenticado."""
    app = create_app()
    paciente_id = uuid4()
    atendimento_id = uuid4()
    org_id = 42

    mock_service = MagicMock(spec=FilaService)
    mock_service.regularizar_atendimento = AsyncMock(
        return_value=RegularizacaoFilaResult(
            atendimento_id=atendimento_id,
            promovido=True,
            status="APTO_PARA_CHAMADA",
            score=3000000000000,
            tipo_contingencia="CONTINGENCIA_ASSISTENCIAL",
            mensagem="Atendimento regularizado com sucesso.",
        )
    )
    mock_checker = AsyncMock(return_value=True)

    app.dependency_overrides[get_fila_service] = lambda: mock_service
    app.dependency_overrides[get_patient_queue_ownership_checker] = lambda: mock_checker

    try:
        token = _make_jwt_token(paciente_id, org_id, papel="PACIENTE")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/fila/atendimentos/{atendimento_id}/regularizar",
                headers={
                    "X-Tenant-ID": str(org_id),
                    "Authorization": f"Bearer {token}",
                },
                json={
                    "motivo": "Gateway da operadora fora do ar",
                    "tipo_contingencia": "CONTINGENCIA_ASSISTENCIAL",
                },
            )
            assert resp.status_code == 200
            data = cast("dict[str, object]", resp.json())
            assert data["atendimento_id"] == str(atendimento_id)
            assert data["promovido"] is True
            mock_service.regularizar_atendimento.assert_awaited_once()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_post_regularizar_bloqueio_anti_idor_sem_posse() -> None:
    """Verifica bloqueio 403 Forbidden quando token não confere posse sobre
    o atendimento (Anti-IDOR).
    """
    app = create_app()
    paciente_id = uuid4()
    atendimento_id = uuid4()
    org_id = 42

    mock_checker = AsyncMock(return_value=False)
    app.dependency_overrides[get_patient_queue_ownership_checker] = lambda: mock_checker

    try:
        token = _make_intake_token(paciente_id, org_id)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/fila/atendimentos/{atendimento_id}/regularizar",
                headers={
                    "X-Tenant-ID": str(org_id),
                    "Authorization": f"Bearer {token}",
                },
                json={
                    "motivo": "Gateway da operadora fora do ar",
                    "tipo_contingencia": "CONTINGENCIA_ASSISTENCIAL",
                },
            )
            assert resp.status_code == 403
            data = cast("dict[str, object]", resp.json())
            assert data["code"] == "FORBIDDEN"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_post_regularizar_sem_autenticacao_retorna_401() -> None:
    """Verifica retorno 401 Unauthorized na ausência de cabeçalho de autenticação."""
    app = create_app()
    atendimento_id = uuid4()
    org_id = 42

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/fila/atendimentos/{atendimento_id}/regularizar",
                headers={
                    "X-Tenant-ID": str(org_id),
                },
                json={
                    "motivo": "Gateway da operadora fora do ar",
                    "tipo_contingencia": "CONTINGENCIA_ASSISTENCIAL",
                },
            )
            assert resp.status_code == 401
            data = cast("dict[str, object]", resp.json())
            assert data["code"] == "UNAUTHORIZED"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_post_regularizar_conflito_estado_retorna_409() -> None:
    """Verifica retorno 409 Conflict quando atendimento está em estado incompatível."""
    app = create_app()
    paciente_id = uuid4()
    atendimento_id = uuid4()
    org_id = 42

    mock_service = MagicMock(spec=FilaService)
    mock_service.regularizar_atendimento = AsyncMock(
        side_effect=TransicaoEstadoInvalidaError(
            "Não é possível regularizar atendimento no status 'EM_CONSULTA'."
        )
    )
    mock_checker = AsyncMock(return_value=True)

    app.dependency_overrides[get_fila_service] = lambda: mock_service
    app.dependency_overrides[get_patient_queue_ownership_checker] = lambda: mock_checker

    try:
        token = _make_intake_token(paciente_id, org_id)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/fila/atendimentos/{atendimento_id}/regularizar",
                headers={
                    "X-Tenant-ID": str(org_id),
                    "Authorization": f"Bearer {token}",
                },
                json={
                    "motivo": "Gateway da operadora fora do ar",
                    "tipo_contingencia": "CONTINGENCIA_ASSISTENCIAL",
                },
            )
            assert resp.status_code == 409
            data = cast("dict[str, object]", resp.json())
            assert data["code"] == "TRANSICAO_ESTADO_INVALIDA"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_post_regularizar_payload_invalido_retorna_422() -> None:
    """Verifica validação de payload (422) quando motivo for curto demais
    (< 3 caracteres).
    """
    app = create_app()
    paciente_id = uuid4()
    atendimento_id = uuid4()
    org_id = 42

    mock_checker = AsyncMock(return_value=True)
    app.dependency_overrides[get_patient_queue_ownership_checker] = lambda: mock_checker

    try:
        token = _make_intake_token(paciente_id, org_id)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/fila/atendimentos/{atendimento_id}/regularizar",
                headers={
                    "X-Tenant-ID": str(org_id),
                    "Authorization": f"Bearer {token}",
                },
                json={"motivo": "ab"},
            )
            assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()
