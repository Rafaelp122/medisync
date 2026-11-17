import { useNavigate } from "@tanstack/react-router";
import { ShieldCheck } from "lucide-react";
import { type PerfilStaffAuth, StaffAuthCard } from "@/features/auth/components/staff-auth-card";
import {
  type StoredDoctorSession,
  type StoredManagerSession,
  saveStoredDoctorSession,
  saveStoredManagerSession,
} from "@/lib/session-storage";

export interface InternalLoginPageProps {
  initialPerfil?: PerfilStaffAuth;
}

/**
 * Página isolada de login corporativo da equipe (/interno/login).
 * Contém exclusivamente acesso Médico e Gestor, sem links para a área pública do cidadão.
 */
export function InternalLoginPage({ initialPerfil = "medico" }: InternalLoginPageProps) {
  const navigate = useNavigate();

  const handleDoctorLogin = (session: StoredDoctorSession) => {
    saveStoredDoctorSession(session);
    void navigate({ to: "/medico" });
  };

  const handleManagerLogin = (session: StoredManagerSession) => {
    saveStoredManagerSession(session);
    void navigate({ to: "/gestor" });
  };

  return (
    <div className="w-full max-w-md mx-auto space-y-4">
      <div className="flex items-center justify-center gap-2 text-xs font-medium text-muted-foreground py-1">
        <ShieldCheck className="size-4 text-primary" aria-hidden="true" />
        <span>MediSync Express • Acesso Interno Restrito</span>
      </div>

      <StaffAuthCard
        initialPerfil={initialPerfil}
        onDoctorAuthenticated={handleDoctorLogin}
        onManagerAuthenticated={handleManagerLogin}
      />
    </div>
  );
}

export default InternalLoginPage;
