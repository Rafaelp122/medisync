import {
  AlertCircle,
  CheckCircle2,
  Download,
  FileCheck2,
  FileText,
  Loader2,
  QrCode,
  RotateCcw,
  ShieldCheck,
  Stethoscope,
} from "lucide-react";
import { extractProblemDetail } from "@/api/errors";
import type { PacienteDocumentoItemResponse } from "@/api/generated/types.gen";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { getTipoDocumentoLabel } from "@/lib/formatters";
import { cn } from "@/lib/utils";
import {
  useDownloadPatientConsultationPdf,
  usePatientConsultationDocuments,
} from "../api/use-patient-consultation-documents";

export interface PosConsultaSummaryProps {
  atendimentoId: string;
  pacienteNome?: string;
  medicoNome?: string;
  crmUf?: string;
  token?: string;
  documentos?: PacienteDocumentoItemResponse[];
  onNovaConsulta?: () => void;
  className?: string;
}

/**
 * Resumo Pós-Consulta do Paciente consumindo `/consultations/me/documentos`
 * e `/consultations/me/documents/{documento_id}/pdf` com rótulos canônicos.
 * @see docs/user-stories/US-09-teleconsulta-pep-soap.md
 */
export function PosConsultaSummary({
  atendimentoId,
  pacienteNome = "Cidadão",
  medicoNome = "Médico Plantonista",
  crmUf,
  token,
  documentos: docsProps,
  onNovaConsulta,
  className,
}: PosConsultaSummaryProps) {
  const {
    data: fetchedDocs,
    isLoading,
    isError: isDocsError,
    error: docsError,
  } = usePatientConsultationDocuments(token, {
    enabled: !docsProps,
  });

  const docs = docsProps
    ? docsProps
    : (fetchedDocs ?? []).filter((doc) => !atendimentoId || doc.atendimento_id === atendimentoId);
  const { downloadPdf, downloadingId, downloadError } = useDownloadPatientConsultationPdf();

  const handleDownloadPdf = async (documentoId: string, tipoDoc: string) => {
    await downloadPdf(documentoId, token, tipoDoc);
  };

  return (
    <div className={cn("w-full max-w-2xl mx-auto space-y-4", className)}>
      <Card className="border-emerald-500/40 bg-card shadow-md text-left">
        <CardHeader className="pb-3 space-y-2">
          <div className="flex items-center gap-3">
            <div className="size-12 rounded-full bg-emerald-100 dark:bg-emerald-950 flex items-center justify-center text-emerald-600 dark:text-emerald-400 shrink-0">
              <CheckCircle2 className="size-7" />
            </div>
            <div>
              <CardTitle className="text-xl sm:text-2xl font-bold text-foreground">
                Consulta Médica Concluída
              </CardTitle>
              <CardDescription className="text-xs sm:text-sm text-muted-foreground">
                Seu atendimento assistencial foi encerrado com sucesso pelo médico plantonista.
              </CardDescription>
            </div>
          </div>
        </CardHeader>

        <CardContent className="space-y-3.5 text-xs">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 p-3 bg-muted/50 rounded-lg border border-border">
            <div>
              <span className="text-muted-foreground block text-[11px]">Paciente:</span>
              <p className="font-semibold text-foreground text-sm">{pacienteNome}</p>
            </div>
            <div>
              <span className="text-muted-foreground block text-[11px]">Médico Responsável:</span>
              <p className="font-semibold text-foreground text-sm flex items-center gap-1.5">
                <Stethoscope className="size-3.5 text-primary" />
                <span>{medicoNome}</span>
                {crmUf && <span className="text-[11px] text-muted-foreground">(CRM {crmUf})</span>}
              </p>
            </div>
          </div>

          <div className="flex items-start gap-2.5 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-950 dark:text-emerald-100">
            <ShieldCheck className="size-5 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" />
            <div className="space-y-0.5">
              <p className="font-semibold text-xs">
                Documentos com Assinatura Digital ICP-Brasil (PAdES)
              </p>
              <p className="text-[11px] text-muted-foreground">
                Em conformidade com a MP nº 2.200-2/2001, Lei nº 14.063/2020 e Resoluções CFM nº
                2.299/2021 e nº 2.314/2022. Os documentos possuem QR Code para validação pública e
                são aceitos em farmácias e laboratórios de todo o território nacional.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="border-border shadow-sm text-left">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base font-bold text-foreground flex items-center gap-2">
              <FileCheck2 className="size-4 text-primary" />
              <span>Documentos Emitidos ({docs.length})</span>
            </CardTitle>
            <Badge variant="outline" className="text-[11px] py-0 px-2 gap-1 text-muted-foreground">
              <QrCode className="size-3" />
              <span>Validação ITI / CFM</span>
            </Badge>
          </div>
          <CardDescription className="text-xs text-muted-foreground">
            Baixe seus arquivos em PDF/A ou apresente o código de validação na farmácia.
          </CardDescription>
        </CardHeader>

        <CardContent className="space-y-3">
          {downloadError && (
            <Alert variant="destructive" role="alert" className="py-2.5 text-xs">
              <AlertCircle className="size-4" aria-hidden="true" />
              <AlertDescription className="text-xs">{downloadError}</AlertDescription>
            </Alert>
          )}
          {!docsProps && isDocsError ? (
            <Alert variant="destructive" role="alert" className="py-2.5 text-xs">
              <AlertCircle className="size-4" aria-hidden="true" />
              <AlertDescription className="text-xs">
                {extractProblemDetail(
                  docsError,
                  "Não foi possível carregar os documentos emitidos. Tente novamente.",
                )}
              </AlertDescription>
            </Alert>
          ) : isLoading && docs.length === 0 ? (
            <div className="flex items-center justify-center p-6 text-muted-foreground gap-2">
              <Loader2 className="size-4 animate-spin text-primary" />
              <span className="text-xs">Carregando documentos assinados…</span>
            </div>
          ) : docs.length === 0 ? (
            <div className="p-6 text-center text-muted-foreground border border-dashed rounded-lg">
              <FileText className="size-8 mx-auto mb-2 text-muted-foreground/60" />
              <p className="text-xs">
                Nenhum documento adicional (receita ou atestado) foi emitido nesta consulta.
              </p>
            </div>
          ) : (
            docs.map((doc) => {
              const labelDoc = getTipoDocumentoLabel(doc.tipo_documento);
              const isAssinado = Boolean(doc.assinado_em) || doc.status_assinatura === "ASSINADO";

              return (
                <div
                  key={doc.documento_id}
                  className="p-3.5 rounded-lg border border-border bg-card space-y-2.5 transition-colors hover:border-primary/40"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <FileText className="size-4 text-primary shrink-0" />
                        <h4 className="font-semibold text-xs text-foreground">{labelDoc}</h4>
                      </div>
                      {doc.token_validacao && (
                        <p className="text-[11px] text-muted-foreground font-mono">
                          Código / Validação ITI: <strong>{doc.token_validacao}</strong>
                        </p>
                      )}
                    </div>
                    <Badge
                      variant={isAssinado ? "success" : "secondary"}
                      className="text-[10px] py-0.5 px-2 shrink-0"
                    >
                      {isAssinado ? "Assinado ICP-Brasil" : "Processado"}
                    </Badge>
                  </div>

                  <div className="flex items-center justify-between pt-1">
                    <span className="text-[10px] text-muted-foreground">
                      ID: {doc.documento_id.substring(0, 8)}…
                    </span>
                    <Button
                      type="button"
                      size="sm"
                      onClick={() => handleDownloadPdf(doc.documento_id, doc.tipo_documento)}
                      disabled={downloadingId === doc.documento_id}
                      className="h-8 text-xs px-3 gap-1.5"
                    >
                      {downloadingId === doc.documento_id ? (
                        <>
                          <Loader2 className="size-3.5 animate-spin" />
                          <span>Baixando…</span>
                        </>
                      ) : (
                        <>
                          <Download className="size-3.5" />
                          <span>Baixar PDF</span>
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              );
            })
          )}
        </CardContent>

        {onNovaConsulta && (
          <CardFooter className="pt-2 border-t border-border flex justify-end">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onNovaConsulta}
              className="text-xs h-9 gap-1.5"
            >
              <RotateCcw className="size-3.5" />
              <span>Concluir e Voltar ao Início</span>
            </Button>
          </CardFooter>
        )}
      </Card>
    </div>
  );
}

export default PosConsultaSummary;
