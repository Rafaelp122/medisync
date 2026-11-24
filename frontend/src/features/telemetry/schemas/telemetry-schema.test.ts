import { describe, expect, it } from "vitest";
import { configPlantaoFormSchema } from "./telemetry-schema";

const validBasePayload = {
  medicos_ativos_planejados: 3,
  alpha_backpressure: 1.25,
  cota_diaria_maxima: 100,
  tma_padrao_segundos: 600,
  tempo_tolerancia_ring_segundos: 45,
  modo_operacao: "SUS" as const,
  sla_minutos_nivel_1: 0,
  sla_minutos_nivel_2: 10,
  sla_minutos_nivel_3: 60,
  sla_minutos_nivel_4: 120,
  sla_minutos_nivel_5: 240,
};

describe("telemetry-schema (configPlantaoFormSchema)", () => {
  it("aceita cota_diaria_maxima: null (Cota Livre SUS) e os 11 campos completos", () => {
    const result = configPlantaoFormSchema.safeParse({
      ...validBasePayload,
      cota_diaria_maxima: null,
    });

    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.cota_diaria_maxima).toBeNull();
      expect(result.data.tempo_tolerancia_ring_segundos).toBe(45);
      expect(result.data.sla_minutos_nivel_5).toBe(240);
    }
  });

  it("rejeita cota_diaria_maxima <= 0, ring < 10s, alpha fora de 1.20..1.30 e SLA negativo", () => {
    expect(
      configPlantaoFormSchema.safeParse({ ...validBasePayload, cota_diaria_maxima: 0 }).success,
    ).toBe(false);
    expect(
      configPlantaoFormSchema.safeParse({
        ...validBasePayload,
        tempo_tolerancia_ring_segundos: 5,
      }).success,
    ).toBe(false);
    expect(
      configPlantaoFormSchema.safeParse({ ...validBasePayload, alpha_backpressure: 1.45 }).success,
    ).toBe(false);
    expect(
      configPlantaoFormSchema.safeParse({ ...validBasePayload, sla_minutos_nivel_3: -1 }).success,
    ).toBe(false);
  });
});
