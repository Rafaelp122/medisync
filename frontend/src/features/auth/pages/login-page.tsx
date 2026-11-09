import { Link, useNavigate } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import {
  type PerfilAuth,
  TripartiteAuthCard,
} from "@/features/auth/components/tripartite-auth-card";
import {
  type StoredDoctorSession,
  type StoredManagerSession,
  type StoredPatientSession,
  saveStoredDoctorSession,
  saveStoredManagerSession,
  saveStoredSession,
} from "@/lib/session-storage";

export interface LoginPageProps {
  initialPerfil?: PerfilAuth;
}

export function LoginPage({ initialPerfil = "medico" }: LoginPageProps) {
  const navigate = useNavigate();

  const handleDoctorLogin = (session: StoredDoctorSession) => {
    saveStoredDoctorSession(session);
    navigate({ to: "/medico" });
  };

  const handleManagerLogin = (session: StoredManagerSession) => {
    saveStoredManagerSession(session);
    navigate({ to: "/gestor" });
  };

  const handlePatientLogin = (session: StoredPatientSession) => {
    saveStoredSession(session);
    navigate({ to: "/fila" });
  };

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

      <TripartiteAuthCard
        initialPerfil={initialPerfil}
        onDoctorAuthenticated={handleDoctorLogin}
        onManagerAuthenticated={handleManagerLogin}
        onPatientAuthenticated={handlePatientLogin}
        onAlternarOtp={() => navigate({ to: "/otp" })}
      />
    </div>
  );
}
