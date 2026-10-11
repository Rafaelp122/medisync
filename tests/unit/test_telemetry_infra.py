"""Unit tests for telemetry infrastructure adapters (repository, reader, cache)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.modules.telemetry.application.dtos import (
    MedicoTMADTO,
    PainelTelemetriaDTO,
)
from src.modules.telemetry.domain.models import ConfiguracaoPlantao
from src.modules.telemetry.infrastructure.config_plantao_repository import (
    SqlConfigPlantaoRepository,
)
from src.modules.telemetry.infrastructure.telemetry_reader_sql import (
    SqlTelemetryReader,
)
from src.modules.telemetry.infrastructure.valkey_telemetry_cache import (
    MemoryTelemetryCache,
    ValkeyTelemetryCache,
)


@pytest.mark.asyncio
async def test_sql_config_plantao_repository_salvar_e_obter() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.add = MagicMock()
    session.flush = AsyncMock()

    repo = SqlConfigPlantaoRepository(session)
    config = ConfiguracaoPlantao(organizacao_id=123)

    # Test salvar
    salvo = await repo.salvar(config)
    assert salvo.organizacao_id == 123
    session.add.assert_called_once_with(config)
    session.flush.assert_awaited_once()

    # Test obter_por_organizacao
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = config
    session.execute.return_value = mock_result

    obtido = await repo.obter_por_organizacao(123)
    assert obtido is not None
    assert obtido.organizacao_id == 123
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_sql_telemetry_reader_obter_painel() -> None:
    session = AsyncMock(spec=AsyncSession)

    medico_id = uuid4()
    mock_agregados_row = {
        "total_atendimentos": 20,
        "total_ausentes": 2,
        "total_cancelados": 1,
        "total_chamados": 15,
        "total_dentro_sla": 15,
        "tme_medio": 180.5,
        "tme_nivel_1": 0.0,
        "tme_nivel_2": 30.0,
        "tme_nivel_3": 120.0,
        "tme_nivel_4": 200.0,
        "tme_nivel_5": 300.0,
        "tma_medio": 450.2,
    }

    mock_medicos_rows = [
        {
            "medico_id": medico_id,
            "nome": "Dr. House",
            "total_atendimentos": 10,
            "tma_segundos": 420.0,
        }
    ]

    # Mock execute returns depending on call
    res_agregados = MagicMock()
    res_agregados.mappings.return_value.one_or_none.return_value = mock_agregados_row

    res_medicos = MagicMock()
    res_medicos.mappings.return_value.all.return_value = mock_medicos_rows

    res_fila = MagicMock()
    res_fila.scalar.return_value = 5

    res_medicos_ativos = MagicMock()
    res_medicos_ativos.scalar.return_value = 3

    session.execute.side_effect = [
        res_agregados,
        res_medicos,
        res_fila,
        res_medicos_ativos,
    ]

    reader = SqlTelemetryReader(session)
    config = ConfiguracaoPlantao(organizacao_id=1)

    painel = await reader.obter_painel_telemetria(organizacao_id=1, config=config)

    assert painel.organizacao_id == 1
    assert painel.total_atendimentos == 20
    assert painel.no_show_rate == 10.0  # 2 / 20 = 10%
    assert painel.evasao_rate == 5.0  # 1 / 20 = 5%
    assert painel.sla_compliance_percentual == 100.0  # 15 / 15 = 100%
    assert painel.sla_em_conformidade is True
    assert painel.total_pacientes_fila == 5
    assert painel.medicos_ativos_count == 3
    assert len(painel.medicos_tma) == 1
    assert painel.medicos_tma[0].medico_id == medico_id
    assert painel.medicos_tma[0].nome == "Dr. House"


@pytest.mark.asyncio
async def test_memory_telemetry_cache_lifecycle() -> None:
    cache = MemoryTelemetryCache()

    painel = PainelTelemetriaDTO(
        organizacao_id=99,
        gerado_em=datetime.now(UTC),
        tme_medio_segundos=120.0,
        tme_nivel_1_segundos=0.0,
        tme_nivel_2_segundos=10.0,
        tme_nivel_3_segundos=60.0,
        tme_nivel_4_segundos=120.0,
        tme_nivel_5_segundos=240.0,
        tma_medio_segundos=600.0,
        medicos_tma=(),
        no_show_rate=2.5,
        evasao_rate=1.0,
        sla_compliance_percentual=96.5,
        sla_em_conformidade=True,
        medicos_ativos_count=2,
        total_pacientes_fila=3,
        total_atendimentos=50,
    )

    # Initial get: miss
    assert await cache.obter_painel(99) is None

    # Save
    await cache.salvar_painel(99, painel, ttl_segundos=60)

    # Get: hit
    cached = await cache.obter_painel(99)
    assert cached is not None
    assert cached.organizacao_id == 99
    assert cached.sla_compliance_percentual == 96.5
    assert cached.sla_em_conformidade is True

    # Invalidate
    await cache.invalidar_painel(99)
    assert await cache.obter_painel(99) is None


@pytest.mark.asyncio
async def test_valkey_telemetry_cache_mocked() -> None:
    mock_redis = AsyncMock()
    cache = ValkeyTelemetryCache(mock_redis)

    med_id = uuid4()
    painel = PainelTelemetriaDTO(
        organizacao_id=77,
        gerado_em=datetime.now(UTC),
        tme_medio_segundos=100.0,
        tme_nivel_1_segundos=0.0,
        tme_nivel_2_segundos=5.0,
        tme_nivel_3_segundos=50.0,
        tme_nivel_4_segundos=100.0,
        tme_nivel_5_segundos=200.0,
        tma_medio_segundos=500.0,
        medicos_tma=(
            MedicoTMADTO(
                medico_id=med_id,
                nome="Dra. Santos",
                total_atendimentos=12,
                tma_segundos=480.0,
            ),
        ),
        no_show_rate=4.0,
        evasao_rate=2.0,
        sla_compliance_percentual=94.0,
        sla_em_conformidade=False,
        medicos_ativos_count=4,
        total_pacientes_fila=8,
        total_atendimentos=80,
    )

    # Test salvar
    await cache.salvar_painel(77, painel, ttl_segundos=30)
    mock_redis.set.assert_awaited_once()
    call_args = mock_redis.set.call_args
    assert call_args[0][0] == "telemetry:painel:77"
    payload_str = call_args[0][1]
    assert call_args[1]["ex"] == 30

    # Test obter
    mock_redis.get.return_value = payload_str
    obtido = await cache.obter_painel(77)
    assert obtido is not None
    assert obtido.organizacao_id == 77
    assert obtido.sla_compliance_percentual == 94.0
    assert obtido.sla_em_conformidade is False
    assert len(obtido.medicos_tma) == 1
    assert obtido.medicos_tma[0].medico_id == med_id

    # Test invalidar
    await cache.invalidar_painel(77)
    mock_redis.delete.assert_awaited_once_with("telemetry:painel:77")
