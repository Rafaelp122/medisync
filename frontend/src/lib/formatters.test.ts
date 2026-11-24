import { describe, expect, it } from "vitest";
import {
  formatarDataBR,
  formatarDataIso,
  getStatusBadgeProps,
  STATUS_BADGE_MAP,
  somarDiasIso,
} from "./formatters";

describe("lib/formatters (UTC canônico e STATUS_BADGE_MAP)", () => {
  it("formatarDataIso usa UTC canônico sem voltar dia às 23h30 BRT (02h30Z)", () => {
    const noiteBrt = new Date("2026-11-24T02:30:00.000Z");
    const inicioMesUtc = new Date("2026-12-01T01:00:00.000Z");

    expect(formatarDataIso(noiteBrt)).toBe("2026-11-24");
    expect(formatarDataIso(inicioMesUtc)).toBe("2026-12-01");
    expect(somarDiasIso(formatarDataIso(noiteBrt), 1)).toBe("2026-11-25");
    expect(formatarDataBR("2026-11-24T02:30:00Z")).toBe("24/11/2026");
  });

  it("STATUS_BADGE_MAP exclui aliases fantasmas e preserva chaves canônicas", () => {
    expect(STATUS_BADGE_MAP.CHAMADO).toBeUndefined();
    expect(STATUS_BADGE_MAP.EVADIDO).toBeUndefined();
    expect(STATUS_BADGE_MAP.NO_SHOW).toBeUndefined();

    expect(STATUS_BADGE_MAP.CHAMANDO_PACIENTE).toEqual({
      label: "Chamando",
      variant: "warning",
    });
    expect(STATUS_BADGE_MAP.PACIENTE_AUSENTE).toEqual({
      label: "Ausência",
      variant: "destructive",
    });
    expect(getStatusBadgeProps("CANCELADO_PACIENTE")).toEqual({
      label: "Cancelado",
      variant: "destructive",
    });
    expect(getStatusBadgeProps("FINALIZADO")).toEqual({
      label: "Finalizado",
      variant: "success",
    });
  });
});
