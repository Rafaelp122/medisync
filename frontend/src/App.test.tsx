import { createMemoryHistory } from "@tanstack/react-router";
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
import { createAppRouter } from "./router";

const queueWs = ws.link(/.*\/ws\/queue\/.*/);

function renderApp(initialEntries: string[] = ["/"]) {
  const history = createMemoryHistory({ initialEntries });
  const router = createAppRouter(history);
  const result = render(<App customRouter={router} />);
  return { ...result, router, history };
}

describe("App (Orquestração de Rotas Declarativas, Persistência e Guards)", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
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

  it("IT-APP-01: Montagem inicial exibe Home com cards assistenciais e link discreto da equipe", async () => {
    renderApp(["/"]);

    expect(
      await screen.findByRole("heading", { name: /pronto atendimento virtual/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /novo atendimento/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /já tenho atendimento/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /área do profissional/i })).toBeInTheDocument();
  });

  it("IT-APP-02: Clique em 'Iniciar Triagem' navega para /triagem", async () => {
    const { history } = renderApp(["/"]);
    const user = userEvent.setup();

    const linkTriagem = await screen.findByRole("link", { name: /iniciar triagem/i });
    await user.click(linkTriagem);

    await waitFor(() => {
      expect(history.location.pathname).toBe("/triagem");
      expect(screen.getByRole("link", { name: /voltar ao início/i })).toBeInTheDocument();
      expect(screen.getByLabelText(/nome completo/i)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /continuar para triagem/i })).toBeInTheDocument();
    });
  });

  it("IT-APP-03: Clique em 'Acompanhar por SMS' navega para /otp", async () => {
    const { history } = renderApp(["/"]);
    const user = userEvent.setup();

    const linkOtp = await screen.findByRole("link", { name: /acompanhar por sms/i });
    await user.click(linkOtp);

    await waitFor(() => {
      expect(history.location.pathname).toBe("/otp");
      expect(screen.getByRole("link", { name: /voltar ao início/i })).toBeInTheDocument();
      expect(screen.getByLabelText(/telefone celular/i)).toBeInTheDocument();
    });
  });

  it("IT-APP-04: Clique em 'Área do Profissional' navega para /login", async () => {
    const { history } = renderApp(["/"]);
    const user = userEvent.setup();

    const linkProfissional = await screen.findByRole("link", { name: /área do profissional/i });
    await user.click(linkProfissional);

    await waitFor(() => {
      expect(history.location.pathname).toBe("/login");
      expect(screen.getByRole("link", { name: /voltar ao início/i })).toBeInTheDocument();
      expect(
        screen.getByRole("tablist", { name: /seleção de perfil de acesso sus/i }),
      ).toBeInTheDocument();
    });
  });

  it("IT-APP-05: Restaura automaticamente a sessão salva com atendimentoId na rota /fila", async () => {
    saveStoredSession(mockSession);

    renderApp(["/fila"]);

    expect(
      await screen.findByRole("heading", { name: /sala de espera virtual/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /sua posição na fila/i })).toBeInTheDocument();
    expect(screen.getByText(/laranja: muito urgente/i)).toBeInTheDocument();
  });

  it("IT-APP-06: Botão 'Desistir do atendimento' na /fila cancela e permite voltar ao início", async () => {
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

    const { history } = renderApp(["/fila"]);

    const btnDesistir = await screen.findByRole("button", {
      name: /desistir do atendimento/i,
    });
    await user.click(btnDesistir);

    const btnConfirmar = screen.getByRole("button", {
      name: /confirmar desistência/i,
    });
    await user.click(btnConfirmar);

    const btnVoltar = await screen.findByRole("button", {
      name: /voltar ao início/i,
    });
    await user.click(btnVoltar);

    expect(getStoredSession()).toBeNull();
    expect(localStorage.getItem(MEDISYNC_SESSION_KEY)).toBeNull();
    await waitFor(() => {
      expect(history.location.pathname).toBe("/");
      expect(
        screen.getByRole("heading", { name: /pronto atendimento virtual/i }),
      ).toBeInTheDocument();
    });
  });

  it("IT-APP-07: Autenticação via OTP em /otp salva sessão e exibe o card de confirmação", async () => {
    const user = userEvent.setup();
    renderApp(["/otp"]);

    const phoneInput = await screen.findByLabelText(/telefone celular/i);
    await user.type(phoneInput, "11987654321");

    const submitBtn = screen.getByRole("button", { name: /receber código/i });
    await user.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByLabelText("Dígito 1")).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText("Dígito 1"), "1");
    await user.type(screen.getByLabelText("Dígito 2"), "2");
    await user.type(screen.getByLabelText("Dígito 3"), "3");
    await user.type(screen.getByLabelText("Dígito 4"), "4");
    await user.type(screen.getByLabelText("Dígito 5"), "5");
    await user.type(screen.getByLabelText("Dígito 6"), "6");

    const btnConfirmar = screen.getByRole("button", { name: /confirmar e entrar/i });
    await user.click(btnConfirmar);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /acesso autorizado/i })).toBeInTheDocument();
    });

    const stored = getStoredSession();
    expect(stored).not.toBeNull();
    expect(stored?.token).toBe("mock-jwt-token-paciente");
    expect(stored?.tipo).toBe("otp");
    expect(stored?.role).toBe("PACIENTE");
  });

  it("IT-APP-08: Login de médico em /login transiciona para /medico e logout retorna para /login", async () => {
    const user = userEvent.setup();
    const { history } = renderApp(["/login"]);

    const tabMedico = await screen.findByRole("tab", { name: /^médico$/i });
    await user.click(tabMedico);

    expect(
      await screen.findByRole("heading", { name: /acesso à estação médica/i }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /entrar no plantão/i }));

    await waitFor(() => {
      expect(history.location.pathname).toBe("/medico");
      expect(screen.getByRole("button", { name: /chamar próximo paciente/i })).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: /dr\. eduardo rocha/i })).toBeInTheDocument();
    });

    const btnSair = screen.getByRole("button", { name: /sair do plantão/i });
    await user.click(btnSair);

    await waitFor(() => {
      expect(history.location.pathname).toBe("/login");
      expect(
        screen.getByRole("tablist", { name: /seleção de perfil de acesso sus/i }),
      ).toBeInTheDocument();
    });
  });

  it("IT-APP-09: Route Guard /fila redireciona para / se não houver sessão ativa de paciente", async () => {
    const { history } = renderApp(["/fila"]);

    expect(
      await screen.findByRole("heading", { name: /pronto atendimento virtual/i }),
    ).toBeInTheDocument();
    expect(history.location.pathname).toBe("/");
    expect(
      screen.queryByRole("heading", { name: /sala de espera virtual/i }),
    ).not.toBeInTheDocument();
  });

  it("IT-APP-10: Route Guard /medico redireciona para /login se não houver sessão de médico", async () => {
    const { history } = renderApp(["/medico"]);

    expect(
      await screen.findByRole("tablist", { name: /seleção de perfil de acesso sus/i }),
    ).toBeInTheDocument();
    expect(history.location.pathname).toBe("/login");
    expect(
      screen.queryByRole("button", { name: /chamar próximo paciente/i }),
    ).not.toBeInTheDocument();
  });

  it("IT-APP-11: Route Guard /gestor redireciona para /login se não houver sessão de gestor", async () => {
    const { history } = renderApp(["/gestor"]);

    expect(
      await screen.findByRole("tablist", { name: /seleção de perfil de acesso sus/i }),
    ).toBeInTheDocument();
    expect(history.location.pathname).toBe("/login");
    expect(screen.queryByText(/visão geral da rede/i)).not.toBeInTheDocument();
  });

  it("IT-APP-12: Route Guard /chamada redireciona para / se não houver sessão nem token LiveKit", async () => {
    const { history } = renderApp(["/chamada"]);

    expect(
      await screen.findByRole("heading", { name: /pronto atendimento virtual/i }),
    ).toBeInTheDocument();
    expect(history.location.pathname).toBe("/");
    expect(screen.queryByText(/conectando à sala de teleconsulta/i)).not.toBeInTheDocument();
  });

  it("IT-APP-13: Route Guard /pos-consulta redireciona para / se não houver atendimento concluído", async () => {
    const { history } = renderApp(["/pos-consulta"]);

    expect(
      await screen.findByRole("heading", { name: /pronto atendimento virtual/i }),
    ).toBeInTheDocument();
    expect(history.location.pathname).toBe("/");
    expect(
      screen.queryByRole("heading", { name: /atendimento finalizado/i }),
    ).not.toBeInTheDocument();
  });

  it("IT-APP-14: Catch-all redireciona rota inexistente deterministicamente para /", async () => {
    const { history } = renderApp(["/rota-inexistente-404"]);

    expect(
      await screen.findByRole("heading", { name: /pronto atendimento virtual/i }),
    ).toBeInTheDocument();
    expect(history.location.pathname).toBe("/");
  });

  it("IT-APP-15: Deep links legados /?mode=otp e /?mode=login redirecionam para /otp e /login", async () => {
    const { history: histOtp } = renderApp(["/?mode=otp"]);
    await waitFor(() => {
      expect(histOtp.location.pathname).toBe("/otp");
    });

    const { history: histLogin } = renderApp(["/?mode=login"]);
    await waitFor(() => {
      expect(histLogin.location.pathname).toBe("/login");
    });
  });

  it("IT-APP-16: Route Guard /triagem redireciona para /fila se paciente já possuir atendimento ativo", async () => {
    saveStoredSession(mockSession);
    const { history } = renderApp(["/triagem"]);

    await waitFor(() => {
      expect(history.location.pathname).toBe("/fila");
    });
    expect(
      await screen.findByRole("heading", { name: /sala de espera virtual/i }),
    ).toBeInTheDocument();
  });

  it("IT-APP-17: Route Guard /otp redireciona para /fila se paciente já possuir atendimento ativo", async () => {
    saveStoredSession(mockSession);
    const { history } = renderApp(["/otp"]);

    await waitFor(() => {
      expect(history.location.pathname).toBe("/fila");
    });
    expect(
      await screen.findByRole("heading", { name: /sala de espera virtual/i }),
    ).toBeInTheDocument();
  });

  it("IT-APP-18: Deep link legado /?mode=gestor redireciona para /login com search param perfil=gestor", async () => {
    const { history, router } = renderApp(["/?mode=gestor"]);
    await waitFor(() => {
      expect(history.location.pathname).toBe("/login");
      expect(history.location.search).toBe("?perfil=gestor");
      expect(router.state.location.search).toEqual({ perfil: "gestor" });
    });
  });
});
