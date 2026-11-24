import {
  type UseMutationOptions,
  type UseQueryOptions,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { client, getSessionQueryScope } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import {
  atualizarConfiguracaoPlantaoApiV1TelemetriaConfigPlantaoPut,
  obterConfiguracaoPlantaoApiV1TelemetriaConfigPlantaoGet,
} from "@/api/generated/sdk.gen";
import type { ConfigPlantaoRequest, ConfigPlantaoResponse } from "@/api/generated/types.gen";
import { PAINEL_TELEMETRIA_QUERY_KEY_PREFIX } from "@/api/hooks/use-painel-telemetria";

export const CONFIG_PLANTAO_QUERY_KEY_PREFIX = ["telemetria", "config-plantao"] as const;

/**
 * Hook headless TanStack Query para leitura da política atual de plantão/backpressure (US-12).
 * Escopa cache por sessão ativa via `getSessionQueryScope()`.
 */
export function useConfigPlantao(
  options?: Omit<
    UseQueryOptions<ConfigPlantaoResponse, ProblemDetailsError>,
    "queryKey" | "queryFn"
  >,
) {
  const scopeKey = getSessionQueryScope();
  return useQuery<ConfigPlantaoResponse, ProblemDetailsError>({
    queryKey: [...CONFIG_PLANTAO_QUERY_KEY_PREFIX, scopeKey],
    queryFn: async () => {
      try {
        const response = await obterConfiguracaoPlantaoApiV1TelemetriaConfigPlantaoGet({
          client,
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

/**
 * Hook headless de mutação para parametrização da política de plantão (US-12 / RF-09).
 */
export function useAtualizarConfigPlantao(
  options?: UseMutationOptions<ConfigPlantaoResponse, ProblemDetailsError, ConfigPlantaoRequest>,
) {
  const queryClient = useQueryClient();
  const { onSuccess, ...restOptions } = options ?? {};

  return useMutation<ConfigPlantaoResponse, ProblemDetailsError, ConfigPlantaoRequest>({
    mutationFn: async (body: ConfigPlantaoRequest) => {
      try {
        const response = await atualizarConfiguracaoPlantaoApiV1TelemetriaConfigPlantaoPut({
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
      const scopeKey = getSessionQueryScope();
      queryClient.setQueryData([...CONFIG_PLANTAO_QUERY_KEY_PREFIX, scopeKey], data);
      void queryClient.invalidateQueries({ queryKey: [...CONFIG_PLANTAO_QUERY_KEY_PREFIX] });
      void queryClient.invalidateQueries({ queryKey: [...PAINEL_TELEMETRIA_QUERY_KEY_PREFIX] });
      onSuccess?.(data, variables, onMutateResult, context);
    },
    ...restOptions,
  });
}
