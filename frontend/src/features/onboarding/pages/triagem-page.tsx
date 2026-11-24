import { Link, useNavigate } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import {
  type AcolhimentoConcluidoData,
  ProgressiveOnboardingWizard,
} from "@/features/onboarding/components/progressive-onboarding-wizard";
import {
  getStoredSession,
  isThreePartJwt,
  type StoredPatientSession,
  saveStoredSession,
} from "@/lib/session-storage";

export interface TriagemPageProps {
  session?: StoredPatientSession | null;
}

function mergeSessionPreservingJwt(
  existing: StoredPatientSession | null,
  data: AcolhimentoConcluidoData,
): StoredPatientSession {
  const preserveJwt = Boolean(existing?.token && isThreePartJwt(existing.token));
  return {
    tipo: preserveJwt && existing ? existing.tipo : "acolhimento",
    role: existing?.role || "PACIENTE",
    pacienteId: data.pacienteId,
    atendimentoId: data.atendimentoId,
    prioridadeClinica: data.prioridadeClinica,
    token: preserveJwt && existing ? existing.token : data.token,
    status: "APTO_PARA_CHAMADA",
  };
}

/**
 * Página de Triagem Clínica.
 * Preserva o JWT 3-partes de cidadãos autenticados sem jamais sobrescrevê-lo por intake_token.
 * @see docs/user-stories/US-01-acolhimento-triagem-tcle.md
 */
export function TriagemPage({ session }: TriagemPageProps) {
  const navigate = useNavigate();
  const activeSession = session ?? getStoredSession();

  const handleSessaoIniciada = (data: AcolhimentoConcluidoData) => {
    saveStoredSession(mergeSessionPreservingJwt(getStoredSession() ?? activeSession, data));
  };

  const handleOnboardingFinalizado = (data: AcolhimentoConcluidoData) => {
    saveStoredSession(mergeSessionPreservingJwt(getStoredSession() ?? activeSession, data));
    navigate({ to: "/fila" });
  };

  return (
    <div className="w-full max-w-xl mx-auto space-y-4">
      <div>
        <Link
          to="/home"
          className="inline-flex items-center gap-1.5 text-xs sm:text-sm text-muted-foreground hover:text-foreground transition-colors py-1"
        >
          <ArrowLeft className="h-4 w-4" />
          <span>Voltar ao Portal</span>
        </Link>
      </div>

      <ProgressiveOnboardingWizard
        session={activeSession}
        onSessaoIniciada={handleSessaoIniciada}
        onFinalizar={handleOnboardingFinalizado}
      />
    </div>
  );
}
