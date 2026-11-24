import type { Control } from "react-hook-form";
import { FormField, FormItem, FormMessage } from "@/components/ui/form";
import type { EnrichmentFase2InputFormData } from "../schemas/onboarding-schema";

export interface SexoBiologicoFieldsetProps {
  control: Control<EnrichmentFase2InputFormData>;
  isSubmitting: boolean;
}

/**
 * Grupo acessível `<fieldset>`/`<legend>` de Sexo Biológico conforme WCAG 2.1 AA 1.3.1/4.1.2.
 */
export function SexoBiologicoFieldset({ control, isSubmitting }: SexoBiologicoFieldsetProps) {
  return (
    <FormField
      control={control}
      name="sexo_biologico"
      render={({ field }) => (
        <FormItem className="space-y-1">
          <fieldset className="space-y-1.5 border-0 p-0 m-0">
            <legend className="text-sm font-medium leading-none">
              Sexo Biológico (Atribuído no Nascimento)
            </legend>
            <div className="flex gap-3 pt-1">
              <label className="flex items-center gap-2 text-sm font-medium cursor-pointer">
                <input
                  type="radio"
                  name={field.name}
                  value="F"
                  checked={field.value === "F"}
                  onChange={() => field.onChange("F")}
                  onBlur={field.onBlur}
                  disabled={isSubmitting}
                  className="h-4 w-4 text-primary focus:ring-primary"
                />
                Feminino
              </label>
              <label className="flex items-center gap-2 text-sm font-medium cursor-pointer">
                <input
                  type="radio"
                  name={field.name}
                  value="M"
                  checked={field.value === "M"}
                  onChange={() => field.onChange("M")}
                  onBlur={field.onBlur}
                  disabled={isSubmitting}
                  className="h-4 w-4 text-primary focus:ring-primary"
                />
                Masculino
              </label>
            </div>
          </fieldset>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
