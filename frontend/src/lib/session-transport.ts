import { settings } from "@/config/settings";
import {
  clearStoredCallData,
  clearStoredDoctorSession,
  clearStoredManagerSession,
  clearStoredSession,
  getStoredDoctorSession,
  getStoredManagerSession,
  getStoredSession,
  getStoredToken,
  type StoredDoctorSession,
  type StoredManagerSession,
  type StoredPatientSession,
  saveStoredDoctorSession,
  saveStoredManagerSession,
  saveStoredSession,
} from "@/lib/session-storage";

export type StaffRole = "MEDICO" | "GESTOR_UNIDADE";

export type StaffSession =
  | {
      role: "MEDICO";
      doctorSession: StoredDoctorSession;
    }
  | {
      role: "GESTOR_UNIDADE";
      managerSession: StoredManagerSession;
    };

export type ActivateStaffSessionParams =
  | { role: "MEDICO"; token: string; session: StoredDoctorSession }
  | { role: "GESTOR_UNIDADE"; token: string; session: StoredManagerSession };

export interface SessionTransport {
  ensureStaffSession(role: StaffRole): Promise<StaffSession>;
  activatePatientSession(session: StoredPatientSession): void;
  clearSession(scope?: "patient" | "staff" | "all"): void;
  getQueryScope(): string;
  subscribeInvalidated(listener: () => void): () => void;
}

const REFRESH_TIMEOUT_MS = 10_000;

function decodeJwtPayload(token?: string | null): Record<string, unknown> | undefined {
  if (!token || typeof token !== "string") return undefined;
  const parts = token.split(".");
  if (parts.length < 2 || !parts[1]) return undefined;
  try {
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), "=");
    const parsed: unknown = JSON.parse(atob(padded));
    if (parsed && typeof parsed === "object") {
      return parsed as Record<string, unknown>;
    }
  } catch {
    return undefined;
  }
  return undefined;
}

function extractJwtRole(token?: string | null): string | undefined {
  const payload = decodeJwtPayload(token);
  const rawRole = payload?.papel ?? payload?.role;
  return typeof rawRole === "string" && rawRole.trim() ? rawRole.trim() : undefined;
}

function hashTokenFingerprint(value: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < value.length; i += 1) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

function createRefreshTimeoutSignal(): AbortSignal | undefined {
  if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function") {
    return AbortSignal.timeout(REFRESH_TIMEOUT_MS);
  }
  return undefined;
}

export interface SessionTransportController extends SessionTransport {
  activateStaffSession(params: ActivateStaffSessionParams): void;
  getVolatileStaffToken(): string | null;
  setVolatileStaffToken(token: string | null): void;
  getActiveBearerToken(): string | null;
  hasCorporateSession(): boolean;
  silentRefreshToken(): Promise<string | null>;
}

/**
 * Cria instância coesa de transporte de sessão, isolando o access token corporativo
 * em closure privada de memória, gerenciando silent refresh com mutex, escopo de cache
 * TanStack Query e validação estrita de papel corporativo.
 *
 * Regras: ADR-011, RN-AUT-05, RN-AUT-07, OWASP ASVS v4.0 (V3.5.2).
 */
