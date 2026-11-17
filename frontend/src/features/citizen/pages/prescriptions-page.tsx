import { type LinkProps, useNavigate } from "@tanstack/react-router";
import { AlertCircle, Check, Download, FileText, Loader2, QrCode, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { extractProblemDetail } from "@/api/errors";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  useDownloadCitizenDocumentPdf,
  usePatientDocuments,
} from "@/features/citizen/api/use-patient-documents";
import { CitizenShellLayout } from "@/layouts/citizen-shell-layout";
import { formatarDataHoraBR, getTipoDocumentoLabel } from "@/lib/formatters";
import { getStoredSession, type StoredPatientSession } from "@/lib/session-storage";

type LinkTo = LinkProps["to"];

export interface PrescriptionsPageProps {
  session?: StoredPatientSession | null;
}

function getSignatureBadge(status: string) {
  const upper = status.trim().toUpperCase();
  if (upper.includes("ASSINAD") || upper === "VALIDO" || upper === "VALIDA") {
    return { variant: "success" as const, label: "Assinado ICP-Brasil" };
  }
  if (upper.includes("PENDENTE") || upper === "EMITIDO") {
    return { variant: "warning" as const, label: "Aguardando Assinatura" };
  }
  return { variant: "secondary" as const, label: status };
}

/**
 * Página de Receitas, Atestados e Documentos Clínicos do Cidadão (`/receitas`).
 * Permite baixar o PDF/A autenticado e copiar/validar o token ICP-Brasil em `/validar/$token`.
 */
export function PrescriptionsPage({ session }: PrescriptionsPageProps) {
  const activeSession = session ?? getStoredSession();
  const navigate = useNavigate();
  const [copiedDocId, setCopiedDocId] = useState<string | null>(null);

  const documentsQuery = usePatientDocuments(activeSession?.token);
  const { downloadPdf, downloadingId, downloadError } = useDownloadCitizenDocumentPdf();

  const handleCopyAndValidate = async (documentoId: string, tokenValidacao: string) => {
    try {
      if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(tokenValidacao);
        setCopiedDocId(documentoId);
      }
    } catch {
      // Clipboard pode não estar disponível em contextos não seguros
    }
    navigate({
      to: "/validar/$token" as LinkTo,
      params: { token: tokenValidacao } as never,
    });
  };

  const documentos = documentsQuery.data ?? [];

  return (
    <CitizenShellLayout session={activeSession}>
      <div className="space-y-5">
        <header className="space-y-1">
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            Receitas e Documentos
          </h1>
          <p className="text-sm text-muted-foreground">
            Acesse suas receitas médicas, atestados e pedidos de exame com assinatura digital
            ICP-Brasil.
          </p>
        </header>

        <div className="flex items-start gap-2.5 rounded-xl border border-border bg-muted/30 p-3.5 text-xs">
          <ShieldCheck className="h-4 w-4 text-primary shrink-0 mt-0.5" aria-hidden="true" />
          <p className="text-muted-foreground">
            Todos os documentos emitidos seguem o padrão PDF/A e podem ser validados publicamente em
            farmácias e empresas através do código de verificação ITI / CFM.
          </p>
        </div>

        {documentsQuery.isLoading && (
          <div
            role="status"
            aria-live="polite"
            className="flex items-center justify-center gap-2 rounded-xl border border-border bg-card p-8 text-sm text-muted-foreground"
          >
            <Loader2 className="h-4 w-4 animate-spin text-primary" aria-hidden="true" />
            <span>Carregando seus documentos clínicos…</span>
          </div>
        )}

        {documentsQuery.isError && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" aria-hidden="true" />
            <AlertTitle>Erro ao listar documentos</AlertTitle>
            <AlertDescription>
              {extractProblemDetail(
                documentsQuery.error,
                "Não foi possível obter suas receitas e documentos.",
              )}
            </AlertDescription>
          </Alert>
        )}

        {downloadError && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" aria-hidden="true" />
            <AlertTitle>Falha ao baixar PDF</AlertTitle>
            <AlertDescription>{downloadError}</AlertDescription>
          </Alert>
        )}

        {!documentsQuery.isLoading && !documentsQuery.isError && documentos.length === 0 && (
          <Card className="border-dashed border-border">
            <CardContent className="py-10 text-center space-y-2 text-muted-foreground">
              <FileText className="h-8 w-8 mx-auto opacity-60" aria-hidden="true" />
              <p className="text-sm font-medium text-foreground">
                Nenhum documento clínico emitido até o momento.
              </p>
              <p className="text-xs">
                Quando um profissional assinar sua receita ou atestado, ele ficará disponível aqui.
              </p>
            </CardContent>
          </Card>
        )}

        {documentos.length > 0 && (
          <div className="space-y-3">
            {documentos.map((doc) => {
              const badge = getSignatureBadge(doc.status_assinatura);
              const isDownloading = downloadingId === doc.documento_id;

              return (
                <Card key={doc.documento_id} className="border-border shadow-sm">
                  <CardHeader className="pb-3">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="space-y-1">
                        <CardTitle className="text-base flex items-center gap-2">
                          <FileText className="h-4 w-4 text-primary shrink-0" aria-hidden="true" />
                          <span>{getTipoDocumentoLabel(doc.tipo_documento)}</span>
                        </CardTitle>
                        <CardDescription className="text-xs">
                          Emitido em {formatarDataHoraBR(doc.criado_em)}
                          {doc.assinado_em
                            ? ` · Assinado em ${formatarDataHoraBR(doc.assinado_em)}`
                            : ""}
                        </CardDescription>
                      </div>
                      <Badge variant={badge.variant}>{badge.label}</Badge>
                    </div>
                  </CardHeader>

                  <CardContent className="space-y-3">
                    <div className="rounded-lg border border-border bg-muted/30 px-3 py-2 text-xs">
                      <span className="text-muted-foreground">Código de Validação ITI: </span>
                      <code className="font-mono font-semibold text-foreground">
                        {doc.token_validacao}
                      </code>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      <Button
                        type="button"
                        onClick={() =>
                          downloadPdf(doc.documento_id, doc.tipo_documento, activeSession?.token)
                        }
                        disabled={isDownloading}
                        className="min-h-[44px] gap-2"
                      >
                        {isDownloading ? (
                          <>
                            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                            <span>Baixando…</span>
                          </>
                        ) : (
                          <>
                            <Download className="h-4 w-4" aria-hidden="true" />
                            <span>Baixar PDF</span>
                          </>
                        )}
                      </Button>

                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => handleCopyAndValidate(doc.documento_id, doc.token_validacao)}
                        className="min-h-[44px] gap-2"
                      >
                        {copiedDocId === doc.documento_id ? (
                          <Check className="h-4 w-4 text-primary" aria-hidden="true" />
                        ) : (
                          <QrCode className="h-4 w-4" aria-hidden="true" />
                        )}
                        <span>Copiar / Validar Código</span>
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </CitizenShellLayout>
  );
}

export default PrescriptionsPage;
