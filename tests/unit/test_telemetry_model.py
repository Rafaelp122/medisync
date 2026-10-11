"""Unit tests for ConfiguracaoPlantao rich domain model and invariants."""

from decimal import Decimal
from uuid import uuid4

import pytest
from src.core.errors import ValidationError
from src.modules.telemetry.application.dtos import (
    ConfigPlantaoCommand,
    ConfigPlantaoResultDTO,
)
from src.modules.telemetry.domain.models import ConfiguracaoPlantao, ModoOperacao


def test_configuracao_plantao_default_initialization() -> None:
    config = ConfiguracaoPlantao(organizacao_id=101)

    assert config.organizacao_id == 101
    assert config.medicos_ativos_planejados == 1
    assert config.alpha_backpressure == Decimal("1.25")
    assert config.cota_diaria_maxima == 300
    assert config.tma_padrao_segundos == 600
    assert config.tempo_tolerancia_ring_segundos == 45
    assert config.modo_operacao == "SUS"
    assert config.sla_minutos_nivel_1 == 0
    assert config.sla_minutos_nivel_2 == 10
    assert config.sla_minutos_nivel_3 == 60
    assert config.sla_minutos_nivel_4 == 120
    assert config.sla_minutos_nivel_5 == 240
    assert config.id is not None
    assert config.criado_em is not None
    assert config.atualizado_em is not None
    assert config.atualizado_por_id is None


def test_configuracao_plantao_custom_initialization() -> None:
    admin_id = uuid4()
    config = ConfiguracaoPlantao(
        organizacao_id=202,
        medicos_ativos_planejados=5,
        alpha_backpressure=Decimal("1.28"),
        cota_diaria_maxima=500,
        tma_padrao_segundos=720,
        tempo_tolerancia_ring_segundos=60,
        modo_operacao=ModoOperacao.PRIVADO,
        sla_minutos_nivel_1=1,
        sla_minutos_nivel_2=15,
        sla_minutos_nivel_3=45,
        sla_minutos_nivel_4=90,
        sla_minutos_nivel_5=180,
        atualizado_por_id=admin_id,
    )

    assert config.organizacao_id == 202
    assert config.medicos_ativos_planejados == 5
    assert config.alpha_backpressure == Decimal("1.28")
    assert config.cota_diaria_maxima == 500
    assert config.tma_padrao_segundos == 720
    assert config.tempo_tolerancia_ring_segundos == 60
    assert config.modo_operacao == "PRIVADO"
    assert config.atualizado_por_id == admin_id


def test_invariante_organizacao_id_positivo() -> None:
    with pytest.raises(ValidationError, match="organizacao_id inválido"):
        ConfiguracaoPlantao(organizacao_id=0)

    with pytest.raises(ValidationError, match="organizacao_id inválido"):
        ConfiguracaoPlantao(organizacao_id=-10)


def test_invariante_medicos_ativos_planejados() -> None:
    with pytest.raises(ValidationError, match="medicos_ativos_planejados inválido"):
        ConfiguracaoPlantao(organizacao_id=1, medicos_ativos_planejados=0)


def test_invariante_alpha_backpressure_bounds() -> None:
    with pytest.raises(ValidationError, match="alpha_backpressure inválido"):
        ConfiguracaoPlantao(organizacao_id=1, alpha_backpressure="1.19")

    with pytest.raises(ValidationError, match="alpha_backpressure inválido"):
        ConfiguracaoPlantao(organizacao_id=1, alpha_backpressure="1.31")

    # Boundary values must succeed
    c1 = ConfiguracaoPlantao(organizacao_id=1, alpha_backpressure="1.20")
    assert c1.alpha_backpressure == Decimal("1.20")

    c2 = ConfiguracaoPlantao(organizacao_id=1, alpha_backpressure="1.30")
    assert c2.alpha_backpressure == Decimal("1.30")


def test_invariante_cota_diaria_maxima() -> None:
    with pytest.raises(ValidationError, match="cota_diaria_maxima inválida"):
        ConfiguracaoPlantao(organizacao_id=1, cota_diaria_maxima=0)

    # None is allowed (unlimited)
    c = ConfiguracaoPlantao(organizacao_id=1, cota_diaria_maxima=None)
    assert c.cota_diaria_maxima is None


def test_invariante_tma_padrao() -> None:
    with pytest.raises(ValidationError, match="tma_padrao_segundos inválido"):
        ConfiguracaoPlantao(organizacao_id=1, tma_padrao_segundos=59)

    c = ConfiguracaoPlantao(organizacao_id=1, tma_padrao_segundos=60)
    assert c.tma_padrao_segundos == 60


