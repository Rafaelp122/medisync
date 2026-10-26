import { type UseMutationOptions, useMutation } from "@tanstack/react-query";
import { client, getActiveTenantId } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { requestOtpApiV1AuthPatientOtpRequestPost } from "@/api/generated/sdk.gen";
import type {
  RequestOtpApiV1AuthPatientOtpRequestPostResponse,
  SolicitarOtpRequest,
} from "@/api/generated/types.gen";

/**
 * Hook headless de mutação para solicitação de código OTP de paciente via SMS.
 * Regras canônicas: RF-01, US-02 (Cenários 1 e 3) e ADR-011.
 * @see docs/user-stories/US-02-autenticacao-passwordless-otp.md
 */
export function useSolicitarOtp(
  options?: UseMutationOptions<
    RequestOtpApiV1AuthPatientOtpRequestPostResponse,
    ProblemDetailsError,
    SolicitarOtpRequest
  >,
) {
  return useMutation<
    RequestOtpApiV1AuthPatientOtpRequestPostResponse,
    ProblemDetailsError,
    SolicitarOtpRequest
  >({
    mutationFn: async (payload: SolicitarOtpRequest) => {
      try {
        const response = await requestOtpApiV1AuthPatientOtpRequestPost({
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
