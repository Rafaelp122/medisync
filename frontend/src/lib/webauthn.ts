/**
 * Utilitários WebAuthn / FIDO2 para detecção de suporte e codificação Base64url <-> ArrayBuffer.
 * Regras: RF-01, ADR-005 e US-14.
 */

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

export function base64UrlToUint8Array(base64url: string): Uint8Array<ArrayBuffer> {
  const normalized = base64url.replace(/-/g, "+").replace(/_/g, "/");
  const padding = "=".repeat((4 - (normalized.length % 4)) % 4);
  const binary = window.atob(normalized + padding);
  const buffer = new ArrayBuffer(binary.length);
  const bytes = new Uint8Array(buffer);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

export function bufferToBase64Url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return window.btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
