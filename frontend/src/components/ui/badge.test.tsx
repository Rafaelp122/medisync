import { render, screen } from "@testing-library/react";
import React from "react";
import { describe, expect, it } from "vitest";
import { Badge } from "./badge";

describe("Badge Component & WCAG 2.1 AA Contrast Compliance", () => {
  it("IT-BADGE-01: aplica classes de alto contraste (>= 4.5:1) na variante warning", () => {
    render(<Badge variant="warning">Atenção</Badge>);
    const badge = screen.getByText("Atenção");
    // Garante que não utiliza text-white com bg-amber-500 (contraste falho de 2.14:1)
    expect(badge.className).not.toMatch(/bg-amber-500 text-white/);
    expect(badge.className).toMatch(/text-amber-950 font-bold/);
  });

  it("IT-BADGE-02: aplica classes de contraste conforme (>= 4.5:1) nas variantes de risco Manchester/ACR", () => {
    const { rerender } = render(<Badge variant="nivel1">Vermelho</Badge>);
    expect(screen.getByText("Vermelho").className).toMatch(/bg-red-700 text-white/);

    rerender(<Badge variant="nivel2">Laranja</Badge>);
    expect(screen.getByText("Laranja").className).toMatch(/bg-orange-700 text-white/);

    rerender(<Badge variant="nivel3">Amarelo</Badge>);
    expect(screen.getByText("Amarelo").className).toMatch(/text-yellow-950 font-bold/);

    rerender(<Badge variant="nivel4">Verde</Badge>);
    expect(screen.getByText("Verde").className).toMatch(/bg-emerald-700 text-white/);

    rerender(<Badge variant="nivel5">Azul</Badge>);
    expect(screen.getByText("Azul").className).toMatch(/bg-blue-600 text-white/);
  });

  it("IT-BADGE-03: suporta prop ref direta conforme convenção React 19", () => {
    const ref = React.createRef<HTMLDivElement>();
    render(<Badge ref={ref}>Com Ref</Badge>);
    expect(ref.current).toBeInstanceOf(HTMLDivElement);
  });
});
