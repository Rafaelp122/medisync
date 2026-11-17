import { type UseQueryOptions, useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { client, getSessionQueryScope, resolveExplicitAuthHeaders } from "@/api/client";
import {
  extractProblemDetail,
  type ProblemDetailsError,
  toProblemDetailsError,
} from "@/api/errors";
import {
  listarDocumentosPacienteApiV1ConsultationsMeDocumentosGet,
  obterDocumentoPdfPacienteApiV1ConsultationsMeDocumentsDocumentoIdPdfGet,
} from "@/api/generated/sdk.gen";
import type { PacienteDocumentoItemResponse } from "@/api/generated/types.gen";

/**
 * Hook headless para listar receitas, atestados e pedidos de exame do paciente autenticado.
 */
export function usePatientDocuments(
  token?: string,
  options?: Omit<
    UseQueryOptions<PacienteDocumentoItemResponse[], ProblemDetailsError>,
    "queryKey" | "queryFn"
  >,
) {
  const scopeKey = getSessionQueryScope(token);
  return useQuery<PacienteDocumentoItemResponse[], ProblemDetailsError>({
    queryKey: ["citizen", "documents", scopeKey],
    queryFn: async () => {
      try {
        const response = await listarDocumentosPacienteApiV1ConsultationsMeDocumentosGet({
          client,
          headers: resolveExplicitAuthHeaders(token),
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

export interface UseDownloadCitizenDocumentPdfReturn {
  downloadPdf: (documentoId: string, tipoDocumento?: string, token?: string) => Promise<void>;
  downloadingId: string | null;
  downloadError: string | null;
}

/**
 * Hook headless para download seguro de PDF/A de documentos do paciente via Blob.
 */
export function useDownloadCitizenDocumentPdf(): UseDownloadCitizenDocumentPdfReturn {
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const downloadPdf = useCallback(
    async (documentoId: string, tipoDocumento?: string, token?: string) => {
      setDownloadingId(documentoId);
      setDownloadError(null);
      try {
        const response =
          await obterDocumentoPdfPacienteApiV1ConsultationsMeDocumentsDocumentoIdPdfGet({
            client,
            path: { documento_id: documentoId },
            headers: resolveExplicitAuthHeaders(token),
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
        const prefix = (tipoDocumento || "documento").toLowerCase().replace(/_/g, "-");
        link.download = `${prefix}-${documentoId.substring(0, 8)}.pdf`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(blobUrl);
      } catch (err) {
        setDownloadError(
          extractProblemDetail(err, "Não foi possível baixar o PDF deste documento."),
        );
      } finally {
        setDownloadingId(null);
      }
    },
    [],
  );

  return {
    downloadPdf,
    downloadingId,
    downloadError,
  };
}
