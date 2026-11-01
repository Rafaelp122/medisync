import { type UseMutationOptions, useMutation } from "@tanstack/react-query";
import { client, getActiveTenantId } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { cancelarAtendimentoFilaApiV1FilaCancelarAtendimentoIdPost } from "@/api/generated/sdk.gen";
import type { CancelarFilaRequest, CancelarFilaResponse } from "@/api/generated/types.gen";

export interface CancelarFilaParams {
  atendimentoId: string;
  body?: CancelarFilaRequest;
  token?: string;
}

/**
 * Hook headless de mutação para cancelamento voluntário de atendimento na fila (RN06).
 */
export function useCancelarFila(
  options?: UseMutationOptions<CancelarFilaResponse, ProblemDetailsError, CancelarFilaParams>,
) {
  return useMutation<CancelarFilaResponse, ProblemDetailsError, CancelarFilaParams>({
    mutationFn: async ({ atendimentoId, body, token }: CancelarFilaParams) => {
      try {
        const headers: Record<string, string> = {
          "X-Tenant-ID": getActiveTenantId(),
        };
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }
        const response = await cancelarAtendimentoFilaApiV1FilaCancelarAtendimentoIdPost({
          client,
          path: { atendimento_id: atendimentoId },
          body: body ?? { motivo: "Desistência voluntária pelo paciente" },
          headers,
          throwOnError: true,
        });
        return response.data;
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    ...options,
  });
}
