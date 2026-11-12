import { beforeEach, describe, expect, it, vi } from "vitest";
import { clearAccessToken, getAccessToken, setAccessToken } from "@/lib/auth-token";
import { saveStoredDoctorSession, saveStoredSession } from "@/lib/session-storage";
import { client } from "./client";

function toRequest(input: RequestInfo | URL, init?: RequestInit): Request {
  return input instanceof Request ? input : new Request(input, init);
}

describe("client interceptor (Authorization Bearer & Token Handler)", () => {
  beforeEach(() => {
    localStorage.clear();
    clearAccessToken();
    vi.restoreAllMocks();
  });

  it("UT-CLI-01: deve injetar Authorization a partir da memória volátil (setAccessToken)", async () => {
    setAccessToken("volatile-jwt-token-999");

    let interceptedRequest: Request | undefined;

    await client.get({
      url: "/api/v1/test-auth",
      fetch: async (input: RequestInfo | URL, init?: RequestInit) => {
        const req = toRequest(input, init);
        interceptedRequest = req;
        return new Response(JSON.stringify({ ok: true }), { status: 200 });
      },
    });

    expect(interceptedRequest).toBeDefined();
    expect(interceptedRequest?.headers.get("Authorization")).toBe("Bearer volatile-jwt-token-999");
    expect(interceptedRequest?.credentials).toBe("include");
  });

  it("UT-CLI-02: fallback para token de paciente quando memória volátil for nula", async () => {
    clearAccessToken();
    saveStoredSession({
      token: "patient-jwt-token-123",
      pacienteId: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
      role: "PACIENTE",
      tipo: "acolhimento",
    });

    let interceptedRequest: Request | undefined;

    await client.get({
      url: "/api/v1/test-auth-patient",
      fetch: async (input: RequestInfo | URL, init?: RequestInit) => {
        const req = toRequest(input, init);
        interceptedRequest = req;
        return new Response(JSON.stringify({ ok: true }), { status: 200 });
      },
    });

    expect(interceptedRequest).toBeDefined();
    expect(interceptedRequest?.headers.get("Authorization")).toBe("Bearer patient-jwt-token-123");
  });

  it("UT-CLI-03: não deve sobrescrever cabeçalho Authorization se já fornecido na requisição", async () => {
    setAccessToken("volatile-token");

    let interceptedRequest: Request | undefined;

    await client.get({
      url: "/api/v1/test-custom-auth",
      headers: {
        Authorization: "Bearer custom-override-token",
      },
      fetch: async (input: RequestInfo | URL, init?: RequestInit) => {
        const req = toRequest(input, init);
        interceptedRequest = req;
        return new Response(JSON.stringify({ ok: true }), { status: 200 });
      },
    });

    expect(interceptedRequest).toBeDefined();
    expect(interceptedRequest?.headers.get("Authorization")).toBe("Bearer custom-override-token");
  });

  it("UT-CLI-04: interceptor 401 aciona silent refresh e repete a requisição com novo token", async () => {
    setAccessToken("old-stale-token");

    // Simula resposta global de fetch para /api/v1/auth/refresh
    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockImplementation(async (url: string | URL | Request) => {
      const urlStr =
        typeof url === "string" ? url : url instanceof Request ? url.url : url.toString();
      if (urlStr.includes("/api/v1/auth/refresh")) {
        return new Response(JSON.stringify({ access_token: "new-rotated-token-888" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return originalFetch(url);
    });

    let callCount = 0;
    let retriedAuthHeader: string | null = null;

    const response = await client.get({
      url: "/api/v1/clinical/resource",
      fetch: async (input: RequestInfo | URL, init?: RequestInit) => {
        const req = toRequest(input, init);
        callCount++;
        if (callCount === 1) {
          return new Response(JSON.stringify({ detail: "Token expired" }), { status: 401 });
        }
        retriedAuthHeader = req.headers.get("Authorization");
        return new Response(JSON.stringify({ data: "success" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      },
    });

    expect(callCount).toBe(2);
    expect(retriedAuthHeader).toBe("Bearer new-rotated-token-888");
    expect(getAccessToken()).toBe("new-rotated-token-888");
    expect(response.response?.status).toBe(200);
    expect(response.data).toEqual({ data: "success" });
  });

  it("UT-CLI-05: falha no silent refresh purga sessões corporativas e access token", async () => {
    setAccessToken("old-token");
    saveStoredDoctorSession({
      medicoId: "med-1",
      medicoNome: "Dr. Teste",
      crmUf: "1234/SP",
      identificador: "dr.teste",
    });

    globalThis.fetch = vi.fn().mockImplementation(async () => {
      return new Response(JSON.stringify({ detail: "Revoked cookie" }), { status: 401 });
    });

    try {
      await client.get({
        url: "/api/v1/clinical/resource",
        fetch: async () => {
          return new Response(JSON.stringify({ detail: "Unauthorized" }), { status: 401 });
        },
      });
    } catch {
      // ProblemDetailsError esperado
    }

    expect(getAccessToken()).toBeNull();
    expect(localStorage.getItem("medisync_doctor_session")).toBeNull();
  });
});
