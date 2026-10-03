"""Integration tests for PEP SOAP workflow, prescriptions, and TMA indicators."""

from collections.abc import AsyncGenerator
from typing import cast
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from src.core.database import Base, async_session_factory, engine
from src.main import app

from tests.factories.identity import (
    make_organizacao,
    make_paciente,
    make_profissional,
)
from tests.factories.queue import make_atendimento


@pytest.fixture(autouse=True)
async def setup_consultation_db() -> AsyncGenerator[None, None]:
    """Ensure database schema is ready before running tests and clean up after."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_consultation_soap_full_lifecycle_and_safeguards() -> None:
    """Test entire PEP workflow: SOAP notes, validation and immutability."""
    async with async_session_factory() as session:
        org = make_organizacao(cnpj="22222222000102")
        session.add(org)
        await session.commit()
        await session.refresh(org)

        paciente = make_paciente(org.id, cpf="33333333301")
        medico = make_profissional(
            org.id,
            cpf="44444444401",
            email="dr.rodrigo@hospital.com.br",
            papel="MEDICO",
            crm="54321",
            crm_uf="MG",
        )
        session.add_all([paciente, medico])
        await session.commit()
        await session.refresh(paciente)
        await session.refresh(medico)

        atendimento = make_atendimento(
            organizacao_id=org.id,
            paciente_id=paciente.id,
            status="EM_ATENDIMENTO",
        )
        session.add(atendimento)
        await session.commit()
        await session.refresh(atendimento)

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Tenant-ID": str(org.id)},
    ) as client:
        # 1. Register SOAP notes (Subjetivo, Objetivo, Avaliação, Plano)
        soap_payload = {
            "medico_id": str(medico.id),
            "organizacao_id": org.id,
            "anamnese": "Paciente queixa-se de odinofagia e coriza há 3 dias.",
            "exame_fisico_virtual": (
                "Orofaringe com hiperemia leve, sem placas purulentas."
            ),
            "cid10_principal": "J00",
            "conduta": "Orientada hidratação, analgesia e repouso.",
        }
        res_soap = await client.post(
            f"/api/v1/consultations/{atendimento.id}/soap",
            json=soap_payload,
        )
        assert res_soap.status_code == 200
        data_soap = cast("dict[str, object]", res_soap.json())
        assert data_soap["anamnese"] == soap_payload["anamnese"]
        assert data_soap["cid10_principal"] == "J00"
        assert data_soap["is_finalizado"] is False

        # 2. Update existing SOAP notes while consultation is open
        soap_update_payload = {
            "medico_id": str(medico.id),
            "organizacao_id": org.id,
            "anamnese": "Paciente queixa-se de odinofagia, coriza e febre há 3 dias.",
            "exame_fisico_virtual": (
                "Orofaringe com hiperemia leve e congestão nasal."
            ),
            "cid10_principal": "J00",
            "conduta": "Orientada hidratação abundante e paracetamol.",
        }
        res_soap_update = await client.post(
            f"/api/v1/consultations/{atendimento.id}/soap",
            json=soap_update_payload,
        )
        assert res_soap_update.status_code == 200
        data_updated = cast("dict[str, object]", res_soap_update.json())
        assert "febre" in str(data_updated["anamnese"])

        # 3. Get registered SOAP notes
        res_get_soap = await client.get(
            f"/api/v1/consultations/{atendimento.id}/soap",
        )
        assert res_get_soap.status_code == 200
        data_get_soap = cast("dict[str, object]", res_get_soap.json())
        assert data_get_soap["cid10_principal"] == "J00"

        # 4. Check 404 for nonexistent attendance SOAP
        res_not_found = await client.get(
            f"/api/v1/consultations/{uuid4()}/soap",
        )
        assert res_not_found.status_code == 404

        # 3. Pre-validate permitted medication
        res_val_ok = await client.post(
            f"/api/v1/consultations/{atendimento.id}/prescriptions/validate",
            json={"medicamento": "Dipirona 500mg comprimidos"},
        )
        assert res_val_ok.status_code == 200
        assert cast("dict[str, object]", res_val_ok.json())["status"] == "PERMITIDO"

        # 4. Pre-validate prohibited medication (Portaria 344/98 Lista B - Clonazepam)
        res_val_proibido = await client.post(
            f"/api/v1/consultations/{atendimento.id}/prescriptions/validate",
            json={"medicamento": "Clonazepam 2mg gotas"},
        )
        assert res_val_proibido.status_code == 422
        problem = cast("dict[str, object]", res_val_proibido.json())
        assert problem["code"] == "PRESCRICAO_FISICA_OBRIGATORIA"
        assert "Portaria SVS/MS nº 344/98" in str(problem["detail"])

        # 5. Attempt issuing prohibited document type NOTIFICACAO_RECEITA_A (Yellow pad)
        res_doc_tipo_proibido = await client.post(
            f"/api/v1/consultations/{atendimento.id}/documents",
            json={
                "medico_id": str(medico.id),
                "organizacao_id": org.id,
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

        # 6. Attempt issuing document with prohibited item (Morfina in RECEITA_SIMPLES)
        res_doc_item_proibido = await client.post(
            f"/api/v1/consultations/{atendimento.id}/documents",
            json={
                "medico_id": str(medico.id),
                "organizacao_id": org.id,
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

        # 7. Issue valid digital prescription (RECEITA_SIMPLES with Dipirona)
        res_doc_valido = await client.post(
            f"/api/v1/consultations/{atendimento.id}/documents",
            json={
                "medico_id": str(medico.id),
                "organizacao_id": org.id,
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

        # 8. Query TMA Status (RN06)
        res_tma = await client.get(
            f"/api/v1/consultations/{atendimento.id}/tma-status",
        )
        assert res_tma.status_code == 200
        data_tma = cast("dict[str, object]", res_tma.json())
        assert "tempo_decorrido_segundos" in data_tma
        assert "aviso_visual" in data_tma

        # 9. Conclude and finalize consultation
        res_finalize = await client.post(
            f"/api/v1/consultations/{atendimento.id}/finalize",
            json={
                "medico_id": str(medico.id),
                "organizacao_id": org.id,
            },
        )
        assert res_finalize.status_code == 200
        assert cast("dict[str, object]", res_finalize.json())["is_finalizado"] is True

        # 10. Verify immutability: attempting to edit SOAP returns 409
        res_soap_after = await client.post(
            f"/api/v1/consultations/{atendimento.id}/soap",
            json=soap_payload,
        )
        assert res_soap_after.status_code == 409
        assert res_soap_after.json()["code"] == "CONSULTA_FINALIZADA_IMUTAVEL"

        # 11. Verify immutability: attempting to issue document returns 409
        res_doc_after = await client.post(
            f"/api/v1/consultations/{atendimento.id}/documents",
            json={
                "medico_id": str(medico.id),
                "organizacao_id": org.id,
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
        assert res_doc_after.status_code == 409
