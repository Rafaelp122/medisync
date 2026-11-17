import { AlertCircle, CheckCircle2, Copy, KeyRound, Loader2, ShieldCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { extractProblemDetail } from "@/api/errors";
import type { MfaSetupResponse } from "@/api/generated/types.gen";
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
import { useMfaActivate, useMfaSetup } from "../api/use-mfa-setup";
import { mfaActivateSchema } from "../schemas/patient-hybrid-auth-schemas";

export interface MfaSetupModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onActivated?: () => void;
}

/**
 * Modal de configuração inicial e ativação do segundo fator TOTP (MFA) para equipe interna.
 * Regras canônicas: RN-AUT-04, RN-AUT-08 e Resoluções CFM nº 2.299/2021 e nº 2.314/2022.
 */
export function MfaSetupModal({ open, onOpenChange, onActivated }: MfaSetupModalProps) {
  const [setupData, setSetupData] = useState<MfaSetupResponse | null>(null);
  const [codigo, setCodigo] = useState("");
  const [erroValidacao, setErroValidacao] = useState<string | null>(null);
  const [copiado, setCopiado] = useState(false);
  const [ativadoMsg, setAtivadoMsg] = useState<string | null>(null);
  const requestedRef = useRef(false);

  const {
    mutate: requestSetup,
    isPending: isSettingUp,
    isError: isSetupError,
    error: setupError,
  } = useMfaSetup({
    onSuccess: (data) => setSetupData(data),
  });

  const activateMutation = useMfaActivate({
    onSuccess: (data) => {
      setAtivadoMsg(data.mensagem ?? "Segundo fator de autenticação ativado com sucesso.");
      onActivated?.();
    },
  });

  useEffect(() => {
    if (!open) {
      requestedRef.current = false;
      return;
    }
    if (!setupData && !requestedRef.current) {
      requestedRef.current = true;
      requestSetup();
    }
  }, [open, setupData, requestSetup]);

  const handleCopySecret = async () => {
    if (!setupData?.secret || typeof navigator === "undefined" || !navigator.clipboard) {
      return;
    }
    await navigator.clipboard.writeText(setupData.secret);
    setCopiado(true);
  };

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErroValidacao(null);
    const parsed = mfaActivateSchema.safeParse({ codigo: codigo.trim() });
    if (!parsed.success) {
      setErroValidacao(parsed.error.issues[0]?.message ?? "Código inválido.");
      return;
    }
    activateMutation.mutate(parsed.data);
  };

  const erroAtivo =
    erroValidacao ??
    (isSetupError
      ? extractProblemDetail(setupError)
      : activateMutation.isError
        ? extractProblemDetail(activateMutation.error)
        : null);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md bg-card text-foreground border-border">
        <DialogHeader className="text-center space-y-2">
          <div className="mx-auto size-12 rounded-full bg-primary/10 flex items-center justify-center text-primary">
            <ShieldCheck className="size-6" aria-hidden="true" />
          </div>
          <DialogTitle className="text-lg font-bold">
            Configurar Autenticação em Duas Etapas (MFA)
          </DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground">
            Adicione a chave secreta no Google Authenticator, Microsoft Authenticator ou app TOTP
            compatível e confirme com o código gerado.
          </DialogDescription>
        </DialogHeader>

        {erroAtivo && (
          <Alert variant="destructive" className="py-2.5 text-xs">
            <AlertCircle className="size-4" aria-hidden="true" />
            <AlertDescription className="text-xs">{erroAtivo}</AlertDescription>
          </Alert>
        )}

        {ativadoMsg ? (
          <div className="space-y-4 pt-2">
            <Alert className="bg-acr-green/10 border-acr-green/30 text-foreground">
              <CheckCircle2 className="size-4 text-acr-green" aria-hidden="true" />
              <AlertDescription className="text-xs font-medium">{ativadoMsg}</AlertDescription>
            </Alert>
            <Button
              type="button"
              onClick={() => onOpenChange(false)}
              className="w-full min-h-[44px]"
            >
              Concluir
            </Button>
          </div>
        ) : isSettingUp ? (
          <div className="flex items-center justify-center gap-2 py-6 text-xs text-muted-foreground">
            <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            <span>Gerando chave secreta TOTP…</span>
          </div>
        ) : (
          setupData && (
            <form onSubmit={handleSubmit} className="space-y-4 pt-2">
              <div className="rounded-lg border bg-muted/40 p-3 space-y-2 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-foreground">Chave Secreta (Base32):</span>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleCopySecret}
                    className="h-8 px-2.5 text-xs gap-1"
                  >
                    <Copy className="size-3.5" aria-hidden="true" />
                    <span>{copiado ? "Copiada" : "Copiar"}</span>
                  </Button>
                </div>
                <code className="block w-full break-all rounded bg-background px-2.5 py-2 font-mono text-xs border">
                  {setupData.secret}
                </code>
                <p className="text-[11px] text-muted-foreground break-all">
                  URI otpauth: <span className="font-mono">{setupData.uri}</span>
                </p>
              </div>

              <div className="space-y-1.5 text-center">
                <Label htmlFor="mfa-setup-codigo" className="text-xs font-semibold block">
                  Código de Confirmação (6 dígitos)
                </Label>
                <Input
                  id="mfa-setup-codigo"
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  autoComplete="one-time-code"
                  placeholder="000000"
                  maxLength={6}
                  value={codigo}
                  onChange={(e) => {
                    setErroValidacao(null);
                    setCodigo(e.target.value.replace(/\D/g, "").slice(0, 6));
                  }}
                  disabled={activateMutation.isPending}
                  className="min-h-[44px] text-center text-xl font-mono tracking-widest w-48 mx-auto"
                  required
                />
              </div>

              <Button
                type="submit"
                disabled={activateMutation.isPending || codigo.length !== 6}
                className="w-full min-h-[44px] text-xs font-semibold gap-1.5"
              >
                <KeyRound className="size-4" aria-hidden="true" />
                <span>{activateMutation.isPending ? "Ativando MFA…" : "Validar e Ativar MFA"}</span>
              </Button>
            </form>
          )
        )}
      </DialogContent>
    </Dialog>
  );
}

export default MfaSetupModal;
