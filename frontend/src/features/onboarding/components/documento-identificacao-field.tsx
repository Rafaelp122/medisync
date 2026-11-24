import type { Control } from "react-hook-form";
import { FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { mascararCNS, mascararCPF } from "@/lib/validators";
import type { IntakeFase1UiInputData } from "../schemas/onboarding-schema";

export interface DocumentoIdentificacaoFieldProps {
  control: Control<IntakeFase1UiInputData>;
  tipoDoc: "cpf" | "cns";
  isSubmitting: boolean;
  onAlternarParaCpf: () => void;
  onAlternarParaCns: () => void;
}

/**
 * Alternador e campo mascarado CPF/CNS com `{...field}` antes de `onChange`.
 */
export function DocumentoIdentificacaoField({
  control,
  tipoDoc,
  isSubmitting,
  onAlternarParaCpf,
  onAlternarParaCns,
}: DocumentoIdentificacaoFieldProps) {
  const isCpf = tipoDoc === "cpf";

  return (
    <FormField
      control={control}
      name={isCpf ? "cpf" : "cns"}
      render={({ field }) => (
        <FormItem>
          <div className="flex items-center justify-between">
            <FormLabel>
              {isCpf
                ? "Documento de Identificação (CPF)"
                : "Documento de Identificação (Cartão SUS)"}
            </FormLabel>
            <div className="flex gap-1.5 p-0.5 rounded-lg bg-muted border border-border">
              <button
                type="button"
                aria-pressed={isCpf}
                onClick={onAlternarParaCpf}
                className={`text-xs px-2.5 py-0.5 rounded-md transition-colors ${isCpf ? "font-semibold shadow-xs bg-background text-foreground" : "text-muted-foreground hover:text-foreground"}`}
              >
                CPF
              </button>
              <button
                type="button"
                aria-pressed={!isCpf}
                onClick={onAlternarParaCns}
                className={`text-xs px-2.5 py-0.5 rounded-md transition-colors ${!isCpf ? "font-semibold shadow-xs bg-background text-foreground" : "text-muted-foreground hover:text-foreground"}`}
              >
                Cartão SUS (CNS)
              </button>
            </div>
          </div>
          <FormControl>
            <Input
              type="text"
              inputMode="numeric"
              autoComplete="off"
              spellCheck={false}
              placeholder={isCpf ? "000.000.000-00…" : "000 0000 0000 0000…"}
              disabled={isSubmitting}
              {...field}
              value={field.value ?? ""}
              onChange={(e) =>
                field.onChange(isCpf ? mascararCPF(e.target.value) : mascararCNS(e.target.value))
              }
            />
          </FormControl>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
