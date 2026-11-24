import { type UseMutationOptions, useMutation } from "@tanstack/react-query";
import { client } from "@/api/client";
import { ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import {
  postAuthPatientWebauthnRegisterOptions,
  postAuthPatientWebauthnRegisterVerify,
} from "@/api/generated/sdk.gen";
import type { WebAuthnRegisterVerifyResponse } from "@/api/generated/types.gen";
import { base64UrlToUint8Array, bufferToBase64Url } from "@/lib/webauthn";

export interface CitizenPasskeyParams {
  deviceName?: string;
}

/**
 * Hook headless para ativação de Passkey WebAuthn no perfil do cidadão (US-14).
 */
export function useCitizenPasskeyRegister(
  options?: UseMutationOptions<
    WebAuthnRegisterVerifyResponse,
    ProblemDetailsError,
    CitizenPasskeyParams
  >,
) {
  return useMutation<WebAuthnRegisterVerifyResponse, ProblemDetailsError, CitizenPasskeyParams>({
    mutationFn: async ({ deviceName }: CitizenPasskeyParams = {}) => {
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

        const optionsRes = await postAuthPatientWebauthnRegisterOptions({
          client,
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
              userVerification:
                (creationOpts.authenticatorSelection?.userVerification as
                  | UserVerificationRequirement
                  | undefined) ?? "preferred",
              residentKey:
                (creationOpts.authenticatorSelection?.residentKey as
                  | ResidentKeyRequirement
                  | undefined) ?? "required",
              requireResidentKey: creationOpts.authenticatorSelection?.requireResidentKey ?? true,
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
        const pubKeyBuf =
          typeof attestation.getPublicKey === "function" ? attestation.getPublicKey() : null;

        const verifyRes = await postAuthPatientWebauthnRegisterVerify({
          client,
          body: {
            id: credential.id,
            rawId: bufferToBase64Url(credential.rawId),
            type: credential.type || "public-key",
            device_name: deviceName ?? "Biometria do Dispositivo",
            response: {
              clientDataJSON: bufferToBase64Url(attestation.clientDataJSON),
              attestationObject: bufferToBase64Url(attestation.attestationObject),
              ...(pubKeyBuf ? { publicKey: bufferToBase64Url(pubKeyBuf) } : {}),
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
