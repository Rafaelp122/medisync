import { useEffect, useRef, useState } from "react";
import { LIVENESS_DATA_TOPIC, type LivenessChannelMessage } from "../lib/liveness-channel";
import { type VideoConnectionStatus, VideoStageLayout } from "./video-call-stage";

export interface OfflineFallbackAdapterProps {
  roomName: string;
  participantName: string;
  remoteParticipantName: string;
  connectionStatus?: Extract<VideoConnectionStatus, "connected" | "connecting">;
  onDisconnected?: () => void;
  onLivenessMessage?: (message: LivenessChannelMessage) => void;
  onRegisterLivenessSender?: (
    sender: ((message: LivenessChannelMessage) => Promise<void>) | null,
  ) => void;
}

/**
 * Adaptador de contingência para ambientes sem WebRTC/MediaDevices (ex.: JSDOM em testes)
 * ou enquanto o token LiveKit ainda está sendo negociado.
 */
export function OfflineFallbackAdapter({
  roomName,
  participantName,
  remoteParticipantName,
  connectionStatus = "connecting",
  onDisconnected,
  onLivenessMessage,
  onRegisterLivenessSender,
}: OfflineFallbackAdapterProps) {
  const [micMuted, setMicMuted] = useState(false);
  const [camOff, setCamOff] = useState(false);
  const onLivenessMessageRef = useRef(onLivenessMessage);
  onLivenessMessageRef.current = onLivenessMessage;

  useEffect(() => {
    if (!onRegisterLivenessSender && !onLivenessMessageRef.current) return;
    const channelName = roomName ? `${LIVENESS_DATA_TOPIC}:${roomName}` : LIVENESS_DATA_TOPIC;
    const bc = typeof BroadcastChannel !== "undefined" ? new BroadcastChannel(channelName) : null;
    if (bc) {
      bc.onmessage = (event: MessageEvent<LivenessChannelMessage>) => {
        if (event.data && typeof event.data === "object") {
          onLivenessMessageRef.current?.(event.data);
        }
      };
    }
    onRegisterLivenessSender?.(async (message) => {
      bc?.postMessage(message);
    });
    return () => {
      onRegisterLivenessSender?.(null);
      bc?.close();
    };
  }, [onRegisterLivenessSender, roomName]);

  return (
    <VideoStageLayout
      connectionStatus={connectionStatus}
      roomName={roomName}
      participantName={participantName}
      remoteParticipantName={remoteParticipantName}
      micState={micMuted ? "muted" : "enabled"}
      cameraState={camOff ? "off" : "enabled"}
      onToggleMic={() => setMicMuted((prev) => !prev)}
      onToggleCamera={() => setCamOff((prev) => !prev)}
      onDisconnected={onDisconnected}
    />
  );
}
