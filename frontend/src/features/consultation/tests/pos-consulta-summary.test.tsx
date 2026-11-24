import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  handleListarDocumentosPacienteApiV1ConsultationsMeDocumentosGet,
  handleObterDocumentoPdfPacienteApiV1ConsultationsMeDocumentsDocumentoIdPdfGet,
} from "@/api/generated/msw.gen";
import type { PacienteDocumentoItemResponse } from "@/api/generated/types.gen";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/utils";
import { PosConsultaSummary } from "../components/pos-consulta-summary";

const MOCK_ATENDIMENTO_ID = "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2d";
const MOCK_DOC_C1_ID = "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2f";
const MOCK_DOC_ANTI_ID = "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b30";

const mockDocumentosPaciente: PacienteDocumentoItemResponse[] = [
  {
    documento_id: MOCK_DOC_C1_ID,
    atendimento_id: MOCK_ATENDIMENTO_ID,
    tipo_documento: "RECEITA_CONTROLE_ESPECIAL_C1",
    status_assinatura: "ASSINADO",
    token_validacao: "ITI-MEDISYNC-998877",
    criado_em: "2026-11-02T12:25:00Z",
    assinado_em: "2026-11-02T12:30:00Z",
  },
  {
    documento_id: MOCK_DOC_ANTI_ID,
    atendimento_id: MOCK_ATENDIMENTO_ID,
    tipo_documento: "RECEITA_ANTIMICROBIANO",
    status_assinatura: "ASSINADO",
    token_validacao: "ITI-MEDISYNC-445566",
    criado_em: "2026-11-02T12:26:00Z",
    assinado_em: "2026-11-02T12:31:00Z",
  },
];

