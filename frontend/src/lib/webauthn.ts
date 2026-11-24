import { client } from "@/api/client";
import { ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import {
  postAuthPatientWebauthnRegisterOptions,
  postAuthPatientWebauthnRegisterVerify,
} from "@/api/generated/sdk.gen";
import type { WebAuthnRegisterVerifyResponse } from "@/api/generated/types.gen";

/**
 * Utilitários WebAuthn / FIDO2 para detecção de suporte, codificação Base64url <-> ArrayBuffer
 * e cerimônia compartilhada de cadastro de Passkey do cidadão (RF-01, ADR-005, US-14).
 */
export function isWebAuthnSupported(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  return Boolean(window.PublicKeyCredential && typeof window.PublicKeyCredential === "function");
}

export function base64UrlToUint8Array(base64url: string): Uint8Array<ArrayBuffer> {
  const normalized = base64url.replace(/-/g, "+").replace(/_/g, "/");
  const padding = "=".repeat((4 - (normalized.length % 4)) % 4);
  const binary = window.atob(normalized + padding);
  const buffer = new ArrayBuffer(binary.length);
  const bytes = new Uint8Array(buffer);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

export function bufferToBase64Url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return window.btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export interface RegisterPasskeyCredentialParams {
  token: string;
  deviceName?: string;
}

/**
 * Executa a cerimônia completa WebAuthn (`register/options` -> `navigator.credentials.create` -> `register/verify`).
 * @see docs/user-stories/US-14-biometria-passkeys-webauthn.md
 */
export async function registerPatientPasskeyCredential({
  token,
  deviceName,
}: RegisterPasskeyCredentialParams): Promise<WebAuthnRegisterVerifyResponse> {
  try {
    if (typeof navigator === "undefined" || typeof navigator.credentials?.create !== "function") {
      throw new ProblemDetailsError({
        status: 400,
        detail: "Este navegador ou dispositivo não oferece suporte ativo a biometria WebAuthn.",
      });
    }

    const headers: Record<string, string> = {
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
      headers,
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
}
