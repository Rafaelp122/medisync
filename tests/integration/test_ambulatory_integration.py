"""Integration tests for ambulatory BPA-I integrity, idempotency, and directory."""

import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.audit.models import AtorPapel, AuditEvent
from src.core.authz.roles import Role
from src.core.database import get_session_factory
from src.modules.ambulatory.application.dtos import ConsolidarTeleconsultaCommand
from src.modules.ambulatory.composition import build_producao_ambulatorial_service
from src.modules.ambulatory.domain.models.producao_ambulatorial import (
    ProducaoAmbulatorial,
)
from src.modules.ambulatory.infrastructure.adapters.sql_bpa_directory import (
    SqlBpaDirectory,
)
from src.modules.queue.domain.models import Atendimento, StatusAtendimento
from src.modules.scheduling.domain.models import EspecialidadeAgenda

from tests.factories.identity import (
    make_configuracao_unidade,
    make_paciente,
    make_profissional,
)
from tests.factories.queue import make_atendimento
from tests.factories.scenarios import seed_clinical_scenario
from tests.helpers import auth_headers

if TYPE_CHECKING:
    from src.modules.identity.domain.models import (
        ConfiguracaoUnidade,
        Paciente,
        Profissional,
    )

pytestmark = pytest.mark.usefixtures("clean_db")


@pytest.mark.asyncio
async def test_consolidar_teleconsulta_concorrente_e_flush_only_postgres(
    db_session: AsyncSession,
) -> None:
    """Resolve 23505 na concorrência e preserva tx externa com auto_commit=False."""
    cenario = await seed_clinical_scenario(
        db_session,
        unidade_cnpj="12345678000199",
        paciente_cpf="11122233301",
        medico_cpf="44455566601",
        medico_email="bpa-tx@medisync.local",
        status_atendimento=StatusAtendimento.CONCLUIDO,
    )
    atend_id = cenario.atendimento.id
    med_id = cenario.medico.id
    pac_id = cenario.paciente.id

    # 1. auto_commit=False não commita prematuramente até o caller commitar
    async with get_session_factory()() as s1:
        svc1 = build_producao_ambulatorial_service(session=s1)
        cmd = ConsolidarTeleconsultaCommand(
            atendimento_id=atend_id,
            profissional_id=med_id,
            paciente_id=pac_id,
            cnes="2695251",
        )
        prod_flush = await svc1.consolidar_teleconsulta(cmd, auto_commit=False)

        async with get_session_factory()() as s_other:
            visivel_antes = (
                await s_other.execute(
                    select(ProducaoAmbulatorial).where(
                        ProducaoAmbulatorial.atendimento_id == atend_id
                    )
                )
            ).scalar_one_or_none()
            assert visivel_antes is None

        await s1.commit()

    # 2. Auditoria gravada com WORKER_ARQ válido no PostgreSQL
    async with get_session_factory()() as s_verify:
        evt = (
            await s_verify.execute(
                select(AuditEvent).where(
                    AuditEvent.atendimento_id == atend_id,
                    AuditEvent.tipo_evento == "PRODUCAO_AMBULATORIAL_CONSOLIDADA",
                )
            )
        ).scalar_one()
        assert evt.ator_papel == AtorPapel.WORKER_ARQ.value

    # 3. Colisão concorrente (23505) em novo atendimento devolve único registro
    atend_2 = make_atendimento(
        paciente_id=pac_id,
        medico_id=med_id,
        status=StatusAtendimento.CONCLUIDO,
        tcle_hash="b" * 64,
    )
    db_session.add(atend_2)
    await db_session.commit()

    async def _consolidar_concorrente() -> str:
        async with get_session_factory()() as sx:
            svcx = build_producao_ambulatorial_service(session=sx)
            res = await svcx.consolidar_teleconsulta(
                ConsolidarTeleconsultaCommand(
                    atendimento_id=atend_2.id,
                    profissional_id=med_id,
                    paciente_id=pac_id,
                    cnes="2695251",
                )
            )
            return str(res.id)

    ids = await asyncio.gather(*[_consolidar_concorrente() for _ in range(4)])
    assert len(set(ids)) == 1
    assert prod_flush.id != atend_2.id

    async with get_session_factory()() as s_count:
        total = (
            await s_count.execute(
                select(func.count())
                .select_from(ProducaoAmbulatorial)
                .where(ProducaoAmbulatorial.atendimento_id == atend_2.id)
            )
        ).scalar_one()
        assert total == 1

    # 4. Colisão 23505 com auto_commit=False preserva mutação pendente na sessão externa
    async with get_session_factory()() as s_outer:
        atend_obj = (
            await s_outer.execute(
                select(Atendimento).where(Atendimento.id == atend_2.id)
            )
        ).scalar_one()
        atend_obj.tcle_hash = "d" * 64
        await s_outer.flush()

        svc_outer = build_producao_ambulatorial_service(session=s_outer)
        orig_buscar = svc_outer._buscar_por_atendimento  # pyright: ignore[reportPrivateUsage]
        chamadas = 0

        async def _miss_primeira_vez(aid: object) -> ProducaoAmbulatorial | None:
            nonlocal chamadas
            chamadas += 1
            if chamadas == 1:
                return None
            return await orig_buscar(aid)  # type: ignore[arg-type]

        svc_outer._buscar_por_atendimento = _miss_primeira_vez  # type: ignore[method-assign]  # pyright: ignore[reportPrivateUsage]
        existente = await svc_outer.consolidar_teleconsulta(
            ConsolidarTeleconsultaCommand(
                atendimento_id=atend_2.id,
                profissional_id=med_id,
                paciente_id=pac_id,
                cnes="2695251",
            ),
            auto_commit=False,
        )
        assert str(existente.id) == ids[0]
        assert chamadas == 2
        await s_outer.commit()

    async with get_session_factory()() as s_check:
        refreshed = (
            await s_check.execute(
                select(Atendimento).where(Atendimento.id == atend_2.id)
            )
        ).scalar_one()
        assert refreshed.tcle_hash == "d" * 64


