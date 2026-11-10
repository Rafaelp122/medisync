import type { AdmissaoResponse, LiveKitTokenResponse } from "@/api/generated/types.gen";
import { settings } from "@/config/settings";

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

/**
 * Recupera com segurança a sessão persistida no localStorage do navegador.
 * Possui guard clauses contra SSR, parsing corrompido e payload incompleto.
 */
export function getStoredSession(): StoredPatientSession | null {
  if (typeof window === "undefined" || !window.localStorage) {
    return null;
  }

  try {
    const raw = window.localStorage.getItem(MEDISYNC_SESSION_KEY);
    if (!raw) {
      return null;
    }

    const parsed = JSON.parse(raw) as Partial<StoredPatientSession>;

    if (
      !parsed ||
      typeof parsed !== "object" ||
      typeof parsed.token !== "string" ||
      typeof parsed.pacienteId !== "string" ||
      typeof parsed.role !== "string" ||
      (parsed.tipo !== "acolhimento" && parsed.tipo !== "otp") ||
      !parsed.token.trim() ||
      !parsed.pacienteId.trim()
    ) {
      clearStoredSession();
      return null;
    }

    return parsed as StoredPatientSession;
  } catch {
    clearStoredSession();
    return null;
  }
}

/**
 * Persiste a sessão do paciente no localStorage sob a chave canônica medisync_session.
 */
export function saveStoredSession(session: StoredPatientSession): void {
  if (typeof window === "undefined" || !window.localStorage) {
    return;
  }

  try {
    window.localStorage.setItem(MEDISYNC_SESSION_KEY, JSON.stringify(session));
  } catch {
    // Tratamento silencioso para QuotaExceededError em modo anônimo restritivo
  }
}

/**
 * Remove atomicamente a sessão persistida do paciente.
 */
export function clearStoredSession(): void {
  if (typeof window === "undefined" || !window.localStorage) {
    return;
  }

  try {
    window.localStorage.removeItem(MEDISYNC_SESSION_KEY);
  } catch {
    // Ignora erros de storage
  }
}

/**
 * Helper enxuto para extração direta do token de autenticação ativo.
 */
export function getStoredToken(): string | null {
  const session = getStoredSession();
  return session?.token ?? null;
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
}

/**
 * Recupera com segurança a sessão persistida do médico.
 */
export function getStoredDoctorSession(): StoredDoctorSession | null {
  if (typeof window === "undefined" || !window.localStorage) {
    return null;
  }

  try {
    const raw = window.localStorage.getItem(MEDISYNC_DOCTOR_SESSION_KEY);
    if (!raw) {
      return null;
    }

    const parsed = JSON.parse(raw) as Partial<StoredDoctorSession>;
    if (
      !parsed ||
      typeof parsed !== "object" ||
      typeof parsed.medicoId !== "string" ||
      typeof parsed.medicoNome !== "string" ||
      !parsed.medicoId.trim() ||
      !parsed.medicoNome.trim()
    ) {
      clearStoredDoctorSession();
      return null;
    }

    return parsed as StoredDoctorSession;
  } catch {
    clearStoredDoctorSession();
    return null;
  }
}

/**
 * Persiste a sessão do médico no localStorage.
 */
export function saveStoredDoctorSession(session: StoredDoctorSession): void {
  if (typeof window === "undefined" || !window.localStorage) {
    return;
  }

  try {
    window.localStorage.setItem(MEDISYNC_DOCTOR_SESSION_KEY, JSON.stringify(session));
  } catch {
    // Tratamento silencioso para storage restrito
  }
}

/**
 * Remove atomicamente a sessão persistida do médico.
 */
export function clearStoredDoctorSession(): void {
  if (typeof window === "undefined" || !window.localStorage) {
    return;
  }

  try {
    window.localStorage.removeItem(MEDISYNC_DOCTOR_SESSION_KEY);
  } catch {
    // Ignora erros de storage
  }
}

export const MEDISYNC_MANAGER_SESSION_KEY = settings.storage.managerSession;

/**
 * Contrato da sessão do gestor municipal / regulação persistida no navegador.
 */
export interface StoredManagerSession {
  usuarioId: string;
  nome: string;
  email: string;
  papel: string;
}

/**
 * Recupera com segurança a sessão persistida do gestor.
 */
export function getStoredManagerSession(): StoredManagerSession | null {
  if (typeof window === "undefined" || !window.localStorage) {
    return null;
  }

  try {
    const raw = window.localStorage.getItem(MEDISYNC_MANAGER_SESSION_KEY);
    if (!raw) {
      return null;
    }

    const parsed = JSON.parse(raw) as Partial<StoredManagerSession>;
    if (
      !parsed ||
      typeof parsed !== "object" ||
      typeof parsed.usuarioId !== "string" ||
      typeof parsed.email !== "string" ||
      !parsed.usuarioId.trim() ||
      !parsed.email.trim()
    ) {
      clearStoredManagerSession();
      return null;
    }

    return parsed as StoredManagerSession;
  } catch {
    clearStoredManagerSession();
    return null;
  }
}

/**
 * Persiste a sessão do gestor no localStorage.
 */
export function saveStoredManagerSession(session: StoredManagerSession): void {
  if (typeof window === "undefined" || !window.localStorage) {
    return;
  }

  try {
    window.localStorage.setItem(MEDISYNC_MANAGER_SESSION_KEY, JSON.stringify(session));
  } catch {
    // Tratamento silencioso para storage restrito
  }
}

/**
 * Remove atomicamente a sessão persistida do gestor.
 */
export function clearStoredManagerSession(): void {
  if (typeof window === "undefined" || !window.localStorage) {
    return;
  }

  try {
    window.localStorage.removeItem(MEDISYNC_MANAGER_SESSION_KEY);
  } catch {
    // Ignora erros de storage
  }
}

export const MEDISYNC_CALL_DATA_KEY = settings.storage.callData;

/**
 * Recupera dados de conexão WebRTC da chamada ativa persistidos no sessionStorage.
 */
export function getStoredCallData(): LiveKitTokenResponse | null {
  if (typeof window === "undefined" || !window.sessionStorage) {
    return null;
  }

  try {
    const raw = window.sessionStorage.getItem(MEDISYNC_CALL_DATA_KEY);
    if (!raw) {
      return null;
    }

    const parsed = JSON.parse(raw) as Partial<LiveKitTokenResponse>;
    if (!parsed || typeof parsed !== "object" || !parsed.token || !parsed.server_url) {
      clearStoredCallData();
      return null;
    }

    return parsed as LiveKitTokenResponse;
  } catch {
    clearStoredCallData();
    return null;
  }
}

/**
 * Persiste temporariamente os dados de conexão WebRTC no sessionStorage.
 */
export function saveStoredCallData(data: LiveKitTokenResponse): void {
  if (typeof window === "undefined" || !window.sessionStorage) {
    return;
  }

  try {
    window.sessionStorage.setItem(MEDISYNC_CALL_DATA_KEY, JSON.stringify(data));
  } catch {
    // Tratamento silencioso
  }
}

/**
 * Remove atomicamente os dados da chamada encerrada do sessionStorage.
 */
export function clearStoredCallData(): void {
  if (typeof window === "undefined" || !window.sessionStorage) {
    return;
  }

  try {
    window.sessionStorage.removeItem(MEDISYNC_CALL_DATA_KEY);
  } catch {
    // Ignora erros
  }
}
