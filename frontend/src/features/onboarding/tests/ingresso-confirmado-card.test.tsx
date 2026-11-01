import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { StoredPatientSession } from "@/lib/session-storage";
import { IngressoConfirmadoCard } from "../components/ingresso-confirmado-card";

describe("IngressoConfirmadoCard (Card Canônico de Sessão Ativa)", () => {
  const sessionAdmissao: StoredPatientSession = {
    token: "jwt-token-123",
    pacienteId: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
    role: "PACIENTE",
    tipo: "acolhimento",
    atendimentoId: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2d",
    prioridadeClinica: 3,
    status: "TRIADO_AGUARDANDO_ELEGIBILIDADE",
  };

  const sessionOtp: StoredPatientSession = {
    token: "jwt-token-otp",
    pacienteId: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
    role: "PACIENTE",
    tipo: "otp",
  };

  it("deve renderizar os detalhes completos de atendimento admitido na fila", () => {
    render(<IngressoConfirmadoCard session={sessionAdmissao} />);

    expect(screen.getByRole("heading", { name: /ingresso confirmado!/i })).toBeInTheDocument();
    expect(
      screen.getByText(/você já está posicionado na fila virtual de espera/i),
    ).toBeInTheDocument();
    expect(screen.getByText("018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2d")).toBeInTheDocument();
    expect(screen.getByText(/nível 3 \(acr\)/i)).toBeInTheDocument();
    expect(screen.getByText("TRIADO_AGUARDANDO_ELEGIBILIDADE")).toBeInTheDocument();
  });

  it("deve renderizar adequadamente a sessão autenticada via OTP sem atendimento ativo (Acesso Autorizado)", () => {
    render(<IngressoConfirmadoCard session={sessionOtp} />);

    expect(screen.getByRole("heading", { name: /acesso autorizado/i })).toBeInTheDocument();
    expect(
      screen.getByText(/sua sessão de paciente está autenticada na plataforma/i),
    ).toBeInTheDocument();
    expect(screen.getByText("018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c")).toBeInTheDocument();
    expect(screen.getByText(/autenticado na plataforma/i)).toBeInTheDocument();
    expect(
      screen.getByText(/você não possui atendimento em andamento no momento/i),
    ).toBeInTheDocument();
  });

  it("deve chamar onEncerrarSessao ao clicar no botão de encerramento", async () => {
    const handleEncerrar = vi.fn();
    const user = userEvent.setup();

    render(<IngressoConfirmadoCard session={sessionAdmissao} onEncerrarSessao={handleEncerrar} />);

    const btnEncerrar = screen.getByRole("button", {
      name: /encerrar sessão \/ novo atendimento/i,
    });
    expect(btnEncerrar).toBeInTheDocument();

    await user.click(btnEncerrar);
    expect(handleEncerrar).toHaveBeenCalledTimes(1);
  });
});
