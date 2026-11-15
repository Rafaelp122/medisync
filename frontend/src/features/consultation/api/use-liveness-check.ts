import { type UseMutationOptions, useMutation } from "@tanstack/react-query";
import { client, getActiveTenantId } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import {
  solicitarDesafioLivenessPrescricaoApiV1ConsultationsAtendimentoIdPrescriptionsLivenessChallengePost,
  verificarLivenessPrescricaoApiV1ConsultationsAtendimentoIdPrescriptionsLivenessVerifyPost,
} from "@/api/generated/sdk.gen";
import type {
  LivenessChallengeResponse,
  LivenessVerifyRequest,
  LivenessVerifyResponse,
} from "@/api/generated/types.gen";

export interface SolicitarDesafioLivenessParams {
  token?: string;
}

export interface VerificarLivenessParams extends LivenessVerifyRequest {
  token?: string;
}

function buildHeaders(token?: string): Record<string, string> {
  const headers: Record<string, string> = {
    "X-Tenant-ID": getActiveTenantId(),
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

/**
 * Hook headless de mutação para solicitar desafio ativo de prova de vida facial (US-15).
 * @see docs/user-stories/US-15-prova-de-vida-facial-liveness.md
 */
export function useSolicitarDesafioLiveness(
  atendimentoId: string,
  options?: UseMutationOptions<
    LivenessChallengeResponse,
    ProblemDetailsError,
    SolicitarDesafioLivenessParams | undefined
  >,
) {
  return useMutation<
    LivenessChallengeResponse,
    ProblemDetailsError,
    SolicitarDesafioLivenessParams | undefined
  >({
    mutationFn: async (params?: SolicitarDesafioLivenessParams) => {
      try {
        const response =
          await solicitarDesafioLivenessPrescricaoApiV1ConsultationsAtendimentoIdPrescriptionsLivenessChallengePost(
            {
              client,
              path: { atendimento_id: atendimentoId },
              headers: buildHeaders(params?.token),
              throwOnError: true,
            },
          );
        return response.data;
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    ...options,
  });
}

/**
 * Hook headless de mutação para verificar frames de prova de vida facial (US-15).
 * @see docs/user-stories/US-15-prova-de-vida-facial-liveness.md
 */
export function useVerificarLiveness(
  atendimentoId: string,
  options?: UseMutationOptions<
    LivenessVerifyResponse,
    ProblemDetailsError,
    VerificarLivenessParams
  >,
) {
  return useMutation<LivenessVerifyResponse, ProblemDetailsError, VerificarLivenessParams>({
    mutationFn: async ({ token, ...body }: VerificarLivenessParams) => {
      try {
        const response =
          await verificarLivenessPrescricaoApiV1ConsultationsAtendimentoIdPrescriptionsLivenessVerifyPost(
            {
              client,
              path: { atendimento_id: atendimentoId },
              body,
              headers: buildHeaders(token),
              throwOnError: true,
            },
          );
        return response.data;
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    ...options,
  });
}
