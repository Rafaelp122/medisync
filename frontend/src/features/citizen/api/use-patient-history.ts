import { type UseQueryOptions, useQuery } from "@tanstack/react-query";
import { client, getSessionQueryScope, resolveExplicitAuthHeaders } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { listarHistoricoPacienteApiV1ConsultationsMeHistoricoGet } from "@/api/generated/sdk.gen";
import type { HistoricoAtendimentoItemResponse } from "@/api/generated/types.gen";

/**
 * Hook headless para histórico de teleconsultas de Pronto-Atendimento do paciente autenticado.
 */
export function usePatientHistory(
  token?: string,
  options?: Omit<
    UseQueryOptions<HistoricoAtendimentoItemResponse[], ProblemDetailsError>,
    "queryKey" | "queryFn"
  >,
) {
  const scopeKey = getSessionQueryScope(token);
  return useQuery<HistoricoAtendimentoItemResponse[], ProblemDetailsError>({
    queryKey: ["citizen", "history", scopeKey],
    queryFn: async () => {
      try {
        const response = await listarHistoricoPacienteApiV1ConsultationsMeHistoricoGet({
          client,
          headers: resolveExplicitAuthHeaders(token),
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
