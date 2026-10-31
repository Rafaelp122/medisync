import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export interface SamuEmergencyModalProps {
  open: boolean;
  onOpenChange?: (open: boolean) => void;
  orientacoes?: string | null;
  onConfirmarSaida?: () => void;
  onCorrigirSintomas?: () => void;
}

/**
 * Emite sinal sonoro de dois tons (880Hz / 440Hz) de alerta médico de emergência.
 * Atende ao critério de alerta audiovisual (RN04 / Issue 29 / WCAG 2.1 AA).
 */
export function reproduzirAlertaEmergenciaSonoro() {
  try {
    if (typeof window === "undefined") return;
    const AudioCtx =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const now = ctx.currentTime;

    const osc1 = ctx.createOscillator();
    const gain1 = ctx.createGain();
    osc1.type = "sine";
    osc1.frequency.setValueAtTime(880, now);
    gain1.gain.setValueAtTime(0.25, now);
    gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.25);
    osc1.connect(gain1);
    gain1.connect(ctx.destination);
    osc1.start(now);
    osc1.stop(now + 0.25);

    const osc2 = ctx.createOscillator();
    const gain2 = ctx.createGain();
    osc2.type = "sine";
    osc2.frequency.setValueAtTime(440, now + 0.25);
    gain2.gain.setValueAtTime(0.25, now + 0.25);
    gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.55);
    osc2.connect(gain2);
    gain2.connect(ctx.destination);
    osc2.start(now + 0.25);
    osc2.stop(now + 0.55);

    setTimeout(() => {
      ctx.close().catch(() => {});
    }, 600);
  } catch {
    // Silencioso em caso de restrição de autoplay ou ambiente sem áudio
  }
}

/**
 * Modal Composto de Emergência Clínica e Salvaguarda SAMU 192 (RN04, RF-06).
 *
 * Interrompe imediatamente o acolhimento telemédico em caso de risco clínico crítico
 * (Nível 1 - Vermelho), fornecendo discagem rápida telefônica (tel:192) e
 * orientações de encaminhamento pré-hospitalar urgente.
 *
 * @see docs/user-stories/US-01-acolhimento-triagem-tcle.md
 * @see docs/user-stories/US-06-deterioracao-clinica-escape-samu.md
 */
export function SamuEmergencyModal({
  open,
  onOpenChange,
  orientacoes,
  onConfirmarSaida,
  onCorrigirSintomas,
}: SamuEmergencyModalProps) {
  useEffect(() => {
    if (open) {
      reproduzirAlertaEmergenciaSonoro();
    }
  }, [open]);

  const instrucaoPadrao =
    orientacoes ||
    "Ligue imediatamente para o SAMU 192 ou dirija-se à UPA ou Pronto-Socorro mais próximo.";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        role="alertdialog"
        className="border-destructive/80 bg-background text-foreground sm:max-w-md shadow-2xl"
        onPointerDownOutside={(e) => e.preventDefault()}
        onEscapeKeyDown={(e) => e.preventDefault()}
      >
        <DialogHeader className="space-y-3">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-destructive/10 text-destructive">
            <span className="text-3xl" aria-hidden="true">
              🚑
            </span>
          </div>
          <DialogTitle className="text-center text-xl font-bold text-destructive">
            Emergência Médica Detectada
          </DialogTitle>
          <DialogDescription className="text-center text-base text-foreground/90 font-medium leading-relaxed">
            Seus sintomas ou queixas indicam um quadro crítico de saúde que{" "}
            <strong>não pode ser atendido por teleconsulta virtual</strong>.
          </DialogDescription>
        </DialogHeader>

        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-foreground space-y-2">
          <p className="font-semibold text-destructive">Orientações Imediatas de Socorro:</p>
          <p className="leading-relaxed">{instrucaoPadrao}</p>
        </div>

        <DialogFooter className="flex flex-col gap-2 sm:flex-col sm:space-x-0 pt-2">
          <Button
            asChild
            variant="destructive"
            size="lg"
            className="w-full text-base font-bold shadow-md"
          >
            <a href="tel:192" className="flex items-center justify-center gap-2">
              <span aria-hidden="true">📞</span>
              Ligar para o SAMU 192
            </a>
          </Button>

          {onCorrigirSintomas && (
            <Button
              type="button"
              variant="outline"
              size="default"
              onClick={onCorrigirSintomas}
              className="w-full font-medium"
            >
              ↩️ Selecionei por engano, quero corrigir meus sintomas
            </Button>
          )}

          {onConfirmarSaida && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onConfirmarSaida}
              className="w-full text-xs text-muted-foreground mt-1"
            >
              Entendi, vou procurar atendimento presencial
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
