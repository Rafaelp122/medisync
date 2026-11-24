import { createRoute, lazyRouteComponent, redirect } from "@tanstack/react-router";
import { Suspense } from "react";
import { RoutePendingFallback } from "@/components/route-fallbacks";
import { getStoredSession, type StoredPatientSession } from "@/lib/session-storage";
import { rootRoute } from "./root";

const LazyCitizenHomePage = lazyRouteComponent(
  () => import("@/features/citizen/pages/citizen-home-page"),
  "CitizenHomePage",
);

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
    return (
      <Suspense fallback={<RoutePendingFallback />}>
        <LazyCitizenHomePage session={session} />
      </Suspense>
    );
  },
});
