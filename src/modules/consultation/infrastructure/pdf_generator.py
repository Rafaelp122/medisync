"""ReportLab PDF/A clinical document generator with ITI verification QR Code."""

import io
from typing import Any

import qrcode
from qrcode.constants import ERROR_CORRECT_M
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfdoc, pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src.core.config import get_settings
from src.modules.consultation.application.ports.pdf_generator_port import (
    DocumentoItemPDFDTO,
    DocumentoPDFPayload,
    PDFGeneratorPort,
)
from src.modules.consultation.domain.models.documento_clinico import (
    TipoDocumentoClinico,
)

# Ensure OutputIntents is recognized by ReportLab Catalog serialization
if "OutputIntents" not in pdfdoc.PDFCatalog.__NoDefault__:
    pdfdoc.PDFCatalog.__NoDefault__.append("OutputIntents")

_fonts_registered: bool = False


def _register_pdfa_fonts() -> None:
    """Register embedded TrueType fonts required for PDF/A compliance."""
    global _fonts_registered
    if _fonts_registered:
        return

    # ReportLab ships with Vera TrueType fonts in its internal font directory
    pdfmetrics.registerFont(TTFont("Vera", "Vera.ttf"))  # pyright: ignore[reportUnknownMemberType]
    pdfmetrics.registerFont(TTFont("VeraBd", "VeraBd.ttf"))  # pyright: ignore[reportUnknownMemberType]
    pdfmetrics.registerFont(TTFont("VeraIt", "VeraIt.ttf"))  # pyright: ignore[reportUnknownMemberType]
    pdfmetrics.registerFont(TTFont("VeraBI", "VeraBI.ttf"))  # pyright: ignore[reportUnknownMemberType]

    pdfmetrics.registerFontFamily(  # pyright: ignore[reportUnknownMemberType]
        "Vera",
        normal="Vera",
        bold="VeraBd",
        italic="VeraIt",
        boldItalic="VeraBI",
    )
    _fonts_registered = True


