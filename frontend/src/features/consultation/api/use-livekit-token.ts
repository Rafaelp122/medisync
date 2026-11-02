import { type UseMutationOptions, useMutation } from "@tanstack/react-query";
import { client, getActiveTenantId } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { generateTeleconsultaRoomTokenApiV1ConsultationsAtendimentoIdLivekitTokenPost } from "@/api/generated/sdk.gen";
import type { LiveKitTokenRequest, LiveKitTokenResponse } from "@/api/generated/types.gen";

export interface LiveKitTokenParams extends LiveKitTokenRequest {
  atendimento_id?: string;
  token?: string;
}

/**
 * Hook headless de mutação para emissão de JWT assinado com Video Grants do LiveKit SFU.
 * Regras: RF-07, US-09, ADR-005.
 */
export function useLiveKitToken(
  atendimentoId?: string,
  options?: UseMutationOptions<LiveKitTokenResponse, ProblemDetailsError, LiveKitTokenParams>,
) {
  return useMutation<LiveKitTokenResponse, ProblemDetailsError, LiveKitTokenParams>({
    mutationFn: async ({ token, atendimento_id: paramId, ...body }: LiveKitTokenParams) => {
      const resolvedAtendimentoId = paramId || atendimentoId;
      if (!resolvedAtendimentoId) {
        throw new Error("atendimento_id é obrigatório para emissão de token LiveKit");
      }

      try {
        const headers: Record<string, string> = {
          "X-Tenant-ID": getActiveTenantId(),
        };
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }

        const response =
          await generateTeleconsultaRoomTokenApiV1ConsultationsAtendimentoIdLivekitTokenPost({
            client,
            path: {
              atendimento_id: resolvedAtendimentoId,
            },
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
