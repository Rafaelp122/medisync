import { useEffect, useRef, useState } from "react";
import { Progress } from "@/components/ui/progress";

export interface RingCountdownProps {
  open: boolean;
  ttlSegundos: number;
  chamadaIniciadaEm?: string | null;
  onExpire: () => void;
}

function calcularSegundosRestantes(ttlSegundos: number, chamadaIniciadaEm?: string | null): number {
  if (!chamadaIniciadaEm) {
    return Math.max(0, ttlSegundos);
  }
  const inicioMs = new Date(chamadaIniciadaEm).getTime();
  if (Number.isNaN(inicioMs)) {
    return Math.max(0, ttlSegundos);
  }
  const decorrido = Math.floor((Date.now() - inicioMs) / 1000);
  return Math.max(0, ttlSegundos - decorrido);
}

/**
 * Componente folha isolado para contagem regressiva de 45s (RN02 / RF-03).
 * Isola as atualizações de 1 Hz para evitar re-render no modal pai 45×/min
 * e respeita estritamente `@media (prefers-reduced-motion: reduce)`.
 * @see docs/user-stories/US-08-atendimento-chamada-no-show.md
 */
export function RingCountdown({
  open,
  ttlSegundos,
  chamadaIniciadaEm,
  onExpire,
}: RingCountdownProps) {
  const [segundosRestantes, setSegundosRestantes] = useState<number>(() =>
    calcularSegundosRestantes(ttlSegundos, chamadaIniciadaEm),
  );
  const onExpireRef = useRef(onExpire);
  onExpireRef.current = onExpire;

  useEffect(() => {
    if (!open) return;

    const initial = calcularSegundosRestantes(ttlSegundos, chamadaIniciadaEm);
    setSegundosRestantes(initial);

    if (initial <= 0) {
      onExpireRef.current();
      return;
    }

    let remaining = initial;
    const timer = setInterval(() => {
      remaining -= 1;
      const clamped = Math.max(0, remaining);
      setSegundosRestantes(clamped);
      if (clamped <= 0) {
        clearInterval(timer);
        onExpireRef.current();
      }
    }, 1000);

    return () => {
      clearInterval(timer);
    };
  }, [open, ttlSegundos, chamadaIniciadaEm]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between text-xs font-semibold px-1">
        <span className="text-muted-foreground uppercase tracking-wider">Tempo para Resposta</span>
        <span
          role="timer"
          aria-label={`${segundosRestantes} segundos restantes`}
          data-testid="ring-timer"
          className={
            segundosRestantes <= 10
              ? "text-destructive font-black text-base animate-pulse motion-reduce:animate-none"
              : "text-primary font-bold text-base motion-reduce:animate-none"
          }
        >
          {segundosRestantes}s
        </span>
      </div>

      {segundosRestantes === 10 && (
        <div role="status" aria-live="assertive" className="sr-only">
          Atenção: restam 10 segundos para atender a chamada médica.
        </div>
      )}
      {segundosRestantes === 0 && (
        <div role="status" aria-live="assertive" className="sr-only">
          O tempo de atendimento expirou.
        </div>
      )}

      <Progress
        value={segundosRestantes}
        max={ttlSegundos}
        aria-label="Tempo restante para atendimento"
        indicatorClassName={segundosRestantes <= 10 ? "bg-destructive" : "bg-primary"}
      />

      <p className="text-[11px] text-muted-foreground">
        A tolerância máxima para atendimento é de {ttlSegundos} segundos (RN02).
      </p>
    </div>
  );
}
