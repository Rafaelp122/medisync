import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  handleEmitirDocumentoClinicoApiV1ConsultationsAtendimentoIdDocumentsPost,
  handleSolicitarDesafioLivenessPrescricaoApiV1ConsultationsAtendimentoIdPrescriptionsLivenessChallengePost,
  handleValidarPrescricaoMedicamentoApiV1ConsultationsAtendimentoIdPrescriptionsValidatePost,
  handleVerificarLivenessPrescricaoApiV1ConsultationsAtendimentoIdPrescriptionsLivenessVerifyPost,
} from "@/api/generated/msw.gen";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/utils";
import { PrescriptionBuilder } from "../components/prescription-builder";
import { createDocumentoClinicoResponse, MOCK_ATENDIMENTO_ID } from "./fixtures";

async function addControlledMedication(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/medicamento \/ princípio ativo/i), "Fluoxetina 20mg");
  await user.type(screen.getByLabelText(/dosagem/i), "1 cp");
  await user.type(screen.getByLabelText(/posologia/i), "1 comprimido ao dia");
  await user.click(screen.getByLabelText(/controle especial \(lista c1\)/i));
  await user.click(screen.getByRole("button", { name: /adicionar à receita/i }));
}

describe("CameraLivenessCheck & Trava Lista C1 (US-15)", () => {
  beforeEach(() => {
    server.use(
      handleValidarPrescricaoMedicamentoApiV1ConsultationsAtendimentoIdPrescriptionsValidatePost({
        status: 200,
        body: {
          status: "PERMITIDO",
          medicamento: "Fluoxetina 20mg",
          mensagem: "Substância permitida para prescrição digital.",
        },
      }),
    );
  });

  it("bloqueia emissão de receita Lista C1 até concluir prova de vida ou justificativa", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <PrescriptionBuilder
        atendimentoId={MOCK_ATENDIMENTO_ID}
        identidadeVerificada={true}
        token="mock-medico-jwt"
      />,
    );

    await addControlledMedication(user);

    expect(screen.getByTestId("camera-liveness-check")).toBeInTheDocument();
    expect(screen.getByText(/Prova de Vida Facial Obrigatória/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /emitir prescrição digital/i })).toBeDisabled();
  });

  it("aprova desafio facial e envia hash SHA-256 com tipo RECEITA_CONTROLE_ESPECIAL_C1", async () => {
    const expectedHash = `sha256_${"a".repeat(64)}`;
    let capturedPayload: Record<string, unknown> | null = null;

    server.use(
      handleSolicitarDesafioLivenessPrescricaoApiV1ConsultationsAtendimentoIdPrescriptionsLivenessChallengePost(
        {
          status: 200,
          body: {
            challenge_id: "ch_us15_001",
            instrucoes_movimento: ["piscar_olhos", "sorrir"],
            timeout_segundos: 60,
          },
        },
      ),
      handleVerificarLivenessPrescricaoApiV1ConsultationsAtendimentoIdPrescriptionsLivenessVerifyPost(
        {
          status: 200,
          body: {
            status: "APROVADO",
            liveness_score: 0.98,
            verificacao_hash: expectedHash,
            validado_em: "2026-11-15T12:00:00Z",
          },
        },
      ),
      http.post("*/api/v1/consultations/:atendimento_id/documents", async ({ request }) => {
        capturedPayload = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          createDocumentoClinicoResponse({
            tipo_documento: "RECEITA_CONTROLE_ESPECIAL_C1",
            liveness_verificacao_hash: expectedHash,
          }),
          { status: 201 },
        );
      }),
    );

    const onIssued = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <PrescriptionBuilder
        atendimentoId={MOCK_ATENDIMENTO_ID}
        identidadeVerificada={true}
        token="mock-medico-jwt"
        onPrescriptionIssued={onIssued}
      />,
    );

    await addControlledMedication(user);

    await user.click(screen.getByRole("button", { name: /iniciar prova de vida facial/i }));
    await screen.findByText(/piscar os olhos naturalmente/i);

    await user.click(screen.getByRole("button", { name: /capturar e validar vivacidade/i }));
    await screen.findByText(/prova de vida facial aprovada/i);

    const emitBtn = screen.getByRole("button", { name: /emitir prescrição digital/i });
    expect(emitBtn).toBeEnabled();
    await user.click(emitBtn);

    await waitFor(() => expect(onIssued).toHaveBeenCalledTimes(1));
    expect(capturedPayload).toMatchObject({
      tipo_documento: "RECEITA_CONTROLE_ESPECIAL_C1",
      liveness_verificacao_hash: expectedHash,
    });
  });

  it("exibe alerta e mantém emissão bloqueada quando backend detecta spoofing facial (422)", async () => {
    server.use(
      handleSolicitarDesafioLivenessPrescricaoApiV1ConsultationsAtendimentoIdPrescriptionsLivenessChallengePost(
        {
          status: 200,
          body: {
            challenge_id: "ch_spoof_002",
            instrucoes_movimento: ["piscar_olhos"],
            timeout_segundos: 60,
          },
        },
      ),
      http.post("*/api/v1/consultations/:atendimento_id/prescriptions/liveness/verify", () => {
        return HttpResponse.json(
          {
            type: "https://medisync.app/errors/spoofing-facial-detectado",
            title: "Prova de Vida Reprovada",
            status: 422,
            code: "SPOOFING_FACIAL_DETECTADO",
            detail: "Prova de vida reprovada por suspeita de foto estática (score 0.42).",
          },
          { status: 422 },
        );
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(
      <PrescriptionBuilder
        atendimentoId={MOCK_ATENDIMENTO_ID}
        identidadeVerificada={true}
        token="mock-medico-jwt"
      />,
    );

    await addControlledMedication(user);
    await user.click(screen.getByRole("button", { name: /iniciar prova de vida facial/i }));
    await screen.findByRole("button", { name: /capturar e validar vivacidade/i });
    await user.click(screen.getByRole("button", { name: /capturar e validar vivacidade/i }));

    await screen.findByText(/suspeita de foto estática/i);
    expect(screen.getByRole("button", { name: /emitir prescrição digital/i })).toBeDisabled();
  });

  it("permite emissão com justificativa clínica de contingência (>= 10 caracteres)", async () => {
    let capturedBody: Record<string, unknown> | null = null;
    server.use(
      handleEmitirDocumentoClinicoApiV1ConsultationsAtendimentoIdDocumentsPost(
        async ({ request }) => {
          capturedBody = (await request.json()) as Record<string, unknown>;
          return HttpResponse.json(
            createDocumentoClinicoResponse({
              tipo_documento: "RECEITA_CONTROLE_ESPECIAL_C1",
              justificativa_excecao_liveness: "Paciente acamado sem câmera disponível",
            }),
            { status: 201 },
          );
        },
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(
      <PrescriptionBuilder
        atendimentoId={MOCK_ATENDIMENTO_ID}
        identidadeVerificada={true}
        token="mock-medico-jwt"
      />,
    );

    await addControlledMedication(user);
    await user.click(screen.getByRole("button", { name: /declarar contingência clínica/i }));

    const inputJustificativa = screen.getByLabelText(
      /justificativa médica para dispensa de prova de vida/i,
    );
    await user.type(inputJustificativa, "Paciente acamado sem câmera disponível");

    const emitBtn = screen.getByRole("button", { name: /emitir prescrição digital/i });
    expect(emitBtn).toBeEnabled();
    await user.click(emitBtn);

    await waitFor(() => expect(capturedBody).not.toBeNull());
    expect(capturedBody).toMatchObject({
      tipo_documento: "RECEITA_CONTROLE_ESPECIAL_C1",
      justificativa_excecao_liveness: "Paciente acamado sem câmera disponível",
    });
  });
});
