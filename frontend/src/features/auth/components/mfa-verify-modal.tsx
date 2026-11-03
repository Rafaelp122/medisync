import { AlertCircle, KeyRound, Loader2, ShieldCheck } from "lucide-react";
import { useState } from "react";
import type { TokenResponse } from "@/api/generated/types.gen";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useMfaVerify } from "../api/use-mfa-verify";
import { mfaVerifySchema } from "../schemas/auth-schemas";

export interface MfaVerifyModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  tempToken: string;
  perfilNome?: string;
  onSuccess: (data: TokenResponse) => void;
}

export function MfaVerifyModal({
  open,
  onOpenChange,
  tempToken,
  perfilNome = "Profissional",
  onSuccess,
}: MfaVerifyModalProps) {
  const [codigo, setCodigo] = useState("");
  const [erro, setErro] = useState<string | null>(null);

  const { mutate: verifyMfa, isPending } = useMfaVerify({
    onSuccess: (data) => {
      onOpenChange(false);
      onSuccess(data);
    },
    onError: (err) => {
      setErro(err.detail || err.message || "Código TOTP inválido ou expirado. Tente novamente.");
    },
  });

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErro(null);

    const validation = mfaVerifySchema.safeParse({ codigo: codigo.trim() });
    if (!validation.success) {
      setErro(validation.error.issues[0]?.message ?? "Código inválido");
      return;
    }

    verifyMfa({
      temp_token: tempToken,
      codigo: validation.data.codigo,
    });
  };

  const handleCodigoChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const limpo = e.target.value.replace(/\D/g, "").slice(0, 6);
    setCodigo(limpo);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md bg-card text-foreground border-border">
        <DialogHeader className="text-center space-y-2">
          <div className="mx-auto size-12 rounded-full bg-primary/10 flex items-center justify-center text-primary">
            <ShieldCheck className="size-6 text-primary" />
          </div>
          <DialogTitle className="text-lg font-bold">
            Autenticação em Duas Etapas (MFA / TOTP)
          </DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground">
            Acesso protegido para {perfilNome}. Digite o código de 6 dígitos gerado pelo seu
            aplicativo autenticador (Google Authenticator, Microsoft Authenticator ou similar).
          </DialogDescription>
        </DialogHeader>

        {erro && (
          <Alert variant="destructive" className="py-2.5 text-xs">
            <AlertCircle className="size-4" />
            <AlertDescription className="text-xs">{erro}</AlertDescription>
          </Alert>
        )}

        <form onSubmit={handleSubmit} className="space-y-4 pt-2">
          <div className="space-y-1.5 text-center">
            <Label htmlFor="mfa-code" className="text-xs font-semibold block">
              Código de Verificação (6 dígitos):
            </Label>
            <Input
              id="mfa-code"
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              autoComplete="one-time-code"
              placeholder="000000"
              value={codigo}
              onChange={handleCodigoChange}
              maxLength={6}
              disabled={isPending}
              autoFocus
              className="text-center text-xl font-mono tracking-widest h-12 w-48 mx-auto"
            />
          </div>

          <Button
            type="submit"
            disabled={isPending || codigo.length !== 6}
            className="w-full text-xs font-semibold h-10 gap-1.5 bg-primary text-primary-foreground hover:bg-primary/90"
          >
            {isPending ? (
              <>
                <Loader2 className="size-4 animate-spin" />
                <span>Validando token…</span>
              </>
            ) : (
              <>
                <KeyRound className="size-4" />
                <span>Confirmar e Acessar</span>
              </>
            )}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default MfaVerifyModal;
