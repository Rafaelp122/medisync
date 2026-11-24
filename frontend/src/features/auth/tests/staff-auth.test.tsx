import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  handleLoginApiV1AuthLoginPost,
  handleMeApiV1AuthMeGet,
  handleMfaActivateApiV1AuthMfaActivatePost,
  handleMfaSetupApiV1AuthMfaSetupPost,
  handleMfaVerifyApiV1AuthMfaVerifyPost,
} from "@/api/generated/msw.gen";
import { clearAccessToken, getAccessToken, setAccessToken } from "@/lib/auth-token";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/utils";
import { MfaSetupModal } from "../components/mfa-setup-modal";
import { StaffAuthCard } from "../components/staff-auth-card";

describe("Login Interno Isolado — StaffAuthCard, MfaSetupModal e /auth/me", () => {
  beforeEach(() => {
    localStorage.clear();
    clearAccessToken();
    server.use(
      handleLoginApiV1AuthLoginPost({
        body: {
          access_token: "staff-access-token",
          refresh_token: "staff-refresh-token",
          token_type: "bearer",
          expires_in: 900,
          refresh_expires_in: 604800,
          mfa_requerido: false,
          mfa_setup_requerido: false,
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

  afterEach(() => {
    clearAccessToken();
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
    expect(screen.getByRole("heading", { name: /gestão da unidade/i })).toBeInTheDocument();

    screen.getByRole("tab", { name: /gestor/i }).focus();
    await user.keyboard("{ArrowLeft}");
    expect(screen.getByRole("tab", { name: /médico/i })).toHaveAttribute("aria-selected", "true");
  });

  it("StaffAuthCard hidrata gestor real via GET /auth/me com papel GESTOR_UNIDADE sem UUID hardcoded", async () => {
    server.use(
      handleMeApiV1AuthMeGet({
        body: {
          usuario_id: "018f9999-1111-7777-8888-aaaaaaaa0001",
          identificador: "gestor.unidade@saude.gov.br",
          papel: "GESTOR_UNIDADE",
          ativo: true,
        },
      }),
    );

    const onManagerAuthenticated = vi.fn();
    renderWithProviders(
      <StaffAuthCard
        initialPerfil="gestor"
        onDoctorAuthenticated={vi.fn()}
        onManagerAuthenticated={onManagerAuthenticated}
      />,
    );

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/e-mail institucional/i), "gestor.unidade@saude.gov.br");
    await user.type(screen.getByLabelText(/senha/i), "Gestor@2026");
    await user.click(screen.getByRole("button", { name: /acessar painel da unidade/i }));

    await waitFor(() => {
      expect(onManagerAuthenticated).toHaveBeenCalledWith({
        usuarioId: "018f9999-1111-7777-8888-aaaaaaaa0001",
        nome: "gestor.unidade@saude.gov.br",
        email: "gestor.unidade@saude.gov.br",
        papel: "GESTOR_UNIDADE",
      });
      expect(getAccessToken()).toBe("staff-access-token");
    });
  });

  it("StaffAuthCard aciona MfaSetupModal -> MfaVerifyModal -> /auth/me para médico com mfa_setup_requerido", async () => {
    let setupAuthHeader: string | null = null;
    let meAuthHeader: string | null = null;

    server.use(
      handleLoginApiV1AuthLoginPost({
        body: {
          access_token: "mfa-pending-temp-token-12345",
          refresh_token: "refresh-pending",
          token_type: "bearer",
          expires_in: 300,
          refresh_expires_in: 300,
          mfa_requerido: false,
          mfa_setup_requerido: true,
        },
      }),
      handleMfaSetupApiV1AuthMfaSetupPost(({ request }) => {
        setupAuthHeader = request.headers.get("Authorization");
        return HttpResponse.json({
          secret: "JBSWY3DPEHPK3PXP",
          uri: "otpauth://totp/MediSync:987654/RJ?secret=JBSWY3DPEHPK3PXP&issuer=MediSync",
        });
      }),
      handleMfaActivateApiV1AuthMfaActivatePost({
        body: {
          ativo: true,
          mensagem: "Segundo fator de autenticação ativado com sucesso.",
        },
      }),
      handleMfaVerifyApiV1AuthMfaVerifyPost({
        body: {
          access_token: "final-doctor-jwt-999",
          refresh_token: "final-doctor-refresh",
          token_type: "bearer",
          expires_in: 900,
          refresh_expires_in: 604800,
          mfa_requerido: false,
          mfa_setup_requerido: false,
        },
      }),
      handleMeApiV1AuthMeGet(({ request }) => {
        meAuthHeader = request.headers.get("Authorization");
        return HttpResponse.json({
          usuario_id: "018f9999-2222-7777-8888-bbbbbbbb0002",
          identificador: "987654/RJ",
          papel: "MEDICO",
          ativo: true,
        });
      }),
    );

    const onDoctorAuthenticated = vi.fn();
    renderWithProviders(
      <StaffAuthCard
        onDoctorAuthenticated={onDoctorAuthenticated}
        onManagerAuthenticated={vi.fn()}
      />,
    );

    const user = userEvent.setup();
    const crmInput = screen.getByLabelText(/^crm:/i);
    const ufInput = screen.getByLabelText(/^uf:/i);
    const senhaInput = screen.getByLabelText(/senha de acesso/i);

    await user.clear(crmInput);
    await user.type(crmInput, "987654");
    await user.clear(ufInput);
    await user.type(ufInput, "RJ");
    await user.clear(senhaInput);
    await user.type(senhaInput, "Medisync@2026");
    await user.click(screen.getByRole("button", { name: /entrar no plantão/i }));

    await waitFor(() => {
      expect(screen.getByText("JBSWY3DPEHPK3PXP")).toBeInTheDocument();
    });
    expect(setupAuthHeader).toBe("Bearer mfa-pending-temp-token-12345");

    await user.type(screen.getByLabelText(/código de confirmação/i), "123456");
    await user.click(screen.getByRole("button", { name: /validar e ativar mfa/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/código de verificação \(6 dígitos\)/i)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/código de verificação \(6 dígitos\)/i), "654321");
    await user.click(screen.getByRole("button", { name: /confirmar e acessar/i }));

    await waitFor(() => {
      expect(meAuthHeader).toBe("Bearer final-doctor-jwt-999");
      expect(onDoctorAuthenticated).toHaveBeenCalledWith({
        medicoId: "018f9999-2222-7777-8888-bbbbbbbb0002",
        medicoNome: "987654/RJ",
        crmUf: "987654/RJ",
        identificador: "987654/RJ",
        papel: "MEDICO",
      });
      expect(getAccessToken()).toBe("final-doctor-jwt-999");
    });
  });

  it("Rejeita e limpa sessão quando GET /auth/me retorna papel incompatível com a aba selecionada", async () => {
    server.use(
      handleMeApiV1AuthMeGet({
        body: {
          usuario_id: "018f9999-3333-7777-8888-cccccccc0003",
          identificador: "medico@saude.gov.br",
          papel: "MEDICO",
          ativo: true,
        },
      }),
    );

    const onManagerAuthenticated = vi.fn();
    renderWithProviders(
      <StaffAuthCard
        initialPerfil="gestor"
        onDoctorAuthenticated={vi.fn()}
        onManagerAuthenticated={onManagerAuthenticated}
      />,
    );

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/e-mail institucional/i), "medico@saude.gov.br");
    await user.type(screen.getByLabelText(/senha/i), "Senha@2026");
    await user.click(screen.getByRole("button", { name: /acessar painel da unidade/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/acesso restrito a gestores da unidade ativos \(perfil gestor_unidade\)/i),
      ).toBeInTheDocument();
    });
    expect(onManagerAuthenticated).not.toHaveBeenCalled();
    expect(getAccessToken()).toBeNull();
  });

  it("MfaSetupModal exibe segredo TOTP Base32, URI otpauth:// e ativa MFA com código de 6 dígitos", async () => {
    setAccessToken("staff-access-token");
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
    setAccessToken("staff-access-token");
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
