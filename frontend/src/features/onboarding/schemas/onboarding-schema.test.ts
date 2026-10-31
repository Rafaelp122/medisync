import { describe, expect, it } from "vitest";
import {
  admissaoSchema,
  enrichmentFase2Schema,
  intakeFase1Schema,
  solicitarOtpSchema,
  verificarOtpSchema,
} from "./onboarding-schema";

describe("Schemas Zod de Onboarding OTP", () => {
  it("UT-10: solicitarOtpSchema aceita payload válido", () => {
    const result = solicitarOtpSchema.safeParse({
      telefone: "(11) 98765-4321",
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.telefone).toBe("+5511987654321");
    }
  });

  it("UT-11: solicitarOtpSchema rejeita telefone inválido com mensagem canônica em português", () => {
    const result = solicitarOtpSchema.safeParse({
      telefone: "1133334444",
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toContain(
        "Telefone inválido; informe DDD + 9 dígitos",
      );
    }
  });

  it("UT-12: verificarOtpSchema aceita código de 6 dígitos numéricos", () => {
    const result = verificarOtpSchema.safeParse({
      telefone: "+5511987654321",
      codigo: "123456",
    });
    expect(result.success).toBe(true);
  });

  it("UT-13: verificarOtpSchema rejeita código alfanumérico ou com menos de 6 dígitos", () => {
    const resultShort = verificarOtpSchema.safeParse({
      telefone: "+5511987654321",
      codigo: "12345",
    });
    expect(resultShort.success).toBe(false);

    const resultAlpha = verificarOtpSchema.safeParse({
      telefone: "+5511987654321",
      codigo: "12345a",
    });
    expect(resultAlpha.success).toBe(false);
  });
});

describe("Schema Zod IntakeFase1 (Acolhimento Rápido)", () => {
  const tcleValido64 = "a".repeat(64);

  it("UT-SCH-01: Aceita payload válido com CPF sanitizado", () => {
    const result = intakeFase1Schema.safeParse({
      nome_completo: "Juliana Silva",
      data_nascimento: "1990-05-15",
      telefone: "(11) 98765-4321",
      queixa_principal: "Febre alta e dor de cabeça há 2 dias",
      tcle_hash: tcleValido64,
      cpf: "111.444.777-35",
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.cpf).toBe("11144477735");
      expect(result.data.telefone).toBe("+5511987654321");
    }
  });

  it("UT-SCH-02: Aceita payload válido com CNS", () => {
    const result = intakeFase1Schema.safeParse({
      nome_completo: "Juliana Silva",
      data_nascimento: "1990-05-15",
      telefone: "11987654321",
      queixa_principal: "Febre e dor",
      tcle_hash: tcleValido64,
      cns: "100 0000 0000 0007",
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.cns).toBe("100000000000007");
    }
  });

  it("UT-SCH-03: Rejeita quando nem CPF nem CNS são fornecidos", () => {
    const result = intakeFase1Schema.safeParse({
      nome_completo: "Juliana Silva",
      data_nascimento: "1990-05-15",
      telefone: "11987654321",
      queixa_principal: "Febre e dor",
      tcle_hash: tcleValido64,
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toContain(
        "Informe ao menos um documento de identificação (CPF ou CNS)",
      );
    }
  });

  it("UT-SCH-04: Rejeita data de nascimento futura", () => {
    const dataFutura = "2099-01-01";
    const result = intakeFase1Schema.safeParse({
      nome_completo: "Juliana Silva",
      data_nascimento: dataFutura,
      telefone: "11987654321",
      queixa_principal: "Febre e dor",
      tcle_hash: tcleValido64,
      cpf: "11144477735",
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toContain("Data de nascimento não pode ser no futuro");
    }
  });

  it("UT-SCH-05: Rejeita queixa principal menor que 3 caracteres", () => {
    const result = intakeFase1Schema.safeParse({
      nome_completo: "Juliana Silva",
      data_nascimento: "1990-05-15",
      telefone: "11987654321",
      queixa_principal: "oi",
      tcle_hash: tcleValido64,
      cpf: "11144477735",
    });
    expect(result.success).toBe(false);
  });
});

describe("Schema Zod Admissao (Triagem e Entrada na Fila)", () => {
  it("Aceita payload válido de admissão", () => {
    const result = admissaoSchema.safeParse({
      paciente_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
      queixa_principal: "Febre moderada e dor de garganta",
      sintomas: ["febre", "dor_de_garganta"],
      escala_dor: 4,
      tcle_hash: "b".repeat(64),
    });
    expect(result.success).toBe(true);
  });

  it("Rejeita escala de dor fora da faixa 0..10", () => {
    const result = admissaoSchema.safeParse({
      paciente_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
      queixa_principal: "Dor",
      escala_dor: 15,
    });
    expect(result.success).toBe(false);
  });
});

describe("Schema Zod EnrichmentFase2 (Enriquecimento CFM 1.821/2007)", () => {
  it("UT-SCH-06: Aceita payload válido com endereço e CEP sanitizados", () => {
    const result = enrichmentFase2Schema.safeParse({
      paciente_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
      nome_mae: "Maria Aparecida Silva",
      sexo_biologico: "F",
      cep: "01310-100",
      logradouro: "Avenida Paulista",
      numero: "1000",
      bairro: "Bela Vista",
      cidade: "São Paulo",
      estado: "SP",
      alergias: ["Dipirona"],
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.cep).toBe("01310100");
    }
  });

  it("UT-SCH-07: Rejeita nome da mãe com apenas uma palavra ou caracteres inválidos", () => {
    const resultUmaPalavra = enrichmentFase2Schema.safeParse({
      paciente_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
      nome_mae: "Maria",
      sexo_biologico: "F",
      cep: "01310100",
      logradouro: "Avenida Paulista",
      numero: "1000",
      bairro: "Bela Vista",
      cidade: "São Paulo",
      estado: "SP",
    });
    expect(resultUmaPalavra.success).toBe(false);
    if (!resultUmaPalavra.success) {
      expect(resultUmaPalavra.error.issues[0].message).toContain(
        "Informe o nome completo da mãe (ao menos dois nomes)",
      );
    }

    const resultDigitos = enrichmentFase2Schema.safeParse({
      paciente_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
      nome_mae: "Maria Silva 123",
      sexo_biologico: "F",
      cep: "01310100",
      logradouro: "Avenida Paulista",
      numero: "1000",
      bairro: "Bela Vista",
      cidade: "São Paulo",
      estado: "SP",
    });
    expect(resultDigitos.success).toBe(false);
  });

  it("UT-SCH-08: Rejeita CEP com 8 zeros ou formato incorreto", () => {
    const result = enrichmentFase2Schema.safeParse({
      paciente_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
      nome_mae: "Maria Aparecida Silva",
      sexo_biologico: "F",
      cep: "00000-000",
      logradouro: "Avenida Paulista",
      numero: "1000",
      bairro: "Bela Vista",
      cidade: "São Paulo",
      estado: "SP",
    });
    expect(result.success).toBe(false);
  });
});
