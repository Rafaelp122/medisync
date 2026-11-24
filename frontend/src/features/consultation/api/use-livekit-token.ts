import { type UseMutationOptions, useMutation } from "@tanstack/react-query";
import { client } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { generateTeleconsultaRoomTokenApiV1ConsultationsAtendimentoIdLivekitTokenPost } from "@/api/generated/sdk.gen";
import type { LiveKitTokenRequest, LiveKitTokenResponse } from "@/api/generated/types.gen";
import { zLiveKitTokenRequest, zLiveKitTokenResponse } from "@/api/generated/zod.gen";

export interface LiveKitTokenParams extends LiveKitTokenRequest {
  atendimento_id?: string;
  token?: string;
}

/**
 * Hook headless de mutação para emissão de JWT assinado com Video Grants do LiveKit SFU.
 * Valida entrada e resposta em runtime via `zLiveKitTokenRequest` / `zLiveKitTokenResponse`.
 * Regras: RF-07, US-09, ADR-005.
 */
export function useLiveKitToken(
  atendimentoId?: string,
  options?: UseMutationOptions<LiveKitTokenResponse, ProblemDetailsError, LiveKitTokenParams>,
) {
  return useMutation<LiveKitTokenResponse, ProblemDetailsError, LiveKitTokenParams>({
    mutationFn: async ({ token, atendimento_id: paramId, ...rawBody }: LiveKitTokenParams) => {
      const resolvedAtendimentoId = paramId || atendimentoId;
      if (!resolvedAtendimentoId) {
        throw new Error("atendimento_id é obrigatório para emissão de token LiveKit");
      }

      try {
        const parsedBody = zLiveKitTokenRequest.parse(rawBody);
        const headers: Record<string, string> = {};
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }

        const response =
          await generateTeleconsultaRoomTokenApiV1ConsultationsAtendimentoIdLivekitTokenPost({
            client,
            path: {
              atendimento_id: resolvedAtendimentoId,
            },
            body: parsedBody,
            headers,
            throwOnError: true,
          });
        return zLiveKitTokenResponse.parse(response.data);
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    ...options,
  });
}
