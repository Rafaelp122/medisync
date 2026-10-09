"""SQLAlchemy 2.0 ORM implementation of IdentityReaderPort."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import NotFoundError
from src.modules.identity.application.ports.identity_reader_port import (
    IdentityDirectoryDTO,
    IdentityReaderPort,
)
from src.modules.identity.domain.models import Organizacao, Paciente, Profissional


class SqlIdentityReader(IdentityReaderPort):
    """Chainable ORM identity reader encapsulating identity tables."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def obter_dados_diretorio(
        self,
        organizacao_id: int,
        medico_id: UUID,
        paciente_id: UUID,
    ) -> IdentityDirectoryDTO:
        # 1. Fetch organization
        stmt_org = select(Organizacao).where(Organizacao.id == organizacao_id)
        org = (await self._session.execute(stmt_org)).scalar_one_or_none()
        org_nome = "MediSync Pronto-Atendimento Virtual"
        org_cnpj: str | None = None
        if org is not None:
            org_nome = org.nome_fantasia or org.razao_social or org_nome
            org_cnpj = org.cnpj

        # 2. Fetch professional
        stmt_prof = select(Profissional).where(Profissional.id == medico_id)
        prof = (await self._session.execute(stmt_prof)).scalar_one_or_none()
        if prof is None:
            raise NotFoundError(f"Profissional médico '{medico_id}' não encontrado.")

        # 3. Fetch patient
        stmt_pac = select(Paciente).where(
            Paciente.id == paciente_id,
            Paciente.organizacao_id == organizacao_id,
        )
        pac = (await self._session.execute(stmt_pac)).scalar_one_or_none()
        if pac is None:
            raise NotFoundError(
                f"Paciente '{paciente_id}' não encontrado na "
                f"organização {organizacao_id}."
            )

        # Format address parts
        end_parts = [
            str(pac.logradouro or "").strip(),
            str(pac.numero or "").strip(),
            str(pac.bairro or "").strip(),
            str(pac.cidade or "").strip(),
            str(pac.estado or "").strip(),
        ]
        valid_parts = [p for p in end_parts if p]
        endereco_fmt = ", ".join(valid_parts) if valid_parts else None

        return IdentityDirectoryDTO(
            organizacao_id=organizacao_id,
            organizacao_nome=org_nome,
            organizacao_cnpj=org_cnpj,
            medico_id=prof.id,
            medico_nome=prof.nome_completo,
            medico_crm=prof.crm,
            medico_crm_uf=prof.crm_uf,
            paciente_id=pac.id,
            paciente_nome=pac.nome_completo or "",
            paciente_cpf=pac.cpf,
            paciente_data_nascimento=pac.data_nascimento,
            paciente_endereco=endereco_fmt,
        )

    async def obter_modo_sus(self, organizacao_id: int) -> bool:
        stmt = select(Organizacao.modo_publico_sus).where(
            Organizacao.id == organizacao_id
        )
        modo = (await self._session.execute(stmt)).scalar_one_or_none()
        return bool(modo) if modo is not None else False

    async def listar_organizacoes_ativas(self) -> list[int]:
        stmt = (
            select(Organizacao.id)
            .where(Organizacao.ativo.is_(True))
            .order_by(Organizacao.id.asc())
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [int(r) for r in rows]
