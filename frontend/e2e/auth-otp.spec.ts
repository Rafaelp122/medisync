import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.describe("Autenticação OTP de Paciente (E2E)", () => {
  test.beforeEach(async ({ page }) => {
    // Intercept API routes
    await page.route("**/api/v1/auth/patient/otp/request", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          mensagem: "Código enviado com sucesso.",
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
          access_token: "fake-e2e-jwt-token",
          token_type: "bearer",
          expires_in: 3600,
          paciente_id: "00000000-0000-0000-0000-000000000001",
          role: "PACIENTE",
        }),
      });
    });
  });

  test("E2E-01: Jornada Completa do Paciente com Login OTP", async ({ page }) => {
    await page.goto("/otp");

    // Verify title and prompt
    await expect(page.getByRole("heading", { level: 1, name: /medisync express/i })).toBeVisible();

    // Fill phone number
    const phoneInput = page.getByLabel(/telefone celular/i);
    await phoneInput.fill("11987654321");
    await expect(phoneInput).toHaveValue("(11) 98765-4321");

    // Click submit
    await page.getByRole("button", { name: /receber código/i }).click();

    // Verify transition to OTP code verification
    await expect(page.getByText(/código de 6 dígitos/i)).toBeVisible();

    // Fill OTP digits
    await page.getByLabel("Dígito 1").fill("1");
    await page.getByLabel("Dígito 2").fill("2");
    await page.getByLabel("Dígito 3").fill("3");
    await page.getByLabel("Dígito 4").fill("4");
    await page.getByLabel("Dígito 5").fill("5");
    await page.getByLabel("Dígito 6").fill("6");

    // Submit OTP
    await page.getByRole("button", { name: /confirmar e entrar/i }).click();

    // Verify successful authentication via unified canonical card (Acesso Autorizado sem atendimento em curso)
    await expect(page.getByRole("heading", { name: /acesso autorizado/i })).toBeVisible();
    await expect(page.getByText(/papel:\s*paciente/i)).toBeVisible();

    // Verify localStorage session persistence
    const rawSession = await page.evaluate(() => localStorage.getItem("medisync_session"));
    expect(rawSession).not.toBeNull();
    const parsed = JSON.parse(rawSession ?? "{}");
    expect(parsed.token).toBe("fake-e2e-jwt-token");
    expect(parsed.pacienteId).toBe("00000000-0000-0000-0000-000000000001");

    // Verify that client attaches Authorization Bearer header to network requests
    const tokenHeader = await page.evaluate(async () => {
      const client = (
        window as unknown as { __medisyncClient: { get: (opts: unknown) => Promise<unknown> } }
      ).__medisyncClient;
      let capturedAuth: string | null = null;
      await client.get({
        url: "/api/v1/auth/me",
        fetch: async (req: Request) => {
          capturedAuth = req.headers.get("Authorization");
          return new Response(JSON.stringify({ ok: true }), { status: 200 });
        },
      });
      return capturedAuth;
    });
    expect(tokenHeader).toBe("Bearer fake-e2e-jwt-token");

    // Verify persistence across page reload (F5)
    await page.reload();
    await expect(page.getByRole("heading", { name: /acesso autorizado/i })).toBeVisible();
    await expect(page.getByLabel(/telefone celular/i)).not.toBeVisible();

    // Verify logout / session termination
    await page.getByRole("button", { name: /encerrar sessão \/ novo atendimento/i }).click();
    await expect(page.getByLabel(/telefone celular/i)).toBeVisible();
    const clearedSession = await page.evaluate(() => localStorage.getItem("medisync_session"));
    expect(clearedSession).toBeNull();
  });

  test("E2E-02: Auditoria de Acessibilidade WCAG 2.1 AA", async ({ page }) => {
    await page.goto("/otp");

    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();

    expect(accessibilityScanResults.violations).toEqual([]);
  });

  test("E2E-03: Respeito estrito a prefers-reduced-motion", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/otp");

    const button = page.getByRole("button", { name: /receber código/i });
    const duration = await button.evaluate((el) => {
      return window.getComputedStyle(el).getPropertyValue("transition-duration");
    });

    // In CSS we set transition-duration: 0.01ms !important under prefers-reduced-motion
    const durationSeconds = Number.parseFloat(duration) * (duration.endsWith("ms") ? 0.001 : 1);
    expect(durationSeconds).toBeLessThanOrEqual(0.001);
  });

  test("E2E-04: Passkeys WebAuthn — Cadastro em /fila e Login em 1 Toque em /otp (US-14)", async ({
    page,
    context,
  }, testInfo) => {
    const rawBaseUrl = testInfo.project.use.baseURL || "http://127.0.0.1:5183";
    const originUrl = new URL(rawBaseUrl);
    const localhostOrigin = `http://localhost:${originUrl.port}`;

    const cdp = await context.newCDPSession(page);
    await cdp.send("WebAuthn.enable");
    const { authenticatorId } = await cdp.send("WebAuthn.addVirtualAuthenticator", {
      options: {
        protocol: "ctap2",
        transport: "internal",
        hasResidentKey: true,
        hasUserVerification: true,
        isUserVerified: true,
        automaticPresenceSimulation: true,
      },
    });

    try {
      let registeredCredentialId = "";

      await page.route("**/api/v1/fila/posicao/*", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            atendimento_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b99",
            posicao: 2,
            total_aguardando: 4,
            tempo_estimado_segundos: 300,
            prioridade_clinica: 3,
            status: "AGUARDANDO_CHAMADA",
            protocolo: "MED-2026-0099",
          }),
        });
      });

      await page.route("**/api/v1/auth/patient/webauthn/register/options", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            challenge: "dGVzdC1yZWdpc3Rlci1jaGFsbGVuZ2UtdXMxNC0wMDE",
            rp: { name: "MediSync Express", id: "localhost" },
            user: {
              id: "MDE4ZjNhNWItN2IyYy00YjJjLThiMmMtMDE4ZjNhNWI3YjJj",
              name: "Maria Silva",
              displayName: "Maria Silva",
            },
            pubKeyCredParams: [{ alg: -7, type: "public-key" }],
            timeout: 60000,
            attestation: "none",
          }),
        });
      });

      await page.route("**/api/v1/auth/patient/webauthn/register/verify", async (route) => {
        const payload = JSON.parse(route.request().postData() || "{}") as { id?: string };
        registeredCredentialId = payload.id || "";
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            status: "registrado",
            credencial_id: registeredCredentialId,
          }),
        });
      });

      await page.goto(localhostOrigin);
      await page.evaluate(() => {
        localStorage.setItem(
          "medisync_session",
          JSON.stringify({
            tipo: "acolhimento",
            role: "PACIENTE",
            pacienteId: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
            atendimentoId: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b99",
            prioridadeClinica: 3,
            protocolo: "MED-2026-0099",
            nomePaciente: "Maria Silva",
            token: "fake-intake-token-us14",
          }),
        );
      });

      await page.goto(`${localhostOrigin}/fila`);
      await page.getByRole("button", { name: /ativar biometria deste aparelho/i }).click();
      await expect(page.getByText(/biometria ativada com sucesso neste aparelho/i)).toBeVisible();
      expect(registeredCredentialId.length).toBeGreaterThan(0);

      // Agora testa Login em 1 Toque em /otp usando a credencial virtual recém-registrada
      await page.route("**/api/v1/auth/patient/webauthn/authenticate/options", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            challenge: "dGVzdC1hdXRoLWNoYWxsZW5nZS11czE0LTAwMg",
            rpId: "localhost",
            allowCredentials: [{ id: registeredCredentialId, type: "public-key" }],
            timeout: 60000,
            userVerification: "preferred",
          }),
        });
      });

      await page.route("**/api/v1/auth/patient/webauthn/authenticate/verify", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            access_token: "fake-webauthn-jwt-e2e",
            token_type: "bearer",
            expires_in: 3600,
            paciente_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
            role: "PACIENTE",
            atendimento_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b99",
          }),
        });
      });

      await page.evaluate(() => localStorage.removeItem("medisync_session"));
      await page.goto(`${localhostOrigin}/otp`);
      await page.getByRole("button", { name: /entrar com biometria do aparelho/i }).click();

      await page.waitForURL("**/fila");
      await expect(page.getByRole("heading", { name: /sala de espera virtual/i })).toBeVisible();
      await expect(page.getByText(/2º na fila/i)).toBeVisible();
    } finally {
      await cdp.send("WebAuthn.removeVirtualAuthenticator", { authenticatorId }).catch(() => {});
    }
  });
});
