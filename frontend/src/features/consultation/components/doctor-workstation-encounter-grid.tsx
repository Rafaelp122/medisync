import { CheckCircle2, Lock } from "lucide-react";
import { useCallback, useRef, useState } from "react";
import type { LiveKitTokenResponse } from "@/api/generated/types.gen";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useConsultationEncounter } from "../context/consultation-encounter-provider";
import type { LivenessChannelMessage } from "../lib/liveness-channel";
import { CfmIdentityGate } from "./cfm-identity-gate";
import { FinalizeConsultationModal } from "./finalize-consultation-modal";
import { MedicalRecordsPane } from "./medical-records-pane";
import { PrescriptionBuilder } from "./prescription-builder";
import { SoapEditor } from "./soap-editor";
import { WorkstationMediaPane } from "./workstation-media-pane";

export interface DoctorWorkstationEncounterGridProps {
  livekitData?: LiveKitTokenResponse;
}

/**
 * Grade single-pane em 3 colunas do atendimento ativo isolada via `ConsultationEncounterProvider`.
 */
export function DoctorWorkstationEncounterGrid({
  livekitData,
}: DoctorWorkstationEncounterGridProps) {
  const { atendimento, isFinalizado, setLivenessResult } = useConsultationEncounter();
  const [modalFinalizarAberto, setModalFinalizarAberto] = useState(false);
  const livenessSenderRef = useRef<((message: LivenessChannelMessage) => Promise<void>) | null>(
    null,
  );

  const handleLivenessMessage = useCallback(
    (message: LivenessChannelMessage) => {
      if (message.type === "LIVENESS_RESULT") {
        setLivenessResult(message);
      }
    },
    [setLivenessResult],
  );

  const handleRegisterLivenessSender = useCallback(
    (sender: ((message: LivenessChannelMessage) => Promise<void>) | null) => {
      livenessSenderRef.current = sender;
    },
    [],
  );

  const scopedLivekitData =
    livekitData &&
    (!livekitData.room_name?.startsWith("room_") ||
      livekitData.room_name === `room_${atendimento.atendimentoId}`)
      ? livekitData
      : undefined;

  return (
    <>
      {isFinalizado && (
        <Alert className="py-2.5 text-xs border-acr-green/40 bg-acr-green/10 text-foreground">
          <CheckCircle2 className="size-4 text-acr-green inline mr-2" />
          <AlertDescription className="text-xs inline font-medium">
            Atendimento concluído com sucesso. Todos os registros clínicos PEP e prescrições foram
            congelados em modo imutável conforme a Resolução CFM nº 1.821/2007 e LGPD Art. 16.
          </AlertDescription>
        </Alert>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
        <section
          aria-label="Videoconferência e Identificação"
          className="lg:col-span-4 flex flex-col gap-3.5"
        >
          <WorkstationMediaPane
            atendimentoId={atendimento.atendimentoId}
            medicoNome={atendimento.medicoNome}
            remoteParticipantName={`${atendimento.pacienteNome} (Paciente)`}
            livekitToken={scopedLivekitData?.token}
            wsUrl={scopedLivekitData?.server_url}
            roomName={scopedLivekitData?.room_name}
            onLivenessMessage={handleLivenessMessage}
            onRegisterLivenessSender={handleRegisterLivenessSender}
          />

          <CfmIdentityGate />
        </section>

        <section
          aria-label="Prontuário Médico e Histórico"
          className="lg:col-span-4 flex flex-col gap-3.5"
        >
          <MedicalRecordsPane atendimentoId={atendimento.atendimentoId} />
        </section>

        <section
          aria-label="Evolução Clínica e Prescrição"
          className="lg:col-span-4 flex flex-col gap-3.5"
        >
          <SoapEditor atendimentoId={atendimento.atendimentoId} />

          <PrescriptionBuilder
            atendimentoId={atendimento.atendimentoId}
            atendimentoIniciadoEm={atendimento.chamadaIniciadaEm}
            onSendLivenessChallenge={(challenge) => {
              void livenessSenderRef.current?.({
                type: "LIVENESS_CHALLENGE",
                atendimento_id: atendimento.atendimentoId,
                challenge,
              });
            }}
          />

          {!isFinalizado && (
            <Button
              type="button"
              size="sm"
              onClick={() => setModalFinalizarAberto(true)}
              className="w-full h-9 text-xs font-semibold gap-2 bg-acr-green hover:bg-acr-green/90 text-acr-green-foreground shadow-xs"
            >
              <Lock className="size-4" />
              <span>Concluir Atendimento & Assinar</span>
            </Button>
          )}
        </section>
      </div>

      <FinalizeConsultationModal
        open={modalFinalizarAberto}
        onOpenChange={setModalFinalizarAberto}
        atendimentoId={atendimento.atendimentoId}
      />
    </>
  );
}
