import { type UseMutationOptions, useMutation } from "@tanstack/react-query";
import { client, extractTenantIdFromJwt, getActiveTenantId, getTenantHeaders } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { generateTeleconsultaRoomTokenApiV1ConsultationsAtendimentoIdLivekitTokenPost } from "@/api/generated/sdk.gen";
import type { LiveKitTokenRequest, LiveKitTokenResponse } from "@/api/generated/types.gen";
import { getAccessToken } from "@/lib/auth-token";
import { getStoredToken } from "@/lib/session-storage";

export interface AtenderChamadaParams {
  atendimentoId: string;
  pacienteId: string;
  nomePaciente?: string | null;
  token?: string;
}

/**
 * Hook headless para atendimento tempestivo de chamada médica na fila virtual.
 * Regras: RF-03, RN02, US-08 e ADR-011.
 * Dispara emissão de token LiveKit SFU; no backend, transiciona o status para EM_ATENDIMENTO
 * e cancela o timeout determinístico de 45s.
 */
export function useAtenderChamada(
  options?: UseMutationOptions<LiveKitTokenResponse, ProblemDetailsError, AtenderChamadaParams>,
) {
  return useMutation<LiveKitTokenResponse, ProblemDetailsError, AtenderChamadaParams>({
    mutationFn: async ({
      atendimentoId,
      pacienteId,
      nomePaciente,
      token,
    }: AtenderChamadaParams) => {
      try {
        const activeTenant = getActiveTenantId();
        const parsedTenant = activeTenant ? Number.parseInt(activeTenant, 10) : Number.NaN;
        const resolvedTenantId =
          extractTenantIdFromJwt(token ?? getAccessToken() ?? getStoredToken()) ??
          (Number.isFinite(parsedTenant) && parsedTenant > 0 ? parsedTenant : undefined);

        const body = {
          ...(resolvedTenantId !== undefined ? { organizacao_id: resolvedTenantId } : {}),
          participant_id: pacienteId,
          role: "paciente" as const,
          participant_name: nomePaciente ?? "Paciente",
          is_publisher: true,
          ttl_seconds: 3600,
        } as LiveKitTokenRequest;

        const headers: Record<string, string> = {
          ...getTenantHeaders(),
        };
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }

        const response =
          await generateTeleconsultaRoomTokenApiV1ConsultationsAtendimentoIdLivekitTokenPost({
            client,
            path: { atendimento_id: atendimentoId },
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
