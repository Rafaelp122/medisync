import { describe, expect, it } from "vitest";
import {
  calcularHashTcle,
  formatarTelefoneE164,
  limparDigitos,
  mascararCEP,
  mascararCNS,
  mascararCPF,
  mascararTelefoneBR,
  validarCEP,
  validarCNS,
  validarCPF,
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

describe("Validadores de CPF (Algoritmo Módulo 11 - RFC mod-11)", () => {
  it("UT-VAL-01: CPF válido formatado e não formatado", () => {
    expect(validarCPF("111.444.777-35")).toBe(true);
    expect(validarCPF("11144477735")).toBe(true);
    expect(validarCPF("529.982.247-25")).toBe(true);
    expect(validarCPF("52998224725")).toBe(true);
  });

  it("UT-VAL-03: CPF com todos dígitos iguais rejeitado", () => {
    expect(validarCPF("111.111.111-11")).toBe(false);
    expect(validarCPF("000.000.000-00")).toBe(false);
    expect(validarCPF("99999999999")).toBe(false);
  });

  it("UT-VAL-04: CPF com 1º DV inválido rejeitado", () => {
    expect(validarCPF("111.444.777-95")).toBe(false);
  });

  it("UT-VAL-05: CPF com 2º DV inválido rejeitado", () => {
    expect(validarCPF("111.444.777-39")).toBe(false);
  });

  it("UT-VAL-06: CPF com tamanho incorreto ou caracteres insuficientes rejeitado", () => {
    expect(validarCPF("123456")).toBe(false);
    expect(validarCPF("111444777350")).toBe(false);
    expect(validarCPF("")).toBe(false);
  });

  it("UT-VAL-07: Máscara dinâmica progressiva de CPF (mascararCPF)", () => {
    expect(mascararCPF("1")).toBe("1");
    expect(mascararCPF("111")).toBe("111");
    expect(mascararCPF("1114")).toBe("111.4");
    expect(mascararCPF("1114447")).toBe("111.444.7");
    expect(mascararCPF("1114447773")).toBe("111.444.777-3");
    expect(mascararCPF("11144477735")).toBe("111.444.777-35");
  });
});

describe("Validadores de CNS (Cartão Nacional de Saúde - DATASUS)", () => {
  it("UT-VAL-08: CNS definitivo válido (inicia com 1 ou 2)", () => {
    // 166070708560003 ou similar
    // Vamos testar algoritmo com dígitos conhecidos
    // 100000000000000: soma = 1*15 = 15; resto = 4; dv = 11-4 = 7 -> 10000000000 000 7
    // int_digits[:11] = 1,0,0,0,0,0,0,0,0,0,0; soma = 1*15 = 15; resto = 15 % 11 = 4; dv = 7 -> "100000000000007"
    expect(validarCNS("100000000000007")).toBe(true);
    expect(validarCNS("100 0000 0000 0007")).toBe(true);
    // Caso com dv == 10:
    // int_digits[:11] tal que soma % 11 == 1: dv = 10 -> dv_alt com (soma+2) % 11 = 3 -> dv_alt = 8 -> sufixo 0018
    // soma = 12: ex: digitos "10000000000" dá 15 % 11 = 4;
  });

  it("UT-VAL-09: CNS provisório válido (inicia com 7, 8 ou 9)", () => {
    // soma total ponderada % 11 == 0
    // "700000000000005": 7*15 + 5*1 = 105 + 5 = 110 % 11 == 0
    expect(validarCNS("700000000000005")).toBe(true);
    // 8*15 = 120; 120 + 1 = 121 (múltiplo de 11) -> 800000000000001
    expect(validarCNS("800000000000001")).toBe(true);
    // 8*15 + 2*1 = 122 % 11 != 0 -> inválido
    expect(validarCNS("800000000000002")).toBe(false);
  });

  it("UT-VAL-10: CNS com primeiro dígito inválido rejeitado", () => {
    expect(validarCNS("300000000000000")).toBe(false);
    expect(validarCNS("400000000000000")).toBe(false);
    expect(validarCNS("000000000000000")).toBe(false);
  });

  it("UT-VAL-11: CNS com tamanho diferente de 15 dígitos rejeitado", () => {
    expect(validarCNS("70000000000000")).toBe(false);
    expect(validarCNS("7000000000000050")).toBe(false);
    expect(validarCNS("")).toBe(false);
  });

  it("Máscara dinâmica progressiva de CNS (mascararCNS)", () => {
    expect(mascararCNS("7")).toBe("7");
    expect(mascararCNS("7000")).toBe("700 0");
    expect(mascararCNS("70000000")).toBe("700 0000 0");
    expect(mascararCNS("700000000000005")).toBe("700 0000 0000 0005");
  });
});

describe("Validadores de CEP", () => {
  it("UT-VAL-12: CEP válido de 8 dígitos", () => {
    expect(validarCEP("01310-100")).toBe(true);
    expect(validarCEP("01310100")).toBe(true);
    expect(validarCEP("70040-010")).toBe(true);
  });

  it("UT-VAL-13: CEP com 8 zeros rejeitado", () => {
    expect(validarCEP("00000-000")).toBe(false);
    expect(validarCEP("00000000")).toBe(false);
  });

  it("CEP com tamanho incorreto rejeitado", () => {
    expect(validarCEP("0131010")).toBe(false);
    expect(validarCEP("013101000")).toBe(false);
    expect(validarCEP("")).toBe(false);
  });

  it("UT-VAL-14: Máscara dinâmica progressiva de CEP (mascararCEP)", () => {
    expect(mascararCEP("0")).toBe("0");
    expect(mascararCEP("01310")).toBe("01310");
    expect(mascararCEP("013101")).toBe("01310-1");
    expect(mascararCEP("01310100")).toBe("01310-100");
  });
});

describe("Cálculo de Hash SHA-256 do TCLE (Web Crypto API)", () => {
  it("UT-VAL-15: Gera 64 caracteres hexadecimais correspondentes ao SHA-256 canônico", async () => {
    const texto = "Termo de Consentimento Livre e Esclarecido - MediSync Express";
    const hash = await calcularHashTcle(texto);
    expect(hash).toHaveLength(64);
    expect(/^[0-9a-f]{64}$/.test(hash)).toBe(true);
  });

  it("UT-VAL-16: Efeito avalanche no Hash TCLE", async () => {
    const texto1 = "Termo de consentimento telemedicina versao 1";
    const texto2 = "Termo de consentimento telemedicina versao 2";
    const hash1 = await calcularHashTcle(texto1);
    const hash2 = await calcularHashTcle(texto2);
    expect(hash1).not.toBe(hash2);
    expect(hash1).toHaveLength(64);
    expect(hash2).toHaveLength(64);
  });
});
