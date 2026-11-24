"""Presentation schemas for shift telemetry dashboard and configuration (ADR-008)."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MedicoTMAResponse(BaseModel):
    """Average attendance time metrics per medical professional."""

    model_config = ConfigDict(from_attributes=True)

    medico_id: UUID
    nome: str
    total_atendimentos: int
    tma_segundos: float


class PainelTelemetriaResponse(BaseModel):
    """Aggregated operational telemetry dashboard response (RF-10)."""

    model_config = ConfigDict(from_attributes=True)

    gerado_em: datetime
    tme_medio_segundos: float
    tme_nivel_1_segundos: float
    tme_nivel_2_segundos: float
    tme_nivel_3_segundos: float
    tme_nivel_4_segundos: float
    tme_nivel_5_segundos: float
    tma_medio_segundos: float
    medicos_tma: list[MedicoTMAResponse]
    no_show_rate: float
    evasao_rate: float
    sla_compliance_percentual: float
    sla_em_conformidade: bool
    medicos_ativos_count: int
    total_pacientes_fila: int
    total_atendimentos: int


class ConfigPlantaoRequest(BaseModel):
    """Request payload for updating shift configuration and SLAs (RF-09)."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    medicos_ativos_planejados: int = Field(
        ge=1,
        description="Número planejado de médicos ativos no plantão",
    )
    alpha_backpressure: Decimal = Field(
        ge=Decimal("1.20"),
        le=Decimal("1.30"),
        description="Fator de sobrecarga (alpha) do plantão (entre 1.20 e 1.30)",
    )
    cota_diaria_maxima: int | None = Field(
        gt=0,
        description="Cota máxima diária de atendimentos (ou null para ilimitado)",
    )
    tma_padrao_segundos: int = Field(
        ge=60,
        description="Tempo Médio de Atendimento planejado em segundos (mínimo 60s)",
    )
    tempo_tolerancia_ring_segundos: int = Field(
        ge=10,
        description="Tolerância de ring em segundos antes de timeout (mínimo 10s)",
    )
    modo_operacao: Literal["SUS", "PRIVADO"] = Field(
        description="Modo de operação do plantão (SUS ou PRIVADO)",
    )
    sla_minutos_nivel_1: int = Field(
        ge=0,
        description="SLA nível 1 (Vermelho - Emergência) em minutos",
    )
    sla_minutos_nivel_2: int = Field(
        ge=0,
        description="SLA nível 2 (Laranja - Muito Urgente) em minutos",
    )
    sla_minutos_nivel_3: int = Field(
        ge=0,
        description="SLA nível 3 (Amarelo - Urgente) em minutos",
    )
    sla_minutos_nivel_4: int = Field(
        ge=0,
        description="SLA nível 4 (Verde - Pouco Urgente) em minutos",
    )
    sla_minutos_nivel_5: int = Field(
        ge=0,
        description="SLA nível 5 (Azul - Não Urgente) em minutos",
    )


class ConfigPlantaoResponse(BaseModel):
    """Response representation of shift configuration and operational SLAs (RF-09)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    medicos_ativos_planejados: int
    alpha_backpressure: Decimal
    cota_diaria_maxima: int | None
    tma_padrao_segundos: int
    tempo_tolerancia_ring_segundos: int
    modo_operacao: str
    sla_minutos_nivel_1: int
    sla_minutos_nivel_2: int
    sla_minutos_nivel_3: int
    sla_minutos_nivel_4: int
    sla_minutos_nivel_5: int
    criado_em: datetime
    atualizado_em: datetime
    atualizado_por_id: UUID | None
