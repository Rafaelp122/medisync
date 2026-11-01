import { beforeEach, describe, expect, it } from "vitest";
import {
  clearStoredSession,
  getStoredSession,
  getStoredToken,
  MEDISYNC_SESSION_KEY,
  type StoredPatientSession,
  saveStoredSession,
} from "./session-storage";

describe("session-storage", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  const mockSession: StoredPatientSession = {
    token: "mock-jwt-token-123",
    pacienteId: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
    role: "PACIENTE",
    tipo: "acolhimento",
    atendimentoId: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2d",
    prioridadeClinica: 3,
    status: "TRIADO_AGUARDANDO_ELEGIBILIDADE",
  };

  it("UT-SES-01: deve salvar e recuperar a sessão íntegra do localStorage", () => {
    saveStoredSession(mockSession);

    const stored = getStoredSession();
    expect(stored).toEqual(mockSession);
    expect(getStoredToken()).toBe("mock-jwt-token-123");
  });

  it("UT-SES-02: deve retornar null e limpar o storage defensivamente se o JSON estiver corrompido", () => {
    localStorage.setItem(MEDISYNC_SESSION_KEY, "invalid-json{{");

    const stored = getStoredSession();
    expect(stored).toBeNull();
    expect(getStoredToken()).toBeNull();
    expect(localStorage.getItem(MEDISYNC_SESSION_KEY)).toBeNull();
  });

  it("UT-SES-03: deve retornar null e limpar o storage se campos essenciais estiverem ausentes", () => {
    // Falta pacienteId e token
    localStorage.setItem(
      MEDISYNC_SESSION_KEY,
      JSON.stringify({ role: "PACIENTE", tipo: "acolhimento" }),
    );

    const stored = getStoredSession();
    expect(stored).toBeNull();
    expect(localStorage.getItem(MEDISYNC_SESSION_KEY)).toBeNull();
  });

  it("UT-SES-05: deve retornar null e limpar o storage se tipo ou role forem inválidos", () => {
    localStorage.setItem(
      MEDISYNC_SESSION_KEY,
      JSON.stringify({
        token: "tok",
        pacienteId: "pac",
        role: 123,
        tipo: "invalido",
      }),
    );

    const stored = getStoredSession();
    expect(stored).toBeNull();
    expect(localStorage.getItem(MEDISYNC_SESSION_KEY)).toBeNull();
  });

  it("UT-SES-04: clearStoredSession deve purgar atomicamente a chave do storage", () => {
    saveStoredSession(mockSession);
    expect(localStorage.getItem(MEDISYNC_SESSION_KEY)).not.toBeNull();

    clearStoredSession();
    expect(localStorage.getItem(MEDISYNC_SESSION_KEY)).toBeNull();
    expect(getStoredSession()).toBeNull();
    expect(getStoredToken()).toBeNull();
  });
});
