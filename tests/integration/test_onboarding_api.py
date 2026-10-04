"""Integration tests for progressive 2-phase onboarding API and dependent management.

Complies with RF-01, RF-02, NEC-01, CFM 1.821/2007, and CFM 2.314/2022.
"""

import asyncio
import time
from collections.abc import AsyncGenerator

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from src.core.config import get_settings
from src.core.database import async_session_factory, engine
from src.core.security import verify_intake_token
from src.core.uuid7 import uuid7
from src.main import create_app
from src.modules.identity.domain.models import Organizacao

from tests.factories.identity import make_organizacao

SAMPLE_TCLE_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def _run_alembic_upgrade_head() -> None:
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")


@pytest.fixture(autouse=True)
async def clean_database() -> AsyncGenerator[None, None]:
    """Ensure clean table state before each test."""
    await asyncio.to_thread(_run_alembic_upgrade_head)
    async with engine.begin() as conn:
        await conn.execute(
            text("TRUNCATE TABLE dependentes, pacientes, organizacoes CASCADE;")
        )
    yield
    async with engine.begin() as conn:
        await conn.execute(
            text("TRUNCATE TABLE dependentes, pacientes, organizacoes CASCADE;")
        )


@pytest.fixture
async def test_orgs() -> AsyncGenerator[tuple[Organizacao, Organizacao], None]:
    """Ensure two test organizations exist for multi-tenant verification."""
    async with async_session_factory() as session:
        org1 = make_organizacao(
            cnpj="55667788000199", razao_social="UBS Central Tenant 1"
        )
        org2 = make_organizacao(
            cnpj="66778899000111", razao_social="UPA Municipal Tenant 2"
        )
        session.add_all([org1, org2])
        await session.commit()
        await session.refresh(org1)
        await session.refresh(org2)

        yield org1, org2


@pytest.mark.asyncio
async def test_onboarding_fase_1_happy_path_under_45s(
    test_orgs: tuple[Organizacao, Organizacao],
) -> None:
    """Validate Phase 1 rapid intake executes in < 45 seconds (NEC-01)."""
    org1, _ = test_orgs
    app = create_app()

    start_time = time.monotonic()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        payload = {
            "nome_completo": "Carlos Drumond de Andrade",
            "data_nascimento": "1980-10-31",
            "telefone": "(11) 98765-4321",
            "queixa_principal": (
                "Cefaleia holocraniana pulsátil com fotofobia há 3 horas"
            ),
            "tcle_hash": SAMPLE_TCLE_HASH,
            "cpf": "111.444.777-35",
        }
        res = await client.post(
            "/api/v1/onboarding/fase-1",
            json=payload,
            headers={"X-Tenant-ID": str(org1.id)},
        )
    elapsed = time.monotonic() - start_time

    assert res.status_code == 201
    assert elapsed < 45.0  # NEC-01 SLA requirement

    data = res.json()
    assert "paciente_id" in data
    assert "token" in data
    assert data["status"] == "TRIADO_AGUARDANDO_ELEGIBILIDADE"
    assert data["is_novo_paciente"] is True

    # Validate intake token integrity and claims
    settings = get_settings()
    claims = verify_intake_token(data["token"], settings.SECRET_KEY)
    assert claims["paciente_id"] == data["paciente_id"]
    assert claims["organizacao_id"] == org1.id
    assert claims["tipo"] == "intake_provisional"


