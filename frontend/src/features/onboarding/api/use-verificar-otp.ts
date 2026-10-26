import { type UseMutationOptions, useMutation } from "@tanstack/react-query";
import { client, getActiveTenantId } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { verifyOtpApiV1AuthPatientOtpVerifyPost } from "@/api/generated/sdk.gen";
import type { VerificarOtpRequest, VerificarOtpResponse } from "@/api/generated/types.gen";

/**
 * Hook headless de mutação para verificação de código OTP de paciente e emissão de credencial.
 * Regras canônicas: RF-01, US-02 (Cenários 1 e 2) e ADR-011.
 * @see docs/user-stories/US-02-autenticacao-passwordless-otp.md
 */
export function useVerificarOtp(
  options?: UseMutationOptions<VerificarOtpResponse, ProblemDetailsError, VerificarOtpRequest>,
) {
  return useMutation<VerificarOtpResponse, ProblemDetailsError, VerificarOtpRequest>({
    mutationFn: async (payload: VerificarOtpRequest) => {
      try {
        const response = await verifyOtpApiV1AuthPatientOtpVerifyPost({
          client,
          body: payload,
          headers: {
            "X-Tenant-ID": getActiveTenantId(),
          },
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
