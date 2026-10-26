"""Script idempotente de povoamento (seed) para ambiente de desenvolvimento local."""

import asyncio
import logging
from datetime import date

from sqlalchemy import select
from src.core.context import set_current_tenant_id
from src.core.database import async_session_factory
from src.modules.identity.domain.models import Organizacao, Paciente

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("medisync.seed_dev")


async def main() -> None:
    set_current_tenant_id(1)
    async with async_session_factory() as session:
        # 1. Garante Organização Tenant 1
        stmt_org = select(Organizacao).where(Organizacao.id == 1)
        res_org = await session.execute(stmt_org)
        org = res_org.scalar_one_or_none()

        if org is None:
            logger.info("Criando organização de demonstração (Tenant 1)...")
            org = Organizacao(
                id=1,
                cnpj="11223344000188",
                razao_social="Hospital Municipal MediSync",
                nome_fantasia="MediSync Demo",
                modo_publico_sus=True,
                ativo=True,
            )
            session.add(org)
            await session.commit()
            logger.info("Organização Tenant 1 criada com sucesso.")
        else:
            logger.info("Organização Tenant 1 já existente: %s", org.razao_social)

        # 2. Garante Pacientes de Teste
        pacientes_demo = [
            {
                "nome_completo": "Juliana Silva",
                "cpf": "11144477735",
                "telefone": "11987654321",
                "data_nascimento": date(1990, 5, 20),
            },
            {
                "nome_completo": "Rafael Paciente",
                "cpf": "22233344455",
                "telefone": "21975118173",
                "data_nascimento": date(1988, 10, 15),
            },
        ]

        for dados in pacientes_demo:
            stmt_pac = select(Paciente).where(
                Paciente.organizacao_id == 1,
                Paciente.telefone == dados["telefone"],
            )
            res_pac = await session.execute(stmt_pac)
            pac = res_pac.scalar_one_or_none()

            if pac is None:
                logger.info(
                    "Criando paciente demo '%s' (%s)...",
                    dados["nome_completo"],
                    dados["telefone"],
                )
                pac = Paciente(
                    organizacao_id=1,
                    nome_completo=dados["nome_completo"],
                    cpf=dados["cpf"],
                    telefone=dados["telefone"],
                    data_nascimento=dados["data_nascimento"],
                )
                session.add(pac)
                await session.commit()
                logger.info("Paciente '%s' criado com sucesso.", dados["nome_completo"])
            else:
                logger.info(
                    "Paciente '%s' (%s) já existente.", pac.nome_completo, pac.telefone
                )

    logger.info("Seed de desenvolvimento finalizado com sucesso!")


if __name__ == "__main__":
    asyncio.run(main())
