import { z } from "zod";
import { zPioraClinicaRequest } from "@/api/generated/zod.gen";

/**
 * Schema Zod refinado para o formulário de relato de piora clínica na sala de espera.
 * Derivado de zPioraClinicaRequest gerado pelo Hey API (ADR-011 / RF-06).
 */
export const pioraClinicaFormSchema = zPioraClinicaRequest
  .extend({
    escala_dor: z
      .int("A escala de dor deve ser um número inteiro.")
      .min(0, "A escala de dor deve ser no mínimo 0.")
      .max(10, "A escala de dor deve estar entre 0 e 10."),
    queixa_adicional: z
      .string()
      .max(2000, "A queixa adicional deve ter no máximo 2000 caracteres.")
      .default(""),
    novos_sintomas: z.array(z.string()).default([]),
  })
  .refine(
    (data) =>
      (data.novos_sintomas && data.novos_sintomas.length > 0) ||
      data.queixa_adicional.trim().length > 0 ||
      data.escala_dor > 0,
    {
      message: "Informe ao menos um sintoma novo, alteração na dor ou descreva o agravamento.",
      path: ["queixa_adicional"],
    },
  );

export type PioraClinicaFormData = z.infer<typeof pioraClinicaFormSchema>;
