import { type UseMutationOptions, useMutation } from "@tanstack/react-query";
import { client, getActiveTenantId } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { validarPrescricaoMedicamentoApiV1ConsultationsAtendimentoIdPrescriptionsValidatePost } from "@/api/generated/sdk.gen";
import type {
  ValidarPrescricaoRequest,
  ValidarPrescricaoResponse,
} from "@/api/generated/types.gen";

export interface PrescricaoValidatorParams extends ValidarPrescricaoRequest {
  token?: string;
}

/**
 * Hook headless de validação prévia de substâncias contra a Portaria SVS/MS nº 344/98.
 * Bloqueia medicamentos das Listas A e B (talonário físico obrigatório).
 * Regras: RF-07, US-10.
 */
export function usePrescricaoValidator(
  atendimentoId: string,
  options?: UseMutationOptions<
    ValidarPrescricaoResponse,
    ProblemDetailsError,
    PrescricaoValidatorParams
  >,
) {
  return useMutation<ValidarPrescricaoResponse, ProblemDetailsError, PrescricaoValidatorParams>({
    mutationFn: async ({ token, ...body }: PrescricaoValidatorParams) => {
      try {
        const headers: Record<string, string> = {
          "X-Tenant-ID": getActiveTenantId(),
        };
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }

        const response =
          await validarPrescricaoMedicamentoApiV1ConsultationsAtendimentoIdPrescriptionsValidatePost(
            {
              client,
              path: {
                atendimento_id: atendimentoId,
              },
              body,
              headers,
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
