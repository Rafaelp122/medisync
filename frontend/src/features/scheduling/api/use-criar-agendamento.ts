import { type UseMutationOptions, useMutation, useQueryClient } from "@tanstack/react-query";
import { client } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { criarAgendamentoApiV1SchedulingAgendamentosPost } from "@/api/generated/sdk.gen";
import type { AgendamentoResponse, CriarAgendamentoRequest } from "@/api/generated/types.gen";
import { MEUS_AGENDAMENTOS_QUERY_KEY_PREFIX } from "@/api/hooks/use-meus-agendamentos";

export interface CriarAgendamentoParams {
  body: CriarAgendamentoRequest;
}

/**
 * Hook headless de mutação para reserva de horário pelo paciente autenticado (Anti-IDOR).
 */
export function useCriarAgendamento(
  options?: UseMutationOptions<AgendamentoResponse, ProblemDetailsError, CriarAgendamentoParams>,
) {
  const queryClient = useQueryClient();

  return useMutation<AgendamentoResponse, ProblemDetailsError, CriarAgendamentoParams>({
    ...options,
    mutationFn: async ({ body }: CriarAgendamentoParams) => {
      try {
        const response = await criarAgendamentoApiV1SchedulingAgendamentosPost({
          client,
          body,
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
