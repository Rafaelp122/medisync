import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  handleAtualizarConfiguracaoPlantaoApiV1TelemetriaConfigPlantaoPut,
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
  no_show_rate: 5.0,
  evasao_rate: 2.0,
  sla_compliance_percentual: 98.5,
  sla_em_conformidade: true,
  medicos_ativos_count: 2,
  total_pacientes_fila: 5,
  total_atendimentos: 24,
};

const mockConfigData: ConfigPlantaoResponse = {
  id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b01",
  medicos_ativos_planejados: 2,
  alpha_backpressure: "1.25",
  cota_diaria_maxima: 50,
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

function BpaSlotProbe({ onRender }: { onRender: () => void }) {
  onRender();
  return <div data-testid="bpa-slot">Slot BPA</div>;
}

describe("PainelGestor Integration Tests (RF-10, US-13, ACR SUS, RN06)", () => {
  beforeEach(() => {
    server.use(
      handleObterPainelTelemetriaApiV1TelemetriaPainelGet({ body: mockPainelData }),
      handleObterConfiguracaoPlantaoApiV1TelemetriaConfigPlantaoGet({ body: mockConfigData }),
      handleAtualizarConfiguracaoPlantaoApiV1TelemetriaConfigPlantaoPut({ body: mockConfigData }),
    );
  });

  it("IT-PANEL-01: Renderiza métricas operacionais consolidadas e cabeçalho da regulação", async () => {
    renderWithProviders(<PainelGestor gestorNome="Dra. Mariana Santos" />);

    expect(
      screen.getByRole("heading", { name: /painel de regulação e telemetria sus/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/dra\. mariana santos/i)).toBeInTheDocument();
    expect(screen.getByText(/polling 5s/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId("tma-real")).toHaveTextContent(/aproximadamente 14 minutos/i);
    });
    expect(screen.getByText(/meta estimada:/i)).toBeInTheDocument();
    expect(screen.getByText(/aproximadamente 15 minutos/i)).toBeInTheDocument();

    expect(screen.getByTestId("pacientes-atendidos")).toHaveTextContent("24");
    expect(screen.getByText(/\/ cota 50/i)).toBeInTheDocument();
    expect(screen.getByText(/48% da cota utilizada/i)).toBeInTheDocument();

    expect(screen.getByTestId("total-pacientes-fila")).toHaveTextContent("5");
    expect(screen.getByText(/5 pacientes aguardando/i)).toBeInTheDocument();
  });

  it("IT-PANEL-02: Exibe status de capacidade adequada ou alerta de sobrecarga", async () => {
    renderWithProviders(<PainelGestor />);

    await waitFor(() => {
      expect(screen.getByTestId("status-saturacao")).toHaveTextContent(/capacidade adequada/i);
    });
    expect(screen.getByTestId("medicos-ativos-info")).toHaveTextContent("2 de 2 médicos ativos");

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

    expect(screen.getByText(/emergência imediata \(samu 192\)/i)).toBeInTheDocument();
    expect(screen.getByText(/^muito urgente$/i)).toBeInTheDocument();
    expect(screen.getByText(/^urgente$/i)).toBeInTheDocument();
    expect(screen.getByText(/^pouco urgente$/i)).toBeInTheDocument();
    expect(screen.getByText(/^não urgente$/i)).toBeInTheDocument();

    expect(screen.getByText(/aproximadamente 1 minuto/i)).toBeInTheDocument();
    expect(screen.getByText(/aproximadamente 5 minutos/i)).toBeInTheDocument();
    expect(screen.getByText(/aproximadamente 10 minutos/i)).toBeInTheDocument();
    expect(screen.getByText(/aproximadamente 20 minutos/i)).toBeInTheDocument();
    expect(screen.getByText(/aproximadamente 40 minutos/i)).toBeInTheDocument();
  });

  it("IT-PANEL-04: Exibe taxas reais 0..100 sem multiplicar por 100 e métricas da equipe médica", async () => {
    renderWithProviders(<PainelGestor />);

    await waitFor(() => {
      expect(screen.getByTestId("taxa-no-show")).toHaveTextContent("5.0%");
    });
    expect(screen.getByTestId("taxa-evasao")).toHaveTextContent("2.0%");
    expect(screen.getByTestId("taxa-no-show")).not.toHaveTextContent("500.0%");

    expect(screen.getByText(/dr\. eduardo rocha/i)).toBeInTheDocument();
    expect(screen.getByText(/12 atendimentos/i)).toBeInTheDocument();
    expect(screen.getByText(/tma: aproximadamente 14 minutos/i)).toBeInTheDocument();
  });

  it("IT-PANEL-05: Botão Sair executa callback de encerramento da sessão do gestor", async () => {
    const handleLogout = vi.fn();
    renderWithProviders(<PainelGestor onLogout={handleLogout} />);

    const btnSair = screen.getByRole("button", { name: /sair/i });
    const user = userEvent.setup();
    await user.click(btnSair);

    expect(handleLogout).toHaveBeenCalledTimes(1);
  });

  it("IT-PANEL-06: Atualiza política completa (11 campos incluindo ring e SLAs) via formulário (US-12)", async () => {
    let payloadRecebido: Record<string, unknown> | null = null;

    server.use(
      handleAtualizarConfiguracaoPlantaoApiV1TelemetriaConfigPlantaoPut(async ({ request }) => {
        payloadRecebido = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          ...mockConfigData,
          medicos_ativos_planejados: 4,
          alpha_backpressure: "1.28",
          tempo_tolerancia_ring_segundos: 30,
          sla_minutos_nivel_2: 15,
        });
      }),
    );

    renderWithProviders(<PainelGestor gestorNome="Dra. Mariana Santos" />);

    const medicosInput = await screen.findByLabelText(/médicos ativos planejados/i);
    await waitFor(() => expect(medicosInput).toHaveValue(2));
    const alphaInput = screen.getByLabelText(/fator alpha backpressure/i);
    const ringInput = screen.getByLabelText(/tolerância de chamada \/ ring/i);
    const sla2Input = screen.getByLabelText(/sla nível 2/i);

    const user = userEvent.setup();
    await user.clear(medicosInput);
    await user.type(medicosInput, "4");
    await user.clear(alphaInput);
    await user.type(alphaInput, "1.28");
    await user.clear(ringInput);
    await user.type(ringInput, "30");
    await user.clear(sla2Input);
    await user.type(sla2Input, "15");

    await user.click(screen.getByRole("button", { name: /salvar política do plantão/i }));

    await waitFor(() => {
      expect(payloadRecebido).toEqual({
        medicos_ativos_planejados: 4,
        alpha_backpressure: "1.28",
        cota_diaria_maxima: 50,
        tma_padrao_segundos: 900,
        tempo_tolerancia_ring_segundos: 30,
        modo_operacao: "SUS",
        sla_minutos_nivel_1: 0,
        sla_minutos_nivel_2: 15,
        sla_minutos_nivel_3: 60,
        sla_minutos_nivel_4: 120,
        sla_minutos_nivel_5: 240,
      });
      expect(screen.getByText(/política do plantão atualizada com sucesso/i)).toBeInTheDocument();
    });
  });

  it("IT-PANEL-07: Permite marcar 'Cota Livre SUS' enviando cota_diaria_maxima: null (US-12)", async () => {
    let payloadRecebido: Record<string, unknown> | null = null;

    server.use(
      handleAtualizarConfiguracaoPlantaoApiV1TelemetriaConfigPlantaoPut(async ({ request }) => {
        payloadRecebido = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          ...mockConfigData,
          cota_diaria_maxima: null,
        });
      }),
    );

    renderWithProviders(<PainelGestor />);

    const cotaInput = await screen.findByLabelText(/cota diária máxima/i);
    await waitFor(() => expect(cotaInput).toHaveValue(50));

    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/cota livre sus/i));
    expect(cotaInput).toBeDisabled();

    await user.click(screen.getByRole("button", { name: /salvar política do plantão/i }));

    await waitFor(() => {
      expect(payloadRecebido?.cota_diaria_maxima).toBeNull();
      expect(screen.getByText(/política do plantão atualizada com sucesso/i)).toBeInTheDocument();
    });
  });

  it("IT-PANEL-08: Usa fallback de TMA padrão 600s (10 min) e rótulo padrão 'Gestor da Unidade'", async () => {
    server.use(
      handleObterConfiguracaoPlantaoApiV1TelemetriaConfigPlantaoGet(() =>
        HttpResponse.json({ detail: "Sem config" }, { status: 404 }),
      ),
    );

    renderWithProviders(<PainelGestor />);

    expect(screen.getByText(/gestor da unidade/i)).toBeInTheDocument();
    expect(screen.queryByText(/gestor municipal/i)).not.toBeInTheDocument();
    expect(screen.getByText(/aproximadamente 10 minutos/i)).toBeInTheDocument();
  });

  it("IT-PANEL-09: Isola refetch de telemetria em PainelMetricasAoVivo sem re-renderizar o slot BPA", async () => {
    const bpaRenderSpy = vi.fn();

    renderWithProviders(<PainelGestor renderBpaCard={<BpaSlotProbe onRender={bpaRenderSpy} />} />);

    await waitFor(() => {
      expect(screen.getByTestId("total-pacientes-fila")).toHaveTextContent("5");
    });
    const medicosInput = screen.getByLabelText(/médicos ativos planejados/i);
    await waitFor(() => expect(medicosInput).toHaveValue(2));
    const rendersAntesDoPolling = bpaRenderSpy.mock.calls.length;

    server.use(
      handleObterPainelTelemetriaApiV1TelemetriaPainelGet({
        body: {
          ...mockPainelData,
          total_pacientes_fila: 12,
        },
      }),
    );

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /atualizar telemetria/i }));

    await waitFor(() => {
      expect(screen.getByTestId("total-pacientes-fila")).toHaveTextContent("12");
    });
    expect(bpaRenderSpy).toHaveBeenCalledTimes(rendersAntesDoPolling);
  });
});
