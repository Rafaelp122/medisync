import { type UseMutationOptions, useMutation } from "@tanstack/react-query";
import { client } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { validarPrescricaoMedicamentoApiV1ConsultationsAtendimentoIdPrescriptionsValidatePost } from "@/api/generated/sdk.gen";
import type {
  ValidarPrescricaoRequest,
  ValidarPrescricaoResponse,
} from "@/api/generated/types.gen";
import { zValidarPrescricaoRequest, zValidarPrescricaoResponse } from "@/api/generated/zod.gen";

export interface PrescricaoValidatorParams extends ValidarPrescricaoRequest {
  token?: string;
}

/**
 * Hook headless de validação prévia de substâncias contra a Portaria SVS/MS nº 344/98.
 * Valida entrada e resposta em runtime via `zValidarPrescricaoRequest` / `zValidarPrescricaoResponse`.
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
    mutationFn: async ({ token, ...rawBody }: PrescricaoValidatorParams) => {
      try {
        const parsedBody = zValidarPrescricaoRequest.parse(rawBody);
        const headers: Record<string, string> = {};
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
              body: parsedBody,
              headers,
              throwOnError: true,
            },
          );
        return zValidarPrescricaoResponse.parse(response.data);
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    ...options,
  });
}
