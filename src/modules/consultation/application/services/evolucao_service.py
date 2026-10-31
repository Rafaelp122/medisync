"""SOAP evolution owner: salvar/obter evolucao with terminal guard via reader port."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.audit import AtorPapel, AtorTipo, AuditTrailPort
from src.modules.consultation.application.dtos import RegistrarEvolucaoSOAPCommand
from src.modules.consultation.application.ports.atendimento_reader_port import (
    AtendimentoReaderPort,
    is_atendimento_terminal,
)
from src.modules.consultation.domain.exceptions import (
    ConsultaFinalizadaError,
    EvolucaoNaoEncontradaError,
)
from src.modules.consultation.domain.models import EvolucaoClinica


class EvolucaoService:
    """Owns SOAP evolution persistence; terminal check via AtendimentoReaderPort."""

    def __init__(
        self,
        session: AsyncSession,
        reader: AtendimentoReaderPort | None = None,
        audit_trail: AuditTrailPort | None = None,
    ) -> None:
        self._session = session
        self._reader = reader
        self._audit_trail = audit_trail

    async def _is_terminal(self, atendimento_id: UUID) -> bool:
        """Return True when queue-owned attendance reached terminal status."""
        return await is_atendimento_terminal(self._reader, atendimento_id)

    async def salvar_evolucao_soap(
        self, command: RegistrarEvolucaoSOAPCommand
    ) -> EvolucaoClinica:
        """Registra ou atualiza evolução SOAP com validação clínica.

        Garante conformidade com CFM nº 1.821/2007 e CFM nº 2.314/2022.
        Regras: RN06 (Ato Médico) e docs/explanation/domains/consultation-domain.md.
        """
        stmt = select(EvolucaoClinica).where(
            EvolucaoClinica.atendimento_id == command.atendimento_id
        )
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()

        is_term = await self._is_terminal(command.atendimento_id)

        if existing is not None:
            if existing.is_finalizado or is_term:
                existing.marcar_finalizado()
                status_desc = "terminal" if is_term else "evolucao_finalizada"
                raise ConsultaFinalizadaError(
                    "Não é permitido alterar evolução de consulta finalizada "
                    f"(status atual: '{status_desc}')."
                )

            existing.atualizar_soap(
                anamnese=command.anamnese,
                conduta=command.conduta,
                exame_fisico_virtual=command.exame_fisico_virtual,
                cid10_principal=command.cid10_principal,
            )

            await self._session.flush()
            if self._audit_trail is not None:
                await self._audit_trail.record_event(
                    organizacao_id=command.organizacao_id,
                    tipo_evento="EVOLUCAO_SOAP_REGISTRADA",
                    ator_tipo=AtorTipo.PROFISSIONAL.value,
                    ator_papel=AtorPapel.MEDICO.value,
                    ator_id=command.medico_id,
                    atendimento_id=command.atendimento_id,
                    payload={
                        "evolucao_id": str(existing.id),
                        "cid10": existing.cid10_principal,
                    },
                )
            await self._session.commit()
            return existing

        if is_term:
            raise ConsultaFinalizadaError(
                "Não é permitido criar evolução de consulta já finalizada "
                f"(atendimento '{command.atendimento_id}')."
            )

        evolucao = EvolucaoClinica(
            organizacao_id=command.organizacao_id,
            atendimento_id=command.atendimento_id,
            medico_id=command.medico_id,
            anamnese=command.anamnese,
            conduta=command.conduta,
            exame_fisico_virtual=command.exame_fisico_virtual,
            cid10_principal=command.cid10_principal,
        )
        self._session.add(evolucao)
        try:
            await self._session.flush()
        except IntegrityError as err:
            await self._session.rollback()
            stmt_retry = select(EvolucaoClinica).where(
                EvolucaoClinica.atendimento_id == command.atendimento_id
            )
            res_retry = await self._session.execute(stmt_retry)
            existing_retry = res_retry.scalar_one_or_none()
            if existing_retry is None:
                raise
            if existing_retry.is_finalizado or is_term:
                existing_retry.marcar_finalizado()
                status_desc = "terminal" if is_term else "evolucao_finalizada"
                raise ConsultaFinalizadaError(
                    "Não é permitido alterar evolução de consulta finalizada "
                    f"(status atual: '{status_desc}')."
                ) from err
            existing_retry.atualizar_soap(
                anamnese=command.anamnese,
                conduta=command.conduta,
                exame_fisico_virtual=command.exame_fisico_virtual,
                cid10_principal=command.cid10_principal,
            )
            await self._session.flush()
            if self._audit_trail is not None:
                await self._audit_trail.record_event(
                    organizacao_id=command.organizacao_id,
                    tipo_evento="EVOLUCAO_SOAP_REGISTRADA",
                    ator_tipo=AtorTipo.PROFISSIONAL.value,
                    ator_papel=AtorPapel.MEDICO.value,
                    ator_id=command.medico_id,
                    atendimento_id=command.atendimento_id,
                    payload={
                        "evolucao_id": str(existing_retry.id),
                        "cid10": existing_retry.cid10_principal,
                    },
                )
            await self._session.commit()
            return existing_retry

        if self._audit_trail is not None:
            await self._audit_trail.record_event(
                organizacao_id=command.organizacao_id,
                tipo_evento="EVOLUCAO_SOAP_REGISTRADA",
                ator_tipo=AtorTipo.PROFISSIONAL.value,
                ator_papel=AtorPapel.MEDICO.value,
                ator_id=command.medico_id,
                atendimento_id=command.atendimento_id,
                payload={
                    "evolucao_id": str(evolucao.id),
                    "cid10": command.cid10_principal,
                },
            )
        await self._session.commit()
        return evolucao

    async def obter_evolucao(self, atendimento_id: UUID) -> EvolucaoClinica:
        """Recupera evolução clínica SOAP persistida para o atendimento.

        Garante integridade e rastreabilidade conforme CFM nº 1.821/2007.
        Regras: RN06 e docs/explanation/domains/consultation-domain.md.
        """
        stmt = select(EvolucaoClinica).where(
            EvolucaoClinica.atendimento_id == atendimento_id
        )
        res = await self._session.execute(stmt)
        evolucao = res.scalar_one_or_none()
        if evolucao is None:
            raise EvolucaoNaoEncontradaError(
                f"Nenhuma evolução clínica registrada para o atendimento "
                f"'{atendimento_id}'."
            )
        return evolucao
