import { describe, expect, it } from "vitest";
import {
  admissaoSchema,
  clinicalTriageFormSchema,
  enrichmentFase2Schema,
  intakeFase1FormSchema,
  intakeFase1Schema,
} from "./onboarding-schema";

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

describe("Schemas de Formulário de Triagem sem dummy TCLE", () => {
  it("UT-SCH-09: clinicalTriageFormSchema exige aceite real do TCLE (true)", () => {
    const rejected = clinicalTriageFormSchema.safeParse({
      queixa_principal: "Febre alta há 2 dias",
      sintomas: ["febre"],
      escala_dor: 5,
      aceite_tcle: false,
    });
    expect(rejected.success).toBe(false);

    const accepted = clinicalTriageFormSchema.safeParse({
      queixa_principal: "Febre alta há 2 dias",
      sintomas: ["febre"],
      escala_dor: 5,
      aceite_tcle: true,
    });
    expect(accepted.success).toBe(true);
  });

  it("UT-SCH-10: intakeFase1FormSchema aceita nome_social opcional e valida aceite_tcle", () => {
    const result = intakeFase1FormSchema.safeParse({
      nome_completo: "Juliana Silva",
      nome_social: "Júlia Silva",
      data_nascimento: "1990-05-15",
      telefone: "(11) 98765-4321",
      cpf: "52998224725",
      queixa_principal: "Febre alta e dor",
      aceite_tcle: true,
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.nome_social).toBe("Júlia Silva");
    }
  });
});
