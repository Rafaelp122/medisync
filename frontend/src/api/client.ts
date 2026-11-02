import { settings } from "@/config/settings";
import { clearStoredSession, getStoredToken } from "@/lib/session-storage";
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
  headers: {
    "X-Tenant-ID": getActiveTenantId(),
  },
});

// Configure client request interceptor to inject default X-Tenant-ID and Authorization headers
client.interceptors.request.use((request) => {
  const tenantId = getActiveTenantId();
  if (!request.headers.has("X-Tenant-ID")) {
    request.headers.set("X-Tenant-ID", tenantId);
  }
  const token = getStoredToken();
  if (token && !request.headers.has("Authorization")) {
    request.headers.set("Authorization", `Bearer ${token}`);
  }
  return request;
});

// Configure client error interceptor to convert RFC 7807 responses into ProblemDetailsError and purge session on 401
client.interceptors.error.use((error, response) => {
  const status = response?.status ?? 500;
  if (status === 401) {
    clearStoredSession();
  }
  return toProblemDetailsError(error, status);
});

if (typeof window !== "undefined") {
  (window as unknown as { __medisyncClient?: typeof client }).__medisyncClient = client;
}

export { client };
