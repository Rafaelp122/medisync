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
import { useComunicarPiora } from "../api/use-comunicar-piora";

export interface PioraClinicaModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  atendimentoId: string;
  token?: string;
  onEmergenciaSamu: (orientacoes?: string | null) => void;
  onReclassificado: (data: {
    novaPrioridade: number;
    novaPosicao?: number | null;
    instrucoes?: string | null;
  }) => void;
}

const SINTOMAS_ALARME = [
  { id: "falta_de_ar", label: "Falta de ar intensa ou dificuldade para respirar" },
  { id: "dor_no_peito", label: "Dor ou aperto forte no peito" },
  { id: "tontura_desmaio", label: "Tontura severa, desmaio ou perda de consciência" },
  { id: "confusao_mental", label: "Confusão mental ou dificuldade para falar" },
  { id: "sangramento_grave", label: "Sangramento volumoso ou descontrolado" },
  { id: "febre_alta", label: "Febre muito alta com calafrios intensos" },
];

export function PioraClinicaModal({
  open,
  onOpenChange,
  atendimentoId,
  token,
  onEmergenciaSamu,
  onReclassificado,
}: PioraClinicaModalProps) {
  const [sintomasSelecionados, setSintomasSelecionados] = useState<string[]>([]);
  const [escalaDor, setEscalaDor] = useState<number>(0);
  const [queixaAdicional, setQueixaAdicional] = useState<string>("");
  const [erroValidacao, setErroValidacao] = useState<string | null>(null);

  const { mutate: comunicarPiora, isPending } = useComunicarPiora({
    onSuccess: (data) => {
      onOpenChange(false);
      if (data.alerta_samu_disparado || data.redirecionado_emergencia) {
        onEmergenciaSamu(data.orientacoes_emergencia || data.instrucoes);
      } else {
        onReclassificado({
          novaPrioridade: data.nova_prioridade ?? data.prioridade_clinica,
          novaPosicao: data.nova_posicao,
          instrucoes: data.instrucoes,
        });
      }
    },
    onError: (err) => {
      setErroValidacao(
        err.detail || err.message || "Erro ao comunicar piora clínica. Tente novamente.",
      );
    },
  });

  const toggleSintoma = (id: string) => {
    setSintomasSelecionados((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id],
    );
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setErroValidacao(null);

    if (sintomasSelecionados.length === 0 && !queixaAdicional.trim() && escalaDor === 0) {
      setErroValidacao(
        "Selecione ao menos um sintoma novo, informe alteração na dor ou descreva o agravamento.",
      );
      return;
    }

    comunicarPiora({
      token,
      body: {
        atendimento_id: atendimentoId,
        novos_sintomas: sintomasSelecionados,
        escala_dor: escalaDor,
        queixa_adicional: queixaAdicional.trim(),
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-xl font-bold text-destructive flex items-center gap-2">
            <span aria-hidden="true">⚠️</span>
            Salvaguarda de Piora Clínica
          </DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            Sua saúde é nossa prioridade. Relate qualquer agravamento dos seus sintomas para
            reavaliação imediata pelo motor de triagem (RF-06).
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 pt-2">
          {erroValidacao && (
            <div
              role="alert"
              className="p-3 bg-destructive/10 text-destructive rounded-lg text-xs font-medium border border-destructive/20"
            >
              {erroValidacao}
            </div>
          )}

          <div className="space-y-2">
            <p className="text-xs font-bold text-foreground block">
              Sinais de Alerta ou Novos Sintomas
            </p>
            <div className="space-y-2">
              {SINTOMAS_ALARME.map((sintoma) => (
                <label
                  key={sintoma.id}
                  htmlFor={`sintoma-${sintoma.id}`}
                  className="flex items-start gap-2.5 p-2 rounded-lg border border-border hover:bg-muted/50 cursor-pointer text-xs"
                >
                  <input
                    id={`sintoma-${sintoma.id}`}
                    type="checkbox"
                    checked={sintomasSelecionados.includes(sintoma.id)}
                    onChange={() => toggleSintoma(sintoma.id)}
                    className="mt-0.5 h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
                  />
                  <span className="text-foreground leading-snug">{sintoma.label}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="space-y-1.5">
            <div className="flex justify-between items-center">
              <label htmlFor="piora-escala-dor" className="text-xs font-bold text-foreground">
                Intensidade da Dor Atual (0 a 10)
              </label>
              <span className="text-xs font-extrabold text-primary px-2 py-0.5 bg-primary/10 rounded">
                Nível {escalaDor}
              </span>
            </div>
            <input
              id="piora-escala-dor"
              type="range"
              min="0"
              max="10"
              value={escalaDor}
              onChange={(e) => setEscalaDor(Number.parseInt(e.target.value, 10))}
              className="w-full accent-primary cursor-pointer h-2 bg-muted rounded-lg"
            />
            <div className="flex justify-between text-[10px] text-muted-foreground px-1">
              <span>0 (Sem dor)</span>
              <span>5 (Moderada)</span>
              <span>10 (Insuportável)</span>
            </div>
          </div>

          <div className="space-y-1.5">
            <label htmlFor="piora-queixa" className="text-xs font-bold text-foreground">
              Descreva com suas palavras o que piorou
            </label>
            <textarea
              id="piora-queixa"
              rows={3}
              value={queixaAdicional}
              onChange={(e) => setQueixaAdicional(e.target.value)}
              placeholder="Exemplo: Comecei a suar frio e a dor se espalhou…"
              maxLength={2000}
              className="w-full text-xs p-2.5 rounded-lg border border-input bg-background text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>

          <DialogFooter className="gap-2 sm:gap-0 pt-2">
            <Button
              type="button"
              variant="outline"
              disabled={isPending}
              onClick={() => onOpenChange(false)}
            >
              Cancelar
            </Button>
            <Button type="submit" variant="destructive" disabled={isPending}>
              {isPending ? "Reavaliando…" : "Enviar Reavaliação"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
