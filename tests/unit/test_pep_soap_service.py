"""Unit tests for PEP SOAP workflow, Portaria 344/98 safeguards, and RN06."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from src.core.uuid7 import uuid7
from src.modules.consultation.application.dtos import (
    CriarItemPrescricaoDTO,
    EmitirDocumentoClinicoCommand,
    TMAStatusDTO,
)
from src.modules.consultation.domain.exceptions import (
    ConsultaFinalizadaError,
    ConsultaInvalidaError,
    PrescricaoFisicaObrigatoriaError,
)

from tests.factories.consultation import (
    make_documento_clinico,
    make_evolucao_clinica,
)
from tests.helpers import make_pep_service


def test_validar_prescricao_permitida() -> None:
    """Ensure permitted telemedicine drugs pass validation without error."""
    service = make_pep_service(AsyncMock())

    # Simple prescription and antimicrobials
    service.validar_prescricao("Dipirona Monoidratada 500mg")
    service.validar_prescricao("Paracetamol 750mg comprimido")
    service.validar_prescricao("Amoxicilina com Clavulanato de Potássio 875mg")
    service.validar_prescricao("Azitromicina 500mg")
    service.validar_prescricao("Ibuprofeno 600mg")
    service.validar_prescricao("Omeprazol 20mg cápsulas")


@pytest.mark.parametrize(
    "substancia_proibida",
    [
        # Lista A (Talonário Amarelo - Entorpecentes)
        "Sulfato de Morfina 10mg comprimidos",
        "Adesivo transdérmico de Fentanil 25mcg",
        "Fentanila injetável 50mcg/ml",
        "Cloridrato de Oxicodona 10mg",
        "Metadona 10mg",
        "Ópio pó 100mg",
        # Lista B1 (Talonário Azul - Benzodiazepínicos e Hipnóticos)
        "Clonazepam 2mg comprimido",
        "Gotas de Rivotril 2.5mg/ml",
        "Diazepam 10mg VO",
        "Valium 5mg",
        "Alprazolam 0.5mg",
        "Frontal 1mg",
        "Bromazepam 3mg",
        "Lorazepam 2mg",
        "Midazolam 15mg",
        "Zolpidem 10mg ao deitar",
        # Lista B2 (Talonário Azul - Anorexígenos)
        "Sibutramina 15mg cápsula",
        "Femproporex 25mg",
        "Anfepramona 75mg",
    ],
)
def test_validar_prescricao_proibida_portaria_344(substancia_proibida: str) -> None:
    """Ensure yellow/blue pad drugs raise PrescricaoFisicaObrigatoriaError."""
    service = make_pep_service(AsyncMock())

    with pytest.raises(PrescricaoFisicaObrigatoriaError) as exc_info:
        service.validar_prescricao(substancia_proibida)

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "PRESCRICAO_FISICA_OBRIGATORIA"
    assert "Portaria SVS/MS nº 344/98" in exc_info.value.detail


@pytest.mark.parametrize(
    "tipo_proibido",
    ["NOTIFICACAO_RECEITA_A", "NOTIFICACAO_RECEITA_B", "notificacao_receita_a"],
)
@pytest.mark.asyncio
async def test_emitir_documento_tipo_proibido_falha(tipo_proibido: str) -> None:
    """Ensure requesting yellow or blue notification pad types fails with HTTP 422."""
    service = make_pep_service(AsyncMock())

    cmd = EmitirDocumentoClinicoCommand(
        atendimento_id=uuid7(),
        organizacao_id=1,
        medico_id=uuid7(),
        tipo_documento=tipo_proibido,
        itens=[
            CriarItemPrescricaoDTO(
                medicamento="Dipirona 500mg",
                dosagem="1 cp",
                posologia="1 cp a cada 6h",
            )
        ],
    )

    with pytest.raises(PrescricaoFisicaObrigatoriaError) as exc_info:
        await service.emitir_documento(cmd)

    assert exc_info.value.status_code == 422
    assert "talonário físico impresso de segurança" in exc_info.value.detail


def test_tma_sovereign_medical_act_preservation() -> None:
    """Ensure RN06: exceeding TMA emits visual indicator but never forces disconnect."""
    service = make_pep_service(AsyncMock())
    atend_id = uuid4()

    # Scenario 1: Inside planned TMA (e.g. 5 minutes into a 15-minute slot)
    inicio_recente = datetime.now(UTC) - timedelta(minutes=5)
    status_ok: TMAStatusDTO = service.calcular_tma_status(
        atendimento_id=atend_id,
        iniciado_em=inicio_recente,
        tma_planejado_segundos=900,
    )
    assert not status_ok.excedeu_tma
    assert status_ok.tempo_decorrido_segundos >= 300
    assert "Dentro do TMA" in status_ok.aviso_visual

    # Scenario 2: Exceeded planned TMA (e.g. 25 minutes into a 15-minute slot)
    inicio_antigo = datetime.now(UTC) - timedelta(minutes=25)
    status_excedido: TMAStatusDTO = service.calcular_tma_status(
        atendimento_id=atend_id,
        iniciado_em=inicio_antigo,
        tma_planejado_segundos=900,
    )
    assert status_excedido.excedeu_tma
    assert status_excedido.tempo_decorrido_segundos >= 1500
    assert "TMA ultrapassado" in status_excedido.aviso_visual
    assert "sem desconexão forçada (RN06)" in status_excedido.aviso_visual


def test_evolucao_clinica_soap_validation() -> None:
    """Verify field constraints and CID-10 validation on EvolucaoClinica."""
    # Mandatory anamnese (Subjetivo)
    with pytest.raises(ConsultaInvalidaError) as exc_info:
        make_evolucao_clinica(anamnese="   ")
    assert "Anamnese clínica é obrigatória" in exc_info.value.detail

    # Mandatory conduta (Plano)
    with pytest.raises(ConsultaInvalidaError) as exc_info:
        make_evolucao_clinica(conduta="")
    assert "Conduta clínica é obrigatória" in exc_info.value.detail

    # Invalid CID-10 format
    with pytest.raises(ConsultaInvalidaError) as exc_info:
        make_evolucao_clinica(cid10_principal="123")
    assert "Código CID-10 inválido" in exc_info.value.detail

    # Valid CID-10
    evolucao = make_evolucao_clinica(cid10_principal="j02.9")
    assert evolucao.cid10_principal == "J02.9"


def test_finalized_consultation_immutability() -> None:
    """Ensure PEP records cannot be deleted once marked finalized."""
    evolucao = make_evolucao_clinica()
    evolucao.validar_pode_excluir()  # Should pass when open

    evolucao.marcar_finalizado()
    assert evolucao.is_finalizado

    with pytest.raises(ConsultaFinalizadaError):
        evolucao.validar_pode_excluir()

    doc = make_documento_clinico()
    doc.validar_pode_excluir()  # Should pass when open

    doc.marcar_finalizado()
    assert doc.is_finalizado

    with pytest.raises(ConsultaFinalizadaError):
        doc.validar_pode_excluir()
