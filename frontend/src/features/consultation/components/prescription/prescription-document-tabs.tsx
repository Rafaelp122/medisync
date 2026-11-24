import { cn } from "@/lib/utils";

export interface PrescriptionDocumentTabsProps {
  selected: "RECEITA_SIMPLES" | "ATESTADO_MEDICO";
  onSelect: (tipo: "RECEITA_SIMPLES" | "ATESTADO_MEDICO") => void;
}

/**
 * Alternador em abas entre Receita Digital e Atestado Médico.
 */
export function PrescriptionDocumentTabs({ selected, onSelect }: PrescriptionDocumentTabsProps) {
  const isAtestado = selected === "ATESTADO_MEDICO";

  return (
    <div
      role="tablist"
      aria-label="Tipo de documento clínico"
      className="flex items-center gap-1 p-1 bg-muted rounded-md"
    >
      <button
        type="button"
        role="tab"
        aria-selected={!isAtestado}
        onClick={() => onSelect("RECEITA_SIMPLES")}
        className={cn(
          "flex-1 py-1 px-2.5 rounded text-xs font-medium transition-[background-color,color,box-shadow]",
          !isAtestado
            ? "bg-background text-foreground shadow-xs font-semibold"
            : "text-muted-foreground hover:text-foreground",
        )}
      >
        Receita Simples
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={isAtestado}
        onClick={() => onSelect("ATESTADO_MEDICO")}
        className={cn(
          "flex-1 py-1 px-2.5 rounded text-xs font-medium transition-[background-color,color,box-shadow]",
          isAtestado
            ? "bg-background text-foreground shadow-xs font-semibold"
            : "text-muted-foreground hover:text-foreground",
        )}
      >
        Atestado Médico
      </button>
    </div>
  );
}
