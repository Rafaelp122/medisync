import { act, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/utils";
import { SolicitarOtpForm } from "../components/solicitar-otp-form";

describe("SolicitarOtpForm (Integração de Tela)", () => {
  it("IT-01: Cenário Feliz de Solicitação de OTP", async () => {
    const user = userEvent.setup();
    const handleOtpSent = vi.fn();

    const { getByRole, getByLabelText } = renderWithProviders(
      <SolicitarOtpForm onOtpSent={handleOtpSent} />,
    );

    const input = getByLabelText(/telefone celular/i);
    await user.type(input, "11987654321");
    expect(input).toHaveValue("(11) 98765-4321");

    const submitBtn = getByRole("button", { name: /receber código/i });
    await user.click(submitBtn);

    await waitFor(() => {
      expect(handleOtpSent).toHaveBeenCalledWith(
        expect.objectContaining({
          telefone: "+5511987654321",
          expiraEmSegundos: 300,
        }),
      );
    });
  });

  it("IT-02: Validação Zod Client-Side com Alerta em Português", async () => {
    const user = userEvent.setup();
    const handleOtpSent = vi.fn();

    const { getByRole, getByLabelText, findByRole } = renderWithProviders(
      <SolicitarOtpForm onOtpSent={handleOtpSent} />,
    );

    const input = getByLabelText(/telefone celular/i);
    await user.type(input, "1133334444");

    const submitBtn = getByRole("button", { name: /receber código/i });
    await user.click(submitBtn);

    const alert = await findByRole("alert");
    expect(alert).toHaveTextContent("Telefone inválido; informe DDD + 9 dígitos");
    expect(handleOtpSent).not.toHaveBeenCalled();
  });

  it("IT-03: Cooldown Determinístico de 60s com Fake Timers", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTimeAsync });
    const handleOtpSent = vi.fn();

    const { getByRole, getByLabelText, findByRole } = renderWithProviders(
      <SolicitarOtpForm onOtpSent={handleOtpSent} />,
    );

    const input = getByLabelText(/telefone celular/i);
    await user.type(input, "11987654321");

    const submitBtn = getByRole("button", { name: /receber código/i });
    await user.click(submitBtn);

    await waitFor(() => {
      expect(handleOtpSent).toHaveBeenCalled();
    });

    // Confirm button in cooldown
    const cooldownBtn = await findByRole("button", {
      name: /reenviar código em 60s/i,
    });
    expect(cooldownBtn).toBeDisabled();

    // Advance 30 seconds inside act
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(getByRole("button", { name: /reenviar código em 30s/i })).toBeDisabled();

    // Advance remaining 30 seconds inside act
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    const enabledBtn = getByRole("button", { name: /receber código/i });
    expect(enabledBtn).toBeEnabled();
  });

  it("IT-04: Erro RFC 7807 de Rate Limit (HTTP 429)", async () => {
    server.use(
      http.post("*/api/v1/auth/patient/otp/request", () => {
        return HttpResponse.json(
          {
            title: "Limite de envios excedido",
            status: 429,
            detail: "Limite de 3 envios atingido. Aguarde 15 minutos.",
          },
          { status: 429 },
        );
      }),
    );

    const user = userEvent.setup();
    const handleOtpSent = vi.fn();

    const { getByRole, getByLabelText, findByText } = renderWithProviders(
      <SolicitarOtpForm onOtpSent={handleOtpSent} />,
    );

    const input = getByLabelText(/telefone celular/i);
    await user.type(input, "11987654321");

    const submitBtn = getByRole("button", { name: /receber código/i });
    await user.click(submitBtn);

    const errorMsg = await findByText(/limite de 3 envios atingido\. aguarde 15 minutos\./i);
    expect(errorMsg).toBeInTheDocument();
    expect(handleOtpSent).not.toHaveBeenCalled();
  });
});
