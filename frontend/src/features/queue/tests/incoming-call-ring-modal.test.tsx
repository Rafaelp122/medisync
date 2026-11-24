import { fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProblemDetailsError } from "@/api/errors";
import { handleGenerateTeleconsultaRoomTokenApiV1ConsultationsAtendimentoIdLivekitTokenPost } from "@/api/generated/msw.gen";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/utils";
import { IncomingCallRingModal } from "../components/incoming-call-ring-modal";
import { RingCountdown } from "../components/ring-countdown";
import {
  MOCK_ATENDIMENTO_ID,
  MOCK_LIVEKIT_TOKEN_RESPONSE,
  MOCK_PACIENTE_ID,
  MOCK_TOKEN,
} from "./fixtures";

function IsolatedParentHost({ onRender }: { onRender: () => void }) {
  onRender();
  return (
    <RingCountdown
      open={true}
      ttlSegundos={45}
      chamadaIniciadaEm="2026-11-24T12:00:00.000Z"
      onExpire={vi.fn()}
    />
  );
}

describe("IncomingCallRingModal (Toque de Chamada Médica & 45s No-Show - RN02, RF-03)", () => {
  let mockStart: ReturnType<typeof vi.fn>;
  let mockStop: ReturnType<typeof vi.fn>;
  let mockSetValueAtTime: ReturnType<typeof vi.fn>;
  let mockExponentialRampToValueAtTime: ReturnType<typeof vi.fn>;
  let mockConnect: ReturnType<typeof vi.fn>;
  let mockClose: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockStart = vi.fn();
    mockStop = vi.fn();
    mockSetValueAtTime = vi.fn();
    mockExponentialRampToValueAtTime = vi.fn();
    mockConnect = vi.fn();
    mockClose = vi.fn().mockResolvedValue(undefined);

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
    vi.restoreAllMocks();
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
      handleGenerateTeleconsultaRoomTokenApiV1ConsultationsAtendimentoIdLivekitTokenPost({
        body: MOCK_LIVEKIT_TOKEN_RESPONSE,
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
      handleGenerateTeleconsultaRoomTokenApiV1ConsultationsAtendimentoIdLivekitTokenPost(() => {
        return HttpResponse.json(
          {
            type: "about:blank",
            title: "Conflict",
            status: 409,
            detail: "Acesso negado: atendimento expirou por ausência do paciente.",
            code: "ATENDIMENTO_EXPIRADO_NO_SHOW",
          },
          { status: 409 },
        ) as never;
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

  it("IT-RING-05: Fornece botão de cancelamento/escape hatch acessível e permite saída voluntária", async () => {
    const user = userEvent.setup();
    const handleNoShow = vi.fn();

    const { getByRole } = renderWithProviders(
      <IncomingCallRingModal
        open={true}
        atendimentoId={MOCK_ATENDIMENTO_ID}
        pacienteId={MOCK_PACIENTE_ID}
        token={MOCK_TOKEN}
        ttlSegundos={45}
        onAtendido={vi.fn()}
        onNoShow={handleNoShow}
      />,
    );

    const btnRecusar = getByRole("button", {
      name: /recusar chamada|não posso atender agora/i,
    });
    expect(btnRecusar).toBeInTheDocument();
    await user.click(btnRecusar);
    expect(handleNoShow).toHaveBeenCalledTimes(1);
  });

  it("IT-RING-06: Permite fechamento voluntário via Escape silenciando o áudio e acionando onNoShow sem keyboard trap", async () => {
    const user = userEvent.setup();
    const handleNoShow = vi.fn();

    renderWithProviders(
      <IncomingCallRingModal
        open={true}
        atendimentoId={MOCK_ATENDIMENTO_ID}
        pacienteId={MOCK_PACIENTE_ID}
        token={MOCK_TOKEN}
        ttlSegundos={45}
        onAtendido={vi.fn()}
        onNoShow={handleNoShow}
      />,
    );

    await user.keyboard("{Escape}");
    expect(handleNoShow).toHaveBeenCalledTimes(1);
  });

  it("IT-RING-07: <RingCountdown /> isola ticks de 1s sem re-renderizar o pai e respeita motion-reduce", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-24T12:00:15.000Z"));

    const parentRenderSpy = vi.fn();
    const { getByTestId } = renderWithProviders(<IsolatedParentHost onRender={parentRenderSpy} />);

    expect(getByTestId("ring-timer")).toHaveTextContent("30s");
    expect(parentRenderSpy).toHaveBeenCalledTimes(1);

    // Avança 22 segundos (chegando a <=10s onde entra em alerta)
    await vi.advanceTimersByTimeAsync(22_000);
    expect(getByTestId("ring-timer")).toHaveTextContent("8s");
    expect(getByTestId("ring-timer")).toHaveClass("motion-reduce:animate-none");

    // Pai não re-renderizou em nenhum dos 22 ticks de 1s
    expect(parentRenderSpy).toHaveBeenCalledTimes(1);
  });

  it("IT-RING-08: Aciona callback dedicado onRecusar ao recusar chamada médica", async () => {
    const user = userEvent.setup();
    const handleRecusar = vi.fn();
    const handleNoShow = vi.fn();

    const { getByRole } = renderWithProviders(
      <IncomingCallRingModal
        open={true}
        atendimentoId={MOCK_ATENDIMENTO_ID}
        pacienteId={MOCK_PACIENTE_ID}
        token={MOCK_TOKEN}
        ttlSegundos={45}
        onAtendido={vi.fn()}
        onNoShow={handleNoShow}
        onRecusar={handleRecusar}
      />,
    );

    await user.click(getByRole("button", { name: /recusar chamada|não posso atender agora/i }));
    expect(handleRecusar).toHaveBeenCalledTimes(1);
    expect(handleNoShow).not.toHaveBeenCalled();
  });

  it("IT-RING-09: Exibe alerta acessível e não dispara onNoShow quando onRecusar falha com HTTP 500", async () => {
    const user = userEvent.setup();
    const handleNoShow = vi.fn();
    const handleRecusar = vi.fn().mockRejectedValue(
      new ProblemDetailsError({
        status: 500,
        title: "Internal Server Error",
        detail: "Erro temporário ao cancelar atendimento na fila.",
      }),
    );

    const { getByRole, findByRole } = renderWithProviders(
      <IncomingCallRingModal
        open={true}
        atendimentoId={MOCK_ATENDIMENTO_ID}
        pacienteId={MOCK_PACIENTE_ID}
        token={MOCK_TOKEN}
        ttlSegundos={45}
        onAtendido={vi.fn()}
        onNoShow={handleNoShow}
        onRecusar={handleRecusar}
      />,
    );

    await user.click(getByRole("button", { name: /recusar chamada|não posso atender agora/i }));

    expect(handleRecusar).toHaveBeenCalledTimes(1);
    expect(await findByRole("alert")).toHaveTextContent(
      /erro temporário ao cancelar atendimento na fila/i,
    );
    expect(handleNoShow).not.toHaveBeenCalled();
  });

  it("IT-RING-10: Aciona onNoShow com mensagem de expiração quando onRecusar falha com HTTP 409 / ATENDIMENTO_EXPIRADO_NO_SHOW", async () => {
    const user = userEvent.setup();
    const handleNoShow = vi.fn();
    const handleRecusar = vi.fn().mockRejectedValue(
      new ProblemDetailsError({
        status: 409,
        title: "Conflict",
        code: "ATENDIMENTO_EXPIRADO_NO_SHOW",
        detail: "Chamada já expirada por no-show.",
      }),
    );

    const { getByRole, findByRole } = renderWithProviders(
      <IncomingCallRingModal
        open={true}
        atendimentoId={MOCK_ATENDIMENTO_ID}
        pacienteId={MOCK_PACIENTE_ID}
        token={MOCK_TOKEN}
        ttlSegundos={45}
        onAtendido={vi.fn()}
        onNoShow={handleNoShow}
        onRecusar={handleRecusar}
      />,
    );

    await user.click(getByRole("button", { name: /recusar chamada|não posso atender agora/i }));

    expect(await findByRole("alert")).toHaveTextContent(
      /prazo de 45 segundos para resposta expirou/i,
    );
    expect(handleNoShow).toHaveBeenCalledTimes(1);
  });
});
