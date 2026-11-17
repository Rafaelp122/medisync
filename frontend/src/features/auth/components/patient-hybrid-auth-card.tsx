import {
  AlertCircle,
  ArrowLeft,
  Fingerprint,
  KeyRound,
  Loader2,
  ShieldCheck,
  Smartphone,
} from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { StoredPatientSession } from "@/lib/session-storage";
import { cn } from "@/lib/utils";
import { type HybridAuthStep, usePatientHybridAuthFlow } from "../api/use-patient-identify";
import { PatientIdentifyForm, PatientNotFoundPanel } from "./patient-identify-form";
import { PatientOtpVerifyStep } from "./patient-otp-verify-step";

export interface PatientHybridAuthCardProps {
  onAuthenticated: (session: StoredPatientSession) => void;
  onGoToRegister?: () => void;
  onGovbrClick?: () => void;
  className?: string;
}

const STEP_DESCRIPTIONS: Record<HybridAuthStep, string> = {
  identify: "Acesse suas consultas, receitas e fila de atendimento SUS.",
  not_found: "Não localizamos um cadastro ativo com este identificador.",
  methods: "Escolha como prefere confirmar seu acesso.",
  otp_verify: "Digite o código de 6 dígitos enviado por SMS.",
  password: "Acesse usando sua senha cadastrada.",
};

/**
 * Card principal do IAM Híbrido do Cidadão (/entrar).
 * Passo 1: Identificação única -> Passo 2A: OTP SMS / Passkey / Gov.br -> Passo 2B: Senha alternativa.
 */
