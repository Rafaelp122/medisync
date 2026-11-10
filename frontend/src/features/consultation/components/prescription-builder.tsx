import { AlertCircle, FileCheck2, Loader2, Pill } from "lucide-react";
import { useState } from "react";
import type { DocumentoClinicoResponse, ItemPrescricaoRequest } from "@/api/generated/types.gen";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useEmitirDocumento } from "../api/use-emitir-documento";
import { AtestadoForm } from "./prescription/atestado-form";
import { PrescriptionForm } from "./prescription/prescription-form";
import { PrescriptionItemsList } from "./prescription/prescription-items-list";

export interface PrescriptionBuilderProps {
  atendimentoId: string;
  identidadeVerificada: boolean;
  isReadOnly?: boolean;
  onPrescriptionIssued?: (doc: DocumentoClinicoResponse) => void;
  token?: string;
  duracaoSegundos?: number;
}

/**
 * Construtor Composto de Documentos Clínicos Digitais (Receita e Atestado).
 * Decomposto em Compound Components (ADR-011 §2.4) para manter coesão e teto de complexidade.
 * Regras: RF-07, US-10, CFM nº 2.314/2022, Portaria SVS/MS 344/98.
 */
export function PrescriptionBuilder({
  atendimentoId,
  identidadeVerificada,
  isReadOnly = false,
  onPrescriptionIssued,
  token,
  duracaoSegundos,
}: PrescriptionBuilderProps) {
  const [tipoDocumento, setTipoDocumento] = useState<"RECEITA_SIMPLES" | "ATESTADO_MEDICO">(
    "RECEITA_SIMPLES",
  );
  const [justificativaTempoInferior, setJustificativaTempoInferior] = useState("");
  const [itens, setItens] = useState<ItemPrescricaoRequest[]>([]);
  const [erroSanitario, setErroSanitario] = useState<string | null>(null);
  const [sucessoEmissao, setSucessoEmissao] = useState<string | null>(null);

  const { mutate: emitirDocumento, isPending: isEmitting } = useEmitirDocumento(atendimentoId);

  const isAtestado = tipoDocumento === "ATESTADO_MEDICO";
  const duracaoConsulta = duracaoSegundos ?? 0;
  const exigeJustificativa = isAtestado && duracaoConsulta < 180;
  const justificativaValida = !exigeJustificativa || justificativaTempoInferior.trim().length >= 15;

  const handleAddItem = (novoItem: ItemPrescricaoRequest) => {
    setItens((prev) => [...prev, novoItem]);
  };

  const handleRemoveItem = (index: number) => {
    if (isReadOnly) return;
    setItens((prev) => prev.filter((_, i) => i !== index));
  };

  const handleEmitirDocumento = () => {
    if (isReadOnly || !identidadeVerificada) return;
    setErroSanitario(null);
    setSucessoEmissao(null);

    if (!isAtestado && itens.length === 0) return;

    if (isAtestado && exigeJustificativa && !justificativaValida) {
      setErroSanitario(
        "A consulta durou menos de 180s. A justificativa médica circunstanciada deve conter no mínimo 15 caracteres (CFM nº 2.314/2022).",
      );
      return;
    }

    emitirDocumento(
      {
        token,
        tipo_documento: tipoDocumento,
        itens: isAtestado ? (itens.length > 0 ? itens : undefined) : itens,
        justificativa_tempo_inferior:
          isAtestado && exigeJustificativa ? justificativaTempoInferior.trim() : undefined,
      },
      {
        onSuccess: (doc) => {
          setSucessoEmissao(
            isAtestado
              ? `Atestado médico #${doc.id.substring(0, 8)} gerado com sucesso. Prossiga para assinatura ICP-Brasil.`
              : `Receita digital #${doc.id.substring(0, 8)} gerada com sucesso. Prossiga para assinatura ICP-Brasil.`,
          );
          if (!isAtestado) {
            setItens([]);
          }
          setJustificativaTempoInferior("");
          onPrescriptionIssued?.(doc);
        },
        onError: (err) => {
          setErroSanitario(err.detail || "Erro ao emitir documento clínico digital.");
        },
      },
    );
  };

  return (
    <Card className="border-border">
      <CardHeader className="py-3 px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <Pill className="size-4 text-primary" />
            <span>
              {isAtestado
                ? "Atestado Médico & Justificativa Legal"
                : "Prescrição Digital & Salvaguardas Farmacêuticas"}
            </span>
          </CardTitle>
          <span className="text-[11px] text-muted-foreground">
            {isAtestado ? "CFM nº 2.314/2022" : "Portaria SVS/MS 344/98"}
          </span>
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4 space-y-3.5">
        {/* Seletor do Tipo de Documento */}
        {!isReadOnly && (
          <div
            role="tablist"
            aria-label="Tipo de documento clínico"
            className="flex items-center gap-1 p-1 bg-muted rounded-md"
          >
            <button
              type="button"
              role="tab"
              aria-selected={!isAtestado}
              onClick={() => {
                setTipoDocumento("RECEITA_SIMPLES");
                setErroSanitario(null);
              }}
              className={cn(
                "flex-1 py-1 px-2.5 rounded text-xs font-medium transition-[background-color,color,box-shadow]",
                !isAtestado
                  ? "bg-background text-foreground shadow-xs font-semibold"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              Receita Simples
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={isAtestado}
              onClick={() => {
                setTipoDocumento("ATESTADO_MEDICO");
                setErroSanitario(null);
              }}
              className={cn(
                "flex-1 py-1 px-2.5 rounded text-xs font-medium transition-[background-color,color,box-shadow]",
                isAtestado
                  ? "bg-background text-foreground shadow-xs font-semibold"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              Atestado Médico
            </button>
          </div>
        )}

        {/* Alerta de erro sanitário / substância proibida com offending value */}
        {erroSanitario && (
          <Alert variant="destructive" className="py-2 text-xs">
            <AlertCircle className="size-4" />
            <AlertTitle className="text-xs font-semibold">Bloqueio Sanitário Legal</AlertTitle>
            <AlertDescription className="text-xs">{erroSanitario}</AlertDescription>
          </Alert>
        )}

        {/* Mensagem de sucesso de emissão */}
        {sucessoEmissao && (
          <Alert className="py-2 text-xs border-emerald-500/30 bg-emerald-500/10 text-emerald-800 dark:text-emerald-200">
            <FileCheck2 className="size-4 text-emerald-600 mr-2 inline" />
            <AlertDescription className="text-xs inline">{sucessoEmissao}</AlertDescription>
          </Alert>
        )}

        {isAtestado ? (
          <AtestadoForm
            duracaoConsulta={duracaoConsulta}
            exigeJustificativa={exigeJustificativa}
            justificativaTempoInferior={justificativaTempoInferior}
            onJustificativaChange={setJustificativaTempoInferior}
            isReadOnly={isReadOnly}
          />
        ) : (
          <>
            <PrescriptionForm
              atendimentoId={atendimentoId}
              token={token}
              isReadOnly={isReadOnly}
              onAddItem={handleAddItem}
              onError={setErroSanitario}
            />

            <PrescriptionItemsList
              itens={itens}
              onRemoveItem={handleRemoveItem}
              isReadOnly={isReadOnly}
            />
          </>
        )}

        {/* Alerta explicativo se a identidade não estiver confirmada */}
        {!identidadeVerificada && !isReadOnly && (
          <p className="text-[11px] text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/30 p-2 rounded border border-amber-200 dark:border-amber-800">
            A emissão da receita digital está bloqueada até a conclusão da conferência visual de
            identidade oficial (RG/CNH/CNS) sob o CFM nº 2.314/2022.
          </p>
        )}

        {/* Botão de Emissão */}
        {!isReadOnly && (
          <Button
            type="button"
            size="sm"
            onClick={handleEmitirDocumento}
            disabled={
              !identidadeVerificada ||
              isEmitting ||
              (!isAtestado && itens.length === 0) ||
              (isAtestado && exigeJustificativa && !justificativaValida)
            }
            className="w-full text-xs font-medium h-8 gap-1.5"
          >
            {isEmitting ? (
              <>
                <Loader2 className="size-3.5 animate-spin" />
                <span>{isAtestado ? "Emitindo Atestado…" : "Emitindo Prescrição…"}</span>
              </>
            ) : (
              <>
                <FileCheck2 className="size-3.5" />
                <span>{isAtestado ? "Emitir Atestado Médico" : "Emitir Prescrição Digital"}</span>
              </>
            )}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
