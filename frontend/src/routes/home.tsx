import { createRoute, redirect } from "@tanstack/react-router";
import { CitizenHomePage } from "@/features/citizen/pages/citizen-home-page";
import { getStoredSession, type StoredPatientSession } from "@/lib/session-storage";
import { rootRoute } from "./root";

export const homeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/home",
  beforeLoad: () => {
    const session = getStoredSession();
    if (!session?.token) {
      throw redirect({ to: "/entrar" });
    }
    return { session };
  },
  component: function HomeRouteComponent() {
    const { session } = homeRoute.useRouteContext() as { session: StoredPatientSession };
    return <CitizenHomePage session={session} />;
  },
});