@pytest.mark.asyncio
async def test_sql_bpa_directory_e_exportar_bpa_real_postgres(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate SqlBpaDirectory and GET /exportar fidelity against real PostgreSQL."""
    unidade: ConfiguracaoUnidade = make_configuracao_unidade(
        cnpj="11222333000144",
        razao_social="Unidade Municipal de Telessaúde",
        nome_fantasia="UPA Digital Central",
        cnes="2695251",
        ibge_municipio="355030",
    )
    medico: Profissional = make_profissional(
        cpf="55544433322",
        nome_completo="Dra. Ana Médica",
        email="ana.bpa@medisync.local",
        papel=Role.MEDICO,
        crm="112233",
        crm_uf="SP",
    )
    # Lactente com idade == 0 e apenas CPF (cns ausente)
    lactente: Paciente = make_paciente(
        cpf="98765432100",
        cns=None,
        data_nascimento=date(2026, 6, 1),
        nome_completo="Bebe da Silva",
        telefone="11999990001",
    )
    # Adulto nascido em 2000-01-01 com CNS válido (sem CPF)
    nasc_2000: Paciente = make_paciente(
        cpf=None,
        cns="700000000000005",
        data_nascimento=date(2000, 1, 1),
        nome_completo="Carlos Milenio",
        telefone="11999990002",
    )
    # Adulto para nutrição
    pac_nutri: Paciente = make_paciente(
        cpf="12312312399",
        cns="700000000000006",
        data_nascimento=date(1992, 5, 20),
        nome_completo="Paula Nutricao",
        telefone="11999990003",
    )
    db_session.add_all([unidade, medico, lactente, nasc_2000, pac_nutri])
    await db_session.flush()

    atend_lactente = Atendimento(
        paciente_id=lactente.id,
        medico_id=medico.id,
        status=StatusAtendimento.CONCLUIDO,
        tcle_hash="a" * 64,
    )
    atend_2000 = Atendimento(
        paciente_id=nasc_2000.id,
        medico_id=medico.id,
        status=StatusAtendimento.CONCLUIDO,
        tcle_hash="b" * 64,
    )
    atend_nutri = Atendimento(
        paciente_id=pac_nutri.id,
        medico_id=medico.id,
        status=StatusAtendimento.CONCLUIDO,
        tcle_hash="c" * 64,
    )
    db_session.add_all([atend_lactente, atend_2000, atend_nutri])
    await db_session.flush()

    slot_base = datetime(2026, 11, 10, 10, 0, tzinfo=UTC)
    await db_session.execute(
        text(
            """
            INSERT INTO agendamentos (
                id, paciente_id, profissional_id, especialidade,
                slot_inicio, slot_fim, status, atendimento_id
            ) VALUES
                (:id1, :pac1, :med, :esp1, :ini1, :fim1, 'CONCLUIDO', :atend1),
                (:id2, :pac2, :med, :esp2, :ini2, :fim2, 'CONCLUIDO', :atend2)
            """
        ),
        {
            "id1": uuid4(),
            "pac1": nasc_2000.id,
            "med": medico.id,
            "esp1": EspecialidadeAgenda.PSICOLOGIA.value,
            "ini1": slot_base,
            "fim1": slot_base + timedelta(minutes=50),
            "atend1": atend_2000.id,
            "id2": uuid4(),
            "pac2": pac_nutri.id,
            "esp2": EspecialidadeAgenda.NUTRICAO.value,
            "ini2": slot_base + timedelta(hours=1),
            "fim2": slot_base + timedelta(hours=1, minutes=30),
            "atend2": atend_nutri.id,
        },
    )

    p1 = ProducaoAmbulatorial(
        atendimento_id=atend_lactente.id,
        profissional_id=medico.id,
        paciente_id=lactente.id,
        cnes="2695251",
        competencia="202611",
        consolidado_em=datetime(2026, 11, 10, 12, 0, tzinfo=UTC),
    )
    p2 = ProducaoAmbulatorial(
        atendimento_id=atend_2000.id,
        profissional_id=medico.id,
        paciente_id=nasc_2000.id,
        cnes="2695251",
        competencia="202611",
        consolidado_em=datetime(2026, 11, 10, 13, 0, tzinfo=UTC),
    )
    p3 = ProducaoAmbulatorial(
        atendimento_id=atend_nutri.id,
        profissional_id=medico.id,
        paciente_id=pac_nutri.id,
        cnes="2695251",
        competencia="202611",
        consolidado_em=datetime(2026, 11, 10, 14, 0, tzinfo=UTC),
    )
    db_session.add_all([p1, p2, p3])
    await db_session.commit()

    directory = SqlBpaDirectory(db_session)
    detalhes = await directory.buscar_detalhes_bpa_lote("202611")
    assert len(detalhes) == 3

    d_lac, d_2000, d_nutri = detalhes
    assert d_lac.idade == 0
    assert d_lac.paciente_cns is None
    assert d_lac.medico_cns is None
    assert d_lac.medico_cbo == "225125"
    assert d_lac.unidade_nome == "UPA Digital Central"
    assert d_lac.unidade_cnpj == "11222333000144"

    assert d_2000.paciente_data_nascimento == "20000101"
    assert d_2000.paciente_cns == "700000000000005"
    assert d_2000.medico_cbo == "251510"

    assert d_nutri.medico_cbo == "223710"

    audit_before = (
        await db_session.execute(select(func.count()).select_from(AuditEvent))
    ).scalar_one()

    headers = auth_headers(papel=Role.FATURAMENTO, usuario_id=uuid4())
    resp = await async_client.get(
        "/api/v1/ambulatory/producao/exportar?competencia=202611",
        headers=headers,
    )
    assert resp.status_code == 200
    linhas = resp.text.splitlines()
    assert len(linhas) == 4
    # Lactente: idade 000, sem CPF mascarado como CNS
    assert linhas[1][85:88] == "000"
    assert "98765432100" not in linhas[1]
    assert linhas[1][59:74] == "000000000000000"
    assert linhas[1][30:36] == "225125"
    # Paciente nascido em 2000-01-01 e CBO Psicologia 251510
    assert linhas[2][142:150] == "20000101"
    assert linhas[2][30:36] == "251510"
    # CBO Nutrição 223710
    assert linhas[3][30:36] == "223710"

    audit_after = (
        await db_session.execute(select(func.count()).select_from(AuditEvent))
    ).scalar_one()
    assert audit_after == audit_before

    resp_list = await async_client.get(
        "/api/v1/ambulatory/producao?competencia=202611",
        headers=headers,
    )
    assert resp_list.status_code == 200
    body_list = resp_list.json()
    assert body_list["total"] == 3
    assert len(body_list["items"]) == 3
