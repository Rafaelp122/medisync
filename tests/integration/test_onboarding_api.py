"""Integration tests for progressive 2-phase onboarding API and dependent management.

Complies with RF-01, RF-02, NEC-01, CFM 1.821/2007, and CFM 2.314/2022.
"""

import time
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.authz.roles import Role
from src.core.config import get_settings
from src.core.security import create_intake_token, verify_intake_token
from src.core.uuid7 import uuid7
from src.modules.identity.domain.models import Organizacao

from tests.factories.scenarios import seed_multi_tenant_orgs

pytestmark = pytest.mark.usefixtures("clean_db")

SAMPLE_TCLE_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


@pytest.fixture
async def test_orgs(
    db_session: AsyncSession,
) -> tuple[Organizacao, Organizacao]:
    """Ensure two test organizations exist for multi-tenant verification."""
    return await seed_multi_tenant_orgs(
        db_session,
        cnpj_a="55667788000199",
        cnpj_b="66778899000111",
    )


@pytest.mark.asyncio
async def test_onboarding_fase_1_happy_path_under_45s(
    async_client: AsyncClient,
    test_orgs: tuple[Organizacao, Organizacao],
) -> None:
    """Validate Phase 1 rapid intake executes in < 45 seconds (NEC-01)."""
    org1, _ = test_orgs

    start_time = time.monotonic()
    payload = {
        "nome_completo": "Carlos Drumond de Andrade",
        "data_nascimento": "1980-10-31",
        "telefone": "(11) 98765-4321",
        "queixa_principal": "Cefaleia holocraniana pulsátil com fotofobia há 3 horas",
        "tcle_hash": SAMPLE_TCLE_HASH,
        "cpf": "111.444.777-35",
    }
    res = await async_client.post(
        "/api/v1/onboarding/fase-1",
        json=payload,
        headers={"X-Tenant-ID": str(org1.id)},
    )
    elapsed = time.monotonic() - start_time

    assert res.status_code == 201
    assert elapsed < 45.0  # NEC-01 SLA requirement

    data = cast("dict[str, object]", res.json())
    assert "paciente_id" in data
    assert "token" in data
    assert data["status"] == "TRIADO_AGUARDANDO_ELEGIBILIDADE"
    assert data["is_novo_paciente"] is True

    # Validate intake token integrity and claims
    settings = get_settings()
    token = cast("str", data["token"])
    claims = verify_intake_token(token, settings.SECRET_KEY)
    assert claims["paciente_id"] == data["paciente_id"]
    assert claims["organizacao_id"] == org1.id
    assert claims["tipo"] == "intake_provisional"


