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

// Configure client request interceptor to inject default X-Tenant-ID header
client.interceptors.request.use((request) => {
  const tenantId = getActiveTenantId();
  if (!request.headers.has("X-Tenant-ID")) {
    request.headers.set("X-Tenant-ID", tenantId);
  }
  return request;
});

// Configure client error interceptor to convert RFC 7807 responses into ProblemDetailsError
client.interceptors.error.use((error, response) => {
  const status = response?.status ?? 500;
  return toProblemDetailsError(error, status);
});

export { client };
