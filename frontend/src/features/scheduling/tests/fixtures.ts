import type {
  AgendamentoResponse,
  DisponibilidadeResponse,
  EspecialidadeResponse,
  SlotDisponivelResponse,
} from "@/api/generated/types.gen";

export const MOCK_PACIENTE_ID = "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b10";
export const MOCK_PROFISSIONAL_ID = "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b20";
export const MOCK_AGENDAMENTO_ID = "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b30";
export const MOCK_DISPONIBILIDADE_ID = "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b40";

export const MOCK_ESPECIALIDADES: EspecialidadeResponse[] = [
  {
    codigo: "PSICOLOGIA",
    nome: "Psicologia",
    descricao: "Acompanhamento psicológico clínico multiprofissional programado (eMulti).",
    duracao_padrao_minutos: 50,
  },
  {
    codigo: "NUTRICAO",
    nome: "Nutrição",
    descricao: "Orientação e acompanhamento nutricional clínico programado (eMulti).",
    duracao_padrao_minutos: 30,
  },
];

export const MOCK_SLOTS_PSICOLOGIA: SlotDisponivelResponse[] = [
  {
    profissional_id: MOCK_PROFISSIONAL_ID,
    especialidade: "PSICOLOGIA",
    slot_inicio: "2026-11-20T09:00:00Z",
    slot_fim: "2026-11-20T09:50:00Z",
    duracao_minutos: 50,
  },
  {
    profissional_id: MOCK_PROFISSIONAL_ID,
    especialidade: "PSICOLOGIA",
    slot_inicio: "2026-11-20T10:00:00Z",
    slot_fim: "2026-11-20T10:50:00Z",
    duracao_minutos: 50,
  },
];

export const MOCK_SLOTS_NUTRICAO: SlotDisponivelResponse[] = [
  {
    profissional_id: MOCK_PROFISSIONAL_ID,
    especialidade: "NUTRICAO",
    slot_inicio: "2026-11-20T14:00:00Z",
    slot_fim: "2026-11-20T14:30:00Z",
    duracao_minutos: 30,
  },
];

export function createAgendamentoFixture(
  overrides: Partial<AgendamentoResponse> = {},
): AgendamentoResponse {
  return {
    id: MOCK_AGENDAMENTO_ID,
    organizacao_id: 1,
    paciente_id: MOCK_PACIENTE_ID,
    profissional_id: MOCK_PROFISSIONAL_ID,
    especialidade: "PSICOLOGIA",
    slot_inicio: "2026-11-20T09:00:00Z",
    slot_fim: "2026-11-20T09:50:00Z",
    status: "AGENDADO",
    observacoes: "Primeira sessão de acompanhamento",
    atendimento_id: null,
    criado_em: "2026-11-16T10:00:00Z",
    atualizado_em: "2026-11-16T10:00:00Z",
    ...overrides,
  };
}

export function createDisponibilidadeFixture(
  overrides: Partial<DisponibilidadeResponse> = {},
): DisponibilidadeResponse {
  return {
    id: MOCK_DISPONIBILIDADE_ID,
    organizacao_id: 1,
    profissional_id: MOCK_PROFISSIONAL_ID,
    especialidade: "PSICOLOGIA",
    dia_semana: 0,
    hora_inicio: "08:00:00",
    hora_fim: "12:00:00",
    duracao_minutos: 50,
    ativo: true,
    ...overrides,
  };
}
