import { describe, expect, it } from "vitest";
import { solicitarOtpSchema, verificarOtpSchema } from "./onboarding-schema";

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
