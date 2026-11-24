import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { useComunicarPiora } from "../api/use-comunicar-piora";
import {
  type PioraClinicaFormData,
  type PioraClinicaInputFormData,
  pioraClinicaFormSchema,
} from "../schemas/piora-clinica-schema";

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

export const SINTOMAS_ALARME = [
  { id: "dispneia_grave", label: "Falta de ar intensa ou dificuldade para respirar" },
  { id: "dor_toracica_irradiada", label: "Dor ou aperto forte no peito" },
  { id: "inconsciencia", label: "Tontura severa, desmaio ou perda de consciência" },
  { id: "confusao_mental", label: "Confusão mental ou dificuldade para falar" },
  { id: "hemorragia_grave", label: "Sangramento volumoso ou descontrolado" },
  { id: "febre", label: "Febre muito alta com calafrios intensos" },
];

/**
 * Modal de Salvaguarda de Piora Clínica e Reavaliação de Risco (RF-06, RN04).
 * Gerenciado via React Hook Form + zodResolver(pioraClinicaFormSchema) enviando IDs
 * canônicos de gravidade reconhecidos pelo motor backend `triage`.
 * @see docs/user-stories/US-06-deterioracao-clinica-escape-samu.md
 */
export function PioraClinicaModal({
  open,
  onOpenChange,
  atendimentoId,
  token,
  onEmergenciaSamu,
  onReclassificado,
}: PioraClinicaModalProps) {
  const [erroServidor, setErroServidor] = useState<string | null>(null);

  const form = useForm<PioraClinicaInputFormData, unknown, PioraClinicaFormData>({
    resolver: zodResolver(pioraClinicaFormSchema),
    defaultValues: {
      atendimento_id: atendimentoId,
      novos_sintomas: [],
      escala_dor: 0,
      queixa_adicional: "",
    },
  });

  useEffect(() => {
    if (open) {
      setErroServidor(null);
      form.reset({
        atendimento_id: atendimentoId,
        novos_sintomas: [],
        escala_dor: 0,
        queixa_adicional: "",
      });
    }
  }, [open, atendimentoId, form]);

  const { mutate: comunicarPiora, isPending } = useComunicarPiora({
    onSuccess: (data) => {
      onOpenChange(false);
      if (data.alerta_samu_disparado || data.redirecionado_emergencia) {
        onEmergenciaSamu(data.instrucoes);
      } else {
        onReclassificado({
          novaPrioridade: data.prioridade_clinica,
          novaPosicao: data.nova_posicao,
          instrucoes: data.instrucoes,
        });
      }
    },
    onError: (err) => {
      setErroServidor(
        err.detail || err.message || "Erro ao comunicar piora clínica. Tente novamente.",
      );
    },
  });

  const sintomasSelecionados = form.watch("novos_sintomas") ?? [];
  const escalaDor = form.watch("escala_dor") ?? 0;

  const toggleSintoma = (id: string) => {
    const atuais = form.getValues("novos_sintomas") ?? [];
    const proximos = atuais.includes(id) ? atuais.filter((item) => item !== id) : [...atuais, id];
    form.setValue("novos_sintomas", proximos, { shouldValidate: true, shouldDirty: true });
  };

  const onSubmit = (values: PioraClinicaFormData) => {
    setErroServidor(null);
    comunicarPiora({
      token,
      body: {
        ...values,
        queixa_adicional: values.queixa_adicional.trim(),
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

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4 pt-2">
            {erroServidor && (
              <div
                role="alert"
                className="p-3 bg-destructive/10 text-destructive rounded-lg text-xs font-medium border border-destructive/20"
              >
                {erroServidor}
              </div>
            )}

            <fieldset className="space-y-2 border-0 p-0 m-0">
              <legend className="text-xs font-bold text-foreground block">
                Sinais de Alerta ou Novos Sintomas
              </legend>
              <div className="space-y-2 pt-1">
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
            </fieldset>

            <FormField
              control={form.control}
              name="escala_dor"
              render={({ field }) => (
                <FormItem className="space-y-1.5">
                  <div className="flex justify-between items-center">
                    <FormLabel htmlFor="piora-escala-dor" className="text-xs font-bold">
                      Intensidade da Dor Atual (0 a 10)
                    </FormLabel>
                    <span className="text-xs font-extrabold text-primary px-2 py-0.5 bg-primary/10 rounded">
                      Nível {escalaDor}
                    </span>
                  </div>
                  <FormControl>
                    <input
                      id="piora-escala-dor"
                      type="range"
                      min="0"
                      max="10"
                      name={field.name}
                      ref={field.ref}
                      value={field.value}
                      onBlur={field.onBlur}
                      onChange={(e) => field.onChange(Number.parseInt(e.target.value, 10))}
                      className="w-full accent-primary cursor-pointer h-2 bg-muted rounded-lg"
                    />
                  </FormControl>
                  <div className="flex justify-between text-[10px] text-muted-foreground px-1">
                    <span>0 (Sem dor)</span>
                    <span>5 (Moderada)</span>
                    <span>10 (Insuportável)</span>
                  </div>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="queixa_adicional"
              render={({ field }) => (
                <FormItem className="space-y-1.5">
                  <FormLabel htmlFor="piora-queixa" className="text-xs font-bold">
                    Descreva com suas palavras o que piorou
                  </FormLabel>
                  <FormControl>
                    <textarea
                      id="piora-queixa"
                      rows={3}
                      placeholder="Exemplo: Comecei a suar frio e a dor se espalhou…"
                      maxLength={2000}
                      className="w-full text-xs p-2.5 rounded-lg border border-input bg-background text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

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
        </Form>
      </DialogContent>
    </Dialog>
  );
}
