import { AlertCircle, FileCheck2, Loader2, Pill } from "lucide-react";
import { useEffect, useState } from "react";
import type {
  DocumentoClinicoResponse,
  ItemPrescricaoRequest,
  LivenessChallengeResponse,
} from "@/api/generated/types.gen";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useEmitirDocumento } from "../api/use-emitir-documento";
import { useOptionalConsultationEncounter } from "../context/consultation-encounter-provider";
import type { LivenessResultMessage } from "../lib/liveness-channel";
import { CameraLivenessCheck } from "./camera-liveness-check";
import { AtestadoForm } from "./prescription/atestado-form";
import { PrescriptionDocumentTabs } from "./prescription/prescription-document-tabs";
import { PrescriptionForm } from "./prescription/prescription-form";
import { PrescriptionItemsList } from "./prescription/prescription-items-list";

export interface PrescriptionBuilderProps {
  atendimentoId: string;
  identidadeVerificada?: boolean;
  accessMode?: "editable" | "readonly";
  onPrescriptionIssued?: (doc: DocumentoClinicoResponse) => void;
  onSendLivenessChallenge?: (challenge: LivenessChallengeResponse) => void;
  remoteLivenessResult?: LivenessResultMessage | null;
  token?: string;
  duracaoSegundos?: number;
  atendimentoIniciadoEm?: string | null;
}

function atingiuTempoMinimo(
  atendimentoIniciadoEm?: string | null,
  duracaoSegundos?: number,
): boolean {
  if (atendimentoIniciadoEm) {
    const inicioMs = new Date(atendimentoIniciadoEm).getTime();
    if (!Number.isNaN(inicioMs)) {
      return Math.floor((Date.now() - inicioMs) / 1000) >= 180;
    }
  }
  return (duracaoSegundos ?? 0) >= 180;
}

/**
 * Construtor Composto de Documentos Clínicos Digitais (Receita e Atestado).
 * Delega tick temporal de 180s ao componente folha `AtestadoForm`.
 * Regras: RF-07, US-10, CFM nº 2.314/2022, Portaria SVS/MS 344/98.
 */
