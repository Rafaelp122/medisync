import { type UseMutationOptions, useMutation } from "@tanstack/react-query";
import { client } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import {
  mfaActivateApiV1AuthMfaActivatePost,
  mfaSetupApiV1AuthMfaSetupPost,
} from "@/api/generated/sdk.gen";
import type {
  MfaAtivarRequest,
  MfaAtivarResponse,
  MfaSetupResponse,
} from "@/api/generated/types.gen";

/**
 * Hook headless de mutação para gerar segredo TOTP Base32 e URI otpauth:// (MFA Setup).
 * Regras canônicas: RN-AUT-04, RN-AUT-08 e ADR-011.
 */
export function useMfaSetup(
  options?: UseMutationOptions<MfaSetupResponse, ProblemDetailsError, void>,
) {
  return useMutation<MfaSetupResponse, ProblemDetailsError, void>({
    mutationFn: async () => {
      try {
        const response = await mfaSetupApiV1AuthMfaSetupPost({
          client,
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

/**
 * Hook headless de mutação para validar o primeiro código TOTP e ativar o MFA do profissional.
 * Regras canônicas: RN-AUT-04, RN-AUT-08 e ADR-011.
 */
export function useMfaActivate(
  options?: UseMutationOptions<MfaAtivarResponse, ProblemDetailsError, MfaAtivarRequest>,
) {
  return useMutation<MfaAtivarResponse, ProblemDetailsError, MfaAtivarRequest>({
    mutationFn: async (body: MfaAtivarRequest) => {
      try {
        const response = await mfaActivateApiV1AuthMfaActivatePost({
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
