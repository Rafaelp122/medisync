import fs from "node:fs";
import path from "node:path";
import { render, screen } from "@testing-library/react";
import React from "react";
import { describe, expect, it } from "vitest";
import { Badge } from "./badge";

describe("Badge Component & WCAG 2.1 AA Contrast Compliance", () => {
  it("IT-BADGE-01: aplica classes semânticas de alto contraste (>= 4.5:1) na variante warning", () => {
    render(<Badge variant="warning">Atenção</Badge>);
    const badge = screen.getByText("Atenção");
    // Garante que não utiliza text-white com bg-amber-500 (contraste falho de 2.14:1)
    expect(badge.className).not.toMatch(/bg-amber-500 text-white/);
    expect(badge.className).toMatch(/bg-warning text-warning-foreground font-bold/);
  });

  it("IT-BADGE-02: aplica classes semânticas acr-* de alto contraste nas variantes de risco Manchester/ACR", () => {
    const { rerender } = render(<Badge variant="nivel1">Vermelho</Badge>);
    expect(screen.getByText("Vermelho").className).toMatch(/bg-acr-red text-acr-red-foreground/);
    expect(screen.getByText("Vermelho").className).not.toMatch(/bg-red-700/);

    rerender(<Badge variant="nivel2">Laranja</Badge>);
    expect(screen.getByText("Laranja").className).toMatch(
      /bg-acr-orange text-acr-orange-foreground/,
    );
    expect(screen.getByText("Laranja").className).not.toMatch(/bg-orange-700/);

    rerender(<Badge variant="nivel3">Amarelo</Badge>);
    expect(screen.getByText("Amarelo").className).toMatch(
      /bg-acr-yellow text-acr-yellow-foreground font-bold/,
    );
    expect(screen.getByText("Amarelo").className).not.toMatch(/bg-yellow-400/);

    rerender(<Badge variant="nivel4">Verde</Badge>);
    expect(screen.getByText("Verde").className).toMatch(/bg-acr-green text-acr-green-foreground/);
    expect(screen.getByText("Verde").className).not.toMatch(/bg-emerald-700/);

    rerender(<Badge variant="nivel5">Azul</Badge>);
    expect(screen.getByText("Azul").className).toMatch(/bg-acr-blue text-acr-blue-foreground/);
    expect(screen.getByText("Azul").className).not.toMatch(/bg-blue-600/);
  });

  it("IT-BADGE-03: suporta prop ref direta conforme convenção React 19", () => {
    const ref = React.createRef<HTMLDivElement>();
    render(<Badge ref={ref}>Com Ref</Badge>);
    expect(ref.current).toBeInstanceOf(HTMLDivElement);
  });

  it("IT-BADGE-04: valida conformidade matemática de contraste WCAG 2.1 AA (>= 4.5:1) para tokens OKLCH lidos de globals.css", () => {
    const cssPath = path.resolve(__dirname, "../../globals.css");
    const cssContent = fs.readFileSync(cssPath, "utf-8");

    function extrairBlocoCss(css: string, seletor: string): Record<string, string> {
      const regex = new RegExp(`${seletor}\\s*\\{([^}]+(?:\\{[^}]*\\}[^}]*)*)\\}`);
      const match = css.match(regex);
      if (!match) throw new Error(`Seletor CSS não encontrado: ${seletor}`);
      const bloco = match[1];
      const tokens: Record<string, string> = {};
      const tokenRegex = /--([a-z0-9-]+):\s*([^;]+);/g;
      for (const [, chave, valor] of bloco.matchAll(tokenRegex)) {
        tokens[chave.trim()] = valor.trim();
      }
      return tokens;
    }

    const tokensLight = extrairBlocoCss(cssContent, ":root");
    const tokensDark = extrairBlocoCss(cssContent, "\\.dark");

    function parseOklch(str: string): { l: number; c: number; h: number } {
      const match = str.match(/oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\)/);
      if (!match) throw new Error(`Cor OKLCH inválida: ${str}`);
      return {
        l: parseFloat(match[1]),
        c: parseFloat(match[2]),
        h: parseFloat(match[3]),
      };
    }

    function oklchToRelativeLuminance(oklchStr: string): number {
      const { l: L, c: C, h: H } = parseOklch(oklchStr);
      const hRad = (H * Math.PI) / 180;
      const a = C * Math.cos(hRad);
      const b = C * Math.sin(hRad);

      const l_ = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
      const m_ = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
      const s_ = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;

      const rLinear = +4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_;
      const gLinear = -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_;
      const bLinear = -0.0041960863 * l_ - 0.7034186147 * m_ + 1.707614701 * s_;

      const r = Math.min(Math.max(rLinear, 0), 1);
      const g = Math.min(Math.max(gLinear, 0), 1);
      const b_ = Math.min(Math.max(bLinear, 0), 1);

      return 0.2126 * r + 0.7152 * g + 0.0722 * b_;
    }

    function calcularContraste(bg: string, fg: string): number {
      const y1 = oklchToRelativeLuminance(bg);
      const y2 = oklchToRelativeLuminance(fg);
      const claro = Math.max(y1, y2);
      const escuro = Math.min(y1, y2);
      return (claro + 0.05) / (escuro + 0.05);
    }

    const paresParaTestar = [
      { nome: "Nível 1 (Vermelho)", bgToken: "acr-red", fgToken: "acr-red-foreground", minCr: 4.5 },
      {
        nome: "Nível 2 (Laranja)",
        bgToken: "acr-orange",
        fgToken: "acr-orange-foreground",
        minCr: 4.5,
      },
      {
        nome: "Nível 3 (Amarelo)",
        bgToken: "acr-yellow",
        fgToken: "acr-yellow-foreground",
        minCr: 7.0,
      },
      {
        nome: "Nível 4 (Verde)",
        bgToken: "acr-green",
        fgToken: "acr-green-foreground",
        minCr: 4.5,
      },
      { nome: "Nível 5 (Azul)", bgToken: "acr-blue", fgToken: "acr-blue-foreground", minCr: 4.5 },
      { nome: "Warning (Aviso)", bgToken: "warning", fgToken: "warning-foreground", minCr: 7.0 },
    ];

    for (const { nome, bgToken, fgToken, minCr } of paresParaTestar) {
      const bgLight = tokensLight[bgToken];
      const fgLight = tokensLight[fgToken];
      expect(bgLight, `Token --${bgToken} ausente em :root`).toBeDefined();
      expect(fgLight, `Token --${fgToken} ausente em :root`).toBeDefined();
      const crLight = calcularContraste(bgLight, fgLight);
      expect(
        crLight,
        `Contraste insuficiente para ${nome} em Light mode: ${crLight.toFixed(2)}:1 (mínimo esperado: ${minCr}:1)`,
      ).toBeGreaterThanOrEqual(minCr);

      const bgDark = tokensDark[bgToken];
      const fgDark = tokensDark[fgToken];
      expect(bgDark, `Token --${bgToken} ausente em .dark`).toBeDefined();
      expect(fgDark, `Token --${fgToken} ausente em .dark`).toBeDefined();
      const crDark = calcularContraste(bgDark, fgDark);
      expect(
        crDark,
        `Contraste insuficiente para ${nome} em Dark mode: ${crDark.toFixed(2)}:1 (mínimo esperado: ${minCr}:1)`,
      ).toBeGreaterThanOrEqual(minCr);
    }
  });
});
