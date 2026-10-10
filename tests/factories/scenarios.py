"""Composite scenario seeders for end-to-end and integration tests."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from src.core.authz.roles import Role
from src.modules.identity.domain.models import Organizacao, Paciente, Profissional
from src.modules.queue.domain.models import (
    Atendimento,
    PrioridadeClinica,
    StatusAtendimento,
)

from tests.factories.identity import (
    make_organizacao,
    make_paciente,
    make_profissional,
)
from tests.factories.queue import make_atendimento


@dataclass(frozen=True)
class ClinicalScenario:
    """Convenience bundle of persisted entities representing an active clinical flow."""

    organizacao: Organizacao
    paciente: Paciente
    medico: Profissional
    atendimento: Atendimento


async def seed_clinical_scenario(
    session: AsyncSession,
    *,
    org_id: int | None = None,
    org_cnpj: str = "22222222000102",
    org_razao_social: str = "Unidade Básica de Saúde Central",
    org_nome_fantasia: str = "UBS Central",
    paciente_nome: str = "Maria dos Santos",
    paciente_cpf: str = "33333333301",
    medico_nome: str = "Dr. Carlos Plantonista",
    medico_cpf: str = "44444444401",
    medico_email: str = "carlos@medisync.local",
    medico_papel: str = Role.MEDICO,
    medico_crm: str | None = "998877",
    medico_crm_uf: str | None = "SP",
    status_atendimento: str | StatusAtendimento = StatusAtendimento.EM_ATENDIMENTO,
    prioridade_clinica: int | PrioridadeClinica = PrioridadeClinica.NAO_URGENTE,
    tcle_hash: str | None = None,
) -> ClinicalScenario:
    """Seed a coherent clinical graph (Org -> Paciente -> Medico -> Atend)."""
    org = make_organizacao(
        cnpj=org_cnpj,
        razao_social=org_razao_social,
        nome_fantasia=org_nome_fantasia,
        id=org_id,
    )
    session.add(org)
    await session.commit()
    await session.refresh(org)

    paciente = make_paciente(org.id, cpf=paciente_cpf, nome_completo=paciente_nome)
    medico = make_profissional(
        org.id,
        cpf=medico_cpf,
        nome_completo=medico_nome,
        email=medico_email,
        papel=medico_papel,
        crm=medico_crm,
        crm_uf=medico_crm_uf,
    )
    session.add_all([paciente, medico])
    await session.commit()
    await session.refresh(paciente)
    await session.refresh(medico)

    atendimento = make_atendimento(
        organizacao_id=org.id,
        paciente_id=paciente.id,
        medico_id=medico.id,
        status=status_atendimento,
        prioridade_clinica=prioridade_clinica,
        tcle_hash=tcle_hash,
    )
    session.add(atendimento)
    await session.commit()
    await session.refresh(atendimento)

    return ClinicalScenario(
        organizacao=org,
        paciente=paciente,
        medico=medico,
        atendimento=atendimento,
    )


async def seed_multi_tenant_orgs(
    session: AsyncSession,
    *,
    cnpj_a: str = "55667788000199",
    cnpj_b: str = "66778899000111",
) -> tuple[Organizacao, Organizacao]:
    """Seed two isolated organizations for tenant segregation and RLS assertions."""
    org_a = make_organizacao(
        cnpj=cnpj_a, razao_social="Hospital Tenant A", nome_fantasia="Tenant A"
    )
    org_b = make_organizacao(
        cnpj=cnpj_b, razao_social="Unidade Tenant B", nome_fantasia="Tenant B"
    )
    session.add_all([org_a, org_b])
    await session.commit()
    await session.refresh(org_a)
    await session.refresh(org_b)
    return org_a, org_b
