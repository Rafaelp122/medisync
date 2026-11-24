import { z } from "zod";
import { zAdmissaoRequest, zFase1Request, zFase2Request } from "@/api/generated/zod.gen";
import {
  formatarTelefoneE164,
  limparDigitos,
  validarCEP,
  validarCNS,
  validarCPF,
  validarTelefoneCelularBR,
} from "@/lib/validators";

const intakeCamposIdentificacaoExtendidos = {
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
  nome_social: z
    .string()
    .nullish()
    .transform((val) => {
      const trimmed = val?.trim();
      return trimmed ? trimmed : undefined;
    }),
};

function validarIdentificacaoCivil(
  data: { cpf?: string | null; cns?: string | null; data_nascimento?: string },
  ctx: z.RefinementCtx,
): void {
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
}

/**
 * Schema Zod de validação de payload da API de Acolhimento Rápido (Fase 1 - RF-01, US-01).
 */
export const intakeFase1Schema = zFase1Request
  .extend({
    ...intakeCamposIdentificacaoExtendidos,
    tcle_hash: z
      .string()
      .length(64, "Hash do TCLE deve conter exatamente 64 caracteres hexadecimais"),
  })
  .superRefine(validarIdentificacaoCivil);

/**
 * Schema Zod de formulário para walk-in sem JWT (substitui dummy "0"*64 por aceite_tcle booleano).
 * @see docs/user-stories/US-01-acolhimento-triagem-tcle.md
 */
export const intakeFase1FormSchema = zFase1Request
  .omit({ tcle_hash: true })
  .extend({
    ...intakeCamposIdentificacaoExtendidos,
    aceite_tcle: z.boolean().refine((val) => val === true, {
      message:
        "É obrigatório concordar com o Termo de Consentimento Livre e Esclarecido (TCLE) para ingressar na fila virtual.",
    }),
  })
  .superRefine(validarIdentificacaoCivil);

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
 * Schema Zod do formulário headless de Triagem Clínica (cidadão autenticado via JWT).
 * Exige aceite real do TCLE antes do cálculo WebCrypto SHA-256.
 * @see docs/user-stories/US-01-acolhimento-triagem-tcle.md
 */
export const clinicalTriageFormSchema = admissaoSchema
  .omit({ paciente_id: true, tcle_hash: true, tcle_texto: true })
  .extend({
    sintomas: z.array(z.string()).default([]),
    aceite_tcle: z.boolean().refine((val) => val === true, {
      message:
        "É obrigatório concordar com o Termo de Consentimento Livre e Esclarecido (TCLE) para ingressar na fila virtual.",
    }),
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

export type IntakeFase1FormData = z.output<typeof intakeFase1Schema>;
export type IntakeFase1InputFormData = z.input<typeof intakeFase1Schema>;
export type IntakeFase1UiOutputData = z.output<typeof intakeFase1FormSchema>;
export type IntakeFase1UiInputData = z.input<typeof intakeFase1FormSchema>;
export type AdmissaoFormData = z.output<typeof admissaoSchema>;
export type ClinicalTriageFormData = z.output<typeof clinicalTriageFormSchema>;
export type ClinicalTriageInputFormData = z.input<typeof clinicalTriageFormSchema>;
export type EnrichmentFase2FormData = z.output<typeof enrichmentFase2Schema>;
export type EnrichmentFase2InputFormData = z.input<typeof enrichmentFase2Schema>;
