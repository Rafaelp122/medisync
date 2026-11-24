import { isRedirect } from "@tanstack/react-router";
import { HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { handleRefreshTokenApiV1AuthRefreshPost } from "@/api/generated/msw.gen";
import { clearAccessToken, getAccessToken, setAccessToken } from "@/lib/auth-token";
import {
  getStoredDoctorSession,
  getStoredManagerSession,
  saveStoredDoctorSession,
  saveStoredManagerSession,
} from "@/lib/session-storage";
import { server } from "@/mocks/server";
import { gestorRoute } from "@/routes/gestor";
import { medicoRoute } from "@/routes/medico";

interface RedirectLike {
  options?: {
    to?: string;
  };
}

type BeforeLoadFn<T> = (args: Record<string, unknown>) => Promise<T>;

describe("Session Persistence & Silent Rehydration on F5 Reload (ADR-005, ADR-011, Issue #144)", () => {
  beforeEach(() => {
    localStorage.clear();
    clearAccessToken();
  });

  afterEach(() => {
    localStorage.clear();
    clearAccessToken();
    server.resetHandlers();
  });

  describe("Rota Médica (/medico)", () => {
    const runMedicoBeforeLoad = medicoRoute.options.beforeLoad as unknown as BeforeLoadFn<{
      doctorSession: unknown;
    }>;

    it("IT-PERSIST-01: Redireciona para /interno/login se não houver sessão médica armazenada", async () => {
      try {
        await runMedicoBeforeLoad({});
        expect.unreachable("Deveria ter lançado redirect");
      } catch (err) {
        expect(isRedirect(err)).toBe(true);
        expect((err as unknown as RedirectLike).options?.to).toBe("/interno/login");
      }
    });

    it("IT-PERSIST-02: Preserva sessão médica sem chamar refresh quando token em memória já existe", async () => {
      saveStoredDoctorSession({
        medicoId: "med-1",
        medicoNome: "Dr. Eduardo",
        crmUf: "12345/SP",
        identificador: "12345/SP",
      });
      setAccessToken("token-ja-em-memoria");

      let refreshChamado = false;
      server.use(
        handleRefreshTokenApiV1AuthRefreshPost(() => {
          refreshChamado = true;
          return HttpResponse.json({
            access_token: "unused-token",
            refresh_token: "unused-cookie",
            token_type: "Bearer",
            expires_in: 900,
            refresh_expires_in: 604800,
          });
        }),
      );

      const ctx = await runMedicoBeforeLoad({});
      expect((ctx.doctorSession as { medicoNome: string }).medicoNome).toBe("Dr. Eduardo");
      expect(refreshChamado).toBe(false);
      expect(getAccessToken()).toBe("token-ja-em-memoria");
    });

    it("IT-PERSIST-03: F5 Reload em /medico reidrata access token via cookie HttpOnly silenciosamente", async () => {
      saveStoredDoctorSession({
        medicoId: "med-1",
        medicoNome: "Dr. Eduardo",
        crmUf: "12345/SP",
        identificador: "12345/SP",
      });
      expect(getAccessToken()).toBeNull();

      server.use(
        handleRefreshTokenApiV1AuthRefreshPost({
          body: {
            access_token: "rotated-doctor-access-token",
            refresh_token: "new-cookie",
            token_type: "Bearer",
            expires_in: 900,
            refresh_expires_in: 604800,
            mfa_requerido: false,
          },
        }),
      );

      const ctx = await runMedicoBeforeLoad({});
      expect((ctx.doctorSession as { medicoNome: string }).medicoNome).toBe("Dr. Eduardo");
      expect(getAccessToken()).toBe("rotated-doctor-access-token");
    });

    it("IT-PERSIST-04: F5 Reload em /medico purga sessão e redireciona para /interno/login se cookie for inválido/expirado", async () => {
      saveStoredDoctorSession({
        medicoId: "med-1",
        medicoNome: "Dr. Eduardo",
        crmUf: "12345/SP",
        identificador: "12345/SP",
      });
      expect(getAccessToken()).toBeNull();

      server.use(
        handleRefreshTokenApiV1AuthRefreshPost(() => {
          return HttpResponse.json(
            { detail: "Token de refresh expirado ou revogado" },
            { status: 401 },
          );
        }),
      );

      try {
        await runMedicoBeforeLoad({});
        expect.unreachable("Deveria ter lançado redirect");
      } catch (err) {
        expect(isRedirect(err)).toBe(true);
        expect((err as unknown as RedirectLike).options?.to).toBe("/interno/login");
        expect(getAccessToken()).toBeNull();
        expect(getStoredDoctorSession()).toBeNull();
      }
    });
  });

  describe("Rota Gestor (/gestor)", () => {
    const runGestorBeforeLoad = gestorRoute.options.beforeLoad as unknown as BeforeLoadFn<{
      managerSession: unknown;
    }>;

    it("IT-PERSIST-05: Redireciona para /interno/login se não houver sessão de gestor armazenada", async () => {
      try {
        await runGestorBeforeLoad({});
        expect.unreachable("Deveria ter lançado redirect");
      } catch (err) {
        expect(isRedirect(err)).toBe(true);
        expect((err as unknown as RedirectLike).options?.to).toBe("/interno/login");
      }
    });

    it("IT-PERSIST-06: F5 Reload em /gestor reidrata access token via cookie HttpOnly silenciosamente", async () => {
      saveStoredManagerSession({
        usuarioId: "gestor-1",
        nome: "Gestora Maria",
        email: "gestor@saude.gov.br",
        papel: "GESTOR_UNIDADE",
      });
      expect(getAccessToken()).toBeNull();

      server.use(
        handleRefreshTokenApiV1AuthRefreshPost({
          body: {
            access_token: "rotated-manager-access-token",
            refresh_token: "new-cookie",
            token_type: "Bearer",
            expires_in: 900,
            refresh_expires_in: 604800,
            mfa_requerido: false,
          },
        }),
      );

      const ctx = await runGestorBeforeLoad({});
      expect((ctx.managerSession as { nome: string }).nome).toBe("Gestora Maria");
      expect(getAccessToken()).toBe("rotated-manager-access-token");
    });

    it("IT-PERSIST-07: F5 Reload em /gestor purga sessão e redireciona para /interno/login se refresh falhar", async () => {
      saveStoredManagerSession({
        usuarioId: "gestor-1",
        nome: "Gestora Maria",
        email: "gestor@saude.gov.br",
        papel: "GESTOR_UNIDADE",
      });
      expect(getAccessToken()).toBeNull();

      server.use(
        handleRefreshTokenApiV1AuthRefreshPost(() => {
          return HttpResponse.json({ detail: "Sessão corporativa encerrada" }, { status: 401 });
        }),
      );

      try {
        await runGestorBeforeLoad({});
        expect.unreachable("Deveria ter lançado redirect");
      } catch (err) {
        expect(isRedirect(err)).toBe(true);
        expect((err as unknown as RedirectLike).options?.to).toBe("/interno/login");
        expect(getAccessToken()).toBeNull();
        expect(getStoredManagerSession()).toBeNull();
      }
    });

    it("IT-PERSIST-08: Bloqueia e purga sessão em /gestor quando papel armazenado ou JWT não for GESTOR_UNIDADE", async () => {
      const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
      const medicoPayload = btoa(JSON.stringify({ sub: "user-1", papel: "MEDICO" }));
      setAccessToken(`${header}.${medicoPayload}.sig`);
      saveStoredManagerSession({
        usuarioId: "gestor-1",
        nome: "Gestora Inválida",
        email: "medico@saude.gov.br",
        papel: "GESTOR_UNIDADE",
      });

      try {
        await runGestorBeforeLoad({});
        expect.unreachable("Deveria ter bloqueado acesso de MEDICO ao /gestor");
      } catch (err) {
        expect(isRedirect(err)).toBe(true);
        expect((err as unknown as RedirectLike).options?.to).toBe("/interno/login");
        expect(getAccessToken()).toBeNull();
        expect(getStoredManagerSession()).toBeNull();
      }
    });

    it("IT-PERSIST-09: Bloqueia e purga sessão em /medico quando JWT possuir papel divergente (GESTOR_UNIDADE)", async () => {
      const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
      const gestorPayload = btoa(JSON.stringify({ sub: "user-2", papel: "GESTOR_UNIDADE" }));
      setAccessToken(`${header}.${gestorPayload}.sig`);
      saveStoredDoctorSession({
        medicoId: "med-1",
        medicoNome: "Dr. Eduardo",
        crmUf: "12345/SP",
        identificador: "12345/SP",
        papel: "MEDICO",
      });

      try {
        await (
          medicoRoute.options.beforeLoad as unknown as BeforeLoadFn<{ doctorSession: unknown }>
        )({});
        expect.unreachable("Deveria ter bloqueado acesso de GESTOR_UNIDADE ao /medico");
      } catch (err) {
        expect(isRedirect(err)).toBe(true);
        expect((err as unknown as RedirectLike).options?.to).toBe("/interno/login");
        expect(getAccessToken()).toBeNull();
        expect(getStoredDoctorSession()).toBeNull();
      }
    });
  });
});
