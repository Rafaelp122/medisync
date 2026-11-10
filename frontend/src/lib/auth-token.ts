/**
 * Módulo de armazenamento volátil em memória para Access Tokens JWT corporativos.
 * Retém o token estritamente em closure JavaScript, eliminando o vetor de exfiltração por XSS.
 * Regras: OWASP ASVS v4.0 (V3.5.2), RN-AUT-07 e Issue #144.
 */

let inMemoryAccessToken: string | null = null;

export function getAccessToken(): string | null {
  return inMemoryAccessToken;
}

export function setAccessToken(token: string | null): void {
  if (token && typeof token === "string" && token.trim().length > 0) {
    inMemoryAccessToken = token.trim();
  } else {
    inMemoryAccessToken = null;
  }
}

export function clearAccessToken(): void {
  inMemoryAccessToken = null;
}
