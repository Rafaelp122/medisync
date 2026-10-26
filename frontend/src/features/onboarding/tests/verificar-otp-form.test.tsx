import { waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/utils";
import { VerificarOtpForm } from "../components/verificar-otp-form";

describe("VerificarOtpForm (Integração de Tela)", () => {
  const defaultTelefone = "+5511987654321";

  it("IT-05: Cenário Feliz de Verificação OTP", async () => {
    const user = userEvent.setup();
    const handleAuthenticated = vi.fn();

    const { getAllByRole, getByRole } = renderWithProviders(
      <VerificarOtpForm telefone={defaultTelefone} onAuthenticated={handleAuthenticated} />,
    );

    const inputs = getAllByRole("textbox");
    expect(inputs).toHaveLength(6);

    for (let i = 0; i < 6; i++) {
      await user.type(inputs[i], String(i + 1));
    }

    const submitBtn = getByRole("button", { name: /confirmar e entrar/i });
    await user.click(submitBtn);

    await waitFor(() => {
      expect(handleAuthenticated).toHaveBeenCalledWith(
        expect.objectContaining({
          access_token: "mock-jwt-token-paciente",
          role: "PACIENTE",
        }),
      );
    });
  });

  it("IT-06: Auto-advance e Suporte a Colagem (Paste)", async () => {
    const user = userEvent.setup();

    const { getAllByRole } = renderWithProviders(
      <VerificarOtpForm telefone={defaultTelefone} onAuthenticated={vi.fn()} />,
    );

    const inputs = getAllByRole("textbox");
    inputs[0].focus();
    await user.paste("654321");

    expect(inputs[0]).toHaveValue("6");
    expect(inputs[1]).toHaveValue("5");
    expect(inputs[2]).toHaveValue("4");
    expect(inputs[3]).toHaveValue("3");
    expect(inputs[4]).toHaveValue("2");
    expect(inputs[5]).toHaveValue("1");
    expect(inputs[5]).toHaveFocus();

    // Test backspace retreating
    await user.keyboard("{Backspace}");
    expect(inputs[5]).toHaveValue("");
    expect(inputs[4]).toHaveFocus();
  });

  it("IT-07: Erro RFC 7807 de Código Inválido (HTTP 401)", async () => {
    server.use(
      http.post("*/api/v1/auth/patient/otp/verify", () => {
        return HttpResponse.json(
          {
            title: "Código OTP inválido",
            status: 401,
            detail: "Código incorreto. Você tem mais 2 tentativa(s).",
          },
          { status: 401 },
        );
      }),
    );

    const user = userEvent.setup();
    const handleAuthenticated = vi.fn();

    const { getAllByRole, getByRole, findByText } = renderWithProviders(
      <VerificarOtpForm telefone={defaultTelefone} onAuthenticated={handleAuthenticated} />,
    );

    const inputs = getAllByRole("textbox");
    inputs[0].focus();
    await user.paste("000000");

    const submitBtn = getByRole("button", { name: /confirmar e entrar/i });
    await user.click(submitBtn);

    const errorMsg = await findByText(/código incorreto\. você tem mais 2 tentativa\(s\)\./i);
    expect(errorMsg).toBeInTheDocument();
    expect(handleAuthenticated).not.toHaveBeenCalled();
    expect(inputs[0]).toHaveFocus();
  });

  it("IT-08: Bloqueio por Tentativas Excedidas (HTTP 429)", async () => {
    server.use(
      http.post("*/api/v1/auth/patient/otp/verify", () => {
        return HttpResponse.json(
          {
            title: "Tentativas excedidas",
            status: 429,
            detail: "Número excessivo de tentativas incorretas. Solicite um novo código.",
          },
          { status: 429 },
        );
      }),
    );

    const user = userEvent.setup();
    const handleAuthenticated = vi.fn();

    const { getAllByRole, getByRole, findByText } = renderWithProviders(
      <VerificarOtpForm telefone={defaultTelefone} onAuthenticated={handleAuthenticated} />,
    );

    const inputs = getAllByRole("textbox");
    inputs[0].focus();
    await user.paste("999999");

    const submitBtn = getByRole("button", { name: /confirmar e entrar/i });
    await user.click(submitBtn);

    const errorMsg = await findByText(
      /número excessivo de tentativas incorretas\. solicite um novo código\./i,
    );
    expect(errorMsg).toBeInTheDocument();
    expect(inputs[0]).toBeDisabled();
    expect(submitBtn).toBeDisabled();
    expect(handleAuthenticated).not.toHaveBeenCalled();
  });

  it("IT-09: Foco inicial automático no primeiro dígito (US-02 §5.1)", () => {
    const { getAllByRole } = renderWithProviders(
      <VerificarOtpForm telefone={defaultTelefone} onAuthenticated={vi.fn()} />,
    );
    const inputs = getAllByRole("textbox");
    expect(inputs[0]).toHaveFocus();
  });

  it("IT-10: Validação de código com verificarOtpSchema antes da submissão", async () => {
    const user = userEvent.setup();
    const handleAuthenticated = vi.fn();

    const { getAllByRole, getByRole } = renderWithProviders(
      <VerificarOtpForm telefone={defaultTelefone} onAuthenticated={handleAuthenticated} />,
    );

    const inputs = getAllByRole("textbox");
    // Type incomplete 5 digits
    await user.type(inputs[0], "1");
    await user.type(inputs[1], "2");
    await user.type(inputs[2], "3");
    await user.type(inputs[3], "4");
    await user.type(inputs[4], "5");

    const submitBtn = getByRole("button", { name: /confirmar e entrar/i });
    expect(submitBtn).toBeDisabled();
    expect(handleAuthenticated).not.toHaveBeenCalled();
  });
});
