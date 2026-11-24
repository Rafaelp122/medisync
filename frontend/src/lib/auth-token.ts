import { sessionTransport } from "./session-transport";

/**
 * Módulo de compatibilidade para acesso ao Access Token JWT corporativo em memória.
 * A closure volátil única reside encapsulada em `session-transport.ts`.
 * Regras: OWASP ASVS v4.0 (V3.5.2), RN-AUT-07 e Issue #144.
 */

export function getAccessToken(): string | null {
  return sessionTransport.getVolatileStaffToken();
}

export function setAccessToken(token: string | null): void {
  sessionTransport.setVolatileStaffToken(token);
}

export function clearAccessToken(): void {
  sessionTransport.setVolatileStaffToken(null);
}
