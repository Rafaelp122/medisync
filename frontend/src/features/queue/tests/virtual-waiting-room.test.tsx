import { waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http, ws } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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
    vi.stubGlobal("PublicKeyCredential", undefined);

    server.use(
      queueWs.addEventListener("connection", ({ client }) => {
        client.send(JSON.stringify({ event: "CONNECTED" }));
      }),
      http.get("*/api/v1/fila/posicao/:atendimentoId", () => {
        return HttpResponse.json(MOCK_POSICAO_RESPONSE, { status: 200 });
      }),
    );
  });

  afterEach(() => {
    vi.useRealTimers();
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
    expect(getByTestId("atendimento-id-completo")).toHaveTextContent(MOCK_SESSION.atendimentoId);
    expect(getByText(/urgente \(amarelo\)/i)).toBeInTheDocument();
    expect(getByText(/sentiu piora nos sintomas\?/i)).toBeInTheDocument();
  });

  it("IT-WAIT-02: Acionamento de piora com reclassificação para Laranja (Nível 2)", async () => {
    const user = userEvent.setup();

    server.use(
      http.post("*/api/v1/fila/piora", () => {
        return HttpResponse.json(MOCK_PIORA_RECLASSIFICADO_RESPONSE, { status: 200 });
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
    expect(getByText(/muito urgente \(laranja\)/i)).toBeInTheDocument();
  });

  it("IT-WAIT-03: Acionamento de piora com emergência máxima SAMU 192 (RF-06 / RN04)", async () => {
    const user = userEvent.setup();

    server.use(
      http.post("*/api/v1/fila/piora", () => {
        return HttpResponse.json(MOCK_PIORA_SAMU_RESPONSE, { status: 200 });
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
      http.get("*/api/v1/fila/posicao/:atendimentoId", () => {
        return HttpResponse.json(
          {
            ...MOCK_POSICAO_RESPONSE,
            status: "CHAMANDO_PACIENTE",
          },
          { status: 200 },
        );
      }),
      http.post("*/api/v1/consultations/:atendimentoId/livekit/token", () => {
        return HttpResponse.json(MOCK_LIVEKIT_TOKEN_RESPONSE, { status: 200 });
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
      http.get("*/api/v1/fila/posicao/:atendimentoId", () => {
        return HttpResponse.json(
          {
            ...MOCK_POSICAO_RESPONSE,
            status: "CHAMANDO_PACIENTE",
          },
          { status: 200 },
        );
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

  it("IT-WAIT-06: Cancelamento voluntário da fila transiciona para estado CANCELADO", async () => {
    const user = userEvent.setup();

    server.use(
      http.post("*/api/v1/fila/cancelar/:atendimentoId", () => {
        return HttpResponse.json(
          {
            atendimento_id: MOCK_ATENDIMENTO_ID,
            status: "CANCELADO",
            cancelado_em: new Date().toISOString(),
            motivo: "Desistência voluntária pelo paciente",
          },
          { status: 200 },
        );
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

    expect(getByTestId("atendimento-id-completo")).toHaveTextContent(MOCK_SESSION.atendimentoId);

    const btnComplementar = getByRole("button", { name: /completar cadastro/i });
    await user.click(btnComplementar);

    expect(handleComplementar).toHaveBeenCalledTimes(1);
  });
});
