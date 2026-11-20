import { type UseQueryOptions, useQuery } from "@tanstack/react-query";
import { client } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import { validarDocumentoApiV1DocumentsValidateTokenValidacaoGet } from "@/api/generated/sdk.gen";
import type { ValidarDocumentoResponse } from "@/api/generated/types.gen";

/**
 * Hook headless de consulta pública para validação de autenticidade de documentos clínicos
 * emitidos pelo MediSync Express (QR Code CFM/ITI com mascaramento LGPD).
 * Regras: CFM nº 2.299/2021, nº 2.314/2022 e LGPD.
 */
export function useValidateDocument(
  tokenValidacao: string,
  options?: Omit<
    UseQueryOptions<ValidarDocumentoResponse, ProblemDetailsError>,
    "queryKey" | "queryFn"
  >,
) {
  const normalizedToken = tokenValidacao.trim();

  return useQuery<ValidarDocumentoResponse, ProblemDetailsError>({
    queryKey: ["validate-document", normalizedToken],
    queryFn: async () => {
      try {
        const response = await validarDocumentoApiV1DocumentsValidateTokenValidacaoGet({
          client,
          path: { token_validacao: normalizedToken },
          throwOnError: true,
        });
        return response.data;
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    enabled: Boolean(normalizedToken),
    retry: false,
    ...options,
  });
}
