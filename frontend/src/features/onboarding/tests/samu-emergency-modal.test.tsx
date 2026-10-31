import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SamuEmergencyModal } from "../components/samu-emergency-modal";

describe("SamuEmergencyModal (Salvaguarda SAMU 192 - RN04)", () => {
  it("IT-SAMU-01: Renderiza o modal de emergência quando aberto com role alertdialog", () => {
    render(
      <SamuEmergencyModal
        open={true}
        orientacoes="Ligue imediatamente para o SAMU 192 ou dirija-se à UPA mais próxima."
      />,
    );

    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /emergência médica/i })).toBeInTheDocument();
    expect(screen.getByText(/dirija-se à upa/i)).toBeInTheDocument();
  });

  it("IT-SAMU-02: Fornece botão de discagem rápida acessível com tel:192", () => {
    render(<SamuEmergencyModal open={true} />);

    const callButton = screen.getByRole("link", { name: /ligar para o samu 192/i });
    expect(callButton).toHaveAttribute("href", "tel:192");
  });

  it("IT-SAMU-03: Não renderiza conteúdo quando open é false", () => {
    render(<SamuEmergencyModal open={false} />);

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("IT-SAMU-04: Renderiza botão de correção voluntária por engano e aciona callback", async () => {
    const handleCorrigir = vi.fn();
    render(<SamuEmergencyModal open={true} onCorrigirSintomas={handleCorrigir} />);

    const btnCorrigir = screen.getByRole("button", {
      name: /selecionei por engano/i,
    });
    expect(btnCorrigir).toBeInTheDocument();
    btnCorrigir.click();
    expect(handleCorrigir).toHaveBeenCalledTimes(1);
  });

  it("IT-SAMU-05: Renderiza botão de confirmação de atendimento presencial e aciona callback", async () => {
    const handleSaida = vi.fn();
    render(<SamuEmergencyModal open={true} onConfirmarSaida={handleSaida} />);

    const btnSaida = screen.getByRole("button", {
      name: /entendi, vou procurar atendimento presencial/i,
    });
    expect(btnSaida).toBeInTheDocument();
    btnSaida.click();
    expect(handleSaida).toHaveBeenCalledTimes(1);
  });

  it("IT-SAMU-06: Dispara sinal sonoro de alerta de emergência ao abrir o modal (RN04)", () => {
    const mockStart = vi.fn();
    const mockStop = vi.fn();
    const mockSetValueAtTime = vi.fn();
    const mockExponentialRampToValueAtTime = vi.fn();
    const mockConnect = vi.fn();

    class FakeAudioContext {
      currentTime = 0;
      destination = {};
      createOscillator() {
        return {
          type: "sine",
          frequency: { setValueAtTime: mockSetValueAtTime },
          connect: mockConnect,
          start: mockStart,
          stop: mockStop,
        };
      }
      createGain() {
        return {
          gain: {
            setValueAtTime: mockSetValueAtTime,
            exponentialRampToValueAtTime: mockExponentialRampToValueAtTime,
          },
          connect: mockConnect,
        };
      }
    }

    vi.stubGlobal("AudioContext", FakeAudioContext);

    render(<SamuEmergencyModal open={true} />);

    expect(mockStart).toHaveBeenCalledTimes(2);
    expect(mockStop).toHaveBeenCalledTimes(2);

    vi.unstubAllGlobals();
  });
});
