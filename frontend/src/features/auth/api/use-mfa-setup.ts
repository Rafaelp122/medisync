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

export interface MfaSetupParams {
  tempToken?: string;
}

/**
 * Hook headless de mutação para gerar segredo TOTP Base32 e URI otpauth:// (MFA Setup).
 * Aceita token temporário `mfa_pending` quando disparado durante o primeiro login.
 * Regras canônicas: RN-AUT-04, RN-AUT-08 e ADR-011.
 */
export function useMfaSetup(
  options?: UseMutationOptions<MfaSetupResponse, ProblemDetailsError, MfaSetupParams | undefined>,
) {
  return useMutation<MfaSetupResponse, ProblemDetailsError, MfaSetupParams | undefined>({
    mutationFn: async (params?: MfaSetupParams) => {
      try {
        const headers = params?.tempToken
          ? { Authorization: `Bearer ${params.tempToken}` }
          : undefined;
        const response = await mfaSetupApiV1AuthMfaSetupPost({
          client,
          headers,
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

export interface MfaActivateParams {
  body: MfaAtivarRequest;
  tempToken?: string;
}

/**
 * Hook headless de mutação para validar o primeiro código TOTP e ativar o MFA do profissional.
 * Regras canônicas: RN-AUT-04, RN-AUT-08 e ADR-011.
 */
export function useMfaActivate(
  options?: UseMutationOptions<MfaAtivarResponse, ProblemDetailsError, MfaActivateParams>,
) {
  return useMutation<MfaAtivarResponse, ProblemDetailsError, MfaActivateParams>({
    mutationFn: async ({ body, tempToken }: MfaActivateParams) => {
      try {
        const headers = tempToken ? { Authorization: `Bearer ${tempToken}` } : undefined;
        const response = await mfaActivateApiV1AuthMfaActivatePost({
          client,
          body,
          headers,
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
