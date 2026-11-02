import type {
  AssinarDocumentoResponse,
  ChamarProximoResponse,
  DocumentoClinicoResponse,
  EvolucaoSoapResponse,
  LiveKitTokenResponse,
  PainelTelemetriaResponse,
  ProntuarioResponse,
  TmaStatusResponse,
} from "@/api/generated/types.gen";

export const MOCK_ATENDIMENTO_ID = "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2d";
export const MOCK_MEDICO_ID = "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2e";
export const MOCK_PACIENTE_ID = "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c";
export const MOCK_DOC_ID = "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2f";

export function createChamarProximoResponse(
  overrides?: Partial<ChamarProximoResponse>,
): ChamarProximoResponse {
  return {
    alocado: true,
    atendimento_id: MOCK_ATENDIMENTO_ID,
    paciente_id: MOCK_PACIENTE_ID,
    medico_id: MOCK_MEDICO_ID,
    prioridade_clinica: 2,
    status: "EM_ATENDIMENTO",
    chamada_iniciada_em: "2026-11-01T12:00:00Z",
    ttl_segundos: 900,
    ...overrides,
  };
}

export function createLiveKitTokenResponse(
  overrides?: Partial<LiveKitTokenResponse>,
): LiveKitTokenResponse {
  return {
    token: "mock-jwt-livekit-room-token",
    room_name: "org_1_atend_018f3a5b",
    participant_identity: `medico_${MOCK_MEDICO_ID}`,
    server_url: "wss://livekit.medisync.local",
    expires_in: 3600,
    ...overrides,
  };
}

export function createEvolucaoSoapResponse(
  overrides?: Partial<EvolucaoSoapResponse>,
): EvolucaoSoapResponse {
  return {
    id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b30",
    atendimento_id: MOCK_ATENDIMENTO_ID,
    organizacao_id: 1,
    medico_id: MOCK_MEDICO_ID,
    anamnese: "Paciente refere dor de garganta intensa há 3 dias com febre.",
    exame_fisico_virtual: "Orofaringe hiperemiada com exsudato purulento amigdaliano.",
    cid10_principal: "J03.0",
    conduta: "Prescrito Amoxicilina 500mg de 8/8h por 7 dias e repouso.",
    registrado_em: "2026-11-01T12:05:00Z",
    is_finalizado: false,
    ...overrides,
  };
}

export function createDocumentoClinicoResponse(
  overrides?: Partial<DocumentoClinicoResponse>,
): DocumentoClinicoResponse {
  return {
    id: MOCK_DOC_ID,
    atendimento_id: MOCK_ATENDIMENTO_ID,
    organizacao_id: 1,
    medico_id: MOCK_MEDICO_ID,
    tipo_documento: "RECEITA_SIMPLES",
    chave_s3: `prescricoes/${MOCK_DOC_ID}.pdf`,
    sha256_hash: "a".repeat(64),
    is_finalizado: false,
    itens: [
      {
        id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b31",
        medicamento: "Amoxicilina 500mg",
        dosagem: "500mg",
        posologia: "1 cápsula de 8 em 8 horas",
        duracao: "7 dias",
        controle_especial: false,
      },
    ],
    ...overrides,
  };
}

export function createProntuarioResponse(
  overrides?: Partial<ProntuarioResponse>,
): ProntuarioResponse {
  return {
    atendimento_id: MOCK_ATENDIMENTO_ID,
    is_finalizado: false,
    evolucao: null,
    documentos: [],
    ...overrides,
  };
}

export function createAssinarDocumentoResponse(
  overrides?: Partial<AssinarDocumentoResponse>,
): AssinarDocumentoResponse {
  return {
    documento_id: MOCK_DOC_ID,
    tipo_documento: "RECEITA_SIMPLES",
    sha256_hash: "b".repeat(64),
    assinado_em: "2026-11-01T12:15:00Z",
    tamanho_bytes: 14500,
    status: "ASSINADO",
    ...overrides,
  };
}

export function createTmaStatusResponse(overrides?: Partial<TmaStatusResponse>): TmaStatusResponse {
  return {
    atendimento_id: MOCK_ATENDIMENTO_ID,
    tempo_decorrido_segundos: 300,
    tma_planejado_segundos: 900,
    excedeu_tma: false,
    aviso_visual: "Dentro do TMA previsto.",
    ...overrides,
  };
}

export function createPainelTelemetriaResponse(
  overrides?: Partial<PainelTelemetriaResponse>,
): PainelTelemetriaResponse {
  return {
    organizacao_id: 1,
    gerado_em: "2026-11-01T12:00:00Z",
    tme_medio_segundos: 120,
    tme_nivel_1_segundos: 0,
    tme_nivel_2_segundos: 60,
    tme_nivel_3_segundos: 180,
    tme_nivel_4_segundos: 240,
    tme_nivel_5_segundos: 300,
    tma_medio_segundos: 600,
    medicos_tma: [],
    no_show_rate: 0.05,
    evasao_rate: 0.02,
    sla_compliance_percentual: 98.5,
    sla_em_conformidade: true,
    medicos_ativos_count: 1,
    total_pacientes_fila: 3,
    total_atendimentos: 10,
    ...overrides,
  };
}
