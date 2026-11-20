"""Schemas Pydantic v2 (from_attributes=True) do módulo scheduling."""

from datetime import datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.modules.scheduling.application.dtos import (
    AgendarConsultaCommand,
    CriarDisponibilidadeCommand,
)


class EspecialidadeResponse(BaseModel):
    """Schema de resposta para especialidade disponível na agenda eMulti."""

    model_config = ConfigDict(from_attributes=True)

    codigo: str = Field(description="Código da especialidade (PSICOLOGIA, NUTRICAO)")
    nome: str = Field(description="Nome amigável da especialidade")
    descricao: str = Field(description="Descrição clínica da especialidade")
    duracao_padrao_minutos: int = Field(
        description="Duração padrão da consulta em minutos"
    )


class SlotDisponivelResponse(BaseModel):
    """Schema de resposta representando um horário livre para agendamento."""

    model_config = ConfigDict(from_attributes=True)

    profissional_id: UUID = Field(description="Identificador do profissional")
    especialidade: str = Field(description="Especialidade do atendimento")
    slot_inicio: datetime = Field(description="Início do horário em UTC")
    slot_fim: datetime = Field(description="Fim do horário em UTC")
    duracao_minutos: int = Field(description="Duração do slot em minutos")


class CriarDisponibilidadeRequest(BaseModel):
    """Payload para cadastro de janela semanal de agenda do profissional."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    especialidade: str = Field(description="Especialidade (PSICOLOGIA ou NUTRICAO)")
    dia_semana: int = Field(
        ge=0, le=6, description="Dia da semana (0=segunda .. 6=domingo)"
    )
    hora_inicio: time = Field(description="Horário inicial da janela (naive UTC)")
    hora_fim: time = Field(description="Horário final da janela (naive UTC)")
    duracao_minutos: int = Field(
        ge=15, le=120, description="Duração de cada slot (15 a 120 min)"
    )

    @field_validator("hora_inicio", "hora_fim")
    @classmethod
    def _validar_horario_sem_fuso(cls, valor: time) -> time:
        if valor.tzinfo is not None:
            raise ValueError(
                f"Horário '{valor.isoformat()}' não deve incluir fuso horário; "
                "informe no formato sem fuso (naive UTC)."
            )
        return valor

    def to_command(
        self,
        *,
        profissional_id: UUID,
    ) -> CriarDisponibilidadeCommand:
        """Converte payload HTTP em command de aplicação."""
        return CriarDisponibilidadeCommand(
            profissional_id=profissional_id,
            especialidade=self.especialidade,
            dia_semana=self.dia_semana,
            hora_inicio=self.hora_inicio,
            hora_fim=self.hora_fim,
            duracao_minutos=self.duracao_minutos,
        )


class DisponibilidadeResponse(BaseModel):
    """Schema de resposta da janela semanal cadastrada."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    profissional_id: UUID
    especialidade: str
    dia_semana: int
    hora_inicio: time
    hora_fim: time
    duracao_minutos: int
    ativo: bool


class CriarAgendamentoRequest(BaseModel):
    """Payload de reserva de horário pelo paciente autenticado (Anti-IDOR)."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    profissional_id: UUID = Field(description="Identificador do profissional")
    especialidade: str = Field(description="Especialidade agendada")
    slot_inicio: datetime = Field(description="Data/hora de início do slot")
    slot_fim: datetime | None = Field(
        default=None,
        description="Data/hora de término do slot (opcional; calculada se omitida)",
    )
    observacoes: str | None = Field(
        default=None, max_length=500, description="Observações opcionais do paciente"
    )

    def to_command(
        self,
        *,
        paciente_id: UUID,
    ) -> AgendarConsultaCommand:
        """Converte payload HTTP vinculando estritamente ao paciente do JWT."""
        return AgendarConsultaCommand(
            paciente_id=paciente_id,
            profissional_id=self.profissional_id,
            especialidade=self.especialidade,
            slot_inicio=self.slot_inicio,
            slot_fim=self.slot_fim,
            observacoes=self.observacoes,
        )


class IniciarAgendamentoRequest(BaseModel):
    """Payload opcional para iniciar atendimento a partir de agendamento."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    atendimento_id: UUID | None = Field(
        default=None, description="ID do atendimento clínico associado (opcional)"
    )


class AgendamentoResponse(BaseModel):
    """Schema de resposta de agendamento multiprofissional."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paciente_id: UUID
    profissional_id: UUID
    especialidade: str
    slot_inicio: datetime
    slot_fim: datetime
    status: str
    observacoes: str | None = None
    atendimento_id: UUID | None = None
    criado_em: datetime
    atualizado_em: datetime
