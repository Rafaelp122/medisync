"""Application service orchestrating progressive 2-phase patient onboarding."""

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import ColumnElement, or_, select

from src.core.config import get_settings
from src.core.errors import ValidationError
from src.core.security import create_intake_token
from src.modules.identity.application.dtos import (
    Fase1InputDTO,
    Fase1OutputDTO,
    Fase2InputDTO,
    Fase2OutputDTO,
)
from src.modules.identity.domain.exceptions import (
    IdentificacaoObrigatoriaError,
    PacienteNaoEncontradoError,
    TenantInvalidoError,
)
from src.modules.identity.domain.models import Paciente
from src.modules.identity.domain.validators import (
    validate_cep,
    validate_cns,
    validate_cpf,
    validate_nome_mae,
    validate_tcle_hash,
    validate_telefone,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class OnboardingService:
    """Application service coordinating the two-phase onboarding workflow."""

    async def realizar_fase_1(
        self,
        session: "AsyncSession",
        organizacao_id: int,
        dados: Fase1InputDTO,
    ) -> Fase1OutputDTO:
        """Execute Phase 1 rapid intake in under 45 seconds (NEC-01)."""
        if organizacao_id <= 0:
            raise TenantInvalidoError("Identificador da organização deve ser positivo.")

        # 1. Mandatory input validations
        clean_cpf = validate_cpf(dados.cpf) if dados.cpf else None
        clean_cns = validate_cns(dados.cns) if dados.cns else None
        if not clean_cpf and not clean_cns:
            raise IdentificacaoObrigatoriaError(
                "Obrigatório informar CPF ou CNS válido para acolhimento do paciente."
            )

        clean_telefone = validate_telefone(dados.telefone)
        _ = validate_tcle_hash(dados.tcle_hash)

        if dados.data_nascimento > date.today():
            raise ValidationError("Data de nascimento não pode estar no futuro.")

        queixa = dados.queixa_principal.strip()
        if len(queixa) < 3:
            raise ValidationError(
                "Queixa principal deve conter ao menos 3 caracteres descritivos."
            )

        # 2. Check for existing patient record in this organization
        conditions: list[ColumnElement[bool]] = []
        if clean_cpf:
            conditions.append(Paciente.cpf == clean_cpf)
        if clean_cns:
            conditions.append(Paciente.cns == clean_cns)

        stmt = select(Paciente).where(
            Paciente.organizacao_id == organizacao_id,
            or_(*conditions),
        )
        result = await session.execute(stmt)
        paciente = result.scalars().first()

        is_novo = False
        nome = dados.nome_completo.strip()
        if paciente is None:
            # Create new patient
            paciente = Paciente(
                organizacao_id=organizacao_id,
                data_nascimento=dados.data_nascimento,
                telefone=clean_telefone,
                cpf=clean_cpf,
                cns=clean_cns,
                nome_completo=nome,
            )
            session.add(paciente)
            is_novo = True
        else:
            # Update contact info and name if empty or changed
            paciente.telefone = clean_telefone
            if nome:
                paciente.nome_completo = nome

        await session.commit()
        await session.refresh(paciente)

        # 3. Generate provisional intake token
        settings = get_settings()
        token = create_intake_token(
            paciente_id=paciente.id,
            organizacao_id=organizacao_id,
            secret_key=settings.SECRET_KEY,
            expires_in_seconds=7200,  # 2 hours validity
        )

        return Fase1OutputDTO(
            paciente_id=paciente.id,
            token=token,
            status="TRIADO_AGUARDANDO_ELEGIBILIDADE",
            mensagem="Acolhimento registrado com sucesso. Prossiga para a Fase 2.",
            is_novo_paciente=is_novo,
        )

    async def realizar_fase_2(
        self,
        session: "AsyncSession",
        organizacao_id: int,
        dados: Fase2InputDTO,
    ) -> Fase2OutputDTO:
        """Execute Phase 2 clinical record enrichment (CFM 1.821/2007)."""
        if organizacao_id <= 0:
            raise TenantInvalidoError("Identificador da organização deve ser positivo.")

        # 1. Regulatory validations
        clean_nome_mae = validate_nome_mae(dados.nome_mae)
        clean_cep = validate_cep(dados.cep)

        sexo = dados.sexo_biologico.strip().upper()
        if sexo not in ("M", "F"):
            raise ValidationError(
                "Sexo biológico inválido: deve ser 'M' (Masculino) ou 'F' (Feminino)."
            )

        logradouro = dados.logradouro.strip()
        numero = dados.numero.strip()
        bairro = dados.bairro.strip()
        cidade = dados.cidade.strip()
        estado = dados.estado.strip().upper()

        if not logradouro or not numero or not bairro or not cidade or not estado:
            raise ValidationError(
                "Endereço incompleto: logradouro, número, bairro, cidade e estado "
                "são mandatórios conforme CFM 1.821/2007."
            )

        if len(estado) != 2:
            raise ValidationError(
                "Sigla de estado (UF) inválida: deve conter exatamente 2 caracteres."
            )

        # 2. Retrieve patient
        stmt = select(Paciente).where(
            Paciente.id == dados.paciente_id,
            Paciente.organizacao_id == organizacao_id,
        )
        result = await session.execute(stmt)
        paciente = result.scalars().first()

        if paciente is None:
            raise PacienteNaoEncontradoError(
                f"Paciente '{dados.paciente_id}' não encontrado nesta organização."
            )

        # 3. Enrich patient fields
        paciente.nome_mae = clean_nome_mae
        paciente.sexo_biologico = sexo
        paciente.cep = clean_cep
        paciente.logradouro = logradouro
        paciente.numero = numero
        paciente.bairro = bairro
        paciente.cidade = cidade
        paciente.estado = estado

        # Clean allergies
        clean_alergias = [a.strip() for a in dados.alergias if a.strip()]
        paciente.alergias = clean_alergias

        await session.commit()
        await session.refresh(paciente)

        return Fase2OutputDTO(
            paciente_id=paciente.id,
            nome_completo=paciente.nome_completo,
            nome_mae=clean_nome_mae,
            sexo_biologico=sexo,
            cep=clean_cep,
            logradouro=logradouro,
            numero=numero,
            bairro=bairro,
            cidade=cidade,
            estado=estado,
            alergias=clean_alergias,
            status="DADOS_COMPLETOS",
        )
