import { useCallback, useState } from "react";
import { getActiveTenantId } from "@/api/client";

export interface UseDownloadDocumentoPdfReturn {
  downloadPdf: (documentoId: string, token?: string) => Promise<void>;
  downloadingId: string | null;
  isDownloading: boolean;
}

/**
 * Hook headless para download seguro de documento clínico compilado em PDF/A.
 * Encapsula obtenção de stream binário, injeção de headers e gestão de Blob URL.
 * Regras: US-09, US-10, CFM nº 2.314/2022, ADR-011 §2.3.
 */
export function useDownloadDocumentoPdf(atendimentoId: string): UseDownloadDocumentoPdfReturn {
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const downloadPdf = useCallback(
    async (documentoId: string, token?: string) => {
      try {
        setDownloadingId(documentoId);
        const headers: Record<string, string> = {
          "X-Tenant-ID": getActiveTenantId(),
        };
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }

        const res = await fetch(
          `/api/v1/consultations/${atendimentoId}/documents/${documentoId}/pdf`,
          { headers },
        );

        if (!res.ok) {
          throw new Error(`Falha ao obter PDF do documento (status ${res.status})`);
        }

        const blob = await res.blob();
        const blobUrl = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = blobUrl;
        link.download = `receita-${documentoId.substring(0, 8)}.pdf`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(blobUrl);
      } catch (err) {
        console.error("Erro no download de PDF:", err);
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
  };
}
