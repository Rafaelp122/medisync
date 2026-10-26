import * as React from "react";
import type { VerificarOtpResponse } from "@/api/generated/types.gen";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { SolicitarOtpForm } from "./solicitar-otp-form";
import { VerificarOtpForm } from "./verificar-otp-form";

export interface AuthOtpCardProps {
  onAuthenticated?: (data: VerificarOtpResponse) => void;
  className?: string;
}

/**
 * Card contêiner da jornada de autenticação passwordless OTP do paciente.
 * Regras canônicas: RF-01, US-02 e ADR-011.
 * @see docs/user-stories/US-02-autenticacao-passwordless-otp.md
 */
export function AuthOtpCard({ onAuthenticated, className }: AuthOtpCardProps) {
  const [step, setStep] = React.useState<"solicitar" | "verificar">("solicitar");
  const [telefone, setTelefone] = React.useState("");
  const [codigoDebug, setCodigoDebug] = React.useState<string | null>(null);

  const changeStep = (nextStep: "solicitar" | "verificar") => {
    if (typeof document !== "undefined" && "startViewTransition" in document) {
      document.startViewTransition(() => setStep(nextStep));
    } else {
      setStep(nextStep);
    }
  };

  const handleOtpSent = (data: {
    telefone: string;
    expiraEmSegundos: number;
    codigoDebug?: string | null;
  }) => {
    setTelefone(data.telefone);
    setCodigoDebug(data.codigoDebug ?? null);
    changeStep("verificar");
  };

  const handleVoltar = () => {
    changeStep("solicitar");
  };

  return (
    <Card className={`w-full max-w-md mx-auto shadow-lg border ${className ?? ""}`}>
      <CardHeader className="text-center">
        <CardTitle className="text-2xl font-bold tracking-tight text-primary">
          MediSync Express
        </CardTitle>
        <CardDescription>
          {step === "solicitar"
            ? "Acesso rápido sem senhas para pacientes"
            : "Confirme sua identidade com o código recebido"}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {step === "solicitar" ? (
          <SolicitarOtpForm onOtpSent={handleOtpSent} />
        ) : (
          <VerificarOtpForm
            telefone={telefone}
            codigoDebug={codigoDebug}
            onAuthenticated={onAuthenticated}
            onVoltar={handleVoltar}
          />
        )}
      </CardContent>
    </Card>
  );
}
