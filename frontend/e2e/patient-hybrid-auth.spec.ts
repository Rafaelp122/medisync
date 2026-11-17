import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const MOCK_PACIENTE_ID = "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c";

test.describe("IAM Híbrido do Cidadão — /entrar e /cadastro (E2E)", () => {
  test.beforeEach(async ({ page }) => {
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
        body: JSON.stringify([]),
      });
    });
  });

  test("E2E-HYBRID-01: Passo 1 (CPF/e-mail) -> Passo 2A (OTP SMS) -> /home", async ({ page }) => {
    let identifiedPayload: Record<string, unknown> | null = null;

    await page.route("**/api/v1/auth/patient/identify", async (route) => {
      identifiedPayload = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          possui_conta: true,
          metodos_disponiveis: ["otp", "senha", "passkey"],
          telefone_mascarado: "(11) 9****-4321",
          govbr_habilitado: false,
        }),
      });
    });

    await page.route("**/api/v1/auth/patient/otp/request", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          mensagem: "Código enviado com sucesso.",
          expira_em_segundos: 300,
          codigo_debug: "654321",
        }),
      });
    });

    await page.route("**/api/v1/auth/patient/otp/verify", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          access_token: "fake-jwt-hybrid-otp-e2e",
          token_type: "bearer",
          expires_in: 3600,
          paciente_id: MOCK_PACIENTE_ID,
          role: "PACIENTE",
          atendimento_id: null,
        }),
      });
    });

    await page.goto("/entrar");

    await page.getByLabel(/cpf ou e-mail/i).fill("52998224725");
    await page.getByRole("button", { name: /continuar/i }).click();

    await expect(page.getByText("(11) 9****-4321")).toBeVisible();
    expect(identifiedPayload).toEqual({ identificador: "52998224725" });

    await page.getByLabel(/confirme seu celular para receber o código sms/i).fill("11987654321");
    await page.getByRole("button", { name: /receber código de 6 dígitos por sms/i }).click();

    const otpInput = page.getByLabel(/código sms de 6 dígitos/i);
    await expect(otpInput).toBeVisible();
    await otpInput.fill("654321");
    await page.getByRole("button", { name: /confirmar e entrar/i }).click();

    await expect(page).toHaveURL(/\/home$/);
    await expect(
      page.getByRole("heading", { level: 1, name: /serviços de saúde digital/i }),
    ).toBeVisible();

    const session = await page.evaluate(() =>
      JSON.parse(localStorage.getItem("medisync_session") ?? "{}"),
    );
    expect(session.token).toBe("fake-jwt-hybrid-otp-e2e");
    expect(session.pacienteId).toBe(MOCK_PACIENTE_ID);
  });

  test("E2E-HYBRID-02: Passo 1 (e-mail) -> Fallback Passo 2B (Entrar com senha) -> /home", async ({
    page,
  }) => {
    let loginPasswordPayload: Record<string, unknown> | null = null;

    await page.route("**/api/v1/auth/patient/identify", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          possui_conta: true,
          metodos_disponiveis: ["otp", "senha"],
          telefone_mascarado: "(21) 9****-8877",
          govbr_habilitado: false,
        }),
      });
    });

    await page.route("**/api/v1/auth/patient/login-password", async (route) => {
      loginPasswordPayload = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          access_token: "fake-jwt-hybrid-password-e2e",
          token_type: "bearer",
          expires_in: 3600,
          paciente_id: MOCK_PACIENTE_ID,
          role: "PACIENTE",
          atendimento_id: null,
        }),
      });
    });

    await page.goto("/entrar");

    await page.getByLabel(/cpf ou e-mail/i).fill("Maria@Exemplo.COM");
    await page.getByRole("button", { name: /continuar/i }).click();

    await page
      .getByRole("button", { name: /não tem acesso ao celular agora\? entrar com senha/i })
      .click();

    await page.getByLabel(/senha de acesso/i).fill("SenhaForte@2026");
    await page.getByRole("button", { name: /entrar com senha/i }).click();

    await expect(page).toHaveURL(/\/home$/);
    expect(loginPasswordPayload).toEqual({
      identificador: "maria@exemplo.com",
      senha: "SenhaForte@2026",
    });

    const session = await page.evaluate(() =>
      JSON.parse(localStorage.getItem("medisync_session") ?? "{}"),
    );
    expect(session.token).toBe("fake-jwt-hybrid-password-e2e");
  });

  test("E2E-HYBRID-03: Cadastro em /cadastro -> registro + OTP inicial -> /home e WCAG 2.1 AA", async ({
    page,
  }) => {
    let registerPayload: Record<string, unknown> | null = null;

    await page.route("**/api/v1/auth/patient/register", async (route) => {
      registerPayload = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          paciente_id: MOCK_PACIENTE_ID,
          telefone_mascarado: "(11) 9****-4321",
          otp_enviado: true,
          expira_em_segundos: 300,
          codigo_debug: "123456",
        }),
      });
    });

    await page.route("**/api/v1/auth/patient/otp/verify", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          access_token: "fake-jwt-cadastro-otp-e2e",
          token_type: "bearer",
          expires_in: 3600,
          paciente_id: MOCK_PACIENTE_ID,
          role: "PACIENTE",
          atendimento_id: null,
        }),
      });
    });

    await page.goto("/cadastro");

    const cadastroAxe = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(cadastroAxe.violations).toEqual([]);

    await page.getByLabel(/^cpf/i).fill("52998224725");
    await page.getByLabel(/nome completo/i).fill("Ana Paula Ferreira");
    await page.getByLabel(/data de nascimento/i).fill("1992-07-14");
    await page.getByLabel(/telefone celular/i).fill("11987654321");
    await page.getByLabel(/^e-mail/i).fill("ana.paula@exemplo.com");
    await page.getByLabel(/senha alternativa/i).fill("SenhaSegura@2026");
    await page.getByLabel(/política de privacidade/i).check();

    await page.getByRole("button", { name: /criar conta e receber código sms/i }).click();

    await expect(page.getByText(/cadastro realizado!/i)).toBeVisible();
    await expect(page.getByText("123456")).toBeVisible();
    expect(registerPayload).toMatchObject({
      cpf: "52998224725",
      nome_completo: "Ana Paula Ferreira",
      telefone: "+5511987654321",
      email: "ana.paula@exemplo.com",
      aceite_privacidade: true,
    });

    await page.getByLabel(/código sms \(6 dígitos\)/i).fill("123456");
    await page.getByRole("button", { name: /confirmar e acessar/i }).click();

    await expect(page).toHaveURL(/\/home$/);
    await expect(
      page.getByRole("heading", { level: 1, name: /serviços de saúde digital/i }),
    ).toBeVisible();

    const session = await page.evaluate(() =>
      JSON.parse(localStorage.getItem("medisync_session") ?? "{}"),
    );
    expect(session.token).toBe("fake-jwt-cadastro-otp-e2e");
  });

  test("E2E-HYBRID-04: Identificador sem cadastro (possui_conta: false) direciona para /cadastro", async ({
    page,
  }) => {
    await page.route("**/api/v1/auth/patient/identify", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          possui_conta: false,
          metodos_disponiveis: [],
          telefone_mascarado: null,
          govbr_habilitado: false,
        }),
      });
    });

    await page.goto("/entrar");
    await page.getByLabel(/cpf ou e-mail/i).fill("cidadao.novo@exemplo.com");
    await page.getByRole("button", { name: /continuar/i }).click();

    await expect(page.getByText(/primeiro acesso no medisync\?/i)).toBeVisible();
    await page.getByRole("button", { name: /criar minha conta/i }).click();

    await expect(page).toHaveURL(/\/cadastro$/);
    await expect(page.getByText(/cadastro do cidadão/i)).toBeVisible();
  });
});
