import { createRoute, redirect } from "@tanstack/react-router";
import { HistoryPage } from "@/features/citizen/pages/history-page";
import { getStoredSession, type StoredPatientSession } from "@/lib/session-storage";
import { rootRoute } from "./root";

export const historicoRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/historico",
  beforeLoad: () => {
    const session = getStoredSession();
    if (!session?.token) {
      throw redirect({ to: "/entrar" });
    }
    return { session };
  },
  component: function HistoricoRouteComponent() {
    const { session } = historicoRoute.useRouteContext() as { session: StoredPatientSession };
    return <HistoryPage session={session} />;
  },
});
