import { type UseMutationOptions, useMutation } from "@tanstack/react-query";
import { client, getActiveTenantId } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { comunicarPioraClinicaApiV1FilaPioraPost } from "@/api/generated/sdk.gen";
import type { PioraClinicaRequest, PioraClinicaResponse } from "@/api/generated/types.gen";
import { pioraClinicaFormSchema } from "../schemas/piora-clinica-schema";

export interface ComunicarPioraParams {
  body: PioraClinicaRequest;
  token?: string;
}

/**
 * Hook headless de mutação para comunicação de piora clínica pelo paciente na fila (RF-06).
 * Se emergência máxima (Vermelho), dispara alerta SAMU; caso contrário recalcula score.
 */
export function useComunicarPiora(
  options?: UseMutationOptions<PioraClinicaResponse, ProblemDetailsError, ComunicarPioraParams>,
) {
  return useMutation<PioraClinicaResponse, ProblemDetailsError, ComunicarPioraParams>({
    mutationFn: async ({ body, token }: ComunicarPioraParams) => {
      try {
        const validatedBody = pioraClinicaFormSchema.parse(body);
        const headers: Record<string, string> = {
          "X-Tenant-ID": getActiveTenantId(),
        };
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }
        const response = await comunicarPioraClinicaApiV1FilaPioraPost({
          client,
          body: validatedBody,
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
