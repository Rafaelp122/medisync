import { type UseQueryOptions, useMutation, useQuery } from "@tanstack/react-query";
import { client } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import {
  exportarBpaApiV1AmbulatoryProducaoExportarGet,
  listarProducaoApiV1AmbulatoryProducaoGet,
} from "@/api/generated/sdk.gen";
import type { ListaProducaoAmbulatorialResponse } from "@/api/generated/types.gen";

/**
 * Hook headless TanStack Query para listagem de produção ambulatorial SUS BPA-I (US-11 / RF-08).
 */
export function useProducaoBpa(
  competencia: string,
  token?: string,
  options?: Omit<
    UseQueryOptions<ListaProducaoAmbulatorialResponse, ProblemDetailsError>,
    "queryKey" | "queryFn"
  >,
) {
  return useQuery<ListaProducaoAmbulatorialResponse, ProblemDetailsError>({
    queryKey: ["ambulatory", "producao", competencia],
    queryFn: async () => {
      try {
        const headers: Record<string, string> = {};
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }

        const response = await listarProducaoApiV1AmbulatoryProducaoGet({
          client,
          query: { competencia, page: 1, size: 50 },
          headers,
          throwOnError: true,
        });
        return response.data;
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    enabled: /^\d{6}$/.test(competencia),
    ...options,
  });
}

/**
 * Hook headless de mutação para download/exportação do arquivo oficial BPA-I (.txt) (US-11 / RF-08).
 */
export function useExportarBpa(token?: string) {
  return useMutation<string, ProblemDetailsError, string>({
    mutationFn: async (competencia: string) => {
      try {
        const headers: Record<string, string> = {};
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }

        const response = await exportarBpaApiV1AmbulatoryProducaoExportarGet({
          client,
          query: { competencia },
          headers,
          throwOnError: true,
        });
        return typeof response.data === "string" ? response.data : String(response.data ?? "");
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
  });
}
