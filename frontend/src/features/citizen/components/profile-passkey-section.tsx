import { Fingerprint, Loader2, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { extractProblemDetail } from "@/api/errors";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useCitizenPasskeyRegister } from "@/features/citizen/api/use-citizen-profile-actions";
import { isWebAuthnSupported } from "@/lib/formatters";

export interface ProfilePasskeySectionProps {
  token?: string;
}

/**
 * Gerenciamento de biometria Passkey (WebAuthn FIDO2) na página de perfil do cidadão.
 */
export function ProfilePasskeySection({ token }: ProfilePasskeySectionProps) {
  const [registrado, setRegistrado] = useState(false);
  const [erroPasskey, setErroPasskey] = useState<string | null>(null);
  const registerMutation = useCitizenPasskeyRegister();
  const webAuthnDisponivel = isWebAuthnSupported();

  const handleAtivar = async () => {
    setErroPasskey(null);
    try {
      await registerMutation.mutateAsync({ token });
      setRegistrado(true);
    } catch (err) {
      setErroPasskey(
        extractProblemDetail(err, "Não foi possível ativar a biometria neste dispositivo."),
      );
    }
  };

  return (
    <Card className="border-border shadow-sm">
      <CardHeader className="pb-3">
        <CardTitle className="text-lg flex items-center gap-2">
          <Fingerprint className="h-5 w-5 text-primary" aria-hidden="true" />
          <span>Biometria e Passkeys (Acesso sem Senha)</span>
        </CardTitle>
        <CardDescription>
          Cadastre a biometria deste aparelho (TouchID, FaceID ou digital) para entrar com 1 toque
          nas próximas consultas (US-14).
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-3">
        {!webAuthnDisponivel && (
          <p className="text-xs text-muted-foreground">
            Seu navegador atual não possui suporte ativo à API WebAuthn / Passkeys.
          </p>
        )}

        {registrado && (
          <Alert>
            <ShieldCheck className="h-4 w-4 text-primary" aria-hidden="true" />
            <AlertTitle>Biometria ativada</AlertTitle>
            <AlertDescription>
              Chave Passkey vinculada com segurança a este dispositivo.
            </AlertDescription>
          </Alert>
        )}

        {erroPasskey && (
          <Alert variant="destructive">
            <AlertTitle>Falha ao configurar Passkey</AlertTitle>
            <AlertDescription>{erroPasskey}</AlertDescription>
          </Alert>
        )}

        {webAuthnDisponivel && !registrado && (
          <Button
            type="button"
            onClick={handleAtivar}
            disabled={registerMutation.isPending}
            className="min-h-[44px] gap-2"
          >
            {registerMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                <span>Cadastrando biometria…</span>
              </>
            ) : (
              <>
                <Fingerprint className="h-4 w-4" aria-hidden="true" />
                <span>Ativar Biometria neste Aparelho</span>
              </>
            )}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
