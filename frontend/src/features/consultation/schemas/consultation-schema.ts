import { z } from "zod";
import {
  zAssinarDocumentoRequest,
  zEmitirDocumentoRequest,
  zItemPrescricaoRequest,
  zRegistrarSoapRequest,
} from "@/api/generated/zod.gen";

const CID10_REGEX = /^[A-Z][0-9]{2}(\.[0-9]{1,2})?$/;

/**
 * Schema Zod de validação para registro e atualização de evolução clínica SOAP (PEP).
 * Regras: RF-07, US-09, CFM nº 1.821/2007 e CFM nº 2.314/2022.
 */
export const soapSchema = zRegistrarSoapRequest.extend({
  anamnese: z.string().trim().min(3, "Anamnese é obrigatória e deve ter ao menos 3 caracteres"),
  conduta: z
    .string()
    .trim()
    .min(3, "Conduta clínica é obrigatória e deve ter ao menos 3 caracteres"),
  exame_fisico_virtual: z
    .string()
    .nullish()
    .transform((val) => (val?.trim() ? val.trim() : null)),
  cid10_principal: z
    .string()
    .nullish()
    .refine(
      (val) => {
        if (!val?.trim()) return true;
        return CID10_REGEX.test(val.trim().toUpperCase());
      },
      {
        message: "Código CID-10 inválido; formato esperado: ex. J00, J02.9, A09.0",
      },
    )
    .transform((val) => (val?.trim() ? val.trim().toUpperCase() : null)),
});

/**
 * Schema Zod de validação para item de prescrição medicamentosa.
 * Regras: US-10, Portaria SVS/MS 344/98 e RDC ANVISA 20/2011.
 */
export const itemPrescricaoSchema = zItemPrescricaoRequest.extend({
  medicamento: z.string().trim().min(2, "Nome do medicamento é obrigatório"),
  dosagem: z.string().trim().min(1, "Dosagem é obrigatória (ex: 500mg)"),
  posologia: z.string().trim().min(2, "Instruções de posologia são obrigatórias"),
  duracao: z.string().nullish(),
  controle_especial: z.boolean().default(false),
});

/**
 * Schema Zod de validação para emissão de documento clínico (receita ou atestado).
 * Regras: RF-07, US-10.
 */
export const emitirDocumentoSchema = zEmitirDocumentoRequest
  .extend({
    tipo_documento: z.string().default("RECEITA_SIMPLES"),
    itens: z.array(itemPrescricaoSchema).optional().default([]),
  })
  .superRefine((data, ctx) => {
    if (data.tipo_documento === "RECEITA_SIMPLES" && (!data.itens || data.itens.length === 0)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "A receita deve conter ao menos um medicamento",
        path: ["itens"],
      });
    }
  });

/**
 * Schema Zod de validação para assinatura digital ICP-Brasil via PSC em nuvem.
 * Regras: RF-07, US-10, ADR-006.
 */
export const assinarDocumentoSchema = zAssinarDocumentoRequest.extend({
  token: z.string().trim().min(1, "Token de autorização PSC é obrigatório"),
  provider: z.string().default("birdid"),
});

/**
 * Schema Zod para conferência visual de identidade em vídeo sob CFM nº 2.314/2022.
 * Bloqueia prescrição e checkout se não verificado nem justificado eticamente.
 */
export const cfmIdentityGateSchema = z
  .object({
    identidade_verificada: z.boolean(),
    tipo_documento_apresentado: z.enum(["RG", "CNH", "CNS"]).nullish(),
    justificativa_excecao: z.string().nullish(),
  })
  .superRefine((data, ctx) => {
    if (!data.identidade_verificada) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Conferência de identidade oficial com foto é mandatória (CFM nº 2.314/2022)",
        path: ["identidade_verificada"],
      });
      return;
    }

    const temDoc = Boolean(data.tipo_documento_apresentado);
    const justificativaValida = Boolean(
      data.justificativa_excecao && data.justificativa_excecao.trim().length >= 10,
    );

    if (!temDoc && !justificativaValida) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message:
          "Selecione o documento oficial apresentado (RG/CNH/CNS) ou informe justificativa formal de exceção clínica (mínimo 10 caracteres)",
        path: ["tipo_documento_apresentado"],
      });
    }
  });

export type SoapFormData = z.output<typeof soapSchema>;
export type SoapInputFormData = z.input<typeof soapSchema>;
export type ItemPrescricaoFormData = z.infer<typeof itemPrescricaoSchema>;
export type EmitirDocumentoFormData = z.infer<typeof emitirDocumentoSchema>;
export type AssinarDocumentoFormData = z.infer<typeof assinarDocumentoSchema>;
export type CfmIdentityGateData = z.infer<typeof cfmIdentityGateSchema>;
