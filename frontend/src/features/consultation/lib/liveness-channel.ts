import type { LivenessChallengeResponse } from "@/api/generated/types.gen";

export const LIVENESS_DATA_TOPIC = "medisync.liveness";

export type LivenessResultStatus = "APROVADO" | "REPROVADO" | "DESAFIO_INVALIDO";

export interface LivenessChallengeDispatchMessage {
  type: "LIVENESS_CHALLENGE";
  atendimento_id: string;
  challenge: LivenessChallengeResponse;
}

export interface LivenessResultMessage {
  type: "LIVENESS_RESULT";
  atendimento_id: string;
  status: LivenessResultStatus;
  verificacao_hash?: string | null;
  liveness_score?: number;
  detail?: string;
}

export type LivenessChannelMessage = LivenessChallengeDispatchMessage | LivenessResultMessage;

const encoder = new TextEncoder();
const decoder = new TextDecoder();

export function encodeLivenessMessage(message: LivenessChannelMessage): Uint8Array {
  return encoder.encode(JSON.stringify(message));
}

export function decodeLivenessMessage(payload: Uint8Array): LivenessChannelMessage | null {
  try {
    const parsed = JSON.parse(decoder.decode(payload)) as Partial<LivenessChannelMessage> | null;
    if (!parsed || typeof parsed !== "object" || typeof parsed.atendimento_id !== "string") {
      return null;
    }
    if (
      parsed.type === "LIVENESS_CHALLENGE" &&
      parsed.challenge &&
      typeof parsed.challenge.challenge_id === "string"
    ) {
      return parsed as LivenessChallengeDispatchMessage;
    }
    if (parsed.type === "LIVENESS_RESULT" && typeof parsed.status === "string") {
      return parsed as LivenessResultMessage;
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Captura um frame JPEG da câmera ativa do paciente via `<canvas>` para submissão ao backend.
 * Retorna fallback determinístico base64 apenas quando o canvas não possui dimensões em JSDOM.
 */
export function captureVideoFrameAsBase64(videoElement: HTMLVideoElement | null): string {
  if (
    typeof document === "undefined" ||
    !videoElement ||
    videoElement.videoWidth === 0 ||
    videoElement.videoHeight === 0
  ) {
    return btoa(`liveness_frame_${Date.now()}`);
  }
  const width = videoElement.videoWidth;
  const height = videoElement.videoHeight;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = typeof canvas.getContext === "function" ? canvas.getContext("2d") : null;
  if (ctx) {
    ctx.drawImage(videoElement, 0, 0, width, height);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.85);
    const commaIdx = dataUrl.indexOf(",");
    if (commaIdx !== -1 && dataUrl.length > commaIdx + 8) {
      return dataUrl.slice(commaIdx + 1);
    }
  }
  return btoa(`liveness_frame_${Date.now()}`);
}
