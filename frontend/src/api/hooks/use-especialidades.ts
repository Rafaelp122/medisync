import { type UseQueryOptions, useQuery } from "@tanstack/react-query";
import { client, getSessionQueryScope } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { listarEspecialidadesApiV1SchedulingEspecialidadesGet } from "@/api/generated/sdk.gen";
import type { EspecialidadeResponse } from "@/api/generated/types.gen";

export interface UseEspecialidadesParams {
  enabled?: boolean;
}

export const ESPECIALIDADES_QUERY_KEY_PREFIX = ["scheduling", "especialidades"] as const;

/**
 * Hook headless canônico para listar especialidades disponíveis na agenda multiprofissional (eMulti).
 * Compartilhado entre o Portal do Cidadão (/home) e a jornada de Agendamento (/agendar).
 */
export function useEspecialidades(
  { enabled = true }: UseEspecialidadesParams = {},
  options?: Omit<
    UseQueryOptions<EspecialidadeResponse[], ProblemDetailsError>,
    "queryKey" | "queryFn"
  >,
) {
  const scopeKey = getSessionQueryScope();
  return useQuery<EspecialidadeResponse[], ProblemDetailsError>({
    queryKey: [...ESPECIALIDADES_QUERY_KEY_PREFIX, scopeKey],
    queryFn: async () => {
      try {
        const response = await listarEspecialidadesApiV1SchedulingEspecialidadesGet({
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
