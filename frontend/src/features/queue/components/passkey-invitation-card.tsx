import { Loader2, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { extractProblemDetail } from "@/api/errors";
import type { WebAuthnRegisterVerifyResponse } from "@/api/generated/types.gen";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { settings } from "@/config/settings";
import { cn } from "@/lib/utils";
import { isWebAuthnSupported, type RegisterPasskeyCredentialParams } from "@/lib/webauthn";

export interface PasskeyInvitationCardProps {
  className?: string;
  onAtivarBiometria?: () => void;
  onRegisterPasskey?: (
    params: RegisterPasskeyCredentialParams,
  ) => Promise<WebAuthnRegisterVerifyResponse>;
  isRegistering?: boolean;
  token?: string;
}

const DISMISSED_KEY = settings.storage.passkeyDismissed;

/**
 * Card Informativo Visual e Headless de Convite Não-Bloqueante de Biometria Passkeys (US-14).
 * Toda lógica de rede/mutação FIDO2 reside no hook externo (`usePasskeyRegister`) injetado via prop.
 *
 * @see docs/user-stories/US-14-biometria-passkeys-webauthn.md
 * @see docs/how-to/patient-virtual-waiting-room.md
 */
export function PasskeyInvitationCard({
  className,
  onAtivarBiometria,
  onRegisterPasskey,
  isRegistering = false,
  token,
}: PasskeyInvitationCardProps) {
  const [isVisible, setIsVisible] = useState(false);
  const [registrado, setRegistrado] = useState(false);
  const [isPendingLocal, setIsPendingLocal] = useState(false);
  const [erroRegistro, setErroRegistro] = useState<string | null>(null);
  const isPending = isRegistering || isPendingLocal;

  useEffect(() => {
    if (!isWebAuthnSupported()) return;
    if (typeof window !== "undefined" && window.sessionStorage) {
      const dismissed = window.sessionStorage.getItem(DISMISSED_KEY);
      if (dismissed === "true") return;
    }
    setIsVisible(true);
  }, []);

  if (!isVisible) return null;

  const handleDismiss = () => {
    setIsVisible(false);
    if (typeof window !== "undefined" && window.sessionStorage) {
      window.sessionStorage.setItem(DISMISSED_KEY, "true");
    }
  };

  const handleAtivar = async () => {
    if (onAtivarBiometria) {
      onAtivarBiometria();
      return;
    }

    const canCreateCredential =
      Boolean(token) &&
      Boolean(onRegisterPasskey) &&
      typeof navigator !== "undefined" &&
      typeof navigator.credentials?.create === "function";

    if (!canCreateCredential || !token || !onRegisterPasskey) {
      setErroRegistro(
        "Sessão ou suporte biométrico indisponível neste navegador para ativar Passkey.",
      );
      return;
    }

    setErroRegistro(null);
    setIsPendingLocal(true);
    try {
      await onRegisterPasskey({ token });
      setRegistrado(true);
    } catch (err) {
      setErroRegistro(
        extractProblemDetail(err, "Não foi possível cadastrar a biometria neste aparelho."),
      );
    } finally {
      setIsPendingLocal(false);
    }
  };

  return (
    <Card
      data-testid="passkey-invitation-card"
      className={cn(
        "w-full bg-gradient-to-r from-blue-50/70 to-indigo-50/70 dark:from-blue-950/20 dark:to-indigo-950/20 border-blue-200/60 dark:border-blue-900/40 text-left shadow-sm",
        className,
      )}
    >
      <CardHeader className="pb-2 space-y-1">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-bold text-blue-950 dark:text-blue-100 flex items-center gap-2">
            <span aria-hidden="true">🔒</span>
            Acesso Rápido com Biometria
          </CardTitle>
          <button
            type="button"
            onClick={handleDismiss}
            aria-label="Dispensar convite de biometria"
            className="text-xs text-muted-foreground hover:text-foreground p-1 rounded-md"
          >
            ✕
          </button>
        </div>
        <CardDescription className="text-xs text-blue-900/80 dark:text-blue-300/80 text-pretty">
          Aproveite o tempo de espera para ativar o FaceID, TouchID ou impressão digital do seu
          aparelho. Acesso futuro em 1 toque, sem senhas e imune a clonagem de chip (US-14).
        </CardDescription>
      </CardHeader>

      <CardContent className="pt-1 space-y-2">
        {registrado ? (
          <div
            className="text-xs text-emerald-900 dark:text-emerald-200 py-1 space-y-1"
            role="status"
          >
            <p className="font-semibold flex items-center gap-1.5">
              <ShieldCheck className="size-4 text-emerald-600" aria-hidden="true" />
              Biometria ativada com sucesso neste aparelho (US-14).
            </p>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              size="sm"
              variant="default"
              disabled={isPending}
              className="bg-blue-600 hover:bg-blue-700 text-white text-xs min-h-[38px] px-3.5"
              onClick={handleAtivar}
            >
              {isPending ? (
                <>
                  <Loader2 className="mr-1.5 size-3.5 animate-spin" />
                  Cadastrando biometria…
                </>
              ) : (
                "Ativar Biometria deste Aparelho"
              )}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={isPending}
              className="text-xs text-muted-foreground hover:text-foreground min-h-[38px]"
              onClick={handleDismiss}
            >
              Agora não
            </Button>
          </div>
        )}
        {erroRegistro && (
          <p role="alert" className="text-xs text-destructive">
            {erroRegistro}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
