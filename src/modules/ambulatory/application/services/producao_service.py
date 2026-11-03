"""Ambulatory production service for SUS BPA-I and SISAB consolidation (ADR-012)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.modules.ambulatory.application.dtos import (
    BpaProducaoDTO,
    ConsolidarTeleconsultaCommand,
)
from src.modules.ambulatory.domain.models.producao_ambulatorial import (
    ProducaoAmbulatorial,
)


class ProducaoAmbulatorialService:
    """Serviço de aplicação para consolidação de produção ambulatorial SUS.

    Orquestra a persistência e exportação de itens de faturamento público
    (BPA-I / SISAB) vinculados ao procedimento SIGTAP 03.01.01.025-0.
    Regras: docs/explanation/domains/ambulatory-domain.md, US-11 e ADR-012.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Inicializa serviço com sessão assíncrona do SQLAlchemy."""
        self._session = session

    @staticmethod
    def converter_para_bpa_dto(producao: ProducaoAmbulatorial) -> BpaProducaoDTO:
        """Converte a entidade de produção ambulatorial para o DTO BPA-I."""
        return BpaProducaoDTO(
            atendimento_id=producao.atendimento_id,
            cnes=producao.cnes,
            codigo_sigtap=producao.codigo_sigtap,
            carater_atendimento=producao.carater_atendimento,
            consolidado_em=producao.consolidado_em,
        )

    async def consolidar_teleconsulta(
        self,
        cmd: ConsolidarTeleconsultaCommand,
        *,
        organizacao_id: int,
    ) -> BpaProducaoDTO:
        """Consolida atendimento médico finalizado para faturamento BPA-I no SUS.

        Regras: US-11 (Consolidação Ambulatorial SUS) e ADR-012.
        Garante idempotência caso o atendimento já tenha sido consolidado.
        """
        # 1. Checagem de idempotência
        stmt = select(ProducaoAmbulatorial).where(
            ProducaoAmbulatorial.atendimento_id == cmd.atendimento_id
        )
        result = await self._session.execute(stmt)
        existente = result.scalar_one_or_none()
        if existente is not None:
            return self.converter_para_bpa_dto(existente)

        # 2. Criação da produção ambulatorial
        producao = ProducaoAmbulatorial(
            organizacao_id=organizacao_id,
            atendimento_id=cmd.atendimento_id,
            profissional_id=cmd.profissional_id,
            paciente_id=cmd.paciente_id,
            cnes=cmd.cnes,
            codigo_sigtap=cmd.codigo_sigtap,
            carater_atendimento=cmd.carater_atendimento,
        )
        self._session.add(producao)
        await self._session.commit()

        return self.converter_para_bpa_dto(producao)
