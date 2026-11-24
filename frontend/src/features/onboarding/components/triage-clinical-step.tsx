import { Loader2 } from "lucide-react";
import type { Control, FieldPath } from "react-hook-form";
import { Button } from "@/components/ui/button";
import { FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PainScaleSelector } from "./pain-scale-selector";

export const SINTOMAS_COMUNS = [
  { id: "febre", label: "Febre" },
  { id: "cefaleia", label: "Dor de cabeça" },
  { id: "tosse", label: "Tosse" },
  { id: "coriza", label: "Coriza / Congestão" },
  { id: "dor_de_garganta", label: "Dor de garganta" },
  { id: "nausea_vomito", label: "Náusea ou vômitos" },
  { id: "diarreia", label: "Diarreia" },
  { id: "mialgia", label: "Dores no corpo" },
];

export const SINAIS_ALARME_CRITICOS = [
  { id: "dor_toracica_irradiada", label: "Dor no peito irradiando para o braço ou pescoço" },
  { id: "inconsciencia", label: "Desmaio ou perda de consciência" },
  { id: "dispneia_grave", label: "Falta de ar severa / sensação de asfixia" },
  { id: "convulsao_em_curso", label: "Crise convulsiva em andamento" },
  { id: "hemorragia_grave", label: "Hemorragia abundante que não estanca" },
  { id: "anafilaxia", label: "Reação alérgica com inchaço nos lábios ou glote" },
];

export interface TriageClinicalFieldShape {
  queixa_principal: string;
  aceite_tcle: boolean;
}

export interface TriageClinicalStepProps<TFieldValues extends TriageClinicalFieldShape> {
  control: Control<TFieldValues>;
  sintomasSelecionados: string[];
  escalaDor: number;
  tcleAceito: boolean;
  isSubmitting: boolean;
  onToggleSintoma: (sintomaId: string, isCritico?: boolean) => void;
  onEscalaDorChange: (valor: number) => void;
  onTcleChange: (checked: boolean) => void;
  onAbrirTcle: () => void;
  onVoltar?: () => void;
}

/**
 * Etapa clínica compartilhada de Triagem (queixa, sintomas, red flags SAMU, dor EVA e TCLE).
 * Reutilizada pelo fluxo autenticado via JWT e pelo acolhimento walk-in.
 * @see docs/user-stories/US-01-acolhimento-triagem-tcle.md
 */
export function TriageClinicalStep<TFieldValues extends TriageClinicalFieldShape>({
  control,
  sintomasSelecionados,
  escalaDor,
  tcleAceito,
  isSubmitting,
  onToggleSintoma,
  onEscalaDorChange,
  onTcleChange,
  onAbrirTcle,
  onVoltar,
}: TriageClinicalStepProps<TFieldValues>) {
  return (
    <div className="space-y-4">
      <FormField
        control={control}
        name={"queixa_principal" as FieldPath<TFieldValues>}
        render={({ field }) => (
          <FormItem>
            <FormLabel>O que você está sentindo? (Queixa Principal)</FormLabel>
            <FormControl>
              <Input
                placeholder="Ex: Febre alta há 2 dias com dor no corpo…"
                disabled={isSubmitting}
                {...field}
                value={typeof field.value === "string" ? field.value : ""}
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <div className="space-y-1.5">
        <Label className="text-xs text-muted-foreground">Sintomas comuns:</Label>
        <div className="flex flex-wrap gap-1.5">
          {SINTOMAS_COMUNS.map((s) => {
            const ativo = sintomasSelecionados.includes(s.id);
            return (
              <button
                key={s.id}
                type="button"
                aria-pressed={ativo}
                onClick={() => onToggleSintoma(s.id)}
                className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${ativo ? "bg-primary text-primary-foreground border-primary font-medium" : "bg-background text-foreground hover:bg-muted border-border"}`}
              >
                {s.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 space-y-2">
        <p className="text-xs font-semibold text-amber-800 dark:text-amber-300 flex items-center gap-1.5">
          <span aria-hidden="true">⚠️</span> Sintomas graves exigem socorro imediato
        </p>
        <p className="text-[11px] text-muted-foreground leading-snug">
          Se você apresenta dor forte no peito, falta de ar severa ou desmaio, não aguarde
          teleconsulta. Toque abaixo para socorro direto:
        </p>
        <div className="flex flex-wrap gap-1.5 pt-1">
          {SINAIS_ALARME_CRITICOS.map((critico) => (
            <button
              key={critico.id}
              type="button"
              onClick={() => onToggleSintoma(critico.id, true)}
              className="text-[11px] px-2.5 py-1 rounded-md border border-destructive/40 bg-background text-destructive hover:bg-destructive/10 text-left font-medium transition-colors"
            >
              {critico.label}
            </button>
          ))}
        </div>
      </div>

      <div className="pt-1">
        <PainScaleSelector value={escalaDor} onChange={onEscalaDorChange} />
      </div>

      <div className="rounded-lg border p-3 bg-muted/20 space-y-2">
        <div className="flex items-start gap-2.5">
          <input
            id="tcle_consentimento"
            type="checkbox"
            aria-label="Concordo com o Termo de Consentimento Livre e Esclarecido (TCLE)"
            checked={tcleAceito}
            onChange={(e) => onTcleChange(e.target.checked)}
            className="mt-1 h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary cursor-pointer"
            disabled={isSubmitting}
          />
          <div className="text-xs leading-relaxed text-foreground select-none">
            <label htmlFor="tcle_consentimento" className="cursor-pointer">
              Li e concordo com os termos do{" "}
            </label>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onAbrirTcle();
              }}
              className="font-semibold text-primary underline underline-offset-2 hover:opacity-80"
            >
              Termo de Consentimento Livre e Esclarecido (TCLE)
            </button>
            <label htmlFor="tcle_consentimento" className="cursor-pointer">
              , autorizando a realização da teleconsulta e o tratamento dos meus dados clínicos
              (LGPD Art. 11 e CFM 2.314/2022).
            </label>
          </div>
        </div>
        <p className="text-[11px] text-muted-foreground pl-6">
          O aceite gera um hash forense SHA-256 anexado de forma imutável ao seu prontuário.
        </p>
      </div>

      <div className="flex items-center gap-3 pt-2">
        {onVoltar && (
          <Button
            type="button"
            variant="outline"
            onClick={onVoltar}
            disabled={isSubmitting}
            className="w-1/3 h-11"
          >
            ← Voltar
          </Button>
        )}
        <Button
          type="submit"
          size="lg"
          disabled={!tcleAceito || isSubmitting}
          aria-busy={isSubmitting}
          className={`${onVoltar ? "w-2/3" : "w-full"} font-bold text-base h-11`}
        >
          {isSubmitting ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
              Avaliando e Ingressando…
            </>
          ) : (
            "Entrar na Fila Virtual"
          )}
        </Button>
      </div>
    </div>
  );
}
