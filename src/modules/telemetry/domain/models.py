"""Shift configuration and operational telemetry parameters (ADR-001/ADR-008)."""

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base
from src.core.errors import ValidationError
from src.core.uuid7 import uuid7

_MIN_ALPHA = Decimal("1.20")
_MAX_ALPHA = Decimal("1.30")
_MIN_TMA = 60
_MIN_RING = 10


class ModoOperacao(StrEnum):
    """Operational mode of the emergency virtual shift."""

    SUS = "SUS"
    PRIVADO = "PRIVADO"


_VALID_MODOS: frozenset[str] = frozenset(
    {ModoOperacao.SUS.value, ModoOperacao.PRIVADO.value}
)


class ConfiguracaoPlantao(Base):
    """Configuração operacional do plantão de telemedicina por organização de saúde.

    Modela capacidade médica, tolerância a ring, metas de TMA e SLAs clínicos.
    Regras: RN06 (Ato Médico) e docs/explanation/domains/telemetry-domain.md.
    """

    __tablename__ = "configuracoes_plantao"
    __table_args__ = (
        UniqueConstraint("organizacao_id", name="uq_configuracoes_plantao_org"),
        CheckConstraint(
            "alpha_backpressure >= 1.20 AND alpha_backpressure <= 1.30",
            name="chk_config_plantao_alpha",
        ),
        CheckConstraint(
            "tma_padrao_segundos >= 60",
            name="chk_config_plantao_tma",
        ),
        CheckConstraint(
            "tempo_tolerancia_ring_segundos >= 10",
            name="chk_config_plantao_ring",
        ),
        CheckConstraint(
            "modo_operacao IN ('SUS', 'PRIVADO')",
            name="chk_config_plantao_modo",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid7
    )
    organizacao_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("organizacoes.id", ondelete="RESTRICT"), nullable=False
    )
    medicos_ativos_planejados: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False
    )
    alpha_backpressure: Mapped[Decimal] = mapped_column(
        Numeric(precision=4, scale=2), default=Decimal("1.25"), nullable=False
    )
    cota_diaria_maxima: Mapped[int | None] = mapped_column(
        Integer, default=300, nullable=True
    )
    tma_padrao_segundos: Mapped[int] = mapped_column(
        Integer, default=600, nullable=False
    )
    tempo_tolerancia_ring_segundos: Mapped[int] = mapped_column(
        Integer, default=45, nullable=False
    )
    modo_operacao: Mapped[str] = mapped_column(
        String(32), default=ModoOperacao.SUS.value, nullable=False
    )
    sla_minutos_nivel_1: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sla_minutos_nivel_2: Mapped[int] = mapped_column(
        Integer, default=10, nullable=False
    )
    sla_minutos_nivel_3: Mapped[int] = mapped_column(
        Integer, default=60, nullable=False
    )
    sla_minutos_nivel_4: Mapped[int] = mapped_column(
        Integer, default=120, nullable=False
    )
    sla_minutos_nivel_5: Mapped[int] = mapped_column(
        Integer, default=240, nullable=False
    )
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    atualizado_por_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )

    def __init__(
        self,
        organizacao_id: int,
        *,
        id: UUID | None = None,
        medicos_ativos_planejados: int = 1,
        alpha_backpressure: Decimal | float | str = Decimal("1.25"),
        cota_diaria_maxima: int | None = 300,
        tma_padrao_segundos: int = 600,
        tempo_tolerancia_ring_segundos: int = 45,
        modo_operacao: ModoOperacao | str = ModoOperacao.SUS,
        sla_minutos_nivel_1: int = 0,
        sla_minutos_nivel_2: int = 10,
        sla_minutos_nivel_3: int = 60,
        sla_minutos_nivel_4: int = 120,
        sla_minutos_nivel_5: int = 240,
        atualizado_por_id: UUID | None = None,
        criado_em: datetime | None = None,
        atualizado_em: datetime | None = None,
    ) -> None:
        self._validar_invariantes(
            organizacao_id=organizacao_id,
            medicos_ativos_planejados=medicos_ativos_planejados,
            alpha_backpressure=alpha_backpressure,
            cota_diaria_maxima=cota_diaria_maxima,
            tma_padrao_segundos=tma_padrao_segundos,
            tempo_tolerancia_ring_segundos=tempo_tolerancia_ring_segundos,
            modo_operacao=modo_operacao,
            sla_minutos_nivel_1=sla_minutos_nivel_1,
            sla_minutos_nivel_2=sla_minutos_nivel_2,
            sla_minutos_nivel_3=sla_minutos_nivel_3,
            sla_minutos_nivel_4=sla_minutos_nivel_4,
            sla_minutos_nivel_5=sla_minutos_nivel_5,
        )

        now = datetime.now(UTC)
        self.id = id or uuid7()
        self.organizacao_id = organizacao_id
        self.medicos_ativos_planejados = medicos_ativos_planejados
        self.alpha_backpressure = self._converter_alpha(alpha_backpressure)
        self.cota_diaria_maxima = cota_diaria_maxima
        self.tma_padrao_segundos = tma_padrao_segundos
        self.tempo_tolerancia_ring_segundos = tempo_tolerancia_ring_segundos
        self.modo_operacao = self._normalizar_modo(modo_operacao)
        self.sla_minutos_nivel_1 = sla_minutos_nivel_1
        self.sla_minutos_nivel_2 = sla_minutos_nivel_2
        self.sla_minutos_nivel_3 = sla_minutos_nivel_3
        self.sla_minutos_nivel_4 = sla_minutos_nivel_4
        self.sla_minutos_nivel_5 = sla_minutos_nivel_5
        self.atualizado_por_id = atualizado_por_id
        self.criado_em = criado_em or now
        self.atualizado_em = atualizado_em or now

    @staticmethod
    def _converter_alpha(alpha: Decimal | float | str) -> Decimal:
        if isinstance(alpha, Decimal):
            return alpha
        return Decimal(str(alpha))

    @staticmethod
    def _normalizar_modo(modo: ModoOperacao | str) -> str:
        if isinstance(modo, ModoOperacao):
            return modo.value
        return str(modo).strip().upper()

    @classmethod
    def _validar_invariantes(
        cls,
        *,
        organizacao_id: int,
        medicos_ativos_planejados: int,
        alpha_backpressure: Decimal | float | str,
        cota_diaria_maxima: int | None,
        tma_padrao_segundos: int,
        tempo_tolerancia_ring_segundos: int,
        modo_operacao: ModoOperacao | str,
        sla_minutos_nivel_1: int,
        sla_minutos_nivel_2: int,
        sla_minutos_nivel_3: int,
        sla_minutos_nivel_4: int,
        sla_minutos_nivel_5: int,
    ) -> None:
        if organizacao_id <= 0:
            raise ValidationError(
                f"organizacao_id inválido: {organizacao_id}; "
                "deve ser um identificador positivo (> 0)."
            )

        if medicos_ativos_planejados < 1:
            raise ValidationError(
                f"medicos_ativos_planejados inválido: {medicos_ativos_planejados}; "
                "deve ser no mínimo 1."
            )

        try:
            alpha_dec = cls._converter_alpha(alpha_backpressure)
        except Exception as exc:
            raise ValidationError(
                f"alpha_backpressure inválido: valor '{alpha_backpressure}' "
                "não conversível."
            ) from exc

        if not (_MIN_ALPHA <= alpha_dec <= _MAX_ALPHA):
            raise ValidationError(
                f"alpha_backpressure inválido: deve estar entre "
                f"{_MIN_ALPHA} e {_MAX_ALPHA}. Valor recebido: {alpha_dec}."
            )

        if cota_diaria_maxima is not None and cota_diaria_maxima <= 0:
            raise ValidationError(
                f"cota_diaria_maxima inválida: {cota_diaria_maxima}; "
                "deve ser maior que zero quando definida (> 0)."
            )

        if tma_padrao_segundos < _MIN_TMA:
            raise ValidationError(
                f"tma_padrao_segundos inválido: deve ser no mínimo {_MIN_TMA}s. "
                f"Valor recebido: {tma_padrao_segundos}."
            )

        if tempo_tolerancia_ring_segundos < _MIN_RING:
            raise ValidationError(
                f"tempo_tolerancia_ring_segundos inválido: deve ser no mínimo "
                f"{_MIN_RING}s. Valor recebido: {tempo_tolerancia_ring_segundos}."
            )

        modo_str = cls._normalizar_modo(modo_operacao)
        if modo_str not in _VALID_MODOS:
            raise ValidationError(
                f"modo_operacao inválido: deve ser um dos valores {_VALID_MODOS}. "
                f"Valor recebido: '{modo_str}'."
            )

        slas = (
            sla_minutos_nivel_1,
            sla_minutos_nivel_2,
            sla_minutos_nivel_3,
            sla_minutos_nivel_4,
            sla_minutos_nivel_5,
        )
        for i, sla in enumerate(slas, start=1):
            if sla < 0:
                raise ValidationError(
                    f"sla_minutos_nivel_{i} inválido: deve ser maior ou igual a zero. "
                    f"Valor recebido: {sla}."
                )

    def atualizar_parametros(
        self,
        *,
        medicos_ativos_planejados: int | None = None,
        alpha_backpressure: Decimal | float | str | None = None,
        cota_diaria_maxima: int | Any | None = ...,
        tma_padrao_segundos: int | None = None,
        tempo_tolerancia_ring_segundos: int | None = None,
        modo_operacao: ModoOperacao | str | None = None,
        sla_minutos_nivel_1: int | None = None,
        sla_minutos_nivel_2: int | None = None,
        sla_minutos_nivel_3: int | None = None,
        sla_minutos_nivel_4: int | None = None,
        sla_minutos_nivel_5: int | None = None,
        atualizado_por_id: UUID | None = None,
    ) -> None:
        """Atualiza parâmetros operacionais com invariantes estritas.

        Ajusta capacidade teórica e políticas de backpressure da telemedicina.
        Regras: docs/explanation/domains/telemetry-domain.md.
        """
        novo_medicos = (
            medicos_ativos_planejados
            if medicos_ativos_planejados is not None
            else self.medicos_ativos_planejados
        )
        novo_alpha = (
            alpha_backpressure
            if alpha_backpressure is not None
            else self.alpha_backpressure
        )
        novo_cota = (
            self.cota_diaria_maxima if cota_diaria_maxima is ... else cota_diaria_maxima
        )
        novo_tma = (
            tma_padrao_segundos
            if tma_padrao_segundos is not None
            else self.tma_padrao_segundos
        )
        novo_ring = (
            tempo_tolerancia_ring_segundos
            if tempo_tolerancia_ring_segundos is not None
            else self.tempo_tolerancia_ring_segundos
        )
        novo_modo = modo_operacao if modo_operacao is not None else self.modo_operacao
        novo_sla1 = (
            sla_minutos_nivel_1
            if sla_minutos_nivel_1 is not None
            else self.sla_minutos_nivel_1
        )
        novo_sla2 = (
            sla_minutos_nivel_2
            if sla_minutos_nivel_2 is not None
            else self.sla_minutos_nivel_2
        )
        novo_sla3 = (
            sla_minutos_nivel_3
            if sla_minutos_nivel_3 is not None
            else self.sla_minutos_nivel_3
        )
        novo_sla4 = (
            sla_minutos_nivel_4
            if sla_minutos_nivel_4 is not None
            else self.sla_minutos_nivel_4
        )
        novo_sla5 = (
            sla_minutos_nivel_5
            if sla_minutos_nivel_5 is not None
            else self.sla_minutos_nivel_5
        )

        self._validar_invariantes(
            organizacao_id=self.organizacao_id,
            medicos_ativos_planejados=novo_medicos,
            alpha_backpressure=novo_alpha,
            cota_diaria_maxima=novo_cota,
            tma_padrao_segundos=novo_tma,
            tempo_tolerancia_ring_segundos=novo_ring,
            modo_operacao=novo_modo,
            sla_minutos_nivel_1=novo_sla1,
            sla_minutos_nivel_2=novo_sla2,
            sla_minutos_nivel_3=novo_sla3,
            sla_minutos_nivel_4=novo_sla4,
            sla_minutos_nivel_5=novo_sla5,
        )

        self.medicos_ativos_planejados = novo_medicos
        self.alpha_backpressure = self._converter_alpha(novo_alpha)
        self.cota_diaria_maxima = novo_cota
        self.tma_padrao_segundos = novo_tma
        self.tempo_tolerancia_ring_segundos = novo_ring
        self.modo_operacao = self._normalizar_modo(novo_modo)
        self.sla_minutos_nivel_1 = novo_sla1
        self.sla_minutos_nivel_2 = novo_sla2
        self.sla_minutos_nivel_3 = novo_sla3
        self.sla_minutos_nivel_4 = novo_sla4
        self.sla_minutos_nivel_5 = novo_sla5
        self.atualizado_por_id = (
            atualizado_por_id
            if atualizado_por_id is not None
            else self.atualizado_por_id
        )
        self.atualizado_em = datetime.now(UTC)

    def obter_sla_minutos(self, prioridade: int) -> int:
        """Retorna o SLA alvo em minutos para o nível de prioridade clínica de 1 a 5.

        Define tempo máximo de espera de acordo com o protocolo de classificação.
        Regras: docs/explanation/domains/telemetry-domain.md.
        """
        match prioridade:
            case 1:
                return self.sla_minutos_nivel_1
            case 2:
                return self.sla_minutos_nivel_2
            case 3:
                return self.sla_minutos_nivel_3
            case 4:
                return self.sla_minutos_nivel_4
            case 5:
                return self.sla_minutos_nivel_5
            case _:
                raise ValidationError(
                    f"Prioridade clínica inválida: {prioridade}. Deve ser entre 1 e 5."
                )

    def obter_sla_segundos(self, prioridade: int) -> int:
        """Retorna o SLA alvo em segundos para o nível de prioridade clínica de 1 a 5.

        Converte a meta de tempo para unidades de telemetria em tempo real.
        Regras: docs/explanation/domains/telemetry-domain.md.
        """
        return self.obter_sla_minutos(prioridade) * 60

    def capacidade_atendimento_hora(self) -> float:
        """Calcula a capacidade teórica de atendimentos por hora com base no TMA padrão.

        Determina o throughput projetado do plantão para dimensionamento de escala.
        Regras: docs/explanation/domains/telemetry-domain.md.
        """
        return (self.medicos_ativos_planejados * 3600.0) / float(
            self.tma_padrao_segundos
        )
