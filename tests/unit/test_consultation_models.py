"""Unit tests for consultation models, exceptions, and substances validation."""

import pytest
from src.core.errors import DomainError, ValidationError
from src.core.uuid7 import uuid7
from src.modules.consultation.domain.exceptions import (
    ConsultaFinalizadaError,
    ConsultaInvalidaError,
    PrescricaoFisicaObrigatoriaError,
    PrescricaoFisicaObrigatoriaException,
)
from src.modules.consultation.domain.models._substances import (
    validar_substancia_permitida_telemedicina,
)


def test_consultation_exceptions_hierarchy_and_attributes() -> None:
    err_presc = PrescricaoFisicaObrigatoriaError("Morfina exige talonário amarelo.")
    assert isinstance(err_presc, ValidationError)
    assert err_presc.status_code == 422
    assert err_presc.code == "PRESCRICAO_FISICA_OBRIGATORIA"
    assert PrescricaoFisicaObrigatoriaException is PrescricaoFisicaObrigatoriaError

    err_fin = ConsultaFinalizadaError(
        "Não é permitido alterar ou excluir registros de consulta finalizada."
    )
    assert isinstance(err_fin, DomainError)
    assert err_fin.status_code == 409
    assert err_fin.code == "CONSULTA_FINALIZADA_IMUTAVEL"

    err_inv = ConsultaInvalidaError("Anamnese não pode ser vazia.")
    assert isinstance(err_inv, ValidationError)
    assert err_inv.status_code == 422
    assert err_inv.code == "CONSULTA_INVALIDA"


@pytest.mark.parametrize(
    "medicamento_proibido",
    [
        "Morfina 10mg comprimidos",
        "Sulfato de Morfina 10mg/mL",
        "Fentanil 50mcg adesivo transdérmico",
        "Citrato de Fentanila injetável",
        "Oxicodona 10mg",
        "Cloridrato de Metadona 10mg",
        "Meperidina (Petidina) 50mg/mL",
        "Hidromorfona 4mg",
        "Sufentanil 50mcg/mL",
        "Remifentanil 2mg",
        "Clonazepam 2mg comprimidos",
        "Rivotril (clonazepam 2,5mg/mL)",
        "Diazepam 10mg",
        "Valium (diazepam)",
        "Alprazolam 0.5mg",
        "Frontal (alprazolam 1mg)",
        "Lorazepam 2mg",
        "Midazolam 15mg",
        "Bromazepam 3mg",
        "Clobazam 10mg",
        "Flunitrazepam 1mg",
        "Zolpidem 10mg",
        "Hemitartarato de Zolpidem 10mg",
        "Zopiclona 7.5mg",
        "Sibutramina 15mg",
        "Cloridrato de Sibutramina monoidratado",
        "Femproporex 25mg",
        "Anfepramona 75mg",
    ],
)
def test_validar_substancia_proibida_listas_a_e_b(medicamento_proibido: str) -> None:
    with pytest.raises(PrescricaoFisicaObrigatoriaError) as exc_info:
        validar_substancia_permitida_telemedicina(medicamento_proibido)
    assert "Portaria SVS/MS nº 344/98" in exc_info.value.detail
    assert "talonário físico" in exc_info.value.detail


@pytest.mark.parametrize(
    "medicamento_permitido",
    [
        "Dipirona Monoidratada 500mg",
        "Paracetamol 750mg",
        "Ibuprofeno 600mg",
        "Amoxicilina + Clavulanato de Potássio 875mg",
        "Azitromicina 500mg",
        "Ciprofloxacino 500mg",
        "Losartana Potássica 50mg",
        "Amlodipino 5mg",
        "Omeprazol 20mg",
        "Metformina 850mg",
        "Cloridrato de Sertralina 50mg",
        "Fluoxetina 20mg",
        "Oxalato de Escitalopram 10mg",
        "Cloridrato de Venlafaxina 75mg",
        "Pregabalina 75mg",
        "Gabapentina 300mg",
        "Carbamazepina 200mg",
        "Hemifumarato de Quetiapina 25mg",
        "Risperidona 1mg",
    ],
)
def test_validar_substancia_permitida(medicamento_permitido: str) -> None:
    validar_substancia_permitida_telemedicina(medicamento_permitido)