def test_invariante_ring_tolerancia() -> None:
    with pytest.raises(
        ValidationError, match="tempo_tolerancia_ring_segundos inválido"
    ):
        ConfiguracaoPlantao(organizacao_id=1, tempo_tolerancia_ring_segundos=9)

    c = ConfiguracaoPlantao(organizacao_id=1, tempo_tolerancia_ring_segundos=10)
    assert c.tempo_tolerancia_ring_segundos == 10


def test_invariante_modo_operacao() -> None:
    with pytest.raises(ValidationError, match="modo_operacao inválido"):
        ConfiguracaoPlantao(organizacao_id=1, modo_operacao="MISTO")


def test_invariante_sla_minutos_negativo() -> None:
    with pytest.raises(ValidationError, match="sla_minutos_nivel_1 inválido"):
        ConfiguracaoPlantao(organizacao_id=1, sla_minutos_nivel_1=-1)


def test_atualizar_parametros_success() -> None:
    config = ConfiguracaoPlantao(organizacao_id=10)
    user_id = uuid4()
    old_updated_at = config.atualizado_em

    config.atualizar_parametros(
        medicos_ativos_planejados=3,
        alpha_backpressure=Decimal("1.22"),
        cota_diaria_maxima=400,
        tma_padrao_segundos=480,
        tempo_tolerancia_ring_segundos=30,
        modo_operacao="PRIVADO",
        sla_minutos_nivel_1=5,
        atualizado_por_id=user_id,
    )

    assert config.medicos_ativos_planejados == 3
    assert config.alpha_backpressure == Decimal("1.22")
    assert config.cota_diaria_maxima == 400
    assert config.tma_padrao_segundos == 480
    assert config.tempo_tolerancia_ring_segundos == 30
    assert config.modo_operacao == "PRIVADO"
    assert config.sla_minutos_nivel_1 == 5
    assert config.atualizado_por_id == user_id
    assert config.atualizado_em >= old_updated_at


def test_atualizar_parametros_invariante_falha() -> None:
    config = ConfiguracaoPlantao(organizacao_id=10)

    with pytest.raises(ValidationError, match="alpha_backpressure inválido"):
        config.atualizar_parametros(alpha_backpressure=Decimal("1.40"))


def test_obter_sla_minutos_e_segundos() -> None:
    config = ConfiguracaoPlantao(
        organizacao_id=10,
        sla_minutos_nivel_1=0,
        sla_minutos_nivel_2=15,
        sla_minutos_nivel_3=45,
        sla_minutos_nivel_4=120,
        sla_minutos_nivel_5=240,
    )

    assert config.obter_sla_minutos(1) == 0
    assert config.obter_sla_segundos(1) == 0
    assert config.obter_sla_minutos(2) == 15
    assert config.obter_sla_segundos(2) == 900
    assert config.obter_sla_minutos(3) == 45
    assert config.obter_sla_segundos(3) == 2700
    assert config.obter_sla_minutos(4) == 120
    assert config.obter_sla_segundos(4) == 7200
    assert config.obter_sla_minutos(5) == 240
    assert config.obter_sla_segundos(5) == 14400

    with pytest.raises(ValidationError, match="Prioridade clínica inválida"):
        config.obter_sla_minutos(6)


def test_capacidade_atendimento_hora() -> None:
    config = ConfiguracaoPlantao(
        organizacao_id=1,
        medicos_ativos_planejados=2,
        tma_padrao_segundos=600,
    )
    # (2 * 3600) / 600 = 12 atendimentos/hora
    assert config.capacidade_atendimento_hora() == 12.0


def test_result_dto_from_entity() -> None:
    config = ConfiguracaoPlantao(organizacao_id=42)
    dto = ConfigPlantaoResultDTO.from_entity(config)

    assert dto.id == config.id
    assert dto.organizacao_id == 42
    assert dto.medicos_ativos_planejados == 1
    assert dto.alpha_backpressure == Decimal("1.25")
    assert dto.cota_diaria_maxima == 300
    assert dto.tma_padrao_segundos == 600
    assert dto.tempo_tolerancia_ring_segundos == 45
    assert dto.modo_operacao == "SUS"


def test_config_plantao_command_defaults() -> None:
    cmd = ConfigPlantaoCommand(
        organizacao_id=10,
        medicos_ativos_planejados=2,
        alpha_backpressure=Decimal("1.25"),
    )
    assert cmd.cota_diaria_maxima == 300
    assert cmd.tma_padrao_segundos == 600
    assert cmd.modo_operacao == "SUS"