describe("PosConsultaSummary Integration Tests (/me/documentos, C1/Antimicrobiano, ICP-Brasil)", () => {
  const prontuarioProibidoSpy = vi.fn();
  const mePdfDownloadSpy = vi.fn();

  beforeEach(() => {
    prontuarioProibidoSpy.mockClear();
    mePdfDownloadSpy.mockClear();

    server.use(
      http.get(`*/api/v1/consultations/${MOCK_ATENDIMENTO_ID}/prontuario`, () => {
        prontuarioProibidoSpy();
        return HttpResponse.json({ detail: "Forbidden" }, { status: 403 });
      }),
      handleListarDocumentosPacienteApiV1ConsultationsMeDocumentosGet(() => {
        return HttpResponse.json(mockDocumentosPaciente);
      }),
      handleObterDocumentoPdfPacienteApiV1ConsultationsMeDocumentsDocumentoIdPdfGet(
        ({ params }) => {
          mePdfDownloadSpy(params.documento_id);
          return new HttpResponse(
            new Blob(["%PDF-1.4 mock content"], { type: "application/pdf" }) as never,
            {
              headers: {
                "Content-Type": "application/pdf",
                "Content-Disposition": `attachment; filename="documento-${String(params.documento_id).substring(0, 8)}.pdf"`,
              },
            },
          );
        },
      ),
    );
  });

  it("IT-POST-01: Exibe banner sem dados médicos hardcoded quando omitidos e aceita props explícitas", async () => {
    const { rerender } = renderWithProviders(
      <PosConsultaSummary atendimentoId={MOCK_ATENDIMENTO_ID} />,
    );

    expect(screen.getByRole("heading", { name: /consulta médica concluída/i })).toBeInTheDocument();
    expect(screen.queryByText(/dr\. eduardo rocha/i)).not.toBeInTheDocument();
    expect(screen.getByText("Médico Plantonista")).toBeInTheDocument();

    rerender(
      <PosConsultaSummary
        atendimentoId={MOCK_ATENDIMENTO_ID}
        pacienteNome="Maria de Souza"
        medicoNome="Dra. Clara Mendes"
        crmUf="99887/RJ"
      />,
    );
    expect(screen.getByText("Maria de Souza")).toBeInTheDocument();
    expect(screen.getByText(/dra\. clara mendes/i)).toBeInTheDocument();
    expect(screen.getByText(/\(crm 99887\/rj\)/i)).toBeInTheDocument();
  });

  it("IT-POST-02: Consome /me/documentos sem chamar /prontuario e exibe rótulos C1 e Antimicrobiano", async () => {
    renderWithProviders(<PosConsultaSummary atendimentoId={MOCK_ATENDIMENTO_ID} />);

    expect(
      await screen.findByText(/receita de controle especial \(portaria 344\/98\)/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/receita de antimicrobiano/i)).toBeInTheDocument();
    expect(screen.getByText("ITI-MEDISYNC-998877")).toBeInTheDocument();
    expect(screen.getByText("ITI-MEDISYNC-445566")).toBeInTheDocument();
    expect(prontuarioProibidoSpy).not.toHaveBeenCalled();
  });

  it("IT-POST-03: Exibe aviso amigável quando /me/documentos não possui itens do atendimento", async () => {
    server.use(
      handleListarDocumentosPacienteApiV1ConsultationsMeDocumentosGet(() => HttpResponse.json([])),
    );

    renderWithProviders(<PosConsultaSummary atendimentoId={MOCK_ATENDIMENTO_ID} />);

    await waitFor(() => {
      expect(
        screen.getByText(/nenhum documento adicional \(receita ou atestado\) foi emitido/i),
      ).toBeInTheDocument();
    });
  });

  it("IT-POST-04: Baixar PDF usa /api/v1/consultations/me/documents/{documento_id}/pdf", async () => {
    const createObjectURLMock = vi.fn().mockReturnValue("blob:http://localhost/mock-pdf-url");
    window.URL.createObjectURL = createObjectURLMock;
    window.URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    renderWithProviders(<PosConsultaSummary atendimentoId={MOCK_ATENDIMENTO_ID} />);

    const downloadButtons = await screen.findAllByRole("button", { name: /baixar pdf/i });
    expect(downloadButtons.length).toBeGreaterThan(0);

    const user = userEvent.setup();
    await user.click(downloadButtons[0]);

    await waitFor(() => {
      expect(mePdfDownloadSpy).toHaveBeenCalledWith(MOCK_DOC_C1_ID);
      expect(createObjectURLMock).toHaveBeenCalled();
    });
  });

  it("IT-POST-05: Botão 'Concluir e Voltar ao Início' chama callback onNovaConsulta", async () => {
    const handleNovaConsulta = vi.fn();
    renderWithProviders(
      <PosConsultaSummary
        atendimentoId={MOCK_ATENDIMENTO_ID}
        onNovaConsulta={handleNovaConsulta}
      />,
    );

    const btnVoltar = screen.getByRole("button", { name: /concluir e voltar ao início/i });
    const user = userEvent.setup();
    await user.click(btnVoltar);

    expect(handleNovaConsulta).toHaveBeenCalledTimes(1);
  });

  it("IT-POST-06: Exibe alerta de erro explícito quando /me/documentos falha sem mostrar estado vazio enganoso", async () => {
    server.use(
      handleListarDocumentosPacienteApiV1ConsultationsMeDocumentosGet(() =>
        HttpResponse.json({ detail: "Falha ao consultar documentos assinados." }, { status: 500 }),
      ),
    );

    renderWithProviders(<PosConsultaSummary atendimentoId={MOCK_ATENDIMENTO_ID} />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/falha ao consultar documentos assinados/i);
    expect(
      screen.queryByText(/nenhum documento adicional \(receita ou atestado\) foi emitido/i),
    ).not.toBeInTheDocument();
  });

  it("IT-POST-07: Exibe alerta de erro quando o download de PDF em /me/documents/{id}/pdf falha", async () => {
    server.use(
      handleObterDocumentoPdfPacienteApiV1ConsultationsMeDocumentsDocumentoIdPdfGet(() =>
        HttpResponse.json({ detail: "Assinatura PDF indisponível no momento." }, { status: 500 }),
      ),
    );

    renderWithProviders(<PosConsultaSummary atendimentoId={MOCK_ATENDIMENTO_ID} />);

    const downloadButtons = await screen.findAllByRole("button", { name: /baixar pdf/i });
    const user = userEvent.setup();
    await user.click(downloadButtons[0]);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/assinatura pdf indisponível no momento/i);
  });
});