def test_criar_evolucao_clinica_sucesso() -> None:
    from src.modules.consultation.domain.models import EvolucaoClinica

    atend_id = uuid7()
    med_id = uuid7()
    evolucao = EvolucaoClinica(
        atendimento_id=atend_id,
        medico_id=med_id,
        anamnese="Paciente relata dor de garganta e febre moderada há 2 dias.",
        exame_fisico_virtual="Orofaringe hiperemiada sem placas exsudativas.",
        cid10_principal="J02.9",
        conduta="Prescrito sintomáticos, repouso e hidratação oral abundante.",
    )
    assert evolucao.id is not None
    assert not hasattr(evolucao, "organizacao_id")
    assert evolucao.atendimento_id == atend_id
    assert evolucao.medico_id == med_id
    assert evolucao.anamnese.startswith("Paciente relata")
    assert evolucao.exame_fisico_virtual is not None
    assert evolucao.cid10_principal == "J02.9"
    assert evolucao.conduta.startswith("Prescrito")
    assert evolucao.registrado_em is not None
    assert evolucao.is_finalizado is False


def test_evolucao_clinica_validacoes_obrigatorias() -> None:
    from src.modules.consultation.domain.models import EvolucaoClinica

    atend_id = uuid7()
    med_id = uuid7()

    with pytest.raises(ConsultaInvalidaError, match="Anamnese"):
        EvolucaoClinica(
            atendimento_id=atend_id,
            medico_id=med_id,
            anamnese="   ",
            conduta="Conduta",
        )

    with pytest.raises(ConsultaInvalidaError, match="Conduta"):
        EvolucaoClinica(
            atendimento_id=atend_id,
            medico_id=med_id,
            anamnese="Anamnese válida",
            conduta="   ",
        )

    with pytest.raises(ConsultaInvalidaError, match="CID-10"):
        EvolucaoClinica(
            atendimento_id=atend_id,
            medico_id=med_id,
            anamnese="Anamnese válida",
            conduta="Conduta válida",
            cid10_principal="INVALID_CID_10_TOO_LONG",
        )


def test_evolucao_clinica_bloqueio_exclusao_consulta_finalizada() -> None:
    from src.modules.consultation.domain.models import EvolucaoClinica

    evolucao = EvolucaoClinica(
        atendimento_id=uuid7(),
        medico_id=uuid7(),
        anamnese="Paciente com tosse seca persistente.",
        conduta="Xarope expectorante e reavaliação se febre.",
        cid10_principal="R05",
    )

    evolucao.validar_pode_excluir(status_atendimento="EM_ATENDIMENTO")

    for status_terminal in ["CONCLUIDO", "PACIENTE_AUSENTE", "CANCELADO_PACIENTE"]:
        with pytest.raises(ConsultaFinalizadaError, match="finalizada"):
            evolucao.validar_pode_excluir(status_atendimento=status_terminal)

    evolucao.marcar_finalizado()
    assert evolucao.is_finalizado is True
    with pytest.raises(ConsultaFinalizadaError, match="finalizada"):
        evolucao.validar_pode_excluir()


def test_criar_documento_clinico_e_itens_sucesso() -> None:
    from src.modules.consultation.domain.models import (
        DocumentoClinico,
        DocumentoItem,
        TipoDocumentoClinico,
    )

    doc_id = uuid7()
    doc = DocumentoClinico(
        atendimento_id=uuid7(),
        medico_id=uuid7(),
        tipo_documento=TipoDocumentoClinico.RECEITA_SIMPLES,
        chave_s3="consultations/123/documents/receita.pdf",
        sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        id=doc_id,
    )
    assert doc.id == doc_id
    assert not hasattr(doc, "organizacao_id")
    assert doc.tipo_documento == TipoDocumentoClinico.RECEITA_SIMPLES
    assert doc.sha256_hash is not None
    assert doc.sha256_hash.islower()
    assert len(doc.sha256_hash) == 64
    assert doc.is_finalizado is False
    assert len(doc.itens) == 0

    item = DocumentoItem(
        documento_id=doc.id,
        medicamento="Dipirona 500mg",
        dosagem="1 comprimido",
        posologia="Tomar 1 comprimido de 6/6h se dor ou febre",
        duracao="5 dias",
        controle_especial=False,
    )
    assert not hasattr(item, "organizacao_id")
    doc.adicionar_item(item)
    assert len(doc.itens) == 1
    assert doc.itens[0].medicamento == "Dipirona 500mg"


