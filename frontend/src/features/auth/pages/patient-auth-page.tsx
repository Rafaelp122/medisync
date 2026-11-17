import { Link, useNavigate } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import { PatientHybridAuthCard } from "@/features/auth/components/patient-hybrid-auth-card";
import { type StoredPatientSession, saveStoredSession } from "@/lib/session-storage";

/**
 * Página pública de entrada do cidadão (/entrar) no fluxo IAM Híbrido.
 * Redireciona para /fila quando houver atendimento ativo ou para /home.
 */
export function PatientAuthPage() {
  const navigate = useNavigate();

  const handleAuthenticated = (session: StoredPatientSession) => {
    saveStoredSession(session);
    if (session.atendimentoId) {
      void navigate({ to: "/fila" });
      return;
    }
    void navigate({ to: "/home" });
  };

  return (
    <div className="w-full max-w-md mx-auto space-y-4">
      <div>
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 text-xs sm:text-sm text-muted-foreground hover:text-foreground transition-colors py-1 min-h-[44px]"
        >
          <ArrowLeft className="size-4" aria-hidden="true" />
          <span>Voltar ao Início</span>
        </Link>
      </div>

      <PatientHybridAuthCard
        onAuthenticated={handleAuthenticated}
        onGoToRegister={() => void navigate({ to: "/cadastro" })}
      />

      <p className="text-center text-xs text-muted-foreground">
        Ainda não tem cadastro?{" "}
        <Link
          to="/cadastro"
          className="font-semibold text-primary underline underline-offset-4 hover:text-primary/80"
        >
          Criar conta gratuita
        </Link>
      </p>
    </div>
  );
}

export default PatientAuthPage;