export function PrescriptionBuilder({
  atendimentoId,
  identidadeVerificada,
  accessMode,
  onPrescriptionIssued,
  onSendLivenessChallenge,
  remoteLivenessResult,
  token,
  duracaoSegundos,
  atendimentoIniciadoEm,
}: PrescriptionBuilderProps) {
  const encounter = useOptionalConsultationEncounter();
  const effectiveMode = accessMode ?? (encounter?.isFinalizado ? "readonly" : "editable");
  const isLocked = effectiveMode === "readonly";
  const resolvedIdentidadeVerificada =
    identidadeVerificada ?? encounter?.identidadeVerificada ?? false;
  const resolvedToken = token ?? encounter?.atendimento.token;
  const resolvedStartedAt = atendimentoIniciadoEm ?? encounter?.atendimento.chamadaIniciadaEm;
  const resolvedLivenessResult = remoteLivenessResult ?? encounter?.livenessResult ?? null;

  const [tipoDocumento, setTipoDocumento] = useState<"RECEITA_SIMPLES" | "ATESTADO_MEDICO">(
    "RECEITA_SIMPLES",
  );
  const [tempoMinimoAtingido, setTempoMinimoAtingido] = useState<boolean>(() =>
    atingiuTempoMinimo(resolvedStartedAt, duracaoSegundos),
  );
  const [justificativaTempoInferior, setJustificativaTempoInferior] = useState("");
  const [itens, setItens] = useState<ItemPrescricaoRequest[]>([]);
  const [erroSanitario, setErroSanitario] = useState<string | null>(null);
  const [sucessoEmissao, setSucessoEmissao] = useState<string | null>(null);
  const [livenessHash, setLivenessHash] = useState<string | null>(null);
  const [justificativaExcecaoLiveness, setJustificativaExcecaoLiveness] = useState("");

  useEffect(() => {
    setTempoMinimoAtingido(atingiuTempoMinimo(resolvedStartedAt, duracaoSegundos));
  }, [resolvedStartedAt, duracaoSegundos]);

  const { mutate: emitirDocumento, isPending: isEmitting } = useEmitirDocumento(atendimentoId);

  const isAtestado = tipoDocumento === "ATESTADO_MEDICO";
  const exigeJustificativa = isAtestado && !tempoMinimoAtingido;
  const justificativaValida = !exigeJustificativa || justificativaTempoInferior.trim().length >= 15;
  const exigeProvaDeVida = !isAtestado && itens.some((item) => Boolean(item.controle_especial));
  const livenessSatisfeita =
    !exigeProvaDeVida || Boolean(livenessHash) || justificativaExcecaoLiveness.trim().length >= 10;
  const effectiveTipoDocumento = exigeProvaDeVida ? "RECEITA_CONTROLE_ESPECIAL_C1" : tipoDocumento;

  const handleEmitirDocumento = () => {
    if (isLocked || !resolvedIdentidadeVerificada) return;
    setErroSanitario(null);
    setSucessoEmissao(null);

    if (!isAtestado && itens.length === 0) return;

    const precisaJustificativaAgora =
      isAtestado && !atingiuTempoMinimo(resolvedStartedAt, duracaoSegundos);

    if (precisaJustificativaAgora && justificativaTempoInferior.trim().length < 15) {
      setErroSanitario(
        "A consulta durou menos de 180s. A justificativa médica circunstanciada deve conter no mínimo 15 caracteres (CFM nº 2.314/2022).",
      );
      return;
    }

    if (exigeProvaDeVida && !livenessSatisfeita) {
      setErroSanitario(
        "Prova de vida facial aprovada (ou justificativa clínica de contingência) é obrigatória para receitas da Lista C1.",
      );
      return;
    }

    emitirDocumento(
      {
        token: resolvedToken,
        tipo_documento: effectiveTipoDocumento,
        itens: isAtestado ? (itens.length > 0 ? itens : undefined) : itens,
        justificativa_tempo_inferior: precisaJustificativaAgora
          ? justificativaTempoInferior.trim()
          : undefined,
        liveness_verificacao_hash: exigeProvaDeVida ? livenessHash : undefined,
        justificativa_excecao_liveness:
          exigeProvaDeVida && !livenessHash ? justificativaExcecaoLiveness.trim() : undefined,
      },
      {
        onSuccess: (doc) => {
          setSucessoEmissao(
            isAtestado
              ? `Atestado médico #${doc.id.substring(0, 8)} gerado com sucesso.`
              : `Receita digital #${doc.id.substring(0, 8)} gerada com sucesso.`,
          );
          encounter?.setDocumentoPendente(doc);
          onPrescriptionIssued?.(doc);
        },
        onError: (err) => {
          setErroSanitario(err.detail || "Falha ao emitir documento clínico digital.");
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
        {!isLocked && (
          <PrescriptionDocumentTabs
            selected={tipoDocumento}
            onSelect={(tipo) => {
              setTipoDocumento(tipo);
              setErroSanitario(null);
            }}
          />
        )}

        {erroSanitario && (
          <Alert variant="destructive" className="py-2 text-xs">
            <AlertCircle className="size-4" />
            <AlertTitle className="text-xs font-semibold">Bloqueio Sanitário Legal</AlertTitle>
            <AlertDescription className="text-xs">{erroSanitario}</AlertDescription>
          </Alert>
        )}

        {sucessoEmissao && (
          <Alert className="py-2 text-xs border-emerald-500/30 bg-emerald-500/10 text-emerald-800 dark:text-emerald-200">
            <FileCheck2 className="size-4 text-emerald-600 mr-2 inline" />
            <AlertDescription className="text-xs inline">{sucessoEmissao}</AlertDescription>
          </Alert>
        )}

        {isAtestado ? (
          <AtestadoForm
            duracaoConsulta={duracaoSegundos}
            atendimentoIniciadoEm={resolvedStartedAt}
            justificativaTempoInferior={justificativaTempoInferior}
            onJustificativaChange={setJustificativaTempoInferior}
            onTempoMinimoAtingido={() => setTempoMinimoAtingido(true)}
            accessMode={effectiveMode}
          />
        ) : (
          <>
            <PrescriptionForm
              atendimentoId={atendimentoId}
              token={resolvedToken}
              accessMode={effectiveMode}
              onAddItem={(novoItem) => setItens((prev) => [...prev, novoItem])}
              onError={setErroSanitario}
            />

            <PrescriptionItemsList
              itens={itens}
              onRemoveItem={(index) => {
                if (!isLocked) {
                  setItens((prev) => prev.filter((_, i) => i !== index));
                }
              }}
              accessMode={effectiveMode}
            />

            {exigeProvaDeVida && !isLocked && (
              <CameraLivenessCheck
                atendimentoId={atendimentoId}
                token={resolvedToken}
                approvedHash={livenessHash}
                justificativaExcecao={justificativaExcecaoLiveness}
                onApproved={setLivenessHash}
                onJustificativaChange={setJustificativaExcecaoLiveness}
                onSendChallenge={onSendLivenessChallenge}
                remoteResult={resolvedLivenessResult}
                accessMode={effectiveMode}
              />
            )}
          </>
        )}

        {!resolvedIdentidadeVerificada && !isLocked && (
          <p className="text-[11px] text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/30 p-2 rounded border border-amber-200 dark:border-amber-800">
            A emissão da receita digital está bloqueada até a conclusão da conferência visual de
            identidade oficial (RG/CNH/CNS) sob o CFM nº 2.314/2022.
          </p>
        )}

        {!isLocked && (
          <Button
            type="button"
            size="sm"
            onClick={handleEmitirDocumento}
            disabled={
              !resolvedIdentidadeVerificada ||
              isEmitting ||
              (!isAtestado && itens.length === 0) ||
              (isAtestado && exigeJustificativa && !justificativaValida) ||
              (exigeProvaDeVida && !livenessSatisfeita)
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
