import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.describe("Acolhimento Rápido, TCLE e Salvaguarda SAMU 192 (E2E)", () => {
  test.beforeEach(async ({ page }) => {
    // Intercepta rotas do backend e ViaCEP
    await page.route("**/api/v1/onboarding/fase-1", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          paciente_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
          token: "fake-jwt-intake-token-e2e",
          status: "TRIADO_AGUARDANDO_ELEGIBILIDADE",
          mensagem: "Acolhimento e triagem realizados com sucesso.",
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
          protocolo: "MED-2026-0001",
          posicao_fila: 3,
          previsao_minutos: 15,
          status: "AGUARDANDO_TRIAGEM",
          prioridade_clinica: 3,
        }),
      });
    });

    await page.route("**/api/v1/onboarding/fase-2", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "CONCLUIDO",
          dados_completos: true,
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
  });

  test("E2E-ONB-01: Jornada Completa de Onboarding (Fase 1 -> Admissão -> Fase 2)", async ({
    page,
  }) => {
    await page.goto("/");

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
    await page.getByRole("button", { name: /^nível 4$/i }).click();

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

    // Preencher dados da Fase 2
    await page.getByLabel(/nome completo da mãe/i).fill("Maria Silva");
    await page.getByLabel(/cep/i).fill("01310100");

    // Validação de autopreenchimento assíncrono via ViaCEP
    await expect(page.getByLabel(/logradouro/i)).toHaveValue("Avenida Paulista");
    await expect(page.getByLabel(/cidade/i)).toHaveValue("São Paulo");
    await expect(page.getByLabel(/^uf$/i)).toHaveValue("SP");

    await page.getByLabel(/número/i).fill("1000");

    // Submeter Fase 2
    await page.getByRole("button", { name: /concluir enriquecimento/i }).click();

    // 4. Conclusão do Wizard
    await expect(page.getByRole("heading", { name: /ingresso confirmado!/i })).toBeVisible();
    await expect(
      page.getByText(/você já está posicionado na fila virtual de espera/i),
    ).toBeVisible();
  });

  test("E2E-ONB-02: Salvaguarda SAMU 192 imediata e recuperação por engano (Red Flag RN04)", async ({
    page,
  }) => {
    await page.goto("/");

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
    // Simula backend retornando 422 de emergência médica
    await page.route("**/api/v1/onboarding/fase-1", async (route) => {
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

    await page.goto("/");

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

  test("E2E-A11Y-01: Auditoria de Acessibilidade WCAG 2.1 AA na tela de Onboarding", async ({
    page,
  }) => {
    await page.goto("/");

    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();

    expect(accessibilityScanResults.violations).toEqual([]);
  });

  test("E2E-A11Y-02: Respeito estrito a prefers-reduced-motion", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");

    const button = page.getByRole("button", { name: /continuar para triagem/i });
    const duration = await button.evaluate((el) => {
      return window.getComputedStyle(el).getPropertyValue("transition-duration");
    });

    const durationSeconds = Number.parseFloat(duration) * (duration.endsWith("ms") ? 0.001 : 1);
    expect(durationSeconds).toBeLessThanOrEqual(0.001);
  });
});
