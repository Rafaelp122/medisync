import { createRoute, redirect } from "@tanstack/react-router";
import { PrescriptionsPage } from "@/features/citizen/pages/prescriptions-page";
import { getStoredSession, type StoredPatientSession } from "@/lib/session-storage";
import { rootRoute } from "./root";

export const receitasRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/receitas",
  beforeLoad: () => {
    const session = getStoredSession();
    if (!session?.token) {
      throw redirect({ to: "/entrar" });
    }
    return { session };
  },
  component: function ReceitasRouteComponent() {
    const { session } = receitasRoute.useRouteContext() as { session: StoredPatientSession };
    return <PrescriptionsPage session={session} />;
  },
});
