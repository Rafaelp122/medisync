import { type UseMutationOptions, useMutation, useQueryClient } from "@tanstack/react-query";
import { client, getActiveTenantId } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { emitirDocumentoClinicoApiV1ConsultationsAtendimentoIdDocumentsPost } from "@/api/generated/sdk.gen";
import type { DocumentoClinicoResponse, EmitirDocumentoRequest } from "@/api/generated/types.gen";
import { emitirDocumentoSchema } from "../schemas/consultation-schema";

export interface EmitirDocumentoParams extends EmitirDocumentoRequest {
  token?: string;
}

/**
 * Hook headless de mutação para emitir documento clínico digital (receita simples/especial, atestado).
 * Aplica salvaguardas da Portaria 344/98 e RDC ANVISA 20/2011.
 * Regras: RF-07, US-10.
 */
export function useEmitirDocumento(
  atendimentoId: string,
  options?: UseMutationOptions<
    DocumentoClinicoResponse,
    ProblemDetailsError,
    EmitirDocumentoParams
  >,
) {
  const queryClient = useQueryClient();

  return useMutation<DocumentoClinicoResponse, ProblemDetailsError, EmitirDocumentoParams>({
    mutationFn: async ({ token, ...body }: EmitirDocumentoParams) => {
      try {
        const validatedBody = emitirDocumentoSchema.parse(body);
        const headers: Record<string, string> = {
          "X-Tenant-ID": getActiveTenantId(),
        };
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }

        const response = await emitirDocumentoClinicoApiV1ConsultationsAtendimentoIdDocumentsPost({
          client,
          path: {
            atendimento_id: atendimentoId,
          },
          body: validatedBody,
          headers,
          throwOnError: true,
        });
        return response.data;
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    onSuccess: (data, variables, context) => {
      queryClient.invalidateQueries({ queryKey: ["prontuario", atendimentoId] });
      options?.onSuccess?.(data, variables, context);
    },
    ...options,
  });
}
