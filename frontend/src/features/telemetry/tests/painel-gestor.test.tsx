import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  handleAtualizarConfiguracaoPlantaoApiV1TelemetriaConfigPlantaoPut,
  handleExportarBpaApiV1AmbulatoryProducaoExportarGet,
  handleListarProducaoApiV1AmbulatoryProducaoGet,
  handleObterConfiguracaoPlantaoApiV1TelemetriaConfigPlantaoGet,
  handleObterPainelTelemetriaApiV1TelemetriaPainelGet,
} from "@/api/generated/msw.gen";
import type { ConfigPlantaoResponse, PainelTelemetriaResponse } from "@/api/generated/types.gen";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/utils";
import { PainelGestor } from "../components/painel-gestor";

const mockPainelData: PainelTelemetriaResponse = {
  gerado_em: "2026-11-02T12:00:00Z",
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
  no_show_rate: 0.05,
  evasao_rate: 0.02,
  sla_compliance_percentual: 98.5,
  sla_em_conformidade: true,
  medicos_ativos_count: 2,
  total_pacientes_fila: 5,
  total_atendimentos: 24,
};

const mockConfigData: ConfigPlantaoResponse = {
  id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b01",
  medicos_ativos_planejados: 2,
  alpha_backpressure: "1.0",
  cota_diaria_maxima: 50,
  tma_padrao_segundos: 900,
  tempo_tolerancia_ring_segundos: 45,
  modo_operacao: "NORMAL",
  sla_minutos_nivel_1: 0,
  sla_minutos_nivel_2: 10,
  sla_minutos_nivel_3: 60,
  sla_minutos_nivel_4: 120,
  sla_minutos_nivel_5: 240,
  criado_em: "2026-11-01T00:00:00Z",
  atualizado_em: "2026-11-01T00:00:00Z",
  atualizado_por_id: null,
};

