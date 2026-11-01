import { fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/utils";
import { IncomingCallRingModal } from "../components/incoming-call-ring-modal";
import {
  MOCK_ATENDIMENTO_ID,
  MOCK_LIVEKIT_TOKEN_RESPONSE,
  MOCK_PACIENTE_ID,
  MOCK_TOKEN,
} from "./fixtures";

describe("IncomingCallRingModal (Toque de Chamada Médica & 45s No-Show - RN02, RF-03)", () => {
  const mockStart = vi.fn();
  const mockStop = vi.fn();
  const mockSetValueAtTime = vi.fn();
  const mockExponentialRampToValueAtTime = vi.fn();
  const mockConnect = vi.fn();
  const mockClose = vi.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    class FakeAudioContext {
      currentTime = 0;
      destination = {};
      state = "running";
      close = mockClose;
      resume = vi.fn().mockResolvedValue(undefined);
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
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("IT-RING-01: Renderiza modal fullscreen com role alertdialog, inicia chime sonoro e exibe timer de 45s", () => {
    const handleAtendido = vi.fn();
    const handleNoShow = vi.fn();

    const { getByRole, getByTestId, getByText } = renderWithProviders(
      <IncomingCallRingModal
        open={true}
        atendimentoId={MOCK_ATENDIMENTO_ID}
        pacienteId={MOCK_PACIENTE_ID}
        token={MOCK_TOKEN}
        ttlSegundos={45}
        onAtendido={handleAtendido}
        onNoShow={handleNoShow}
      />,
    );

    expect(getByRole("alertdialog")).toBeInTheDocument();
    expect(getByText(/o médico está chamando!/i)).toBeInTheDocument();
    expect(getByTestId("ring-timer")).toHaveTextContent("45s");

    // Verifica que o chime sonoro (2 osciladores do Web Audio API) foi disparado
    expect(mockStart).toHaveBeenCalledTimes(2);
    expect(mockStop).toHaveBeenCalledTimes(2);
  });

  it("IT-RING-02: Paciente clica em 'Entrar na Teleconsulta' dentro dos 45s e obtém token LiveKit", async () => {
    const user = userEvent.setup();
    const handleAtendido = vi.fn();
    const handleNoShow = vi.fn();

    server.use(
      http.post("*/api/v1/consultations/:atendimentoId/livekit/token", () => {
        return HttpResponse.json(MOCK_LIVEKIT_TOKEN_RESPONSE, { status: 200 });
      }),
    );

    const { getByRole } = renderWithProviders(
      <IncomingCallRingModal
        open={true}
        atendimentoId={MOCK_ATENDIMENTO_ID}
        pacienteId={MOCK_PACIENTE_ID}
        token={MOCK_TOKEN}
        ttlSegundos={45}
        onAtendido={handleAtendido}
        onNoShow={handleNoShow}
      />,
    );

    const btnEntrar = getByRole("button", { name: /entrar na teleconsulta/i });
    expect(btnEntrar).toBeEnabled();
    await user.click(btnEntrar);

    await waitFor(() => {
      expect(handleAtendido).toHaveBeenCalledTimes(1);
    });
    expect(handleAtendido).toHaveBeenCalledWith(MOCK_LIVEKIT_TOKEN_RESPONSE);
    expect(handleNoShow).not.toHaveBeenCalled();
    expect(mockClose).toHaveBeenCalled();
  });

  it("IT-RING-03: Contagem de 45s expira sem resposta: silencia áudio e aciona onNoShow (RN02)", async () => {
    vi.useFakeTimers();
    const handleAtendido = vi.fn();
    const handleNoShow = vi.fn();

    renderWithProviders(
      <IncomingCallRingModal
        open={true}
        atendimentoId={MOCK_ATENDIMENTO_ID}
        pacienteId={MOCK_PACIENTE_ID}
        token={MOCK_TOKEN}
        ttlSegundos={45}
        onAtendido={handleAtendido}
        onNoShow={handleNoShow}
      />,
    );

    expect(handleNoShow).not.toHaveBeenCalled();

    // Avança 45 segundos
    await vi.advanceTimersByTimeAsync(45_000);

    expect(handleNoShow).toHaveBeenCalledTimes(1);
    expect(handleAtendido).not.toHaveBeenCalled();
  });

  it("IT-RING-04: Tentativa tardia de ingresso com retorno HTTP 409 trata RFC 7807 e aciona no-show", async () => {
    const handleAtendido = vi.fn();
    const handleNoShow = vi.fn();

    server.use(
      http.post("*/api/v1/consultations/:atendimentoId/livekit/token", () => {
        return HttpResponse.json(
          {
            type: "about:blank",
            title: "Conflict",
            status: 409,
            detail: "Acesso negado: atendimento expirou por ausência do paciente.",
            code: "ATENDIMENTO_EXPIRADO_NO_SHOW",
          },
          { status: 409 },
        );
      }),
    );

    const { getByRole } = renderWithProviders(
      <IncomingCallRingModal
        open={true}
        atendimentoId={MOCK_ATENDIMENTO_ID}
        pacienteId={MOCK_PACIENTE_ID}
        token={MOCK_TOKEN}
        ttlSegundos={45}
        onAtendido={handleAtendido}
        onNoShow={handleNoShow}
      />,
    );

    const btnEntrar = getByRole("button", { name: /entrar na teleconsulta/i });
    fireEvent.click(btnEntrar);

    await waitFor(() => {
      expect(handleNoShow).toHaveBeenCalledTimes(1);
    });
    expect(handleAtendido).not.toHaveBeenCalled();
  });
});
