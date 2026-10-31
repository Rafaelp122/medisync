import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { extractProblemDetail } from "@/api/errors";
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
import { mascararCEP } from "@/lib/validators";
import { useEnrichmentFase2 } from "../api/use-enrichment-fase2";
import { useViaCep } from "../api/use-via-cep";
import { type EnrichmentFase2FormData, enrichmentFase2Schema } from "../schemas/onboarding-schema";

export const ALERGIAS_COMUNS = [
  "Não possuo alergias",
  "Dipirona",
  "Penicilina / Amoxicilina",
  "AINEs (Ibuprofeno/AAS)",
  "Sulfa",
  "Contraste iodado",
];

export interface EnriquecimentoFase2FormProps {
  pacienteId: string;
  token?: string;
  onConcluido: () => void;
  onPular?: () => void;
}

export function EnriquecimentoFase2Form({
  pacienteId,
  token,
  onConcluido,
  onPular,
}: EnriquecimentoFase2FormProps) {
  const [alergiasSelecionadas, setAlergiasSelecionadas] = useState<string[]>([]);
  const [erroGeral, setErroGeral] = useState<string | null>(null);

  const enrichmentMutation = useEnrichmentFase2();

  const form = useForm<EnriquecimentoFase2FormData>({
    resolver: zodResolver(enrichmentFase2Schema),
    defaultValues: {
      paciente_id: pacienteId,
      nome_mae: "",
      sexo_biologico: "F",
      cep: "",
      logradouro: "",
      numero: "",
      bairro: "",
      cidade: "",
      estado: "",
      nome_social: "",
      alergias: [],
    },
  });

  const cepDigitado = form.watch("cep");
  const {
    endereco: enderecoViaCep,
    isLoading: buscandoCep,
    erro: erroCep,
  } = useViaCep(cepDigitado);

  useEffect(() => {
    if (enderecoViaCep) {
      if (enderecoViaCep.logradouro) {
        form.setValue("logradouro", enderecoViaCep.logradouro, { shouldValidate: true });
      }
      if (enderecoViaCep.bairro) {
        form.setValue("bairro", enderecoViaCep.bairro, { shouldValidate: true });
      }
      if (enderecoViaCep.cidade) {
        form.setValue("cidade", enderecoViaCep.cidade, { shouldValidate: true });
      }
      if (enderecoViaCep.estado) {
        form.setValue("estado", enderecoViaCep.estado, { shouldValidate: true });
      }
    }
  }, [enderecoViaCep, form]);

  const toggleAlergia = (alergia: string) => {
    if (alergia === "Não possuo alergias") {
      setAlergiasSelecionadas(["Não possuo alergias"]);
      return;
    }

    setAlergiasSelecionadas((prev) => {
      const semNenhuma = prev.filter((a) => a !== "Não possuo alergias");
      if (semNenhuma.includes(alergia)) {
        return semNenhuma.filter((a) => a !== alergia);
      }
      return [...semNenhuma, alergia];
    });
  };

  const onSubmit = async (values: EnrichmentFase2FormData) => {
    setErroGeral(null);

    try {
      await enrichmentMutation.mutateAsync({
        body: {
          ...values,
          paciente_id: pacienteId,
          alergias: alergiasSelecionadas.filter((a) => a !== "Não possuo alergias"),
        },
        token,
      });

      onConcluido();
    } catch (err: unknown) {
      setErroGeral(extractProblemDetail(err, "Erro ao salvar enriquecimento cadastral."));
    }
  };

  const isSubmitting = enrichmentMutation.isPending;

  return (
    <Card className="w-full max-w-xl mx-auto shadow-md">
      <CardHeader className="space-y-1">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-emerald-600">
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
        {erroGeral && (
          <Alert variant="destructive" className="mb-4">
            <AlertTitle>Erro ao salvar dados</AlertTitle>
            <AlertDescription>{erroGeral}</AlertDescription>
          </Alert>
        )}

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            {/* Nome da Mãe */}
            <FormField
              control={form.control}
              name="nome_mae"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Nome Completo da Mãe</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="Ex: Maria Aparecida Santos Silva"
                      disabled={isSubmitting}
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

            {/* Sexo Biológico */}
            <FormField
              control={form.control}
              name="sexo_biologico"
              render={({ field }) => (
                <FormItem className="space-y-1">
                  <FormLabel>Sexo Biológico (Atribuído no Nascimento)</FormLabel>
                  <FormControl>
                    <div className="flex gap-3">
                      <label className="flex items-center gap-2 text-sm font-medium cursor-pointer">
                        <input
                          type="radio"
                          name="sexo_biologico"
                          value="F"
                          checked={field.value === "F"}
                          onChange={() => field.onChange("F")}
                          disabled={isSubmitting}
                          className="h-4 w-4 text-primary focus:ring-primary"
                        />
                        Feminino
                      </label>
                      <label className="flex items-center gap-2 text-sm font-medium cursor-pointer">
                        <input
                          type="radio"
                          name="sexo_biologico"
                          value="M"
                          checked={field.value === "M"}
                          onChange={() => field.onChange("M")}
                          disabled={isSubmitting}
                          className="h-4 w-4 text-primary focus:ring-primary"
                        />
                        Masculino
                      </label>
                    </div>
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* Endereço: CEP com busca automática */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <FormField
                control={form.control}
                name="cep"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      CEP{" "}
                      {buscandoCep && (
                        <span className="text-xs text-primary font-normal">(Buscando...)</span>
                      )}
                    </FormLabel>
                    <FormControl>
                      <Input
                        placeholder="00000-000"
                        disabled={isSubmitting}
                        value={field.value}
                        onChange={(e) => field.onChange(mascararCEP(e.target.value))}
                      />
                    </FormControl>
                    {erroCep && <p className="text-xs text-amber-600 font-medium">{erroCep}</p>}
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="sm:col-span-2">
                <FormField
                  control={form.control}
                  name="logradouro"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Logradouro / Rua</FormLabel>
                      <FormControl>
                        <Input placeholder="Ex: Av. Paulista" disabled={isSubmitting} {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <FormField
                control={form.control}
                name="numero"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Número</FormLabel>
                    <FormControl>
                      <Input placeholder="1000" disabled={isSubmitting} {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="bairro"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Bairro</FormLabel>
                    <FormControl>
                      <Input placeholder="Bela Vista" disabled={isSubmitting} {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="cidade"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Cidade</FormLabel>
                    <FormControl>
                      <Input placeholder="São Paulo" disabled={isSubmitting} {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="estado"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>UF</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="SP"
                        maxLength={2}
                        disabled={isSubmitting}
                        value={field.value}
                        onChange={(e) => field.onChange(e.target.value.toUpperCase())}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            {/* Nome Social (Opcional) */}
            <FormField
              control={form.control}
              name="nome_social"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Nome Social (Opcional)</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="Como prefere ser chamado(a)"
                      disabled={isSubmitting}
                      value={field.value || ""}
                      onChange={field.onChange}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* Alergias Medicamentosas */}
            <div className="space-y-2">
              <FormLabel>Alergias Medicamentosas Conhecidas</FormLabel>
              <div className="flex flex-wrap gap-1.5">
                {ALERGIAS_COMUNS.map((alergia) => {
                  const ativa = alergiasSelecionadas.includes(alergia);
                  return (
                    <button
                      key={alergia}
                      type="button"
                      aria-pressed={ativa}
                      onClick={() => toggleAlergia(alergia)}
                      className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${ativa ? "bg-primary text-primary-foreground border-primary font-medium" : "bg-background text-foreground hover:bg-muted border-border"}`}
                    >
                      {alergia}
                    </button>
                  );
                })}
              </div>
            </div>

            <Button type="submit" size="lg" disabled={isSubmitting} className="w-full font-bold">
              {isSubmitting ? "Salvando Dados..." : "Concluir Enriquecimento"}
            </Button>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}
