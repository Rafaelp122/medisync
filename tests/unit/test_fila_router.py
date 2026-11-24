"""Unit tests for patient queue router (position, cancel, deterioration)."""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from src.core.authz.token import create_access_token
from src.core.config import get_settings
from src.core.errors import NotFoundError
from src.core.security import create_intake_token
from src.main import create_app
from src.modules.queue.application.dtos import (
    AdmissaoAtendimentoResult,
    CancelarAtendimentoResult,
    PioraClinicaResult,
    PosicaoFilaResult,
    RegularizacaoFilaResult,
)
from src.modules.queue.composition import (
    get_fila_service,
    get_patient_queue_ownership_checker,
)
from src.modules.queue.domain.exceptions import TransicaoEstadoInvalidaError

from tests.doubles import FakeFilaService


async def _allow_ownership(_atendimento_id: UUID, _paciente_id: UUID) -> bool:
    return True


async def _deny_ownership(_atendimento_id: UUID, _paciente_id: UUID) -> bool:
    return False


def _make_intake_token(paciente_id: UUID) -> str:
    settings = get_settings()
    return create_intake_token(paciente_id, settings.SECRET_KEY)


def _make_jwt_token(user_id: UUID, papel: str = "PACIENTE") -> str:
    return create_access_token(usuario_id=user_id, papel=papel)


