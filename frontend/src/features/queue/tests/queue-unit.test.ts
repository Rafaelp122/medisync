import { describe, expect, it } from "vitest";
import {
  formatarPosicaoOrdinal,
  formatarTempoEstimado,
  isWebAuthnSupported,
} from "@/lib/formatters";

describe("Queue Unit Formatters & Helpers", () => {
  describe("formatarTempoEstimado", () => {
    it("deve retornar mensagem padrão quando tempo for nulo ou indefinido", () => {
      expect(formatarTempoEstimado(null)).toBe("Calculando estimativa...");
      expect(formatarTempoEstimado(undefined)).toBe("Calculando estimativa...");
    });

    it("deve retornar menos de 1 minuto para tempos inferiores a 60 segundos", () => {
      expect(formatarTempoEstimado(0)).toBe("Menos de 1 minuto");
      expect(formatarTempoEstimado(45)).toBe("Menos de 1 minuto");
    });

    it("deve formatar minutos corretamente", () => {
      expect(formatarTempoEstimado(60)).toBe("Aproximadamente 1 minuto");
      expect(formatarTempoEstimado(600)).toBe("Aproximadamente 10 minutos");
      expect(formatarTempoEstimado(1800)).toBe("Aproximadamente 30 minutos");
    });

    it("deve formatar horas e minutos quando ultrapassar 60 minutos", () => {
      expect(formatarTempoEstimado(3600)).toBe("Aproximadamente 1 hora");
      expect(formatarTempoEstimado(3660)).toBe("Aproximadamente 1 hora e 1 minuto");
      expect(formatarTempoEstimado(3720)).toBe("Aproximadamente 1 hora e 2 minutos");
      expect(formatarTempoEstimado(7320)).toBe("Aproximadamente 2 horas e 2 minutos");
    });
  });

  describe("formatarPosicaoOrdinal", () => {
    it("deve formatar posição ordinal válida", () => {
      expect(formatarPosicaoOrdinal(1)).toBe("1º na fila");
      expect(formatarPosicaoOrdinal(5)).toBe("5º na fila");
      expect(formatarPosicaoOrdinal(12)).toBe("12º na fila");
    });

    it("deve retornar traço quando a posição for nula ou menor que 1", () => {
      expect(formatarPosicaoOrdinal(null)).toBe("—");
      expect(formatarPosicaoOrdinal(undefined)).toBe("—");
      expect(formatarPosicaoOrdinal(0)).toBe("—");
      expect(formatarPosicaoOrdinal(-1)).toBe("—");
    });
  });

  describe("isWebAuthnSupported", () => {
    it("deve retornar booleano sem lançar exceções", () => {
      const supported = isWebAuthnSupported();
      expect(typeof supported).toBe("boolean");
    });
  });
});
