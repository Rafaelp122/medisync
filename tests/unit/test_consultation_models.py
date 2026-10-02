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
    # Alias compatibility check
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
        # Lista C1 (Permitidos digitalmente via RECEITA_CONTROLE_ESPECIAL_C1)
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
    # Não deve levantar exceção
    validar_substancia_permitida_telemedicina(medicamento_permitido)


def test_criar_evolucao_clinica_sucesso() -> None:
    from src.modules.consultation.domain.models import EvolucaoClinica

    atend_id = uuid7()
    med_id = uuid7()
    evolucao = EvolucaoClinica(
        organizacao_id=1,
        atendimento_id=atend_id,
        medico_id=med_id,
        anamnese="Paciente relata dor de garganta e febre moderada há 2 dias.",
        exame_fisico_virtual="Orofaringe hiperemiada sem placas exsudativas.",
        cid10_principal="J02.9",
        conduta="Prescrito sintomáticos, repouso e hidratação oral abundante.",
    )
    assert evolucao.id is not None
    assert evolucao.organizacao_id == 1
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

    # organizacao_id inválido
    with pytest.raises(ConsultaInvalidaError, match="organizacao_id"):
        EvolucaoClinica(
            organizacao_id=0,
            atendimento_id=atend_id,
            medico_id=med_id,
            anamnese="Queixa",
            conduta="Conduta",
        )

    # anamnese vazia
    with pytest.raises(ConsultaInvalidaError, match="Anamnese"):
        EvolucaoClinica(
            organizacao_id=1,
            atendimento_id=atend_id,
            medico_id=med_id,
            anamnese="   ",
            conduta="Conduta",
        )

    # conduta vazia
    with pytest.raises(ConsultaInvalidaError, match="Conduta"):
        EvolucaoClinica(
            organizacao_id=1,
            atendimento_id=atend_id,
            medico_id=med_id,
            anamnese="Anamnese válida",
            conduta="   ",
        )

    # CID-10 inválido
    with pytest.raises(ConsultaInvalidaError, match="CID-10"):
        EvolucaoClinica(
            organizacao_id=1,
            atendimento_id=atend_id,
            medico_id=med_id,
            anamnese="Anamnese válida",
            conduta="Conduta válida",
            cid10_principal="INVALID_CID_10_TOO_LONG",
        )


def test_evolucao_clinica_bloqueio_exclusao_consulta_finalizada() -> None:
    from src.modules.consultation.domain.models import EvolucaoClinica

    evolucao = EvolucaoClinica(
        organizacao_id=1,
        atendimento_id=uuid7(),
        medico_id=uuid7(),
        anamnese="Paciente com tosse seca persistente.",
        conduta="Xarope expectorante e reavaliação se febre.",
        cid10_principal="R05",
    )

    # Status em andamento permite exclusão (se necessário antes de assinar)
    evolucao.validar_pode_excluir(status_atendimento="EM_ATENDIMENTO")

    # Status terminais bloqueiam exclusão
    for status_terminal in ["CONCLUIDO", "PACIENTE_AUSENTE", "CANCELADO_PACIENTE"]:
        with pytest.raises(ConsultaFinalizadaError, match="finalizada"):
            evolucao.validar_pode_excluir(status_atendimento=status_terminal)

    # Bloqueio explícito por marcar_finalizado
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
        organizacao_id=1,
        atendimento_id=uuid7(),
        medico_id=uuid7(),
        tipo_documento=TipoDocumentoClinico.RECEITA_SIMPLES,
        chave_s3="s3://medisync-docs/1/atendimentos/123/receita.pdf",
        sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        id=doc_id,
    )
    assert doc.id == doc_id
    assert doc.tipo_documento == TipoDocumentoClinico.RECEITA_SIMPLES
    assert doc.sha256_hash.islower()
    assert len(doc.sha256_hash) == 64
    assert doc.is_finalizado is False
    assert len(doc.itens) == 0

    item = DocumentoItem(
        organizacao_id=1,
        documento_id=doc.id,
        medicamento="Dipirona 500mg",
        dosagem="1 comprimido",
        posologia="Tomar 1 comprimido de 6/6h se dor ou febre",
        duracao="5 dias",
        controle_especial=False,
    )
    doc.adicionar_item(item)
    assert len(doc.itens) == 1
    assert doc.itens[0].medicamento == "Dipirona 500mg"
    assert doc.itens[0].organizacao_id == 1


