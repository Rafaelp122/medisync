import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { PainScaleSelector } from "../components/pain-scale-selector";

describe("PainScaleSelector (Escala Visual Analógica de Dor)", () => {
  it("IT-PAIN-01: Renderiza botões de 0 a 10 e permite seleção", async () => {
    const user = userEvent.setup();
    const handleChange = vi.fn();

    render(<PainScaleSelector value={0} onChange={handleChange} />);

    // Verificar presença dos 11 botões de 0 a 10
    for (let i = 0; i <= 10; i++) {
      expect(
        screen.getByRole("radio", { name: new RegExp(`^nível ${i}$`, "i") }),
      ).toBeInTheDocument();
    }

    // Clicar no nível 4
    const btn4 = screen.getByRole("radio", { name: /^nível 4$/i });
    await user.click(btn4);

    expect(handleChange).toHaveBeenCalledWith(4);
  });

  it("IT-PAIN-02: Exibe texto descritivo correspondente ao nível de dor selecionado", () => {
    const { rerender } = render(<PainScaleSelector value={0} onChange={vi.fn()} />);
    expect(screen.getByText(/Sem dor \(0\/10\)/i)).toBeInTheDocument();

    rerender(<PainScaleSelector value={5} onChange={vi.fn()} />);
    expect(screen.getByText(/Dor moderada \(5\/10\)/i)).toBeInTheDocument();

    rerender(<PainScaleSelector value={8} onChange={vi.fn()} />);
    expect(screen.getByText(/Dor intensa \(8\/10\)/i)).toBeInTheDocument();

    rerender(<PainScaleSelector value={10} onChange={vi.fn()} />);
    expect(screen.getByText(/Pior dor imaginável \(10\/10\)/i)).toBeInTheDocument();
  });

  it("IT-PAIN-03: Garante alvos de toque mínimos de 44x44px (WCAG 2.5.5) em todos os botões", () => {
    render(<PainScaleSelector value={0} onChange={vi.fn()} />);
    for (let i = 0; i <= 10; i++) {
      const btn = screen.getByRole("radio", { name: new RegExp(`^nível ${i}$`, "i") });
      expect(btn.className).toMatch(/min-h-\[44px\]/);
      expect(btn.className).toMatch(/min-w-\[44px\]/);
      expect(btn.className).toMatch(/touch-manipulation/);
    }
  });

  it("IT-PAIN-04: Adota layout responsivo com quebra mobile (grid-cols-6 sm:grid-cols-11)", () => {
    render(<PainScaleSelector value={0} onChange={vi.fn()} />);
    const group = screen.getByRole("radiogroup");
    expect(group.className).toMatch(/grid-cols-6/);
    expect(group.className).toMatch(/sm:grid-cols-11/);
  });

  it("IT-PAIN-05: aplica tokens semânticos acr-* de alto contraste nos botões de dor ativos", () => {
    const { rerender } = render(<PainScaleSelector value={0} onChange={vi.fn()} />);
    const btn0 = screen.getByRole("radio", { name: /^nível 0$/i });
    expect(btn0.className).toMatch(/bg-acr-green text-acr-green-foreground/);

    rerender(<PainScaleSelector value={5} onChange={vi.fn()} />);
    const btn5 = screen.getByRole("radio", { name: /^nível 5$/i });
    expect(btn5.className).toMatch(/bg-acr-yellow text-acr-yellow-foreground/);
    expect(btn5.className).not.toMatch(/bg-amber-500/);

    rerender(<PainScaleSelector value={8} onChange={vi.fn()} />);
    const btn8 = screen.getByRole("radio", { name: /^nível 8$/i });
    expect(btn8.className).toMatch(/bg-acr-orange text-acr-orange-foreground/);
    expect(btn8.className).not.toMatch(/bg-orange-700/);

    rerender(<PainScaleSelector value={10} onChange={vi.fn()} />);
    const btn10 = screen.getByRole("radio", { name: /^nível 10$/i });
    expect(btn10.className).toMatch(/bg-acr-red text-acr-red-foreground/);
  });

  it("IT-PAIN-06: suporta navegação por teclado com setas direcionais e teclas Home e End", () => {
    const handleChange = vi.fn();
    render(<PainScaleSelector value={5} onChange={handleChange} />);
    const radiogroup = screen.getByRole("radiogroup", { name: /escala de dor de 0 a 10/i });

    fireEvent.keyDown(radiogroup, { key: "ArrowLeft" });
    expect(handleChange).toHaveBeenCalledWith(4);

    fireEvent.keyDown(radiogroup, { key: "ArrowDown" });
    expect(handleChange).toHaveBeenCalledWith(4);

    fireEvent.keyDown(radiogroup, { key: "ArrowRight" });
    expect(handleChange).toHaveBeenCalledWith(6);

    fireEvent.keyDown(radiogroup, { key: "ArrowUp" });
    expect(handleChange).toHaveBeenCalledWith(6);

    fireEvent.keyDown(radiogroup, { key: "Home" });
    expect(handleChange).toHaveBeenCalledWith(0);

    fireEvent.keyDown(radiogroup, { key: "End" });
    expect(handleChange).toHaveBeenCalledWith(10);
  });
});
