import type { Control } from "react-hook-form";
import { Button } from "@/components/ui/button";
import { FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { mascararTelefoneBR } from "@/lib/validators";
import type { IntakeFase1UiInputData } from "../schemas/onboarding-schema";
import { DocumentoIdentificacaoField } from "./documento-identificacao-field";

export interface TriageIdentificationStepProps {
  control: Control<IntakeFase1UiInputData>;
  tipoDoc: "cpf" | "cns";
  isSubmitting: boolean;
  onAlternarParaCpf: () => void;
  onAlternarParaCns: () => void;
  onAvancar: () => void;
}

/**
 * Etapa 1 do Acolhimento Walk-In (<130L): identificação civil mínima + nome social opcional.
 * Propaga `{...field}` antes de `onChange` nos inputs mascarados para preservar `onBlur` e `ref`.
 * @see docs/user-stories/US-01-acolhimento-triagem-tcle.md
 */
export function TriageIdentificationStep({
  control,
  tipoDoc,
  isSubmitting,
  onAlternarParaCpf,
  onAlternarParaCns,
  onAvancar,
}: TriageIdentificationStepProps) {
  return (
    <div className="space-y-4">
      <FormField
        control={control}
        name="nome_completo"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Nome Completo</FormLabel>
            <FormControl>
              <Input
                placeholder="Ex: Juliana Santos Silva…"
                autoComplete="name"
                spellCheck={false}
                disabled={isSubmitting}
                {...field}
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={control}
        name="nome_social"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Nome Social (Opcional)</FormLabel>
            <FormControl>
              <Input
                placeholder="Como prefere ser chamado(a)…"
                autoComplete="nickname"
                spellCheck={false}
                disabled={isSubmitting}
                {...field}
                value={field.value ?? ""}
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <FormField
          control={control}
          name="data_nascimento"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Data de Nascimento</FormLabel>
              <FormControl>
                <Input type="date" autoComplete="bday" disabled={isSubmitting} {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={control}
          name="telefone"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Telefone Celular com DDD</FormLabel>
              <FormControl>
                <Input
                  placeholder="(11) 98765-4321…"
                  type="tel"
                  inputMode="tel"
                  autoComplete="tel-national"
                  spellCheck={false}
                  disabled={isSubmitting}
                  {...field}
                  onChange={(e) => field.onChange(mascararTelefoneBR(e.target.value))}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      </div>

      <DocumentoIdentificacaoField
        control={control}
        tipoDoc={tipoDoc}
        isSubmitting={isSubmitting}
        onAlternarParaCpf={onAlternarParaCpf}
        onAlternarParaCns={onAlternarParaCns}
      />

      <Button
        type="button"
        size="lg"
        onClick={onAvancar}
        className="w-full font-bold text-base h-11 mt-2"
      >
        Continuar para Triagem →
      </Button>
    </div>
  );
}
