import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  handleGetAuthPatientMethods,
  handlePostAuthPatientIdentify,
  handlePostAuthPatientLoginPassword,
  handlePostAuthPatientRegister,
  handleRequestOtpApiV1AuthPatientOtpRequestPost,
  handleVerifyOtpApiV1AuthPatientOtpVerifyPost,
} from "@/api/generated/msw.gen";
import { clearStoredSession, getStoredSession } from "@/lib/session-storage";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/utils";
import { PatientHybridAuthCard } from "../components/patient-hybrid-auth-card";
import { PatientRegisterForm } from "../components/patient-register-form";

const MOCK_PACIENTE_ID = "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c";
const MOCK_ATENDIMENTO_ID = "018f3a5b-aaaa-bbbb-cccc-018f3a5b9999";

describe("IAM Híbrido do Cidadão — PatientHybridAuthCard e PatientRegisterForm", () => {
  beforeEach(() => {
    clearStoredSession();
    server.use(
      handleGetAuthPatientMethods({
        body: {
          govbr_oidc_enabled: false,
          passkeys_enabled: true,
          otp_enabled: true,
          password_fallback_enabled: true,
        },
      }),
      handleRequestOtpApiV1AuthPatientOtpRequestPost({
        body: {
          mensagem: "Código enviado com sucesso.",
          expira_em_segundos: 300,
          codigo_debug: "654321",
        },
      }),
      handleVerifyOtpApiV1AuthPatientOtpVerifyPost({
        body: {
          access_token: "jwt-paciente-otp",
          token_type: "bearer",
          expires_in: 3600,
          paciente_id: MOCK_PACIENTE_ID,
          role: "PACIENTE",
          atendimento_id: null,
        },
      }),
    );
  });

  it("Passo 1 (CPF) -> Passo 2A (OTP) -> autentica, persiste sessão e aciona onAuthenticated", async () => {
    let identifiedCpf = "";
    server.use(
      handlePostAuthPatientIdentify(async ({ request }) => {
        const body = await request.json();
        identifiedCpf = body.identificador;
        return HttpResponse.json({
          possui_conta: true,
          metodos_disponiveis: ["otp", "senha", "passkey"],
          telefone_mascarado: "(11) 9****-4321",
          govbr_habilitado: false,
        });
      }),
    );

    const onAuthenticated = vi.fn();
    renderWithProviders(<PatientHybridAuthCard onAuthenticated={onAuthenticated} />);

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/cpf ou e-mail/i), "52998224725");
    await user.click(screen.getByRole("button", { name: /continuar/i }));

    await waitFor(() => {
      expect(identifiedCpf).toBe("52998224725");
      expect(screen.getByText("(11) 9****-4321")).toBeInTheDocument();
    });

    // Gov.br não habilitado -> não deve renderizar botão fake
    expect(screen.queryByRole("button", { name: /gov\.br/i })).not.toBeInTheDocument();
    // Passkey disponível nos métodos -> renderiza botão biométrico
    expect(screen.getByRole("button", { name: /passkey/i })).toBeInTheDocument();

    // Confirma celular e solicita código OTP
    await user.type(screen.getByLabelText(/confirme seu celular/i), "11987654321");
    await user.click(screen.getByRole("button", { name: /receber código de 6 dígitos/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/código sms de 6 dígitos/i)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/código sms de 6 dígitos/i), "654321");
    await user.click(screen.getByRole("button", { name: /confirmar e entrar/i }));

    await waitFor(() => {
      expect(onAuthenticated).toHaveBeenCalledWith(
        expect.objectContaining({
          token: "jwt-paciente-otp",
          pacienteId: MOCK_PACIENTE_ID,
          role: "PACIENTE",
        }),
      );
      expect(getStoredSession()?.token).toBe("jwt-paciente-otp");
    });
  });

  it("Passo 1 quando possui_conta === false exibe convite empático para /cadastro", async () => {
    server.use(
      handlePostAuthPatientIdentify({
        body: {
          possui_conta: false,
          metodos_disponiveis: [],
          telefone_mascarado: null,
          govbr_habilitado: false,
        },
      }),
    );

    const onGoToRegister = vi.fn();
    renderWithProviders(
      <PatientHybridAuthCard onAuthenticated={vi.fn()} onGoToRegister={onGoToRegister} />,
    );

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/cpf ou e-mail/i), "paciente.novo@exemplo.com");
    await user.click(screen.getByRole("button", { name: /continuar/i }));

    await waitFor(() => {
      expect(screen.getByText(/primeiro acesso no medisync/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /criar minha conta/i }));
    expect(onGoToRegister).toHaveBeenCalledTimes(1);
  });

  it("Passo 1 (e-mail) -> clique no link discreto para Passo 2B (login-password) -> sucesso com atendimento ativo", async () => {
    server.use(
      handlePostAuthPatientIdentify({
        body: {
          possui_conta: true,
          metodos_disponiveis: ["otp", "senha", "govbr"],
          telefone_mascarado: "(21) 9****-8877",
          govbr_habilitado: true,
        },
      }),
      handlePostAuthPatientLoginPassword({
        body: {
          access_token: "jwt-paciente-senha",
          token_type: "bearer",
          expires_in: 3600,
          paciente_id: MOCK_PACIENTE_ID,
          role: "PACIENTE",
          atendimento_id: MOCK_ATENDIMENTO_ID,
        },
      }),
    );

    const onAuthenticated = vi.fn();
    renderWithProviders(
      <PatientHybridAuthCard onAuthenticated={onAuthenticated} onGovbrClick={vi.fn()} />,
    );

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/cpf ou e-mail/i), "Maria@Exemplo.COM");
    await user.click(screen.getByRole("button", { name: /continuar/i }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /entrar com gov\.br/i })).toBeInTheDocument();
    });

    await user.click(
      screen.getByRole("button", { name: /não tem acesso ao celular agora\? entrar com senha/i }),
    );

    await user.type(screen.getByLabelText(/senha de acesso/i), "SenhaForte@2026");
    await user.click(screen.getByRole("button", { name: /entrar com senha/i }));

    await waitFor(() => {
      expect(onAuthenticated).toHaveBeenCalledWith(
        expect.objectContaining({
          token: "jwt-paciente-senha",
          atendimentoId: MOCK_ATENDIMENTO_ID,
        }),
      );
      expect(getStoredSession()?.atendimentoId).toBe(MOCK_ATENDIMENTO_ID);
    });
  });

  it("Passo 2B exibe erro RFC 7807 quando login-password retorna 401 ou 423", async () => {
    server.use(
      handlePostAuthPatientIdentify({
        body: {
          possui_conta: true,
          metodos_disponiveis: ["otp", "senha"],
          telefone_mascarado: "(11) 9****-1111",
          govbr_habilitado: false,
        },
      }),
      handlePostAuthPatientLoginPassword(() =>
        HttpResponse.json(
          {
            type: "about:blank",
            title: "Conta bloqueada",
            status: 423,
            detail:
              "Conta temporariamente bloqueada após tentativas inválidas. Aguarde 15 minutos.",
          },
          { status: 423 },
        ),
      ),
    );

    renderWithProviders(<PatientHybridAuthCard onAuthenticated={vi.fn()} />);

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/cpf ou e-mail/i), "maria@exemplo.com");
    await user.click(screen.getByRole("button", { name: /continuar/i }));

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /não tem acesso ao celular agora\?/i }),
      ).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /não tem acesso ao celular agora\?/i }));
    await user.type(screen.getByLabelText(/senha de acesso/i), "errada123");
    await user.click(screen.getByRole("button", { name: /entrar com senha/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/conta temporariamente bloqueada após tentativas inválidas/i),
      ).toBeInTheDocument();
    });
  });

  it("Cadastro (/cadastro): PatientRegisterForm envia register (201) e conclui confirmação OTP", async () => {
    let capturedRegisterBody: Record<string, unknown> | null = null;
    server.use(
      handlePostAuthPatientRegister(async ({ request }) => {
        capturedRegisterBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          {
            paciente_id: MOCK_PACIENTE_ID,
            telefone_mascarado: "(11) 9****-4321",
            otp_enviado: true,
            expira_em_segundos: 300,
            codigo_debug: "654321",
          },
          { status: 201 },
        );
      }),
    );

    const onAuthenticated = vi.fn();
    renderWithProviders(<PatientRegisterForm onAuthenticated={onAuthenticated} />);

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/^cpf/i), "52998224725");
    await user.type(screen.getByLabelText(/nome completo/i), "Ana Paula Ferreira");
    await user.type(screen.getByLabelText(/data de nascimento/i), "1992-07-14");
    await user.type(screen.getByLabelText(/telefone celular/i), "11987654321");
    await user.type(screen.getByLabelText(/e-mail/i), "ana.paula@exemplo.com");
    await user.type(screen.getByLabelText(/senha alternativa/i), "SenhaSegura@2026");
    await user.click(screen.getByLabelText(/política de privacidade/i));
    await user.click(screen.getByRole("button", { name: /criar conta e receber código sms/i }));

    await waitFor(() => {
      expect(capturedRegisterBody).toMatchObject({
        cpf: "52998224725",
        nome_completo: "Ana Paula Ferreira",
        telefone: "+5511987654321",
        aceite_privacidade: true,
        email: "ana.paula@exemplo.com",
      });
      expect(screen.getByLabelText(/código sms \(6 dígitos\)/i)).toBeInTheDocument();
      expect(screen.getByText(/código sms:/i)).toBeInTheDocument();
      expect(screen.getByText("654321")).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/código sms \(6 dígitos\)/i), "654321");
    await user.click(screen.getByRole("button", { name: /confirmar e acessar/i }));

    await waitFor(() => {
      expect(onAuthenticated).toHaveBeenCalledWith(
        expect.objectContaining({
          token: "jwt-paciente-otp",
          pacienteId: MOCK_PACIENTE_ID,
        }),
      );
      expect(getStoredSession()?.token).toBe("jwt-paciente-otp");
    });
  });

  it("Cadastro (/cadastro): exige e-mail válido obrigatório antes de enviar requisição", async () => {
    renderWithProviders(<PatientRegisterForm onAuthenticated={vi.fn()} />);

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/^cpf/i), "52998224725");
    await user.type(screen.getByLabelText(/nome completo/i), "Ana Paula Ferreira");
    await user.type(screen.getByLabelText(/data de nascimento/i), "1992-07-14");
    await user.type(screen.getByLabelText(/telefone celular/i), "11987654321");
    await user.click(screen.getByLabelText(/política de privacidade/i));
    await user.type(screen.getByLabelText(/^e-mail/i), "invalido");
    await user.click(screen.getByRole("button", { name: /criar conta e receber código sms/i }));

    await waitFor(() => {
      expect(screen.getByText(/informe um e-mail válido/i)).toBeInTheDocument();
    });
  });

  it("Não renderiza botão clicável 'Entrar com Gov.br' quando onGovbrClick for omitido", async () => {
    server.use(
      handleGetAuthPatientMethods({
        body: {
          govbr_oidc_enabled: true,
          passkeys_enabled: true,
          otp_enabled: true,
          password_fallback_enabled: true,
        },
      }),
      handlePostAuthPatientIdentify({
        body: {
          possui_conta: true,
          metodos_disponiveis: ["otp", "senha", "govbr"],
          telefone_mascarado: "(21) 9****-8877",
          govbr_habilitado: true,
        },
      }),
    );

    renderWithProviders(<PatientHybridAuthCard onAuthenticated={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByLabelText(/cpf ou e-mail/i)).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: /gov\.br/i })).not.toBeInTheDocument();

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/cpf ou e-mail/i), "maria@exemplo.com");
    await user.click(screen.getByRole("button", { name: /continuar/i }));

    await waitFor(() => {
      expect(screen.getByText("(21) 9****-8877")).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: /gov\.br/i })).not.toBeInTheDocument();
  });
});
