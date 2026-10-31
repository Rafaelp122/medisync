"""Domain enums and terminal status sets for queue lifecycle (RN01, RN03)."""

from enum import IntEnum, StrEnum


class StatusAtendimento(StrEnum):
    """Deterministic states of clinical attendance lifecycle (RN03)."""

    TRIADO_AGUARDANDO_ELEGIBILIDADE = "TRIADO_AGUARDANDO_ELEGIBILIDADE"
    APTO_PARA_CHAMADA = "APTO_PARA_CHAMADA"
    CHAMANDO_PACIENTE = "CHAMANDO_PACIENTE"
    EM_ATENDIMENTO = "EM_ATENDIMENTO"
    PACIENTE_AUSENTE = "PACIENTE_AUSENTE"
    CONCLUIDO = "CONCLUIDO"
    CANCELADO_PACIENTE = "CANCELADO_PACIENTE"


class PrioridadeClinica(IntEnum):
    """Clinical urgency triage levels (RN01 / Acolhimento ACR)."""

    EMERGENCIA = 1  # Vermelho - Risco Iminente
    MUITO_URGENTE = 2  # Laranja - Alta Gravidade
    URGENTE = 3  # Amarelo - Moderada Gravidade
    POUCO_URGENTE = 4  # Verde - Baixa Gravidade
    NAO_URGENTE = 5  # Azul - Eletivo / Não Urgente


TERMINAL_STATUSES = frozenset(
    {
        StatusAtendimento.CONCLUIDO,
        StatusAtendimento.PACIENTE_AUSENTE,
        StatusAtendimento.CANCELADO_PACIENTE,
    }
)