describe("PainelGestor Integration Tests (RF-10, US-13, ACR SUS, RN06)", () => {
  beforeEach(() => {
    server.use(
      handleObterPainelTelemetriaApiV1TelemetriaPainelGet({ body: mockPainelData }),
      handleObterConfiguracaoPlantaoApiV1TelemetriaConfigPlantaoGet({ body: mockConfigData }),
      handleAtualizarConfiguracaoPlantaoApiV1TelemetriaConfigPlantaoPut({ body: mockConfigData }),
      handleListarProducaoApiV1AmbulatoryProducaoGet({
        body: {
          items: [],
          total: 0,
          competencia: "202611",
          page: 1,
          size: 50,
        },
      }),
      handleExportarBpaApiV1AmbulatoryProducaoExportarGet({ body: "01#BPA#MOCK" }),
    );
  });

  it("IT-PANEL-01: Renderiza métricas operacionais consolidadas e cabeçalho da regulação", async () => {
    renderWithProviders(<PainelGestor gestorNome="Dra. Mariana Santos" />);

    // Cabeçalho da regulação
    expect(
      screen.getByRole("heading", { name: /painel de regulação e telemetria sus/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/dra\. mariana santos/i)).toBeInTheDocument();
    expect(screen.getByText(/polling 5s/i)).toBeInTheDocument();

    // TMA Real vs Planejado
    await waitFor(() => {
      expect(screen.getByTestId("tma-real")).toHaveTextContent(/aproximadamente 14 minutos/i);
    });
    expect(screen.getByText(/meta estimada:/i)).toBeInTheDocument();
    expect(screen.getByText(/aproximadamente 15 minutos/i)).toBeInTheDocument();

    // Atendimentos e cota
    expect(screen.getByTestId("pacientes-atendidos")).toHaveTextContent("24");
    expect(screen.getByText(/\/ cota 50/i)).toBeInTheDocument();
    expect(screen.getByText(/48% da cota utilizada/i)).toBeInTheDocument();

    // Fila de espera
    expect(screen.getByTestId("total-pacientes-fila")).toHaveTextContent("5");
    expect(screen.getByText(/5 pacientes aguardando/i)).toBeInTheDocument();
  });

  it("IT-PANEL-02: Exibe status de capacidade adequada ou alerta de sobrecarga", async () => {
    renderWithProviders(<PainelGestor />);

    await waitFor(() => {
      expect(screen.getByTestId("status-saturacao")).toHaveTextContent(/capacidade adequada/i);
    });
    expect(screen.getByTestId("medicos-ativos-info")).toHaveTextContent("2 de 2 médicos ativos");

    // Simula sobrecarga / saturação
    server.use(
      handleObterPainelTelemetriaApiV1TelemetriaPainelGet({
        body: {
          ...mockPainelData,
          medicos_ativos_count: 1,
          total_pacientes_fila: 15,
        },
      }),
    );

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /atualizar telemetria/i }));

    await waitFor(() => {
      expect(screen.getByTestId("status-saturacao")).toHaveTextContent(/atenção \/ sobrecarga/i);
    });
  });

  it("IT-PANEL-03: Exibe distribuição e TME por classificação ACR SUS oficial", async () => {
    renderWithProviders(<PainelGestor />);

    await waitFor(() => {
      expect(screen.getByTestId("badge-sla-geral")).toHaveTextContent(/sla geral: 98.5%/i);
    });

    // 5 Níveis de Risco ACR SUS
    expect(screen.getByText(/emergência imediata \(samu 192\)/i)).toBeInTheDocument();
    expect(screen.getByText(/muito urgente/i)).toBeInTheDocument();
    expect(screen.getByText(/^urgente$/i)).toBeInTheDocument();
    expect(screen.getByText(/pouco urgente/i)).toBeInTheDocument();
    expect(screen.getByText(/não urgente/i)).toBeInTheDocument();

    // TME formatados
    expect(screen.getByText(/aproximadamente 1 minuto/i)).toBeInTheDocument(); // Nível 1
    expect(screen.getByText(/aproximadamente 5 minutos/i)).toBeInTheDocument(); // Nível 2
    expect(screen.getByText(/aproximadamente 10 minutos/i)).toBeInTheDocument(); // Nível 3
    expect(screen.getByText(/aproximadamente 20 minutos/i)).toBeInTheDocument(); // Nível 4
    expect(screen.getByText(/aproximadamente 40 minutos/i)).toBeInTheDocument(); // Nível 5
  });

  it("IT-PANEL-04: Exibe taxas de No-Show e Evasão e métricas da equipe médica", async () => {
    renderWithProviders(<PainelGestor />);

    await waitFor(() => {
      expect(screen.getByTestId("taxa-no-show")).toHaveTextContent("5.0%");
    });
    expect(screen.getByTestId("taxa-evasao")).toHaveTextContent("2.0%");

    // Tabela de médicos
    expect(screen.getByText(/dr\. eduardo rocha/i)).toBeInTheDocument();
    expect(screen.getByText(/12 atendimentos/i)).toBeInTheDocument();
    expect(screen.getByText(/tma: aproximadamente 14 minutos/i)).toBeInTheDocument();
  });

  it("IT-PANEL-05: Botão Sair executa callback de encerramento da sessão do gestor", async () => {
    const handleLogout = vi.fn();
    renderWithProviders(<PainelGestor onLogout={handleLogout} />);

    const btnSair = screen.getByRole("button", { name: /sair/i });
    expect(btnSair).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(btnSair);

    expect(handleLogout).toHaveBeenCalledTimes(1);
  });

  it("IT-PANEL-06: Atualiza política do plantão e fator alpha de backpressure via formulário (US-12)", async () => {
    let payloadRecebido: Record<string, unknown> | null = null;

    server.use(
      handleAtualizarConfiguracaoPlantaoApiV1TelemetriaConfigPlantaoPut(async ({ request }) => {
        payloadRecebido = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          ...mockConfigData,
          medicos_ativos_planejados: 4,
          alpha_backpressure: "1.28",
        });
      }),
    );

    renderWithProviders(<PainelGestor gestorNome="Dra. Mariana Santos" />);

    const medicosInput = await screen.findByLabelText(/médicos ativos planejados/i);
    const alphaInput = screen.getByLabelText(/fator alpha backpressure/i);

    const user = userEvent.setup();
    await user.clear(medicosInput);
    await user.type(medicosInput, "4");
    await user.clear(alphaInput);
    await user.type(alphaInput, "1.28");

    await user.click(screen.getByRole("button", { name: /salvar política do plantão/i }));

    await waitFor(() => {
      expect(payloadRecebido).toMatchObject({
        medicos_ativos_planejados: 4,
        alpha_backpressure: "1.28",
      });
      expect(screen.getByText(/política do plantão atualizada com sucesso/i)).toBeInTheDocument();
    });
  });

  it("IT-PANEL-07: Lista produção ambulatorial SUS BPA-I e executa exportação .txt (US-11)", async () => {
    let exportarCompetencia: string | null = null;

    server.use(
      handleListarProducaoApiV1AmbulatoryProducaoGet({
        body: {
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
        },
      }),
      handleExportarBpaApiV1AmbulatoryProducaoExportarGet(({ request }) => {
        const url = new URL(request.url);
        exportarCompetencia = url.searchParams.get("competencia");
        return HttpResponse.text("01#2269988#202611#0301010250", { status: 200 });
      }),
    );

    renderWithProviders(<PainelGestor gestorNome="Dra. Mariana Santos" />);

    expect(await screen.findByText("03.01.01.025-0")).toBeInTheDocument();
    expect(screen.getByText("1 registros")).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /exportar bpa-i \(\.txt\)/i }));

    await waitFor(() => {
      expect(exportarCompetencia).toBe("202611");
      expect(
        screen.getByText(/arquivo bpa-i da competência 202611 exportado/i),
      ).toBeInTheDocument();
      expect(screen.getByText(/BPA_I_202611_2269988\.txt/)).toBeInTheDocument();
    });
  });
});
