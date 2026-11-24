import { waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, ws } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  handleCancelarAtendimentoFilaApiV1FilaCancelarAtendimentoIdPost,
  handleComunicarPioraClinicaApiV1FilaPioraPost,
  handleGenerateTeleconsultaRoomTokenApiV1ConsultationsAtendimentoIdLivekitTokenPost,
  handleObterPosicaoFilaApiV1FilaPosicaoAtendimentoIdGet,
  handleRegularizarAtendimentoFilaApiV1FilaAtendimentosAtendimentoIdRegularizarPost,
} from "@/api/generated/msw.gen";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/utils";
import { VirtualWaitingRoom } from "../components/virtual-waiting-room";
import {
  MOCK_ATENDIMENTO_ID,
  MOCK_LIVEKIT_TOKEN_RESPONSE,
  MOCK_PIORA_RECLASSIFICADO_RESPONSE,
  MOCK_PIORA_SAMU_RESPONSE,
  MOCK_POSICAO_RESPONSE,
  MOCK_SESSION,
} from "./fixtures";

const queueWs = ws.link(/.*\/ws\/queue\/.*/);

describe("VirtualWaitingRoom (Integração de Tela - RF-03, RF-06, RN01, RN02)", () => {
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
    vi.stubGlobal("PublicKeyCredential", undefined);

    server.use(
      queueWs.addEventListener("connection", ({ client }) => {
        client.send(JSON.stringify({ event: "CONNECTED" }));
      }),
      handleObterPosicaoFilaApiV1FilaPosicaoAtendimentoIdGet({
        body: MOCK_POSICAO_RESPONSE,
      }),
    );
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("IT-WAIT-01: Renderiza a sala de espera com posição ordinal, tempo estimado e badge ACR", async () => {
    const { getByText, getByTestId } = renderWithProviders(
      <VirtualWaitingRoom session={MOCK_SESSION} />,
    );

    expect(getByText(/sala de espera virtual/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(getByTestId("posicao-ordinal")).toHaveTextContent("4º na fila");
    });
    expect(getByTestId("tempo-estimado")).toHaveTextContent("Aproximadamente 15 minutos");
    expect(getByTestId("atendimento-id-completo")).toHaveTextContent(
      MOCK_SESSION.atendimentoId ?? "",
    );
    expect(getByText(/amarelo: urgente/i)).toBeInTheDocument();
    expect(getByText(/sentiu piora nos sintomas\?/i)).toBeInTheDocument();
  });

  it("IT-WAIT-02: Acionamento de piora com reclassificação para Laranja (Nível 2)", async () => {
    const user = userEvent.setup();

    server.use(
      handleComunicarPioraClinicaApiV1FilaPioraPost({
        body: MOCK_PIORA_RECLASSIFICADO_RESPONSE,
      }),
    );

    const { getByRole, getByLabelText, getByText, queryByRole } = renderWithProviders(
      <VirtualWaitingRoom session={MOCK_SESSION} />,
    );

    // Clica no botão de relatar piora
    const btnPiora = getByRole("button", { name: /relatar piora/i });
    await user.click(btnPiora);

    // Modal de piora abre
    expect(getByRole("dialog")).toBeInTheDocument();
    expect(getByText(/salvaguarda de piora clínica/i)).toBeInTheDocument();

    // Seleciona sintoma de alarme
    const chkFaltaAr = getByLabelText(/falta de ar intensa/i);
    await user.click(chkFaltaAr);

    // Envia reavaliação
    const btnEnviar = getByRole("button", { name: /enviar reavaliação/i });
    await user.click(btnEnviar);

    // Modal fecha e prioridade é atualizada para Nível 2 Laranja
    await waitFor(() => {
      expect(queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(getByText(/laranja: muito urgente/i)).toBeInTheDocument();
  });

  it("IT-WAIT-03: Acionamento de piora com emergência máxima SAMU 192 (RF-06 / RN04)", async () => {
    const user = userEvent.setup();

    server.use(
      handleComunicarPioraClinicaApiV1FilaPioraPost({
        body: MOCK_PIORA_SAMU_RESPONSE,
      }),
    );

    const { getByRole, getByLabelText, getByText } = renderWithProviders(
      <VirtualWaitingRoom session={MOCK_SESSION} />,
    );

    // Clica em relatar piora
    await user.click(getByRole("button", { name: /relatar piora/i }));

    // Seleciona dor no peito
    await user.click(getByLabelText(/dor ou aperto forte no peito/i));

    // Envia reavaliação
    await user.click(getByRole("button", { name: /enviar reavaliação/i }));

    // Deve abrir o SamuEmergencyModal com role alertdialog e discador 192
    await waitFor(() => {
      expect(getByRole("alertdialog")).toBeInTheDocument();
    });
    expect(getByText(/emergência médica/i)).toBeInTheDocument();
    const samuLink = getByRole("link", { name: /ligar para o samu 192/i });
    expect(samuLink).toHaveAttribute("href", "tel:192");
  });

  it("IT-WAIT-04: Transição para chamada médica e atendimento com LiveKit", async () => {
    const user = userEvent.setup();
    const handleAtendimentoIniciado = vi.fn();

    // Mock do polling retornando CHAMANDO_PACIENTE
    server.use(
      handleObterPosicaoFilaApiV1FilaPosicaoAtendimentoIdGet({
        body: {
          ...MOCK_POSICAO_RESPONSE,
          status: "CHAMANDO_PACIENTE",
        },
      }),
      handleGenerateTeleconsultaRoomTokenApiV1ConsultationsAtendimentoIdLivekitTokenPost({
        body: MOCK_LIVEKIT_TOKEN_RESPONSE,
      }),
    );

    const { getByRole, getByText } = renderWithProviders(
      <VirtualWaitingRoom
        session={MOCK_SESSION}
        onAtendimentoIniciado={handleAtendimentoIniciado}
      />,
    );

    // O modal de chamada deve surgir
    await waitFor(() => {
      expect(getByRole("alertdialog")).toBeInTheDocument();
    });
    expect(getByText(/o médico está chamando!/i)).toBeInTheDocument();

    // Paciente atende a chamada
    const btnEntrar = getByRole("button", { name: /entrar na teleconsulta/i });
    await user.click(btnEntrar);

    await waitFor(() => {
      expect(handleAtendimentoIniciado).toHaveBeenCalledWith(MOCK_LIVEKIT_TOKEN_RESPONSE);
    });
  });

  it("IT-WAIT-05: Expiração de chamada médica transiciona tela para PACIENTE_AUSENTE (No-Show)", async () => {
    vi.useFakeTimers();

    server.use(
      handleObterPosicaoFilaApiV1FilaPosicaoAtendimentoIdGet({
        body: {
          ...MOCK_POSICAO_RESPONSE,
          status: "CHAMANDO_PACIENTE",
        },
      }),
    );

    const { getByRole, getByText, queryByRole } = renderWithProviders(
      <VirtualWaitingRoom
        session={{
          ...MOCK_SESSION,
          status: "CHAMANDO_PACIENTE",
        }}
      />,
    );

    expect(getByRole("alertdialog")).toBeInTheDocument();

    await vi.advanceTimersByTimeAsync(46_000);

    expect(queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(getByText(/chamada não atendida/i)).toBeInTheDocument();
    expect(getByText(/não houve confirmação dentro da janela de 45 segundos/i)).toBeInTheDocument();
  });

  it("IT-WAIT-06: Cancelamento voluntário da fila transiciona para estado CANCELADO_PACIENTE", async () => {
    const user = userEvent.setup();

    server.use(
      handleCancelarAtendimentoFilaApiV1FilaCancelarAtendimentoIdPost({
        body: {
          atendimento_id: MOCK_ATENDIMENTO_ID,
          status: "CANCELADO_PACIENTE",
          cancelado_em: new Date().toISOString(),
          motivo: "Desistência voluntária pelo paciente",
        },
      }),
    );

    const { getByRole, getByText } = renderWithProviders(
      <VirtualWaitingRoom session={MOCK_SESSION} />,
    );

    // Clica em desistir
    const btnDesistir = getByRole("button", { name: /desistir do atendimento/i });
    await user.click(btnDesistir);

    // Confirma desistência no modal
    expect(getByText(/tem certeza de que deseja sair da fila virtual\?/i)).toBeInTheDocument();
    const btnConfirmar = getByRole("button", { name: /confirmar desistência/i });
    await user.click(btnConfirmar);

    // Transiciona para a tela de cancelamento
    await waitFor(() => {
      expect(getByText(/atendimento cancelado/i)).toBeInTheDocument();
    });
  });

  it("IT-WAIT-07: Clique em 'Completar Cadastro' aciona callback onComplementarCadastro", async () => {
    const user = userEvent.setup();
    const handleComplementar = vi.fn();

    const { getByRole, getByTestId } = renderWithProviders(
      <VirtualWaitingRoom session={MOCK_SESSION} onComplementarCadastro={handleComplementar} />,
    );

    expect(getByTestId("atendimento-id-completo")).toHaveTextContent(
      MOCK_SESSION.atendimentoId ?? "",
    );

    const btnComplementar = getByRole("button", { name: /completar cadastro/i });
    await user.click(btnComplementar);

    expect(handleComplementar).toHaveBeenCalledTimes(1);
  });

  it("IT-WAIT-08: Convocação médica recebida via WebSocket dispara o modal de chamada imediatamente (DoD 1)", async () => {
    let wsClient: { send: (data: string) => void } | null = null;
    server.use(
      queueWs.addEventListener("connection", ({ client }) => {
        wsClient = client;
        client.send(JSON.stringify({ event: "CONNECTED" }));
      }),
    );

    const { getByRole, queryByRole } = renderWithProviders(
      <VirtualWaitingRoom session={MOCK_SESSION} />,
    );

    expect(queryByRole("alertdialog")).not.toBeInTheDocument();

    await waitFor(() => {
      expect(wsClient).not.toBeNull();
    });

    // Envia evento CALLED em tempo real pelo WebSocket
    if (wsClient) {
      const clientWithSend: { send: (data: string) => void } = wsClient;
      clientWithSend.send(
        JSON.stringify({
          event: "CALLED",
          atendimento_id: MOCK_ATENDIMENTO_ID,
          medico_id: "018f3a5b-7b2c-4b2c-8b2c-018f3a5b7b99",
          status: "CHAMANDO_PACIENTE",
          ttl_segundos: 45,
          chamada_iniciada_em: new Date().toISOString(),
        }),
      );
    }

    // O modal deve abrir instantaneamente
    await waitFor(() => {
      expect(getByRole("alertdialog")).toBeInTheDocument();
    });
  });

  it("IT-WAIT-09: Permite regularizar elegibilidade pendente e promove paciente para fila ativa (US-05)", async () => {
    let statusAtual = "TRIADO_AGUARDANDO_ELEGIBILIDADE";
    let regularizarCalled = false;

    server.use(
      handleObterPosicaoFilaApiV1FilaPosicaoAtendimentoIdGet(() => {
        return HttpResponse.json({
          ...MOCK_POSICAO_RESPONSE,
          status: statusAtual,
        });
      }),
      handleRegularizarAtendimentoFilaApiV1FilaAtendimentosAtendimentoIdRegularizarPost(() => {
        regularizarCalled = true;
        statusAtual = "APTO_PARA_CHAMADA";
        return HttpResponse.json({
          atendimento_id: MOCK_ATENDIMENTO_ID,
          promovido: true,
          status: "APTO_PARA_CHAMADA",
          score: 1500,
          tipo_contingencia: "REGULARIZACAO_ELEGIBILIDADE",
          mensagem: "Atendimento regularizado e promovido para fila ativa.",
        });
      }),
    );

    const { findByRole, queryByRole } = renderWithProviders(
      <VirtualWaitingRoom session={MOCK_SESSION} />,
    );

    const regularizarButton = await findByRole("button", {
      name: /regularizar elegibilidade agora/i,
    });
    expect(regularizarButton).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(regularizarButton);

    await waitFor(() => {
      expect(regularizarCalled).toBe(true);
      expect(
        queryByRole("button", { name: /regularizar elegibilidade agora/i }),
      ).not.toBeInTheDocument();
    });
  });

  it("IT-WAIT-10: PioraClinicaModal envia IDs canônicos de triage (dispneia_grave, dor_toracica_irradiada) via RHF", async () => {
    const user = userEvent.setup();
    let capturedBody: { novos_sintomas?: string[] } | null = null;

    server.use(
      handleComunicarPioraClinicaApiV1FilaPioraPost(async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json(MOCK_PIORA_RECLASSIFICADO_RESPONSE, { status: 200 });
      }),
    );

    const { getByRole, getByLabelText } = renderWithProviders(
      <VirtualWaitingRoom session={MOCK_SESSION} />,
    );

    await user.click(getByRole("button", { name: /relatar piora/i }));
    await user.click(getByLabelText(/falta de ar intensa/i));
    await user.click(getByLabelText(/dor ou aperto forte no peito/i));
    await user.click(getByRole("button", { name: /enviar reavaliação/i }));

    await waitFor(() => {
      expect(capturedBody?.novos_sintomas).toEqual(["dispneia_grave", "dor_toracica_irradiada"]);
    });
  });

  it("IT-WAIT-11: Restaura countdown restante após F5 via chamada_iniciada_em/ttl_segundos e recusa via POST /fila/cancelar", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const now = new Date("2026-11-24T12:00:20.000Z");
    vi.setSystemTime(now);

    const cancelSpy = vi.fn();

    server.use(
      handleObterPosicaoFilaApiV1FilaPosicaoAtendimentoIdGet(() => {
        return HttpResponse.json({
          ...MOCK_POSICAO_RESPONSE,
          status: "CHAMANDO_PACIENTE",
          chamada_iniciada_em: "2026-11-24T12:00:00.000Z",
          ttl_segundos: 45,
        });
      }),
      handleCancelarAtendimentoFilaApiV1FilaCancelarAtendimentoIdPost(() => {
        cancelSpy();
        return HttpResponse.json({
          atendimento_id: MOCK_ATENDIMENTO_ID,
          status: "CANCELADO_PACIENTE",
          cancelado_em: now.toISOString(),
          motivo: "Chamada médica recusada pelo paciente",
        });
      }),
    );

    const { getByTestId, getByRole, getByText, queryByRole } = renderWithProviders(
      <VirtualWaitingRoom session={MOCK_SESSION} />,
    );

    await waitFor(() => {
      expect(getByRole("alertdialog")).toBeInTheDocument();
    });
    expect(getByTestId("ring-timer")).toHaveTextContent("25s");

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.click(getByRole("button", { name: /não posso atender agora|recusar chamada/i }));

    await waitFor(() => {
      expect(cancelSpy).toHaveBeenCalledTimes(1);
    });
    expect(queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(getByText(/atendimento cancelado/i)).toBeInTheDocument();
  });

  it("IT-WAIT-12: Para polling e WS em estados terminais CANCELADO_PACIENTE, PACIENTE_AUSENTE e CONCLUIDO", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });

    for (const [terminalStatus, expectedHeading] of [
      ["CANCELADO_PACIENTE", /atendimento cancelado/i],
      ["PACIENTE_AUSENTE", /chamada não atendida/i],
      ["CONCLUIDO", /atendimento concluído/i],
    ] as const) {
      let pollCount = 0;
      let wsClosed = false;

      server.use(
        queueWs.addEventListener("connection", ({ client }) => {
          client.send(JSON.stringify({ event: "CONNECTED" }));
          client.addEventListener("close", () => {
            wsClosed = true;
          });
        }),
        handleObterPosicaoFilaApiV1FilaPosicaoAtendimentoIdGet(() => {
          pollCount += 1;
          return HttpResponse.json({
            ...MOCK_POSICAO_RESPONSE,
            status: terminalStatus,
          });
        }),
      );

      const { getByText, unmount } = renderWithProviders(
        <VirtualWaitingRoom session={MOCK_SESSION} />,
      );

      await waitFor(() => {
        expect(getByText(expectedHeading)).toBeInTheDocument();
      });

      const countAtTerminal = pollCount;
      await vi.advanceTimersByTimeAsync(15_000);

      expect(pollCount).toBe(countAtTerminal);
      await waitFor(() => {
        expect(wsClosed).toBe(true);
      });
      unmount();
    }
  });
});