def test_documento_clinico_validacoes_sha256_e_campos() -> None:
    from src.modules.consultation.domain.models import (
        DocumentoClinico,
        TipoDocumentoClinico,
    )

    valid_sha = "a" * 64
    atend_id = uuid7()
    med_id = uuid7()

    with pytest.raises(ConsultaInvalidaError, match="chave_s3"):
        DocumentoClinico(
            atendimento_id=atend_id,
            medico_id=med_id,
            tipo_documento=TipoDocumentoClinico.RECEITA_SIMPLES,
            chave_s3="   ",
            sha256_hash=valid_sha,
        )

    with pytest.raises(ConsultaInvalidaError, match="SHA-256"):
        DocumentoClinico(
            atendimento_id=atend_id,
            medico_id=med_id,
            tipo_documento=TipoDocumentoClinico.RECEITA_SIMPLES,
            chave_s3="s3://bucket/doc.pdf",
            sha256_hash="abc",
        )

    with pytest.raises(ConsultaInvalidaError, match="SHA-256"):
        DocumentoClinico(
            atendimento_id=atend_id,
            medico_id=med_id,
            tipo_documento=TipoDocumentoClinico.RECEITA_SIMPLES,
            chave_s3="s3://bucket/doc.pdf",
            sha256_hash="z" * 64,
        )


def test_documento_item_validacoes_portaria_344() -> None:
    from src.modules.consultation.domain.models import (
        DocumentoClinico,
        DocumentoItem,
        TipoDocumentoClinico,
    )

    doc_id = uuid7()
    valid_sha = "b" * 64
    doc = DocumentoClinico(
        atendimento_id=uuid7(),
        medico_id=uuid7(),
        tipo_documento=TipoDocumentoClinico.RECEITA_CONTROLE_ESPECIAL_C1,
        chave_s3="s3://bucket/c1.pdf",
        sha256_hash=valid_sha,
        id=doc_id,
    )

    with pytest.raises(PrescricaoFisicaObrigatoriaError):
        DocumentoItem(
            documento_id=doc.id,
            medicamento="Clonazepam 2mg",
            dosagem="1 comp",
            posologia="À noite",
        )

    item_c1 = DocumentoItem(
        documento_id=doc.id,
        medicamento="Cloridrato de Sertralina 50mg",
        dosagem="50mg",
        posologia="1 comprimido ao dia",
        duracao="30 dias",
    )
    doc.adicionar_item(item_c1)
    assert item_c1.controle_especial is True
    assert item_c1 in doc.itens


def test_documento_clinico_bloqueio_exclusao_consulta_finalizada() -> None:
    from src.modules.consultation.domain.models import (
        DocumentoClinico,
        TipoDocumentoClinico,
    )

    doc = DocumentoClinico(
        atendimento_id=uuid7(),
        medico_id=uuid7(),
        tipo_documento=TipoDocumentoClinico.ATESTADO_MEDICO,
        chave_s3="s3://bucket/atestado.pdf",
        sha256_hash="c" * 64,
    )

    doc.validar_pode_excluir(status_atendimento="EM_ATENDIMENTO")

    for status_terminal in ["CONCLUIDO", "PACIENTE_AUSENTE", "CANCELADO_PACIENTE"]:
        with pytest.raises(ConsultaFinalizadaError, match="finalizada"):
            doc.validar_pode_excluir(status_atendimento=status_terminal)

    doc.marcar_finalizado()
    assert doc.is_finalizado is True
    with pytest.raises(ConsultaFinalizadaError, match="finalizada"):
        doc.validar_pode_excluir()


def test_documento_clinico_tipo_invalido() -> None:
    from src.modules.consultation.domain.models import DocumentoClinico

    with pytest.raises(ConsultaInvalidaError, match="Tipo de documento"):
        DocumentoClinico(
            atendimento_id=uuid7(),
            medico_id=uuid7(),
            tipo_documento="TIPO_INVENTADO",
            chave_s3="s3://bucket/doc.pdf",
            sha256_hash="d" * 64,
        )


def test_documento_item_validacoes_campos_obrigatorios() -> None:
    from src.modules.consultation.domain.models import DocumentoItem

    doc_id = uuid7()

    with pytest.raises(ConsultaInvalidaError, match="medicamento"):
        DocumentoItem(
            documento_id=doc_id,
            medicamento="   ",
            dosagem="500mg",
            posologia="6/6h",
        )

    with pytest.raises(ConsultaInvalidaError, match="Dosagem"):
        DocumentoItem(
            documento_id=doc_id,
            medicamento="Dipirona",
            dosagem="   ",
            posologia="6/6h",
        )

    with pytest.raises(ConsultaInvalidaError, match="Posologia"):
        DocumentoItem(
            documento_id=doc_id,
            medicamento="Dipirona",
            dosagem="500mg",
            posologia="   ",
        )


