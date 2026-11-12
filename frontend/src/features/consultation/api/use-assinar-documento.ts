import { type UseMutationOptions, useMutation, useQueryClient } from "@tanstack/react-query";
import { client, getActiveTenantId } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { assinarDocumentoApiV1ConsultationsAtendimentoIdDocumentsDocumentoIdSignPost } from "@/api/generated/sdk.gen";
import type { AssinarDocumentoRequest, AssinarDocumentoResponse } from "@/api/generated/types.gen";
import { assinarDocumentoSchema } from "../schemas/consultation-schema";

export interface AssinarDocumentoParams {
  documento_id: string;
  payload: AssinarDocumentoRequest;
  token?: string;
}

/**
 * Hook headless de mutação para aplicar assinatura digital ICP-Brasil PAdES via PSC na nuvem.
 * Regras: RF-07, US-10, CFM nº 2.314/2022, ADR-006.
 */
export function useAssinarDocumento(
  atendimentoId: string,
  options?: UseMutationOptions<
    AssinarDocumentoResponse,
    ProblemDetailsError,
    AssinarDocumentoParams
  >,
) {
  const queryClient = useQueryClient();

  return useMutation<AssinarDocumentoResponse, ProblemDetailsError, AssinarDocumentoParams>({
    mutationFn: async ({ documento_id, payload, token }: AssinarDocumentoParams) => {
      try {
        const validatedPayload = assinarDocumentoSchema.parse(payload);
        const headers: Record<string, string> = {
          "X-Tenant-ID": getActiveTenantId(),
        };
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }

        const response =
          await assinarDocumentoApiV1ConsultationsAtendimentoIdDocumentsDocumentoIdSignPost({
            client,
            path: {
              atendimento_id: atendimentoId,
              documento_id,
            },
            body: validatedPayload,
            headers,
            throwOnError: true,
          });
        return response.data;
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    onSuccess: (data, variables, onMutateResult, context) => {
      queryClient.invalidateQueries({ queryKey: ["prontuario", atendimentoId] });
      options?.onSuccess?.(data, variables, onMutateResult, context);
    },
    ...options,
  });
}
