import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export interface QueueWaitingActionsCardProps {
  onAbrirPiora: () => void;
  onComplementarCadastro?: () => void;
  onAbrirCancelar: () => void;
}

/**
 * Painel de ações assistenciais durante espera ativa na fila virtual (RF-06, RF-02, RN06).
 */
export function QueueWaitingActionsCard({
  onAbrirPiora,
  onComplementarCadastro,
  onAbrirCancelar,
}: QueueWaitingActionsCardProps) {
  return (
    <Card className="border-border/80 shadow-sm">
      <CardContent className="pt-4 space-y-3">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 p-3 bg-destructive/5 rounded-lg border border-destructive/15">
          <div className="text-left space-y-0.5">
            <span className="text-xs font-bold text-destructive block">
              Sentiu piora nos sintomas?
            </span>
            <span className="text-[11px] text-muted-foreground block">
              Acione a reavaliação imediata de risco pelo protocolo de triagem (RF-06).
            </span>
          </div>
          <Button
            type="button"
            variant="destructive"
            size="sm"
            className="w-full sm:w-auto shrink-0 font-semibold"
            onClick={onAbrirPiora}
          >
            Relatar Piora
          </Button>
        </div>

        {onComplementarCadastro && (
          <div className="flex flex-col sm:flex-row items-center justify-between gap-3 p-3 bg-muted/40 rounded-lg border border-border">
            <div className="text-left space-y-0.5">
              <span className="text-xs font-semibold text-foreground block">
                Prontuário e Dados Cadastrais
              </span>
              <span className="text-[11px] text-muted-foreground block">
                Complete seu endereço e alergias para agilizar o atendimento médico.
              </span>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-full sm:w-auto shrink-0 font-medium"
              onClick={onComplementarCadastro}
            >
              Completar Cadastro
            </Button>
          </div>
        )}

        <div className="flex justify-between items-center pt-1 border-t text-xs">
          <button
            type="button"
            onClick={onAbrirCancelar}
            className="text-muted-foreground hover:text-destructive underline-offset-4 hover:underline transition-colors py-1"
          >
            Desistir do atendimento
          </button>
        </div>
      </CardContent>
    </Card>
  );
}
