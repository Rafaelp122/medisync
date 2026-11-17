import { AlertCircle, Calendar, Clock, Loader2 } from "lucide-react";
import { getHumanizedErrorMessage, type ProblemDetailsError } from "@/api/errors";
import type { SlotDisponivelResponse } from "@/api/generated/types.gen";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatarDataBR, formatarEspecialidadeNome, formatarHorarioSlot } from "@/lib/formatters";
import { cn } from "@/lib/utils";
import { validarPeriodoSlots } from "../schemas/scheduling-schema";

export interface SlotPickerProps {
  especialidade: string;
  dataInicio: string;
  dataFim: string;
  onChangePeriodo: (dataInicio: string, dataFim: string) => void;
  slots: SlotDisponivelResponse[];
  selectedSlot: SlotDisponivelResponse | null;
  onSelectSlot: (slot: SlotDisponivelResponse) => void;
  isLoading?: boolean;
  error?: ProblemDetailsError | null;
  onRetry?: () => void;
}

function buildSlotKey(slot: SlotDisponivelResponse): string {
  return `${slot.profissional_id}::${slot.slot_inicio}`;
}

/**
 * Seletor de período e grade acessível de horários livres para agendamento.
 * Garante alvos de toque >= 44x44px e contraste WCAG 2.1 AA.
 */
export function SlotPicker({
  especialidade,
  dataInicio,
  dataFim,
  onChangePeriodo,
  slots,
  selectedSlot,
  onSelectSlot,
  isLoading = false,
  error = null,
  onRetry,
}: SlotPickerProps) {
  const erroPeriodo = validarPeriodoSlots(dataInicio, dataFim);
  const erroHumanizado = error ? getHumanizedErrorMessage(error) : null;
  const selectedKey = selectedSlot ? buildSlotKey(selectedSlot) : null;

  const slotsPorData = slots.reduce<Record<string, SlotDisponivelResponse[]>>((acc, slot) => {
    const dataLabel = formatarDataBR(slot.slot_inicio);
    const grupo = acc[dataLabel] ?? [];
    grupo.push(slot);
    acc[dataLabel] = grupo;
    return acc;
  }, {});

  return (
    <Card className="border-border shadow-sm">
      <CardHeader className="pb-3">
        <CardTitle className="text-lg flex items-center gap-2">
          <Calendar className="size-5 text-primary" aria-hidden="true" />
          <span>2. Escolha a Data e o Horário</span>
        </CardTitle>
        <CardDescription>
          {especialidade
            ? `Consultando horários disponíveis para ${formatarEspecialidadeNome(especialidade)}.`
            : "Selecione primeiro uma especialidade para visualizar os horários."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="slot-data-inicio">Data inicial</Label>
            <Input
              id="slot-data-inicio"
              type="date"
              value={dataInicio}
              onChange={(e) => onChangePeriodo(e.target.value, dataFim)}
              disabled={!especialidade}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="slot-data-fim">Data final</Label>
            <Input
              id="slot-data-fim"
              type="date"
              value={dataFim}
              min={dataInicio}
              onChange={(e) => onChangePeriodo(dataInicio, e.target.value)}
              disabled={!especialidade}
            />
          </div>
        </div>

        {erroPeriodo && especialidade && (
          <Alert variant="destructive" role="alert">
            <AlertCircle className="size-4" aria-hidden="true" />
            <AlertTitle>Período inválido</AlertTitle>
            <AlertDescription>{erroPeriodo}</AlertDescription>
          </Alert>
        )}

        {erroHumanizado && (
          <Alert variant="destructive" role="alert">
            <AlertCircle className="size-4" aria-hidden="true" />
            <AlertTitle>{erroHumanizado.title}</AlertTitle>
            <AlertDescription className="flex flex-col sm:flex-row sm:items-center gap-2">
              <span>{erroHumanizado.detail}</span>
              {onRetry && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={onRetry}
                  className="min-h-[44px]"
                >
                  Tentar novamente
                </Button>
              )}
            </AlertDescription>
          </Alert>
        )}

        {!especialidade ? (
          <p className="text-sm text-muted-foreground py-2">
            Selecione uma especialidade acima para carregar os horários livres.
          </p>
        ) : isLoading ? (
          <div
            role="status"
            aria-live="polite"
            className="flex items-center gap-2 py-4 text-sm text-muted-foreground"
          >
            <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            <span>Buscando horários disponíveis…</span>
          </div>
        ) : !erroPeriodo && !error && slots.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border p-4 text-center text-sm text-muted-foreground">
            Nenhum horário disponível para {formatarEspecialidadeNome(especialidade)} neste período.
            Tente ampliar as datas.
          </div>
        ) : (
          <div className="space-y-4">
            {Object.entries(slotsPorData).map(([dataLabel, grupoSlots]) => (
              <div key={dataLabel} className="space-y-2">
                <h3 className="text-sm font-semibold text-foreground">{dataLabel}</h3>
                <fieldset
                  aria-label={`Horários disponíveis em ${dataLabel}`}
                  className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2.5 border-0 p-0 m-0"
                >
                  {grupoSlots.map((slot) => {
                    const key = buildSlotKey(slot);
                    const isSelected = selectedKey === key;
                    const horaInicio = formatarHorarioSlot(slot.slot_inicio);
                    const horaFim = formatarHorarioSlot(slot.slot_fim);

                    return (
                      <button
                        key={key}
                        type="button"
                        aria-pressed={isSelected}
                        aria-label={`${dataLabel} das ${horaInicio} às ${horaFim} (${slot.duracao_minutos} minutos)`}
                        onClick={() => onSelectSlot(slot)}
                        className={cn(
                          "min-h-[44px] min-w-[44px] flex flex-col items-center justify-center rounded-lg border px-3 py-2 text-sm font-medium transition-[border-color,background-color,box-shadow] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                          isSelected
                            ? "border-primary bg-primary text-primary-foreground shadow-xs"
                            : "border-input bg-background text-foreground hover:border-primary/60 hover:bg-muted/40",
                        )}
                      >
                        <span className="inline-flex items-center gap-1.5 font-semibold">
                          <Clock className="size-3.5" aria-hidden="true" />
                          <span>
                            {horaInicio} - {horaFim}
                          </span>
                        </span>
                        <span
                          className={cn(
                            "text-xs mt-0.5",
                            isSelected ? "text-primary-foreground/90" : "text-muted-foreground",
                          )}
                        >
                          {slot.duracao_minutos} min
                        </span>
                      </button>
                    );
                  })}
                </fieldset>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
