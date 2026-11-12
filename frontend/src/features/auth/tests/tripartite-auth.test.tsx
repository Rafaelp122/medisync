import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { TokenResponse, VerificarOtpResponse } from "@/api/generated/types.gen";
import { getAccessToken } from "@/lib/auth-token";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/utils";
import { CadsusLoginForm } from "../components/cadsus-login-form";
import { DoctorLoginForm } from "../components/doctor-login-form";
import { ManagerLoginForm } from "../components/manager-login-form";
import { TripartiteAuthCard } from "../components/tripartite-auth-card";

const mockTokenResponse: TokenResponse = {
  access_token: "mock-access-token-xyz",
  refresh_token: "mock-refresh-token-abc",
  token_type: "Bearer",
  expires_in: 900,
  refresh_expires_in: 604800,
  mfa_requerido: false,
};

const mockCadsusResponse: VerificarOtpResponse = {
  access_token: "mock-cadsus-token-xyz",
  role: "PACIENTE",
  paciente_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
  expires_in: 900,
};

describe("Tripartite Authentication Integration Tests (CADSUS, Doctor, Manager, MFA)", () => {
  beforeEach(() => {
    server.use(
      http.post("*/api/v1/auth/patient/cadsus", () => {
        return HttpResponse.json(mockCadsusResponse);
      }),
      http.post("*/api/v1/auth/login", () => {
        return HttpResponse.json(mockTokenResponse);
      }),
      http.post("*/api/v1/auth/mfa/verify", () => {
        return HttpResponse.json(mockTokenResponse);
      }),
    );
  });

  it("IT-AUTH-01: TripartiteAuthCard renderiza o seletor tripartito de perfis e permite alternar abas", async () => {
    const handlePatient = vi.fn();
    const handleDoctor = vi.fn();
    const handleManager = vi.fn();

    renderWithProviders(
      <TripartiteAuthCard
        onPatientAuthenticated={handlePatient}
        onDoctorAuthenticated={handleDoctor}
        onManagerAuthenticated={handleManager}
      />,
    );

    const tablist = screen.getByRole("tablist", { name: /seleção de perfil de acesso sus/i });
    expect(tablist).toBeInTheDocument();

    const tabCidadao = screen.getByRole("tab", { name: /cidadão/i });
    const tabMedico = screen.getByRole("tab", { name: /médico/i });
    const tabGestor = screen.getByRole("tab", { name: /gestor/i });

    expect(tabCidadao).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { name: /acesso cidadão sus/i })).toBeInTheDocument();

    const user = userEvent.setup();

    // Alterna para Médico
    await user.click(tabMedico);
    expect(tabMedico).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { name: /acesso à estação médica/i })).toBeInTheDocument();

    // Alterna para Gestor
    await user.click(tabGestor);
    expect(tabGestor).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { name: /regulação municipal/i })).toBeInTheDocument();
  });

  it("IT-AUTH-02: Suporta navegação por teclado (ArrowRight / ArrowLeft) no tablist de perfis", async () => {
    renderWithProviders(
      <TripartiteAuthCard
        onPatientAuthenticated={vi.fn()}
        onDoctorAuthenticated={vi.fn()}
        onManagerAuthenticated={vi.fn()}
      />,
    );

    const tabCidadao = screen.getByRole("tab", { name: /cidadão/i });
    tabCidadao.focus();

    const user = userEvent.setup();
    await user.keyboard("{ArrowRight}");

    expect(screen.getByRole("tab", { name: /médico/i })).toHaveAttribute("aria-selected", "true");

    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: /gestor/i })).toHaveAttribute("aria-selected", "true");
  });

  it("IT-AUTH-03: CadsusLoginForm valida formulário e aciona post_auth_paciente_cadsus com sucesso", async () => {
    const handleSuccess = vi.fn();
    renderWithProviders(<CadsusLoginForm onSuccess={handleSuccess} />);

    expect(screen.getByRole("heading", { name: /acesso cidadão sus/i })).toBeInTheDocument();

    const user = userEvent.setup();

    // Preenche CPF válido (algoritmicamente válido), Data de Nascimento e Nome da Mãe
    // CPF de teste gerado valido: 52998224725
    await user.type(screen.getByLabelText(/cpf do paciente/i), "52998224725");
    await user.type(screen.getByLabelText(/data de nascimento/i), "1985-05-15");
    await user.type(screen.getByLabelText(/nome completo da mãe/i), "Maria Conceição Silva");

    await user.click(screen.getByRole("button", { name: /acessar atendimento/i }));

    await waitFor(() => {
      expect(handleSuccess).toHaveBeenCalledWith(mockCadsusResponse);
    });
  });

  it("IT-AUTH-04: CadsusLoginForm bloqueia CPF inválido com mensagem de validação", async () => {
    const handleSuccess = vi.fn();
    renderWithProviders(<CadsusLoginForm onSuccess={handleSuccess} />);

    const user = userEvent.setup();

    // CPF inválido (todos dígitos iguais)
    await user.type(screen.getByLabelText(/cpf do paciente/i), "11111111111");
    await user.type(screen.getByLabelText(/data de nascimento/i), "1990-01-01");
    await user.type(screen.getByLabelText(/nome completo da mãe/i), "Mãe Teste");

    await user.click(screen.getByRole("button", { name: /acessar atendimento/i }));

    expect(screen.getByText(/cpf inválido/i)).toBeInTheDocument();
    expect(handleSuccess).not.toHaveBeenCalled();
  });

  it("IT-AUTH-05: DoctorLoginForm autentica médico com sucesso ou aciona desafio MFA TOTP", async () => {
    const handleSuccess = vi.fn();

    // Cenário 1: Login com MFA requerido
    server.use(
      http.post("*/api/v1/auth/login", () => {
        return HttpResponse.json({
          ...mockTokenResponse,
          mfa_requerido: true,
          access_token: "temp-mfa-token-jwt",
        });
      }),
    );

    renderWithProviders(<DoctorLoginForm onLoginSuccess={handleSuccess} />);

    const user = userEvent.setup();

    // Usa botão de demo para preencher
    await user.click(screen.getByRole("button", { name: /preencher credenciais demo/i }));

    // Deve abrir o modal de desafio MFA TOTP
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /mfa.*totp/i })).toBeInTheDocument();
    });

    // Insere código de 6 dígitos
    const inputTotp = screen.getByLabelText(/código de verificação/i);
    await user.type(inputTotp, "123456");

    await user.click(screen.getByRole("button", { name: /confirmar e acessar/i }));

    await waitFor(() => {
      expect(handleSuccess).toHaveBeenCalledWith(
        expect.objectContaining({
          medicoNome: "Dr. Eduardo Rocha",
          crmUf: "123456/SP",
        }),
      );
      expect(getAccessToken()).toBe("mock-access-token-xyz");
    });
  });

  it("IT-AUTH-06: ManagerLoginForm autentica gestor da regulação municipal", async () => {
    const handleSuccess = vi.fn();
    renderWithProviders(<ManagerLoginForm onLoginSuccess={handleSuccess} />);

    expect(screen.getByRole("heading", { name: /regulação municipal/i })).toBeInTheDocument();

    const user = userEvent.setup();
    await user.type(
      screen.getByLabelText(/e-mail institucional/i),
      "gestor.regulacao@saude.gov.br",
    );
    await user.type(screen.getByLabelText(/senha/i), "Gestor@123456");

    await user.click(screen.getByRole("button", { name: /acessar painel da regulação/i }));

    await waitFor(() => {
      expect(handleSuccess).toHaveBeenCalledWith(
        expect.objectContaining({
          nome: "Gestor da Regulação Municipal",
          email: "gestor.regulacao@saude.gov.br",
          papel: "GESTOR",
        }),
      );
    });
  });
});
