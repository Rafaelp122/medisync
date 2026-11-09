import { createRoute, redirect, useNavigate } from "@tanstack/react-router";
import { PainelGestor } from "@/features/telemetry/components/painel-gestor";
import {
  clearStoredManagerSession,
  getStoredManagerSession,
  type StoredManagerSession,
} from "@/lib/session-storage";
import { rootRoute } from "./root";

export const gestorRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/gestor",
  beforeLoad: () => {
    const managerSession = getStoredManagerSession();
    if (!managerSession?.token) {
      throw redirect({ to: "/login" });
    }
    return { managerSession };
  },
  component: GestorPage,
});

function GestorPage() {
  const navigate = useNavigate();
  const { managerSession } = gestorRoute.useRouteContext() as {
    managerSession: StoredManagerSession;
  };

  const handleManagerLogout = () => {
    clearStoredManagerSession();
    navigate({ to: "/login" });
  };

  return (
    <PainelGestor
      token={managerSession.token}
      gestorNome={managerSession.nome}
      onLogout={handleManagerLogout}
    />
  );
}
