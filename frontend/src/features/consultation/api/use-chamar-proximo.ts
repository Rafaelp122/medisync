import { type UseMutationOptions, useMutation } from "@tanstack/react-query";
import { client, getActiveTenantId } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { chamarProximoPacienteApiV1FilaChamarProximoPost } from "@/api/generated/sdk.gen";
import type { ChamarProximoResponse } from "@/api/generated/types.gen";

export interface ChamarProximoParams {
  token?: string;
}

/**
 * Hook headless de mutação para alocação atômica do próximo paciente da fila clínica (RF-03, US-07).
 * Utiliza script Lua no Valkey para garantir exclusividade e prevenir race conditions.
 */
export function useChamarProximo(
  options?: UseMutationOptions<ChamarProximoResponse, ProblemDetailsError, ChamarProximoParams>,
) {
  return useMutation<ChamarProximoResponse, ProblemDetailsError, ChamarProximoParams>({
    mutationFn: async ({ token }: ChamarProximoParams = {}) => {
      try {
        const headers: Record<string, string> = {
          "X-Tenant-ID": getActiveTenantId(),
        };
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }

        const response = await chamarProximoPacienteApiV1FilaChamarProximoPost({
          client,
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
