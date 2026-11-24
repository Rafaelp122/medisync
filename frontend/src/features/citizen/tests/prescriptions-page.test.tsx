import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  handleListarDocumentosPacienteApiV1ConsultationsMeDocumentosGet,
  handleObterDocumentoPdfPacienteApiV1ConsultationsMeDocumentsDocumentoIdPdfGet,
} from "@/api/generated/msw.gen";
import { PrescriptionsPage } from "@/features/citizen/pages/prescriptions-page";
import {
  MOCK_CITIZEN_SESSION,
  renderCitizenRoute,
} from "@/features/citizen/tests/test-router-helper";
import { server } from "@/mocks/server";

const MOCK_DOC_ID = "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b51";
const MOCK_ATEND_ID = "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b50";
const originalClipboardDescriptor =
  typeof navigator !== "undefined"
    ? Object.getOwnPropertyDescriptor(navigator, "clipboard")
    : undefined;

describe("PrescriptionsPage (/receitas)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    if (typeof navigator !== "undefined") {
      if (originalClipboardDescriptor) {
        Object.defineProperty(navigator, "clipboard", originalClipboardDescriptor);
      } else {
        Reflect.deleteProperty(navigator, "clipboard");
      }
    }
  });

  beforeEach(() => {
    server.use(
      handleListarDocumentosPacienteApiV1ConsultationsMeDocumentosGet({
        body: [
          {
            documento_id: MOCK_DOC_ID,
            atendimento_id: MOCK_ATEND_ID,
            tipo_documento: "RECEITA_SIMPLES",
            status_assinatura: "ASSINADO",
            token_validacao: "ITI-TOK-2026-XYZ",
            criado_em: "2026-11-12T10:00:00Z",
            assinado_em: "2026-11-12T10:05:00Z",
          },
          {
            documento_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b52",
            atendimento_id: MOCK_ATEND_ID,
            tipo_documento: "RECEITA_CONTROLE_ESPECIAL_C1",
            status_assinatura: "EMITIDO",
            token_validacao: "ITI-TOK-2026-PEND",
            criado_em: "2026-11-12T11:00:00Z",
            assinado_em: null,
          },
        ],
      }),
      handleObterDocumentoPdfPacienteApiV1ConsultationsMeDocumentsDocumentoIdPdfGet(() => {
        return new HttpResponse(new Blob(["%PDF-1.4 fake"], { type: "application/pdf" }), {
          status: 200,
          headers: { "Content-Type": "application/pdf" },
        });
      }),
    );
  });

  it("lista documentos com selo ICP-Brasil e permite baixar PDF via Blob", async () => {
    const createObjectURLMock = vi
      .spyOn(window.URL, "createObjectURL")
      .mockReturnValue("blob:http://localhost/doc-1");
    const revokeObjectURLMock = vi
      .spyOn(window.URL, "revokeObjectURL")
      .mockImplementation(() => {});
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    renderCitizenRoute(<PrescriptionsPage session={MOCK_CITIZEN_SESSION} />, "/receitas");
    const user = userEvent.setup();

    expect(await screen.findByText(/receita médica simples/i)).toBeInTheDocument();
    expect(screen.getByText(/assinado icp-brasil/i)).toBeInTheDocument();
    expect(screen.getByText("ITI-TOK-2026-XYZ")).toBeInTheDocument();
    expect(
      screen.getByText(/receita de controle especial \(portaria 344\/98\)/i),
    ).toBeInTheDocument();
    const awaitingBadge = screen.getByText("Aguardando Assinatura");
    expect(awaitingBadge).toBeInTheDocument();
    expect(awaitingBadge).toHaveClass("bg-warning");
    expect(screen.queryByText("EMITIDO")).not.toBeInTheDocument();

    const downloadButtons = screen.getAllByRole("button", { name: /baixar pdf/i });
    await user.click(downloadButtons[0]);

    await waitFor(() => {
      expect(createObjectURLMock).toHaveBeenCalledTimes(1);
      expect(revokeObjectURLMock).toHaveBeenCalledWith("blob:http://localhost/doc-1");
    });
  });

  it("botão 'Copiar / Validar Código' copia token e navega para /validar/$token", async () => {
    const { history } = renderCitizenRoute(
      <PrescriptionsPage session={MOCK_CITIZEN_SESSION} />,
      "/receitas",
    );
    const user = userEvent.setup();
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: writeTextMock },
      configurable: true,
    });

    await screen.findByText("ITI-TOK-2026-XYZ");

    const validateButtons = screen.getAllByRole("button", { name: /copiar \/ validar código/i });
    await user.click(validateButtons[0]);

    await waitFor(() => {
      expect(writeTextMock).toHaveBeenCalledWith("ITI-TOK-2026-XYZ");
      expect(history.location.pathname).toBe("/validar/ITI-TOK-2026-XYZ");
    });
  });
});
