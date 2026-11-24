import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export type FiltroTipo = "TODOS" | "PA" | "AGENDAMENTO";
export type FiltroStatus = "TODOS" | "FINALIZADO" | "ATIVOS" | "CANCELADO";

const TIPO_OPTIONS: ReadonlyArray<{ id: FiltroTipo; label: string }> = [
  { id: "TODOS", label: "Todos" },
  { id: "PA", label: "Pronto-Atendimento" },
  { id: "AGENDAMENTO", label: "Agendamentos eMulti" },
];

const STATUS_OPTIONS: ReadonlyArray<{ id: FiltroStatus; label: string }> = [
  { id: "TODOS", label: "Todos" },
  { id: "FINALIZADO", label: "Finalizados" },
  { id: "ATIVOS", label: "Em Andamento / Agendados" },
  { id: "CANCELADO", label: "Cancelados" },
];

export interface HistoryFiltersCardProps {
  filtroTipo: FiltroTipo;
  filtroStatus: FiltroStatus;
  onSelectTipo: (tipo: FiltroTipo) => void;
  onSelectStatus: (status: FiltroStatus) => void;
}

export function HistoryFiltersCard({
  filtroTipo,
  filtroStatus,
  onSelectTipo,
  onSelectStatus,
}: HistoryFiltersCardProps) {
  return (
    <Card className="border-border shadow-sm">
      <CardContent className="pt-4 space-y-3">
        <fieldset
          className="flex flex-wrap items-center gap-2 border-0 p-0 m-0"
          aria-label="Filtrar por tipo de consulta"
        >
          <span className="text-xs font-medium text-muted-foreground mr-1">Tipo:</span>
          {TIPO_OPTIONS.map((opt) => (
            <Button
              key={opt.id}
              type="button"
              size="sm"
              variant={filtroTipo === opt.id ? "default" : "outline"}
              aria-pressed={filtroTipo === opt.id}
              onClick={() => onSelectTipo(opt.id)}
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
          {STATUS_OPTIONS.map((opt) => (
            <Button
              key={opt.id}
              type="button"
              size="sm"
              variant={filtroStatus === opt.id ? "default" : "outline"}
              aria-pressed={filtroStatus === opt.id}
              onClick={() => onSelectStatus(opt.id)}
              className="min-h-[44px] px-3"
            >
              {opt.label}
            </Button>
          ))}
        </fieldset>
      </CardContent>
    </Card>
  );
}
