import { TrendingDown } from "lucide-react";
import type { TelemetriaPainelResponse } from "@/api/generated/types.gen";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export interface TaxasOperacionaisCardProps {
  painel?: TelemetriaPainelResponse;
}

/**
 * Card com Indicadores de Evasão Voluntária e No-Show em 45s (RN02).
 */
export function TaxasOperacionaisCard({ painel }: TaxasOperacionaisCardProps) {
  return (
    <Card className="border-border">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm sm:text-base font-bold text-foreground flex items-center gap-2">
          <TrendingDown className="size-4 text-primary" />
          <span>Taxas de Desistência e Ausência (No-Show)</span>
        </CardTitle>
        <CardDescription className="text-xs text-muted-foreground">
          Indicadores de evasão e abstenção após convocação de 45 segundos (RN02).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center justify-between p-3 bg-muted/40 rounded-lg border border-border">
          <div>
            <span className="text-xs font-semibold text-foreground block">
              Taxa de No-Show (Ausência na Chamada)
            </span>
            <span className="text-[11px] text-muted-foreground">
              Pacientes que não atenderam ao ring em 45s
            </span>
          </div>
          <span data-testid="taxa-no-show" className="text-lg font-bold text-foreground">
            {painel ? `${(painel.no_show_rate * 100).toFixed(1)}%` : "0.0%"}
          </span>
        </div>

        <div className="flex items-center justify-between p-3 bg-muted/40 rounded-lg border border-border">
          <div>
            <span className="text-xs font-semibold text-foreground block">
              Taxa de Evasão (Desistência Voluntária)
            </span>
            <span className="text-[11px] text-muted-foreground">
              Cancelamento voluntário pelo paciente enquanto em espera
            </span>
          </div>
          <span data-testid="taxa-evasao" className="text-lg font-bold text-foreground">
            {painel ? `${(painel.evasao_rate * 100).toFixed(1)}%` : "0.0%"}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
