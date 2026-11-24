import { waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { getSessionQueryScope } from "@/api/client";
import {
  handleCancelarAgendamentoApiV1SchedulingAgendamentosAgendamentoIdCancelarPost,
  handleCriarAgendamentoApiV1SchedulingAgendamentosPost,
  handleListarEspecialidadesApiV1SchedulingEspecialidadesGet,
  handleListarMeusAgendamentosApiV1SchedulingAgendamentosMeGet,
  handleListarSlotsApiV1SchedulingSlotsGet,
} from "@/api/generated/msw.gen";
import type { AgendamentoResponse } from "@/api/generated/types.gen";
import { MEUS_AGENDAMENTOS_QUERY_KEY_PREFIX } from "@/api/hooks/use-meus-agendamentos";
import { sessionTransport } from "@/lib/session-transport";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/utils";
import { ScheduleAppointmentPage } from "../pages/schedule-appointment-page";
import {
  createAgendamentoFixture,
  MOCK_AGENDAMENTO_ID,
  MOCK_ESPECIALIDADES,
  MOCK_SLOTS_NUTRICAO,
  MOCK_SLOTS_PSICOLOGIA,
} from "./fixtures";

describe("ScheduleAppointmentPage (Jornada de Agendamento do Paciente)", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionTransport.activatePatientSession({
      token: "paciente-token",
      pacienteId: "pac-padrao",
      role: "PACIENTE",
      tipo: "acolhimento",
    });
    server.use(
      handleListarEspecialidadesApiV1SchedulingEspecialidadesGet({
        body: MOCK_ESPECIALIDADES,
      }),
    );
  });

  afterEach(() => {
    sessionTransport.clearSession("all");
  });

  it("executa fluxo completo: escolher especialidade -> buscar slots -> agendar -> visualizar -> cancelar", async () => {
    const user = userEvent.setup();
    let agendamentosAtuais: AgendamentoResponse[] = [];

    server.use(
      handleListarMeusAgendamentosApiV1SchedulingAgendamentosMeGet(() => {
        return HttpResponse.json(agendamentosAtuais, { status: 200 });
      }),
      handleListarSlotsApiV1SchedulingSlotsGet(({ request }) => {
        const url = new URL(request.url);
        const esp = url.searchParams.get("especialidade");
        if (esp === "PSICOLOGIA") {
          return HttpResponse.json(MOCK_SLOTS_PSICOLOGIA, { status: 200 });
        }
        return HttpResponse.json([], { status: 200 });
      }),
      handleCriarAgendamentoApiV1SchedulingAgendamentosPost(async ({ request }) => {
        const body = await request.json();
        const novoAgendamento = createAgendamentoFixture({
          id: MOCK_AGENDAMENTO_ID,
          especialidade: body.especialidade,
          profissional_id: body.profissional_id,
          slot_inicio: body.slot_inicio,
          slot_fim: body.slot_fim ?? "2026-11-20T09:50:00Z",
          observacoes: body.observacoes ?? null,
          status: "AGENDADO",
        });
        agendamentosAtuais = [novoAgendamento];
        return HttpResponse.json(novoAgendamento, { status: 201 });
      }),
      handleCancelarAgendamentoApiV1SchedulingAgendamentosAgendamentoIdCancelarPost(
        ({ params }) => {
          agendamentosAtuais = agendamentosAtuais.map((item) =>
            item.id === params.agendamento_id ? { ...item, status: "CANCELADO" } : item,
          );
          const atualizado =
            agendamentosAtuais.find((item) => item.id === params.agendamento_id) ??
            createAgendamentoFixture({ status: "CANCELADO" });
          return HttpResponse.json(atualizado, { status: 200 });
        },
      ),
    );

    const { getByRole, getByLabelText, getByText, findByRole, queryByRole } = renderWithProviders(
      <ScheduleAppointmentPage />,
    );

    // 1. Escolhe especialidade Psicologia
    const btnPsicologia = await findByRole("button", { name: /psicologia/i });
    expect(btnPsicologia).toHaveClass("min-h-[44px]");
    await user.click(btnPsicologia);

    // 2. Aguarda slots carregarem e seleciona horário 09:00 - 09:50
    const btnSlot = await findByRole("button", { name: /09:00 às 09:50/i });
    expect(btnSlot).toHaveClass("min-h-[44px]");
    await user.click(btnSlot);

    // 3. Preenche observações opcionais e confirma agendamento
    const inputObs = getByLabelText(/observações ou motivo da consulta/i);
    await user.type(inputObs, "Crise de ansiedade recente");

    const btnConfirmar = getByRole("button", { name: /confirmar agendamento/i });
    await user.click(btnConfirmar);

    // 4. Confirmação aparece e item é listado em Meus Agendamentos
    await waitFor(() => {
      expect(getByText(/agendamento confirmado/i)).toBeInTheDocument();
    });
    expect(getByText("Observações: Crise de ansiedade recente")).toBeInTheDocument();

    // 5. Cancela o agendamento recém-criado
    const btnCancelar = await findByRole("button", { name: /cancelar agendamento/i });
    await user.click(btnCancelar);

    await waitFor(() => {
      expect(getByText("Cancelado")).toBeInTheDocument();
      expect(queryByRole("button", { name: /cancelar agendamento/i })).not.toBeInTheDocument();
    });
  });

  it("pré-seleciona especialidade via initialEspecialidade e consulta slots automaticamente", async () => {
    server.use(
      handleListarMeusAgendamentosApiV1SchedulingAgendamentosMeGet({ body: [] }),
      handleListarSlotsApiV1SchedulingSlotsGet(({ request }) => {
        const url = new URL(request.url);
        expect(url.searchParams.get("especialidade")).toBe("NUTRICAO");
        return HttpResponse.json(MOCK_SLOTS_NUTRICAO, { status: 200 });
      }),
    );

    const { findByRole } = renderWithProviders(
      <ScheduleAppointmentPage initialEspecialidade="nutricao" />,
    );

    const btnNutricao = await findByRole("button", { name: /nutrição/i });
    expect(btnNutricao).toHaveAttribute("aria-pressed", "true");

    const btnSlot = await findByRole("button", { name: /14:00 às 14:30/i });
    expect(btnSlot).toBeInTheDocument();
  });

  it("exibe alerta RFC 7807 legível quando o servidor retorna erro 409 (slot ocupado)", async () => {
    const user = userEvent.setup();

    server.use(
      handleListarMeusAgendamentosApiV1SchedulingAgendamentosMeGet({ body: [] }),
      handleListarSlotsApiV1SchedulingSlotsGet({ body: MOCK_SLOTS_PSICOLOGIA }),
      handleCriarAgendamentoApiV1SchedulingAgendamentosPost(() => {
        return HttpResponse.json(
          {
            type: "https://medisync.sus.gov.br/errors/slot-indisponivel",
            title: "Conflito de horário",
            status: 409,
            detail:
              "Este horário acabou de ser reservado por outro paciente. Escolha outro horário.",
          },
          { status: 409 },
        );
      }),
    );

    const { findByRole, getByRole, getByText } = renderWithProviders(
      <ScheduleAppointmentPage initialEspecialidade="PSICOLOGIA" />,
    );

    const btnSlot = await findByRole("button", { name: /09:00 às 09:50/i });
    await user.click(btnSlot);

    await user.click(getByRole("button", { name: /confirmar agendamento/i }));

    const alert = await findByRole("alert");
    expect(alert).toBeInTheDocument();
    expect(getByText(/horário já ocupado/i)).toBeInTheDocument();
    expect(
      getByText(/este horário acabou de ser reservado por outro paciente/i),
    ).toBeInTheDocument();
  });

  it("valida período inválido quando data final é anterior à data inicial", async () => {
    const user = userEvent.setup();

    server.use(
      handleListarMeusAgendamentosApiV1SchedulingAgendamentosMeGet({ body: [] }),
      handleListarSlotsApiV1SchedulingSlotsGet({ body: MOCK_SLOTS_PSICOLOGIA }),
    );

    const { getByLabelText, findByRole, getByText } = renderWithProviders(
      <ScheduleAppointmentPage initialEspecialidade="PSICOLOGIA" />,
    );

    const inputDataFim = getByLabelText(/data final/i);
    await user.clear(inputDataFim);
    await user.type(inputDataFim, "2020-01-01");

    const alert = await findByRole("alert");
    expect(alert).toBeInTheDocument();
    expect(
      getByText(/a data final deve ser igual ou posterior à data inicial/i),
    ).toBeInTheDocument();
  });

  it("escopa cache de meus-agendamentos por sessão e invalida chave canônica compartilhada com /historico", async () => {
    const user = userEvent.setup();
    const novo = createAgendamentoFixture({ id: MOCK_AGENDAMENTO_ID });

    server.use(
      handleListarMeusAgendamentosApiV1SchedulingAgendamentosMeGet({ body: [] }),
      handleListarSlotsApiV1SchedulingSlotsGet({ body: MOCK_SLOTS_PSICOLOGIA }),
      handleCriarAgendamentoApiV1SchedulingAgendamentosPost({
        status: 201,
        body: novo,
      }),
    );

    sessionTransport.activatePatientSession({
      token: "token-paciente-a",
      pacienteId: "pac-a",
      role: "PACIENTE",
      tipo: "acolhimento",
    });
    const scopeA = getSessionQueryScope();

    sessionTransport.activatePatientSession({
      token: "token-paciente-b",
      pacienteId: "pac-b",
      role: "PACIENTE",
      tipo: "acolhimento",
    });
    const scopeB = getSessionQueryScope();
    expect(scopeA).not.toBe(scopeB);

    sessionTransport.activatePatientSession({
      token: "token-paciente-a",
      pacienteId: "pac-a",
      role: "PACIENTE",
      tipo: "acolhimento",
    });

    const { findByRole, getByRole, queryClient } = renderWithProviders(
      <ScheduleAppointmentPage initialEspecialidade="PSICOLOGIA" />,
    );

    await findByRole("button", { name: /09:00 às 09:50/i });
    const cacheEntry = queryClient.getQueryCache().find({
      queryKey: [...MEUS_AGENDAMENTOS_QUERY_KEY_PREFIX, scopeA],
    });
    expect(cacheEntry).toBeDefined();

    await user.click(getByRole("button", { name: /09:00 às 09:50/i }));
    await user.click(getByRole("button", { name: /confirmar agendamento/i }));

    await waitFor(() => {
      const updatedState = queryClient.getQueryState([
        ...MEUS_AGENDAMENTOS_QUERY_KEY_PREFIX,
        scopeA,
      ]);
      expect(updatedState?.dataUpdatedAt).toBeGreaterThan(0);
    });
  });
});
