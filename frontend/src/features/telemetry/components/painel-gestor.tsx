import {
  Activity,
  AlertTriangle,
  Building2,
  CheckCircle2,
  Clock,
  LogOut,
  RefreshCw,
  ShieldAlert,
  TrendingDown,
  UserCheck,
  Users,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { formatarTempoEstimado } from "@/lib/formatters";
import { cn } from "@/lib/utils";
import { useConfigPlantao, useTelemetriaPainel } from "../api/use-telemetria-painel";

export interface PainelGestorProps {
  token?: string;
  gestorNome?: string;
  onLogout?: () => void;
  className?: string;
}

export function PainelGestor({
  token,
  gestorNome = "Gestor Municipal",
  onLogout,
  className,
}: PainelGestorProps) {
  const {
    data: painel,
    isLoading: isLoadingPainel,
    isFetching,
    refetch,
  } = useTelemetriaPainel(token);
  const { data: config } = useConfigPlantao(token);

  const tmaRealSegundos = painel?.tma_medio_segundos ?? 0;
  const tmaPlanejadoSegundos = config?.tma_padrao_segundos ?? 900;
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

  const slaCompliance = painel?.sla_compliance_percentual ?? 100;
  const slaOk = painel?.sla_em_conformidade ?? true;

  return (
    <div className={cn("w-full max-w-7xl mx-auto space-y-4 p-2 sm:p-4 text-foreground", className)}>
      {/* Header do Painel da Regulação */}
      <header className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 p-4 rounded-xl border border-border bg-card shadow-xs">
        <div className="flex items-center gap-3">
          <div className="size-11 rounded-lg bg-primary/10 flex items-center justify-center text-primary font-bold">
            <Building2 className="size-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg sm:text-xl font-extrabold tracking-tight text-foreground">
                Painel de Regulação e Telemetria SUS
              </h1>
              <Badge variant="outline" className="text-[10px] py-0 px-2 gap-1">
                <span className="inline-block size-1.5 rounded-full bg-emerald-500 animate-pulse" />
                <span>Polling 5s</span>
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              Monitoramento Operacional em Tempo Real • {gestorNome}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void refetch()}
            disabled={isFetching}
            className="text-xs h-9 px-3 gap-1.5"
            aria-label="Atualizar telemetria"
          >
            <RefreshCw className={cn("size-3.5", isFetching && "animate-spin text-primary")} />
            <span>{isFetching ? "Atualizando…" : "Atualizar"}</span>
          </Button>

          {onLogout && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onLogout}
              className="text-xs h-9 px-3 gap-1.5 text-muted-foreground hover:text-foreground"
            >
              <LogOut className="size-3.5" />
              <span>Sair</span>
            </Button>
          )}
        </div>
      </header>

      {/* Grid de Métricas Principais (4 Cards) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
        {/* Card 1: TMA Real vs Planejado */}
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

        {/* Card 2: Pacientes Atendidos Hoje vs Cota */}
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
                <Progress value={percentualCota} className="h-1.5" />
                <span className="text-[10px] text-muted-foreground block text-right">
                  {percentualCota}% da cota utilizada
                </span>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Card 3: Fila de Espera Atual */}
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

        {/* Card 4: Saturação da Equipe e Plantão */}
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

      {/* Seção 2: Distribuição por Prioridade Clínica ACR SUS (Portaria GM/MS nº 2.048/2002) */}
      <Card className="border-border">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <CardTitle className="text-sm sm:text-base font-bold text-foreground">
                Distribuição da Fila e Tempo Médio de Espera (TME) por ACR SUS
              </CardTitle>
              <CardDescription className="text-xs text-muted-foreground">
                Classificação de Risco Oficial conforme Portaria GM/MS nº 2.048/2002 e Parecer
                CREMESP nº 278.262/2023.
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
            <div className="p-3 rounded-lg border border-red-500/30 bg-red-500/5 space-y-1 text-center">
              <Badge variant="nivel1" className="text-[11px] mb-1">
                Vermelho
              </Badge>
              <p className="text-[11px] font-semibold text-foreground">
                Emergência Imediata (SAMU 192)
              </p>
              <div className="pt-1 border-t border-red-500/20 text-xs">
                <span className="text-muted-foreground block text-[10px]">TME Atual:</span>
                <strong className="text-foreground">
                  {formatarTempoEstimado(painel?.tme_nivel_1_segundos ?? 0)}
                </strong>
              </div>
            </div>

            {/* Laranja */}
            <div className="p-3 rounded-lg border border-orange-500/30 bg-orange-500/5 space-y-1 text-center">
              <Badge variant="nivel2" className="text-[11px] mb-1">
                Laranja
              </Badge>
              <p className="text-[11px] font-semibold text-foreground">Muito Urgente</p>
              <div className="pt-1 border-t border-orange-500/20 text-xs">
                <span className="text-muted-foreground block text-[10px]">TME Atual:</span>
                <strong className="text-foreground">
                  {formatarTempoEstimado(painel?.tme_nivel_2_segundos ?? 0)}
                </strong>
              </div>
            </div>

            {/* Amarelo */}
            <div className="p-3 rounded-lg border border-amber-500/30 bg-amber-500/5 space-y-1 text-center">
              <Badge variant="nivel3" className="text-[11px] mb-1">
                Amarelo
              </Badge>
              <p className="text-[11px] font-semibold text-foreground">Urgente</p>
              <div className="pt-1 border-t border-amber-500/20 text-xs">
                <span className="text-muted-foreground block text-[10px]">TME Atual:</span>
                <strong className="text-foreground">
                  {formatarTempoEstimado(painel?.tme_nivel_3_segundos ?? 0)}
                </strong>
              </div>
            </div>

            {/* Verde */}
            <div className="p-3 rounded-lg border border-emerald-500/30 bg-emerald-500/5 space-y-1 text-center">
              <Badge variant="nivel4" className="text-[11px] mb-1">
                Verde
              </Badge>
              <p className="text-[11px] font-semibold text-foreground">Pouco Urgente</p>
              <div className="pt-1 border-t border-emerald-500/20 text-xs">
                <span className="text-muted-foreground block text-[10px]">TME Atual:</span>
                <strong className="text-foreground">
                  {formatarTempoEstimado(painel?.tme_nivel_4_segundos ?? 0)}
                </strong>
              </div>
            </div>

            {/* Azul */}
            <div className="p-3 rounded-lg border border-blue-500/30 bg-blue-500/5 space-y-1 text-center">
              <Badge variant="nivel5" className="text-[11px] mb-1">
                Azul
              </Badge>
              <p className="text-[11px] font-semibold text-foreground">Não Urgente</p>
              <div className="pt-1 border-t border-blue-500/20 text-xs">
                <span className="text-muted-foreground block text-[10px]">TME Atual:</span>
                <strong className="text-foreground">
                  {formatarTempoEstimado(painel?.tme_nivel_5_segundos ?? 0)}
                </strong>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Seção 3: Indicadores de Evasão, No-Show e Desempenho Médico Individual */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3.5">
        {/* Card: Taxas Operacionais de Evasão & No-Show */}
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

        {/* Card: Desempenho Médico Individual (TMA por Profissional) */}
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
      </div>
    </div>
  );
}

export default PainelGestor;
