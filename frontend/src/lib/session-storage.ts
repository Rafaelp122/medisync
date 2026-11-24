import type { AdmissaoResponse, LiveKitTokenResponse } from "@/api/generated/types.gen";
import { settings } from "@/config/settings";

export interface StorageSlot<T> {
  get: () => T | null;
  save: (value: T) => void;
  clear: () => void;
}

export interface CreateStorageSlotOptions<T> {
  key: string;
  storage: () => Storage | null;
  isValid: (parsed: Partial<T>) => parsed is T;
}

/**
 * Cria um slot tipado de Web Storage com proteção SSR, parsing seguro e limpeza defensiva.
 */
export function createStorageSlot<T>({
  key,
  storage,
  isValid,
}: CreateStorageSlotOptions<T>): StorageSlot<T> {
  const clear = (): void => {
    const store = storage();
    if (!store) return;
    try {
      store.removeItem(key);
    } catch {
      // Ignora erros de storage restrito
    }
  };

  const get = (): T | null => {
    const store = storage();
    if (!store) return null;

    try {
      const raw = store.getItem(key);
      if (!raw) return null;

      const parsed = JSON.parse(raw) as Partial<T>;
      if (!parsed || typeof parsed !== "object" || !isValid(parsed)) {
        clear();
        return null;
      }

      return parsed;
    } catch {
      clear();
      return null;
    }
  };

  const save = (value: T): void => {
    const store = storage();
    if (!store) return;
    try {
      store.setItem(key, JSON.stringify(value));
    } catch {
      // Tratamento silencioso para QuotaExceededError em modo anônimo restritivo
    }
  };

  return { get, save, clear };
}

function getLocalStorage(): Storage | null {
  if (typeof window === "undefined" || !window.localStorage) return null;
  return window.localStorage;
}

function getSessionStorage(): Storage | null {
  if (typeof window === "undefined" || !window.sessionStorage) return null;
  return window.sessionStorage;
}

export const MEDISYNC_SESSION_KEY = settings.storage.patientSession;

/**
 * Contrato canônico da sessão do paciente persistida no navegador.
 * Regras: US-01, US-02 e ADR-011 (Zero DTO Duplication derivado de OpenAPI).
 */
export interface StoredPatientSession {
  token: string;
  pacienteId: string;
  role: string;
  tipo: "acolhimento" | "otp";
  atendimentoId?: AdmissaoResponse["atendimento_id"];
  prioridadeClinica?: AdmissaoResponse["prioridade_clinica"];
  status?: AdmissaoResponse["status_atendimento"];
}

const patientSessionSlot = createStorageSlot<StoredPatientSession>({
  key: MEDISYNC_SESSION_KEY,
  storage: getLocalStorage,
  isValid: (parsed): parsed is StoredPatientSession =>
    typeof parsed.token === "string" &&
    typeof parsed.pacienteId === "string" &&
    typeof parsed.role === "string" &&
    (parsed.tipo === "acolhimento" || parsed.tipo === "otp") &&
    parsed.token.trim().length > 0 &&
    parsed.pacienteId.trim().length > 0,
});

export const getStoredSession = (): StoredPatientSession | null => patientSessionSlot.get();
export const saveStoredSession = (session: StoredPatientSession): void =>
  patientSessionSlot.save(session);
export const clearStoredSession = (): void => patientSessionSlot.clear();

export function getStoredToken(): string | null {
  return getStoredSession()?.token ?? null;
}

/**
 * Verifica estruturalmente se um token de sessão possui formato JWT de 3 segmentos (header.payload.signature).
 * Tokens de acolhimento (intake_token) possuem apenas 2 segmentos (payload.sig).
 * @see docs/user-stories/US-01-acolhimento-triagem-tcle.md
 */
export function isThreePartJwt(token?: string | null): boolean {
  if (!token) return false;
  const parts = token.trim().split(".");
  return parts.length === 3 && parts.every((part) => part.length > 0);
}

export const MEDISYNC_DOCTOR_SESSION_KEY = settings.storage.doctorSession;

/**
 * Contrato da sessão do médico plantonista persistida no navegador.
 */
export interface StoredDoctorSession {
  medicoId: string;
  medicoNome: string;
  crmUf: string;
  identificador: string;
  papel?: string;
}

const doctorSessionSlot = createStorageSlot<StoredDoctorSession>({
  key: MEDISYNC_DOCTOR_SESSION_KEY,
  storage: getLocalStorage,
  isValid: (parsed): parsed is StoredDoctorSession =>
    typeof parsed.medicoId === "string" &&
    typeof parsed.medicoNome === "string" &&
    parsed.medicoId.trim().length > 0 &&
    parsed.medicoNome.trim().length > 0,
});

export const getStoredDoctorSession = (): StoredDoctorSession | null => doctorSessionSlot.get();
export const saveStoredDoctorSession = (session: StoredDoctorSession): void =>
  doctorSessionSlot.save(session);
export const clearStoredDoctorSession = (): void => doctorSessionSlot.clear();

export const MEDISYNC_MANAGER_SESSION_KEY = settings.storage.managerSession;

/**
 * Contrato da sessão do gestor da unidade persistida no navegador.
 */
export interface StoredManagerSession {
  usuarioId: string;
  nome: string;
  email: string;
  papel: string;
}

const managerSessionSlot = createStorageSlot<StoredManagerSession>({
  key: MEDISYNC_MANAGER_SESSION_KEY,
  storage: getLocalStorage,
  isValid: (parsed): parsed is StoredManagerSession =>
    typeof parsed.usuarioId === "string" &&
    typeof parsed.email === "string" &&
    typeof parsed.papel === "string" &&
    parsed.usuarioId.trim().length > 0 &&
    parsed.email.trim().length > 0 &&
    parsed.papel.trim().length > 0,
});

export const getStoredManagerSession = (): StoredManagerSession | null => managerSessionSlot.get();
export const saveStoredManagerSession = (session: StoredManagerSession): void =>
  managerSessionSlot.save(session);
export const clearStoredManagerSession = (): void => managerSessionSlot.clear();

export const MEDISYNC_CALL_DATA_KEY = settings.storage.callData;

const callDataSlot = createStorageSlot<LiveKitTokenResponse>({
  key: MEDISYNC_CALL_DATA_KEY,
  storage: getSessionStorage,
  isValid: (parsed): parsed is LiveKitTokenResponse =>
    typeof parsed.token === "string" &&
    typeof parsed.server_url === "string" &&
    parsed.token.trim().length > 0 &&
    parsed.server_url.trim().length > 0,
});

export const getStoredCallData = (): LiveKitTokenResponse | null => callDataSlot.get();
export const saveStoredCallData = (data: LiveKitTokenResponse): void => callDataSlot.save(data);
export const clearStoredCallData = (): void => callDataSlot.clear();
