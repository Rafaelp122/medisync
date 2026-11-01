import { clearStoredSession, getStoredToken } from "@/lib/session-storage";
import { toProblemDetailsError } from "./errors";
import { client } from "./generated/client.gen";

const baseUrl =
  import.meta.env.VITE_API_BASE_URL ||
  (typeof window !== "undefined" && window.location?.origin && window.location.origin !== "null"
    ? window.location.origin
    : "http://localhost:5173");

export function getActiveTenantId(): string {
  if (typeof window !== "undefined" && window.localStorage) {
    const stored = window.localStorage.getItem("tenant_id");
    if (stored) return stored;
  }
  return import.meta.env.VITE_TENANT_ID || "1";
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
