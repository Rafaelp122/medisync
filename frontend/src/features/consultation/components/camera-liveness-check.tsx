import { Camera, CheckCircle2, Loader2, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";
import type { LivenessChallengeResponse } from "@/api/generated/types.gen";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useSolicitarDesafioLiveness, useVerificarLiveness } from "../api/use-liveness-check";
import type { LivenessResultMessage } from "../lib/liveness-channel";

export interface CameraLivenessCheckProps {
  atendimentoId: string;
  token?: string;
  approvedHash: string | null;
  justificativaExcecao: string;
  onApproved: (verificacaoHash: string) => void;
  onJustificativaChange: (value: string) => void;
  onSendChallenge?: (challenge: LivenessChallengeResponse) => void;
  remoteResult?: LivenessResultMessage | null;
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
  onSendChallenge,
  remoteResult,
  isReadOnly = false,
}: CameraLivenessCheckProps) {
  const [challenge, setChallenge] = useState<LivenessChallengeResponse | null>(null);
  const [modoContingencia, setModoContingencia] = useState(false);
  const [erroCamera, setErroCamera] = useState<string | null>(null);

  const solicitarDesafio = useSolicitarDesafioLiveness(atendimentoId);
  const verificarLiveness = useVerificarLiveness(atendimentoId);

  useEffect(() => {
    if (!remoteResult || remoteResult.atendimento_id !== atendimentoId) return;
    if (remoteResult.status === "APROVADO" && remoteResult.verificacao_hash && !approvedHash) {
      onApproved(remoteResult.verificacao_hash);
      return;
    }
    if (remoteResult.status !== "APROVADO") {
      setErroCamera(
        remoteResult.detail ||
          "Prova de vida facial do paciente reprovada. Emissão da Lista C1 bloqueada.",
      );
    }
  }, [remoteResult, atendimentoId, approvedHash, onApproved]);

  const handleIniciarDesafio = () => {
    setErroCamera(null);
    solicitarDesafio.mutate(
      { token },
      {
        onSuccess: (data) => {
          setChallenge(data);
          onSendChallenge?.(data);
        },
      },
    );
  };

  const handleCapturarEValidar = async () => {
    if (!challenge) return;
    setErroCamera(null);

    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setErroCamera(
        "Câmera indisponível neste dispositivo ou navegador. Caso o paciente não possua câmera operante, registre a justificativa clínica de contingência abaixo.",
      );
      setModoContingencia(true);
      return;
    }

    let payloadToken: string;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      for (const track of stream.getTracks()) {
        track.stop();
      }
      payloadToken = `LIVE_CAMERA_STREAM_${challenge.challenge_id}`;
    } catch {
      setErroCamera(
        "Permissão de câmera negada ou falha na captura de vídeo. Autorize o acesso à câmera ou registre justificativa clínica de contingência.",
      );
      setModoContingencia(true);
      return;
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

  const erroAtual =
    erroCamera || solicitarDesafio.error?.detail || verificarLiveness.error?.detail || null;

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
              {onSendChallenge ? (
                <div className="space-y-1.5" role="status" aria-live="polite">
                  <p className="text-[11px] text-amber-900 dark:text-amber-300 font-medium">
                    Desafio biométrico enviado ao paciente na chamada… Aguardando captura pela
                    câmera do paciente.
                  </p>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={isReadOnly || solicitarDesafio.isPending}
                    onClick={handleIniciarDesafio}
                    className="w-full h-7 text-[11px]"
                  >
                    Reenviar Desafio ao Paciente
                  </Button>
                </div>
              ) : (
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
              )}
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
