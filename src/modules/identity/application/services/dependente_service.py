"""Application service managing pediatric and legal dependent linkages."""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ColumnElement, or_, select

from src.core.errors import ValidationError
from src.modules.identity.application.dtos import (
    CriarDependenteInput,
    DependenteDetalheDTO,
    DependenteOutputDTO,
)
from src.modules.identity.domain.exceptions import (
    DependenteAutoReferenciaError,
    IdentificacaoObrigatoriaError,
    PacienteNaoEncontradoError,
    VinculoDependenteExistenteError,
)
from src.modules.identity.domain.models import Dependente, Paciente
from src.modules.identity.domain.validators import (
    validate_cns,
    validate_cpf,
    validate_telefone,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class DependenteService:
    """Gerencia vínculos e cadastros de dependentes pediátricos e legais de titulares.

    Regras: RN-IDE-05, RN07 (TCLE), LGPD Art. 11, CFM 1.821/2007, ADR-013.
    Documentação: docs/explanation/domains/identity-domain.md
    """

    def __init__(self, session: "AsyncSession | None" = None) -> None:
        self._session = session

    async def _resolve_dependente(
        self,
        db: "AsyncSession",
        titular: Paciente,
        dados: CriarDependenteInput,
    ) -> Paciente:
        """Resolve existing dependent entity or register new patient record."""
        if dados.dependente_id is not None:
            stmt_dep = select(Paciente).where(Paciente.id == dados.dependente_id)
            dep_paciente = (await db.execute(stmt_dep)).scalars().first()
            if dep_paciente is None:
                raise PacienteNaoEncontradoError(
                    f"Paciente dependente '{dados.dependente_id}' não encontrado "
                    "na plataforma."
                )
            return dep_paciente

        if not dados.nome_completo or not dados.data_nascimento:
            raise ValidationError(
                "Nome completo e data de nascimento são mandatórios "
                "para cadastrar um novo dependente "
                f"(recebido nome_completo={dados.nome_completo!r}, "
                f"data_nascimento={dados.data_nascimento!r})."
            )

        clean_cpf = validate_cpf(dados.cpf) if dados.cpf else None
        clean_cns = validate_cns(dados.cns) if dados.cns else None
        if not clean_cpf and not clean_cns:
            raise IdentificacaoObrigatoriaError(
                "Obrigatório fornecer CPF ou CNS válido para o dependente "
                f"(recebido cpf={dados.cpf!r}, cns={dados.cns!r}; CFM/SUS)."
            )

        conditions: list[ColumnElement[bool]] = []
        if clean_cpf:
            conditions.append(Paciente.cpf == clean_cpf)
        if clean_cns:
            conditions.append(Paciente.cns == clean_cns)

        stmt_exist = select(Paciente).where(or_(*conditions))
        existing_dep = (await db.execute(stmt_exist)).scalars().first()
        if existing_dep is not None:
            return existing_dep

        telefone_dep = (
            validate_telefone(dados.telefone) if dados.telefone else titular.telefone
        )
        novo_dep = Paciente(
            data_nascimento=dados.data_nascimento,
            telefone=telefone_dep,
            cpf=clean_cpf,
            cns=clean_cns,
            nome_completo=dados.nome_completo.strip(),
        )
        db.add(novo_dep)
        await db.flush()
        return novo_dep

    async def adicionar_dependente(
        self,
        titular_id: UUID,
        dados: CriarDependenteInput,
        session: "AsyncSession | None" = None,
    ) -> DependenteOutputDTO:
        """Cadastra dependente exigindo outorga TCLE para menores (RN-IDE-05).

        Regras: RN-IDE-05, RN07 (TCLE titular/dependente), LGPD Art. 11, CFM 1.821,
        docs/explanation/domains/identity-domain.md.
        """
        db = session or self._session
        if db is None:
            raise ValueError(
                f"AsyncSession não configurada no DependenteService (recebido: {db!r})."
            )

        stmt_titular = select(Paciente).where(Paciente.id == titular_id)
        titular = (await db.execute(stmt_titular)).scalars().first()
        if titular is None:
            raise PacienteNaoEncontradoError(
                f"Paciente titular '{titular_id}' não encontrado na plataforma."
            )

        dep_paciente = await self._resolve_dependente(db, titular, dados)
        if dep_paciente.id == titular_id:
            raise DependenteAutoReferenciaError(
                titular_id=titular_id, dependente_id=dep_paciente.id
            )

        stmt_link = select(Dependente).where(
            Dependente.titular_id == titular_id,
            Dependente.dependente_id == dep_paciente.id,
        )
        if (await db.execute(stmt_link)).scalars().first() is not None:
            raise VinculoDependenteExistenteError(
                f"O vínculo entre titular '{titular_id}' e dependente "
                f"'{dep_paciente.id}' já está cadastrado."
            )

        vinculo = Dependente(
            titular_id=titular_id,
            dependente_id=dep_paciente.id,
            grau_parentesco=dados.grau_parentesco,
            outorga_tcle=dados.outorga_tcle,
            is_pediatrico=dep_paciente.is_pediatrico(),
        )
        db.add(vinculo)
        await db.commit()

        return DependenteOutputDTO(
            id=vinculo.id,
            titular_id=vinculo.titular_id,
            dependente_id=vinculo.dependente_id,
            grau_parentesco=vinculo.grau_parentesco,
            vinculado_em=vinculo.vinculado_em,
            outorga_tcle=vinculo.outorga_tcle,
        )

    async def listar_dependentes(
        self,
        titular_id: UUID,
        session: "AsyncSession | None" = None,
    ) -> list[DependenteDetalheDTO]:
        """Recupera dependentes vinculados ao titular autenticado (Anti-IDOR).

        Regras: LGPD Art. 11, CFM 1.821/2007, ADR-013.
        Documentação: docs/explanation/domains/identity-domain.md
        """
        db = session or self._session
        if db is None:
            raise ValueError(
                f"AsyncSession não configurada no DependenteService (recebido: {db!r})."
            )

        stmt = (
            select(Dependente, Paciente)
            .join(Paciente, Dependente.dependente_id == Paciente.id)
            .where(Dependente.titular_id == titular_id)
            .order_by(Dependente.vinculado_em.desc())
        )
        rows = (await db.execute(stmt)).all()

        return [
            DependenteDetalheDTO(
                id=vinculo.id,
                titular_id=vinculo.titular_id,
                dependente_id=vinculo.dependente_id,
                grau_parentesco=vinculo.grau_parentesco,
                nome_completo=paciente.nome_completo,
                data_nascimento=paciente.data_nascimento,
                cpf=paciente.cpf,
                cns=paciente.cns,
                vinculado_em=vinculo.vinculado_em,
                outorga_tcle=vinculo.outorga_tcle,
            )
            for vinculo, paciente in rows
        ]
