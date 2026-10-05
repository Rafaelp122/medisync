"""SOAP evolution owner: salvar/obter evolucao with terminal guard via reader port."""

import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.consultation.application.dtos import RegistrarEvolucaoSOAPCommand
from src.modules.consultation.application.ports.atendimento_reader_port import (
    AtendimentoReaderPort,
)
from src.modules.consultation.domain.exceptions import (
    ConsultaFinalizadaError,
    ConsultaInvalidaError,
    EvolucaoNaoEncontradaError,
)
from src.modules.consultation.domain.models import EvolucaoClinica

_CID10_REGEX = re.compile(r"^[A-Z][0-9]{2}(\.[0-9]{1,2})?$")


class EvolucaoService:
    """Owns SOAP evolution persistence; terminal check via AtendimentoReaderPort."""

    def __init__(
        self,
        session: AsyncSession,
        reader: AtendimentoReaderPort | None = None,
    ) -> None:
        self._session = session
        self._reader = reader

    async def _is_terminal(self, atendimento_id: UUID) -> bool:
        """Return True when queue-owned attendance reached terminal status."""
        if self._reader is None:
            return False
        try:
            resumo = await self._reader.obter_resumo(atendimento_id)
        except Exception:
            return False
        return bool(resumo is not None and resumo.is_terminal)

    async def salvar_evolucao_soap(
        self, command: RegistrarEvolucaoSOAPCommand
    ) -> EvolucaoClinica:
        """Record or update SOAP clinical notes for an attendance."""
        stmt = select(EvolucaoClinica).where(
            EvolucaoClinica.atendimento_id == command.atendimento_id
        )
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()

        is_term = await self._is_terminal(command.atendimento_id)

        if existing is not None:
            if existing.is_finalizado or is_term:
                existing.marcar_finalizado()
                raise ConsultaFinalizadaError(
                    "Não é permitido alterar evolução de consulta finalizada."
                )

            # Validate fields on update
            if not command.anamnese or not command.anamnese.strip():
                raise ConsultaInvalidaError(
                    "Anamnese clínica é obrigatória e não pode ser vazia."
                )
            if not command.conduta or not command.conduta.strip():
                raise ConsultaInvalidaError(
                    "Conduta clínica é obrigatória e não pode ser vazia."
                )

            clean_cid10: str | None = None
            if command.cid10_principal and command.cid10_principal.strip():
                c = command.cid10_principal.strip().upper()
                if not _CID10_REGEX.match(c):
                    raise ConsultaInvalidaError(
                        f"Código CID-10 inválido: '{command.cid10_principal}'. "
                        "Formato esperado: letra maiúscula seguida de 2 dígitos "
                        "e subcategoria opcional (ex.: J00, J02.9, A09.0)."
                    )
                clean_cid10 = c

            existing.anamnese = command.anamnese.strip()
            existing.conduta = command.conduta.strip()
            existing.exame_fisico_virtual = (
                command.exame_fisico_virtual.strip()
                if command.exame_fisico_virtual and command.exame_fisico_virtual.strip()
                else None
            )
            existing.cid10_principal = clean_cid10
            existing.registrado_em = datetime.now(UTC)

            await self._session.flush()
            await self._session.commit()
            return existing

        if is_term:
            raise ConsultaFinalizadaError(
                "Não é permitido criar evolução de consulta já finalizada."
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
        await self._session.flush()
        await self._session.commit()
        return evolucao

    async def obter_evolucao(self, atendimento_id: UUID) -> EvolucaoClinica:
        """Return SOAP evolution or raise 404 EvolucaoNaoEncontradaError."""
        stmt = select(EvolucaoClinica).where(
            EvolucaoClinica.atendimento_id == atendimento_id
        )
        res = await self._session.execute(stmt)
        evolucao = res.scalar_one_or_none()
        if evolucao is None:
            raise EvolucaoNaoEncontradaError(
                "Nenhuma evolução clínica registrada para este atendimento."
            )
        return evolucao
