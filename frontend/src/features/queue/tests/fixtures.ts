import type {
  LiveKitTokenResponse,
  PioraClinicaResponse,
  PosicaoFilaResponse,
} from "@/api/generated/types.gen";
import type { StoredPatientSession } from "@/lib/session-storage";

export const MOCK_ATENDIMENTO_ID = "018f3a5b-0000-7000-8000-000000000001";
export const MOCK_PACIENTE_ID = "018f3a5b-0000-7000-8000-000000000002";
export const MOCK_MEDICO_ID = "018f3a5b-0000-7000-8000-000000000003";
export const MOCK_TOKEN = "mock-bearer-token";

export const MOCK_SESSION: StoredPatientSession = {
  tipo: "acolhimento",
  role: "PACIENTE",
  pacienteId: MOCK_PACIENTE_ID,
  atendimentoId: MOCK_ATENDIMENTO_ID,
  prioridadeClinica: 3,
  token: MOCK_TOKEN,
  status: "APTO_PARA_CHAMADA",
};

export const MOCK_POSICAO_RESPONSE: PosicaoFilaResponse = {
  atendimento_id: MOCK_ATENDIMENTO_ID,
  status: "APTO_PARA_CHAMADA",
  posicao: 4,
  total_aguardando: 6,
  tempo_estimado_segundos: 900,
};

export const MOCK_LIVEKIT_TOKEN_RESPONSE: LiveKitTokenResponse = {
  token: "jwt.mock.livekit.token",
  server_url: "wss://livekit.test:7880",
  room_name: `room_${MOCK_ATENDIMENTO_ID}`,
  participant_identity: `paciente:${MOCK_PACIENTE_ID}`,
};

export const MOCK_PIORA_RECLASSIFICADO_RESPONSE: PioraClinicaResponse = {
  atendimento_id: MOCK_ATENDIMENTO_ID,
  prioridade_clinica: 2,
  nova_prioridade: 2,
  status_atendimento: "APTO_PARA_CHAMADA",
  alerta_samu_disparado: false,
  redirecionado_emergencia: false,
  nova_posicao: 1,
  instrucoes: "Prioridade reclassificada para Nível 2 (Laranja).",
};

export const MOCK_PIORA_SAMU_RESPONSE: PioraClinicaResponse = {
  atendimento_id: MOCK_ATENDIMENTO_ID,
  prioridade_clinica: 1,
  nova_prioridade: 1,
  status_atendimento: "REDIRECIONADO_SAMU",
  alerta_samu_disparado: true,
  redirecionado_emergencia: true,
  nova_posicao: null,
  instrucoes: "Sinais de risco iminente de morte.",
  orientacoes_emergencia: "Ligue imediatamente para o SAMU 192 ou dirija-se à UPA mais próxima.",
};
