import { type UseQueryOptions, useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { client, getSessionQueryScope } from "@/api/client";
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
 * Hook headless de documentos do paciente autenticado (`GET /consultations/me/documentos`).
 * @see docs/user-stories/US-09-teleconsulta-pep-soap.md
 */
export function usePatientConsultationDocuments(
  token?: string,
  options?: Omit<
    UseQueryOptions<PacienteDocumentoItemResponse[], ProblemDetailsError>,
    "queryKey" | "queryFn"
  >,
) {
  const scopeKey = getSessionQueryScope();
  return useQuery<PacienteDocumentoItemResponse[], ProblemDetailsError>({
    queryKey: ["consultation", "me", "documents", scopeKey],
    queryFn: async () => {
      try {
        const headers: Record<string, string> = {};
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }
        const response = await listarDocumentosPacienteApiV1ConsultationsMeDocumentosGet({
          client,
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

/**
 * Hook headless de download seguro de PDF pelo paciente (`/consultations/me/documents/{id}/pdf`).
 */
export function useDownloadPatientConsultationPdf() {
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const downloadPdf = useCallback(
    async (documentoId: string, token?: string, tipoDocumento?: string) => {
      setDownloadingId(documentoId);
      setDownloadError(null);
      try {
        const headers: Record<string, string> = {};
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }
        const response =
          await obterDocumentoPdfPacienteApiV1ConsultationsMeDocumentsDocumentoIdPdfGet({
            client,
            path: { documento_id: documentoId },
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
        const prefix = (tipoDocumento || "documento").toLowerCase().replace(/_/g, "-");
        link.download = `${prefix}-${documentoId.substring(0, 8)}.pdf`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        setTimeout(() => window.URL.revokeObjectURL(blobUrl), 100);
      } catch (err) {
        setDownloadError(extractProblemDetail(err, "Erro ao baixar o arquivo PDF."));
      } finally {
        setDownloadingId(null);
      }
    },
    [],
  );

  return { downloadPdf, downloadingId, downloadError };
}
