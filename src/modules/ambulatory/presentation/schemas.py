"""Pydantic v2 presentation schemas for SUS ambulatory production (ADR-001/ADR-008)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BpaProducaoItemResponse(BaseModel):
    """Schema de resposta para item consolidado de produção ambulatorial SUS (BPA-I)."""

    model_config = ConfigDict(from_attributes=True)

    atendimento_id: UUID = Field(description="Identificador único do atendimento")
    cnes: str = Field(description="Código CNES do ponto de telessaúde")
    codigo_sigtap: str = Field(description="Procedimento SIGTAP (03.01.01.025-0)")
    carater_atendimento: str = Field(
        description="Caráter do atendimento (02 - Urgência)"
    )
    consolidado_em: datetime = Field(description="Data e hora UTC da consolidação")


class ListaProducaoAmbulatorialResponse(BaseModel):
    """Schema de resposta paginada da produção ambulatorial por competência."""

    model_config = ConfigDict(from_attributes=True)

    items: list[BpaProducaoItemResponse] = Field(
        description="Itens de produção ambulatorial"
    )
    total: int = Field(description="Total de registros na competência")
    competencia: str = Field(description="Competência de referência no formato YYYYMM")
    organizacao_id: int = Field(description="Identificador do tenant municipal")
    page: int = Field(description="Página atual")
    size: int = Field(description="Tamanho da página")
