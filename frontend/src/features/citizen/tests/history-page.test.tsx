import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import {
  handleListarHistoricoPacienteApiV1ConsultationsMeHistoricoGet,
  handleListarMeusAgendamentosApiV1SchedulingAgendamentosMeGet,
} from "@/api/generated/msw.gen";
import { HistoryPage } from "@/features/citizen/pages/history-page";
import {
  MOCK_CITIZEN_SESSION,
  renderCitizenRoute,
} from "@/features/citizen/tests/test-router-helper";
import { server } from "@/mocks/server";

describe("HistoryPage (/historico)", () => {
  beforeEach(() => {
    server.use(
      handleListarHistoricoPacienteApiV1ConsultationsMeHistoricoGet({
        body: [
          {
            atendimento_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b11",
            status: "FINALIZADO",
            prioridade_clinica: 4,
            queixa_principal: "Dor de garganta e febre baixa há 2 dias",
            criado_em: "2026-11-10T14:00:00Z",
            finalizado_em: "2026-11-10T14:22:00Z",
            medico_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b99",
            diagnostico_cid10: "J02.9",
            conduta_resumo: "Hidratação oral, analgésico sintomático e retorno se piora.",
          },
          {
            atendimento_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b12",
            status: "CANCELADO",
            prioridade_clinica: 5,
            queixa_principal: "Consulta cancelada pelo paciente",
            criado_em: "2026-11-08T09:00:00Z",
            finalizado_em: null,
            medico_id: null,
            diagnostico_cid10: null,
            conduta_resumo: null,
          },
        ],
      }),
      handleListarMeusAgendamentosApiV1SchedulingAgendamentosMeGet({
        body: [
          {
            id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b21",
            paciente_id: MOCK_CITIZEN_SESSION.pacienteId,
            profissional_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b88",
            especialidade: "PSICOLOGIA",
            slot_inicio: "2026-11-20T10:00:00Z",
            slot_fim: "2026-11-20T10:45:00Z",
            status: "AGENDADO",
            observacoes: "Primeira sessão de acolhimento psicológico",
            atendimento_id: null,
            criado_em: "2026-11-15T10:00:00Z",
            atualizado_em: "2026-11-15T10:00:00Z",
          },
          {
            id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b22",
            paciente_id: MOCK_CITIZEN_SESSION.pacienteId,
            profissional_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b88",
            especialidade: "NUTRICAO",
            slot_inicio: "2026-11-18T14:00:00Z",
            slot_fim: "2026-11-18T14:30:00Z",
            status: "CONCLUIDO",
            observacoes: "Retorno nutricional concluído",
            atendimento_id: null,
            criado_em: "2026-11-12T10:00:00Z",
            atualizado_em: "2026-11-18T14:30:00Z",
          },
          {
            id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b23",
            paciente_id: MOCK_CITIZEN_SESSION.pacienteId,
            profissional_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b88",
            especialidade: "PSICOLOGIA",
            slot_inicio: "2026-11-17T11:00:00Z",
            slot_fim: "2026-11-17T11:45:00Z",
            status: "FALTA",
            observacoes: "Paciente não compareceu",
            atendimento_id: null,
            criado_em: "2026-11-10T10:00:00Z",
            atualizado_em: "2026-11-17T11:45:00Z",
          },
        ],
      }),
    );
  });

  it("exibe atendimentos de PA com CID-10 e agendamentos eMulti no mesmo fuso horário UTC e badges alinhados", async () => {
    renderCitizenRoute(<HistoryPage session={MOCK_CITIZEN_SESSION} />, "/historico");

    expect(await screen.findByText(/dor de garganta e febre baixa há 2 dias/i)).toBeInTheDocument();
    expect(screen.getByText(/cid-10: j02\.9/i)).toBeInTheDocument();
    expect(
      screen.getByText(/hidratação oral, analgésico sintomático e retorno se piora/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/nível 4 · pouco urgente/i)).toBeInTheDocument();

    expect(screen.getAllByText("Psicologia")).toHaveLength(2);
    expect(screen.getByText("Nutrição")).toBeInTheDocument();
    expect(screen.getByText(/primeira sessão de acolhimento psicológico/i)).toBeInTheDocument();
    expect(screen.getByText(/20\/11\/2026, 10:00 até 20\/11\/2026, 10:45/)).toBeInTheDocument();
    expect(screen.getByText("Concluído")).toBeInTheDocument();
    expect(screen.getByText("Falta")).toBeInTheDocument();
  });

  it("filtra atendimentos por tipo e status usando controles acessíveis (incluindo FALTA em Cancelados)", async () => {
    renderCitizenRoute(<HistoryPage session={MOCK_CITIZEN_SESSION} />, "/historico");
    const user = userEvent.setup();

    await screen.findByText(/dor de garganta/i);

    await user.click(screen.getByRole("button", { name: /^agendamentos emulti$/i }));

    await waitFor(() => {
      expect(screen.queryByText(/dor de garganta/i)).not.toBeInTheDocument();
      expect(screen.getAllByText("Psicologia")).toHaveLength(2);
    });

    await user.click(screen.getByRole("button", { name: /^cancelados$/i }));
    await waitFor(() => {
      expect(screen.getByText(/paciente não compareceu/i)).toBeInTheDocument();
      expect(screen.queryByText(/retorno nutricional concluído/i)).not.toBeInTheDocument();
    });

    const tipoGroup = screen.getByRole("group", { name: /filtrar por tipo de consulta/i });
    await user.click(within(tipoGroup).getByRole("button", { name: /^todos$/i }));
    await user.click(screen.getByRole("button", { name: /^finalizados$/i }));

    await waitFor(() => {
      expect(screen.getByText(/dor de garganta/i)).toBeInTheDocument();
      expect(screen.getByText(/retorno nutricional concluído/i)).toBeInTheDocument();
      expect(screen.queryByText(/consulta cancelada pelo paciente/i)).not.toBeInTheDocument();
      expect(screen.queryByText("Psicologia")).not.toBeInTheDocument();
    });
  });
});
