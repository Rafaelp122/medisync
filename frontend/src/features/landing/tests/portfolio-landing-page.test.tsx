import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { AUTHOR_PROFILE, OTHER_PROJECTS } from "@/features/landing/data/portfolio-content";
import { PortfolioLandingPage } from "@/features/landing/pages/portfolio-landing-page";

function renderLandingPage(initialPath = "/") {
  const testRootRoute = createRootRoute({
    component: () => <Outlet />,
  });

  const indexRoute = createRoute({
    getParentRoute: () => testRootRoute,
    path: "/",
    component: PortfolioLandingPage,
  });

  const homeRoute = createRoute({
    getParentRoute: () => testRootRoute,
    path: "/home",
    component: () => <div>Portal do Cidadão Mock</div>,
  });

  const entrarRoute = createRoute({
    getParentRoute: () => testRootRoute,
    path: "/entrar",
    component: () => <div>Entrar Mock</div>,
  });

  const cadastroRoute = createRoute({
    getParentRoute: () => testRootRoute,
    path: "/cadastro",
    component: () => <div>Cadastro Mock</div>,
  });

  const validarRoute = createRoute({
    getParentRoute: () => testRootRoute,
    path: "/validar",
    component: () => <div>Validar Receita Mock</div>,
  });

  const testRouteTree = testRootRoute.addChildren([
    indexRoute,
    homeRoute,
    entrarRoute,
    cadastroRoute,
    validarRoute,
  ]);

  const history = createMemoryHistory({ initialEntries: [initialPath] });
  const testRouter = createRouter({
    routeTree: testRouteTree,
    history,
  });

  const rendered = render(<RouterProvider router={testRouter as never} />);
  return { ...rendered, history, testRouter };
}

describe("PortfolioLandingPage (Landing Page Editorial / Portfólio em /)", () => {
  it("renderiza os headings principais, layout público acessível e seção Hero", async () => {
    renderLandingPage();

    const h1 = await screen.findByRole("heading", {
      level: 1,
      name: /pronto-atendimento digital para casos leves & atenção multiprofissional/i,
    });
    expect(h1).toBeInTheDocument();

    expect(document.getElementById("main-content")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: /navegação pública/i })).toBeInTheDocument();
    expect(screen.getByText(/fichas verdes e azuis/i)).toBeInTheDocument();
  });

  it("exibe links de navegação pública para /home, /cadastro, /entrar, /validar e âncoras", async () => {
    renderLandingPage();

    const headerCta = await screen.findByRole("link", { name: /^acessar portal$/i });
    expect(headerCta).toHaveAttribute("href", "/home");

    const heroPortalLinks = screen.getAllByRole("link", { name: /acessar portal do cidadão/i });
    expect(heroPortalLinks.length).toBeGreaterThanOrEqual(1);
    for (const link of heroPortalLinks) {
      expect(link).toHaveAttribute("href", "/home");
    }

    const cadastroLinks = screen.getAllByRole("link", { name: /criar conta/i });
    expect(cadastroLinks.length).toBeGreaterThanOrEqual(1);
    for (const link of cadastroLinks) {
      expect(link).toHaveAttribute("href", "/cadastro");
    }

    const validarLinks = screen.getAllByRole("link", { name: /validar receita/i });
    expect(validarLinks.length).toBeGreaterThanOrEqual(1);
    for (const link of validarLinks) {
      expect(link).toHaveAttribute("href", "/validar");
    }

    const entrarLink = screen.getByRole("link", { name: /já possui cadastro\? entrar/i });
    expect(entrarLink).toHaveAttribute("href", "/entrar");

    expect(screen.getByRole("link", { name: /^arquitetura$/i })).toHaveAttribute(
      "href",
      "#arquitetura",
    );
    expect(screen.getByRole("link", { name: /^sobre$/i })).toHaveAttribute("href", "#sobre");
    expect(screen.getByRole("link", { name: /^projetos$/i })).toHaveAttribute("href", "#projetos");
  });

  it("apresenta os diferenciais reais de engenharia na vitrine de arquitetura", async () => {
    renderLandingPage();

    expect(
      await screen.findByRole("heading", { level: 2, name: /diferenciais reais de engenharia/i }),
    ).toBeInTheDocument();

    expect(
      screen.getByRole("heading", { level: 3, name: /fastapi \+ granian/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 3, name: /hexagonal pragmático \+ tach/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 3, name: /valkey 8\.0 zset \+ scripts lua/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 3, name: /rbac estrito & anti-idor por titularidade/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 3, name: /livekit sfu webrtc/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        level: 3,
        name: /icp-brasil pades & cfm nº 2\.314\/2022 \+ lgpd/i,
      }),
    ).toBeInTheDocument();
  });

  it("exibe as seções editáveis 'Sobre Mim' e 'Outros Projetos' e rodapé com licença e disclaimer", async () => {
    renderLandingPage();

    expect(
      await screen.findByRole("heading", { level: 2, name: /^sobre mim$/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 3, name: AUTHOR_PROFILE.name }),
    ).toBeInTheDocument();

    expect(
      screen.getByRole("heading", { level: 2, name: /^outros projetos$/i }),
    ).toBeInTheDocument();
    for (const project of OTHER_PROJECTS) {
      expect(screen.getByRole("heading", { level: 3, name: project.name })).toBeInTheDocument();
    }

    expect(screen.getAllByText(/mit \/ apache 2\.0/i).length).toBeGreaterThanOrEqual(1);
    expect(
      screen.getByText(/não constitui dispositivo médico homologado pela anvisa/i),
    ).toBeInTheDocument();
  });

  it("não expõe nenhum link ou menção para /login ou /interno/login", async () => {
    const { container } = renderLandingPage();

    await screen.findByRole("heading", { level: 1 });

    const allLinks = Array.from(container.querySelectorAll("a"));
    const hrefs = allLinks.map((anchor) => anchor.getAttribute("href") ?? "");

    expect(hrefs.some((href) => href.includes("/login"))).toBe(false);
    expect(hrefs.some((href) => href.includes("/interno/login"))).toBe(false);

    const bodyText = document.body.textContent ?? "";
    expect(bodyText).not.toMatch(/\/interno\/login/i);
    expect(bodyText).not.toMatch(/\/login\b/i);
  });

  it("navega via TanStack Router ao clicar em 'Validar Receita'", async () => {
    const { history } = renderLandingPage();
    const user = userEvent.setup();

    const validarLinks = await screen.findAllByRole("link", { name: /validar receita/i });
    await user.click(validarLinks[0]);

    await waitFor(() => {
      expect(history.location.pathname).toBe("/validar");
      expect(screen.getByText("Validar Receita Mock")).toBeInTheDocument();
    });
  });
});
