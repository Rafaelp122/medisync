import { type UseQueryOptions, useQuery } from "@tanstack/react-query";
import { client, getSessionQueryScope } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { listarMeusAgendamentosApiV1SchedulingAgendamentosMeGet } from "@/api/generated/sdk.gen";
import type { AgendamentoResponse } from "@/api/generated/types.gen";

export interface UseMeusAgendamentosParams {
  enabled?: boolean;
}

export const MEUS_AGENDAMENTOS_QUERY_KEY_PREFIX = ["scheduling", "meus-agendamentos"] as const;

/**
 * Hook headless canônico para listar agendamentos do paciente autenticado.
 * Compartilhado entre Agendamento (/agendar) e Histórico (/historico) garantindo invalidação única.
 */
export function useMeusAgendamentos(
  { enabled = true }: UseMeusAgendamentosParams = {},
  options?: Omit<
    UseQueryOptions<AgendamentoResponse[], ProblemDetailsError>,
    "queryKey" | "queryFn"
  >,
) {
  const scopeKey = getSessionQueryScope();
  return useQuery<AgendamentoResponse[], ProblemDetailsError>({
    queryKey: [...MEUS_AGENDAMENTOS_QUERY_KEY_PREFIX, scopeKey],
    queryFn: async () => {
      try {
        const response = await listarMeusAgendamentosApiV1SchedulingAgendamentosMeGet({
          client,
          throwOnError: true,
        });
        return response.data;
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    enabled,
    ...options,
  });
}
