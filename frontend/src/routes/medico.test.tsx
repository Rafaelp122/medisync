import { createMemoryHistory } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { beforeAll, beforeEach, describe, expect, it } from "vitest";
import { App } from "@/App";
import {
  handleGenerateTeleconsultaRoomTokenApiV1ConsultationsAtendimentoIdLivekitTokenPost,
  handleIniciarAtendimentoAgendadoApiV1SchedulingAgendamentosAgendamentoIdIniciarPost,
  handleListarAgendaDiaApiV1SchedulingAgendaDiaGet,
  handleObterEvolucaoSoapApiV1ConsultationsAtendimentoIdSoapGet,
  handleObterPainelTelemetriaApiV1TelemetriaPainelGet,
  handleObterProntuarioProtegidoApiV1ConsultationsAtendimentoIdProntuarioGet,
  handleObterTmaStatusApiV1ConsultationsAtendimentoIdTmaStatusGet,
} from "@/api/generated/msw.gen";
import { saveStoredDoctorSession } from "@/lib/session-storage";
import { server } from "@/mocks/server";
import { createAppRouter } from "@/router";

const MEDICO_ID = "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2e";
const AGENDAMENTO_ID = "018f3a5b-5555-4b2c-8b2c-018f3a5b5555";
const ATENDIMENTO_ID = "018f3a5b-6666-4b2c-8b2c-018f3a5b6666";
const PACIENTE_ID = "018f3a5b-7777-4b2c-8b2c-018f3a5b7777";

function buildStaffJwt(papel: string): string {
  const encode = (obj: unknown) => btoa(JSON.stringify(obj)).replace(/=/g, "");
  return `${encode({ alg: "HS256", typ: "JWT" })}.${encode({ sub: MEDICO_ID, papel })}.sig`;
}

describe("Rota /medico + Agenda Programada + DoctorWorkstation", () => {
  beforeAll(async () => {
    await import("@/features/consultation/components/livekit-media-adapter");
  });

  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  it("IT-ROUTE-MED-01: Clicar em 'Iniciar Teleconsulta Agendada' em /medico abre sala LiveKit e PEP", async () => {
    saveStoredDoctorSession({
      medicoId: MEDICO_ID,
      medicoNome: "Dra. Beatriz Alencar",
      crmUf: "54321/DF",
      identificador: "54321/DF",
      papel: "MEDICO",
    });

    const agendamentoBase = {
      id: AGENDAMENTO_ID,
      paciente_id: PACIENTE_ID,
      profissional_id: MEDICO_ID,
      especialidade: "PSICOLOGIA",
      slot_inicio: "2026-11-24T14:00:00Z",
      slot_fim: "2026-11-24T14:50:00Z",
      status: "AGENDADO",
      observacoes: "Sessão inicial eMulti agendada",
      atendimento_id: null,
      criado_em: "2026-11-20T10:00:00Z",
      atualizado_em: "2026-11-20T10:00:00Z",
    };

    server.use(
      handleObterPainelTelemetriaApiV1TelemetriaPainelGet({
        body: {
          gerado_em: "2026-11-24T14:00:00Z",
          tme_medio_segundos: 120,
          tme_nivel_1_segundos: 0,
          tme_nivel_2_segundos: 60,
          tme_nivel_3_segundos: 180,
          tme_nivel_4_segundos: 240,
          tme_nivel_5_segundos: 300,
          tma_medio_segundos: 600,
          medicos_tma: [],
          no_show_rate: 0.05,
          evasao_rate: 0.02,
          sla_compliance_percentual: 98.5,
          sla_em_conformidade: true,
          medicos_ativos_count: 1,
          total_pacientes_fila: 0,
          total_atendimentos: 10,
        },
      }),
      handleListarAgendaDiaApiV1SchedulingAgendaDiaGet({
        body: [agendamentoBase],
      }),
      handleIniciarAtendimentoAgendadoApiV1SchedulingAgendamentosAgendamentoIdIniciarPost(() =>
        HttpResponse.json({
          ...agendamentoBase,
          status: "EM_ATENDIMENTO",
          atendimento_id: ATENDIMENTO_ID,
          atualizado_em: new Date().toISOString(),
        }),
      ),
      handleGenerateTeleconsultaRoomTokenApiV1ConsultationsAtendimentoIdLivekitTokenPost({
        body: {
          token: "lk-scheduled-room-token",
          room_name: `room_${ATENDIMENTO_ID}`,
          participant_identity: `medico_${MEDICO_ID}`,
          server_url: "wss://livekit.medisync.local",
          expires_in: 3600,
        },
      }),
      handleObterProntuarioProtegidoApiV1ConsultationsAtendimentoIdProntuarioGet({
        body: {
          atendimento_id: ATENDIMENTO_ID,
          is_finalizado: false,
          evolucao: null,
          documentos: [],
        },
      }),
      handleObterEvolucaoSoapApiV1ConsultationsAtendimentoIdSoapGet({
        body: {
          id: "018f3a5b-4444-4b2c-8b2c-018f3a5b4444",
          atendimento_id: ATENDIMENTO_ID,
          medico_id: MEDICO_ID,
          anamnese: "",
          exame_fisico_virtual: "",
          cid10_principal: "",
          conduta: "",
          registrado_em: "2026-11-24T14:00:00Z",
          is_finalizado: false,
        },
      }),
      handleObterTmaStatusApiV1ConsultationsAtendimentoIdTmaStatusGet({
        body: {
          atendimento_id: ATENDIMENTO_ID,
          tempo_decorrido_segundos: 10,
          tma_planejado_segundos: 900,
          excedeu_tma: false,
          aviso_visual: "Dentro do SLA.",
        },
      }),
    );

    const { setAccessToken } = await import("@/lib/auth-token");
    setAccessToken(buildStaffJwt("MEDICO"));

    const history = createMemoryHistory({ initialEntries: ["/medico"] });
    const router = createAppRouter(history);
    render(<App customRouter={router} />);

    const iniciarBtn = await screen.findByRole("button", {
      name: /iniciar teleconsulta agendada/i,
    });
    const user = userEvent.setup();
    await user.click(iniciarBtn);

    await waitFor(() => {
      expect(screen.getByText(/livekit sfu conectado/i)).toBeInTheDocument();
      expect(screen.getByText(/sessão inicial emulti agendada/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/subjetivo \(s\)/i)).toBeInTheDocument();
    });
  });
});
