import { useNavigate } from "@tanstack/react-router";
import { lazy, Suspense } from "react";
import type { LiveKitTokenResponse } from "@/api/generated/types.gen";
import { clearStoredCallData, type StoredPatientSession } from "@/lib/session-storage";

const LazyLiveKitVideoCall = lazy(
  () => import("@/features/consultation/components/livekit-video-call"),
);

export interface ConsultationRoomPageProps {
  session: StoredPatientSession;
  callData: LiveKitTokenResponse;
}

export function ConsultationRoomPage({ callData }: ConsultationRoomPageProps) {
  const navigate = useNavigate();

  const handleTeleconsultaEncerrada = () => {
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
          className="min-h-[420px]"
        />
      </Suspense>
    </div>
  );
}
