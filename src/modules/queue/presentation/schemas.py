"""Presentation schemas for queue admission and triage endpoints."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.modules.queue.application.dtos import (
    AdmissaoAtendimentoCommand,
    RegularizacaoFilaCommand,
)


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
    cpf: str | None = Field(default=None, description="CPF do paciente (opcional)")
    cns: str | None = Field(default=None, description="Cartão Nacional de Saúde (SUS)")

    def to_command(
        self,
        ip_origem: str | None = None,
    ) -> AdmissaoAtendimentoCommand:
        """Convert request into application command."""
        return AdmissaoAtendimentoCommand(
            paciente_id=self.paciente_id,
            queixa_principal=self.queixa_principal,
            sintomas=self.sintomas,
            escala_dor=self.escala_dor,
            tcle_texto=self.tcle_texto,
            tcle_hash=self.tcle_hash,
            cpf=self.cpf,
            cns=self.cns,
            ip_origem=ip_origem,
        )


class AdmissaoResponse(BaseModel):
    """Response payload for patient admission and triage."""

    model_config = ConfigDict(from_attributes=True)

    atendimento_id: UUID
    triagem_id: UUID
    paciente_id: UUID
    status_atendimento: str
    prioridade_clinica: int
    alerta_samu_disparado: bool
    instrucoes: str | None = None
    tcle_hash: str | None = Field(
        default=None, description="Hash SHA-256 do TCLE digital aceito"
    )


class ChamarProximoResponse(BaseModel):
    """Resposta para a aquisição e chamada do próximo paciente da fila."""

    model_config = ConfigDict(from_attributes=True)

    alocado: bool = Field(description="Indica se um paciente foi alocado com sucesso")
    atendimento_id: UUID | None = Field(
        default=None, description="ID do atendimento alocado"
    )
    medico_id: UUID | None = Field(
        default=None, description="ID do médico que realizou a chamada"
    )
    paciente_id: UUID | None = Field(default=None, description="ID do paciente alocado")
    prioridade_clinica: int | None = Field(
        default=None, description="Prioridade clínica do atendimento"
    )
    status: str | None = Field(default=None, description="Status do atendimento")
    chamada_iniciada_em: datetime | None = Field(
        default=None, description="Data/hora de início da chamada"
    )
    ttl_segundos: int | None = Field(
        default=None, description="Tempo limite em segundos para início do atendimento"
    )
    mensagem: str = Field(description="Mensagem descritiva do resultado da alocação")


class PosicaoFilaResponse(BaseModel):
    """Resposta com posição ordinal, timer de chamada e estimativa de espera."""

    model_config = ConfigDict(from_attributes=True)

    atendimento_id: UUID = Field(description="ID do atendimento")
    status: str = Field(description="Status atual do atendimento")
    posicao: int | None = Field(
        description="Posição 1-based na fila, ou None se não estiver na fila ativa"
    )
    total_aguardando: int = Field(description="Total de pacientes aguardando na fila")
    tempo_estimado_segundos: int | None = Field(
        description="Tempo de espera estimado em segundos"
    )
    prioridade_clinica: int = Field(
        description="Classificação de risco Manchester (1=Emergência a 5=Não Urgente)"
    )
    chamada_iniciada_em: datetime | None = Field(
        default=None,
        description="Timestamp de início do toque de chamada (para countdown após F5)",
    )
    ttl_segundos: int | None = Field(
        default=None,
        description="Tolerância em segundos da janela de toque ativa",
    )


class CancelarFilaRequest(BaseModel):
    """Payload opcional para cancelamento voluntário de atendimento na fila."""

    model_config = ConfigDict(frozen=True)

    motivo: str = Field(
        default="Desistência voluntária pelo paciente",
        max_length=500,
        description="Motivo do cancelamento",
    )


class CancelarFilaResponse(BaseModel):
    """Resposta de confirmação de cancelamento do atendimento na fila."""

    model_config = ConfigDict(from_attributes=True)

    atendimento_id: UUID = Field(description="ID do atendimento cancelado")
    status: str = Field(description="Novo status do atendimento")
    cancelado_em: datetime = Field(description="Data/hora do cancelamento")
    motivo: str | None = Field(
        default=None, description="Motivo registrado para o cancelamento"
    )


class PioraClinicaRequest(BaseModel):
    """Payload para comunicação de piora clínica pelo paciente na fila."""

    model_config = ConfigDict(frozen=True)

    atendimento_id: UUID = Field(description="ID do atendimento ativo na fila")
    novos_sintomas: list[str] = Field(
        default_factory=list,
        description="Sintomas novos ou agravados",
    )
    escala_dor: Annotated[
        int, Field(ge=0, le=10, description="Nova escala de dor relatada (0 a 10)")
    ] = 0
    queixa_adicional: str = Field(
        default="",
        max_length=2000,
        description="Descrição dos novos sintomas ou agravamento do quadro clínico",
    )


class PioraClinicaResponse(BaseModel):
    """Resposta com resultado da reavaliação de risco e salvaguardas clínicas."""

    model_config = ConfigDict(from_attributes=True)

    atendimento_id: UUID = Field(description="ID do atendimento")
    prioridade_clinica: int = Field(
        description="Prioridade clínica consolidada pós-reavaliação"
    )
    status_atendimento: str | None = Field(
        default=None,
        description="Status do atendimento após a reavaliação de piora",
    )
    alerta_samu_disparado: bool = Field(
        description="Classificado como emergência máxima (Vermelho)"
    )
    redirecionado_emergencia: bool = Field(
        description="Redirecionamento imediato ao pronto-socorro"
    )
    nova_posicao: int | None = Field(
        default=None,
        description="Nova posição ordinal na fila após reclassificação",
    )
    instrucoes: str | None = Field(
        default=None,
        description="Instruções de redirecionamento ou emergência imediata",
    )


class RegularizacaoFilaRequest(BaseModel):
    """Payload para regularização de atendimento retido ou contingência assistencial."""

    model_config = ConfigDict(frozen=True)

    motivo: str = Field(
        min_length=3,
        max_length=500,
        description="Motivo da regularização ou contingência assistencial",
    )
    tipo_contingencia: str = Field(
        default="CONTINGENCIA_ASSISTENCIAL",
        description="Tipo de contingência assistencial acionada",
    )

    def to_command(self, atendimento_id: UUID) -> RegularizacaoFilaCommand:
        """Converte a requisição em comando da camada de aplicação."""
        return RegularizacaoFilaCommand(
            atendimento_id=atendimento_id,
            motivo=self.motivo,
            tipo_contingencia=self.tipo_contingencia,
        )


class RegularizacaoFilaResponse(BaseModel):
    """Resposta com resultado da regularização ou promoção por contingência na fila."""

    model_config = ConfigDict(from_attributes=True)

    atendimento_id: UUID = Field(description="ID do atendimento regularizado")
    promovido: bool = Field(
        description="Indica se o atendimento foi promovido para apto"
    )
    status: str = Field(description="Novo status do atendimento após regularização")
    score: int = Field(
        description="Score ordinal de antiguidade e prioridade na fila virtual"
    )
    tipo_contingencia: str = Field(
        description="Tipo de contingência registrado na regularização"
    )
    mensagem: str = Field(description="Mensagem descritiva do resultado da operação")


__all__ = [
    "AdmissaoRequest",
    "AdmissaoResponse",
    "CancelarFilaRequest",
    "CancelarFilaResponse",
    "ChamarProximoResponse",
    "PioraClinicaRequest",
    "PioraClinicaResponse",
    "PosicaoFilaResponse",
    "RegularizacaoFilaRequest",
    "RegularizacaoFilaResponse",
]
