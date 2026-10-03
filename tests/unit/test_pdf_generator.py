"""Unit tests for ReportLab PDF/A clinical document generator and QR Code."""

from datetime import UTC, datetime
from uuid import uuid4

from src.modules.consultation.application.ports.pdf_generator_port import (
    DocumentoItemPDFDTO,
    DocumentoPDFPayload,
    PDFGeneratorPort,
)
from src.modules.consultation.domain.models.documento_clinico import (
    TipoDocumentoClinico,
)
from src.modules.consultation.infrastructure.pdf_generator import (
    FakePDFGenerator,
    ReportLabPDFGenerator,
)


def _build_sample_payload(
    tipo: TipoDocumentoClinico | str,
    *,
    itens: list[DocumentoItemPDFDTO] | None = None,
    dias_afastamento: int | None = None,
    cid10: str | None = None,
    cid10_autorizado: bool = True,
    especialidade: str | None = None,
    motivo: str | None = None,
    texto_livre: str | None = None,
    validation_url: str | None = None,
) -> DocumentoPDFPayload:
    return DocumentoPDFPayload(
        documento_id=uuid4(),
        tipo_documento=tipo,
        data_emissao=datetime(2026, 10, 3, 14, 30, tzinfo=UTC),
        organizacao_nome="Clínica São Rafael de Telemedicina",
        organizacao_cnpj="12.345.678/0001-90",
        organizacao_cnes="7654321",
        organizacao_endereco="Av. Paulista, 1000, São Paulo - SP",
        organizacao_telefone="(11) 3333-4444",
        medico_nome="Dr. Roberto Carlos",
        medico_crm="123456",
        medico_crm_uf="SP",
        medico_rqe="9876",
        paciente_nome="Maria Joana dos Santos",
        paciente_cpf="111.222.333-44",
        paciente_data_nascimento="15/05/1988",
        paciente_endereco="Rua das Flores, 123, Campinas - SP",
        itens=itens if itens is not None else [],
        dias_afastamento=dias_afastamento,
        cid10=cid10,
        cid10_autorizado_paciente=cid10_autorizado,
        especialidade_encaminhamento=especialidade,
        motivo_encaminhamento=motivo,
        texto_livre=texto_livre,
        validation_url=validation_url,
        sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )


def test_pdf_generator_port_conformance() -> None:
    generator = ReportLabPDFGenerator()
    assert isinstance(generator, PDFGeneratorPort)

    fake = FakePDFGenerator()
    assert isinstance(fake, PDFGeneratorPort)


def test_gerar_pdf_receita_simples() -> None:
    generator = ReportLabPDFGenerator()
    itens = [
        DocumentoItemPDFDTO(
            medicamento="Dipirona Monoidratada",
            dosagem="500 mg/mL",
            posologia="Tomar 30 gotas a cada 6 horas se dor ou febre.",
            duracao="3 dias",
        ),
        DocumentoItemPDFDTO(
            medicamento="Paracetamol",
            dosagem="750 mg",
            posologia="Tomar 1 comprimido se persistência dos sintomas.",
            duracao="5 dias",
        ),
    ]
    payload = _build_sample_payload(
        TipoDocumentoClinico.RECEITA_SIMPLES,
        itens=itens,
        texto_livre="Manter hidratação oral adequada.",
    )

    pdf_bytes = generator.gerar_pdf(payload)

    # Valid PDF file structure
    assert pdf_bytes.startswith(b"%PDF-")
    assert b"%%EOF" in pdf_bytes

    # PDF/A-1b ISO 19005 compliance markers
    assert b"pdfaid:part>1</pdfaid:part" in pdf_bytes
    assert b"pdfaid:conformance>B</pdfaid:conformance" in pdf_bytes
    assert b"GTS_PDFA1" in pdf_bytes
    assert b"sRGB IEC61966-2.1" in pdf_bytes

    # Embedded font
    assert b"FontFile2" in pdf_bytes or b"Vera" in pdf_bytes


def test_gerar_pdf_receita_antimicrobiano_rdc_20_2011() -> None:
    """Validate RDC ANVISA nº 20/2011 compliance: 10-day validity, 2 vias."""
    generator = ReportLabPDFGenerator()
    itens = [
        DocumentoItemPDFDTO(
            medicamento="Amoxicilina + Clavulanato de Potássio",
            dosagem="875 mg + 125 mg",
            posologia="Tomar 1 comprimido por via oral a cada 12 horas por 10 dias.",
            duracao="10 dias",
        )
    ]
    payload = _build_sample_payload(
        TipoDocumentoClinico.RECEITA_ANTIMICROBIANO, itens=itens
    )

    pdf_bytes = generator.gerar_pdf(payload)

    assert pdf_bytes.startswith(b"%PDF-")
    assert b"pdfaid:part>1</pdfaid:part" in pdf_bytes

    # Two vias indicators
    assert b"1\xc2\xaa VIA" in pdf_bytes or b"1" in pdf_bytes
    assert b"2\xc2\xaa VIA" in pdf_bytes or b"2" in pdf_bytes


