import { cn } from "@/lib/utils";

export interface PainScaleSelectorProps {
  value: number;
  onChange: (value: number) => void;
  className?: string;
}

export function obterDescricaoDor(nivel: number): string {
  if (nivel === 0) return "Sem dor";
  if (nivel <= 3) return "Dor leve";
  if (nivel <= 6) return "Dor moderada";
  if (nivel <= 8) return "Dor intensa";
  return "Pior dor imaginável";
}

function obterCorBotaoDor(nivel: number, selecionado: boolean): string {
  if (!selecionado) {
    return "bg-secondary text-secondary-foreground hover:bg-muted";
  }
  if (nivel === 0)
    return "bg-emerald-600 text-white font-bold ring-2 ring-emerald-600 ring-offset-2";
  if (nivel <= 3) return "bg-green-600 text-white font-bold ring-2 ring-green-600 ring-offset-2";
  if (nivel <= 6) return "bg-amber-500 text-black font-bold ring-2 ring-amber-500 ring-offset-2";
  if (nivel <= 8) return "bg-orange-600 text-white font-bold ring-2 ring-orange-600 ring-offset-2";
  return "bg-destructive text-destructive-foreground font-bold ring-2 ring-destructive ring-offset-2";
}

const NIVEIS_DOR = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10] as const;

export function PainScaleSelector({ value, onChange, className }: PainScaleSelectorProps) {
  const descricao = obterDescricaoDor(value);

  return (
    <div className={cn("space-y-3", className)}>
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium text-foreground">Escala Visual Analógica de Dor:</span>
        <span className="font-semibold text-primary">
          {descricao} ({value}/10)
        </span>
      </div>

      <fieldset
        aria-label="Escala de dor de 0 a 10"
        className="border-0 p-0 m-0 min-w-0 grid grid-cols-11 gap-1 sm:gap-1.5"
      >
        {NIVEIS_DOR.map((nivel) => {
          const selecionado = value === nivel;
          return (
            <button
              key={`pain-level-${nivel}`}
              type="button"
              aria-label={`Nível ${nivel}`}
              aria-pressed={selecionado}
              onClick={() => onChange(nivel)}
              className={cn(
                "h-10 sm:h-11 rounded-md text-sm sm:text-base font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                obterCorBotaoDor(nivel, selecionado),
              )}
            >
              {nivel}
            </button>
          );
        })}
      </fieldset>

      <div className="flex justify-between text-xs text-muted-foreground px-0.5">
        <span>0 - Sem dor</span>
        <span>10 - Pior dor</span>
      </div>
    </div>
  );
}
