import { AlertCircle } from "lucide-react";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export interface AtestadoFormProps {
  duracaoConsulta: number;
  exigeJustificativa: boolean;
  justificativaTempoInferior: string;
  onJustificativaChange: (valor: string) => void;
  isReadOnly?: boolean;
}

/**
 * Formulário de justificativa médica e trava temporal antifraude para Atestado Médico.
 * Regras: CFM nº 2.314/2022, RF-07, US-10.
 */
export function AtestadoForm({
  duracaoConsulta,
  exigeJustificativa,
  justificativaTempoInferior,
  onJustificativaChange,
  isReadOnly = false,
}: AtestadoFormProps) {
  return (
    <div className="space-y-3">
      {exigeJustificativa && (
        <div className="space-y-1.5 p-2.5 rounded-md bg-amber-500/10 border border-amber-500/30 text-amber-900 dark:text-amber-200">
          <div className="flex items-center gap-1.5 text-xs font-semibold">
            <AlertCircle className="size-3.5 text-amber-600 dark:text-amber-400" />
            <span>Trava Temporal Antifraude (CFM nº 2.314/2022)</span>
          </div>
          <p className="text-[11px] text-muted-foreground">
            A consulta durou {duracaoConsulta}s (inferior ao piso de 180s). É mandatória a
            justificativa médica circunstanciando a emissão célere de atestado (mínimo de 15
            caracteres).
          </p>
          <div className="space-y-1 pt-1">
            <Label htmlFor="justificativa-tempo-inferior" className="text-xs">
              Justificativa Médica:
            </Label>
            <Textarea
              id="justificativa-tempo-inferior"
              placeholder="Descreva a justificativa clínica circunstanciada para emissão em tempo inferior a 180s (mínimo 15 caracteres)..."
              value={justificativaTempoInferior}
              onChange={(e) => onJustificativaChange(e.target.value)}
              className="text-xs min-h-[60px]"
              disabled={isReadOnly}
            />
            {justificativaTempoInferior.trim().length > 0 &&
              justificativaTempoInferior.trim().length < 15 && (
                <p className="text-[11px] text-destructive">
                  Mínimo de 15 caracteres (atual: {justificativaTempoInferior.trim().length})
                </p>
              )}
          </div>
        </div>
      )}
      {!exigeJustificativa && (
        <p className="text-xs text-muted-foreground italic py-1">
          Emissão de atestado médico de afastamento com carimbo temporal e assinatura qualificada
          ICP-Brasil.
        </p>
      )}
    </div>
  );
}
