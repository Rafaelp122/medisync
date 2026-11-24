import { AlertCircle, Users } from "lucide-react";
import type { ReactNode } from "react";
import type { AgendamentoResponse } from "@/api/generated/types.gen";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent, CardTitle } from "@/components/ui/card";
import { ConsultationEncounterProvider } from "../context/consultation-encounter-provider";
import { useDoctorWorkstation } from "../hooks/use-doctor-workstation";
import { DoctorWorkstationEncounterGrid } from "./doctor-workstation-encounter-grid";
import { DoctorWorkstationHeader } from "./doctor-workstation-header";

export type SchedulePanelRenderer =
  | ReactNode
  | ((onAtendimentoIniciado: (agendamento: AgendamentoResponse) => void) => ReactNode);

export interface DoctorWorkstationProps {
  medicoId?: string;
  medicoNome?: string;
  crmUf?: string;
  token?: string;
  onLogout?: () => void;
  idleTimeoutMs?: number;
  renderSchedulePanel?: SchedulePanelRenderer;
}

/**
 * Estação de Trabalho Clínica Unificada do Médico (<120L via `ConsultationEncounterProvider`).
 * Remonta o contexto via `key={atendimentoId}` garantindo isolamento total entre pacientes.
 * @see docs/user-stories/US-09-teleconsulta-pep-soap.md
 */
export function DoctorWorkstation({
  medicoId = "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2e",
  medicoNome = "Médico Plantonista",
  crmUf = "Registro pendente",
  token,
  onLogout,
  idleTimeoutMs = 15 * 60 * 1000,
  renderSchedulePanel,
}: DoctorWorkstationProps) {
  const ws = useDoctorWorkstation({
    medicoId,
    medicoNome,
    crmUf,
    token,
    onLogout,
    idleTimeoutMs,
  });

  const scheduleContent =
    typeof renderSchedulePanel === "function"
      ? renderSchedulePanel(ws.handleAgendamentoIniciado)
      : renderSchedulePanel;

  return (
    <div className="w-full flex flex-col gap-4 max-w-[1600px] mx-auto p-2 sm:p-4 text-foreground">
      <DoctorWorkstationHeader
        medicoNome={medicoNome}
        crmUf={crmUf}
        totalPacientesFila={ws.totalPacientesFila}
        isCarregandoPainel={ws.isCarregandoPainel}
        isCallingNext={ws.isCallingNext}
        chamadaIniciadaEm={ws.atendimentoAtivo?.chamadaIniciadaEm}
        ttlSegundos={ws.atendimentoAtivo?.ttlSegundos}
        hasActiveEncounter={Boolean(ws.atendimentoAtivo?.atendimentoId)}
        onChamarProximo={ws.handleChamarProximo}
        onLogout={onLogout}
      />

      {ws.mensagemFilaVazia && (
        <Alert className="py-2.5 text-xs bg-muted/50 border-border">
          <AlertCircle className="size-4 text-muted-foreground" />
          <AlertDescription className="text-xs text-muted-foreground">
            {ws.mensagemFilaVazia}
          </AlertDescription>
        </Alert>
      )}

      {!ws.atendimentoAtivo?.atendimentoId ? (
        <div className="space-y-4">
          <Card className="border-dashed border-2 border-border p-12 text-center bg-card/50">
            <CardContent className="flex flex-col items-center justify-center p-0 space-y-3">
              <div className="size-14 rounded-full bg-muted flex items-center justify-center text-muted-foreground">
                <Users className="size-7" />
              </div>
              <CardTitle className="text-base font-semibold">
                Nenhum atendimento clínico ativo
              </CardTitle>
              <p className="text-xs text-muted-foreground max-w-md">
                A fila virtual está monitorada em tempo real.{" "}
                {ws.totalPacientesFila > 0 ? (
                  <span>
                    Há{" "}
                    <strong>
                      {ws.totalPacientesFila}{" "}
                      {ws.totalPacientesFila === 1 ? "paciente aguardando" : "pacientes aguardando"}
                    </strong>{" "}
                    por atendimento.
                  </span>
                ) : (
                  <span>Não há pacientes aguardando no momento.</span>
                )}{" "}
                Clique em <strong>"Chamar Próximo Paciente"</strong> para alocar o próximo
                atendimento por ordem de prioridade clínica.
              </p>
            </CardContent>
          </Card>

          {scheduleContent}
        </div>
      ) : (
        <ConsultationEncounterProvider
          key={ws.atendimentoAtivo.atendimentoId}
          atendimento={ws.atendimentoAtivo}
        >
          <DoctorWorkstationEncounterGrid livekitData={ws.livekitData} />
        </ConsultationEncounterProvider>
      )}
    </div>
  );
}
