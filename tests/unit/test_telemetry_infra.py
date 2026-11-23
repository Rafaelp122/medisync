"""Unit tests for telemetry infrastructure adapters using canonical Fakes."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import pytest
from src.modules.telemetry.application.dtos import (
    MedicoTMADTO,
    PainelTelemetriaDTO,
)
from src.modules.telemetry.application.ports.telemetry_reader_port import (
    TelemetryReaderPort,
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

from tests.doubles import FakeAsyncSession, FakeResult, FakeValkey

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_sql_config_plantao_repository_salvar_e_obter() -> None:
    config = ConfiguracaoPlantao()
    session = FakeAsyncSession(results=[FakeResult(config)])
    repo = SqlConfigPlantaoRepository(cast("AsyncSession", session))

    salvo = await repo.salvar(config)
    assert salvo.singleton_guard is True
    assert session.added == [config]
    assert session.flushes == 1

    obtido = await repo.obter_atual()
    assert obtido is config
    assert session.executes == 1


@pytest.mark.asyncio
async def test_sql_config_plantao_repository_obter_ou_criar_padrao_on_conflict() -> (
    None
):
    padrao = ConfiguracaoPlantao()
    session = FakeAsyncSession(
        results=[
            FakeResult(None),  # obter_atual inicial -> ausente
            FakeResult(None),  # INSERT ... ON CONFLICT DO NOTHING
            FakeResult(padrao),  # obter_atual pos-insert
        ]
    )
    repo = SqlConfigPlantaoRepository(cast("AsyncSession", session))

    obtido = await repo.obter_ou_criar_padrao()

    assert obtido is padrao
    assert session.executes == 3
    insert_sql = session.executed_sql[1][0]
    assert "INSERT INTO configuracoes_plantao" in insert_sql
    assert "ON CONFLICT (singleton_guard) DO NOTHING" in insert_sql


def test_telemetry_reader_port_exposes_single_method() -> None:
    public_methods = [
        name
        for name in TelemetryReaderPort.__dict__
        if not name.startswith("_") and callable(TelemetryReaderPort.__dict__[name])
    ]
    assert public_methods == ["obter_painel_telemetria"]


@pytest.mark.asyncio
async def test_sql_telemetry_reader_obter_painel_reutiliza_obter_sla_segundos() -> None:
    medico_id = uuid4()
    agregados_row = {
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
    medicos_rows = [
        {
            "medico_id": medico_id,
            "nome": "Dr. House",
            "total_atendimentos": 10,
            "tma_segundos": 420.0,
        }
    ]
    session = FakeAsyncSession(
        results=[
            FakeResult(mappings_rows=[agregados_row]),
            FakeResult(mappings_rows=medicos_rows),
            FakeResult(5),
            FakeResult(3),
        ]
    )

    reader = SqlTelemetryReader(cast("AsyncSession", session))
    config = ConfiguracaoPlantao(
        sla_minutos_nivel_1=1,
        sla_minutos_nivel_2=15,
        sla_minutos_nivel_3=45,
        sla_minutos_nivel_4=90,
        sla_minutos_nivel_5=180,
    )

    painel = await reader.obter_painel_telemetria(config=config)

    assert not hasattr(painel, "organizacao_id")
    assert painel.total_atendimentos == 20
    assert painel.no_show_rate == 10.0
    assert painel.evasao_rate == 5.0
    assert painel.sla_compliance_percentual == 100.0
    assert painel.sla_em_conformidade is True
    assert painel.total_pacientes_fila == 5
    assert painel.medicos_ativos_count == 3
    assert len(painel.medicos_tma) == 1
    assert painel.medicos_tma[0].medico_id == medico_id
    assert painel.medicos_tma[0].nome == "Dr. House"

    sql_agregados, params_agregados = session.executed_sql[0]
    assert "organizacao_id" not in sql_agregados
    assert params_agregados["sla_1"] == config.obter_sla_segundos(1)
    assert params_agregados["sla_2"] == config.obter_sla_segundos(2)
    assert params_agregados["sla_3"] == config.obter_sla_segundos(3)
    assert params_agregados["sla_4"] == config.obter_sla_segundos(4)
    assert params_agregados["sla_5"] == config.obter_sla_segundos(5)


@pytest.mark.asyncio
async def test_memory_telemetry_cache_lifecycle() -> None:
    cache = MemoryTelemetryCache()

    painel = PainelTelemetriaDTO(
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

    assert await cache.obter_painel() is None

    await cache.salvar_painel(painel, ttl_segundos=60)
    cached = await cache.obter_painel()
    assert cached is not None
    assert cached.sla_compliance_percentual == 96.5
    assert cached.sla_em_conformidade is True

    await cache.invalidar_painel()
    assert await cache.obter_painel() is None


@pytest.mark.asyncio
async def test_valkey_telemetry_cache_roundtrip_com_type_adapter() -> None:
    fake_valkey = FakeValkey()
    cache = ValkeyTelemetryCache(cast("Redis", fake_valkey))

    med_id = uuid4()
    painel = PainelTelemetriaDTO(
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

    await cache.salvar_painel(painel, ttl_segundos=30)
    assert await fake_valkey.ttl("telemetry:painel") == 30

    obtido = await cache.obter_painel()
    assert obtido is not None
    assert obtido.sla_compliance_percentual == 94.0
    assert obtido.sla_em_conformidade is False
    assert len(obtido.medicos_tma) == 1
    assert obtido.medicos_tma[0].medico_id == med_id
    assert obtido.gerado_em.tzinfo is not None

    # Payload corrompido retorna None sem propagar excecao
    await fake_valkey.set("telemetry:painel", "{json-corrompido")
    assert await cache.obter_painel() is None

    await cache.invalidar_painel()
    assert await fake_valkey.get("telemetry:painel") is None
