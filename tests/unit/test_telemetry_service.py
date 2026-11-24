"""Unit tests for TelemetryService and ConfigPlantaoService using canonical Fakes."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import uuid4

import pytest
from src.core.errors import ValidationError
from src.modules.telemetry.application.dtos import (
    MedicoTMADTO,
    PainelTelemetriaDTO,
)
from src.modules.telemetry.application.services.config_plantao_service import (
    ConfigPlantaoService,
)
from src.modules.telemetry.application.services.telemetry_service import (
    TelemetryService,
)
from src.modules.telemetry.domain.models import ConfiguracaoPlantao
from src.modules.telemetry.presentation.schemas import ConfigPlantaoRequest

from tests.doubles import (
    FakeAsyncSession,
    FakeConfigPlantaoRepository,
    FakeTelemetryCache,
    FakeTelemetryReader,
)


def _sample_painel() -> PainelTelemetriaDTO:
    return PainelTelemetriaDTO(
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


def _sample_request(
    *,
    medicos_ativos_planejados: int = 4,
    alpha_backpressure: Decimal = Decimal("1.28"),
    cota_diaria_maxima: int | None = 450,
    tma_padrao_segundos: int = 700,
    tempo_tolerancia_ring_segundos: int = 50,
    modo_operacao: Literal["SUS", "PRIVADO"] = "PRIVADO",
    sla_minutos_nivel_1: int = 2,
    sla_minutos_nivel_2: int = 12,
    sla_minutos_nivel_3: int = 50,
    sla_minutos_nivel_4: int = 100,
    sla_minutos_nivel_5: int = 200,
) -> ConfigPlantaoRequest:
    return ConfigPlantaoRequest(
        medicos_ativos_planejados=medicos_ativos_planejados,
        alpha_backpressure=alpha_backpressure,
        cota_diaria_maxima=cota_diaria_maxima,
        tma_padrao_segundos=tma_padrao_segundos,
        tempo_tolerancia_ring_segundos=tempo_tolerancia_ring_segundos,
        modo_operacao=modo_operacao,
        sla_minutos_nivel_1=sla_minutos_nivel_1,
        sla_minutos_nivel_2=sla_minutos_nivel_2,
        sla_minutos_nivel_3=sla_minutos_nivel_3,
        sla_minutos_nivel_4=sla_minutos_nivel_4,
        sla_minutos_nivel_5=sla_minutos_nivel_5,
    )


@pytest.mark.asyncio
async def test_telemetry_service_obter_painel_cache_hit() -> None:
    cached_painel = _sample_painel()
    reader = FakeTelemetryReader()
    config_repo = FakeConfigPlantaoRepository()
    cache = FakeTelemetryCache(initial=cached_painel)

    service = TelemetryService(reader=reader, config_repo=config_repo, cache=cache)
    result = await service.obter_painel(desconsiderar_cache=False)

    assert result == cached_painel
    assert cache.obter_calls == 1
    assert config_repo.obter_atual_calls == 0
    assert reader.calls == []
    assert cache.salvar_calls == []


@pytest.mark.asyncio
async def test_telemetry_service_obter_painel_cache_miss() -> None:
    fresh_painel = _sample_painel()
    config = ConfiguracaoPlantao()
    reader = FakeTelemetryReader(painel=fresh_painel)
    config_repo = FakeConfigPlantaoRepository(config=config)
    cache = FakeTelemetryCache()

    service = TelemetryService(reader=reader, config_repo=config_repo, cache=cache)
    result = await service.obter_painel(desconsiderar_cache=False)

    assert result == fresh_painel
    assert cache.obter_calls == 1
    assert config_repo.obter_atual_calls == 1
    assert len(reader.calls) == 1
    assert reader.calls[0]["config"] is config
    assert cache.salvar_calls == [(fresh_painel, 5)]


@pytest.mark.asyncio
async def test_telemetry_service_obter_painel_desconsiderar_cache() -> None:
    fresh_painel = _sample_painel()
    config = ConfiguracaoPlantao()
    reader = FakeTelemetryReader(painel=fresh_painel)
    config_repo = FakeConfigPlantaoRepository(config=config)
    cache = FakeTelemetryCache(initial=_sample_painel())

    service = TelemetryService(reader=reader, config_repo=config_repo, cache=cache)
    result = await service.obter_painel(desconsiderar_cache=True)

    assert result == fresh_painel
    assert cache.obter_calls == 0
    assert config_repo.obter_atual_calls == 1
    assert len(reader.calls) == 1
    assert cache.salvar_calls == [(fresh_painel, 5)]


@pytest.mark.asyncio
async def test_telemetry_service_custom_cache_ttl_segundos() -> None:
    fresh_painel = _sample_painel()
    reader = FakeTelemetryReader(painel=fresh_painel)
    config_repo = FakeConfigPlantaoRepository(config=ConfiguracaoPlantao())
    cache = FakeTelemetryCache()

    service = TelemetryService(
        reader=reader,
        config_repo=config_repo,
        cache=cache,
        cache_ttl_segundos=30,
    )
    result = await service.obter_painel()

    assert result == fresh_painel
    assert cache.salvar_calls == [(fresh_painel, 30)]


@pytest.mark.asyncio
async def test_telemetry_service_obter_painel_usa_defaults_quando_sem_config() -> None:
    fresh_painel = _sample_painel()
    reader = FakeTelemetryReader(painel=fresh_painel)
    config_repo = FakeConfigPlantaoRepository(config=None)
    cache = FakeTelemetryCache()

    service = TelemetryService(reader=reader, config_repo=config_repo, cache=cache)
    result = await service.obter_painel()

    assert result == fresh_painel
    passed_config = reader.calls[0]["config"]
    assert isinstance(passed_config, ConfiguracaoPlantao)
    assert passed_config.singleton_guard is True
    assert passed_config.alpha_backpressure == Decimal("1.25")


@pytest.mark.asyncio
async def test_config_plantao_service_obter_configuracao_existente() -> None:
    config = ConfiguracaoPlantao(medicos_ativos_planejados=3)
    repo = FakeConfigPlantaoRepository(config=config)
    cache = FakeTelemetryCache()
    session = FakeAsyncSession()

    service = ConfigPlantaoService(
        repo=repo,
        cache=cache,
        session=session,  # pyright: ignore[reportArgumentType]
    )
    result = await service.obter_configuracao()

    assert result is config
    assert result.medicos_ativos_planejados == 3
    assert repo.obter_ou_criar_calls == 0
    assert repo.salvos == []
    assert session.commits == 0


@pytest.mark.asyncio
async def test_config_plantao_service_obter_inexistente_provisiona_atomico() -> None:
    repo = FakeConfigPlantaoRepository(config=None)
    cache = FakeTelemetryCache()
    session = FakeAsyncSession()

    service = ConfigPlantaoService(
        repo=repo,
        cache=cache,
        session=session,  # pyright: ignore[reportArgumentType]
    )
    result = await service.obter_configuracao()

    assert isinstance(result, ConfiguracaoPlantao)
    assert result.singleton_guard is True
    assert result.alpha_backpressure == Decimal("1.25")
    assert result.medicos_ativos_planejados == 1
    assert repo.obter_ou_criar_calls == 1
    assert session.commits == 1


@pytest.mark.asyncio
async def test_config_plantao_service_atualizar_configuracao_existente() -> None:
    config_existente = ConfiguracaoPlantao()
    repo = FakeConfigPlantaoRepository(config=config_existente)
    cache = FakeTelemetryCache(initial=_sample_painel())
    session = FakeAsyncSession()

    admin_id = uuid4()
    req = _sample_request()

    service = ConfigPlantaoService(
        repo=repo,
        cache=cache,
        session=session,  # pyright: ignore[reportArgumentType]
    )
    result = await service.atualizar_configuracao(req, atualizado_por_id=admin_id)

    assert result is config_existente
    assert result.medicos_ativos_planejados == 4
    assert result.alpha_backpressure == Decimal("1.28")
    assert result.modo_operacao == "PRIVADO"
    assert result.atualizado_por_id == admin_id
    assert repo.obter_ou_criar_calls == 1
    assert repo.salvos == [config_existente]
    assert cache.invalidar_calls == 1
    assert cache.painel is None
    assert session.commits == 1


@pytest.mark.asyncio
async def test_config_plantao_service_atualizar_cria_nova_se_inexistente() -> None:
    repo = FakeConfigPlantaoRepository(config=None)
    cache = FakeTelemetryCache()
    session = FakeAsyncSession()

    req = _sample_request(
        medicos_ativos_planejados=2,
        alpha_backpressure=Decimal("1.22"),
        modo_operacao="SUS",
    )

    service = ConfigPlantaoService(
        repo=repo,
        cache=cache,
        session=session,  # pyright: ignore[reportArgumentType]
    )
    result = await service.atualizar_configuracao(req)

    assert result.medicos_ativos_planejados == 2
    assert result.alpha_backpressure == Decimal("1.22")
    assert result.modo_operacao == "SUS"
    assert repo.obter_ou_criar_calls == 1
    assert len(repo.salvos) == 1
    assert cache.invalidar_calls == 1
    assert session.commits == 1


@pytest.mark.asyncio
async def test_config_plantao_service_atualizar_invariante_invalida_nao_commita() -> (
    None
):
    config_existente = ConfiguracaoPlantao()
    repo = FakeConfigPlantaoRepository(config=config_existente)
    cache = FakeTelemetryCache(initial=_sample_painel())
    session = FakeAsyncSession()

    req_invalida = ConfigPlantaoRequest.model_construct(
        medicos_ativos_planejados=2,
        alpha_backpressure=Decimal("1.50"),
        cota_diaria_maxima=300,
        tma_padrao_segundos=600,
        tempo_tolerancia_ring_segundos=45,
        modo_operacao="SUS",
        sla_minutos_nivel_1=0,
        sla_minutos_nivel_2=10,
        sla_minutos_nivel_3=60,
        sla_minutos_nivel_4=120,
        sla_minutos_nivel_5=240,
    )

    service = ConfigPlantaoService(
        repo=repo,
        cache=cache,
        session=session,  # pyright: ignore[reportArgumentType]
    )
    with pytest.raises(ValidationError, match="alpha_backpressure inválido"):
        await service.atualizar_configuracao(req_invalida)

    assert repo.obter_ou_criar_calls == 0
    assert repo.salvos == []
    assert cache.invalidar_calls == 0
    assert session.commits == 0
