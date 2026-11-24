import { Camera, CameraOff, Mic, MicOff, PhoneOff, ShieldCheck, Video } from "lucide-react";
import { lazy, type ReactNode, Suspense } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { LivenessChannelMessage } from "../lib/liveness-channel";
import { OfflineFallbackAdapter } from "./offline-fallback-adapter";

const LazyLiveKitMediaAdapter = lazy(() => import("./livekit-media-adapter"));

export type VideoConnectionStatus = "connected" | "connecting" | "reconnecting" | "disconnected";

export interface VideoCallStageProps {
  roomName: string;
  participantName: string;
  token?: string;
  serverUrl?: string;
  remoteParticipantName?: string;
  connectionMode?: "auto" | "offline_fallback";
  onDisconnected?: () => void;
  onLivenessMessage?: (message: LivenessChannelMessage) => void;
  onRegisterLivenessSender?: (
    sender: ((message: LivenessChannelMessage) => Promise<void>) | null,
  ) => void;
  className?: string;
}

export interface VideoStageLayoutProps {
  connectionStatus: VideoConnectionStatus;
  roomName?: string;
  participantName: string;
  remoteParticipantName: string;
  micState: "enabled" | "muted";
  cameraState: "enabled" | "off";
  onToggleMic: () => void;
  onToggleCamera: () => void;
  onDisconnected?: () => void;
  audioRendererSlot?: ReactNode;
  remoteMediaSlot?: ReactNode;
  localMediaSlot?: ReactNode;
}

const CONNECTION_STATUS_UI: Record<
  VideoConnectionStatus,
  { label: string; dotColor: string; textColor: string }
> = {
  connected: {
    label: "LiveKit SFU Conectado",
    dotColor: "bg-emerald-500 animate-pulse motion-reduce:animate-none",
    textColor: "text-emerald-400",
  },
  connecting: {
    label: "Conectando ao LiveKit…",
    dotColor: "bg-amber-500 animate-ping motion-reduce:animate-none",
    textColor: "text-amber-400",
  },
  reconnecting: {
    label: "Reconectando chamada WebRTC…",
    dotColor: "bg-amber-500 animate-pulse motion-reduce:animate-none",
    textColor: "text-amber-400",
  },
  disconnected: {
    label: "Desconectado do SFU",
    dotColor: "bg-red-500",
    textColor: "text-red-400",
  },
};

/**
 * Shell visual único de videoconferência WebRTC compartilhado pelos adaptadores
 * `LiveKitMediaAdapter` e `OfflineFallbackAdapter`, eliminando triplicação de UI.
 */
