import { createRoute, Link, redirect } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import type { VerificarOtpResponse } from "@/api/generated/types.gen";
import { AuthOtpCard } from "@/features/onboarding/components/auth-otp-card";
import { IngressoConfirmadoCard } from "@/features/onboarding/components/ingresso-confirmado-card";
import {
  clearStoredSession,
  getStoredDoctorSession,
  getStoredManagerSession,
  getStoredSession,
  type StoredPatientSession,
  saveStoredSession,
} from "@/lib/session-storage";
import { startSafeViewTransition } from "@/lib/view-transitions";
import { rootRoute } from "./root";

export const otpRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/otp",
  beforeLoad: () => {
    const session = getStoredSession();
    if (session?.atendimentoId) {
      throw redirect({ to: "/fila" });
    }

    const doctor = getStoredDoctorSession();
    if (doctor) {
      throw redirect({ to: "/medico" });
    }

    const manager = getStoredManagerSession();
    if (manager) {
      throw redirect({ to: "/gestor" });
    }
  },
  component: OtpPage,
});

function OtpPage() {
  const [session, setSession] = useState<StoredPatientSession | null>(() => getStoredSession());

  const handleOtpAuthenticated = (data: VerificarOtpResponse) => {
    const newSession: StoredPatientSession = {
      tipo: "otp",
      role: data.role ?? "PACIENTE",
      pacienteId: data.paciente_id,
      token: data.access_token,
    };
    saveStoredSession(newSession);
    startSafeViewTransition(() => {
      setSession(newSession);
    });
  };

  const handleEncerrarSessao = () => {
    clearStoredSession();
    startSafeViewTransition(() => {
      setSession(null);
    });
  };

  if (session && !session.atendimentoId) {
    return (
      <div className="w-full max-w-xl mx-auto space-y-4">
        <div>
          <Link
            to="/"
            className="inline-flex items-center gap-1.5 text-xs sm:text-sm text-muted-foreground hover:text-foreground transition-colors py-1"
          >
            <ArrowLeft className="h-4 w-4" />
            <span>Voltar ao Início</span>
          </Link>
        </div>
        <IngressoConfirmadoCard session={session} onEncerrarSessao={handleEncerrarSessao} />
      </div>
    );
  }

  return (
    <div className="w-full max-w-md mx-auto space-y-4">
      <div>
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 text-xs sm:text-sm text-muted-foreground hover:text-foreground transition-colors py-1"
        >
          <ArrowLeft className="h-4 w-4" />
          <span>Voltar ao Início</span>
        </Link>
      </div>

      <AuthOtpCard onAuthenticated={handleOtpAuthenticated} />
    </div>
  );
}