@pytest.mark.asyncio
async def test_onboarding_fase_1_deduplication_reuses_patient(
    test_orgs: tuple[Organizacao, Organizacao],
) -> None:
    """Submitting Phase 1 intake for an existing patient returns the same record."""
    org1, _ = test_orgs
    app = create_app()

    cpf = "529.982.247-25"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # First submission
        res1 = await client.post(
            "/api/v1/onboarding/fase-1",
            json={
                "nome_completo": "Ana Maria Braga",
                "data_nascimento": "1975-04-01",
                "telefone": "11988887777",
                "queixa_principal": "Dor de garganta e febre",
                "tcle_hash": SAMPLE_TCLE_HASH,
                "cpf": cpf,
            },
            headers={"X-Tenant-ID": str(org1.id)},
        )
        assert res1.status_code == 201
        data1 = res1.json()
        assert data1["is_novo_paciente"] is True

        # Second submission with new phone and updated complaint
        res2 = await client.post(
            "/api/v1/onboarding/fase-1",
            json={
                "nome_completo": "Ana Maria Braga",
                "data_nascimento": "1975-04-01",
                "telefone": "11999990000",
                "queixa_principal": "Sintomas persistentes",
                "tcle_hash": SAMPLE_TCLE_HASH,
                "cpf": cpf,
            },
            headers={"X-Tenant-ID": str(org1.id)},
        )
        assert res2.status_code == 201
        data2 = res2.json()
        assert data2["paciente_id"] == data1["paciente_id"]
        assert data2["is_novo_paciente"] is False


@pytest.mark.asyncio
async def test_onboarding_fase_1_validation_errors(
    test_orgs: tuple[Organizacao, Organizacao],
) -> None:
    """Validate RFC 7807 problem details on input errors."""
    org1, _ = test_orgs
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. Missing both CPF and CNS
        res_no_doc = await client.post(
            "/api/v1/onboarding/fase-1",
            json={
                "nome_completo": "Paciente Sem Documento",
                "data_nascimento": "1990-01-01",
                "telefone": "11987654321",
                "queixa_principal": "Febre",
                "tcle_hash": SAMPLE_TCLE_HASH,
            },
            headers={"X-Tenant-ID": str(org1.id)},
        )
        assert res_no_doc.status_code == 422
        problem = res_no_doc.json()
        assert problem["code"] == "IDENTIFICACAO_OBRIGATORIA"

        # 2. Invalid CPF check digits
        res_bad_cpf = await client.post(
            "/api/v1/onboarding/fase-1",
            json={
                "nome_completo": "Paciente CPF Invalido",
                "data_nascimento": "1990-01-01",
                "telefone": "11987654321",
                "queixa_principal": "Febre",
                "tcle_hash": SAMPLE_TCLE_HASH,
                "cpf": "111.444.777-99",
            },
            headers={"X-Tenant-ID": str(org1.id)},
        )
        assert res_bad_cpf.status_code == 422

        # 3. Missing X-Tenant-ID header
        res_no_tenant = await client.post(
            "/api/v1/onboarding/fase-1",
            json={
                "nome_completo": "Paciente Sem Tenant",
                "data_nascimento": "1990-01-01",
                "telefone": "11987654321",
                "queixa_principal": "Febre",
                "tcle_hash": SAMPLE_TCLE_HASH,
                "cpf": "11144477735",
            },
        )
        assert res_no_tenant.status_code == 400
        assert res_no_tenant.json()["code"] == "TENANT_INVALIDO"


