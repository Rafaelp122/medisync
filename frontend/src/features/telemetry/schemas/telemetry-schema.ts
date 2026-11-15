import { z } from "zod";
import { zConfigPlantaoRequest } from "@/api/generated/zod.gen";

/**
 * Schema Zod para parametrização de política de plantão e backpressure (US-12 / RF-09).
 * Estende zConfigPlantaoRequest gerado pelo Hey API (ADR-011).
 */
export const configPlantaoFormSchema = zConfigPlantaoRequest.extend({
  medicos_ativos_planejados: z
    .int("Informe um número inteiro para médicos ativos.")
    .min(1, "Deve haver ao menos 1 médico ativo planejado."),
  alpha_backpressure: z
    .number("Informe um valor numérico para o fator alpha.")
    .min(1.2, "Fator alpha deve estar entre 1,20 e 1,30.")
    .max(1.3, "Fator alpha deve estar entre 1,20 e 1,30."),
  cota_diaria_maxima: z
    .int("Informe um número inteiro para a cota diária.")
    .min(1, "Cota diária máxima deve ser maior que zero."),
  tma_padrao_segundos: z
    .int("Informe um número inteiro em segundos para o TMA.")
    .min(60, "TMA padrão deve ser de no mínimo 60 segundos."),
  modo_operacao: z.enum(["SUS", "PRIVADO"]),
});

export type ConfigPlantaoFormData = z.output<typeof configPlantaoFormSchema>;
export type ConfigPlantaoInputFormData = z.input<typeof configPlantaoFormSchema>;