def test_documento_clinico_validacoes_sha256_e_campos() -> None:
    from src.modules.consultation.domain.models import (
        DocumentoClinico,
        TipoDocumentoClinico,
    )

    valid_sha = "a" * 64
    atend_id = uuid7()
    med_id = uuid7()

    # organizacao_id inválido
    with pytest.raises(ConsultaInvalidaError, match="organizacao_id"):
        DocumentoClinico(
            organizacao_id=0,
            atendimento_id=atend_id,
            medico_id=med_id,
            tipo_documento=TipoDocumentoClinico.RECEITA_SIMPLES,
            chave_s3="s3://bucket/doc.pdf",
            sha256_hash=valid_sha,
        )

    # chave_s3 vazia
    with pytest.raises(ConsultaInvalidaError, match="chave_s3"):
        DocumentoClinico(
            organizacao_id=1,
            atendimento_id=atend_id,
            medico_id=med_id,
            tipo_documento=TipoDocumentoClinico.RECEITA_SIMPLES,
            chave_s3="   ",
            sha256_hash=valid_sha,
        )

    # sha256 tamanho != 64
    with pytest.raises(ConsultaInvalidaError, match="SHA-256"):
        DocumentoClinico(
            organizacao_id=1,
            atendimento_id=atend_id,
            medico_id=med_id,
            tipo_documento=TipoDocumentoClinico.RECEITA_SIMPLES,
            chave_s3="s3://bucket/doc.pdf",
            sha256_hash="abc",
        )

    # sha256 não hexadecimal
    with pytest.raises(ConsultaInvalidaError, match="SHA-256"):
        DocumentoClinico(
            organizacao_id=1,
            atendimento_id=atend_id,
            medico_id=med_id,
            tipo_documento=TipoDocumentoClinico.RECEITA_SIMPLES,
            chave_s3="s3://bucket/doc.pdf",
            sha256_hash="z" * 64,
        )


def test_documento_item_validacoes_e_multi_tenant() -> None:
    from src.modules.consultation.domain.models import (
        DocumentoClinico,
        DocumentoItem,
        TipoDocumentoClinico,
    )

    doc_id = uuid7()
    valid_sha = "b" * 64
    doc = DocumentoClinico(
        organizacao_id=1,
        atendimento_id=uuid7(),
        medico_id=uuid7(),
        tipo_documento=TipoDocumentoClinico.RECEITA_CONTROLE_ESPECIAL_C1,
        chave_s3="s3://bucket/c1.pdf",
        sha256_hash=valid_sha,
        id=doc_id,
    )

    # Criar item com organizacao_id diferente do documento
    item_cross_tenant = DocumentoItem(
        organizacao_id=2,  # Org 2 diferente da Org 1 do doc!
        documento_id=doc.id,
        medicamento="Sertralina 50mg",
        dosagem="1 comp",
        posologia="1x ao dia pela manhã",
    )
    with pytest.raises(ConsultaInvalidaError, match=r"multi-tenant|organizacao_id"):
        doc.adicionar_item(item_cross_tenant)

    # Tentativa de criar item com substância proibida Lista B (Clonazepam)
    with pytest.raises(PrescricaoFisicaObrigatoriaError):
        DocumentoItem(
            organizacao_id=1,
            documento_id=doc.id,
            medicamento="Clonazepam 2mg",
            dosagem="1 comp",
            posologia="À noite",
        )

    # Item válido para Lista C1 no documento C1 ganha controle_especial=True
    item_c1 = DocumentoItem(
        organizacao_id=1,
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
        organizacao_id=1,
        atendimento_id=uuid7(),
        medico_id=uuid7(),
        tipo_documento=TipoDocumentoClinico.ATESTADO_MEDICO,
        chave_s3="s3://bucket/atestado.pdf",
        sha256_hash="c" * 64,
    )

    # Status em andamento permite exclusão
    doc.validar_pode_excluir(status_atendimento="EM_ATENDIMENTO")

    # Status terminais bloqueiam
    for status_terminal in ["CONCLUIDO", "PACIENTE_AUSENTE", "CANCELADO_PACIENTE"]:
        with pytest.raises(ConsultaFinalizadaError, match="finalizada"):
            doc.validar_pode_excluir(status_atendimento=status_terminal)

    # Bloqueio explícito por marcar_finalizado
    doc.marcar_finalizado()
    assert doc.is_finalizado is True
    with pytest.raises(ConsultaFinalizadaError, match="finalizada"):
        doc.validar_pode_excluir()


