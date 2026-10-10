"""Integration tests for PEP SOAP workflow, prescriptions, and TMA indicators."""

from typing import cast
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.authz.roles import Role

from tests.factories.identity import make_profissional
from tests.factories.scenarios import seed_clinical_scenario
from tests.helpers import auth_headers


@pytest.mark.usefixtures("clean_db")
@pytest.mark.asyncio
async def test_consultation_soap_full_lifecycle_and_safeguards(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Test entire PEP workflow: SOAP notes, validation and immutability."""
    cenario = await seed_clinical_scenario(db_session)
    async_client.headers["X-Tenant-ID"] = str(cenario.organizacao.id)
    async_client.headers.update(
        auth_headers(Role.MEDICO, cenario.organizacao.id, cenario.medico.id)
    )
    client = async_client

    # 1. Register SOAP notes (Subjetivo, Objetivo, Avaliação, Plano)
    soap_payload = {
        "organizacao_id": cenario.organizacao.id,
        "anamnese": "Paciente queixa-se de odinofagia e coriza há 3 dias.",
        "exame_fisico_virtual": (
            "Orofaringe com hiperemia leve, sem placas purulentas."
        ),
        "cid10_principal": "J00",
        "conduta": "Orientada hidratação, analgesia e repouso.",
    }
    res_soap = await client.post(
        f"/api/v1/consultations/{cenario.atendimento.id}/soap",
        json=soap_payload,
    )
    assert res_soap.status_code == 200
    data_soap = cast("dict[str, object]", res_soap.json())
    assert data_soap["anamnese"] == soap_payload["anamnese"]
    assert data_soap["cid10_principal"] == "J00"
    assert data_soap["is_finalizado"] is False

    # 2. Update existing SOAP notes while consultation is open
    soap_update_payload = {
        "organizacao_id": cenario.organizacao.id,
        "anamnese": "Paciente queixa-se de odinofagia, coriza e febre há 3 dias.",
        "exame_fisico_virtual": ("Orofaringe com hiperemia leve e congestão nasal."),
        "cid10_principal": "J00",
        "conduta": "Orientada hidratação abundante e paracetamol.",
    }
    res_soap_update = await client.post(
        f"/api/v1/consultations/{cenario.atendimento.id}/soap",
        json=soap_update_payload,
    )
    assert res_soap_update.status_code == 200
    data_updated = cast("dict[str, object]", res_soap_update.json())
    assert "febre" in str(data_updated["anamnese"])

    # 3. Get registered SOAP notes
    res_get_soap = await client.get(
        f"/api/v1/consultations/{cenario.atendimento.id}/soap",
    )
    assert res_get_soap.status_code == 200
    data_get_soap = cast("dict[str, object]", res_get_soap.json())
    assert data_get_soap["cid10_principal"] == "J00"

    # 4. Check 404 for nonexistent attendance SOAP
    res_not_found = await client.get(
        f"/api/v1/consultations/{uuid4()}/soap",
    )
    assert res_not_found.status_code == 404

    # 5. Pre-validate permitted medication
    res_val_ok = await client.post(
        f"/api/v1/consultations/{cenario.atendimento.id}/prescriptions/validate",
        json={"medicamento": "Dipirona 500mg comprimidos"},
    )
    assert res_val_ok.status_code == 200
    assert cast("dict[str, object]", res_val_ok.json())["status"] == "PERMITIDO"

    # 6. Pre-validate prohibited medication (Portaria 344/98 Lista B - Clonazepam)
    res_val_proibido = await client.post(
        f"/api/v1/consultations/{cenario.atendimento.id}/prescriptions/validate",
        json={"medicamento": "Clonazepam 2mg gotas"},
    )
    assert res_val_proibido.status_code == 422
    problem = cast("dict[str, object]", res_val_proibido.json())
    assert problem["code"] == "PRESCRICAO_FISICA_OBRIGATORIA"
    assert "Portaria SVS/MS nº 344/98" in str(problem["detail"])

    # 7. Attempt issuing prohibited document type NOTIFICACAO_RECEITA_A (Yellow pad)
    res_doc_tipo_proibido = await client.post(
        f"/api/v1/consultations/{cenario.atendimento.id}/documents",
        json={
            "organizacao_id": cenario.organizacao.id,
            "tipo_documento": "NOTIFICACAO_RECEITA_A",
            "itens": [
                {
                    "medicamento": "Morfina 10mg",
                    "dosagem": "1 cp",
                    "posologia": "1 cp se dor intensa",
                }
            ],
        },
    )
    assert res_doc_tipo_proibido.status_code == 422
    assert "talonário físico" in str(res_doc_tipo_proibido.json()["detail"])

    # 8. Attempt issuing document with prohibited item (Morfina in RECEITA_SIMPLES)
    res_doc_item_proibido = await client.post(
        f"/api/v1/consultations/{cenario.atendimento.id}/documents",
        json={
            "organizacao_id": cenario.organizacao.id,
            "tipo_documento": "RECEITA_SIMPLES",
            "itens": [
                {
                    "medicamento": "Sulfato de Morfina 10mg",
                    "dosagem": "1 cp",
                    "posologia": "1 cp de 4/4h",
                }
            ],
        },
    )
    assert res_doc_item_proibido.status_code == 422

    # 9. Issue valid digital prescription (RECEITA_SIMPLES with Dipirona)
    res_doc_valido = await client.post(
        f"/api/v1/consultations/{cenario.atendimento.id}/documents",
        json={
            "organizacao_id": cenario.organizacao.id,
            "tipo_documento": "RECEITA_SIMPLES",
            "itens": [
                {
                    "medicamento": "Dipirona 500mg",
                    "dosagem": "1 comprimido",
                    "posologia": "Tomar 1 cp a cada 6h em caso de febre ou dor.",
                    "duracao": "3 dias",
                }
            ],
        },
    )
    assert res_doc_valido.status_code == 201
    data_doc = cast("dict[str, object]", res_doc_valido.json())
    assert data_doc["tipo_documento"] == "RECEITA_SIMPLES"
    assert len(cast("list[object]", data_doc["itens"])) == 1

    # 10. Query TMA Status (RN06)
    res_tma = await client.get(
        f"/api/v1/consultations/{cenario.atendimento.id}/tma-status",
    )
    assert res_tma.status_code == 200
    data_tma = cast("dict[str, object]", res_tma.json())
    assert "tempo_decorrido_segundos" in data_tma
    assert "aviso_visual" in data_tma

    # 11. Conclude and finalize consultation
    res_finalize = await client.post(
        f"/api/v1/consultations/{cenario.atendimento.id}/finalize",
        json={
            "organizacao_id": cenario.organizacao.id,
        },
    )
    assert res_finalize.status_code == 200
    assert cast("dict[str, object]", res_finalize.json())["is_finalizado"] is True

    # 12. Attending physician CAN read medical record after CONCLUIDO (CFM 1.821/2007)
    res_prontuario_pos = await client.get(
        f"/api/v1/consultations/{cenario.atendimento.id}/prontuario",
    )
    assert res_prontuario_pos.status_code == 200
    data_prontuario = cast("dict[str, object]", res_prontuario_pos.json())
    assert data_prontuario["is_finalizado"] is True
    assert data_prontuario["evolucao"] is not None

    # 13. Verify immutability: attempting mutation on CONCLUIDO returns 403 Forbidden
    res_soap_after = await client.post(
        f"/api/v1/consultations/{cenario.atendimento.id}/soap",
        json=soap_payload,
    )
    assert res_soap_after.status_code == 403
    assert "atendimento já concluído" in str(res_soap_after.json()["detail"])

    # 14. Verify immutability: attempting to issue document returns 403 Forbidden
    res_doc_after = await client.post(
        f"/api/v1/consultations/{cenario.atendimento.id}/documents",
        json={
            "organizacao_id": cenario.organizacao.id,
            "tipo_documento": "RECEITA_SIMPLES",
            "itens": [
                {
                    "medicamento": "Paracetamol 500mg",
                    "dosagem": "1 cp",
                    "posologia": "1 cp se dor",
                }
            ],
        },
    )
    assert res_doc_after.status_code == 403
    assert "atendimento já concluído" in str(res_doc_after.json()["detail"])


@pytest.mark.usefixtures("clean_db")
@pytest.mark.asyncio
async def test_consultation_mutation_endpoints_unauthenticated_blocked(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate that mutation endpoints without Bearer token return 401 Unauthorized."""
    cenario = await seed_clinical_scenario(db_session)
    async_client.headers["X-Tenant-ID"] = str(cenario.organizacao.id)
    # Ensure Authorization header is absent
    async_client.headers.pop("Authorization", None)
    client = async_client

    atend_id = cenario.atendimento.id

    # 1. POST /soap without token -> 401
    resp_soap = await client.post(
        f"/api/v1/consultations/{atend_id}/soap",
        json={"anamnese": "teste", "conduta": "teste"},
    )
    assert resp_soap.status_code == 401
    assert "não fornecida" in str(resp_soap.json()["detail"])

    # 2. POST /documents without token -> 401
    resp_doc = await client.post(
        f"/api/v1/consultations/{atend_id}/documents",
        json={"tipo_documento": "RECEITA_SIMPLES", "itens": []},
    )
    assert resp_doc.status_code == 401
    assert "não fornecida" in str(resp_doc.json()["detail"])

    # 3. POST /finalize without token -> 401
    resp_fin = await client.post(
        f"/api/v1/consultations/{atend_id}/finalize",
        json={},
    )
    assert resp_fin.status_code == 401
    assert "não fornecida" in str(resp_fin.json()["detail"])

    # 4. POST /documents/{doc_id}/sign without token -> 401
    resp_sign = await client.post(
        f"/api/v1/consultations/{atend_id}/documents/{uuid4()}/sign",
        json={"token": "fake-token", "provider": "fake"},
    )
    assert resp_sign.status_code == 401
    assert "não fornecida" in str(resp_sign.json()["detail"])


@pytest.mark.usefixtures("clean_db")
@pytest.mark.asyncio
async def test_consultation_mutation_endpoints_unassigned_physician_blocked(
    db_session: AsyncSession,
    async_client: AsyncClient,
) -> None:
    """Validate that non-assigned physician receives 403 Forbidden Problem Details."""
    cenario = await seed_clinical_scenario(db_session)
    medico_intruso = make_profissional(
        cenario.organizacao.id,
        cpf="99988877766",
        email="dr.intruso@hospital.local",
        papel=Role.MEDICO,
        crm="55443",
        crm_uf="SP",
    )
    db_session.add(medico_intruso)
    await db_session.commit()
    await db_session.refresh(medico_intruso)

    async_client.headers["X-Tenant-ID"] = str(cenario.organizacao.id)
    async_client.headers.update(
        auth_headers(Role.MEDICO, cenario.organizacao.id, medico_intruso.id)
    )
    client = async_client
    atend_id = cenario.atendimento.id

    # 1. Intruding doctor attempting POST /soap -> 403
    resp_soap = await client.post(
        f"/api/v1/consultations/{atend_id}/soap",
        json={"anamnese": "teste", "conduta": "teste"},
    )
    assert resp_soap.status_code == 403
    err_soap = cast("dict[str, object]", resp_soap.json())
    assert err_soap["title"] == "Forbidden"
    assert "não é o profissional assistente" in str(err_soap["detail"])

    # 2. Intruding doctor attempting POST /documents -> 403
    resp_doc = await client.post(
        f"/api/v1/consultations/{atend_id}/documents",
        json={"tipo_documento": "RECEITA_SIMPLES", "itens": []},
    )
    assert resp_doc.status_code == 403
    assert "não é o profissional assistente" in str(resp_doc.json()["detail"])

    # 3. Intruding doctor attempting POST /finalize -> 403
    resp_fin = await client.post(
        f"/api/v1/consultations/{atend_id}/finalize",
        json={},
    )
    assert resp_fin.status_code == 403
    assert "não é o profissional assistente" in str(resp_fin.json()["detail"])

    # 4. Intruding doctor attempting POST /documents/{doc_id}/sign -> 403
    resp_sign = await client.post(
        f"/api/v1/consultations/{atend_id}/documents/{uuid4()}/sign",
        json={"token": "fake-token", "provider": "fake"},
    )
    assert resp_sign.status_code == 403
    assert "não é o profissional assistente" in str(resp_sign.json()["detail"])
