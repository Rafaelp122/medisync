"""Presentation schemas for queue admission and triage endpoints."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.modules.queue.application.dtos import AdmissaoAtendimentoCommand


class AdmissaoRequest(BaseModel):
    """Payload for patient admission and triage."""

    model_config = ConfigDict(frozen=True)

    paciente_id: UUID = Field(description="ID do paciente acolhido")
    queixa_principal: str = Field(
        min_length=1, max_length=2000, description="Queixa clínica principal"
    )
    sintomas: list[str] = Field(
        default_factory=list, description="Lista de sintomas relatados"
    )
    escala_dor: Annotated[
        int, Field(ge=0, le=10, description="Escala de dor (0 a 10)")
    ] = 0
    tcle_texto: str = Field(
        default="",
        description="Texto do termo de consentimento (opcional se tcle_hash fornecido)",
    )
    tcle_hash: str | None = Field(
        default=None, min_length=64, max_length=64, description="Hash SHA-256 do TCLE"
    )
    medicos_ativos: int = Field(
        default=1,
        ge=1,
        description="Médicos ativos no plantão para cálculo de backpressure",
    )

    def to_command(self, organizacao_id: int) -> AdmissaoAtendimentoCommand:
        """Convert request into application command."""
        return AdmissaoAtendimentoCommand(
            organizacao_id=organizacao_id,
            paciente_id=self.paciente_id,
            queixa_principal=self.queixa_principal,
            sintomas=self.sintomas,
            escala_dor=self.escala_dor,
            tcle_texto=self.tcle_texto,
            tcle_hash=self.tcle_hash,
            medicos_ativos=self.medicos_ativos,
        )


class AdmissaoResponse(BaseModel):
    """Response payload for patient admission and triage."""

    model_config = ConfigDict(from_attributes=True)

    atendimento_id: UUID
    triagem_id: UUID
    organizacao_id: int
    paciente_id: UUID
    status_atendimento: str
    prioridade_clinica: int
    alerta_samu_disparado: bool
    instrucoes: str | None = None