@pytest.mark.asyncio
async def test_onboarding_fase_2_enrichment_happy_path(
    test_orgs: tuple[Organizacao, Organizacao],
) -> None:
    """Validate Phase 2 CFM 1.821/2007 mandatory enrichment."""
    org1, _ = test_orgs
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Step 1: Intake
        intake_res = await client.post(
            "/api/v1/onboarding/fase-1",
            json={
                "nome_completo": "Juliana Paes",
                "data_nascimento": "1979-03-26",
                "telefone": "21988881234",
                "queixa_principal": "Dor lombar aguda",
                "tcle_hash": SAMPLE_TCLE_HASH,
                "cpf": "11144477735",
            },
            headers={"X-Tenant-ID": str(org1.id)},
        )
        assert intake_res.status_code == 201
        paciente_id = intake_res.json()["paciente_id"]

        # Step 2: Enrichment
        fase2_payload = {
            "paciente_id": paciente_id,
            "nome_mae": "Regina Couto Paes",
            "sexo_biologico": "F",
            "cep": "22041-001",
            "logradouro": "Avenida Atlântica",
            "numero": "1500",
            "bairro": "Copacabana",
            "cidade": "Rio de Janeiro",
            "estado": "RJ",
            "alergias": ["Dipirona", "Anti-inflamatórios não esteroides"],
        }
        res2 = await client.post(
            "/api/v1/onboarding/fase-2",
            json=fase2_payload,
            headers={"X-Tenant-ID": str(org1.id)},
        )
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["paciente_id"] == paciente_id
        assert data2["nome_mae"] == "Regina Couto Paes"
        assert data2["sexo_biologico"] == "F"
        assert data2["cep"] == "22041001"
        assert data2["cidade"] == "Rio de Janeiro"
        assert len(data2["alergias"]) == 2
        assert data2["status"] == "DADOS_COMPLETOS"


@pytest.mark.asyncio
async def test_onboarding_fase_2_cfm_validation_failures(
    test_orgs: tuple[Organizacao, Organizacao],
) -> None:
    """Validate CFM requirements reject incomplete data."""
    org1, _ = test_orgs
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Non-existent patient
        res_404 = await client.post(
            "/api/v1/onboarding/fase-2",
            json={
                "paciente_id": str(uuid7()),
                "nome_mae": "Maria da Silva",
                "sexo_biologico": "F",
                "cep": "01310-100",
                "logradouro": "Av Paulista",
                "numero": "100",
                "bairro": "Bela Vista",
                "cidade": "São Paulo",
                "estado": "SP",
            },
            headers={"X-Tenant-ID": str(org1.id)},
        )
        assert res_404.status_code == 404
        assert res_404.json()["code"] == "PACIENTE_NAO_ENCONTRADO"

        # Incomplete mother name (single name)
        intake_res = await client.post(
            "/api/v1/onboarding/fase-1",
            json={
                "nome_completo": "Lucas Santos",
                "data_nascimento": "1995-07-10",
                "telefone": "11987654321",
                "queixa_principal": "Náusea e mal estar",
                "tcle_hash": SAMPLE_TCLE_HASH,
                "cns": "700000000000005",
            },
            headers={"X-Tenant-ID": str(org1.id)},
        )
        paciente_id = intake_res.json()["paciente_id"]

        res_single_name = await client.post(
            "/api/v1/onboarding/fase-2",
            json={
                "paciente_id": paciente_id,
                "nome_mae": "Maria",  # Violates CFM 1.821/2007 (must be full name)
                "sexo_biologico": "M",
                "cep": "01310-100",
                "logradouro": "Av Paulista",
                "numero": "100",
                "bairro": "Bela Vista",
                "cidade": "São Paulo",
                "estado": "SP",
            },
            headers={"X-Tenant-ID": str(org1.id)},
        )
        assert res_single_name.status_code == 422


