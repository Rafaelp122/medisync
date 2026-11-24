import { settings } from "@/config/settings";
import { sessionTransport } from "@/lib/session-transport";
import { toProblemDetailsError } from "./errors";
import { client } from "./generated/client.gen";

const baseUrl = settings.env.apiBaseUrl;
const REQUEST_TIMEOUT_MS = 15_000;

const AUTH_ROUTE_PATHS = [
  "/api/v1/auth/refresh",
  "/api/v1/auth/login",
  "/api/v1/auth/logout",
  "/api/v1/auth/mfa/verify",
  "/api/v1/auth/mfa/setup",
  "/api/v1/auth/mfa/activate",
  "/api/v1/auth/patient/otp/request",
  "/api/v1/auth/patient/otp/verify",
  "/api/v1/auth/patient/login-password",
  "/api/v1/auth/patient/webauthn/authenticate/options",
  "/api/v1/auth/patient/webauthn/authenticate/verify",
] as const;

export function isAuthRoute(url: string): boolean {
  return AUTH_ROUTE_PATHS.some((path) => url.includes(path));
}

function createRequestSignal(existing?: AbortSignal | null): AbortSignal | undefined {
  if (typeof AbortSignal === "undefined" || typeof AbortSignal.timeout !== "function") {
    return existing ?? undefined;
  }
  const timeoutSignal = AbortSignal.timeout(REQUEST_TIMEOUT_MS);
  if (existing && typeof AbortSignal.any === "function") {
    return AbortSignal.any([existing, timeoutSignal]);
  }
  return existing ?? timeoutSignal;
}

export function getSessionQueryScope(): string {
  return sessionTransport.getQueryScope();
}

export async function silentRefreshToken(): Promise<string | null> {
  return sessionTransport.silentRefreshToken();
}

client.setConfig({
  baseUrl,
  credentials: "include",
});

const retryRequestClones = new WeakMap<Request, Request>();

// Inject active Bearer token from SessionTransport, attach AbortSignal.timeout,
// and preserve an unconsumed Request clone for safe 401 retries on POST/PUT/PATCH.
client.interceptors.request.use((request, opts) => {
  const token = sessionTransport.getActiveBearerToken();
  if (token && !request.headers.has("Authorization")) {
    request.headers.set("Authorization", `Bearer ${token}`);
  }

  const signal = createRequestSignal(opts.signal);
  let nextRequest = request;
  if (signal) {
    try {
      nextRequest = new Request(request, { signal });
    } catch {
      // Fallback caso o ambiente Fetch restrinja rewrap de stream sem duplex
      nextRequest = request;
    }
  }

  if (!nextRequest.bodyUsed) {
    retryRequestClones.set(nextRequest, nextRequest.clone());
  }
  return nextRequest;
});

// Silent refresh on 401 strictly for non-auth routes under active corporate staff session.
client.interceptors.response.use(async (response, request, opts) => {
  const clonedRequest = retryRequestClones.get(request);
  retryRequestClones.delete(request);

  if (response.status === 401) {
    const alreadyRetried = request.headers.get("X-Retry") === "1";

    if (!isAuthRoute(request.url) && !alreadyRetried && sessionTransport.hasCorporateSession()) {
      const newToken = await sessionTransport.silentRefreshToken();
      if (newToken) {
        const headers = new Headers(request.headers);
        headers.set("Authorization", `Bearer ${newToken}`);
        headers.set("X-Retry", "1");

        const retryBase = clonedRequest && !clonedRequest.bodyUsed ? clonedRequest : request;
        const retrySignal = createRequestSignal(opts.signal);
        const retryRequest = new Request(retryBase, {
          headers,
          credentials: "include",
          ...(retrySignal ? { signal: retrySignal } : {}),
        });

        const retryFetch = opts.fetch ?? fetch;
        return await retryFetch(retryRequest);
      }
    }
  }
  return response;
});

// Convert RFC 7807 / network / timeout errors into ProblemDetailsError and purge session on terminal 401.
client.interceptors.error.use((error, response, request) => {
  const status = response?.status ?? 500;
  const url = request?.url ?? "";
  if (status === 401 && !isAuthRoute(url)) {
    sessionTransport.clearSession("all");
  }
  return toProblemDetailsError(error, status);
});

if (typeof window !== "undefined" && (settings.env.isDev || settings.env.mode === "test")) {
  (window as unknown as { __medisyncClient?: typeof client }).__medisyncClient = client;
}

export { client };
