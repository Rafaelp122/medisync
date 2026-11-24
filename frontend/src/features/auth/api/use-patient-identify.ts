import { type UseMutationOptions, useMutation } from "@tanstack/react-query";
import { client } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { postAuthPatientIdentify } from "@/api/generated/sdk.gen";
import type {
  IdentificarPacienteRequest,
  IdentificarPacienteResponse,
} from "@/api/generated/types.gen";

/**
 * Hook headless de mutação para identificação única anti-enumeração do cidadão (CPF ou e-mail).
 * Regras canônicas: RF-01, ADR-005 e ADR-011.
 * @see docs/explanation/domains/auth-domain.md
 */
export function usePatientIdentify(
  options?: UseMutationOptions<
    IdentificarPacienteResponse,
    ProblemDetailsError,
    IdentificarPacienteRequest
  >,
) {
  return useMutation<IdentificarPacienteResponse, ProblemDetailsError, IdentificarPacienteRequest>({
    mutationFn: async (body: IdentificarPacienteRequest) => {
      try {
        const response = await postAuthPatientIdentify({
          client,
          body,
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
