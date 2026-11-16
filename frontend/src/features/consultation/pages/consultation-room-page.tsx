import { useNavigate } from "@tanstack/react-router";
import { lazy, Suspense, useCallback, useRef, useState } from "react";
import type { LiveKitTokenResponse, LivenessChallengeResponse } from "@/api/generated/types.gen";
import { PatientLivenessModal } from "@/features/consultation/components/patient-liveness-modal";
import type {
  LivenessChannelMessage,
  LivenessResultMessage,
} from "@/features/consultation/lib/liveness-channel";
import { clearStoredCallData, type StoredPatientSession } from "@/lib/session-storage";

const LazyLiveKitVideoCall = lazy(
  () => import("@/features/consultation/components/livekit-video-call"),
);

export interface ConsultationRoomPageProps {
  session: StoredPatientSession;
  callData: LiveKitTokenResponse;
}

export function ConsultationRoomPage({ session, callData }: ConsultationRoomPageProps) {
  const navigate = useNavigate();
  const [activeChallenge, setActiveChallenge] = useState<LivenessChallengeResponse | null>(null);
  const livenessSenderRef = useRef<((message: LivenessChannelMessage) => Promise<void>) | null>(
    null,
  );
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleLivenessMessage = useCallback(
    (message: LivenessChannelMessage) => {
      if (message.type !== "LIVENESS_CHALLENGE") return;
      if (!session.atendimentoId || message.atendimento_id !== session.atendimentoId) return;
      if (closeTimerRef.current) {
        clearTimeout(closeTimerRef.current);
        closeTimerRef.current = null;
      }
      setActiveChallenge(message.challenge);
    },
    [session.atendimentoId],
  );

  const handleLivenessResult = useCallback((result: LivenessResultMessage) => {
    void livenessSenderRef.current?.(result);
    if (result.status === "APROVADO") {
      closeTimerRef.current = setTimeout(() => {
        setActiveChallenge(null);
      }, 1200);
    }
  }, []);

  const handleTeleconsultaEncerrada = () => {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
    }
    clearStoredCallData();
    navigate({ to: "/pos-consulta" });
  };

  return (
    <div className="w-full max-w-2xl mx-auto space-y-4">
      <Suspense
        fallback={
          <div className="h-80 flex items-center justify-center bg-slate-900 rounded-xl text-slate-300 text-xs">
            Conectando à Sala de Teleconsulta LiveKit SFU…
          </div>
        }
      >
        <LazyLiveKitVideoCall
          wsUrl={callData.server_url}
          token={callData.token}
          roomName={callData.room_name}
          participantName={callData.participant_identity}
          remoteParticipantName="Dr. Eduardo Rocha (Médico Plantonista)"
          onDisconnected={handleTeleconsultaEncerrada}
          onLivenessMessage={handleLivenessMessage}
          onRegisterLivenessSender={(sender) => {
            livenessSenderRef.current = sender;
          }}
          className="min-h-[420px]"
        />
      </Suspense>

      {activeChallenge && session.atendimentoId && (
        <PatientLivenessModal
          key={activeChallenge.challenge_id}
          atendimentoId={session.atendimentoId}
          token={session.token}
          challenge={activeChallenge}
          onResult={handleLivenessResult}
          onClose={() => setActiveChallenge(null)}
        />
      )}
    </div>
  );
}
