import { Trash2 } from "lucide-react";
import type { ItemPrescricaoRequest } from "@/api/generated/types.gen";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export interface PrescriptionItemsListProps {
  itens: ItemPrescricaoRequest[];
  onRemoveItem: (index: number) => void;
  isReadOnly?: boolean;
}

/**
 * Listagem acessível de medicamentos prescritos com salvaguardas de controle especial.
 */
export function PrescriptionItemsList({
  itens,
  onRemoveItem,
  isReadOnly = false,
}: PrescriptionItemsListProps) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-foreground">
          Itens da Prescrição ({itens.length}):
        </span>
      </div>

      {itens.length === 0 ? (
        <p className="text-xs text-muted-foreground italic py-2">
          Nenhum medicamento adicionado à receita até o momento.
        </p>
      ) : (
        <div className="divide-y divide-border border border-border rounded-md overflow-hidden text-xs">
          {itens.map((item, idx) => (
            <div
              key={`${item.medicamento}-${item.dosagem}-${item.posologia}`}
              className="flex items-center justify-between p-2 hover:bg-muted/30"
            >
              <div className="space-y-0.5">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-foreground">{item.medicamento}</span>
                  <span className="text-muted-foreground">({item.dosagem})</span>
                  {item.controle_especial && (
                    <Badge variant="warning" className="text-[10px] py-0 px-1">
                      Controle Especial C1
                    </Badge>
                  )}
                </div>
                <p className="text-muted-foreground text-[11px]">
                  {item.posologia} {item.duracao ? `• Duração: ${item.duracao}` : ""}
                </p>
              </div>
              {!isReadOnly && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => onRemoveItem(idx)}
                  aria-label={`Remover ${item.medicamento}`}
                  className="size-7 p-0 text-muted-foreground hover:text-destructive"
                >
                  <Trash2 className="size-3.5" />
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
