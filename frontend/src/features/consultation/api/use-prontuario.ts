import { type UseQueryOptions, useQuery } from "@tanstack/react-query";
import { client } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { obterProntuarioProtegidoApiV1ConsultationsAtendimentoIdProntuarioGet } from "@/api/generated/sdk.gen";
import type { ProntuarioResponse } from "@/api/generated/types.gen";

/**
 * Hook headless de consulta ao prontuário médico protegido em 2 camadas (PEP).
 * Camada 1: RBAC Médico | Camada 2: ABAC Clínico + Anti-IDOR por titularidade.
 * Regras: RF-07, US-09, CFM nº 1.821/2007, ADR-013.
 */
export function useProntuario(
  atendimentoId: string,
  token?: string,
  options?: Omit<UseQueryOptions<ProntuarioResponse, ProblemDetailsError>, "queryKey" | "queryFn">,
) {
  return useQuery<ProntuarioResponse, ProblemDetailsError>({
    queryKey: ["prontuario", atendimentoId],
    queryFn: async () => {
      try {
        const headers: Record<string, string> = {};
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }

        const response = await obterProntuarioProtegidoApiV1ConsultationsAtendimentoIdProntuarioGet(
          {
            client,
            path: {
              atendimento_id: atendimentoId,
            },
            headers,
            throwOnError: true,
          },
        );
        return response.data;
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    enabled: Boolean(atendimentoId),
    ...options,
  });
}
