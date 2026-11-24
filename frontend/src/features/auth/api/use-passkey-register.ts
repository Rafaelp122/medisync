import { type UseMutationOptions, useMutation } from "@tanstack/react-query";
import type { ProblemDetailsError } from "@/api/errors";
import type { WebAuthnRegisterVerifyResponse } from "@/api/generated/types.gen";
import {
  type RegisterPasskeyCredentialParams,
  registerPatientPasskeyCredential,
} from "@/lib/webauthn";

export type RegisterPasskeyParams = RegisterPasskeyCredentialParams;

/**
 * Hook headless de mutação para cadastro de Passkey FIDO2/WebAuthn do cidadão (US-14).
 * Alocado em features/auth/api conforme fronteira modular da Issue #168.
 * @see docs/user-stories/US-14-biometria-passkeys-webauthn.md
 */
export function usePasskeyRegister(
  options?: UseMutationOptions<
    WebAuthnRegisterVerifyResponse,
    ProblemDetailsError,
    RegisterPasskeyParams
  >,
) {
  return useMutation<WebAuthnRegisterVerifyResponse, ProblemDetailsError, RegisterPasskeyParams>({
    mutationFn: registerPatientPasskeyCredential,
    ...options,
  });
}
