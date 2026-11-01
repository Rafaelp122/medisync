import { type UseMutationOptions, useMutation } from "@tanstack/react-query";
import { client, getActiveTenantId } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { generateTeleconsultaRoomTokenApiV1ConsultationsAtendimentoIdLivekitTokenPost } from "@/api/generated/sdk.gen";
import type { LiveKitTokenRequest, LiveKitTokenResponse } from "@/api/generated/types.gen";

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
        const tenantId = Number.parseInt(getActiveTenantId(), 10) || 1;
        const body: LiveKitTokenRequest = {
          organizacao_id: tenantId,
          participant_id: pacienteId,
          role: "paciente",
          participant_name: nomePaciente ?? "Paciente",
          is_publisher: true,
          ttl_seconds: 3600,
        };

        const headers: Record<string, string> = {
          "X-Tenant-ID": String(tenantId),
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
