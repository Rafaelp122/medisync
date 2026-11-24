import { type UseQueryOptions, useQuery } from "@tanstack/react-query";
import { client, getSessionQueryScope } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { listarSlotsApiV1SchedulingSlotsGet } from "@/api/generated/sdk.gen";
import type { SlotDisponivelResponse } from "@/api/generated/types.gen";

export interface UseSlotsParams {
  especialidade: string;
  dataInicio: string;
  dataFim: string;
  enabled?: boolean;
}

/**
 * Hook headless para consultar horários livres por especialidade e janela de datas.
 */
export function useSlots(
  { especialidade, dataInicio, dataFim, enabled = true }: UseSlotsParams,
  options?: Partial<UseQueryOptions<SlotDisponivelResponse[], ProblemDetailsError>>,
) {
  const isPeriodoValido =
    Boolean(especialidade) && Boolean(dataInicio) && Boolean(dataFim) && dataInicio <= dataFim;
  const scopeKey = getSessionQueryScope();

  return useQuery<SlotDisponivelResponse[], ProblemDetailsError>({
    queryKey: ["scheduling", "slots", scopeKey, especialidade, dataInicio, dataFim],
    queryFn: async () => {
      try {
        const response = await listarSlotsApiV1SchedulingSlotsGet({
          client,
          query: {
            especialidade,
            data_inicio: dataInicio,
            data_fim: dataFim,
          },
          throwOnError: true,
        });
        return response.data;
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    enabled: Boolean(enabled && isPeriodoValido),
    ...options,
  });
}
