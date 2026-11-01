/**
 * Formata o tempo de espera estimado em segundos para uma representação amigável e empática em português.
 * Regras: US-07, US-08 e Diretrizes de UI em Telemedicina.
 */
export function formatarTempoEstimado(segundos: number | null | undefined): string {
  if (segundos === null || segundos === undefined) {
    return "Calculando estimativa...";
  }

  if (segundos < 60) {
    return "Menos de 1 minuto";
  }

  const minutosTotais = Math.round(segundos / 60);

  if (minutosTotais < 60) {
    return `Aproximadamente ${minutosTotais} ${minutosTotais === 1 ? "minuto" : "minutos"}`;
  }

  const horas = Math.floor(minutosTotais / 60);
  const minutosRestantes = minutosTotais % 60;

  if (minutosRestantes === 0) {
    return `Aproximadamente ${horas} ${horas === 1 ? "hora" : "horas"}`;
  }

  return `Aproximadamente ${horas} ${horas === 1 ? "hora" : "horas"} e ${minutosRestantes} ${minutosRestantes === 1 ? "minuto" : "minutos"}`;
}

/**
 * Formata a posição ordinal do paciente na fila virtual.
 * Exemplo: 1 -> "1º na fila", null -> "—"
 */
export function formatarPosicaoOrdinal(posicao: number | null | undefined): string {
  if (!posicao || posicao < 1) {
    return "—";
  }
  return `${posicao}º na fila`;
}

/**
 * Verifica de forma silenciosa e resiliente se o navegador/dispositivo possui suporte à Web Authentication API.
 * Regras: US-14 (Passkeys / WebAuthn - Detecção silenciosa sem lançar exceções).
 */
export function isWebAuthnSupported(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  return Boolean(window.PublicKeyCredential && typeof window.PublicKeyCredential === "function");
}
