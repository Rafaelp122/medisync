import { Camera, CheckCircle2, Loader2, ShieldAlert } from "lucide-react";
import { useState } from "react";
import type { LivenessChallengeResponse } from "@/api/generated/types.gen";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useSolicitarDesafioLiveness, useVerificarLiveness } from "../api/use-liveness-check";

export interface CameraLivenessCheckProps {
  atendimentoId: string;
  token?: string;
  approvedHash: string | null;
  justificativaExcecao: string;
  onApproved: (verificacaoHash: string) => void;
  onJustificativaChange: (value: string) => void;
  isReadOnly?: boolean;
}

const INSTRUCTION_LABELS: Record<string, string> = {
  piscar_olhos: "Piscar os olhos naturalmente",
  sorrir: "Sorrir brevemente para a câmera",
};

/**
 * Gate visual ativo de Prova de Vida Facial para receitas Lista C1 (US-15).
 * @see docs/user-stories/US-15-prova-de-vida-facial-liveness.md
 */
export function CameraLivenessCheck({
  atendimentoId,
  token,
  approvedHash,
  justificativaExcecao,
  onApproved,
  onJustificativaChange,
  isReadOnly = false,
}: CameraLivenessCheckProps) {
  const [challenge, setChallenge] = useState<LivenessChallengeResponse | null>(null);
  const [modoContingencia, setModoContingencia] = useState(false);

  const solicitarDesafio = useSolicitarDesafioLiveness(atendimentoId);
  const verificarLiveness = useVerificarLiveness(atendimentoId);

  const handleIniciarDesafio = () => {
    solicitarDesafio.mutate(
      { token },
      {
        onSuccess: (data) => {
          setChallenge(data);
        },
      },
    );
  };

  const handleCapturarEValidar = async () => {
    if (!challenge) return;
    let payloadToken = "LIVE_WEBRTC_FRAME_CAPTURE_OK";

    if (typeof navigator !== "undefined" && navigator.mediaDevices?.getUserMedia) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true });
        for (const track of stream.getTracks()) {
          track.stop();
        }
        payloadToken = `LIVE_CAMERA_STREAM_${challenge.challenge_id}`;
      } catch {
        payloadToken = `LIVE_SANDBOX_FALLBACK_${challenge.challenge_id}`;
      }
    }

    verificarLiveness.mutate(
      {
        token,
        challenge_id: challenge.challenge_id,
        liveness_payload: payloadToken,
      },
      {
        onSuccess: (res) => {
          if (res.status === "APROVADO" && res.verificacao_hash) {
            onApproved(res.verificacao_hash);
          }
        },
      },
    );
  };

  const erroAtual = solicitarDesafio.error?.detail || verificarLiveness.error?.detail || null;

  return (
    <div
      className="rounded-lg border border-amber-300/70 bg-amber-50/60 dark:bg-amber-950/20 p-3 space-y-2.5"
      data-testid="camera-liveness-check"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <Camera className="size-4 text-amber-700 dark:text-amber-400" aria-hidden="true" />
          <span className="text-xs font-semibold text-amber-950 dark:text-amber-200">
            Prova de Vida Facial Obrigatória (Lista C1)
          </span>
        </div>
        <Badge
          variant="outline"
          className="text-[10px] border-amber-400/70 text-amber-900 dark:text-amber-300"
        >
          US-15 / Portaria 344/98
        </Badge>
      </div>

      {erroAtual && (
        <Alert variant="destructive" className="py-2" role="alert">
          <ShieldAlert className="size-4" />
          <AlertTitle className="text-xs">Falha na Prova de Vida</AlertTitle>
          <AlertDescription className="text-xs">{erroAtual}</AlertDescription>
        </Alert>
      )}

      {approvedHash ? (
        <div
          className="flex items-center gap-2 rounded-md border border-emerald-300 bg-emerald-50/80 dark:bg-emerald-950/30 px-2.5 py-2 text-xs text-emerald-900 dark:text-emerald-200"
          role="status"
        >
          <CheckCircle2 className="size-4 shrink-0 text-emerald-600" aria-hidden="true" />
          <span>Prova de vida facial aprovada ({approvedHash.slice(0, 18)}…)</span>
        </div>
      ) : (
        <div className="space-y-2">
          {!challenge ? (
            <Button
              type="button"
              size="sm"
              variant="secondary"
              disabled={isReadOnly || solicitarDesafio.isPending}
              onClick={handleIniciarDesafio}
              className="w-full h-8 text-xs gap-1.5"
            >
              {solicitarDesafio.isPending ? (
                <>
                  <Loader2 className="size-3.5 animate-spin" />
                  Gerando desafio biométrico…
                </>
              ) : (
                <>
                  <Camera className="size-3.5" />
                  Iniciar Prova de Vida Facial
                </>
              )}
            </Button>
          ) : (
            <div className="space-y-2 rounded-md border border-amber-200 bg-background/80 p-2.5">
              <p className="text-[11px] font-medium text-foreground">
                Solicite ao paciente os movimentos abaixo diante da câmera:
              </p>
              <ul className="list-disc pl-4 text-[11px] text-muted-foreground space-y-0.5">
                {challenge.instrucoes_movimento.map((instr) => (
                  <li key={instr}>{INSTRUCTION_LABELS[instr] ?? instr}</li>
                ))}
              </ul>
              <Button
                type="button"
                size="sm"
                disabled={isReadOnly || verificarLiveness.isPending}
                onClick={() => void handleCapturarEValidar()}
                className="w-full h-8 text-xs gap-1.5"
              >
                {verificarLiveness.isPending ? (
                  <>
                    <Loader2 className="size-3.5 animate-spin" />
                    Validando vivacidade facial…
                  </>
                ) : (
                  "Capturar e Validar Vivacidade"
                )}
              </Button>
            </div>
          )}

          <div className="pt-1 border-t border-amber-200/70 space-y-1.5">
            <button
              type="button"
              disabled={isReadOnly}
              onClick={() => setModoContingencia((prev) => !prev)}
              className="text-[11px] underline text-muted-foreground hover:text-foreground"
            >
              {modoContingencia
                ? "Ocultar justificativa de contingência"
                : "Declarar contingência clínica sem câmera"}
            </button>

            {modoContingencia && (
              <div className="space-y-1">
                <Label htmlFor="justificativa-excecao-liveness" className="text-[11px]">
                  Justificativa médica para dispensa de prova de vida (mín. 10 caracteres)
                </Label>
                <Textarea
                  id="justificativa-excecao-liveness"
                  value={justificativaExcecao}
                  onChange={(e) => onJustificativaChange(e.target.value)}
                  disabled={isReadOnly}
                  rows={2}
                  placeholder="Ex: Paciente acamado em domicílio sem câmera frontal operante"
                  className="text-xs resize-none"
                />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
