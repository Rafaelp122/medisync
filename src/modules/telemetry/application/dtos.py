"""Application DTOs and structural input contracts for telemetry module (ADR-008)."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID


@dataclass(frozen=True)
class MedicoTMADTO:
    """Average attendance time metrics per medical professional."""

    medico_id: UUID
    nome: str
    total_atendimentos: int
    tma_segundos: float


@dataclass(frozen=True)
class PainelTelemetriaDTO:
    """Aggregated operational telemetry dashboard metrics."""

    gerado_em: datetime
    tme_medio_segundos: float
    tme_nivel_1_segundos: float
    tme_nivel_2_segundos: float
    tme_nivel_3_segundos: float
    tme_nivel_4_segundos: float
    tme_nivel_5_segundos: float
    tma_medio_segundos: float
    medicos_tma: tuple[MedicoTMADTO, ...]
    no_show_rate: float
    evasao_rate: float
    sla_compliance_percentual: float
    sla_em_conformidade: bool
    medicos_ativos_count: int
    total_pacientes_fila: int
    total_atendimentos: int


class ConfigPlantaoInput(Protocol):
    """Structural input contract satisfied directly by ConfigPlantaoRequest."""

    @property
    def medicos_ativos_planejados(self) -> int: ...

    @property
    def alpha_backpressure(self) -> Decimal: ...

    @property
    def cota_diaria_maxima(self) -> int | None: ...

    @property
    def tma_padrao_segundos(self) -> int: ...

    @property
    def tempo_tolerancia_ring_segundos(self) -> int: ...

    @property
    def modo_operacao(self) -> Literal["SUS", "PRIVADO"]: ...

    @property
    def sla_minutos_nivel_1(self) -> int: ...

    @property
    def sla_minutos_nivel_2(self) -> int: ...

    @property
    def sla_minutos_nivel_3(self) -> int: ...

    @property
    def sla_minutos_nivel_4(self) -> int: ...

    @property
    def sla_minutos_nivel_5(self) -> int: ...


@dataclass(frozen=True)
class PoliticaPlantaoSnapshotDTO:
    """Read-only snapshot of active shift operational parameters across modules."""

    alpha_backpressure: float = 1.25
    cota_diaria_maxima: int | None = 300
    tma_padrao_segundos: int = 600
    tempo_tolerancia_ring_segundos: int = 45
