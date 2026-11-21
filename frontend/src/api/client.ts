import { settings } from "@/config/settings";
import { clearAccessToken, getAccessToken, setAccessToken } from "@/lib/auth-token";
import {
  clearStoredDoctorSession,
  clearStoredManagerSession,
  clearStoredSession,
  getStoredDoctorSession,
  getStoredSession,
  getStoredToken,
} from "@/lib/session-storage";
import { toProblemDetailsError } from "./errors";
import { client } from "./generated/client.gen";

const baseUrl = settings.env.apiBaseUrl;

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

function hashTokenFingerprint(value: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < value.length; i += 1) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

/**
 * Retorna cabeçalho Authorization explícito apenas quando o caller fornece
 * um token distinto do armazenado em memória/localStorage; caso contrário delega ao interceptor.
 */
export function resolveExplicitAuthHeaders(token?: string): Record<string, string> | undefined {
  const explicit = token?.trim();
  if (!explicit) return undefined;
  const current = getAccessToken() || getStoredToken();
  if (explicit === current) return undefined;
  return { Authorization: `Bearer ${explicit}` };
}

/**
 * Deriva chave de escopo (identidade/sessão) para isolar entradas do TanStack Query.
 */
export function getSessionQueryScope(explicitToken?: string): string {
  const trimmedExplicit = explicitToken?.trim();
  const activeToken = trimmedExplicit || getAccessToken() || getStoredToken();

  const patientSession = getStoredSession();
  const doctorSession = getStoredDoctorSession();
  const payload = decodeJwtPayload(activeToken);
  const jwtSub = typeof payload?.sub === "string" ? payload.sub.trim() : "";

  if (jwtSub) {
    return `sub:${jwtSub}`;
  }
  if (
    patientSession?.pacienteId &&
    (!trimmedExplicit || trimmedExplicit === patientSession.token)
  ) {
    return `pac:${patientSession.pacienteId}`;
  }
  if (doctorSession?.medicoId && (!trimmedExplicit || trimmedExplicit === getAccessToken())) {
    return `med:${doctorSession.medicoId}`;
  }
  if (activeToken) {
    return `tok:${hashTokenFingerprint(activeToken)}`;
  }

  return "anon";
}

client.setConfig({
  baseUrl,
  credentials: "include",
});

let refreshPromise: Promise<string | null> | null = null;
const retryRequestClones = new WeakMap<Request, Request>();

/**
 * Executa o silent refresh de forma coordenada via Promise compartilhada (mutex anti-concorrência).
 * Utiliza o cookie HttpOnly refresh_token gerenciado pelo navegador.
 * Regras: RN-AUT-05, RN-AUT-07, OWASP ASVS v4.0 (V3.5.2).
 */
export async function silentRefreshToken(): Promise<string | null> {
  if (refreshPromise) {
    return refreshPromise;
  }

  refreshPromise = (async () => {
    try {
      const refreshUrl = `${baseUrl.replace(/\/+$/, "")}/api/v1/auth/refresh`;
      const res = await fetch(refreshUrl, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({}),
      });

      if (!res.ok) {
        clearAccessToken();
        clearStoredDoctorSession();
        clearStoredManagerSession();
        return null;
      }

      const data = (await res.json()) as { access_token?: string };
      if (data.access_token) {
        setAccessToken(data.access_token);
        return data.access_token;
      }
      return null;
    } catch {
      clearAccessToken();
      clearStoredDoctorSession();
      clearStoredManagerSession();
      return null;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

// Configure client request interceptor to inject dynamic Authorization header
// and preserve an unconsumed Request clone for safe 401 retries on POST/PUT/PATCH.
client.interceptors.request.use((request) => {
  const token = getAccessToken() || getStoredToken();
  if (token && !request.headers.has("Authorization")) {
    request.headers.set("Authorization", `Bearer ${token}`);
  }
  if (!request.bodyUsed) {
    retryRequestClones.set(request, request.clone());
  }
  return request;
});

// Configure client response interceptor for silent refresh on 401 with loop protection
client.interceptors.response.use(async (response, request, opts) => {
  const clonedRequest = retryRequestClones.get(request);
  retryRequestClones.delete(request);

  if (response.status === 401) {
    const url = request.url;
    const isAuthRoute =
      url.includes("/api/v1/auth/refresh") ||
      url.includes("/api/v1/auth/login") ||
      url.includes("/api/v1/auth/logout") ||
      url.includes("/api/v1/auth/patient/otp/verify");

    const alreadyRetried = request.headers.get("X-Retry") === "1";

    if (!isAuthRoute && !alreadyRetried) {
      const newToken = await silentRefreshToken();
      if (newToken) {
        const headers = new Headers(request.headers);
        headers.set("Authorization", `Bearer ${newToken}`);
        headers.set("X-Retry", "1");

        const retryBase = clonedRequest && !clonedRequest.bodyUsed ? clonedRequest : request;
        const retryRequest = new Request(retryBase, {
          headers,
          credentials: "include",
        });

        const retryFetch = opts.fetch ?? fetch;
        return await retryFetch(retryRequest);
      }
    }
  }
  return response;
});

// Configure client error interceptor to convert RFC 7807 responses into ProblemDetailsError and purge session on 401
client.interceptors.error.use((error, response) => {
  const status = response?.status ?? 500;
  if (status === 401) {
    clearStoredSession();
    clearStoredDoctorSession();
    clearStoredManagerSession();
    clearAccessToken();
  }
  return toProblemDetailsError(error, status);
});

if (typeof window !== "undefined" && (settings.env.isDev || settings.env.mode === "test")) {
  (window as unknown as { __medisyncClient?: typeof client }).__medisyncClient = client;
}

export { client };
