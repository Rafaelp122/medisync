import { z } from "zod";
import type { VerificarOtpResponse } from "@/api/generated/types.gen";
import {
  zIdentificarPacienteRequest,
  zLoginPacienteSenhaRequest,
  zMfaAtivarRequest,
  zRegistrarPacienteRequest,
  zSolicitarOtpRequest,
  zVerificarOtpRequest,
} from "@/api/generated/zod.gen";
import { type StoredPatientSession, saveStoredSession } from "@/lib/session-storage";
import {
  formatarTelefoneE164,
  limparDigitos,
  validarCPF,
  validarTelefoneCelularBR,
} from "@/lib/validators";

/**
 * Converte a resposta de autenticação do paciente em StoredPatientSession e persiste no storage.
 */
export function persistirSessaoPaciente(
  data: VerificarOtpResponse,
  onAuthenticated?: (session: StoredPatientSession) => void,
): StoredPatientSession {
  const session: StoredPatientSession = {
    tipo: "otp",
    role: data.role ?? "PACIENTE",
    pacienteId: data.paciente_id,
    token: data.access_token,
    atendimentoId: data.atendimento_id ?? undefined,
  };
  saveStoredSession(session);
  onAuthenticated?.(session);
  return session;
}

const EMAIL_SCHEMA = z.string().email("Informe um endereço de e-mail válido.");

/**
 * Normaliza o identificador único do cidadão (CPF limpo com 11 dígitos ou e-mail em minúsculas).
 */
export function normalizarIdentificadorCidadao(valor: string): string {
  const trimmed = valor.trim();
  if (trimmed.includes("@")) {
    return trimmed.toLowerCase();
  }
  const digits = limparDigitos(trimmed);
  if (digits.length === 11 && /^[0-9.\-\s]+$/.test(trimmed)) {
    return digits;
  }
  return trimmed;
}

export const patientIdentifySchema = zIdentificarPacienteRequest.extend({
  identificador: z
    .string()
    .trim()
    .min(3, "Informe seu CPF (11 dígitos) ou e-mail cadastrado.")
    .refine(
      (val) => {
        if (val.includes("@")) {
          return EMAIL_SCHEMA.safeParse(val).success;
        }
        return /^[0-9.\-\s]+$/.test(val) && validarCPF(val);
      },
      {
        message: "Informe um CPF válido (11 dígitos) ou um e-mail válido.",
      },
    ),
});

export type PatientIdentifyFormData = z.infer<typeof patientIdentifySchema>;

export const patientLoginPasswordSchema = zLoginPacienteSenhaRequest.extend({
  identificador: z
    .string()
    .trim()
    .min(3, "Informe seu CPF ou e-mail cadastrado.")
    .max(255, "Identificador muito longo."),
  senha: z.string().min(1, "Informe sua senha de acesso.").max(128, "Senha muito longa."),
});

export type PatientLoginPasswordFormData = z.infer<typeof patientLoginPasswordSchema>;

export const patientOtpRequestSchema = zSolicitarOtpRequest.extend({
  telefone: z
    .string()
    .refine((val) => validarTelefoneCelularBR(val), {
      message: "Telefone inválido; informe DDD + 9 dígitos.",
    })
    .transform((val) => formatarTelefoneE164(val)),
});

export const patientOtpVerifySchema = zVerificarOtpRequest.extend({
  codigo: z.string().regex(/^\d{6}$/, "O código deve conter exatamente 6 dígitos numéricos."),
});

export const patientRegisterSchema = zRegistrarPacienteRequest.extend({
  cpf: z
    .string()
    .min(11, "CPF deve conter 11 dígitos.")
    .refine((val) => validarCPF(val), {
      message: "CPF inválido. Verifique os dígitos informados.",
    }),
  nome_completo: z
    .string()
    .trim()
    .min(3, "Informe seu nome completo (ao menos 3 caracteres).")
    .max(255, "Nome completo muito longo."),
  data_nascimento: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/, "Data de nascimento obrigatória (AAAA-MM-DD).")
    .refine((val) => new Date(`${val}T00:00:00`) <= new Date(), {
      message: "Data de nascimento não pode ser no futuro.",
    }),
  telefone: z.string().refine((val) => validarTelefoneCelularBR(val), {
    message: "Telefone celular inválido; informe DDD + 9 dígitos.",
  }),
  email: z
    .string()
    .trim()
    .min(5, "Informe seu e-mail.")
    .max(255, "E-mail muito longo.")
    .refine((val) => EMAIL_SCHEMA.safeParse(val).success, {
      message: "Informe um e-mail válido.",
    }),
  senha: z
    .string()
    .max(128, "Senha muito longa.")
    .optional()
    .nullable()
    .refine((val) => !val || val.trim().length >= 8, {
      message: "A senha opcional deve conter pelo menos 8 caracteres.",
    }),
  aceite_privacidade: z.boolean().refine((val) => val === true, {
    message: "É obrigatório aceitar a Política de Privacidade (LGPD) para concluir o cadastro.",
  }),
});

export type PatientRegisterFormData = z.infer<typeof patientRegisterSchema>;

export const mfaActivateSchema = zMfaAtivarRequest.extend({
  codigo: z
    .string()
    .length(6, "Código TOTP deve ter exatamente 6 dígitos.")
    .regex(/^\d{6}$/, "O código deve conter apenas números."),
});

export type MfaActivateFormData = z.infer<typeof mfaActivateSchema>;
