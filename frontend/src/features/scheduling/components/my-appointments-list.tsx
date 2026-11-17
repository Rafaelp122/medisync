import { AlertCircle, CalendarCheck2, Loader2, XCircle } from "lucide-react";
import { getHumanizedErrorMessage, type ProblemDetailsError } from "@/api/errors";
import type { AgendamentoResponse } from "@/api/generated/types.gen";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  formatarDataHoraBR,
  formatarEspecialidadeNome,
  formatarHorarioSlot,
  getStatusBadgeProps,
  isAgendamentoCancelavel,
} from "@/lib/formatters";

export interface MyAppointmentsListProps {
  agendamentos: AgendamentoResponse[];
  isLoading?: boolean;
  error?: ProblemDetailsError | null;
  cancellingId?: string | null;
  cancelError?: ProblemDetailsError | null;
  onCancelar: (agendamentoId: string) => void;
}

/**
 * Lista de agendamentos do paciente autenticado com ação de cancelamento acessível.
 */
export function MyAppointmentsList({
  agendamentos,
  isLoading = false,
  error = null,
  cancellingId = null,
  cancelError = null,
  onCancelar,
}: MyAppointmentsListProps) {
  const erroLista = error ? getHumanizedErrorMessage(error) : null;
  const erroCancelamento = cancelError ? getHumanizedErrorMessage(cancelError) : null;

  return (
    <Card className="border-border shadow-sm">
      <CardHeader className="pb-3">
        <CardTitle className="text-lg flex items-center gap-2">
          <CalendarCheck2 className="size-5 text-primary" aria-hidden="true" />
          <span>Meus Agendamentos</span>
        </CardTitle>
        <CardDescription>
          Acompanhe suas consultas agendadas ou realize o cancelamento quando necessário.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {erroLista && (
          <Alert variant="destructive" role="alert">
            <AlertCircle className="size-4" aria-hidden="true" />
            <AlertTitle>{erroLista.title}</AlertTitle>
            <AlertDescription>{erroLista.detail}</AlertDescription>
          </Alert>
        )}

        {erroCancelamento && (
          <Alert variant="destructive" role="alert">
            <AlertCircle className="size-4" aria-hidden="true" />
            <AlertTitle>Não foi possível cancelar o agendamento</AlertTitle>
            <AlertDescription>{erroCancelamento.detail}</AlertDescription>
          </Alert>
        )}

        {isLoading ? (
          <div
            role="status"
            aria-live="polite"
            className="flex items-center gap-2 py-4 text-sm text-muted-foreground"
          >
            <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            <span>Carregando seus agendamentos…</span>
          </div>
        ) : agendamentos.length === 0 ? (
          <p className="text-sm text-muted-foreground py-2">
            Você ainda não possui consultas agendadas.
          </p>
        ) : (
          <ul className="space-y-3" aria-label="Lista de agendamentos">
            {agendamentos.map((agendamento) => {
              const statusInfo = getStatusBadgeProps(agendamento.status);
              const podeCancelar = isAgendamentoCancelavel(agendamento.status);
              const isCancelling = cancellingId === agendamento.id;

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

                  {podeCancelar && (
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => onCancelar(agendamento.id)}
                      disabled={isCancelling}
                      className="min-h-[44px] shrink-0 gap-1.5 border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive"
                    >
                      {isCancelling ? (
                        <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                      ) : (
                        <XCircle className="size-4" aria-hidden="true" />
                      )}
                      <span>{isCancelling ? "Cancelando…" : "Cancelar Agendamento"}</span>
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
