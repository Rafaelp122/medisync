import { z } from "zod";
import {
  zAdmissaoRequest,
  zFase1Request,
  zFase2Request,
  zSolicitarOtpRequest,
  zVerificarOtpRequest,
} from "@/api/generated/zod.gen";
import {
  formatarTelefoneE164,
  limparDigitos,
  validarCEP,
  validarCNS,
  validarCPF,
  validarTelefoneCelularBR,
} from "@/lib/validators";

/**
 * Schema Zod de validação para solicitação de OTP com validação estrita de telefone brasileiro.
 * Regras canônicas: RF-01, US-02 (§5.1) e ADR-011.
 * @see docs/user-stories/US-02-autenticacao-passwordless-otp.md
 */
export const solicitarOtpSchema = zSolicitarOtpRequest.extend({
  telefone: z
    .string()
    .refine((val) => validarTelefoneCelularBR(val), {
      message: "Telefone inválido; informe DDD + 9 dígitos",
    })
    .transform((val) => formatarTelefoneE164(val)),
});

/**
 * Schema Zod de validação para verificação de OTP com 6 dígitos numéricos.
 * Regras canônicas: RF-01, US-02 (§5.1) e ADR-011.
 * @see docs/user-stories/US-02-autenticacao-passwordless-otp.md
 */
export const verificarOtpSchema = zVerificarOtpRequest.extend({
  codigo: z.string().regex(/^\d{6}$/, "O código deve conter exatamente 6 dígitos numéricos"),
});

/**
 * Schema Zod de validação para Acolhimento Clínico Rápido (Fase 1 - RF-01, US-01).
 * Valida CPF ou CNS, telefone brasileiro, queixa e hash SHA-256 do TCLE digital.
 * Tempo de preenchimento planejado: < 45s (NEC-01).
 */
export const intakeFase1Schema = zFase1Request
  .extend({
    telefone: z
      .string()
      .refine((val) => validarTelefoneCelularBR(val), {
        message: "Telefone inválido; informe DDD + 9 dígitos",
      })
      .transform((val) => formatarTelefoneE164(val)),
    cpf: z
      .string()
      .nullish()
      .transform((val) => (val ? limparDigitos(val) : val)),
    cns: z
      .string()
      .nullish()
      .transform((val) => (val ? limparDigitos(val) : val)),
    tcle_hash: z
      .string()
      .length(64, "Hash do TCLE deve conter exatamente 64 caracteres hexadecimais"),
  })
  .superRefine((data, ctx) => {
    // Ao menos um documento de identificação é mandatório
    const temCpf = Boolean(data.cpf?.trim());
    const temCns = Boolean(data.cns?.trim());

    if (!temCpf && !temCns) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Informe ao menos um documento de identificação (CPF ou CNS)",
        path: ["cpf"],
      });
    }

    if (temCpf && data.cpf && !validarCPF(data.cpf)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "CPF inválido; verifique os dígitos informados",
        path: ["cpf"],
      });
    }

    if (temCns && data.cns && !validarCNS(data.cns)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "CNS inválido; informe um número de Cartão SUS válido",
        path: ["cns"],
      });
    }

    // Validação de data de nascimento (não futura)
    if (data.data_nascimento) {
      const dataNasc = new Date(`${data.data_nascimento}T00:00:00`);
      const hoje = new Date();
      if (dataNasc > hoje) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "Data de nascimento não pode ser no futuro",
          path: ["data_nascimento"],
        });
      }
    }
  });

/**
 * Schema Zod de validação para Admissão e Triagem Clínica (RF-01, RN01, RN04).
 */
export const admissaoSchema = zAdmissaoRequest.extend({
  escala_dor: z
    .number()
    .int()
    .min(0, "Escala de dor mínima é 0")
    .max(10, "Escala de dor máxima é 10")
    .default(0),
  queixa_principal: z.string().min(3, "Queixa clínica deve ter ao menos 3 caracteres"),
});

/**
 * Schema Zod de validação para Enriquecimento Cadastral CFM 1.821/2007 (Fase 2 - RF-02, US-03).
 */
export const enrichmentFase2Schema = zFase2Request.extend({
  nome_mae: z
    .string()
    .min(3, "Nome da mãe deve ter no mínimo 3 caracteres")
    .max(255)
    .refine(
      (val) => {
        const clean = val.trim();
        const words = clean.split(/\s+/);
        return words.length >= 2 && /^[A-Za-zÀ-ÖØ-öø-ÿ\s'-]+$/.test(clean);
      },
      {
        message:
          "Informe o nome completo da mãe (ao menos dois nomes), contendo apenas letras e acentos",
      },
    ),
  cep: z
    .string()
    .refine((val) => validarCEP(val), {
      message: "CEP inválido; informe 8 dígitos numéricos válidos",
    })
    .transform((val) => limparDigitos(val)),
  estado: z
    .string()
    .length(2, "UF deve conter exatamente 2 letras")
    .transform((val) => val.toUpperCase()),
});

export type SolicitarOtpFormData = z.infer<typeof solicitarOtpSchema>;
export type VerificarOtpFormData = z.infer<typeof verificarOtpSchema>;
export type IntakeFase1FormData = z.infer<typeof intakeFase1Schema>;
export type AdmissaoFormData = z.infer<typeof admissaoSchema>;
export type EnrichmentFase2FormData = z.infer<typeof enrichmentFase2Schema>;
