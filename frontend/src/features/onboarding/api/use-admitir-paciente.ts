import { type UseMutationOptions, useMutation } from "@tanstack/react-query";
import { client, getActiveTenantId } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { admitirPacienteApiV1FilaAdmissaoPost } from "@/api/generated/sdk.gen";
import type {
  AdmissaoRequest,
  AdmitirPacienteApiV1FilaAdmissaoPostResponse,
} from "@/api/generated/types.gen";

import { admissaoSchema } from "../schemas/onboarding-schema";

export interface AdmitirPacienteParams {
  body: AdmissaoRequest;
  token?: string;
}

/**
 * Hook headless de mutação para Admissão e Triagem Clínica no PA Virtual.
 * Regras canônicas: RF-01, RN01, RN04 (Salvaguarda SAMU 192), US-01 e ADR-011.
 * @see docs/user-stories/US-01-acolhimento-triagem-tcle.md
 */
export function useAdmitirPaciente(
  options?: UseMutationOptions<
    AdmitirPacienteApiV1FilaAdmissaoPostResponse,
    ProblemDetailsError,
    AdmitirPacienteParams
  >,
) {
  return useMutation<
    AdmitirPacienteApiV1FilaAdmissaoPostResponse,
    ProblemDetailsError,
    AdmitirPacienteParams
  >({
    mutationFn: async ({ body, token }: AdmitirPacienteParams) => {
      try {
        const validatedBody = admissaoSchema.parse(body);
        const headers: Record<string, string> = {
          "X-Tenant-ID": getActiveTenantId(),
        };
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }

        const response = await admitirPacienteApiV1FilaAdmissaoPost({
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
