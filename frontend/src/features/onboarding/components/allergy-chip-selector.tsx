import { Label } from "@/components/ui/label";

export const ALERGIAS_COMUNS = [
  "Não possuo alergias",
  "Dipirona",
  "Penicilina / Amoxicilina",
  "AINEs (Ibuprofeno/AAS)",
  "Sulfa",
  "Contraste iodado",
];

export interface AllergyChipSelectorProps {
  selected: string[];
  onToggle: (alergia: string) => void;
}

/**
 * Seletor multi-escolha de alergias medicamentosas conhecidas em Fase 2.
 */
export function AllergyChipSelector({ selected, onToggle }: AllergyChipSelectorProps) {
  return (
    <div className="space-y-2">
      <Label>Alergias Medicamentosas Conhecidas</Label>
      <div className="flex flex-wrap gap-1.5">
        {ALERGIAS_COMUNS.map((alergia) => {
          const ativa = selected.includes(alergia);
          return (
            <button
              key={alergia}
              type="button"
              aria-pressed={ativa}
              onClick={() => onToggle(alergia)}
              className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${ativa ? "bg-primary text-primary-foreground border-primary font-medium" : "bg-background text-foreground hover:bg-muted border-border"}`}
            >
              {alergia}
            </button>
          );
        })}
      </div>
    </div>
  );
}
