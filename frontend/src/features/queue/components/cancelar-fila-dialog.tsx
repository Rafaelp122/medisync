import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useCancelarFila } from "../api/use-cancelar-fila";

export interface CancelarFilaDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  atendimentoId: string;
  token?: string;
  onCancelado: () => void;
}

export function CancelarFilaDialog({
  open,
  onOpenChange,
  atendimentoId,
  token,
  onCancelado,
}: CancelarFilaDialogProps) {
  const [motivo, setMotivo] = useState("");
  const { mutate: cancelar, isPending } = useCancelarFila({
    onSuccess: () => {
      onOpenChange(false);
      onCancelado();
    },
  });

  const handleConfirmar = () => {
    cancelar({
      atendimentoId,
      token,
      body: {
        motivo: motivo.trim() || "Desistência voluntária pelo paciente",
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-lg font-bold text-foreground">
            Desistir do Atendimento
          </DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            Tem certeza de que deseja sair da fila virtual? Sua vaga será cancelada e você precisará
            reiniciar o processo caso deseje novo atendimento (RN06).
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2 py-2">
          <label htmlFor="motivo-cancelamento" className="text-xs font-medium text-foreground">
            Motivo da desistência (opcional)
          </label>
          <input
            id="motivo-cancelamento"
            type="text"
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            placeholder="Ex.: Melhora espontânea, outro compromisso…"
            maxLength={500}
            className="w-full text-xs p-2.5 rounded-lg border border-input bg-background text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            type="button"
            variant="outline"
            disabled={isPending}
            onClick={() => onOpenChange(false)}
          >
            Permanecer na Fila
          </Button>
          <Button
            type="button"
            variant="destructive"
            disabled={isPending}
            onClick={handleConfirmar}
          >
            {isPending ? "Cancelando…" : "Confirmar Desistência"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
