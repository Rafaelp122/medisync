import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { handleVerificarLivenessPrescricaoApiV1ConsultationsAtendimentoIdPrescriptionsLivenessVerifyPost } from "@/api/generated/msw.gen";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/utils";
import { PatientLivenessModal } from "../components/patient-liveness-modal";
import { MOCK_ATENDIMENTO_ID } from "./fixtures";

const originalMediaDevicesDescriptor =
  typeof navigator !== "undefined"
    ? Object.getOwnPropertyDescriptor(navigator, "mediaDevices")
    : undefined;

describe("PatientLivenessModal (Captura Facial do Paciente - US-15)", () => {
  let trackStopSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    trackStopSpy = vi.fn();
    Object.defineProperty(navigator, "mediaDevices", {
      value: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [{ stop: trackStopSpy }],
        }),
      },
      configurable: true,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    if (typeof navigator !== "undefined") {
      if (originalMediaDevicesDescriptor) {
        Object.defineProperty(navigator, "mediaDevices", originalMediaDevicesDescriptor);
      } else {
        Reflect.deleteProperty(navigator, "mediaDevices");
      }
    }
  });

  it("exibe instruções com aria-live assertive, envia verify com token do paciente e retorna hash", async () => {
    const expectedHash = `sha256_${"c".repeat(64)}`;
    let capturedAuth: string | null = null;
    let capturedChallengeId: unknown;

    server.use(
      handleVerificarLivenessPrescricaoApiV1ConsultationsAtendimentoIdPrescriptionsLivenessVerifyPost(
        async ({ request }) => {
          capturedAuth = request.headers.get("Authorization");
          const body = (await request.json()) as { challenge_id?: string };
          capturedChallengeId = body.challenge_id;
          return HttpResponse.json({
            status: "APROVADO",
            liveness_score: 0.97,
            verificacao_hash: expectedHash,
            validado_em: "2026-11-15T12:00:00Z",
          });
        },
      ),
    );

    const onResult = vi.fn();
    const user = userEvent.setup();
    const { unmount } = renderWithProviders(
      <PatientLivenessModal
        atendimentoId={MOCK_ATENDIMENTO_ID}
        token="patient-intake-token"
        challenge={{
          challenge_id: "ch_patient_01",
          instrucoes_movimento: ["piscar_olhos", "sorrir"],
          timeout_segundos: 60,
        }}
        onResult={onResult}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByTestId("patient-liveness-modal")).toBeInTheDocument();
    expect(screen.getByText(/pisque os olhos lentamente para a câmera/i)).toBeInTheDocument();

    const confirmBtn = screen.getByRole("button", { name: /confirmar e enviar prova de vida/i });
    await user.click(confirmBtn);

    await screen.findByRole("status");
    expect(capturedAuth).toBe("Bearer patient-intake-token");
    expect(capturedChallengeId).toBe("ch_patient_01");
    expect(onResult).toHaveBeenCalledWith({
      type: "LIVENESS_RESULT",
      atendimento_id: MOCK_ATENDIMENTO_ID,
      status: "APROVADO",
      verificacao_hash: expectedHash,
      liveness_score: 0.97,
    });

    unmount();
    await waitFor(() => expect(trackStopSpy).toHaveBeenCalled());
  });

  it("exibe alerta acessível e emite REPROVADO quando backend acusa spoofing (422)", async () => {
    server.use(
      handleVerificarLivenessPrescricaoApiV1ConsultationsAtendimentoIdPrescriptionsLivenessVerifyPost(
        () => {
          return HttpResponse.json(
            {
              status: 422,
              title: "Prova de Vida Reprovada",
              code: "SPOOFING_FACIAL_DETECTADO",
              detail: "Suspeita de imagem estática na câmera do paciente.",
            },
            { status: 422 },
          ) as never;
        },
      ),
    );

    const onResult = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <PatientLivenessModal
        atendimentoId={MOCK_ATENDIMENTO_ID}
        token="patient-intake-token"
        challenge={{
          challenge_id: "ch_patient_spoof",
          instrucoes_movimento: ["piscar_olhos"],
          timeout_segundos: 60,
        }}
        onResult={onResult}
        onClose={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: /confirmar e enviar prova de vida/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/imagem estática/i);
    expect(onResult).toHaveBeenCalledWith({
      type: "LIVENESS_RESULT",
      atendimento_id: MOCK_ATENDIMENTO_ID,
      status: "REPROVADO",
      detail: "Suspeita de imagem estática na câmera do paciente.",
    });
  });

  it("exibe countdown regressivo real a partir de challenge.timeout_segundos", async () => {
    vi.useFakeTimers();

    renderWithProviders(
      <PatientLivenessModal
        atendimentoId={MOCK_ATENDIMENTO_ID}
        token="patient-intake-token"
        challenge={{
          challenge_id: "ch_countdown_01",
          instrucoes_movimento: ["piscar_olhos"],
          timeout_segundos: 45,
        }}
        onResult={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByTestId("liveness-timeout-countdown")).toHaveTextContent(/45s/);
    await vi.advanceTimersByTimeAsync(3_000);
    expect(screen.getByTestId("liveness-timeout-countdown")).toHaveTextContent(/42s/);
  });
});
