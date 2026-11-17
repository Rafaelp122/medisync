import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  handleLoginApiV1AuthLoginPost,
  handleMfaActivateApiV1AuthMfaActivatePost,
  handleMfaSetupApiV1AuthMfaSetupPost,
} from "@/api/generated/msw.gen";
import { getAccessToken, setAccessToken } from "@/lib/auth-token";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/utils";
import { MfaSetupModal } from "../components/mfa-setup-modal";
import { StaffAuthCard } from "../components/staff-auth-card";

describe("Login Interno Isolado — StaffAuthCard e MfaSetupModal", () => {
  beforeEach(() => {
    setAccessToken(null);
    server.use(
      handleLoginApiV1AuthLoginPost({
        body: {
          access_token: "staff-access-token",
          refresh_token: "staff-refresh-token",
          token_type: "bearer",
          expires_in: 900,
          refresh_expires_in: 604800,
          mfa_requerido: false,
        },
      }),
      handleMfaSetupApiV1AuthMfaSetupPost({
        body: {
          secret: "JBSWY3DPEHPK3PXP",
          uri: "otpauth://totp/MediSync:dr.eduardo@medisync.com.br?secret=JBSWY3DPEHPK3PXP&issuer=MediSync",
        },
      }),
      handleMfaActivateApiV1AuthMfaActivatePost({
        body: {
          ativo: true,
          mensagem: "Segundo fator de autenticação ativado com sucesso.",
        },
      }),
    );
  });

  it("StaffAuthCard renderiza exclusivamente as abas Médico e Gestor (sem aba Cidadão)", async () => {
    renderWithProviders(
      <StaffAuthCard onDoctorAuthenticated={vi.fn()} onManagerAuthenticated={vi.fn()} />,
    );

    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(2);
    expect(screen.getByRole("tab", { name: /médico/i })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: /gestor/i })).toHaveAttribute("aria-selected", "false");
    expect(screen.queryByRole("tab", { name: /cidadão/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /paciente/i })).not.toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: /gestor/i }));
    expect(screen.getByRole("tab", { name: /gestor/i })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { name: /regulação municipal/i })).toBeInTheDocument();

    // Navegação por teclado entre as 2 abas
    screen.getByRole("tab", { name: /gestor/i }).focus();
    await user.keyboard("{ArrowLeft}");
    expect(screen.getByRole("tab", { name: /médico/i })).toHaveAttribute("aria-selected", "true");
  });

  it("StaffAuthCard autentica gestor corporativo sem exibir entrada pública", async () => {
    const onManagerAuthenticated = vi.fn();
    renderWithProviders(
      <StaffAuthCard
        initialPerfil="gestor"
        onDoctorAuthenticated={vi.fn()}
        onManagerAuthenticated={onManagerAuthenticated}
      />,
    );

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/e-mail institucional/i), "gestor@saude.gov.br");
    await user.type(screen.getByLabelText(/senha/i), "Gestor@2026");
    await user.click(screen.getByRole("button", { name: /acessar painel da regulação/i }));

    await waitFor(() => {
      expect(onManagerAuthenticated).toHaveBeenCalledWith(
        expect.objectContaining({
          email: "gestor@saude.gov.br",
          papel: "GESTOR",
        }),
      );
      expect(getAccessToken()).toBe("staff-access-token");
    });
  });

  it("MfaSetupModal exibe segredo TOTP Base32, URI otpauth:// e ativa MFA com código de 6 dígitos", async () => {
    const onActivated = vi.fn();
    renderWithProviders(
      <MfaSetupModal open={true} onOpenChange={vi.fn()} onActivated={onActivated} />,
    );

    await waitFor(() => {
      expect(screen.getByText("JBSWY3DPEHPK3PXP")).toBeInTheDocument();
      expect(screen.getByText(/otpauth:\/\/totp\/MediSync/i)).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/código de confirmação/i), "123456");
    await user.click(screen.getByRole("button", { name: /validar e ativar mfa/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/segundo fator de autenticação ativado com sucesso/i),
      ).toBeInTheDocument();
      expect(onActivated).toHaveBeenCalledTimes(1);
    });
  });

  it("MfaSetupModal exibe erro RFC 7807 se o código TOTP for rejeitado na ativação", async () => {
    server.use(
      handleMfaActivateApiV1AuthMfaActivatePost(() =>
        HttpResponse.json(
          {
            type: "about:blank",
            title: "Código TOTP inválido",
            status: 400,
            detail: "Código TOTP incorreto; verifique o relógio do aplicativo autenticador.",
          },
          { status: 400 },
        ),
      ),
    );

    renderWithProviders(<MfaSetupModal open={true} onOpenChange={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText("JBSWY3DPEHPK3PXP")).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/código de confirmação/i), "000000");
    await user.click(screen.getByRole("button", { name: /validar e ativar mfa/i }));

    await waitFor(() => {
      expect(screen.getByText(/código totp incorreto/i)).toBeInTheDocument();
    });
  });
});
