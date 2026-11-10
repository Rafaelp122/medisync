import React, { lazy, Suspense } from "react";
import { VideoPane } from "./video-pane";

const LazyLiveKitVideoCall = lazy(() => import("./livekit-video-call"));

export interface WorkstationMediaPaneProps {
  atendimentoId: string;
  medicoNome: string;
  remoteParticipantName?: string;
  livekitToken?: string;
  wsUrl?: string;
  roomName?: string;
}

/**
 * Contêiner de Mídia WebRTC da Estação de Trabalho Clínica isolado com React.memo.
 * Impede re-renders acidentais no canvas de vídeo ou LiveKit durante digitação no SOAP,
 * inclusão de prescrições ou polling de telemetria médica em segundo plano.
 * Regras: ADR-011, CFM nº 2.314/2022.
 */
export const WorkstationMediaPane = React.memo(function WorkstationMediaPane({
  atendimentoId,
  medicoNome,
  remoteParticipantName = "Juliana Silva (Paciente)",
  livekitToken,
  wsUrl,
  roomName,
}: WorkstationMediaPaneProps) {
  if (livekitToken) {
    return (
      <Suspense
        fallback={
          <div className="h-64 flex items-center justify-center bg-slate-900 rounded-lg text-slate-400 text-xs">
            Conectando ao WebRTC LiveKit…
          </div>
        }
      >
        <LazyLiveKitVideoCall
          wsUrl={wsUrl}
          token={livekitToken}
          roomName={roomName}
          participantName={medicoNome}
          remoteParticipantName={remoteParticipantName}
          className="min-h-[300px]"
        />
      </Suspense>
    );
  }

  return (
    <VideoPane
      atendimentoId={atendimentoId}
      pacienteNome={remoteParticipantName}
      medicoNome={medicoNome}
      roomName={roomName}
      isConnected={false}
    />
  );
});
