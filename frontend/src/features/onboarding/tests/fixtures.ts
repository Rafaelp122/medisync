/**
 * Canonical test data fixtures and typed builders for Onboarding.
 * Follows ADR-011 and PEP 544 / TypeScript strict typing.
 */

import type { AdmissaoResponse, Fase1Response, Fase2Response } from "@/api/generated/types.gen";
import type { EnderecoViaCep } from "../api/use-via-cep";
import type { EnrichmentFase2FormData, IntakeFase1FormData } from "../schemas/onboarding-schema";

export const MOCK_PACIENTE_ID = "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c";
export const MOCK_ATENDIMENTO_ID = "018f3a5b-0000-4b2c-8b2c-018f3a5b7b2c";
export const MOCK_TRIAGEM_ID = "018f3a5b-1111-4b2c-8b2c-018f3a5b7b2c";
export const MOCK_ORGANIZACAO_ID = 1;
export const MOCK_CPF_VALIDO = "52998224725";
export const MOCK_CNS_VALIDO = "100000000000007";
export const MOCK_CEP_VALIDO = "01310100";
export const MOCK_TCLE_HASH = "a".repeat(64);
export const MOCK_INTAKE_TOKEN = "mock-intake-token-fase1";

/**
 * Retorna dados válidos de formulário da Fase 1 para testes de preenchimento.
 */
export function createIntakeFase1FormData(
  overrides?: Partial<IntakeFase1FormData>,
): IntakeFase1FormData {
  return {
    nome_completo: "Juliana Silva",
    cpf: MOCK_CPF_VALIDO,
    cns: "",
    nome_social: "",
    data_nascimento: "1990-05-15",
    telefone: "11987654321",
    queixa_principal: "Cefaleia moderada e febre há 2 dias",
    tcle_hash: MOCK_TCLE_HASH,
    ...overrides,
  };
}

/**
 * Retorna DTO mockado de resposta da Fase 1 (POST /api/v1/onboarding/fase-1).
 */
export function createIntakeFase1Response(overrides?: Partial<Fase1Response>): Fase1Response {
  return {
    paciente_id: MOCK_PACIENTE_ID,
    token: MOCK_INTAKE_TOKEN,
    status: "TRIADO_AGUARDANDO_ELEGIBILIDADE",
    mensagem: "Acolhimento registrado com sucesso.",
    is_novo_paciente: true,
    ...overrides,
  };
}

/**
 * Retorna DTO mockado de resposta de Admissão (POST /api/v1/fila/admissao).
 */
export function createAdmissaoResponse(overrides?: Partial<AdmissaoResponse>): AdmissaoResponse {
  return {
    atendimento_id: MOCK_ATENDIMENTO_ID,
    triagem_id: MOCK_TRIAGEM_ID,
    organizacao_id: MOCK_ORGANIZACAO_ID,
    paciente_id: MOCK_PACIENTE_ID,
    status_atendimento: "TRIADO_AGUARDANDO_ELEGIBILIDADE",
    prioridade_clinica: 3,
    alerta_samu_disparado: false,
    instrucoes: null,
    tcle_hash: MOCK_TCLE_HASH,
    ...overrides,
  };
}

/**
 * Retorna dados válidos de formulário da Fase 2 para testes.
 */
export function createEnrichmentFase2FormData(
  overrides?: Partial<EnrichmentFase2FormData>,
): EnrichmentFase2FormData {
  return {
    paciente_id: MOCK_PACIENTE_ID,
    nome_mae: "Maria Aparecida Silva",
    sexo_biologico: "F",
    cep: MOCK_CEP_VALIDO,
    logradouro: "Avenida Paulista",
    numero: "1000",
    complemento: "Apto 42",
    bairro: "Bela Vista",
    cidade: "São Paulo",
    estado: "SP",
    alergias: ["Dipirona"],
    ...overrides,
  };
}

/**
 * Retorna DTO mockado de resposta da Fase 2 (PATCH /api/v1/onboarding/fase-2).
 */
export function createEnrichmentFase2Response(overrides?: Partial<Fase2Response>): Fase2Response {
  return {
    paciente_id: MOCK_PACIENTE_ID,
    nome_completo: "Juliana Silva",
    nome_social: null,
    nome_mae: "Maria Aparecida Silva",
    sexo_biologico: "F",
    cep: MOCK_CEP_VALIDO,
    logradouro: "Avenida Paulista",
    numero: "1000",
    bairro: "Bela Vista",
    cidade: "São Paulo",
    estado: "SP",
    alergias: ["Dipirona"],
    ...overrides,
  };
}

/**
 * Retorna endereço resolvido da API ViaCEP para testes.
 */
export function createViaCepEndereco(overrides?: Partial<EnderecoViaCep>): EnderecoViaCep {
  return {
    logradouro: "Avenida Paulista",
    bairro: "Bela Vista",
    cidade: "São Paulo",
    estado: "SP",
    ...overrides,
  };
}

export interface ViaCepRawResponse {
  cep: string;
  logradouro: string;
  bairro: string;
  localidade: string;
  uf: string;
  complemento?: string;
  ibge?: string;
  erro?: boolean | string;
}

/**
 * Retorna payload bruto recebido da API pública do ViaCEP.
 */
export function createViaCepRawResponse(overrides?: Partial<ViaCepRawResponse>): ViaCepRawResponse {
  return {
    cep: "01310-100",
    logradouro: "Avenida Paulista",
    bairro: "Bela Vista",
    localidade: "São Paulo",
    uf: "SP",
    ...overrides,
  };
}
