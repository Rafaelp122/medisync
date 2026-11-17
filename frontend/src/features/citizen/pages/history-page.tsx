import {
  AlertCircle,
  CalendarClock,
  ClipboardList,
  FileCheck2,
  Loader2,
  Stethoscope,
} from "lucide-react";
import { startTransition, useMemo, useState } from "react";
import { extractProblemDetail } from "@/api/errors";
import { useMeusAgendamentos } from "@/api/hooks/use-meus-agendamentos";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { usePatientHistory } from "@/features/citizen/api/use-patient-history";
import { CitizenShellLayout } from "@/layouts/citizen-shell-layout";
import {
  formatarDataHoraBR,
  formatarEspecialidadeNome,
  getPrioridadeBadgeProps,
  getStatusBadgeProps,
} from "@/lib/formatters";
import { getStoredSession, type StoredPatientSession } from "@/lib/session-storage";

type FiltroTipo = "TODOS" | "PA" | "AGENDAMENTO";
type FiltroStatus = "TODOS" | "FINALIZADO" | "ATIVOS" | "CANCELADO";

export interface HistoryPageProps {
  session?: StoredPatientSession | null;
}

const FINALIZED_STATUSES = new Set(["FINALIZADO", "CONCLUIDO", "REALIZADO"]);
const CANCELLED_STATUSES = new Set([
  "CANCELADO",
  "CANCELADO_PACIENTE",
  "FALTA",
  "NO_SHOW",
  "PACIENTE_AUSENTE",
  "EVADIDO",
]);

function matchesStatusFilter(rawStatus: string, filtro: FiltroStatus): boolean {
  if (filtro === "TODOS") return true;
  const upper = rawStatus.toUpperCase();
  if (filtro === "FINALIZADO") return FINALIZED_STATUSES.has(upper);
  if (filtro === "CANCELADO") return CANCELLED_STATUSES.has(upper);
  return !FINALIZED_STATUSES.has(upper) && !CANCELLED_STATUSES.has(upper);
}

/**
 * Página de Histórico de Consultas do Cidadão (`/historico`).
 * Unifica atendimentos de Pronto-Atendimento Digital (PA) e agendamentos eMulti,
 * com filtragem não-bloqueante via `startTransition` e exibição de CID-10 e conduta.
 */
