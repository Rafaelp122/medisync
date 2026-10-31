import { render, screen } from "@testing-library/react";
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
        screen.getByRole("button", { name: new RegExp(`^nível ${i}$`, "i") }),
      ).toBeInTheDocument();
    }

    // Clicar no nível 4
    const btn4 = screen.getByRole("button", { name: /^nível 4$/i });
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
});
