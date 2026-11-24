import { waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  handleCadastrarDisponibilidadeApiV1SchedulingDisponibilidadesPost,
  handleIniciarAtendimentoAgendadoApiV1SchedulingAgendamentosAgendamentoIdIniciarPost,
  handleListarAgendaDiaApiV1SchedulingAgendaDiaGet,
} from "@/api/generated/msw.gen";
import type { AgendamentoResponse } from "@/api/generated/types.gen";
import { clearAccessToken, setAccessToken } from "@/lib/auth-token";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/utils";
import { ProfessionalSchedulePanel } from "../components/professional-schedule-panel";
import {
  createAgendamentoFixture,
  createDisponibilidadeFixture,
  MOCK_AGENDAMENTO_ID,
} from "./fixtures";

describe("ProfessionalSchedulePanel (Agenda Programada do Profissional)", () => {
  beforeEach(() => {
    setAccessToken("profissional-token");
  });

  afterEach(() => {
    clearAccessToken();
  });

  it("lista agenda do dia e inicia teleconsulta agendada", async () => {
    const user = userEvent.setup();
    const onAtendimentoIniciado = vi.fn();

    let agendaAtual: AgendamentoResponse[] = [
      createAgendamentoFixture({
        id: MOCK_AGENDAMENTO_ID,
        especialidade: "PSICOLOGIA",
        status: "AGENDADO",
        observacoes: "Retorno semanal",
      }),
    ];

    server.use(
      handleListarAgendaDiaApiV1SchedulingAgendaDiaGet(() => {
        return HttpResponse.json(agendaAtual, { status: 200 });
      }),
      handleIniciarAtendimentoAgendadoApiV1SchedulingAgendamentosAgendamentoIdIniciarPost(
        ({ params }) => {
          const iniciado = createAgendamentoFixture({
            id: params.agendamento_id,
            status: "EM_ATENDIMENTO",
            observacoes: "Retorno semanal",
          });
          agendaAtual = [iniciado];
          return HttpResponse.json(iniciado, { status: 200 });
        },
      ),
    );

    const { findByRole, getByText, queryByRole } = renderWithProviders(
      <ProfessionalSchedulePanel onAtendimentoIniciado={onAtendimentoIniciado} />,
    );

    const btnIniciar = await findByRole("button", { name: /iniciar teleconsulta agendada/i });
    expect(btnIniciar).toHaveClass("min-h-[44px]");
    expect(getByText(/retorno semanal/i)).toBeInTheDocument();

    await user.click(btnIniciar);

    await waitFor(() => {
      expect(onAtendimentoIniciado).toHaveBeenCalledTimes(1);
      expect(getByText("Em atendimento")).toBeInTheDocument();
      expect(
        queryByRole("button", { name: /iniciar teleconsulta agendada/i }),
      ).not.toBeInTheDocument();
    });
  });

  it("permite cadastrar nova janela semanal de disponibilidade via modal validado", async () => {
    const user = userEvent.setup();
    let payloadRecebido: unknown = null;

    server.use(
      handleListarAgendaDiaApiV1SchedulingAgendaDiaGet({ body: [] }),
      handleCadastrarDisponibilidadeApiV1SchedulingDisponibilidadesPost(async ({ request }) => {
        const body = await request.json();
        payloadRecebido = body;
        return HttpResponse.json(
          createDisponibilidadeFixture({
            especialidade: body.especialidade,
            dia_semana: body.dia_semana,
            hora_inicio: `${body.hora_inicio}:00`,
            hora_fim: `${body.hora_fim}:00`,
            duracao_minutos: body.duracao_minutos,
          }),
          { status: 201 },
        );
      }),
    );

    const { getByRole, getByLabelText, findByRole, queryByRole, getByText } = renderWithProviders(
      <ProfessionalSchedulePanel />,
    );

    const btnAbrirModal = getByRole("button", { name: /cadastrar disponibilidade/i });
    await user.click(btnAbrirModal);

    expect(await findByRole("dialog")).toBeInTheDocument();

    await user.selectOptions(getByLabelText(/especialidade/i), "NUTRICAO");
    await user.selectOptions(getByLabelText(/dia da semana/i), "2");

    const inputInicio = getByLabelText(/horário inicial/i);
    await user.clear(inputInicio);
    await user.type(inputInicio, "13:00");

    const inputFim = getByLabelText(/horário final/i);
    await user.clear(inputFim);
    await user.type(inputFim, "17:00");

    const inputDuracao = getByLabelText(/duração do atendimento/i);
    await user.clear(inputDuracao);
    await user.type(inputDuracao, "30");

    await user.click(getByRole("button", { name: /salvar disponibilidade/i }));

    await waitFor(() => {
      expect(queryByRole("dialog")).not.toBeInTheDocument();
    });

    expect(payloadRecebido).toEqual({
      especialidade: "NUTRICAO",
      dia_semana: 2,
      hora_inicio: "13:00",
      hora_fim: "17:00",
      duracao_minutos: 30,
    });
    expect(getByText(/disponibilidade cadastrada: nutrição · quarta-feira/i)).toBeInTheDocument();
  });

  it("valida faixa horária inválida no formulário de disponibilidade antes de enviar", async () => {
    const user = userEvent.setup();

    server.use(handleListarAgendaDiaApiV1SchedulingAgendaDiaGet({ body: [] }));

    const { getByRole, getByLabelText, findByText } = renderWithProviders(
      <ProfessionalSchedulePanel />,
    );

    await user.click(getByRole("button", { name: /cadastrar disponibilidade/i }));

    const inputInicio = getByLabelText(/horário inicial/i);
    await user.clear(inputInicio);
    await user.type(inputInicio, "16:00");

    const inputFim = getByLabelText(/horário final/i);
    await user.clear(inputFim);
    await user.type(inputFim, "14:00");

    await user.click(getByRole("button", { name: /salvar disponibilidade/i }));

    expect(
      await findByText(/o horário final deve ser posterior ao horário inicial/i),
    ).toBeInTheDocument();
  });
});