export function PatientHybridAuthCard({
  onAuthenticated,
  onGoToRegister,
  onGovbrClick,
  className,
}: PatientHybridAuthCardProps) {
  const flow = usePatientHybridAuthFlow(onAuthenticated);

  return (
    <Card className={cn("w-full max-w-md mx-auto shadow-lg border", className)}>
      <CardHeader className="space-y-1.5 text-center pb-4">
        <CardTitle className="text-xl font-bold tracking-tight text-foreground">
          Entrar no MediSync
        </CardTitle>
        <CardDescription className="text-xs text-muted-foreground">
          {STEP_DESCRIPTIONS[flow.step]}
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        {flow.activeError && (
          <Alert variant="destructive" className="py-2.5 text-xs">
            <AlertCircle className="size-4" aria-hidden="true" />
            <AlertDescription className="text-xs">{flow.activeError}</AlertDescription>
          </Alert>
        )}

        {flow.step === "identify" && (
          <PatientIdentifyForm
            onIdentified={flow.handleIdentified}
            govbrHabilitado={flow.govbrGlobalHabilitado && Boolean(onGovbrClick)}
            onGovbrLogin={onGovbrClick}
          />
        )}

        {flow.step === "not_found" && (
          <PatientNotFoundPanel
            identificador={flow.identificador}
            onGoToRegister={onGoToRegister}
            onRetry={flow.resetarFluxo}
          />
        )}

        {flow.step === "methods" && flow.identifyData && (
          <div className="space-y-4">
            <div className="flex items-center justify-between gap-2 rounded-lg bg-muted/60 px-3 py-2 text-xs">
              <span className="truncate font-medium text-foreground">{flow.identificador}</span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={flow.resetarFluxo}
                className="h-8 px-2 text-xs"
              >
                Trocar
              </Button>
            </div>

            <form onSubmit={flow.handleEnviarOtp} className="space-y-3">
              {flow.identifyData.telefone_mascarado && (
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Smartphone className="size-4 text-primary shrink-0" aria-hidden="true" />
                  <span>
                    Celular cadastrado:{" "}
                    <Badge variant="outline" className="font-mono text-xs">
                      {flow.identifyData.telefone_mascarado}
                    </Badge>
                  </span>
                </div>
              )}

              <div className="space-y-1.5">
                <Label htmlFor="patient-otp-telefone" className="text-xs font-semibold">
                  Confirme seu celular para receber o código SMS
                </Label>
                <Input
                  id="patient-otp-telefone"
                  type="tel"
                  inputMode="tel"
                  autoComplete="tel-national"
                  placeholder="(11) 98765-4321"
                  value={flow.telefoneInput}
                  onChange={(e) => flow.onTelefoneChange(e.target.value)}
                  disabled={flow.isSendingOtp}
                  className="min-h-[44px]"
                  required
                />
              </div>

              <Button
                type="submit"
                disabled={flow.isSendingOtp}
                className="w-full min-h-[44px] text-sm font-semibold gap-2"
              >
                {flow.isSendingOtp ? (
                  <>
                    <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                    <span>Enviando código SMS…</span>
                  </>
                ) : (
                  <>
                    <Smartphone className="size-4" aria-hidden="true" />
                    <span>Receber código de 6 dígitos por SMS</span>
                  </>
                )}
              </Button>
            </form>

            {flow.mostrarPasskey && (
              <Button
                type="button"
                variant="outline"
                disabled={flow.isAuthenticatingPasskey}
                onClick={flow.triggerPasskey}
                className="w-full min-h-[44px] text-sm font-semibold gap-2"
              >
                <Fingerprint className="size-4 text-primary" aria-hidden="true" />
                <span>
                  {flow.isAuthenticatingPasskey
                    ? "Validando biometria…"
                    : "Entrar com Passkey (Biometria)"}
                </span>
              </Button>
            )}

            {flow.govbrHabilitado && onGovbrClick && (
              <Button
                type="button"
                variant="outline"
                onClick={onGovbrClick}
                className="w-full min-h-[44px] text-sm font-semibold gap-2"
              >
                <ShieldCheck className="size-4 text-primary" aria-hidden="true" />
                <span>Entrar com Gov.br</span>
              </Button>
            )}

            <div className="pt-2 border-t border-border/60 text-center">
              <button
                type="button"
                onClick={() => flow.setStep("password")}
                className="inline-flex items-center justify-center min-h-[44px] px-2 text-xs text-muted-foreground underline underline-offset-4 hover:text-foreground transition-colors"
              >
                Não tem acesso ao celular agora? Entrar com senha
              </button>
            </div>
          </div>
        )}

        {flow.step === "otp_verify" && (
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">
              Código enviado para{" "}
              <strong>{flow.telefoneInput || flow.identifyData?.telefone_mascarado}</strong>.
            </p>
            <PatientOtpVerifyStep
              inputId="patient-otp-codigo"
              label="Código SMS de 6 dígitos"
              telefoneE164={flow.telefoneE164}
              submitLabel="Confirmar e entrar"
              codigoDebug={flow.codigoDebug}
              secondaryActionLabel="Voltar às opções de acesso"
              onSecondaryAction={() => flow.setStep("methods")}
              onAuthenticated={onAuthenticated}
            />
          </div>
        )}

        {flow.step === "password" && (
          <form onSubmit={flow.handleLoginSenha} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="patient-password-identificador" className="text-xs font-semibold">
                CPF ou E-mail
              </Label>
              <Input
                id="patient-password-identificador"
                type="text"
                autoComplete="username"
                value={flow.identificador}
                onChange={(e) => flow.setIdentificador(e.target.value)}
                disabled={flow.isLoggingInPassword}
                className="min-h-[44px]"
                required
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="patient-password-senha" className="text-xs font-semibold">
                Senha de Acesso
              </Label>
              <Input
                id="patient-password-senha"
                type="password"
                autoComplete="current-password"
                placeholder="••••••••"
                value={flow.senha}
                onChange={(e) => flow.onSenhaChange(e.target.value)}
                disabled={flow.isLoggingInPassword}
                className="min-h-[44px]"
                required
              />
            </div>

            <Button
              type="submit"
              disabled={flow.isLoggingInPassword}
              className="w-full min-h-[44px] text-sm font-semibold gap-2"
            >
              <KeyRound className="size-4" aria-hidden="true" />
              <span>{flow.isLoggingInPassword ? "Autenticando…" : "Entrar com senha"}</span>
            </Button>

            <Button
              type="button"
              variant="ghost"
              onClick={() => flow.setStep("methods")}
              className="w-full min-h-[44px] text-xs"
            >
              <ArrowLeft className="size-4 mr-1.5" aria-hidden="true" />
              Voltar para acesso via SMS ou Passkey
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}

export default PatientHybridAuthCard;
