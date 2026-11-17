import { Link, useNavigate } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import { PatientRegisterForm } from "@/features/auth/components/patient-register-form";
import { type StoredPatientSession, saveStoredSession } from "@/lib/session-storage";

/**
 * Página pública de auto-cadastro do cidadão (/cadastro) com confirmação OTP inicial.
 */
export function PatientRegisterPage() {
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

      <PatientRegisterForm
        onAuthenticated={handleAuthenticated}
        onGoToLogin={() => void navigate({ to: "/entrar" })}
      />
    </div>
  );
}

export default PatientRegisterPage;
