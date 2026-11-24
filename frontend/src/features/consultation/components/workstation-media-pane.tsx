import React from "react";
import type { LivenessChannelMessage } from "../lib/liveness-channel";
import { VideoCallStage } from "./video-call-stage";

export interface WorkstationMediaPaneProps {
  atendimentoId: string;
  medicoNome: string;
  remoteParticipantName?: string;
  livekitToken?: string;
  wsUrl?: string;
  roomName?: string;
  onLivenessMessage?: (message: LivenessChannelMessage) => void;
  onRegisterLivenessSender?: (
    sender: ((message: LivenessChannelMessage) => Promise<void>) | null,
  ) => void;
}

/**
 * Contêiner de Mídia WebRTC da Estação de Trabalho Clínica isolado com `React.memo`.
 * Impede re-renders do palco de vídeo durante edição do SOAP ou polling em segundo plano.
 */
export const WorkstationMediaPane = React.memo(function WorkstationMediaPane({
  atendimentoId,
  medicoNome,
  remoteParticipantName = "Paciente em Atendimento",
  livekitToken,
  wsUrl,
  roomName,
  onLivenessMessage,
  onRegisterLivenessSender,
}: WorkstationMediaPaneProps) {
  return (
    <VideoCallStage
      roomName={roomName ?? `room_${atendimentoId}`}
      participantName={medicoNome}
      remoteParticipantName={remoteParticipantName}
      token={livekitToken}
      serverUrl={wsUrl}
      onLivenessMessage={onLivenessMessage}
      onRegisterLivenessSender={onRegisterLivenessSender}
      className="min-h-[300px]"
    />
  );
});
