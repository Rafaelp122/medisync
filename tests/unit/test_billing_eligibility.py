"""Unit tests for billing eligibility adapters and service (RF-02, RF-05, RT-01)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from src.modules.billing import (
    ElegibilidadeFalhaEvent,
    ElegibilidadeNotifierPort,
    ElegibilidadeService,
    LoggingElegibilidadeNotifier,
    PrivateInsuranceGatewayAdapter,
    RequisicaoElegibilidade,
    StatusElegibilidade,
    SusEligibilityAdapter,
)


@pytest.mark.asyncio
async def test_sus_adapter_instant_no_op_approval() -> None:
    """SUS adapter immediately approves attendance without network latency (RT-01)."""
    adapter = SusEligibilityAdapter()
    req = RequisicaoElegibilidade(
        organizacao_id=1,
        atendimento_id=uuid4(),
        paciente_id=uuid4(),
        cpf="12345678901",
    )

    resultado = await adapter.verificar_elegibilidade(req)

    assert resultado.aprovado is True
    assert resultado.status == StatusElegibilidade.APROVADO
    assert resultado.codigo_autorizacao == "SUS-ISENTO"
    assert resultado.motivo is None


@pytest.mark.asyncio
async def test_private_gateway_adapter_approved() -> None:
    """Private gateway approves when operator returns 200 with aprovado=True."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "aprovado": True,
        "codigo_autorizacao": "AUTH-UNIMED-998",
    }
    mock_client.post.return_value = mock_response

    adapter = PrivateInsuranceGatewayAdapter(client=mock_client)
    req = RequisicaoElegibilidade(
        organizacao_id=2,
        atendimento_id=uuid4(),
        paciente_id=uuid4(),
        cpf="98765432100",
        operadora_id="UNIMED",
        numero_carteirinha="0011223344",
    )

    resultado = await adapter.verificar_elegibilidade(req)

    assert resultado.aprovado is True
    assert resultado.status == StatusElegibilidade.APROVADO
    assert resultado.codigo_autorizacao == "AUTH-UNIMED-998"


@pytest.mark.asyncio
async def test_private_gateway_adapter_rejected() -> None:
    """Private gateway records rejection reason from operator payload."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "aprovado": False,
        "motivo": "Carência não cumprida para teleconsulta",
    }
    mock_client.post.return_value = mock_response

    adapter = PrivateInsuranceGatewayAdapter(client=mock_client)
    req = RequisicaoElegibilidade(
        organizacao_id=2,
        atendimento_id=uuid4(),
        paciente_id=uuid4(),
        cpf="98765432100",
        operadora_id="BRADESCO",
        numero_carteirinha="99887766",
    )

    resultado = await adapter.verificar_elegibilidade(req)

    assert resultado.aprovado is False
    assert resultado.status == StatusElegibilidade.REJEITADO
    assert "Carência não cumprida" in (resultado.motivo or "")


@pytest.mark.asyncio
async def test_private_gateway_adapter_timeout_15s() -> None:
    """Private gateway handles timeout exception and returns TIMEOUT status (RF-02)."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = httpx.TimeoutException("Read timed out")

    adapter = PrivateInsuranceGatewayAdapter(timeout_segundos=15.0, client=mock_client)
    req = RequisicaoElegibilidade(
        organizacao_id=2,
        atendimento_id=uuid4(),
        paciente_id=uuid4(),
        cpf="98765432100",
    )

    resultado = await adapter.verificar_elegibilidade(req)

    assert resultado.aprovado is False
    assert resultado.status == StatusElegibilidade.TIMEOUT
    assert "15s excedido" in (resultado.motivo or "")


@pytest.mark.asyncio
async def test_private_gateway_adapter_http_error() -> None:
    """Private gateway handles non-200 operator status code."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 502
    mock_response.text = "Bad Gateway"
    mock_client.post.return_value = mock_response

    adapter = PrivateInsuranceGatewayAdapter(client=mock_client)
    req = RequisicaoElegibilidade(
        organizacao_id=2,
        atendimento_id=uuid4(),
        paciente_id=uuid4(),
    )

    resultado = await adapter.verificar_elegibilidade(req)

    assert resultado.aprovado is False
    assert resultado.status == StatusElegibilidade.REJEITADO
    assert "502" in (resultado.motivo or "")


@pytest.mark.asyncio
async def test_elegibilidade_service_emits_failure_event_on_rejection() -> None:
    """ElegibilidadeService dispatches failure event to waiting room on rejection."""
    mock_provider = AsyncMock()
    mock_provider.verificar_elegibilidade.return_value = MagicMock(
        aprovado=False,
        status=StatusElegibilidade.REJEITADO,
        motivo="Plano suspenso",
    )
    mock_notifier = AsyncMock(spec=ElegibilidadeNotifierPort)

    service = ElegibilidadeService(
        provider=mock_provider,
        notifier=mock_notifier,
    )
    atend_id = uuid4()
    pac_id = uuid4()
    req = RequisicaoElegibilidade(
        organizacao_id=1,
        atendimento_id=atend_id,
        paciente_id=pac_id,
    )

    resultado = await service.avaliar_elegibilidade(req)

    assert resultado.aprovado is False
    mock_notifier.notificar_falha.assert_awaited_once()
    evento: ElegibilidadeFalhaEvent = mock_notifier.notificar_falha.call_args[0][0]
    assert evento.atendimento_id == atend_id
    assert evento.paciente_id == pac_id
    assert evento.motivo == "Plano suspenso"
    assert evento.status == StatusElegibilidade.REJEITADO


@pytest.mark.asyncio
async def test_elegibilidade_service_does_not_notify_on_approval() -> None:
    """ElegibilidadeService does not dispatch failure event when approved."""
    mock_provider = AsyncMock()
    mock_provider.verificar_elegibilidade.return_value = MagicMock(
        aprovado=True,
        status=StatusElegibilidade.APROVADO,
        codigo_autorizacao="AUTH-OK",
    )
    mock_notifier = AsyncMock(spec=ElegibilidadeNotifierPort)

    service = ElegibilidadeService(
        provider=mock_provider,
        notifier=mock_notifier,
    )
    req = RequisicaoElegibilidade(
        organizacao_id=1,
        atendimento_id=uuid4(),
        paciente_id=uuid4(),
    )

    resultado = await service.avaliar_elegibilidade(req)

    assert resultado.aprovado is True
    mock_notifier.notificar_falha.assert_not_awaited()


@pytest.mark.asyncio
async def test_logging_elegibilidade_notifier() -> None:
    """LoggingElegibilidadeNotifier logs structured warning."""
    notifier = LoggingElegibilidadeNotifier()
    evento = ElegibilidadeFalhaEvent(
        atendimento_id=uuid4(),
        organizacao_id=1,
        paciente_id=uuid4(),
        motivo="Cartão vencido",
        status=StatusElegibilidade.REJEITADO,
        disparado_em=datetime.now(UTC),
    )
    with patch(
        "src.modules.billing.application.ports.eligibility_notifier.logger.warning"
    ) as mock_log:
        await notifier.notificar_falha(evento)

    mock_log.assert_called_once()
    assert "Event ELEGIBILIDADE_FALHA" in str(mock_log.call_args[0][0])
