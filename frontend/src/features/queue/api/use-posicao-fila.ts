import { type UseQueryOptions, useQuery } from "@tanstack/react-query";
import { client, getActiveTenantId } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { obterPosicaoFilaApiV1FilaPosicaoAtendimentoIdGet } from "@/api/generated/sdk.gen";
import type { PosicaoFilaResponse } from "@/api/generated/types.gen";
import { settings } from "@/config/settings";

export interface UsePosicaoFilaParams {
  atendimentoId?: string;
  token?: string;
  pollingInterval?: number | false;
  enabled?: boolean;
}

/**
 * Hook headless para consulta contínua da posição e tempo estimado na fila virtual.
 * Regras: RF-03, RN01, US-07, US-08 e ADR-011.
 */
export function usePosicaoFila(
  {
    atendimentoId,
    token,
    pollingInterval = settings.network.queuePollingIntervalMs,
    enabled = true,
  }: UsePosicaoFilaParams,
  options?: Partial<UseQueryOptions<PosicaoFilaResponse, ProblemDetailsError>>,
) {
  return useQuery<PosicaoFilaResponse, ProblemDetailsError>({
    queryKey: ["queue", "posicao", atendimentoId],
    queryFn: async () => {
      if (!atendimentoId) {
        throw new Error("atendimentoId é obrigatório para consulta de fila.");
      }
      try {
        const headers: Record<string, string> = {
          "X-Tenant-ID": getActiveTenantId(),
        };
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }
        const response = await obterPosicaoFilaApiV1FilaPosicaoAtendimentoIdGet({
          client,
          path: { atendimento_id: atendimentoId },
          headers,
          throwOnError: true,
        });
        return response.data;
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    enabled: Boolean(enabled && atendimentoId),
    refetchInterval: pollingInterval,
    refetchIntervalInBackground: false,
    ...options,
  });
}
