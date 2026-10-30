"""Unit tests for TelemetryService and ConfigPlantaoService."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.errors import ValidationError
from src.modules.telemetry.application.dtos import (
    ConfigPlantaoCommand,
    MedicoTMADTO,
    PainelTelemetriaDTO,
)
from src.modules.telemetry.application.ports.config_plantao_port import (
    ConfigPlantaoRepositoryPort,
)
from src.modules.telemetry.application.ports.telemetry_cache_port import (
    TelemetryCachePort,
)
from src.modules.telemetry.application.ports.telemetry_reader_port import (
    TelemetryReaderPort,
)
from src.modules.telemetry.application.services.config_plantao_service import (
    ConfigPlantaoService,
)
from src.modules.telemetry.application.services.telemetry_service import (
    TelemetryService,
)
from src.modules.telemetry.domain.models import ConfiguracaoPlantao


def _sample_painel(org_id: int = 1) -> PainelTelemetriaDTO:
    return PainelTelemetriaDTO(
        organizacao_id=org_id,
        gerado_em=datetime.now(UTC),
        tme_medio_segundos=150.0,
        tme_nivel_1_segundos=0.0,
        tme_nivel_2_segundos=10.0,
        tme_nivel_3_segundos=45.0,
        tme_nivel_4_segundos=90.0,
        tme_nivel_5_segundos=180.0,
        tma_medio_segundos=480.0,
        medicos_tma=(
            MedicoTMADTO(
                medico_id=uuid4(),
                nome="Dr. Teste",
                total_atendimentos=5,
                tma_segundos=480.0,
            ),
        ),
        no_show_rate=3.0,
        evasao_rate=1.0,
        sla_compliance_percentual=98.0,
        sla_em_conformidade=True,
        medicos_ativos_count=2,
        total_pacientes_fila=3,
        total_atendimentos=30,
    )


def _fake_salvar(cfg: ConfiguracaoPlantao) -> ConfiguracaoPlantao:
    return cfg


@pytest.mark.asyncio
async def test_telemetry_service_obter_painel_cache_hit() -> None:
    reader = AsyncMock(spec=TelemetryReaderPort)
    config_repo = AsyncMock(spec=ConfigPlantaoRepositoryPort)
    cache = AsyncMock(spec=TelemetryCachePort)

    cached_painel = _sample_painel(org_id=10)
    cache.obter_painel.return_value = cached_painel

    service = TelemetryService(reader=reader, config_repo=config_repo, cache=cache)
    result = await service.obter_painel(organizacao_id=10, desconsiderar_cache=False)

    assert result == cached_painel
    cache.obter_painel.assert_awaited_once_with(10)
    config_repo.obter_por_organizacao.assert_not_called()
    reader.obter_painel_telemetria.assert_not_called()
    cache.salvar_painel.assert_not_called()


@pytest.mark.asyncio
async def test_telemetry_service_obter_painel_cache_miss() -> None:
    reader = AsyncMock(spec=TelemetryReaderPort)
    config_repo = AsyncMock(spec=ConfigPlantaoRepositoryPort)
    cache = AsyncMock(spec=TelemetryCachePort)

    cache.obter_painel.return_value = None
    config = ConfiguracaoPlantao(organizacao_id=10)
    config_repo.obter_por_organizacao.return_value = config

    fresh_painel = _sample_painel(org_id=10)
    reader.obter_painel_telemetria.return_value = fresh_painel

    service = TelemetryService(reader=reader, config_repo=config_repo, cache=cache)
    result = await service.obter_painel(organizacao_id=10, desconsiderar_cache=False)

    assert result == fresh_painel
    cache.obter_painel.assert_awaited_once_with(10)
    config_repo.obter_por_organizacao.assert_awaited_once_with(10)
    reader.obter_painel_telemetria.assert_awaited_once_with(
        organizacao_id=10,
        config=config,
    )
    cache.salvar_painel.assert_awaited_once_with(
        organizacao_id=10,
        painel=fresh_painel,
        ttl_segundos=5,
    )


@pytest.mark.asyncio
async def test_telemetry_service_obter_painel_desconsiderar_cache() -> None:
    reader = AsyncMock(spec=TelemetryReaderPort)
    config_repo = AsyncMock(spec=ConfigPlantaoRepositoryPort)
    cache = AsyncMock(spec=TelemetryCachePort)

    config = ConfiguracaoPlantao(organizacao_id=10)
    config_repo.obter_por_organizacao.return_value = config
    fresh_painel = _sample_painel(org_id=10)
    reader.obter_painel_telemetria.return_value = fresh_painel

    service = TelemetryService(reader=reader, config_repo=config_repo, cache=cache)
    result = await service.obter_painel(organizacao_id=10, desconsiderar_cache=True)

    assert result == fresh_painel
    cache.obter_painel.assert_not_called()
    config_repo.obter_por_organizacao.assert_awaited_once_with(10)
    reader.obter_painel_telemetria.assert_awaited_once()
    cache.salvar_painel.assert_awaited_once_with(
        organizacao_id=10,
        painel=fresh_painel,
        ttl_segundos=5,
    )


@pytest.mark.asyncio
async def test_telemetry_service_custom_cache_ttl_segundos() -> None:
    reader = AsyncMock(spec=TelemetryReaderPort)
    config_repo = AsyncMock(spec=ConfigPlantaoRepositoryPort)
    cache = AsyncMock(spec=TelemetryCachePort)

    cache.obter_painel.return_value = None
    config = ConfiguracaoPlantao(organizacao_id=10)
    config_repo.obter_por_organizacao.return_value = config

    fresh_painel = _sample_painel(org_id=10)
    reader.obter_painel_telemetria.return_value = fresh_painel

    service = TelemetryService(
        reader=reader,
        config_repo=config_repo,
        cache=cache,
        cache_ttl_segundos=30,
    )
    result = await service.obter_painel(organizacao_id=10)
    assert result == fresh_painel
    cache.salvar_painel.assert_awaited_once_with(
        organizacao_id=10,
        painel=fresh_painel,
        ttl_segundos=30,
    )


@pytest.mark.asyncio
async def test_telemetry_service_obter_painel_usa_defaults_quando_sem_config() -> None:
    reader = AsyncMock(spec=TelemetryReaderPort)
    config_repo = AsyncMock(spec=ConfigPlantaoRepositoryPort)
    cache = AsyncMock(spec=TelemetryCachePort)

    cache.obter_painel.return_value = None
    config_repo.obter_por_organizacao.return_value = None
    fresh_painel = _sample_painel(org_id=25)
    reader.obter_painel_telemetria.return_value = fresh_painel

    service = TelemetryService(reader=reader, config_repo=config_repo, cache=cache)
    result = await service.obter_painel(organizacao_id=25)

    assert result == fresh_painel
    # Reader deve ter sido chamado com a entidade default
    call_kwargs = reader.obter_painel_telemetria.call_args[1]
    assert call_kwargs["organizacao_id"] == 25
    passed_config: ConfiguracaoPlantao = call_kwargs["config"]
    assert passed_config.organizacao_id == 25
    assert passed_config.alpha_backpressure == Decimal("1.25")


@pytest.mark.asyncio
async def test_config_plantao_service_obter_configuracao_existente() -> None:
    repo = AsyncMock(spec=ConfigPlantaoRepositoryPort)
    cache = AsyncMock(spec=TelemetryCachePort)
    session = AsyncMock(spec=AsyncSession)

    config = ConfiguracaoPlantao(organizacao_id=42, medicos_ativos_planejados=3)
    repo.obter_por_organizacao.return_value = config

    service = ConfigPlantaoService(repo=repo, cache=cache, session=session)
    result = await service.obter_configuracao(organizacao_id=42)

    assert isinstance(result, ConfiguracaoPlantao)
    assert result.organizacao_id == 42
    assert result.medicos_ativos_planejados == 3
    repo.salvar.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_config_plantao_service_obter_inexistente_persiste_default() -> None:
    repo = AsyncMock(spec=ConfigPlantaoRepositoryPort)
    cache = AsyncMock(spec=TelemetryCachePort)
    session = AsyncMock(spec=AsyncSession)

    repo.obter_por_organizacao.return_value = None
    repo.salvar.side_effect = _fake_salvar

    service = ConfigPlantaoService(repo=repo, cache=cache, session=session)
    result = await service.obter_configuracao(organizacao_id=99)

    assert isinstance(result, ConfiguracaoPlantao)
    assert result.organizacao_id == 99
    assert result.alpha_backpressure == Decimal("1.25")
    assert result.medicos_ativos_planejados == 1

    repo.salvar.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_config_plantao_service_atualizar_configuracao_existente() -> None:
    repo = AsyncMock(spec=ConfigPlantaoRepositoryPort)
    cache = AsyncMock(spec=TelemetryCachePort)
    session = AsyncMock(spec=AsyncSession)

    config_existente = ConfiguracaoPlantao(organizacao_id=50)
    repo.obter_por_organizacao.return_value = config_existente
    repo.salvar.side_effect = _fake_salvar

    admin_id = uuid4()
    cmd = ConfigPlantaoCommand(
        organizacao_id=50,
        medicos_ativos_planejados=4,
        alpha_backpressure=Decimal("1.28"),
        cota_diaria_maxima=450,
        tma_padrao_segundos=700,
        tempo_tolerancia_ring_segundos=50,
        modo_operacao="PRIVADO",
        sla_minutos_nivel_1=2,
        sla_minutos_nivel_2=12,
        sla_minutos_nivel_3=50,
        sla_minutos_nivel_4=100,
        sla_minutos_nivel_5=200,
        atualizado_por_id=admin_id,
    )

    service = ConfigPlantaoService(repo=repo, cache=cache, session=session)
    result = await service.atualizar_configuracao(cmd)

    assert result.organizacao_id == 50
    assert result.medicos_ativos_planejados == 4
    assert result.alpha_backpressure == Decimal("1.28")
    assert result.modo_operacao == "PRIVADO"
    assert result.atualizado_por_id == admin_id

    repo.salvar.assert_awaited_once_with(config_existente)
    cache.invalidar_painel.assert_awaited_once_with(50)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_config_plantao_service_atualizar_cria_nova_se_inexistente() -> None:
    repo = AsyncMock(spec=ConfigPlantaoRepositoryPort)
    cache = AsyncMock(spec=TelemetryCachePort)
    session = AsyncMock(spec=AsyncSession)

    repo.obter_por_organizacao.return_value = None
    repo.salvar.side_effect = _fake_salvar

    cmd = ConfigPlantaoCommand(
        organizacao_id=60,
        medicos_ativos_planejados=2,
        alpha_backpressure=Decimal("1.22"),
        modo_operacao="SUS",
    )

    service = ConfigPlantaoService(repo=repo, cache=cache, session=session)
    result = await service.atualizar_configuracao(cmd)

    assert result.organizacao_id == 60
    assert result.medicos_ativos_planejados == 2
    assert result.alpha_backpressure == Decimal("1.22")

    repo.salvar.assert_awaited_once()
    cache.invalidar_painel.assert_awaited_once_with(60)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_config_plantao_service_atualizar_invariante_invalida_nao_commita() -> (
    None
):
    repo = AsyncMock(spec=ConfigPlantaoRepositoryPort)
    cache = AsyncMock(spec=TelemetryCachePort)
    session = AsyncMock(spec=AsyncSession)

    config_existente = ConfiguracaoPlantao(organizacao_id=70)
    repo.obter_por_organizacao.return_value = config_existente

    # alpha fora da faixa 1.20 - 1.30
    cmd = ConfigPlantaoCommand(
        organizacao_id=70,
        medicos_ativos_planejados=2,
        alpha_backpressure=Decimal("1.50"),
    )

    service = ConfigPlantaoService(repo=repo, cache=cache, session=session)
    with pytest.raises(ValidationError, match="alpha_backpressure inválido"):
        await service.atualizar_configuracao(cmd)

    repo.salvar.assert_not_called()
    cache.invalidar_painel.assert_not_called()
    session.commit.assert_not_called()
