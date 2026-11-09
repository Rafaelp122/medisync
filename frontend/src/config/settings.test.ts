import { describe, expect, it } from "vitest";
import { ZodError } from "zod";
import { createSettings, PSC_PROVIDERS, settings } from "./settings";

describe("Frontend Canonical Settings (Issue #126 / ADR-009)", () => {
  it("UT-SET-01: deve carregar defaults consistentes em ambiente vazio", () => {
    const config = createSettings({});

    // env
    expect(config.env.defaultTenantId).toBe("1");
    expect(config.env.isDemoMode).toBe(false);
    expect(config.env.defaultPscProvider).toBe("birdid");
    expect(config.env.apiBaseUrl).toBeDefined();

    // clinical
    expect(config.clinical.callRingTtlSeconds).toBe(45);
    expect(config.clinical.tmaPlannedSeconds).toBe(900);
    expect(config.clinical.otpCooldownSeconds).toBe(60);
    expect(config.clinical.otpExpirationSeconds).toBe(300);

    // network
    expect(config.network.queuePollingIntervalMs).toBe(5000);
    expect(config.network.tmaTelemetryIntervalMs).toBe(30000);
    expect(config.network.viaCepTimeoutMs).toBe(5000);
    expect(config.network.wsBackoffMaxDelayMs).toBe(5000);

    // storage
    expect(config.storage.patientSession).toBe("medisync_session");
    expect(config.storage.doctorSession).toBe("medisync_doctor_session");
    expect(config.storage.tenantId).toBe("tenant_id");
    expect(config.storage.passkeyDismissed).toBe("medisync_passkey_invite_dismissed");

    // demo
    expect(config.demo.doctorEmail).toBe("eduardo.rocha@medisync.com.br");
    expect(config.demo.doctorPassword).toBe("Medisync@2026");
    expect(config.demo.pscToken).toBe("demo-psc-token-123");
  });

  it("UT-SET-02: deve respeitar variáveis explícitas injetadas no ambiente", () => {
    const config = createSettings({
      VITE_API_BASE_URL: "https://api.medisync.com.br",
      VITE_TENANT_ID: "00000000-0000-0000-0000-000000000001",
      VITE_ENABLE_DEMO_HELPERS: "true",
      VITE_DEFAULT_PSC_PROVIDER: "fake",
    });

    expect(config.env.apiBaseUrl).toBe("https://api.medisync.com.br");
    expect(config.env.defaultTenantId).toBe("00000000-0000-0000-0000-000000000001");
    expect(config.env.isDemoMode).toBe(true);
    expect(config.env.defaultPscProvider).toBe("fake");
  });

  it("UT-SET-03: deve rejeitar provedor de PSC inválido com ZodError", () => {
    expect(() => createSettings({ VITE_DEFAULT_PSC_PROVIDER: "provedor_invalido" })).toThrow(
      ZodError,
    );
  });

  it("UT-SET-04: deve aplicar fail-fast desligando demo em produção a menos que explicitamente habilitado", () => {
    const configProdSemDemo = createSettings({
      PROD: true,
      DEV: false,
      VITE_ENABLE_DEMO_HELPERS: "false",
    });
    expect(configProdSemDemo.env.isDemoMode).toBe(false);

    const configProdDefault = createSettings({
      PROD: true,
      DEV: false,
    });
    expect(configProdDefault.env.isDemoMode).toBe(false);

    const configProdComDemo = createSettings({
      PROD: true,
      DEV: false,
      VITE_ENABLE_DEMO_HELPERS: "true",
    });
    expect(configProdComDemo.env.isDemoMode).toBe(true);
  });

  it("UT-SET-05: objeto retornado deve ser estritamente imutável (deep freeze)", () => {
    const config = createSettings({});
    expect(Object.isFrozen(config)).toBe(true);
    expect(Object.isFrozen(config.env)).toBe(true);
    expect(Object.isFrozen(config.clinical)).toBe(true);
    expect(Object.isFrozen(config.network)).toBe(true);
    expect(Object.isFrozen(config.storage)).toBe(true);
    expect(Object.isFrozen(config.demo)).toBe(true);

    expect(() => {
      // @ts-expect-error validação em runtime contra mutação acidental
      config.clinical.callRingTtlSeconds = 999;
    }).toThrow(TypeError);

    expect(() => {
      // @ts-expect-error validação em runtime contra mutação acidental
      config.env.apiBaseUrl = "http://hack";
    }).toThrow(TypeError);
  });

  it("UT-SET-06: singleton settings em runtime deve estar íntegro e congelado", () => {
    expect(settings.env.defaultTenantId).toBeDefined();
    expect(PSC_PROVIDERS).toContain(settings.env.defaultPscProvider);
    expect(Object.isFrozen(settings)).toBe(true);
  });

  it("UT-SET-07: deve validar invariantes clínicas e de rede", () => {
    const config = createSettings({});
    expect(config.clinical.callRingTtlSeconds).toBeGreaterThan(0);
    expect(config.clinical.tmaPlannedSeconds).toBeGreaterThanOrEqual(60);
    expect(config.clinical.otpCooldownSeconds).toBeGreaterThan(0);
    expect(config.network.queuePollingIntervalMs).toBeGreaterThanOrEqual(1000);
  });
});
