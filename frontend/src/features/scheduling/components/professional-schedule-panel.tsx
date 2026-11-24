import { AlertCircle, CalendarDays, CheckCircle2, Loader2, RefreshCw, Video } from "lucide-react";
import { useState } from "react";
import { getHumanizedErrorMessage } from "@/api/errors";
import type { AgendamentoResponse, DisponibilidadeResponse } from "@/api/generated/types.gen";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  DIAS_SEMANA_OPCOES,
  formatarDataHoraBR,
  formatarDataIso,
  formatarEspecialidadeNome,
  formatarHorarioSlot,
  getStatusBadgeProps,
  isAgendamentoIniciavel,
} from "@/lib/formatters";
import { useAgendaDia, useIniciarAtendimentoAgendado } from "../api/use-agenda-profissional";
import { DisponibilidadeFormDialog } from "./disponibilidade-form-dialog";

export interface ProfessionalSchedulePanelProps {
  onAtendimentoIniciado?: (agendamento: AgendamentoResponse) => void;
}

/**
 * Painel autônomo da agenda programada do profissional de saúde.
 * Exibe os agendamentos do dia com acionamento de teleconsulta e cadastro de disponibilidade.
 */
export function ProfessionalSchedulePanel({
  onAtendimentoIniciado,
}: ProfessionalSchedulePanelProps) {
  const [dataSelecionada, setDataSelecionada] = useState(() => formatarDataIso(new Date()));
  const [iniciandoId, setIniciandoId] = useState<string | null>(null);
  const [feedbackSucesso, setFeedbackSucesso] = useState<string | null>(null);

  const {
    data: agendamentos = [],
    isLoading,
    isFetching,
    error: agendaError,
    refetch,
  } = useAgendaDia({ data: dataSelecionada });

  const { mutate: iniciarAtendimento, error: iniciarError } = useIniciarAtendimentoAgendado();

  const handleIniciarTeleconsulta = (agendamentoId: string) => {
    setFeedbackSucesso(null);
    setIniciandoId(agendamentoId);
    iniciarAtendimento(
      { agendamentoId },
      {
        onSuccess: (updated) => {
          setFeedbackSucesso(
            `Teleconsulta de ${formatarEspecialidadeNome(updated.especialidade)} iniciada.`,
          );
          onAtendimentoIniciado?.(updated);
        },
        onSettled: () => {
          setIniciandoId(null);
        },
      },
    );
  };

  const handleDisponibilidadeCriada = (disp: DisponibilidadeResponse) => {
    const diaLabel =
      DIAS_SEMANA_OPCOES.find((d) => d.valor === disp.dia_semana)?.label ??
      `Dia ${disp.dia_semana}`;
    setFeedbackSucesso(
      `Disponibilidade cadastrada: ${formatarEspecialidadeNome(disp.especialidade)} · ${diaLabel} (${disp.hora_inicio.slice(0, 5)} às ${disp.hora_fim.slice(0, 5)}).`,
    );
  };

  const erroAgenda = agendaError ? getHumanizedErrorMessage(agendaError) : null;
  const erroIniciar = iniciarError ? getHumanizedErrorMessage(iniciarError) : null;

  return (
    <Card className="border-border shadow-sm">
      <CardHeader className="pb-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <CardTitle className="text-lg flex items-center gap-2">
              <CalendarDays className="size-5 text-primary" aria-hidden="true" />
              <span>Agenda Programada do Profissional</span>
            </CardTitle>
            <CardDescription>
              Consulte seus atendimentos agendados por data e gerencie janelas de disponibilidade.
            </CardDescription>
          </div>
          <DisponibilidadeFormDialog onSuccess={handleDisponibilidadeCriada} />
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-end gap-3">
          <div className="space-y-1.5 flex-1 sm:max-w-xs">
            <Label htmlFor="agenda-profissional-data">Data da agenda</Label>
            <Input
              id="agenda-profissional-data"
              type="date"
              value={dataSelecionada}
              onChange={(e) => setDataSelecionada(e.target.value)}
            />
          </div>
          <Button
            type="button"
            variant="secondary"
            onClick={() => void refetch()}
            disabled={isFetching}
            className="min-h-[44px] gap-1.5"
          >
            <RefreshCw
              className={`size-4 ${isFetching ? "animate-spin" : ""}`}
              aria-hidden="true"
            />
            <span>Atualizar Agenda</span>
          </Button>
        </div>

        {feedbackSucesso && (
          <Alert className="border-acr-green/40 bg-acr-green/10 text-foreground">
            <CheckCircle2 className="size-4 text-acr-green" aria-hidden="true" />
            <AlertTitle>Operação realizada</AlertTitle>
            <AlertDescription>{feedbackSucesso}</AlertDescription>
          </Alert>
        )}

        {erroAgenda && (
          <Alert variant="destructive" role="alert">
            <AlertCircle className="size-4" aria-hidden="true" />
            <AlertTitle>{erroAgenda.title}</AlertTitle>
            <AlertDescription>{erroAgenda.detail}</AlertDescription>
          </Alert>
        )}

        {erroIniciar && (
          <Alert variant="destructive" role="alert">
            <AlertCircle className="size-4" aria-hidden="true" />
            <AlertTitle>Não foi possível iniciar a teleconsulta</AlertTitle>
            <AlertDescription>{erroIniciar.detail}</AlertDescription>
          </Alert>
        )}

        {isLoading ? (
          <div
            role="status"
            aria-live="polite"
            className="flex items-center gap-2 py-4 text-sm text-muted-foreground"
          >
            <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            <span>Carregando agenda do dia…</span>
          </div>
        ) : agendamentos.length === 0 && !agendaError ? (
          <div className="rounded-lg border border-dashed border-border p-4 text-center text-sm text-muted-foreground">
            Nenhum agendamento programado para a data selecionada.
          </div>
        ) : (
          <ul className="space-y-3" aria-label="Agenda do dia">
            {agendamentos.map((agendamento) => {
              const statusInfo = getStatusBadgeProps(agendamento.status);
              const podeIniciar = isAgendamentoIniciavel(agendamento.status);
              const isStarting = iniciandoId === agendamento.id;

              return (
                <li
                  key={agendamento.id}
                  className="rounded-xl border border-border bg-card p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                >
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-base font-semibold text-foreground">
                        {formatarEspecialidadeNome(agendamento.especialidade)}
                      </span>
                      <Badge variant={statusInfo.variant}>{statusInfo.label}</Badge>
                    </div>
                    <p className="text-sm text-foreground">
                      {formatarDataHoraBR(agendamento.slot_inicio)} às{" "}
                      {formatarHorarioSlot(agendamento.slot_fim)}
                    </p>
                    {agendamento.observacoes && (
                      <p className="text-xs text-muted-foreground">
                        Observações: {agendamento.observacoes}
                      </p>
                    )}
                  </div>

                  {podeIniciar && (
                    <Button
                      type="button"
                      onClick={() => handleIniciarTeleconsulta(agendamento.id)}
                      disabled={isStarting}
                      className="min-h-[44px] shrink-0 gap-1.5"
                    >
                      {isStarting ? (
                        <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                      ) : (
                        <Video className="size-4" aria-hidden="true" />
                      )}
                      <span>{isStarting ? "Iniciando…" : "Iniciar Teleconsulta Agendada"}</span>
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
