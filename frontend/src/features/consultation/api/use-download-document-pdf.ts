import { useCallback, useState } from "react";
import { client, getTenantHeaders } from "@/api/client";
import {
  extractProblemDetail,
  type ProblemDetailsError,
  toProblemDetailsError,
} from "@/api/errors";
import { obterDocumentoPdfApiV1ConsultationsAtendimentoIdDocumentsDocumentoIdPdfGet } from "@/api/generated/sdk.gen";

export interface UseDownloadDocumentoPdfReturn {
  downloadPdf: (documentoId: string, token?: string, tipoDoc?: string) => Promise<void>;
  downloadingId: string | null;
  isDownloading: boolean;
  error: ProblemDetailsError | null;
  downloadError: string | null;
}

/**
 * Hook headless para download seguro de documento clínico compilado em PDF/A.
 * Encapsula obtenção de stream binário via SDK gerado, injeção de headers e gestão de Blob URL.
 * Regras: US-09, US-10, CFM nº 2.314/2022, ADR-011 §2.3.
 */
export function useDownloadDocumentoPdf(atendimentoId: string): UseDownloadDocumentoPdfReturn {
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [error, setError] = useState<ProblemDetailsError | null>(null);

  const downloadPdf = useCallback(
    async (documentoId: string, token?: string, tipoDoc?: string) => {
      setDownloadingId(documentoId);
      setError(null);
      try {
        const headers: Record<string, string> = {
          ...getTenantHeaders(),
        };
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }

        const response =
          await obterDocumentoPdfApiV1ConsultationsAtendimentoIdDocumentsDocumentoIdPdfGet({
            client,
            path: {
              atendimento_id: atendimentoId,
              documento_id: documentoId,
            },
            headers,
            parseAs: "blob",
            throwOnError: true,
          });

        const rawData = response.data as unknown;
        const blob =
          rawData instanceof Blob
            ? rawData
            : new Blob([rawData as BlobPart], { type: "application/pdf" });

        const blobUrl = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = blobUrl;
        const cleanTipo = (tipoDoc || "receita").toLowerCase().replace(/_/g, "-");
        link.download = `${cleanTipo}-${documentoId.substring(0, 8)}.pdf`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(blobUrl);
      } catch (err) {
        setError(toProblemDetailsError(err));
      } finally {
        setDownloadingId(null);
      }
    },
    [atendimentoId],
  );

  return {
    downloadPdf,
    downloadingId,
    isDownloading: downloadingId !== null,
    error,
    downloadError: error ? extractProblemDetail(error, "Falha ao obter PDF do documento.") : null,
  };
}
