import { Camera, CheckCircle2, Loader2, ShieldAlert, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import type { LivenessChallengeResponse } from "@/api/generated/types.gen";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useVerificarLiveness } from "../api/use-liveness-check";
import { captureVideoFrameAsBase64, type LivenessResultMessage } from "../lib/liveness-channel";

export interface PatientLivenessModalProps {
  atendimentoId: string;
  token: string;
  challenge: LivenessChallengeResponse;
  onResult: (result: LivenessResultMessage) => void;
  onClose: () => void;
}

const PATIENT_INSTRUCTION_LABELS: Record<string, string> = {
  piscar_olhos: "Pisque os olhos lentamente para a câmera",
  sorrir: "Sorria brevemente olhando para a tela",
};

/**
 * Modal guiada de Prova de Vida Facial na tela do paciente durante teleconsulta (US-15).
 * Captura frames reais pela câmera do paciente, exibe guia oval semântico com instruções em
 * `aria-live="assertive"` e envia para validação do endpoint exclusivo `PACIENTE`.
 * @see docs/user-stories/US-15-prova-de-vida-facial-liveness.md
 */
export function PatientLivenessModal({
  atendimentoId,
  token,
  challenge,
  onResult,
  onClose,
}: PatientLivenessModalProps) {
  const titleId = useId();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [cameraReady, setCameraReady] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [approvedScore, setApprovedScore] = useState<number | null>(null);

  const verificarLiveness = useVerificarLiveness(atendimentoId);

  useEffect(() => {
    let cancelled = false;

    async function startCamera() {
      if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
        setCameraError(
          "Câmera frontal indisponível neste dispositivo. Informe ao médico na chamada.",
        );
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "user" },
        });
        if (cancelled) {
          for (const track of stream.getTracks()) track.stop();
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
        setCameraReady(true);
      } catch {
        if (!cancelled) {
          setCameraError(
            "Permissão de câmera negada. Autorize o acesso à câmera ou avise o médico.",
          );
        }
      }
    }

    void startCamera();

    return () => {
      cancelled = true;
      if (streamRef.current) {
        for (const track of streamRef.current.getTracks()) {
          track.stop();
        }
        streamRef.current = null;
      }
    };
  }, []);

  const instructionText = challenge.instrucoes_movimento
    .map((step) => PATIENT_INSTRUCTION_LABELS[step] ?? step)
    .join(" e depois ");

  const ovalBorderClass = verificarLiveness.isPending
    ? "border-sky-400 shadow-[0_0_0_2px_rgba(56,189,248,0.45)]"
    : cameraReady
      ? "border-emerald-400 shadow-[0_0_0_2px_rgba(52,211,153,0.45)]"
      : "border-amber-400 shadow-[0_0_0_2px_rgba(251,191,36,0.45)]";

  const handleCapturar = () => {
    setCameraError(null);
    const frameBase64 = captureVideoFrameAsBase64(videoRef.current);

    verificarLiveness.mutate(
      {
        token,
        challenge_id: challenge.challenge_id,
        liveness_payload: frameBase64,
      },
      {
        onSuccess: (res) => {
          setApprovedScore(res.liveness_score);
          onResult({
            type: "LIVENESS_RESULT",
            atendimento_id: atendimentoId,
            status: res.status === "APROVADO" ? "APROVADO" : "REPROVADO",
            verificacao_hash: res.verificacao_hash,
            liveness_score: res.liveness_score,
          });
        },
        onError: (err) => {
          const status =
            err.code === "LIVENESS_CHALLENGE_INVALIDO" ? "DESAFIO_INVALIDO" : "REPROVADO";
          onResult({
            type: "LIVENESS_RESULT",
            atendimento_id: atendimentoId,
            status,
            detail: err.detail,
          });
        },
      },
    );
  };

  const activeError = cameraError || verificarLiveness.error?.detail || null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      data-testid="patient-liveness-modal"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/75 p-4 backdrop-blur-xs"
    >
      <Card className="w-full max-w-md border-slate-700 bg-slate-900 text-slate-100 shadow-2xl">
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
          <CardTitle id={titleId} className="text-base font-semibold flex items-center gap-2">
            <Camera className="size-4 text-sky-400" />
            Confirmação Facial para Receita Controlada
          </CardTitle>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={onClose}
            aria-label="Fechar verificação facial"
            className="size-7 text-slate-400 hover:text-slate-100"
          >
            <X className="size-4" />
          </Button>
        </CardHeader>

        <CardContent className="space-y-4">
          <div className="relative mx-auto h-56 w-44 overflow-hidden rounded-full bg-slate-950 flex items-center justify-center">
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              className="h-full w-full object-cover"
            />
            <div
              aria-hidden="true"
              className={cn(
                "pointer-events-none absolute inset-0 rounded-full border-4 transition-colors",
                ovalBorderClass,
              )}
            />
          </div>

          <div
            aria-live="assertive"
            className="rounded-md border border-slate-700 bg-slate-800/80 p-3 text-center text-xs text-slate-100"
          >
            <p className="font-semibold text-sky-300">Siga as instruções na câmera:</p>
            <p className="mt-1">{instructionText}</p>
            <p className="mt-1 text-[11px] text-slate-400">
              {verificarLiveness.isPending
                ? "Capturando e validando prova de vida…"
                : cameraReady
                  ? "Rosto enquadrado. Posicione no guia oval e confirme."
                  : "Aproximando câmera… aguarde a liberação de vídeo."}
            </p>
          </div>

          {activeError && (
            <Alert variant="destructive" aria-live="assertive" className="text-xs">
              <ShieldAlert className="size-4" />
              <AlertTitle className="text-xs font-semibold">Falha na Prova de Vida</AlertTitle>
              <AlertDescription className="text-xs">{activeError}</AlertDescription>
            </Alert>
          )}

          {approvedScore !== null ? (
            <div
              role="status"
              className="flex items-center justify-center gap-2 rounded-md border border-emerald-700 bg-emerald-950/60 p-3 text-xs font-medium text-emerald-300"
            >
              <CheckCircle2 className="size-4 shrink-0" />
              <span>
                Prova de vida aprovada ({Math.round(approvedScore * 100)}% confiança). Receita
                liberada ao médico.
              </span>
            </div>
          ) : (
            <Button
              type="button"
              disabled={verificarLiveness.isPending || Boolean(cameraError)}
              onClick={handleCapturar}
              className="w-full gap-2"
            >
              {verificarLiveness.isPending ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  Validando Vivacidade…
                </>
              ) : (
                "Confirmar e Enviar Prova de Vida"
              )}
            </Button>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
