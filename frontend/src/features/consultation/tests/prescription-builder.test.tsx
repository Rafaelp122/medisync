import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/utils";
import { PrescriptionBuilder } from "../components/prescription-builder";
import { createDocumentoClinicoResponse, MOCK_ATENDIMENTO_ID } from "./fixtures";

describe("PrescriptionBuilder Integration Tests (Receita vs Atestado & CFM 2.314)", () => {
  beforeEach(() => {
    server.use(
      http.post(`*/api/v1/consultations/${MOCK_ATENDIMENTO_ID}/documents`, async ({ request }) => {
        const body = (await request.json()) as {
          tipo_documento: string;
          justificativa_tempo_inferior?: string;
        };
        return HttpResponse.json(
          createDocumentoClinicoResponse({
            tipo_documento: body.tipo_documento,
          }),
          { status: 201 },
        );
      }),
    );
  });

  it("IT-PRESC-01: Permite alternar entre Receita Simples e Atestado Médico", async () => {
    renderWithProviders(
      <PrescriptionBuilder
        atendimentoId={MOCK_ATENDIMENTO_ID}
        identidadeVerificada={true}
        duracaoSegundos={200}
      />,
    );

    const tabReceita = screen.getByRole("tab", { name: /receita simples/i });
    const tabAtestado = screen.getByRole("tab", { name: /atestado médico/i });

    expect(tabReceita).toHaveAttribute("aria-selected", "true");
    expect(
      screen.getByText(/prescrição digital & salvaguardas farmacêuticas/i),
    ).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(tabAtestado);

    expect(tabAtestado).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText(/atestado médico & justificativa legal/i)).toBeInTheDocument();
  });

  it("IT-PRESC-02: Exibe trava antifraude (CFM nº 2.314/2022) quando consulta < 180s para Atestado", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <PrescriptionBuilder
        atendimentoId={MOCK_ATENDIMENTO_ID}
        identidadeVerificada={true}
        duracaoSegundos={60}
      />,
    );

    await user.click(screen.getByRole("tab", { name: /atestado médico/i }));

    expect(
      screen.getByText(/trava temporal antifraude \(cfm nº 2\.314\/2022\)/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/a consulta durou 60s \(inferior ao piso de 180s\)/i),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/justificativa médica/i)).toBeInTheDocument();
  });

  it("IT-PRESC-03: Bloqueia emissão de atestado quando justificativa tem menos de 15 caracteres", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <PrescriptionBuilder
        atendimentoId={MOCK_ATENDIMENTO_ID}
        identidadeVerificada={true}
        duracaoSegundos={90}
      />,
    );

    await user.click(screen.getByRole("tab", { name: /atestado médico/i }));

    const btnEmitir = screen.getByRole("button", { name: /emitir atestado médico/i });
    expect(btnEmitir).toBeDisabled();

    const inputJustificativa = screen.getByLabelText(/justificativa médica/i);
    await user.type(inputJustificativa, "Muito curto");

    expect(screen.getByText(/mínimo de 15 caracteres \(atual:/i)).toBeInTheDocument();
    expect(btnEmitir).toBeDisabled();
  });

  it("IT-PRESC-04: Habilita e emite Atestado Médico com justificativa válida (>= 15 caracteres)", async () => {
    const handleIssued = vi.fn();
    const user = userEvent.setup();

    renderWithProviders(
      <PrescriptionBuilder
        atendimentoId={MOCK_ATENDIMENTO_ID}
        identidadeVerificada={true}
        duracaoSegundos={100}
        onPrescriptionIssued={handleIssued}
      />,
    );

    await user.click(screen.getByRole("tab", { name: /atestado médico/i }));

    const inputJustificativa = screen.getByLabelText(/justificativa médica/i);
    await user.type(
      inputJustificativa,
      "Paciente em acompanhamento crônico apresentando atestado de comparecimento célere",
    );

    const btnEmitir = screen.getByRole("button", { name: /emitir atestado médico/i });
    expect(btnEmitir).not.toBeDisabled();

    await user.click(btnEmitir);

    await waitFor(() => {
      expect(screen.getByText(/atestado médico #.* gerado com sucesso/i)).toBeInTheDocument();
      expect(handleIssued).toHaveBeenCalledWith(
        expect.objectContaining({
          tipo_documento: "ATESTADO_MEDICO",
        }),
      );
    });
  });

  it("IT-PRESC-05: Emite Atestado Médico sem exigir justificativa quando duração for >= 180s", async () => {
    const handleIssued = vi.fn();
    const user = userEvent.setup();

    renderWithProviders(
      <PrescriptionBuilder
        atendimentoId={MOCK_ATENDIMENTO_ID}
        identidadeVerificada={true}
        duracaoSegundos={250}
        onPrescriptionIssued={handleIssued}
      />,
    );

    await user.click(screen.getByRole("tab", { name: /atestado médico/i }));

    // Não deve exibir o card de trava temporal nem campo obrigatório
    expect(
      screen.queryByText(/trava temporal antifraude \(cfm nº 2\.314\/2022\)/i),
    ).not.toBeInTheDocument();

    const btnEmitir = screen.getByRole("button", { name: /emitir atestado médico/i });
    expect(btnEmitir).not.toBeDisabled();

    await user.click(btnEmitir);

    await waitFor(() => {
      expect(screen.getByText(/atestado médico #.* gerado com sucesso/i)).toBeInTheDocument();
      expect(handleIssued).toHaveBeenCalled();
    });
  });
});
