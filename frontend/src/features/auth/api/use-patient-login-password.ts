import { type UseMutationOptions, useMutation } from "@tanstack/react-query";
import { client } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { postAuthPatientLoginPassword } from "@/api/generated/sdk.gen";
import type { LoginPacienteSenhaRequest, VerificarOtpResponse } from "@/api/generated/types.gen";

/**
 * Hook headless de mutação para login tradicional do cidadão (Passo 2B - identificador e senha).
 * Regras canônicas: RF-01, RN-AUT-02 (Lockout), ADR-005 e ADR-011.
 * @see docs/explanation/domains/auth-domain.md
 */
export function usePatientLoginPassword(
  options?: UseMutationOptions<
    VerificarOtpResponse,
    ProblemDetailsError,
    LoginPacienteSenhaRequest
  >,
) {
  return useMutation<VerificarOtpResponse, ProblemDetailsError, LoginPacienteSenhaRequest>({
    mutationFn: async (body: LoginPacienteSenhaRequest) => {
      try {
        const response = await postAuthPatientLoginPassword({
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
