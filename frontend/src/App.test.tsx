import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http, ws } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "./App";
import {
  getStoredSession,
  MEDISYNC_SESSION_KEY,
  type StoredPatientSession,
  saveStoredSession,
} from "./lib/session-storage";
import { server } from "./mocks/server";

const queueWs = ws.link(/.*\/ws\/queue\/.*/);

describe("App (Orquestração de Sessão, Persistência e Abas)", () => {
  beforeEach(() => {
    localStorage.clear();
    server.use(
      queueWs.addEventListener("connection", ({ client }) => {
        client.send(JSON.stringify({ event: "CONNECTED" }));
      }),
      http.get("*/api/v1/fila/posicao/:atendimentoId", () => {
        return HttpResponse.json(
          {
            atendimento_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2d",
            status: "TRIADO_AGUARDANDO_ELEGIBILIDADE",
            posicao: 2,
            total_aguardando: 3,
            tempo_estimado_segundos: 600,
          },
          { status: 200 },
        );
      }),
    );
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

  it("IT-APP-02: Restaura automaticamente a sessão salva com atendimentoId e exibe a Sala de Espera Virtual", () => {
    saveStoredSession(mockSession);

    render(<App />);

    // Abas de seleção de modo DEVEM ser ocultadas
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();

    // Sala de Espera Virtual DEVE estar visível com dados da fila
    expect(screen.getByRole("heading", { name: /sala de espera virtual/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /sua posição na fila/i })).toBeInTheDocument();
    expect(screen.getByText(/laranja: muito urgente/i)).toBeInTheDocument();
  });

  it("IT-APP-03: Botão 'Desistir do atendimento' cancela a fila e permite voltar ao início", async () => {
    server.use(
      http.post("*/api/v1/fila/cancelar/:atendimentoId", () => {
        return HttpResponse.json(
          {
            atendimento_id: mockSession.atendimentoId,
            status: "CANCELADO",
            cancelado_em: new Date().toISOString(),
            motivo: "Desistência voluntária pelo paciente",
          },
          { status: 200 },
        );
      }),
    );

    saveStoredSession(mockSession);
    const user = userEvent.setup();

    render(<App />);

    const btnDesistir = screen.getByRole("button", {
      name: /desistir do atendimento/i,
    });
    await user.click(btnDesistir);

    const btnConfirmar = screen.getByRole("button", {
      name: /confirmar desistência/i,
    });
    await user.click(btnConfirmar);

    // Card de cancelamento exibido com botão para voltar
    const btnVoltar = await screen.findByRole("button", {
      name: /voltar ao início/i,
    });
    await user.click(btnVoltar);

    // Storage limpo
    expect(getStoredSession()).toBeNull();
    expect(localStorage.getItem(MEDISYNC_SESSION_KEY)).toBeNull();

    // Abas reexibidas
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

  it("IT-APP-05: Abre e fecha o formulário de complementação cadastral sem perder a sala de espera", async () => {
    saveStoredSession(mockSession);
    const user = userEvent.setup();

    render(<App />);

    expect(screen.getByRole("heading", { name: /sala de espera virtual/i })).toBeInTheDocument();

    const btnComplementar = screen.getByRole("button", { name: /completar cadastro/i });
    await user.click(btnComplementar);

    // Modal de complementação abre com formulário da Fase 2
    expect(
      screen.getByRole("heading", { name: /completar prontuário regulatório/i }),
    ).toBeInTheDocument();

    // Clica em "Completar mais tarde" para fechar
    const btnPular = screen.getByRole("button", { name: /completar mais tarde/i });
    await user.click(btnPular);

    // Modal fecha e sala de espera continua ativa
    await waitFor(() => {
      expect(
        screen.queryByRole("heading", { name: /completar prontuário regulatório/i }),
      ).not.toBeInTheDocument();
    });
    expect(screen.getByRole("heading", { name: /sala de espera virtual/i })).toBeInTheDocument();
  });

  it("IT-APP-06: Alternar para aba 'Estação Médica' exibe login e permite autenticar", async () => {
    const user = userEvent.setup();
    render(<App />);

    const tabMedico = screen.getByRole("tab", { name: /estação médica/i });
    expect(tabMedico).toBeInTheDocument();

    await user.click(tabMedico);

    // Deve exibir o card de login do médico
    expect(screen.getByRole("heading", { name: /acesso à estação médica/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /entrar no plantão/i })).toBeInTheDocument();

    // Clica para autenticar
    await user.click(screen.getByRole("button", { name: /entrar no plantão/i }));

    // Deve transicionar para a estação clínica e ocultar as abas de navegação
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /chamar próximo paciente/i })).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: /dr\. eduardo rocha/i })).toBeInTheDocument();
      expect(screen.getByText(/nenhum atendimento clínico ativo/i)).toBeInTheDocument();
      expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    });

    // Ao sair do plantão, as abas devem ser restauradas
    const btnSair = screen.getByRole("button", { name: /sair do plantão/i });
    await user.click(btnSair);

    await waitFor(() => {
      expect(screen.getByRole("tablist")).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: /acesso à estação médica/i })).toBeInTheDocument();
    });
  });
});
