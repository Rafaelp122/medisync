import { beforeEach, describe, expect, it } from "vitest";
import { clearAccessToken, getAccessToken, setAccessToken } from "./auth-token";

describe("auth-token (Volatile Memory Token Store)", () => {
  beforeEach(() => {
    clearAccessToken();
    localStorage.clear();
    sessionStorage.clear();
  });

  it("UT-MEM-01: setAccessToken armazena token em memória volátil e getAccessToken recupera", () => {
    setAccessToken("test-jwt-access-token-123");
    expect(getAccessToken()).toBe("test-jwt-access-token-123");

    // Garante que o token NÃO vazou para localStorage ou sessionStorage (OWASP ASVS V3.5.2)
    expect(localStorage.getItem("token")).toBeNull();
    expect(localStorage.getItem("access_token")).toBeNull();
    expect(sessionStorage.getItem("token")).toBeNull();
  });

  it("UT-MEM-02: clearAccessToken limpa atomicamente o token da memória", () => {
    setAccessToken("test-jwt-access-token-123");
    expect(getAccessToken()).toBe("test-jwt-access-token-123");

    clearAccessToken();
    expect(getAccessToken()).toBeNull();
  });

  it("UT-MEM-03: setAccessToken com string vazia ou nula normaliza para null", () => {
    setAccessToken("   ");
    expect(getAccessToken()).toBeNull();

    setAccessToken(null);
    expect(getAccessToken()).toBeNull();
  });
});
