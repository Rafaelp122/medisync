import { Loader2 } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { useEnriquecimentoFase2Flow } from "../hooks/use-enriquecimento-fase2-flow";
import { ALERGIAS_COMUNS, AllergyChipSelector } from "./allergy-chip-selector";
import { CfmAddressFields } from "./cfm-address-fields";
import { SexoBiologicoFieldset } from "./sexo-biologico-fieldset";

export { ALERGIAS_COMUNS };

export interface EnriquecimentoFase2FormProps {
  pacienteId: string;
  token?: string;
  onConcluido: () => void;
  onPular?: () => void;
}

/**
 * Formulário de Enriquecimento Cadastral CFM 1.821/2007 (<160L via `useEnriquecimentoFase2Flow`).
 * @see docs/user-stories/US-03-elegibilidade-onboarding-fase2.md
 */
export function EnriquecimentoFase2Form({
  pacienteId,
  token,
  onConcluido,
  onPular,
}: EnriquecimentoFase2FormProps) {
  const flow = useEnriquecimentoFase2Flow({ pacienteId, token, onConcluido });

  return (
    <Card className="w-full max-w-xl mx-auto shadow-md">
      <CardHeader className="space-y-1">
        <div className="flex items-center justify-between">
          <span className="inline-flex items-center rounded-full bg-acr-green px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wider text-acr-green-foreground">
            Você já está na fila &bull; Fase 2
          </span>
          {onPular && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onPular}
              className="text-xs text-muted-foreground"
            >
              Completar mais tarde
            </Button>
          )}
        </div>
        <CardTitle className="text-xl font-bold">Completar Prontuário Regulatório</CardTitle>
        <CardDescription>
          Exigência da Resolução CFM nº 1.821/2007. Seu lugar na fila virtual está garantido
          enquanto você preenche.
        </CardDescription>
      </CardHeader>

      <CardContent>
        {flow.erroGeral && (
          <Alert variant="destructive" className="mb-4">
            <AlertTitle>Erro ao salvar dados</AlertTitle>
            <AlertDescription>{flow.erroGeral}</AlertDescription>
          </Alert>
        )}

        <Form {...flow.form}>
          <form onSubmit={flow.form.handleSubmit(flow.onSubmit)} className="space-y-4">
            <FormField
              control={flow.form.control}
              name="nome_mae"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Nome Completo da Mãe</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="Ex: Maria Aparecida Santos Silva…"
                      spellCheck={false}
                      autoComplete="off"
                      disabled={flow.isSubmitting}
                      {...field}
                    />
                  </FormControl>
                  <FormDescription className="text-xs">
                    Obrigatório para conformidade de prontuário e identificação civil inequívoca.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <SexoBiologicoFieldset control={flow.form.control} isSubmitting={flow.isSubmitting} />

            <CfmAddressFields
              control={flow.form.control}
              isSubmitting={flow.isSubmitting}
              buscandoCep={flow.buscandoCep}
              erroCep={flow.erroCep}
            />

            <FormField
              control={flow.form.control}
              name="nome_social"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Nome Social (Opcional)</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="Como prefere ser chamado(a)…"
                      autoComplete="nickname"
                      spellCheck={false}
                      disabled={flow.isSubmitting}
                      {...field}
                      value={field.value ?? ""}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <AllergyChipSelector
              selected={flow.alergiasSelecionadas}
              onToggle={flow.toggleAlergia}
            />

            <Button
              type="submit"
              size="lg"
              disabled={flow.isSubmitting}
              aria-busy={flow.isSubmitting}
              className="w-full font-bold"
            >
              {flow.isSubmitting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
                  Salvando Dados…
                </>
              ) : (
                "Concluir Enriquecimento"
              )}
            </Button>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}
