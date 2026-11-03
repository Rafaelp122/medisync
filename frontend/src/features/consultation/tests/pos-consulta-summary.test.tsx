import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { DocumentoClinicoResponse, ProntuarioResponse } from "@/api/generated/types.gen";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/utils";
import { PosConsultaSummary } from "../components/pos-consulta-summary";

const MOCK_ATENDIMENTO_ID = "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2d";
const MOCK_DOC_ID = "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2f";

const mockDocumentos: DocumentoClinicoResponse[] = [
  {
    id: MOCK_DOC_ID,
    atendimento_id: MOCK_ATENDIMENTO_ID,
    tipo_documento: "RECEITA_SIMPLES",
    conteudo: "Amoxicilina 500mg de 8/8h por 7 dias",
    itens: [
      {
        medicamento: "Amoxicilina 500mg",
        posologia: "1 cápsula de 8 em 8 horas por 7 dias",
        quantidade: "21 cápsulas",
      },
    ],
    assinado_em: "2026-11-02T12:30:00Z",
    token_validacao: "ITI-MEDISYNC-998877",
    criado_em: "2026-11-02T12:28:00Z",
  },
];

const mockProntuario: ProntuarioResponse = {
  id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2a",
  atendimento_id: MOCK_ATENDIMENTO_ID,
  paciente_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
  documentos: mockDocumentos,
  criado_em: "2026-11-02T12:00:00Z",
  atualizado_em: "2026-11-02T12:30:00Z",
};

describe("PosConsultaSummary Integration Tests (US-09, US-10, ICP-Brasil, ITI)", () => {
  beforeEach(() => {
    server.use(
      http.get(`*/api/v1/consultations/${MOCK_ATENDIMENTO_ID}/prontuario`, () => {
        return HttpResponse.json(mockProntuario);
      }),
      http.get(`*/api/v1/consultations/${MOCK_ATENDIMENTO_ID}/documents/${MOCK_DOC_ID}/pdf`, () => {
        return new HttpResponse(new Blob(["%PDF-1.4 mock content"], { type: "application/pdf" }), {
          headers: {
            "Content-Type": "application/pdf",
            "Content-Disposition": `attachment; filename="receita-simples-${MOCK_DOC_ID.substring(0, 8)}.pdf"`,
          },
        });
      }),
    );
  });

  it("IT-POST-01: Exibe banner de consulta concluída, paciente e médico responsável com CRM", async () => {
    renderWithProviders(
      <PosConsultaSummary
        atendimentoId={MOCK_ATENDIMENTO_ID}
        pacienteNome="Maria de Souza"
        medicoNome="Dr. Eduardo Rocha"
        crmUf="123456/SP"
        documentos={mockDocumentos}
      />,
    );

    expect(screen.getByRole("heading", { name: /consulta médica concluída/i })).toBeInTheDocument();
    expect(screen.getByText("Maria de Souza")).toBeInTheDocument();
    expect(screen.getByText(/dr\. eduardo rocha/i)).toBeInTheDocument();
    expect(screen.getByText(/\(crm 123456\/sp\)/i)).toBeInTheDocument();
  });

  it("IT-POST-02: Exibe selo de conformidade ICP-Brasil PAdES e ITI/CFM", async () => {
    renderWithProviders(
      <PosConsultaSummary atendimentoId={MOCK_ATENDIMENTO_ID} documentos={mockDocumentos} />,
    );

    expect(
      screen.getByText(/documentos com assinatura digital icp-brasil \(pades\)/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/validação iti \/ cfm/i)).toBeInTheDocument();
    expect(screen.getByText(/mp nº 2\.200-2\/2001/i)).toBeInTheDocument();
  });

  it("IT-POST-03: Renderiza lista de documentos emitidos com código de validação ITI e prescrição", async () => {
    renderWithProviders(
      <PosConsultaSummary atendimentoId={MOCK_ATENDIMENTO_ID} documentos={mockDocumentos} />,
    );

    expect(screen.getByText(/receita médica simples/i)).toBeInTheDocument();
    expect(screen.getByText(/assinado icp-brasil/i)).toBeInTheDocument();
    expect(screen.getByText("ITI-MEDISYNC-998877")).toBeInTheDocument();
    expect(screen.getByText("Amoxicilina 500mg")).toBeInTheDocument();
    expect(screen.getByText(/1 cápsula de 8 em 8 horas por 7 dias/i)).toBeInTheDocument();
  });

  it("IT-POST-04: Exibe aviso amigável quando nenhum documento adicional foi emitido", async () => {
    server.use(
      http.get(`*/api/v1/consultations/${MOCK_ATENDIMENTO_ID}/prontuario`, () => {
        return HttpResponse.json({ ...mockProntuario, documentos: [] });
      }),
    );

    renderWithProviders(<PosConsultaSummary atendimentoId={MOCK_ATENDIMENTO_ID} />);

    await waitFor(() => {
      expect(
        screen.getByText(/nenhum documento adicional \(receita ou atestado\) foi emitido/i),
      ).toBeInTheDocument();
    });
  });

  it("IT-POST-05: Clicar no botão 'Baixar PDF' dispara download do arquivo", async () => {
    // Mock URL.createObjectURL and URL.revokeObjectURL
    const createObjectURLMock = vi.fn().mockReturnValue("blob:http://localhost/mock-pdf-url");
    const revokeObjectURLMock = vi.fn();
    window.URL.createObjectURL = createObjectURLMock;
    window.URL.revokeObjectURL = revokeObjectURLMock;

    renderWithProviders(
      <PosConsultaSummary atendimentoId={MOCK_ATENDIMENTO_ID} documentos={mockDocumentos} />,
    );

    const btnDownload = screen.getByRole("button", { name: /baixar pdf/i });
    expect(btnDownload).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(btnDownload);

    await waitFor(() => {
      expect(createObjectURLMock).toHaveBeenCalled();
    });
  });

  it("IT-POST-06: Botão 'Concluir e Voltar ao Início' chama callback onNovaConsulta", async () => {
    const handleNovaConsulta = vi.fn();
    renderWithProviders(
      <PosConsultaSummary
        atendimentoId={MOCK_ATENDIMENTO_ID}
        documentos={mockDocumentos}
        onNovaConsulta={handleNovaConsulta}
      />,
    );

    const btnVoltar = screen.getByRole("button", { name: /concluir e voltar ao início/i });
    expect(btnVoltar).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(btnVoltar);

    expect(handleNovaConsulta).toHaveBeenCalledTimes(1);
  });
});
