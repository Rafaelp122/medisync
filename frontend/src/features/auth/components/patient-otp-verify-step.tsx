import { AlertCircle } from "lucide-react";
import { useState } from "react";
import { extractProblemDetail } from "@/api/errors";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { settings } from "@/config/settings";
import type { StoredPatientSession } from "@/lib/session-storage";
import { sessionTransport } from "@/lib/session-transport";
import { usePatientVerificarOtp } from "../api/use-patient-methods";
import {
  patientOtpVerifySchema,
  toStoredPatientSession,
} from "../schemas/patient-hybrid-auth-schemas";

export interface PatientOtpVerifyStepProps {
  inputId: string;
  label: string;
  telefoneE164: string;
  submitLabel: string;
  codigoDebug?: string | null;
  secondaryActionLabel?: string;
  secondaryActionPending?: boolean;
  onSecondaryAction?: () => void;
  onAuthenticated: (session: StoredPatientSession) => void;
}

/**
 * Etapa compartilhada de confirmação de código OTP de 6 dígitos (login e pós-cadastro).
 * Regras canônicas: RF-01, ADR-005 e ADR-011.
 */
export function PatientOtpVerifyStep({
  inputId,
  label,
  telefoneE164,
  submitLabel,
  codigoDebug,
  secondaryActionLabel,
  secondaryActionPending = false,
  onSecondaryAction,
  onAuthenticated,
}: PatientOtpVerifyStepProps) {
  const [codigo, setCodigo] = useState("");
  const [erroValidacao, setErroValidacao] = useState<string | null>(null);

  const verificarOtp = usePatientVerificarOtp({
    onSuccess: (data) => {
      const session = toStoredPatientSession(data);
      sessionTransport.activatePatientSession(session);
      onAuthenticated(session);
    },
  });

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErroValidacao(null);
    const parsed = patientOtpVerifySchema.safeParse({
      telefone: telefoneE164,
      codigo: codigo.trim(),
    });
    if (!parsed.success) {
      setErroValidacao(parsed.error.issues[0]?.message ?? "Informe o código de 6 dígitos.");
      return;
    }
    verificarOtp.mutate(parsed.data);
  };

  const erroAtivo =
    erroValidacao ?? (verificarOtp.isError ? extractProblemDetail(verificarOtp.error) : null);

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {erroAtivo && (
        <Alert variant="destructive" className="py-2.5 text-xs">
          <AlertCircle className="size-4" aria-hidden="true" />
          <AlertDescription className="text-xs">{erroAtivo}</AlertDescription>
        </Alert>
      )}
      {codigoDebug &&
        (settings.env.isDev || settings.env.isDemoMode || settings.env.mode === "test") && (
          <div
            role="status"
            aria-live="polite"
            className="p-2.5 text-xs rounded-md bg-secondary/80 border border-primary/20 text-muted-foreground"
          >
            {settings.env.isDemoMode && !settings.env.isDev
              ? "Modo Demo — Código SMS: "
              : "Ambiente de Desenvolvimento — Código SMS: "}
            <strong className="font-mono text-foreground tracking-widest">{codigoDebug}</strong>
          </div>
        )}
      <div className="space-y-1.5">
        <Label htmlFor={inputId} className="text-xs font-semibold">
          {label}
        </Label>
        <Input
          id={inputId}
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          autoComplete="one-time-code"
          maxLength={6}
          placeholder="000000"
          value={codigo}
          onChange={(e) => {
            setErroValidacao(null);
            setCodigo(e.target.value.replace(/\D/g, "").slice(0, 6));
          }}
          disabled={verificarOtp.isPending}
          className="min-h-[44px] text-center text-xl font-mono tracking-widest"
          required
        />
      </div>
      <Button
        type="submit"
        disabled={verificarOtp.isPending || codigo.length !== 6}
        className="w-full min-h-[44px] text-sm font-semibold"
      >
        {verificarOtp.isPending ? "Confirmando código…" : submitLabel}
      </Button>
      {secondaryActionLabel && onSecondaryAction && (
        <Button
          type="button"
          variant="ghost"
          disabled={secondaryActionPending || verificarOtp.isPending}
          onClick={onSecondaryAction}
          className="w-full min-h-[44px] text-xs"
        >
          {secondaryActionLabel}
        </Button>
      )}
    </form>
  );
}

export default PatientOtpVerifyStep;
