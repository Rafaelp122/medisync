import {
  CheckCircle2,
  Download,
  FileCheck2,
  FileText,
  Loader2,
  Pill,
  QrCode,
  RotateCcw,
  ShieldCheck,
  Stethoscope,
} from "lucide-react";
import type { DocumentoClinicoResponse } from "@/api/generated/types.gen";
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
import { cn } from "@/lib/utils";
import { useDownloadDocumentoPdf } from "../api/use-download-document-pdf";
import { useProntuario } from "../api/use-prontuario";

export interface PosConsultaSummaryProps {
  atendimentoId: string;
  pacienteNome?: string;
  medicoNome?: string;
  crmUf?: string;
  token?: string;
  documentos?: DocumentoClinicoResponse[];
  onNovaConsulta?: () => void;
  className?: string;
}

const TIPO_DOC_LABELS: Record<string, string> = {
  RECEITA_SIMPLES: "Receita Médica Simples",
  RECEITA_CONTROLE_ESPECIAL: "Receita de Controle Especial (Portaria 344/98)",
  ATESTADO_MEDICO: "Atestado Médico / Comparecimento",
  PEDIDO_EXAME: "Pedido de Exames Complementares",
};

export function PosConsultaSummary({
  atendimentoId,
  pacienteNome = "Cidadão",
  medicoNome = "Dr. Eduardo Rocha",
  crmUf = "123456/SP",
  token,
  documentos: docsProps,
  onNovaConsulta,
  className,
}: PosConsultaSummaryProps) {
  const { data: prontuario, isLoading } = useProntuario(atendimentoId, token, {
    enabled: !docsProps || docsProps.length === 0,
  });

  const docs = docsProps && docsProps.length > 0 ? docsProps : (prontuario?.documentos ?? []);
  const { downloadPdf, downloadingId } = useDownloadDocumentoPdf(atendimentoId);

  const handleDownloadPdf = async (documentoId: string, tipoDoc: string) => {
    await downloadPdf(documentoId, token, tipoDoc);
  };

  return (
    <div className={cn("w-full max-w-2xl mx-auto space-y-4", className)}>
      {/* Banner de Consulta Concluída */}
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
                <span className="text-[11px] text-muted-foreground">(CRM {crmUf})</span>
              </p>
            </div>
          </div>

          {/* Selo ITI / ICP-Brasil */}
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

      {/* Lista de Documentos Clínicos Emitidos */}
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
          {isLoading && (!docs || docs.length === 0) ? (
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
              const labelDoc = TIPO_DOC_LABELS[doc.tipo_documento] || doc.tipo_documento;
              const hasItens = doc.itens && doc.itens.length > 0;

              return (
                <div
                  key={doc.id}
                  className="p-3.5 rounded-lg border border-border bg-card space-y-2.5 transition-colors hover:border-primary/40"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <FileText className="size-4 text-primary shrink-0" />
                        <h4 className="font-semibold text-xs text-foreground">{labelDoc}</h4>
                      </div>
                      {doc.sha256_hash && (
                        <p className="text-[11px] text-muted-foreground font-mono">
                          Código / Validação ITI: <strong>{doc.sha256_hash}</strong>
                        </p>
                      )}
                    </div>
                    <Badge
                      variant={doc.assinado_em ? "success" : "secondary"}
                      className="text-[10px] py-0.5 px-2 shrink-0"
                    >
                      {doc.assinado_em ? "Assinado ICP-Brasil" : "Processado"}
                    </Badge>
                  </div>

                  {hasItens && (
                    <div className="p-2 rounded bg-muted/40 border border-border/50 text-[11px] space-y-1">
                      <div className="font-medium text-foreground flex items-center gap-1">
                        <Pill className="size-3 text-primary" />
                        <span>Prescrição:</span>
                      </div>
                      <ul className="list-disc list-inside text-muted-foreground space-y-0.5">
                        {doc.itens?.map((item) => (
                          <li key={item.medicamento}>
                            <strong>{item.medicamento}</strong> — {item.posologia}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  <div className="flex items-center justify-between pt-1">
                    <span className="text-[10px] text-muted-foreground">
                      ID: {doc.id.substring(0, 8)}…
                    </span>
                    <Button
                      type="button"
                      size="sm"
                      onClick={() => handleDownloadPdf(doc.id, doc.tipo_documento)}
                      disabled={downloadingId === doc.id}
                      className="h-8 text-xs px-3 gap-1.5"
                    >
                      {downloadingId === doc.id ? (
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
