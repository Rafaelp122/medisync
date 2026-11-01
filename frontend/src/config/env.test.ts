import { describe, expect, it } from "vitest";
import { env } from "./env";

describe("Frontend Environment Config (IoC)", () => {
  it("deve carregar configurações padrão consistentes", () => {
    expect(env.defaultTenantId).toBe("1");
    expect(typeof env.isDemoMode).toBe("boolean");
    expect(["fake", "birdid", "safeid", "vidaas"]).toContain(env.defaultPscProvider);
    expect(env.apiBaseUrl).toBeDefined();
  });
});