def test_documento_clinico_tipo_invalido() -> None:
    from src.modules.consultation.domain.models import DocumentoClinico

    with pytest.raises(ConsultaInvalidaError, match="Tipo de documento"):
        DocumentoClinico(
            organizacao_id=1,
            atendimento_id=uuid7(),
            medico_id=uuid7(),
            tipo_documento="TIPO_INVENTADO",
            chave_s3="s3://bucket/doc.pdf",
            sha256_hash="d" * 64,
        )


def test_documento_item_validacoes_campos_obrigatorios() -> None:
    from src.modules.consultation.domain.models import DocumentoItem

    doc_id = uuid7()

    with pytest.raises(ConsultaInvalidaError, match="organizacao_id"):
        DocumentoItem(
            organizacao_id=0,
            documento_id=doc_id,
            medicamento="Dipirona",
            dosagem="500mg",
            posologia="6/6h",
        )

    with pytest.raises(ConsultaInvalidaError, match="medicamento"):
        DocumentoItem(
            organizacao_id=1,
            documento_id=doc_id,
            medicamento="   ",
            dosagem="500mg",
            posologia="6/6h",
        )

    with pytest.raises(ConsultaInvalidaError, match="Dosagem"):
        DocumentoItem(
            organizacao_id=1,
            documento_id=doc_id,
            medicamento="Dipirona",
            dosagem="   ",
            posologia="6/6h",
        )

    with pytest.raises(ConsultaInvalidaError, match="Posologia"):
        DocumentoItem(
            organizacao_id=1,
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
        organizacao_id=1,
        atendimento_id=uuid7(),
        medico_id=uuid7(),
        anamnese="Anamnese",
        conduta="Conduta",
    )
    # Não finalizado: hook não deve disparar exceção
    impedir_exclusao_evolucao_finalizada(None, None, evolucao)

    # Finalizado: hook bloqueia
    evolucao.marcar_finalizado()
    with pytest.raises(ConsultaFinalizadaError, match="finalizada"):
        impedir_exclusao_evolucao_finalizada(None, None, evolucao)

    doc = DocumentoClinico(
        organizacao_id=1,
        atendimento_id=uuid7(),
        medico_id=uuid7(),
        tipo_documento=TipoDocumentoClinico.RECEITA_SIMPLES,
        chave_s3="s3://bucket/doc.pdf",
        sha256_hash="e" * 64,
    )
    # Não finalizado: hook não deve disparar exceção
    impedir_exclusao_documento_finalizado(None, None, doc)

    # Finalizado: hook bloqueia
    doc.marcar_finalizado()
    with pytest.raises(ConsultaFinalizadaError, match="finalizada"):
        impedir_exclusao_documento_finalizado(None, None, doc)
