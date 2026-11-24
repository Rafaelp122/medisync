import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearAccessToken, getAccessToken, setAccessToken } from "@/lib/auth-token";
import {
  getStoredDoctorSession,
  getStoredManagerSession,
  saveStoredDoctorSession,
  saveStoredManagerSession,
} from "@/lib/session-storage";
import { sessionTransport } from "@/lib/session-transport";
import { client, getSessionQueryScope, isAuthRoute } from "./client";
import { isProblemDetailsError } from "./errors";

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
    sessionTransport.activatePatientSession({
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

  it("UT-CLI-06: getSessionQueryScope isola chaves por sub JWT ou sessão ativa", () => {
    expect(getSessionQueryScope()).toBe("anon");

    const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
    const payloadA = btoa(JSON.stringify({ sub: "pac-1" }));
    const payloadB = btoa(JSON.stringify({ sub: "pac-2" }));

    sessionTransport.activatePatientSession({
      token: `${header}.${payloadA}.sig`,
      pacienteId: "pac-1",
      role: "PACIENTE",
      tipo: "acolhimento",
    });
    expect(getSessionQueryScope()).toBe("sub:pac-1");

    sessionTransport.activatePatientSession({
      token: `${header}.${payloadB}.sig`,
      pacienteId: "pac-2",
      role: "PACIENTE",
      tipo: "acolhimento",
    });
    expect(getSessionQueryScope()).toBe("sub:pac-2");

    sessionTransport.clearSession("all");
    setAccessToken("opaque-token-a");
    const scopeA = getSessionQueryScope();
    setAccessToken("opaque-token-b");
    const scopeB = getSessionQueryScope();
    expect(scopeA).not.toBe(scopeB);
  });

  it("UT-CLI-07: retry 401 em POST preserva o body JSON após silentRefreshToken sem erro de ReadableStream consumido", async () => {
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

  it("UT-CLI-08: lê tokens dinamicamente entre requisições sem congelar config estática", async () => {
    const capturedAuths: Array<string | null> = [];

    const captureFetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const req = toRequest(input, init);
      capturedAuths.push(req.headers.get("Authorization"));
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    };

    setAccessToken("token-alpha");
    await client.get({ url: "/api/v1/dynamic-1", fetch: captureFetch });

    setAccessToken("token-beta");
    await client.get({ url: "/api/v1/dynamic-2", fetch: captureFetch });

    clearAccessToken();
    await client.get({ url: "/api/v1/dynamic-3", fetch: captureFetch });

    await client.get({
      url: "/api/v1/dynamic-4",
      headers: { Authorization: "Bearer explicit-override" },
      fetch: captureFetch,
    });

    expect(capturedAuths).toEqual([
      "Bearer token-alpha",
      "Bearer token-beta",
      null,
      "Bearer explicit-override",
    ]);
  });

  it("UT-CLI-09: expõe window.__medisyncClient em modo test", () => {
    const exposed = (window as unknown as { __medisyncClient?: typeof client }).__medisyncClient;
    expect(exposed).toBe(client);
  });

  it("UT-CLI-10: rotação T1 -> T2 em chamadas consecutivas à agenda não mantém header stale", async () => {
    setAccessToken("T1-token");

    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async () => {
        return new Response(JSON.stringify({ access_token: "T2-token" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );

    let firstCall = 0;
    const secondCallAuths: Array<string | null> = [];

    await client.get({
      url: "/api/v1/scheduling/agenda/dia",
      fetch: async (input: RequestInfo | URL, init?: RequestInit) => {
        const req = toRequest(input, init);
        firstCall += 1;
        if (firstCall === 1) {
          expect(req.headers.get("Authorization")).toBe("Bearer T1-token");
          return new Response(JSON.stringify({ detail: "Expired" }), { status: 401 });
        }
        expect(req.headers.get("Authorization")).toBe("Bearer T2-token");
        return new Response(JSON.stringify([]), { status: 200 });
      },
    });

    await client.get({
      url: "/api/v1/scheduling/agenda/dia",
      fetch: async (input: RequestInfo | URL, init?: RequestInit) => {
        const req = toRequest(input, init);
        secondCallAuths.push(req.headers.get("Authorization"));
        return new Response(JSON.stringify([]), { status: 200 });
      },
    });

    expect(secondCallAuths).toEqual(["Bearer T2-token"]);
  });

  it("UT-CLI-11: isAuthRoute reconhece login-password, webauthn verify e mfa/verify sem apagar sessão em 401", async () => {
    expect(isAuthRoute("/api/v1/auth/patient/login-password")).toBe(true);
    expect(isAuthRoute("/api/v1/auth/patient/webauthn/authenticate/verify")).toBe(true);
    expect(isAuthRoute("/api/v1/auth/mfa/verify")).toBe(true);

    setAccessToken("staff-session-should-stay");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    for (const authPath of [
      "/api/v1/auth/patient/login-password",
      "/api/v1/auth/patient/webauthn/authenticate/verify",
      "/api/v1/auth/mfa/verify",
    ]) {
      await expect(
        client.post({
          url: authPath,
          body: {},
          throwOnError: true,
          fetch: async () => new Response(JSON.stringify({ detail: "Invalid" }), { status: 401 }),
        }),
      ).rejects.toBeDefined();
    }

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(getAccessToken()).toBe("staff-session-should-stay");
  });

  it("UT-CLI-12: sessão de paciente em 401 não aciona /auth/refresh e notifica invalidate listeners", async () => {
    sessionTransport.activatePatientSession({
      token: "pac-jwt-expired",
      pacienteId: "pac-1",
      role: "PACIENTE",
      tipo: "acolhimento",
    });

    const invalidatedSpy = vi.fn();
    const unsubscribe = sessionTransport.subscribeInvalidated(invalidatedSpy);
    const globalFetchSpy = vi.fn();
    vi.stubGlobal("fetch", globalFetchSpy);

    try {
      await client.get({
        url: "/api/v1/scheduling/agendamentos/me",
        throwOnError: true,
        fetch: async () =>
          new Response(JSON.stringify({ detail: "Unauthorized" }), { status: 401 }),
      });
    } catch {
      // ProblemDetailsError esperado
    } finally {
      unsubscribe();
    }

    expect(globalFetchSpy).not.toHaveBeenCalled();
    expect(invalidatedSpy).toHaveBeenCalledTimes(1);
    expect(getSessionQueryScope()).toBe("anon");
  });

  it("UT-CLI-13: anexa AbortSignal de timeout e converte TimeoutError em ProblemDetailsError 504", async () => {
    let receivedSignal: AbortSignal | undefined;

    await expect(
      client.get({
        url: "/api/v1/clinical/slow-endpoint",
        throwOnError: true,
        fetch: async (input: RequestInfo | URL, init?: RequestInit) => {
          const req = toRequest(input, init);
          receivedSignal = req.signal;
          throw new DOMException("The operation was aborted due to timeout", "TimeoutError");
        },
      }),
    ).rejects.toSatisfy((err: unknown) => {
      return isProblemDetailsError(err) && err.status === 504 && err.code === "TIMEOUT";
    });

    expect(receivedSignal).toBeDefined();
  });

  it("UT-CLI-14: paciente ativa sessão corporativa -> clearSession('staff') -> sem token residual e queryScope 'anon'", () => {
    sessionTransport.activatePatientSession({
      token: "pac-jwt-antigo",
      pacienteId: "pac-99",
      role: "PACIENTE",
      tipo: "acolhimento",
    });

    sessionTransport.activateStaffSession({
      role: "MEDICO",
      token: "med-jwt-ativo",
      session: {
        medicoId: "med-99",
        medicoNome: "987654/SP",
        crmUf: "987654/SP",
        identificador: "987654/SP",
        papel: "MEDICO",
      },
    });

    expect(sessionTransport.getActiveBearerToken()).toBe("med-jwt-ativo");

    sessionTransport.clearSession("staff");

    expect(sessionTransport.getActiveBearerToken()).toBeNull();
    expect(sessionTransport.getQueryScope()).toBe("anon");
    expect(localStorage.getItem("medisync_session")).toBeNull();
  });

  it("UT-CLI-15: com slots staff residuais, activatePatientSession limpa slots corporativos e 401 não chama /auth/refresh", async () => {
    saveStoredDoctorSession({
      medicoId: "med-residual",
      medicoNome: "Dr. Residual",
      crmUf: "11111/SP",
      identificador: "11111/SP",
      papel: "MEDICO",
    });
    saveStoredManagerSession({
      usuarioId: "mgr-residual",
      nome: "Gestor Residual",
      email: "mgr@saude.gov.br",
      papel: "GESTOR_UNIDADE",
    });

    sessionTransport.activatePatientSession({
      token: "pac-jwt-limpo",
      pacienteId: "pac-42",
      role: "PACIENTE",
      tipo: "acolhimento",
    });

    expect(getStoredDoctorSession()).toBeNull();
    expect(getStoredManagerSession()).toBeNull();
    expect(sessionTransport.hasCorporateSession()).toBe(false);

    const refreshSpy = vi.fn();
    vi.stubGlobal("fetch", refreshSpy);

    await expect(
      client.get({
        url: "/api/v1/scheduling/agendamentos/me",
        throwOnError: true,
        fetch: async () =>
          new Response(JSON.stringify({ detail: "Unauthorized" }), { status: 401 }),
      }),
    ).rejects.toBeDefined();

    expect(refreshSpy).not.toHaveBeenCalled();
    expect(sessionTransport.getActiveBearerToken()).toBeNull();
    expect(sessionTransport.getQueryScope()).toBe("anon");
  });
});
