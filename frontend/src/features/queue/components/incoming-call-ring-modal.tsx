import { useEffect, useRef, useState } from "react";
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
import { Progress } from "@/components/ui/progress";
import { useAtenderChamada } from "../api/use-atender-chamada";
import { iniciarToqueChamadaMedica } from "../lib/audio-chime";

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
}

export function IncomingCallRingModal({
  open,
  atendimentoId,
  pacienteId,
  nomePaciente,
  token,
  ttlSegundos = 45,
  chamadaIniciadaEm,
  onAtendido,
  onNoShow,
}: IncomingCallRingModalProps) {
  const [segundosRestantes, setSegundosRestantes] = useState<number>(ttlSegundos);
  const [erroAtendimento, setErroAtendimento] = useState<string | null>(null);
  const pararToqueRef = useRef<(() => void) | null>(null);

  const { mutate: atenderChamada, isPending } = useAtenderChamada({
    onSuccess: (data) => {
      if (pararToqueRef.current) {
        pararToqueRef.current();
        pararToqueRef.current = null;
      }
      onAtendido(data);
    },
    onError: (err) => {
      if (err.status === 409 || err.code === "ATENDIMENTO_EXPIRADO_NO_SHOW") {
        setErroAtendimento(
          "O prazo de 45 segundos para resposta expirou. O atendimento foi encerrado por ausência.",
        );
        if (pararToqueRef.current) {
          pararToqueRef.current();
          pararToqueRef.current = null;
        }
        onNoShow();
      } else {
        setErroAtendimento(err.detail || err.message || "Erro ao conectar à chamada médica.");
      }
    },
  });

  const onNoShowRef = useRef(onNoShow);
  onNoShowRef.current = onNoShow;

  // Gerenciamento do Áudio Chime
  useEffect(() => {
    if (!open) {
      if (pararToqueRef.current) {
        pararToqueRef.current();
        pararToqueRef.current = null;
      }
      return;
    }

    // Inicia toque sonoro contínuo
    pararToqueRef.current = iniciarToqueChamadaMedica();

    return () => {
      if (pararToqueRef.current) {
        pararToqueRef.current();
        pararToqueRef.current = null;
      }
    };
  }, [open]);

  // Contagem Regressiva Determinística de 45s (RN02 / RF-03)
  useEffect(() => {
    if (!open) return;

    // Calcula tempo inicial com base no timestamp da chamada (se fornecido)
    let initialSeconds = ttlSegundos;
    if (chamadaIniciadaEm) {
      const inicioMs = new Date(chamadaIniciadaEm).getTime();
      const decorrido = Math.floor((Date.now() - inicioMs) / 1000);
      initialSeconds = Math.max(0, ttlSegundos - decorrido);
    }
    setSegundosRestantes(initialSeconds);

    if (initialSeconds <= 0) {
      if (pararToqueRef.current) {
        pararToqueRef.current();
        pararToqueRef.current = null;
      }
      onNoShowRef.current();
      return;
    }

    let remaining = initialSeconds;
    const timer = setInterval(() => {
      remaining -= 1;
      setSegundosRestantes(Math.max(0, remaining));
      if (remaining <= 0) {
        clearInterval(timer);
        if (pararToqueRef.current) {
          pararToqueRef.current();
          pararToqueRef.current = null;
        }
        onNoShowRef.current();
      }
    }, 1000);

    return () => {
      clearInterval(timer);
    };
  }, [open, ttlSegundos, chamadaIniciadaEm]);

  const handleEntrarConsulta = () => {
    setErroAtendimento(null);
    atenderChamada({
      atendimentoId,
      pacienteId,
      nomePaciente,
      token,
    });
  };

  return (
    <Dialog open={open}>
      <DialogContent
        role="alertdialog"
        onPointerDownOutside={(e) => e.preventDefault()}
        onEscapeKeyDown={(e) => e.preventDefault()}
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

        <div className="space-y-3">
          <div className="flex items-center justify-between text-xs font-semibold px-1">
            <span className="text-muted-foreground uppercase tracking-wider">
              Tempo para Resposta
            </span>
            <span
              role="timer"
              aria-live="assertive"
              data-testid="ring-timer"
              className={
                segundosRestantes <= 10
                  ? "text-destructive font-black text-base animate-pulse"
                  : "text-primary font-bold text-base"
              }
            >
              {segundosRestantes}s
            </span>
          </div>

          <Progress
            value={segundosRestantes}
            max={ttlSegundos}
            indicatorClassName={segundosRestantes <= 10 ? "bg-destructive" : "bg-primary"}
          />

          <p className="text-[11px] text-muted-foreground">
            A tolerância máxima para atendimento é de 45 segundos (RN02).
          </p>
        </div>

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
            disabled={isPending || segundosRestantes <= 0}
            onClick={handleEntrarConsulta}
            className="w-full text-base font-bold min-h-[50px] shadow-lg shadow-primary/20 hover:scale-[1.02] active:scale-[0.98] transition-transform motion-reduce:transform-none"
          >
            {isPending ? "Conectando à Teleconsulta…" : "Entrar na Teleconsulta"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
