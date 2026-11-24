import { type UseQueryOptions, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { client, getSessionQueryScope } from "@/api/client";
import { type ProblemDetailsError, toProblemDetailsError } from "@/api/errors";
import {
  exportarBpaApiV1AmbulatoryProducaoExportarGet,
  listarProducaoApiV1AmbulatoryProducaoGet,
} from "@/api/generated/sdk.gen";
import type { ListaProducaoAmbulatorialResponse } from "@/api/generated/types.gen";

export const AMBULATORY_PRODUCAO_QUERY_KEY_PREFIX = ["ambulatory", "producao"] as const;

export interface ExportarBpaResult {
  conteudo: string;
  filename: string | null;
}

export function extractFilenameFromContentDisposition(headerValue: string | null): string | null {
  if (!headerValue) return null;

  const utf8Match = headerValue.match(/filename\*=UTF-8''([^;\r\n]+)/i);
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1].trim().replace(/^["']|["']$/g, ""));
    } catch {
      return utf8Match[1].trim().replace(/^["']|["']$/g, "");
    }
  }

  const quotedMatch = headerValue.match(/filename="([^"]+)"/i);
  if (quotedMatch?.[1]) {
    return quotedMatch[1].trim();
  }

  const bareMatch = headerValue.match(/filename=([^;\s\r\n]+)/i);
  if (bareMatch?.[1]) {
    return bareMatch[1].trim().replace(/^["']|["']$/g, "");
  }

  return null;
}

/**
 * Hook headless TanStack Query para listagem de produção ambulatorial SUS BPA-I (US-11 / RF-08).
 * Escopa cache por sessão ativa via `getSessionQueryScope()`.
 * Regras: ADR-011, docs/user-stories/US-11-liquidacao-fechamento-contabil.md.
 */
export function useProducaoBpa(
  competencia: string,
  options?: Omit<
    UseQueryOptions<ListaProducaoAmbulatorialResponse, ProblemDetailsError>,
    "queryKey" | "queryFn"
  >,
) {
  const scopeKey = getSessionQueryScope();
  return useQuery<ListaProducaoAmbulatorialResponse, ProblemDetailsError>({
    queryKey: [...AMBULATORY_PRODUCAO_QUERY_KEY_PREFIX, scopeKey, competencia],
    queryFn: async () => {
      try {
        const response = await listarProducaoApiV1AmbulatoryProducaoGet({
          client,
          query: { competencia, page: 1, size: 50 },
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
 * Retorna o conteúdo textual e o nome oficial extraído de Content-Disposition quando presente.
 */
export function useExportarBpa() {
  const queryClient = useQueryClient();
  return useMutation<ExportarBpaResult, ProblemDetailsError, string>({
    mutationFn: async (competencia: string) => {
      try {
        const response = await exportarBpaApiV1AmbulatoryProducaoExportarGet({
          client,
          query: { competencia },
          throwOnError: true,
        });
        const conteudo =
          typeof response.data === "string" ? response.data : String(response.data ?? "");
        const contentDisposition = response.response?.headers.get("Content-Disposition") ?? null;
        return {
          conteudo,
          filename: extractFilenameFromContentDisposition(contentDisposition),
        };
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...AMBULATORY_PRODUCAO_QUERY_KEY_PREFIX] });
    },
  });
}
