"""Application service managing pediatric and legal dependent linkages."""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ColumnElement, or_, select

from src.core.errors import ValidationError
from src.modules.identity.application.dtos import (
    CriarDependenteDTO,
    DependenteDetalheDTO,
    DependenteOutputDTO,
)
from src.modules.identity.domain.exceptions import (
    DependenteAutoReferenciaError,
    IdentificacaoObrigatoriaError,
    PacienteNaoEncontradoError,
    TenantInvalidoError,
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
    """Application service governing patient dependent relationships."""

    def __init__(self, session: "AsyncSession | None" = None) -> None:
        self._session = session

    async def adicionar_dependente(
        self,
        organizacao_id: int,
        titular_id: UUID,
        dados: CriarDependenteDTO,
        session: "AsyncSession | None" = None,
    ) -> DependenteOutputDTO:
        """Register a dependent relationship with strict anti-reflexive validation."""
        db = session or self._session
        if db is None:
            raise ValueError("AsyncSession não configurada no DependenteService.")
        if organizacao_id <= 0:
            raise TenantInvalidoError("Identificador da organização deve ser positivo.")

        # 1. Verify titular patient exists
        stmt_titular = select(Paciente).where(
            Paciente.id == titular_id,
            Paciente.organizacao_id == organizacao_id,
        )
        result_titular = await db.execute(stmt_titular)
        titular = result_titular.scalars().first()
        if titular is None:
            raise PacienteNaoEncontradoError(
                f"Paciente titular '{titular_id}' não encontrado nesta organização."
            )

        # 2. Resolve dependent entity
        dep_id: UUID
        if dados.dependente_id is not None:
            dep_id = dados.dependente_id
            if dep_id == titular_id:
                raise DependenteAutoReferenciaError()

            # Verify target dependent exists in tenant
            stmt_dep = select(Paciente).where(
                Paciente.id == dep_id,
                Paciente.organizacao_id == organizacao_id,
            )
            result_dep = await db.execute(stmt_dep)
            dep_paciente = result_dep.scalars().first()
            if dep_paciente is None:
                raise PacienteNaoEncontradoError(
                    f"Paciente dependente '{dep_id}' não encontrado nesta organização."
                )
        else:
            # Create new patient record for the dependent
            if not dados.nome_completo or not dados.data_nascimento:
                raise ValidationError(
                    "Nome completo e data de nascimento são mandatórios "
                    "para cadastrar um novo dependente."
                )

            clean_cpf = validate_cpf(dados.cpf) if dados.cpf else None
            clean_cns = validate_cns(dados.cns) if dados.cns else None

            # CFM/SUS rule: At least CPF or CNS is mandatory for any patient
            if not clean_cpf and not clean_cns:
                raise IdentificacaoObrigatoriaError(
                    "Obrigatório fornecer CPF ou CNS válido para o dependente "
                    "(CFM/SUS)."
                )

            # Check if patient already exists in this organization
            conditions: list[ColumnElement[bool]] = []
            if clean_cpf:
                conditions.append(Paciente.cpf == clean_cpf)
            if clean_cns:
                conditions.append(Paciente.cns == clean_cns)

            stmt_exist = select(Paciente).where(
                Paciente.organizacao_id == organizacao_id,
                or_(*conditions),
            )
            res_exist = await db.execute(stmt_exist)
            existing_dep = res_exist.scalars().first()

            if existing_dep is not None:
                dep_id = existing_dep.id
            else:
                # Use titular's telephone if not provided
                telefone_dep = (
                    validate_telefone(dados.telefone)
                    if dados.telefone
                    else titular.telefone
                )

                novo_dep = Paciente(
                    organizacao_id=organizacao_id,
                    data_nascimento=dados.data_nascimento,
                    telefone=telefone_dep,
                    cpf=clean_cpf,
                    cns=clean_cns,
                    nome_completo=dados.nome_completo.strip(),
                )
                db.add(novo_dep)
                await db.flush()
                dep_id = novo_dep.id

            if dep_id == titular_id:
                raise DependenteAutoReferenciaError()

        # 3. Check for existing linkage
        stmt_link = select(Dependente).where(
            Dependente.organizacao_id == organizacao_id,
            Dependente.titular_id == titular_id,
            Dependente.dependente_id == dep_id,
        )
        result_link = await db.execute(stmt_link)
        if result_link.scalars().first() is not None:
            raise VinculoDependenteExistenteError()

        # 4. Create and persist linkage
        vinculo = Dependente(
            organizacao_id=organizacao_id,
            titular_id=titular_id,
            dependente_id=dep_id,
            grau_parentesco=dados.grau_parentesco,
        )
        db.add(vinculo)
        await db.commit()
        await db.refresh(vinculo)

        return DependenteOutputDTO(
            id=vinculo.id,
            organizacao_id=vinculo.organizacao_id,
            titular_id=vinculo.titular_id,
            dependente_id=vinculo.dependente_id,
            grau_parentesco=vinculo.grau_parentesco,
            vinculado_em=vinculo.vinculado_em,
        )

    async def listar_dependentes(
        self,
        organizacao_id: int,
        titular_id: UUID,
        session: "AsyncSession | None" = None,
    ) -> list[DependenteDetalheDTO]:
        """Fetch all dependents linked to a titular patient."""
        db = session or self._session
        if db is None:
            raise ValueError("AsyncSession não configurada no DependenteService.")
        if organizacao_id <= 0:
            raise TenantInvalidoError("Identificador da organização deve ser positivo.")

        stmt = (
            select(Dependente, Paciente)
            .join(Paciente, Dependente.dependente_id == Paciente.id)
            .where(
                Dependente.organizacao_id == organizacao_id,
                Dependente.titular_id == titular_id,
            )
            .order_by(Dependente.vinculado_em.desc())
        )
        result = await db.execute(stmt)
        rows = result.all()

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
            )
            for vinculo, paciente in rows
        ]
