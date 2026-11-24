import { Activity, AlertTriangle, Clock, UserCheck, Users } from "lucide-react";
import type { ConfigPlantaoResponse } from "@/api/generated/types.gen";
import { usePainelTelemetria } from "@/api/hooks/use-painel-telemetria";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { formatarTempoEstimado } from "@/lib/formatters";
import { AcrTriageDistributionGrid } from "./acr-triage-distribution-grid";
import { MedicosTmaCard } from "./medicos-tma-card";
import { PainelHeader } from "./painel-header";
import { TaxasOperacionaisCard } from "./taxas-operacionais-card";

export interface PainelMetricasAoVivoProps {
  gestorNome?: string;
  config?: ConfigPlantaoResponse;
  onLogout?: () => void;
}

/**
 * Subárvore isolada que assina o polling de 5s da telemetria ao vivo (US-13 / RF-10).
 * Evita re-renderizar o formulário de parametrização e o card de exportação BPA-I a cada tick.
 */
export function PainelMetricasAoVivo({
  gestorNome = "Gestor da Unidade",
  config,
  onLogout,
}: PainelMetricasAoVivoProps) {
  const {
    data: painel,
    isLoading: isLoadingPainel,
    isFetching,
    refetch,
  } = usePainelTelemetria({ refetchInterval: 5000 });

  const tmaRealSegundos = painel?.tma_medio_segundos ?? 0;
  const tmaPlanejadoSegundos = config?.tma_padrao_segundos ?? 600;
  const totalAtendidos = painel?.total_atendimentos ?? 0;
  const cotaMaxima = config?.cota_diaria_maxima ?? null;
  const percentualCota =
    cotaMaxima && cotaMaxima > 0
      ? Math.min(100, Math.round((totalAtendidos / cotaMaxima) * 100))
      : null;

  const medicosAtivos = painel?.medicos_ativos_count ?? 0;
  const medicosPlanejados = config?.medicos_ativos_planejados ?? 1;
  const totalFila = painel?.total_pacientes_fila ?? 0;

  const isEquipeSaturada =
    medicosAtivos < medicosPlanejados || (medicosAtivos > 0 && totalFila > medicosAtivos * 5);

  return (
    <div className="space-y-4">
      <PainelHeader
        gestorNome={gestorNome}
        isFetching={isFetching}
        onRefresh={() => void refetch()}
        onLogout={onLogout}
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
        <Card className="border-border">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                TMA Médio Real
              </span>
              <Clock className="size-4 text-primary" />
            </div>
          </CardHeader>
          <CardContent className="space-y-1">
            <div
              data-testid="tma-real"
              className="text-2xl sm:text-3xl font-extrabold text-foreground"
            >
              {isLoadingPainel ? "…" : formatarTempoEstimado(tmaRealSegundos)}
            </div>
            <p className="text-[11px] text-muted-foreground">
              Meta estimada: <strong>{formatarTempoEstimado(tmaPlanejadoSegundos)}</strong> (RN06)
            </p>
          </CardContent>
        </Card>

        <Card className="border-border">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Atendimentos Hoje
              </span>
              <UserCheck className="size-4 text-emerald-600" />
            </div>
          </CardHeader>
          <CardContent className="space-y-1.5">
            <div
              data-testid="pacientes-atendidos"
              className="text-2xl sm:text-3xl font-extrabold text-foreground"
            >
              {isLoadingPainel ? "…" : totalAtendidos}
              {cotaMaxima ? (
                <span className="text-xs font-normal text-muted-foreground ml-1.5">
                  / cota {cotaMaxima}
                </span>
              ) : (
                <span className="text-xs font-normal text-muted-foreground ml-1.5">
                  (Cota Livre SUS)
                </span>
              )}
            </div>
            {percentualCota !== null && (
              <div className="space-y-1">
                <Progress
                  value={percentualCota}
                  aria-label="Percentual da cota diária utilizada"
                  className="h-1.5"
                />
                <span className="text-[10px] text-muted-foreground block text-right">
                  {percentualCota}% da cota utilizada
                </span>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="border-border">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Fila de Espera
              </span>
              <Users className="size-4 text-amber-500" />
            </div>
          </CardHeader>
          <CardContent className="space-y-1">
            <div
              data-testid="total-pacientes-fila"
              className="text-2xl sm:text-3xl font-extrabold text-foreground"
            >
              {isLoadingPainel ? "…" : totalFila}
            </div>
            <p className="text-[11px] text-muted-foreground">
              {totalFila === 1 ? "1 paciente aguardando" : `${totalFila} pacientes aguardando`}
            </p>
          </CardContent>
        </Card>

        <Card className="border-border">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Status da Equipe
              </span>
              {isEquipeSaturada ? (
                <AlertTriangle className="size-4 text-amber-500" />
              ) : (
                <Activity className="size-4 text-emerald-600" />
              )}
            </div>
          </CardHeader>
          <CardContent className="space-y-1">
            <div className="flex items-center gap-2">
              <Badge
                variant={isEquipeSaturada ? "warning" : "success"}
                className="text-xs py-0.5 px-2"
                data-testid="status-saturacao"
              >
                {isEquipeSaturada ? "Atenção / Sobrecarga" : "Capacidade Adequada"}
              </Badge>
            </div>
            <p className="text-[11px] text-muted-foreground pt-1" data-testid="medicos-ativos-info">
              <strong>{medicosAtivos}</strong> de <strong>{medicosPlanejados}</strong> médicos
              ativos
            </p>
          </CardContent>
        </Card>
      </div>

      <AcrTriageDistributionGrid painel={painel} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3.5">
        <TaxasOperacionaisCard painel={painel} />
        <MedicosTmaCard painel={painel} />
      </div>
    </div>
  );
}