@pytest.mark.asyncio
async def test_obter_posicao_sucesso_com_token_intake() -> None:
    """Verifica consulta de posição ordinal com token provisório de intake."""
    app = create_app()
    paciente_id = uuid4()
    atendimento_id = uuid4()

    chamada_em = datetime.now(UTC)
    fake_service = FakeFilaService(
        posicao_result=PosicaoFilaResult(
            atendimento_id=atendimento_id,
            status="CHAMANDO_PACIENTE",
            posicao=0,
            total_aguardando=5,
            tempo_estimado_segundos=0,
            prioridade_clinica=2,
            chamada_iniciada_em=chamada_em,
            ttl_segundos=45,
        )
    )

    app.dependency_overrides[get_fila_service] = lambda: fake_service
    app.dependency_overrides[get_patient_queue_ownership_checker] = lambda: (
        _allow_ownership
    )

    try:
        token = _make_intake_token(paciente_id)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/api/v1/fila/posicao/{atendimento_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            data = cast("dict[str, object]", resp.json())
            assert data["atendimento_id"] == str(atendimento_id)
            assert data["posicao"] == 0
            assert data["total_aguardando"] == 5
            assert data["tempo_estimado_segundos"] == 0
            assert data["prioridade_clinica"] == 2
            assert data["chamada_iniciada_em"] is not None
            assert data["ttl_segundos"] == 45
            assert fake_service.posicao_calls == [atendimento_id]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_obter_posicao_rejeitada_sem_posse_idor() -> None:
    """Verifica bloqueio 403 Forbidden quando o token não possui posse (Anti-IDOR)."""
    app = create_app()
    paciente_id = uuid4()
    atendimento_id = uuid4()

    app.dependency_overrides[get_patient_queue_ownership_checker] = lambda: (
        _deny_ownership
    )

    try:
        token = _make_intake_token(paciente_id)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/api/v1/fila/posicao/{atendimento_id}",
                headers={"Authorization": f"Bearer {token}"},
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

    fake_service = FakeFilaService(
        posicao_result=NotFoundError("Atendimento não encontrado.")
    )

    app.dependency_overrides[get_fila_service] = lambda: fake_service
    app.dependency_overrides[get_patient_queue_ownership_checker] = lambda: (
        _allow_ownership
    )

    try:
        token = _make_intake_token(paciente_id)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/api/v1/fila/posicao/{atendimento_id}",
                headers={"Authorization": f"Bearer {token}"},
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

    now = datetime.now(UTC)
    fake_service = FakeFilaService(
        cancelar_result=CancelarAtendimentoResult(
            atendimento_id=atendimento_id,
            status="CANCELADO",
            cancelado_em=now,
            motivo="Melhora espontânea dos sintomas",
        )
    )

    app.dependency_overrides[get_fila_service] = lambda: fake_service
    app.dependency_overrides[get_patient_queue_ownership_checker] = lambda: (
        _allow_ownership
    )

    try:
        token = _make_jwt_token(paciente_id, papel="PACIENTE")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/fila/cancelar/{atendimento_id}",
                headers={"Authorization": f"Bearer {token}"},
                json={"motivo": "Melhora espontânea dos sintomas"},
            )
            assert resp.status_code == 200
            data = cast("dict[str, object]", resp.json())
            assert data["atendimento_id"] == str(atendimento_id)
            assert data["status"] == "CANCELADO"
            assert data["motivo"] == "Melhora espontânea dos sintomas"
            assert fake_service.cancelar_calls == [
                (atendimento_id, "Melhora espontânea dos sintomas")
            ]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_comunicar_piora_clinica_reclassificacao_sucesso() -> None:
    """Verifica comunicação de piora clínica e reclassificação na fila (RF-06)."""
    app = create_app()
    paciente_id = uuid4()
    atendimento_id = uuid4()

    fake_service = FakeFilaService(
        piora_result=PioraClinicaResult(
            atendimento_id=atendimento_id,
            prioridade_clinica=2,
            alerta_samu_disparado=False,
            redirecionado_emergencia=False,
            nova_posicao=1,
            instrucoes="Prioridade atualizada para Laranja.",
        )
    )

    app.dependency_overrides[get_fila_service] = lambda: fake_service
    app.dependency_overrides[get_patient_queue_ownership_checker] = lambda: (
        _allow_ownership
    )

    try:
        token = _make_jwt_token(paciente_id, papel="PACIENTE")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/fila/piora",
                headers={"Authorization": f"Bearer {token}"},
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
            assert "nova_prioridade" not in data
            assert data["alerta_samu_disparado"] is False
            assert data["redirecionado_emergencia"] is False
            assert data["nova_posicao"] == 1
            assert len(fake_service.piora_calls) == 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_comunicar_piora_clinica_emergencia_samu() -> None:
    """Verifica salvaguarda de emergência imediata (Vermelho) com alerta SAMU."""
    app = create_app()
    paciente_id = uuid4()
    atendimento_id = uuid4()

    fake_service = FakeFilaService(
        piora_result=PioraClinicaResult(
            atendimento_id=atendimento_id,
            prioridade_clinica=1,
            alerta_samu_disparado=True,
            redirecionado_emergencia=True,
            nova_posicao=None,
            instrucoes="Emergência detectada. SAMU 192 notificado imediatamente.",
            status_atendimento="CANCELADO_PACIENTE",
        )
    )

    app.dependency_overrides[get_fila_service] = lambda: fake_service
    app.dependency_overrides[get_patient_queue_ownership_checker] = lambda: (
        _allow_ownership
    )

    try:
        token = _make_intake_token(paciente_id)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/fila/piora",
                headers={"Authorization": f"Bearer {token}"},
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
            assert data["status_atendimento"] == "CANCELADO_PACIENTE"
            assert data["alerta_samu_disparado"] is True
            assert data["redirecionado_emergencia"] is True
            assert data["nova_posicao"] is None
            assert (
                data["instrucoes"]
                == "Emergência detectada. SAMU 192 notificado imediatamente."
            )
            assert "nova_prioridade" not in data
            assert "orientacoes_emergencia" not in data
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admissao_paciente_unificada_no_fila_router() -> None:
    """Verifica admissão de paciente via endpoint unificado da fila (/fila/admissao)."""
    app = create_app()
    paciente_id = uuid4()
    atendimento_id = uuid4()
    triagem_id = uuid4()

    fake_service = FakeFilaService(
        admitir_result=AdmissaoAtendimentoResult(
            atendimento_id=atendimento_id,
            triagem_id=triagem_id,
            paciente_id=paciente_id,
            status_atendimento="APTO_PARA_CHAMADA",
            prioridade_clinica=3,
            alerta_samu_disparado=False,
            instrucoes=None,
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
            assert data["status_atendimento"] == "APTO_PARA_CHAMADA"
            assert data["prioridade_clinica"] == 3
            assert len(fake_service.admitir_calls) == 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_post_regularizar_sucesso_com_token_intake() -> None:
    """Verifica regularização de atendimento na fila com token de intake (US-05)."""
    app = create_app()
    paciente_id = uuid4()
    atendimento_id = uuid4()

    fake_service = FakeFilaService(
        regularizar_result=RegularizacaoFilaResult(
            atendimento_id=atendimento_id,
            promovido=True,
            status="APTO_PARA_CHAMADA",
            score=3000000000000,
            tipo_contingencia="CONTINGENCIA_ASSISTENCIAL",
            mensagem="Atendimento regularizado com sucesso.",
        )
    )

    app.dependency_overrides[get_fila_service] = lambda: fake_service
    app.dependency_overrides[get_patient_queue_ownership_checker] = lambda: (
        _allow_ownership
    )

    try:
        token = _make_intake_token(paciente_id)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/fila/atendimentos/{atendimento_id}/regularizar",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "motivo": "Serviço CADSUS temporariamente indisponível",
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
            assert len(fake_service.regularizar_calls) == 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_post_regularizar_sucesso_com_jwt_paciente() -> None:
    """Verifica regularização de atendimento com JWT de paciente autenticado."""
    app = create_app()
    paciente_id = uuid4()
    atendimento_id = uuid4()

    fake_service = FakeFilaService(
        regularizar_result=RegularizacaoFilaResult(
            atendimento_id=atendimento_id,
            promovido=True,
            status="APTO_PARA_CHAMADA",
            score=3000000000000,
            tipo_contingencia="CONTINGENCIA_ASSISTENCIAL",
            mensagem="Atendimento regularizado com sucesso.",
        )
    )

    app.dependency_overrides[get_fila_service] = lambda: fake_service
    app.dependency_overrides[get_patient_queue_ownership_checker] = lambda: (
        _allow_ownership
    )

    try:
        token = _make_jwt_token(paciente_id, papel="PACIENTE")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/fila/atendimentos/{atendimento_id}/regularizar",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "motivo": "Serviço CADSUS temporariamente indisponível",
                    "tipo_contingencia": "CONTINGENCIA_ASSISTENCIAL",
                },
            )
            assert resp.status_code == 200
            data = cast("dict[str, object]", resp.json())
            assert data["atendimento_id"] == str(atendimento_id)
            assert data["promovido"] is True
            assert len(fake_service.regularizar_calls) == 1
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

    app.dependency_overrides[get_patient_queue_ownership_checker] = lambda: (
        _deny_ownership
    )

    try:
        token = _make_intake_token(paciente_id)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/fila/atendimentos/{atendimento_id}/regularizar",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "motivo": "Serviço CADSUS temporariamente indisponível",
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

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/fila/atendimentos/{atendimento_id}/regularizar",
                json={
                    "motivo": "Serviço CADSUS temporariamente indisponível",
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

    fake_service = FakeFilaService(
        regularizar_result=TransicaoEstadoInvalidaError(
            "Não é possível regularizar atendimento no status 'EM_CONSULTA'."
        )
    )

    app.dependency_overrides[get_fila_service] = lambda: fake_service
    app.dependency_overrides[get_patient_queue_ownership_checker] = lambda: (
        _allow_ownership
    )

    try:
        token = _make_intake_token(paciente_id)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/fila/atendimentos/{atendimento_id}/regularizar",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "motivo": "Serviço CADSUS temporariamente indisponível",
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

    app.dependency_overrides[get_patient_queue_ownership_checker] = lambda: (
        _allow_ownership
    )

    try:
        token = _make_intake_token(paciente_id)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/v1/fila/atendimentos/{atendimento_id}/regularizar",
                headers={"Authorization": f"Bearer {token}"},
                json={"motivo": "ab"},
            )
            assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()
