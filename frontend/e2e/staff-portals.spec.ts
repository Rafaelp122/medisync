import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const MOCK_PAINEL_TELEMETRIA = {
  gerado_em: "2026-11-15T12:00:00Z",
  tme_medio_segundos: 450,
  tme_nivel_1_segundos: 60,
  tme_nivel_2_segundos: 300,
  tme_nivel_3_segundos: 600,
  tme_nivel_4_segundos: 1200,
  tme_nivel_5_segundos: 2400,
  tma_medio_segundos: 840,
  medicos_tma: [
    {
      medico_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2e",
      nome: "Dr. Eduardo Rocha",
      total_atendimentos: 12,
      tma_segundos: 820,
    },
  ],
  no_show_rate: 5.0,
  evasao_rate: 2.0,
  sla_compliance_percentual: 98.5,
  sla_em_conformidade: true,
  medicos_ativos_count: 2,
  total_pacientes_fila: 5,
  total_atendimentos: 24,
};

const MOCK_CONFIG_PLANTAO = {
  id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b01",
  medicos_ativos_planejados: 2,
  alpha_backpressure: "1.25",
  cota_diaria_maxima: 300,
  tma_padrao_segundos: 900,
  tempo_tolerancia_ring_segundos: 45,
  modo_operacao: "SUS",
  sla_minutos_nivel_1: 0,
  sla_minutos_nivel_2: 10,
  sla_minutos_nivel_3: 60,
  sla_minutos_nivel_4: 120,
  sla_minutos_nivel_5: 240,
  criado_em: "2026-11-01T00:00:00Z",
  atualizado_em: "2026-11-01T00:00:00Z",
  atualizado_por_id: null,
};

