import { createRoute, lazyRouteComponent, redirect } from "@tanstack/react-router";
import { Suspense } from "react";
import { RoutePendingFallback } from "@/components/route-fallbacks";
import { getStoredSession, type StoredPatientSession } from "@/lib/session-storage";
import { rootRoute } from "./root";

const LazyPrescriptionsPage = lazyRouteComponent(
  () => import("@/features/citizen/pages/prescriptions-page"),
  "PrescriptionsPage",
);

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
    return (
      <Suspense fallback={<RoutePendingFallback />}>
        <LazyPrescriptionsPage session={session} />
      </Suspense>
    );
  },
});
