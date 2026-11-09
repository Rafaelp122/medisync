import { describe, expect, it } from "vitest";
import {
  assinarDocumentoSchema,
  cfmIdentityGateSchema,
  emitirDocumentoSchema,
  itemPrescricaoSchema,
  soapSchema,
} from "./consultation-schema";

describe("Consultation Schemas (Zod Validation - US-09, US-10, CFM 2.314/2022)", () => {
  describe("soapSchema", () => {
    it("valida com sucesso payload SOAP completo com CID-10 válido", () => {
      const validData = {
        anamnese: "Paciente com dor de garganta há 3 dias e febre 38.5C.",
        exame_fisico_virtual: "Orofaringe hiperemiada com pontos de pus.",
        cid10_principal: "j03.0",
        conduta: "Prescrito antibiótico e repouso domiciliar.",
      };

      const result = soapSchema.safeParse(validData);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.cid10_principal).toBe("J03.0"); // Transformado para maiúsculas
        expect(result.data.anamnese).toBe(validData.anamnese);
      }
    });

    it("rejeita Anamnese vazia ou com menos de 3 caracteres", () => {
      const invalidData = {
        anamnese: "  ",
        conduta: "Repouso e hidratação.",
      };

      const result = soapSchema.safeParse(invalidData);
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.issues[0]?.message).toMatch(/anamnese/i);
      }
    });

    it("rejeita Conduta vazia ou com menos de 3 caracteres", () => {
      const invalidData = {
        anamnese: "Paciente com cefaleia intensa.",
        conduta: "",
      };

      const result = soapSchema.safeParse(invalidData);
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.issues[0]?.message).toMatch(/conduta/i);
      }
    });

    it("rejeita código CID-10 com formato inválido", () => {
      const invalidData = {
        anamnese: "Paciente com sintomas respiratórios.",
        conduta: "Isolamento domiciliar.",
        cid10_principal: "123.4", // Deve iniciar com letra maiúscula
      };

      const result = soapSchema.safeParse(invalidData);
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.issues[0]?.message).toMatch(/cid-10/i);
      }
    });
  });

  describe("itemPrescricaoSchema", () => {
    it("valida item de prescrição com campos obrigatórios", () => {
      const validItem = {
        medicamento: "Amoxicilina 500mg",
        dosagem: "500mg",
        posologia: "1 cápsula de 8 em 8 horas",
        duracao: "7 dias",
        controle_especial: false,
      };

      const result = itemPrescricaoSchema.safeParse(validItem);
      expect(result.success).toBe(true);
    });

    it("rejeita item de prescrição sem posologia", () => {
      const invalidItem = {
        medicamento: "Dipirona 500mg",
        dosagem: "500mg",
        posologia: "",
      };

      const result = itemPrescricaoSchema.safeParse(invalidItem);
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.issues[0]?.message).toMatch(/posologia/i);
      }
    });
  });

  describe("emitirDocumentoSchema", () => {
    it("valida emissão de receita com ao menos um item de medicamento", () => {
      const validDoc = {
        tipo_documento: "RECEITA_SIMPLES",
        itens: [
          {
            medicamento: "Paracetamol 750mg",
            dosagem: "750mg",
            posologia: "1 cp se dor",
            controle_especial: false,
          },
        ],
      };

      const result = emitirDocumentoSchema.safeParse(validDoc);
      expect(result.success).toBe(true);
    });

    it("rejeita emissão de receita com lista vazia de itens", () => {
      const invalidDoc = {
        tipo_documento: "RECEITA_SIMPLES",
        itens: [],
      };

      const result = emitirDocumentoSchema.safeParse(invalidDoc);
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.issues[0]?.message).toMatch(/ao menos um medicamento/i);
      }
    });

    it("valida emissão de atestado médico mesmo com lista vazia de medicamentos", () => {
      const validAtestado = {
        tipo_documento: "ATESTADO_MEDICO",
        itens: [],
        justificativa_tempo_inferior:
          "Consulta rápida com paciente previamente conhecido no ambulatório",
      };

      const result = emitirDocumentoSchema.safeParse(validAtestado);
      expect(result.success).toBe(true);
    });
  });

  describe("assinarDocumentoSchema", () => {
    it("valida payload de assinatura com token PSC", () => {
      const validSign = {
        token: "psc-oauth2-token-valid-12345",
        provider: "birdid",
      };

      const result = assinarDocumentoSchema.safeParse(validSign);
      expect(result.success).toBe(true);
    });

    it("rejeita assinatura com token vazio", () => {
      const invalidSign = {
        token: "   ",
        provider: "birdid",
      };

      const result = assinarDocumentoSchema.safeParse(invalidSign);
      expect(result.success).toBe(false);
    });
  });

  describe("cfmIdentityGateSchema (Conferência Visual CFM 2.314/2022)", () => {
    it("valida conferência quando documento oficial com foto é informado", () => {
      const validGate = {
        identidade_verificada: true,
        tipo_documento_apresentado: "RG",
      };

      const result = cfmIdentityGateSchema.safeParse(validGate);
      expect(result.success).toBe(true);
    });

    it("valida conferência em situação de emergência justificada", () => {
      const validEmergency = {
        identidade_verificada: true,
        tipo_documento_apresentado: null,
        justificativa_excecao: "Paciente inconsciente em estado grave na emergência",
      };

      const result = cfmIdentityGateSchema.safeParse(validEmergency);
      expect(result.success).toBe(true);
    });

    it("rejeita conferência sem documento nem justificativa médica adequada", () => {
      const invalidGate = {
        identidade_verificada: true,
        tipo_documento_apresentado: null,
        justificativa_excecao: "Curto", // Menos de 10 caracteres
      };

      const result = cfmIdentityGateSchema.safeParse(invalidGate);
      expect(result.success).toBe(false);
    });

    it("rejeita quando identidade_verificada é false", () => {
      const unverifiedGate = {
        identidade_verificada: false,
        tipo_documento_apresentado: null,
      };

      const result = cfmIdentityGateSchema.safeParse(unverifiedGate);
      expect(result.success).toBe(false);
    });
  });
});
