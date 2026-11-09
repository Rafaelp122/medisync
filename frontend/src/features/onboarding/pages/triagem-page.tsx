import { Link, useNavigate } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import {
  type AcolhimentoConcluidoData,
  ProgressiveOnboardingWizard,
} from "@/features/onboarding/components/progressive-onboarding-wizard";
import { type StoredPatientSession, saveStoredSession } from "@/lib/session-storage";

export function TriagemPage() {
  const navigate = useNavigate();

  const handleSessaoIniciada = (data: AcolhimentoConcluidoData) => {
    const newSession: StoredPatientSession = {
      tipo: "acolhimento",
      role: "PACIENTE",
      pacienteId: data.pacienteId,
      atendimentoId: data.atendimentoId,
      prioridadeClinica: data.prioridadeClinica,
      token: data.token,
      status: "APTO_PARA_CHAMADA",
    };
    saveStoredSession(newSession);
  };

  const handleOnboardingFinalizado = (data: AcolhimentoConcluidoData) => {
    const newSession: StoredPatientSession = {
      tipo: "acolhimento",
      role: "PACIENTE",
      pacienteId: data.pacienteId,
      atendimentoId: data.atendimentoId,
      prioridadeClinica: data.prioridadeClinica,
      token: data.token,
      status: "APTO_PARA_CHAMADA",
    };
    saveStoredSession(newSession);
    navigate({ to: "/fila" });
  };

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

      <ProgressiveOnboardingWizard
        onTrocarParaOtp={() => navigate({ to: "/otp" })}
        onSessaoIniciada={handleSessaoIniciada}
        onFinalizar={handleOnboardingFinalizado}
      />
    </div>
  );
}
