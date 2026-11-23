"""Unit tests for ConfiguracaoPlantao rich domain model and invariants."""

from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError
from src.core.errors import ValidationError
from src.modules.telemetry.domain.models import ConfiguracaoPlantao, ModoOperacao
from src.modules.telemetry.presentation.schemas import (
    ConfigPlantaoRequest,
    ConfigPlantaoResponse,
)

if TYPE_CHECKING:
    from src.modules.telemetry.application.dtos import ConfigPlantaoInput


def test_configuracao_plantao_default_initialization() -> None:
    config = ConfiguracaoPlantao()

    assert not hasattr(config, "organizacao_id")
    assert config.singleton_guard is True
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

    assert config.medicos_ativos_planejados == 5
    assert config.alpha_backpressure == Decimal("1.28")
    assert config.cota_diaria_maxima == 500
    assert config.tma_padrao_segundos == 720
    assert config.tempo_tolerancia_ring_segundos == 60
    assert config.modo_operacao == "PRIVADO"
    assert config.atualizado_por_id == admin_id


def test_invariante_singleton_guard() -> None:
    with pytest.raises(ValidationError, match="singleton_guard"):
        ConfiguracaoPlantao(singleton_guard=False)


def test_invariante_medicos_ativos_planejados() -> None:
    with pytest.raises(ValidationError, match="medicos_ativos_planejados inválido"):
        ConfiguracaoPlantao(medicos_ativos_planejados=0)


def test_invariante_alpha_backpressure_bounds() -> None:
    with pytest.raises(ValidationError, match="alpha_backpressure inválido"):
        ConfiguracaoPlantao(alpha_backpressure="1.19")

    with pytest.raises(ValidationError, match="alpha_backpressure inválido"):
        ConfiguracaoPlantao(alpha_backpressure="1.31")

    c1 = ConfiguracaoPlantao(alpha_backpressure="1.20")
    assert c1.alpha_backpressure == Decimal("1.20")

    c2 = ConfiguracaoPlantao(alpha_backpressure="1.30")
    assert c2.alpha_backpressure == Decimal("1.30")


def test_invariante_cota_diaria_maxima() -> None:
    with pytest.raises(ValidationError, match="cota_diaria_maxima inválida"):
        ConfiguracaoPlantao(cota_diaria_maxima=0)

    c = ConfiguracaoPlantao(cota_diaria_maxima=None)
    assert c.cota_diaria_maxima is None


def test_invariante_tma_padrao() -> None:
    with pytest.raises(ValidationError, match="tma_padrao_segundos inválido"):
        ConfiguracaoPlantao(tma_padrao_segundos=59)

    c = ConfiguracaoPlantao(tma_padrao_segundos=60)
    assert c.tma_padrao_segundos == 60


def test_invariante_ring_tolerancia() -> None:
    with pytest.raises(
        ValidationError, match="tempo_tolerancia_ring_segundos inválido"
    ):
        ConfiguracaoPlantao(tempo_tolerancia_ring_segundos=9)

    c = ConfiguracaoPlantao(tempo_tolerancia_ring_segundos=10)
    assert c.tempo_tolerancia_ring_segundos == 10


def test_invariante_modo_operacao() -> None:
    with pytest.raises(ValidationError, match="modo_operacao inválido"):
        ConfiguracaoPlantao(modo_operacao="MISTO")


def test_invariante_sla_minutos_negativo() -> None:
    with pytest.raises(ValidationError, match="sla_minutos_nivel_1 inválido"):
        ConfiguracaoPlantao(sla_minutos_nivel_1=-1)


def test_atualizar_parametros_success() -> None:
    config = ConfiguracaoPlantao()
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
    config = ConfiguracaoPlantao()

    with pytest.raises(ValidationError, match="alpha_backpressure inválido"):
        config.atualizar_parametros(alpha_backpressure=Decimal("1.40"))


def test_obter_sla_minutos_e_segundos() -> None:
    config = ConfiguracaoPlantao(
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


def test_capacidade_atendimento_hora_podada() -> None:
    assert not hasattr(ConfiguracaoPlantao, "capacidade_atendimento_hora")


def test_response_schema_from_entity() -> None:
    config = ConfiguracaoPlantao()
    dto = ConfigPlantaoResponse.model_validate(config)

    assert dto.id == config.id
    assert not hasattr(dto, "organizacao_id")
    assert dto.medicos_ativos_planejados == 1
    assert dto.alpha_backpressure == Decimal("1.25")
    assert dto.cota_diaria_maxima == 300
    assert dto.tma_padrao_segundos == 600
    assert dto.tempo_tolerancia_ring_segundos == 45
    assert dto.modo_operacao == "SUS"


def test_config_plantao_request_exige_todos_os_11_campos_sem_defaults() -> None:
    with pytest.raises(PydanticValidationError):
        ConfigPlantaoRequest.model_validate({"medicos_ativos_planejados": 2})

    req = ConfigPlantaoRequest(
        medicos_ativos_planejados=3,
        alpha_backpressure=Decimal("1.25"),
        cota_diaria_maxima=None,
        tma_padrao_segundos=600,
        tempo_tolerancia_ring_segundos=45,
        modo_operacao="SUS",
        sla_minutos_nivel_1=0,
        sla_minutos_nivel_2=10,
        sla_minutos_nivel_3=60,
        sla_minutos_nivel_4=120,
        sla_minutos_nivel_5=240,
    )
    contrato: ConfigPlantaoInput = req
    assert contrato.cota_diaria_maxima is None
    assert not hasattr(req, "to_command")
