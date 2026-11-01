import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatarPosicaoOrdinal, formatarTempoEstimado } from "@/lib/formatters";
import { cn } from "@/lib/utils";

export interface QueuePositionCardProps {
  atendimentoId?: string;
  posicao: number | null | undefined;
  totalAguardando: number | null | undefined;
  tempoEstimadoSegundos: number | null | undefined;
  prioridadeClinica?: number | null;
  status?: string | null;
  className?: string;
}

const PRIORIDADE_LABELS: Record<
  number,
  { label: string; variant: "nivel1" | "nivel2" | "nivel3" | "nivel4" | "nivel5" }
> = {
  1: { label: "Nível 1 — Emergência (Vermelho)", variant: "nivel1" },
  2: { label: "Nível 2 — Muito Urgente (Laranja)", variant: "nivel2" },
  3: { label: "Nível 3 — Urgente (Amarelo)", variant: "nivel3" },
  4: { label: "Nível 4 — Pouco Urgente (Verde)", variant: "nivel4" },
  5: { label: "Nível 5 — Não Urgente (Azul)", variant: "nivel5" },
};

export function QueuePositionCard({
  atendimentoId,
  posicao,
  totalAguardando,
  tempoEstimadoSegundos,
  prioridadeClinica,
  status,
  className,
}: QueuePositionCardProps) {
  const [copiado, setCopiado] = useState(false);
  const prioridadeInfo = prioridadeClinica ? PRIORIDADE_LABELS[prioridadeClinica] : null;

  const handleCopyId = () => {
    if (!atendimentoId) return;
    try {
      if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
        navigator.clipboard.writeText(atendimentoId).catch(() => {});
      }
    } catch {}
    setCopiado(true);
    setTimeout(() => setCopiado(false), 2000);
  };

  return (
    <Card className={cn("w-full shadow-md border-border/80 text-left", className)}>
      <CardHeader className="pb-3 space-y-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-xl sm:text-2xl font-bold text-foreground">
            Sua Posição na Fila
          </CardTitle>
          {prioridadeInfo && (
            <Badge variant={prioridadeInfo.variant} className="text-xs px-2.5 py-1">
              {prioridadeInfo.label}
            </Badge>
          )}
        </div>
        <CardDescription className="text-xs sm:text-sm text-muted-foreground">
          {status === "TRIADO_AGUARDANDO_ELEGIBILIDADE"
            ? "Triagem concluída. Validando elegibilidade em segundo plano."
            : status === "APTO_PARA_CHAMADA"
              ? "Atendimento apto e priorizado conforme gravidade clínica."
              : "Acompanhe seu andamento em tempo real."}
        </CardDescription>

        {atendimentoId && (
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1.5 p-2.5 bg-muted/60 rounded-lg border border-border text-xs">
            <span className="text-muted-foreground font-medium text-[11px] sm:text-xs">
              Atendimento ID:
            </span>
            <div className="flex items-center gap-2">
              <code
                data-testid="atendimento-id-completo"
                className="font-mono text-[11px] sm:text-xs font-bold text-foreground select-all break-all sm:break-normal"
              >
                {atendimentoId}
              </code>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={handleCopyId}
                className="h-6 px-2 text-[10px] shrink-0 text-muted-foreground hover:text-foreground"
                aria-label="Copiar ID do atendimento"
              >
                {copiado ? "Copiado!" : "Copiar"}
              </Button>
            </div>
          </div>
        )}
      </CardHeader>

      <CardContent className="space-y-4">
        <section
          aria-label="Posição e estimativa de espera"
          aria-live="polite"
          aria-atomic="true"
          className="grid grid-cols-1 sm:grid-cols-2 gap-3"
        >
          <div className="p-4 bg-primary/5 rounded-xl border border-primary/15 text-center">
            <span className="text-xs font-semibold text-primary uppercase tracking-wider block mb-1">
              Posição Atual
            </span>
            <span
              data-testid="posicao-ordinal"
              className="text-3xl sm:text-4xl font-extrabold text-primary block"
            >
              {formatarPosicaoOrdinal(posicao)}
            </span>
            <span className="text-xs text-muted-foreground mt-1 block">
              {totalAguardando && totalAguardando > 0
                ? `De um total de ${totalAguardando} ${totalAguardando === 1 ? "paciente" : "pacientes"}`
                : "Aguardando próxima chamada"}
            </span>
          </div>

          <div className="p-4 bg-muted/60 rounded-xl border border-border text-center">
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider block mb-1">
              Tempo Estimado de Espera
            </span>
            <span
              data-testid="tempo-estimado"
              className="text-lg sm:text-xl font-bold text-foreground block my-1"
            >
              {formatarTempoEstimado(tempoEstimadoSegundos)}
            </span>
            <span className="text-xs text-muted-foreground block">
              Calculado pelo TMA dos médicos ativos
            </span>
          </div>
        </section>
      </CardContent>
    </Card>
  );
}
