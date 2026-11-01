import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { isWebAuthnSupported } from "@/lib/formatters";
import { cn } from "@/lib/utils";

export interface PasskeyInvitationCardProps {
  className?: string;
  onAtivarBiometria?: () => void;
}

const DISMISSED_KEY = "medisync_passkey_invite_dismissed";

export function PasskeyInvitationCard({
  className,
  onAtivarBiometria,
}: PasskeyInvitationCardProps) {
  const [isVisible, setIsVisible] = useState(false);
  const [ativado, setAtivado] = useState(false);

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

  const handleAtivar = () => {
    setAtivado(true);
    onAtivarBiometria?.();
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

      <CardContent className="pt-1">
        {ativado ? (
          <div className="text-xs font-semibold text-emerald-600 dark:text-emerald-400 flex items-center gap-1.5 py-1">
            <span aria-hidden="true">✓</span>
            Biometria habilitada com sucesso neste dispositivo!
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              size="sm"
              variant="default"
              className="bg-blue-600 hover:bg-blue-700 text-white text-xs min-h-[38px] px-3.5"
              onClick={handleAtivar}
            >
              Ativar Biometria deste Aparelho
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="text-xs text-muted-foreground hover:text-foreground min-h-[38px]"
              onClick={handleDismiss}
            >
              Agora não
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
