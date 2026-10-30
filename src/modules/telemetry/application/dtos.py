"""Application DTOs and commands for telemetry module."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
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

    organizacao_id: int
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

    def to_dict(self) -> dict[str, Any]:
        """Convert DTO to JSON-serializable dictionary."""
        return {
            "organizacao_id": self.organizacao_id,
            "gerado_em": self.gerado_em.isoformat(),
            "tme_medio_segundos": self.tme_medio_segundos,
            "tme_nivel_1_segundos": self.tme_nivel_1_segundos,
            "tme_nivel_2_segundos": self.tme_nivel_2_segundos,
            "tme_nivel_3_segundos": self.tme_nivel_3_segundos,
            "tme_nivel_4_segundos": self.tme_nivel_4_segundos,
            "tme_nivel_5_segundos": self.tme_nivel_5_segundos,
            "tma_medio_segundos": self.tma_medio_segundos,
            "medicos_tma": [
                {
                    "medico_id": str(m.medico_id),
                    "nome": m.nome,
                    "total_atendimentos": m.total_atendimentos,
                    "tma_segundos": m.tma_segundos,
                }
                for m in self.medicos_tma
            ],
            "no_show_rate": self.no_show_rate,
            "evasao_rate": self.evasao_rate,
            "sla_compliance_percentual": self.sla_compliance_percentual,
            "sla_em_conformidade": self.sla_em_conformidade,
            "medicos_ativos_count": self.medicos_ativos_count,
            "total_pacientes_fila": self.total_pacientes_fila,
            "total_atendimentos": self.total_atendimentos,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PainelTelemetriaDTO":
        """Reconstruct DTO from dictionary."""
        gerado_em_raw = data["gerado_em"]
        if isinstance(gerado_em_raw, datetime):
            gerado_em = gerado_em_raw
        else:
            gerado_em = datetime.fromisoformat(str(gerado_em_raw))
        if gerado_em.tzinfo is None:
            gerado_em = gerado_em.replace(tzinfo=UTC)

        medicos_raw = data.get("medicos_tma", [])
        medicos: list[MedicoTMADTO] = []
        for item in medicos_raw:
            raw_id = item["medico_id"]
            med_id = raw_id if isinstance(raw_id, UUID) else UUID(str(raw_id))
            medicos.append(
                MedicoTMADTO(
                    medico_id=med_id,
                    nome=str(item["nome"]),
                    total_atendimentos=int(item["total_atendimentos"]),
                    tma_segundos=float(item["tma_segundos"]),
                )
            )

        sla_comp = float(data["sla_compliance_percentual"])
        return cls(
            organizacao_id=int(data["organizacao_id"]),
            gerado_em=gerado_em,
            tme_medio_segundos=float(data["tme_medio_segundos"]),
            tme_nivel_1_segundos=float(data["tme_nivel_1_segundos"]),
            tme_nivel_2_segundos=float(data["tme_nivel_2_segundos"]),
            tme_nivel_3_segundos=float(data["tme_nivel_3_segundos"]),
            tme_nivel_4_segundos=float(data["tme_nivel_4_segundos"]),
            tme_nivel_5_segundos=float(data["tme_nivel_5_segundos"]),
            tma_medio_segundos=float(data["tma_medio_segundos"]),
            medicos_tma=tuple(medicos),
            no_show_rate=float(data["no_show_rate"]),
            evasao_rate=float(data["evasao_rate"]),
            sla_compliance_percentual=sla_comp,
            sla_em_conformidade=bool(data.get("sla_em_conformidade", sla_comp >= 95.0)),
            medicos_ativos_count=int(data["medicos_ativos_count"]),
            total_pacientes_fila=int(data["total_pacientes_fila"]),
            total_atendimentos=int(data["total_atendimentos"]),
        )


@dataclass(frozen=True)
class ConfigPlantaoCommand:
    """Command payload for creating or updating shift configuration."""

    organizacao_id: int
    medicos_ativos_planejados: int
    alpha_backpressure: Decimal
    cota_diaria_maxima: int | None = 300
    tma_padrao_segundos: int = 600
    tempo_tolerancia_ring_segundos: int = 45
    modo_operacao: str = "SUS"
    sla_minutos_nivel_1: int = 0
    sla_minutos_nivel_2: int = 10
    sla_minutos_nivel_3: int = 60
    sla_minutos_nivel_4: int = 120
    sla_minutos_nivel_5: int = 240
    atualizado_por_id: UUID | None = None
