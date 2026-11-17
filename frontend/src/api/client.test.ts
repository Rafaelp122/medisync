import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearAccessToken, getAccessToken, setAccessToken } from "@/lib/auth-token";
import { saveStoredDoctorSession, saveStoredSession } from "@/lib/session-storage";
import { client, extractTenantIdFromJwt, getActiveTenantId, getTenantHeaders } from "./client";

function toRequest(input: RequestInfo | URL, init?: RequestInit): Request {
  return input instanceof Request ? input : new Request(input, init);
}

describe("client interceptor (Authorization Bearer & Token Handler)", () => {
  beforeEach(() => {
    localStorage.clear();
    clearAccessToken();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
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
    const passthroughFetch = globalThis.fetch;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (url: string | URL | Request, init?: RequestInit) => {
        const urlStr =
          typeof url === "string" ? url : url instanceof Request ? url.url : url.toString();
        if (urlStr.includes("/api/v1/auth/refresh")) {
          return new Response(JSON.stringify({ access_token: "new-rotated-token-888" }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        return passthroughFetch(url, init);
      }),
    );

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

    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async () => {
        return new Response(JSON.stringify({ detail: "Revoked cookie" }), { status: 401 });
      }),
    );

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

  it("UT-CLI-06: sem VITE_TENANT_ID e sem localStorage['tenant_id'], nenhuma requisição envia X-Tenant-ID estático", async () => {
    expect(getActiveTenantId()).toBeNull();
    expect(getTenantHeaders()).toEqual({});

    let interceptedRequest: Request | undefined;

    await client.get({
      url: "/api/v1/test-no-tenant",
      fetch: async (input: RequestInfo | URL, init?: RequestInit) => {
        const req = toRequest(input, init);
        interceptedRequest = req;
        return new Response(JSON.stringify({ ok: true }), { status: 200 });
      },
    });

    expect(interceptedRequest).toBeDefined();
    expect(interceptedRequest?.headers.get("X-Tenant-ID")).toBeNull();
  });

  it("UT-CLI-07: com localStorage['tenant_id'] = '42', injeta X-Tenant-ID: 42 normalmente", async () => {
    localStorage.setItem("tenant_id", "42");
    expect(getActiveTenantId()).toBe("42");
    expect(getTenantHeaders()).toEqual({ "X-Tenant-ID": "42" });

    let interceptedRequest: Request | undefined;

    await client.get({
      url: "/api/v1/test-with-tenant",
      fetch: async (input: RequestInfo | URL, init?: RequestInit) => {
        const req = toRequest(input, init);
        interceptedRequest = req;
        return new Response(JSON.stringify({ ok: true }), { status: 200 });
      },
    });

    expect(interceptedRequest).toBeDefined();
    expect(interceptedRequest?.headers.get("X-Tenant-ID")).toBe("42");
  });

  it("UT-CLI-08: extractTenantIdFromJwt extrai organizacao_id do payload JWT ou retorna undefined", () => {
    const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
    const payload = btoa(JSON.stringify({ sub: "user-1", organizacao_id: 77 }));
    const fakeJwt = `${header}.${payload}.sig`;

    expect(extractTenantIdFromJwt(fakeJwt)).toBe(77);
    expect(extractTenantIdFromJwt("invalid-token")).toBeUndefined();
    expect(extractTenantIdFromJwt(null)).toBeUndefined();
  });

  it("UT-CLI-09: retry 401 em POST preserva o body JSON após silentRefreshToken sem erro de ReadableStream consumido", async () => {
    setAccessToken("expired-post-token");

    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async () => {
        return new Response(JSON.stringify({ access_token: "fresh-post-token-777" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );

    const capturedAttempts: Array<{
      auth: string | null;
      retryHeader: string | null;
      body: unknown;
    }> = [];

    const response = await client.post({
      url: "/api/v1/scheduling/agendamentos",
      body: {
        especialidade: "PSICOLOGIA",
        slot_inicio: "2026-11-20T09:00:00Z",
      },
      fetch: async (input: RequestInfo | URL, init?: RequestInit) => {
        const req = toRequest(input, init);
        const parsedBody = await req.json();
        capturedAttempts.push({
          auth: req.headers.get("Authorization"),
          retryHeader: req.headers.get("X-Retry"),
          body: parsedBody,
        });
        if (capturedAttempts.length === 1) {
          return new Response(JSON.stringify({ detail: "Expired" }), { status: 401 });
        }
        return new Response(JSON.stringify({ id: "ag-123", status: "AGENDADO" }), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        });
      },
    });

    expect(capturedAttempts).toHaveLength(2);
    expect(capturedAttempts[0]).toEqual({
      auth: "Bearer expired-post-token",
      retryHeader: null,
      body: { especialidade: "PSICOLOGIA", slot_inicio: "2026-11-20T09:00:00Z" },
    });
    expect(capturedAttempts[1]).toEqual({
      auth: "Bearer fresh-post-token-777",
      retryHeader: "1",
      body: { especialidade: "PSICOLOGIA", slot_inicio: "2026-11-20T09:00:00Z" },
    });
    expect(response.response?.status).toBe(201);
    expect(response.data).toEqual({ id: "ag-123", status: "AGENDADO" });
  });

  it("UT-CLI-10: lê localStorage['tenant_id'] e tokens dinamicamente entre requisições sem congelar config estática", async () => {
    const capturedTenants: Array<string | null> = [];
    const capturedAuths: Array<string | null> = [];

    const captureFetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const req = toRequest(input, init);
      capturedTenants.push(req.headers.get("X-Tenant-ID"));
      capturedAuths.push(req.headers.get("Authorization"));
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    };

    localStorage.setItem("tenant_id", "42");
    setAccessToken("token-alpha");
    await client.get({ url: "/api/v1/dynamic-1", fetch: captureFetch });

    localStorage.setItem("tenant_id", "99");
    setAccessToken("token-beta");
    await client.get({ url: "/api/v1/dynamic-2", fetch: captureFetch });

    localStorage.removeItem("tenant_id");
    clearAccessToken();
    await client.get({ url: "/api/v1/dynamic-3", fetch: captureFetch });

    // Override explícito continua respeitado
    localStorage.setItem("tenant_id", "99");
    await client.get({
      url: "/api/v1/dynamic-4",
      headers: { "X-Tenant-ID": "777" },
      fetch: captureFetch,
    });

    expect(capturedTenants).toEqual(["42", "99", null, "777"]);
    expect(capturedAuths).toEqual(["Bearer token-alpha", "Bearer token-beta", null, null]);
  });

  it("UT-CLI-11: expõe window.__medisyncClient em modo test", () => {
    const exposed = (window as unknown as { __medisyncClient?: typeof client }).__medisyncClient;
    expect(exposed).toBe(client);
  });
});