@pytest.mark.asyncio
async def test_onboarding_fase_1_deduplication_reuses_patient(
    async_client: AsyncClient,
    test_orgs: tuple[Organizacao, Organizacao],
) -> None:
    """Submitting Phase 1 intake for an existing patient returns the same record."""
    org1, _ = test_orgs
    cpf = "529.982.247-25"

    # First submission
    res1 = await async_client.post(
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
    data1 = cast("dict[str, object]", res1.json())
    assert data1["is_novo_paciente"] is True

    # Second submission with new phone and updated complaint
    res2 = await async_client.post(
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
    data2 = cast("dict[str, object]", res2.json())
    assert data2["paciente_id"] == data1["paciente_id"]
    assert data2["is_novo_paciente"] is False


@pytest.mark.asyncio
async def test_onboarding_fase_1_validation_errors(
    async_client: AsyncClient,
    test_orgs: tuple[Organizacao, Organizacao],
) -> None:
    """Validate RFC 7807 problem details on input errors."""
    org1, _ = test_orgs

    # 1. Missing both CPF and CNS
    res_no_doc = await async_client.post(
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
    problem = cast("dict[str, object]", res_no_doc.json())
    assert problem["code"] == "IDENTIFICACAO_OBRIGATORIA"

    # 2. Invalid CPF check digits
    res_bad_cpf = await async_client.post(
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
    res_no_tenant = await async_client.post(
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
    problem_tenant = cast("dict[str, object]", res_no_tenant.json())
    assert problem_tenant["code"] == "TENANT_INVALIDO"


def make_test_jwt(
    usuario_id: UUID,
    organizacao_id: int,
    papel: str,
    secret_key: str,
    expires_in_seconds: int = 900,
) -> str:
    """Helper to generate JWT tokens for integration testing."""
    now = datetime.now(UTC)
    exp = now + timedelta(seconds=expires_in_seconds)
    payload = {
        "sub": str(usuario_id),
        "org_id": organizacao_id,
        "papel": papel,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": str(uuid4()),
        "type": "access",
    }
    return jwt.encode(payload, secret_key, algorithm="HS256")


@pytest.mark.asyncio
async def test_onboarding_fase_2_enrichment_happy_path(
    async_client: AsyncClient,
    test_orgs: tuple[Organizacao, Organizacao],
) -> None:
    """Validate Phase 2 CFM mandatory enrichment with token in Authorization header."""
    org1, _ = test_orgs

    # Step 1: Intake
    intake_res = await async_client.post(
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
    intake_data = cast("dict[str, object]", intake_res.json())
    paciente_id = cast("str", intake_data["paciente_id"])
    token = cast("str", intake_data["token"])

    # Step 2: Enrichment with Authorization header
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
    res2 = await async_client.post(
        "/api/v1/onboarding/fase-2",
        json=fase2_payload,
        headers={
            "X-Tenant-ID": str(org1.id),
            "Authorization": f"Bearer {token}",
        },
    )
    assert res2.status_code == 200
    data2 = cast("dict[str, object]", res2.json())
    assert data2["paciente_id"] == paciente_id
    assert data2["nome_mae"] == "Regina Couto Paes"
    assert data2["sexo_biologico"] == "F"
    assert data2["cep"] == "22041001"
    assert data2["cidade"] == "Rio de Janeiro"
    alergias = cast("list[str]", data2["alergias"])
    assert len(alergias) == 2
    assert data2["status"] == "DADOS_COMPLETOS"


@pytest.mark.asyncio
async def test_onboarding_fase_2_enrichment_via_body_token(
    async_client: AsyncClient,
    test_orgs: tuple[Organizacao, Organizacao],
) -> None:
    """Validate Phase 2 enrichment succeeds when token is sent inside the JSON body."""
    org1, _ = test_orgs

    intake_res = await async_client.post(
        "/api/v1/onboarding/fase-1",
        json={
            "nome_completo": "Marcos Frota",
            "data_nascimento": "1972-09-29",
            "telefone": "21977771234",
            "queixa_principal": "Cefaleia tensional",
            "tcle_hash": SAMPLE_TCLE_HASH,
            "cpf": "11144477735",
        },
        headers={"X-Tenant-ID": str(org1.id)},
    )
    assert intake_res.status_code == 201
    intake_data = cast("dict[str, object]", intake_res.json())
    paciente_id = cast("str", intake_data["paciente_id"])
    token = cast("str", intake_data["token"])

    fase2_payload = {
        "paciente_id": paciente_id,
        "token": token,
        "nome_mae": "Lourdes Frota da Silva",
        "sexo_biologico": "M",
        "cep": "22041-001",
        "logradouro": "Avenida Atlântica",
        "numero": "1500",
        "bairro": "Copacabana",
        "cidade": "Rio de Janeiro",
        "estado": "RJ",
    }
    res2 = await async_client.post(
        "/api/v1/onboarding/fase-2",
        json=fase2_payload,
        headers={"X-Tenant-ID": str(org1.id)},
    )
    assert res2.status_code == 200
    data2 = cast("dict[str, object]", res2.json())
    assert data2["paciente_id"] == paciente_id
    assert data2["status"] == "DADOS_COMPLETOS"


@pytest.mark.asyncio
async def test_onboarding_fase_2_security_rejections(
    async_client: AsyncClient,
    test_orgs: tuple[Organizacao, Organizacao],
) -> None:
    """Validate RFC 7807 401 and 403 on invalid, missing, or mismatched tokens."""
    org1, org2 = test_orgs
    settings = get_settings()

    # Step 1: Create patient in Org 1
    intake_res = await async_client.post(
        "/api/v1/onboarding/fase-1",
        json={
            "nome_completo": "Paciente Teste Seguranca",
            "data_nascimento": "1990-01-01",
            "telefone": "11988887777",
            "queixa_principal": "Febre alta",
            "tcle_hash": SAMPLE_TCLE_HASH,
            "cpf": "11144477735",
        },
        headers={"X-Tenant-ID": str(org1.id)},
    )
    assert intake_res.status_code == 201
    intake_data = cast("dict[str, object]", intake_res.json())
    paciente_id = cast("str", intake_data["paciente_id"])
    valid_token = cast("str", intake_data["token"])

    base_fase2 = {
        "paciente_id": paciente_id,
        "nome_mae": "Mae de Teste Seguranca",
        "sexo_biologico": "F",
        "cep": "01310-100",
        "logradouro": "Av Paulista",
        "numero": "100",
        "bairro": "Bela Vista",
        "cidade": "São Paulo",
        "estado": "SP",
    }

    # 1. Missing token -> 401 Unauthorized
    res_no_tok = await async_client.post(
        "/api/v1/onboarding/fase-2",
        json=base_fase2,
        headers={"X-Tenant-ID": str(org1.id)},
    )
    assert res_no_tok.status_code == 401
    assert cast("dict[str, object]", res_no_tok.json())["code"] == "UNAUTHORIZED"

    # 2. Tampered token -> 401 Unauthorized
    tampered_token = valid_token[:-4] + "wxyz"
    res_tampered = await async_client.post(
        "/api/v1/onboarding/fase-2",
        json=base_fase2,
        headers={
            "X-Tenant-ID": str(org1.id),
            "Authorization": f"Bearer {tampered_token}",
        },
    )
    assert res_tampered.status_code == 401

    # 3. Expired token -> 401 Unauthorized
    expired_token = create_intake_token(
        paciente_id=UUID(paciente_id),
        organizacao_id=org1.id,
        secret_key=settings.SECRET_KEY,
        expires_in_seconds=-10,
    )
    res_expired = await async_client.post(
        "/api/v1/onboarding/fase-2",
        json=base_fase2,
        headers={
            "X-Tenant-ID": str(org1.id),
            "Authorization": f"Bearer {expired_token}",
        },
    )
    assert res_expired.status_code == 401

    # 4. Mismatched paciente_id in body vs token -> 403 Forbidden
    other_patient_id = str(uuid7())
    mismatched_payload = {**base_fase2, "paciente_id": other_patient_id}
    res_mismatch = await async_client.post(
        "/api/v1/onboarding/fase-2",
        json=mismatched_payload,
        headers={
            "X-Tenant-ID": str(org1.id),
            "Authorization": f"Bearer {valid_token}",
        },
    )
    assert res_mismatch.status_code == 403
    assert cast("dict[str, object]", res_mismatch.json())["code"] == "FORBIDDEN"

    # 5. Token from Org 1 used with X-Tenant-ID of Org 2 -> 403 Forbidden
    res_cross_org = await async_client.post(
        "/api/v1/onboarding/fase-2",
        json=base_fase2,
        headers={
            "X-Tenant-ID": str(org2.id),
            "Authorization": f"Bearer {valid_token}",
        },
    )
    assert res_cross_org.status_code == 403
    assert cast("dict[str, object]", res_cross_org.json())["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_onboarding_fase_2_cfm_validation_failures(
    async_client: AsyncClient,
    test_orgs: tuple[Organizacao, Organizacao],
) -> None:
    """Validate CFM requirements reject incomplete data when authenticated."""
    org1, _ = test_orgs
    settings = get_settings()

    # Non-existent patient with validly signed token for that tenant
    fake_id = uuid7()
    fake_token = create_intake_token(
        paciente_id=fake_id,
        organizacao_id=org1.id,
        secret_key=settings.SECRET_KEY,
    )
    res_404 = await async_client.post(
        "/api/v1/onboarding/fase-2",
        json={
            "paciente_id": str(fake_id),
            "nome_mae": "Maria da Silva",
            "sexo_biologico": "F",
            "cep": "01310-100",
            "logradouro": "Av Paulista",
            "numero": "100",
            "bairro": "Bela Vista",
            "cidade": "São Paulo",
            "estado": "SP",
        },
        headers={
            "X-Tenant-ID": str(org1.id),
            "Authorization": f"Bearer {fake_token}",
        },
    )
    assert res_404.status_code == 404
    res_404_data = cast("dict[str, object]", res_404.json())
    assert res_404_data["code"] == "PACIENTE_NAO_ENCONTRADO"

    # Incomplete mother name (single name)
    intake_res = await async_client.post(
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
    intake_data = cast("dict[str, object]", intake_res.json())
    paciente_id = cast("str", intake_data["paciente_id"])
    token = cast("str", intake_data["token"])

    res_single_name = await async_client.post(
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
        headers={
            "X-Tenant-ID": str(org1.id),
            "Authorization": f"Bearer {token}",
        },
    )
    assert res_single_name.status_code == 422


@pytest.mark.asyncio
async def test_dependente_management_lifecycle(
    async_client: AsyncClient,
    test_orgs: tuple[Organizacao, Organizacao],
) -> None:
    """Validate dependent lifecycle and anti-reflexive checks with possession."""
    org1, _ = test_orgs

    # 1. Create titular
    intake_titular = await async_client.post(
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
    titular_data = cast("dict[str, object]", intake_titular.json())
    titular_id = cast("str", titular_data["paciente_id"])
    titular_token = cast("str", titular_data["token"])

    auth_headers = {
        "X-Tenant-ID": str(org1.id),
        "Authorization": f"Bearer {titular_token}",
    }

    # 2. Anti-reflexive check: titular cannot be dependent of themselves
    res_self = await async_client.post(
        f"/api/v1/pacientes/{titular_id}/dependentes",
        json={
            "grau_parentesco": "FILHO",
            "dependente_id": titular_id,
        },
        headers=auth_headers,
    )
    assert res_self.status_code == 400
    res_self_data = cast("dict[str, object]", res_self.json())
    assert res_self_data["code"] == "DEPENDENTE_AUTO_REFERENCIA"

    # 3. Create new minor dependent
    res_dep1 = await async_client.post(
        f"/api/v1/pacientes/{titular_id}/dependentes",
        json={
            "grau_parentesco": "FILHO",
            "nome_completo": "Enzo Gabriel Ribeiro",
            "data_nascimento": "2020-06-15",
            "cns": "800000000000001",
        },
        headers=auth_headers,
    )
    assert res_dep1.status_code == 201
    data_dep1 = cast("dict[str, object]", res_dep1.json())
    assert data_dep1["titular_id"] == titular_id
    assert data_dep1["grau_parentesco"] == "FILHO"
    dep1_id = cast("str", data_dep1["dependente_id"])

    # 4. Duplicate linkage fails with 409 Conflict
    res_dup = await async_client.post(
        f"/api/v1/pacientes/{titular_id}/dependentes",
        json={
            "grau_parentesco": "FILHO",
            "dependente_id": dep1_id,
        },
        headers=auth_headers,
    )
    assert res_dup.status_code == 409
    res_dup_data = cast("dict[str, object]", res_dup.json())
    assert res_dup_data["code"] == "VINCULO_DEPENDENTE_EXISTENTE"

    # 5. List dependents
    res_list = await async_client.get(
        f"/api/v1/pacientes/{titular_id}/dependentes",
        headers=auth_headers,
    )
    assert res_list.status_code == 200
    lista = cast("list[dict[str, object]]", res_list.json())
    assert len(lista) == 1
    assert lista[0]["nome_completo"] == "Enzo Gabriel Ribeiro"
    assert lista[0]["dependente_id"] == dep1_id


@pytest.mark.asyncio
async def test_dependente_security_rejections(
    async_client: AsyncClient,
    test_orgs: tuple[Organizacao, Organizacao],
) -> None:
    """Validate dependent endpoints reject unauthorized requests (DoD Issue #40)."""
    org1, org2 = test_orgs
    settings = get_settings()

    # Create titular in Org 1
    intake_res = await async_client.post(
        "/api/v1/onboarding/fase-1",
        json={
            "nome_completo": "Titular Teste Seguranca",
            "data_nascimento": "1985-03-10",
            "telefone": "11966665555",
            "queixa_principal": "Checkup",
            "tcle_hash": SAMPLE_TCLE_HASH,
            "cpf": "11144477735",
        },
        headers={"X-Tenant-ID": str(org1.id)},
    )
    intake_data = cast("dict[str, object]", intake_res.json())
    titular_id = cast("str", intake_data["paciente_id"])
    valid_token = cast("str", intake_data["token"])

    dep_payload = {
        "grau_parentesco": "FILHO",
        "nome_completo": "Filho Teste",
        "data_nascimento": "2018-01-01",
        "cns": "800000000000001",
    }

    # 1. Missing Authorization header -> 401
    res_get_no_tok = await async_client.get(
        f"/api/v1/pacientes/{titular_id}/dependentes",
        headers={"X-Tenant-ID": str(org1.id)},
    )
    assert res_get_no_tok.status_code == 401

    res_post_no_tok = await async_client.post(
        f"/api/v1/pacientes/{titular_id}/dependentes",
        json=dep_payload,
        headers={"X-Tenant-ID": str(org1.id)},
    )
    assert res_post_no_tok.status_code == 401

    # 2. Tampered token -> 401
    bad_token = valid_token[:-3] + "abc"
    res_tampered = await async_client.get(
        f"/api/v1/pacientes/{titular_id}/dependentes",
        headers={
            "X-Tenant-ID": str(org1.id),
            "Authorization": f"Bearer {bad_token}",
        },
    )
    assert res_tampered.status_code == 401

    # 3. Expired token -> 401
    exp_token = create_intake_token(
        paciente_id=UUID(titular_id),
        organizacao_id=org1.id,
        secret_key=settings.SECRET_KEY,
        expires_in_seconds=-10,
    )
    res_expired = await async_client.get(
        f"/api/v1/pacientes/{titular_id}/dependentes",
        headers={
            "X-Tenant-ID": str(org1.id),
            "Authorization": f"Bearer {exp_token}",
        },
    )
    assert res_expired.status_code == 401

    # 4. Token of another patient -> 403 Forbidden
    other_patient_id = uuid7()
    other_token = create_intake_token(
        paciente_id=other_patient_id,
        organizacao_id=org1.id,
        secret_key=settings.SECRET_KEY,
    )
    res_other = await async_client.get(
        f"/api/v1/pacientes/{titular_id}/dependentes",
        headers={
            "X-Tenant-ID": str(org1.id),
            "Authorization": f"Bearer {other_token}",
        },
    )
    assert res_other.status_code == 403

    # 5. Token belonging to another org -> 403 Forbidden
    res_cross_org = await async_client.get(
        f"/api/v1/pacientes/{titular_id}/dependentes",
        headers={
            "X-Tenant-ID": str(org2.id),
            "Authorization": f"Bearer {valid_token}",
        },
    )
    assert res_cross_org.status_code == 403


@pytest.mark.asyncio
async def test_dependente_allowed_with_corporate_jwt(
    async_client: AsyncClient,
    test_orgs: tuple[Organizacao, Organizacao],
) -> None:
    """Validate corporate roles (ADMIN_GLOBAL, GESTOR_UNIDADE) can manage dependents."""
    org1, _ = test_orgs
    settings = get_settings()

    # Create titular
    intake_res = await async_client.post(
        "/api/v1/onboarding/fase-1",
        json={
            "nome_completo": "Titular Recepcao Atendimento",
            "data_nascimento": "1983-05-20",
            "telefone": "11955554444",
            "queixa_principal": "Febre",
            "tcle_hash": SAMPLE_TCLE_HASH,
            "cpf": "11144477735",
        },
        headers={"X-Tenant-ID": str(org1.id)},
    )
    titular_id = cast("str", intake_res.json()["paciente_id"])

    # Admin global JWT
    admin_jwt = make_test_jwt(
        usuario_id=uuid4(),
        organizacao_id=org1.id,
        papel=Role.ADMIN_GLOBAL,
        secret_key=settings.JWT_SECRET_KEY,
    )
    res_admin_create = await async_client.post(
        f"/api/v1/pacientes/{titular_id}/dependentes",
        json={
            "grau_parentesco": "FILHO",
            "nome_completo": "Dependente Cadastrado Por Admin",
            "data_nascimento": "2019-02-15",
            "cns": "800000000000001",
        },
        headers={
            "X-Tenant-ID": str(org1.id),
            "Authorization": f"Bearer {admin_jwt}",
        },
    )
    assert res_admin_create.status_code == 201

    # Gestor unidade JWT lists dependents
    gestor_jwt = make_test_jwt(
        usuario_id=uuid4(),
        organizacao_id=org1.id,
        papel=Role.GESTOR_UNIDADE,
        secret_key=settings.JWT_SECRET_KEY,
    )
    res_gestor_list = await async_client.get(
        f"/api/v1/pacientes/{titular_id}/dependentes",
        headers={
            "X-Tenant-ID": str(org1.id),
            "Authorization": f"Bearer {gestor_jwt}",
        },
    )
    assert res_gestor_list.status_code == 200
    assert len(cast("list[dict[str, object]]", res_gestor_list.json())) == 1


@pytest.mark.asyncio
async def test_tenant_isolation_onboarding_and_dependents(
    async_client: AsyncClient,
    test_orgs: tuple[Organizacao, Organizacao],
) -> None:
    """Verify tenant isolation: Tenant 2 cannot access or mutate Tenant 1 patients."""
    org1, org2 = test_orgs

    # Create patient in Tenant 1
    intake_res = await async_client.post(
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
    intake_data = cast("dict[str, object]", intake_res.json())
    paciente_id = cast("str", intake_data["paciente_id"])
    token_t1 = cast("str", intake_data["token"])

    # Tenant 2 attempts Phase 2 on Tenant 1 patient with token -> 403
    res_enrich_t2 = await async_client.post(
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
        headers={
            "X-Tenant-ID": str(org2.id),
            "Authorization": f"Bearer {token_t1}",
        },
    )
    assert res_enrich_t2.status_code == 403

    # Tenant 2 attempts to link dependent to Tenant 1 patient -> 403
    res_dep_t2 = await async_client.post(
        f"/api/v1/pacientes/{paciente_id}/dependentes",
        json={
            "grau_parentesco": "FILHO",
            "nome_completo": "Filho Ilegitimo",
            "data_nascimento": "2022-01-01",
            "cns": "700000000000005",
        },
        headers={
            "X-Tenant-ID": str(org2.id),
            "Authorization": f"Bearer {token_t1}",
        },
    )
    assert res_dep_t2.status_code == 403
