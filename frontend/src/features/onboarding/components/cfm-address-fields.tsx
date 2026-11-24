import type { Control } from "react-hook-form";
import { FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { mascararCEP } from "@/lib/validators";
import type { EnrichmentFase2InputFormData } from "../schemas/onboarding-schema";

export interface CfmAddressFieldsProps {
  control: Control<EnrichmentFase2InputFormData>;
  isSubmitting: boolean;
  buscandoCep: boolean;
  erroCep: string | null;
}

/**
 * Campos de endereço CFM 1.821/2007 com autopreenchimento ViaCEP e propagação de `{...field}`
 * antes de `onChange` nos inputs mascarados (`cep`, `estado`) para preservar `onBlur` e `ref`.
 * @see docs/user-stories/US-03-elegibilidade-onboarding-fase2.md
 */
export function CfmAddressFields({
  control,
  isSubmitting,
  buscandoCep,
  erroCep,
}: CfmAddressFieldsProps) {
  return (
    <>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <FormField
          control={control}
          name="cep"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                CEP{" "}
                {buscandoCep && (
                  <span
                    role="status"
                    aria-live="polite"
                    className="text-xs text-primary font-normal"
                  >
                    (Buscando…)
                  </span>
                )}
              </FormLabel>
              <FormControl>
                <Input
                  type="text"
                  inputMode="numeric"
                  autoComplete="postal-code"
                  spellCheck={false}
                  placeholder="00000-000…"
                  disabled={isSubmitting}
                  {...field}
                  value={field.value ?? ""}
                  onChange={(e) => field.onChange(mascararCEP(e.target.value))}
                />
              </FormControl>
              {erroCep && (
                <p
                  role="status"
                  aria-live="polite"
                  className="text-xs text-amber-800 dark:text-amber-200 font-medium"
                >
                  {erroCep}
                </p>
              )}
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="sm:col-span-2">
          <FormField
            control={control}
            name="logradouro"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Logradouro / Rua</FormLabel>
                <FormControl>
                  <Input
                    placeholder="Ex: Av. Paulista…"
                    autoComplete="street-address"
                    disabled={isSubmitting}
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <FormField
          control={control}
          name="numero"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Número</FormLabel>
              <FormControl>
                <Input
                  placeholder="1000…"
                  autoComplete="address-line2"
                  inputMode="numeric"
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
          name="bairro"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Bairro</FormLabel>
              <FormControl>
                <Input
                  placeholder="Bela Vista…"
                  autoComplete="address-level3"
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
          name="cidade"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Cidade</FormLabel>
              <FormControl>
                <Input
                  placeholder="São Paulo…"
                  autoComplete="address-level2"
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
          name="estado"
          render={({ field }) => (
            <FormItem>
              <FormLabel>UF</FormLabel>
              <FormControl>
                <Input
                  placeholder="SP…"
                  autoComplete="address-level1"
                  spellCheck={false}
                  maxLength={2}
                  disabled={isSubmitting}
                  {...field}
                  value={field.value ?? ""}
                  onChange={(e) => field.onChange(e.target.value.toUpperCase())}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      </div>
    </>
  );
}
