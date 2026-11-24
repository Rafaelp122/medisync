import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const MOCK_SESSION = {
  tipo: "acolhimento",
  role: "PACIENTE",
  pacienteId: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
  atendimentoId: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b99",
  prioridadeClinica: 3,
  token: "fake-jwt-queue-token-e2e",
  status: "APTO_PARA_CHAMADA",
};

test.describe("Sala de Espera Virtual, Ring Modal 45s e Acessibilidade (E2E)", () => {
  test.beforeEach(async ({ page }) => {
    let prioridadeAtual = 3;
    let posicaoAtual = 2;

    // Intercepta rotas da fila e consultas com contratos OpenAPI vigentes
    await page.route("**/api/v1/fila/posicao/*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          atendimento_id: MOCK_SESSION.atendimentoId,
          posicao: posicaoAtual,
          total_aguardando: 5,
          tempo_estimado_segundos: 600,
          prioridade_clinica: prioridadeAtual,
          status: "APTO_PARA_CHAMADA",
          chamada_iniciada_em: null,
          ttl_segundos: null,
        }),
      });
    });

    await page.route("**/api/v1/consultations/*/livekit/token", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          token: "fake-livekit-room-token-e2e",
          room_name: `atend_${MOCK_SESSION.atendimentoId}`,
          participant_identity: `paciente_${MOCK_SESSION.pacienteId}`,
          server_url: "wss://livekit.medisync.local",
          expires_in: 3600,
        }),
      });
    });

    await page.route("**/api/v1/fila/piora", async (route) => {
      prioridadeAtual = 2;
      posicaoAtual = 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          atendimento_id: MOCK_SESSION.atendimentoId,
          prioridade_clinica: 2,
          status_atendimento: "APTO_PARA_CHAMADA",
          alerta_samu_disparado: false,
          redirecionado_emergencia: false,
          nova_posicao: 1,
          instrucoes: "Prioridade reclassificada para Muito Urgente (Laranja).",
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

    await page.route("**/api/v1/fila/cancelar/*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          atendimento_id: MOCK_SESSION.atendimentoId,
          status: "CANCELADO_PACIENTE",
          cancelado_em: new Date().toISOString(),
          motivo: "Desistência voluntária pelo paciente",
        }),
      });
    });
  });

  test("E2E-QUEUE-01: Exibição da Sala de Espera Virtual, Posição Ordinal, TMA e Auditoria WCAG 2.1 AA", async ({
    page,
  }) => {
    await page.clock.install();

    await page.addInitScript((sessionData) => {
      window.localStorage.setItem("medisync_session", JSON.stringify(sessionData));
    }, MOCK_SESSION);

    await page.goto("/fila");

    // Valida elementos principais da sala de espera
    await expect(page.getByRole("heading", { name: /sala de espera virtual/i })).toBeVisible();
    await expect(page.getByTestId("atendimento-id-completo")).toHaveText(
      MOCK_SESSION.atendimentoId,
    );
    await expect(page.getByText(/2º na fila/i)).toBeVisible();
    await expect(page.getByText(/aproximadamente 10 minutos/i)).toBeVisible();
    await expect(page.getByText(/amarelo: urgente/i)).toBeVisible();

    // Auditoria automatizada de acessibilidade WCAG 2.1 AA
    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(accessibilityScanResults.violations).toEqual([]);
  });

  test("E2E-QUEUE-02: Convocação Médica com Ring Modal e No-Show após 45s via page.clock", async ({
    page,
  }) => {
    // Sobrescreve rota de posição retornando status de chamada médica
    await page.route("**/api/v1/fila/posicao/*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          atendimento_id: MOCK_SESSION.atendimentoId,
          posicao: 1,
          total_aguardando: 1,
          tempo_estimado_segundos: 0,
          prioridade_clinica: 3,
          status: "CHAMANDO_PACIENTE",
          chamada_iniciada_em: null,
          ttl_segundos: 45,
        }),
      });
    });

    // Instalação do relógio virtual ANTES de page.goto (mandatório na ADR-011)
    await page.clock.install();

    await page.addInitScript((sessionData) => {
      window.localStorage.setItem("medisync_session", JSON.stringify(sessionData));
    }, MOCK_SESSION);

    await page.goto("/fila");

    // Modal de convocação médica visível
    const modal = page.getByRole("alertdialog");
    await expect(modal).toBeVisible();
    await expect(page.getByRole("heading", { name: /o médico está chamando!/i })).toBeVisible();

    // Auditoria de acessibilidade do modal (sem quebras de aria-live)
    const scanResults = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(scanResults.violations).toEqual([]);

    // Avanço determinístico de tempo de 46 segundos (além dos 45s da tolerância RN02)
    for (let i = 0; i < 46; i++) {
      await page.clock.fastForward(1000);
    }

    // Modal deve ser descartado automaticamente para estado de ausência
    await expect(modal).not.toBeVisible();
    await expect(page.getByText(/chamada não atendida/i)).toBeVisible();
    await expect(
      page.getByText(/não houve confirmação dentro da janela de 45 segundos/i),
    ).toBeVisible();
  });

  test("E2E-QUEUE-03: Relato de Piora Clínica com IDs canônicos e <fieldset>/<legend> WCAG (RF-06)", async ({
    page,
  }) => {
    let capturedPioraPayload: Record<string, unknown> | null = null;
    await page.route("**/api/v1/fila/piora", async (route) => {
      capturedPioraPayload = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          atendimento_id: MOCK_SESSION.atendimentoId,
          prioridade_clinica: 2,
          status_atendimento: "APTO_PARA_CHAMADA",
          alerta_samu_disparado: false,
          redirecionado_emergencia: false,
          nova_posicao: 1,
          instrucoes: "Prioridade reclassificada para Muito Urgente (Laranja).",
        }),
      });
    });

    await page.addInitScript((sessionData) => {
      window.localStorage.setItem("medisync_session", JSON.stringify(sessionData));
    }, MOCK_SESSION);

    await page.goto("/fila");

    // Clica em relatar piora
    await page.getByRole("button", { name: /relatar piora/i }).click();

    // Modal de piora clínica visível com <fieldset>/<legend>
    await expect(
      page.getByRole("heading", { name: /salvaguarda de piora clínica/i }),
    ).toBeVisible();
    const sintomasGroup = page.getByRole("group", { name: /sinais de alerta ou novos sintomas/i });
    await expect(sintomasGroup).toBeVisible();
    await expect(sintomasGroup.evaluate((el) => el.tagName)).resolves.toBe("FIELDSET");

    const pioraScan = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(pioraScan.violations).toEqual([]);

    // Seleciona sintoma canônico e preenche queixa de agravamento
    await page.getByLabel(/falta de ar intensa/i).check();
    await page
      .getByLabel(/descreva com suas palavras o que piorou/i)
      .fill("Dor aumentou progressivamente na última hora");

    // Submete reavaliação
    await page.getByRole("button", { name: /enviar reavaliação/i }).click();

    // Payload envia IDs canônicos de triage e prioridade atualiza para Laranja
    expect(capturedPioraPayload).toMatchObject({
      atendimento_id: MOCK_SESSION.atendimentoId,
      novos_sintomas: ["dispneia_grave"],
    });
    await expect(page.getByText(/laranja: muito urgente/i)).toBeVisible();
  });

  test("E2E-QUEUE-04: Desistência Voluntária da Fila (RN06)", async ({ page }) => {
    await page.addInitScript((sessionData) => {
      window.localStorage.setItem("medisync_session", JSON.stringify(sessionData));
    }, MOCK_SESSION);

    await page.goto("/fila");

    // Clica no link de desistência
    await page.getByRole("button", { name: /desistir do atendimento/i }).click();

    // Confirma desistência no modal
    await expect(page.getByText(/tem certeza de que deseja sair da fila virtual\?/i)).toBeVisible();
    await page.getByRole("button", { name: /confirmar desistência/i }).click();

    // Transição para tela de cancelamento
    await expect(page.getByText(/atendimento cancelado/i)).toBeVisible();

    // Retorna para /home mantendo a sessão do cidadão sem atendimentoId ativo
    await page.getByRole("button", { name: /voltar ao início/i }).click();
    await expect(page).toHaveURL(/\/home$/);
    await expect(
      page.getByRole("heading", { level: 1, name: /serviços de saúde digital/i }),
    ).toBeVisible();
    const updatedSession = await page.evaluate(() => localStorage.getItem("medisync_session"));
    expect(updatedSession).not.toBeNull();
    const parsed = JSON.parse(updatedSession ?? "{}");
    expect(parsed.token).toBe(MOCK_SESSION.token);
    expect(parsed.atendimentoId).toBeUndefined();
  });
});
