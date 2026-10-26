import { describe, expect, it } from "vitest";
import {
  formatarTelefoneE164,
  limparDigitos,
  mascararTelefoneBR,
  validarTelefoneCelularBR,
} from "./validators";

describe("Validadores de Telefone Celular BR", () => {
  it("UT-01: Celular válido com DDD e 11 dígitos numéricos", () => {
    expect(validarTelefoneCelularBR("11987654321")).toBe(true);
  });

  it("UT-02: Celular formatado com máscara válida", () => {
    expect(validarTelefoneCelularBR("(11) 98765-4321")).toBe(true);
  });

  it("UT-03: Celulares válidos de outros estados", () => {
    expect(validarTelefoneCelularBR("(21) 98888-7777")).toBe(true);
    expect(validarTelefoneCelularBR("(85) 99999-0000")).toBe(true);
  });

  it("UT-04: Telefone fixo com 10 dígitos rejeitado", () => {
    expect(validarTelefoneCelularBR("1133334444")).toBe(false);
  });

  it("UT-05: Telefone celular sem nono dígito 9 rejeitado", () => {
    expect(validarTelefoneCelularBR("11887654321")).toBe(false);
  });

  it("UT-06: DDDs inválidos ou inexistentes rejeitados", () => {
    expect(validarTelefoneCelularBR("(00) 98765-4321")).toBe(false);
    expect(validarTelefoneCelularBR("(20) 98765-4321")).toBe(false);
    expect(validarTelefoneCelularBR("(01) 98765-4321")).toBe(false);
  });

  it("UT-07: Telefone incompleto/truncado rejeitado", () => {
    expect(validarTelefoneCelularBR("119876")).toBe(false);
    expect(validarTelefoneCelularBR("")).toBe(false);
  });

  it("UT-08: Sanitização estrita de caracteres (limparDigitos)", () => {
    expect(limparDigitos("(11) 98765-4321")).toBe("11987654321");
    expect(limparDigitos("+55 (11) 98765-4321")).toBe("5511987654321");
    expect(limparDigitos("abc-123.456")).toBe("123456");
  });

  it("UT-09: Máscara dinâmica progressiva durante digitação (mascararTelefoneBR)", () => {
    expect(mascararTelefoneBR("1")).toBe("(1");
    expect(mascararTelefoneBR("11")).toBe("(11");
    expect(mascararTelefoneBR("119")).toBe("(11) 9");
    expect(mascararTelefoneBR("1198765")).toBe("(11) 9876-5");
    expect(mascararTelefoneBR("11987654321")).toBe("(11) 98765-4321");
  });

  it("Formatação E.164 brasileira (+55)", () => {
    expect(formatarTelefoneE164("(11) 98765-4321")).toBe("+5511987654321");
    expect(formatarTelefoneE164("11987654321")).toBe("+5511987654321");
  });
});
