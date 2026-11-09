import { createRoute, Link, redirect, useNavigate } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import {
  type PerfilAuth,
  TripartiteAuthCard,
} from "@/features/auth/components/tripartite-auth-card";
import {
  getStoredDoctorSession,
  getStoredManagerSession,
  type StoredDoctorSession,
  type StoredManagerSession,
  type StoredPatientSession,
  saveStoredDoctorSession,
  saveStoredManagerSession,
  saveStoredSession,
} from "@/lib/session-storage";
import { rootRoute } from "./root";

export const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  validateSearch: (search: Record<string, unknown>) => ({
    perfil:
      search.perfil === "medico" || search.perfil === "gestor" || search.perfil === "cidadao"
        ? (search.perfil as PerfilAuth)
        : undefined,
  }),
  beforeLoad: () => {
    const doctor = getStoredDoctorSession();
    if (doctor) throw redirect({ to: "/medico" });

    const manager = getStoredManagerSession();
    if (manager) throw redirect({ to: "/gestor" });
  },
  component: LoginPage,
});

function LoginPage() {
  const search = loginRoute.useSearch();
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
        initialPerfil={search.perfil ?? "medico"}
        onDoctorAuthenticated={handleDoctorLogin}
        onManagerAuthenticated={handleManagerLogin}
        onPatientAuthenticated={handlePatientLogin}
        onAlternarOtp={() => navigate({ to: "/otp" })}
      />
    </div>
  );
}