class PDFACanvas(canvas.Canvas):
    """Two-pass Canvas enforcing PDF/A-1b metadata, fonts and page numbering."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)  # pyright: ignore[reportUnknownMemberType]
        self._saved_page_states: list[dict[str, Any]] = []

        # Configure XMP metadata packet for PDF/A-1b
        xmp_content = (
            '<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
            '<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
            '  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
            '    <rdf:Description rdf:about=""\n'
            '        xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
            '      <dc:title><rdf:Alt><rdf:li xml:lang="x-default">'
            "Documento Clinico MediSync</rdf:li></rdf:Alt></dc:title>\n"
            "      <dc:creator><rdf:Seq><rdf:li>"
            "MediSync Express</rdf:li></rdf:Seq></dc:creator>\n"
            "    </rdf:Description>\n"
            '    <rdf:Description rdf:about=""\n'
            '        xmlns:xmp="http://ns.adobe.com/xap/1.0/">\n'
            "      <xmp:CreatorTool>MediSync PDF/A</xmp:CreatorTool>\n"
            "    </rdf:Description>\n"
            '    <rdf:Description rdf:about=""\n'
            '        xmlns:pdf="http://ns.adobe.com/pdf/1.3/">\n'
            "      <pdf:Producer>ReportLab PDF/A Library</pdf:Producer>\n"
            "    </rdf:Description>\n"
            '    <rdf:Description rdf:about=""\n'
            '        xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/">\n'
            "      <pdfaid:part>1</pdfaid:part>\n"
            "      <pdfaid:conformance>B</pdfaid:conformance>\n"
            "    </rdf:Description>\n"
            "  </rdf:RDF>\n"
            "</x:xmpmeta>\n"
            '<?xpacket end="w"?>'
        )

        def _build_xmp(_doc_obj: Any) -> str:
            return xmp_content

        doc_ref: Any = getattr(self, "_doc", None)
        if doc_ref is not None:
            doc_ref.Catalog.Metadata = pdfdoc.XMP(creator=_build_xmp)

            # Configure PDF/A OutputIntent (sRGB profile)
            output_intent = pdfdoc.PDFDictionary(
                {
                    "Type": pdfdoc.PDFName("OutputIntent"),  # pyright: ignore[reportUnknownMemberType]
                    "S": pdfdoc.PDFName("GTS_PDFA1"),  # pyright: ignore[reportUnknownMemberType]
                    "OutputConditionIdentifier": pdfdoc.PDFString("sRGB IEC61966-2.1"),
                    "Info": pdfdoc.PDFString("sRGB IEC61966-2.1"),
                }
            )
            doc_ref.Catalog.OutputIntents = pdfdoc.PDFArray([output_intent])

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        start_page_fn: Any = getattr(self, "_startPage", None)
        if callable(start_page_fn):
            start_page_fn()

    def save(self) -> None:
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def _draw_page_decorations(self, total_pages: int) -> None:
        """Draw running footer on each page."""
        self.saveState()
        self.setFont("Vera", 7)
        self.setFillColor(colors.HexColor("#64748b"))

        # Footer divider
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(36, 32, 559, 32)

        # Footer text
        page_num: Any = getattr(self, "_pageNumber", 1)
        footer_text = (
            "MediSync Express • Telemedicina CFM nº 2.314/2022 • MP nº 2.200-2/2001 "
            f"• Página {page_num} de {total_pages}"
        )
        self.drawCentredString(297.5, 20, footer_text)
        self.restoreState()


class ReportLabPDFGenerator(PDFGeneratorPort):
    """Clinical document generator producing PDF/A-1b with ITI QR Code."""

    def __init__(
        self,
        validation_url_prefix: str | None = None,
        page_compression: int = 0,
    ) -> None:
        _register_pdfa_fonts()
        settings = get_settings()
        self._validation_url_prefix = (
            validation_url_prefix or settings.DOCUMENTS_VALIDATION_URL_PREFIX
        ).rstrip("/")
        self._page_compression = page_compression

    def gerar_pdf(self, payload: DocumentoPDFPayload) -> bytes:
        """Render clinical document into archivable PDF/A-1b binary."""
        tipo_str = (
            payload.tipo_documento.value
            if isinstance(payload.tipo_documento, TipoDocumentoClinico)
            else str(payload.tipo_documento).strip().upper()
        )

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=36,
            rightMargin=36,
            topMargin=36,
            bottomMargin=42,
            pageCompression=self._page_compression,
        )

        styles = self._build_styles()
        validation_url = payload.validation_url or (
            f"{self._validation_url_prefix}/{payload.documento_id}"
        )

        story: list[Any] = []

        if tipo_str in (
            TipoDocumentoClinico.RECEITA_ANTIMICROBIANO.value,
            TipoDocumentoClinico.RECEITA_CONTROLE_ESPECIAL_C1.value,
        ):
            # Prescrições de controle especial e antimicrobianos exigem 2 vias
            story.extend(
                self._render_prescricao_via(
                    payload,
                    styles,
                    via_numero=1,
                    via_titulo="1ª VIA — RETENÇÃO DA FARMÁCIA / DROGARIA",
                    validation_url=validation_url,
                )
            )
            story.append(PageBreak())
            story.extend(
                self._render_prescricao_via(
                    payload,
                    styles,
                    via_numero=2,
                    via_titulo="2ª VIA — ORIENTAÇÃO DO PACIENTE",
                    validation_url=validation_url,
                )
            )
        elif tipo_str == TipoDocumentoClinico.RECEITA_SIMPLES.value:
            story.extend(self._render_receita_simples(payload, styles, validation_url))
        elif tipo_str == TipoDocumentoClinico.ATESTADO_MEDICO.value:
            story.extend(self._render_atestado_medico(payload, styles, validation_url))
        elif tipo_str == TipoDocumentoClinico.RELATORIO_ENCAMINHAMENTO.value:
            story.extend(
                self._render_relatorio_encaminhamento(payload, styles, validation_url)
            )
        else:
            # Fallback genérico para documentos clínicos
            story.extend(self._render_receita_simples(payload, styles, validation_url))

        doc.build(story, canvasmaker=PDFACanvas)  # pyright: ignore[reportUnknownMemberType]
        return buffer.getvalue()

    def _build_styles(self) -> dict[str, ParagraphStyle]:
        """Construct typography palette using embedded Vera fonts."""
        sample = getSampleStyleSheet()
        normal = sample["Normal"]

        return {
            "OrgTitle": ParagraphStyle(
                "OrgTitle",
                parent=normal,
                fontName="VeraBd",
                fontSize=12,
                leading=15,
                textColor=colors.HexColor("#0f172a"),
            ),
            "OrgSubtitle": ParagraphStyle(
                "OrgSubtitle",
                parent=normal,
                fontName="Vera",
                fontSize=7.5,
                leading=10,
                textColor=colors.HexColor("#475569"),
            ),
            "LegalBadge": ParagraphStyle(
                "LegalBadge",
                parent=normal,
                fontName="VeraBd",
                fontSize=7.5,
                leading=9.5,
                alignment=2,  # Right aligned
                textColor=colors.HexColor("#0284c7"),
            ),
            "DocTitle": ParagraphStyle(
                "DocTitle",
                parent=normal,
                fontName="VeraBd",
                fontSize=13,
                leading=16,
                alignment=1,  # Centered
                textColor=colors.HexColor("#0f172a"),
            ),
            "DocSubtitle": ParagraphStyle(
                "DocSubtitle",
                parent=normal,
                fontName="VeraBd",
                fontSize=8.5,
                leading=11,
                alignment=1,  # Centered
                textColor=colors.HexColor("#b91c1c"),
            ),
            "ViaBadge": ParagraphStyle(
                "ViaBadge",
                parent=normal,
                fontName="VeraBd",
                fontSize=9,
                leading=12,
                alignment=1,  # Centered
                textColor=colors.HexColor("#047857"),
            ),
            "SectionHeader": ParagraphStyle(
                "SectionHeader",
                parent=normal,
                fontName="VeraBd",
                fontSize=8.5,
                leading=11,
                textColor=colors.HexColor("#1e293b"),
            ),
            "Body": ParagraphStyle(
                "Body",
                parent=normal,
                fontName="Vera",
                fontSize=8.5,
                leading=11.5,
                textColor=colors.HexColor("#334155"),
            ),
            "BodyBold": ParagraphStyle(
                "BodyBold",
                parent=normal,
                fontName="VeraBd",
                fontSize=8.5,
                leading=11.5,
                textColor=colors.HexColor("#1e293b"),
            ),
            "ItemTitle": ParagraphStyle(
                "ItemTitle",
                parent=normal,
                fontName="VeraBd",
                fontSize=9,
                leading=12,
                textColor=colors.HexColor("#0f172a"),
            ),
            "ItemDetail": ParagraphStyle(
                "ItemDetail",
                parent=normal,
                fontName="Vera",
                fontSize=8,
                leading=10.5,
                textColor=colors.HexColor("#334155"),
            ),
            "LegalText": ParagraphStyle(
                "LegalText",
                parent=normal,
                fontName="Vera",
                fontSize=6.5,
                leading=8.5,
                textColor=colors.HexColor("#64748b"),
            ),
            "VerificationTitle": ParagraphStyle(
                "VerificationTitle",
                parent=normal,
                fontName="VeraBd",
                fontSize=7.5,
                leading=9.5,
                textColor=colors.HexColor("#0f172a"),
            ),
            "VerificationUrl": ParagraphStyle(
                "VerificationUrl",
                parent=normal,
                fontName="VeraBd",
                fontSize=7,
                leading=9,
                textColor=colors.HexColor("#0369a1"),
            ),
        }

    def _render_header(
        self, payload: DocumentoPDFPayload, styles: dict[str, ParagraphStyle]
    ) -> list[Any]:
        """Render clinic header, identification and teleconsultation legal frame."""
        org_details: list[str] = []
        if payload.organizacao_cnpj:
            org_details.append(f"CNPJ: {payload.organizacao_cnpj}")
        if payload.organizacao_cnes:
            org_details.append(f"CNES: {payload.organizacao_cnes}")
        if payload.organizacao_endereco:
            org_details.append(payload.organizacao_endereco)
        if payload.organizacao_telefone:
            org_details.append(f"Tel: {payload.organizacao_telefone}")

        org_subtitle_str = (
            " • ".join(org_details)
            if org_details
            else "Unidade de Teleatendimento 24/7"
        )

        left_cell = [
            Paragraph(payload.organizacao_nome, styles["OrgTitle"]),
            Spacer(1, 2),
            Paragraph(org_subtitle_str, styles["OrgSubtitle"]),
        ]

        right_cell = [
            Paragraph("TELEMEDICINA — CFM Nº 2.314/2022", styles["LegalBadge"]),
            Spacer(1, 2),
            Paragraph("ASSINATURA DIGITAL ICP-BRASIL", styles["LegalBadge"]),
        ]

        header_table = Table([[left_cell, right_cell]], colWidths=[360, 163])
        header_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )

        return [
            header_table,
            Spacer(1, 6),
            HRFlowable(
                width="100%",
                thickness=1.5,
                color=colors.HexColor("#0284c7"),
                spaceAfter=8,
            ),
        ]

    def _render_parties_box(
        self, payload: DocumentoPDFPayload, styles: dict[str, ParagraphStyle]
    ) -> list[Any]:
        """Render patient and prescribing doctor identification banner."""
        medico_rqe_str = f" • RQE: {payload.medico_rqe}" if payload.medico_rqe else ""
        pac_nasc_str = (
            f" • Nasc: {payload.paciente_data_nascimento}"
            if payload.paciente_data_nascimento
            else ""
        )

        data_formatada = payload.data_emissao.strftime("%d/%m/%Y às %H:%M:%S UTC")

        data_matrix = [
            [
                Paragraph("PACIENTE:", styles["SectionHeader"]),
                Paragraph(
                    f"<b>{payload.paciente_nome}</b> (CPF: {payload.paciente_cpf}"
                    f"{pac_nasc_str})",
                    styles["Body"],
                ),
            ],
            [
                Paragraph("MÉDICO(A):", styles["SectionHeader"]),
                Paragraph(
                    f"<b>{payload.medico_nome}</b> — CRM/{payload.medico_crm_uf}: "
                    f"<b>{payload.medico_crm}</b>{medico_rqe_str}",
                    styles["Body"],
                ),
            ],
            [
                Paragraph("EMISSÃO:", styles["SectionHeader"]),
                Paragraph(data_formatada, styles["Body"]),
            ],
        ]

        if payload.paciente_endereco:
            data_matrix.append(
                [
                    Paragraph("ENDEREÇO:", styles["SectionHeader"]),
                    Paragraph(payload.paciente_endereco, styles["Body"]),
                ]
            )

        box_table = Table(data_matrix, colWidths=[80, 443])
        box_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#f1f5f9")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )

        return [box_table, Spacer(1, 10)]

    def _render_receita_simples(
        self,
        payload: DocumentoPDFPayload,
        styles: dict[str, ParagraphStyle],
        validation_url: str,
    ) -> list[Any]:
        """Render single via regular prescription."""
        elements: list[Any] = []
        elements.extend(self._render_header(payload, styles))
        elements.append(Paragraph("RECEITA MÉDICA", styles["DocTitle"]))
        elements.append(Spacer(1, 8))
        elements.extend(self._render_parties_box(payload, styles))

        elements.extend(self._render_itens_table(payload.itens, styles))

        if payload.texto_livre:
            elements.append(Spacer(1, 8))
            elements.append(
                Paragraph("<b>Orientações Gerais:</b>", styles["SectionHeader"])
            )
            elements.append(Spacer(1, 3))
            elements.append(Paragraph(payload.texto_livre, styles["Body"]))

        elements.append(Spacer(1, 14))
        elements.extend(self._render_verification_box(payload, styles, validation_url))
        return elements

    def _render_prescricao_via(
        self,
        payload: DocumentoPDFPayload,
        styles: dict[str, ParagraphStyle],
        via_numero: int,
        via_titulo: str,
        validation_url: str,
    ) -> list[Any]:
        """Render special control or antimicrobial prescription via."""
        elements: list[Any] = []
        elements.extend(self._render_header(payload, styles))

        tipo_str = (
            payload.tipo_documento.value
            if isinstance(payload.tipo_documento, TipoDocumentoClinico)
            else str(payload.tipo_documento).strip().upper()
        )

        if tipo_str == TipoDocumentoClinico.RECEITA_ANTIMICROBIANO.value:
            elements.append(
                Paragraph("RECEITUÁRIO DE ANTIMICROBIANOS", styles["DocTitle"])
            )
            elements.append(
                Paragraph(
                    "RDC ANVISA Nº 20/2011 — VALIDADE: 10 (DEZ) DIAS",
                    styles["DocSubtitle"],
                )
            )
        else:
            elements.append(
                Paragraph("RECEITUÁRIO DE CONTROLE ESPECIAL", styles["DocTitle"])
            )
            elements.append(
                Paragraph(
                    "PORTARIA SVS/MS Nº 344/98 (LISTA C1) — VALIDADE: 30 DIAS",
                    styles["DocSubtitle"],
                )
            )

        elements.append(Spacer(1, 4))
        elements.append(Paragraph(via_titulo, styles["ViaBadge"]))
        elements.append(Spacer(1, 8))
        elements.extend(self._render_parties_box(payload, styles))

        elements.extend(self._render_itens_table(payload.itens, styles))

        if payload.texto_livre:
            elements.append(Spacer(1, 6))
            elements.append(
                Paragraph("<b>Orientações e Posologia:</b>", styles["SectionHeader"])
            )
            elements.append(Spacer(1, 2))
            elements.append(Paragraph(payload.texto_livre, styles["Body"]))

        # 1ª Via requires mandatory sanitary buyer and dispenser identification boxes
        if via_numero == 1:
            elements.append(Spacer(1, 8))
            elements.extend(self._render_sanitary_retention_boxes(styles))

        elements.append(Spacer(1, 10))
        elements.extend(self._render_verification_box(payload, styles, validation_url))
        return elements

    def _render_atestado_medico(
        self,
        payload: DocumentoPDFPayload,
        styles: dict[str, ParagraphStyle],
        validation_url: str,
    ) -> list[Any]:
        """Render medical leave certificate complying with CFM 1.658/2002."""
        elements: list[Any] = []
        elements.extend(self._render_header(payload, styles))
        elements.append(Paragraph("ATESTADO MÉDICO", styles["DocTitle"]))
        elements.append(Spacer(1, 10))
        elements.extend(self._render_parties_box(payload, styles))

        dias = payload.dias_afastamento or 1
        dias_extenso = "um" if dias == 1 else str(dias)
        plural = "dia" if dias == 1 else "dias"
        data_inicio = payload.data_emissao.strftime("%d/%m/%Y")

        cert_text = (
            "Atesto para os devidos fins, a pedido do(a) paciente interessado(a), "
            f"que <b>{payload.paciente_nome}</b>, inscrito(a) no CPF sob o nº "
            f"<b>{payload.paciente_cpf}</b>, foi submetido(a) a teleconsulta médica "
            f"e necessita de <b>{dias} ({dias_extenso}) {plural}</b> de repouso e "
            f"afastamento de suas atividades habituais, a contar de {data_inicio}."
        )

        elements.append(
            Table(
                [[Paragraph(cert_text, styles["Body"])]],
                colWidths=[523],
                style=[
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ],
            )
        )

        elements.append(Spacer(1, 10))

        if payload.cid10 and payload.cid10_autorizado_paciente:
            cid_text = (
                f"<b>Diagnóstico / CID-10:</b> {payload.cid10} "
                "<i>(Divulgação expressamente autorizada pelo(a) paciente, "
                "conforme Art. 5º da Resolução CFM nº 1.658/2002 e CFM 2.314/2022).</i>"
            )
        else:
            cid_text = (
                "<b>Diagnóstico:</b> Omitido nos termos do Art. 5º da Resolução "
                "CFM nº 1.658/2002 (preservação do sigilo médico)."
            )

        elements.append(Paragraph(cid_text, styles["Body"]))

        if payload.texto_livre:
            elements.append(Spacer(1, 8))
            elements.append(Paragraph("<b>Observações:</b>", styles["SectionHeader"]))
            elements.append(Spacer(1, 2))
            elements.append(Paragraph(payload.texto_livre, styles["Body"]))

        elements.append(Spacer(1, 16))
        elements.extend(self._render_verification_box(payload, styles, validation_url))
        return elements

    def _render_relatorio_encaminhamento(
        self,
        payload: DocumentoPDFPayload,
        styles: dict[str, ParagraphStyle],
        validation_url: str,
    ) -> list[Any]:
        """Render clinical referral report for specialists or diagnostic exams."""
        elements: list[Any] = []
        elements.extend(self._render_header(payload, styles))
        elements.append(
            Paragraph("RELATÓRIO DE ENCAMINHAMENTO CLÍNICO", styles["DocTitle"])
        )
        elements.append(Spacer(1, 10))
        elements.extend(self._render_parties_box(payload, styles))

        especialidade = payload.especialidade_encaminhamento or "Especialidade Médica"
        elements.append(
            Paragraph(
                f"<b>Encaminhamento Solicitado:</b> Especialidade em {especialidade}",
                styles["SectionHeader"],
            )
        )
        elements.append(Spacer(1, 6))

        if payload.motivo_encaminhamento:
            elements.append(
                Paragraph("<b>Motivo do Encaminhamento:</b>", styles["SectionHeader"])
            )
            elements.append(Spacer(1, 2))
            elements.append(Paragraph(payload.motivo_encaminhamento, styles["Body"]))
            elements.append(Spacer(1, 6))

        if payload.cid10:
            elements.append(
                Paragraph(
                    f"<b>Hipótese Diagnóstica (CID-10):</b> {payload.cid10}",
                    styles["BodyBold"],
                )
            )
            elements.append(Spacer(1, 6))

        if payload.texto_livre:
            elements.append(
                Paragraph(
                    "<b>Resumo Clínico e Conduta Prévia:</b>", styles["SectionHeader"]
                )
            )
            elements.append(Spacer(1, 2))
            elements.append(Paragraph(payload.texto_livre, styles["Body"]))

        elements.append(Spacer(1, 16))
        elements.extend(self._render_verification_box(payload, styles, validation_url))
        return elements

    def _render_itens_table(
        self, itens: list[DocumentoItemPDFDTO], styles: dict[str, ParagraphStyle]
    ) -> list[Any]:
        """Render prescription items table with dosage and posology."""
        if not itens:
            return [
                Paragraph(
                    "<i>Nenhum medicamento prescrito para este documento.</i>",
                    styles["Body"],
                )
            ]

        rows: list[list[Any]] = [
            [
                Paragraph("#", styles["SectionHeader"]),
                Paragraph("Medicamento / Concentração", styles["SectionHeader"]),
                Paragraph("Posologia / Instruções de Uso", styles["SectionHeader"]),
                Paragraph("Duração", styles["SectionHeader"]),
            ]
        ]

        for idx, item in enumerate(itens, start=1):
            duracao_str = item.duracao or "Conforme prescrição"
            controle_badge = " [C1]" if item.controle_especial else ""
            rows.append(
                [
                    Paragraph(f"<b>{idx}</b>", styles["Body"]),
                    Paragraph(
                        f"<b>{item.medicamento}</b> {item.dosagem}{controle_badge}",
                        styles["ItemTitle"],
                    ),
                    Paragraph(item.posologia, styles["ItemDetail"]),
                    Paragraph(duracao_str, styles["Body"]),
                ]
            )

        items_table = Table(rows, colWidths=[24, 180, 240, 79])
        items_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )

        return [items_table]

    def _render_sanitary_retention_boxes(
        self, styles: dict[str, ParagraphStyle]
    ) -> list[Any]:
        """Render buyer/dispenser boxes mandated by Portaria 344/98 & RDC 20/2011."""
        comprador_content = [
            Paragraph("<b>IDENTIFICAÇÃO DO COMPRADOR</b>", styles["SectionHeader"]),
            Spacer(1, 2),
            Paragraph(
                "Nome Completo: ____________________________________________",
                styles["LegalText"],
            ),
            Paragraph(
                "Doc. Identidade (RG): ________________ Órgão Emissor: _______",
                styles["LegalText"],
            ),
            Paragraph(
                "Endereço: __________________________________ Tel: __________",
                styles["LegalText"],
            ),
            Paragraph(
                "Cidade/UF: ________________________________________________",
                styles["LegalText"],
            ),
        ]

        dispensador_content = [
            Paragraph("<b>IDENTIFICAÇÃO DO DISPENSADOR</b>", styles["SectionHeader"]),
            Spacer(1, 2),
            Paragraph(
                "Nome Farmacêutico: _______________________________________",
                styles["LegalText"],
            ),
            Paragraph(
                "CRF/UF: ________________ Assinatura: _______________________",
                styles["LegalText"],
            ),
            Paragraph(
                "Data da Dispensação: ___/___/______ Carimbo da Farmácia: ____",
                styles["LegalText"],
            ),
            Paragraph(
                "Quantidade Dispensada: ________________ Lote: ______________",
                styles["LegalText"],
            ),
        ]

        sanitary_table = Table(
            [[comprador_content, dispensador_content]], colWidths=[256, 267]
        )
        sanitary_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fafafa")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )

        return [KeepTogether([sanitary_table])]

    def _render_verification_box(
        self,
        payload: DocumentoPDFPayload,
        styles: dict[str, ParagraphStyle],
        validation_url: str,
    ) -> list[Any]:
        """Render ITI verification QR Code and legal validity banner."""
        qr_image = self._generate_qr_flowable(validation_url)

        hash_display = (
            payload.sha256_hash
            if payload.sha256_hash
            else f"doc_{payload.documento_id.hex}"
        )

        info_lines = [
            Paragraph(
                "VERIFICAÇÃO DE AUTENTICIDADE DIGITAL (ITI / CFM Nº 2.314/2022)",
                styles["VerificationTitle"],
            ),
            Spacer(1, 1),
            Paragraph(
                "Aponte a câmera do celular para o QR Code ao lado ou acesse o "
                "portal público:",
                styles["LegalText"],
            ),
            Paragraph(validation_url, styles["VerificationUrl"]),
            Spacer(1, 1),
            Paragraph(
                f"Código do Documento: <b>{payload.documento_id}</b>",
                styles["LegalText"],
            ),
            Paragraph(
                f"Assinatura / SHA-256: <font name='Vera'>{hash_display[:28]}..."
                f"{hash_display[-8:]}</font>",
                styles["LegalText"],
            ),
            Paragraph(
                "Documento assinado digitalmente no padrão ICP-Brasil (PAdES) com "
                "validade jurídica em todo o território nacional "
                "(MP nº 2.200-2/2001 e Lei Federal nº 14.063/2020).",
                styles["LegalText"],
            ),
        ]

        verification_table = Table([[qr_image, info_lines]], colWidths=[66, 457])
        verification_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0fdf4")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#86efac")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )

        return [KeepTogether([verification_table])]

    def _generate_qr_flowable(self, data_url: str) -> Image:
        """Create an in-memory QR code flowable Image from target URL."""
        qr = qrcode.QRCode(
            version=1,
            box_size=3,
            border=1,
            error_correction=ERROR_CORRECT_M,
        )
        qr.add_data(data_url)
        qr.make(fit=True)

        img: Any = qr.make_image(fill_color="black", back_color="white")
        qr_io = io.BytesIO()
        img.save(qr_io, "PNG")
        qr_io.seek(0)

        return Image(qr_io, width=54, height=54)


class FakePDFGenerator(PDFGeneratorPort):
    """In-memory stub returning deterministic PDF bytes for lightweight testing."""

    def __init__(
        self, validation_url_prefix: str = "https://medisync.app/validar"
    ) -> None:
        self._validation_url_prefix = validation_url_prefix.rstrip("/")
        self.last_payload: DocumentoPDFPayload | None = None

    def gerar_pdf(self, payload: DocumentoPDFPayload) -> bytes:
        """Return synthetic valid PDF/A bytes embedding payload metadata."""
        self.last_payload = payload
        validation_url = payload.validation_url or (
            f"{self._validation_url_prefix}/{payload.documento_id}"
        )

        # Synthetic minimal valid PDF with XMP pdfaid:part=1 and GTS_PDFA1 marker
        header = b"%PDF-1.4\n"
        metadata = (
            f"% MediSync Fake PDF/A Generator\n"
            f"% doc_id: {payload.documento_id}\n"
            f"% validation_url: {validation_url}\n"
            f"% tipo: {payload.tipo_documento}\n"
            f"% pdfaid:part=1 pdfaid:conformance=B\n"
            f"% OutputIntent: GTS_PDFA1 sRGB IEC61966-2.1\n"
        ).encode()
        body = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        trailer = b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"

        return header + metadata + body + trailer