test.describe("Portais Corporativos (/interno/login, /medico e /gestor)", () => {
  test.beforeEach(async ({ page }) => {
    let activeRole: "MEDICO" | "GESTOR_UNIDADE" = "MEDICO";
    let activeIdentificador = "123456/SP";

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

    await page.route("**/api/v1/auth/login", async (route) => {
      const payload = (route.request().postDataJSON() ?? {}) as { identificador?: string };
      if (payload.identificador?.includes("@") && !payload.identificador.includes("eduardo")) {
        activeRole = "GESTOR_UNIDADE";
        activeIdentificador = payload.identificador;
      } else {
        activeRole = "MEDICO";
        activeIdentificador = payload.identificador ?? "123456/SP";
      }

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          access_token: "fake-corporate-jwt-e2e",
          token_type: "bearer",
          expires_in: 3600,
          mfa_requerido: false,
          mfa_setup_requerido: false,
        }),
      });
    });

    await page.route("**/api/v1/auth/me", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          usuario_id:
            activeRole === "MEDICO"
              ? "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2e"
              : "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b99",
          identificador: activeIdentificador,
          papel: activeRole,
          ativo: true,
        }),
      });
    });

    await page.route("**/api/v1/scheduling/agenda/dia*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    await page.route("**/api/v1/telemetria/painel", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_PAINEL_TELEMETRIA),
      });
    });

    await page.route("**/api/v1/telemetria/config-plantao", async (route) => {
      if (route.request().method() === "PUT") {
        const body = (await route.request().postDataJSON()) as Record<string, unknown>;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            ...MOCK_CONFIG_PLANTAO,
            ...body,
          }),
        });
        return;
      }

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_CONFIG_PLANTAO),
      });
    });

    await page.route("**/api/v1/ambulatory/producao?*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [
            {
              atendimento_id: "018f3a5b-0000-7000-8000-000000000099",
              cnes: "2269988",
              codigo_sigtap: "03.01.01.025-0",
              carater_atendimento: "02",
              consolidado_em: "2026-11-15T12:00:00Z",
            },
          ],
          total: 1,
          competencia: "202611",
          page: 1,
          size: 50,
        }),
      });
    });

    await page.route("**/api/v1/ambulatory/producao/exportar?*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "text/plain; charset=utf-8",
        headers: {
          "Content-Disposition": 'attachment; filename="BPA_I_202611_2269988.txt"',
        },
        body: "01#BPA#202611000001\n0322699882026110301010250",
      });
    });
  });

  test("E2E-STAFF-01: Autentica médico em /interno/login, redireciona para /medico e valida WCAG 2.1 AA", async ({
    page,
  }) => {
    await page.goto("/interno/login");

    const loginAxe = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(loginAxe.violations).toEqual([]);

    await page.getByRole("tab", { name: /médico/i }).click();
    await page.getByLabel(/^crm:/i).fill("123456");
    await page.getByLabel(/^uf:/i).fill("SP");
    await page.getByLabel(/senha de acesso/i).fill("Medisync@2026");
    await page.getByRole("button", { name: /entrar no plantão/i }).click();

    await expect(page).toHaveURL(/\/medico$/);
    await expect(page.getByRole("button", { name: /chamar próximo paciente/i })).toBeVisible();

    const medicoAxe = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(medicoAxe.violations).toEqual([]);
  });

  test("E2E-STAFF-02: Autentica gestor em /interno/login, opera US-11/US-12 em /gestor e valida WCAG 2.1 AA", async ({
    page,
  }) => {
    await page.goto("/interno/login");

    await page.getByRole("tab", { name: /gestor/i }).click();
    await page.getByLabel(/e-mail institucional/i).fill("gestor@medisync.sus.gov.br");
    await page.getByLabel(/senha institucional/i).fill("Gestor@2026");
    await page.getByRole("button", { name: /acessar painel da unidade/i }).click();

    await expect(page).toHaveURL(/\/gestor$/);
    await expect(page.getByText("Dr. Eduardo Rocha")).toBeVisible();

    // US-12: Atualiza política do plantão
    const medicosInput = page.getByLabel(/médicos ativos planejados/i);
    await expect(medicosInput).toBeVisible();
    await medicosInput.fill("5");
    await page.getByRole("button", { name: /salvar política do plantão/i }).click();
    await expect(page.getByText(/política do plantão atualizada com sucesso/i)).toBeVisible();

    // US-11: Lista e exporta BPA-I (.txt)
    await page.getByLabel(/competência \(yyyymm\)/i).fill("202611");
    await expect(page.getByText("03.01.01.025-0")).toBeVisible();
    await page.getByRole("button", { name: /exportar bpa-i \(\.txt\)/i }).click();
    await expect(page.getByText(/arquivo bpa-i da competência 202611 exportado/i)).toBeVisible();

    const gestorAxe = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(gestorAxe.violations).toEqual([]);
  });

  test("E2E-STAFF-03: Segregação estrita — /, /entrar e /login não expõem acesso médico/gestor", async ({
    page,
  }) => {
    // Landing page pública (/) não possui links nem formulários corporativos
    await page.goto("/");
    await expect(
      page.getByRole("heading", {
        level: 1,
        name: /pronto-atendimento digital para casos leves/i,
      }),
    ).toBeVisible();
    await expect(page.locator('a[href*="/interno/login"], a[href="/login"]')).toHaveCount(0);
    await expect(page.getByRole("tab", { name: /médico|gestor/i })).toHaveCount(0);

    // Portal de entrada do cidadão (/entrar) não expõe login médico ou gestor
    await page.goto("/entrar");
    await expect(page.getByRole("heading", { name: /entrar no medisync/i })).toBeVisible();
    await expect(page.locator('a[href*="/interno/login"], a[href="/login"]')).toHaveCount(0);
    await expect(page.getByRole("tab", { name: /médico|gestor/i })).toHaveCount(0);
    await expect(page.getByText(/acesso à estação médica/i)).toHaveCount(0);

    // Rota legada /login redireciona para / sem expor /interno/login
    await page.goto("/login");
    await expect(page).toHaveURL(/\/$/);
    await expect(page.locator('a[href*="/interno/login"]')).toHaveCount(0);
    await expect(page.getByRole("tab", { name: /médico|gestor/i })).toHaveCount(0);
  });
});