export function VideoStageLayout({
  connectionStatus,
  roomName,
  participantName,
  remoteParticipantName,
  micState,
  cameraState,
  onToggleMic,
  onToggleCamera,
  onDisconnected,
  audioRendererSlot,
  remoteMediaSlot,
  localMediaSlot,
}: VideoStageLayoutProps) {
  const statusUi = CONNECTION_STATUS_UI[connectionStatus];
  const micMuted = micState === "muted";
  const cameraOff = cameraState === "off";

  return (
    <div className="flex flex-col h-full w-full">
      {audioRendererSlot}

      <div className="flex items-center justify-between px-3 py-2 bg-slate-900 border-b border-slate-800 text-xs shrink-0">
        <div className="flex items-center gap-2" role="status" aria-live="polite">
          <span className={cn("inline-block size-2 rounded-full", statusUi.dotColor)} />
          <span className={cn("font-semibold text-xs", statusUi.textColor)}>{statusUi.label}</span>
          {roomName && (
            <Badge
              variant="outline"
              className="text-[10px] py-0 px-1.5 border-slate-700 text-slate-300"
            >
              {roomName}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-1 text-slate-300 text-xs">
          <ShieldCheck className="size-3.5 text-emerald-400" />
          <span>E2EE Criptografado</span>
        </div>
      </div>

      <div className="relative flex-1 min-h-[220px] bg-slate-900 flex items-center justify-center p-3">
        <div className="relative w-full h-full min-h-[180px] rounded-lg bg-slate-800 border border-slate-700 flex flex-col items-center justify-center overflow-hidden">
          {remoteMediaSlot ?? (
            <div className="flex flex-col items-center justify-center text-slate-300 p-4 text-center">
              <div className="size-16 rounded-full bg-slate-700 flex items-center justify-center text-slate-300 mb-2">
                <Video className="size-8 text-primary" />
              </div>
              <p className="text-sm font-medium text-slate-200">{remoteParticipantName}</p>
              <p className="text-xs text-slate-400">
                {connectionStatus === "connected"
                  ? "Câmera remota conectada (HD 720p)"
                  : "Aguardando transmissão de vídeo…"}
              </p>
            </div>
          )}

          <div className="absolute bottom-2 left-2 bg-slate-900/80 backdrop-blur-xs px-2 py-0.5 rounded text-[11px] text-slate-200">
            {remoteParticipantName}
          </div>
        </div>

        <div className="absolute top-5 right-5 w-28 h-20 rounded-md bg-slate-800 border-2 border-slate-700 shadow-lg flex flex-col items-center justify-center overflow-hidden">
          {localMediaSlot ??
            (cameraOff ? (
              <div className="flex flex-col items-center justify-center text-slate-400">
                <CameraOff className="size-5 mb-0.5 text-slate-500" />
                <span className="text-[9px]">Câmera Desligada</span>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center text-slate-300">
                <Camera className="size-5 mb-0.5 text-emerald-400" />
                <span className="text-[9px] truncate max-w-[90px]">{participantName}</span>
              </div>
            ))}
          <div className="absolute bottom-1 left-1 bg-slate-900/90 px-1 rounded text-[9px] text-slate-300">
            Você
          </div>
        </div>
      </div>

      <div className="flex items-center justify-center gap-2 p-3 bg-slate-900 border-t border-slate-800 shrink-0">
        <Button
          type="button"
          size="sm"
          variant={micMuted ? "destructive" : "secondary"}
          onClick={onToggleMic}
          aria-label={micMuted ? "Ativar microfone" : "Silenciar microfone"}
          className="gap-1.5"
        >
          {micMuted ? <MicOff className="size-4" /> : <Mic className="size-4" />}
          <span className="text-xs">{micMuted ? "Mutado" : "Microfone"}</span>
        </Button>

        <Button
          type="button"
          size="sm"
          variant={cameraOff ? "destructive" : "secondary"}
          onClick={onToggleCamera}
          aria-label={cameraOff ? "Ligar câmera" : "Desligar câmera"}
          className="gap-1.5"
        >
          {cameraOff ? <CameraOff className="size-4" /> : <Camera className="size-4" />}
          <span className="text-xs">{cameraOff ? "Câmera Off" : "Câmera"}</span>
        </Button>

        {onDisconnected && (
          <Button
            type="button"
            size="sm"
            variant="destructive"
            onClick={onDisconnected}
            aria-label="Encerrar chamada"
            className="gap-1.5 ml-2"
          >
            <PhoneOff className="size-4" />
            <span className="text-xs">Encerrar</span>
          </Button>
        )}
      </div>
    </div>
  );
}

/**
 * Palco único de Teleconsulta WebRTC com seleção de adaptador LiveKit (`React.lazy`) ou fallback JSDOM.
 * Sem boolean props (`isConnected`, `isOfflineFallback`) nem UI triplicada.
 * @see docs/user-stories/US-09-teleconsulta-pep-soap.md
 */
export function VideoCallStage({
  roomName,
  participantName,
  token,
  serverUrl = "ws://localhost:7880",
  remoteParticipantName = "Participante Remoto",
  connectionMode = "auto",
  onDisconnected,
  onLivenessMessage,
  onRegisterLivenessSender,
  className,
}: VideoCallStageProps) {
  const isWebRTCSupported =
    connectionMode === "auto" &&
    Boolean(token) &&
    typeof window !== "undefined" &&
    typeof window.RTCPeerConnection !== "undefined" &&
    typeof navigator !== "undefined" &&
    Boolean(navigator.mediaDevices);

  return (
    <Card
      className={cn(
        "flex flex-col h-full overflow-hidden bg-slate-950 text-slate-100 border-slate-800 shadow-md",
        className,
      )}
    >
      {isWebRTCSupported && token ? (
        <Suspense
          fallback={
            <div className="h-64 flex items-center justify-center bg-slate-900 text-slate-300 text-xs">
              Conectando ao WebRTC LiveKit…
            </div>
          }
        >
          <LazyLiveKitMediaAdapter
            wsUrl={serverUrl}
            token={token}
            roomName={roomName}
            participantName={participantName}
            remoteParticipantName={remoteParticipantName}
            onDisconnected={onDisconnected}
            onLivenessMessage={onLivenessMessage}
            onRegisterLivenessSender={onRegisterLivenessSender}
          />
        </Suspense>
      ) : (
        <OfflineFallbackAdapter
          roomName={roomName}
          participantName={participantName}
          remoteParticipantName={remoteParticipantName}
          connectionStatus={token ? "connected" : "connecting"}
          onDisconnected={onDisconnected}
          onLivenessMessage={onLivenessMessage}
          onRegisterLivenessSender={onRegisterLivenessSender}
        />
      )}
    </Card>
  );
}
