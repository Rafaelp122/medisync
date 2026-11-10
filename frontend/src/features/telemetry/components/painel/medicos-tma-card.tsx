import { UserCheck } from "lucide-react";
import type { TelemetriaPainelResponse } from "@/api/generated/types.gen";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatarTempoEstimado } from "@/lib/formatters";

export interface MedicosTmaCardProps {
  painel?: TelemetriaPainelResponse;
}

/**
 * Card com Desempenho Médico Individual (Volume e TMA por profissional).
 */
export function MedicosTmaCard({ painel }: MedicosTmaCardProps) {
  return (
    <Card className="border-border">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm sm:text-base font-bold text-foreground flex items-center gap-2">
          <UserCheck className="size-4 text-primary" />
          <span>TMA por Médico Plantonista</span>
        </CardTitle>
        <CardDescription className="text-xs text-muted-foreground">
          Volume de atendimentos concluídos e tempo médio individual.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {!painel?.medicos_tma || painel.medicos_tma.length === 0 ? (
          <p className="text-xs text-muted-foreground italic py-4 text-center">
            Nenhum médico com atendimentos concluídos no plantão ativo.
          </p>
        ) : (
          <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
            {painel.medicos_tma.map((med) => (
              <div
                key={med.medico_id}
                className="flex items-center justify-between p-2.5 rounded-lg border border-border bg-card text-xs"
              >
                <div>
                  <span className="font-semibold text-foreground block">{med.nome}</span>
                  <span className="text-[10px] text-muted-foreground">
                    {med.total_atendimentos}{" "}
                    {med.total_atendimentos === 1 ? "atendimento" : "atendimentos"}
                  </span>
                </div>
                <Badge variant="outline" className="font-mono text-xs">
                  TMA: {formatarTempoEstimado(med.tma_segundos)}
                </Badge>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
