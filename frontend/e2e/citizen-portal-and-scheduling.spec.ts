import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

const MOCK_PACIENTE_ID = "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c";
const MOCK_PROFISSIONAL_ID = "018f3a5b-7b2c-4b2c-8b2c-018f3a5b4444";
const MOCK_AGENDAMENTO_ID = "018f3a5b-aaaa-4bbb-8ccc-018f3a5b5555";

const MOCK_CITIZEN_SESSION = {
  tipo: "otp" as const,
  role: "PACIENTE",
  pacienteId: MOCK_PACIENTE_ID,
  token: "fake-citizen-jwt-e2e",
};

const MOCK_ESPECIALIDADES = [
  {
    codigo: "PSICOLOGIA",
    nome: "Psicologia",
    descricao: "Acompanhamento psicológico agendado com profissionais da equipe eMulti.",
    duracao_padrao_minutos: 45,
  },
  {
    codigo: "NUTRICAO",
    nome: "Nutrição",
    descricao: "Orientação nutricional e cuidado alimentar multiprofissional agendado.",
    duracao_padrao_minutos: 30,
  },
];

function buildTomorrowIsoRange() {
  const tomorrow = new Date(Date.now() + 86_400_000).toISOString().slice(0, 10);
  return {
    slotInicio: `${tomorrow}T14:00:00Z`,
    slotFim: `${tomorrow}T14:45:00Z`,
  };
}

async function setupCitizenApiMocks(page: Page) {
  const { slotInicio, slotFim } = buildTomorrowIsoRange();
  let agendamentosState: Array<Record<string, unknown>> = [];
  const dependentesState: Array<Record<string, unknown>> = [];

  await page.route("**/api/v1/auth/patient/methods", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        govbr_oidc_enabled: false,
        passkeys_enabled: true,
        otp_enabled: true,
        password_fallback_enabled: true,
      }),
    });
  });

  await page.route("**/api/v1/scheduling/especialidades", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_ESPECIALIDADES),
    });
  });

  await page.route("**/api/v1/scheduling/slots*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          profissional_id: MOCK_PROFISSIONAL_ID,
          especialidade: "PSICOLOGIA",
          slot_inicio: slotInicio,
          slot_fim: slotFim,
          duracao_minutos: 45,
        },
      ]),
    });
  });

  await page.route("**/api/v1/scheduling/agendamentos/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(agendamentosState),
    });
  });

  await page.route("**/api/v1/scheduling/agendamentos", async (route) => {
    if (route.request().method() === "POST") {
      const reqBody = route.request().postDataJSON() as Record<string, unknown>;
      const novo = {
        id: MOCK_AGENDAMENTO_ID,
        paciente_id: MOCK_PACIENTE_ID,
        profissional_id: reqBody.profissional_id ?? MOCK_PROFISSIONAL_ID,
        especialidade: reqBody.especialidade ?? "PSICOLOGIA",
        slot_inicio: reqBody.slot_inicio ?? slotInicio,
        slot_fim: reqBody.slot_fim ?? slotFim,
        status: "AGENDADO",
        observacoes: reqBody.observacoes ?? null,
        atendimento_id: null,
        criado_em: "2026-11-16T10:00:00Z",
        atualizado_em: "2026-11-16T10:00:00Z",
      };
      agendamentosState = [novo];
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(novo),
      });
      return;
    }
    await route.continue();
  });

  await page.route("**/api/v1/scheduling/agendamentos/*/cancelar", async (route) => {
    agendamentosState = agendamentosState.map((item) => ({
      ...item,
      status: "CANCELADO",
    }));
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(agendamentosState[0]),
    });
  });

  await page.route("**/api/v1/consultations/me/historico", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          atendimento_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b8888",
          status: "FINALIZADO",
          prioridade_clinica: 4,
          queixa_principal: "Dor de garganta leve e coriza",
          criado_em: "2026-11-10T14:00:00Z",
          finalizado_em: "2026-11-10T14:20:00Z",
          medico_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2e",
          diagnostico_cid10: "J06.9",
          conduta_resumo: "Hidratação oral e sintomáticos por 5 dias.",
        },
      ]),
    });
  });

  await page.route("**/api/v1/consultations/me/documentos", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          documento_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7777",
          atendimento_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b8888",
          tipo_documento: "RECEITA_SIMPLES",
          status_assinatura: "ASSINADO",
          token_validacao: "ITI-MEDISYNC-998877",
          criado_em: "2026-11-10T14:15:00Z",
          assinado_em: "2026-11-10T14:18:00Z",
        },
      ]),
    });
  });

  await page.route("**/api/v1/pacientes/*/dependentes", async (route) => {
    if (route.request().method() === "POST") {
      const reqBody = route.request().postDataJSON() as Record<string, unknown>;
      const criado = {
        id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b6666",
        titular_id: MOCK_PACIENTE_ID,
        dependente_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b6667",
        grau_parentesco: reqBody.grau_parentesco ?? "FILHO",
        nome_completo: reqBody.nome_completo ?? "Lucas Oliveira Silva",
        data_nascimento: reqBody.data_nascimento ?? "2018-04-10",
        cpf: reqBody.cpf ?? null,
        cns: reqBody.cns ?? null,
        vinculado_em: "2026-11-16T10:05:00Z",
      };
      dependentesState.push(criado);
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(criado),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(dependentesState),
    });
  });

  await page.route("**/api/v1/documents/validate/ITI-MEDISYNC-998877", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        documento_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7777",
        tipo_documento: "RECEITA_SIMPLES",
        status_documento: "ASSINADO",
        sha256_hash: "a".repeat(64),
        assinado_em: "2026-11-10T14:18:00Z",
        emissor_medico_nome: "Dr. Eduardo Rocha",
        emissor_medico_crm: "123456",
        emissor_medico_uf: "SP",
        organizacao_nome: "UBS Centro Digital",
        paciente_nome_mascarado: "M*** S***",
        paciente_cpf_mascarado: "***.998.224-**",
        assinatura_digital_valida: true,
        conformidade_icp_brasil: true,
        itens: [
          {
            medicamento: "Paracetamol",
            dosagem: "500 mg",
            posologia: "1 comprimido a cada 8 horas se dor ou febre",
            duracao: "5 dias",
            controle_especial: false,
          },
        ],
      }),
    });
  });
}

