import { AlertCircle, Loader2 } from "lucide-react";
import { startTransition, useMemo, useState } from "react";
import { extractProblemDetail } from "@/api/errors";
import { useMeusAgendamentos } from "@/api/hooks/use-meus-agendamentos";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { usePatientHistory } from "@/features/citizen/api/use-patient-history";
import {
  type FiltroStatus,
  type FiltroTipo,
  HistoryFiltersCard,
} from "@/features/citizen/components/history-filters-card";
import { HistoryRecordsList } from "@/features/citizen/components/history-records-list";
import { CitizenShellLayout } from "@/layouts/citizen-shell-layout";
import { getStoredSession, type StoredPatientSession } from "@/lib/session-storage";

export interface HistoryPageProps {
  session?: StoredPatientSession | null;
}

const FINALIZED_STATUSES = new Set(["FINALIZADO", "CONCLUIDO", "REALIZADO"]);
const CANCELLED_STATUSES = new Set([
  "CANCELADO",
  "CANCELADO_PACIENTE",
  "FALTA",
  "PACIENTE_AUSENTE",
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

  const historyQuery = usePatientHistory();
  const appointmentsQuery = useMeusAgendamentos();

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
    startTransition(() => setFiltroTipo(tipo));
  };

  const handleSelectStatus = (status: FiltroStatus) => {
    startTransition(() => setFiltroStatus(status));
  };

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

        <HistoryFiltersCard
          filtroTipo={filtroTipo}
          filtroStatus={filtroStatus}
          onSelectTipo={handleSelectTipo}
          onSelectStatus={handleSelectStatus}
        />

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

        {!isLoading && !hasError && (
          <HistoryRecordsList paItems={paItems} agendamentoItems={agendamentoItems} />
        )}
      </div>
    </CitizenShellLayout>
  );
}

export default HistoryPage;
