import { type UseQueryOptions, useQuery } from "@tanstack/react-query";
import { client, getActiveTenantId } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { obterPainelTelemetriaApiV1TelemetriaPainelGet } from "@/api/generated/sdk.gen";
import type { PainelTelemetriaResponse } from "@/api/generated/types.gen";

/**
 * Hook headless para consulta do painel operacional e telemetria da fila virtual.
 * Monitora contagem de pacientes aguardando (total_pacientes_fila) e métricas do plantão.
 * Regras: RF-03, RF-10, US-13 e ADR-011.
 */
export function usePainelTelemetria(
  token?: string,
  options?: Omit<
    UseQueryOptions<PainelTelemetriaResponse, ProblemDetailsError>,
    "queryKey" | "queryFn"
  >,
) {
  return useQuery<PainelTelemetriaResponse, ProblemDetailsError>({
    queryKey: ["telemetria-painel"],
    queryFn: async () => {
      try {
        const headers: Record<string, string> = {
          "X-Tenant-ID": getActiveTenantId(),
        };
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }

        const response = await obterPainelTelemetriaApiV1TelemetriaPainelGet({
          client,
          headers,
          throwOnError: true,
        });
        return response.data;
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    refetchInterval: 10000, // Atualização a cada 10 segundos para visibilidade da fila
    ...options,
  });
}
