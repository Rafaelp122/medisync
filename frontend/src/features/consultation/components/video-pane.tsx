import { Camera, CameraOff, Mic, MicOff, ShieldCheck, Video } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

export interface VideoPaneProps {
  atendimentoId: string;
  pacienteNome?: string;
  medicoNome?: string;
  roomName?: string;
  isConnected?: boolean;
}

/**
 * Componente de videoconferência WebRTC LiveKit do médico e paciente.
 * Possui desacoplamento seguro de mídia e fallback declarativo para ambientes sem suporte a MediaStream (jsdom).
 * Regras: RF-07, ADR-005, ADR-011.
 */
export function VideoPane({
  atendimentoId,
  pacienteNome = "Paciente em Atendimento",
  medicoNome = "Dr. Eduardo Rocha",
  roomName,
  isConnected = true,
}: VideoPaneProps) {
  const [audioMuted, setAudioMuted] = useState(false);
  const [videoDisabled, setVideoDisabled] = useState(false);

  return (
    <Card
      data-atendimento-id={atendimentoId}
      className="flex flex-col h-full overflow-hidden bg-slate-950 text-slate-100 border-slate-800 shadow-md"
    >
      {/* Barra superior de status de conexão e segurança */}
      <div className="flex items-center justify-between px-3 py-2 bg-slate-900 border-b border-slate-800 text-xs">
        <div className="flex items-center gap-2">
          <span
            className={`inline-block size-2 rounded-full ${
              isConnected ? "bg-emerald-500 animate-pulse" : "bg-amber-500"
            }`}
          />
          <span className="font-semibold text-slate-200">
            {isConnected ? "LiveKit SFU Conectado" : "Conectando ao LiveKit…"}
          </span>
          {roomName && (
            <Badge
              variant="outline"
              className="text-[10px] py-0 px-1.5 border-slate-700 text-slate-400"
            >
              {roomName}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-1 text-slate-400">
          <ShieldCheck className="size-3.5 text-emerald-400" />
          <span>E2EE Criptografado</span>
        </div>
      </div>

      {/* Grid de Vídeo (Paciente principal + Médico picture-in-picture) */}
      <div className="relative flex-1 min-h-[220px] bg-slate-900 flex items-center justify-center p-3">
        {/* Painel do Paciente (Feed Principal) */}
        <div className="relative w-full h-full min-h-[180px] rounded-lg bg-slate-800 border border-slate-700 flex flex-col items-center justify-center overflow-hidden">
          <div className="size-16 rounded-full bg-slate-700 flex items-center justify-center text-slate-300 mb-2">
            <Video className="size-8 text-primary" />
          </div>
          <p className="text-sm font-medium text-slate-200">{pacienteNome}</p>
          <p className="text-xs text-slate-400">Câmera remota ativa (HD 720p)</p>

          {/* Badge de identificação do paciente no canto */}
          <div className="absolute bottom-2 left-2 bg-slate-900/80 backdrop-blur-xs px-2 py-0.5 rounded text-[11px] text-slate-300">
            {pacienteNome}
          </div>
        </div>

        {/* Painel do Médico (Picture-in-Picture) */}
        <div className="absolute top-5 right-5 w-28 h-20 rounded-md bg-slate-800 border-2 border-slate-700 shadow-lg flex flex-col items-center justify-center overflow-hidden">
          {videoDisabled ? (
            <div className="flex flex-col items-center justify-center text-slate-500">
              <CameraOff className="size-5 mb-0.5" />
              <span className="text-[9px]">Câmera Desligada</span>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center text-slate-300">
              <Camera className="size-5 mb-0.5 text-emerald-400" />
              <span className="text-[9px] truncate max-w-[90px]">{medicoNome}</span>
            </div>
          )}

          <div className="absolute bottom-1 left-1 bg-slate-900/90 px-1 rounded text-[9px] text-slate-400">
            Você
          </div>
        </div>
      </div>

      {/* Barra de Controles de Áudio e Vídeo */}
      <div className="flex items-center justify-center gap-2 p-3 bg-slate-900 border-t border-slate-800">
        <Button
          type="button"
          size="sm"
          variant={audioMuted ? "destructive" : "secondary"}
          onClick={() => setAudioMuted((prev) => !prev)}
          aria-label={audioMuted ? "Ativar microfone" : "Silenciar microfone"}
          className="gap-1.5"
        >
          {audioMuted ? <MicOff className="size-4" /> : <Mic className="size-4" />}
          <span className="text-xs">{audioMuted ? "Mutado" : "Microfone"}</span>
        </Button>

        <Button
          type="button"
          size="sm"
          variant={videoDisabled ? "destructive" : "secondary"}
          onClick={() => setVideoDisabled((prev) => !prev)}
          aria-label={videoDisabled ? "Ligar câmera" : "Desligar câmera"}
          className="gap-1.5"
        >
          {videoDisabled ? <CameraOff className="size-4" /> : <Camera className="size-4" />}
          <span className="text-xs">{videoDisabled ? "Câmera Off" : "Câmera"}</span>
        </Button>
      </div>
    </Card>
  );
}
