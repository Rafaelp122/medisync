import { CheckCircle2, ShieldAlert } from "lucide-react";
import type { TelemetriaPainelResponse } from "@/api/generated/types.gen";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatarTempoEstimado } from "@/lib/formatters";

export interface AcrTriageDistributionGridProps {
  painel?: TelemetriaPainelResponse;
}

/**
 * Grid de Distribuição por Prioridade Clínica ACR SUS (Portaria GM/MS nº 2.048/2002).
 */
export function AcrTriageDistributionGrid({ painel }: AcrTriageDistributionGridProps) {
  const slaCompliance = painel?.sla_compliance_percentual ?? 100;
  const slaOk = painel?.sla_em_conformidade ?? true;

  return (
    <Card className="border-border">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="space-y-0.5">
            <CardTitle className="text-sm sm:text-base font-bold text-foreground">
              Distribuição da Fila e Tempo Médio de Espera (TME) por ACR SUS
            </CardTitle>
            <CardDescription className="text-xs text-muted-foreground">
              Classificação de Risco Oficial conforme Portaria GM/MS nº 2.048/2002 e Parecer CREMESP
              nº 278.262/2023.
            </CardDescription>
          </div>
          <Badge
            variant={slaOk ? "success" : "destructive"}
            className="text-xs py-0.5 px-2.5 gap-1 shrink-0"
            data-testid="badge-sla-geral"
          >
            {slaOk ? <CheckCircle2 className="size-3" /> : <ShieldAlert className="size-3" />}
            <span>SLA Geral: {slaCompliance.toFixed(1)}%</span>
          </Badge>
        </div>
      </CardHeader>

      <CardContent>
        <div className="grid grid-cols-1 sm:grid-cols-5 gap-3">
          {/* Vermelho */}
          <div className="p-3 rounded-lg border border-acr-red/30 bg-acr-red/5 space-y-1 text-center">
            <Badge variant="nivel1" className="text-[11px] mb-1">
              Vermelho
            </Badge>
            <p className="text-[11px] font-semibold text-foreground">
              Emergência Imediata (SAMU 192)
            </p>
            <div className="pt-1 border-t border-acr-red/20 text-xs">
              <span className="text-muted-foreground block text-[10px]">TME Atual:</span>
              <strong className="text-foreground">
                {formatarTempoEstimado(painel?.tme_nivel_1_segundos ?? 0)}
              </strong>
            </div>
          </div>

          {/* Laranja */}
          <div className="p-3 rounded-lg border border-acr-orange/30 bg-acr-orange/5 space-y-1 text-center">
            <Badge variant="nivel2" className="text-[11px] mb-1">
              Laranja
            </Badge>
            <p className="text-[11px] font-semibold text-foreground">Muito Urgente</p>
            <div className="pt-1 border-t border-acr-orange/20 text-xs">
              <span className="text-muted-foreground block text-[10px]">TME Atual:</span>
              <strong className="text-foreground">
                {formatarTempoEstimado(painel?.tme_nivel_2_segundos ?? 0)}
              </strong>
            </div>
          </div>

          {/* Amarelo */}
          <div className="p-3 rounded-lg border border-acr-yellow/30 bg-acr-yellow/5 space-y-1 text-center">
            <Badge variant="nivel3" className="text-[11px] mb-1">
              Amarelo
            </Badge>
            <p className="text-[11px] font-semibold text-foreground">Urgente</p>
            <div className="pt-1 border-t border-acr-yellow/20 text-xs">
              <span className="text-muted-foreground block text-[10px]">TME Atual:</span>
              <strong className="text-foreground">
                {formatarTempoEstimado(painel?.tme_nivel_3_segundos ?? 0)}
              </strong>
            </div>
          </div>

          {/* Verde */}
          <div className="p-3 rounded-lg border border-acr-green/30 bg-acr-green/5 space-y-1 text-center">
            <Badge variant="nivel4" className="text-[11px] mb-1">
              Verde
            </Badge>
            <p className="text-[11px] font-semibold text-foreground">Pouco Urgente</p>
            <div className="pt-1 border-t border-acr-green/20 text-xs">
              <span className="text-muted-foreground block text-[10px]">TME Atual:</span>
              <strong className="text-foreground">
                {formatarTempoEstimado(painel?.tme_nivel_4_segundos ?? 0)}
              </strong>
            </div>
          </div>

          {/* Azul */}
          <div className="p-3 rounded-lg border border-acr-blue/30 bg-acr-blue/5 space-y-1 text-center">
            <Badge variant="nivel5" className="text-[11px] mb-1">
              Azul
            </Badge>
            <p className="text-[11px] font-semibold text-foreground">Não Urgente</p>
            <div className="pt-1 border-t border-acr-blue/20 text-xs">
              <span className="text-muted-foreground block text-[10px]">TME Atual:</span>
              <strong className="text-foreground">
                {formatarTempoEstimado(painel?.tme_nivel_5_segundos ?? 0)}
              </strong>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
