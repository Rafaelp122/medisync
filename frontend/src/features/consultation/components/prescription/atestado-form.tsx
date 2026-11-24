import { AlertCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export interface AtestadoFormProps {
  duracaoConsulta?: number;
  atendimentoIniciadoEm?: string | null;
  justificativaTempoInferior: string;
  onJustificativaChange: (valor: string) => void;
  onTempoMinimoAtingido?: () => void;
  accessMode?: "editable" | "readonly";
}

function calcularSegundosDecorridos(
  atendimentoIniciadoEm?: string | null,
  fallbackSegundos = 0,
): number {
  if (!atendimentoIniciadoEm) return Math.max(0, fallbackSegundos);
  const inicioMs = new Date(atendimentoIniciadoEm).getTime();
  if (Number.isNaN(inicioMs)) return Math.max(0, fallbackSegundos);
  return Math.max(0, Math.floor((Date.now() - inicioMs) / 1000));
}

/**
 * Formulário de justificativa médica e trava temporal antifraude de 180s para Atestado Médico.
 * Isola o tick de 1s internamente para impedir re-renders no componente pai.
 * Regras: CFM nº 2.314/2022, RF-07, US-10.
 */
export function AtestadoForm({
  duracaoConsulta,
  atendimentoIniciadoEm,
  justificativaTempoInferior,
  onJustificativaChange,
  onTempoMinimoAtingido,
  accessMode = "editable",
}: AtestadoFormProps) {
  const isLocked = accessMode === "readonly";
  const [segundosDecorridos, setSegundosDecorridos] = useState<number>(() =>
    calcularSegundosDecorridos(atendimentoIniciadoEm, duracaoConsulta ?? 0),
  );
  const onTempoMinimoRef = useRef(onTempoMinimoAtingido);
  onTempoMinimoRef.current = onTempoMinimoAtingido;

  useEffect(() => {
    const initial = calcularSegundosDecorridos(atendimentoIniciadoEm, duracaoConsulta ?? 0);
    setSegundosDecorridos(initial);
    if (initial >= 180) {
      onTempoMinimoRef.current?.();
      return;
    }
    if (!atendimentoIniciadoEm) return;

    const timer = setInterval(() => {
      const elapsed = calcularSegundosDecorridos(atendimentoIniciadoEm, 0);
      setSegundosDecorridos(elapsed);
      if (elapsed >= 180) {
        clearInterval(timer);
        onTempoMinimoRef.current?.();
      }
    }, 1000);

    return () => {
      clearInterval(timer);
    };
  }, [atendimentoIniciadoEm, duracaoConsulta]);

  const exigeJustificativa = segundosDecorridos < 180;

  return (
    <div className="space-y-3">
      {exigeJustificativa ? (
        <div className="space-y-1.5 p-2.5 rounded-md bg-amber-500/10 border border-amber-500/30 text-amber-900 dark:text-amber-200">
          <div className="flex items-center gap-1.5 text-xs font-semibold">
            <AlertCircle className="size-3.5 text-amber-600 dark:text-amber-400" />
            <span>Trava Temporal Antifraude (CFM nº 2.314/2022)</span>
          </div>
          <p className="text-[11px] text-muted-foreground">
            A consulta durou {segundosDecorridos}s (inferior ao piso de 180s). É mandatória a
            justificativa médica circunstanciando a emissão célere de atestado (mínimo de 15
            caracteres).
          </p>
          <div className="space-y-1 pt-1">
            <Label htmlFor="justificativa-tempo-inferior" className="text-xs">
              Justificativa Médica:
            </Label>
            <Textarea
              id="justificativa-tempo-inferior"
              placeholder="Descreva a justificativa clínica circunstanciada para emissão em tempo inferior a 180s (mínimo 15 caracteres)…"
              value={justificativaTempoInferior}
              onChange={(e) => onJustificativaChange(e.target.value)}
              className="text-xs min-h-[60px]"
              disabled={isLocked}
            />
            {justificativaTempoInferior.trim().length > 0 &&
              justificativaTempoInferior.trim().length < 15 && (
                <p className="text-[11px] text-destructive">
                  Mínimo de 15 caracteres (atual: {justificativaTempoInferior.trim().length})
                </p>
              )}
          </div>
        </div>
      ) : (
        <p className="text-xs text-muted-foreground italic py-1">
          Emissão de atestado médico de afastamento com carimbo temporal e assinatura qualificada
          ICP-Brasil.
        </p>
      )}
    </div>
  );
}