export function HistoryPage({ session }: HistoryPageProps) {
  const activeSession = session ?? getStoredSession();
  const [filtroTipo, setFiltroTipo] = useState<FiltroTipo>("TODOS");
  const [filtroStatus, setFiltroStatus] = useState<FiltroStatus>("TODOS");

  const historyQuery = usePatientHistory(activeSession?.token);
  const appointmentsQuery = useMeusAgendamentos({ token: activeSession?.token });

  const isLoading = historyQuery.isLoading || appointmentsQuery.isLoading;
  const hasError = historyQuery.isError || appointmentsQuery.isError;
  const errorMessage = hasError
    ? extractProblemDetail(
        historyQuery.error ?? appointmentsQuery.error,
        "Não foi possível carregar o histórico de consultas.",
      )
    : null;

  const paItems = useMemo(() => {
    if (filtroTipo === "AGENDAMENTO") return [];
    return (historyQuery.data ?? []).filter((item) =>
      matchesStatusFilter(item.status, filtroStatus),
    );
  }, [historyQuery.data, filtroTipo, filtroStatus]);

  const agendamentoItems = useMemo(() => {
    if (filtroTipo === "PA") return [];
    return (appointmentsQuery.data ?? []).filter((item) =>
      matchesStatusFilter(item.status, filtroStatus),
    );
  }, [appointmentsQuery.data, filtroTipo, filtroStatus]);

  const handleSelectTipo = (tipo: FiltroTipo) => {
    startTransition(() => {
      setFiltroTipo(tipo);
    });
  };

  const handleSelectStatus = (status: FiltroStatus) => {
    startTransition(() => {
      setFiltroStatus(status);
    });
  };

  const totalExibido = paItems.length + agendamentoItems.length;

  return (
    <CitizenShellLayout session={activeSession}>
      <div className="space-y-5">
        <header className="space-y-1">
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            Histórico de Consultas
          </h1>
          <p className="text-sm text-muted-foreground">
            Acompanhe seus atendimentos no Pronto-Atendimento Digital e consultas agendadas eMulti.
          </p>
        </header>

        {/* Filtros */}
        <Card className="border-border shadow-sm">
          <CardContent className="pt-4 space-y-3">
            <fieldset
              className="flex flex-wrap items-center gap-2 border-0 p-0 m-0"
              aria-label="Filtrar por tipo de consulta"
            >
              <span className="text-xs font-medium text-muted-foreground mr-1">Tipo:</span>
              {(
                [
                  { id: "TODOS", label: "Todos" },
                  { id: "PA", label: "Pronto-Atendimento" },
                  { id: "AGENDAMENTO", label: "Agendamentos eMulti" },
                ] as const
              ).map((opt) => (
                <Button
                  key={opt.id}
                  type="button"
                  size="sm"
                  variant={filtroTipo === opt.id ? "default" : "outline"}
                  aria-pressed={filtroTipo === opt.id}
                  onClick={() => handleSelectTipo(opt.id)}
                  className="min-h-[44px] px-3"
                >
                  {opt.label}
                </Button>
              ))}
            </fieldset>

            <fieldset
              className="flex flex-wrap items-center gap-2 border-0 p-0 m-0"
              aria-label="Filtrar por status"
            >
              <span className="text-xs font-medium text-muted-foreground mr-1">Status:</span>
              {(
                [
                  { id: "TODOS", label: "Todos" },
                  { id: "FINALIZADO", label: "Finalizados" },
                  { id: "ATIVOS", label: "Em Andamento / Agendados" },
                  { id: "CANCELADO", label: "Cancelados" },
                ] as const
              ).map((opt) => (
                <Button
                  key={opt.id}
                  type="button"
                  size="sm"
                  variant={filtroStatus === opt.id ? "default" : "outline"}
                  aria-pressed={filtroStatus === opt.id}
                  onClick={() => handleSelectStatus(opt.id)}
                  className="min-h-[44px] px-3"
                >
                  {opt.label}
                </Button>
              ))}
            </fieldset>
          </CardContent>
        </Card>

        {isLoading && (
          <div
            role="status"
            aria-live="polite"
            className="flex items-center justify-center gap-2 rounded-xl border border-border bg-card p-8 text-sm text-muted-foreground"
          >
            <Loader2 className="h-4 w-4 animate-spin text-primary" aria-hidden="true" />
            <span>Carregando histórico assistencial…</span>
          </div>
        )}

        {hasError && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" aria-hidden="true" />
            <AlertTitle>Erro ao carregar histórico</AlertTitle>
            <AlertDescription>{errorMessage}</AlertDescription>
          </Alert>
        )}

        {!isLoading && !hasError && totalExibido === 0 && (
          <Card className="border-dashed border-border">
            <CardContent className="py-10 text-center space-y-2 text-muted-foreground">
              <ClipboardList className="h-8 w-8 mx-auto opacity-60" aria-hidden="true" />
              <p className="text-sm font-medium text-foreground">
                Nenhuma consulta encontrada para os filtros selecionados.
              </p>
              <p className="text-xs">
                Seus atendimentos digitais e agendamentos concluídos aparecerão aqui.
              </p>
            </CardContent>
          </Card>
        )}

        {/* Lista de Atendimentos de Pronto-Atendimento */}
        {paItems.length > 0 && (
          <section aria-label="Atendimentos de Pronto-Atendimento" className="space-y-3">
            <h2 className="text-base font-semibold text-foreground flex items-center gap-2">
              <Stethoscope className="h-4 w-4 text-primary" aria-hidden="true" />
              <span>Pronto-Atendimento Digital ({paItems.length})</span>
            </h2>
            <div className="space-y-3">
              {paItems.map((item) => {
                const prioridade = getPrioridadeBadgeProps(item.prioridade_clinica);
                const statusBadge = getStatusBadgeProps(item.status);
                return (
                  <Card key={item.atendimento_id} className="border-border shadow-sm">
                    <CardHeader className="pb-2">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div className="space-y-1">
                          <CardTitle className="text-base">
                            {item.queixa_principal || "Atendimento de Pronto-Atendimento"}
                          </CardTitle>
                          <CardDescription className="text-xs">
                            Iniciado em {formatarDataHoraBR(item.criado_em)}
                            {item.finalizado_em
                              ? ` · Finalizado em ${formatarDataHoraBR(item.finalizado_em)}`
                              : ""}
                          </CardDescription>
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          <Badge variant={prioridade.variant}>{prioridade.label}</Badge>
                          <Badge variant={statusBadge.variant}>{statusBadge.label}</Badge>
                        </div>
                      </div>
                    </CardHeader>
                    {(item.diagnostico_cid10 || item.conduta_resumo) && (
                      <CardContent className="pt-2 space-y-2 text-xs">
                        <div className="rounded-lg border border-border bg-muted/30 p-3 space-y-1.5">
                          {item.diagnostico_cid10 && (
                            <p className="font-semibold text-foreground flex items-center gap-1.5">
                              <FileCheck2 className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
                              <span>CID-10: {item.diagnostico_cid10}</span>
                            </p>
                          )}
                          {item.conduta_resumo && (
                            <p className="text-muted-foreground">
                              <strong className="text-foreground">Resumo da conduta:</strong>{" "}
                              {item.conduta_resumo}
                            </p>
                          )}
                        </div>
                      </CardContent>
                    )}
                  </Card>
                );
              })}
            </div>
          </section>
        )}

        {/* Lista de Agendamentos Multiprofissionais eMulti */}
        {agendamentoItems.length > 0 && (
          <section aria-label="Consultas Agendadas eMulti" className="space-y-3">
            <h2 className="text-base font-semibold text-foreground flex items-center gap-2">
              <CalendarClock className="h-4 w-4 text-primary" aria-hidden="true" />
              <span>Consultas Agendadas eMulti ({agendamentoItems.length})</span>
            </h2>
            <div className="space-y-3">
              {agendamentoItems.map((ag) => {
                const statusBadge = getStatusBadgeProps(ag.status);
                return (
                  <Card key={ag.id} className="border-border shadow-sm">
                    <CardHeader className="pb-2">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div className="space-y-1">
                          <CardTitle className="text-base">
                            {formatarEspecialidadeNome(ag.especialidade)}
                          </CardTitle>
                          <CardDescription className="text-xs">
                            Horário: {formatarDataHoraBR(ag.slot_inicio)} até{" "}
                            {formatarDataHoraBR(ag.slot_fim)}
                          </CardDescription>
                        </div>
                        <Badge variant={statusBadge.variant}>{statusBadge.label}</Badge>
                      </div>
                    </CardHeader>
                    {ag.observacoes && (
                      <CardContent className="pt-1 text-xs text-muted-foreground">
                        Observações: {ag.observacoes}
                      </CardContent>
                    )}
                  </Card>
                );
              })}
            </div>
          </section>
        )}
      </div>
    </CitizenShellLayout>
  );
}

export default HistoryPage;
