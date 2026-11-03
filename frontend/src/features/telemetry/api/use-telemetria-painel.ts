import { type UseQueryOptions, useQuery } from "@tanstack/react-query";
import { client, getActiveTenantId } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import {
  obterConfiguracaoPlantaoApiV1TelemetriaConfigPlantaoGet,
  obterPainelTelemetriaApiV1TelemetriaPainelGet,
} from "@/api/generated/sdk.gen";
import type { ConfigPlantaoResponse, PainelTelemetriaResponse } from "@/api/generated/types.gen";

/**
 * Hook headless TanStack Query para monitoramento do painel operacional da regulação municipal.
 * Realiza polling respeitoso a cada 5 segundos (RF-10, US-13, ADR-011).
 */
export function useTelemetriaPainel(
  token?: string,
  options?: Omit<
    UseQueryOptions<PainelTelemetriaResponse, ProblemDetailsError>,
    "queryKey" | "queryFn"
  >,
) {
  return useQuery<PainelTelemetriaResponse, ProblemDetailsError>({
    queryKey: ["telemetria", "painel"],
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
    refetchInterval: 5000,
    ...options,
  });
}

/**
 * Hook headless TanStack Query para obtenção das configurações e SLAs operacionais do plantão.
 */
export function useConfigPlantao(
  token?: string,
  options?: Omit<
    UseQueryOptions<ConfigPlantaoResponse, ProblemDetailsError>,
    "queryKey" | "queryFn"
  >,
) {
  return useQuery<ConfigPlantaoResponse, ProblemDetailsError>({
    queryKey: ["telemetria", "config-plantao"],
    queryFn: async () => {
      try {
        const headers: Record<string, string> = {
          "X-Tenant-ID": getActiveTenantId(),
        };
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }

        const response = await obterConfiguracaoPlantaoApiV1TelemetriaConfigPlantaoGet({
          client,
          headers,
          throwOnError: true,
        });
        return response.data;
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    staleTime: 60000,
    ...options,
  });
}
