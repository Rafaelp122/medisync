import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { handleListarEspecialidadesApiV1SchedulingEspecialidadesGet } from "@/api/generated/msw.gen";
import { CitizenHomePage } from "@/features/citizen/pages/citizen-home-page";
import {
  MOCK_CITIZEN_ACTIVE_SESSION,
  MOCK_CITIZEN_SESSION,
  renderCitizenRoute,
} from "@/features/citizen/tests/test-router-helper";
import { getStoredSession, saveStoredSession } from "@/lib/session-storage";
import { server } from "@/mocks/server";

describe("CitizenHomePage & CitizenShellLayout (/home)", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    server.use(
      handleListarEspecialidadesApiV1SchedulingEspecialidadesGet({
        body: [
          {
            codigo: "PSICOLOGIA",
            nome: "Psicologia",
            descricao: "Apoio psicológico clínico agendado via SUS.",
            duracao_padrao_minutos: 50,
          },
          {
            codigo: "NUTRICAO",
            nome: "Nutrição",
            descricao: "Orientação nutricional individualizada eMulti.",
            duracao_padrao_minutos: 30,
          },
        ],
      }),
    );
  });

  it("renderiza navegação do portal sem links para /login ou /interno/login e oculta Fila Atual sem atendimentoId", async () => {
    saveStoredSession(MOCK_CITIZEN_SESSION);
    const { container } = renderCitizenRoute(
      <CitizenHomePage session={MOCK_CITIZEN_SESSION} />,
      "/home",
    );

    expect(
      await screen.findByRole("heading", { level: 1, name: /serviços de saúde digital/i }),
    ).toBeInTheDocument();

    const desktopNav = screen.getByRole("navigation", { name: /navegação do portal do cidadão/i });
    expect(within(desktopNav).getByRole("link", { name: /início \/ serviços/i })).toHaveAttribute(
      "href",
      "/home",
    );
    expect(within(desktopNav).getByRole("link", { name: /agendar consulta/i })).toHaveAttribute(
      "href",
      "/agendar",
    );
    expect(within(desktopNav).getByRole("link", { name: /histórico/i })).toHaveAttribute(
      "href",
      "/historico",
    );
    expect(
      within(desktopNav).getByRole("link", { name: /receitas e documentos/i }),
    ).toHaveAttribute("href", "/receitas");
    expect(within(desktopNav).getByRole("link", { name: /perfil e dependentes/i })).toHaveAttribute(
      "href",
      "/perfil",
    );

    expect(within(desktopNav).queryByRole("link", { name: /fila atual/i })).not.toBeInTheDocument();

    const allHrefs = Array.from(container.querySelectorAll("a")).map(
      (a) => a.getAttribute("href") ?? "",
    );
    expect(allHrefs.some((href) => href.includes("/login"))).toBe(false);
    expect(allHrefs.some((href) => href.includes("/interno/login"))).toBe(false);
  });

  it("exibe banner de atendimento ativo e link destacado para Fila Atual quando atendimentoId existir", async () => {
    saveStoredSession(MOCK_CITIZEN_ACTIVE_SESSION);
    renderCitizenRoute(<CitizenHomePage session={MOCK_CITIZEN_ACTIVE_SESSION} />, "/home");

    expect(
      await screen.findByText(/você possui um atendimento ativo na fila virtual/i),
    ).toBeInTheDocument();

    const desktopNav = screen.getByRole("navigation", { name: /navegação do portal do cidadão/i });
    const filaNavLink = within(desktopNav).getByRole("link", { name: /fila atual/i });
    expect(filaNavLink).toHaveAttribute("href", "/fila");

    expect(screen.getByRole("link", { name: /ir para fila atual/i })).toHaveAttribute(
      "href",
      "/fila",
    );
  });

  it("apresenta orientações de PA Digital (/triagem), especialidades eMulti da API (/agendar) e Acesso Rápido", async () => {
    renderCitizenRoute(<CitizenHomePage session={MOCK_CITIZEN_SESSION} />, "/home");

    expect(
      await screen.findByRole("heading", { name: /pronto-atendimento digital \(casos leves\)/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /iniciar triagem rápida/i })).toHaveAttribute(
      "href",
      "/triagem",
    );

    expect(await screen.findByText("Psicologia")).toBeInTheDocument();
    expect(screen.getByText("Nutrição")).toBeInTheDocument();

    const agendarPsico = screen.getByRole("link", { name: /agendar psicologia/i });
    expect(agendarPsico.getAttribute("href")).toContain("/agendar");

    expect(screen.getByRole("link", { name: /histórico de consultas/i })).toHaveAttribute(
      "href",
      "/historico",
    );
    expect(screen.getByRole("link", { name: /minhas receitas/i })).toHaveAttribute(
      "href",
      "/receitas",
    );
  });

  it("botão Sair limpa a sessão persistida, limpa o cache do QueryClient e redireciona para /", async () => {
    saveStoredSession(MOCK_CITIZEN_ACTIVE_SESSION);
    const { history, queryClient } = renderCitizenRoute(
      <CitizenHomePage session={MOCK_CITIZEN_ACTIVE_SESSION} />,
      "/home",
    );
    const user = userEvent.setup();

    await screen.findByText("Psicologia");
    queryClient.setQueryData(["citizen", "sensitive-cache"], { segredo: true });
    expect(queryClient.getQueryCache().getAll().length).toBeGreaterThan(0);

    const logoutButtons = await screen.findAllByRole("button", { name: /^sair$/i });
    await user.click(logoutButtons[0]);

    await waitFor(() => {
      expect(getStoredSession()).toBeNull();
      expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
      expect(history.location.pathname).toBe("/");
    });
  });
});
