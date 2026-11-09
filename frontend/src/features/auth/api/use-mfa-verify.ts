import { type UseMutationOptions, useMutation } from "@tanstack/react-query";
import { client, getActiveTenantId } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { mfaVerifyApiV1AuthMfaVerifyPost } from "@/api/generated/sdk.gen";
import type { MfaVerificarLoginRequest, TokenResponse } from "@/api/generated/types.gen";

export function useMfaVerify(
  options?: UseMutationOptions<TokenResponse, ProblemDetailsError, MfaVerificarLoginRequest>,
) {
  return useMutation<TokenResponse, ProblemDetailsError, MfaVerificarLoginRequest>({
    mutationFn: async (body: MfaVerificarLoginRequest) => {
      try {
        const headers: Record<string, string> = {
          "X-Tenant-ID": getActiveTenantId(),
        };

        const response = await mfaVerifyApiV1AuthMfaVerifyPost({
          client,
          headers,
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
