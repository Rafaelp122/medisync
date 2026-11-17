import { type UseMutationOptions, useMutation, useQueryClient } from "@tanstack/react-query";
import { client, getTenantHeaders } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { regularizarAtendimentoFilaApiV1FilaAtendimentosAtendimentoIdRegularizarPost } from "@/api/generated/sdk.gen";
import type {
  RegularizacaoFilaRequest,
  RegularizacaoFilaResponse,
} from "@/api/generated/types.gen";

export interface RegularizarFilaParams {
  atendimentoId: string;
  body?: RegularizacaoFilaRequest;
  token?: string;
}

/**
 * Hook headless de mutação para regularização cadastral ou contingência na fila (US-05 / RN03).
 */
export function useRegularizarFila(
  options?: UseMutationOptions<
    RegularizacaoFilaResponse,
    ProblemDetailsError,
    RegularizarFilaParams
  >,
) {
  const queryClient = useQueryClient();

  return useMutation<RegularizacaoFilaResponse, ProblemDetailsError, RegularizarFilaParams>({
    ...options,
    mutationFn: async ({ atendimentoId, body, token }: RegularizarFilaParams) => {
      try {
        const headers: Record<string, string> = {
          ...getTenantHeaders(),
        };
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }
        const response =
          await regularizarAtendimentoFilaApiV1FilaAtendimentosAtendimentoIdRegularizarPost({
            client,
            path: { atendimento_id: atendimentoId },
            body: body ?? {
              motivo: "Regularização cadastral confirmada pelo paciente na sala de espera",
              tipo_contingencia: "REGULARIZACAO_ELEGIBILIDADE",
            },
            headers,
            throwOnError: true,
          });
        return response.data;
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    onSuccess: (data, variables, onMutateResult, context) => {
      void queryClient.invalidateQueries({
        queryKey: ["queue", "posicao", variables.atendimentoId],
      });
      options?.onSuccess?.(data, variables, onMutateResult, context);
    },
  });
}