export function createSessionTransport(
  baseUrl: string = settings.env.apiBaseUrl,
): SessionTransportController {
  let inMemoryStaffToken: string | null = null;
  let refreshPromise: Promise<string | null> | null = null;
  const invalidatedListeners = new Set<() => void>();

  const notifyInvalidated = () => {
    for (const listener of invalidatedListeners) {
      listener();
    }
  };

  const setVolatileStaffToken = (token: string | null): void => {
    if (token && typeof token === "string" && token.trim().length > 0) {
      inMemoryStaffToken = token.trim();
    } else {
      inMemoryStaffToken = null;
    }
  };

  const getVolatileStaffToken = (): string | null => inMemoryStaffToken;

  const getActiveBearerToken = (): string | null => {
    return inMemoryStaffToken || getStoredToken();
  };

  const hasCorporateSession = (): boolean => {
    if (inMemoryStaffToken) {
      const jwtRole = extractJwtRole(inMemoryStaffToken);
      return jwtRole !== "PACIENTE";
    }
    if (getStoredToken()) {
      return false;
    }
    return Boolean(getStoredDoctorSession() || getStoredManagerSession());
  };

  const clearSession = (scope: "patient" | "staff" | "all" = "all"): void => {
    if (scope === "patient" || scope === "all") {
      clearStoredSession();
      clearStoredCallData();
    }
    if (scope === "staff" || scope === "all") {
      inMemoryStaffToken = null;
      clearStoredDoctorSession();
      clearStoredManagerSession();
    }
    notifyInvalidated();
  };

  const silentRefreshToken = async (): Promise<string | null> => {
    if (refreshPromise) {
      return refreshPromise;
    }

    refreshPromise = (async () => {
      try {
        const refreshUrl = `${baseUrl.replace(/\/+$/, "")}/api/v1/auth/refresh`;
        const signal = createRefreshTimeoutSignal();
        const res = await fetch(refreshUrl, {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({}),
          ...(signal ? { signal } : {}),
        });

        if (!res.ok) {
          clearSession("staff");
          return null;
        }

        const data = (await res.json()) as { access_token?: string };
        if (data.access_token && data.access_token.trim().length > 0) {
          setVolatileStaffToken(data.access_token);
          return inMemoryStaffToken;
        }
        clearSession("staff");
        return null;
      } catch {
        clearSession("staff");
        return null;
      } finally {
        refreshPromise = null;
      }
    })();

    return refreshPromise;
  };

  const ensureStaffSession = async (role: StaffRole): Promise<StaffSession> => {
    if (role === "MEDICO") {
      const doctorSession = getStoredDoctorSession();
      if (!doctorSession) {
        throw new Error("Sessão médica ausente.");
      }
      if (doctorSession.papel && doctorSession.papel !== "MEDICO") {
        clearSession("staff");
        throw new Error(`Papel '${doctorSession.papel}' não autorizado para /medico.`);
      }

      const token = inMemoryStaffToken ?? (await silentRefreshToken());
      if (!token) {
        clearSession("staff");
        throw new Error("Sessão médica expirada.");
      }

      const jwtRole = extractJwtRole(token);
      if (jwtRole && jwtRole !== "MEDICO") {
        clearSession("staff");
        throw new Error(`Token com papel '${jwtRole}' não autorizado para /medico.`);
      }

      return { role: "MEDICO", doctorSession };
    }

    const managerSession = getStoredManagerSession();
    if (!managerSession) {
      throw new Error("Sessão de gestão ausente.");
    }
    if (managerSession.papel !== "GESTOR_UNIDADE") {
      clearSession("staff");
      throw new Error(`Papel '${managerSession.papel}' não autorizado para /gestor.`);
    }

    const token = inMemoryStaffToken ?? (await silentRefreshToken());
    if (!token) {
      clearSession("staff");
      throw new Error("Sessão de gestão expirada.");
    }

    const jwtRole = extractJwtRole(token);
    if (jwtRole && jwtRole !== "GESTOR_UNIDADE") {
      clearSession("staff");
      throw new Error(`Token com papel '${jwtRole}' não autorizado para /gestor.`);
    }

    return { role: "GESTOR_UNIDADE", managerSession };
  };

  const activatePatientSession = (session: StoredPatientSession): void => {
    inMemoryStaffToken = null;
    clearStoredDoctorSession();
    clearStoredManagerSession();
    saveStoredSession(session);
  };

  const activateStaffSession = (params: ActivateStaffSessionParams): void => {
    clearStoredSession();
    clearStoredCallData();
    setVolatileStaffToken(params.token);
    if (params.role === "MEDICO") {
      clearStoredManagerSession();
      saveStoredDoctorSession({ ...params.session, papel: params.session.papel ?? "MEDICO" });
    } else {
      clearStoredDoctorSession();
      saveStoredManagerSession(params.session);
    }
  };

  const getQueryScope = (): string => {
    const activeToken = getActiveBearerToken();
    const patientSession = getStoredSession();
    const doctorSession = getStoredDoctorSession();
    const managerSession = getStoredManagerSession();
    const payload = decodeJwtPayload(activeToken);
    const jwtSub = typeof payload?.sub === "string" ? payload.sub.trim() : "";

    if (jwtSub) {
      return `sub:${jwtSub}`;
    }
    if (patientSession?.pacienteId && !inMemoryStaffToken) {
      return `pac:${patientSession.pacienteId}`;
    }
    if (doctorSession?.medicoId) {
      return `med:${doctorSession.medicoId}`;
    }
    if (managerSession?.usuarioId) {
      return `mgr:${managerSession.usuarioId}`;
    }
    if (activeToken) {
      return `tok:${hashTokenFingerprint(activeToken)}`;
    }

    return "anon";
  };

  const subscribeInvalidated = (listener: () => void): (() => void) => {
    invalidatedListeners.add(listener);
    return () => {
      invalidatedListeners.delete(listener);
    };
  };

  return {
    ensureStaffSession,
    activatePatientSession,
    activateStaffSession,
    clearSession,
    getQueryScope,
    subscribeInvalidated,
    getVolatileStaffToken,
    setVolatileStaffToken,
    getActiveBearerToken,
    hasCorporateSession,
    silentRefreshToken,
  };
}

export const sessionTransport: SessionTransportController = createSessionTransport();
