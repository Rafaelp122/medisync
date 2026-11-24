import type { FieldErrors, UseFormRegister } from "react-hook-form";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type {
  ConfigPlantaoFormData,
  ConfigPlantaoInputFormData,
} from "../../schemas/telemetry-schema";

const SLA_CAMPOS = [
  { name: "sla_minutos_nivel_1", label: "SLA Nível 1 · Emergência (min)" },
  { name: "sla_minutos_nivel_2", label: "SLA Nível 2 · Muito Urgente (min)" },
  { name: "sla_minutos_nivel_3", label: "SLA Nível 3 · Urgente (min)" },
  { name: "sla_minutos_nivel_4", label: "SLA Nível 4 · Pouco Urgente (min)" },
  { name: "sla_minutos_nivel_5", label: "SLA Nível 5 · Não Urgente (min)" },
] as const;

export interface ConfigPlantaoSlaFieldsProps {
  register: UseFormRegister<ConfigPlantaoInputFormData>;
  errors: FieldErrors<ConfigPlantaoFormData>;
}

/**
 * Grade de inputs das metas de SLA por prioridade clínica ACR SUS (minutos).
 */
export function ConfigPlantaoSlaFields({ register, errors }: ConfigPlantaoSlaFieldsProps) {
  return (
    <fieldset className="space-y-2.5 rounded-lg border border-border/70 p-3">
      <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Metas de SLA por Classificação ACR SUS (minutos)
      </legend>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {SLA_CAMPOS.map(({ name, label }) => {
          const fieldError = errors[name];
          return (
            <div key={name} className="space-y-1">
              <Label htmlFor={name} className="text-xs">
                {label}
              </Label>
              <Input id={name} type="number" min={0} {...register(name, { valueAsNumber: true })} />
              {fieldError && (
                <p className="text-xs text-destructive" role="alert">
                  {fieldError.message}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </fieldset>
  );
}
