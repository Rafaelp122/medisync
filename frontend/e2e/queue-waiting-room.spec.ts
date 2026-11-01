import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const MOCK_SESSION = {
  tipo: "acolhimento",
  role: "PACIENTE",
  pacienteId: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
  atendimentoId: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b99",
  prioridadeClinica: 3,
  protocolo: "MED-2026-0099",
  nomePaciente: "Juliana Silva",
  token: "fake-jwt-queue-token-e2e",
};

test.describe("Sala de Espera Virtual, Ring Modal 45s e Acessibilidade (E2E)", () => {
  test.beforeEach(async ({ page }) => {
    // Intercepta rotas da fila e consultas
    await page.route("**/api/v1/fila/posicao/*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          atendimento_id: MOCK_SESSION.atendimentoId,
          posicao: 2,
          total_aguardando: 5,
          tempo_estimado_segundos: 600,
          prioridade_clinica: 3,
          status: "AGUARDANDO_CHAMADA",
          protocolo: MOCK_SESSION.protocolo,
        }),
      });
    });

    await page.route("**/api/v1/consultations/*/livekit/token", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          token: "fake-livekit-room-token-e2e",
          url: "wss://livekit.medisync.local",
          room: `room-${MOCK_SESSION.atendimentoId}`,
          ttl_seconds: 3600,
        }),
      });
    });

    await page.route("**/api/v1/fila/piora", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          atendimento_id: MOCK_SESSION.atendimentoId,
          nova_prioridade: 2,
          nova_posicao: 1,
          alerta_samu_disparado: false,
          redirecionado_emergencia: false,
          instrucoes: "Prioridade reclassificada para Muito Urgente (Laranja).",
        }),
      });
    });

    await page.route("**/api/v1/fila/cancelar/*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          atendimento_id: MOCK_SESSION.atendimentoId,
          status: "CANCELADO",
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

    await page.goto("/");

    // Valida elementos principais da sala de espera
    await expect(page.getByRole("heading", { name: /sala de espera virtual/i })).toBeVisible();
    await expect(page.getByTestId("atendimento-id-completo")).toHaveText(
      MOCK_SESSION.atendimentoId,
    );
    await expect(page.getByText(/2º na fila/i)).toBeVisible();
    await expect(page.getByText(/aproximadamente 10 minutos/i)).toBeVisible();
    await expect(page.getByText(/urgente \(amarelo\)/i)).toBeVisible();

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
          protocolo: MOCK_SESSION.protocolo,
        }),
      });
    });

    // Instalação do relógio virtual ANTES de page.goto (mandatório na ADR-011)
    await page.clock.install();

    await page.addInitScript((sessionData) => {
      window.localStorage.setItem("medisync_session", JSON.stringify(sessionData));
    }, MOCK_SESSION);

    await page.goto("/");

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

  test("E2E-QUEUE-03: Relato de Piora Clínica e Reclassificação de Risco (RF-06)", async ({
    page,
  }) => {
    await page.addInitScript((sessionData) => {
      window.localStorage.setItem("medisync_session", JSON.stringify(sessionData));
    }, MOCK_SESSION);

    await page.goto("/");

    // Clica em relatar piora
    await page.getByRole("button", { name: /relatar piora/i }).click();

    // Modal de piora clínica visível
    await expect(
      page.getByRole("heading", { name: /salvaguarda de piora clínica/i }),
    ).toBeVisible();

    // Preenche queixa de agravamento
    await page
      .getByLabel(/descreva com suas palavras o que piorou/i)
      .fill("Dor aumentou progressivamente na última hora");

    // Submete reavaliação
    await page.getByRole("button", { name: /enviar reavaliação/i }).click();

    // Prioridade e badge devem atualizar para Laranja
    await expect(page.getByText(/muito urgente \(laranja\)/i)).toBeVisible();
  });

  test("E2E-QUEUE-04: Desistência Voluntária da Fila (RN06)", async ({ page }) => {
    await page.addInitScript((sessionData) => {
      window.localStorage.setItem("medisync_session", JSON.stringify(sessionData));
    }, MOCK_SESSION);

    await page.goto("/");

    // Clica no link de desistência
    await page.getByRole("button", { name: /desistir do atendimento/i }).click();

    // Confirma desistência no modal
    await expect(page.getByText(/tem certeza de que deseja sair da fila virtual\?/i)).toBeVisible();
    await page.getByRole("button", { name: /confirmar desistência/i }).click();

    // Transição para tela de cancelamento
    await expect(page.getByText(/atendimento cancelado/i)).toBeVisible();
  });
});
