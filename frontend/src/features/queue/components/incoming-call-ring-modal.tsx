import { useCallback, useEffect, useRef, useState } from "react";
import { extractProblemDetail } from "@/api/errors";
import type { LiveKitTokenResponse } from "@/api/generated/types.gen";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { settings } from "@/config/settings";
import { useAtenderChamada } from "../api/use-atender-chamada";
import { iniciarToqueChamadaMedica } from "../lib/audio-chime";
import { RingCountdown } from "./ring-countdown";

export interface IncomingCallRingModalProps {
  open: boolean;
  atendimentoId: string;
  pacienteId: string;
  nomePaciente?: string | null;
  token?: string;
  ttlSegundos?: number;
  chamadaIniciadaEm?: string | null;
  onAtendido: (data: LiveKitTokenResponse) => void;
  onNoShow: () => void;
  onRecusar?: () => void | Promise<void>;
  isRecusando?: boolean;
}

/**
 * Modal Fullscreen de Convocação Médica com Tolerância de 45s (RF-03, RN02).
 * Delega o tick de 1s para `<RingCountdown />` e integra recusa com o backend.
 * @see docs/user-stories/US-08-atendimento-chamada-no-show.md
 */
export function IncomingCallRingModal({
  open,
  atendimentoId,
  pacienteId,
  nomePaciente,
  token,
  ttlSegundos = settings.clinical.callRingTtlSeconds,
  chamadaIniciadaEm,
  onAtendido,
  onNoShow,
  onRecusar,
  isRecusando = false,
}: IncomingCallRingModalProps) {
  const [erroAtendimento, setErroAtendimento] = useState<string | null>(null);
  const [expirado, setExpirado] = useState(false);
  const pararToqueRef = useRef<(() => void) | null>(null);

  const silenciarChime = useCallback(() => {
    if (pararToqueRef.current) {
      pararToqueRef.current();
      pararToqueRef.current = null;
    }
  }, []);

  const { mutate: atenderChamada, isPending } = useAtenderChamada({
    onSuccess: (data) => {
      silenciarChime();
      onAtendido(data);
    },
    onError: (err) => {
      if (err.status === 409 || err.code === "ATENDIMENTO_EXPIRADO_NO_SHOW") {
        setErroAtendimento(
          "O prazo de 45 segundos para resposta expirou. O atendimento foi encerrado por ausência.",
        );
        silenciarChime();
        onNoShow();
      } else {
        setErroAtendimento(err.detail || err.message || "Erro ao conectar à chamada médica.");
      }
    },
  });

  useEffect(() => {
    if (!open) {
      setExpirado(false);
      silenciarChime();
      return;
    }

    pararToqueRef.current = iniciarToqueChamadaMedica();
    return () => {
      silenciarChime();
    };
  }, [open, silenciarChime]);

  const handleExpire = useCallback(() => {
    setExpirado(true);
    silenciarChime();
    onNoShow();
  }, [onNoShow, silenciarChime]);

  const handleEntrarConsulta = () => {
    setErroAtendimento(null);
    atenderChamada({
      atendimentoId,
      pacienteId,
      nomePaciente,
      token,
    });
  };

  const handleRecusar = async () => {
    setErroAtendimento(null);
    silenciarChime();
    if (!onRecusar) {
      onNoShow();
      return;
    }

    try {
      await onRecusar();
    } catch (err) {
      const status =
        typeof err === "object" && err !== null && "status" in err
          ? (err as { status?: unknown }).status
          : undefined;
      const code =
        typeof err === "object" && err !== null && "code" in err
          ? (err as { code?: unknown }).code
          : undefined;
      if (status === 409 || code === "ATENDIMENTO_EXPIRADO_NO_SHOW") {
        setErroAtendimento(
          "O prazo de 45 segundos para resposta expirou. O atendimento foi encerrado por ausência.",
        );
        onNoShow();
        return;
      }
      setErroAtendimento(
        extractProblemDetail(err, "Não foi possível recusar a chamada médica. Tente novamente."),
      );
    }
  };

  return (
    <Dialog open={open}>
      <DialogContent
        role="alertdialog"
        onPointerDownOutside={(e) => e.preventDefault()}
        onEscapeKeyDown={(e) => {
          e.preventDefault();
          silenciarChime();
          onNoShow();
        }}
        className="sm:max-w-md text-center p-6 sm:p-8 space-y-6 border-primary/30 shadow-2xl"
      >
        <DialogHeader className="space-y-3">
          <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-full bg-primary/10 text-primary animate-pulse motion-reduce:animate-none">
            <span className="text-4xl" aria-hidden="true">
              🩺
            </span>
          </div>

          <DialogTitle className="text-2xl sm:text-3xl font-extrabold text-foreground tracking-tight text-balance">
            O Médico está Chamando!
          </DialogTitle>

          <DialogDescription className="text-sm text-muted-foreground text-pretty">
            O Dr. Plantonista alocou seu atendimento e aguarda sua confirmação de presença para
            iniciar a teleconsulta com vídeo.
          </DialogDescription>
        </DialogHeader>

        <RingCountdown
          open={open}
          ttlSegundos={ttlSegundos}
          chamadaIniciadaEm={chamadaIniciadaEm}
          onExpire={handleExpire}
        />

        {erroAtendimento && (
          <div
            role="alert"
            className="p-3 bg-destructive/10 text-destructive rounded-lg text-xs font-medium border border-destructive/20 text-left"
          >
            {erroAtendimento}
          </div>
        )}

        <DialogFooter className="flex-col gap-2 sm:flex-col pt-2">
          <Button
            type="button"
            size="lg"
            disabled={isPending || isRecusando || expirado}
            onClick={handleEntrarConsulta}
            className="w-full text-base font-bold min-h-[50px] shadow-lg shadow-primary/20 hover:scale-[1.02] active:scale-[0.98] transition-transform motion-reduce:transform-none"
          >
            {isPending ? "Conectando à Teleconsulta…" : "Entrar na Teleconsulta"}
          </Button>

          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={isPending || isRecusando}
            onClick={handleRecusar}
            aria-label="Não posso atender agora (Recusar chamada médica)"
            className="w-full text-xs text-muted-foreground hover:text-destructive"
          >
            {isRecusando ? "Recusando chamada…" : "Não posso atender agora (Recusar chamada)"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
