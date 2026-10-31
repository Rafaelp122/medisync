"""Application service orchestrating progressive 2-phase patient onboarding."""

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import ColumnElement, or_, select

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
    validate_sexo_biologico,
    validate_tcle_hash,
    validate_telefone,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class OnboardingService:
    """Orquestra o acolhimento progressivo em duas fases (rápido e regulatório).

    Regras: RN07 (TCLE), LGPD Art. 11 (tratamento de dados de saúde), CFM 1.821/2007.
    Documentação: docs/explanation/domains/identity-domain.md
    """

    def __init__(
        self,
        session: "AsyncSession | None" = None,
        secret_key: str | None = None,
    ) -> None:
        self._session = session
        self._secret_key = (
            secret_key or "dev-insecure-secret-key-change-in-production-min-32-chars"
        )

    async def realizar_fase_1(
        self,
        organizacao_id: int,
        dados: Fase1InputDTO,
        session: "AsyncSession | None" = None,
    ) -> Fase1OutputDTO:
        """Executa acolhimento rápido Fase 1 em <45 segundos emitindo token provisório.

        Regras: RN07 (TCLE), LGPD Art. 11, NEC-01.
        Documentação: docs/explanation/domains/identity-domain.md
        """
        db = session or self._session
        if db is None:
            raise ValueError("AsyncSession não configurada no OnboardingService.")
        if organizacao_id <= 0:
            raise TenantInvalidoError(
                f"Identificador da organização '{organizacao_id}' deve ser "
                "positivo; esperado valor > 0."
            )

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
            raise ValidationError(
                f"Data de nascimento '{dados.data_nascimento}' não pode estar no "
                f"futuro (hoje: {date.today()})."
            )

        queixa = dados.queixa_principal.strip()
        if len(queixa) < 3:
            raise ValidationError(
                f"Queixa principal '{queixa}' muito curta ({len(queixa)} chars); "
                "esperado ao menos 3 caracteres descritivos."
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
        result = await db.execute(stmt)
        paciente = result.scalars().first()

        is_novo = False
        nome = dados.nome_completo.strip()
        nome_social = dados.nome_social.strip() if dados.nome_social else None
        if paciente is None:
            # Create new patient
            paciente = Paciente(
                organizacao_id=organizacao_id,
                data_nascimento=dados.data_nascimento,
                telefone=clean_telefone,
                cpf=clean_cpf,
                cns=clean_cns,
                nome_completo=nome,
                nome_social=nome_social,
            )
            db.add(paciente)
            is_novo = True
        else:
            # Update contact info and name if empty or changed
            paciente.telefone = clean_telefone
            if nome:
                paciente.nome_completo = nome
            if nome_social:
                paciente.nome_social = nome_social

        await db.commit()

        token = create_intake_token(
            paciente_id=paciente.id,
            organizacao_id=organizacao_id,
            secret_key=self._secret_key,
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
        organizacao_id: int,
        dados: Fase2InputDTO,
        session: "AsyncSession | None" = None,
    ) -> Fase2OutputDTO:
        """Executa enriquecimento cadastral e clínico da Fase 2 sob normas regulatórias.

        Regras: CFM 1.821/2007 (prontuário eletrônico), LGPD Art. 11.
        Documentação: docs/explanation/domains/identity-domain.md
        """
        db = session or self._session
        if db is None:
            raise ValueError("AsyncSession não configurada no OnboardingService.")
        if organizacao_id <= 0:
            raise TenantInvalidoError(
                f"Identificador da organização '{organizacao_id}' deve ser "
                "positivo; esperado valor > 0."
            )

        # 1. Regulatory validations
        clean_nome_mae = validate_nome_mae(dados.nome_mae)
        clean_cep = validate_cep(dados.cep)
        clean_sexo = validate_sexo_biologico(dados.sexo_biologico)

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
                f"Sigla de estado (UF) '{estado}' inválida ({len(estado)} chars); "
                "esperado exatamente 2 caracteres."
            )

        # 2. Retrieve patient
        stmt = select(Paciente).where(
            Paciente.id == dados.paciente_id,
            Paciente.organizacao_id == organizacao_id,
        )
        result = await db.execute(stmt)
        paciente = result.scalars().first()

        if paciente is None:
            raise PacienteNaoEncontradoError(
                f"Paciente '{dados.paciente_id}' não encontrado na "
                f"organização '{organizacao_id}'."
            )

        # 3. Enrich patient fields via rich domain model (CFM 1.821/2007)
        paciente.completar_fase_2(
            nome_mae=clean_nome_mae,
            sexo_biologico=clean_sexo,
            cep=clean_cep,
            logradouro=logradouro,
            numero=numero,
            bairro=bairro,
            cidade=cidade,
            estado=estado,
            nome_social=dados.nome_social,
            alergias=dados.alergias,
        )

        await db.commit()

        return Fase2OutputDTO(
            paciente_id=paciente.id,
            nome_completo=paciente.nome_completo,
            nome_social=paciente.nome_social,
            nome_mae=paciente.nome_mae or clean_nome_mae,
            sexo_biologico=paciente.sexo_biologico or clean_sexo,
            cep=paciente.cep or clean_cep,
            logradouro=paciente.logradouro or logradouro,
            numero=paciente.numero or numero,
            bairro=paciente.bairro or bairro,
            cidade=paciente.cidade or cidade,
            estado=paciente.estado or estado,
            alergias=list(paciente.alergias),
            status="DADOS_COMPLETOS",
        )
