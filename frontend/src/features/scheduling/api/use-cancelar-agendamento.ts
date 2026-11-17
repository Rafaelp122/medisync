import { type UseMutationOptions, useMutation, useQueryClient } from "@tanstack/react-query";
import { client, resolveExplicitAuthHeaders } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { cancelarAgendamentoApiV1SchedulingAgendamentosAgendamentoIdCancelarPost } from "@/api/generated/sdk.gen";
import type { AgendamentoResponse } from "@/api/generated/types.gen";
import { MEUS_AGENDAMENTOS_QUERY_KEY_PREFIX } from "@/api/hooks/use-meus-agendamentos";

export interface CancelarAgendamentoParams {
  agendamentoId: string;
  token?: string;
}

/**
 * Hook headless de mutação para cancelamento de agendamento pelo paciente autenticado.
 */
export function useCancelarAgendamento(
  options?: UseMutationOptions<AgendamentoResponse, ProblemDetailsError, CancelarAgendamentoParams>,
) {
  const queryClient = useQueryClient();

  return useMutation<AgendamentoResponse, ProblemDetailsError, CancelarAgendamentoParams>({
    ...options,
    mutationFn: async ({ agendamentoId, token }: CancelarAgendamentoParams) => {
      try {
        const response =
          await cancelarAgendamentoApiV1SchedulingAgendamentosAgendamentoIdCancelarPost({
            client,
            path: { agendamento_id: agendamentoId },
            headers: resolveExplicitAuthHeaders(token),
            throwOnError: true,
          });
        return response.data;
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    onSuccess: (data, variables, onMutateResult, context) => {
      void queryClient.invalidateQueries({ queryKey: [...MEUS_AGENDAMENTOS_QUERY_KEY_PREFIX] });
      void queryClient.invalidateQueries({ queryKey: ["scheduling", "slots"] });
      options?.onSuccess?.(data, variables, onMutateResult, context);
    },
  });
}
