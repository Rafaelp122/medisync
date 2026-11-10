import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import type React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import { createTestQueryClient } from "@/test/utils";
import { MedicalRecordsPane } from "../components/medical-records-pane";
import {
  createDocumentoClinicoResponse,
  createProntuarioResponse,
  MOCK_ATENDIMENTO_ID,
  MOCK_DOC_ID,
} from "./fixtures";

describe("MedicalRecordsPane Triage Fidelity (Portaria GM/MS nº 2.048/2002, US-09)", () => {
  beforeEach(() => {
    server.use(
      http.get(`*/api/v1/consultations/${MOCK_ATENDIMENTO_ID}/prontuario`, () => {
        return HttpResponse.json(createProntuarioResponse());
      }),
    );
  });

  it("IT-MRP-01: mapeia rigidamente prioridades clínicas 1 a 5 para variantes nivel1 a nivel5 com tokens semânticos", () => {
    const queryClient = createTestQueryClient();
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { rerender } = render(
      <MedicalRecordsPane atendimentoId={MOCK_ATENDIMENTO_ID} prioridadeClinica={1} />,
      { wrapper },
    );
    const badge1 = screen.getByText(/Vermelho: Emergência Imediata \(SAMU 192\)/i);
    expect(badge1.className).toMatch(/bg-acr-red text-acr-red-foreground/);
    expect(badge1.className).not.toMatch(/bg-destructive/);

    rerender(<MedicalRecordsPane atendimentoId={MOCK_ATENDIMENTO_ID} prioridadeClinica={2} />);
    const badge2 = screen.getByText(/Laranja: Muito Urgente/i);
    expect(badge2.className).toMatch(/bg-acr-orange text-acr-orange-foreground/);
    expect(badge2.className).not.toMatch(/bg-amber/);

    rerender(<MedicalRecordsPane atendimentoId={MOCK_ATENDIMENTO_ID} prioridadeClinica={3} />);
    const badge3 = screen.getByText(/Amarelo: Urgente/i);
    expect(badge3.className).toMatch(/bg-acr-yellow text-acr-yellow-foreground font-bold/);
    expect(badge3.className).not.toMatch(/bg-amber-400/);

    rerender(<MedicalRecordsPane atendimentoId={MOCK_ATENDIMENTO_ID} prioridadeClinica={4} />);
    const badge4 = screen.getByText(/Verde: Pouco Urgente/i);
    expect(badge4.className).toMatch(/bg-acr-green text-acr-green-foreground/);

    rerender(<MedicalRecordsPane atendimentoId={MOCK_ATENDIMENTO_ID} prioridadeClinica={5} />);
    const badge5 = screen.getByText(/Azul: Não Urgente/i);
    expect(badge5.className).toMatch(/bg-acr-blue text-acr-blue-foreground/);
    expect(badge5.className).not.toMatch(/bg-secondary/);
  });

  it("IT-MRP-02: renderiza documento clínico emitido e aciona download de PDF via hook headless", async () => {
    let downloadEndpointCalled = false;
    server.use(
      http.get(`*/api/v1/consultations/${MOCK_ATENDIMENTO_ID}/prontuario`, () => {
        return HttpResponse.json(
          createProntuarioResponse({
            documentos: [createDocumentoClinicoResponse({ assinado_em: "2026-11-01T12:00:00Z" })],
          }),
        );
      }),
      http.get(`*/api/v1/consultations/${MOCK_ATENDIMENTO_ID}/documents/${MOCK_DOC_ID}/pdf`, () => {
        downloadEndpointCalled = true;
        return new HttpResponse(new Blob(["%PDF-mock"], { type: "application/pdf" }), {
          headers: { "Content-Type": "application/pdf" },
        });
      }),
    );

    window.URL.createObjectURL = vi.fn(() => "blob:http://localhost/test-url");
    window.URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    const user = userEvent.setup();
    const queryClient = createTestQueryClient();
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    render(
      <MedicalRecordsPane
        atendimentoId={MOCK_ATENDIMENTO_ID}
        prioridadeClinica={3}
        token="token-123"
      />,
      { wrapper },
    );

    const btnBaixar = await screen.findByRole("button", { name: /baixar pdf/i });
    expect(btnBaixar).toBeInTheDocument();

    await user.click(btnBaixar);

    expect(downloadEndpointCalled).toBe(true);
    expect(window.URL.createObjectURL).toHaveBeenCalled();
  });
});
