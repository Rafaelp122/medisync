import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { type UseFormReturn, useForm } from "react-hook-form";
import { getHumanizedErrorMessage, type HumanizedError, isProblemDetailsError } from "@/api/errors";
import type { AdmissaoResponse } from "@/api/generated/types.gen";
import { isThreePartJwt, type StoredPatientSession } from "@/lib/session-storage";
import { calcularHashTcle } from "@/lib/validators";
import { useAdmitirPaciente } from "../api/use-admitir-paciente";
import { TEXTO_TCLE_PADRAO } from "../components/tcle-dialog";
import {
  admissaoSchema,
  type ClinicalTriageFormData,
  type ClinicalTriageInputFormData,
  clinicalTriageFormSchema,
} from "../schemas/onboarding-schema";

export type AcolhimentoTriagemStep = "clinical" | "samu_redirect" | "enrichment";

export interface UseAcolhimentoTriagemFlowResult {
  form: UseFormReturn<ClinicalTriageInputFormData, unknown, ClinicalTriageFormData>;
  step: AcolhimentoTriagemStep;
  submitTriagem: () => Promise<void>;
  isSubmitting: boolean;
  samuOrientacoes: string | null;
  samuModalOpen: boolean;
  setSamuModalOpen: (open: boolean) => void;
  sintomaAcidental: string | null;
  erroHumanizado: HumanizedError | null;
  selecionarSintoma: (sintomaId: string, isCritico?: boolean) => void;
  corrigirSintomaAcidental: () => void;
  confirmarSaidaSamu: () => void;
  reiniciarTriagem: () => void;
  hasAuthenticatedJwt: boolean;
  admissaoConcluida: AdmissaoResponse | null;
}

/**
 * Hook headless de Triagem Clínica para cidadãos já autenticados (JWT 3-partes).
 * Reutiliza pacienteId e token sem invocar /onboarding/fase-1, calcula hash SHA-256
 * WebCrypto do TCLE sob validação Zod e trata HTTP 422 EMERGENCIA_CRITICA_SAMU_192.
 *
 * Regras: RF-01, RN04, US-01, ADR-011.
 * @see docs/user-stories/US-01-acolhimento-triagem-tcle.md
 */
export function useAcolhimentoTriagemFlow(params: {
  session: StoredPatientSession | null;
  onAdmitted: (data: AdmissaoResponse) => void;
}): UseAcolhimentoTriagemFlowResult {
  const { session, onAdmitted } = params;
  const hasAuthenticatedJwt = Boolean(session?.pacienteId && isThreePartJwt(session?.token));

  const [step, setStep] = useState<AcolhimentoTriagemStep>("clinical");
  const [samuModalOpen, setSamuModalOpen] = useState(false);
  const [samuOrientacoes, setSamuOrientacoes] = useState<string | null>(null);
  const [sintomaAcidental, setSintomaAcidental] = useState<string | null>(null);
  const [erroHumanizado, setErroHumanizado] = useState<HumanizedError | null>(null);
  const [admissaoConcluida, setAdmissaoConcluida] = useState<AdmissaoResponse | null>(null);

  const admitirMutation = useAdmitirPaciente();

  const form = useForm<ClinicalTriageInputFormData, unknown, ClinicalTriageFormData>({
    resolver: zodResolver(clinicalTriageFormSchema),
    defaultValues: {
      queixa_principal: "",
      sintomas: [],
      escala_dor: 0,
      aceite_tcle: false,
    },
  });

  const selecionarSintoma = (sintomaId: string, isCritico = false) => {
    if (isCritico) {
      setSintomaAcidental(sintomaId);
      setSamuModalOpen(true);
      return;
    }

    const atuais = form.getValues("sintomas") ?? [];
    const proximos = atuais.includes(sintomaId)
      ? atuais.filter((item) => item !== sintomaId)
      : [...atuais, sintomaId];
    form.setValue("sintomas", proximos, { shouldDirty: true });
  };

  const corrigirSintomaAcidental = () => {
    setSintomaAcidental(null);
    setSamuModalOpen(false);
  };

  const confirmarSaidaSamu = () => {
    setSamuModalOpen(false);
    setStep("samu_redirect");
  };

  const reiniciarTriagem = () => {
    form.reset({
      queixa_principal: "",
      sintomas: [],
      escala_dor: 0,
      aceite_tcle: false,
    });
    setSintomaAcidental(null);
    setSamuOrientacoes(null);
    setSamuModalOpen(false);
    setErroHumanizado(null);
    setAdmissaoConcluida(null);
    setStep("clinical");
  };

  const submitTriagem = async (): Promise<void> => {
    await form.handleSubmit(async (values) => {
      if (!session?.pacienteId || !session?.token) {
        setErroHumanizado({
          title: "Sessão inválida para triagem",
          detail: "Faça login novamente no Portal do Cidadão antes de ingressar na fila.",
          retryable: false,
        });
        return;
      }

      setErroHumanizado(null);

      try {
        const hashTcle = await calcularHashTcle(TEXTO_TCLE_PADRAO);
        const payload = admissaoSchema.parse({
          paciente_id: session.pacienteId,
          queixa_principal: values.queixa_principal,
          sintomas: values.sintomas,
          escala_dor: values.escala_dor,
          tcle_texto: TEXTO_TCLE_PADRAO,
          tcle_hash: hashTcle,
        });

        const admissaoRes = await admitirMutation.mutateAsync({
          body: payload,
          token: session.token,
        });

        if (admissaoRes.alerta_samu_disparado || admissaoRes.prioridade_clinica === 1) {
          setSamuOrientacoes(admissaoRes.instrucoes || null);
          setSintomaAcidental(null);
          setSamuModalOpen(false);
          setStep("samu_redirect");
          return;
        }

        setAdmissaoConcluida(admissaoRes);
        onAdmitted(admissaoRes);
        setStep("enrichment");
      } catch (err: unknown) {
        if (isProblemDetailsError(err) && err.code === "EMERGENCIA_CRITICA_SAMU_192") {
          setSamuOrientacoes(err.detail || null);
          setSintomaAcidental(null);
          setSamuModalOpen(false);
          setStep("samu_redirect");
          return;
        }
        setErroHumanizado(getHumanizedErrorMessage(err));
      }
    })();
  };

  return {
    form,
    step,
    submitTriagem,
    isSubmitting: admitirMutation.isPending,
    samuOrientacoes,
    samuModalOpen,
    setSamuModalOpen,
    sintomaAcidental,
    erroHumanizado,
    selecionarSintoma,
    corrigirSintomaAcidental,
    confirmarSaidaSamu,
    reiniciarTriagem,
    hasAuthenticatedJwt,
    admissaoConcluida,
  };
}
