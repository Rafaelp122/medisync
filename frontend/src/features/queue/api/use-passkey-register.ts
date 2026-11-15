import { type UseMutationOptions, useMutation } from "@tanstack/react-query";
import { client, getActiveTenantId } from "@/api/client";
import { ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import {
  postAuthPatientWebauthnRegisterOptions,
  postAuthPatientWebauthnRegisterVerify,
} from "@/api/generated/sdk.gen";
import type { WebAuthnRegisterVerifyResponse } from "@/api/generated/types.gen";
import { base64UrlToUint8Array, bufferToBase64Url } from "@/lib/webauthn";

export interface RegisterPasskeyParams {
  token: string;
  deviceName?: string;
}

/**
 * Hook headless de mutação para cadastro de Passkey FIDO2/WebAuthn em /fila (US-14).
 * @see docs/user-stories/US-14-biometria-passkeys-webauthn.md
 */
export function usePasskeyRegister(
  options?: UseMutationOptions<
    WebAuthnRegisterVerifyResponse,
    ProblemDetailsError,
    RegisterPasskeyParams
  >,
) {
  return useMutation<WebAuthnRegisterVerifyResponse, ProblemDetailsError, RegisterPasskeyParams>({
    mutationFn: async ({ token, deviceName }: RegisterPasskeyParams) => {
      try {
        if (
          typeof navigator === "undefined" ||
          typeof navigator.credentials?.create !== "function"
        ) {
          throw new ProblemDetailsError({
            status: 400,
            detail: "Este navegador ou dispositivo não oferece suporte ativo a biometria WebAuthn.",
          });
        }

        const headers: Record<string, string> = {
          "X-Tenant-ID": getActiveTenantId(),
          Authorization: `Bearer ${token}`,
        };

        const optionsRes = await postAuthPatientWebauthnRegisterOptions({
          client,
          headers,
          throwOnError: true,
        });
        const creationOpts = optionsRes.data;

        const credential = (await navigator.credentials.create({
          publicKey: {
            challenge: base64UrlToUint8Array(creationOpts.challenge),
            rp: {
              name: creationOpts.rp.name,
              id: creationOpts.rp.id,
            },
            user: {
              id: base64UrlToUint8Array(creationOpts.user.id),
              name: creationOpts.user.name,
              displayName: creationOpts.user.displayName,
            },
            pubKeyCredParams: creationOpts.pubKeyCredParams.map((param) => ({
              alg: param.alg,
              type: "public-key" as const,
            })),
            timeout: creationOpts.timeout ?? 60_000,
            attestation:
              (creationOpts.attestation as AttestationConveyancePreference | undefined) ?? "none",
            authenticatorSelection: {
              userVerification: "preferred",
              residentKey: "preferred",
            },
          },
        })) as PublicKeyCredential | null;

        if (!credential) {
          throw new ProblemDetailsError({
            status: 400,
            detail: "Cadastro biométrico cancelado ou não autorizado no dispositivo.",
          });
        }

        const attestation = credential.response as AuthenticatorAttestationResponse;
        const verifyRes = await postAuthPatientWebauthnRegisterVerify({
          client,
          headers,
          body: {
            id: credential.id,
            rawId: bufferToBase64Url(credential.rawId),
            type: credential.type || "public-key",
            device_name: deviceName ?? "Biometria do Dispositivo",
            response: {
              clientDataJSON: bufferToBase64Url(attestation.clientDataJSON),
              attestationObject: bufferToBase64Url(attestation.attestationObject),
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