def test_before_delete_listeners_bloqueiam_quando_finalizado() -> None:
    from src.modules.consultation.domain.models.documento_clinico import (
        DocumentoClinico,
        TipoDocumentoClinico,
        impedir_exclusao_documento_finalizado,
    )
    from src.modules.consultation.domain.models.evolucao_clinica import (
        EvolucaoClinica,
        impedir_exclusao_evolucao_finalizada,
    )

    evolucao = EvolucaoClinica(
        atendimento_id=uuid7(),
        medico_id=uuid7(),
        anamnese="Anamnese",
        conduta="Conduta",
    )
    impedir_exclusao_evolucao_finalizada(None, None, evolucao)

    evolucao.marcar_finalizado()
    with pytest.raises(ConsultaFinalizadaError, match="finalizada"):
        impedir_exclusao_evolucao_finalizada(None, None, evolucao)

    doc = DocumentoClinico(
        atendimento_id=uuid7(),
        medico_id=uuid7(),
        tipo_documento=TipoDocumentoClinico.RECEITA_SIMPLES,
        chave_s3="s3://bucket/doc.pdf",
        sha256_hash="e" * 64,
    )
    impedir_exclusao_documento_finalizado(None, None, doc)

    doc.marcar_finalizado()
    with pytest.raises(ConsultaFinalizadaError, match="finalizada"):
        impedir_exclusao_documento_finalizado(None, None, doc)


def test_documento_clinico_rascunho_e_registro_assinatura() -> None:
    from src.modules.consultation.domain.models import (
        DocumentoClinico,
        DocumentoItem,
        TipoDocumentoClinico,
    )

    doc = DocumentoClinico(
        atendimento_id=uuid7(),
        medico_id=uuid7(),
        tipo_documento=TipoDocumentoClinico.RECEITA_SIMPLES,
        chave_s3="s3://bucket/rascunho.pdf",
        sha256_hash=None,
    )
    assert doc.sha256_hash is None
    assert doc.assinado_em is None
    assert doc.finalizado_em is None
    assert doc.is_finalizado is False

    valid_hash = "a" * 64
    doc.registrar_assinatura(valid_hash)
    assert doc.sha256_hash == valid_hash
    assert doc.assinado_em is not None

    with pytest.raises(ConsultaInvalidaError, match="Hash SHA-256 inválido"):
        doc.registrar_assinatura("curto_invalido")

    doc.marcar_finalizado()
    assert doc.is_finalizado is True
    assert doc.finalizado_em is not None

    with pytest.raises(ConsultaFinalizadaError, match="já finalizado"):
        doc.registrar_assinatura("b" * 64)

    item = DocumentoItem(
        documento_id=doc.id,
        medicamento="Paracetamol 750mg",
        dosagem="1 cp",
        posologia="1 cp de 8 em 8h",
    )
    with pytest.raises(ConsultaFinalizadaError, match="consulta finalizada"):
        doc.adicionar_item(item)


def test_evolucao_clinica_atualizar_soap_sucesso_e_validacoes() -> None:
    from src.modules.consultation.domain.models import EvolucaoClinica

    evolucao = EvolucaoClinica(
        atendimento_id=uuid7(),
        medico_id=uuid7(),
        anamnese="Anamnese inicial",
        conduta="Conduta inicial",
    )
    ts_original = evolucao.registrado_em

    evolucao.atualizar_soap(
        anamnese="Anamnese atualizada",
        conduta="Conduta atualizada",
        exame_fisico_virtual="Sinais vitais normais",
        cid10_principal="j02.9",
    )
    assert evolucao.anamnese == "Anamnese atualizada"
    assert evolucao.conduta == "Conduta atualizada"
    assert evolucao.exame_fisico_virtual == "Sinais vitais normais"
    assert evolucao.cid10_principal == "J02.9"
    assert evolucao.registrado_em >= ts_original

    with pytest.raises(ConsultaInvalidaError, match="Anamnese clínica é obrigatória"):
        evolucao.atualizar_soap(anamnese="   ", conduta="Ok")

    with pytest.raises(ConsultaInvalidaError, match="Conduta clínica é obrigatória"):
        evolucao.atualizar_soap(anamnese="Ok", conduta="   ")

    with pytest.raises(ConsultaInvalidaError, match="Código CID-10 inválido"):
        evolucao.atualizar_soap(anamnese="Ok", conduta="Ok", cid10_principal="999")

    evolucao.marcar_finalizado()
    assert evolucao.is_finalizado is True
    assert evolucao.finalizado_em is not None

    with pytest.raises(ConsultaFinalizadaError, match="consulta finalizada"):
        evolucao.atualizar_soap(anamnese="Nova", conduta="Nova")
