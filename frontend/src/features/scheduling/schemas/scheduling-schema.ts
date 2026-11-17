import { z } from "zod";
import { zCriarAgendamentoRequest, zCriarDisponibilidadeRequest } from "@/api/generated/zod.gen";

/**
 * Schema Zod derivado do OpenAPI para validação em runtime da reserva de consulta pelo paciente.
 * Regras: ADR-011 (Zero DTO Duplication).
 */
export const criarAgendamentoFormSchema = zCriarAgendamentoRequest.extend({
  observacoes: z.string().max(500, "As observações devem ter no máximo 500 caracteres.").nullish(),
});

/**
 * Schema Zod derivado do OpenAPI para cadastro de janela semanal de disponibilidade do profissional.
 * Regras: ADR-011 (Zero DTO Duplication).
 */
export const criarDisponibilidadeFormSchema = zCriarDisponibilidadeRequest
  .extend({
    especialidade: z.string().min(1, "Selecione uma especialidade."),
    dia_semana: z
      .number({ message: "Selecione o dia da semana." })
      .int("Dia da semana inválido.")
      .min(0, "Dia da semana inválido.")
      .max(6, "Dia da semana inválido."),
    hora_inicio: z
      .string()
      .regex(/^\d{2}:\d{2}(:\d{2})?$/, "Informe o horário inicial no formato HH:MM."),
    hora_fim: z
      .string()
      .regex(/^\d{2}:\d{2}(:\d{2})?$/, "Informe o horário final no formato HH:MM."),
    duracao_minutos: z
      .number({ message: "Informe a duração em minutos." })
      .int("A duração deve ser um número inteiro.")
      .min(15, "A duração mínima do slot é de 15 minutos.")
      .max(120, "A duração máxima do slot é de 120 minutos."),
  })
  .refine((data) => data.hora_fim > data.hora_inicio, {
    message: "O horário final deve ser posterior ao horário inicial.",
    path: ["hora_fim"],
  });

export type CriarAgendamentoFormData = z.output<typeof criarAgendamentoFormSchema>;
export type CriarDisponibilidadeFormData = z.output<typeof criarDisponibilidadeFormSchema>;

const MAX_JANELA_DIAS = 31;

/**
 * Valida o período de busca de slots (dataInicio <= dataFim e máximo de 31 dias).
 */
export function validarPeriodoSlots(dataInicio: string, dataFim: string): string | null {
  if (!dataInicio || !dataFim) {
    return "Informe a data inicial e a data final para consultar horários.";
  }
  if (dataFim < dataInicio) {
    return "A data final deve ser igual ou posterior à data inicial.";
  }
  const inicioMs = new Date(`${dataInicio}T00:00:00Z`).getTime();
  const fimMs = new Date(`${dataFim}T00:00:00Z`).getTime();
  const diffDias = Math.round((fimMs - inicioMs) / (1000 * 60 * 60 * 24));
  if (diffDias > MAX_JANELA_DIAS) {
    return `O intervalo máximo de busca é de ${MAX_JANELA_DIAS} dias.`;
  }
  return null;
}
