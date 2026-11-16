import { type UseMutationOptions, useMutation } from "@tanstack/react-query";
import { client, getActiveTenantId } from "@/api/client";
import { ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import {
  postAuthPatientWebauthnAuthenticateOptions,
  postAuthPatientWebauthnAuthenticateVerify,
} from "@/api/generated/sdk.gen";
import type { VerificarOtpResponse } from "@/api/generated/types.gen";
import { base64UrlToUint8Array, bufferToBase64Url } from "@/lib/webauthn";

export interface AuthenticatePasskeyParams {
  pacienteId?: string | null;
}

/**
 * Hook headless de mutação para login em 1 toque via Passkey FIDO2/WebAuthn (US-14).
 * @see docs/user-stories/US-14-biometria-passkeys-webauthn.md
 */
export function usePasskeyAuth(
  options?: UseMutationOptions<
    VerificarOtpResponse,
    ProblemDetailsError,
    AuthenticatePasskeyParams | undefined
  >,
) {
  return useMutation<
    VerificarOtpResponse,
    ProblemDetailsError,
    AuthenticatePasskeyParams | undefined
  >({
    mutationFn: async (params?: AuthenticatePasskeyParams) => {
      try {
        if (typeof navigator === "undefined" || typeof navigator.credentials?.get !== "function") {
          throw new ProblemDetailsError({
            status: 400,
            detail: "Biometria WebAuthn indisponível neste navegador; utilize o código SMS.",
          });
        }

        const headers: Record<string, string> = {
          "X-Tenant-ID": getActiveTenantId(),
        };

        const optionsRes = await postAuthPatientWebauthnAuthenticateOptions({
          client,
          headers,
          body: params?.pacienteId ? { paciente_id: params.pacienteId } : undefined,
          throwOnError: true,
        });
        const requestOpts = optionsRes.data;

        const assertion = (await navigator.credentials.get({
          publicKey: {
            challenge: base64UrlToUint8Array(requestOpts.challenge),
            rpId: requestOpts.rpId,
            timeout: requestOpts.timeout ?? 60_000,
            userVerification:
              (requestOpts.userVerification as UserVerificationRequirement | undefined) ??
              "preferred",
            allowCredentials: requestOpts.allowCredentials.map((cred) => ({
              id: base64UrlToUint8Array(cred.id),
              type: "public-key" as const,
            })),
          },
        })) as PublicKeyCredential | null;

        if (!assertion) {
          throw new ProblemDetailsError({
            status: 401,
            detail: "Autenticação biométrica cancelada pelo usuário.",
          });
        }

        const assertionResp = assertion.response as AuthenticatorAssertionResponse;
        const verifyRes = await postAuthPatientWebauthnAuthenticateVerify({
          client,
          headers,
          body: {
            id: assertion.id,
            rawId: bufferToBase64Url(assertion.rawId),
            type: assertion.type || "public-key",
            response: {
              clientDataJSON: bufferToBase64Url(assertionResp.clientDataJSON),
              authenticatorData: bufferToBase64Url(assertionResp.authenticatorData),
              signature: bufferToBase64Url(assertionResp.signature),
              ...(assertionResp.userHandle
                ? { userHandle: bufferToBase64Url(assertionResp.userHandle) }
                : {}),
            },
          },
          throwOnError: true,
        });
        return verifyRes.data;
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    ...options,
  });
}
