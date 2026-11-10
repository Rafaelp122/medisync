import { settings } from "@/config/settings";
import { clearAccessToken, getAccessToken, setAccessToken } from "@/lib/auth-token";
import {
  clearStoredDoctorSession,
  clearStoredManagerSession,
  clearStoredSession,
  getStoredToken,
} from "@/lib/session-storage";
import { toProblemDetailsError } from "./errors";
import { client } from "./generated/client.gen";

const baseUrl = settings.env.apiBaseUrl;

export function getActiveTenantId(): string {
  if (typeof window !== "undefined" && window.localStorage) {
    const stored = window.localStorage.getItem(settings.storage.tenantId);
    if (stored) return stored;
  }
  return settings.env.defaultTenantId;
}

client.setConfig({
  baseUrl,
  credentials: "include",
  headers: {
    "X-Tenant-ID": getActiveTenantId(),
  },
});

let refreshPromise: Promise<string | null> | null = null;

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
      const tenantId = getActiveTenantId();
      const res = await fetch(refreshUrl, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-Tenant-ID": tenantId,
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

// Configure client request interceptor to inject default X-Tenant-ID and Authorization headers
client.interceptors.request.use((request) => {
  const tenantId = getActiveTenantId();
  if (!request.headers.has("X-Tenant-ID")) {
    request.headers.set("X-Tenant-ID", tenantId);
  }
  const token = getAccessToken() || getStoredToken();
  if (token && !request.headers.has("Authorization")) {
    request.headers.set("Authorization", `Bearer ${token}`);
  }
  return request;
});

// Configure client response interceptor for silent refresh on 401 with loop protection
client.interceptors.response.use(async (response, request, opts) => {
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

        const retryRequest = new Request(request.url, {
          method: request.method,
          headers,
          body: request.body,
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

if (typeof window !== "undefined") {
  (window as unknown as { __medisyncClient?: typeof client }).__medisyncClient = client;
}

export { client };
