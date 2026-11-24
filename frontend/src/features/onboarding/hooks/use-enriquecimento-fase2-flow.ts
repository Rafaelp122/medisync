import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { extractProblemDetail } from "@/api/errors";
import { useEnrichmentFase2 } from "../api/use-enrichment-fase2";
import { useViaCepQuery } from "../api/use-via-cep";
import {
  type EnrichmentFase2FormData,
  type EnrichmentFase2InputFormData,
  enrichmentFase2Schema,
} from "../schemas/onboarding-schema";

/**
 * Hook headless do Enriquecimento Cadastral (Fase 2 - CFM 1.821/2007) + ViaCEP `useViaCepQuery`.
 */
export function useEnriquecimentoFase2Flow(params: {
  pacienteId: string;
  token?: string;
  onConcluido: () => void;
}) {
  const { pacienteId, token, onConcluido } = params;
  const [alergiasSelecionadas, setAlergiasSelecionadas] = useState<string[]>([]);
  const [erroGeral, setErroGeral] = useState<string | null>(null);
  const enrichmentMutation = useEnrichmentFase2();

  const form = useForm<EnrichmentFase2InputFormData, unknown, EnrichmentFase2FormData>({
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
  } = useViaCepQuery(cepDigitado);

  useEffect(() => {
    if (!enderecoViaCep) return;
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
  }, [enderecoViaCep, form]);

  const toggleAlergia = (alergia: string) => {
    if (alergia === "Não possuo alergias") {
      setAlergiasSelecionadas(["Não possuo alergias"]);
      return;
    }
    setAlergiasSelecionadas((prev) => {
      const semNenhuma = prev.filter((a) => a !== "Não possuo alergias");
      return semNenhuma.includes(alergia)
        ? semNenhuma.filter((a) => a !== alergia)
        : [...semNenhuma, alergia];
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

  return {
    form,
    alergiasSelecionadas,
    toggleAlergia,
    erroGeral,
    buscandoCep,
    erroCep,
    isSubmitting: enrichmentMutation.isPending,
    onSubmit,
  };
}
