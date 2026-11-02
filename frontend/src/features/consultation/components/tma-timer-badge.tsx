import { useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { settings } from "@/config/settings";

export interface TmaTimerBadgeProps {
  iniciadoEm?: string | null;
  tmaPlanejadoSegundos?: number;
}

/**
 * Componente folha isolado para contagem e exibição passiva de TMA.
 * Garante estrita conformidade com a Regra RN06 (Preservação Soberana do Ato Médico):
 * o estouro de tempo NUNCA interrompe, desconecta ou bloqueia a consulta médica.
 */
export function TmaTimerBadge({
  iniciadoEm,
  tmaPlanejadoSegundos = settings.clinical.tmaPlannedSeconds,
}: TmaTimerBadgeProps) {
  const calcularDiff = () => {
    if (!iniciadoEm) return 0;
    const inicio = new Date(iniciadoEm).getTime();
    return Math.max(0, Math.floor((Date.now() - inicio) / 1000));
  };

  const [segundosDecorridos, setSegundosDecorridos] = useState<number>(calcularDiff);
  const inicioRef = useRef<number>(iniciadoEm ? new Date(iniciadoEm).getTime() : Date.now());

  useEffect(() => {
    const inicio = iniciadoEm ? new Date(iniciadoEm).getTime() : Date.now();
    inicioRef.current = inicio;
    setSegundosDecorridos(Math.max(0, Math.floor((Date.now() - inicio) / 1000)));

    const interval = setInterval(() => {
      const agora = Date.now();
      const diff = Math.max(0, Math.floor((agora - inicioRef.current) / 1000));
      setSegundosDecorridos(diff);
    }, 1000);

    return () => clearInterval(interval);
  }, [iniciadoEm]);

  const minutos = Math.floor(segundosDecorridos / 60);
  const segundos = segundosDecorridos % 60;
  const tempoFormatado = `${String(minutos).padStart(2, "0")}:${String(segundos).padStart(2, "0")}`;

  const excedeuTma = segundosDecorridos > tmaPlanejadoSegundos;
  const minutosExcedidos = Math.max(
    1,
    Math.floor((segundosDecorridos - tmaPlanejadoSegundos) / 60),
  );

  if (excedeuTma) {
    return (
      <Badge
        variant="warning"
        aria-live="polite"
        className="text-xs px-2.5 py-1 font-medium gap-1.5"
      >
        <span className="inline-block size-2 rounded-full bg-amber-500 animate-pulse" />
        <span>
          TMA: {tempoFormatado} (+{minutosExcedidos}m) — Teleconsulta preservada sob RN06
        </span>
      </Badge>
    );
  }

  return (
    <Badge
      variant="outline"
      aria-live="polite"
      className="text-xs px-2.5 py-1 font-medium gap-1.5 text-muted-foreground"
    >
      <span className="inline-block size-2 rounded-full bg-emerald-500" />
      <span>
        TMA: {tempoFormatado} / {Math.floor(tmaPlanejadoSegundos / 60)}m
      </span>
    </Badge>
  );
}
