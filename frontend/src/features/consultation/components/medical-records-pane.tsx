import { Clock, Download, FileCheck, History, Loader2, Shield, User } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useDownloadDocumentoPdf } from "../api/use-download-document-pdf";
import { useProntuario } from "../api/use-prontuario";

export interface MedicalRecordsPaneProps {
  atendimentoId: string;
  pacienteNome?: string;
  pacienteCpf?: string;
  prioridadeClinica?: number;
  queixaPrincipal?: string;
  token?: string;
}

/**
 * Painel central de visualização do prontuário, triagem e documentos emitidos (PEP).
 * Apresenta dados protegidos e mascarados sob LGPD e histórico de receitas assinadas.
 * Regras: RF-07, US-09, US-10.
 */
export function MedicalRecordsPane({
  atendimentoId,
  pacienteNome = "Juliana Silva",
  pacienteCpf = "123.***.***-00",
  prioridadeClinica = 3,
  queixaPrincipal = "Paciente acolhido com queixa de febre e dor de garganta.",
  token,
}: MedicalRecordsPaneProps) {
  const { data: prontuario, isLoading } = useProntuario(atendimentoId, token);
  const { downloadPdf, downloadingId } = useDownloadDocumentoPdf(atendimentoId);

  const PRIORIDADE_CLINICA_MAP: Record<
    number,
    { label: string; variant: "nivel1" | "nivel2" | "nivel3" | "nivel4" | "nivel5" }
  > = {
    1: { label: "Vermelho: Emergência Imediata (SAMU 192)", variant: "nivel1" },
    2: { label: "Laranja: Muito Urgente", variant: "nivel2" },
    3: { label: "Amarelo: Urgente", variant: "nivel3" },
    4: { label: "Verde: Pouco Urgente", variant: "nivel4" },
    5: { label: "Azul: Não Urgente", variant: "nivel5" },
  };

  const getPrioridadeBadge = (prioridade: number) => {
    const config = PRIORIDADE_CLINICA_MAP[prioridade] ?? PRIORIDADE_CLINICA_MAP[5];
    return <Badge variant={config.variant}>{config.label}</Badge>;
  };

  return (
    <div className="space-y-3.5 h-full flex flex-col">
      {/* Card de Identificação e Triagem do Paciente */}
      <Card className="border-border">
        <CardHeader className="py-3 px-4">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <User className="size-4 text-primary" />
              <span>Identificação do Paciente</span>
            </CardTitle>
            {getPrioridadeBadge(prioridadeClinica)}
          </div>
        </CardHeader>
        <CardContent className="px-4 pb-4 space-y-2 text-xs">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <span className="text-muted-foreground">Nome Completo:</span>
              <p className="font-semibold text-foreground">{pacienteNome}</p>
            </div>
            <div>
              <span className="text-muted-foreground">CPF (Protegido LGPD):</span>
              <p className="font-semibold text-foreground">{pacienteCpf}</p>
            </div>
          </div>

          <div className="pt-1.5 border-t border-border">
            <span className="text-muted-foreground font-medium flex items-center gap-1 mb-1">
              <Clock className="size-3 text-muted-foreground" />
              <span>Queixa Inicial Registrada no Acolhimento:</span>
            </span>
            <p className="p-2 rounded bg-muted/40 text-foreground font-normal italic">
              "{queixaPrincipal}"
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Card de Documentos Emitidos e Assinados no Atendimento */}
      <Card className="border-border flex-1 flex flex-col">
        <CardHeader className="py-3 px-4">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <History className="size-4 text-primary" />
              <span>Documentos Emitidos ({prontuario?.documentos?.length ?? 0})</span>
            </CardTitle>
            <span className="text-[11px] text-muted-foreground flex items-center gap-1">
              <Shield className="size-3 text-acr-green" />
              PAdES ICP-Brasil
            </span>
          </div>
        </CardHeader>
        <CardContent className="px-4 pb-4 flex-1 text-xs">
          {isLoading ? (
            <p className="text-muted-foreground italic py-3 text-center">Carregando prontuário…</p>
          ) : !prontuario?.documentos || prontuario.documentos.length === 0 ? (
            <p className="text-muted-foreground italic py-3 text-center">
              Nenhum documento clínico emitido neste atendimento.
            </p>
          ) : (
            <div className="space-y-2">
              {prontuario.documentos.map((doc) => (
                <div
                  key={doc.id}
                  className="p-2.5 rounded-md border border-border bg-card space-y-1.5 hover:bg-muted/20"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-foreground flex items-center gap-1.5">
                      <FileCheck className="size-3.5 text-primary" />
                      {doc.tipo_documento.replace("_", " ")}
                    </span>
                    <Badge
                      variant={doc.assinado_em ? "success" : "secondary"}
                      className="text-[10px] py-0 px-1.5"
                    >
                      {doc.assinado_em ? "Assinado ICP-Brasil" : "Rascunho Emitido"}
                    </Badge>
                  </div>

                  <p className="text-[11px] text-muted-foreground">
                    Itens: {doc.itens?.map((i) => i.medicamento).join(", ") || "Sem itens"}
                  </p>

                  <div className="flex items-center justify-between pt-1">
                    <span className="text-[10px] text-muted-foreground font-mono">
                      ID: {doc.id.substring(0, 8)}…
                    </span>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={downloadingId === doc.id}
                      onClick={() => downloadPdf(doc.id, token)}
                      className="h-6 text-[10px] px-2 gap-1"
                    >
                      {downloadingId === doc.id ? (
                        <Loader2 className="size-3 animate-spin text-primary" />
                      ) : (
                        <Download className="size-3" />
                      )}
                      <span>{downloadingId === doc.id ? "Baixando…" : "Baixar PDF"}</span>
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
