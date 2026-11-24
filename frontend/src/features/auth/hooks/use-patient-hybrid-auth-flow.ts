import { useState } from "react";
import { extractProblemDetail } from "@/api/errors";
import type { IdentificarPacienteResponse, VerificarOtpResponse } from "@/api/generated/types.gen";
import type { StoredPatientSession } from "@/lib/session-storage";
import { sessionTransport } from "@/lib/session-transport";
import { limparDigitos, mascararTelefoneBR } from "@/lib/validators";
import { isWebAuthnSupported } from "@/lib/webauthn";
import { usePatientLoginPassword } from "../api/use-patient-login-password";
import {
  usePatientMethods,
  usePatientPasskeyAuth,
  usePatientSolicitarOtp,
} from "../api/use-patient-methods";
import {
  patientLoginPasswordSchema,
  patientOtpRequestSchema,
  toStoredPatientSession,
} from "../schemas/patient-hybrid-auth-schemas";

export type HybridAuthStep = "identify" | "not_found" | "methods" | "otp_verify" | "password";

/**
 * Hook headless orquestrador da máquina de estados do IAM Híbrido do Cidadão (/entrar).
 * Regras: RF-01, US-14 e ADR-011.
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

  const activateAndNotify = (res: VerificarOtpResponse) => {
    const session = toStoredPatientSession(res);
    sessionTransport.activatePatientSession(session);
    onAuthenticated(session);
  };

  const methodsQuery = usePatientMethods();
  const solicitarOtp = usePatientSolicitarOtp({
    onSuccess: (res) => {
      setCodigoDebug(res.codigo_debug ?? null);
      setStep("otp_verify");
    },
  });
  const loginPassword = usePatientLoginPassword({
    onSuccess: activateAndNotify,
  });
  const passkeyAuth = usePatientPasskeyAuth({
    onSuccess: activateAndNotify,
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
      Boolean(identifyData?.metodos_disponiveis.includes("passkey")) && isWebAuthnSupported(),
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
