"""Composite scenario seeders for end-to-end and integration tests."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.authz.roles import Role
from src.modules.identity.domain.models import (
    ConfiguracaoUnidade,
    Paciente,
    Profissional,
)
from src.modules.queue.domain.models import (
    Atendimento,
    PrioridadeClinica,
    StatusAtendimento,
)

from tests.factories.identity import (
    make_configuracao_unidade,
    make_paciente,
    make_profissional,
)
from tests.factories.queue import make_atendimento


@dataclass(frozen=True)
class ClinicalScenario:
    """Convenience bundle of persisted entities representing an active clinical flow."""

    configuracao_unidade: ConfiguracaoUnidade
    paciente: Paciente
    medico: Profissional
    atendimento: Atendimento


async def seed_clinical_scenario(
    session: AsyncSession,
    *,
    unidade_cnpj: str = "22222222000102",
    unidade_razao_social: str = "Unidade Básica de Saúde Central",
    unidade_nome_fantasia: str = "UBS Central",
    unidade_cnes: str | None = "2695251",
    unidade_ibge_municipio: str | None = "3550308",
    paciente_nome: str = "Maria dos Santos",
    paciente_cpf: str = "33333333301",
    paciente_telefone: str = "11987654321",
    medico_nome: str = "Dr. Carlos Plantonista",
    medico_cpf: str = "44444444401",
    medico_email: str = "carlos@medisync.local",
    medico_papel: str = Role.MEDICO,
    medico_crm: str | None = "998877",
    medico_crm_uf: str | None = "SP",
    status_atendimento: str | StatusAtendimento = StatusAtendimento.EM_ATENDIMENTO,
    prioridade_clinica: int | PrioridadeClinica = PrioridadeClinica.NAO_URGENTE,
    tcle_hash: str | None = "a" * 64,
) -> ClinicalScenario:
    """Seed a coherent clinical graph (Unidade -> Paciente -> Medico -> Atend)."""
    res = await session.execute(select(ConfiguracaoUnidade).limit(1))
    unidade = res.scalar_one_or_none()
    if unidade is None:
        unidade = make_configuracao_unidade(
            cnpj=unidade_cnpj,
            razao_social=unidade_razao_social,
            nome_fantasia=unidade_nome_fantasia,
            cnes=unidade_cnes,
            ibge_municipio=unidade_ibge_municipio,
        )
        session.add(unidade)
        await session.commit()
        await session.refresh(unidade)

    paciente = make_paciente(
        cpf=paciente_cpf,
        nome_completo=paciente_nome,
        telefone=paciente_telefone,
    )
    medico = make_profissional(
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
        configuracao_unidade=unidade,
        paciente=paciente,
        medico=medico,
        atendimento=atendimento,
    )
