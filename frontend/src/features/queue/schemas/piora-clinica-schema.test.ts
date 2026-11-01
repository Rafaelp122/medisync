import { describe, expect, it } from "vitest";
import { pioraClinicaFormSchema } from "./piora-clinica-schema";

describe("pioraClinicaFormSchema", () => {
  const validUuid = "11111111-1111-4111-a111-111111111111";

  it("deve validar com sucesso quando houver novos sintomas e escala de dor válida", () => {
    const input = {
      atendimento_id: validUuid,
      escala_dor: 7,
      novos_sintomas: ["falta_de_ar"],
      queixa_adicional: "Dor no peito irradiando para o braço",
    };

    const result = pioraClinicaFormSchema.safeParse(input);
    expect(result.success).toBe(true);
  });

  it("deve rejeitar escala de dor maior que 10 com mensagem amigável", () => {
    const input = {
      atendimento_id: validUuid,
      escala_dor: 15,
      novos_sintomas: ["febre"],
      queixa_adicional: "",
    };

    const result = pioraClinicaFormSchema.safeParse(input);
    expect(result.success).toBe(false);
    if (!result.success) {
      const errorMsg = result.error.issues.find((i) => i.path.includes("escala_dor"))?.message;
      expect(errorMsg).toBe("A escala de dor deve estar entre 0 e 10.");
    }
  });

  it("deve rejeitar quando atendimento_id for UUID inválido", () => {
    const input = {
      atendimento_id: "invalido",
      escala_dor: 5,
      novos_sintomas: ["dor"],
      queixa_adicional: "",
    };

    const result = pioraClinicaFormSchema.safeParse(input);
    expect(result.success).toBe(false);
  });

  it("deve rejeitar quando nenhum sintoma, queixa ou dor for informada", () => {
    const input = {
      atendimento_id: validUuid,
      escala_dor: 0,
      novos_sintomas: [],
      queixa_adicional: "   ",
    };

    const result = pioraClinicaFormSchema.safeParse(input);
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0]?.message).toContain("Informe ao menos um sintoma novo");
    }
  });
});
