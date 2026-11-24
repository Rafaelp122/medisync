import {
  LiveKitRoom,
  RoomAudioRenderer,
  useConnectionState,
  useDataChannel,
  useLocalParticipant,
  useTracks,
  VideoTrack,
} from "@livekit/components-react";
import { ConnectionState, Track } from "livekit-client";
import { useEffect, useRef } from "react";
import {
  decodeLivenessMessage,
  encodeLivenessMessage,
  LIVENESS_DATA_TOPIC,
  type LivenessChannelMessage,
} from "../lib/liveness-channel";
import { type VideoConnectionStatus, VideoStageLayout } from "./video-call-stage";

export interface LiveKitMediaAdapterProps {
  wsUrl: string;
  token: string;
  roomName: string;
  participantName: string;
  remoteParticipantName: string;
  onDisconnected?: () => void;
  onLivenessMessage?: (message: LivenessChannelMessage) => void;
  onRegisterLivenessSender?: (
    sender: ((message: LivenessChannelMessage) => Promise<void>) | null,
  ) => void;
}

function mapConnectionState(state: ConnectionState): VideoConnectionStatus {
  switch (state) {
    case ConnectionState.Connected:
      return "connected";
    case ConnectionState.Connecting:
      return "connecting";
    case ConnectionState.Reconnecting:
      return "reconnecting";
    default:
      return "disconnected";
  }
}

function LiveKitRoomStage({
  roomName,
  participantName,
  remoteParticipantName,
  onDisconnected,
  onLivenessMessage,
  onRegisterLivenessSender,
}: Omit<LiveKitMediaAdapterProps, "wsUrl" | "token">) {
  const connectionState = useConnectionState();
  const { isMicrophoneEnabled, isCameraEnabled, localParticipant } = useLocalParticipant();
  const tracks = useTracks([Track.Source.Camera]);
  const onLivenessMessageRef = useRef(onLivenessMessage);
  onLivenessMessageRef.current = onLivenessMessage;

  const { send } = useDataChannel(LIVENESS_DATA_TOPIC, (msg) => {
    const decoded = decodeLivenessMessage(msg.payload);
    if (decoded) {
      onLivenessMessageRef.current?.(decoded);
    }
  });

  useEffect(() => {
    if (!onRegisterLivenessSender) return;
    const sender = async (message: LivenessChannelMessage) => {
      await send(encodeLivenessMessage(message), { reliable: true });
    };
    onRegisterLivenessSender(sender);
    return () => {
      onRegisterLivenessSender(null);
    };
  }, [onRegisterLivenessSender, send]);

  const remoteTrack = tracks.find((t) => t.participant.identity !== localParticipant.identity);
  const localTrack = tracks.find((t) => t.participant.identity === localParticipant.identity);

  return (
    <VideoStageLayout
      connectionStatus={mapConnectionState(connectionState)}
      roomName={roomName}
      participantName={participantName}
      remoteParticipantName={remoteParticipantName}
      micState={isMicrophoneEnabled ? "enabled" : "muted"}
      cameraState={isCameraEnabled ? "enabled" : "off"}
      onToggleMic={() => void localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled)}
      onToggleCamera={() => void localParticipant.setCameraEnabled(!isCameraEnabled)}
      onDisconnected={onDisconnected}
      audioRendererSlot={<RoomAudioRenderer />}
      remoteMediaSlot={
        remoteTrack?.publication && !remoteTrack.publication.isMuted ? (
          <VideoTrack trackRef={remoteTrack} className="w-full h-full object-cover" />
        ) : undefined
      }
      localMediaSlot={
        localTrack?.publication && isCameraEnabled ? (
          <VideoTrack trackRef={localTrack} className="w-full h-full object-cover" />
        ) : undefined
      }
    />
  );
}

/**
 * Adaptador WebRTC real carregado via `React.lazy()` dentro de `VideoCallStage`.
 */
export function LiveKitMediaAdapter(props: LiveKitMediaAdapterProps) {
  return (
    <LiveKitRoom
      serverUrl={props.wsUrl}
      token={props.token}
      connect={Boolean(props.token)}
      video={true}
      audio={true}
      onDisconnected={props.onDisconnected}
      className="flex flex-col h-full w-full"
    >
      <LiveKitRoomStage
        roomName={props.roomName}
        participantName={props.participantName}
        remoteParticipantName={props.remoteParticipantName}
        onDisconnected={props.onDisconnected}
        onLivenessMessage={props.onLivenessMessage}
        onRegisterLivenessSender={props.onRegisterLivenessSender}
      />
    </LiveKitRoom>
  );
}

export default LiveKitMediaAdapter;
