import { zodResolver } from "@hookform/resolvers/zod";
import { AlertCircle, CheckCircle2, Settings2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import type { ConfigPlantaoResponse } from "@/api/generated/types.gen";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAtualizarConfigPlantao } from "../../api/use-telemetria-painel";
import {
  type ConfigPlantaoFormData,
  type ConfigPlantaoInputFormData,
  configPlantaoFormSchema,
} from "../../schemas/telemetry-schema";

export interface ConfigPlantaoCardProps {
  config?: ConfigPlantaoResponse;
  token?: string;
}

function normalizeFormDefaults(config?: ConfigPlantaoResponse): ConfigPlantaoFormData {
  const alphaNumerico = Number(config?.alpha_backpressure ?? 1.25);
  const alphaValido =
    Number.isFinite(alphaNumerico) && alphaNumerico >= 1.2 && alphaNumerico <= 1.3
      ? alphaNumerico
      : 1.25;

  return {
    medicos_ativos_planejados: Math.max(1, config?.medicos_ativos_planejados ?? 1),
    alpha_backpressure: alphaValido,
    cota_diaria_maxima: Math.max(1, config?.cota_diaria_maxima ?? 300),
    tma_padrao_segundos: Math.max(60, config?.tma_padrao_segundos ?? 600),
    tempo_tolerancia_ring_segundos: Math.max(10, config?.tempo_tolerancia_ring_segundos ?? 45),
    modo_operacao: config?.modo_operacao === "PRIVADO" ? "PRIVADO" : "SUS",
    sla_minutos_nivel_1: config?.sla_minutos_nivel_1 ?? 0,
    sla_minutos_nivel_2: config?.sla_minutos_nivel_2 ?? 10,
    sla_minutos_nivel_3: config?.sla_minutos_nivel_3 ?? 60,
    sla_minutos_nivel_4: config?.sla_minutos_nivel_4 ?? 120,
    sla_minutos_nivel_5: config?.sla_minutos_nivel_5 ?? 240,
  };
}

/**
 * Cartão de parametrização operacional do plantão e regra de backpressure (US-12 / RF-09).
 */
export function ConfigPlantaoCard({ config, token }: ConfigPlantaoCardProps) {
  const [mensagemSucesso, setMensagemSucesso] = useState<string | null>(null);
  const { mutate: atualizarConfig, isPending, error } = useAtualizarConfigPlantao(token);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isDirty },
  } = useForm<ConfigPlantaoInputFormData, unknown, ConfigPlantaoFormData>({
    resolver: zodResolver(configPlantaoFormSchema),
    defaultValues: normalizeFormDefaults(config),
  });

  useEffect(() => {
    if (config && !isDirty) {
      reset(normalizeFormDefaults(config));
    }
  }, [config, isDirty, reset]);

  const onSubmit = (formData: ConfigPlantaoFormData) => {
    setMensagemSucesso(null);
    atualizarConfig(
      {
        ...formData,
        alpha_backpressure: formData.alpha_backpressure.toFixed(2),
      },
      {
        onSuccess: (updated) => {
          reset(normalizeFormDefaults(updated));
          setMensagemSucesso("Política do plantão atualizada com sucesso.");
        },
      },
    );
  };

  return (
    <Card className="border-border/80 shadow-sm">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base font-semibold">
          <Settings2 className="h-4 w-4 text-primary" aria-hidden="true" />
          Política de Plantão e Backpressure (US-12)
        </CardTitle>
        <CardDescription>
          Parametrize dimensionamento médico, fator alpha de contenção, cota e TMA padrão.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          {error && (
            <Alert variant="destructive" role="alert">
              <AlertCircle className="h-4 w-4" aria-hidden="true" />
              <AlertTitle>Erro ao salvar configuração</AlertTitle>
              <AlertDescription>{error.detail || error.message}</AlertDescription>
            </Alert>
          )}

          {mensagemSucesso && (
            <Alert
              role="status"
              className="border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-100"
            >
              <CheckCircle2
                className="h-4 w-4 text-emerald-700 dark:text-emerald-400"
                aria-hidden="true"
              />
              <AlertTitle>Configuração aplicada</AlertTitle>
              <AlertDescription>{mensagemSucesso}</AlertDescription>
            </Alert>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
            <div className="space-y-1.5">
              <Label htmlFor="medicos_ativos_planejados">Médicos Ativos Planejados</Label>
              <Input
                id="medicos_ativos_planejados"
                type="number"
                min={1}
                {...register("medicos_ativos_planejados", { valueAsNumber: true })}
              />
              {errors.medicos_ativos_planejados && (
                <p className="text-xs text-destructive" role="alert">
                  {errors.medicos_ativos_planejados.message}
                </p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="alpha_backpressure">Fator Alpha Backpressure (1.20–1.30)</Label>
              <Input
                id="alpha_backpressure"
                type="number"
                step="0.01"
                min={1.2}
                max={1.3}
                {...register("alpha_backpressure", { valueAsNumber: true })}
              />
              {errors.alpha_backpressure && (
                <p className="text-xs text-destructive" role="alert">
                  {errors.alpha_backpressure.message}
                </p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="cota_diaria_maxima">Cota Diária Máxima</Label>
              <Input
                id="cota_diaria_maxima"
                type="number"
                min={1}
                {...register("cota_diaria_maxima", { valueAsNumber: true })}
              />
              {errors.cota_diaria_maxima && (
                <p className="text-xs text-destructive" role="alert">
                  {errors.cota_diaria_maxima.message}
                </p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="tma_padrao_segundos">TMA Padrão (segundos)</Label>
              <Input
                id="tma_padrao_segundos"
                type="number"
                min={60}
                {...register("tma_padrao_segundos", { valueAsNumber: true })}
              />
              {errors.tma_padrao_segundos && (
                <p className="text-xs text-destructive" role="alert">
                  {errors.tma_padrao_segundos.message}
                </p>
              )}
            </div>

            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="modo_operacao">Modo de Operação</Label>
              <select
                id="modo_operacao"
                {...register("modo_operacao")}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                <option value="SUS">SUS (Regulação Pública)</option>
                <option value="PRIVADO">Privado (Saúde Suplementar)</option>
              </select>
              {errors.modo_operacao && (
                <p className="text-xs text-destructive" role="alert">
                  {errors.modo_operacao.message}
                </p>
              )}
            </div>
          </div>

          <Button type="submit" disabled={isPending} className="w-full sm:w-auto">
            {isPending ? "Salvando…" : "Salvar Política do Plantão"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
