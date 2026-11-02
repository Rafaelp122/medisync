import { type UseQueryOptions, useQuery } from "@tanstack/react-query";
import { client, getActiveTenantId } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { obterTmaStatusApiV1ConsultationsAtendimentoIdTmaStatusGet } from "@/api/generated/sdk.gen";
import type { TmaStatusResponse } from "@/api/generated/types.gen";

export interface TmaStatusQueryParams {
  iniciado_em?: string;
  tma_planejado_segundos?: number;
}

/**
 * Hook headless de consulta e telemetria de TMA sem desconexão forçada.
 * Respeita a Soberania do Ato Médico (RN06).
 * Regras: RF-07, RN06, US-09.
 */
export function useTmaStatus(
  atendimentoId: string,
  params?: TmaStatusQueryParams,
  token?: string,
  options?: Omit<UseQueryOptions<TmaStatusResponse, ProblemDetailsError>, "queryKey" | "queryFn">,
) {
  return useQuery<TmaStatusResponse, ProblemDetailsError>({
    queryKey: ["tma-status", atendimentoId, params?.iniciado_em, params?.tma_planejado_segundos],
    queryFn: async () => {
      try {
        const headers: Record<string, string> = {
          "X-Tenant-ID": getActiveTenantId(),
        };
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }

        const response = await obterTmaStatusApiV1ConsultationsAtendimentoIdTmaStatusGet({
          client,
          path: {
            atendimento_id: atendimentoId,
          },
          query: {
            iniciado_em: params?.iniciado_em,
            tma_planejado_segundos: params?.tma_planejado_segundos ?? 900,
          },
          headers,
          throwOnError: true,
        });
        return response.data;
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    enabled: Boolean(atendimentoId),
    refetchInterval: 30000, // Telemetria a cada 30 segundos sem travar a interface
    ...options,
  });
}
