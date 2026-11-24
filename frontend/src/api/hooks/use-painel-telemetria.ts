import { type UseQueryOptions, useQuery } from "@tanstack/react-query";
import { client, getSessionQueryScope } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { obterPainelTelemetriaApiV1TelemetriaPainelGet } from "@/api/generated/sdk.gen";
import type { PainelTelemetriaResponse } from "@/api/generated/types.gen";

export const PAINEL_TELEMETRIA_QUERY_KEY_PREFIX = ["telemetria", "painel"] as const;

/**
 * Hook headless canônico para consulta do painel operacional de telemetria (RF-10, US-13).
 * Compartilhado entre a Estação do Médico e o Painel do Gestor com escopo de sessão.
 */
export function usePainelTelemetria(
  options?: Omit<
    UseQueryOptions<PainelTelemetriaResponse, ProblemDetailsError>,
    "queryKey" | "queryFn"
  >,
) {
  const scopeKey = getSessionQueryScope();
  return useQuery<PainelTelemetriaResponse, ProblemDetailsError>({
    queryKey: [...PAINEL_TELEMETRIA_QUERY_KEY_PREFIX, scopeKey],
    queryFn: async () => {
      try {
        const response = await obterPainelTelemetriaApiV1TelemetriaPainelGet({
          client,
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
