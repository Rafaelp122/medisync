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
  if (nivel <= 3) {
    return "bg-acr-green text-acr-green-foreground font-bold ring-2 ring-acr-green ring-offset-2";
  }
  if (nivel <= 6) {
    return "bg-acr-yellow text-acr-yellow-foreground font-bold ring-2 ring-acr-yellow ring-offset-2";
  }
  if (nivel <= 8) {
    return "bg-acr-orange text-acr-orange-foreground font-bold ring-2 ring-acr-orange ring-offset-2";
  }
  return "bg-acr-red text-acr-red-foreground font-bold ring-2 ring-acr-red ring-offset-2";
}

const NIVEIS_DOR = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10] as const;

export function PainScaleSelector({ value, onChange, className }: PainScaleSelectorProps) {
  const descricao = obterDescricaoDor(value);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowLeft" || e.key === "ArrowDown") {
      e.preventDefault();
      onChange(Math.max(0, value - 1));
    } else if (e.key === "ArrowRight" || e.key === "ArrowUp") {
      e.preventDefault();
      onChange(Math.min(10, value + 1));
    } else if (e.key === "Home") {
      e.preventDefault();
      onChange(0);
    } else if (e.key === "End") {
      e.preventDefault();
      onChange(10);
    }
  };

  return (
    <div className={cn("space-y-3", className)}>
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium text-foreground">Escala Visual Analógica de Dor:</span>
        <span className="font-semibold text-primary">
          {descricao} ({value}/10)
        </span>
      </div>

      <div
        role="radiogroup"
        aria-label="Escala de dor de 0 a 10"
        onKeyDown={handleKeyDown}
        className="grid grid-cols-6 sm:grid-cols-11 gap-2 sm:gap-1.5"
      >
        {NIVEIS_DOR.map((nivel) => {
          const selecionado = value === nivel;
          return (
            // biome-ignore lint/a11y/useSemanticElements: custom visual radio buttons with keyboard navigation
            <button
              key={`pain-level-${nivel}`}
              type="button"
              role="radio"
              aria-label={`Nível ${nivel}`}
              aria-checked={selecionado}
              tabIndex={selecionado || (value === 0 && nivel === 0) ? 0 : -1}
              onClick={() => onChange(nivel)}
              className={cn(
                "min-h-[44px] min-w-[44px] h-11 rounded-md text-sm sm:text-base font-semibold touch-manipulation transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                obterCorBotaoDor(nivel, selecionado),
              )}
            >
              {nivel}
            </button>
          );
        })}
      </div>

      <div className="flex justify-between text-xs text-muted-foreground px-0.5">
        <span>0 - Sem dor</span>
        <span>10 - Pior dor</span>
      </div>
    </div>
  );
}