@pytest.mark.asyncio
async def test_dependente_management_lifecycle(
    test_orgs: tuple[Organizacao, Organizacao],
) -> None:
    """Validate dependent creation, anti-reflexive checks, and listing."""
    org1, _ = test_orgs
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. Create titular
        intake_titular = await client.post(
            "/api/v1/onboarding/fase-1",
            json={
                "nome_completo": "Mariana Ribeiro (Titular)",
                "data_nascimento": "1988-12-05",
                "telefone": "11977778888",
                "queixa_principal": "Consulta preventiva",
                "tcle_hash": SAMPLE_TCLE_HASH,
                "cpf": "11144477735",
            },
            headers={"X-Tenant-ID": str(org1.id)},
        )
        titular_id = intake_titular.json()["paciente_id"]

        # 2. Anti-reflexive check: titular cannot be dependent of themselves
        res_self = await client.post(
            f"/api/v1/pacientes/{titular_id}/dependentes",
            json={
                "grau_parentesco": "FILHO",
                "dependente_id": titular_id,
            },
            headers={"X-Tenant-ID": str(org1.id)},
        )
        assert res_self.status_code == 400
        assert res_self.json()["code"] == "DEPENDENTE_AUTO_REFERENCIA"

        # 3. Create new minor dependent
        res_dep1 = await client.post(
            f"/api/v1/pacientes/{titular_id}/dependentes",
            json={
                "grau_parentesco": "FILHO",
                "nome_completo": "Enzo Gabriel Ribeiro",
                "data_nascimento": "2020-06-15",
                "cns": "800000000000001",
            },
            headers={"X-Tenant-ID": str(org1.id)},
        )
        assert res_dep1.status_code == 201
        data_dep1 = res_dep1.json()
        assert data_dep1["titular_id"] == titular_id
        assert data_dep1["grau_parentesco"] == "FILHO"
        dep1_id = data_dep1["dependente_id"]

        # 4. Duplicate linkage fails with 409 Conflict
        res_dup = await client.post(
            f"/api/v1/pacientes/{titular_id}/dependentes",
            json={
                "grau_parentesco": "FILHO",
                "dependente_id": dep1_id,
            },
            headers={"X-Tenant-ID": str(org1.id)},
        )
        assert res_dup.status_code == 409
        assert res_dup.json()["code"] == "VINCULO_DEPENDENTE_EXISTENTE"

        # 5. List dependents
        res_list = await client.get(
            f"/api/v1/pacientes/{titular_id}/dependentes",
            headers={"X-Tenant-ID": str(org1.id)},
        )
        assert res_list.status_code == 200
        lista = res_list.json()
        assert len(lista) == 1
        assert lista[0]["nome_completo"] == "Enzo Gabriel Ribeiro"
        assert lista[0]["dependente_id"] == dep1_id


@pytest.mark.asyncio
async def test_tenant_isolation_onboarding_and_dependents(
    test_orgs: tuple[Organizacao, Organizacao],
) -> None:
    """Verify tenant isolation: Tenant 2 cannot access or mutate Tenant 1 patients."""
    org1, org2 = test_orgs
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Create patient in Tenant 1
        intake_res = await client.post(
            "/api/v1/onboarding/fase-1",
            json={
                "nome_completo": "Paciente Tenant 1",
                "data_nascimento": "1992-08-20",
                "telefone": "11988884321",
                "queixa_principal": "Gripe",
                "tcle_hash": SAMPLE_TCLE_HASH,
                "cpf": "11144477735",
            },
            headers={"X-Tenant-ID": str(org1.id)},
        )
        assert intake_res.status_code == 201
        paciente_id = intake_res.json()["paciente_id"]

        # Tenant 2 attempts Phase 2 enrichment on Tenant 1 patient -> 404
        res_enrich_t2 = await client.post(
            "/api/v1/onboarding/fase-2",
            json={
                "paciente_id": paciente_id,
                "nome_mae": "Mae de Teste",
                "sexo_biologico": "F",
                "cep": "01310-100",
                "logradouro": "Rua A",
                "numero": "1",
                "bairro": "Centro",
                "cidade": "SP",
                "estado": "SP",
            },
            headers={"X-Tenant-ID": str(org2.id)},
        )
        assert res_enrich_t2.status_code == 404

        # Tenant 2 attempts to link dependent to Tenant 1 patient -> 404
        res_dep_t2 = await client.post(
            f"/api/v1/pacientes/{paciente_id}/dependentes",
            json={
                "grau_parentesco": "FILHO",
                "nome_completo": "Filho Ilegitimo",
                "data_nascimento": "2022-01-01",
                "cns": "700000000000005",
            },
            headers={"X-Tenant-ID": str(org2.id)},
        )
        assert res_dep_t2.status_code == 404
