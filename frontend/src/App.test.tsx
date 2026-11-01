import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "./App";
import {
  getStoredSession,
  MEDISYNC_SESSION_KEY,
  type StoredPatientSession,
  saveStoredSession,
} from "./lib/session-storage";

describe("App (Orquestração de Sessão, Persistência e Abas)", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  const mockSession: StoredPatientSession = {
    token: "mock-jwt-active-session",
    pacienteId: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
    role: "PACIENTE",
    tipo: "acolhimento",
    atendimentoId: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2d",
    prioridadeClinica: 2,
    status: "TRIADO_AGUARDANDO_ELEGIBILIDADE",
  };

  it("IT-APP-01: Montagem inicial sem sessão exibe abas e formulário de acolhimento", () => {
    render(<App />);

    // Abas devem estar visíveis com novas nomenclaturas claras
    const tablist = screen.getByRole("tablist", { name: /opções de atendimento/i });
    expect(tablist).toBeInTheDocument();

    expect(
      screen.getByRole("tab", { name: /novo atendimento \(primeira vez\)/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: /já tenho atendimento \(telefone\)/i }),
    ).toBeInTheDocument();

    // Card de sessão ativa NÃO deve estar presente
    expect(
      screen.queryByRole("heading", { name: /ingresso confirmado!/i }),
    ).not.toBeInTheDocument();
  });

  it("IT-APP-02: Restaura automaticamente a sessão salva no localStorage e oculta abas", () => {
    saveStoredSession(mockSession);

    render(<App />);

    // Abas de seleção de modo DEVEM ser ocultadas
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();

    // Card canônico unificado "Ingresso Confirmado!" DEVE estar visível com dados
    expect(screen.getByRole("heading", { name: /ingresso confirmado!/i })).toBeInTheDocument();
    expect(screen.getByText("018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2d")).toBeInTheDocument();
    expect(screen.getByText(/nível 2 \(acr\)/i)).toBeInTheDocument();
  });

  it("IT-APP-03: Botão 'Encerrar Sessão' limpa o storage e reexibe a interface inicial", async () => {
    saveStoredSession(mockSession);
    const user = userEvent.setup();

    render(<App />);

    const btnEncerrar = screen.getByRole("button", {
      name: /encerrar sessão \/ novo atendimento/i,
    });
    await user.click(btnEncerrar);

    // Storage limpo
    expect(getStoredSession()).toBeNull();
    expect(localStorage.getItem(MEDISYNC_SESSION_KEY)).toBeNull();

    // Card de ingresso confirmado fechado e abas reexibidas
    expect(
      screen.queryByRole("heading", { name: /ingresso confirmado!/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("tablist")).toBeInTheDocument();
  });

  it("IT-APP-04: Autenticação via OTP salva a sessão no localStorage e transiciona para o card unificado", async () => {
    const user = userEvent.setup();
    render(<App />);

    // Alternar para aba OTP
    const tabOtp = screen.getByRole("tab", { name: /já tenho atendimento \(telefone\)/i });
    await user.click(tabOtp);

    // Preencher telefone
    const phoneInput = screen.getByLabelText(/telefone celular/i);
    await user.type(phoneInput, "11987654321");

    // Solicitar código
    const submitBtn = screen.getByRole("button", { name: /receber código/i });
    await user.click(submitBtn);

    // Digitar código nos 6 inputs
    await waitFor(() => {
      expect(screen.getByLabelText("Dígito 1")).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText("Dígito 1"), "1");
    await user.type(screen.getByLabelText("Dígito 2"), "2");
    await user.type(screen.getByLabelText("Dígito 3"), "3");
    await user.type(screen.getByLabelText("Dígito 4"), "4");
    await user.type(screen.getByLabelText("Dígito 5"), "5");
    await user.type(screen.getByLabelText("Dígito 6"), "6");

    // Confirmar e entrar
    const btnConfirmar = screen.getByRole("button", { name: /confirmar e entrar/i });
    await user.click(btnConfirmar);

    // Aguardar transição e salvar storage
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /acesso autorizado/i })).toBeInTheDocument();
    });

    // Abas devem estar ocultadas
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();

    // Storage deve conter a sessão com token normalizado (access_token)
    const stored = getStoredSession();
    expect(stored).not.toBeNull();
    expect(stored?.token).toBe("mock-jwt-token-paciente");
    expect(stored?.tipo).toBe("otp");
    expect(stored?.role).toBe("PACIENTE");
  });
});
