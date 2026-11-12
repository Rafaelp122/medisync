import { type UseMutationOptions, useMutation, useQueryClient } from "@tanstack/react-query";
import { client, getActiveTenantId } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { finalizarConsultaApiV1ConsultationsAtendimentoIdFinalizePost } from "@/api/generated/sdk.gen";
import type {
  FinalizarConsultaRequest,
  FinalizarConsultaResponse,
} from "@/api/generated/types.gen";

export interface FinalizarConsultaParams extends FinalizarConsultaRequest {
  token?: string;
}

/**
 * Hook headless de mutação para conclusão formal do atendimento e travamento imutável do PEP.
 * Inviabiliza alterações posteriores conforme CFM nº 1.821/2007 e LGPD Art. 16.
 * Regras: RF-07, RF-08, US-09.
 */
export function useFinalizarConsulta(
  atendimentoId: string,
  options?: UseMutationOptions<
    FinalizarConsultaResponse,
    ProblemDetailsError,
    FinalizarConsultaParams
  >,
) {
  const queryClient = useQueryClient();

  return useMutation<FinalizarConsultaResponse, ProblemDetailsError, FinalizarConsultaParams>({
    mutationFn: async ({ token, ...body }: FinalizarConsultaParams = {}) => {
      try {
        const headers: Record<string, string> = {
          "X-Tenant-ID": getActiveTenantId(),
        };
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }

        const response = await finalizarConsultaApiV1ConsultationsAtendimentoIdFinalizePost({
          client,
          path: {
            atendimento_id: atendimentoId,
          },
          body,
          headers,
          throwOnError: true,
        });
        return response.data;
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    onSuccess: (data, variables, onMutateResult, context) => {
      queryClient.invalidateQueries({ queryKey: ["prontuario", atendimentoId] });
      queryClient.invalidateQueries({ queryKey: ["soap", atendimentoId] });
      options?.onSuccess?.(data, variables, onMutateResult, context);
    },
    ...options,
  });
}