test.describe("Portal do Cidadão, Agendamento eMulti, Validação Pública e WCAG 2.1 AA", () => {
  test("E2E-CITIZEN-01: Guard fechado redireciona rotas protegidas sem sessão para /entrar", async ({
    page,
  }) => {
    await setupCitizenApiMocks(page);

    const protectedRoutes = ["/home", "/historico", "/receitas", "/perfil", "/agendar"];
    for (const routePath of protectedRoutes) {
      await page.goto(routePath);
      await expect(page).toHaveURL(/\/entrar$/);
      await expect(page.getByRole("heading", { name: /entrar no medisync/i })).toBeVisible();
    }
  });

  test("E2E-CITIZEN-02: Navegação completa pela sidebar (/home -> /agendar -> /historico -> /receitas -> /perfil) e /validar/$token público", async ({
    page,
    browser,
  }) => {
    await setupCitizenApiMocks(page);
    await page.addInitScript((sessionData) => {
      if (!window.localStorage.getItem("medisync_session")) {
        window.localStorage.setItem("medisync_session", JSON.stringify(sessionData));
      }
    }, MOCK_CITIZEN_SESSION);

    await page.goto("/home");
    await expect(
      page.getByRole("heading", { level: 1, name: /serviços de saúde digital/i }),
    ).toBeVisible();

    const sidebarNav = page.getByRole("navigation", {
      name: /navegação do portal do cidadão/i,
    });

    // 1. Navegar para /agendar pela sidebar e agendar + cancelar PSICOLOGIA
    await sidebarNav.getByRole("link", { name: /agendar consulta/i }).click();
    await expect(page).toHaveURL(/\/agendar$/);
    await expect(page.getByRole("heading", { level: 1, name: /agendar consulta/i })).toBeVisible();

    await page.getByRole("button", { name: /psicologia/i }).click();
    const slotButton = page.getByRole("button", { name: /das 14:00 às 14:45/i });
    await expect(slotButton).toBeVisible();
    await slotButton.click();

    await page
      .getByLabel(/observações ou motivo da consulta/i)
      .fill("Acompanhamento psicológico inicial");
    await page.getByRole("button", { name: /confirmar agendamento/i }).click();

    await expect(page.getByText(/agendamento confirmado/i)).toBeVisible();
    const cancelBtn = page.getByRole("button", { name: /cancelar agendamento/i });
    await expect(cancelBtn).toBeVisible();

    await cancelBtn.click();
    await expect(page.getByText(/^cancelado$/i)).toBeVisible();

    // 2. Navegar para /historico pela sidebar
    await sidebarNav.getByRole("link", { name: /^histórico$/i }).click();
    await expect(page).toHaveURL(/\/historico$/);
    await expect(
      page.getByRole("heading", { level: 1, name: /histórico de consultas/i }),
    ).toBeVisible();
    await expect(page.getByText(/CID-10: J06\.9/i)).toBeVisible();
    await expect(page.getByText(/hidratação oral e sintomáticos/i)).toBeVisible();

    // 3. Navegar para /receitas pela sidebar
    await sidebarNav.getByRole("link", { name: /receitas e documentos/i }).click();
    await expect(page).toHaveURL(/\/receitas$/);
    await expect(
      page.getByRole("heading", { level: 1, name: /receitas e documentos/i }),
    ).toBeVisible();
    await expect(page.getByText("ITI-MEDISYNC-998877")).toBeVisible();

    // 4. Navegar para /perfil pela sidebar e cadastrar dependente
    await sidebarNav.getByRole("link", { name: /perfil e dependentes/i }).click();
    await expect(page).toHaveURL(/\/perfil$/);
    await expect(
      page.getByRole("heading", { level: 1, name: /perfil e dependentes/i }),
    ).toBeVisible();

    const depSection = page.getByRole("region", { name: /meus dependentes/i });
    await depSection.getByLabel(/nome completo do dependente/i).fill("Lucas Oliveira Silva");
    await depSection.getByLabel(/grau de parentesco/i).selectOption("FILHO");
    await depSection.getByLabel(/data de nascimento/i).fill("2018-04-10");
    await depSection.getByRole("button", { name: /cadastrar dependente/i }).click();

    await expect(
      depSection.getByText(/dependente cadastrado e vinculado com sucesso/i),
    ).toBeVisible();
    await expect(depSection.getByText("Lucas Oliveira Silva")).toBeVisible();

    // 5. Validar rota pública /validar/$token em contexto limpo (sem sessão)
    const publicContext = await browser.newContext();
    try {
      const publicPage = await publicContext.newPage();
      await setupCitizenApiMocks(publicPage);
      await publicPage.goto("/validar/ITI-MEDISYNC-998877");

      await expect(publicPage).toHaveURL(/\/validar\/ITI-MEDISYNC-998877$/);
      await expect(publicPage.getByTestId("validation-result-card")).toBeVisible();
      await expect(publicPage.getByText(/documento clínico autêntico/i)).toBeVisible();
      await expect(publicPage.getByText(/selo icp-brasil \/ iti/i)).toBeVisible();
      await expect(publicPage.getByText("Dr. Eduardo Rocha")).toBeVisible();
      await expect(publicPage.getByText("M*** S***")).toBeVisible();
    } finally {
      await publicContext.close();
    }
  });

  test("E2E-CITIZEN-03: Auditoria WCAG 2.1 AA (/, /entrar, /home, /agendar, /historico, /receitas, /perfil, /validar) e prefers-reduced-motion", async ({
    page,
  }) => {
    test.slow();
    await setupCitizenApiMocks(page);

    // Páginas públicas: /, /entrar, /validar
    for (const publicRoute of ["/", "/entrar", "/validar"]) {
      await page.goto(publicRoute);
      const scan = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      expect(scan.violations, `Violações WCAG em ${publicRoute}`).toEqual([]);
    }

    // Página pública de validação com card de resultado carregado
    await page.goto("/validar/ITI-MEDISYNC-998877");
    await expect(page.getByTestId("validation-result-card")).toBeVisible();
    const validarResultScan = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(validarResultScan.violations, "Violações WCAG em /validar/ITI-MEDISYNC-998877").toEqual(
      [],
    );

    // Verifica prefers-reduced-motion na Landing Page (/)
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    const landingCta = page
      .getByRole("main")
      .getByRole("link", { name: /acessar portal do cidadão/i });
    const landingDuration = await landingCta.evaluate((el) =>
      window.getComputedStyle(el).getPropertyValue("transition-duration"),
    );
    const landingDurationSeconds =
      Number.parseFloat(landingDuration) * (landingDuration.endsWith("ms") ? 0.001 : 1);
    expect(landingDurationSeconds).toBeLessThanOrEqual(0.001);

    // Páginas autenticadas: /home, /agendar, /historico, /receitas, /perfil
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await page.addInitScript((sessionData) => {
      if (!window.localStorage.getItem("medisync_session")) {
        window.localStorage.setItem("medisync_session", JSON.stringify(sessionData));
      }
    }, MOCK_CITIZEN_SESSION);

    const authenticatedRoutes: Array<{ path: string; waitForReady: () => Promise<void> }> = [
      {
        path: "/home",
        waitForReady: async () => {
          await expect(
            page.getByRole("heading", { level: 1, name: /serviços de saúde digital/i }),
          ).toBeVisible();
        },
      },
      {
        path: "/agendar",
        waitForReady: async () => {
          await expect(
            page.getByRole("heading", { level: 1, name: /agendar consulta/i }),
          ).toBeVisible();
        },
      },
      {
        path: "/historico",
        waitForReady: async () => {
          await expect(page.getByText(/CID-10: J06\.9/i)).toBeVisible();
        },
      },
      {
        path: "/receitas",
        waitForReady: async () => {
          await expect(page.getByText("ITI-MEDISYNC-998877")).toBeVisible();
        },
      },
      {
        path: "/perfil",
        waitForReady: async () => {
          await expect(page.getByRole("region", { name: /meus dependentes/i })).toBeVisible();
        },
      },
    ];

    for (const authRoute of authenticatedRoutes) {
      await page.goto(authRoute.path);
      await authRoute.waitForReady();
      const scan = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      expect(scan.violations, `Violações WCAG em ${authRoute.path}`).toEqual([]);
    }

    // Verifica prefers-reduced-motion em /home
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/home");
    const homeLink = page.getByRole("link", { name: /iniciar triagem rápida/i });
    const homeDuration = await homeLink.evaluate((el) =>
      window.getComputedStyle(el).getPropertyValue("transition-duration"),
    );
    const homeDurationSeconds =
      Number.parseFloat(homeDuration) * (homeDuration.endsWith("ms") ? 0.001 : 1);
    expect(homeDurationSeconds).toBeLessThanOrEqual(0.001);
  });
});
