import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const INITIAL_PATIENT_SESSION = {
  tipo: "otp",
  role: "PACIENTE",
  pacienteId: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
  token: "fake-jwt-citizen-token-e2e",
};

const VALID_THREE_PART_JWT = "fake-header.fake-payload.fake-signature";

test.describe("Acolhimento Rápido, TCLE e Salvaguarda SAMU 192 (E2E)", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript((sessionData) => {
      if (!window.localStorage.getItem("medisync_session")) {
        window.localStorage.setItem("medisync_session", JSON.stringify(sessionData));
      }
    }, INITIAL_PATIENT_SESSION);

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

    // Intercepta rotas do backend e ViaCEP com contratos OpenAPI vigentes
    await page.route("**/api/v1/onboarding/fase-1", async (route) => {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          paciente_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
          token: "fake-jwt-intake-token-e2e",
          status: "APTO_PARA_CHAMADA",
          mensagem: "Acolhimento registrado com sucesso.",
          is_novo_paciente: true,
        }),
      });
    });

    await page.route("**/api/v1/fila/admissao", async (route) => {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          atendimento_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
          triagem_id: "018f3a5b-1111-4b2c-8b2c-018f3a5b7b2c",
          paciente_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
          status_atendimento: "APTO_PARA_CHAMADA",
          prioridade_clinica: 3,
          alerta_samu_disparado: false,
          instrucoes: null,
          tcle_hash: "a".repeat(64),
        }),
      });
    });

    await page.route("**/api/v1/onboarding/fase-2", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          paciente_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
          nome_completo: "Juliana Silva",
          nome_social: null,
          nome_mae: "Maria Silva",
          sexo_biologico: "F",
          cep: "01310100",
          logradouro: "Avenida Paulista",
          numero: "1000",
          bairro: "Bela Vista",
          cidade: "São Paulo",
          estado: "SP",
          alergias: [],
          status: "CADASTRO_COMPLETO",
        }),
      });
    });

    await page.route("https://viacep.com.br/ws/**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          cep: "01310-100",
          logradouro: "Avenida Paulista",
          complemento: "lado ímpar",
          bairro: "Bela Vista",
          localidade: "São Paulo",
          uf: "SP",
          ibge: "3550308",
        }),
      });
    });

    await page.route("**/api/v1/fila/posicao/*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          atendimento_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
          status: "APTO_PARA_CHAMADA",
          posicao: 2,
          total_aguardando: 8,
          tempo_estimado_segundos: 600,
          prioridade_clinica: 3,
          chamada_iniciada_em: null,
          ttl_segundos: null,
        }),
      });
    });

    await page.route("**/api/v1/fila/cancelar/*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          atendimento_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
          status: "CANCELADO_PACIENTE",
          cancelado_em: new Date().toISOString(),
          motivo: "Desistência voluntária pelo paciente",
        }),
      });
    });
  });

  test("E2E-ONB-01: Jornada Completa de Onboarding (Fase 1 -> Admissão -> Fase 2)", async ({
    page,
  }) => {
    await page.goto("/triagem");

    // 1. Fase 1: Identificação Rápida (Etapa 1)
    await expect(page.getByRole("heading", { name: /pronto atendimento virtual/i })).toBeVisible();

    await page.getByLabel(/nome completo/i).fill("Juliana Silva");
    await page.getByLabel(/documento de identificação \(cpf\)/i).fill("52998224725");
    await page.getByLabel(/telefone celular/i).fill("11987654321");
    await page.getByLabel(/data de nascimento/i).fill("1990-05-15");

    // Avançar para Triagem Clínica (Etapa 2)
    await page.getByRole("button", { name: /continuar para triagem/i }).click();

    // 2. Fase 1: Triagem Clínica & TCLE (Etapa 2)
    await page.getByLabel(/queixa principal/i).fill("Cefaleia moderada e febre baixa há 2 dias");

    // Selecionar sintoma e nível de dor
    await page.getByRole("button", { name: /^dor de cabeça$/i }).click();
    await page.getByRole("radio", { name: /^nível 4$/i }).click();

    // Visualizar TCLE em modal
    await page.getByRole("button", { name: /termo de consentimento livre e esclarecido/i }).click();
    await expect(page.getByRole("heading", { name: /termo de consentimento/i })).toBeVisible();
    await page.getByRole("button", { name: /entendido e ciente/i }).click();

    // Aceitar TCLE
    await page.getByLabel(/concordo com o termo de consentimento/i).check();

    // Submeter Fase 1
    await page.getByRole("button", { name: /entrar na fila virtual/i }).click();

    // 3. Transição para Fase 2 (Enriquecimento Regulatório CFM 1.821/2007)
    await expect(
      page.getByRole("heading", { name: /completar prontuário regulatório/i }),
    ).toBeVisible();

    // Preencher dados da Fase 2 (validando <fieldset>/<legend> WCAG de Sexo Biológico)
    const sexoGroup = page.getByRole("group", { name: /sexo biológico/i });
    await expect(sexoGroup).toBeVisible();
    await expect(sexoGroup.evaluate((el) => el.tagName)).resolves.toBe("FIELDSET");
    await sexoGroup.getByRole("radio", { name: /feminino/i }).check();

    await page.getByLabel(/nome completo da mãe/i).fill("Maria Silva");
    await page.getByLabel(/cep/i).fill("01310100");

    // Validação de autopreenchimento assíncrono via ViaCEP
    await expect(page.getByLabel(/logradouro/i)).toHaveValue("Avenida Paulista");
    await expect(page.getByLabel(/cidade/i)).toHaveValue("São Paulo");
    await expect(page.getByLabel(/^uf$/i)).toHaveValue("SP");

    await page.getByLabel(/número/i).fill("1000");

    // Submeter Fase 2
    await page.getByRole("button", { name: /concluir enriquecimento/i }).click();

    // 4. Redirecionamento automático para /fila e exibição da Sala de Espera Virtual
    await expect(page).toHaveURL(/\/fila/);
    await expect(page.getByRole("heading", { name: /sala de espera virtual/i })).toBeVisible();
    await expect(page.getByTestId("atendimento-id-completo")).toHaveText(
      "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
    );

    // 5. Persistência de Sessão e Recarga (Issue #113)
    const rawSession = await page.evaluate(() => localStorage.getItem("medisync_session"));
    expect(rawSession).not.toBeNull();
    const parsed = JSON.parse(rawSession ?? "{}");
    expect(parsed.atendimentoId).toBe("018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c");
    expect(parsed.token).toBe("fake-jwt-intake-token-e2e");

    // Recarregar a página (F5)
    await page.reload();

    // Deve restaurar automaticamente na Sala de Espera Virtual sem voltar ao início
    await expect(page).toHaveURL(/\/fila/);
    await expect(page.getByRole("heading", { name: /sala de espera virtual/i })).toBeVisible();

    // 6. Desistência Voluntária e Limpeza de Storage
    await page.getByRole("button", { name: /desistir do atendimento/i }).click();
    await page.getByRole("button", { name: /confirmar desistência/i }).click();
    await expect(page.getByText(/atendimento cancelado/i)).toBeVisible();
    await page.getByRole("button", { name: /voltar ao início/i }).click();
    await expect(page).toHaveURL(/\/home$/);
    const updatedSession = await page.evaluate(() => localStorage.getItem("medisync_session"));
    expect(updatedSession).not.toBeNull();
    const parsedAfterCancel = JSON.parse(updatedSession ?? "{}");
    expect(parsedAfterCancel.token).toBe("fake-jwt-intake-token-e2e");
    expect(parsedAfterCancel.atendimentoId).toBeUndefined();
  });

  test("E2E-ONB-02: Salvaguarda SAMU 192 imediata e recuperação por engano (Red Flag RN04)", async ({
    page,
  }) => {
    await page.goto("/triagem");

    // Preencher Identificação e Avançar para Triagem
    await page.getByLabel(/nome completo/i).fill("Juliana Silva");
    await page.getByLabel(/documento de identificação \(cpf\)/i).fill("52998224725");
    await page.getByLabel(/telefone celular/i).fill("11987654321");
    await page.getByLabel(/data de nascimento/i).fill("1990-05-15");
    await page.getByRole("button", { name: /continuar para triagem/i }).click();

    // Seleciona um sintoma de alarme crítico
    await page.getByRole("button", { name: /dor no peito irradiando para o braço/i }).click();

    // Deve abrir imediatamente o modal SAMU 192 (role=alertdialog)
    const modal = page.getByRole("alertdialog");
    await expect(modal).toBeVisible();
    await expect(
      modal.getByRole("heading", { name: /emergência médica detectada/i }),
    ).toBeVisible();

    // Deve conter botão com link de discagem rápida tel:192
    const ligarSamu = modal.getByRole("link", { name: /ligar para o samu 192/i });
    await expect(ligarSamu).toBeVisible();
    await expect(ligarSamu).toHaveAttribute("href", "tel:192");

    // Recuperação de erro humano: clicar em "Selecionei por engano"
    const btnCorrigir = modal.getByRole("button", { name: /selecionei por engano/i });
    await expect(btnCorrigir).toBeVisible();
    await btnCorrigir.click();

    // Modal deve fechar e manter o usuário no formulário
    await expect(modal).not.toBeVisible();
    await expect(page.getByLabel(/queixa principal/i)).toBeVisible();
  });

  test("E2E-ONB-03: Salvaguarda SAMU 192 ao receber HTTP 422 EMERGENCIA_CRITICA_SAMU_192", async ({
    page,
  }) => {
    // Simula backend retornando 422 de emergência médica em /fila/admissao
    await page.route("**/api/v1/fila/admissao", async (route) => {
      await route.fulfill({
        status: 422,
        contentType: "application/json",
        body: JSON.stringify({
          type: "urn:medisync:error:emergencia-critica-samu-192",
          title: "Emergência Médica Detectada",
          status: 422,
          detail:
            "Sintomas relatados indicam potencial risco de morte imediato. Acione o SAMU 192 ou dirija-se à UPA mais próxima.",
          code: "EMERGENCIA_CRITICA_SAMU_192",
        }),
      });
    });

    await page.goto("/triagem");

    await page.getByLabel(/nome completo/i).fill("Juliana Silva");
    await page.getByLabel(/documento de identificação \(cpf\)/i).fill("52998224725");
    await page.getByLabel(/telefone celular/i).fill("11987654321");
    await page.getByLabel(/data de nascimento/i).fill("1990-05-15");
    await page.getByRole("button", { name: /continuar para triagem/i }).click();

    await page.getByLabel(/queixa principal/i).fill("Falta de ar aguda progressiva");

    await page.getByRole("button", { name: /^tosse$/i }).click();
    await page.getByLabel(/concordo com o termo de consentimento/i).check();

    await page.getByRole("button", { name: /entrar na fila virtual/i }).click();

    // Modal deve ser exibido com a mensagem de emergência retornada pelo backend
    const modal = page.getByRole("alertdialog");
    await expect(modal).toBeVisible();
    await expect(modal.getByText(/potencial risco de morte imediato/i)).toBeVisible();
    await expect(modal.getByRole("button", { name: /selecionei por engano/i })).not.toBeVisible();
  });

  test("E2E-ONB-04: Cidadão autenticado com JWT 3-partes em /triagem pula Fase 1 e preserva JWT até /fila", async ({
    page,
  }) => {
    let fase1Called = false;
    let capturedAuthHeader: string | null = null;

    await page.addInitScript(
      (sessionData) => {
        window.localStorage.setItem("medisync_session", JSON.stringify(sessionData));
      },
      {
        tipo: "otp",
        role: "PACIENTE",
        pacienteId: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
        token: VALID_THREE_PART_JWT,
      },
    );

    await page.route("**/api/v1/onboarding/fase-1", async (route) => {
      fase1Called = true;
      await route.fulfill({ status: 500, body: "{}" });
    });

    await page.route("**/api/v1/fila/admissao", async (route) => {
      capturedAuthHeader = route.request().headers().authorization ?? null;
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          atendimento_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
          triagem_id: "018f3a5b-1111-4b2c-8b2c-018f3a5b7b2c",
          paciente_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
          status_atendimento: "APTO_PARA_CHAMADA",
          prioridade_clinica: 3,
          alerta_samu_disparado: false,
          instrucoes: null,
          tcle_hash: "a".repeat(64),
        }),
      });
    });

    await page.goto("/triagem");

    // Não deve exibir identificação civil nem acionar /onboarding/fase-1
    await expect(page.getByLabel(/o que você está sentindo\?/i)).toBeVisible();
    await expect(page.getByLabel(/nome completo/i)).toHaveCount(0);

    await page.getByLabel(/o que você está sentindo\?/i).fill("Dor abdominal leve sem febre");
    await page.getByLabel(/concordo com o termo de consentimento/i).check();
    await page.getByRole("button", { name: /entrar na fila virtual/i }).click();

    await expect(
      page.getByRole("heading", { name: /completar prontuário regulatório/i }),
    ).toBeVisible();
    expect(fase1Called).toBe(false);
    expect(capturedAuthHeader).toBe(`Bearer ${VALID_THREE_PART_JWT}`);

    await page.getByRole("button", { name: /completar mais tarde/i }).click();
    await expect(page).toHaveURL(/\/fila$/);

    const sessionAfter = await page.evaluate(() =>
      JSON.parse(window.localStorage.getItem("medisync_session") ?? "{}"),
    );
    expect(sessionAfter.token).toBe(VALID_THREE_PART_JWT);
    expect(sessionAfter.token.split(".")).toHaveLength(3);
  });

  test("E2E-A11Y-01: Auditoria de Acessibilidade WCAG 2.1 AA nas Etapas 1, 2 e Fase 2 do Onboarding", async ({
    page,
  }) => {
    await page.goto("/triagem");

    // Etapa 1: Identificação
    const step1Scan = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(step1Scan.violations, "Violações WCAG na Etapa 1").toEqual([]);

    await page.getByLabel(/nome completo/i).fill("Juliana Silva");
    await page.getByLabel(/documento de identificação \(cpf\)/i).fill("52998224725");
    await page.getByLabel(/telefone celular/i).fill("11987654321");
    await page.getByLabel(/data de nascimento/i).fill("1990-05-15");
    await page.getByRole("button", { name: /continuar para triagem/i }).click();

    // Etapa 2: Triagem Clínica & TCLE
    await expect(page.getByLabel(/queixa principal/i)).toBeVisible();
    const step2Scan = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(step2Scan.violations, "Violações WCAG na Etapa 2").toEqual([]);

    await page.getByLabel(/queixa principal/i).fill("Cefaleia moderada");
    await page.getByLabel(/concordo com o termo de consentimento/i).check();
    await page.getByRole("button", { name: /entrar na fila virtual/i }).click();

    // Fase 2: Enriquecimento Regulatório (<fieldset>/<legend> de Sexo Biológico)
    await expect(
      page.getByRole("heading", { name: /completar prontuário regulatório/i }),
    ).toBeVisible();
    const fase2Scan = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(fase2Scan.violations, "Violações WCAG na Fase 2").toEqual([]);
  });

  test("E2E-A11Y-02: Respeito estrito a prefers-reduced-motion", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/triagem");

    const button = page.getByRole("button", { name: /continuar para triagem/i });
    const duration = await button.evaluate((el) => {
      return window.getComputedStyle(el).getPropertyValue("transition-duration");
    });

    const durationSeconds = Number.parseFloat(duration) * (duration.endsWith("ms") ? 0.001 : 1);
    expect(durationSeconds).toBeLessThanOrEqual(0.001);
  });
});
