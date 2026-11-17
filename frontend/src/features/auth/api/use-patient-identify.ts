import { type UseMutationOptions, useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { client, getTenantHeaders } from "@/api/client";
import {
  extractProblemDetail,
  type ProblemDetailsError,
  toProblemDetailsError,
} from "@/api/errors";
import { postAuthPatientIdentify } from "@/api/generated/sdk.gen";
import type {
  IdentificarPacienteRequest,
  IdentificarPacienteResponse,
} from "@/api/generated/types.gen";
import type { StoredPatientSession } from "@/lib/session-storage";
import { limparDigitos, mascararTelefoneBR } from "@/lib/validators";
import {
  patientLoginPasswordSchema,
  patientOtpRequestSchema,
  persistirSessaoPaciente,
} from "../schemas/patient-hybrid-auth-schemas";
import { usePatientLoginPassword } from "./use-patient-login-password";
import {
  usePatientMethods,
  usePatientPasskeyAuth,
  usePatientSolicitarOtp,
} from "./use-patient-methods";

export type HybridAuthStep = "identify" | "not_found" | "methods" | "otp_verify" | "password";

/**
 * Hook headless de mutação para identificação única anti-enumeração do cidadão (CPF ou e-mail).
 * Regras canônicas: RF-01, ADR-005 e ADR-011.
 * @see docs/explanation/domains/auth-domain.md
 */
export function usePatientIdentify(
  options?: UseMutationOptions<
    IdentificarPacienteResponse,
    ProblemDetailsError,
    IdentificarPacienteRequest
  >,
) {
  return useMutation<IdentificarPacienteResponse, ProblemDetailsError, IdentificarPacienteRequest>({
    mutationFn: async (body: IdentificarPacienteRequest) => {
      try {
        const response = await postAuthPatientIdentify({
          client,
          headers: { ...getTenantHeaders() },
          body,
          throwOnError: true,
        });
        return response.data;
      } catch (err) {
        throw toProblemDetailsError(err);
      }
    },
    ...options,
  });
}

function isWebAuthnSupported(): boolean {
  return typeof navigator !== "undefined" && typeof navigator.credentials?.get === "function";
}

/**
 * Hook headless orquestrador da máquina de estados do IAM Híbrido do Cidadão (/entrar).
 */
export function usePatientHybridAuthFlow(onAuthenticated: (session: StoredPatientSession) => void) {
  const [step, setStep] = useState<HybridAuthStep>("identify");
  const [identificador, setIdentificador] = useState("");
  const [identifyData, setIdentifyData] = useState<IdentificarPacienteResponse | null>(null);
  const [telefoneInput, setTelefoneInput] = useState("");
  const [telefoneE164, setTelefoneE164] = useState("");
  const [codigoDebug, setCodigoDebug] = useState<string | null>(null);
  const [senha, setSenha] = useState("");
  const [erroLocal, setErroLocal] = useState<string | null>(null);

  const methodsQuery = usePatientMethods();
  const solicitarOtp = usePatientSolicitarOtp({
    onSuccess: (res) => {
      setCodigoDebug(res.codigo_debug ?? null);
      setStep("otp_verify");
    },
  });
  const loginPassword = usePatientLoginPassword({
    onSuccess: (res) => persistirSessaoPaciente(res, onAuthenticated),
  });
  const passkeyAuth = usePatientPasskeyAuth({
    onSuccess: (res) => persistirSessaoPaciente(res, onAuthenticated),
  });

  const resetarFluxo = () => {
    setErroLocal(null);
    setSenha("");
    setCodigoDebug(null);
    setStep("identify");
  };

  const handleIdentified = (payload: {
    identificador: string;
    response: IdentificarPacienteResponse;
  }) => {
    setErroLocal(null);
    setIdentificador(payload.identificador);
    setIdentifyData(payload.response);
    setStep(payload.response.possui_conta ? "methods" : "not_found");
  };

  const handleEnviarOtp = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErroLocal(null);
    const parsed = patientOtpRequestSchema.safeParse({
      telefone: telefoneInput,
      cpf: /^\d{11}$/.test(limparDigitos(identificador)) ? limparDigitos(identificador) : null,
    });
    if (!parsed.success) {
      setErroLocal(parsed.error.issues[0]?.message ?? "Informe seu telefone celular com DDD.");
      return;
    }
    setTelefoneE164(parsed.data.telefone);
    solicitarOtp.mutate({ telefone: parsed.data.telefone, cpf: parsed.data.cpf ?? null });
  };

  const handleLoginSenha = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErroLocal(null);
    const parsed = patientLoginPasswordSchema.safeParse({ identificador, senha });
    if (!parsed.success) {
      setErroLocal(parsed.error.issues[0]?.message ?? "Informe identificador e senha.");
      return;
    }
    loginPassword.mutate(parsed.data);
  };

  const mutationError = [solicitarOtp, loginPassword, passkeyAuth].find((m) => m.isError)?.error;
  const activeError = erroLocal ?? (mutationError ? extractProblemDetail(mutationError) : null);

  return {
    step,
    setStep: (next: HybridAuthStep) => {
      setErroLocal(null);
      setStep(next);
    },
    identificador,
    setIdentificador,
    identifyData,
    telefoneInput,
    onTelefoneChange: (val: string) => {
      setErroLocal(null);
      setTelefoneInput(mascararTelefoneBR(val));
    },
    telefoneE164,
    codigoDebug,
    senha,
    onSenhaChange: (val: string) => {
      setErroLocal(null);
      setSenha(val);
    },
    activeError,
    govbrGlobalHabilitado: methodsQuery.data?.govbr_oidc_enabled ?? false,
    govbrHabilitado:
      identifyData?.govbr_habilitado ?? methodsQuery.data?.govbr_oidc_enabled ?? false,
    mostrarPasskey:
      Boolean(identifyData?.metodos_disponiveis.includes("passkey")) || isWebAuthnSupported(),
    isSendingOtp: solicitarOtp.isPending,
    isLoggingInPassword: loginPassword.isPending,
    isAuthenticatingPasskey: passkeyAuth.isPending,
    triggerPasskey: () => passkeyAuth.mutate(undefined),
    resetarFluxo,
    handleIdentified,
    handleEnviarOtp,
    handleLoginSenha,
  };
}
