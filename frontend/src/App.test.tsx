import { createMemoryHistory } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http, ws } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import {
  handleGetAuthPatientMethods,
  handleListarAgendaDiaApiV1SchedulingAgendaDiaGet,
  handleListarEspecialidadesApiV1SchedulingEspecialidadesGet,
  handleListarMeusAgendamentosApiV1SchedulingAgendamentosMeGet,
  handleLogoutApiV1AuthLogoutPost,
} from "@/api/generated/msw.gen";
import { App } from "./App";
import {
  getStoredSession,
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

describe("App (Orquestração de Rotas Declarativas, Portal Fechado e Guards)", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    server.use(
      queueWs.addEventListener("connection", ({ client }) => {
        client.send(JSON.stringify({ event: "CONNECTED" }));
      }),
      handleGetAuthPatientMethods({
        body: {
          govbr_oidc_enabled: false,
          passkeys_enabled: true,
          otp_enabled: true,
          password_fallback_enabled: true,
        },
      }),
      handleListarEspecialidadesApiV1SchedulingEspecialidadesGet({
        body: [
          {
            codigo: "PSICOLOGIA",
            nome: "Psicologia",
            descricao: "Acompanhamento psicológico agendado.",
            duracao_padrao_minutos: 50,
          },
        ],
      }),
      handleListarMeusAgendamentosApiV1SchedulingAgendamentosMeGet({
        body: [],
      }),
      handleListarAgendaDiaApiV1SchedulingAgendaDiaGet({
        body: [],
      }),
      handleLogoutApiV1AuthLogoutPost(() => new HttpResponse(null, { status: 204 })),
      http.get("*/api/v1/fila/posicao/:atendimentoId", () => {
        return HttpResponse.json(
          {
            atendimento_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2d",
            status: "APTO_PARA_CHAMADA",
            posicao: 2,
            total_aguardando: 3,
            tempo_estimado_segundos: 600,
          },
          { status: 200 },
        );
      }),
    );
  });

  const basePatientSession: StoredPatientSession = {
    token: "mock-jwt-patient-session",
    pacienteId: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
    role: "PACIENTE",
    tipo: "otp",
  };

  const activeEncounterSession: StoredPatientSession = {
    ...basePatientSession,
    tipo: "acolhimento",
    atendimentoId: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2d",
    prioridadeClinica: 2,
    status: "APTO_PARA_CHAMADA",
  };

  it("IT-APP-01: Raiz '/' renderiza a Landing Page de portfólio sem expor login interno", async () => {
    renderApp(["/"]);

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: /pronto-atendimento digital para casos leves/i,
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /sobre mim/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /outros projetos/i })).toBeInTheDocument();
    expect(screen.queryByText(/área do profissional/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /interno/i })).not.toBeInTheDocument();
  });

  it("IT-APP-02: Portal /home e sub-rotas do cidadão são fechados e redirecionam anônimos para /entrar", async () => {
    for (const protectedPath of [
      "/home",
      "/agendar",
      "/historico",
      "/receitas",
      "/perfil",
      "/triagem",
    ]) {
      const { history, unmount } = renderApp([protectedPath]);
      await waitFor(() => {
        expect(history.location.pathname).toBe("/entrar");
      });
      expect(await screen.findByLabelText(/cpf ou e-mail/i)).toBeInTheDocument();
      unmount();
    }
  });

  it("IT-APP-03: Cidadão autenticado acessa /home com sidebar e navega para /triagem", async () => {
    saveStoredSession(basePatientSession);
    const user = userEvent.setup();
    const { history } = renderApp(["/home"]);

    expect(
      await screen.findByRole("heading", { level: 1, name: /serviços de saúde digital/i }),
    ).toBeInTheDocument();

    const triagemLink = screen.getByRole("link", { name: /iniciar triagem rápida/i });
    await user.click(triagemLink);

    await waitFor(() => {
      expect(history.location.pathname).toBe("/triagem");
      expect(screen.getByLabelText(/nome completo/i)).toBeInTheDocument();
    });
  });

  it("IT-APP-04: Restaura automaticamente sessão com atendimentoId em /fila e volta para /home ao desistir", async () => {
    server.use(
      http.post("*/api/v1/fila/cancelar/:atendimentoId", () => {
        return HttpResponse.json(
          {
            atendimento_id: activeEncounterSession.atendimentoId,
            status: "CANCELADO_PACIENTE",
            cancelado_em: new Date().toISOString(),
            motivo: "Desistência voluntária pelo paciente",
          },
          { status: 200 },
        );
      }),
    );

    saveStoredSession(activeEncounterSession);
    const user = userEvent.setup();
    const { history } = renderApp(["/fila"]);

    expect(
      await screen.findByRole("heading", { name: /sala de espera virtual/i }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /desistir do atendimento/i }));
    await user.click(screen.getByRole("button", { name: /confirmar desistência/i }));
    const btnVoltar = await screen.findByRole("button", { name: /voltar ao início/i });
    await user.click(btnVoltar);

    await waitFor(() => {
      expect(history.location.pathname).toBe("/home");
    });
    expect(getStoredSession()?.token).toBe("mock-jwt-patient-session");
    expect(getStoredSession()?.atendimentoId).toBeUndefined();
  });

  it("IT-APP-05: Login de médico em /interno/login navega para /medico e logout retorna para /interno/login", async () => {
    const user = userEvent.setup();
    const { history } = renderApp(["/interno/login"]);

    expect(screen.queryByRole("tab", { name: /cidadão/i })).not.toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: /acesso à estação médica/i }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /entrar no plantão/i }));

    await waitFor(() => {
      expect(history.location.pathname).toBe("/medico");
      expect(screen.getByRole("button", { name: /chamar próximo paciente/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /sair do plantão/i }));

    await waitFor(() => {
      expect(history.location.pathname).toBe("/interno/login");
    });
  });

  it("IT-APP-06: Route Guards /medico e /gestor redirecionam para /interno/login sem sessão", async () => {
    const { history: histMedico, unmount } = renderApp(["/medico"]);
    await waitFor(() => {
      expect(histMedico.location.pathname).toBe("/interno/login");
    });
    unmount();

    const { history: histGestor } = renderApp(["/gestor"]);
    await waitFor(() => {
      expect(histGestor.location.pathname).toBe("/interno/login");
    });
  });

  it("IT-APP-07: Route Guards /chamada e /pos-consulta redirecionam para /entrar sem sessão", async () => {
    const { history: histChamada, unmount } = renderApp(["/chamada"]);
    await waitFor(() => {
      expect(histChamada.location.pathname).toBe("/entrar");
    });
    unmount();

    const { history: histPos } = renderApp(["/pos-consulta"]);
    await waitFor(() => {
      expect(histPos.location.pathname).toBe("/entrar");
    });
  });

  it("IT-APP-08: Rota pública /validar renderiza consulta de autenticidade de documentos", async () => {
    renderApp(["/validar"]);

    expect(
      await screen.findByRole("heading", { name: /validar receita ou documento clínico/i }),
    ).toBeInTheDocument();
  });

  it("IT-APP-09: Rota legada /login e rotas inexistentes redirecionam para '/' sem vazar /interno/login", async () => {
    const { history: histLegacy, unmount } = renderApp(["/login"]);
    await waitFor(() => {
      expect(histLegacy.location.pathname).toBe("/");
    });
    unmount();

    const { history: histNotFound } = renderApp(["/rota-inexistente-404"]);
    await waitFor(() => {
      expect(histNotFound.location.pathname).toBe("/");
    });
  });

  it("IT-APP-10: Rota legada /otp redireciona para /entrar", async () => {
    const { history } = renderApp(["/otp"]);
    await waitFor(() => {
      expect(history.location.pathname).toBe("/entrar");
    });
  });
});
