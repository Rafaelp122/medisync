import { type UseMutationOptions, useMutation, useQuery } from "@tanstack/react-query";
import { client } from "@/api/client";
import { ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import {
  getAuthPatientMethods,
  postAuthPatientWebauthnAuthenticateOptions,
  postAuthPatientWebauthnAuthenticateVerify,
  requestOtpApiV1AuthPatientOtpRequestPost,
  verifyOtpApiV1AuthPatientOtpVerifyPost,
} from "@/api/generated/sdk.gen";
import type {
  MetodosAutenticacaoPacienteResponse,
  RequestOtpApiV1AuthPatientOtpRequestPostResponse,
  SolicitarOtpRequest,
  VerificarOtpRequest,
  VerificarOtpResponse,
} from "@/api/generated/types.gen";
import { base64UrlToUint8Array, bufferToBase64Url } from "@/lib/webauthn";

/**
 * Hook headless de consulta às capacidades habilitadas de autenticação de pacientes.
 * Regras canônicas: RF-01, ADR-005 e ADR-011.
 */
export function usePatientMethods() {
  return useQuery<MetodosAutenticacaoPacienteResponse, ProblemDetailsError>({
    queryKey: ["auth", "patient", "methods"],
    queryFn: async () => {
      try {
        const response = await getAuthPatientMethods({
          client,
          throwOnError: true,
        });
        return response.data;
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    staleTime: 60_000,
  });
}

/**
 * Hook headless local da feature auth para solicitação de código OTP SMS do cidadão.
 * Evita import cruzado com features/onboarding mantendo conformidade estrita com ADR-011.
 */
export function usePatientSolicitarOtp(
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
    mutationFn: async (body: SolicitarOtpRequest) => {
      try {
        const response = await requestOtpApiV1AuthPatientOtpRequestPost({
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

/**
 * Hook headless local da feature auth para verificação do código OTP SMS de 6 dígitos.
 */
export function usePatientVerificarOtp(
  options?: UseMutationOptions<VerificarOtpResponse, ProblemDetailsError, VerificarOtpRequest>,
) {
  return useMutation<VerificarOtpResponse, ProblemDetailsError, VerificarOtpRequest>({
    mutationFn: async (body: VerificarOtpRequest) => {
      try {
        const response = await verifyOtpApiV1AuthPatientOtpVerifyPost({
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

export interface PatientPasskeyAuthParams {
  pacienteId?: string | null;
}

/**
 * Hook headless local da feature auth para login biométrico Passkey/WebAuthn (US-14).
 */
export function usePatientPasskeyAuth(
  options?: UseMutationOptions<
    VerificarOtpResponse,
    ProblemDetailsError,
    PatientPasskeyAuthParams | undefined
  >,
) {
  return useMutation<
    VerificarOtpResponse,
    ProblemDetailsError,
    PatientPasskeyAuthParams | undefined
  >({
    mutationFn: async (params?: PatientPasskeyAuthParams) => {
      try {
        if (typeof navigator === "undefined" || typeof navigator.credentials?.get !== "function") {
          throw new ProblemDetailsError({
            status: 400,
            detail: "Biometria WebAuthn indisponível neste navegador; utilize o código SMS.",
          });
        }

        const optionsRes = await postAuthPatientWebauthnAuthenticateOptions({
          client,
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