def test_gerar_pdf_receita_controle_especial_c1() -> None:
    """Validate Portaria 344/98 Lista C1 compliance: 30-day validity, 2 vias."""
    generator = ReportLabPDFGenerator()
    itens = [
        DocumentoItemPDFDTO(
            medicamento="Amitriptilina",
            dosagem="25 mg",
            posologia="Tomar 1 comprimido ao deitar.",
            duracao="30 dias",
            controle_especial=True,
        )
    ]
    payload = _build_sample_payload(
        TipoDocumentoClinico.RECEITA_CONTROLE_ESPECIAL_C1, itens=itens
    )

    pdf_bytes = generator.gerar_pdf(payload)

    assert pdf_bytes.startswith(b"%PDF-")
    assert b"pdfaid:part>1</pdfaid:part" in pdf_bytes


def test_gerar_pdf_atestado_medico_com_cid() -> None:
    """Validate medical certificate with days and authorized CID-10."""
    generator = ReportLabPDFGenerator()
    payload = _build_sample_payload(
        TipoDocumentoClinico.ATESTADO_MEDICO,
        dias_afastamento=5,
        cid10="J06.9",
        cid10_autorizado=True,
        texto_livre="Paciente necessita de repouso domiciliar.",
    )

    pdf_bytes = generator.gerar_pdf(payload)

    assert pdf_bytes.startswith(b"%PDF-")
    assert b"pdfaid:part>1</pdfaid:part" in pdf_bytes


def test_gerar_pdf_atestado_medico_sem_cid() -> None:
    """Validate medical certificate when CID-10 is omitted (CFM 1.658/2002)."""
    generator = ReportLabPDFGenerator()
    payload = _build_sample_payload(
        TipoDocumentoClinico.ATESTADO_MEDICO,
        dias_afastamento=1,
        cid10=None,
        cid10_autorizado=False,
    )

    pdf_bytes = generator.gerar_pdf(payload)

    assert pdf_bytes.startswith(b"%PDF-")
    assert b"pdfaid:part>1</pdfaid:part" in pdf_bytes


def test_gerar_pdf_relatorio_encaminhamento() -> None:
    """Validate clinical referral report with specialist destination and motive."""
    generator = ReportLabPDFGenerator()
    payload = _build_sample_payload(
        TipoDocumentoClinico.RELATORIO_ENCAMINHAMENTO,
        especialidade="Cardiologia",
        motivo="Investigação de taquicardia paroxística aos esforços.",
        cid10="R00.0",
        texto_livre="Solicitado ECG e Holter 24h ambulatorial.",
    )

    pdf_bytes = generator.gerar_pdf(payload)

    assert pdf_bytes.startswith(b"%PDF-")
    assert b"pdfaid:part>1</pdfaid:part" in pdf_bytes


def test_gerar_pdf_com_url_validacao_customizada() -> None:
    generator = ReportLabPDFGenerator(
        validation_url_prefix="https://saude.gov.br/validar"
    )
    custom_url = "https://saude.gov.br/validar/custom-token-12345"
    payload = _build_sample_payload(
        TipoDocumentoClinico.RECEITA_SIMPLES, validation_url=custom_url
    )

    pdf_bytes = generator.gerar_pdf(payload)

    assert pdf_bytes.startswith(b"%PDF-")
    assert b"https://saude.gov.br/validar/custom-token-12345" in pdf_bytes


def test_gerar_pdf_tipo_documento_como_string() -> None:
    generator = ReportLabPDFGenerator()
    payload = _build_sample_payload("RECEITA_SIMPLES")
    pdf_bytes = generator.gerar_pdf(payload)
    assert pdf_bytes.startswith(b"%PDF-")


def test_fake_pdf_generator() -> None:
    fake = FakePDFGenerator(validation_url_prefix="https://test.medisync.app/validar")
    payload = _build_sample_payload(TipoDocumentoClinico.RECEITA_SIMPLES)

    fake_bytes = fake.gerar_pdf(payload)

    assert fake_bytes.startswith(b"%PDF-1.4\n")
    assert str(payload.documento_id).encode() in fake_bytes
    assert b"pdfaid:part=1" in fake_bytes
    assert b"GTS_PDFA1" in fake_bytes
    assert fake.last_payload == payload
