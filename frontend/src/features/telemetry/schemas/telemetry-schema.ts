import { z } from "zod";
import { zConfigPlantaoRequest } from "@/api/generated/zod.gen";

/**
 * Schema Zod para parametrização de política de plantão, tolerância de ring,
 * SLAs ACR e backpressure (US-12 / RF-09).
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
    .min(1, "Cota diária máxima deve ser maior que zero.")
    .nullable(),
  tma_padrao_segundos: z
    .int("Informe um número inteiro em segundos para o TMA.")
    .min(60, "TMA padrão deve ser de no mínimo 60 segundos."),
  tempo_tolerancia_ring_segundos: z
    .int("Informe um número inteiro em segundos para a tolerância do ring.")
    .min(10, "Tolerância de chamada deve ser de no mínimo 10 segundos."),
  modo_operacao: z.enum(["SUS", "PRIVADO"]),
  sla_minutos_nivel_1: z
    .int("Informe um número inteiro em minutos para o SLA Nível 1.")
    .min(0, "SLA não pode ser negativo."),
  sla_minutos_nivel_2: z
    .int("Informe um número inteiro em minutos para o SLA Nível 2.")
    .min(0, "SLA não pode ser negativo."),
  sla_minutos_nivel_3: z
    .int("Informe um número inteiro em minutos para o SLA Nível 3.")
    .min(0, "SLA não pode ser negativo."),
  sla_minutos_nivel_4: z
    .int("Informe um número inteiro em minutos para o SLA Nível 4.")
    .min(0, "SLA não pode ser negativo."),
  sla_minutos_nivel_5: z
    .int("Informe um número inteiro em minutos para o SLA Nível 5.")
    .min(0, "SLA não pode ser negativo."),
});

export type ConfigPlantaoFormData = z.output<typeof configPlantaoFormSchema>;
export type ConfigPlantaoInputFormData = z.input<typeof configPlantaoFormSchema>;
