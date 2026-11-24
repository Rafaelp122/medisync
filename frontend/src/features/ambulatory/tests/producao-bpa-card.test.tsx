import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  handleExportarBpaApiV1AmbulatoryProducaoExportarGet,
  handleListarProducaoApiV1AmbulatoryProducaoGet,
} from "@/api/generated/msw.gen";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/utils";
import {
  extractCnesFromBpaContent,
  getCompetenciaAtualUtc,
  ProducaoBpaCard,
} from "../components/producao-bpa-card";

describe("ProducaoBpaCard & Ambulatory Helpers (US-11 / RF-08)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("UT-AMB-01: getCompetenciaAtualUtc retorna YYYYMM em UTC sem fixar 202611", () => {
    expect(getCompetenciaAtualUtc(new Date("2027-01-01T01:30:00Z"))).toBe("202701");
    expect(getCompetenciaAtualUtc(new Date("2026-12-31T23:59:59Z"))).toBe("202612");
  });

  it("UT-AMB-02: extractCnesFromBpaContent lê CNES real da linha 03 e ignora cabeçalho 01#BPA#", () => {
    const remessaDatasus = ["01#BPA#2026110000010000011234", "0322699882026110010301010250"].join(
      "\n",
    );

    expect(extractCnesFromBpaContent(remessaDatasus)).toBe("2269988");
    expect(extractCnesFromBpaContent("01#BPA#202611000001")).toBeNull();
  });

  it("IT-AMB-03: Lista produção ambulatorial e prioriza Content-Disposition / linha 03 na exportação .txt", async () => {
    const competenciaAtual = getCompetenciaAtualUtc();
    let exportedComp: string | null = null;

    server.use(
      handleListarProducaoApiV1AmbulatoryProducaoGet({
        body: {
          items: [
            {
              atendimento_id: "018f3a5b-0000-7000-8000-000000000099",
              cnes: "2269988",
              codigo_sigtap: "03.01.01.025-0",
              carater_atendimento: "02",
              consolidado_em: "2026-11-15T01:30:00Z",
            },
          ],
          total: 1,
          competencia: competenciaAtual,
          page: 1,
          size: 50,
        },
      }),
      handleExportarBpaApiV1AmbulatoryProducaoExportarGet(({ request }) => {
        const url = new URL(request.url);
        exportedComp = url.searchParams.get("competencia");
        return HttpResponse.text("01#BPA#202611000001\n0322699882026110301010250", {
          status: 200,
          headers: {
            "Content-Disposition": `attachment; filename="BPA_I_${competenciaAtual}_2269988.txt"`,
          },
        });
      }),
    );

    renderWithProviders(<ProducaoBpaCard />);

    expect(screen.getByLabelText(/competência \(yyyymm\)/i)).toHaveValue(competenciaAtual);
    expect(await screen.findByText("03.01.01.025-0")).toBeInTheDocument();
    expect(screen.getByText("15/11/2026")).toBeInTheDocument();
    expect(screen.getByText("1 registros")).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /exportar bpa-i \(\.txt\)/i }));

    await waitFor(() => {
      expect(exportedComp).toBe(competenciaAtual);
      expect(
        screen.getByText(new RegExp(`BPA_I_${competenciaAtual}_2269988\\.txt`)),
      ).toBeInTheDocument();
    });
  });

  it("IT-AMB-04: Sem Content-Disposition e sem itens listados, extrai CNES da linha 03 e nunca 'BPA'", async () => {
    const competenciaAtual = getCompetenciaAtualUtc();

    server.use(
      handleListarProducaoApiV1AmbulatoryProducaoGet({
        body: {
          items: [],
          total: 0,
          competencia: competenciaAtual,
          page: 1,
          size: 50,
        },
      }),
      handleExportarBpaApiV1AmbulatoryProducaoExportarGet(() =>
        HttpResponse.text("01#BPA#202611000001\n0376543212026110301010250", { status: 200 }),
      ),
    );

    renderWithProviders(<ProducaoBpaCard />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /exportar bpa-i \(\.txt\)/i }));

    await waitFor(() => {
      expect(
        screen.getByText(new RegExp(`BPA_I_${competenciaAtual}_7654321\\.txt`)),
      ).toBeInTheDocument();
    });
    expect(screen.queryByText(/_BPA\.txt/)).not.toBeInTheDocument();
  });
});
