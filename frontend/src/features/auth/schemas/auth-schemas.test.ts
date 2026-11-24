import { describe, expect, it } from "vitest";
import * as authSchemas from "./auth-schemas";
import { doctorLoginSchema, managerLoginSchema, mfaVerifySchema } from "./auth-schemas";

describe("auth-schemas (alinhamento estrito snake_case OpenAPI)", () => {
  it("mfaVerifySchema exige temp_token (>=10 chars) e codigo TOTP de 6 dígitos em snake_case", () => {
    expect(
      mfaVerifySchema.safeParse({
        temp_token: "temp-token-12345",
        codigo: "123456",
      }).success,
    ).toBe(true);

    expect(
      mfaVerifySchema.safeParse({
        temp_token: "curto",
        codigo: "123456",
      }).success,
    ).toBe(false);

    expect(
      mfaVerifySchema.safeParse({
        temp_token: "temp-token-12345",
        codigo: "123",
      }).success,
    ).toBe(false);
  });

  it("doctorLoginSchema e managerLoginSchema rejeitam campos obrigatórios ausentes", () => {
    expect(doctorLoginSchema.safeParse({ crm: "123456", uf: "sp", senha: "" }).success).toBe(false);
    expect(managerLoginSchema.safeParse({ email: "invalido", senha: "Gestor@2026" }).success).toBe(
      false,
    );
    expect(
      managerLoginSchema.safeParse({
        email: "gestor@unidade.saude.gov.br",
        senha: "Gestor@2026",
      }).success,
    ).toBe(true);
  });

  it("não exporta mais cadsusAuthSchema legado com campos frouxos", () => {
    expect("cadsusAuthSchema" in authSchemas).toBe(false);
  });
});
