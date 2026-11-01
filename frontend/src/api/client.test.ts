import { beforeEach, describe, expect, it } from "vitest";
import { clearStoredSession, saveStoredSession } from "@/lib/session-storage";
import { client } from "./client";

describe("client interceptor (Authorization Bearer)", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("UT-CLI-01: deve injetar Authorization: Bearer <token> quando há token no storage", async () => {
    saveStoredSession({
      token: "jwt-test-token-456",
      pacienteId: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
      role: "PACIENTE",
      tipo: "acolhimento",
    });

    let interceptedRequest: Request | undefined;

    await client.get({
      url: "/api/v1/test-auth",
      fetch: async (req: Request) => {
        interceptedRequest = req;
        return new Response(JSON.stringify({ ok: true }), { status: 200 });
      },
    });

    expect(interceptedRequest).toBeDefined();
    expect(interceptedRequest?.headers.get("Authorization")).toBe("Bearer jwt-test-token-456");
    expect(interceptedRequest?.headers.get("X-Tenant-ID")).toBe("1");
  });

  it("UT-CLI-02: não deve injetar Authorization se não houver token no storage", async () => {
    clearStoredSession();

    let interceptedRequest: Request | undefined;

    await client.get({
      url: "/api/v1/test-no-auth",
      fetch: async (req: Request) => {
        interceptedRequest = req;
        return new Response(JSON.stringify({ ok: true }), { status: 200 });
      },
    });

    expect(interceptedRequest).toBeDefined();
    expect(interceptedRequest?.headers.get("Authorization")).toBeNull();
    expect(interceptedRequest?.headers.get("X-Tenant-ID")).toBe("1");
  });

  it("UT-CLI-03: não deve sobrescrever cabeçalho Authorization se já fornecido na requisição", async () => {
    saveStoredSession({
      token: "jwt-test-token-456",
      pacienteId: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
      role: "PACIENTE",
      tipo: "acolhimento",
    });

    let interceptedRequest: Request | undefined;

    await client.get({
      url: "/api/v1/test-custom-auth",
      headers: {
        Authorization: "Bearer custom-override-token",
      },
      fetch: async (req: Request) => {
        interceptedRequest = req;
        return new Response(JSON.stringify({ ok: true }), { status: 200 });
      },
    });

    expect(interceptedRequest).toBeDefined();
    expect(interceptedRequest?.headers.get("Authorization")).toBe("Bearer custom-override-token");
  });

  it("UT-CLI-04: deve purgar a sessão do storage quando a API responde com status 401", async () => {
    saveStoredSession({
      token: "expired-jwt-token",
      pacienteId: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b2c",
      role: "PACIENTE",
      tipo: "acolhimento",
    });

    try {
      await client.get({
        url: "/api/v1/test-expired",
        fetch: async () => {
          return new Response(
            JSON.stringify({
              type: "about:blank",
              title: "Unauthorized",
              status: 401,
              detail: "Token expirado",
            }),
            { status: 401, headers: { "Content-Type": "application/problem+json" } },
          );
        },
      });
    } catch {
      // ProblemDetailsError esperado
    }

    expect(localStorage.getItem("medisync_session")).toBeNull();
  });
});
