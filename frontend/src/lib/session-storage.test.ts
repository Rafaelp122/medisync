import { beforeEach, describe, expect, it } from "vitest";
import type { LiveKitTokenResponse } from "@/api/generated/types.gen";
import {
  clearStoredCallData,
  clearStoredDoctorSession,
  clearStoredManagerSession,
  clearStoredSession,
  getStoredCallData,
  getStoredDoctorSession,
  getStoredManagerSession,
  getStoredSession,
  getStoredToken,
  MEDISYNC_CALL_DATA_KEY,
  MEDISYNC_DOCTOR_SESSION_KEY,
  MEDISYNC_MANAGER_SESSION_KEY,
  MEDISYNC_SESSION_KEY,
  type StoredDoctorSession,
  type StoredManagerSession,
  type StoredPatientSession,
  saveStoredCallData,
  saveStoredDoctorSession,
  saveStoredManagerSession,
  saveStoredSession,
} from "./session-storage";

describe("session-storage", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
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

  const mockDoctorSession: StoredDoctorSession = {
    token: "mock-doctor-jwt-456",
    medicoId: "018f3a5b-med-123",
    medicoNome: "Dr. Eduardo Rocha",
    crmUf: "CRM/SP 123456",
    identificador: "eduardo.rocha",
  };

  const mockManagerSession: StoredManagerSession = {
    token: "mock-manager-jwt-789",
    usuarioId: "018f3a5b-mgr-123",
    nome: "Gestora Maria",
    email: "maria@saude.gov.br",
    papel: "GESTOR_MUNICIPAL",
  };

  const mockCallData: LiveKitTokenResponse = {
    token: "livekit-token-abc",
    server_url: "wss://livekit.medisync.local",
    room_name: "sala-atendimento-123",
    participant_identity: "paciente-juliana",
  };

  describe("Patient Session", () => {
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
      localStorage.setItem(
        MEDISYNC_SESSION_KEY,
        JSON.stringify({ role: "PACIENTE", tipo: "acolhimento" }),
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

  describe("Doctor Session", () => {
    it("UT-DOC-01: deve salvar e recuperar a sessão do médico no localStorage", () => {
      saveStoredDoctorSession(mockDoctorSession);

      const stored = getStoredDoctorSession();
      expect(stored).toEqual(mockDoctorSession);
    });

    it("UT-DOC-02: deve retornar null e limpar o storage se JSON do médico for inválido", () => {
      localStorage.setItem(MEDISYNC_DOCTOR_SESSION_KEY, "invalid-json{{");

      expect(getStoredDoctorSession()).toBeNull();
      expect(localStorage.getItem(MEDISYNC_DOCTOR_SESSION_KEY)).toBeNull();
    });

    it("UT-DOC-03: deve retornar null se campos essenciais do médico estiverem ausentes", () => {
      localStorage.setItem(
        MEDISYNC_DOCTOR_SESSION_KEY,
        JSON.stringify({ medicoNome: "Dr. Teste" }),
      );

      expect(getStoredDoctorSession()).toBeNull();
      expect(localStorage.getItem(MEDISYNC_DOCTOR_SESSION_KEY)).toBeNull();
    });

    it("UT-DOC-04: clearStoredDoctorSession deve purgar atomicamente a sessão do médico", () => {
      saveStoredDoctorSession(mockDoctorSession);
      expect(localStorage.getItem(MEDISYNC_DOCTOR_SESSION_KEY)).not.toBeNull();

      clearStoredDoctorSession();
      expect(localStorage.getItem(MEDISYNC_DOCTOR_SESSION_KEY)).toBeNull();
      expect(getStoredDoctorSession()).toBeNull();
    });
  });

  describe("Manager Session", () => {
    it("UT-MGR-01: deve salvar e recuperar a sessão do gestor no localStorage", () => {
      saveStoredManagerSession(mockManagerSession);

      const stored = getStoredManagerSession();
      expect(stored).toEqual(mockManagerSession);
    });

    it("UT-MGR-02: deve retornar null e limpar o storage se JSON do gestor for inválido", () => {
      localStorage.setItem(MEDISYNC_MANAGER_SESSION_KEY, "corrupt{{");

      expect(getStoredManagerSession()).toBeNull();
      expect(localStorage.getItem(MEDISYNC_MANAGER_SESSION_KEY)).toBeNull();
    });

    it("UT-MGR-03: deve retornar null se campos obrigatórios do gestor faltarem", () => {
      localStorage.setItem(
        MEDISYNC_MANAGER_SESSION_KEY,
        JSON.stringify({ nome: "Gestor Incompleto" }),
      );

      expect(getStoredManagerSession()).toBeNull();
      expect(localStorage.getItem(MEDISYNC_MANAGER_SESSION_KEY)).toBeNull();
    });

    it("UT-MGR-04: clearStoredManagerSession deve purgar atomicamente a sessão do gestor", () => {
      saveStoredManagerSession(mockManagerSession);
      expect(localStorage.getItem(MEDISYNC_MANAGER_SESSION_KEY)).not.toBeNull();

      clearStoredManagerSession();
      expect(localStorage.getItem(MEDISYNC_MANAGER_SESSION_KEY)).toBeNull();
      expect(getStoredManagerSession()).toBeNull();
    });
  });

  describe("Call Data (SessionStorage)", () => {
    it("UT-CALL-01: deve salvar e recuperar dados de conexão LiveKit no sessionStorage", () => {
      saveStoredCallData(mockCallData);

      const stored = getStoredCallData();
      expect(stored).toEqual(mockCallData);
    });

    it("UT-CALL-02: deve retornar null e limpar sessionStorage se JSON de callData for inválido", () => {
      sessionStorage.setItem(MEDISYNC_CALL_DATA_KEY, "bad-json{{");

      expect(getStoredCallData()).toBeNull();
      expect(sessionStorage.getItem(MEDISYNC_CALL_DATA_KEY)).toBeNull();
    });

    it("UT-CALL-03: deve retornar null se token ou server_url faltarem nos dados de chamada", () => {
      sessionStorage.setItem(
        MEDISYNC_CALL_DATA_KEY,
        JSON.stringify({ room_name: "sala-sem-token" }),
      );

      expect(getStoredCallData()).toBeNull();
      expect(sessionStorage.getItem(MEDISYNC_CALL_DATA_KEY)).toBeNull();
    });

    it("UT-CALL-04: clearStoredCallData deve purgar atomicamente a chave do sessionStorage", () => {
      saveStoredCallData(mockCallData);
      expect(sessionStorage.getItem(MEDISYNC_CALL_DATA_KEY)).not.toBeNull();

      clearStoredCallData();
      expect(sessionStorage.getItem(MEDISYNC_CALL_DATA_KEY)).toBeNull();
      expect(getStoredCallData()).toBeNull();
    });
  });
});
