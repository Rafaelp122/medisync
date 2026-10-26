import * as React from "react";
import { extractProblemDetail, extractProblemStatus } from "@/api/errors";
import type { VerificarOtpResponse } from "@/api/generated/types.gen";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useVerificarOtp } from "../api/use-verificar-otp";
import { verificarOtpSchema } from "../schemas/onboarding-schema";

export interface VerificarOtpFormProps {
  telefone: string;
  codigoDebug?: string | null;
  onAuthenticated?: (data: VerificarOtpResponse) => void;
  onVoltar?: () => void;
  className?: string;
}

const OTP_SLOTS = [
  "otp-slot-0",
  "otp-slot-1",
  "otp-slot-2",
  "otp-slot-3",
  "otp-slot-4",
  "otp-slot-5",
] as const;

/**
 * Formulário acessível de entrada OTP com 6 slots numéricos, auto-avanço de foco e validação Zod.
 * Regras canônicas: RF-01, US-02 (§5.1) e ADR-011.
 * @see docs/user-stories/US-02-autenticacao-passwordless-otp.md
 */
export function VerificarOtpForm({
  telefone,
  codigoDebug,
  onAuthenticated,
  onVoltar,
  className,
}: VerificarOtpFormProps) {
  const [digits, setDigits] = React.useState<string[]>(["", "", "", "", "", ""]);
  const [validationError, setValidationError] = React.useState<string | null>(null);
  const inputRefs = React.useRef<(HTMLInputElement | null)[]>([]);
  const verificarOtp = useVerificarOtp();

  const isBlocked = verificarOtp.isError && extractProblemStatus(verificarOtp.error) === 429;

  React.useEffect(() => {
    inputRefs.current[0]?.focus();
  }, []);

  const handleDigitChange = (index: number, value: string) => {
    setValidationError(null);
    const cleaned = value.replace(/\D/g, "");
    if (!cleaned) {
      const nextDigits = [...digits];
      nextDigits[index] = "";
      setDigits(nextDigits);
      return;
    }

    if (cleaned.length > 1) {
      // Multiple digits pasted into single slot
      const nextDigits = [...digits];
      for (let j = 0; j < cleaned.length && index + j < 6; j++) {
        nextDigits[index + j] = cleaned[j];
      }
      setDigits(nextDigits);
      const nextFocus = Math.min(index + cleaned.length, 5);
      inputRefs.current[nextFocus]?.focus();
      return;
    }

    const nextDigits = [...digits];
    nextDigits[index] = cleaned;
    setDigits(nextDigits);

    if (index < 5) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handleKeyDown = (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace") {
      const nextDigits = [...digits];
      nextDigits[index] = "";
      setDigits(nextDigits);
      if (index > 0) {
        inputRefs.current[index - 1]?.focus();
      }
    }
  };

  const handlePaste = (e: React.ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    if (!pasted) return;

    const nextDigits = [...digits];
    for (let i = 0; i < 6; i++) {
      nextDigits[i] = pasted[i] || "";
    }
    setDigits(nextDigits);
    const targetIndex = Math.min(pasted.length, 5);
    inputRefs.current[targetIndex]?.focus();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const code = digits.join("");
    const validation = verificarOtpSchema.safeParse({
      telefone,
      codigo: code,
    });
    if (!validation.success) {
      setValidationError(
        validation.error.issues[0]?.message ??
          "O código deve conter exatamente 6 dígitos numéricos",
      );
      return;
    }

    try {
      const response = await verificarOtp.mutateAsync({
        telefone: validation.data.telefone,
        codigo: validation.data.codigo,
      });
      onAuthenticated?.(response);
    } catch {
      inputRefs.current[0]?.focus();
    }
  };

  return (
    <form onSubmit={handleSubmit} className={`space-y-4 ${className ?? ""}`}>
      {verificarOtp.isError && (
        <Alert variant="destructive">
          <AlertTitle>Erro de Verificação</AlertTitle>
          <AlertDescription>{extractProblemDetail(verificarOtp.error)}</AlertDescription>
        </Alert>
      )}

      {validationError && (
        <Alert variant="destructive">
          <AlertDescription>{validationError}</AlertDescription>
        </Alert>
      )}

      <div className="space-y-2">
        <label htmlFor="otp-slot-0" className="text-sm font-medium leading-none">
          Código de 6 dígitos
        </label>
        <p className="text-xs text-muted-foreground">Enviado por SMS para o telefone {telefone}</p>

        {codigoDebug && (
          <div className="p-2.5 text-xs rounded-md bg-secondary/80 border border-primary/20 text-muted-foreground">
            <span className="font-semibold text-primary">Ambiente de Teste:</span> Código SMS
            gerado:{" "}
            <span className="text-foreground tracking-widest text-sm font-mono font-bold">
              {codigoDebug}
            </span>
          </div>
        )}

        <div className="flex gap-2 justify-between pt-2">
          {OTP_SLOTS.map((slotId, idx) => (
            <Input
              key={slotId}
              id={slotId}
              ref={(el) => {
                inputRefs.current[idx] = el;
              }}
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              maxLength={1}
              value={digits[idx]}
              disabled={isBlocked || verificarOtp.isPending}
              onChange={(e) => handleDigitChange(idx, e.target.value)}
              onKeyDown={(e) => handleKeyDown(idx, e)}
              onPaste={handlePaste}
              className="w-12 h-14 text-center text-xl font-semibold focus:ring-2"
              aria-label={`Dígito ${idx + 1}`}
            />
          ))}
        </div>
      </div>

      <Button
        type="submit"
        className="w-full"
        disabled={isBlocked || verificarOtp.isPending || digits.join("").length < 6}
        aria-busy={verificarOtp.isPending}
      >
        {verificarOtp.isPending ? "Verificando..." : "Confirmar e entrar"}
      </Button>

      {onVoltar && (
        <Button
          type="button"
          variant="ghost"
          className="w-full"
          onClick={onVoltar}
          disabled={verificarOtp.isPending}
        >
          Trocar número de telefone
        </Button>
      )}
    </form>
  );
}
