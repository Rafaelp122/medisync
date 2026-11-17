import { type UseMutationOptions, useMutation } from "@tanstack/react-query";
import { client, getTenantHeaders } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { postAuthPatientRegister } from "@/api/generated/sdk.gen";
import type {
  RegistrarPacienteRequest,
  RegistrarPacienteResponse,
} from "@/api/generated/types.gen";

/**
 * Hook headless de mutação para auto-cadastro do cidadão com aceite LGPD e envio inicial de OTP.
 * Regras canônicas: RF-01, LGPD Art. 11, ADR-005 e ADR-011.
 * @see docs/explanation/domains/auth-domain.md
 */
export function usePatientRegister(
  options?: UseMutationOptions<
    RegistrarPacienteResponse,
    ProblemDetailsError,
    RegistrarPacienteRequest
  >,
) {
  return useMutation<RegistrarPacienteResponse, ProblemDetailsError, RegistrarPacienteRequest>({
    mutationFn: async (body: RegistrarPacienteRequest) => {
      try {
        const response = await postAuthPatientRegister({
          client,
          headers: { ...getTenantHeaders() },
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
