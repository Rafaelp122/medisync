"""Ambulatory domain enumerations (ADR-012, Portaria GM/MS nº 3.232/2024)."""

from enum import StrEnum


class StatusElegibilidade(StrEnum):
    """Eligibility validation status for SUS patient qualification (RF-02, RN03)."""

    APROVADO = "APROVADO"
    REJEITADO = "REJEITADO"
    TIMEOUT = "TIMEOUT"
    PENDENTE = "PENDENTE"


class TipoProcedimentoAmbulatorial(StrEnum):
    """Tabela de Procedimentos do SUS (SIGTAP) para Atenção Primária e Telessaúde."""

    CONSULTA_MEDICA_ATENCAO_PRIMARIA = "03.01.01.025-0"
    CONSULTA_MEDICA_ATENCAO_ESPECIALIZADA = "03.01.01.007-2"


class CaraterAtendimento(StrEnum):
    """Caráter do atendimento para consolidação BPA-I / SISAB no SUS."""

    ELETIVO = "01"
    URGENCIA = "02"
