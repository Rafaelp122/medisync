"""SQLAlchemy read adapter for identity lookups without exposing ORM models."""

from collections.abc import Sequence
from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import ConflictError, NotFoundError, ValidationError
from src.modules.identity.application.ports.identity_reader_port import (
    IdentityDirectoryDTO,
    IdentityReaderPort,
    PacienteAuthLookupData,
    PacienteAuthLookupDTO,
    PacientePasskeyData,
    PacientePasskeyDTO,
)
from src.modules.identity.domain.models import (
    ConfiguracaoUnidade,
    Paciente,
    PacientePasskey,
    Profissional,
)


def _to_lookup_data(pac: Paciente) -> PacienteAuthLookupData:
    return PacienteAuthLookupData(
        id=pac.id,
        telefone=pac.telefone,
        cpf=pac.cpf,
        nome_completo=pac.nome_completo or "",
        nome_mae=pac.nome_mae,
        cns=pac.cns,
        data_nascimento=pac.data_nascimento,
    )


def _to_passkey_data(passkey: PacientePasskey) -> PacientePasskeyData:
    """Convert ORM PacientePasskey model to immutable DTO across boundaries."""
    return PacientePasskeyData(
        id=passkey.id,
        paciente_id=passkey.paciente_id,
        credential_id=passkey.credential_id,
        public_key=passkey.public_key,
        sign_count=passkey.sign_count,
        device_name=passkey.device_name,
    )


class SqlIdentityReader(IdentityReaderPort):
    """Chainable ORM identity reader encapsulating identity tables (CQRS read-only)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def obter_dados_diretorio(
        self,
        medico_id: UUID,
        paciente_id: UUID,
    ) -> IdentityDirectoryDTO:
        """Fetch singleton clinical unit configuration, doctor, and patient details."""
        stmt_unidade = select(ConfiguracaoUnidade).limit(1)
        unidade = (await self._session.execute(stmt_unidade)).scalar_one_or_none()
        org_nome = "MediSync Pronto-Atendimento Virtual"
        org_cnpj: str | None = None
        cnes: str | None = None
        if unidade is not None:
            org_nome = unidade.nome_fantasia or unidade.razao_social or org_nome
            org_cnpj = unidade.cnpj
            cnes = unidade.cnes

        stmt_prof = select(Profissional).where(Profissional.id == medico_id)
        prof = (await self._session.execute(stmt_prof)).scalar_one_or_none()
        if prof is None:
            raise NotFoundError(f"Profissional médico '{medico_id}' não encontrado.")

        stmt_pac = select(Paciente).where(Paciente.id == paciente_id)
        pac = (await self._session.execute(stmt_pac)).scalar_one_or_none()
        if pac is None:
            raise NotFoundError(
                f"Paciente '{paciente_id}' não encontrado na plataforma."
            )

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
            paciente_nome_social=pac.nome_social,
            cnes=cnes,
        )

    async def obter_modo_sus(self) -> bool:
        """Read public SUS mode flag from singleton ConfiguracaoUnidade."""
        stmt = select(ConfiguracaoUnidade.modo_publico_sus).limit(1)
        modo = (await self._session.execute(stmt)).scalar_one_or_none()
        return bool(modo) if modo is not None else False

    async def buscar_paciente_por_telefone(
        self,
        telefone: str,
        cpf: str | None = None,
    ) -> PacienteAuthLookupDTO | None:
        """Look up patient authentication record by verified phone and optional CPF."""
        stmt = select(Paciente).where(Paciente.telefone == telefone)
        if cpf is not None:
            stmt = stmt.where(Paciente.cpf == cpf)

        pac = (await self._session.execute(stmt)).scalars().first()
        if pac is None:
            return None
        return _to_lookup_data(pac)

    async def buscar_paciente_cadsus(
        self,
        cpf: str | None = None,
        data_nascimento: date | None = None,
        cns: str | None = None,
        nome_mae: str | None = None,
    ) -> PacienteAuthLookupDTO | None:
        """Localiza paciente por CPF/CNS e critérios civis evitando query ambígua.

        Regras: RN-AUT-09, LGPD Art. 11, docs/explanation/domains/identity-domain.md
        """
        clean_cpf = cpf.strip() if cpf and cpf.strip() else None
        clean_cns = cns.strip() if cns and cns.strip() else None
        if clean_cpf is None and clean_cns is None:
            raise ValidationError(
                "Consulta CADSUS requer ao menos CPF ou CNS informado "
                f"(recebido cpf={cpf!r}, cns={cns!r})."
            )

        stmt = select(Paciente)
        if clean_cpf is not None:
            stmt = stmt.where(Paciente.cpf == clean_cpf)
        if clean_cns is not None:
            stmt = stmt.where(Paciente.cns == clean_cns)
        if data_nascimento is not None:
            stmt = stmt.where(Paciente.data_nascimento == data_nascimento)
        if nome_mae is not None and nome_mae.strip():
            stmt = stmt.where(func.lower(Paciente.nome_mae) == nome_mae.strip().lower())

        rows = (await self._session.execute(stmt.limit(2))).scalars().all()
        if not rows:
            return None
        if len(rows) > 1:
            raise ConflictError(
                "Consulta CADSUS retornou múltiplos registros ambíguos; "
                "informe CPF ou CNS único junto ao segundo fator civil."
            )
        return _to_lookup_data(rows[0])

    async def buscar_paciente_por_id(
        self,
        paciente_id: UUID,
    ) -> PacienteAuthLookupDTO | None:
        """Recupera dados civis do paciente por ID para descritor FIDO2.

        Regras: RF-01, ADR-005, ADR-013 e
        docs/user-stories/US-14-biometria-passkeys-webauthn.md.
        """
        stmt = select(Paciente).where(Paciente.id == paciente_id)
        pac = (await self._session.execute(stmt)).scalar_one_or_none()
        if pac is None:
            return None
        return _to_lookup_data(pac)

    async def buscar_passkey_por_credencial(
        self,
        credential_id: str,
    ) -> PacientePasskeyDTO | None:
        """Localiza credencial Passkey ativa por credential_id.

        Regras: RF-01, ADR-005, ADR-013 e
        docs/user-stories/US-14-biometria-passkeys-webauthn.md.
        """
        stmt = select(PacientePasskey).where(
            PacientePasskey.credential_id == credential_id
        )
        passkey = (await self._session.execute(stmt)).scalar_one_or_none()
        if passkey is None:
            return None
        return _to_passkey_data(passkey)

    async def listar_passkeys_paciente(
        self,
        paciente_id: UUID,
    ) -> Sequence[PacientePasskeyDTO]:
        """Lista todas as Passkeys registradas pelo paciente na plataforma.

        Regras: RF-01, ADR-005, ADR-013 e
        docs/user-stories/US-14-biometria-passkeys-webauthn.md.
        """
        stmt = (
            select(PacientePasskey)
            .where(PacientePasskey.paciente_id == paciente_id)
            .order_by(PacientePasskey.created_at.desc())
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_passkey_data(r) for r in rows]
