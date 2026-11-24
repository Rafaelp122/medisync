import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { getHumanizedErrorMessage, type HumanizedError, isProblemDetailsError } from "@/api/errors";
import { calcularHashTcle } from "@/lib/validators";
import { startSafeViewTransition } from "@/lib/view-transitions";
import { useAdmitirPaciente } from "../api/use-admitir-paciente";
import { useIntakeFase1 } from "../api/use-intake-fase1";
import type { AcolhimentoConcluidoData } from "../components/acolhimento-fase1-form";
import { TEXTO_TCLE_PADRAO } from "../components/tcle-dialog";
import {
  type IntakeFase1UiInputData,
  type IntakeFase1UiOutputData,
  intakeFase1FormSchema,
} from "../schemas/onboarding-schema";

const DEFAULT_IDENTIFICATION_VALUES: IntakeFase1UiInputData = {
  nome_completo: "",
  nome_social: "",
  data_nascimento: "",
  telefone: "",
  cpf: "",
  cns: "",
  queixa_principal: "",
  aceite_tcle: false,
};

/**
 * Hook headless de controle do fluxo walk-in (2 micro-etapas + SAMU 192 + SHA-256 WebCrypto).
 */
export function useWalkinAcolhimentoFlow(
  onAdmissaoConcluida: (data: AcolhimentoConcluidoData) => void,
) {
  const [microEtapa, setMicroEtapa] = useState<"identificacao" | "triagem">("identificacao");
  const [tipoDoc, setTipoDoc] = useState<"cpf" | "cns">("cpf");
  const [sintomasSelecionados, setSintomasSelecionados] = useState<string[]>([]);
  const [sintomaAcidental, setSintomaAcidental] = useState<boolean>(false);
  const [escalaDor, setEscalaDor] = useState<number>(0);
  const [samuModalOpen, setSamuModalOpen] = useState<boolean>(false);
  const [orientacoesSamu, setOrientacoesSamu] = useState<string | null>(null);
  const [erroHumanizado, setErroHumanizado] = useState<HumanizedError | null>(null);
  const [encaminhadoPresencial, setEncaminhadoPresencial] = useState<boolean>(false);

  const intakeMutation = useIntakeFase1();
  const admitirMutation = useAdmitirPaciente();

  const form = useForm<IntakeFase1UiInputData, unknown, IntakeFase1UiOutputData>({
    resolver: zodResolver(intakeFase1FormSchema),
    defaultValues: DEFAULT_IDENTIFICATION_VALUES,
  });

  const alternarParaCpf = () => {
    setTipoDoc("cpf");
    form.setValue("cns", "");
    form.clearErrors("cns");
  };

  const alternarParaCns = () => {
    setTipoDoc("cns");
    form.setValue("cpf", "");
    form.clearErrors("cpf");
  };

  const mudarMicroEtapa = (novaEtapa: "identificacao" | "triagem") => {
    startSafeViewTransition(() => {
      setMicroEtapa(novaEtapa);
    });
  };

  const avancarParaTriagem = async (onInvalid?: () => void) => {
    setErroHumanizado(null);
    const valido = await form.trigger([
      "nome_completo",
      "data_nascimento",
      "telefone",
      tipoDoc === "cpf" ? "cpf" : "cns",
    ]);
    if (valido) {
      mudarMicroEtapa("triagem");
    } else {
      onInvalid?.();
    }
  };

  const toggleSintoma = (sintomaId: string, isCritico = false) => {
    if (isCritico) {
      setSintomaAcidental(true);
      setSamuModalOpen(true);
      return;
    }
    setSintomasSelecionados((prev) =>
      prev.includes(sintomaId) ? prev.filter((s) => s !== sintomaId) : [...prev, sintomaId],
    );
  };

  const submeter = async (values: IntakeFase1UiOutputData, onErrorBanner?: () => void) => {
    setErroHumanizado(null);

    try {
      const hashTcle = await calcularHashTcle(TEXTO_TCLE_PADRAO);
      const intakeRes = await intakeMutation.mutateAsync({
        nome_completo: values.nome_completo,
        data_nascimento: values.data_nascimento,
        telefone: values.telefone,
        cpf: tipoDoc === "cpf" ? values.cpf : undefined,
        cns: tipoDoc === "cns" ? values.cns : undefined,
        nome_social: values.nome_social,
        queixa_principal: values.queixa_principal,
        tcle_hash: hashTcle,
      });

      const admissaoRes = await admitirMutation.mutateAsync({
        body: {
          paciente_id: intakeRes.paciente_id,
          queixa_principal: values.queixa_principal,
          sintomas: sintomasSelecionados,
          escala_dor: escalaDor,
          tcle_hash: hashTcle,
          cpf: tipoDoc === "cpf" ? values.cpf : undefined,
          cns: tipoDoc === "cns" ? values.cns : undefined,
        },
        token: intakeRes.token,
      });

      if (admissaoRes.alerta_samu_disparado || admissaoRes.prioridade_clinica === 1) {
        setOrientacoesSamu(admissaoRes.instrucoes || null);
        setSintomaAcidental(false);
        setSamuModalOpen(true);
        return;
      }

      onAdmissaoConcluida({
        pacienteId: intakeRes.paciente_id,
        atendimentoId: admissaoRes.atendimento_id,
        token: intakeRes.token,
        prioridadeClinica: admissaoRes.prioridade_clinica,
        isNovoPaciente: intakeRes.is_novo_paciente,
      });
    } catch (err: unknown) {
      if (isProblemDetailsError(err) && err.code === "EMERGENCIA_CRITICA_SAMU_192") {
        setOrientacoesSamu(err.detail || null);
        setSintomaAcidental(false);
        setSamuModalOpen(true);
      } else {
        setErroHumanizado(getHumanizedErrorMessage(err));
        onErrorBanner?.();
      }
    }
  };

  const reiniciar = () => {
    form.reset(DEFAULT_IDENTIFICATION_VALUES);
    setSintomasSelecionados([]);
    setEscalaDor(0);
    setTipoDoc("cpf");
    setErroHumanizado(null);
    setSintomaAcidental(false);
    setOrientacoesSamu(null);
    setEncaminhadoPresencial(false);
    setSamuModalOpen(false);
    setMicroEtapa("identificacao");
  };

  return {
    form,
    microEtapa,
    tipoDoc,
    sintomasSelecionados,
    sintomaAcidental,
    escalaDor,
    setEscalaDor,
    samuModalOpen,
    setSamuModalOpen,
    orientacoesSamu,
    erroHumanizado,
    encaminhadoPresencial,
    setEncaminhadoPresencial,
    isSubmitting: intakeMutation.isPending || admitirMutation.isPending,
    alternarParaCpf,
    alternarParaCns,
    mudarMicroEtapa,
    avancarParaTriagem,
    toggleSintoma,
    submeter,
    reiniciar,
    limparErro: () => setErroHumanizado(null),
    corrigirAcidental: () => {
      setSintomaAcidental(false);
      setSamuModalOpen(false);
    },
  };
}
